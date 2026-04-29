from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
import os
import re
import tomllib
from pathlib import Path

PROFILE_AGENTS: dict[str, list[str]] = {
    "fullstack":      ["pm", "scrum", "analyst", "be1", "be2", "fe1", "fe2", "leader"],
    "dual_fullstack": ["pm", "scrum", "analyst", "fs1", "fs2", "leader"],
    "backend_only":   ["pm", "scrum", "analyst", "be1", "be2", "leader"],
}
DEFAULT_MODEL = {
    "claude":   "",
    "opencode": "opencode/qwen3.5-plus",
}

from system_config import get_system_agents
from database import get_db
from models import Project, ProjectTask

CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/clients"))
OUTPUT_DIR  = Path(os.getenv("OUTPUT_DIR",  "/output"))

VALID_AGENT_KEYS = ["pm", "scrum", "analyst", "be1", "be2", "fe1", "fe2", "fs1", "fs2", "leader"]

_SKIP_EXTS = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico",
              ".woff", ".woff2", ".ttf", ".eot", ".map", ".bin", ".lock", ".cache"}
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
              "node_modules", ".venv", "venv", ".git"}

router = APIRouter()


# ── TOML helpers ──────────────────────────────────────────────────────────────

def _read_toml(folder: Path) -> dict:
    f = folder / "settings.toml"
    if not f.exists():
        return {}
    with open(f, "rb") as fh:
        return tomllib.load(fh)


def _write_toml(folder: Path, raw: dict):
    lines = []
    section_order = ["agents", "slack", "output", "timeouts", "tech_stack", "project"]
    ordered = [s for s in section_order if s in raw] + [s for s in raw if s not in section_order]
    for section in ordered:
        lines.append(f"[{section}]")
        for k, v in raw[section].items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, int):
                lines.append(f"{k} = {v}")
            else:
                lines.append(f'{k} = "{v}"')
        lines.append("")
    (folder / "settings.toml").write_text("\n".join(lines), encoding="utf-8")


def _resolve_dir(folder: Path, key: str, fallback: Path) -> Path:
    """Resolve a directory from settings.toml. Relative paths → relative to project folder."""
    raw     = _read_toml(folder)
    dir_str = raw.get("output", {}).get(key, "")
    if not dir_str:
        return fallback
    p = Path(dir_str)
    if p.is_absolute():
        return fallback  # absolute Windows paths not accessible in Docker
    return (folder / p).resolve()


def _resolve_output_dir(folder: Path) -> Path:
    return _resolve_dir(folder, "directory", OUTPUT_DIR / folder.name)


def _resolve_docs_dir(folder: Path) -> Path:
    code_dir = _resolve_output_dir(folder)
    return _resolve_dir(folder, "docs_directory", code_dir / "docs")


def _folder_to_project(folder: Path) -> dict:
    raw    = _read_toml(folder)
    agents = get_system_agents(folder / "settings.toml")
    tech   = raw.get("tech_stack", {})
    return {
        "id":          folder.name,
        "name":        folder.name.replace("_", " ").replace("-", " ").title(),
        "tech_stack":  tech,
        "agents":      agents,
        "agent_count": len(agents),
        "output_dir":  raw.get("output", {}).get("directory", f"./output/{folder.name}"),
    }


# ── Project endpoints ─────────────────────────────────────────────────────────

@router.get("/")
def list_projects() -> List[dict]:
    if not CLIENTS_DIR.exists():
        return []
    return [
        _folder_to_project(f)
        for f in sorted(CLIENTS_DIR.iterdir())
        if f.is_dir() and (f / "settings.toml").exists()
    ]


