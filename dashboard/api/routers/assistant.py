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

import json
import re
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

import worker_heartbeat
from database import get_db
from models import (AgentQuestion, AssistantMessage, AssistantThread, Project, Setting, Workflow,
                    WorkflowRun, WorkflowStepJob)

router = APIRouter()

GREETING = "Xin chào, ngày mới tốt lành! Bạn muốn trò chuyện gì hôm nay?"

SYSTEM_PROMPT = (
    "Bạn là trợ lý AI trò chuyện trên dashboard nội bộ của một nhóm phát triển phần mềm. "
    "Trò chuyện tự nhiên, thân thiện như một đồng nghiệp: trả lời câu hỏi, giải thích, "
    "góp ý, bàn ý tưởng. Mặc định trả lời bằng tiếng Việt, ngắn gọn, đi thẳng vào ý; "
    "dùng markdown đơn giản (**đậm**, `code`, gạch đầu dòng) khi thật sự giúp dễ đọc. "
    "Bạn không có công cụ, không đọc được file hay chạy lệnh — nếu người dùng muốn giao "
    "việc thật cho agent, nhắc họ bấm nút \"📋 Tạo task\" phía trên khung chat sau khi trao đổi xong "
    "— bạn sẽ soạn nháp task từ cuộc trò chuyện để họ chọn dự án rồi tạo."
)

# Mỗi câu là 1 lần `claude -p` mới (không giữ session), nên lịch sử phải đi kèm
# prompt — cắt bớt để chi phí mỗi câu không phình theo độ dài cuộc trò chuyện.
_HISTORY_N = 20
_HISTORY_CHARS = 24000
# Worker chết giữa chừng thì tin kẹt "running" mãi — quá hạn này coi như lỗi.
_STALE = timedelta(minutes=10)


class MessageIn(BaseModel):
    text: str


class ThreadIn(BaseModel):
    title: Optional[str] = None
    # Gửi kèm mới đổi; null/"" = bỏ gắn dự án (chat tự do). Xem model_fields_set.
    client_folder: Optional[str] = None


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


