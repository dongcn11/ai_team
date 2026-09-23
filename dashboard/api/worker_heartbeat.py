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

Cùng nhịp tim, worker gửi kèm trạng thái các tài khoản Claude nó cầm token
(config/claude_accounts.local.toml trên host): tên + sẵn sàng / đang nghỉ quota
tới lúc nào / lỗi. Chỉ tên và trạng thái — token không bao giờ qua API.
Trang Settings đọc cái này để người dùng chọn tài khoản mà không cần terminal.
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

# worker poll mỗi 3s (WORKER_POLL_S) — 20s là quá đủ để coi là "im lặng"
_ONLINE_WINDOW = timedelta(seconds=20)

_lock = Lock()
_last_seen: Optional[datetime] = None
# [{name, state: ready|cooling|error, until: iso|None, note: str|None}]
_accounts: list[dict] = []
# Trạng thái MCP lần chạy gần nhất, theo (dự án, server):
# [{slug, server, status, at}]. Worker gửi kèm cùng nhịp tim — API chạy trong
# container nên tự nó không thể biết server trên host có lên được không.
_mcp: list[dict] = []


def touch(accounts: Optional[list[dict]] = None, mcp: Optional[list[dict]] = None) -> None:
    """Worker vừa hỏi việc. `accounts` = snapshot tài khoản Claude nếu worker gửi
    (chỉ /workflow-jobs/claim gửi; /run-jobs/claim thì không → giữ bản cũ).
    `mcp` cũng vậy: None nghĩa là không có tin mới, giữ bản cũ."""
    global _last_seen, _accounts, _mcp
    with _lock:
        _last_seen = datetime.utcnow()
        if accounts is not None:
            _accounts = accounts
        if mcp is not None:
            _mcp = mcp


def status() -> dict:
    with _lock:
        seen = _last_seen
        accounts = list(_accounts)
        mcp = list(_mcp)
    if seen is None:
        return {"online": False, "last_seen": None, "silent_s": None,
                "accounts": accounts, "mcp": mcp}
    silent = (datetime.utcnow() - seen).total_seconds()
    return {
        "online": silent < _ONLINE_WINDOW.total_seconds(),
        "last_seen": seen.isoformat(),
        "silent_s": int(silent),
        "accounts": accounts,
        "mcp": mcp,
    }
