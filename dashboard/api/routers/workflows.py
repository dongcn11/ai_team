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

Workflow gắn project vs MẪU (template):
  - Workflow CÓ project → chạy được: task trong project đó chọn nó rồi bấm ▶.
  - Workflow KHÔNG gắn project → chỉ là MẪU: không chạy, không nhận trigger.
    Dùng `POST /{id}/clone?client_folder=...` để nhân bản mẫu vào 1 project rồi
    chạy bản sao đó. (Trước đây mẫu vẫn chạy được và ghi file vào workflow_tasks/
    — lối đó bỏ rồi, file task luôn nằm trong clients/<project>/_tasks.)

Rẽ nhánh (node `logic.condition`):
  - Node điều kiện có 2 cổng ra: `sourceHandle` = "true" / "false".
  - mode "manual": ghi file task như node thường, người dùng điền `decision: true|false`
    (hoặc bấm nút Đúng/Sai trên dashboard) — hệ thống không tự suy đoán.
  - mode "auto": so khớp mục "## Kết quả" của các node ngay trước theo
    contains / not_contains / equals / regex / is_empty, không sinh file task.
  - Các node chỉ nằm trên nhánh không được chọn sẽ mang trạng thái "skipped":
    không sinh file task, và run vẫn kết thúc "done" khi mọi node đã ok/skipped.

