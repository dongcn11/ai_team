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
    CLAUDE_ACCOUNTS_FILE  file tài khoản Claude (mặc định config/claude_accounts.local.toml)
    CLAUDE_COOLDOWN_S     hết quota mà không biết giờ reset thì nghỉ bao lâu (mặc định 1800)

Nhiều tài khoản Claude Pro: khai token từng tài khoản trong
config/claude_accounts.local.toml (mẫu: claude_accounts.example.toml). Chọn tài
khoản trên Dashboard → Settings. Hết quota: bước chưa gọi tool nào thì worker
chạy lại ngay bằng tài khoản kế tiếp; đã gọi tool thì bước báo lỗi kèm tên tài
khoản kế tiếp để bạn bấm chạy lại. Xem mục "Tài khoản Claude" bên dưới.

Chỉ dùng thư viện chuẩn (urllib) → không cần cài thêm gì.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
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
# Hạn riêng cho việc khởi động MCP server, NGẮN HƠN hẳn hạn của cả bước.
MCP_START_TIMEOUT_S = int(os.getenv("MCP_START_TIMEOUT_S", "20"))


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


# Tool MCP có tác dụng GHI. Nhận diện theo tiền tố hành động trong tên tool — tên
# tool do server đặt, nhưng quy ước create/append/insert/update/delete/move/share
# thì gần như phổ quát. Bắt hụt thì chỉ mất một dòng nhật ký; bắt thừa thì thừa
# một dòng — cả hai đều không nguy hiểm, nên chọn bắt rộng.
# Động từ nằm BẤT KỲ đâu trong tên tool, không chỉ ở đầu: tên thật của server
# Google là `sheets-append-values`, `docs-insert-text`, `slides-delete-slide`.
_MCP_WRITE_RE = re.compile(
    r"(^|[-_])(create|append|insert|add|update|write|upload|copy|move|delete|remove|share|"
    r"replace|clear|duplicate|resolve|merge|unmerge|sort|format|resize)([-_]|$)", re.I)
# Khoá trong input có khả năng là định danh của đối tượng bị ghi vào.
_ID_KEY_RE = re.compile(r"(^|[-_])(id|ids)$|Id$|Ids$")


def _mcp_target(inp: dict) -> str:
    """Định danh đối tượng đích của một thao tác ghi, để lần ngược được khi khách
    hỏi 'file này ở đâu ra'. Gom mọi khoá trông như id, cộng `name`/`title`."""
    bits = []
    for k, v in (inp or {}).items():
        if isinstance(v, (str, int)) and (_ID_KEY_RE.search(str(k)) or k in ("name", "title")):
            bits.append(f"{k}={v}")
    return " ".join(bits[:4])


def _describe_tool(name: str, inp: dict) -> str:
    if name.startswith("mcp__") and _MCP_WRITE_RE.search(name.split("__", 2)[-1]):
        # Mọi lần ghi để lại dấu vết, kèm định danh đích. Đây là thứ duy nhất cho
        # phép đối chiếu với nội dung thật trên Drive khi có sự cố.
        target = _mcp_target(inp) or _short(json.dumps(inp, ensure_ascii=False), 120)
        return f"📝 {name}: {_short(target, 200)}"
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
        lines = [f"🚀 Claude bắt đầu · model {ev.get('model') or '?'}"]
        # Nguồn sự thật để đối chiếu bộ MCP thực tế với cấu hình đã khai: đây là
        # CLI tự báo, không phải worker tự tin vào thứ mình vừa truyền vào.
        tools = [x for x in (ev.get("tools") or []) if str(x).startswith("mcp__")]
        for srv in (ev.get("mcp_servers") or []):
            name = (srv or {}).get("name") or "?"
            state = (srv or {}).get("status") or "?"
            n = len([x for x in tools if str(x).startswith(f"mcp__{name}__")])
            lines.append(f"🔌 MCP: {name} · {state}" + (f" · {n} tool" if n else ""))
        return lines
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
        line = _redact(line)
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


