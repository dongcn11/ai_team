"""
Slack bot — nhiều app, buộc theo dự án / quy trình
==================================================

HAI CÁCH NHẬN SỰ KIỆN, ưu tiên cách đầu:

1. SOCKET MODE (khai app token "xapp-…") — app mở WebSocket ĐI RA tới Slack.
   Không có chiều đi vào ⇒ không cần URL công khai, không cần tunnel, không phải
   phơi dashboard ra internet, không cần signing secret. Giống hệt long polling
   của Telegram. Xem phần cuối file.

2. WEBHOOK (khai signing secret) — Slack gọi VÀO dashboard, nên bắt buộc có URL
   HTTPS công khai. Mỗi bot một Request URL riêng mang id của nó:

       /api/slack/events/<bot_id>

   Chữ ký phải kiểm TRƯỚC khi được phép tin nội dung, mà mỗi app có secret riêng
   — biết id thì biết ngay dùng secret nào, không phải dò thử từng cái.

Cả hai cùng khai thì Socket Mode thắng: nó xoá bỏ rủi ro phơi dashboard chứ
không quản lý rủi ro đó. Webhook giữ lại cho workspace bị cấm bật Socket Mode.

Bot khai ở bảng `chat_bots` (tab **Bots**), cùng bảng với Telegram. Phạm vi và
luật "khớp hẹp nhất thắng" nằm ở chat_router.
"""

import json
import re
import threading
import urllib.parse
import urllib.request
from typing import Optional

from sqlalchemy.orm import Session

import chat_router
from database import SessionLocal
from models import AgentQuestion, ChatBot

API_ROOT = "https://slack.com/api"


# ── Cấu hình ──────────────────────────────────────────────────────────────

def channels_of(bot: ChatBot) -> tuple[str, ...]:
    return tuple(c.strip() for c in (bot.chats or "").replace(";", ",").split(",") if c.strip())


def get_bot(db: Session, bot_id: int) -> Optional[ChatBot]:
    """App phụ trách 1 endpoint. Đọc mới mỗi request — sửa trên web là có hiệu lực
    ngay, không phải dựng lại container. Thiếu signing secret thì coi như chưa
    khai: không kiểm được chữ ký thì tuyệt đối không nhận webhook."""
    bot = (db.query(ChatBot)
             .filter(ChatBot.id == bot_id, ChatBot.platform == "slack",
                     ChatBot.enabled == True)                       # noqa: E712
             .first())
    if not bot or not (bot.signing_secret or "").strip():
        return None
    return bot


# ── Gọi Slack ─────────────────────────────────────────────────────────────

def call(token: str, method: str, params: Optional[dict] = None, timeout: int = 15) -> dict:
    """1 lệnh Web API. Slack trả HTTP 200 kể cả khi lỗi — lỗi nằm ở `ok=false`,
    nên phải đọc body chứ không nhìn status code."""
    data = urllib.parse.urlencode(params or {}).encode()
    req  = urllib.request.Request(f"{API_ROOT}/{method}", data=data,
                                  headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read() or b"{}")
    if not body.get("ok"):
        raise RuntimeError(f"Slack {method}: {body.get('error') or 'lỗi không rõ'}")
    return body


def post_message(bot: ChatBot, channel: str, text: str,
                 thread_ts: Optional[str] = None) -> Optional[dict]:
    if not (bot.token or "").strip():
        print(f"[slack:{bot.name}] chưa có bot token — không gửi được tin")
        return None
    params = {"channel": channel, "text": text}
    if thread_ts:
        params["thread_ts"] = thread_ts
    try:
        return call(bot.token, "chat.postMessage", params)
    except Exception as e:
        print(f"[slack:{bot.name}] gửi tin thất bại: {e}")
        return None


def resolve_channel_name(bot: ChatBot, channel_id: str) -> Optional[str]:
    """Tên kênh để khớp node trigger khai theo tên (#general) thay vì id."""
    if not (bot.token or "").strip():
        return None
    try:
        return call(bot.token, "conversations.info",
                    {"channel": channel_id}, timeout=5)["channel"]["name"]
    except Exception:
        return None


# ── Chiều RA: agent hỏi → Slack ───────────────────────────────────────────

def notify_question(q: AgentQuestion) -> None:
    threading.Thread(target=_notify_question_sync, args=(q.id,), daemon=True).start()


def _notify_question_sync(question_id: int) -> None:
    db = SessionLocal()
    try:
        q = db.query(AgentQuestion).filter(AgentQuestion.id == question_id).first()
        if not q or q.status != "open":
            return
        bot = chat_router.pick_bot(db, "slack", q.client_folder, q.workflow_id)
        if not bot:
            return
        chans = channels_of(bot)
        if not chans:
            return
        text = chat_router.question_text(q, chat_router.MrkdwnFmt)
        for ch in chans:
            post_message(bot, ch, text)
    except Exception as e:
        print(f"[slack] lỗi khi đẩy câu hỏi #{question_id}: {e}")
    finally:
        db.close()


# ── Chiều VÀO: app_mention → workflow / trả lời ───────────────────────────

