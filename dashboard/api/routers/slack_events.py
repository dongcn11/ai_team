"""
Slack Events API — webhook nhận sự kiện app_mention
=====================================================
Slack POST tới đây khi bot bị tag (@bot) trong 1 kênh đã invite bot vào.

MỖI DỰ ÁN MỘT REQUEST URL
-------------------------
    /api/slack/events/<bot_id>   -> đúng 1 bot khai ở tab Bots

Chữ ký phải kiểm TRƯỚC khi được phép tin nội dung request, mà mỗi app Slack có
signing secret riêng. Cho mỗi dự án một URL thì biết ngay phải dùng secret nào —
thay vì dò thử lần lượt từng secret rồi đoán. Xem slack_bot.py.

Điều kiện bắt buộc: dashboard phải có URL HTTPS công khai (Cloudflare Tunnel,
ngrok, VPS...). Chạy localhost thì Slack không gọi vào được — đây là khác biệt
lớn nhất so với Telegram, bên đó bot tự đi ra nên không cần gì cả.

Cấu hình từng app trên Slack: bật Event Subscriptions, Request URL = URL ở trên,
subscribe event `app_mention`, cài app vào workspace, invite bot vào kênh.
"""

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

import slack_bot
from database import SessionLocal

router = APIRouter()

_MAX_TS_SKEW_S = 60 * 5
_seen_event_ids: set[str] = set()  # dedup Slack retry — đủ dùng cho 1 instance


def _verify_signature(body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    try:
        skew = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if skew > _MAX_TS_SKEW_S:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring,
                                hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


async def _handle(request: Request, background_tasks: BackgroundTasks, bot_id: int) -> dict:
    body = await request.body()

    db = SessionLocal()
    try:
        cfg = slack_bot.get_bot(db, bot_id)
    finally:
        db.close()

    if not cfg:
        raise HTTPException(status_code=503,
                            detail=f"Không có bot Slack #{bot_id} đang bật, hoặc bot đó "
                                   "chưa khai Signing Secret")

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not timestamp or not signature or not _verify_signature(body, timestamp, signature,
                                                               cfg.signing_secret):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = json.loads(body)

    # Bước xác thực Request URL khi bật Event Subscriptions lần đầu
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    if payload.get("type") != "event_callback":
        return {"ok": True}

    event_id = payload.get("event_id")
    if event_id:
        # Khoá kèm key app: hai app khác nhau về lý thuyết có thể trùng event_id.
        marker = f"{bot_id}:{event_id}"
        if marker in _seen_event_ids:
            return {"ok": True}          # Slack retry — đã xử lý lần trước
        _seen_event_ids.add(marker)
        if len(_seen_event_ids) > 1000:
            _seen_event_ids.clear()

    event = payload.get("event", {}) or {}
    if event.get("type") != "app_mention":
        return {"ok": True}
    if event.get("bot_id"):
        return {"ok": True}              # tin của chính bot — đừng tự trả lời mình

    # Slack đòi trả lời trong 3 giây, còn xử lý thì phải gọi API + đụng đĩa.
    # Nhận rồi làm nền, không thì Slack retry và ta chạy workflow hai lần.
    background_tasks.add_task(_process, cfg.id, event)
    return {"ok": True}


def _process(bot_id: int, event: dict) -> None:
    db = SessionLocal()
    try:
        cfg = slack_bot.get_bot(db, bot_id)
        if cfg:
            slack_bot.handle_event(db, cfg, event)
    except Exception as e:
        print(f"[slack:#{bot_id}] lỗi xử lý sự kiện: {e}")
    finally:
        db.close()


@router.post("/events/{bot_id}")
async def slack_events(bot_id: int, request: Request, background_tasks: BackgroundTasks):
    """1 app Slack = 1 bot ở tab Bots = 1 Request URL riêng."""
    return await _handle(request, background_tasks, bot_id)
