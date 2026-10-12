"""
Model cho khung "Trò chuyện" — danh mục, quyền theo tài khoản
==============================================================

Danh mục = 3 model Claude dựng sẵn (worker chạy `claude -p --model <x>`) + mọi
model đang bật ở tab API (bảng llm_models của LLM gateway). Khoá:
    claude:<opus|sonnet|haiku>   Claude Code CLI trên worker
    gw:<alias>                   alias của gateway

Cách trả lời theo `via`:
    cli   tin `pending` → worker.py claim rồi chạy `claude -p` / `grok -p`
    http  provider HTTP chuẩn OpenAI (OpenRouter, Ollama…) — API tự gọi trong
          thread nền, không cần worker; không đọc được file đính kèm hay dự án.

Quyền: `users.models` NULL = mọi model (kể cả model thêm sau), danh sách = chỉ các
khoá đó. Admin luôn dùng được hết.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from models import LlmModel, LlmProvider, User

BUILTIN = [
    {"key": "claude:opus",   "label": "Claude Opus",   "description": "Mạnh nhất, chậm và đắt nhất",
     "cli": "claude", "model": "opus"},
    {"key": "claude:sonnet", "label": "Claude Sonnet", "description": "Cân bằng — đủ cho hầu hết câu hỏi",
     "cli": "claude", "model": "sonnet"},
    {"key": "claude:haiku",  "label": "Claude Haiku",  "description": "Nhanh và rẻ nhất",
     "cli": "claude", "model": "haiku"},
]
_CLI_OF_KIND = {"claude_cli": "claude", "grok_cli": "grok"}


def catalog(db: Session) -> List[dict]:
    """Mọi model chat dùng được lúc này, theo thứ tự hiển thị (đầu tiên = mặc định)."""
    out = [{**m, "group": "Claude", "via": "cli", "files": True, "project": True,
            "system_prompt": None, "alias": None} for m in BUILTIN]
    rows = (db.query(LlmModel, LlmProvider)
              .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
              .filter(LlmModel.enabled == True, LlmProvider.enabled == True)   # noqa: E712
              .order_by(LlmModel.alias).all())
    for m, p in rows:
        cli = _CLI_OF_KIND.get(p.kind or "openai")
        out.append({
            "key": f"gw:{m.alias}", "label": m.alias, "description": m.description or "",
            "group": f"API · {p.name}", "via": "cli" if cli else "http",
            "cli": cli, "model": m.upstream_model,
            # grok -p đọc được file đính kèm nhưng không có quyền đọc dự án;
            # provider HTTP thì chỉ nhận chữ.
            "files": bool(cli), "project": cli == "claude",
            "system_prompt": m.system_prompt, "alias": m.alias,
        })
    return out


def public(m: dict) -> dict:
    return {k: m[k] for k in ("key", "label", "description", "group", "via", "files", "project")}


def allowed(db: Session, u: User) -> List[dict]:
    cat = catalog(db)
    if u.is_admin or u.models is None:
        return cat
    keys = set(u.models)
    return [m for m in cat if m["key"] in keys]


def get(db: Session, key: Optional[str]) -> Optional[dict]:
    return next((m for m in catalog(db) if m["key"] == key), None) if key else None
