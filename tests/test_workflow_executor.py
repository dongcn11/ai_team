"""Executor — dừng ở gate, resume được, và không cho Claude chạy khi thiếu người bấm.

Không gọi CLI thật: node `claude` được monkeypatch, node `code` dùng handler
đăng ký trong test. Dùng `asyncio.run()` để không cần pytest-asyncio.
"""

import asyncio
import time
from pathlib import Path

import pytest

from ai_team import quota
from ai_team.workflow import executor as ex
from ai_team.workflow import graph as g


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _quota_sandbox(tmp_path, monkeypatch):
    """Quota state ra file tạm — không đụng counter thật ở ~. Tắt khoảng nghỉ."""
    monkeypatch.setenv("CLAUDE_QUOTA_STATE", str(tmp_path / "quota.json"))
    monkeypatch.setenv("CLAUDE_MIN_GAP_S", "0")
    monkeypatch.setenv("CLAUDE_MAX_PER_5H", "50")
    monkeypatch.setenv("CLAUDE_MAX_PER_DAY", "50")
    quota.reset_for_tests()
    yield


@pytest.fixture
def claude_calls(monkeypatch):
    """Thay _run_claude_cli bằng fake, trả list node id đã gọi."""
    calls: list[str] = []

    async def fake(node, ctx):
        calls.append(node.id)
        return f"claude-output:{node.id}"

    monkeypatch.setattr(ex, "_run_claude_cli", fake)
    return calls


def wf(nodes, edges):
    return g.parse({"name": "t", "nodes": nodes, "edges": edges})


def edge(a, b):
    return {"from": a, "to": b}


def run(graph, state=None, ctx=None):
    return asyncio.run(ex.advance(graph, state, ctx))


LISTENER = {"id": "trig", "type": "slack_listener"}
MANUAL = {"id": "trig", "type": "manual_trigger"}
GATE = {"id": "gate", "type": "manual_gate"}
CLAUDE = {"id": "cl", "type": "task", "runtime": "claude", "prompt": "fix {{payload.issue}}"}


# ── Happy path không có Claude ─────────────────────────────────────────────────

def test_chay_het_khi_khong_co_gate(tmp_path):
    @ex.handler("echo_a")
    def _a(node, ctx):
        return "A"

    @ex.handler("echo_b")
    def _b(node, ctx):
        return ctx.outputs.get("n1", "") + "B"

    graph = wf(
        [LISTENER,
         {"id": "n1", "type": "task", "runtime": "code", "handler": "echo_a"},
         {"id": "n2", "type": "task", "runtime": "code", "handler": "echo_b"}],
        [edge("trig", "n1"), edge("n1", "n2")],
    )
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path, trigger_type="slack_listener"))
    assert res.status == g.DONE
    assert res.outputs["n2"] == "AB"
    assert res.state == {"trig": g.DONE, "n1": g.DONE, "n2": g.DONE}


def test_render_prompt_tu_payload_va_outputs(tmp_path):
    seen = {}

    @ex.handler("capture")
    def _c(node, ctx):
        seen["rendered"] = ex.render("issue={{payload.issue}} prev={{outputs.n1}}", ctx)
        return ""

    @ex.handler("first")
    def _f(node, ctx):
        return "X"

    graph = wf(
        [MANUAL,
         {"id": "n1", "type": "task", "runtime": "code", "handler": "first"},
         {"id": "n2", "type": "task", "runtime": "code", "handler": "capture"}],
        [edge("trig", "n1"), edge("n1", "n2")],
    )
    run(graph, ctx=ex.RunContext(work_dir=tmp_path, payload={"issue": "42"}))
    assert seen["rendered"] == "issue=42 prev=X"


# ── Gate dừng và resume ───────────────────────────────────────────────────────

def test_gate_dung_lai_claude_khong_chay(tmp_path, claude_calls):
    graph = wf([LISTENER, GATE, CLAUDE],
               [edge("trig", "gate"), edge("gate", "cl")])
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path, trigger_type="slack_listener"))

    assert res.status == g.WAITING
    assert res.waiting_on == ["gate"]
    assert res.state["cl"] == g.PENDING
    assert claude_calls == []                      # điểm quan trọng nhất


