"""
Trợ lý trên dashboard — khung "Trò chuyện" + cột "Công việc"
=============================================================

Khung chat là TRÒ CHUYỆN AI thông thường — hỏi đáp, bàn ý tưởng, nhờ giải thích —
KHÔNG phải kênh giao việc: không khớp Trigger chat, không chạy workflow. Giao việc
vẫn đi đường cũ (tab Workflows, Features, bot Telegram/Slack).

Ai trả lời: API chạy trong container, không có CLI `claude` lẫn đăng nhập của bạn.
Nên gửi tin chỉ tạo 1 tin trợ lý `pending`; worker.py trên host claim, gọi
`claude -p` (tắt hết tool — chỉ nói chuyện) rồi /complete điền nội dung. Cùng
kiểu hàng đợi với WorkflowStepJob, nhưng worker chạy nó ở thread riêng để câu trả
lời không phải xếp sau một bước workflow 30 phút.

"Công việc" = các WorkflowRun gần đây (từ mọi nguồn), gom trạng thái về vài nhóm
người dùng hiểu được thay vì trạng thái kỹ thuật của từng node:
    waiting  (Chờ làm)    run đang mở nhưng không bước nào đang chạy trên worker
    running  (Đang chạy)  có bước đang chạy trên worker
    done     (Hoàn thành)
    failed / cancelled    chỉ hiện ở "Tất cả"
"""

import base64
import json
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

import auth
import chat_models
import llm_gateway as gw
import worker_heartbeat
from database import SessionLocal, get_db
from llm_gateway import _safe_name
from models import (AgentQuestion, AssistantFile, AssistantMessage, AssistantThread, Project, Setting,
                    User, Workflow, WorkflowRun, WorkflowStepJob)

router = APIRouter()

GREETING = "Xin chào, ngày mới tốt lành! Bạn muốn trò chuyện gì hôm nay?"

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI trò chuyện trên dashboard nội bộ của một nhóm phát triển phần mềm. "
    "Trò chuyện tự nhiên, thân thiện như một đồng nghiệp: trả lời câu hỏi, giải thích, "
    "góp ý, bàn ý tưởng. Mặc định trả lời bằng tiếng Việt, ngắn gọn, đi thẳng vào ý; "
    "dùng markdown đơn giản (**đậm**, `code`, gạch đầu dòng) khi thật sự giúp dễ đọc. "
    "Bạn không có công cụ, không đọc được file hay chạy lệnh (trừ file người dùng đính kèm) — nếu người dùng muốn giao "
    "việc thật cho agent, nhắc họ bấm nút \"📋 Tạo task\" phía trên khung chat sau khi trao đổi xong "
    "— bạn sẽ soạn nháp task từ cuộc trò chuyện để họ chọn dự án rồi tạo."
) + (
    "\n\nTẠO FILE: khi người dùng cần một file (Word, Excel, PowerPoint, PDF, CSV, ảnh, "
    "biểu đồ…), hãy viết MỘT khối code bắt đầu bằng ```python-file chứa script Python 3.12 "
    "hoàn chỉnh. Hệ thống chạy script đó trong sandbox rồi gửi file cho người dùng tải. Quy ước:\n"
    "- Ghi file kết quả vào thư mục `out/` (đường dẫn tương đối, vd `out/bao-cao.docx`), "
    "đặt tên file có nghĩa; tối đa 10 file, 25MB.\n"
    "- File người dùng đã đính kèm trong cuộc trò chuyện nằm ở thư mục `in/` (cùng tên).\n"
    "- Thư viện có sẵn: python-docx, openpyxl, xlsxwriter, python-pptx, reportlab, "
    "matplotlib, pillow, pandas + thư viện chuẩn. KHÔNG có mạng, không cài thêm được gì.\n"
    "- Chữ tiếng Việt trong PDF/ảnh/biểu đồ: dùng font DejaVu Sans tại "
    "`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (đậm: `DejaVuSans-Bold.ttf`) — "
    "reportlab phải registerFont font này, matplotlib đặt rcParams['font.family']='DejaVu Sans'.\n"
    "- Ngoài khối code chỉ viết 1–3 câu nói file có gì; đừng dán lại nội dung file. "
    "Không có yêu cầu tạo file thì trả lời bình thường, không viết khối python-file."
)

# Mỗi câu là 1 lần `claude -p` mới (không giữ session), nên lịch sử phải đi kèm
# prompt — cắt bớt để chi phí mỗi câu không phình theo độ dài cuộc trò chuyện.
_HISTORY_N = 20
_HISTORY_CHARS = 24000
# Worker chết giữa chừng thì tin kẹt "running" mãi — quá hạn này coi như lỗi.
_STALE = timedelta(minutes=10)
# File đính kèm: mỗi file ≤ 15MB (nginx /api/ cho body 20MB), mỗi tin ≤ 10 file.
# Mỗi câu trả lời worker nhận lại file của cả thread → chặn tổng theo thread.
_FILE_MAX = 15 * 1024 * 1024
_FILES_PER_MSG = 10
_THREAD_FILES_MAX = 40 * 1024 * 1024


class MessageIn(BaseModel):
    text: str = ""
    file_ids: List[int] = []


class ThreadIn(BaseModel):
    title: Optional[str] = None
    # Gửi kèm mới đổi; null/"" = bỏ gắn dự án (chat tự do). Xem model_fields_set.
    client_folder: Optional[str] = None
    model: Optional[str] = None      # khoá chat_models; null = mặc định


class DraftIn(BaseModel):
    # Dự án trên dashboard (slug + tên) để Claude gợi ý đúng dự án. Frontend gửi
    # vì danh sách dự án đọc từ thư mục clients/, bảng projects có thể chưa đủ.
    projects: List[dict] = []


