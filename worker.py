"""
AI Team Queue Worker
====================
Chạy TRÊN HOST (không dockerize) — nơi có `main.py`, Claude/OpenCode CLI,
git và thư mục `clients/`. Poll Dashboard API lấy job đang chờ rồi chạy
pipeline tuần tự, thay cho việc gõ tay:

    python main.py --config clients/<slug>/settings.toml --prd clients/<slug>/prd.md

Cách dùng — mở 1 terminal, chạy 1 lần rồi để đó:

    python worker.py

Từ đó về sau chỉ cần bấm nút ▶ Run trên Dashboard.

Worker làm 2 việc, poll xen kẽ trong cùng 1 vòng lặp:

  1. Job pipeline (`/api/run-jobs`)      → chạy `python main.py` (OpenCode).
  2. Job bước workflow (`/api/workflow-jobs`) → chạy `claude -p "<prompt>"`
     cho 1 bước, CHỈ khi workflow đó được bật "Tự chạy (Claude headless)".

Về việc dùng Claude ở đây (xem "Chính sách" trong README): chốt chặn Claude
Code là dành cho pipeline `ai_team/` — chạy nền, nhiều project, agent song
song, không ai giám sát. Việc (2) khác hẳn: bạn phải bật tay từng workflow,
nó chạy trên chính máy bạn bằng đăng nhập của bạn, tuần tự 1 bước/lần, và
bạn nhìn thấy log ngay trong terminal này. Đừng nới 3 giới hạn đó.

Tuỳ biến lệnh headless bằng biến môi trường:

    CLAUDE_BIN        (mặc định "claude")
    CLAUDE_ARGS       cờ thêm, cách nhau bởi dấu cách
                      (mặc định "--permission-mode acceptEdits"; --output-format
                      do worker tự đặt là stream-json để đọc được log sống)
    STEP_TIMEOUT_S    tối đa 1 bước được chạy (mặc định 1800s)
    PROGRESS_FLUSH_S  đẩy log sống lên dashboard mỗi bao nhiêu giây (mặc định 2)

Chỉ dùng thư viện chuẩn (urllib) → không cần cài thêm gì.
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import shlex
import shutil
import tomllib

# Console Windows mặc định cp1252 — log có emoji sẽ ném UnicodeEncodeError và
# giết luôn job đang chạy. Ép UTF-8, ký tự nào không vẽ được thì thay thế.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

API   = os.getenv("DASHBOARD_API_URL", "http://localhost:8100")
ROOT  = Path(__file__).resolve().parent
POLL  = int(os.getenv("WORKER_POLL_S", "3"))

CLAUDE_BIN     = os.getenv("CLAUDE_BIN", "claude")
OPENCODE_BIN   = os.getenv("OPENCODE_BIN", "opencode")
# Giống ai_team/runner.py: opencode chạy nền, không ai bấm duyệt.
OPENCODE_ARGS  = shlex.split(os.getenv("OPENCODE_ARGS", "--dangerously-skip-permissions"))
# acceptEdits: tự duyệt sửa file (bước nào cũng phải sửa file task) nhưng KHÔNG
# dùng --dangerously-skip-permissions — cờ đó đã bị gỡ khỏi repo theo chính sách.
# --output-format KHÔNG nằm ở đây: worker ép stream-json để đọc từng sự kiện
# (xem _run_streaming). Người dùng lỡ đặt --output-format trong CLAUDE_ARGS thì
# bị bỏ (xem _strip_output_flags) — không thì log sống câm.
CLAUDE_ARGS    = shlex.split(os.getenv("CLAUDE_ARGS", "--permission-mode acceptEdits"))
STEP_TIMEOUT_S = int(os.getenv("STEP_TIMEOUT_S", "1800"))


def _req(path: str, body: dict | None = None, method: str = "GET"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def _claim() -> dict | None:
    # Trả null khi rỗng hoặc đang có job chạy (server giữ tuần tự)
    return _req("/api/run-jobs/claim", body={}, method="POST")


def _complete(job_id: int, status: str, error: str = ""):
    try:
        _req(f"/api/run-jobs/{job_id}/complete",
             body={"status": status, "error": error[:1000]}, method="POST")
    except Exception as e:
        print(f"[worker] ⚠️  Không báo được complete cho job #{job_id}: {e}")


def _run_job(job: dict):
    job_id = job["id"]
    slug   = job["client_folder"]
    cfg    = ROOT / "clients" / slug / "settings.toml"
    prd    = ROOT / "clients" / slug / "prd.md"

    if not cfg.exists():
        print(f"[worker] ❌ Job #{job_id}: không tìm thấy {cfg}")
        _complete(job_id, "failed", f"Không tìm thấy {cfg}")
        return
    if not prd.exists():
        print(f"[worker] ❌ Job #{job_id}: không tìm thấy {prd}")
        _complete(job_id, "failed", f"Không tìm thấy {prd}")
        return

    env = os.environ.copy()
    env["CLIENT_NAME"]        = slug
    env["AI_TEAM_PROJECT_ID"] = str(job.get("project_id") or "")
    env["FEATURE_IDS"]        = job.get("feature_ids") or ""
    env.setdefault("DASHBOARD_API_URL", API)
    env.update(_project_git_env(slug))

    cmd = [
        sys.executable, "main.py",
        "--config", f"clients/{slug}/settings.toml",
        "--prd",    f"clients/{slug}/prd.md",
    ]
    if job.get("profile"):
        cmd += ["--profile", job["profile"]]

    print(f"\n[worker] ▶ Job #{job_id} ({slug}) → {' '.join(cmd)}")
    try:
        # stdout/stderr kế thừa terminal → xem log pipeline trực tiếp
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    except Exception as e:
        print(f"[worker] ❌ Job #{job_id} lỗi khi spawn: {e}")
        _complete(job_id, "failed", str(e))
        return

    if proc.returncode == 0:
        print(f"[worker] ✅ Job #{job_id} ({slug}) hoàn thành")
        _complete(job_id, "done")
    else:
        print(f"[worker] ❌ Job #{job_id} ({slug}) thất bại (exit {proc.returncode})")
        _complete(job_id, "failed", f"main.py exit code {proc.returncode}")


def _resolve_bin(name: str) -> str | None:
    """Duong dan that cua 1 CLI."""
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return name if Path(name).exists() else None
    return shutil.which(name)


# ── Log sống của 1 bước ──────────────────────────────────────────────────────
# Trước đây worker gom stdout bằng subprocess.run(capture_output=True) rồi mới
# đọc — trong lúc Claude chạy 5–10 phút, dashboard chỉ hiện "worker đang chạy..."
# và không ai biết nó đang làm gì hay kẹt ở đâu. Giờ chạy claude với
# --output-format stream-json, đọc từng sự kiện, tóm thành 1 dòng dễ đọc, in ra
# terminal này VÀ đẩy lên POST /api/workflow-jobs/<id>/progress theo đợt.

PROGRESS_FLUSH_S = float(os.getenv("PROGRESS_FLUSH_S", "2"))

_TOOL_ICON = {
    "Bash": "🔧", "PowerShell": "🔧", "Read": "📖", "Edit": "✏️", "MultiEdit": "✏️",
    "Write": "📝", "NotebookEdit": "📝", "Grep": "🔍", "Glob": "🔍",
    "WebFetch": "🌐", "WebSearch": "🌐", "Task": "🤖", "Agent": "🤖",
    "TodoWrite": "📋", "Skill": "🧩",
}


def _short(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _result_text(content) -> str:
    """tool_result.content là chuỗi hoặc list block {type:text,text}."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return str(content or "")