Việc gọi Claude luôn do người dùng chủ động thực hiện trong phiên terminal
của chính họ — hệ thống chỉ chuẩn bị file và theo dõi trạng thái qua file.
"""

import copy
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import get_db, SessionLocal
from models import Workflow, WorkflowRun, WorkflowStepJob, Project, ProjectTask
from system_config import SKILLS_DIR, get_system_agents
from schemas import WorkflowCreate, WorkflowUpdate, WorkflowOut, WorkflowRunOut
from routers.projects import _get_or_create_db_project

router = APIRouter()

TRIGGER_PREFIX = "trigger."
CONDITION_TYPE = "logic.condition"
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


# Chính sách README: pipeline không dùng Claude Code. Agent nào khai tool="claude"
# thì coi như không hợp lệ ở đây — node để trống agent là đã chạy bằng Claude rồi.
BLOCKED_AGENT_TOOLS = {"claude"}


def _agent_cfg(agent_key: Optional[str]) -> Optional[dict]:
    """Cau hinh agent pipeline (tool + model) theo key, doc tu config/settings.toml.

    Node khong chon agent -> None -> buoc chay bang Claude headless (hoac tay).
    Agent nao dat tool = "claude" bi bo qua: chinh sach chan Claude o lan pipeline
    (xem README), va node muon dung Claude thi cu de trong la duoc."""
    if not agent_key:
        return None
    for a in get_system_agents():
        if a["key"] == agent_key:
            if a.get("tool") in BLOCKED_AGENT_TOOLS:
                return None
            return a
    return None


def _node_agent(node: dict) -> Optional[dict]:
    return _agent_cfg(((node.get("data") or {}).get("agent_key")) or None)


def _task_prompt(path: Path, is_condition: bool = False, tool: str = "claude") -> str:
    """Prompt cho 1 bước — dùng chung cho lệnh copy-paste và job chạy headless,
    để chạy tay và chạy tự động cho ra đúng một kết quả."""
    rel = _host_relpath(path)
    # opencode nhận file qua cờ -f, không hiểu cú pháp @mention của Claude Code
    ref = "" if tool == "opencode" else f"@{rel} "
    prompt = (
        f"{ref}Thực hiện task trong file này. "
        "Xong thì ghi tóm tắt vào mục '## Kết quả' và đổi 'status: pending' "
        "thành 'status: done' ngay trong file đó."
    )
    if is_condition:
        prompt += (
            " Đây là node điều kiện: kết luận rồi điền 'decision: true' hoặc "
            "'decision: false' ở đầu file để workflow biết đi tiếp nhánh nào."
        )
    return prompt


def _task_command(path: Path, is_condition: bool = False, agent: Optional[dict] = None) -> str:
    """Lệnh copy-paste chạy được trên máy thật — đúng engine mà bước này dùng.

    Claude Code KHÔNG có flag `-f` (đó là opencode). Prompt truyền dạng positional
    arg; file tham chiếu bằng @mention tương đối so với thư mục đang đứng.
    Node có chọn agent pipeline thì lệnh là `opencode run ... -f <file>` cho khớp
    với thứ worker sẽ chạy, và với cách ai_team/runner.py gọi opencode.
    """
    cd = f'cd "{HOST_PROJECT_ROOT}" && ' if HOST_PROJECT_ROOT else ""
    if agent:
        prompt = _task_prompt(path, is_condition, tool="opencode")
        return (f'{cd}opencode run "{prompt}" --model {agent["model"]} '
                f'-f {_host_relpath(path)}')
    return f'{cd}claude "{_task_prompt(path, is_condition)}"'


def _enqueue_step_job(db: Session, wf: Workflow, run: WorkflowRun, node: dict,
                      path: Path, is_condition: bool) -> None:
    """Đưa 1 bước vào hàng đợi cho worker trên host chạy bằng `claude -p`.

    Chỉ gọi khi workflow bật `auto_run`. Không tự chạy gì ở đây — API trong
    container không có CLI lẫn phiên đăng nhập; nó chỉ ghi job.

    Chống trùng: 1 (run, node) chỉ xếp hàng ĐÚNG MỘT LẦN, kể cả khi job trước đã
    fail. Vòng poll nền gọi advance_run mỗi 5s, nên nếu chỉ chặn job "còn sống"
    thì một bước lỗi sẽ bị xếp lại → worker chạy lại → lỗi tiếp, thành vòng lặp
    vô tận đốt quota. Chạy lại phải do người bấm: nút ↻ (endpoint /retry)."""
    existing = (db.query(WorkflowStepJob)
                  .filter(WorkflowStepJob.run_id == run.id,
                          WorkflowStepJob.node_id == node["id"])
                  .first())
    if existing:
        return
    agent = _node_agent(node)
    tool = "opencode" if agent else "claude"
    db.add(WorkflowStepJob(
        run_id=run.id,
        node_id=node["id"],
        node_label=(node.get("data", {}) or {}).get("label") or node["id"],
        client_folder=wf.client_folder,
        file_path=_host_relpath(path),
        prompt=_task_prompt(path, is_condition, tool=tool),
        tool=tool,
        model=agent["model"] if agent else None,
        status="queued",
    ))


# ── CRUD ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[WorkflowOut])
def list_workflows(project_id: Optional[int] = None, client_folder: Optional[str] = None,
                   db: Session = Depends(get_db)):
    """Danh sách workflow. `client_folder` = slug thư mục project (dashboard dùng
    slug chứ không giữ Project.id) — lọc ra đúng danh sách workflow của project đó."""
    q = db.query(Workflow).order_by(desc(Workflow.id))
    if project_id is not None:
        q = q.filter(Workflow.project_id == project_id)
    if client_folder is not None:
        proj = db.query(Project).filter(Project.client_folder == client_folder).first()
        if not proj:
            return []
        q = q.filter(Workflow.project_id == proj.id)
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
        # chuỗi rỗng = gỡ gắn project → workflow trở thành MẪU (không chạy được)
        wf.project_id = _get_or_create_db_project(payload.client_folder, db).id if payload.client_folder else None
    if payload.auto_run is not None:
        wf.auto_run = payload.auto_run
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
    # Task đang chọn workflow này quay về "chưa chọn" thay vì gãy khoá ngoại.
    (db.query(ProjectTask)
       .filter(ProjectTask.workflow_id == workflow_id)
       .update({"workflow_id": None}, synchronize_session=False))
    db.delete(wf)
    db.commit()
    return {"ok": True}


@router.post("/{workflow_id}/clone", response_model=WorkflowOut)
def clone_workflow(workflow_id: int, client_folder: str, name: Optional[str] = None,
                   db: Session = Depends(get_db)):
    """Nhân bản 1 workflow (thường là mẫu) vào danh sách workflow của 1 project.

    Bản sao là dữ liệu độc lập hoàn toàn: sửa/xoá bản sao không đụng tới mẫu, và
    ngược lại — mẫu chỉ là điểm khởi đầu, không phải liên kết sống."""
    src = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not client_folder:
        raise HTTPException(status_code=400, detail="Cần chọn project để nhân bản vào")

    proj = _get_or_create_db_project(client_folder, db)
    wf = Workflow(
        name=(name or src.name).strip() or src.name,
        description=src.description,
        project_id=proj.id,
        definition=copy.deepcopy(src.definition or {"nodes": [], "edges": []}),
        is_active=True,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


# ── Graph validation ──────────────────────────────────────────────────────

def _branch_of_edge(edge: dict) -> Optional[bool]:
    """Nhánh mà 1 edge đại diện khi xuất phát từ node điều kiện.
    True = nhánh Đúng, False = nhánh Sai, None = không xác định."""
    handle = (edge.get("sourceHandle") or "").strip().lower()
    if handle in ("true", "yes", "then"):
        return True
    if handle in ("false", "no", "else"):
        return False
    return None


def _validate_graph(definition: dict, require_trigger: bool = False) -> List[str]:
    """Trả về danh sách lỗi (rỗng = hợp lệ).

    Trigger node KHÔNG bắt buộc. Workflow gắn vào task được kích hoạt bằng nút
    ▶ Chạy ngay trên task đó, nên node `trigger.*` chỉ cần khi muốn Slack tự
    khởi chạy (require_trigger=True). Không có trigger thì mọi node không có
    đường vào chính là điểm bắt đầu — engine ghi file task cho chúng ngay vòng
    đầu, y như khi trigger vừa khớp.
    """
    errors: List[str] = []
    nodes = definition.get("nodes", []) or []
    edges = definition.get("edges", []) or []
    node_ids = {n["id"] for n in nodes}

    if not nodes:
        return ["Workflow chưa có node nào"]

    triggers = [n for n in nodes if str(n.get("type", "")).startswith(TRIGGER_PREFIX)]
    if len(triggers) > 1:
        errors.append("Workflow chỉ được có 1 trigger node")
    elif not triggers and require_trigger:
        errors.append("Workflow cần 1 trigger node thì Slack mới kích hoạt được")

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

    # Node không có đường vào = điểm bắt đầu, hoàn toàn hợp lệ khi chạy thủ công.
    # Nhưng khi ĐÃ có trigger thì luồng phải xuất phát từ trigger; node đứng lẻ
    # gần như luôn là quên nối dây (engine sẽ chạy nó song song với trigger).
    if triggers:
        trigger_ids = {n["id"] for n in triggers}
        for n in nodes:
            if n["id"] not in trigger_ids and incoming.get(n["id"], 0) == 0:
                label = n.get("data", {}).get("label", n["id"])
                errors.append(f"Node '{label}' chưa nối vào luồng — kéo 1 đường từ trigger tới nó")

    # Node điều kiện: phải rẽ được ít nhất 1 nhánh, và mỗi nhánh phải rõ true/false
    for n in nodes:
        if n.get("type") != CONDITION_TYPE:
            continue
        label = n.get("data", {}).get("label", n["id"])
        outs = [e for e in edges if e.get("source") == n["id"]]
        if not outs:
            errors.append(f"Node điều kiện '{label}' chưa nối nhánh nào (cần nhánh Đúng và/hoặc Sai)")
        for e in outs:
            if _branch_of_edge(e) is None:
                errors.append(f"Node điều kiện '{label}' có nhánh không xác định — nối lại từ handle Đúng/Sai")

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

def _client_tasks_dir(db: Session, wf: Workflow, run: Optional[WorkflowRun] = None) -> Path:
    """Thư mục ghi file task: luôn là clients/<folder>/_tasks của project.

    Workflow không gắn project là MẪU — không chạy được, nên tới đây là bất
    thường (vd project bị xoá sau khi run đã tạo). Ném lỗi rõ ràng; poller đã
    bắt HTTPException nên vòng lặp nền không chết.

    Run kích hoạt từ 1 task cụ thể có thư mục con `task<id>/` riêng — nhiều
    task cùng chạy 1 workflow thì file không trộn vào nhau. Run cũ
    (task_id = NULL) giữ nguyên đường dẫn như trước."""
    task_id = getattr(run, "task_id", None) if run is not None else None
    base = None
    if wf.project_id:
        proj = db.query(Project).filter(Project.id == wf.project_id).first()
        if proj and proj.client_folder:
            base = CLIENTS_DIR / proj.client_folder / "_tasks"
    if base is None:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow '{wf.name}' chưa gắn project nên không chạy được — "
                   f"đây là mẫu, hãy nhân bản nó vào 1 project trước.",
        )
    d = base / f"task{task_id}" if task_id else base
    d.mkdir(parents=True, exist_ok=True)
    return d


def _task_context(db: Session, run: WorkflowRun) -> str:
    """Mô tả task đã kích hoạt run — chèn vào đầu mỗi file task để người
    chạy Claude có đủ ngữ cảnh mà không phải mở lại dashboard."""
    task_id = getattr(run, "task_id", None)
    if not task_id:
        return ""
    t = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
    if not t:
        return ""
    lines = [f"## Task: {t.name}", ""]
    if t.description:
        lines += [t.description.strip(), ""]
    if t.acceptance_criteria:
        lines += ["**Tiêu chí nghiệm thu**", "", t.acceptance_criteria.strip(), ""]
    lines.append(f"_(Task #{t.id} · ưu tiên {t.priority} · trạng thái {t.status})_")
    return "\n".join(lines) + "\n\n"


def _task_file_path(tasks_dir: Path, workflow_id: int, run_id: int, node_id: str) -> Path:
    return tasks_dir / f"wf{workflow_id}_run{run_id}_{node_id}.md"


# Nhung bao nhieu ky tu skill vao 1 file task truoc khi chuyen sang chi ghi duong dan.
# File task con phai chua mo ta cong viec; nhoi ca chuc nghin dong skill vao chi to
# loang prompt va dot token moi buoc.
_SKILL_INLINE_BUDGET = 12000

_HEADING_RE = re.compile(r"^(#{1,3}) ", re.MULTILINE)


def _demote_headings(md: str) -> str:
    """Ha cap heading cua noi dung skill xuong ####.

    File task dung '## Ket qua' lam moc de doc ket qua (xem _RESULT_RE). Skill nao
    tinh co co heading '## Ket qua' se khien dashboard doc nham khoi do."""
    return _HEADING_RE.sub(lambda m: "#" * (len(m.group(1)) + 2) + " ", md)


def _skill_section(skill_dirs: List[str]) -> str:
    """Noi dung skill THAT, khong chi cai ten.

    Truoc day cho nay chi liet ke ten thu muc - nguoi/agent chay buoc khong he
    biet quy uoc trong skills/<dir>/*.md, trong khi pipeline `ai_team/` lai nhet
    han noi dung vao prompt (xem ai_team/skill_loader.py). Cung chu 'skill' ma 2
    nghia khac nhau. Gio nhung thang noi dung, phan vuot han muc thi ghi duong
    dan de tu doc.

    `shared` luon duoc them vao - giong skill_loader: moi vai tro deu doc no."""
    dirs = [d for d in dict.fromkeys(skill_dirs or []) if d]
    if not dirs:
        return "## Skill áp dụng\n- (không chọn skill nào)\n"
    if (SKILLS_DIR / "shared").is_dir() and "shared" not in dirs:
        dirs.insert(0, "shared")

    inlined: List[str] = []
    deferred: List[str] = []
    used = 0
    for d in dirs:
        folder = SKILLS_DIR / d
        files = sorted(folder.glob("*.md")) if folder.is_dir() else []
        if not files:
            deferred.append(f"- `skills/{d}/` — không tìm thấy file .md nào")
            continue
        for f in files:
            rel = f"skills/{d}/{f.name}"
            try:
                text = f.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as e:
                deferred.append(f"- `{rel}` — không đọc được ({e})")
                continue
            if used + len(text) <= _SKILL_INLINE_BUDGET:
                inlined.append(f"### {rel}\n\n{_demote_headings(text)}")
                used += len(text)
            else:
                deferred.append(f"- Đọc thêm: `{rel}`")

    out = ["## Skill áp dụng",
           f"Vai trò: {', '.join(dirs)}. Đọc kỹ phần dưới trước khi làm — đây là quy ước "
           "bắt buộc của vai trò này, không phải gợi ý.", ""]
    out.extend(inlined)
    if deferred:
        out.append("### Skill chưa nhúng (tự mở file mà đọc)")
        out.extend(deferred)
        out.append("")
    return "\n".join(out) + "\n"


def _effective_skills(node: dict) -> List[str]:
    """Skill thực sự áp cho 1 bước.

    Chọn agent = nhận luôn bộ skill của vai trò đó (giống pipeline), phần tick tay
    chỉ là skill THÊM. Trước đây 2 ô độc lập nên chọn PM Agent mà tick skill leader
    vẫn được — agent đọc quy ước của vai trò khác, vô lý."""
    data = node.get("data", {}) or {}
    agent = _node_agent(node)
    base = list(agent.get("skill_dirs") or []) if agent else []
    return list(dict.fromkeys(base + list(data.get("skill_dirs") or [])))


def _task_body(node: dict) -> str:
    ntype = node.get("type", "")
    data = node.get("data", {}) or {}
    label = data.get("label") or ntype

    if ntype in ("action.generate_code", "action.code_review", "action.custom"):
        agent = _node_agent(node)
        who = (f"{agent['name']} — {agent['tool']} · {agent['model']}" if agent
               else "Claude headless (hoặc bạn chạy tay)")
        skills = _effective_skills(node)
        return (
            f"# {label}\n\n"
            f"> Người thực thi: {who}\n\n"
            f"## Yêu cầu\n{data.get('prompt', '') or '(chưa có nội dung)'}\n\n"
            f"{_skill_section(skills)}"
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

    if ntype == CONDITION_TYPE:
        return (
            f"# {label}\n\n"
            f"## Điều kiện cần kiểm tra\n{data.get('expression', '') or '(chưa mô tả điều kiện)'}\n\n"
            f"- Nhánh ĐÚNG: {data.get('true_label', '') or 'Đúng'}\n"
            f"- Nhánh SAI: {data.get('false_label', '') or 'Sai'}\n\n"
            "Kiểm tra rồi ghi kết luận vào `decision:` ở đầu file (`true` hoặc `false`).\n"
            "Workflow sẽ chỉ chạy tiếp nhánh tương ứng, nhánh còn lại bị bỏ qua.\n"
        )

    return f"# {label}\n\n(node type '{ntype}' chưa có template task)\n"


RESULT_HEADING = "## Kết quả"


def _write_task_file(path: Path, workflow_id: int, run_id: int, node: dict,
                     context: str = "", task_id: Optional[int] = None) -> None:
    is_condition = node.get("type") == CONDITION_TYPE
    content = (
        "---\n"
        "status: pending\n"
        + ("decision:\n" if is_condition else "")
        + f"workflow_id: {workflow_id}\n"
        f"run_id: {run_id}\n"
        + (f"task_id: {task_id}\n" if task_id else "")
        + f"node_id: {node['id']}\n"
        f"node_type: {node.get('type', '')}\n"
        "---\n\n"
        f"{context}"
        f"{_task_body(node)}\n"
        f"{RESULT_HEADING}\n"
        "<!-- Ghi tóm tắt kết quả vào đây (file đã sửa, MR link, ghi chú...). "
        "Dashboard sẽ hiển thị phần này. -->\n\n"
        "---\n"
        "**Khi hoàn thành**: đổi `status: pending` ở đầu file này thành `status: done` rồi lưu lại.\n"
        + ("**Node điều kiện**: nhớ điền `decision: true` hoặc `decision: false` ở đầu file, "
           "nếu không workflow sẽ đứng chờ.\n" if is_condition else "")
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


_DECISION_RE = re.compile(r"^decision:\s*(\S+)", re.MULTILINE)
_DECISION_LINE_RE = re.compile(r"^decision:.*$", re.MULTILINE)

_TRUE_WORDS = {"true", "yes", "y", "1", "dung", "đúng", "ok", "pass"}
_FALSE_WORDS = {"false", "no", "n", "0", "sai", "fail"}


def _read_task_decision(path: Path) -> Optional[bool]:
    """Đọc `decision: true/false` người dùng điền trong file của node điều kiện."""
    if not path.exists():
        return None
    m = _DECISION_RE.search(path.read_text(encoding="utf-8", errors="replace")[:500])
    if not m:
        return None
    val = m.group(1).strip().lower()
    if val in _TRUE_WORDS:
        return True
    if val in _FALSE_WORDS:
        return False
    return None


def _auto_decision(node: dict, upstream_text: str) -> Optional[bool]:
    """Đánh giá điều kiện tự động dựa trên phần '## Kết quả' của các node trước."""
    data = node.get("data", {}) or {}
    operator = (data.get("operator") or "contains").strip()
    value = data.get("value") or ""
    haystack = upstream_text or ""

    if operator in ("contains", "not_contains"):
        if not value:
            return None
        hit = value.lower() in haystack.lower()
        return hit if operator == "contains" else not hit
    if operator == "equals":
        return haystack.strip().lower() == value.strip().lower()
    if operator == "regex":
        if not value:
            return None
        try:
            return re.search(value, haystack, re.IGNORECASE | re.MULTILINE) is not None
        except re.error:
            return None
    if operator == "is_empty":
        return haystack.strip() == ""
    return None


def _create_run_row(db: Session, workflow_id: int, definition: dict,
                    task_id: Optional[int] = None) -> WorkflowRun:
    nodes = definition.get("nodes", []) or []
    run = WorkflowRun(
        workflow_id=workflow_id,
        task_id=task_id,
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

    incoming_edges: Dict[str, List[dict]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("target") in incoming_edges:
            incoming_edges[e["target"]].append(e)

    node_status: Dict[str, str] = dict(run.node_status or {})
    log: List[dict] = list(run.log or [])
    changed = False
    tasks_dir_holder: List[Optional[Path]] = [None]
    context_holder: List[Optional[str]] = [None]
    branch_cache: Dict[str, Optional[bool]] = {}

    def tasks_dir() -> Path:
        if tasks_dir_holder[0] is None:
            tasks_dir_holder[0] = _client_tasks_dir(db, wf, run)
        return tasks_dir_holder[0]

    def task_context() -> str:
        if context_holder[0] is None:
            context_holder[0] = _task_context(db, run)
        return context_holder[0]

    def upstream_result(nid: str) -> str:
        """Gộp phần '## Kết quả' của các node ngay trước — dữ liệu để đánh giá điều kiện."""
        parts = []
        for e in incoming_edges.get(nid, []):
            src = e.get("source")
            if not src or str(node_by_id.get(src, {}).get("type", "")).startswith(TRIGGER_PREFIX):
                continue
            parts.append(_read_task_result(_task_file_path(tasks_dir(), wf.id, run.id, src)))
        return "\n".join(p for p in parts if p)

    def branch_of(nid: str) -> Optional[bool]:
        """Nhánh mà node điều kiện đã chọn (None = chưa quyết định)."""
        if nid in branch_cache:
            return branch_cache[nid]
        node = node_by_id.get(nid, {})
        data = node.get("data", {}) or {}
        if (data.get("mode") or "manual") == "auto":
            result = _auto_decision(node, upstream_result(nid))
        else:
            result = _read_task_decision(_task_file_path(tasks_dir(), wf.id, run.id, nid))
        branch_cache[nid] = result
        return result

    def edge_active(e: dict) -> Optional[bool]:
        """Edge có được đi qua không: True/False, None = chưa biết (node nguồn chưa xong)."""
        src = e.get("source")
        src_status = node_status.get(src, "pending")
        if src_status == "skipped":
            return False
        if src_status != "ok":
            return None
        if node_by_id.get(src, {}).get("type") != CONDITION_TYPE:
            return True
        chosen = branch_of(src)
        if chosen is None:
            return None
        return _branch_of_edge(e) == chosen

    for node in _topological_order(nodes, edges):
        nid = node["id"]
        cur = node_status.get(nid, "pending")
        if cur in ("ok", "skipped"):
            continue

        parents = incoming_edges.get(nid, [])
        if parents:
            states = [edge_active(e) for e in parents]
            if any(s is None for s in states):
                continue  # dependency chưa xong
            if not any(states):
                # mọi nhánh dẫn tới node này đều không được chọn → bỏ qua cả cụm
                node_status[nid] = "skipped"
                log.append({
                    "node_id": nid,
                    "message": f"[nhánh] Bỏ qua '{node.get('data', {}).get('label', nid)}' — điều kiện không dẫn tới nhánh này",
                    "ts": datetime.utcnow().isoformat(),
                })
                changed = True
                continue

        is_trigger = str(node.get("type", "")).startswith(TRIGGER_PREFIX)
        is_condition = node.get("type") == CONDITION_TYPE

        if cur == "pending":
            if is_trigger:
                node_status[nid] = "ok"
                msg = trigger_message or f"Trigger '{node.get('data', {}).get('label', nid)}' đã kích hoạt"
                log.append({"node_id": nid, "message": msg, "ts": datetime.utcnow().isoformat()})
                changed = True
                continue

            if is_condition and ((node.get("data", {}) or {}).get("mode") or "manual") == "auto":
                # điều kiện tự động: đánh giá ngay trên kết quả của node trước, không cần file
                branch_cache.pop(nid, None)
                chosen = branch_of(nid)
                if chosen is None:
                    continue  # chưa đủ dữ liệu để kết luận — chờ vòng sau
                node_status[nid] = "ok"
                log.append({
                    "node_id": nid,
                    "message": f"[điều kiện] {node.get('data', {}).get('label', nid)} → nhánh {'ĐÚNG' if chosen else 'SAI'}",
                    "ts": datetime.utcnow().isoformat(),
                })
                changed = True
                continue

            path = _task_file_path(tasks_dir(), wf.id, run.id, nid)
            _write_task_file(path, wf.id, run.id, node,
                             context=task_context(), task_id=run.task_id)
            node_status[nid] = "running"
            log.append({
                "node_id": nid,
                "message": f"[task] Đã tạo file {_host_relpath(path)} — tự chạy: {_task_command(path, is_condition, _node_agent(node))}",
                "ts": datetime.utcnow().isoformat(),
            })
            if wf.auto_run:
                _enqueue_step_job(db, wf, run, node, path, is_condition)
                _ag = _node_agent(node)
                log.append({
                    "node_id": nid,
                    "message": ("[auto] Đã xếp hàng cho worker chạy bằng "
                                + (f"opencode ({_ag['name']} · {_ag['model']})" if _ag else "Claude headless")),
                    "ts": datetime.utcnow().isoformat(),
                })
            changed = True

        elif cur == "running":
            path = _task_file_path(tasks_dir(), wf.id, run.id, nid)
            status = _read_task_status(path)
            if status != "done":
                # Bật auto_run khi bước đã đang chờ sẵn: file task tạo từ trước nên
                # nhánh "pending → running" ở trên không chạy lại nữa. Không xếp hàng
                # ở đây thì công tắc chỉ có tác dụng từ run sau — người dùng bật xong
                # ngồi đợi mãi không thấy gì chạy.
                if wf.auto_run and not is_trigger:
                    _enqueue_step_job(db, wf, run, node, path, is_condition)
                continue
            if is_condition:
                branch_cache.pop(nid, None)
                chosen = branch_of(nid)
                if chosen is None:
                    continue  # đã done nhưng chưa điền decision → vẫn chờ
                node_status[nid] = "ok"
                log.append({
                    "node_id": nid,
                    "message": f"[điều kiện] {node.get('data', {}).get('label', nid)} → nhánh {'ĐÚNG' if chosen else 'SAI'}",
                    "ts": datetime.utcnow().isoformat(),
                })
            else:
                node_status[nid] = "ok"
                log.append({"node_id": nid, "message": f"[task] Xác nhận hoàn thành: {path}", "ts": datetime.utcnow().isoformat()})
            changed = True

    if changed:
        run.node_status = node_status
        run.log = log
        db.commit()

    if all(node_status.get(n["id"]) in ("ok", "skipped") for n in nodes) and run.status != "done":
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
            tasks_dir = _client_tasks_dir(db, wf, run)
        except HTTPException:
            continue
        task = run.task

        for node_id, status in (run.node_status or {}).items():
            if status != "running":
                continue
            node = node_by_id.get(node_id, {})
            path = _task_file_path(tasks_dir, wf.id, run.id, node_id)
            out.append({
                "workflow_id": wf.id,
                "workflow_name": wf.name,
                "client_folder": wf.client_folder,
                "task_id": task.id if task else None,
                "task_name": task.name if task else None,
                "run_id": run.id,
                "node_id": node_id,
                "node_label": (node.get("data", {}) or {}).get("label", node_id),
                "node_type": node.get("type", ""),
                "file_path": _host_relpath(path),
                "command": _task_command(path, node.get("type") == CONDITION_TYPE, _node_agent(node)),
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
    branch: Dict[str, str] = {}
    for entry in (run.log or []):
        nid, msg, ts = entry.get("node_id"), entry.get("message", ""), entry.get("ts")
        if not nid:
            continue
        if "Đã tạo file" in msg or "đã kích hoạt" in msg or "[điều kiện]" in msg or "[nhánh]" in msg:
            started.setdefault(nid, ts)
        if ("Xác nhận hoàn thành" in msg or "đã kích hoạt" in msg
                or "[điều kiện]" in msg or "[nhánh]" in msg):
            finished[nid] = ts
        if "[điều kiện]" in msg:
            branch[nid] = "true" if "ĐÚNG" in msg else "false"

    try:
        tasks_dir: Optional[Path] = _client_tasks_dir(db, wf, run)
    except HTTPException:
        tasks_dir = None

    steps: List[dict] = []
    for order, node in enumerate(_topological_order(nodes, edges), start=1):
        nid = node["id"]
        data = node.get("data", {}) or {}
        is_trigger = str(node.get("type", "")).startswith(TRIGGER_PREFIX)
        # điều kiện tự động không sinh file task — không có lệnh để chạy tay
        auto_condition = node.get("type") == CONDITION_TYPE and (data.get("mode") or "manual") == "auto"
        path = None if (is_trigger or auto_condition or tasks_dir is None) else _task_file_path(tasks_dir, wf.id, run.id, nid)

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
            "is_condition": node.get("type") == CONDITION_TYPE,
            "branch": branch.get(nid),
            "status": node_status.get(nid, "pending"),
            "skills": _effective_skills(node),
            "file_path": _host_relpath(path) if path else None,
            "command": _task_command(path, node.get("type") == CONDITION_TYPE, _node_agent(node)) if path else None,
            "agent": (lambda a: {"key": a["key"], "name": a["name"], "tool": a["tool"], "model": a["model"]}
                      if a else None)(_node_agent(node)),
            "result": _read_task_result(path) if path else "",
            "started_at": started.get(nid),
            "finished_at": finished.get(nid),
            "duration_s": duration_s,
        })

    total = len(steps)
    done = sum(1 for s in steps if s["status"] in ("ok", "skipped"))
    return {
        "run_id": run.id,
        "workflow_id": wf.id,
        "workflow_name": wf.name,
        "client_folder": wf.client_folder,
        "task_id": run.task_id,
        "task_name": run.task.name if run.task else None,
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

    path = _task_file_path(_client_tasks_dir(db, wf, run), wf.id, run.id, node_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File task chưa được tạo")
    return {
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="replace"),
        "status": _read_task_status(path),
    }


@router.post("/runs/{run_id}/nodes/{node_id}/done", response_model=WorkflowRunOut)
def mark_task_done(run_id: int, node_id: str, decision: Optional[str] = None, db: Session = Depends(get_db)):
    """Đánh dấu 1 step đã chạy xong ngay trên dashboard — chỉ ghi `status: done`
    vào file (thay vì bạn phải mở file sửa tay), KHÔNG gọi Claude/opencode.

    Với node điều kiện, truyền `?decision=true|false` để chọn luôn nhánh đi tiếp."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    path = _task_file_path(_client_tasks_dir(db, wf, run), wf.id, run.id, node_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File task không tồn tại")

    content = path.read_text(encoding="utf-8", errors="replace")
    content = _STATUS_RE.sub("status: done", content, count=1)
    if decision is not None:
        val = decision.strip().lower()
        if val not in _TRUE_WORDS | _FALSE_WORDS:
            raise HTTPException(status_code=400, detail="decision phải là true hoặc false")
        norm = "true" if val in _TRUE_WORDS else "false"
        content = (_DECISION_LINE_RE.sub(f"decision: {norm}", content, count=1)
                   if _DECISION_LINE_RE.search(content)
                   else content.replace("status: done", f"status: done\ndecision: {norm}", 1))
    path.write_text(content, encoding="utf-8")

    advance_run(db, run)
    db.refresh(run)
    return run


@router.post("/{workflow_id}/run", response_model=WorkflowRunOut)
def run_workflow(workflow_id: int, task_id: Optional[int] = None,
                 db: Session = Depends(get_db)):
    """Chạy workflow. `task_id` = task (feature) của project đang kích hoạt —
    file task ghi vào thư mục riêng của task đó và mang theo mô tả task.

    Nếu task đó đã có 1 run đang chạy với chính workflow này thì trả lại run
    cũ thay vì tạo trùng — bấm ▶ nhiều lần không sinh ra nhiều luồng song song."""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if task_id is not None:
        task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if wf.project_id and task.project_id != wf.project_id:
            raise HTTPException(status_code=400,
                                detail="Workflow không thuộc project của task này")
        existing = (db.query(WorkflowRun)
                      .filter(WorkflowRun.workflow_id == workflow_id,
                              WorkflowRun.task_id == task_id,
                              WorkflowRun.status == "running")
                      .order_by(desc(WorkflowRun.id)).first())
        if existing:
            advance_run(db, existing)
            db.refresh(existing)
            return existing

    if wf.project_id is None:
        raise HTTPException(
            status_code=400,
            detail="Đây là MẪU (chưa gắn project) nên không chạy trực tiếp — "
                   "bấm 'Dùng mẫu' để nhân bản vào 1 project rồi chạy bản sao.",
        )

    errors = _validate_graph(wf.definition or {})
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    run = _create_run_row(db, workflow_id, wf.definition or {}, task_id=task_id)
    advance_run(db, run)
    db.refresh(run)
    return run


@router.post("/runs/{run_id}/refresh", response_model=WorkflowRunOut)
def refresh_run(run_id: int, db: Session = Depends(get_db)):
    """Ép kiểm tra lại ngay các file 'running' thay vì chờ vòng poll nền (5s)."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # Run đã kết thúc/huỷ thì không đẩy tiếp — nếu không, bấm "Kiểm tra ngay"
    # trên 1 run đã huỷ sẽ ghi lại file task và hồi sinh nó.
    if run.status == "running":
        advance_run(db, run)
        db.refresh(run)
    return run


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    """Huỷ 1 lần chạy đang dở.

    Hệ thống không tự chạy gì nên "huỷ" = ngừng chờ: run chuyển sang `cancelled`,
    các bước đang chờ người dùng chạy tay bị đánh dấu bỏ qua, poller nền không
    ngó tới nữa. File task đã ghi vẫn giữ nguyên trên đĩa (có thể đang chứa kết
    quả của bạn) — muốn chạy lại thì bấm ▶ để tạo run mới."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "running":
        raise HTTPException(status_code=400,
                            detail=f"Run #{run_id} đã ở trạng thái '{run.status}' — không huỷ được nữa.")

    node_status = dict(run.node_status or {})
    for nid, st in node_status.items():
        if st == "running":          # bước đang chờ người dùng → không chờ nữa
            node_status[nid] = "skipped"
    run.node_status = node_status
    run.status = "cancelled"
    run.finished_at = datetime.utcnow()
    # job headless còn trong hàng đợi phải huỷ theo, không worker vẫn nhặt lên chạy
    (db.query(WorkflowStepJob)
       .filter(WorkflowStepJob.run_id == run.id,
               WorkflowStepJob.status.in_(("queued", "running")))
       .update({"status": "canceled", "finished_at": datetime.utcnow()},
               synchronize_session=False))
    log = list(run.log or [])
    log.append({"node_id": "", "message": "⛔ Người dùng đã huỷ lần chạy này",
                "ts": datetime.utcnow().isoformat()})
    run.log = log
    db.commit()
    db.refresh(run)
    return run


def run_workflow_from_trigger(workflow_id: int, trigger_message: str) -> None:
    """Kích hoạt workflow từ 1 trigger THẬT (vd Slack app_mention). Chỉ tạo run
    + ghi file task đầu tiên — người dùng vẫn tự chạy Claude thủ công."""
    db = SessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.is_active == True).first()  # noqa: E712
        if not wf or wf.project_id is None:
            return  # mẫu không nhận trigger — không biết ghi file task vào đâu
        errors = _validate_graph(wf.definition or {}, require_trigger=True)
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
    hoặc tên, không phân biệt hoa/thường, có/không dấu #) và keyword (nếu có).

    Mẫu (project_id NULL) bị loại ngay từ query — mẫu không chạy được nên báo
    "đã khớp" chỉ làm người dùng tưởng có run được tạo."""
    channel_name_norm = (channel_name or "").lstrip("#").lower()
    text_lower = text.lower()
    matched: List[Workflow] = []

    for wf in (db.query(Workflow)
                 .filter(Workflow.is_active == True,           # noqa: E712
                         Workflow.project_id.isnot(None)).all()):
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
