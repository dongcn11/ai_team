"""
System Config Reader
====================
Đọc agents từ config/settings.toml và profiles.yaml của ai_team.
"""
import os
import tomllib
import yaml
from pathlib import Path

CONFIG_DIR   = Path(os.getenv("CONFIG_DIR",   "/config"))
PROFILES_DIR = Path(os.getenv("PROFILES_DIR", "/config"))
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
PROFILES_FILE = PROFILES_DIR / "profiles.yaml"
if not PROFILES_FILE.exists():
    PROFILES_FILE = Path("/profiles.yaml")  # fallback: mounted at root

AGENT_LABELS = {
    "pm":      "PM Agent",
    "scrum":   "Scrum Master",
    "analyst": "Analyst",
    "be1":     "BE Agent 1",
    "be2":     "BE Agent 2",
    "fe1":     "FE Agent 1",
    "fe2":     "FE Agent 2",
    "fs1":     "Fullstack Agent 1",
    "fs2":     "Fullstack Agent 2",
    "leader":  "Leader Agent",
}

AGENT_DESCRIPTIONS = {
    "pm":      "Writes user stories and acceptance criteria",
    "scrum":   "Creates sprint backlog and task breakdown",
    "analyst": "Designs API contracts and data models",
    "be1":     "Implements backend APIs and services",
    "be2":     "Implements backend APIs and services (parallel)",
    "fe1":     "Implements frontend UI components and pages",
    "fe2":     "Implements frontend UI components and pages (parallel)",
    "fs1":     "Fullstack: handles both backend and frontend",
    "fs2":     "Fullstack: handles both backend and frontend (parallel)",
    "leader":  "Reviews all code and writes final report",
}

AGENT_STATUS_ORDER = ["available", "busy", "offline"]


def get_system_agents(config_path: Path | None = None) -> list[dict]:
    """Trả về danh sách agent từ settings.toml (global hoặc project-specific)."""
    path = config_path or SETTINGS_FILE
    if not path.exists():
        return []

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    agents_section = raw.get("agents", {})
    result = []

    for key in ["pm", "scrum", "analyst", "be1", "be2", "fe1", "fe2", "fs1", "fs2", "leader"]:
        tool_key = f"{key}_tool"
        model_key = f"{key}_model"
        if tool_key in agents_section and model_key in agents_section:
            tool  = agents_section[tool_key]
            model = agents_section[model_key]
            result.append({
                "key":         key,
                "name":        AGENT_LABELS.get(key, key),
                "role":        key,
                "model":       model or f"{tool}-default",
                "tool":        tool,
                "status":      "available",
                "description": AGENT_DESCRIPTIONS.get(key, ""),
            })

    return result


def get_profiles() -> list[dict]:
    """Trả về danh sách profiles từ profiles.yaml."""
    if not PROFILES_FILE.exists():
        return []

    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    profiles = raw.get("profiles", {}) if raw else {}
    result = []
    for key, val in profiles.items():
        result.append({
            "key":    key,
            "label":  val.get("label", key),
            "agents": val.get("agents", []),
        })
    return result