def _thread_or_404(db: Session, thread_id: int) -> AssistantThread:
    t = db.query(AssistantThread).filter(AssistantThread.id == thread_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Không có cuộc trò chuyện này")
    return t


def _valid_folder(slug: Optional[str]) -> Optional[str]:
    """Slug dự án hợp lệ (có thư mục clients/<slug>) hoặc None = chat tự do."""
    from routers.projects import CLIENTS_DIR
    slug = (slug or "").strip()
    if not slug:
        return None
    if "/" in slug or "\\" in slug or slug.startswith(".") or not (CLIENTS_DIR / slug).is_dir():
        raise HTTPException(status_code=404, detail=f"Không có dự án {slug}")
    return slug


def _project_name(db: Session, slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    p = db.query(Project).filter(Project.client_folder == slug).first()
    return p.name if p and p.name else slug.replace("_", " ").replace("-", " ").title()


def _thread_out(t: AssistantThread, last: Optional[AssistantMessage], count: int, busy: bool) -> dict:
    return {"id": t.id, "title": t.title or "Cuộc trò chuyện mới",
            "client_folder": t.client_folder,
            "message_count": count, "busy": busy,
            "preview": _title_from(last.text) if last and last.text else "",
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None}


@router.get("/threads")
def list_threads(db: Session = Depends(get_db)) -> List[dict]:
    _adopt_orphans(db)
    threads = db.query(AssistantThread).order_by(desc(AssistantThread.updated_at),
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
def create_thread(payload: Optional[ThreadIn] = None, db: Session = Depends(get_db)) -> dict:
    t = AssistantThread(title=((payload.title if payload else None) or "").strip()[:120],
                        client_folder=_valid_folder(payload.client_folder if payload else None))
    db.add(t)
    db.commit()
    db.refresh(t)
    return _thread_out(t, None, 0, False)


@router.patch("/threads/{thread_id}")
def rename_thread(thread_id: int, payload: ThreadIn, db: Session = Depends(get_db)) -> dict:
    t = _thread_or_404(db, thread_id)
    if "title" in payload.model_fields_set:
        t.title = (payload.title or "").strip()[:120]
    if "client_folder" in payload.model_fields_set:
        t.client_folder = _valid_folder(payload.client_folder)
    db.commit()
    return {"id": t.id, "title": t.title or "Cuộc trò chuyện mới", "client_folder": t.client_folder}


@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: int, db: Session = Depends(get_db)) -> dict:
    t = _thread_or_404(db, thread_id)
    # Xoá tay: cột thread_id thêm bằng migration không có FK nên không CASCADE được.
    n = db.query(AssistantMessage).filter(AssistantMessage.thread_id == t.id).delete()
    db.delete(t)
    db.commit()
    return {"deleted": n}


@router.get("/threads/{thread_id}/messages")
def list_messages(thread_id: int, limit: int = 300, db: Session = Depends(get_db)) -> List[dict]:
    _thread_or_404(db, thread_id)
    rows = (db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread_id)
              .order_by(desc(AssistantMessage.id)).limit(max(1, min(limit, 1000))).all())
    return [_msg_out(m) for m in reversed(rows)]


def _busy(db: Session, thread_id: int) -> bool:
    return db.query(AssistantMessage).filter(
        AssistantMessage.thread_id == thread_id,
        AssistantMessage.status.in_(["pending", "running"])).first() is not None


@router.post("/threads/{thread_id}/messages")
def send_message(thread_id: int, payload: MessageIn, db: Session = Depends(get_db)) -> List[dict]:
    """Ghi tin người dùng + 1 tin trợ lý `pending` cho worker trả lời.
    Mỗi thread một câu một lần: gửi chồng khi câu trước chưa xong thì ngữ cảnh
    của câu sau thiếu mất câu trả lời trước. Các thread khác vẫn gửi được."""
    t = _thread_or_404(db, thread_id)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")
    if _busy(db, thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin trước — chờ chút nhé")
    if not t.title:
        t.title = _title_from(text)
    t.updated_at = datetime.utcnow()
    user_msg = AssistantMessage(thread_id=thread_id, role="user", text=text, status="done")
    db.add(user_msg)
    db.flush()                       # user_msg.id < reply.id — _build_prompt dựa vào thứ tự này
    reply = AssistantMessage(thread_id=thread_id, role="assistant", text="", status="pending")
    db.add(reply)
    db.commit()
    db.refresh(user_msg)
    db.refresh(reply)
    return [_msg_out(user_msg), _msg_out(reply)]


@router.post("/threads/{thread_id}/task-draft")
def request_task_draft(thread_id: int, payload: DraftIn, db: Session = Depends(get_db)) -> dict:
    """Nhờ Claude soạn nháp task từ cuộc trò chuyện. Tạo 1 tin trợ lý kind
    `task_draft` chờ worker — cùng hàng đợi với câu trả lời thường."""
    _thread_or_404(db, thread_id)
    if _busy(db, thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin trước — chờ chút nhé")
    has_talk = db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread_id,
                                                 AssistantMessage.role == "user").first()
    if not has_talk:
        raise HTTPException(status_code=400, detail="Trao đổi vài câu trước rồi mới tạo task được")
    projects = [{"id": str(p.get("id") or ""), "name": str(p.get("name") or "")}
                for p in payload.projects if p.get("id")][:50]
    m = AssistantMessage(thread_id=thread_id, role="assistant", text="", status="pending",
                         kind="task_draft", meta={"projects": projects})
    db.add(m)
    db.commit()
    db.refresh(m)
    return _msg_out(m)


@router.post("/messages/{msg_id}/create-task")
def create_task_from_draft(msg_id: int, payload: CreateTaskIn, db: Session = Depends(get_db)) -> dict:
    """Tạo Feature thật cho dự án từ nháp (đi đúng đường của tab Features, nên
    prd.md cũng được cập nhật như khi tạo tay), tuỳ chọn chạy workflow luôn."""
    from routers import projects as projects_router
    from routers.workflows import run_workflow

    m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id,
                                          AssistantMessage.kind == "task_draft").first()
    if not m:
        raise HTTPException(status_code=404, detail="Không có nháp task này")
    if (m.meta or {}).get("created"):
        raise HTTPException(status_code=409, detail="Nháp này đã được tạo thành task rồi")
    if not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail="Task cần có tên")
    if not (projects_router.CLIENTS_DIR / payload.client_folder).is_dir():
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
def retry_message(msg_id: int, db: Session = Depends(get_db)) -> dict:
    m = db.query(AssistantMessage).filter(AssistantMessage.id == msg_id,
                                          AssistantMessage.role == "assistant").first()
    if not m:
        raise HTTPException(status_code=404, detail="Không có tin này")
    if m.status != "error":
        raise HTTPException(status_code=409, detail="Chỉ thử lại được tin bị lỗi")
    if m.thread_id is not None and _busy(db, m.thread_id):
        raise HTTPException(status_code=409, detail="Trợ lý đang trả lời tin khác — chờ chút nhé")
    m.status, m.error, m.text, m.started_at, m.finished_at = "pending", None, "", None, None
    db.commit()
    db.refresh(m)
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

    m = (db.query(AssistantMessage)
           .filter(AssistantMessage.role == "assistant", AssistantMessage.status == "pending")
           .order_by(AssistantMessage.id).first())
    if not m:
        return None
    m.status, m.started_at = "running", now
    db.commit()
    t = db.query(AssistantThread).filter(AssistantThread.id == m.thread_id).first()
    project = _project_ctx(db, t.client_folder) if t and t.client_folder else None
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
    return {"id": m.id, "prompt": _build_prompt(db, m), "system": system,
            "project": project, **_claude_prefs(db)}


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


