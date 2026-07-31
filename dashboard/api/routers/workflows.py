"""
Workflows — CRUD + hàng đợi chạy
=================================
Workflow do user tự vẽ. Mọi lần lưu đều đi qua
`ai_team.workflow.graph.validate()`; graph vi phạm invariant (node Claude bị
auto-trigger kích trực tiếp) bị **từ chối lưu**, kèm danh sách node sai để canvas
tô đỏ. Không lưu được thì không chạy được — chốt chặn nằm ở tầng dữ liệu.

Executor chạy trên host (nơi có CLI), poll `POST /claim` giống worker.py. API
chỉ giữ state; nó không gọi model.

Fail-closed: nếu không import được validator, mọi endpoint ghi trả 503. Container
thiếu mount `ai_team` thì hệ thống dừng, không âm thầm nhận graph chưa kiểm.
"""

import json
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import Workflow, WorkflowApproval, WorkflowRun
from schemas import (
    WorkflowApprove,
    WorkflowClaimOut,
    WorkflowCreate,
    WorkflowGraphIn,
    WorkflowRunComplete,
    WorkflowRunOut,
    WorkflowRunStart,
    WorkflowSummary,
    WorkflowUpdate,
    WorkflowValidateOut,
)

router = APIRouter()

# Run kẹt `running` quá lâu (executor crash) → tự nhả để không nghẽn hàng đợi.
STUCK_AFTER = timedelta(hours=2)
ACTIVE_STATUSES = ("queued", "running")


# ── Validator (fail-closed) ───────────────────────────────────────────────────

def _graph_mod():
    """Import validator. Không có → 503, tuyệt đối không bỏ qua bước validate."""
    try:
        from ai_team.workflow import graph as g   # noqa: PLC0415 — cố ý import muộn
        return g
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Không import được ai_team.workflow.graph nên không validate được "
                f"workflow — từ chối ghi ({e}). Kiểm tra mount `../ai_team:/app/ai_team` "
                "trong docker-compose.yml."
            ),
        )


def _validated_graph(raw: WorkflowGraphIn | dict, name: str = "") -> dict:
    """parse + validate. Lỗi → 400 kèm errors/warnings/bad_nodes."""
    g = _graph_mod()
    payload = raw if isinstance(raw, dict) else raw.model_dump()
    payload = dict(payload)
    payload.setdefault("name", name)
    if not payload.get("name"):
        payload["name"] = name or "untitled"

    try:
        parsed = g.parse(payload)
    except g.GraphError as e:
        raise HTTPException(status_code=400, detail={
            "errors": [str(e)], "warnings": [], "bad_nodes": [],
        })

    res = g.validate(parsed)
    if not res.ok:
        raise HTTPException(status_code=400, detail={
            "errors": res.errors, "warnings": res.warnings, "bad_nodes": res.bad_nodes,
        })
    return parsed.to_dict()


def _loads(raw: Optional[str], fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except ValueError:
        return fallback


def _run_out(run: WorkflowRun) -> WorkflowRunOut:
    state = _loads(run.state_json, {})
    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        trigger_type=run.trigger_type,
        status=run.status,
        payload=_loads(run.payload_json, {}),
        state=state,
        outputs=_loads(run.outputs_json, {}),
        waiting_on=sorted(nid for nid, st in state.items() if st == "waiting"),
        approvals=[
            {"node_id": a.node_id, "approved_by": a.approved_by,
             "approved_at": a.approved_at.isoformat() if a.approved_at else None,
             "note": a.note}
            for a in run.approvals
        ],
        log=run.log,
        error=run.error,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _summary(wf: Workflow) -> WorkflowSummary:
    raw = _loads(wf.graph_json, {"nodes": []})
    nodes = raw.get("nodes", []) or []
    return WorkflowSummary(
        id=wf.id,
        name=wf.name,
        description=wf.description,
        enabled=bool(wf.enabled),
        node_count=len(nodes),
        claude_nodes=sorted(n.get("id", "") for n in nodes if n.get("runtime") == "claude"),
        created_at=wf.created_at,
    )


def _get_wf(db: Session, wf_id: int) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == wf_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow không tồn tại")
    return wf


def _get_run(db: Session, run_id: int) -> WorkflowRun:
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run không tồn tại")
    return run


# ── Literal routes — phải khai TRƯỚC /{wf_id} để không bị parse thành int ─────

@router.post("/validate", response_model=WorkflowValidateOut)
def validate_graph(payload: WorkflowGraphIn) -> WorkflowValidateOut:
    """Canvas gọi lúc vẽ để tô đỏ node sai. Không lưu gì."""
    g = _graph_mod()
    body = payload.model_dump()
    body.setdefault("name", "draft")
    try:
        parsed = g.parse(body)
    except g.GraphError as e:
        return WorkflowValidateOut(ok=False, errors=[str(e)])
    res = g.validate(parsed)
    return WorkflowValidateOut(
        ok=res.ok, errors=res.errors, warnings=res.warnings, bad_nodes=res.bad_nodes
    )


@router.post("/claim", response_model=Optional[WorkflowClaimOut])
def claim_run(db: Session = Depends(get_db)):
    """Executor trên host gọi đây. Trả run `queued` cũ nhất và đánh dấu `running`.

    Trả null nếu hàng đợi rỗng HOẶC đang có run khác chạy — tuần tự 1 run/lần,
    khớp với ràng buộc node Claude phải tuần tự và tránh xung đột git."""
    cutoff = datetime.utcnow() - STUCK_AFTER
    stuck = db.query(WorkflowRun).filter(
        WorkflowRun.status == "running",
        WorkflowRun.started_at < cutoff,
    ).all()
    for s in stuck:
        s.status = "failed"
        s.error = "Timeout: executor không báo complete sau 2 giờ (có thể crash)"
        s.finished_at = datetime.utcnow()
    if stuck:
        db.commit()

    if db.query(WorkflowRun).filter(WorkflowRun.status == "running").first():
        return None

    q = db.query(WorkflowRun).filter(WorkflowRun.status == "queued").order_by(WorkflowRun.id)
    try:
        run = q.with_for_update(skip_locked=True).first()
    except Exception:
        run = q.first()          # sqlite/dev fallback
    if not run:
        return None

    wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
    if not wf:
        run.status = "failed"
        run.error = "Workflow đã bị xoá"
        run.finished_at = datetime.utcnow()
        db.commit()
        return None

    run.status = "running"
    if run.started_at is None:
        run.started_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    return WorkflowClaimOut(
        run_id=run.id,
        workflow_id=wf.id,
        workflow_name=wf.name,
        trigger_type=run.trigger_type,
        graph=_loads(wf.graph_json, {}),
        state=_loads(run.state_json, {}),
        payload=_loads(run.payload_json, {}),
        approvals={a.node_id: a.approved_at.timestamp() for a in run.approvals if a.approved_at},
        started_at=run.started_at,
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)) -> WorkflowRunOut:
    return _run_out(_get_run(db, run_id))


