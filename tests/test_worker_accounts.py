"""Tài khoản Claude trong worker: _Accounts (đọc file, chọn, nghỉ, lỗi) và
_StepWatch (nhìn stream-json để biết có được chạy lại bằng tài khoản khác không).

Chạy:  python -m pytest tests/test_worker_accounts.py -q
"""
import os
import sys
import time
from pathlib import Path

import pytest

NL = chr(10)
SOON = int(time.time()) + 3600      # mốc reset hợp lệ: _epoch chỉ nhận trong [-1 ngày, +30 ngày]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import worker  # noqa: E402


_WRITE_N = [0]


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    # mtime độ phân giải có thể là 1s — ép mỗi lần ghi 1 mốc tăng dần để _load() thấy file đổi
    _WRITE_N[0] += 1
    st = path.stat()
    os.utime(path, (st.st_atime, 1_700_000_000 + 10 * _WRITE_N[0]))


TWO = '''
[[account]]
name  = "pro-1"
token = "sk-ant-oat01-one"

[[account]]
name  = "pro-2"
token = "sk-ant-oat01-two"

[[account]]
name  = "unfilled"
token = "sk-ant-oat01-..."
'''


# ── _Accounts ────────────────────────────────────────────────────────────────

def test_no_file_means_empty_and_env_untouched(tmp_path):
    acc = worker._Accounts(tmp_path / "missing.toml")
    assert len(acc) == 0
    assert acc.pick("pro-1") is None
    assert acc.snapshot() == []


def test_pick_preferred_then_fallback_first_ready(tmp_path):
    f = tmp_path / "acc.toml"
    _write(f, TWO)
    acc = worker._Accounts(f)
    assert len(acc) == 2                       # dòng mẫu "..." bị bỏ
    assert acc.pick("pro-2").name == "pro-2"
    assert acc.pick("xyz").name == "pro-1"     # tên lạ → tài khoản đầu tiên
    assert acc.pick(None).name == "pro-1"
    assert acc.pick("pro-1").env() == {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-one"}


def test_cool_skips_account_until_reset_and_snapshot_hides_token(tmp_path):
    f = tmp_path / "acc.toml"
    _write(f, TWO)
    acc = worker._Accounts(f)
    acc.cool("pro-1", time.time() + 600)
    assert acc.pick("pro-1").name == "pro-2"   # ưu tiên đang nghỉ → tài khoản kế
    snap = acc.snapshot()
    assert [s["state"] for s in snap] == ["cooling", "ready"]
    assert snap[0]["until"] is not None
    assert all("token" not in s for s in snap)
    assert acc.earliest_reset() is not None

    acc.cool("pro-2", None)                    # không biết resetsAt → nghỉ mặc định
    assert acc.pick(None) is None
    # hết giờ nghỉ → dùng lại (giả lập thời gian trôi; cool() với mốc đã qua thì ngược lại: nghỉ mặc định)
    acc._items[0].cooling_until = time.time() - 1
    assert acc.pick(None).name == "pro-1"


def test_error_cleared_on_file_edit_but_cooling_kept(tmp_path):
    f = tmp_path / "acc.toml"
    _write(f, TWO)
    acc = worker._Accounts(f)
    acc.mark_error("pro-1", "token hỏng")
    acc.cool("pro-2", time.time() + 600)
    assert acc.pick(None) is None
    assert acc.snapshot()[0] == {"name": "pro-1", "state": "error", "until": None, "note": "token hỏng"}

    _write(f, TWO.replace("one", "one-new"))   # người dùng sửa token
    assert acc.pick(None).name == "pro-1"      # lỗi được xoá
    assert acc.snapshot()[1]["state"] == "cooling"   # nghỉ quota vẫn giữ


# ── _StepWatch ───────────────────────────────────────────────────────────────

def _assistant(*blocks):
    return {"type": "assistant", "message": {"content": list(blocks)}}


def test_watch_tool_use_and_rejected_event():
    w = worker._StepWatch()
    w.feed(_assistant({"type": "text", "text": "hi"}))
    assert not w.tool_used
    w.feed(_assistant({"type": "tool_use", "name": "Edit", "input": {}}))
    assert w.tool_used

    w.feed({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "utilization": 0.9}})
    assert not w.limit_hit
    w.feed({"type": "rate_limit_event",
            "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour", "resetsAt": SOON}})
    assert w.limit_hit and w.limit_type == "five_hour" and w.resets_at == SOON


def test_watch_reset_ms_vs_seconds():
    assert worker._epoch(SOON) == SOON
    assert worker._epoch(SOON * 1000) == SOON
    assert worker._epoch(SOON - 5 * 86400) is None      # 5 ngày trước → rác
    assert worker._epoch("abc") is None
    assert worker._epoch(None) is None