class CreateTaskIn(BaseModel):
    client_folder: str
    name: str
    description: Optional[str] = ""
    acceptance_criteria: Optional[str] = ""
    priority: str = "medium"
    workflow_id: Optional[int] = None
    agent_key: Optional[str] = None
    run_now: bool = False             # tạo xong chạy workflow luôn


class CompleteIn(BaseModel):
    status: str                      # done | error
    text: Optional[str] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None


SANDBOX_URL = os.getenv("SANDBOX_URL", "http://sandbox:8000").rstrip("/")
_GEN_BLOCK = re.compile(r"```python-file[^\n]*\n(.*?)```", re.S)


def _file_out(f: AssistantFile) -> dict:
    return {"id": f.id, "name": f.name, "mime": f.mime, "size": f.size}


def _msg_out(m: AssistantMessage) -> dict:
    return {"id": m.id, "thread_id": m.thread_id, "role": m.role, "text": m.text or "",
            "kind": m.kind or "chat", "meta": m.meta,
            "status": m.status or "done", "error": m.error, "cost_usd": m.cost_usd,
            "created_at": m.created_at.isoformat() if m.created_at else None}


def _title_from(text: str) -> str:
    line = " ".join(re.sub(r"[*`#_>]+", "", text or "").split())   # bỏ ký hiệu markdown
    return line if len(line) <= 48 else line[:47].rstrip() + "…"


def _adopt_orphans(db: Session) -> None:
    """Tin tạo trước khi có thread (thread_id NULL) → gom vào 1 thread để không mất."""
    first = (db.query(AssistantMessage).filter(AssistantMessage.thread_id.is_(None))
               .order_by(AssistantMessage.id).first())
    if not first:
        return
    t = AssistantThread(title="Cuộc trò chuyện cũ", created_at=first.created_at,
                        updated_at=datetime.utcnow())
    db.add(t)
    db.flush()
    (db.query(AssistantMessage).filter(AssistantMessage.thread_id.is_(None))
       .update({AssistantMessage.thread_id: t.id}, synchronize_session=False))
    db.commit()


def me(request: Request, db: Session = Depends(get_db)) -> User:
    """Tài khoản đang đăng nhập (middleware auth.guard đã kiểm phiên)."""
    u = db.query(User).filter(User.id == getattr(request.state, "user_id", None)).first()
    if not u:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return u


def _mine(u: User):
    """Điều kiện lọc thread của tài khoản. Mỗi người chỉ thấy cuộc trò chuyện
    của mình; thread cũ tạo trước khi có đăng nhập (user_id NULL) chỉ admin thấy."""
    if u.is_admin:
        return or_(AssistantThread.user_id == u.id, AssistantThread.user_id.is_(None))
    return AssistantThread.user_id == u.id


def _my_thread_ids(db: Session, u: User):
    return db.query(AssistantThread.id).filter(_mine(u))


def _thread_or_404(db: Session, thread_id: int, u: User) -> AssistantThread:
    # Thread của người khác trả 404 như không tồn tại — không lộ là có.
    t = db.query(AssistantThread).filter(AssistantThread.id == thread_id, _mine(u)).first()
    if not t:
        raise HTTPException(status_code=404, detail="Không có cuộc trò chuyện này")
    return t


def _valid_folder(slug: Optional[str], request: Optional[Request] = None) -> Optional[str]:
    """Slug dự án hợp lệ (có thư mục clients/<slug>, tài khoản được gán) hoặc
    None = chat tự do."""
    from routers.projects import CLIENTS_DIR
    slug = (slug or "").strip()
    if not slug:
        return None
    if "/" in slug or "\\" in slug or slug.startswith(".") or not (CLIENTS_DIR / slug).is_dir() \
            or (request is not None and not auth.project_ok(request, slug)):
        raise HTTPException(status_code=404, detail=f"Không có dự án {slug}")
    return slug


