"""
Workflows — trình xây dựng workflow kéo-thả
============================================
CRUD định nghĩa workflow (nodes/edges dạng React Flow) + validate graph +
engine thực thi dựa trên FILE .md — KHÔNG tự động gọi Claude/opencode/git.

Cơ chế (xem thêm ai_team/runner.py — pipeline tự động bị cấm dùng Claude Code
subscription cá nhân, xem docstring ở đó):
  1. Trigger khớp (Slack app_mention thật, hoặc bấm ▶ Run trên dashboard).
  2. Với mỗi action node đã sẵn sàng (dependency node trước đã "ok"), hệ thống
     GHI 1 FILE .md vào clients/<project>/_tasks/ chứa skill + nội dung task,
     rồi đánh dấu node "running" — KHÔNG tự chạy gì cả.
  3. Người dùng TỰ mở terminal, tự chạy lệnh `claude "@<file> ..."`, tự theo dõi/duyệt.
     Khi xong, tự sửa `status: pending` → `status: done` trong file rồi lưu.
  4. Background poller (main.py) định kỳ đọc lại các file "running" — thấy
     status: done thì đánh dấu node "ok" và ghi file cho node kế tiếp.

Việc gọi Claude luôn do người dùng chủ động thực hiện trong phiên terminal
của chính họ — hệ thống chỉ chuẩn bị file và theo dõi trạng thái qua file.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, SessionLocal
from models import Workflow, WorkflowRun, Project
from schemas import WorkflowCreate, WorkflowUpdate, WorkflowOut, WorkflowRunOut
from routers.projects import _get_or_create_db_project

router = APIRouter()

TRIGGER_PREFIX = "trigger."
CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/clients"))
WORKFLOW_TASKS_DIR = Path(os.getenv("WORKFLOW_TASKS_DIR", "/workflow_tasks"))
# Repo trên máy thật — API chạy trong container nên path nội bộ (/clients, /workflow_tasks)
# không dùng được ngoài terminal; phải map ngược lại để lệnh copy-paste chạy được.
HOST_PROJECT_ROOT = os.getenv("HOST_PROJECT_ROOT", "").rstrip("/\\")


def _host_relpath(path: Path) -> str:
    """Đường dẫn tương đối so với gốc repo, để dùng với @mention của Claude Code."""
    s = str(path).replace("\\", "/")
    for mount, rel in ((str(WORKFLOW_TASKS_DIR), "workflow_tasks"), (str(CLIENTS_DIR), "clients")):
        m = mount.replace("\\", "/")
        if s.startswith(m):
            return (rel + s[len(m):]).replace("//", "/")
    return s.lstrip("/")


def _task_command(path: Path) -> str:
    """Lệnh copy-paste chạy được trên máy thật.

    Claude Code KHÔNG có flag `-f` (đó là opencode). Prompt truyền dạng positional
    arg; file tham chiếu bằng @mention tương đối so với thư mục đang đứng.
    """
    rel = _host_relpath(path)
    prompt = (
        f"@{rel} Thực hiện task trong file này. "
        "Xong thì ghi tóm tắt vào mục '## Kết quả' và đổi 'status: pending' "
        "thành 'status: done' ngay trong file đó."
    )
    cd = f'cd "{HOST_PROJECT_ROOT}" && ' if HOST_PROJECT_ROOT else ""
    return f'{cd}claude "{prompt}"'


# ── CRUD ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[WorkflowOut])
def list_workflows(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Workflow).order_by(desc(Workflow.id))
    if project_id is not None:
        q = q.filter(Workflow.project_id == project_id)
    return q.all()


@router.post("/", response_model=WorkflowOut)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    project_id = None
    if payload.client_folder:
        proj = _get_or_create_db_project(payload.client_folder, db)
        project_id = proj.id
    wf = Workflow(
        name=payload.name,
        description=payload.description,
        project_id=project_id,
        definition=payload.definition,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(workflow_id: int, payload: WorkflowUpdate, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if payload.name is not None:
        wf.name = payload.name
    if payload.description is not None:
        wf.description = payload.description
    if payload.client_folder is not None:
        # chuỗi rỗng = gỡ gắn project, workflow chạy độc lập
        wf.project_id = _get_or_create_db_project(payload.client_folder, db).id if payload.client_folder else None
    if payload.definition is not None:
        wf.definition = payload.definition
    if payload.is_active is not None:
        wf.is_active = payload.is_active
    db.commit()
    db.refresh(wf)
    return wf


@router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(wf)
    db.commit()
    return {"ok": True}


# ── Graph validation ──────────────────────────────────────────────────────

def _validate_graph(definition: dict) -> List[str]:
    """Trả về danh sách lỗi (rỗng = hợp lệ)."""
    errors: List[str] = []
    nodes = definition.get("nodes", []) or []
    edges = definition.get("edges", []) or []
    node_ids = {n["id"] for n in nodes}

    triggers = [n for n in nodes if str(n.get("type", "")).startswith(TRIGGER_PREFIX)]
    if len(triggers) == 0:
        errors.append("Workflow cần đúng 1 trigger node")
    elif len(triggers) > 1:
        errors.append("Workflow chỉ được có 1 trigger node")

    for e in edges:
        if e.get("source") not in node_ids or e.get("target") not in node_ids:
            errors.append(f"Edge {e.get('id')} tham chiếu node không tồn tại")

    incoming: Dict[str, int] = {n["id"]: 0 for n in nodes}
    adjacency: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src in adjacency and tgt in incoming:
            adjacency[src].append(tgt)
            incoming[tgt] += 1

    trigger_ids = {n["id"] for n in triggers}
    for n in nodes:
        if n["id"] not in trigger_ids and incoming.get(n["id"], 0) == 0:
            errors.append(f"Node '{n.get('data', {}).get('label', n['id'])}' không có kết nối đến")

    # Cycle detection (DFS, 3-màu)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in nodes}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for v in adjacency.get(u, []):
            if color.get(v) == GRAY:
                return True
            if color.get(v) == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    for n in nodes:
        if color[n["id"]] == WHITE and dfs(n["id"]):
            errors.append("Workflow có chu trình (cycle) — không hợp lệ")
            break

    return errors


@router.post("/{workflow_id}/validate")
def validate_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    errors = _validate_graph(wf.definition or {})
    return {"valid": len(errors) == 0, "errors": errors}


def _topological_order(nodes: list, edges: list) -> List[dict]:
    node_by_id = {n["id"]: n for n in nodes}
    incoming: Dict[str, int] = {n["id"]: 0 for n in nodes}
    adjacency: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src in adjacency and tgt in incoming:
            adjacency[src].append(tgt)
            incoming[tgt] += 1

    order: List[dict] = []
    queue = [n["id"] for n in nodes if incoming[n["id"]] == 0]
    seen = set()
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        order.append(node_by_id[nid])
        for nxt in adjacency.get(nid, []):
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
    return order


# ── Task file engine (không gọi Claude/opencode/git — chỉ đọc/ghi file) ───

def _client_tasks_dir(db: Session, wf: Workflow) -> Path:
    """Thư mục ghi file task. Workflow gắn project → clients/<folder>/_tasks;
    workflow độc lập (không gắn project) → workflow_tasks/wf<id>."""
    if wf.project_id:
        proj = db.query(Project).filter(Project.id == wf.project_id).first()
        if proj and proj.client_folder:
            d = CLIENTS_DIR / proj.client_folder / "_tasks"
            d.mkdir(parents=True, exist_ok=True)
            return d
    d = WORKFLOW_TASKS_DIR / f"wf{wf.id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _task_file_path(tasks_dir: Path, workflow_id: int, run_id: int, node_id: str) -> Path:
    return tasks_dir / f"wf{workflow_id}_run{run_id}_{node_id}.md"


def _task_body(node: dict) -> str:
    ntype = node.get("type", "")
    data = node.get("data", {}) or {}
    label = data.get("label") or ntype

    if ntype in ("action.generate_code", "action.code_review", "action.custom"):
        skills = data.get("skill_dirs", []) or []
        skill_block = "\n".join(f"- {s}" for s in skills) or "- (không chọn skill nào)"
        return (
            f"# {label}\n\n"
            f"## Skill áp dụng\n{skill_block}\n\n"
            f"## Yêu cầu\n{data.get('prompt', '') or '(chưa có nội dung)'}\n"
        )

    if ntype == "action.create_mr":
        return (
            f"# {label}\n\n"
            f"## Tạo Merge/Pull Request\n"
            f"- Provider: {str(data.get('provider', '?')).upper()}\n"
            f"- Repo: {data.get('repo', '?')}\n"
            f"- Base branch: {data.get('base_branch', '?')}\n"
            f"- Tiêu đề: {data.get('title_template', '') or '(chưa đặt)'}\n"
            f"- Mô tả: {data.get('description_template', '') or '(chưa có)'}\n\n"
            f"Tự push branch và tạo MR/PR theo thông tin trên (qua web hoặc `git`/`gh`/`glab` CLI bạn tự đăng nhập).\n"
        )

    return f"# {label}\n\n(node type '{ntype}' chưa có template task)\n"


RESULT_HEADING = "## Kết quả"


def _write_task_file(path: Path, workflow_id: int, run_id: int, node: dict) -> None:
    content = (
        "---\n"
        "status: pending\n"
        f"workflow_id: {workflow_id}\n"
        f"run_id: {run_id}\n"
        f"node_id: {node['id']}\n"
        f"node_type: {node.get('type', '')}\n"
        "---\n\n"
        f"{_task_body(node)}\n"
        f"{RESULT_HEADING}\n"
        "<!-- Ghi tóm tắt kết quả vào đây (file đã sửa, MR link, ghi chú...). "
        "Dashboard sẽ hiển thị phần này. -->\n\n"
        "---\n"
        "**Khi hoàn thành**: đổi `status: pending` ở đầu file này thành `status: done` rồi lưu lại.\n"
    )
    path.write_text(content, encoding="utf-8")


_STATUS_RE = re.compile(r"^status:\s*(\w+)", re.MULTILINE)
_RESULT_RE = re.compile(r"^## Kết quả\s*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _read_task_status(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    m = _STATUS_RE.search(path.read_text(encoding="utf-8", errors="replace")[:500])
    return m.group(1) if m else None


def _read_task_result(path: Path) -> str:
    """Đọc phần '## Kết quả' người dùng ghi vào file sau khi chạy xong."""
    if not path.exists():
        return ""
    m = _RESULT_RE.search(path.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return ""
    body = _COMMENT_RE.sub("", m.group(1))
    # bỏ separator '---' và dòng hướng dẫn cuối file
    lines = [ln for ln in body.splitlines() if ln.strip() != "---" and not ln.startswith("**Khi hoàn thành**")]
    return "\n".join(lines).strip()


def _create_run_row(db: Session, workflow_id: int, definition: dict) -> WorkflowRun:
    nodes = definition.get("nodes", []) or []
    run = WorkflowRun(
        workflow_id=workflow_id,
        status="running",
        node_status={n["id"]: "pending" for n in nodes},
        log=[],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def advance_run(db: Session, run: WorkflowRun, trigger_message: Optional[str] = None) -> None:
    """Tiến 1 bước cho tất cả node đã sẵn sàng của 1 run. Gọi lại nhiều lần
    (mỗi lần bấm Run / mỗi vòng poll nền) để tiếp tục tiến trình — idempotent,
    không tự ý gọi Claude/opencode/git, chỉ đọc/ghi file trạng thái."""
    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        return

    nodes = (wf.definition or {}).get("nodes", []) or []
    edges = (wf.definition or {}).get("edges", []) or []
    node_by_id = {n["id"]: n for n in nodes}

    incoming: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("target") in incoming:
            incoming[e["target"]].append(e.get("source"))

    node_status: Dict[str, str] = dict(run.node_status or {})
    log: List[dict] = list(run.log or [])
    changed = False
    tasks_dir: Optional[Path] = None

    for node in _topological_order(nodes, edges):
        nid = node["id"]
        cur = node_status.get(nid, "pending")
        if cur == "ok":
            continue
        if not all(node_status.get(p) == "ok" for p in incoming.get(nid, [])):
            continue  # dependency chưa xong

        is_trigger = str(node.get("type", "")).startswith(TRIGGER_PREFIX)

        if cur == "pending":
            if is_trigger:
                node_status[nid] = "ok"
                msg = trigger_message or f"Trigger '{node.get('data', {}).get('label', nid)}' đã kích hoạt"
                log.append({"node_id": nid, "message": msg, "ts": datetime.utcnow().isoformat()})
                changed = True
                continue
            if tasks_dir is None:
                tasks_dir = _client_tasks_dir(db, wf)
            path = _task_file_path(tasks_dir, wf.id, run.id, nid)
            _write_task_file(path, wf.id, run.id, node)
            node_status[nid] = "running"
            log.append({
                "node_id": nid,
                "message": f"[task] Đã tạo file {_host_relpath(path)} — tự chạy: {_task_command(path)}",
                "ts": datetime.utcnow().isoformat(),
            })
            changed = True

        elif cur == "running":
            if tasks_dir is None:
                tasks_dir = _client_tasks_dir(db, wf)
            path = _task_file_path(tasks_dir, wf.id, run.id, nid)
            status = _read_task_status(path)
            if status == "done":
                node_status[nid] = "ok"
                log.append({"node_id": nid, "message": f"[task] Xác nhận hoàn thành: {path}", "ts": datetime.utcnow().isoformat()})
                changed = True

    if changed:
        run.node_status = node_status
        run.log = log
        db.commit()

    if all(node_status.get(n["id"]) == "ok" for n in nodes) and run.status != "done":
        run.status = "done"
        run.finished_at = datetime.utcnow()
        db.commit()


# ── Task management (xem/đánh dấu các step đang chờ chạy tay) ─────────────

@router.get("/tasks/active")
def list_active_tasks(db: Session = Depends(get_db)) -> List[dict]:
    """Tất cả step đang chờ người dùng tự chạy (node status 'running'), gom từ
    mọi workflow — để dashboard hiển thị 1 chỗ 'việc đang chờ tôi làm'."""
    out: List[dict] = []
    runs = db.query(WorkflowRun).filter(WorkflowRun.status == "running").order_by(desc(WorkflowRun.id)).all()

    for run in runs:
        wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
        if not wf:
            continue
        node_by_id = {n["id"]: n for n in (wf.definition or {}).get("nodes", []) or []}
        try:
            tasks_dir = _client_tasks_dir(db, wf)
        except HTTPException:
            continue

        for node_id, status in (run.node_status or {}).items():
            if status != "running":
                continue
            node = node_by_id.get(node_id, {})
            path = _task_file_path(tasks_dir, wf.id, run.id, node_id)
            out.append({
                "workflow_id": wf.id,
                "workflow_name": wf.name,
                "client_folder": wf.client_folder,
                "run_id": run.id,
                "node_id": node_id,
                "node_label": (node.get("data", {}) or {}).get("label", node_id),
                "node_type": node.get("type", ""),
                "file_path": _host_relpath(path),
                "command": _task_command(path),
                "file_exists": path.exists(),
                "created_at": run.created_at.isoformat() if run.created_at else None,
            })
    return out


@router.get("/runs/{run_id}/steps")
def get_run_steps(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Toàn cảnh 1 lần chạy: từng bước theo đúng thứ tự, trạng thái, thời gian,
    và kết quả người dùng ghi lại trong file .md sau khi chạy."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    definition = wf.definition or {}
    nodes = definition.get("nodes", []) or []
    edges = definition.get("edges", []) or []
    node_status = run.node_status or {}

    # thời điểm bắt đầu/kết thúc mỗi node suy ra từ log
    started: Dict[str, str] = {}
    finished: Dict[str, str] = {}
    for entry in (run.log or []):
        nid, msg, ts = entry.get("node_id"), entry.get("message", ""), entry.get("ts")
        if not nid:
            continue
        if "Đã tạo file" in msg or "đã kích hoạt" in msg:
            started.setdefault(nid, ts)
        if "Xác nhận hoàn thành" in msg or "đã kích hoạt" in msg:
            finished[nid] = ts

    try:
        tasks_dir: Optional[Path] = _client_tasks_dir(db, wf)
    except HTTPException:
        tasks_dir = None

    steps: List[dict] = []
    for order, node in enumerate(_topological_order(nodes, edges), start=1):
        nid = node["id"]
        data = node.get("data", {}) or {}
        is_trigger = str(node.get("type", "")).startswith(TRIGGER_PREFIX)
        path = None if (is_trigger or tasks_dir is None) else _task_file_path(tasks_dir, wf.id, run.id, nid)

        duration_s = None
        if started.get(nid) and finished.get(nid):
            try:
                duration_s = int(
                    (datetime.fromisoformat(finished[nid]) - datetime.fromisoformat(started[nid])).total_seconds()
                )
            except ValueError:
                pass

        steps.append({
            "order": order,
            "node_id": nid,
            "label": data.get("label", nid),
            "node_type": node.get("type", ""),
            "is_trigger": is_trigger,
            "status": node_status.get(nid, "pending"),
            "skills": data.get("skill_dirs", []) or [],
            "file_path": _host_relpath(path) if path else None,
            "command": _task_command(path) if path else None,
            "result": _read_task_result(path) if path else "",
            "started_at": started.get(nid),
            "finished_at": finished.get(nid),
            "duration_s": duration_s,
        })

    total = len(steps)
    done = sum(1 for s in steps if s["status"] == "ok")
    return {
        "run_id": run.id,
        "workflow_id": wf.id,
        "workflow_name": wf.name,
        "client_folder": wf.client_folder,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total_steps": total,
        "done_steps": done,
        "steps": steps,
    }


@router.get("/runs/{run_id}/nodes/{node_id}/file")
def get_task_file(run_id: int, node_id: str, db: Session = Depends(get_db)) -> dict:
    """Đọc nội dung file task để xem ngay trên dashboard (không cần mở editor)."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    path = _task_file_path(_client_tasks_dir(db, wf), wf.id, run.id, node_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File task chưa được tạo")
    return {
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="replace"),
        "status": _read_task_status(path),
    }


