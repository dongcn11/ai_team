from fastapi import APIRouter, HTTPException
from typing import List, Optional
import os
import tomllib
from pathlib import Path
from datetime import datetime

from system_config import get_system_agents

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", str(_PROJECT_ROOT / "clients")))

router = APIRouter()


def _read_settings(folder: Path) -> dict:
    settings_file = folder / "settings.toml"
    if not settings_file.exists():
        return {}
    with open(settings_file, "rb") as f:
        return tomllib.load(f)


def _folder_to_project(folder: Path) -> dict:
    raw = _read_settings(folder)
    agents = get_system_agents(folder / "settings.toml")
    tech = raw.get("tech_stack", {})
    return {
        "id": folder.name,
        "name": folder.name.replace("_", " ").replace("-", " ").title(),
        "tech_stack": tech,
        "agents": agents,
        "agent_count": len(agents),
        "output_dir": raw.get("output", {}).get("directory", f"./output/{folder.name}"),
    }


@router.get("/")
def list_projects() -> List[dict]:
    if not CLIENTS_DIR.exists():
        return []
    result = []
    for folder in sorted(CLIENTS_DIR.iterdir()):
        if folder.is_dir() and (folder / "settings.toml").exists():
            result.append(_folder_to_project(folder))
    return result


@router.get("/{folder_name}")
def get_project(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return _folder_to_project(folder)


@router.post("/{folder_name}/sync-agents")
def sync_agents(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="settings.toml not found")
    agents = get_system_agents(folder / "settings.toml")
    return {"ok": True, "count": len(agents), "agents": agents}