def _source(r: WorkflowRun) -> str:
    if r.chat_bot_id:
        return "chat"
    if r.schedule_id:
        return "schedule"
    return "task" if r.task_id else "manual"


@router.get("/overview")
def overview(limit: int = 60, tz_offset: int = 0, db: Session = Depends(get_db)) -> dict:
    """Mọi thứ màn hình trợ lý cần trong 1 lần gọi (poll vài giây/lần).

    `tz_offset` = Date.getTimezoneOffset() của trình duyệt (phút, VN = -420) —
    để "Hôm nay" là hôm nay của người xem, không phải của container (UTC)."""
    runs = (db.query(WorkflowRun).order_by(desc(WorkflowRun.id))
              .limit(max(1, min(limit, 200))).all())
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
    open_ids = {rid for (rid,) in db.query(WorkflowRun.id).filter(WorkflowRun.status == "running")}
    busy_ids = {rid for (rid,) in db.query(WorkflowStepJob.run_id)
                .filter(WorkflowStepJob.status == "running").distinct()} & open_ids

    # "Hôm nay" theo giờ người xem: nửa đêm địa phương quy về UTC (DB lưu UTC).
    now_local = datetime.utcnow() - timedelta(minutes=tz_offset)
    day_start = (now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                 + timedelta(minutes=tz_offset))
    # "Lượt" = số câu trợ lý đã trả lời hôm nay; chi phí cộng cả chat lẫn bước workflow.
    today_turns = (db.query(func.count(AssistantMessage.id))
                     .filter(AssistantMessage.role == "assistant",
                             AssistantMessage.status == "done",
                             AssistantMessage.finished_at >= day_start).scalar() or 0)
    step_cost = (db.query(func.sum(WorkflowStepJob.cost_usd))
                   .filter(WorkflowStepJob.finished_at >= day_start).scalar() or 0)
    chat_cost = (db.query(func.sum(AssistantMessage.cost_usd))
                   .filter(AssistantMessage.finished_at >= day_start).scalar() or 0)

    hb = worker_heartbeat.status()
    return {
        "jobs": jobs,
        "counts": {"running": len(busy_ids), "waiting": len(open_ids - busy_ids)},
        "today": {"turns": today_turns,
                  "cost_usd": round(float(step_cost) + float(chat_cost), 4),
                  "chat_cost_usd": round(float(chat_cost), 4)},
        "worker": {"online": bool(hb.get("online")), "silent_s": hb.get("silent_s")},
        "chat_busy": db.query(AssistantMessage.id).filter(
            AssistantMessage.status.in_(["pending", "running"])).first() is not None,
        "greeting": GREETING,
    }