@router.post("/runs/{run_id}/nodes/{node_id}/done", response_model=WorkflowRunOut)
def mark_task_done(run_id: int, node_id: str, db: Session = Depends(get_db)):
    """Đánh dấu 1 step đã chạy xong ngay trên dashboard — chỉ ghi `status: done`
    vào file (thay vì bạn phải mở file sửa tay), KHÔNG gọi Claude/opencode."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    path = _task_file_path(_client_tasks_dir(db, wf), wf.id, run.id, node_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File task không tồn tại")

    content = path.read_text(encoding="utf-8", errors="replace")
    path.write_text(_STATUS_RE.sub("status: done", content, count=1), encoding="utf-8")

    advance_run(db, run)
    db.refresh(run)
    return run


@router.post("/{workflow_id}/run", response_model=WorkflowRunOut)
def run_workflow(workflow_id: int, db: Session = Depends(get_db)):
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    errors = _validate_graph(wf.definition or {})
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    run = _create_run_row(db, workflow_id, wf.definition or {})
    advance_run(db, run)
    db.refresh(run)
    return run


@router.post("/runs/{run_id}/refresh", response_model=WorkflowRunOut)
def refresh_run(run_id: int, db: Session = Depends(get_db)):
    """Ép kiểm tra lại ngay các file 'running' thay vì chờ vòng poll nền (5s)."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    advance_run(db, run)
    db.refresh(run)
    return run