def test_watch_error_result_text_old_cli_format():
    w = worker._StepWatch()
    w.feed({"type": "result", "subtype": "error_during_execution", "is_error": True,
            "result": f"Claude AI usage limit reached|{SOON}"})
    assert w.limit_hit and w.resets_at == SOON and not w.auth_failed


def test_watch_success_result_never_trips():
    w = worker._StepWatch()
    w.feed({"type": "result", "subtype": "success", "is_error": False,
            "result": "Implemented rate limit middleware and authentication_error handling"})
    assert not w.limit_hit and not w.auth_failed


def test_watch_auth_failure():
    w = worker._StepWatch()
    w.feed({"type": "result", "subtype": "error_during_execution", "is_error": True,
            "result": "", "errors": ["authentication_error: OAuth token expired"]})
    assert w.auth_failed and not w.limit_hit
    w2 = worker._StepWatch()
    w2.feed_text("API Error: 401 Invalid authentication credentials")
    assert w2.auth_failed


def test_watch_stderr_rate_limit_without_reset():
    w = worker._StepWatch()
    w.feed_text("You've hit your limit · resets 3pm")
    assert w.limit_hit and w.resets_at is None


# ── _run_step_job: vòng lặp chuyển tài khoản, chạy với CLI giả ───────────────
# CLI giả đọc CLAUDE_CODE_OAUTH_TOKEN để quyết định: token "one" → bị chặn quota
# (có/không tool_use tuỳ FAKE_TOOL_USE), token "two" → xong. Nhờ vậy test được
# đúng nhánh trong _run_step_job mà không cần Claude thật.

