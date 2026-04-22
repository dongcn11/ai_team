"""
AI Team Orchestrator
====================
Entry point chính. Chạy: python main.py

Hoặc với PRD file:
    python main.py --prd ./my_prd.md

Hoặc với PRD text trực tiếp:
    python main.py --text "Build một todo app..."
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Windows terminal thường dùng cp1252 — ép UTF-8 để in tiếng Việt không lỗi
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Windows: dùng SelectorEventLoop để tránh lỗi unclosed pipe trên ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from ai_team.orchestrator import orchestrate


def parse_args():
    parser = argparse.ArgumentParser(description="AI Team Orchestrator")
    group  = parser.add_mutually_exclusive_group()
    group.add_argument("--prd",  type=str, help="Đường dẫn file PRD (.md hoặc .txt)")
    group.add_argument("--text", type=str, help="PRD text trực tiếp")
    parser.add_argument("--output", type=str, default="./output", help="Thư mục output (default: ./output)")
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

    # Dùng PRD mặc định nếu không truyền tham số
    default_prd = Path("./prd.md")
    if default_prd.exists():
        print(f"[main] Dùng PRD từ {default_prd}")
        return default_prd.read_text(encoding="utf-8")

    print("ERROR: Không có PRD. Dùng --prd <file> hoặc --text <text>")
    print("       Hoặc tạo file prd.md trong thư mục hiện tại")
    sys.exit(1)


if __name__ == "__main__":
    args   = parse_args()
    prd    = load_prd(args)
    output = args.output

    asyncio.run(orchestrate(prd, output_dir=output))