@router.post("/runs/{run_id}/approve", response_model=WorkflowRunOut)
def approve_gate(run_id: int, payload: WorkflowApprove,
                 db: Session = Depends(get_db)) -> WorkflowRunOut:
    """Bấm duyệt một `manual_gate` (hoặc `manual_trigger`) → ghi bằng chứng có
    người, rồi đưa run về `queued` để executor chạy tiếp.

    Đây là nơi duy nhất sinh ra quyền chạy node Claude. `approved_at` là mốc thời
    gian executor dùng để kiểm tra cú bấm còn tươi."""
    run = _get_run(db, run_id)
    if run.status in ("done", "canceled"):
        raise HTTPException(status_code=400, detail=f"Run đã {run.status}, không duyệt được")

    wf = _get_wf(db, run.workflow_id)
    g = _graph_mod()
    try:
        parsed = g.parse(_loads(wf.graph_json, {}))
    except g.GraphError as e:
        raise HTTPException(status_code=500, detail=f"Graph đã lưu không parse được: {e}")

    node = parsed.get(payload.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{payload.node_id}' không có trong workflow")
    if node.type not in g.HUMAN_CHECKPOINTS:
        raise HTTPException(
            status_code=400,
            detail=(f"Node '{payload.node_id}' là '{node.type}', không phải checkpoint. "
                    f"Chỉ duyệt được: {sorted(g.HUMAN_CHECKPOINTS)}"),
        )

    existing = next((a for a in run.approvals if a.node_id == payload.node_id), None)
    if existing:
        existing.approved_at = datetime.utcnow()      # bấm lại → làm tươi mốc
        existing.approved_by = payload.approved_by or existing.approved_by
        existing.note = payload.note or existing.note
    else:
        db.add(WorkflowApproval(
            run_id=run.id, node_id=payload.node_id,
            approved_by=payload.approved_by, note=payload.note,
        ))

    state = _loads(run.state_json, {})
    if state.get(payload.node_id) == "waiting":
        state[payload.node_id] = "pending"           # executor sẽ thấy approval và cho qua
    run.state_json = json.dumps(state)
    run.status = "queued"
    run.error = None
    run.finished_at = None
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.post("/runs/{run_id}/complete", response_model=WorkflowRunOut)
def complete_run(run_id: int, payload: WorkflowRunComplete,
                 db: Session = Depends(get_db)) -> WorkflowRunOut:
    """Executor báo kết quả một lượt `advance()`."""
    if payload.status not in ("waiting", "done", "failed"):
        raise HTTPException(status_code=400,
                            detail="status phải là 'waiting' / 'done' / 'failed'")
    run = _get_run(db, run_id)
    run.status = payload.status
    run.state_json = json.dumps(payload.state or {})
    run.outputs_json = json.dumps(payload.outputs or {})
    run.log = payload.log
    run.error = (payload.error or "")[:2000] or None
    run.finished_at = datetime.utcnow() if payload.status in ("done", "failed") else None
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunOut)
def cancel_run(run_id: int, db: Session = Depends(get_db)) -> WorkflowRunOut:
    run = _get_run(db, run_id)
    if run.status not in ACTIVE_STATUSES and run.status != "waiting":
        raise HTTPException(status_code=400, detail=f"Run đang '{run.status}', không huỷ được")
    run.status = "canceled"
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    return _run_out(run)