@router.get("/{folder_name}")
def get_project(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return _folder_to_project(folder)


class ProjectCreate(BaseModel):
    folder_name: str
    profile: str = "fullstack"
    default_tool: str = "claude"
    backend: str = ""
    frontend: str = ""


@router.post("/")
def create_project(payload: ProjectCreate) -> dict:
    slug = re.sub(r"[^a-z0-9_-]", "_", payload.folder_name.strip().lower())
    if not slug:
        raise HTTPException(status_code=400, detail="Tên project không hợp lệ")
    if payload.profile not in PROFILE_AGENTS:
        raise HTTPException(status_code=400, detail=f"Profile không hợp lệ. Chọn: {list(PROFILE_AGENTS)}")
    if payload.default_tool not in DEFAULT_MODEL:
        raise HTTPException(status_code=400, detail="Tool phải là 'claude' hoặc 'opencode'")

    folder = CLIENTS_DIR / slug
    if folder.exists():
        raise HTTPException(status_code=409, detail=f"Project '{slug}' đã tồn tại")

    folder.mkdir(parents=True)

    model = DEFAULT_MODEL[payload.default_tool]
    agents: dict[str, str] = {}
    for key in PROFILE_AGENTS[payload.profile]:
        agents[f"{key}_tool"]  = payload.default_tool
        agents[f"{key}_model"] = model

    raw: dict = {
        "project": {"name": slug.replace("_", " ").replace("-", " ").title(), "profile": payload.profile},
        "agents":  agents,
        "output":  {"directory": f"./clients/{slug}/output"},
        "timeouts": {"claude_code": 600, "opencode": 600},
        "tech_stack": {
            "backend":  payload.backend  or "Python FastAPI + SQLModel + SQLite",
            "frontend": payload.frontend or "React + TypeScript + Vite + TailwindCSS",
        },
    }
    _write_toml(folder, raw)
    return _folder_to_project(folder)


# ── Agent management (settings.toml) ─────────────────────────────────────────

@router.get("/{folder_name}/settings-agents")
def list_settings_agents(folder_name: str) -> List[dict]:
    folder = CLIENTS_DIR / folder_name
    return get_system_agents(folder / "settings.toml")


class AgentFsPayload(BaseModel):
    key: str
    tool: str = "opencode"
    model: str = "opencode/qwen3.5-plus"


@router.post("/{folder_name}/settings-agents")
def add_settings_agent(folder_name: str, payload: AgentFsPayload) -> List[dict]:
    if payload.key not in VALID_AGENT_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid key. Valid: {VALID_AGENT_KEYS}")
    folder = CLIENTS_DIR / folder_name
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Client folder not found")
    raw = _read_toml(folder)
    agents = raw.setdefault("agents", {})
    if f"{payload.key}_tool" in agents:
        raise HTTPException(status_code=409, detail=f"Agent '{payload.key}' already exists")
    agents[f"{payload.key}_tool"]  = payload.tool
    agents[f"{payload.key}_model"] = payload.model
    _write_toml(folder, raw)
    return get_system_agents(folder / "settings.toml")


@router.delete("/{folder_name}/settings-agents/{agent_key}")
def remove_settings_agent(folder_name: str, agent_key: str) -> List[dict]:
    folder = CLIENTS_DIR / folder_name
    raw = _read_toml(folder)
    agents = raw.get("agents", {})
    if f"{agent_key}_tool" not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    agents.pop(f"{agent_key}_tool", None)
    agents.pop(f"{agent_key}_model", None)
    raw["agents"] = agents
    _write_toml(folder, raw)
    return get_system_agents(folder / "settings.toml")


# ── PRD ───────────────────────────────────────────────────────────────────────

class PrdPayload(BaseModel):
    content: str


@router.get("/{folder_name}/prd")
def get_prd(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    prd = folder / "prd.md"
    if not prd.exists():
        return {"exists": False, "content": ""}
    return {"exists": True, "content": prd.read_text(encoding="utf-8")}


@router.put("/{folder_name}/prd")
def save_prd(folder_name: str, payload: PrdPayload) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    (folder / "prd.md").write_text(payload.content, encoding="utf-8")
    return {"ok": True}


@router.delete("/{folder_name}/prd")
def delete_prd(folder_name: str) -> dict:
    prd = CLIENTS_DIR / folder_name / "prd.md"
    if not prd.exists():
        raise HTTPException(status_code=404, detail="prd.md not found")
    prd.unlink()
    return {"ok": True}


# ── Features (ideas → ProjectTask + prd.md) ───────────────────────────────────

def _get_or_create_db_project(folder_name: str, db: Session) -> Project:
    proj = db.query(Project).filter(Project.client_folder == folder_name).first()
    if not proj:
        name = folder_name.replace("_", " ").replace("-", " ").title()
        proj = Project(name=name, client_folder=folder_name, status="active")
        db.add(proj)
        db.commit()
        db.refresh(proj)
    return proj


def _sync_features_to_prd(folder: Path, features: list):
    """Ghi/cập nhật section ## Features trong prd.md."""
    prd_path = folder / "prd.md"
    existing = prd_path.read_text(encoding="utf-8") if prd_path.exists() else "# PRD\n\n## Tổng quan\n\n"

    # Build features table
    rows = ["", "## Features", "",
            "| # | Tên | Mô tả | Priority | Status |",
            "|---|-----|-------|----------|--------|"]
    for f in features:
        icon = "✅" if f["status"] == "done" else "📋"
        desc = (f["description"] or "").replace("|", "/").replace("\n", " ").strip()
        rows.append(f"| {f['id']} | {f['name']} | {desc} | {f['priority']} | {icon} {f['status']} |")
    rows.append("")
    block = "\n".join(rows)

    if "## Features" in existing:
        existing = re.sub(r'\n## Features\b[\s\S]*?(?=\n## |\Z)', block, existing)
    else:
        existing = existing.rstrip("\n") + "\n" + block

    prd_path.write_text(existing, encoding="utf-8")


class FeatureCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    priority: str = "medium"


class FeatureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None


def _feature_out(t: ProjectTask) -> dict:
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "status": t.status, "priority": t.priority,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _all_features(proj_id: int, db: Session) -> list:
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == proj_id)\
               .order_by(ProjectTask.created_at).all()
    return [_feature_out(t) for t in tasks]


@router.get("/{folder_name}/features")
def list_features(folder_name: str, db: Session = Depends(get_db)) -> List[dict]:
    proj = _get_or_create_db_project(folder_name, db)
    return _all_features(proj.id, db)


@router.post("/{folder_name}/features")
def create_feature(folder_name: str, payload: FeatureCreate,
                   db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = ProjectTask(project_id=proj.id, name=payload.name,
                         description=payload.description, priority=payload.priority)
    db.add(task)
    db.commit()
    db.refresh(task)
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return _feature_out(task)


@router.put("/{folder_name}/features/{task_id}")
def update_feature(folder_name: str, task_id: int, payload: FeatureUpdate,
                   db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")
    if payload.name        is not None: task.name        = payload.name
    if payload.description is not None: task.description = payload.description
    if payload.status      is not None: task.status      = payload.status
    if payload.priority    is not None: task.priority    = payload.priority
    db.commit()
    db.refresh(task)
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return _feature_out(task)


@router.delete("/{folder_name}/features/{task_id}")
def delete_feature(folder_name: str, task_id: int, db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")
    db.delete(task)
    db.commit()
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return {"ok": True}


# ── Docs (output files) ───────────────────────────────────────────────────────

def _scan_dir(base: Path, source: str) -> List[dict]:
    if not base.exists():
        return []
    files = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(base).parts
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts[:-1]):
            continue
        if f.suffix.lower() in _SKIP_EXTS:
            continue
        files.append({
            "path":     str(f.relative_to(base)).replace("\\", "/"),
            "name":     f.name,
            "size":     f.stat().st_size,
            "modified": f.stat().st_mtime,
            "source":   source,
        })
    return files


@router.get("/{folder_name}/docs")
def list_docs(folder_name: str) -> List[dict]:
    folder   = CLIENTS_DIR / folder_name
    code_dir = _resolve_output_dir(folder)
    docs_dir = _resolve_docs_dir(folder)

    # Nếu docs_dir trùng với code_dir/docs thì chỉ scan code_dir (backward compat)
    if docs_dir == code_dir / "docs" and not docs_dir.exists():
        return _scan_dir(code_dir, "code")

    return _scan_dir(docs_dir, "docs") + _scan_dir(code_dir, "code")


@router.get("/{folder_name}/docs/content")
def get_doc_content(folder_name: str, path: str = "", source: str = "code") -> dict:
    folder   = CLIENTS_DIR / folder_name
    base_dir = _resolve_docs_dir(folder) if source == "docs" else _resolve_output_dir(folder)
    target   = (base_dir / path).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        content = f"[Binary file: {target.name}]"
    return {"path": path, "content": content}
