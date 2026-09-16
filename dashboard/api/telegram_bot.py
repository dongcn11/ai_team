"""
Telegram bot — cầu hai chiều giữa dashboard và điện thoại bạn
==============================================================

Vì sao LONG POLLING chứ không webhook: dashboard chạy ở localhost trong Docker,
không có địa chỉ public. Webhook là chiều *vào* — Slack/Messenger/Zalo đều bắt
phải có một đường HTTPS đi vào máy bạn (Cloudflare Tunnel, VPS...). Long polling
thì bot chủ động đi *ra* hỏi tin mới, đúng khuôn mẫu `worker.py` đang dùng với
dashboard, nên chạy được ngay trên máy cá nhân mà không mở cổng nào.

NHIỀU BOT
---------
Bot khai ở bảng `chat_bots` (xem models.ChatBot), quản lý ở tab **Bots**. Một dự
án có nhiều quy trình (fixbug, làm CR...) nên có nhiều bot, mỗi bot buộc vào một
hoặc vài workflow. Phạm vi và luật "khớp hẹp nhất thắng" nằm ở chat_router.

Mỗi token là một vòng poll riêng: `getUpdates` gắn chặt với token, không gộp
được. Một supervisor rà lại bảng mỗi 15s — thêm bot thì mở thread, đổi token hoặc
tắt thì đóng. Nhờ vậy khai bot trên web là chạy, không phải dựng lại container.

Hai chiều:

  VÀO   tin nhắn khớp node `trigger.chat_message`  → tạo run workflow
        trả lời câu hỏi đang mở                     → ghi vào file task, mở lại bước
  RA    agent ghi `## Cần xác nhận` (AgentQuestion) → đẩy ra bot phụ trách

Chiều RA mới là chiều đáng tiền: mỗi vòng "agent bí → chờ người mở dashboard →
trả lời → chạy lại" tốn trọn một lần gọi CLI (≈45K token tiền tố ghi lại vào
cache với giá gấp đôi). Rút thời gian chờ đó xuống vài phút là tiết kiệm thật.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from sqlalchemy.orm import Session

import chat_router
from database import SessionLocal
from models import AgentQuestion, ChatBot, Setting

API_ROOT = "https://api.telegram.org"

# Long polling: Telegram giữ kết nối tới khi có tin hoặc hết ngần này giây. Để dài
# thì ít request rỗng, nhưng đừng vượt timeout của urlopen bên dưới.
_LONG_POLL_S = 25
_HTTP_TIMEOUT_S = _LONG_POLL_S + 10
# Mất mạng / Telegram 5xx thì nghỉ chừng này rồi thử lại, khỏi quay tít đốt CPU.
_RETRY_S = 15
# Supervisor rà lại bảng chat_bots bao lâu một lần.
_RESCAN_S = 15

_OFFSET_PREFIX = "telegram_offset"     # + ":<bot_id>"

# Telegram giới hạn 4096 ký tự/tin. Chừa chỗ cho phần khung bot tự thêm.
_MAX_TEXT = 3500

_state_lock = threading.Lock()
_state: dict[int, dict] = {}           # bot_id -> {running, me, last_error, last_poll}


def live_state(bot_id: int) -> dict:
    with _state_lock:
        return dict(_state.get(bot_id) or {})


def _mark(bot_id: int, **kw) -> None:
    with _state_lock:
        _state.setdefault(bot_id, {}).update(kw)


# ── Cấu hình ──────────────────────────────────────────────────────────────

def _get(db: Session, key: str, default: str = "") -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return (row.value if row else default) or default


def _set(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def _offset_key(bot_id: int) -> str:
    return f"{_OFFSET_PREFIX}:{bot_id}"


def chats_of(bot: ChatBot) -> set[str]:
    return {c.strip() for c in (bot.chats or "").replace(";", ",").split(",") if c.strip()}


def load_bots(db: Session) -> dict[int, ChatBot]:
    """Bot Telegram đang bật và có token."""
    rows = (db.query(ChatBot)
              .filter(ChatBot.platform == "telegram", ChatBot.enabled == True)   # noqa: E712
              .all())
    return {b.id: b for b in rows if (b.token or "").strip()}


# ── Gọi Telegram ──────────────────────────────────────────────────────────

def call(token: str, method: str, params: Optional[dict] = None, timeout: int = 20) -> dict:
    """1 lệnh Bot API. Ném RuntimeError kèm mô tả của Telegram khi `ok=false`,
    vì thông báo của họ ("chat not found", "Unauthorized") đọc là hiểu ngay."""
    url  = f"{API_ROOT}/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            raise RuntimeError(f"Telegram HTTP {e.code}") from e
        raise RuntimeError(f"Telegram {method}: {body.get('description') or e.code}") from e
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method}: {body.get('description') or 'lỗi không rõ'}")
    return body.get("result")


def send_message(token: str, chat_id, text: str, reply_to: Optional[int] = None) -> Optional[dict]:
    params = {
        "chat_id": chat_id,
        "text": text[:_MAX_TEXT],
        # HTML dễ kiểm soát hơn Markdown: Markdown của Telegram bắt escape cả dấu
        # gạch dưới / ngoặc, mà nội dung ở đây toàn đường dẫn file và tên node.
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if reply_to:
        params["reply_to_message_id"] = reply_to
    try:
        return call(token, "sendMessage", params)
    except Exception as e:
        print(f"[telegram] gửi tin thất bại: {e}")
        return None


def _esc(s) -> str:
    return chat_router.HtmlFmt.esc(s)


# ── Chiều RA: agent hỏi → Telegram ────────────────────────────────────────

def notify_question(q: AgentQuestion) -> None:
    """Đẩy 1 câu hỏi mới ra bot phụ trách. Chạy trong thread riêng để vòng poll
    workflow (5s/lần) không phải ngồi chờ mạng."""
    threading.Thread(target=_notify_question_sync, args=(q.id,), daemon=True).start()


def _notify_question_sync(question_id: int) -> None:
    db = SessionLocal()
    try:
        q = db.query(AgentQuestion).filter(AgentQuestion.id == question_id).first()
        if not q or q.status != "open":
            return
        bot = chat_router.pick_bot(db, "telegram", q.client_folder, q.workflow_id)
        if not bot or not (bot.token or "").strip():
            return
        chats = chats_of(bot)
        if not chats:
            return
        text = chat_router.question_text(q, chat_router.HtmlFmt)
        for chat in chats:
            send_message(bot.token, chat, text)
    except Exception as e:
        print(f"[telegram] lỗi khi đẩy câu hỏi #{question_id}: {e}")
    finally:
        db.close()


# ── Chiều VÀO ─────────────────────────────────────────────────────────────

def _handle_message(db: Session, bot: ChatBot, msg: dict) -> None:
    """Phần riêng của Telegram: cấp quyền theo chat id và lệnh /id. Phần định
    tuyến (trả lời câu hỏi / chạy workflow) giao cho chat_router — dùng chung
    với Slack, khỏi viết hai lần rồi trôi lệch nhau."""
    chat    = (msg.get("chat") or {})
    chat_id = str(chat.get("id") or "")
    text    = (msg.get("text") or "").strip()
    msg_id  = msg.get("message_id")
    if not chat_id or not text:
        return

    sender = (msg.get("from") or {})
    who    = sender.get("username") or sender.get("first_name") or "?"

    def send(t: str) -> None:
        send_message(bot.token, chat_id, t, reply_to=msg_id)

    where = f"tab <b>Bots</b> → bot <b>{_esc(bot.name)}</b>"

    # /id và /start trả lời cho MỌI chat — đó là cách lấy chat id để dán vào cấu
    # hình. Ngoài hai lệnh đó, chat lạ không làm được gì.
    if text.startswith("/id") or text.startswith("/start"):
        send(f"Chat id của chat này: <code>{chat_id}</code>\n\n"
             f"Dán vào {where} trên dashboard rồi nhắn lại.")
        return

    if chat_id not in chats_of(bot):
        send(f"⛔ Chat này chưa được cấp quyền.\nChat id: <code>{chat_id}</code> — "
             f"dán vào {where}.")
        return

    ctx = chat_router.ChatCtx(
        platform="telegram", bot=bot, chat_id=chat_id,
        chat_name=chat.get("username") or chat.get("title") or "",
        sender=who, send=send, fmt=chat_router.HtmlFmt, config_hint=where,
        thread=str(msg_id) if msg_id else None,
    )
    quoted = (msg.get("reply_to_message") or {}).get("text") or ""
    chat_router.handle_text(db, ctx, text, quoted=quoted)


# ── Một vòng poll cho một bot ─────────────────────────────────────────────

def _poll_once(db: Session, bot: ChatBot) -> None:
    key = _offset_key(bot.id)
    updates = call(bot.token, "getUpdates", {
        "offset": _get(db, key, "0"),
        "timeout": _LONG_POLL_S,
        # Chỉ lấy tin nhắn — bỏ qua reaction, poll, edit... cho khỏi nhiễu.
        "allowed_updates": json.dumps(["message"]),
    }, timeout=_HTTP_TIMEOUT_S) or []

    for up in updates:
        # Ghi offset TRƯỚC khi xử lý: một tin gây lỗi thì bỏ qua tin đó, đừng để
        # nó được lấy lại mãi và chặn cả hàng đợi phía sau.
        _set(db, key, str(int(up["update_id"]) + 1))
        msg = up.get("message")
        if not msg:
            continue
        try:
            _handle_message(db, bot, msg)
        except Exception as e:
            print(f"[telegram:{bot.name}] lỗi xử lý update {up.get('update_id')}: {e}")


def _bot_loop(bot_id: int, token: str, name: str, stop: threading.Event) -> None:
    me = None
    while not stop.is_set():
        db = SessionLocal()
        try:
            bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
            if not bot or not bot.enabled or (bot.token or "").strip() != token:
                break                     # supervisor sẽ dọn và mở lại nếu cần
            if me is None:
                me = (call(token, "getMe", timeout=15) or {}).get("username")
                _mark(bot_id, me=me)
            _poll_once(db, bot)
            _mark(bot_id, running=True, last_error=None, last_poll=time.time())
        except Exception as e:
            me = None
            _mark(bot_id, running=False, last_error=str(e), me=None)
            print(f"[telegram:{name}] vòng poll lỗi: {e}")
            stop.wait(_RETRY_S)
        finally:
            db.close()
    _mark(bot_id, running=False, me=None)


# ── Supervisor ────────────────────────────────────────────────────────────

class _Worker:
    def __init__(self, token: str, stop: threading.Event, thread: threading.Thread):
        self.token, self.stop, self.thread = token, stop, thread


def _supervise(stop: threading.Event) -> None:
    workers: dict[int, _Worker] = {}
    while not stop.is_set():
        try:
            db = SessionLocal()
            try:
                wanted = load_bots(db)
                snapshot = {i: (b.token.strip(), b.name) for i, b in wanted.items()}
            finally:
                db.close()

            for bot_id, w in list(workers.items()):
                if not w.thread.is_alive():
                    workers.pop(bot_id)
                    with _state_lock:
                        _state.pop(bot_id, None)
                    continue
                if bot_id not in snapshot or snapshot[bot_id][0] != w.token:
                    # Chỉ RA HIỆU dừng; dọn khỏi dict ở vòng sau, khi thread chết
                    # hẳn. Mở thread mới ngay lúc này thì hai vòng getUpdates cùng
                    # một token chồng nhau và Telegram trả 409 Conflict.
                    w.stop.set()

            for bot_id, (token, name) in snapshot.items():
                if bot_id in workers:
                    continue
                ev = threading.Event()
                th = threading.Thread(target=_bot_loop, args=(bot_id, token, name, ev),
                                      daemon=True, name=f"tg-{bot_id}")
                th.start()
                workers[bot_id] = _Worker(token, ev, th)
                print(f"[telegram] mở bot '{name}' (#{bot_id})")
        except Exception as e:
            print(f"[telegram] supervisor lỗi: {e}")
        stop.wait(_RESCAN_S)

    for w in workers.values():
        w.stop.set()


_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def start() -> None:
    """Gọi 1 lần lúc API khởi động. An toàn khi gọi lại (uvicorn --reload)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_supervise, args=(_stop,), daemon=True,
                               name="telegram-supervisor")
    _thread.start()


def stop() -> None:
    _stop.set()
