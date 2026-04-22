"""
Config Loader
=============
Đọc settings từ config/settings.toml (hoặc custom path).
Hỗ trợ profile-based agent selection qua profiles.yaml.
"""

import tomllib
import yaml
from pathlib import Path
from dataclasses import dataclass, field

DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "settings.toml"
PROFILES_PATH  = Path(__file__).parent.parent / "profiles.yaml"

AGENT_KEYS = {
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


@dataclass
class AgentCfg:
    tool:  str
    model: str
    label: str


@dataclass
class Config:
    agents:           dict[str, AgentCfg]
    enabled_agents:   set[str]
    profile:          str
    slack_token:      str
    slack_channel:    str
    output_dir:       str
    timeout_claude:   int
    timeout_opencode: int
    tech_backend:     str
    tech_frontend:    str
    slack_enabled:    bool


def _load_profiles() -> dict:
    if not PROFILES_PATH.exists():
        return {}
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("profiles", {})


def _resolve_enabled(profile_name: str, profiles: dict) -> set[str]:
    if not profile_name or profile_name not in profiles:
        # Mặc định: tất cả agents
        return set(AGENT_KEYS.values())
    keys = profiles[profile_name].get("agents", list(AGENT_KEYS.keys()))
    return {AGENT_KEYS[k] for k in keys if k in AGENT_KEYS}


def load(config_path: Path | None = None, profile_override: str | None = None) -> Config:
    path = config_path or DEFAULT_CONFIG
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    a = raw["agents"]

    def make_agent(tool_key: str, model_key: str) -> AgentCfg:
        tool  = a[tool_key]
        model = a[model_key]
        if tool == "claude":
            label = "Claude Code"
        else:
            provider = model.split("/")[0] if "/" in model else model
            label = f"OpenCode + {provider.title()}"
        return AgentCfg(tool=tool, model=model, label=label)

    profiles    = _load_profiles()
    profile     = profile_override or raw.get("project", {}).get("profile", "")
    enabled     = _resolve_enabled(profile, profiles)
    slack_token = raw["slack"]["bot_token"]

    def make_agent_optional(tool_key: str, model_key: str) -> AgentCfg | None:
        if tool_key not in a:
            return None
        return make_agent(tool_key, model_key)

    agents: dict[str, AgentCfg] = {
        "PM Agent":     make_agent("pm_tool",      "pm_model"),
        "Scrum Master": make_agent("scrum_tool",   "scrum_model"),
        "Analyst":      make_agent("analyst_tool", "analyst_model"),
        "Leader Agent": make_agent("leader_tool",  "leader_model"),
    }
    for key, name in [("be1", "BE Agent 1"), ("be2", "BE Agent 2"),
                      ("fe1", "FE Agent 1"), ("fe2", "FE Agent 2"),
                      ("fs1", "Fullstack Agent 1"), ("fs2", "Fullstack Agent 2")]:
        agent = make_agent_optional(f"{key}_tool", f"{key}_model")
        if agent:
            agents[name] = agent

    return Config(
        agents=agents,
        enabled_agents=enabled,
        profile=profile or "fullstack",
        slack_token=slack_token,
        slack_channel=raw["slack"]["channel"],
        output_dir=raw["output"]["directory"],
        timeout_claude=raw["timeouts"]["claude_code"],
        timeout_opencode=raw["timeouts"]["opencode"],
        tech_backend=raw["tech_stack"]["backend"],
        tech_frontend=raw["tech_stack"]["frontend"],
        slack_enabled=slack_token != "xoxb-your-token-here",
    )


_config: Config | None = None


def init(config_path: Path | None = None, profile: str | None = None) -> Config:
    global _config
    _config = load(config_path, profile)
    return _config


def get() -> Config:
    global _config
    if _config is None:
        _config = load()
    return _config
