"""
AI Team Orchestrator
====================
Entry point chính. Chạy: python main.py

Ví dụ:
    python main.py --prd ./my_prd.md
    python main.py --prd ./my_prd.md --profile backend_only
    python main.py --config ./clients/project_alpha/settings.toml --prd ./clients/project_alpha/prd.md
    python main.py --text "Build một todo app..."
"""

import argparse
import asyncio
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

if sys.platform == "win32":
    # ProactorEventLoop required for subprocess support on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from ai_team import config as cfg_module
from ai_team.orchestrator import orchestrate


def parse_args():
    parser = argparse.ArgumentParser(description="AI Team Orchestrator")
    group  = parser.add_mutually_exclusive_group()
    group.add_argument("--prd",  type=str, help="Đường dẫn file PRD (.md hoặc .txt)")
    group.add_argument("--text", type=str, help="PRD text trực tiếp")
    parser.add_argument("--output",  type=str, help="Thư mục output (mặc định: từ settings.toml)")
    parser.add_argument("--config",  type=str, help="Đường dẫn settings.toml cho project này")
    parser.add_argument("--profile", type=str, help="Profile team: fullstack, backend_only, api_only, mobile_app, ...")
    return parser.parse_args()


def load_prd(args) -> str:
    if args.prd:
        path = Path(args.prd)
        if not path.exists():
            print(f"ERROR: Không tìm thấy file {path}")
            sys.exit(1)
        return path.read_text(encoding="utf-8")

    if args.text:
        return args.text

    default_prd = Path("./prd.md")
    if default_prd.exists():
        print(f"[main] Dùng PRD từ {default_prd}")
        return default_prd.read_text(encoding="utf-8")

    print("ERROR: Không có PRD. Dùng --prd <file> hoặc --text <text>")
    sys.exit(1)


if __name__ == "__main__":
    args = parse_args()

    config_path = Path(args.config) if args.config else None
    cfg = cfg_module.init(config_path=config_path, profile=args.profile)

    prd    = load_prd(args)
    output = args.output or cfg.output_dir

    asyncio.run(orchestrate(prd, output_dir=output))
