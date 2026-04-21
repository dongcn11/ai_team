"""
Config Loader
=============
Đọc settings từ config/settings.toml.
Dùng ở khắp nơi trong project.
"""

import tomllib
from pathlib import Path
from dataclasses import dataclass

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"


@dataclass
class AgentCfg:
    tool:  str
    model: str
    label: str


@dataclass
class Config:
    agents:     dict[str, AgentCfg]
    slack_token: str
    slack_channel: str
    output_dir:  str
    timeout_claude: int
    timeout_opencode: int
    tech_backend:  str
    tech_frontend: str
    slack_enabled: bool


def load() -> Config:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    a = raw["agents"]

    def make_agent(tool_key, model_key) -> AgentCfg:
        tool  = a[tool_key]
        model = a[model_key]
        if tool == "claude":
            label = "Claude Code"
        else:
            provider = model.split("/")[0] if "/" in model else model
            label = f"OpenCode + {provider.title()}"
        return AgentCfg(tool=tool, model=model, label=label)

    slack_token = raw["slack"]["bot_token"]

    return Config(
        agents={
            "PM Agent":     make_agent("pm_tool",     "pm_model"),
            "Scrum Master": make_agent("scrum_tool",  "scrum_model"),
            "Analyst":      make_agent("analyst_tool","analyst_model"),
            "BE Agent 1":   make_agent("be1_tool",    "be1_model"),
            "BE Agent 2":   make_agent("be2_tool",    "be2_model"),
            "FE Agent 1":   make_agent("fe1_tool",    "fe1_model"),
            "FE Agent 2":   make_agent("fe2_tool",    "fe2_model"),
        },
        slack_token=slack_token,
        slack_channel=raw["slack"]["channel"],
        output_dir=raw["output"]["directory"],
        timeout_claude=raw["timeouts"]["claude_code"],
        timeout_opencode=raw["timeouts"]["opencode"],
        tech_backend=raw["tech_stack"]["backend"],
        tech_frontend=raw["tech_stack"]["frontend"],
        slack_enabled=slack_token != "xoxb-your-token-here",
    )


# Singleton — load 1 lần
_config: Config | None = None

def get() -> Config:
    global _config
    if _config is None:
        _config = load()
    return _config
