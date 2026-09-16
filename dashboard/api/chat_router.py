"""
Định tuyến tin nhắn chat — dùng chung cho mọi nền tảng
=======================================================

Telegram và Slack chỉ khác nhau ở đúng hai chỗ: cách NHẬN tin (long polling vs
webhook) và cách GỬI tin (sendMessage vs chat.postMessage). Phần ở giữa — tin này
là trả lời câu hỏi hay lệnh chạy workflow, câu hỏi có thuộc phạm vi bot không,
khớp node trigger nào — giống hệt nhau.

Gom vào đây để adapter từng nền tảng chỉ còn phần thật sự riêng của nó, và để
Messenger/Zalo về sau không phải chép lại lần thứ ba.

PHẠM VI (`scope`) là thứ quan trọng nhất ở file này: bot của dự án A không được
đọc hay đụng vào việc của dự án B. Nhầm dự án nghĩa là ghi đè file task của nơi
khác — hỏng thật, không phải phiền nhẹ.
"""

import re
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from models import AgentQuestion, ChatBot, Workflow


# ── Phạm vi của bot ───────────────────────────────────────────────────────
# Bot là BỘ LỌC hai tầng, không phải phân cấp cứng:
#     client_folder = None          -> mọi dự án
#     client_folder = 'udom'        -> mọi workflow của dự án đó
#     + workflow_ids = [24]         -> chỉ workflow đó
# Nhờ vậy "1 bot/dự án" và "1 bot/quy trình" dùng chung một bảng, và đổi ý sau
# này không phải đập bảng đi làm lại.

def bot_workflow_ids(bot: ChatBot) -> tuple[int, ...]:
    raw = bot.workflow_ids or []
    return tuple(int(i) for i in raw if str(i).isdigit() or isinstance(i, int))


def bot_matches(bot: ChatBot, client_folder: Optional[str],
                workflow_id: Optional[int]) -> bool:
    if bot.client_folder and bot.client_folder != client_folder:
        return False
    wf_ids = bot_workflow_ids(bot)
    if wf_ids and workflow_id not in wf_ids:
        return False
    return True


def bot_specificity(bot: ChatBot) -> int:
    """Khớp HẸP nhất thắng: bot buộc đúng workflow hơn bot cả dự án, bot cả dự án
    hơn bot chung. Thiếu luật này thì khai bot riêng cho fixbug xong câu hỏi vẫn
    rơi vào bot chung."""
    return (2 if bot_workflow_ids(bot) else 0) + (1 if bot.client_folder else 0)


def pick_bot(db: Session, platform: str, client_folder: Optional[str],
             workflow_id: Optional[int]) -> Optional[ChatBot]:
    """Bot phụ trách 1 câu hỏi. None = chưa khai bot nào hợp."""
    cands = [b for b in db.query(ChatBot)
                          .filter(ChatBot.platform == platform,
                                  ChatBot.enabled == True).all()      # noqa: E712
             if bot_matches(b, client_folder, workflow_id)]
    if not cands:
        return None
    return max(cands, key=lambda b: (bot_specificity(b), -b.id))


def scope_label(db: Session, bot: ChatBot) -> str:
    """Mô tả phạm vi cho người đọc — dùng cả ở API lẫn trong tin nhắn bot gửi."""
    if not bot.client_folder:
        return "mọi dự án"
    wf_ids = bot_workflow_ids(bot)
    if not wf_ids:
        return f"dự án {bot.client_folder}"
    names = [w.name for w in db.query(Workflow).filter(Workflow.id.in_(wf_ids)).all()]
    return f"{bot.client_folder} · " + (", ".join(names) if names else "workflow đã bị xoá")


# ── Định dạng chữ theo nền tảng ───────────────────────────────────────────

class Fmt:
    """Telegram nhận HTML, Slack nhận mrkdwn. Cùng nội dung, khác cú pháp."""

    @staticmethod
    def esc(s) -> str:
        raise NotImplementedError

    @classmethod
    def b(cls, s) -> str:
        raise NotImplementedError

    @classmethod
    def code(cls, s) -> str:
        raise NotImplementedError

    @classmethod
    def i(cls, s) -> str:
        raise NotImplementedError


class HtmlFmt(Fmt):
    @staticmethod
    def esc(s) -> str:
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @classmethod
    def b(cls, s) -> str:
        return f"<b>{cls.esc(s)}</b>"

    @classmethod
    def code(cls, s) -> str:
        return f"<code>{cls.esc(s)}</code>"

    @classmethod
    def i(cls, s) -> str:
        return f"<i>{cls.esc(s)}</i>"


class MrkdwnFmt(Fmt):
    @staticmethod
    def esc(s) -> str:
        # Slack chỉ bắt buộc escape 3 ký tự này; escape thêm sẽ lòi ra dấu \ trong tin.
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @classmethod
    def b(cls, s) -> str:
        return f"*{cls.esc(s)}*"

    @classmethod
    def code(cls, s) -> str:
        return f"`{cls.esc(s)}`"

    @classmethod
    def i(cls, s) -> str:
        return f"_{cls.esc(s)}_"


