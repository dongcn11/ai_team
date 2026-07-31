"""
Claude Quota Guard
==================
Giới hạn cứng cho mọi lời gọi Claude Code do người bấm (node `runtime="claude"`
trong workflow). Ba việc, theo thứ tự quan trọng:

1. **Tuần tự tuyệt đối** — semaphore = 1. Không bao giờ 2 phiên Claude cùng lúc.
2. **Trần theo cửa sổ** — max N lần / 5 giờ và / 24 giờ. Gói subscription tính
   theo cửa sổ rolling, nên trần 5 giờ là cái sát thực tế nhất.
3. **Khoảng nghỉ tối thiểu** giữa 2 lần gọi — chặn kiểu bấm liên tục thành chuỗi.

State persist ra file ở `~` (không phải trong repo, không phải /tmp) → restart
worker không reset được counter. Đó là chủ ý: counter reset được thì trần vô nghĩa.

Đây **không** phải để traffic "trông giống người". Nó thực sự giảm tải và thực sự
ép có người bấm. Đừng nâng trần lên cho bằng chạy 24/7 — làm vậy thì quay lại
đúng chỗ đã bị khoá account.

Tune qua env:
    CLAUDE_MAX_PER_5H   (mặc định 8)
    CLAUDE_MAX_PER_DAY  (mặc định 25)
    CLAUDE_MIN_GAP_S    (mặc định 90; đặt 0 để tắt — chỉ dùng trong test)
    CLAUDE_QUOTA_STATE  (đường dẫn file state)
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

_WINDOW_5H = 5 * 3600
_WINDOW_DAY = 24 * 3600

_LOCK = asyncio.Semaphore(1)


class QuotaExceeded(RuntimeError):
    """Chạm trần — không phải lỗi tạm thời, đừng retry trong vòng lặp."""


def _state_path() -> Path:
    raw = os.getenv("CLAUDE_QUOTA_STATE")
    return Path(raw) if raw else Path.home() / ".ai_team_claude_quota.json"


def _limits() -> tuple[int, int, int]:
    return (
        int(os.getenv("CLAUDE_MAX_PER_5H", "8")),
        int(os.getenv("CLAUDE_MAX_PER_DAY", "25")),
        int(os.getenv("CLAUDE_MIN_GAP_S", "90")),
    )


def _load() -> dict:
    path = _state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"calls": []}
    calls = data.get("calls")
    if not isinstance(calls, list):
        return {"calls": []}
    return {"calls": [float(t) for t in calls if isinstance(t, (int, float))]}


def _save(state: dict) -> None:
    """Ghi atomic — tránh file rỗng nếu process chết giữa lúc ghi."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".quota_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def usage(now: float | None = None) -> dict:
    """Số liệu hiện tại — dùng cho API/UI, không tính phí."""
    now = now if now is not None else time.time()
    max_5h, max_day, min_gap = _limits()
    calls = [t for t in _load()["calls"] if now - t < _WINDOW_DAY]
    in_5h = [t for t in calls if now - t < _WINDOW_5H]
    last = max(calls) if calls else 0.0
    return {
        "used_5h": len(in_5h),
        "max_5h": max_5h,
        "used_day": len(calls),
        "max_day": max_day,
        "min_gap_s": min_gap,
        "seconds_since_last": int(now - last) if last else None,
        "next_5h_slot_in_s": int(_WINDOW_5H - (now - min(in_5h))) if len(in_5h) >= max_5h else 0,
    }


def _charge(now: float | None = None) -> None:
    """Ghi nhận 1 lần gọi. Raise QuotaExceeded nếu vượt trần.
    Gọi lúc *acquire*, không phải lúc xong — thất bại vẫn tính, cố ý bảo thủ."""
    now = now if now is not None else time.time()
    max_5h, max_day, _ = _limits()

    state = _load()
    calls = [t for t in state["calls"] if now - t < _WINDOW_DAY]
    in_5h = [t for t in calls if now - t < _WINDOW_5H]

    if len(in_5h) >= max_5h:
        wait_min = int((_WINDOW_5H - (now - min(in_5h))) / 60)
        raise QuotaExceeded(
            f"Chạm trần {max_5h} lần Claude / 5 giờ. Slot tiếp theo sau ~{wait_min} phút. "
            "Cần chạy ngay thì dùng node runtime=\"opencode\"."
        )
    if len(calls) >= max_day:
        raise QuotaExceeded(
            f"Chạm trần {max_day} lần Claude / ngày. Tiếp tục ngày mai, "
            "hoặc chuyển node sang runtime=\"opencode\"."
        )

    calls.append(now)
    _save({"calls": calls})


@asynccontextmanager
async def claude_slot():
    """Bọc quanh MỌI lời gọi Claude Code.

        async with claude_slot():
            await run_claude_cli(...)

    Giữ semaphore suốt thời gian chạy → lời gọi thứ 2 phải chờ, không chạy song song.
    """
    async with _LOCK:
        _, _, min_gap = _limits()
        if min_gap > 0:
            calls = _load()["calls"]
            if calls:
                gap = min_gap - (time.time() - max(calls))
                if gap > 0:
                    await asyncio.sleep(gap)
        _charge()
        yield


def reset_for_tests() -> None:
    """Xoá state. Chỉ dùng trong test — bắt buộc trỏ CLAUDE_QUOTA_STATE ra
    file tạm trước, để không xoá counter thật của máy."""
    if not os.getenv("CLAUDE_QUOTA_STATE"):
        raise RuntimeError("reset_for_tests() cần CLAUDE_QUOTA_STATE trỏ tới file tạm")
    _state_path().unlink(missing_ok=True)
