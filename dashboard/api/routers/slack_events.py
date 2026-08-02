"""
Slack Events API — webhook nhận sự kiện app_mention
=====================================================
Slack POST tới đây khi bot bị tag (@bot) trong 1 channel đã invite bot vào.
Yêu cầu Slack App đã bật Event Subscriptions, Request URL = <public>/api/slack/events,
subscribe event `app_mention`, và signing secret được lưu ở Settings (key
`slack_signing_secret`) qua tab Settings trên dashboard.

Xác thực chữ ký theo chuẩn Slack: https://api.slack.com/authentication/verifying-requests-from-slack
Downstream action node vẫn MÔ PHỎNG (xem routers/workflows.py) — trigger này chỉ
xác nhận THẬT sự kiện "bị tag", chưa gọi codegen/git thật (Phase 2).
"""

import hashlib
import hmac
import json
import time
import urllib.request
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Setting
from routers.workflows import find_matching_workflows, run_workflow_from_trigger

router = APIRouter()

_MAX_TS_SKEW_S = 60 * 5
_seen_event_ids: set[str] = set()  # dedup Slack retry — đủ dùng cho 1 instance


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else None


def _verify_signature(body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    if abs(time.time() - int(timestamp)) > _MAX_TS_SKEW_S:
        return False
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


def _resolve_channel_name(channel_id: str, bot_token: str) -> Optional[str]:
    req = urllib.request.Request(
        f"https://slack.com/api/conversations.info?channel={channel_id}",
        headers={"Authorization": f"Bearer {bot_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        if data.get("ok"):
            return data["channel"]["name"]
    except Exception:
        pass
    return None


@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    db = SessionLocal()
    try:
        signing_secret = _get_setting(db, "slack_signing_secret")
    finally:
        db.close()

    if not signing_secret:
        raise HTTPException(status_code=503, detail="slack_signing_secret chưa được cấu hình trong Settings")

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature  = request.headers.get("X-Slack-Signature", "")
    if not timestamp or not signature or not _verify_signature(body, timestamp, signature, signing_secret):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = json.loads(body)

    # Bước xác thực Request URL khi bật Event Subscriptions lần đầu
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    if payload.get("type") != "event_callback":
        return {"ok": True}

    event_id = payload.get("event_id")
    if event_id:
        if event_id in _seen_event_ids:
            return {"ok": True}  # Slack retry — đã xử lý lần trước
        _seen_event_ids.add(event_id)
        if len(_seen_event_ids) > 1000:
            _seen_event_ids.clear()

    event = payload.get("event", {}) or {}
    if event.get("type") != "app_mention":
        return {"ok": True}

    channel_id = event.get("channel", "")
    text       = event.get("text", "")
    user       = event.get("user", "?")

    db = SessionLocal()
    try:
        bot_token     = _get_setting(db, "slack_bot_token")
        channel_name  = _resolve_channel_name(channel_id, bot_token) if bot_token else None
        matched       = find_matching_workflows(db, channel_id, channel_name, text)
    finally:
        db.close()

    trigger_message = f"[slack] app_mention từ @{user} trong #{channel_name or channel_id}: {text[:200]}"
    for wf in matched:
        background_tasks.add_task(run_workflow_from_trigger, wf.id, trigger_message)

    return {"ok": True, "matched_workflows": [wf.id for wf in matched]}