# ── Ngữ cảnh 1 tin nhắn đến ───────────────────────────────────────────────

@dataclass
class ChatCtx:
    platform: str                      # "telegram" | "slack"
    bot: ChatBot                       # phạm vi lấy từ đây (dự án + workflow)
    chat_id: str
    chat_name: str
    sender: str
    send: Callable[[str], None]        # gửi text ngược về chính chat đó
    fmt: type[Fmt]
    # Slack thread_ts · Telegram message_id — để kết quả rơi đúng luồng đã ra lệnh
    thread: Optional[str] = None
    # Nơi sửa cấu hình, in trong lời nhắc cho người dùng biết đi đâu mà sửa
    config_hint: str = "cấu hình trên dashboard"


def open_questions(db: Session, bot: ChatBot):
    """Câu hỏi bot này ĐƯỢC PHÉP thấy. Lọc ngay ở query chứ không lọc sau, để
    không có đường nào rò câu hỏi của dự án khác ra ngoài."""
    q = db.query(AgentQuestion).filter(AgentQuestion.status == "open")
    if bot.client_folder:
        q = q.filter(AgentQuestion.client_folder == bot.client_folder)
    wf_ids = bot_workflow_ids(bot)
    if wf_ids:
        q = q.filter(AgentQuestion.workflow_id.in_(wf_ids))
    return q.order_by(AgentQuestion.id).all()


def _question_id_in(text: str) -> Optional[int]:
    """Bắt '#12' ở đầu tin, hoặc trong tin của bot mà người dùng reply vào."""
    m = re.search(r"#(\d+)", text or "")
    return int(m.group(1)) if m else None


def help_text(db: Session, ctx: ChatCtx) -> str:
    f = ctx.fmt
    scope = f"Phạm vi: {f.b(scope_label(db, ctx.bot))}."
    return (
        f"🤖 {f.b('AI Team bot')}\n"
        f"{scope}\n\n"
        f"{f.b('/hoi')} — xem các câu hỏi agent đang chờ\n"
        f"{f.b('/id')} — xem id của chat/kênh này\n"
        f"{f.b('/help')} — bảng này\n\n"
        f"Trả lời câu hỏi: reply vào tin của bot, hoặc nhắn {f.code('#12 nội dung')}.\n"
        "Nhắn tin thường: khớp với node Trigger chat của workflow để chạy."
    )


def handle_text(db: Session, ctx: ChatCtx, text: str, quoted: str = "") -> None:
    """Xử lý 1 tin nhắn đã qua xác thực và đã được cấp quyền.

    `quoted` = nội dung tin mà người dùng reply vào (nếu nền tảng có) — dùng để
    moi số câu hỏi ra khi người ta reply thẳng vào tin của bot thay vì gõ '#12'.
    """
    f    = ctx.fmt
    text = (text or "").strip()
    if not text:
        return

    if text.startswith("/help"):
        ctx.send(help_text(db, ctx))
        return

    if text.startswith("/hoi") or text.startswith("/questions"):
        opens = open_questions(db, ctx.bot)
        if not opens:
            ctx.send("✅ Không có câu hỏi nào đang chờ.")
            return
        lines = [f"❓ {f.b(str(len(opens)) + ' câu đang chờ')}\n"]
        for q in opens[:10]:
            head = (q.question or "").splitlines()[0][:120]
            lines.append(f"{f.b('#' + str(q.id))} · {f.esc(q.node_label or q.node_id)}\n{f.esc(head)}\n")
        ctx.send("\n".join(lines))
        return

    # ── Trả lời câu hỏi ────────────────────────────────────────────────
    qid = _question_id_in(text if text.startswith("#") else quoted)
    answer = text
    if text.startswith("#") and qid is not None:
        parts = text.split(None, 1)
        answer = parts[1] if len(parts) > 1 else ""

    if qid is None and not text.startswith("/"):
        # Chỉ có đúng 1 câu đang chờ (trong phạm vi bot này) thì tin thường coi như
        # trả lời câu đó — đường đi ít ma sát nhất trên điện thoại. Bot xác nhận rõ
        # đã trả lời câu nào để nếu đoán sai thì thấy ngay.
        opens = open_questions(db, ctx.bot)
        if len(opens) == 1:
            qid, answer = opens[0].id, text

    if qid is not None:
        q = db.query(AgentQuestion).filter(AgentQuestion.id == qid).first()
        if not q:
            ctx.send(f"Không có câu hỏi {f.b('#' + str(qid))}.")
            return
        if not bot_matches(ctx.bot, q.client_folder, q.workflow_id):
            ctx.send(f"⛔ Câu {f.b('#' + str(qid))} thuộc dự án {f.b(q.client_folder)}, "
                     f"bot này chỉ phụ trách {f.b(scope_label(db, ctx.bot))}.")
            return
        from routers.workflows import apply_question_answer
        try:
            apply_question_answer(db, q, answer)
        except Exception as e:
            detail = getattr(e, "detail", None) or str(e)
            ctx.send(f"⚠️ Không trả lời được câu #{qid}: {f.esc(detail)}")
            return
        ctx.send(f"✅ Đã trả lời câu {f.b('#' + str(qid))} "
                 f"({f.esc(q.node_label or q.node_id)}) — bước đó đã mở lại.")
        return

    # ── Kích hoạt workflow ─────────────────────────────────────────────
    from routers.workflows import find_workflows_for_chat, run_workflow_from_trigger
    matched = find_workflows_for_chat(db, ctx.platform, ctx.chat_id, ctx.chat_name, text)
    matched = [wf for wf in matched
               if bot_matches(ctx.bot, wf.client_folder, wf.id)]
    if not matched:
        ctx.send("Không có workflow nào khớp tin này.\n"
                 f"Thêm node {f.b('Trigger chat')} (nền tảng {ctx.platform}) vào workflow, "
                 "hoặc gõ /help.")
        return

    trigger_message = (f"[{ctx.platform}] {ctx.sender} trong "
                       f"{ctx.chat_name or ctx.chat_id}: {text[:200]}")
    # Địa chỉ để lần chạy trả kết quả ngược về ĐÚNG chat này — thiếu nó thì
    # trigger là đường một chiều.
    origin = {"bot_id": ctx.bot.id, "chat_id": ctx.chat_id, "thread": ctx.thread}
    names = []
    for wf in matched:
        names.append(wf.name)
        # Thread riêng: tạo run + ghi file task đụng đĩa, đừng giữ vòng poll /
        # request webhook lại.
        threading.Thread(target=run_workflow_from_trigger,
                         args=(wf.id, trigger_message, origin), daemon=True).start()
    ctx.send("▶️ Đã chạy: " + ", ".join(f.b(n) for n in names))


