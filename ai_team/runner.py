"""
Runner
======
Chạy OpenCode CLI qua subprocess.

CHÍNH SÁCH — pipeline tự động KHÔNG dùng Claude Code
----------------------------------------------------
Claude Code chạy bằng subscription cá nhân. Subscription dành cho một người
thật, ngồi máy mình, thao tác ở tốc độ người. Pipeline này thì ngược lại:
worker chạy nền, hàng đợi nhiều project, agent song song, không ai giám sát.
Dùng subscription theo kiểu đó = truy cập tự động + cho người khác dùng chung
account → khoá account.

Vì vậy hệ thống tách làm 2 làn:

  Làn A — automation (worker.py, dashboard, clients/): chỉ OpenCode / model local.
  Làn B — Claude Code: bạn tự mở terminal gõ tay, không qua pipeline này.

`tool = "claude"` bị chặn cứng ở cả config load lẫn runner. Đừng gỡ chốt này
để "chạy nhanh một lần" — đó chính xác là cách account bị khoá lần trước.
"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from ai_team.config import get as get_config


def _resolve_cmd(name: str) -> list[str]:
    """Trả về command list có thể chạy được trên mọi platform."""
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"Không tìm thấy CLI '{name}'. Hãy cài đặt và thêm vào PATH.")
    # .cmd/.bat trên Windows cần chạy qua cmd /c
    if sys.platform == "win32" and Path(path).suffix.lower() in (".cmd", ".bat"):
        return ["cmd", "/c", name]
    return [path]


def write_prompt_file(prompt: str, label: str) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".md", prefix=f"_prompt_{label}_"))
    tmp.write_text(prompt, encoding="utf-8")
    return tmp


CLAUDE_BLOCKED_MSG = (
    "Claude Code bị chặn trong pipeline tự động (xem docstring đầu file).\n"
    "  Sửa: đổi <agent>_tool = \"opencode\" trong settings.toml của project.\n"
    "  Cần Claude? Mở terminal và gõ `claude` thủ công — đừng gọi qua worker."
)


async def run_claude(prompt: str, work_dir: Path, timeout: int | None = None) -> str:
    raise RuntimeError(CLAUDE_BLOCKED_MSG)


async def run_opencode(model: str, prompt: str, work_dir: Path, timeout: int | None = None) -> str:
    cfg         = get_config()
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = write_prompt_file(prompt, "opencode")

    cmd = _resolve_cmd("opencode") + [
        "run",
        "Follow the instructions in the attached file exactly.",
        "--model", model,
        "--dangerously-skip-permissions",
        "-f", str(prompt_file),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=timeout if timeout is not None else cfg.timeout_opencode
    )
    prompt_file.unlink(missing_ok=True)

    stderr_text = stderr.decode("utf-8", errors="replace")
    stdout_text = stdout.decode("utf-8", errors="replace")
    # opencode exits 0 even on fatal errors — detect via stderr content
    if proc.returncode != 0 or ("Error:" in stderr_text and not stdout_text.strip()):
        raise RuntimeError(stderr_text[:500] or stdout_text[:200] or f"exit code {proc.returncode}")
    return stdout_text


async def run(role: str, prompt: str, work_dir: Path, timeout: int | None = None) -> str:
    """Dispatch đúng runner dựa theo config. timeout override per-stage nếu truyền vào."""
    cfg       = get_config()
    agent_cfg = cfg.agents[role]

    if agent_cfg.tool == "claude":
        raise RuntimeError(f"[{role}] {CLAUDE_BLOCKED_MSG}")

    return await run_opencode(agent_cfg.model, prompt, work_dir, timeout=timeout)