def _metrics_from_result(ev: dict) -> dict:
    """Số liệu 1 lần chạy, moi từ sự kiện `result` của stream-json.

    Gửi lên dashboard để thẻ kết quả nói được: model nào chạy, hết bao nhiêu
    token, quy ra bao nhiêu tiền. Trước đây mấy số này chỉ nằm trong log sống
    rồi trôi mất — không cộng lại được theo lần chạy hay theo dự án."""
    u = ev.get("usage") or {}
    mu = ev.get("modelUsage") or {}
    # modelUsage có thể liệt kê cả model phụ (haiku chạy nền); lấy con tốn tiền
    # nhất làm "model đã chạy" — đó là con thật sự làm việc.
    model = max(mu.items(), key=lambda kv: (kv[1] or {}).get("costUSD") or 0)[0] if mu else None
    return {
        "model_used": model,
        "cost_usd": ev.get("total_cost_usd"),
        "duration_ms": ev.get("duration_ms"),
        "usage": {
            "input":       u.get("input_tokens") or 0,
            "output":      u.get("output_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0,
            "cache_read":  u.get("cache_read_input_tokens") or 0,
            "turns":       ev.get("num_turns"),
        },
    }


class _McpStartTimeout(Exception):
    """Server MCP không lên trong hạn riêng. Tách khỏi TimeoutExpired của cả bước:
    chờ 20 giây rồi báo đúng bệnh hơn hẳn chờ 30 phút rồi báo 'quá giờ'."""


def _run_streaming(cmd: list[str], env: dict, progress: _Progress, parse_json: bool,
                   timeout: int, watch: "_StepWatch | None" = None,
                   init_timeout: int | None = None) -> tuple[int, str, str, dict]:
    """Chạy CLI, đọc stdout từng dòng đẩy vào `progress`.

    Trả (exit code, kết quả cuối, stderr, số liệu). Với claude (parse_json) kết
    quả cuối là trường `result` của sự kiện cuối; với opencode là toàn bộ stdout.
    `watch` (nếu có) nhận từng sự kiện JSON — xem _StepWatch.
    stdout và stderr đọc bằng 2 thread riêng — đọc tuần tự 1 pipe thì pipe kia đầy
    là tiến trình con treo."""
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    result: list[str] = []
    errbuf: list[str] = []
    metrics: dict = {}

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
            if watch is not None:
                try:
                    watch.feed(ev)
                except Exception as e:   # 1 sự kiện lạ không được giết thread đọc → CLI treo
                    print(f"[worker] ⚠️  watch bỏ qua 1 sự kiện: {e}")
            for s in _summarize_event(ev):
                progress.add(s)
            if ev.get("type") == "result":
                result.append(ev.get("result") or "")
                metrics.update(_metrics_from_result(ev))
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
        # Hạn riêng cho lúc khởi động server MCP: sự kiện `system/init` chưa tới
        # trong ngần này giây thì server chết, không có lý do gì chờ tới hết
        # STEP_TIMEOUT_S (1800s) rồi mới báo một câu "quá giờ" vô nghĩa.
        started = time.time()
        deadline = started + init_timeout if (init_timeout and watch is not None) else None
        while True:
            left = timeout - (time.time() - started)
            if left <= 0:
                raise subprocess.TimeoutExpired(cmd, timeout)
            slice_s = left
            if deadline and not watch.saw_init:
                slice_s = min(left, max(0.2, deadline - time.time()))
            try:
                proc.wait(timeout=slice_s)
                break
            except subprocess.TimeoutExpired:
                if deadline and not watch.saw_init and time.time() >= deadline:
                    proc.kill()
                    proc.wait()
                    t_out.join(5)
                    t_err.join(5)
                    progress.flush()
                    raise _McpStartTimeout(init_timeout)
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
    return proc.returncode, "\n".join(result).strip(), "".join(errbuf).strip(), metrics


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


def _project_git_env(slug: str | None, agent_key: str | None = None) -> dict:
    """Token GitHub RIENG cho tung project — va rieng tung AGENT DEV trong project.
    Doc tu clients/<slug>/settings.local.toml:

        [git]                     # mac dinh cho ca project
        token    = "ghp_..."      # hoac PAT cua to chuc / GitHub App installation token
        username = "dongcn11"     # tuy chon, mac dinh x-access-token

        [git.be1]                 # ong BE day bang tai khoan rieng
        token    = "ghp_..."
        username = "dev-backend"

    Buoc nao gan agent (be1/fe1/fs1...) thi lay [git.<key>] truoc, khong co moi
    roi ve [git]. 3 ong dev = 3 repo = 3 tai khoan, khong phai chung 1 token.

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
    # Token rieng cua agent thang token chung cua project
    own = cfg.get(agent_key) if agent_key and isinstance(cfg.get(agent_key), dict) else None
    if own and str(own.get("token") or "").strip():
        cfg = own
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


# ── MCP theo từng dự án ──────────────────────────────────────────────────────
# Mỗi dự án khai bộ MCP server riêng trong clients/<slug>/mcp.json. Bước của dự
# án nào chỉ thấy server của dự án đó — connector mức tài khoản bị cắt bằng
# --strict-mcp-config. Vì sao không dùng connector claude.ai: nó gắn với TÀI
# KHOẢN chứ không gắn với dự án, nên bật Drive là mọi khách đều thấy Drive, và
# bộ tool còn đổi theo tài khoản đang tới lượt trong vòng xoay quota.
#
# File này KHÔNG chứa bí mật: credential khai bằng đường dẫn trong
# settings.local.toml ([mcp.<server>]) và đi vào env của tiến trình con — MCP
# server là con của Claude Code nên thừa kế env (đã kiểm trên CLI 2.1.273).
# Nhờ vậy mcp.json commit lên git cũng không lộ gì.
#
# Đọc lại theo (mtime, size) như _Accounts; file hỏng thì GIỮ cấu hình cũ.

# Tên server chui thẳng vào tên tool `mcp__<server>__<tool>` và vào --allowedTools.
# Ký tự lạ làm hỏng lặng lẽ, nên chặn ngay từ lúc đọc.
_MCP_NAME_RE = re.compile(r"^[a-z0-9_-]+$")


class _McpServer:
    __slots__ = ("name", "template", "profile", "declared_write_scope")

    def __init__(self, name: str, template: str, profile: str, declared_write_scope: dict):
        self.name = name
        self.template = template
        self.profile = profile
        # Vùng ghi KHAI BÁO — để hiển thị và để trả lời khách, KHÔNG phải hàng rào.
        # Hàng rào thật là phạm vi chia sẻ phía Google. Đừng viết code bảo vệ dựa
        # vào trường này.
        self.declared_write_scope = declared_write_scope


class _McpConfig:
    """Cấu hình MCP của từng dự án, cache theo (mtime, size) của từng file.

    servers(slug) trả [] khi: không có file · JSON hỏng (lần đầu) · `enabled`
    gốc = false · không server nào bật. [] nghĩa là bước chạy y hệt trước khi
    có tính năng này — không thêm một tham số CLI nào."""

    def __init__(self, root: Path):
        self.root = root
        self._stamps: dict[str, tuple[float, int] | None] = {}
        self._cache:  dict[str, list[_McpServer]] = {}
        self._seen_secrets: set[str] = set()

    def path(self, slug: str) -> Path:
        return self.root / "clients" / slug / "mcp.json"

    def servers(self, slug: str | None) -> list[_McpServer]:
        if not slug:
            return []
        path = self.path(slug)
        try:
            st = path.stat()
        except OSError:
            self._stamps.pop(slug, None)
            self._cache.pop(slug, None)
            return []
        stamp = (st.st_mtime, st.st_size)
        if self._stamps.get(slug) != stamp:
            self._stamps[slug] = stamp     # ghi trước: file hỏng cũng chỉ cảnh báo 1 lần
            self._cache[slug] = self._parse(path, slug)
        return self._cache.get(slug, [])

    def _parse(self, path: Path, slug: str) -> list[_McpServer]:
        keep = self._cache.get(slug, [])
        try:
            with open(path, "rb") as fh:
                raw = json.load(fh)
        except Exception as e:
            print(f"[worker] ⚠️  clients/{slug}/mcp.json lỗi cú pháp, GIỮ cấu hình cũ "
                  f"({len(keep)} server): {e}")
            return keep
        if not isinstance(raw, dict):
            print(f"[worker] ⚠️  clients/{slug}/mcp.json: gốc phải là object, GIỮ cấu hình cũ")
            return keep
        if raw.get("enabled") is False:        # công tắc cấp dự án
            return []
        servers = raw.get("servers")
        if servers is None:
            return []
        if not isinstance(servers, dict):
            print(f"[worker] ⚠️  clients/{slug}/mcp.json: `servers` phải là object, GIỮ cấu hình cũ")
            return keep
        out: list[_McpServer] = []
        for name, row in servers.items():
            if not isinstance(row, dict) or row.get("enabled") is False:
                continue
            name = str(name).strip()
            if not _MCP_NAME_RE.match(name):
                print(f"[worker] ⚠️  clients/{slug}/mcp.json: tên server '{name}' chỉ được dùng "
                      f"a-z 0-9 _ - (nó thành tên tool mcp__<server>__<tool>) — bỏ qua")
                continue
            template = str(row.get("template") or "").strip()
            if not template:
                print(f"[worker] ⚠️  clients/{slug}/mcp.json: server '{name}' thiếu `template` — bỏ qua")
                continue
            scope = row.get("declared_write_scope")
            out.append(_McpServer(
                name=name,
                template=template,
                profile=str(row.get("profile") or "read-only").strip(),
                declared_write_scope=scope if isinstance(scope, dict) else {},
            ))
        return out

    # ── Credential: đường dẫn, không phải giá trị ────────────────────────────
    # settings.local.toml (đã gitignore) khai ĐƯỜNG DẪN tới file credential:
    #
    #     [mcp.gdrive]
    #     credentials_path = "C:/secure/udom-service-account.json"
    #
    # Nội dung file đó không bao giờ đi vào tiến trình này — worker chỉ chuyền
    # đường dẫn qua env cho MCP server tự đọc. Đọc cả settings.toml lẫn
    # settings.local.toml, local thắng — y như _project_git_env.

    def secrets(self, slug: str, servers: list) -> tuple[dict, list[str]]:
        """Trả ({ten_server: duong_dan}, [lỗi cần nói cho người vận hành]).

        Mỗi lỗi nêu ĐỦ HAI VẾ: thiếu cái gì, và sửa ở file/khoá nào — bước fail
        vì thiếu credential phải sửa được mà không cần đọc log CLI thô."""
        cfg = {}
        for name in ("settings.toml", "settings.local.toml"):
            f = self.root / "clients" / slug / name
            if not f.exists():
                continue
            try:
                with open(f, "rb") as fh:
                    cfg = {**cfg, **(tomllib.load(fh).get("mcp") or {})}
            except Exception as e:
                print(f"[worker] ⚠️  Không đọc được [mcp] trong {f}: {e}")
        out: dict[str, str] = {}
        problems: list[str] = []
        where = f"clients/{slug}/settings.local.toml"
        for s in servers:
            row = cfg.get(s.name)
            if not isinstance(row, dict):
                problems.append(f"Server '{s.name}' chưa có credential. Thêm mục "
                                f"[mcp.{s.name}] với khoá `credentials_path` vào {where}.")
                continue
            path = str(row.get("credentials_path") or "").strip()
            if not path:
                problems.append(f"Server '{s.name}' thiếu `credentials_path` trong "
                                f"[mcp.{s.name}] của {where}.")
                continue
            if not Path(path).exists():
                problems.append(f"Không thấy file credential của server '{s.name}': {path} "
                                f"(khai trong [mcp.{s.name}] của {where}).")
                continue
            out[s.name] = path
            self._seen_secrets.add(path)     # để _redact che, xem AR13
        return out, problems

    def secret_values(self) -> list[str]:
        """Mọi đường dẫn credential đã từng thấy — nguồn cho _redact. Đường dẫn
        không phải bí mật như token, nhưng nó lộ bố cục máy chủ nên vẫn che."""
        return [v for v in self._seen_secrets if v]


MCP_TEMPLATES_FILE = Path(os.getenv("MCP_TEMPLATES_FILE",
                                    str(ROOT / "config" / "mcp_templates.toml")))


class _McpTemplates:
    """Danh sách mẫu server + hồ sơ quyền, đọc lại theo (mtime, size).

    Chỉ chạy server có trong file này. Cho khai lệnh tự do từ dashboard nghĩa là
    cho tạo tiến trình tuỳ ý trên máy vận hành qua HTTP — thêm server mới phải
    sửa file trên host, có chủ đích."""

    def __init__(self, path: Path):
        self.path = path
        self._stamp: tuple[float, int] | None = None
        self._items: dict = {}

    def _load(self) -> None:
        try:
            st = self.path.stat()
        except OSError:
            self._items, self._stamp = {}, None
            return
        stamp = (st.st_mtime, st.st_size)
        if stamp == self._stamp:
            return
        self._stamp = stamp            # ghi trước: file hỏng cũng chỉ cảnh báo 1 lần
        try:
            with open(self.path, "rb") as fh:
                raw = tomllib.load(fh).get("template") or {}
        except Exception as e:
            print(f"[worker] ⚠️  {self.path.name} lỗi cú pháp, GIỮ danh sách mẫu cũ "
                  f"({len(self._items)} mẫu): {e}")
            return
        self._items = raw if isinstance(raw, dict) else {}

    def get(self, name: str) -> dict | None:
        self._load()
        row = self._items.get(name)
        return row if isinstance(row, dict) else None

    def names(self) -> list[str]:
        self._load()
        return sorted(self._items)

    def tools(self, template: str, profile: str) -> list[str] | None:
        row = self.get(template)
        if not row:
            return None
        profiles = row.get("profiles")
        if not isinstance(profiles, dict):
            return None
        got = profiles.get(profile)
        return [str(t) for t in got] if isinstance(got, list) else None


MCP = _McpConfig(ROOT)
MCP_TEMPLATES = _McpTemplates(MCP_TEMPLATES_FILE)


MCP_MIN_CLI = (2, 1, 273)     # bản đầu tiên đã kiểm chứng có --mcp-config + --strict-mcp-config
_CLI_VERSION: tuple | None | str = "chua-hoi"      # cache: hỏi 1 lần cho cả đời worker


def _claude_version() -> tuple | None:
    """(major, minor, patch) của CLI, None nếu không đọc được. Hỏi đúng một lần."""
    global _CLI_VERSION
    if _CLI_VERSION != "chua-hoi":
        return _CLI_VERSION
    _CLI_VERSION = None
    binary = _resolve_claude()
    if binary:
        try:
            out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                 timeout=30, encoding="utf-8", errors="replace").stdout or ""
            m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
            if m:
                _CLI_VERSION = tuple(int(x) for x in m.groups())
        except Exception as e:
            print(f"[worker] ⚠️  Không đọc được phiên bản Claude CLI: {e}")
    return _CLI_VERSION


def _mcp_plan(slug: str | None) -> tuple[list[str], dict, list[str]]:
    """Dịch cấu hình của một dự án thành thứ truyền cho CLI.

    Trả (tham số CLI, env cần trộn thêm, danh sách lỗi).

    Không có cấu hình → ([], {}, []) và bước chạy y HỆT trước khi có tính năng
    này: đây là cổng duy nhất, mọi tham số mới nằm sau nó.

    Có lỗi → trả luôn lỗi, KHÔNG trả tham số. Chạy nửa vời với một server thiếu
    credential là cách chắc chắn nhất để sinh ra lỗi khó chẩn đoán."""
    servers = MCP.servers(slug)
    if not servers:
        return [], {}, []

    # CLI quá cũ thì KHÔNG âm thầm bỏ cờ rồi chạy tiếp: bước sẽ chạy không có tool
    # nào, agent báo "không tìm thấy tài liệu", và người vận hành đi tìm lỗi ở
    # Google trong khi thủ phạm là phiên bản CLI.
    ver = _claude_version()
    if ver is not None and ver < MCP_MIN_CLI:
        got = ".".join(str(x) for x in ver)
        need = ".".join(str(x) for x in MCP_MIN_CLI)
        return [], {}, [f"Claude Code CLI {got} quá cũ cho MCP (cần >= {need}). "
                        f"Nâng cấp CLI, hoặc tắt MCP của dự án bằng `enabled = false` ở gốc "
                        f"clients/{slug}/mcp.json."]

    # Hỏi mẫu TRƯỚC: chỉ server có `credential_env` mới cần credential. Mẫu
    # filesystem (dùng để nghiệm thu) không cần gì cả — đòi credential của nó là
    # chặn nhầm. Thứ tự này cũng khiến lỗi template/hồ sơ hiện ra trước lỗi
    # credential, đúng thứ tự người vận hành sẽ phải sửa.
    problems: list[str] = []
    native: dict = {}
    allowed: list[str] = []
    env: dict = {}
    needs_cred = []

    for s in servers:
        tpl = MCP_TEMPLATES.get(s.template)
        if tpl and str(tpl.get("credential_env") or "").strip():
            needs_cred.append(s)
    secret_paths, cred_problems = MCP.secrets(slug, needs_cred) if needs_cred else ({}, [])

    for s in servers:
        tpl = MCP_TEMPLATES.get(s.template)
        if not tpl:
            problems.append(f"Server '{s.name}' khai template '{s.template}' không có trong "
                            f"{MCP_TEMPLATES_FILE.name}. Mẫu hợp lệ: {', '.join(MCP_TEMPLATES.names()) or '(trống)'}.")
            continue
        tools = MCP_TEMPLATES.tools(s.template, s.profile)
        if tools is None:
            profiles = (tpl.get("profiles") or {})
            problems.append(f"Server '{s.name}' khai hồ sơ quyền '{s.profile}' mà template "
                            f"'{s.template}' không có. Hồ sơ hợp lệ: "
                            f"{', '.join(sorted(profiles)) or '(trống)'}.")
            continue

        # Rào chuỗi cung ứng, cưỡng chế bằng mã chứ không bằng lời dặn trong
        # comment: `npx -y` tải bản mới nhất tại thời điểm spawn và chạy nó trên
        # máy vận hành. Áp cho MỌI mẫu, kể cả mẫu dev không có credential — server
        # local vẫn thấy cả thư mục làm việc của bước.
        if str(tpl.get("command") or "") == "npx" or \
                any(str(a) in ("-y", "--yes") for a in (tpl.get("args") or [])):
            problems.append(f"Template '{s.template}' dùng `npx -y` — không cho phép. Cài sẵn server "
                            f"ở phiên bản đã ghim rồi trỏ `command`/`args` vào đó trong "
                            f"{MCP_TEMPLATES_FILE.name}.")
            continue

        args = [str(a) for a in (tpl.get("args") or [])]
        # Đường dẫn tương đối trong mẫu quy về gốc repo — cwd của tiến trình con
        # là gốc repo, nhưng ghi tuyệt đối thì không phụ thuộc chuyện đó nữa.
        args = [str(ROOT / a) if a.endswith(".js") and not Path(a).is_absolute() else a
                for a in args]
        # Mẫu nào nhận thư mục qua tham số (server filesystem) thì lấy từ vùng khai báo.
        scope_key = str(tpl.get("args_from_scope") or "").strip()
        if scope_key:
            args += [str(v) for v in (s.declared_write_scope.get(scope_key) or [])]

        cred_env = str(tpl.get("credential_env") or "").strip()
        if cred_env:
            path = secret_paths.get(s.name)
            if not path:
                continue           # đã có lỗi từ MCP.secrets(), không báo trùng
            env[cred_env] = path

        native[s.name] = {"command": str(tpl.get("command") or ""), "args": args}
        allowed += [f"mcp__{s.name}__{t}" for t in tools]

    problems += cred_problems
    if problems:
        return [], {}, problems
    if not native:
        return [], {}, []

    # Chuỗi JSON inline thay vì file tạm: cấu hình không chứa bí mật (credential
    # đi đường env) nên dòng lệnh sạch, và không có vòng đời file tạm để quản khi
    # worker chết giữa chừng. Đã kiểm chứng CLI nhận chuỗi inline.
    cmd = ["--mcp-config", json.dumps({"mcpServers": native}, ensure_ascii=False),
           "--strict-mcp-config",
           "--allowedTools", ",".join(allowed)]
    return cmd, env, []


# ── Tài khoản Claude ─────────────────────────────────────────────────────────
# Mỗi tài khoản Pro có trần quota 5 giờ. Trước đây hết trần là phải ra terminal
# `claude auth login` sang tài khoản khác rồi xác nhận trên trình duyệt — mỗi
# lần. Giờ khai sẵn token dài hạn (`claude setup-token`) của từng tài khoản trong
# config/claude_accounts.local.toml; worker bơm CLAUDE_CODE_OAUTH_TOKEN vào env
# của tiến trình con. CLI ưu tiên env này hơn ~/.claude/.credentials.json (đã
# kiểm tra trên 2.1.273: `claude auth status` báo authMethod=oauth_token).
#
# Dashboard chỉ chọn TÊN (Setting claude_account) và xem trạng thái qua heartbeat;
# token không bao giờ rời host. Không có file thì mọi thứ y như cũ.

CLAUDE_ACCOUNTS_FILE = Path(os.getenv("CLAUDE_ACCOUNTS_FILE",
                                      str(ROOT / "config" / "claude_accounts.local.toml")))
# Bị chặn quota mà CLI không nói reset lúc nào (hoặc nói một mốc đã qua) → cho
# nghỉ chừng này rồi thử lại; vẫn bị chặn thì lại nghỉ tiếp — tự lành.
COOLDOWN_DEFAULT_S = int(os.getenv("CLAUDE_COOLDOWN_S", "1800"))

# Chỉ soi các chuỗi này trong result LỖI (không phải error_max_turns — chữ trong
# đó là Claude viết về task) và stderr khi exit != 0. Bám câu CLI thật sự in ra,
# không bắt "limit reached" chung chung vì context/output limit cũng nói vậy.
_RATE_LIMIT_RE = re.compile(r"usage limit|rate.?limit|hit your limit|out of extra usage", re.I)
# Token hỏng: chỉ tin câu của CLI/API. Không bắt "401" trần — MCP server hay git
# hook in "status 401" là chuyện của chúng, không phải của token Claude.
_AUTH_FAIL_RE  = re.compile(r"authentication[_ ](error|failed|token)|invalid api key"
                            r"|invalid.{0,30}(oauth|token|credentials)|oauth.{0,20}(expired|revoked|invalid)"
                            r"|not logged in|please run /login|(http|status|error)\W{0,3}401\b", re.I)
# Tool MCP bị từ chối vì chưa nằm trong --allowedTools. Câu CLI thật sự in ra:
# "Claude requested permissions to use mcp__x__y, but you haven't granted it yet."
# Phải tách khỏi "server trả lỗi": một cái sửa bằng hồ sơ quyền, cái kia sửa ở
# tận dịch vụ phía sau — chẩn đoán nhầm là mất cả buổi tối.
_MCP_DENIED_RE = re.compile(r"requested permissions|haven'?t granted", re.I)


def _epoch(v) -> float | None:
    """resetsAt của CLI: epoch giây, đôi khi mili-giây (> 1e12). Ngoài cửa sổ
    [-1 ngày, +30 ngày] quanh bây giờ thì coi là rác — 1 giá trị lạ không được
    phép làm snapshot() ném lỗi và chặn worker nhận việc."""
    try:
        ts = float(v)
    except (TypeError, ValueError):
        return None
    if ts > 1e12:
        ts /= 1000
    now = time.time()
    return ts if now - 86400 < ts < now + 30 * 86400 else None


def _iso(ts: float | None) -> str | None:
    try:
        return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None
    except (OverflowError, OSError, ValueError):
        return None


def _reset_txt(ts: float | None) -> str:
    if not ts:
        return ""
    try:
        d = datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return ""
    fmt = "%H:%M" if ts - time.time() < 86400 else "%H:%M %d/%m"   # quota 7 ngày → phải thấy ngày
    return f" (reset {d.strftime(fmt)})"


_LIMIT_LABEL = {"five_hour": " 5 giờ", "seven_day": " 7 ngày"}


class _Account:
    __slots__ = ("name", "token", "cooling_until", "error")

    def __init__(self, name: str, token: str):
        self.name = name
        self.token = token
        self.cooling_until: float | None = None   # epoch; nghỉ tới lúc này vì hết quota
        self.error: str | None = None             # token hỏng — chỉ mở lại khi sửa file

    def env(self) -> dict:
        return {"CLAUDE_CODE_OAUTH_TOKEN": self.token}

    def usable(self, now: float) -> bool:
        return not self.error and (self.cooling_until is None or self.cooling_until <= now)


class _Accounts:
    """Danh sách tài khoản + trạng thái nghỉ/lỗi, giữ trong bộ nhớ worker.

    Đọc lại file theo (mtime, size) nên sửa token không cần khởi động lại. Sửa
    file = người dùng vừa đổi token → xoá cờ lỗi; giờ nghỉ quota thì giữ theo
    tên, vì hết quota là chuyện của tài khoản chứ không phải của file.
    File hỏng cú pháp thì GIỮ danh sách cũ — đang gõ dở token không được làm
    mọi bước lặng lẽ rơi về đăng nhập trong ~/.claude."""

    def __init__(self, path: Path):
        self.path = path
        self._stamp: tuple[float, int] | None = None
        self._items: list[_Account] = []
        self.exists = False        # file có mặt không — để báo đúng "chưa có file" vs "file rỗng/hỏng"

    def __len__(self) -> int:
        self._load()
        return len(self._items)

    def _load(self) -> None:
        try:
            st = self.path.stat()
        except OSError:
            self._items, self._stamp, self.exists = [], None, False
            return
        self.exists = True
        stamp = (st.st_mtime, st.st_size)
        if stamp == self._stamp:
            return
        self._stamp = stamp            # ghi trước: file hỏng thì cũng chỉ cảnh báo 1 lần
        try:
            with open(self.path, "rb") as fh:
                raw = tomllib.load(fh).get("account")
        except Exception as e:
            print(f"[worker] ⚠️  {self.path.name} lỗi cú pháp, GIỮ danh sách cũ ({len(self._items)} tài khoản): {e}")
            return
        if isinstance(raw, dict):      # viết [account] thay vì [[account]] — hiểu là 1 tài khoản
            raw = [raw]
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            print(f"[worker] ⚠️  {self.path.name}: `account` phải là [[account]] (mảng bảng), GIỮ danh sách cũ")
            return
        old = {a.name: a for a in self._items}
        items: list[_Account] = []
        for row in raw:
            row = row if isinstance(row, dict) else {}
            name  = str(row.get("name") or "").strip()
            token = str(row.get("token") or "").strip()
            if not name or not token or token.endswith("..."):   # dòng mẫu chưa điền
                continue
            if any(a.name == name for a in items):
                print(f"[worker] ⚠️  {self.path.name}: tài khoản '{name}' khai 2 lần — bỏ dòng sau")
                continue
            a = _Account(name, token)
            if name in old:
                a.cooling_until = old[name].cooling_until
            items.append(a)
        self._items = items

    def pick(self, preferred: str | None, strict: bool = False) -> _Account | None:
        """Tài khoản người dùng chọn nếu còn dùng được; không thì tài khoản sẵn sàng
        đầu tiên theo thứ tự file; hết sạch thì None.
        `strict` (tự chuyển đang tắt): tài khoản chọn có trong file mà đang nghỉ/lỗi
        → None, không lén dùng tài khoản khác. Tên không có trong file thì vẫn rơi
        về tài khoản đầu tiên — đó là cấu hình lệch, không phải ý muốn giữ tài khoản."""
        self._load()
        now = time.time()
        usable = [a for a in self._items if a.usable(now)]
        if preferred:
            for a in usable:
                if a.name == preferred:
                    return a
            if any(a.name == preferred for a in self._items):
                if strict:
                    return None
                print(f"[worker] ⚠️  Tài khoản '{preferred}' đang nghỉ/lỗi — dùng tài khoản khác")
            else:
                print(f"[worker] ⚠️  Không có tài khoản '{preferred}' trong {self.path.name} — dùng tài khoản đầu tiên")
        return usable[0] if usable else None

    def get(self, name: str) -> _Account | None:
        self._load()
        return next((a for a in self._items if a.name == name), None)

    def cool(self, name: str, until: float | None) -> None:
        """Mốc reset đã qua / không có → nghỉ mặc định. Sau cool() tài khoản PHẢI
        hết usable, không thì vòng chuyển tài khoản lại chọn đúng nó."""
        self._load()
        now = time.time()
        for a in self._items:
            if a.name == name:
                a.cooling_until = until if until and until > now else now + COOLDOWN_DEFAULT_S

    def mark_error(self, name: str, why: str) -> None:
        self._load()
        for a in self._items:
            if a.name == name:
                a.error = why

    def earliest_reset(self) -> float | None:
        self._load()
        ts = [a.cooling_until for a in self._items if not a.error and a.cooling_until]
        return min(ts) if ts else None

    def tokens(self) -> list[str]:
        self._load()
        return [a.token for a in self._items]

    def snapshot(self) -> list[dict]:
        """Gửi lên dashboard: tên + trạng thái, KHÔNG có token."""
        self._load()
        now = time.time()
        out = []
        for a in self._items:
            if a.error:
                state, until = "error", None
            elif a.cooling_until and a.cooling_until > now:
                state, until = "cooling", a.cooling_until
            else:
                state, until = "ready", None
            out.append({"name": a.name, "state": state, "until": _iso(until), "note": a.error})
        return out


ACCOUNTS = _Accounts(CLAUDE_ACCOUNTS_FILE)


def _redact(text: str) -> str:
    """Token nằm trong env của tiến trình con — Claude có thể `echo` nó ra và dòng
    đó sẽ lên log/DB/UI. Che mọi token đã biết trước khi gửi bất cứ gì lên API.

    ĐÂY LÀ ĐIỂM CHE DUY NHẤT. Có bí mật mới thì thêm nguồn vào đây, đừng dựng
    điểm che thứ hai — hai điểm nghĩa là sẽ có một điểm bị quên."""
    for tok in ACCOUNTS.tokens():
        if tok and tok in text:
            text = text.replace(tok, "***")
    for path in MCP.secret_values():
        if path in text:
            text = text.replace(path, "***")
    return text


class _StepWatch:
    """Nhìn luồng sự kiện của 1 lần chạy để quyết định có được chạy lại bằng tài
    khoản khác không: đã gọi tool (có thể đã sửa file) thì không chạy lại mù."""

    def __init__(self):
        self.tool_used   = False
        self.limit_hit   = False
        self.auth_failed = False
        self.saw_result  = False        # CLI có phát sự kiện result không (chết sớm thì không)
        self.resets_at: float | None = None
        self.limit_type: str | None = None
        # ── Quan sát MCP ─────────────────────────────────────────────────────
        self.saw_init    = False        # đã thấy system/init chưa (mốc khởi động server)
        self.mcp_servers: list[tuple[str, str]] = []   # [(tên, trạng thái)] từ init
        self.mcp_denied: list[str] = []      # tool bị từ chối vì chưa cấp quyền
        self.mcp_errors: list[str] = []      # tool MCP trả lỗi (không phải chuyện quyền)
        # Server MCP trả lỗi xác thực (Google thu quyền service account chẳng hạn).
        # Giữ riêng để KHÔNG quy thành "token Claude hỏng" — xem feed_text.
        self.mcp_auth_error = False
        self._tool_names: dict[str, str] = {}   # tool_use_id → tên tool

    def feed(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            self.saw_init = True
            for srv in (ev.get("mcp_servers") or []):
                if isinstance(srv, dict):
                    self.mcp_servers.append((str(srv.get("name") or "?"),
                                             str(srv.get("status") or "?")))
        if t == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self.tool_used = True
                    if block.get("id"):
                        self._tool_names[str(block["id"])] = str(block.get("name") or "")
        elif t == "user":
            # tool_result không mang tên tool, chỉ mang tool_use_id — tra ngược để
            # biết lỗi này của MCP hay của tool nội bộ.
            for block in (ev.get("message") or {}).get("content") or []:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"
                        and block.get("is_error")):
                    continue
                name = self._tool_names.get(str(block.get("tool_use_id") or ""), "")
                if not name.startswith("mcp__"):
                    continue
                text = _result_text(block.get("content"))
                if _MCP_DENIED_RE.search(text):
                    self.mcp_denied.append(name)
                else:
                    self.mcp_errors.append(f"{name}: {_short(text, 160)}")
                    if _AUTH_FAIL_RE.search(text):
                        self.mcp_auth_error = True
        elif t == "rate_limit_event":
            info = ev.get("rate_limit_info") or {}
            if info.get("status") == "rejected":
                self.limit_hit  = True
                self.limit_type = info.get("rateLimitType")
                self.resets_at  = _epoch(info.get("resetsAt")) or self.resets_at
        elif t == "result":
            self.saw_result = True
            sub = ev.get("subtype")
            # error_max_turns: bước hết lượt, chữ trong result là của Claude viết về
            # task — soi "rate limit" trong đó là bắt nhầm.
            if (ev.get("is_error") or sub != "success") and sub != "error_max_turns":
                self.feed_text(ev.get("result") or "")
                for e in ev.get("errors") or []:
                    self.feed_text(str(e))

    def feed_text(self, text: str, from_stderr: bool = False) -> None:
        """Chữ trong result lỗi / stderr — CLI cũ không phát rate_limit_event mà chỉ in câu.
        stderr chỉ được kết luận "token hỏng" khi CLI chết mà không có result: token
        hỏng là chết ngay từ đầu; còn chạy được tới result thì "401" trong stderr là
        của MCP/git hook."""
        if not text:
            return
        if _RATE_LIMIT_RE.search(text):
            self.limit_hit = True
            m = re.search(r"\|(\d{10,13})\b", text)     # dạng cũ: "usage limit reached|1700000000"
            if m and self.resets_at is None:
                self.resets_at = _epoch(int(m.group(1)))
        elif _AUTH_FAIL_RE.search(text) and not (from_stderr and self.saw_result):
            # Server MCP đã trả lỗi xác thực trước đó → chữ "authentication failed"
            # trong result là Claude đang THUẬT LẠI lỗi của Google, không phải token
            # của nó hỏng. Kết luận nhầm ở đây làm tài khoản Pro bị cho nghỉ oan và
            # bị loại khỏi vòng xoay. stderr trước khi có result vẫn tin như cũ.
            if self.mcp_auth_error and not from_stderr:
                return
            self.auth_failed = True

    def why(self) -> str:
        if self.auth_failed:
            return "token lỗi"
        return f"hết quota{_LIMIT_LABEL.get(self.limit_type or '', '')}{_reset_txt(self.resets_at)}"

    def mcp_problem(self) -> str | None:
        """Bốn nguyên nhân hỏng liên quan MCP → thông báo hai vế: nguyên nhân +
        chỗ sửa. None nghĩa là MCP không phải thủ phạm."""
        if self.mcp_denied:
            names = ", ".join(sorted(set(self.mcp_denied)))
            return (f"Tool {names} chưa được cấp quyền. Hồ sơ quyền của server không có tool này — "
                    f"đổi `profile` trong clients/<slug>/mcp.json, hoặc thêm tool vào hồ sơ trong "
                    f"config/mcp_templates.toml.")
        dead = [n for n, st in self.mcp_servers if st != "connected"]
        if dead:
            return (f"Server MCP không khởi động được: {', '.join(dead)}. Kiểm tra `command` và `args` "
                    f"của template trong config/mcp_templates.toml, và xem server đã được cài chưa.")
        if self.mcp_errors:
            return (f"Server MCP trả lỗi: {self.mcp_errors[0]}. Đây là lỗi của server hoặc của dịch vụ "
                    f"phía sau nó, không phải lỗi tài khoản Claude.")
        return None



# Kết quả nối MCP của lần chạy gần nhất, theo (dự án, server). API chạy trong
# container nên tự nó không biết được server trên host có lên nổi không — chỉ
# worker biết, và nó gửi kèm nhịp tim sẵn có thay vì mở endpoint mới.
MCP_SEEN: dict[tuple[str, str], dict] = {}


def _mcp_note(slug: str | None, servers: list[tuple[str, str]]) -> None:
    if not slug:
        return
    now = _iso(time.time())
    for name, state in servers:
        MCP_SEEN[(slug, name)] = {"slug": slug, "server": name, "status": state, "at": now}


def _mcp_snapshot() -> list[dict]:
    return list(MCP_SEEN.values())[:200]


def _claim_step() -> dict | None:
    """Job bước workflow (chạy bằng Claude headless). Server giữ tuần tự.
    Gửi kèm trạng thái tài khoản Claude và trạng thái MCP — dashboard hiện lại."""
    return _req("/api/workflow-jobs/claim",
                body={"accounts": ACCOUNTS.snapshot(), "mcp": _mcp_snapshot()},
                method="POST")


def _complete_step(job_id: int, status: str, output: str = "", error: str = "",
                   metrics: dict | None = None):
    try:
        _req(f"/api/workflow-jobs/{job_id}/complete",
             body={"status": status, "output": _redact(output[-8000:]), "error": _redact(error[:2000]),
                   **(metrics or {})},
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
    mcp_env: dict = {}          # opencode không có MCP ở đây; nhánh claude điền

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

        # ── Cổng DUY NHẤT của MCP ────────────────────────────────────────────
        # Dự án không khai MCP → _mcp_plan trả rỗng → lệnh không đổi một chữ so
        # với trước khi có tính năng này. Mọi tham số mới nằm sau cổng này, không
        # rải if khắp nơi: một cổng thì kiểm được bằng một test.
        mcp_cmd, mcp_env, mcp_problems = _mcp_plan(job.get("client_folder"))
        if mcp_problems:
            msg = " ".join(mcp_problems)
            print(f"[worker] ❌ Step job #{job_id}: cấu hình MCP chưa chạy được — {msg}")
            _complete_step(job_id, "failed", error=msg)
            return
        cmd += mcp_cmd

    print(f"\n[worker] 🤖 Step job #{job_id} — {label} (run #{job['run_id']})")
    git_env = _project_git_env(job.get("client_folder"), job.get("agent_key"))

    print(f"[worker]    engine: {tool}{f' · {model}' if model else ''}")
    print(f"[worker]    {job.get('file_path') or ''}")
    if git_env:
        print(f"[worker]    git: token riêng ({'agent ' + job['agent_key'] if job.get('agent_key') else 'project'}) "
              "từ settings.local.toml")
    progress = _Progress(job_id)

    # Tài khoản Claude: dashboard chọn tên, worker cầm token. Không có file tài
    # khoản (None) → env giữ nguyên, CLI dùng đăng nhập trong ~/.claude như cũ.
    auto_switch = bool(job.get("claude_auto_switch", True))
    chosen = job.get("claude_account")
    account = ACCOUNTS.pick(chosen, strict=not auto_switch) if tool != "opencode" else None
    if account is None and tool != "opencode" and len(ACCOUNTS):
        # Có file tài khoản mà không lấy được cái nào: tự chuyển tắt và tài khoản
        # chọn đang nghỉ, hoặc tất cả đều nghỉ. Không lén rơi về ~/.claude.
        held = ACCOUNTS.get(chosen) if chosen else None
        if held is not None and not auto_switch:
            msg = (f"Tài khoản Claude '{chosen}' đang {'lỗi: ' + held.error if held.error else 'nghỉ' + _reset_txt(held.cooling_until)}. "
                   "Tự chuyển đang tắt — chọn tài khoản khác trong Settings rồi chạy lại.")
        else:
            msg = f"Không còn tài khoản Claude nào sẵn sàng{_reset_txt(ACCOUNTS.earliest_reset())}."
        progress.add(f"❌ {msg}")
        print(f"[worker] ❌ Step job #{job_id}: {msg}")
        _complete_step(job_id, "failed", error=msg)
        return
    tried = 0
    while True:
        env = {**os.environ, **git_env, **mcp_env, **(account.env() if account else {})}
        if account:
            progress.add(f"🔑 Tài khoản Claude: {account.name}")
        watch = _StepWatch()
        try:
            code, out, err, metrics = _run_streaming(cmd, env, progress,
                                                     parse_json=(tool != "opencode"),
                                                     timeout=STEP_TIMEOUT_S, watch=watch,
                                                     init_timeout=MCP_START_TIMEOUT_S if mcp_cmd else None)
        except _McpStartTimeout as e:
            _mcp_note(job.get("client_folder"),
                      [(s.name, "start-timeout") for s in MCP.servers(job.get("client_folder"))])
            names = ", ".join(s.name for s in MCP.servers(job.get("client_folder"))) or "?"
            msg = (f"Server MCP ({names}) không khởi động được trong {e.args[0]} giây. "
                   f"Kiểm tra `command` và `args` của template trong config/mcp_templates.toml, "
                   f"và xem server đã được cài chưa.")
            progress.add(f"❌ {msg}")
            print(f"[worker] ❌ Step job #{job_id}: {msg}")
            _complete_step(job_id, "failed", error=msg)
            return
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
        _mcp_note(job.get("client_folder"), watch.mcp_servers)
        failed = code != 0 or (tool == "opencode" and "Error:" in err and not out)
        if failed:
            watch.feed_text(err, from_stderr=True)
        # Ghi trạng thái tài khoản TRƯỚC khi tính chuyện chuyển — kể cả khi bước
        # vẫn xong (CLI tự chờ rồi chạy tiếp), tài khoản đó đã hết quota là thật.
        if account and watch.auth_failed:
            ACCOUNTS.mark_error(account.name, "token không hợp lệ — chạy lại `claude setup-token`")
        elif account and watch.limit_hit:
            ACCOUNTS.cool(account.name, watch.resets_at)

        if not failed:
            print(f"[worker] ✅ Step job #{job_id} xong — dashboard sẽ đọc lại file task")
            _complete_step(job_id, "done", output=out, metrics=metrics)
            return

        if not (account and (watch.limit_hit or watch.auth_failed)):
            # MCP là thủ phạm thì nói thẳng nguyên nhân và chỗ sửa, đừng ném ra
            # exit code để người vận hành tự đoán lúc 11 giờ đêm.
            why = watch.mcp_problem() or err or f"{tool} exit code {code}"
            print(f"[worker] ❌ Step job #{job_id} thất bại (exit {code})")
            _complete_step(job_id, "failed", output=out, error=why, metrics=metrics)
            return

        # Tài khoản này chết vì quota/token. Còn tài khoản khác và Claude CHƯA gọi
        # tool nào (chưa sửa gì) → chạy lại nguyên bước bằng tài khoản kế tiếp.
        # Đã gọi tool thì không chạy chồng — fail, nói rõ để người dùng bấm chạy lại.
        why = watch.why()
        nxt = ACCOUNTS.pick(None) if auto_switch else None
        if nxt is not None and nxt.name == account.name:   # cool()/mark_error() phải loại nó rồi — phòng hờ
            nxt = None
        tried += 1
        if nxt and not watch.tool_used and tried < len(ACCOUNTS):
            progress.add(f"🔁 {account.name} {why} → chuyển sang {nxt.name}, chạy lại bước")
            print(f"[worker] 🔁 Step job #{job_id}: {account.name} {why} → {nxt.name}")
            account = nxt
            continue
        if nxt:
            hint = f"Bước kế tiếp sẽ dùng {nxt.name} — bấm chạy lại bước này."
        elif not auto_switch:
            hint = "Tự chuyển đang tắt — chọn tài khoản khác trong Settings rồi chạy lại."
        else:
            hint = f"Không còn tài khoản nào sẵn sàng{_reset_txt(ACCOUNTS.earliest_reset())}."
        msg = f"Tài khoản Claude '{account.name}' {why}. {hint}"
        progress.add(f"❌ {msg}")
        print(f"[worker] ❌ Step job #{job_id}: {msg}")
        _complete_step(job_id, "failed", output=out, error=msg, metrics=metrics)
        return


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
    n_acc = len(ACCOUNTS)
    if n_acc:
        print(f"[worker]   claude accounts = {', '.join(a['name'] for a in ACCOUNTS.snapshot())} "
              f"({CLAUDE_ACCOUNTS_FILE.name}) — chọn ở Dashboard → Settings")
    elif ACCOUNTS.exists:
        print(f"[worker]   ⚠️  {CLAUDE_ACCOUNTS_FILE.name} có mặt nhưng KHÔNG có tài khoản hợp lệ "
              f"(xem cảnh báo bên trên) → dùng đăng nhập trong ~/.claude")
    else:
        print(f"[worker]   claude accounts = (không có {CLAUDE_ACCOUNTS_FILE.name} → dùng đăng nhập trong ~/.claude)")
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