def test_resume_sau_khi_duyet_thi_claude_chay(tmp_path, claude_calls):
    graph = wf([LISTENER, GATE, CLAUDE],
               [edge("trig", "gate"), edge("gate", "cl")])
    ctx = ex.RunContext(work_dir=tmp_path, trigger_type="slack_listener")
    first = run(graph, ctx=ctx)
    assert first.status == g.WAITING

    # Người bấm duyệt → API ghi approval → executor chạy lại
    state = dict(first.state)
    state["gate"] = g.PENDING
    ctx2 = ex.RunContext(work_dir=tmp_path, trigger_type="slack_listener",
                         approvals={"gate": time.time()})
    second = run(graph, state=state, ctx=ctx2)

    assert second.status == g.DONE
    assert claude_calls == ["cl"]
    assert second.outputs["cl"] == "claude-output:cl"


def test_manual_trigger_can_approval_moi_chay_claude(tmp_path, claude_calls):
    """trigger_type do client khai không tự mở quyền — phải có row approval."""
    graph = wf([MANUAL, CLAUDE], [edge("trig", "cl")])

    no_approval = run(graph, ctx=ex.RunContext(work_dir=tmp_path,
                                              trigger_type="manual_trigger"))
    assert no_approval.status == g.FAILED
    assert claude_calls == []
    assert "không có cú bấm duyệt" in no_approval.errors["cl"]

    with_approval = run(graph, ctx=ex.RunContext(
        work_dir=tmp_path, trigger_type="manual_trigger",
        approvals={"trig": time.time()},
    ))
    assert with_approval.status == g.DONE
    assert claude_calls == ["cl"]


# ── Chặn ở tầng executor (defense in depth) ───────────────────────────────────

def test_graph_vi_pham_bi_chan_du_co_approval(tmp_path, claude_calls):
    """DB bị sửa tay bỏ gate: dù đưa approval vào, executor vẫn từ chối."""
    graph = wf([LISTENER, CLAUDE], [edge("trig", "cl")])
    res = run(graph, ctx=ex.RunContext(
        work_dir=tmp_path, trigger_type="slack_listener",
        approvals={"cl": time.time(), "trig": time.time()},
    ))
    assert res.status == g.FAILED
    assert claude_calls == []
    assert "auto-trigger kích được trực tiếp" in res.errors["cl"]


def test_approval_qua_cu_thi_chan(tmp_path, claude_calls, monkeypatch):
    monkeypatch.setattr(ex, "GATE_MAX_AGE_S", 600)
    graph = wf([LISTENER, GATE, CLAUDE], [edge("trig", "gate"), edge("gate", "cl")])
    state = g.initial_state(graph)
    state["trig"] = g.DONE

    res = run(graph, state=state, ctx=ex.RunContext(
        work_dir=tmp_path, trigger_type="slack_listener",
        approvals={"gate": time.time() - 7200},        # bấm 2 giờ trước
    ))
    assert res.status == g.FAILED
    assert claude_calls == []
    assert "không còn ai ngồi" in res.errors["cl"]


