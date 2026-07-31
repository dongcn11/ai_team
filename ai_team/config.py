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

# Agents capable of writing backend / frontend code. Fullstack agents count for both.
BACKEND_CAPABLE_AGENTS  = {"BE Agent 1", "BE Agent 2", "Fullstack Agent 1", "Fullstack Agent 2"}
FRONTEND_CAPABLE_AGENTS = {"FE Agent 1", "FE Agent 2", "Fullstack Agent 1", "Fullstack Agent 2"}


@dataclass
class AgentCfg:
    tool:  str
    model: str
    label: str


@dataclass
class PipelineStage:
    """Cấu hình cho một stage trong pipeline."""
    stage_id: str          # pm, scrum, analyst, coding, leader, fix
    enabled: bool = True
    timeout_s: int = 600
    depends_on: str | None = None  # Stage ID nếu có dependency
    parallel_agents: list[str] | None = None  # Agents chạy song song (cho coding stage)


@dataclass
class Config:
    agents:           dict[str, AgentCfg]
    enabled_agents:   set[str]
    profile:          str
    output_dir:       str
    docs_dir:         str
    timeout_claude:   int
    timeout_opencode: int
    tech_backend:     str
    tech_frontend:    str
    pipeline_stages:  dict[str, PipelineStage] = field(default_factory=dict)  # stage_id → config
    slack_enabled:    bool = False
    slack_token:      str  = ""
    slack_channel:    str  = "#ai-team"


def _load_profiles() -> dict:
    if not PROFILES_PATH.exists():
        return {}
    with open(PROFILES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f).get("profiles", {})


def _resolve_profile(profile_name: str, profiles: dict) -> tuple[set[str], set[str]]:
    """Resolve profile → (enabled_agents, stages_disabled).
    stages_disabled là default từ profile; settings.toml [pipeline.stages] vẫn override được.
    """
    if not profile_name or profile_name not in profiles:
        # Mặc định: tất cả agents, không tắt stage nào
        return set(AGENT_KEYS.values()), set()
    profile = profiles[profile_name]
    keys = profile.get("agents", list(AGENT_KEYS.keys()))
    enabled_agents = {AGENT_KEYS[k] for k in keys if k in AGENT_KEYS}
    stages_disabled = set(profile.get("stages_disabled", []))
    return enabled_agents, stages_disabled