FAKE_CLI = r'''
import json, os, sys
tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
def emit(ev): print(json.dumps(ev), flush=True)
emit({"type": "system", "subtype": "init", "model": "fake"})
if os.environ.get("FAKE_TOOL_USE") == "1":
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {}}]}})
if tok.endswith("one"):
    emit({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour",
                                                          "resetsAt": int(os.environ.get("FAKE_RESETS_AT") or (__import__("time").time() + 3600))}})
    emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "usage limit reached", "duration_ms": 5})
    sys.exit(1)
if os.environ.get("FAKE_MODE") == "noise401":     # bước lỗi thường, MCP in "401" ra stderr
    emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "Tool failed", "duration_ms": 5})
    print("mcp-server: HTTP status 401 Unauthorized", file=sys.stderr)
    sys.exit(1)
if os.environ.get("FAKE_MODE") == "max_turns":    # hết lượt, Claude đang nói về rate limit của task
    emit({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "Implementing the rate limit middleware...", "duration_ms": 5})
    sys.exit(1)
if tok.endswith("bad"):
    emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "", "errors": ["authentication_error: OAuth token expired"], "duration_ms": 5})
    sys.exit(1)
emit({"type": "result", "subtype": "success", "is_error": False, "result": "ok " + tok[-3:], "duration_ms": 5, "num_turns": 1})
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    # worker gọi `<binary> -p <prompt> ...` nên cần 1 file chạy được đứng trước -p:
    # .cmd trên Windows (giống claude.CMD của npm), shell script nơi khác.
    if os.name == "nt":
        launcher = tmp_path / "fake_claude.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*{os.linesep}', encoding="utf-8")
    else:
        launcher = tmp_path / "fake_claude"
        launcher.write_text(f'#!/bin/sh{chr(10)}exec "{sys.executable}" "{script}" "$@"{chr(10)}', encoding="utf-8")
        launcher.chmod(0o755)
    acc_file = tmp_path / "acc.toml"
    _write(acc_file, TWO)
    monkeypatch.setattr(worker, "ACCOUNTS", worker._Accounts(acc_file))
    monkeypatch.setattr(worker, "_resolve_claude", lambda: str(launcher))
    monkeypatch.setattr(worker, "CLAUDE_ARGS", [])
    monkeypatch.setattr(worker, "STEP_TIMEOUT_S", 30)
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(worker, "_req", lambda path, body=None, method="GET": calls.append((path, body or {})) or None)
    return calls


def _job(**over):
    return {"id": 7, "run_id": 1, "node_id": "n", "node_label": "Bước", "prompt": "x",
            "tool": "claude", "model": None, "add_dirs": [], "claude_account": None,
            "claude_auto_switch": True, **over}


def _complete_of(calls):
    return next(b for p, b in calls if p.endswith("/complete"))


def _log_of(calls):
    return "".join(b.get("lines", "") for p, b in calls if p.endswith("/progress"))


def test_switch_and_rerun_when_no_tool_use(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    worker._run_step_job(_job(claude_account="pro-1"))
    done = _complete_of(fake_cli)
    assert done["status"] == "done" and done["output"] == "ok two"
    log = _log_of(fake_cli)
    assert "🔑 Tài khoản Claude: pro-1" in log and "🔑 Tài khoản Claude: pro-2" in log
    assert "🔁 pro-1 hết quota 5 giờ (reset" in log and "→ chuyển sang pro-2" in log
    snap = {a["name"]: a["state"] for a in worker.ACCOUNTS.snapshot()}
    assert snap == {"pro-1": "cooling", "pro-2": "ready"}


def test_fail_with_hint_when_tool_already_used(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "1")
    worker._run_step_job(_job(claude_account="pro-1"))
    done = _complete_of(fake_cli)
    assert done["status"] == "failed"
    assert "pro-1" in done["error"] and "hết quota" in done["error"] and "pro-2" in done["error"]
    assert "🔁" not in _log_of(fake_cli)                     # không chạy chồng
    assert worker.ACCOUNTS.snapshot()[0]["state"] == "cooling"


def test_no_switch_when_auto_off(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    worker._run_step_job(_job(claude_account="pro-1", claude_auto_switch=False))
    done = _complete_of(fake_cli)
    assert done["status"] == "failed" and "Tự chuyển đang tắt" in done["error"]
    assert worker.ACCOUNTS.snapshot()[0]["state"] == "cooling"


def test_auth_failure_marks_error_and_switches(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    _write(tmp_path / "acc.toml", TWO.replace("sk-ant-oat01-one", "sk-ant-oat01-bad"))
    worker._run_step_job(_job(claude_account="pro-1"))
    assert _complete_of(fake_cli)["status"] == "done"
    snap = worker.ACCOUNTS.snapshot()
    assert snap[0]["state"] == "error" and "setup-token" in snap[0]["note"]


def test_all_accounts_exhausted(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    _write(tmp_path / "acc.toml", TWO.replace("sk-ant-oat01-two", "sk-ant-oat01-one"))   # cả 2 đều bị chặn
    worker._run_step_job(_job())
    done = _complete_of(fake_cli)
    assert done["status"] == "failed" and "Không còn tài khoản nào sẵn sàng (reset" in done["error"]
    assert all(a["state"] == "cooling" for a in worker.ACCOUNTS.snapshot())
    assert _log_of(fake_cli).count("🔁") == 1                # pro-1 → pro-2, rồi hết


def test_no_account_file_runs_as_before(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(worker, "ACCOUNTS", worker._Accounts(tmp_path / "missing.toml"))
    worker._run_step_job(_job())
    done = _complete_of(fake_cli)
    assert done["status"] == "done" and done["output"] == "ok"   # không token → CLI giả in "ok "
    assert "🔑" not in _log_of(fake_cli)


# ── Vá sau review ────────────────────────────────────────────────────────────

def test_cool_with_past_reset_still_benches_account(tmp_path):
    f = tmp_path / "acc.toml"; _write(f, TWO)
    acc = worker._Accounts(f)
    acc.cool("pro-1", time.time() - 100)          # resetsAt đã qua (lệch giờ máy)
    assert acc.pick("pro-1").name == "pro-2"      # vẫn phải bị loại, không thì vòng chuyển chọn lại chính nó


def test_past_reset_switches_to_other_account(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    monkeypatch.setenv("FAKE_RESETS_AT", str(int(time.time()) - 60))
    worker._run_step_job(_job(claude_account="pro-1"))
    assert _complete_of(fake_cli)["status"] == "done"
    assert "→ chuyển sang pro-2" in _log_of(fake_cli)


def test_epoch_garbage_never_breaks_snapshot(tmp_path):
    assert worker._epoch(1.7e15) is None           # micro-giây → ngoài cửa sổ hợp lệ
    assert worker._epoch(-5) is None
    assert worker._iso(1e18) is None and worker._reset_txt(1e18) == ""
    f = tmp_path / "acc.toml"; _write(f, TWO)
    acc = worker._Accounts(f)
    assert len(acc) == 2
    acc._items[0].cooling_until = 1e18             # kể cả lọt vào bộ nhớ, snapshot không được ném
    assert acc.snapshot()[0]["until"] is None


def test_reset_txt_shows_date_when_far():
    assert "/" not in worker._reset_txt(time.time() + 3600)
    assert "/" in worker._reset_txt(time.time() + 3 * 86400)   # quota 7 ngày → phải thấy ngày


def test_malformed_toml_keeps_previous_list(tmp_path, capsys):
    f = tmp_path / "acc.toml"; _write(f, TWO)
    acc = worker._Accounts(f)
    acc.cool("pro-1", time.time() + 600)
    _write(f, "[[account]" + NL + "name = 'x'")   # gõ dở
    assert [a["name"] for a in acc.snapshot()] == ["pro-1", "pro-2"]
    assert acc.snapshot()[0]["state"] == "cooling"                 # trạng thái không bị xoá
    assert "lỗi cú pháp" in capsys.readouterr().out
    _write(f, "account = 5")                                       # sai kiểu
    assert len(acc) == 2
    _write(f, "[account]" + NL + "name='solo'" + NL + "token='sk-ant-oat01-solo'")   # [account] đơn → 1 tài khoản
    assert [a["name"] for a in acc.snapshot()] == ["solo"]


def test_duplicate_name_dropped(tmp_path):
    dup = TWO + NL + "[[account]]" + NL + 'name = "pro-1"' + NL + 'token = "sk-ant-oat01-dup"' + NL
    f = tmp_path / "acc.toml"; _write(f, dup)
    acc = worker._Accounts(f)
    assert [a["name"] for a in acc.snapshot()] == ["pro-1", "pro-2"]
    assert acc.pick("pro-1").token == "sk-ant-oat01-one"           # giữ dòng đầu


def test_file_exists_flag(tmp_path):
    acc = worker._Accounts(tmp_path / "none.toml")
    assert len(acc) == 0 and acc.exists is False
    _write(tmp_path / "none.toml", "# rỗng")
    assert len(acc) == 0 and acc.exists is True


def test_strict_pick_when_auto_off(tmp_path):
    f = tmp_path / "acc.toml"; _write(f, TWO)
    acc = worker._Accounts(f)
    acc.cool("pro-1", time.time() + 600)
    assert acc.pick("pro-1", strict=True) is None                  # không lén dùng pro-2
    assert acc.pick("xyz", strict=True).name == "pro-2"            # tên lạ vẫn rơi về đầu tiên


def test_auto_off_chosen_cooling_fails_without_running(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0")
    worker.ACCOUNTS.cool("pro-1", time.time() + 600)
    worker._run_step_job(_job(claude_account="pro-1", claude_auto_switch=False))
    done = _complete_of(fake_cli)
    assert done["status"] == "failed" and "pro-1" in done["error"] and "Tự chuyển đang tắt" in done["error"]
    assert "🔑" not in _log_of(fake_cli)                            # không spawn gì cả


def test_401_noise_in_stderr_does_not_brick_account(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0"); monkeypatch.setenv("FAKE_MODE", "noise401")
    worker._run_step_job(_job(claude_account="pro-2"))
    assert _complete_of(fake_cli)["status"] == "failed"
    assert worker.ACCOUNTS.snapshot()[1]["state"] == "ready"        # không bị đánh dấu lỗi
    assert "🔁" not in _log_of(fake_cli)


def test_max_turns_text_is_not_a_quota_hit(fake_cli, monkeypatch):
    monkeypatch.setenv("FAKE_TOOL_USE", "0"); monkeypatch.setenv("FAKE_MODE", "max_turns")
    worker._run_step_job(_job(claude_account="pro-2"))
    assert _complete_of(fake_cli)["status"] == "failed"
    assert worker.ACCOUNTS.snapshot()[1]["state"] == "ready"
    assert "🔁" not in _log_of(fake_cli)


def test_stderr_auth_only_when_cli_died_early():
    w = worker._StepWatch()
    w.feed({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "x"})
    w.feed_text("status 401 Unauthorized", from_stderr=True)
    assert not w.auth_failed                                       # có result → 401 là của MCP
    w2 = worker._StepWatch()
    w2.feed_text("Not logged in · Please run /login", from_stderr=True)
    assert w2.auth_failed                                          # chết ngay, chưa có result → token
    w3 = worker._StepWatch()
    w3.feed_text("Invalid authentication token supplied", from_stderr=True)
    assert w3.auth_failed
    w4 = worker._StepWatch()
    w4.feed_text("scanned 401 files", from_stderr=True)
    assert not w4.auth_failed


def test_watch_feed_tolerates_odd_shapes():
    # _run_streaming còn bọc feed() trong try/except; ở đây là các dạng lạ hay gặp phải qua sạch
    w = worker._StepWatch()
    for ev in ({"type": "assistant", "message": None}, {"type": "assistant", "message": {"content": None}},
               {"type": "result", "subtype": "success", "errors": None}, {"type": "rate_limit_event"}):
        w.feed(ev)
    assert not (w.tool_used or w.limit_hit or w.auth_failed)


def test_redact_known_tokens(fake_cli):
    assert worker._redact("token=sk-ant-oat01-one ok") == "token=*** ok"
    assert worker._redact("nothing") == "nothing"