def run_workflow_from_trigger(workflow_id: int, trigger_message: str) -> None:
    """Kích hoạt workflow từ 1 trigger THẬT (vd Slack app_mention). Chỉ tạo run
    + ghi file task đầu tiên — người dùng vẫn tự chạy Claude thủ công."""
    db = SessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.is_active == True).first()  # noqa: E712
        if not wf:
            return
        errors = _validate_graph(wf.definition or {})
        if errors:
            return
        run = _create_run_row(db, workflow_id, wf.definition or {})
        advance_run(db, run, trigger_message=trigger_message)
    finally:
        db.close()


def poll_running_workflow_runs() -> None:
    """Gọi định kỳ từ background loop (main.py) — chỉ ĐỌC file status, không
    gọi Claude/opencode/git gì cả."""
    db = SessionLocal()
    try:
        runs = db.query(WorkflowRun).filter(WorkflowRun.status == "running").all()
        for run in runs:
            try:
                advance_run(db, run)
            except HTTPException:
                pass  # workflow thiếu project/client_folder — bỏ qua, chờ user sửa
    finally:
        db.close()


def find_matching_workflows(db: Session, channel_id: str, channel_name: Optional[str], text: str) -> List[Workflow]:
    """Tìm các workflow active có trigger.slack_mention khớp channel (so theo ID
    hoặc tên, không phân biệt hoa/thường, có/không dấu #) và keyword (nếu có)."""
    channel_name_norm = (channel_name or "").lstrip("#").lower()
    text_lower = text.lower()
    matched: List[Workflow] = []

    for wf in db.query(Workflow).filter(Workflow.is_active == True).all():  # noqa: E712
        nodes = (wf.definition or {}).get("nodes", []) or []
        for node in nodes:
            if node.get("type") != "trigger.slack_mention":
                continue
            data = node.get("data", {}) or {}
            configured = str(data.get("channel", "")).lstrip("#").lower()
            if configured not in (channel_id.lower(), channel_name_norm):
                continue
            keyword = (data.get("keyword") or "").strip().lower()
            if keyword and keyword not in text_lower:
                continue
            matched.append(wf)
            break
    return matched


@router.get("/{workflow_id}/runs", response_model=List[WorkflowRunOut])
def list_workflow_runs(workflow_id: int, limit: int = 10, db: Session = Depends(get_db)):
    return (
        db.query(WorkflowRun)
        .filter(WorkflowRun.workflow_id == workflow_id)
        .order_by(desc(WorkflowRun.id))
        .limit(limit)
        .all()
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
def get_workflow_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
