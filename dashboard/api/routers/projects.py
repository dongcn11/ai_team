from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
import io
import os
import re
import shutil
import tomllib
import uuid
import yaml
import zipfile
from datetime import datetime
from pathlib import Path


# ── Profiles loader ──────────────────────────────────────────────────────────
# Đọc profiles từ profiles.yaml (single source of truth). File được mount vào
# /profiles.yaml trong docker-compose. Fallback paths cho dev local.

def _profiles_candidates() -> list[Path]:
    """Build candidate paths for profiles.yaml, defensive against shallow trees."""
    cands: list[Path] = []
    env_path = os.getenv("PROFILES_YAML", "")
    if env_path:
        cands.append(Path(env_path))
    cands.append(Path("/profiles.yaml"))  # docker mount point
    here = Path(__file__).resolve()
    for p in here.parents:  # walk up safely
        cands.append(p / "profiles.yaml")
    return cands


def _load_profiles_yaml() -> dict[str, dict]:
    for cand in _profiles_candidates():
        if cand and cand.exists():
            with open(cand, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("profiles", {}) or {}
    return {}


def _profile_agents() -> dict[str, list[str]]:
    """profile_name → [agent_key list]. Load fresh mỗi lần để pick up yaml changes."""
    profiles = _load_profiles_yaml()
    return {name: cfg.get("agents", []) for name, cfg in profiles.items() if cfg.get("agents")}


DEFAULT_MODEL = {
    "claude":   "",
    "opencode": "opencode/qwen3.5-plus",
}

from system_config import get_system_agents
from database import get_db
from models import Project, ProjectTask, FeatureFile

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


def _write_local_template(folder: Path, slug: str):
    """Tạo settings.local.toml — override cục bộ, KHÔNG commit vào git.

    File chỉ chứa comment mẫu; bỏ comment key cần override cho riêng máy mình.
    Không ghi đè nếu file đã tồn tại.
    """
    target = folder / "settings.local.toml"
    if target.exists():
        return
    template = (
        f"# settings.local.toml — override cục bộ cho project '{slug}'\n"
        "# File này KHÔNG nên commit vào git (đặc thù từng máy / chứa secret).\n"
        "# Bỏ comment các key bên dưới để ghi đè giá trị trong settings.toml.\n"
        "\n"
        "# [output]\n"
        f'# directory = "D:/local/output/{slug}"\n'
        "\n"
        "# [slack]\n"
        '# bot_token = "xoxb-..."\n'
        '# channel = "#ai-team"\n'
        "\n"
        "# [agents]\n"
        '# pm_model = "claude-opus-4-7"\n'
    )
    target.write_text(template, encoding="utf-8")


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
    raw     = _read_toml(folder)
    agents  = get_system_agents(folder / "settings.toml")
    tech    = raw.get("tech_stack", {})
    project = raw.get("project", {})
    name    = project.get("name") or folder.name.replace("_", " ").replace("-", " ").title()
    return {
        "id":          folder.name,
        "name":        name,
        "profile":     project.get("profile", ""),
        "tech_stack":  tech,
        "agents":      agents,
        "agent_count": len(agents),
        "output_dir":  raw.get("output", {}).get("directory", f"./output/{folder.name}"),
    }


# ── Project endpoints ─────────────────────────────────────────────────────────

@router.get("/profiles")
def list_profiles() -> List[dict]:
    """List tất cả profile từ profiles.yaml để dashboard render dropdown."""
    profiles = _load_profiles_yaml()
    result = []
    for name, cfg in profiles.items():
        agents = cfg.get("agents", []) or []
        label = cfg.get("label", name)
        # Hiển thị: "name — agent1+agent2+..."
        agents_display = "+".join(k.upper() if k in ("pm",) else k.capitalize() for k in agents)
        result.append({
            "name": name,
            "label": label,
            "agents": agents,
            "stages_disabled": cfg.get("stages_disabled", []) or [],
            "display": f"{name} — {agents_display}" if agents else name,
        })
    return result


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
    profile_agents = _profile_agents()
    if payload.profile not in profile_agents:
        raise HTTPException(status_code=400, detail=f"Profile không hợp lệ. Chọn: {list(profile_agents)}")
    if payload.default_tool not in DEFAULT_MODEL:
        raise HTTPException(status_code=400, detail="Tool phải là 'claude' hoặc 'opencode'")

    folder = CLIENTS_DIR / slug
    if folder.exists():
        raise HTTPException(status_code=409, detail=f"Project '{slug}' đã tồn tại")

    folder.mkdir(parents=True)

    model = DEFAULT_MODEL[payload.default_tool]
    agents: dict[str, str] = {}
    for key in profile_agents[payload.profile]:
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
    _write_local_template(folder, slug)
    return _folder_to_project(folder)


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    profile: Optional[str] = None
    backend: Optional[str] = None
    frontend: Optional[str] = None
    output_dir: Optional[str] = None


@router.patch("/{folder_name}")
def patch_project(folder_name: str, payload: ProjectPatch) -> dict:
    """Update mutable fields in settings.toml — folder slug stays immutable."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    raw = _read_toml(folder)

    if payload.profile is not None:
        profile_agents = _profile_agents()
        if payload.profile and payload.profile not in profile_agents:
            raise HTTPException(status_code=400,
                                detail=f"Profile không hợp lệ. Chọn: {list(profile_agents)}")
        raw.setdefault("project", {})["profile"] = payload.profile

    if payload.name is not None:
        raw.setdefault("project", {})["name"] = payload.name.strip() or folder.name

    if payload.backend is not None:
        raw.setdefault("tech_stack", {})["backend"] = payload.backend.strip()

    if payload.frontend is not None:
        raw.setdefault("tech_stack", {})["frontend"] = payload.frontend.strip()

    if payload.output_dir is not None:
        raw.setdefault("output", {})["directory"] = payload.output_dir.strip() or f"./clients/{folder_name}/output"

    _write_toml(folder, raw)
    return _folder_to_project(folder)


# ── Delete / Backup ───────────────────────────────────────────────────────────

def _zip_dir(base: Path, zip_buf: io.BytesIO, arcname_prefix: str = ""):
    """Nén toàn bộ base vào zip_buf."""
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(base.rglob("*")):
            if f.is_file():
                arc = Path(arcname_prefix) / f.relative_to(base)
                zf.write(f, arc)


@router.get("/{folder_name}/backup/docs")
def backup_docs(folder_name: str):
    """Tải ZIP chứa docs/ + prd.md của project."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    buf = io.BytesIO()
    docs_dir = folder / "docs"
    prd_file = folder / "prd.md"

    if not docs_dir.exists() and not prd_file.exists():
        raise HTTPException(status_code=404, detail="Chưa có docs để backup")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if docs_dir.exists():
            for f in sorted(docs_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, Path("docs") / f.relative_to(docs_dir))
        if prd_file.exists():
            zf.write(prd_file, "prd.md")

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder_name}_docs_{ts}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{folder_name}/backup/source")
def backup_source(folder_name: str):
    """Tải ZIP chứa toàn bộ source code (output dir) của project."""
    folder   = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    src_dir = _resolve_output_dir(folder)
    if not src_dir.exists():
        raise HTTPException(status_code=404, detail="Chưa có source code để backup")

    buf = io.BytesIO()
    _SKIP = {".pyc", ".pyo", ".cache"}
    _SKIP_D = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".git"}

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src_dir.rglob("*")):
            if not f.is_file():
                continue
            parts = f.relative_to(src_dir).parts
            if any(p in _SKIP_D for p in parts[:-1]):
                continue
            if f.suffix in _SKIP:
                continue
            zf.write(f, Path("source") / f.relative_to(src_dir))

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder_name}_source_{ts}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{folder_name}")
def delete_project(folder_name: str) -> dict:
    """Xóa project (clients/{folder}). Output dir không bị xóa (mounted read-only)."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(folder)
    return {"ok": True, "deleted": folder_name}


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


# Workspace sub-path cho từng coding agent (stage/PM/Scrum/Analyst/Leader dùng docs chung)
_AGENT_WORKSPACE: dict[str, str] = {
    "be1": "backend/be1",
    "be2": "backend/be2",
    "fe1": "frontend/fe1",
    "fe2": "frontend/fe2",
    "fs1": "fullstack/fs1",
    "fs2": "fullstack/fs2",
}


@router.delete("/{folder_name}/settings-agents/{agent_key}")
def remove_settings_agent(
    folder_name: str,
    agent_key: str,
    cleanup: bool = Query(False, description="Xóa workspace code của agent"),
) -> dict:
    folder = CLIENTS_DIR / folder_name
    raw = _read_toml(folder)
    agents = raw.get("agents", {})
    if f"{agent_key}_tool" not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    agents.pop(f"{agent_key}_tool", None)
    agents.pop(f"{agent_key}_model", None)
    raw["agents"] = agents
    _write_toml(folder, raw)

    deleted_workspace: str | None = None
    if cleanup and agent_key in _AGENT_WORKSPACE:
        ws = _resolve_output_dir(folder) / _AGENT_WORKSPACE[agent_key]
        if ws.exists():
            shutil.rmtree(ws)
            deleted_workspace = str(ws)

    return {
        "agents": get_system_agents(folder / "settings.toml"),
        "deleted_workspace": deleted_workspace,
    }


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
    acceptance_criteria: Optional[str] = ""


class FeatureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    acceptance_criteria: Optional[str] = None


def _file_out(f: FeatureFile) -> dict:
    return {
        "id": f.id,
        "filename": f.filename,
        "original_filename": f.original_filename,
        "description": f.description or "",
        "size": f.size or 0,
        "content_type": f.content_type or "",
        "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
    }


def _feature_out(t: ProjectTask) -> dict:
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "status": t.status, "priority": t.priority,
        "acceptance_criteria": t.acceptance_criteria or "",
        "files": [_file_out(f) for f in (t.files or [])],
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
                         description=payload.description, priority=payload.priority,
                         acceptance_criteria=payload.acceptance_criteria or None)
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
    if payload.acceptance_criteria is not None:
        task.acceptance_criteria = payload.acceptance_criteria or None
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
    feature_dir = _feature_files_dir(folder, task_id)
    if feature_dir.exists():
        shutil.rmtree(feature_dir, ignore_errors=True)
    db.delete(task)
    db.commit()
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return {"ok": True}


# ── Feature file attachments ──────────────────────────────────────────────────

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB per file


def _feature_files_dir(folder: Path, task_id: int) -> Path:
    return folder / "feature_files" / str(task_id)


def _safe_filename(name: str) -> str:
    """Strip path components and keep a reasonable, filesystem-safe name."""
    base = Path(name).name  # drop any directory part
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-") or "file"
    return base[:120]


@router.post("/{folder_name}/features/{task_id}/files")
async def upload_feature_file(
    folder_name: str,
    task_id: int,
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")

    feature_dir = _feature_files_dir(folder, task_id)
    feature_dir.mkdir(parents=True, exist_ok=True)

    safe_name   = _safe_filename(file.filename or "file")
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    target      = feature_dir / stored_name

    total = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_FILE_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File quá lớn (giới hạn {_MAX_FILE_BYTES // (1024*1024)} MB)")
            out.write(chunk)

    row = FeatureFile(
        task_id=task_id,
        filename=stored_name,
        original_filename=file.filename or safe_name,
        description=description.strip() or None,
        size=total,
        content_type=file.content_type or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _file_out(row)


@router.get("/{folder_name}/features/{task_id}/files/{file_id}/download")
def download_feature_file(folder_name: str, task_id: int, file_id: int,
                          db: Session = Depends(get_db)):
    folder = CLIENTS_DIR / folder_name
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    path = _feature_files_dir(folder, task_id) / row.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=row.original_filename,
                        media_type=row.content_type or "application/octet-stream")


class FeatureFileUpdate(BaseModel):
    description: Optional[str] = None


@router.put("/{folder_name}/features/{task_id}/files/{file_id}")
def update_feature_file(folder_name: str, task_id: int, file_id: int,
                        payload: FeatureFileUpdate,
                        db: Session = Depends(get_db)) -> dict:
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if payload.description is not None:
        row.description = payload.description.strip() or None
    db.commit()
    db.refresh(row)
    return _file_out(row)


@router.delete("/{folder_name}/features/{task_id}/files/{file_id}")
def delete_feature_file(folder_name: str, task_id: int, file_id: int,
                        db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    path = _feature_files_dir(folder, task_id) / row.filename
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(row)
    db.commit()
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
