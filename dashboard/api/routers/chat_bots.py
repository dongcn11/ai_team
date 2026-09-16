"""
Quản lý bot chat — Telegram + Slack, nhiều bot mỗi dự án
========================================================

Một dự án có nhiều QUY TRÌNH (fixbug, làm CR...) và mỗi quy trình muốn một bot
riêng để thông báo không lẫn vào nhau. Bot vì thế là bộ lọc hai tầng:

    không chọn dự án            -> hứng mọi dự án
    chọn dự án                  -> mọi workflow của dự án đó
    chọn dự án + tick workflow  -> chỉ những workflow đã tick

Khớp HẸP nhất thắng khi đẩy câu hỏi đi (xem chat_router.pick_bot).

Token không bao giờ trả ngược ra web — chỉ trả 4 ký tự cuối đủ để nhận ra là cái
nào. Gửi token rỗng lúc sửa = giữ nguyên token cũ, để đổi tên bot mà không phải
đi tìm lại token.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

import chat_router
from database import get_db
from models import ChatBot, Workflow
from schemas import ChatBotCreate, ChatBotOut, ChatBotUpdate

router = APIRouter()

PLATFORMS = ("telegram", "slack")


def _mask(v: str) -> str:
    v = (v or "").strip()
    return f"…{v[-4:]}" if len(v) > 4 else ("…" if v else "")


def _mode(bot: ChatBot) -> Optional[str]:
    """Slack có 2 cách nhận sự kiện; app token thắng vì không cần URL công khai."""
    if bot.platform != "slack":
        return None
    if (bot.app_token or "").strip():
        return "socket"
    if (bot.signing_secret or "").strip():
        return "webhook"
    return None


def _live_state(bot: ChatBot) -> dict:
    """Trạng thái kết nối sống. Telegram luôn có (vòng poll); Slack chỉ có khi
    chạy Socket Mode — bản webhook thì không có kết nối nào để mà theo dõi."""
    try:
        if bot.platform == "telegram":
            import telegram_bot
            return telegram_bot.live_state(bot.id)
        if _mode(bot) == "socket":
            import slack_bot
            return slack_bot.live_state(bot.id)
    except Exception:
        pass
    return {}


def _out(db: Session, bot: ChatBot) -> ChatBotOut:
    wf_ids = list(chat_router.bot_workflow_ids(bot))
    alive  = {w.id for w in db.query(Workflow).filter(Workflow.id.in_(wf_ids)).all()} if wf_ids else set()
    st     = _live_state(bot)
    return ChatBotOut(
        id=bot.id, platform=bot.platform, name=bot.name, chats=bot.chats or "",
        client_folder=bot.client_folder, workflow_ids=wf_ids,
        enabled=bool(bot.enabled), created_at=bot.created_at,
        token_hint=_mask(bot.token), has_token=bool((bot.token or "").strip()),
        has_secret=bool((bot.signing_secret or "").strip()),
        has_app_token=bool((bot.app_token or "").strip()),
        mode=_mode(bot),
        scope_label=chat_router.scope_label(db, bot),
        # Mỗi app Slack cần Request URL riêng: chữ ký phải kiểm bằng đúng secret
        # của app đó, mà muốn biết secret nào thì phải biết request của app nào.
        # Socket Mode không dùng URL nào — chỉ webhook mới cần dán Request URL.
        request_path=(f"/api/slack/events/{bot.id}" if _mode(bot) == "webhook" else None),
        running=bool(st.get("running")), me=st.get("me"), last_error=st.get("last_error"),
        # Không dọn ngầm: workflow bị xoá thì báo lên để người khai tự quyết
        stale_workflow_ids=[i for i in wf_ids if i not in alive],
    )


@router.get("/", response_model=List[ChatBotOut])
def list_bots(platform: Optional[str] = None, client_folder: Optional[str] = None,
              db: Session = Depends(get_db)):
    q = db.query(ChatBot)
    if platform:
        q = q.filter(ChatBot.platform == platform)
    if client_folder:
        q = q.filter(ChatBot.client_folder == client_folder)
    return [_out(db, b) for b in q.order_by(desc(ChatBot.id)).all()]


@router.post("/", response_model=ChatBotOut)
def create_bot(payload: ChatBotCreate, db: Session = Depends(get_db)):
    if payload.platform not in PLATFORMS:
        raise HTTPException(status_code=400, detail=f"platform phải là một trong {PLATFORMS}")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Chưa đặt tên bot")
    if not payload.token.strip():
        raise HTTPException(status_code=400, detail="Chưa có bot token")
    if payload.platform == "slack" and not ((payload.app_token or "").strip()
                                            or (payload.signing_secret or "").strip()):
        # Thiếu cả hai thì không có đường nào nhận sự kiện. Chặn ngay ở đây thay vì
        # để tạo xong rồi bot nằm im không ai hiểu vì sao.
        raise HTTPException(status_code=400, detail=(
            "Bot Slack cần App Token (xapp-… → Socket Mode, khuyến nghị: không cần "
            "URL công khai) HOẶC Signing Secret (→ webhook, phải có URL công khai)"))
    bot = ChatBot(
        platform=payload.platform, name=payload.name.strip(), token=payload.token.strip(),
        signing_secret=(payload.signing_secret or "").strip() or None,
        app_token=(payload.app_token or "").strip() or None,
        chats=payload.chats.strip(), client_folder=(payload.client_folder or "").strip() or None,
        workflow_ids=[int(i) for i in payload.workflow_ids], enabled=payload.enabled,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return _out(db, bot)


@router.put("/{bot_id}", response_model=ChatBotOut)
def update_bot(bot_id: int, payload: ChatBotUpdate, db: Session = Depends(get_db)):
    bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Không có bot này")
    if payload.name is not None and payload.name.strip():
        bot.name = payload.name.strip()
    if payload.chats is not None:
        bot.chats = payload.chats.strip()
    if payload.clear_client_folder:
        bot.client_folder = None
    elif payload.client_folder is not None:
        bot.client_folder = payload.client_folder.strip() or None
    if payload.workflow_ids is not None:
        bot.workflow_ids = [int(i) for i in payload.workflow_ids]
    if payload.enabled is not None:
        bot.enabled = payload.enabled
    # Chuỗi rỗng = giữ token cũ, không phải xoá token
    if payload.token and payload.token.strip():
        bot.token = payload.token.strip()
    if payload.signing_secret and payload.signing_secret.strip():
        bot.signing_secret = payload.signing_secret.strip()
    if payload.app_token and payload.app_token.strip():
        bot.app_token = payload.app_token.strip()
    db.commit()
    db.refresh(bot)
    return _out(db, bot)


@router.delete("/{bot_id}")
def delete_bot(bot_id: int, db: Session = Depends(get_db)):
    bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Không có bot này")
    db.delete(bot)
    db.commit()
    return {"ok": True}


@router.post("/{bot_id}/test")
def test_bot(bot_id: int, db: Session = Depends(get_db)):
    """Thử token, rồi nhắn thử vào chat đầu tiên.

    Tách bạch 3 kiểu hỏng hay bị lẫn: token sai, chat id sai, và "đúng hết nhưng
    chưa bấm Start với bot" (cả Telegram lẫn Slack đều không cho bot nhắn trước
    vào nơi nó chưa được mời)."""
    bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Không có bot này")
    chats = [c.strip() for c in (bot.chats or "").replace(";", ",").split(",") if c.strip()]
    scope = chat_router.scope_label(db, bot)

    if bot.platform == "telegram":
        import telegram_bot as tg
        try:
            me = tg.call(bot.token, "getMe", timeout=15)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if not chats:
            return {"bot": me.get("username"), "sent": False,
                    "detail": "Token đúng. Chưa khai chat nào — nhắn /id cho bot để lấy chat id."}
        try:
            tg.call(bot.token, "sendMessage", {
                "chat_id": chats[0],
                "text": f"✅ Dashboard nối được tới đây. Phạm vi: {scope}. Gõ /help để xem lệnh.",
            }, timeout=15)
        except Exception as e:
            raise HTTPException(status_code=400, detail=(
                f"Token đúng (@{me.get('username')}) nhưng không nhắn được vào {chats[0]}: {e}. "
                "Kiểm tra chat id, và nhớ bấm Start với bot trước."))
        return {"bot": me.get("username"), "sent": True, "chat_id": chats[0]}

    import slack_bot as sl
    if not bot.token:
        return {"bot": None, "sent": False,
                "detail": "Có signing secret nên nhận được sự kiện, nhưng thiếu Bot Token nên "
                          "không trả lời được. Lấy ở Slack App → OAuth & Permissions (xoxb-…)."}
    try:
        me = sl.call(bot.token, "auth.test", timeout=15)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not chats:
        return {"bot": me.get("user"), "sent": False,
                "detail": "Token đúng. Chưa khai kênh nào — tag bot trong kênh rồi gõ /id."}
    try:
        sl.call(bot.token, "chat.postMessage", {
            "channel": chats[0],
            "text": f"✅ Dashboard nối được tới đây. Phạm vi: {scope}. Gõ /help để xem lệnh.",
        }, timeout=15)
    except Exception as e:
        raise HTTPException(status_code=400, detail=(
            f"Token đúng ({me.get('user')}) nhưng không nhắn được vào {chats[0]}: {e}. "
            "Kiểm tra tên kênh, và nhớ invite bot vào kênh trước."))
    return {"bot": me.get("user"), "sent": True, "chat_id": chats[0]}
