"""
Runner
======
Chạy Claude Code CLI và OpenCode CLI qua subprocess.
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


async def run_claude(prompt: str, work_dir: Path) -> str:
    cfg         = get_config()
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = write_prompt_file(prompt, "claude")

    cmd = _resolve_cmd("claude") + [
        "-p",
        f"Read the instructions at {prompt_file} and follow them exactly.",
        "--allowedTools", "Read,Write,Edit,Bash",
        "--output-format", "text",
        "--dangerously-skip-permissions",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=cfg.timeout_claude
    )
    prompt_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[:400])
    return stdout.decode("utf-8", errors="replace")


async def run_opencode(model: str, prompt: str, work_dir: Path) -> str:
    cfg         = get_config()
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = write_prompt_file(prompt, "opencode")

    cmd = _resolve_cmd("opencode") + [
        "run", "--model", model,
        "--dangerously-skip-permissions",
        "-f", str(prompt_file),
        "Follow the instructions in the attached file exactly. Implement everything as specified.",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(work_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=cfg.timeout_opencode
    )
    prompt_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[:400])
    return stdout.decode("utf-8", errors="replace")


async def run(role: str, prompt: str, work_dir: Path) -> str:
    """Dispatch đúng runner dựa theo config."""
    cfg       = get_config()
    agent_cfg = cfg.agents[role]

    if agent_cfg.tool == "claude":
        return await run_claude(prompt, work_dir)
    else:
        return await run_opencode(agent_cfg.model, prompt, work_dir)