def _describe_tool(name: str, inp: dict) -> str:
    icon = _TOOL_ICON.get(name, "🧰")
    if name in ("Bash", "PowerShell"):
        detail = inp.get("command", "")
    elif name in ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit"):
        detail = inp.get("file_path") or inp.get("notebook_path") or ""
    elif name in ("Grep", "Glob"):
        detail = f"{inp.get('pattern', '')}  {inp.get('path') or ''}"
    elif name in ("Task", "Agent"):
        detail = inp.get("description") or inp.get("prompt", "")
    elif name == "Skill":
        detail = inp.get("skill", "")
    else:
        detail = json.dumps(inp, ensure_ascii=False)
    return f"{icon} {name}: {_short(detail, 220)}"


def _summarize_event(ev: dict) -> list[str]:
    """1 sự kiện stream-json của claude -p → 0..n dòng log đọc được.

    Chỉ giữ cái người xem cần: Claude nói gì, gọi tool nào với tham số gì, tool
    nào báo lỗi, và kết quả cuối. Nội dung tool trả về thành công thì bỏ — dài
    và không cho biết thêm gì về tiến độ."""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        return [f"🚀 Claude bắt đầu · model {ev.get('model') or '?'}"]
    if t == "assistant":
        lines = []
        for block in (ev.get("message") or {}).get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text", "").strip():
                lines.append(f"💬 {_short(block['text'], 240)}")
            elif block.get("type") == "tool_use":
                lines.append(_describe_tool(block.get("name", ""), block.get("input") or {}))
        return lines
    if t == "user":
        lines = []
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                lines.append(f"   ❌ {_short(_result_text(block.get('content')), 300)}")
        return lines
    if t == "rate_limit_event":
        # Sắp chạm trần quota là lý do hay gặp khiến bước chậm/đứt — cho hiện luôn.
        info = ev.get("rate_limit_info") or {}
        util = info.get("utilization")
        if info.get("status") not in (None, "allowed") and isinstance(util, (int, float)):
            return [f"⏳ Quota {info.get('rateLimitType', '?')} đã dùng {util * 100:.0f}% ({info.get('status')})"]
        return []
    if t == "result":
        secs  = (ev.get("duration_ms") or 0) / 1000
        turns = ev.get("num_turns")
        tail  = f"{secs:.0f}s · {turns} lượt" if turns is not None else f"{secs:.0f}s"
        lines = []
        if ev.get("is_error") or ev.get("subtype") != "success":
            lines.append(f"❌ Claude kết thúc lỗi ({ev.get('subtype')}) sau {tail}")
        else:
            lines.append(f"✅ Claude xong sau {tail}")
        # Mỗi lần gọi `claude -p` là 1 phiên MỚI: toàn bộ system prompt + tool schema
        # (~45K token) bị ghi lại vào cache với giá gấp đôi input. Hiện thẳng ra đây
        # để biết bước nào đắt, thay vì đoán.
        u = ev.get("usage") or {}
        cost = ev.get("total_cost_usd")
        if u or cost is not None:
            parts = []
            if u.get("cache_creation_input_tokens"):
                parts.append(f"ghi cache {u['cache_creation_input_tokens']:,}")
            if u.get("cache_read_input_tokens"):
                parts.append(f"đọc cache {u['cache_read_input_tokens']:,}")
            if u.get("input_tokens"):
                parts.append(f"input {u['input_tokens']:,}")
            if u.get("output_tokens"):
                parts.append(f"output {u['output_tokens']:,}")
            money = f" · ${cost:.4f}" if isinstance(cost, (int, float)) else ""
            lines.append(f"💰 {' · '.join(parts)} token{money}")
        return lines
    return []


