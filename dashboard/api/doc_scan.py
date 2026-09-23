"""
Quét tài liệu dự án
===================
Chụp ảnh thư mục tài liệu (`clients/{slug}/`) thành `{đường_dẫn_tương_đối: sha256}`
rồi so với ảnh lần trước để biết "có gì đổi không".

Vì sao snapshot chứ không phải watchdog: ở đây cần quét THEO LỊCH, không cần theo
dõi thời gian thực. Chạy một observer thường trú chỉ để trả lời câu hỏi mỗi ngày
một lần là thừa.

Module này CỐ Ý không import DB và không import FastAPI — nhờ vậy test được bằng
thư mục tạm, không cần dựng Postgres. Nó cũng thuần đồng bộ: người gọi phải đẩy
sang `asyncio.to_thread`, vì hash vài trăm file trong event loop sẽ treo cả API
(cùng lý do slack_bot/telegram_bot phải nằm ở thread riêng — xem main.py).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List

# Thư mục tài liệu. Trong container là /clients (docker-compose mount ../clients).
CLIENTS_DIR = os.getenv("CLIENTS_DIR", "/clients")

# Thư mục không bao giờ quét — vừa vô nghĩa vừa đủ lớn để làm treo một lần quét.
#
# `output` là thứ QUAN TRỌNG NHẤT trong danh sách này: theo quy ước của repo
# (xem routers/projects.py, khối `[output]` trong settings.toml), thư mục code do
# pipeline sinh ra nằm ở `clients/<slug>/.../output/`. Không loại nó thì thành
# vòng lặp tự nuôi: pipeline chạy -> ghi code vào output -> lần quét sau thấy
# composer.json/README.md đổi -> kết luận "tài liệu thay đổi" -> chạy pipeline
# tiếp, mãi mãi. Đã quan sát thấy trên dữ liệu thật của dự án `booking`.
# `_tasks` cũng vậy: routers/workflows.py ghi một file .md vào
# `clients/<slug>/_tasks/` cho MỖI node của MỖI lần chạy workflow (nội dung có
# `status`, `run_id`, `node_id`). Đó là trạng thái máy sinh ra, không phải tài
# liệu người viết — để lại thì cứ chạy workflow là lần quét sau báo "có thay đổi".
_DEFAULT_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea",
                 ".vscode", "dist", "build", ".next", ".cache", ".pytest_cache",
                 "output", "vendor", "_tasks"}
# Thêm thư mục cần bỏ qua mà không phải sửa code: DOC_SCAN_SKIP_DIRS="a,b,c"
SKIP_DIRS = _DEFAULT_SKIP | {
    d.strip() for d in os.getenv("DOC_SCAN_SKIP_DIRS", "").split(",") if d.strip()
}

# Đuôi file coi là tài liệu. Ảnh/binary không nằm trong này — đổi một tấm PNG
# không phải là "tài liệu thay đổi" theo nghĩa cần chạy lại pipeline.
DOC_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc",
                ".yaml", ".yml", ".toml", ".json", ".csv"}

# File cấu hình của dự án, KHÔNG phải tài liệu. `settings.local.toml` còn giữ
# credential (xem mcp_store.py) — đổi một cái token mà kích hoạt "tài liệu thay
# đổi" rồi chạy cả pipeline là vừa sai nghĩa vừa tốn tiền.
SKIP_FILES = {"settings.toml", "settings.local.toml", "mcp.json",
              "package-lock.json", "composer.lock", "yarn.lock"}

MAX_FILE_BYTES = int(os.getenv("DOC_SCAN_MAX_FILE_BYTES", str(5 * 1024 * 1024)))
MAX_FILES      = int(os.getenv("DOC_SCAN_MAX_FILES", "5000"))


class DocScanError(Exception):
    """Thư mục không tồn tại / không đọc được. Người gọi biến thành last_status='error'."""


def docs_path(slug: str) -> Path:
    return Path(CLIENTS_DIR) / slug


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_dir(root: Path | str) -> Dict[str, str]:
    """Trả `{đường_dẫn_tương_đối (dùng '/'): sha256}` cho mọi file tài liệu dưới `root`.

    Đường dẫn luôn dùng dấu '/' kể cả trên Windows — snapshot phải so sánh được
    giữa lần chạy trên host và lần chạy trong container.
    """
    root = Path(root)
    if not root.exists():
        raise DocScanError(f"Thư mục tài liệu không tồn tại: {root}")
    if not root.is_dir():
        raise DocScanError(f"Không phải thư mục: {root}")

    out: Dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Cắt nhánh tại chỗ — os.walk đọc lại `dirnames` nên gán lại là bỏ qua cả cây.
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fname in sorted(filenames):
            if fname in SKIP_FILES or Path(fname).suffix.lower() not in DOC_SUFFIXES:
                continue
            fpath = Path(dirpath) / fname
            try:
                if fpath.stat().st_size > MAX_FILE_BYTES:
                    continue
                rel = fpath.relative_to(root).as_posix()
                out[rel] = _sha256(fpath)
            except OSError:
                # File bị xoá/khoá giữa chừng: bỏ qua 1 file, không làm hỏng cả lần quét.
                continue
            if len(out) >= MAX_FILES:
                return out
    return out


def diff(old: Dict[str, str], new: Dict[str, str]) -> Dict[str, List[str]]:
    """So hai snapshot. Trả các danh sách đã sắp xếp để log và thông báo ổn định."""
    old_keys, new_keys = set(old), set(new)
    return {
        "added":   sorted(new_keys - old_keys),
        "removed": sorted(old_keys - new_keys),
        "changed": sorted(k for k in old_keys & new_keys if old[k] != new[k]),
    }


def has_changes(d: Dict[str, List[str]]) -> bool:
    return bool(d["added"] or d["removed"] or d["changed"])


def summarize(d: Dict[str, List[str]], limit: int = 5) -> str:
    """Câu mô tả ngắn cho log và tin nhắn Telegram/Slack."""
    if not has_changes(d):
        return "không có thay đổi"
    parts = []
    for label, key in (("thêm", "added"), ("sửa", "changed"), ("xoá", "removed")):
        names = d[key]
        if not names:
            continue
        shown = ", ".join(names[:limit])
        more = f" (+{len(names) - limit} nữa)" if len(names) > limit else ""
        parts.append(f"{label} {len(names)}: {shown}{more}")
    return "; ".join(parts)