def _load_pipeline_config(raw: dict, stages_disabled_by_profile: set[str] | None = None) -> dict[str, PipelineStage]:
    """Load pipeline stages: bắt đầu từ defaults, áp dụng profile stages_disabled,
    rồi cuối cùng [pipeline.stages] trong settings.toml override (cụ thể nhất thắng).
    """
    pipeline_raw = raw.get("pipeline", {})
    stages_raw = pipeline_raw.get("stages", {})
    profile_disabled = stages_disabled_by_profile or set()

    # Default pipeline stages nếu không có config
    defaults = {
        "pm": PipelineStage("pm", enabled=True, timeout_s=600),
        "scrum": PipelineStage("scrum", enabled=True, timeout_s=600),
        "analyst": PipelineStage("analyst", enabled=True, timeout_s=600),
        "coding": PipelineStage("coding", enabled=True, timeout_s=1800,
                               parallel_agents=["be1", "be2", "fe1", "fe2", "fs1", "fs2"]),
        "leader": PipelineStage("leader", enabled=True, timeout_s=600),
        "fix": PipelineStage("fix", enabled=True, timeout_s=600, depends_on="leader"),
    }

    # Áp dụng profile stages_disabled lên defaults trước
    for sid in profile_disabled:
        if sid in defaults:
            defaults[sid].enabled = False

    # Override defaults với config từ settings.toml (đặc thù project > profile)
    result = {}
    for stage_id, default_cfg in defaults.items():
        stage_config = stages_raw.get(stage_id, {})

        enabled = stage_config.get("enabled", default_cfg.enabled)
        timeout_s = stage_config.get("timeout_s", default_cfg.timeout_s)
        depends_on = stage_config.get("depends_on", default_cfg.depends_on)
        parallel_agents = stage_config.get("parallel", default_cfg.parallel_agents)

        result[stage_id] = PipelineStage(
            stage_id=stage_id,
            enabled=enabled,
            timeout_s=timeout_s,
            depends_on=depends_on,
            parallel_agents=parallel_agents,
        )

    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override vào base, section-level override."""
    result = {**base}
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = {**result[k], **v}
        else:
            result[k] = v
    return result


def _reject_claude_agents(agents: dict[str, AgentCfg], enabled: set[str], path: Path) -> None:
    """Chặn `tool = "claude"` ngay lúc load config, trước khi pipeline chạy.

    Pipeline này là automation không người giám sát — dùng subscription Claude cho
    nó sẽ bị khoá account. Xem docstring `ai_team/runner.py`. Agent enabled dùng
    claude → dừng hẳn; agent đã tắt → chỉ cảnh báo (mìn chờ, nên dọn).
    """
    offenders = sorted(r for r, a in agents.items() if a.tool == "claude")
    if not offenders:
        return

    blocking = [r for r in offenders if r in enabled]
    dormant  = [r for r in offenders if r not in enabled]

    if dormant:
        print(f"[config] ⚠️  {', '.join(dormant)} đang set tool=\"claude\" (hiện tắt) — "
              f"đổi sang \"opencode\" trong {path} trước khi bật lại.")

    if blocking:
        keys = ", ".join(f"{r} → <key>_tool = \"opencode\"" for r in blocking)
        raise ValueError(
            f"Không chạy được: {', '.join(blocking)} đang dùng Claude Code.\n"
            f"  Pipeline tự động không được dùng subscription Claude (khoá account).\n"
            f"  Sửa trong {path}: {keys}\n"
            f"  Cần Claude thì mở terminal gõ `claude` thủ công, đừng chạy qua worker."
        )


def load(config_path: Path | str | None = None, profile_override: str | None = None) -> Config:
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Load settings.local.toml nếu tồn tại (gitignored, per-machine override)
    local_path = path.parent / "settings.local.toml"
    if local_path.exists():
        with open(local_path, "rb") as f:
            local = tomllib.load(f)
        raw = _deep_merge(raw, local)
        print(f"[config] Loaded local override: {local_path}")

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

    profiles = _load_profiles()
    profile  = profile_override or raw.get("project", {}).get("profile", "")
    enabled, profile_stages_disabled = _resolve_profile(profile, profiles)

    def make_agent_optional(tool_key: str, model_key: str) -> AgentCfg | None:
        if tool_key not in a:
            return None
        return make_agent(tool_key, model_key)

    agents: dict[str, AgentCfg] = {}
    for key, name in [
        ("pm",      "PM Agent"),
        ("scrum",   "Scrum Master"),
        ("analyst", "Analyst"),
        ("leader",  "Leader Agent"),
        ("be1",     "BE Agent 1"),
        ("be2",     "BE Agent 2"),
        ("fe1",     "FE Agent 1"),
        ("fe2",     "FE Agent 2"),
        ("fs1",     "Fullstack Agent 1"),
        ("fs2",     "Fullstack Agent 2"),
    ]:
        agent = make_agent_optional(f"{key}_tool", f"{key}_model")
        if agent:
            agents[name] = agent

    _reject_claude_agents(agents, enabled, path)

    def _resolve_dir(raw_str: str) -> str:
        p = Path(raw_str)
        if not p.is_absolute():
            p = (path.parent / p).resolve()
        return str(p)

    output_dir = _resolve_dir(raw["output"]["directory"])

    # docs_directory: mặc định là {output_dir}/docs nếu không cấu hình
    docs_raw = raw.get("output", {}).get("docs_directory", "")
    docs_dir = _resolve_dir(docs_raw) if docs_raw else str(Path(output_dir) / "docs")

    slack_raw     = raw.get("slack", {})
    slack_token   = slack_raw.get("bot_token", "")
    slack_enabled = bool(slack_token and not slack_token.startswith("xoxb-your"))

    # Load pipeline configuration (profile defaults → settings.toml override)
    pipeline_stages = _load_pipeline_config(raw, stages_disabled_by_profile=profile_stages_disabled)

    # Strip tech_stack parts that no enabled agent can actually use. Prevents
    # PM/Scrum/Analyst from inventing phantom BE/FE roles when the profile
    # only includes the opposite stack.
    tech_backend  = raw["tech_stack"]["backend"]
    tech_frontend = raw["tech_stack"]["frontend"]
    if not (enabled & BACKEND_CAPABLE_AGENTS):
        tech_backend = ""
    if not (enabled & FRONTEND_CAPABLE_AGENTS):
        tech_frontend = ""

    return Config(
        agents=agents,
        enabled_agents=enabled,
        profile=profile or "fullstack",
        output_dir=output_dir,
        docs_dir=docs_dir,
        timeout_claude=raw["timeouts"]["claude_code"],
        timeout_opencode=raw["timeouts"]["opencode"],
        tech_backend=tech_backend,
        tech_frontend=tech_frontend,
        pipeline_stages=pipeline_stages,
        slack_enabled=slack_enabled,
        slack_token=slack_token,
        slack_channel=slack_raw.get("channel", "#ai-team"),
    )


_config: Config | None = None


VALID_STAGE_IDS = {"pm", "scrum", "analyst", "coding", "leader", "fix"}


def apply_stage_overrides(
    cfg: Config,
    disable: list[str] | None = None,
    enable: list[str] | None = None,
) -> Config:
    """Override pipeline stage enabled flags từ CLI (sau khi load config).
    Raise ValueError nếu stage_id không hợp lệ.
    """
    for stage_id in (disable or []):
        if stage_id not in VALID_STAGE_IDS:
            raise ValueError(f"Stage '{stage_id}' không hợp lệ. Hợp lệ: {sorted(VALID_STAGE_IDS)}")
        if stage_id in cfg.pipeline_stages:
            cfg.pipeline_stages[stage_id].enabled = False

    for stage_id in (enable or []):
        if stage_id not in VALID_STAGE_IDS:
            raise ValueError(f"Stage '{stage_id}' không hợp lệ. Hợp lệ: {sorted(VALID_STAGE_IDS)}")
        if stage_id in cfg.pipeline_stages:
            cfg.pipeline_stages[stage_id].enabled = True

    return cfg


def init(config_path: Path | None = None, profile: str | None = None) -> Config:
    global _config
    _config = load(config_path, profile)
    return _config


def get() -> Config:
    global _config
    if _config is None:
        _config = load()
    return _config