def _project_name(db: Session, slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    p = db.query(Project).filter(Project.client_folder == slug).first()
    return p.name if p and p.name else slug.replace("_", " ").replace("-", " ").title()


def _thread_out(t: AssistantThread, last: Optional[AssistantMessage], count: int, busy: bool) -> dict:
    return {"id": t.id, "title": t.title or "Cuộc trò chuyện mới",
            "client_folder": t.client_folder, "model": t.model,
            "message_count": count, "busy": busy,
            "preview": _title_from(last.text) if last and last.text else "",
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None}


# ── Model ──────────────────────────────────────────────────────────────────

def _valid_model(db: Session, u: User, key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    if key not in {m["key"] for m in chat_models.allowed(db, u)}:
        raise HTTPException(status_code=403, detail="Tài khoản không được dùng model này")
    return key


def _thread_model(db: Session, t: AssistantThread, u: User) -> dict:
    """Model sẽ trả lời câu tiếp theo: model của thread nếu còn được dùng, không
    thì model đầu tiên tài khoản được cấp."""
    allowed = chat_models.allowed(db, u)
    if not allowed:
        raise HTTPException(status_code=403, detail="Tài khoản chưa được cấp model nào — liên hệ quản trị viên")
    return next((m for m in allowed if m["key"] == t.model), allowed[0])


@router.get("/models")
def list_models(db: Session = Depends(get_db), u: User = Depends(me)) -> List[dict]:
    """Model tài khoản được dùng — phần tử đầu là mặc định."""
    return [chat_models.public(m) for m in chat_models.allowed(db, u)]


def _dispatch(reply_id: int, spec: dict) -> None:
    """Model HTTP: API tự gọi provider trong thread nền (worker không làm hộ).
    Model CLI: để `pending`, worker claim như cũ."""
    if spec["via"] == "http":
        threading.Thread(target=_http_reply, args=(reply_id,), daemon=True,
                         name=f"chat-http-{reply_id}").start()


def _new_reply(db: Session, t: AssistantThread, u: User, **kw) -> tuple:
    spec = _thread_model(db, t, u)
    meta = {**(kw.pop("meta", None) or {}), "model": spec["key"]}
    http = spec["via"] == "http"
    reply = AssistantMessage(thread_id=t.id, role="assistant", text="", meta=meta,
                             status="running" if http else "pending",
                             started_at=datetime.utcnow() if http else None, **kw)
    return reply, spec


def _http_reply(msg_id: int) -> None:
    db = SessionLocal()
    try:
        m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id).first()
        spec = chat_models.get(db, (m.meta or {}).get("model")) if m else None
        if not m:
            return
        if not spec or spec["via"] != "http":
            body = CompleteIn(status="error", error="Model không còn — chọn model khác rồi thử lại.")
        else:
            try:
                resp = gw.chat(db, None, {"model": spec["alias"], "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_prompt(db, m)}]})
                usage = resp.get("usage") or {}
                body = CompleteIn(status="done",
                                  text=((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or "",
                                  model_used=spec["alias"],
                                  cost_usd=usage.get("cost") if isinstance(usage.get("cost"), (int, float)) else None)
            except gw.GatewayError as e:
                body = CompleteIn(status="error", error=e.message)
            except Exception as e:                       # đừng để tin kẹt "running"
                body = CompleteIn(status="error", error=str(e))
        complete_reply(msg_id, body, db)
    finally:
        db.close()


@router.get("/threads")
def list_threads(db: Session = Depends(get_db), u: User = Depends(me)) -> List[dict]:
    _adopt_orphans(db)
    threads = db.query(AssistantThread).filter(_mine(u)).order_by(desc(AssistantThread.updated_at),
                                                                  desc(AssistantThread.id)).all()
    counts = dict(db.query(AssistantMessage.thread_id, func.count(AssistantMessage.id))
                    .group_by(AssistantMessage.thread_id).all())
    busy = {tid for (tid,) in db.query(AssistantMessage.thread_id).filter(
        AssistantMessage.status.in_(["pending", "running"])).distinct()}
    last_ids = dict(db.query(AssistantMessage.thread_id, func.max(AssistantMessage.id))
                      .filter(AssistantMessage.text != "")
                      .group_by(AssistantMessage.thread_id).all())
    lasts = ({m.id: m for m in db.query(AssistantMessage)
                               .filter(AssistantMessage.id.in_(list(last_ids.values()))).all()}
             if last_ids else {})
    return [_thread_out(t, lasts.get(last_ids.get(t.id)), counts.get(t.id, 0), t.id in busy)
            for t in threads]


@router.post("/threads")
def create_thread(request: Request, payload: Optional[ThreadIn] = None, db: Session = Depends(get_db),
                  u: User = Depends(me)) -> dict:
    t = AssistantThread(user_id=u.id, title=((payload.title if payload else None) or "").strip()[:120],
                        client_folder=_valid_folder(payload.client_folder if payload else None, request),
                        model=_valid_model(db, u, payload.model if payload else None))
    db.add(t)
    db.commit()
    db.refresh(t)
    return _thread_out(t, None, 0, False)


@router.patch("/threads/{thread_id}")
def rename_thread(thread_id: int, payload: ThreadIn, request: Request, db: Session = Depends(get_db),
                  u: User = Depends(me)) -> dict:
    t = _thread_or_404(db, thread_id, u)
    if "title" in payload.model_fields_set:
        t.title = (payload.title or "").strip()[:120]
    if "client_folder" in payload.model_fields_set:
        t.client_folder = _valid_folder(payload.client_folder, request)
    if "model" in payload.model_fields_set:
        t.model = _valid_model(db, u, payload.model)
    db.commit()
    return {"id": t.id, "title": t.title or "Cuộc trò chuyện mới", "client_folder": t.client_folder,
            "model": t.model}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: int, db: Session = Depends(get_db), u: User = Depends(me)) -> dict:
    t = _thread_or_404(db, thread_id, u)
    # Xoá tay: cột thread_id thêm bằng migration không có FK nên không CASCADE được.
    n = db.query(AssistantMessage).filter(AssistantMessage.thread_id == t.id).delete()
    db.query(AssistantFile).filter(AssistantFile.thread_id == t.id).delete()
    db.delete(t)
    db.commit()
    return {"deleted": n}


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: int, limit: int = 300, db: Session = Depends(get_db),
                  u: User = Depends(me)) -> List[dict]:
    _thread_or_404(db, thread_id, u)
    rows = (db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread_id)
              .order_by(desc(AssistantMessage.id)).limit(max(1, min(limit, 1000))).all())
    return [_msg_out(m) for m in reversed(rows)]


def _busy(db: Session, thread_id: int) -> bool:
    return db.query(AssistantMessage).filter(
        AssistantMessage.thread_id == thread_id,
        AssistantMessage.status.in_(["pending", "running"])).first() is not None


@router.post("/threads/{thread_id}/messages")
def send_message(thread_id: int, payload: MessageIn, db: Session = Depends(get_db),
                 u: User = Depends(me)) -> List[dict]:
    """Ghi tin người dùng + 1 tin trợ lý `pending` cho worker trả lời.
    Mỗi thread một câu một lần: gửi chồng khi câu trước chưa xong thì ngữ cảnh
    của câu sau thiếu mất câu trả lời trước. Các thread khác vẫn gửi được."""
    t = _thread_or_404(db, thread_id, u)
    text = (payload.text or "").strip()
    ids = list(dict.fromkeys(payload.file_ids))
    if len(ids) > _FILES_PER_MSG:
        raise HTTPException(status_code=400, detail=f"Tối đa {_FILES_PER_MSG} file mỗi tin")
    files = (db.query(AssistantFile).filter(AssistantFile.id.in_(ids),
                                            AssistantFile.thread_id == thread_id,
                                            AssistantFile.message_id.is_(None))
               .order_by(AssistantFile.id).all()) if ids else []
    if len(files) != len(ids):
        raise HTTPException(status_code=400, detail="File đính kèm không còn — tải lên lại nhé")
    if not text and not files:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")
    if _busy(db, thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin trước — chờ chút nhé")
    reply, spec = _new_reply(db, t, u)
    if files and not spec["files"]:
        raise HTTPException(status_code=400, detail=(
            f"Model {spec['label']} không đọc được file đính kèm — chọn model Claude để gửi file"))
    if not t.title:
        t.title = _title_from(text or files[0].name)
    # Chỉ gửi file, không gõ chữ → câu nhờ mặc định để Claude biết phải làm gì.
    text = text or "Xem giúp mình file đính kèm."
    t.updated_at = datetime.utcnow()
    user_msg = AssistantMessage(thread_id=thread_id, role="user", text=text, status="done",
                                meta={"files": [_file_out(f) for f in files]} if files else None)
    db.add(user_msg)
    db.flush()                       # user_msg.id < reply.id — _build_prompt dựa vào thứ tự này
    for f in files:
        f.message_id = user_msg.id
    db.add(reply)
    db.commit()
    db.refresh(user_msg)
    db.refresh(reply)
    _dispatch(reply.id, spec)
    return [_msg_out(user_msg), _msg_out(reply)]


@router.post("/threads/{thread_id}/files")
async def upload_file(thread_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                      u: User = Depends(me)) -> dict:
    """Tải 1 file lên trước khi gửi tin — tin gửi sau kèm `file_ids`. Lưu trong DB
    (không ghi đĩa API) vì worker trả lời có thể ở máy khác."""
    _thread_or_404(db, thread_id, u)
    data = await file.read(_FILE_MAX + 1)
    if not data:
        raise HTTPException(status_code=400, detail="File rỗng")
    if len(data) > _FILE_MAX:
        raise HTTPException(status_code=413, detail=f"File quá {_FILE_MAX // 1024 // 1024} MB")
    used = (db.query(func.sum(AssistantFile.size))
              .filter(AssistantFile.thread_id == thread_id).scalar() or 0)
    if used + len(data) > _THREAD_FILES_MAX:
        raise HTTPException(status_code=413, detail=(
            f"Cuộc trò chuyện này đã có {used // 1024 // 1024} MB file — tối đa "
            f"{_THREAD_FILES_MAX // 1024 // 1024} MB. Mở cuộc trò chuyện mới để gửi thêm."))
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip()
    # Tên trùng với file khác trong thread thì thêm hậu tố — worker ghi chung 1 thư mục.
    taken = {n.lower() for (n,) in db.query(AssistantFile.name)
                                     .filter(AssistantFile.thread_id == thread_id).all()}
    f = AssistantFile(thread_id=thread_id, mime=mime, size=len(data), data=data,
                      name=_safe_name(file.filename or "", mime, len(taken) + 1, taken))
    db.add(f)
    db.commit()
    db.refresh(f)
    return _file_out(f)


@router.delete("/files/{file_id}")
def delete_file(file_id: int, db: Session = Depends(get_db), u: User = Depends(me)) -> dict:
    """Bỏ file khỏi ô soạn tin. File đã gửi thì giữ — nó thuộc lịch sử trò chuyện."""
    f = db.query(AssistantFile).filter(AssistantFile.id == file_id,
                                       AssistantFile.thread_id.in_(_my_thread_ids(db, u))).first()
    if not f:
        raise HTTPException(status_code=404, detail="Không có file này")
    if f.message_id is not None:
        raise HTTPException(status_code=409, detail="File đã gửi, không xoá riêng được")
    db.delete(f)
    db.commit()
    return {"deleted": file_id}


@router.get("/files/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db), u: User = Depends(me)) -> Response:
    f = db.query(AssistantFile).filter(AssistantFile.id == file_id,
                                       AssistantFile.thread_id.in_(_my_thread_ids(db, u))).first()
    if not f:
        raise HTTPException(status_code=404, detail="Không có file này")
    # Chỉ ảnh/PDF/chữ thuần mới mở thẳng trên trình duyệt; còn lại (kể cả HTML/SVG
    # — chạy được script trên origin dashboard) luôn tải về.
    inline = f.mime in ("application/pdf", "text/plain") or (
        f.mime.startswith("image/") and f.mime != "image/svg+xml")
    return Response(content=f.data, media_type=f.mime if inline else "application/octet-stream",
                    headers={"Content-Disposition": "{}; filename*=UTF-8''{}".format(
                                 "inline" if inline else "attachment", quote(f.name)),
                             "X-Content-Type-Options": "nosniff"})


@router.post("/threads/{thread_id}/task-draft")
def request_task_draft(thread_id: int, payload: DraftIn, db: Session = Depends(get_db),
                       u: User = Depends(me)) -> dict:
    """Nhờ Claude soạn nháp task từ cuộc trò chuyện. Tạo 1 tin trợ lý kind
    `task_draft` chờ worker — cùng hàng đợi với câu trả lời thường."""
    t = _thread_or_404(db, thread_id, u)
    if _busy(db, thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin trước — chờ chút nhé")
    has_talk = db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread_id,
                                                 AssistantMessage.role == "user").first()
    if not has_talk:
        raise HTTPException(status_code=400, detail="Trao đổi vài câu trước rồi mới tạo task được")
    projects = [{"id": str(p.get("id") or ""), "name": str(p.get("name") or "")}
                for p in payload.projects if p.get("id")][:50]
    m, spec = _new_reply(db, t, u, kind="task_draft", meta={"projects": projects})
    db.add(m)
    db.commit()
    db.refresh(m)
    _dispatch(m.id, spec)
    return _msg_out(m)


@router.post("/messages/{msg_id}/create-task")
def create_task_from_draft(msg_id: int, payload: CreateTaskIn, request: Request,
                           db: Session = Depends(get_db), u: User = Depends(me)) -> dict:
    """Tạo Feature thật cho dự án từ nháp (đi đúng đường của tab Features, nên
    prd.md cũng được cập nhật như khi tạo tay), tuỳ chọn chạy workflow luôn."""
    from routers import projects as projects_router
    from routers.workflows import run_workflow

    m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id,
                                          AssistantMessage.kind == "task_draft",
                                          AssistantMessage.thread_id.in_(_my_thread_ids(db, u))).first()
    if not m:
        raise HTTPException(status_code=404, detail="Không có nháp task này")
    if (m.meta or {}).get("created"):
        raise HTTPException(status_code=409, detail="Nháp này đã được tạo thành task rồi")
    if not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail="Task cần có tên")
    if not (projects_router.CLIENTS_DIR / payload.client_folder).is_dir() \
            or not auth.project_ok(request, payload.client_folder):
        raise HTTPException(status_code=404, detail=f"Không có dự án {payload.client_folder}")

    feature = projects_router.create_feature(payload.client_folder, projects_router.FeatureCreate(
        name=payload.name.strip(), description=(payload.description or "").strip(),
        priority=payload.priority if payload.priority in ("high", "medium", "low") else "medium",
        acceptance_criteria=(payload.acceptance_criteria or "").strip(),
        workflow_id=payload.workflow_id, agent_key=payload.agent_key or None), db)

    run_id, run_error = None, None
    if payload.run_now and payload.workflow_id:
        try:
            run_id = run_workflow(payload.workflow_id, task_id=feature["id"], db=db).id
        except HTTPException as e:                # task đã tạo — chỉ báo lỗi chạy
            run_error = str(e.detail)

    meta = dict(m.meta or {})
    meta["created"] = {"client_folder": payload.client_folder, "task_id": feature["id"],
                       "name": feature["name"], "workflow_id": payload.workflow_id,
                       "run_id": run_id, "run_error": run_error,
                       "at": datetime.utcnow().isoformat()}
    m.meta = meta                                 # gán dict mới: JSON không tự theo dõi sửa tại chỗ
    db.commit()
    db.refresh(m)
    return _msg_out(m)


@router.post("/messages/{msg_id}/retry")
def retry_message(msg_id: int, db: Session = Depends(get_db), u: User = Depends(me)) -> dict:
    m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id,
                                          AssistantMessage.role == "assistant",
                                          AssistantMessage.thread_id.in_(_my_thread_ids(db, u))).first()
    if not m:
        raise HTTPException(status_code=404, detail="Không có tin này")
    if m.status != "error":
        raise HTTPException(status_code=409, detail="Chỉ thử lại được tin bị lỗi")
    if m.thread_id is not None and _busy(db, m.thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin khác — chờ chút nhé")
    # Thử lại bằng model ĐANG chọn của thread — lỗi do model thì đổi model rồi bấm lại.
    t = _thread_or_404(db, m.thread_id, u)
    spec = _thread_model(db, t, u)
    http = spec["via"] == "http"
    m.meta = {**(m.meta or {}), "model": spec["key"]}
    m.status, m.error, m.text, m.finished_at = ("running" if http else "pending"), None, "", None
    m.started_at = datetime.utcnow() if http else None
    db.commit()
    db.refresh(m)
    _dispatch(m.id, spec)
    return _msg_out(m)


def _build_prompt(db: Session, reply: AssistantMessage) -> str:
    """Lịch sử của ĐÚNG thread này (tới trước tin trợ lý đang chờ) thành 1 prompt."""
    rows = (db.query(AssistantMessage)
              .filter(AssistantMessage.thread_id == reply.thread_id,
                      AssistantMessage.id < reply.id,
                      AssistantMessage.status == "done",
                      AssistantMessage.text != "")
              .order_by(desc(AssistantMessage.id)).limit(_HISTORY_N).all())
    lines: List[str] = []
    used = 0
    for m in rows:                                   # mới → cũ, dừng khi quá dài
        who = "Người dùng" if m.role == "user" else "Trợ lý"
        line = f"{who}: {m.text.strip()}"
        tag = "Đính kèm" if m.role == "user" else "Đã tạo file"
        line += "".join(f"\n[{tag}: {f['name']}]" for f in (m.meta or {}).get("files") or [])
        if used + len(line) > _HISTORY_CHARS and lines:
            break
        lines.append(line)
        used += len(line)
    lines.reverse()
    if (reply.kind or "chat") == "task_draft":
        t = db.query(AssistantThread).filter(AssistantThread.id == reply.thread_id).first()
        return _draft_prompt(lines, (reply.meta or {}).get("projects") or [],
                             t.client_folder if t else None)
    return ("Đây là cuộc trò chuyện tới giờ. Hãy viết câu trả lời TIẾP THEO của Trợ lý "
            "cho tin cuối của Người dùng — chỉ nội dung câu trả lời, không thêm tiền tố "
            "\"Trợ lý:\".\n\n" + "\n\n".join(lines))


def _draft_prompt(lines: List[str], projects: List[dict], current: Optional[str] = None) -> str:
    proj = "\n".join(f"- {p['id']}: {p['name']}" for p in projects) or "(không có)"
    if current:
        proj += f"\n\nCuộc trò chuyện đang gắn với dự án `{current}` — chọn dự án này trừ khi nội dung rõ ràng nói về dự án khác."
    return (
        "Dưới đây là cuộc trò chuyện giữa Người dùng và Trợ lý. Người dùng muốn biến nội "
        "dung đã trao đổi thành MỘT task (feature) giao cho agent lập trình làm.\n\n"
        "Chỉ trả về đúng 1 object JSON, không kèm chữ nào khác, không bọc ```:\n"
        '{"name": "tên task ngắn gọn, bắt đầu bằng động từ", '
        '"description": "mô tả markdown: bối cảnh, cần làm gì, phạm vi — đủ để dev không phải đọc lại cuộc trò chuyện", '
        '"acceptance_criteria": "mỗi dòng một tiêu chí nghiệm thu, bắt đầu bằng \\"- \\"", '
        '"priority": "high | medium | low", '
        '"project": "id dự án phù hợp nhất trong danh sách, hoặc chuỗi rỗng nếu không rõ"}\n\n'
        "Viết bằng tiếng Việt. Chỉ dùng thông tin có trong cuộc trò chuyện, không bịa thêm yêu cầu.\n\n"
        f"Các dự án:\n{proj}\n\nCuộc trò chuyện:\n\n" + "\n\n".join(lines))


def _parse_draft(text: str) -> Optional[dict]:
    """JSON nháp task từ câu trả lời của Claude — chịu được việc nó lỡ bọc ```json."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(d, dict) or not str(d.get("name") or "").strip():
        return None
    pr = str(d.get("priority") or "medium").strip().lower()
    return {"name": str(d.get("name")).strip()[:200],
            "description": str(d.get("description") or "").strip(),
            "acceptance_criteria": str(d.get("acceptance_criteria") or "").strip(),
            "priority": pr if pr in ("high", "medium", "low") else "medium",
            "project": str(d.get("project") or "").strip()}


def _claude_prefs(db: Session) -> dict:
    """Tài khoản Claude chọn ở Settings (dùng chung với bước workflow) + model
    riêng cho chat nếu có đặt `assistant_model` (trống = mặc định của CLI)."""
    rows = {s.key: s.value for s in db.query(Setting).filter(
        Setting.key.in_(["claude_account", "claude_auto_switch", "assistant_model"])).all()}
    return {
        "claude_account":     (rows.get("claude_account") or "").strip() or None,
        "claude_auto_switch": (rows.get("claude_auto_switch") or "true").strip().lower() != "false",
        "model":              (rows.get("assistant_model") or "").strip() or None,
    }


@router.post("/claim")
def claim_reply(db: Session = Depends(get_db)) -> Optional[dict]:
    """worker.py (thread chat) gọi đây. Trả tin trợ lý `pending` cũ nhất kèm
    prompt, đánh dấu `running`. null = không có gì để trả lời."""
    worker_heartbeat.touch()
    now = datetime.utcnow()
    for m in (db.query(AssistantMessage)
                .filter(AssistantMessage.status == "running",
                        AssistantMessage.started_at < now - _STALE).all()):
        m.status, m.finished_at = "error", now
        m.error = "Worker không trả lời kịp (có thể đã bị tắt giữa chừng)."
    db.commit()

    while True:
        m = (db.query(AssistantMessage)
               .filter(AssistantMessage.role == "assistant", AssistantMessage.status == "pending")
               .order_by(AssistantMessage.id).first())
        if not m:
            return None
        # Tin cũ (trước khi chọn được model) không có meta.model → Claude mặc định của CLI.
        key = (m.meta or {}).get("model")
        spec = chat_models.get(db, key) if key else {"cli": "claude", "model": None, "project": True,
                                                     "system_prompt": None, "via": "cli"}
        if spec and spec["via"] == "cli":
            break
        m.status, m.finished_at = "error", now
        m.error = "Model của tin này đã bị tắt hoặc xoá — chọn model khác rồi bấm thử lại."
        db.commit()
    m.status, m.started_at = "running", now
    db.commit()
    t = db.query(AssistantThread).filter(AssistantThread.id == m.thread_id).first()
    project = (_project_ctx(db, t.client_folder)
               if t and t.client_folder and spec["project"] else None)
    system = SYSTEM_PROMPT
    if project:
        system = SYSTEM_PROMPT.replace(
            "Bạn không có công cụ, không đọc được file hay chạy lệnh",
            "Bạn chỉ có công cụ ĐỌC (Read, Grep, Glob), không sửa file, không chạy lệnh") + (
            f"\n\nCuộc trò chuyện này gắn với dự án **{project['name']}** (slug `{project['slug']}`). "
            f"Tài liệu dự án (PRD, settings.toml, docs) nằm ở `{project['docs_dir']}`; "
            f"code nằm ở: {', '.join('`' + d + '`' for d in project['code_dirs']) or '(chưa cấu hình)'}. "
            "Khi câu hỏi liên quan tới dự án, hãy đọc tài liệu/code thật trước rồi mới trả lời, "
            "nêu rõ file đã xem. Chỉ đọc những gì cần — đừng quét cả repo. Câu hỏi không liên "
            "quan tới dự án thì cứ trả lời bình thường.")
    # File của cả thread (đã gửi trước tin đang trả lời): worker ghi ra thư mục tạm
    # và mở quyền đọc cho Claude — câu sau vẫn hỏi lại được file gửi từ trước.
    files = [{"name": f.name, "mime": f.mime, "data": base64.b64encode(f.data).decode()}
             for f in (db.query(AssistantFile)
                         .filter(AssistantFile.thread_id == m.thread_id,
                                 AssistantFile.message_id.isnot(None),
                                 AssistantFile.message_id < m.id)
                         .order_by(AssistantFile.id).all())] if m.thread_id is not None else []
    if spec.get("system_prompt"):            # system prompt của alias gateway
        system = spec["system_prompt"] + "\n\n" + system
    prefs = _claude_prefs(db)
    return {"id": m.id, "prompt": _build_prompt(db, m), "system": system,
            "project": project, "files": files, **prefs,
            # worker: cli = claude | grok; model None = mặc định của CLI (assistant_model nếu có)
            "cli": spec["cli"], "model": spec["model"] or prefs["model"]}


def _project_ctx(db: Session, slug: str) -> Optional[dict]:
    """Thư mục worker cần mở quyền đọc cho Claude: clients/<slug> (tài liệu) + thư
    mục code theo [output] trong settings.toml — cùng cách tính với bước workflow."""
    from types import SimpleNamespace
    from routers.workflows import _job_add_dirs
    try:
        code_dirs = _job_add_dirs(SimpleNamespace(client_folder=slug))
    except Exception:                                   # settings.toml lạ — vẫn cho đọc tài liệu
        code_dirs = []
    return {"slug": slug, "name": _project_name(db, slug),
            "docs_dir": f"clients/{slug}", "code_dirs": code_dirs}


@router.post("/messages/{msg_id}/complete")
def complete_reply(msg_id: int, payload: CompleteIn, db: Session = Depends(get_db)) -> dict:
    m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Không có tin này")
    text = (payload.text or "").strip()
    ok = payload.status == "done" and bool(text)
    err = None if ok else (payload.error or "Claude không trả lời gì")
    if ok and (m.kind or "chat") == "task_draft":
        draft = _parse_draft(text)
        if draft is None:
            ok, err = False, "Claude không trả về nháp task đúng định dạng — bấm thử lại."
        else:
            projects = (m.meta or {}).get("projects") or []
            if draft["project"] not in {p["id"] for p in projects}:
                draft["project"] = ""
            if not draft["project"] and m.thread_id is not None:
                t = db.query(AssistantThread).filter(AssistantThread.id == m.thread_id).first()
                draft["project"] = (t.client_folder if t else None) or ""
            m.meta = {**(m.meta or {}), "draft": draft}
            # Chữ ngắn thay cho JSON: tin này vẫn nằm trong lịch sử gửi Claude.
            text = f"📋 Đã soạn nháp task: {draft['name']}"
    gen = _GEN_BLOCK.search(text) if ok and (m.kind or "chat") == "chat" else None
    if gen:
        # Có script tạo file: giữ tin ở "running" (khung chat còn chờ) tới khi
        # sandbox chạy xong — worker không phải đợi, request /complete về ngay.
        text = (_GEN_BLOCK.sub("", text).strip() or "Đã tạo file theo yêu cầu.")
        m.meta = {**(m.meta or {}), "gen": {"status": "running", "code": gen.group(1).strip()}}
        m.text, m.error = text, None
        m.model_used, m.cost_usd = payload.model_used, payload.cost_usd
        db.commit()
        threading.Thread(target=_run_gen, args=(m.id,), daemon=True, name=f"chat-gen-{m.id}").start()
        return _msg_out(m)
    m.status      = "done" if ok else "error"
    m.text        = text if ok else ""
    m.error       = None if ok else err[:2000]
    m.model_used  = payload.model_used
    m.cost_usd    = payload.cost_usd
    m.finished_at = datetime.utcnow()
    if m.thread_id is not None:
        t = db.query(AssistantThread).filter(AssistantThread.id == m.thread_id).first()
        if t:
            t.updated_at = m.finished_at
    db.commit()
    return _msg_out(m)


def _sandbox(code: str, files: list) -> dict:
    req = urllib.request.Request(f"{SANDBOX_URL}/run", method="POST",
                                 data=json.dumps({"code": code, "files": files}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "files": [],
                "error": f"Không gọi được sandbox tạo file ({e}) — container `sandbox` có đang chạy?"}


def _run_gen(msg_id: int) -> None:
    """Chạy script của tin trợ lý trong sandbox, lưu file kết quả như file của
    thread (gắn vào chính tin này) → khung chat hiện nút tải; câu sau model
    vẫn thấy file đã tạo trong in/."""
    db = SessionLocal()
    try:
        m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id).first()
        if not m:
            return
        gen = dict((m.meta or {}).get("gen") or {})
        inputs = [{"name": f.name, "data": base64.b64encode(f.data).decode()}
                  for f in db.query(AssistantFile).filter(AssistantFile.thread_id == m.thread_id,
                                                          AssistantFile.message_id.isnot(None),
                                                          AssistantFile.message_id < m.id)]
        res = _sandbox(gen.get("code") or "", inputs)
        taken = {n.lower() for (n,) in db.query(AssistantFile.name)
                                         .filter(AssistantFile.thread_id == m.thread_id).all()}
        made = []
        for f in res.get("files") or []:
            data = base64.b64decode(f.get("data") or "")
            mime = f.get("mime") or "application/octet-stream"
            row = AssistantFile(thread_id=m.thread_id, message_id=m.id, mime=mime, size=len(data),
                                data=data, name=_safe_name(f.get("name") or "", mime, len(taken) + 1, taken))
            db.add(row)
            db.flush()
            made.append(_file_out(row))
        gen["status"] = "done" if res.get("ok") else "error"
        if not res.get("ok"):
            gen["error"] = str(res.get("error") or "Không rõ lỗi")[-3000:]
        meta = {**(m.meta or {}), "gen": gen}
        if made:
            meta["files"] = made
        m.meta = meta
        m.status, m.finished_at = "done", datetime.utcnow()
        t = db.query(AssistantThread).filter(AssistantThread.id == m.thread_id).first()
        if t:
            t.updated_at = m.finished_at
        db.commit()
    except Exception as e:                           # đừng để tin kẹt "running"
        db.rollback()
        m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id).first()
        if m:
            m.meta = {**(m.meta or {}), "gen": {**((m.meta or {}).get("gen") or {}),
                                                "status": "error", "error": str(e)}}
            m.status, m.finished_at = "done", datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _source(r: WorkflowRun) -> str:
    if r.chat_bot_id:
        return "chat"
    if r.schedule_id:
        return "schedule"
    return "task" if r.task_id else "manual"


@router.get("/overview")
def overview(request: Request, limit: int = 60, tz_offset: int = 0, db: Session = Depends(get_db),
             u: User = Depends(me)) -> dict:
    """Mọi thứ màn hình trợ lý cần trong 1 lần gọi (poll vài giây/lần).

    `tz_offset` = Date.getTimezoneOffset() của trình duyệt (phút, VN = -420) —
    để "Hôm nay" là hôm nay của người xem, không phải của container (UTC)."""
    # Tài khoản thường: chỉ run của workflow thuộc dự án được gán (auth.py).
    allowed = auth.allowed_projects(request)
    scoped = db.query(WorkflowRun)
    if allowed is not None:
        # Workflow.client_folder là property (qua Project) → lọc bằng join.
        scoped = scoped.filter(WorkflowRun.workflow_id.in_(
            db.query(Workflow.id).join(Project, Project.id == Workflow.project_id)
              .filter(Project.client_folder.in_(list(allowed) or [""]))))
    runs = scoped.order_by(desc(WorkflowRun.id)).limit(max(1, min(limit, 200))).all()
    ids = [r.id for r in runs]

    step_state: dict[int, set] = {}
    cost_by_run: dict[int, float] = {}
    if ids:
        for run_id, status, cost in (db.query(WorkflowStepJob.run_id, WorkflowStepJob.status,
                                              WorkflowStepJob.cost_usd)
                                       .filter(WorkflowStepJob.run_id.in_(ids)).all()):
            step_state.setdefault(run_id, set()).add(status)
            cost_by_run[run_id] = cost_by_run.get(run_id, 0.0) + (cost or 0.0)

    open_q: dict[int, int] = {}
    for (run_id,) in db.query(AgentQuestion.run_id).filter(AgentQuestion.status == "open").all():
        open_q[run_id] = open_q.get(run_id, 0) + 1

    wf_ids = {r.workflow_id for r in runs}
    wfs = ({w.id: w for w in db.query(Workflow).filter(Workflow.id.in_(wf_ids)).all()}
           if wf_ids else {})

    jobs = []
    for r in runs:
        wf = wfs.get(r.workflow_id)
        st = r.node_status or {}
        steps = step_state.get(r.id, set())
        if r.status == "running":
            state = "running" if "running" in steps else "waiting"
        else:
            state = "done" if r.status == "done" else (r.status or "failed")
        reason = None
        if state == "waiting":
            reason = ("chờ bạn trả lời" if open_q.get(r.id)
                      else "chờ worker nhận" if "queued" in steps
                      else "chờ chạy tay")
        jobs.append({
            "run_id": r.id,
            "workflow_id": r.workflow_id,
            "title": wf.name if wf else f"Workflow #{r.workflow_id}",
            "client_folder": wf.client_folder if wf else None,
            "state": state,
            "reason": reason,
            "open_questions": open_q.get(r.id, 0),
            "source": _source(r),
            "trigger": next((e.get("message") for e in (r.log or []) if e.get("message")), None),
            "progress": {"done": sum(1 for v in st.values() if v in ("ok", "skipped", "error")),
                         "total": len(st)},
            "cost_usd": round(cost_by_run.get(r.id, 0.0), 4),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        })

    # Đếm trên TOÀN bộ run đang mở, không chỉ `limit` bản gần nhất.
    open_ids = {r.id for r in scoped.filter(WorkflowRun.status == "running")}
    busy_ids = {rid for (rid,) in db.query(WorkflowStepJob.run_id)
                .filter(WorkflowStepJob.status == "running").distinct()} & open_ids

    # "Hôm nay" theo giờ người xem: nửa đêm địa phương quy về UTC (DB lưu UTC).
    now_local = datetime.utcnow() - timedelta(minutes=tz_offset)
    day_start = (now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                 + timedelta(minutes=tz_offset))
    # "Lượt" = số câu trợ lý đã trả lời hôm nay trong các cuộc trò chuyện CỦA tài khoản
    # này; chi phí = chat của mình, admin cộng thêm chi phí bước workflow (chung cả nhóm).
    mine = AssistantMessage.thread_id.in_(_my_thread_ids(db, u))
    today_turns = (db.query(func.count(AssistantMessage.id))
                     .filter(mine, AssistantMessage.role == "assistant",
                             AssistantMessage.status == "done",
                             AssistantMessage.finished_at >= day_start).scalar() or 0)
    step_cost = (db.query(func.sum(WorkflowStepJob.cost_usd))
                   .filter(WorkflowStepJob.finished_at >= day_start).scalar() or 0) if u.is_admin else 0
    chat_cost = (db.query(func.sum(AssistantMessage.cost_usd))
                   .filter(mine, AssistantMessage.finished_at >= day_start).scalar() or 0)

    hb = worker_heartbeat.status()
    return {
        "jobs": jobs,
        "counts": {"running": len(busy_ids), "waiting": len(open_ids - busy_ids)},
        "today": {"turns": today_turns,
                  "cost_usd": round(float(step_cost) + float(chat_cost), 4),
                  "chat_cost_usd": round(float(chat_cost), 4)},
        "worker": {"online": bool(hb.get("online")), "silent_s": hb.get("silent_s")},
        "chat_busy": db.query(AssistantMessage.id).filter(
            mine, AssistantMessage.status.in_(["pending", "running"])).first() is not None,
        "greeting": GREETING,
    }