def _looks_like_channel_id(v: str) -> bool:
    """Id kênh Slack: C/G/D + chữ HOA và số (C0C0F25186A). Tên kênh thì chữ thường
    có gạch ngang (udom-core-system). Dùng để biết người ta khai bằng id hay tên."""
    v = (v or "").strip()
    return bool(re.fullmatch(r"[CGD][0-9A-Z]{6,}", v))


def _strip_mentions(text: str) -> str:
    """Bỏ '<@U123>' ở đầu — người ta phải tag bot mới gửi được app_mention, nhưng
    phần tag đó không phải nội dung lệnh."""
    return re.sub(r"<@[^>]+>", " ", text or "").strip()


def handle_event(db: Session, bot: ChatBot, event: dict) -> None:
    """Xử lý 1 app_mention. Kênh không nằm trong danh sách đã khai thì bỏ qua —
    hàng rào ở đây tương đương danh sách chat của Telegram."""
    channel_id = event.get("channel", "")
    thread_ts  = event.get("thread_ts") or event.get("ts")
    user       = event.get("user", "?")
    text       = _strip_mentions(event.get("text", ""))
    if not channel_id or not text:
        return

    channel_name = resolve_channel_name(bot, channel_id)

    def send(t: str) -> None:
        # Trả lời trong thread để kênh không bị ngập — Slack khác Telegram ở chỗ
        # kênh thường đông người, không phải chat riêng.
        post_message(bot, channel_id, t, thread_ts=thread_ts)

    where = f"tab *Bots* → bot *{bot.name}*"

    # /id trả lời cho mọi kênh: đó là cách lấy id/tên kênh để dán vào cấu hình.
    if text.startswith("/id"):
        send(f"Kênh này: `{channel_id}`"
             + (f" (#{channel_name})" if channel_name else "")
             + f"\nDán vào {where} trên dashboard rồi nhắn lại.")
        return

    allowed = {c.lstrip("#").lower() for c in channels_of(bot)}
    if allowed and channel_id.lower() not in allowed and (channel_name or "").lower() not in allowed:
        msg = (f"⛔ Kênh này chưa được cấp quyền.\nKênh: `{channel_id}`"
               + (f" (#{channel_name})" if channel_name else "")
               + f" — dán vào {where}.")
        # Không đọc được tên kênh mà danh sách lại khai bằng TÊN ⇒ không đời nào
        # khớp. Nói thẳng ra, không thì người khai cứ tưởng mình gõ sai tên kênh.
        if channel_name is None and any(not _looks_like_channel_id(c) for c in allowed):
            msg += ("\n\n_Bot không đọc được tên kênh (bot token thiếu scope "
                    "`channels:read`, thêm `groups:read` nếu là kênh riêng tư), nên chỉ "
                    "so khớp được theo id. Dán id ở trên vào, hoặc thêm scope rồi cài lại app._")
        send(msg)
        return

    ctx = chat_router.ChatCtx(
        platform="slack", bot=bot, chat_id=channel_id,
        chat_name=channel_name or "", sender=f"@{user}", send=send,
        fmt=chat_router.MrkdwnFmt, config_hint=where, thread=thread_ts,
    )
    # Slack không gửi kèm nội dung tin được reply; muốn trả lời câu hỏi thì gõ
    # '#12 nội dung' (hoặc nhắn thường khi chỉ có đúng 1 câu đang chờ).
    chat_router.handle_text(db, ctx, text)


# ══════════════════════════════════════════════════════════════════════════
# SOCKET MODE — Slack chạy giống Telegram
# ══════════════════════════════════════════════════════════════════════════
# App mở WebSocket ĐI RA tới Slack, sự kiện chảy ngược về qua đó. Không có chiều
# đi vào ⇒ không cần URL công khai, không cần funnel, không phải phơi dashboard ra
# internet, và không cần signing secret (chẳng có request HTTP nào để kiểm chữ ký).
#
# Đây là lý do nên ưu tiên Socket Mode hơn webhook: nó XOÁ BỎ rủi ro chứ không
# quản lý rủi ro. Webhook vẫn giữ cho workspace nào bị cấm bật Socket Mode.
#
# Vòng đời: apps.connections.open lấy URL wss:// (URL dùng một lần, hết hạn nhanh)
# → connect → nhận "hello" → mỗi sự kiện phải ACK bằng envelope_id trong 3 giây,
# không ACK thì Slack gửi lại → gặp "disconnect" thì xin URL mới và nối lại.

import threading as _threading
import time as _time

_RECONNECT_S = 5          # Slack chủ động ngắt định kỳ; nối lại ngay là bình thường
_RESCAN_S    = 15         # supervisor rà lại bảng chat_bots

_sock_lock = _threading.Lock()
_sock_state: dict[int, dict] = {}      # bot_id -> {running, me, last_error, last_event}


def live_state(bot_id: int) -> dict:
    with _sock_lock:
        return dict(_sock_state.get(bot_id) or {})


def _mark(bot_id: int, **kw) -> None:
    with _sock_lock:
        _sock_state.setdefault(bot_id, {}).update(kw)


