"""
Nhịp tim của worker trên host
=============================
Dashboard không thể tự biết `python worker.py` có đang mở hay không — worker
nằm ngoài container. Nhưng mỗi vòng poll nó đều gọi /claim, nên chỉ cần ghi
lại thời điểm gọi gần nhất là đủ để UI phân biệt 2 tình huống rất khác nhau:

  - job nằm im vì **chưa ai chạy worker**  → bảo người dùng mở terminal;
  - job nằm im vì **worker đang bận** job khác → chỉ cần chờ.

Lưu trong bộ nhớ tiến trình: mất khi API restart (worker sẽ chạm lại sau vài
giây), và không chính xác nếu chạy nhiều tiến trình API — chấp nhận được cho
một chỉ báo trạng thái.

Lưu ý: lúc worker đang chạy 1 job pipeline (`main.py`) nó KHÔNG poll, nên chỗ
này sẽ báo "im lặng" dù process vẫn sống. Đó cũng là sự thật hữu ích: khi ấy
worker không nhận thêm job bước nào.
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

# worker poll mỗi 3s (WORKER_POLL_S) — 20s là quá đủ để coi là "im lặng"
_ONLINE_WINDOW = timedelta(seconds=20)

_lock = Lock()
_last_seen: Optional[datetime] = None


def touch() -> None:
    """Worker vừa hỏi việc."""
    global _last_seen
    with _lock:
        _last_seen = datetime.utcnow()


def status() -> dict:
    with _lock:
        seen = _last_seen
    if seen is None:
        return {"online": False, "last_seen": None, "silent_s": None}
    silent = (datetime.utcnow() - seen).total_seconds()
    return {
        "online": silent < _ONLINE_WINDOW.total_seconds(),
        "last_seen": seen.isoformat(),
        "silent_s": int(silent),
    }