def test_quota_het_thi_node_fail_khong_goi_claude(tmp_path, claude_calls, monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_PER_DAY", "1")
    graph = wf([MANUAL, CLAUDE], [edge("trig", "cl")])
    ctx_kwargs = dict(work_dir=tmp_path, trigger_type="manual_trigger",
                      approvals={"trig": time.time()})

    first = run(graph, ctx=ex.RunContext(**ctx_kwargs))
    assert first.status == g.DONE
    assert claude_calls == ["cl"]

    second = run(graph, ctx=ex.RunContext(**ctx_kwargs))
    assert second.status == g.FAILED
    assert claude_calls == ["cl"]                   # không gọi thêm
    assert "trần" in second.errors["cl"]


def test_hai_node_claude_khong_bao_gio_chay_song_song(tmp_path, monkeypatch):
    """MAX_PARALLEL=2 nên cả 2 vào cùng batch; semaphore trong quota phải ép tuần tự."""
    windows: list[tuple[float, float]] = []

    async def fake(node, ctx):
        start = time.monotonic()
        await asyncio.sleep(0.05)
        windows.append((start, time.monotonic()))
        return ""

    monkeypatch.setattr(ex, "_run_claude_cli", fake)

    graph = wf(
        [MANUAL,
         {"id": "c1", "type": "task", "runtime": "claude"},
         {"id": "c2", "type": "task", "runtime": "claude"}],
        [edge("trig", "c1"), edge("trig", "c2")],
    )
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path, trigger_type="manual_trigger",
                                       approvals={"trig": time.time()}))
    assert res.status == g.DONE
    assert len(windows) == 2
    (s1, e1), (s2, e2) = sorted(windows)
    assert s2 >= e1, f"2 phiên Claude chồng nhau: {windows}"


# ── Fail propagation ──────────────────────────────────────────────────────────

def test_node_fail_thi_downstream_bi_skip(tmp_path):
    @ex.handler("no")
    def _no(node, ctx):
        raise RuntimeError("bang")

    @ex.handler("ok")
    def _ok(node, ctx):
        return "ok"

    graph = wf(
        [MANUAL,
         {"id": "bad", "type": "task", "runtime": "code", "handler": "no"},
         {"id": "after", "type": "task", "runtime": "code", "handler": "ok"},
         {"id": "far", "type": "task", "runtime": "code", "handler": "ok"}],
        [edge("trig", "bad"), edge("bad", "after"), edge("after", "far")],
    )
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path))
    assert res.status == g.FAILED
    assert res.state["bad"] == g.FAILED
    assert res.state["after"] == g.SKIPPED
    assert res.state["far"] == g.SKIPPED
    assert "bang" in res.errors["bad"]


def test_nhanh_khac_van_chay_khi_mot_nhanh_fail(tmp_path):
    @ex.handler("no2")
    def _no(node, ctx):
        raise RuntimeError("x")

    @ex.handler("ok2")
    def _ok(node, ctx):
        return "fine"

    graph = wf(
        [MANUAL,
         {"id": "bad", "type": "task", "runtime": "code", "handler": "no2"},
         {"id": "good", "type": "task", "runtime": "code", "handler": "ok2"}],
        [edge("trig", "bad"), edge("trig", "good")],
    )
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path))
    assert res.state["good"] == g.DONE
    assert res.outputs["good"] == "fine"
    assert res.status == g.FAILED


def test_handler_thieu_thi_bao_ro(tmp_path):
    graph = wf([MANUAL, {"id": "x", "type": "task", "runtime": "code", "handler": "khong-co"}],
               [edge("trig", "x")])
    res = run(graph, ctx=ex.RunContext(work_dir=tmp_path))
    assert res.status == g.FAILED
    assert "chưa đăng ký" in res.errors["x"]


# ── Quota module ──────────────────────────────────────────────────────────────

def test_quota_dem_qua_nhieu_lan_goi():
    async def burn(n):
        for _ in range(n):
            async with quota.claude_slot():
                pass

    asyncio.run(burn(3))
    u = quota.usage()
    assert u["used_5h"] == 3
    assert u["used_day"] == 3


def test_quota_persist_qua_lan_doc_moi(monkeypatch):
    async def one():
        async with quota.claude_slot():
            pass

    asyncio.run(one())
    assert quota.usage()["used_day"] == 1
    # đọc lại từ file, không dựa vào state trong memory
    assert quota._load()["calls"]


def test_quota_vuot_tran_5h(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_PER_5H", "2")

    async def burn():
        for _ in range(3):
            async with quota.claude_slot():
                pass

    with pytest.raises(quota.QuotaExceeded, match="5 giờ"):
        asyncio.run(burn())


def test_reset_for_tests_doi_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_QUOTA_STATE", raising=False)
    with pytest.raises(RuntimeError):
        quota.reset_for_tests()