# ── Workflow CRUD ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[WorkflowSummary])
def list_workflows(db: Session = Depends(get_db)) -> List[WorkflowSummary]:
    return [_summary(w) for w in db.query(Workflow).order_by(Workflow.name).all()]


@router.post("", response_model=WorkflowSummary, status_code=201)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)) -> WorkflowSummary:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name không được rỗng")
    if db.query(Workflow).filter(Workflow.name == name).first():
        raise HTTPException(status_code=409, detail=f"Workflow '{name}' đã tồn tại")

    graph = _validated_graph(payload.graph, name)
    wf = Workflow(
        name=name,
        description=payload.description,
        graph_json=json.dumps(graph),
        enabled=payload.enabled,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return _summary(wf)


@router.get("/{wf_id}")
def get_workflow(wf_id: int, db: Session = Depends(get_db)) -> dict:
    wf = _get_wf(db, wf_id)
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "graph": _loads(wf.graph_json, {}),
        "enabled": bool(wf.enabled),
        "created_at": wf.created_at,
        "updated_at": wf.updated_at,
    }


@router.put("/{wf_id}", response_model=WorkflowSummary)
def update_workflow(wf_id: int, payload: WorkflowUpdate,
                    db: Session = Depends(get_db)) -> WorkflowSummary:
    wf = _get_wf(db, wf_id)

    if payload.name is not None:
        new_name = payload.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="name không được rỗng")
        clash = db.query(Workflow).filter(
            Workflow.name == new_name, Workflow.id != wf_id
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Workflow '{new_name}' đã tồn tại")
        wf.name = new_name

    if payload.description is not None:
        wf.description = payload.description
    if payload.enabled is not None:
        wf.enabled = payload.enabled
    if payload.graph is not None:
        wf.graph_json = json.dumps(_validated_graph(payload.graph, wf.name))

    db.commit()
    db.refresh(wf)
    return _summary(wf)


@router.delete("/{wf_id}")
def delete_workflow(wf_id: int, db: Session = Depends(get_db)) -> dict:
    wf = _get_wf(db, wf_id)
    active = db.query(WorkflowRun).filter(
        WorkflowRun.workflow_id == wf_id,
        WorkflowRun.status.in_(ACTIVE_STATUSES),
    ).count()
    if active:
        raise HTTPException(status_code=409,
                            detail=f"Còn {active} run đang chạy/chờ — huỷ trước khi xoá")
    db.delete(wf)
    db.commit()
    return {"deleted": wf_id}


# ── Runs của một workflow ─────────────────────────────────────────────────────

@router.get("/{wf_id}/runs", response_model=List[WorkflowRunOut])
def list_runs(wf_id: int, limit: int = 20,
              db: Session = Depends(get_db)) -> List[WorkflowRunOut]:
    _get_wf(db, wf_id)
    runs = (db.query(WorkflowRun)
              .filter(WorkflowRun.workflow_id == wf_id)
              .order_by(desc(WorkflowRun.id)).limit(limit).all())
    return [_run_out(r) for r in runs]


@router.post("/{wf_id}/runs", response_model=WorkflowRunOut, status_code=201)
def start_run(wf_id: int, payload: WorkflowRunStart,
              db: Session = Depends(get_db)) -> WorkflowRunOut:
    """Xếp một run vào hàng đợi.

    `trigger_type` phải khớp một trigger node có thật trong graph — không cho
    khai khống. Nếu là `manual_trigger`, ghi luôn một approval cho node đó: cú
    bấm Start chính là bằng chứng có người, và đó là thứ mở quyền chạy node Claude.
    """
    wf = _get_wf(db, wf_id)
    if not wf.enabled:
        raise HTTPException(status_code=400, detail="Workflow đang disabled")

    g = _graph_mod()
    try:
        parsed = g.parse(_loads(wf.graph_json, {}))
    except g.GraphError as e:
        raise HTTPException(status_code=500, detail=f"Graph đã lưu không parse được: {e}")

    trigger_nodes = [n for n in parsed.triggers() if n.type == payload.trigger_type]
    if not trigger_nodes:
        available = sorted({n.type for n in parsed.triggers()})
        raise HTTPException(
            status_code=400,
            detail=(f"Workflow không có trigger node kiểu '{payload.trigger_type}'. "
                    f"Có: {available}"),
        )

    run = WorkflowRun(
        workflow_id=wf.id,
        trigger_type=payload.trigger_type,
        status="queued",
        payload_json=json.dumps(payload.payload or {}),
        state_json=json.dumps(g.initial_state(parsed)),
    )
    db.add(run)
    db.flush()          # cần run.id để gắn approval

    if payload.trigger_type in g.MANUAL_TRIGGERS:
        for node in trigger_nodes:
            db.add(WorkflowApproval(
                run_id=run.id, node_id=node.id,
                approved_by=str(payload.payload.get("started_by") or "dashboard"),
                note="Cú bấm Start",
            ))

    db.commit()
    db.refresh(run)
    return _run_out(run)
