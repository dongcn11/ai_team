from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import os
import tomllib
from pathlib import Path

from system_config import get_system_agents

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


def _folder_to_project(folder: Path) -> dict:
    raw = _read_toml(folder)
    agents = get_system_agents(folder / "settings.toml")
    tech = raw.get("tech_stack", {})
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


# ── Docs (output files) ───────────────────────────────────────────────────────

@router.get("/{folder_name}/docs")
def list_docs(folder_name: str) -> List[dict]:
    output_dir = OUTPUT_DIR / folder_name
    if not output_dir.exists():
        return []
    files = []
    for f in sorted(output_dir.rglob("*")):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(output_dir).parts
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts[:-1]):
            continue
        if f.suffix.lower() in _SKIP_EXTS:
            continue
        files.append({
            "path":     str(f.relative_to(output_dir)).replace("\\", "/"),
            "name":     f.name,
            "size":     f.stat().st_size,
            "modified": f.stat().st_mtime,
        })
    return files


@router.get("/{folder_name}/docs/content")
def get_doc_content(folder_name: str, path: str = "") -> dict:
    output_dir = (OUTPUT_DIR / folder_name).resolve()
    target = (output_dir / path).resolve()
    if not str(target).startswith(str(output_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        content = f"[Binary file: {target.name}]"
    return {"path": path, "content": content}