class _Progress:
    """Gom dòng log của 1 job, in ra terminal ngay và đẩy lên API theo đợt."""

    def __init__(self, job_id: int):
        self.job_id  = job_id
        self._buf: list[str] = []
        self._last  = time.monotonic()
        self._lock  = threading.Lock()

    def add(self, line: str) -> None:
        print(f"    {line}")
        with self._lock:
            self._buf.append(line)
            due = time.monotonic() - self._last >= PROGRESS_FLUSH_S
        if due:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            if not self._buf:
                return
            chunk, self._buf = "\n".join(self._buf) + "\n", []
            self._last = time.monotonic()
        try:
            _req(f"/api/workflow-jobs/{self.job_id}/progress", body={"lines": chunk}, method="POST")
        except Exception as e:
            # Mất 1 đợt log không đáng để dừng bước — chỉ báo ở terminal.
            print(f"[worker] ⚠️  Không đẩy được log lên dashboard: {e}")


def _strip_output_flags(args: list[str]) -> list[str]:
    """Bỏ --output-format/--verbose nếu người dùng đặt trong CLAUDE_ARGS: worker
    phải tự chọn stream-json thì mới đọc được từng bước để hiện log sống."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--output-format":
            skip = True
            continue
        if a.startswith("--output-format=") or a == "--verbose":
            continue
        out.append(a)
    return out


def _run_streaming(cmd: list[str], env: dict, progress: _Progress, parse_json: bool,
                   timeout: int) -> tuple[int, str, str]:
    """Chạy CLI, đọc stdout từng dòng đẩy vào `progress`.

    Trả (exit code, kết quả cuối, stderr). Với claude (parse_json) kết quả cuối
    là trường `result` của sự kiện cuối; với opencode là toàn bộ stdout. stdout
    và stderr đọc bằng 2 thread riêng — đọc tuần tự 1 pipe thì pipe kia đầy là
    tiến trình con treo."""
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    result: list[str] = []
    errbuf: list[str] = []

    def read_out():
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            if not parse_json:
                progress.add(line)
                result.append(line)
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                progress.add(line)          # claude in gì đó không phải JSON — cứ hiện
                continue
            for s in _summarize_event(ev):
                progress.add(s)
            if ev.get("type") == "result":
                result.append(ev.get("result") or "")
                if ev.get("is_error"):
                    errbuf.append(f"claude: {ev.get('subtype')}")

    def read_err():
        for raw in proc.stderr:
            errbuf.append(raw)

    t_out = threading.Thread(target=read_out, daemon=True)
    t_err = threading.Thread(target=read_err, daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        t_out.join(5)
        t_err.join(5)
        progress.flush()
        raise
    t_out.join()
    t_err.join()
    progress.flush()
    return proc.returncode, "\n".join(result).strip(), "".join(errbuf).strip()


def _resolve_claude() -> str | None:
    """Duong dan that cua CLI claude.

    Tren Windows `claude` la shim **claude.CMD** (npm). subprocess goi CreateProcess,
    ma CreateProcess KHONG ap PATHEXT — truyen tran chuoi "claude" se FileNotFoundError
    du go `claude` trong terminal van chay. shutil.which() co ap PATHEXT nen tim ra
    dung file .CMD/.EXE de truyen duong dan day du."""
    return _resolve_bin(CLAUDE_BIN)


def _add_dirs(job: dict) -> list[str]:
    """Thư mục code của project, để truyền cho CLI qua --add-dir.

    API tính sẵn từ [output] trong settings.toml (thư mục gốc + từng vùng BE/FE).
    Đường dẫn tương đối thì quy về gốc repo vì đó là cwd của tiến trình con."""
    out = []
    for raw in (job.get("add_dirs") or []):
        d = str(raw).strip()
        if not d:
            continue
        p = Path(d)
        out.append(str(p if p.is_absolute() else (ROOT / p)))
    return out


def _project_git_env(slug: str | None) -> dict:
    """Token GitHub RIENG cho tung project, doc tu clients/<slug>/settings.local.toml:

        [git]
        token    = "ghp_..."      # hoac PAT cua to chuc / GitHub App installation token
        username = "dongcn11"     # tuy chon, mac dinh x-access-token

    Vi sao khong chot 1 tai khoan trong git config --global: moi project co the day
    len mot to chuc / mot tai khoan khac nhau. Chot cung la sai ngay project thu hai.

    Token chi song trong env cua tien trinh con — khong ghi vao .git/config, khong
    qua API, khong vao DB. settings.local.toml da nam trong .gitignore.

    Tra ve env de merge; khong khai token thi tra {} (giu nguyen hanh vi cu:
    Git Credential Manager tu hoi).
    """
    if not slug:
        return {}
    cfg = {}
    for name in ("settings.local.toml", "settings.toml"):
        f = ROOT / "clients" / slug / name
        if not f.exists():
            continue
        try:
            with open(f, "rb") as fh:
                cfg = {**(tomllib.load(fh).get("git") or {}), **cfg}
        except Exception as e:
            print(f"[worker] !  Khong doc duoc [git] trong {f}: {e}")
    token = str(cfg.get("token") or "").strip()
    if not token:
        return {}
    user = str(cfg.get("username") or "x-access-token").strip()

    # Helper doc token tu env. Dat qua GIT_CONFIG_* de KHONG cham vao file config
    # nao ca. Entry rong o vi tri 0 xoa danh sach helper thua ke tu global (Git
    # Credential Manager) — khong xoa thi GCM van bat hop thoai chon tai khoan
    # va tien trinh headless treo cho toi luc timeout.
    return {
        "GH_TOKEN": token,
        "GITHUB_TOKEN": token,
        "GIT_TERMINAL_PROMPT": "0",          # thà lỗi ngay còn hơn treo chờ nhập tay
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
        "GIT_CONFIG_KEY_1": "credential.helper",
        "GIT_CONFIG_VALUE_1": (
            "!f() { echo username=" + user + "; echo password=$GH_TOKEN; }; f"
        ),
    }


def _claim_step() -> dict | None:
    """Job bước workflow (chạy bằng Claude headless). Server giữ tuần tự."""
    return _req("/api/workflow-jobs/claim", body={}, method="POST")


def _complete_step(job_id: int, status: str, output: str = "", error: str = ""):
    try:
        _req(f"/api/workflow-jobs/{job_id}/complete",
             body={"status": status, "output": output[-8000:], "error": error[:2000]},
             method="POST")
    except Exception as e:
        print(f"[worker] ⚠️  Không báo được complete cho step job #{job_id}: {e}")


def _run_step_job(job: dict):
    """Chạy 1 bước workflow bằng `claude -p`.

    Không tự đánh dấu bước xong: Claude sửa `status: done` ngay trong file task,
    vòng poll của dashboard đọc file rồi mở bước kế tiếp — giống hệt lúc bạn chạy
    tay. Nhờ vậy chạy tự động và chạy tay đi chung một đường, không lệch trạng thái."""
    job_id = job["id"]
    label  = job.get("node_label") or job["node_id"]
    tool  = (job.get("tool") or "claude").lower()
    model = job.get("model")

    if tool == "opencode":
        # Node chon 1 agent cua pipeline -> chay dung tool/model cua agent do,
        # dung cach ai_team/runner.py goi opencode (file dua qua -f).
        binary = _resolve_bin(OPENCODE_BIN)
        if not binary:
            msg = (f"Khong tim thay CLI '{OPENCODE_BIN}' trong PATH cua worker. "
                   f"Kiem tra bang `where {OPENCODE_BIN}`, hoac dat OPENCODE_BIN.")
            print(f"[worker] X {msg}")
            _complete_step(job_id, "failed", error=msg)
            return
        cmd = [binary, "run", job["prompt"]]
        if model:
            cmd += ["--model", model]
        cmd += [*OPENCODE_ARGS, "-f", job.get("file_path") or ""]
        # opencode nhận thư mục làm việc qua cwd chứ không có --add-dir; nó chạy với
        # cwd = gốc repo giống pipeline nên giữ nguyên.
    else:
        binary = _resolve_claude()
        if not binary:
            msg = (f"Khong tim thay CLI '{CLAUDE_BIN}' trong PATH cua tien trinh worker. "
                   f"Kiem tra bang `where {CLAUDE_BIN}`; neu co ma van bao loi thi dat "
                   f"CLAUDE_BIN tro thang vao file, vd C:/nvm4w/nodejs/claude.cmd")
            print(f"[worker] X {msg}")
            _complete_step(job_id, "failed", error=msg)
            return
        cmd = [binary, "-p", job["prompt"], *_strip_output_flags(CLAUDE_ARGS),
               "--output-format", "stream-json", "--verbose"]
        # Model chọn trên node (haiku/sonnet/opus). Bỏ trống -> theo mặc định của
        # CLI. Mỗi lần gọi phải nạp lại ~45K token tiền tố với giá gấp đôi input,
        # nên bậc model nhân thẳng vào sàn chi phí của từng bước.
        if model:
            cmd += ["--model", model]
        # Thư mục code của project thường nằm NGOÀI repo (settings.toml khai
        # output.directory tuyệt đối). Worker chạy với cwd = gốc repo nên nếu không
        # mở quyền, Claude headless không đọc/ghi được chỗ đó và MỌI bước của
        # project ấy cùng chết một lỗi — không riêng bước đầu.
        for d in _add_dirs(job):
            cmd += ["--add-dir", d]

    print(f"\n[worker] 🤖 Step job #{job_id} — {label} (run #{job['run_id']})")
    git_env = _project_git_env(job.get("client_folder"))
    env = {**os.environ, **git_env}

    print(f"[worker]    engine: {tool}{f' · {model}' if model else ''}")
    print(f"[worker]    {job.get('file_path') or ''}")
    if git_env:
        print("[worker]    git: dùng token riêng của project (settings.local.toml)")
    progress = _Progress(job_id)
    try:
        code, out, err = _run_streaming(cmd, env, progress, parse_json=(tool != "opencode"),
                                        timeout=STEP_TIMEOUT_S)
    except (FileNotFoundError, OSError) as e:
        msg = (f"Không chạy được '{binary}': {e}. Cài CLI đó rồi đăng nhập, "
               f"hoặc đặt CLAUDE_BIN/OPENCODE_BIN trỏ thẳng tới file.")
        print(f"[worker] ❌ {msg}")
        _complete_step(job_id, "failed", error=msg)
        return
    except subprocess.TimeoutExpired:
        msg = f"Quá {STEP_TIMEOUT_S}s chưa xong — đã bỏ dở bước này"
        print(f"[worker] ❌ Step job #{job_id}: {msg}")
        _complete_step(job_id, "failed", error=msg)
        return
    except Exception as e:
        print(f"[worker] ❌ Step job #{job_id} lỗi khi spawn: {e}")
        _complete_step(job_id, "failed", error=str(e))
        return

    # opencode thoát 0 cả khi lỗi nặng — nhận diện qua stderr, giống ai_team/runner.py
    opencode_failed = tool == "opencode" and "Error:" in err and not out
    if code == 0 and not opencode_failed:
        print(f"[worker] ✅ Step job #{job_id} xong — dashboard sẽ đọc lại file task")
        _complete_step(job_id, "done", output=out)
    else:
        print(f"[worker] ❌ Step job #{job_id} thất bại (exit {code})")
        _complete_step(job_id, "failed", output=out,
                       error=err or f"{tool} exit code {code}")


def main():
    print(f"[worker] AI Team queue worker khởi động")
    print(f"[worker]   API  = {API}")
    print(f"[worker]   root = {ROOT}")
    print(f"[worker]   poll = {POLL}s")
    _claude = _resolve_claude()
    if _claude:
        flags = " ".join([*_strip_output_flags(CLAUDE_ARGS), "--output-format stream-json --verbose"])
        print(f"[worker]   step = {_claude} -p ... {flags}  (chi workflow bat auto_run)")
    else:
        print(f"[worker]   ⚠️  KHÔNG tìm thấy CLI '{CLAUDE_BIN}' — job bước workflow sẽ fail ngay.")
        print(f"[worker]      Chạy `where {CLAUDE_BIN}`; hoặc đặt CLAUDE_BIN=<đường dẫn đầy đủ>.")
    print(f"[worker] Đang chờ job... (Ctrl+C để dừng)\n")

    while True:
        job = step = None
        try:
            job = _claim()
            if not job:
                step = _claim_step()
        except urllib.error.URLError as e:
            print(f"[worker] ⏳ API chưa sẵn sàng ({e.reason}); thử lại sau {POLL}s")
        except Exception as e:
            print(f"[worker] ⚠️  claim lỗi: {e}")

        if job:
            _run_job(job)
            continue  # chạy ngay job kế tiếp nếu còn, không chờ POLL
        if step:
            try:
                _run_step_job(step)
            except Exception as e:      # đừng để job kẹt 'running' vì worker vấp
                print(f"[worker] ⚠️  step job #{step['id']} lỗi ngoài dự kiến: {e}")
                _complete_step(step["id"], "failed", error=str(e))
            continue

        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[worker] Dừng theo yêu cầu. Tạm biệt 👋")