def socket_bots(db: Session) -> dict[int, ChatBot]:
    """Bot Slack đang bật và có app token — tức là chạy Socket Mode."""
    rows = (db.query(ChatBot)
              .filter(ChatBot.platform == "slack", ChatBot.enabled == True)   # noqa: E712
              .all())
    return {b.id: b for b in rows if (b.app_token or "").strip()}


def open_connection(app_token: str) -> str:
    """Xin 1 URL wss:// từ Slack. URL chỉ dùng được một lần và hết hạn nhanh, nên
    mỗi lần nối lại phải xin mới chứ không cache."""
    res = call(app_token, "apps.connections.open", timeout=20)
    url = res.get("url")
    if not url:
        raise RuntimeError("apps.connections.open không trả url")
    return url


def _socket_loop(bot_id: int, app_token: str, name: str, stop: _threading.Event) -> None:
    from websockets.sync.client import connect     # đi kèm uvicorn[standard]

    while not stop.is_set():
        db = SessionLocal()
        try:
            bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
            if not bot or not bot.enabled or (bot.app_token or "").strip() != app_token:
                break                              # supervisor sẽ dọn / mở lại
            url = open_connection(app_token)
            with connect(url, open_timeout=20, close_timeout=5) as ws:
                _mark(bot_id, running=True, last_error=None)
                print(f"[slack:{name}] đã nối Socket Mode")
                while not stop.is_set():
                    try:
                        raw = ws.recv(timeout=30)
                    except TimeoutError:
                        continue                   # không có tin — vòng lại, giữ kết nối
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue

                    mtype = msg.get("type")
                    if mtype == "disconnect":
                        # Slack bảo ngắt (bảo trì / xoay ticket) — ra ngoài xin URL mới
                        print(f"[slack:{name}] Slack yêu cầu nối lại ({msg.get('reason')})")
                        break

                    env = msg.get("envelope_id")
                    if env:
                        # ACK TRƯỚC khi xử lý: Slack chờ tối đa 3 giây, mà xử lý thì
                        # phải gọi API + đụng đĩa. Chậm ACK là Slack gửi lại và ta
                        # chạy workflow hai lần.
                        try:
                            ws.send(json.dumps({"envelope_id": env}))
                        except Exception as e:
                            print(f"[slack:{name}] không ACK được: {e}")
                            break

                    if mtype != "events_api":
                        continue
                    event = ((msg.get("payload") or {}).get("event") or {})
                    if event.get("type") != "app_mention" or event.get("bot_id"):
                        continue
                    _mark(bot_id, last_event=_time.time())
                    # Thread riêng + session riêng: xử lý có thể mất vài giây, đừng
                    # giữ vòng nhận tin lại.
                    _threading.Thread(target=_process_event, args=(bot_id, event),
                                      daemon=True).start()
        except Exception as e:
            _mark(bot_id, running=False, last_error=str(e))
            print(f"[slack:{name}] Socket Mode lỗi: {e}")
            stop.wait(_RECONNECT_S)
        finally:
            db.close()
    _mark(bot_id, running=False)


def _process_event(bot_id: int, event: dict) -> None:
    db = SessionLocal()
    try:
        bot = db.query(ChatBot).filter(ChatBot.id == bot_id).first()
        if bot:
            handle_event(db, bot, event)
    except Exception as e:
        print(f"[slack:#{bot_id}] lỗi xử lý sự kiện: {e}")
    finally:
        db.close()


class _Worker:
    def __init__(self, token: str, stop: _threading.Event, thread: _threading.Thread):
        self.token, self.stop, self.thread = token, stop, thread


def _supervise(stop: _threading.Event) -> None:
    workers: dict[int, _Worker] = {}
    while not stop.is_set():
        try:
            db = SessionLocal()
            try:
                snapshot = {i: ((b.app_token or "").strip(), b.name)
                            for i, b in socket_bots(db).items()}
            finally:
                db.close()

            for bot_id, w in list(workers.items()):
                if not w.thread.is_alive():
                    workers.pop(bot_id)
                    with _sock_lock:
                        _sock_state.pop(bot_id, None)
                    continue
                if bot_id not in snapshot or snapshot[bot_id][0] != w.token:
                    w.stop.set()          # dọn ở vòng sau, khi thread chết hẳn

            for bot_id, (token, name) in snapshot.items():
                if bot_id in workers:
                    continue
                ev = _threading.Event()
                th = _threading.Thread(target=_socket_loop, args=(bot_id, token, name, ev),
                                       daemon=True, name=f"slack-{bot_id}")
                th.start()
                workers[bot_id] = _Worker(token, ev, th)
                print(f"[slack] mở Socket Mode cho bot '{name}' (#{bot_id})")
        except Exception as e:
            print(f"[slack] supervisor lỗi: {e}")
        stop.wait(_RESCAN_S)

    for w in workers.values():
        w.stop.set()


_stop = _threading.Event()
_thread: Optional[_threading.Thread] = None


def start() -> None:
    """Gọi 1 lần lúc API khởi động. An toàn khi gọi lại (uvicorn --reload)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = _threading.Thread(target=_supervise, args=(_stop,), daemon=True,
                                name="slack-supervisor")
    _thread.start()


def stop() -> None:
    _stop.set()