def question_text(q: AgentQuestion, fmt: type[Fmt]) -> str:
    """Nội dung tin đẩy ra khi agent hỏi — dùng chung cho mọi nền tảng."""
    f = fmt
    where = f" · {f.esc(q.client_folder)}" if q.client_folder else ""
    return (
        f"❓ {f.b('Agent cần bạn quyết')} · câu {f.b('#' + str(q.id))}\n"
        f"{f.i(q.node_label or q.node_id)}{where}\n\n"
        f"{f.esc(q.question)[:2500]}\n\n"
        f"↩️ Trả lời: reply thẳng tin này, hoặc nhắn {f.code('#' + str(q.id) + ' nội dung')}"
    )


# ── Chiều về: báo kết quả ngược lại chính chat đã ra lệnh ─────────────────
# Thiếu phần này thì trigger là đường một chiều — nhắn xong im bặt, muốn biết kết
# quả lại phải mở dashboard, đúng thứ mà bot sinh ra để khỏi phải làm.
#
# Địa chỉ trả lời lưu trên WorkflowRun (chat_bot_id / chat_id / chat_thread) ngay
# lúc tạo run, chứ không suy lại từ workflow: một workflow có thể bị kích hoạt từ
# nhiều kênh, trả nhầm chỗ còn tệ hơn không trả.

def send_to(db: Session, bot: "ChatBot", chat_id: str, text: str,
            thread: Optional[str] = None) -> None:
    """Gửi 1 tin tới chat, chọn đúng adapter theo nền tảng của bot."""
    if bot.platform == "telegram":
        import telegram_bot
        telegram_bot.send_message(bot.token, chat_id, text,
                                  reply_to=int(thread) if thread and thread.isdigit() else None)
    elif bot.platform == "slack":
        import slack_bot
        slack_bot.post_message(bot, chat_id, text, thread_ts=thread)


def fmt_for(bot: "ChatBot") -> type[Fmt]:
    return MrkdwnFmt if bot.platform == "slack" else HtmlFmt


def notify_run(run_id: int, text_builder) -> None:
    """Đẩy 1 thông báo về chat đã kích hoạt lần chạy `run_id`.

    `text_builder(fmt)` nhận lớp định dạng của nền tảng và trả về chuỗi — vì
    Telegram dùng HTML còn Slack dùng mrkdwn cho cùng một nội dung.

    Chạy nền: hàm này bị gọi từ vòng poll workflow (5s/lần) và từ endpoint
    complete của worker, cả hai đều không được ngồi chờ mạng."""
    threading.Thread(target=_notify_run_sync, args=(run_id, text_builder),
                     daemon=True).start()


def _notify_run_sync(run_id: int, text_builder) -> None:
    from database import SessionLocal
    from models import WorkflowRun
    db = SessionLocal()
    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        if not run or not run.chat_bot_id or not run.chat_id:
            return                      # chạy tay từ dashboard — không có chỗ nào để trả
        bot = db.query(ChatBot).filter(ChatBot.id == run.chat_bot_id).first()
        if not bot or not bot.enabled:
            return
        send_to(db, bot, run.chat_id, text_builder(fmt_for(bot)), thread=run.chat_thread)
    except Exception as e:
        print(f"[chat] không báo được kết quả run #{run_id}: {e}")
    finally:
        db.close()
