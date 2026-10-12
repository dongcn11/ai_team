"""
Quản trị LLM gateway — tab "API" trên dashboard
================================================

    /api/llm/providers   nơi gọi model thật (OpenRouter, Ollama, xAI...)
    /api/llm/models      alias tự đặt → provider + model gốc + system prompt
    /api/llm/clients     API key cấp cho hệ thống ngoài
    /api/llm/usage       số liệu dùng (không có nội dung hội thoại)
    /api/llm/playground  thử 1 alias ngay trên dashboard, không cần key

Key provider không bao giờ trả ngược ra web, chỉ 4 ký tự cuối (như bot chat).
Key client chỉ lưu hash — hiện đúng 1 lần trong response tạo/đổi key.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

import llm_gateway as gw
from database import get_db
from models import ApiClient, LlmCliJob, LlmModel, LlmProvider, LlmUsage

router = APIRouter()


def _mask(v: Optional[str]) -> str:
    v = (v or "").strip()
    return f"…{v[-4:]}" if len(v) > 4 else ("…" if v else "")


def _http(e: gw.GatewayError) -> HTTPException:
    return HTTPException(status_code=e.status if e.status < 500 else 502, detail=e.message)


# ── Providers ──────────────────────────────────────────────────────────────

class ProviderIn(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None          # rỗng lúc sửa = giữ nguyên
    clear_api_key: bool = False
    extra_headers: Optional[dict] = None
    timeout_s: Optional[int] = None
    allow_passthrough: Optional[bool] = None
    enabled: Optional[bool] = None
    kind: Optional[str] = None             # openai | claude_cli | grok_cli — chỉ đặt lúc tạo


KINDS = ("openai", *gw.CLI_KINDS)
# Provider *_cli không gọi HTTP — base_url chỉ để hiển thị, vd. "grok-cli://worker".


def _provider_out(db: Session, p: LlmProvider) -> dict:
    return {"id": p.id, "name": p.name, "base_url": p.base_url,
            "key_hint": _mask(p.api_key), "has_key": bool((p.api_key or "").strip()),
            "extra_headers": p.extra_headers or {}, "timeout_s": p.timeout_s or 120,
            "allow_passthrough": bool(p.allow_passthrough), "enabled": bool(p.enabled),
            "kind": p.kind or "openai",
            "model_count": db.query(LlmModel).filter(LlmModel.provider_id == p.id).count()}


def _clean_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not name or "/" in name or " " in name:
        raise HTTPException(400, "Tên provider: chữ thường, không dấu cách, không '/' (vd. openrouter)")
    return name


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    return [_provider_out(db, p) for p in db.query(LlmProvider).order_by(LlmProvider.id).all()]


@router.post("/providers")
def create_provider(payload: ProviderIn, db: Session = Depends(get_db)):
    name = _clean_name(payload.name or "")
    kind = payload.kind or "openai"
    if kind not in KINDS:
        raise HTTPException(400, f"kind phải là một trong {KINDS}")
    if kind in gw.CLI_KINDS:
        payload.base_url = f"{gw.CLI_KINDS[kind][0]}-cli://worker"
        payload.api_key, payload.extra_headers = None, None
        payload.timeout_s = payload.timeout_s or 300
    if not (payload.base_url or "").strip():
        raise HTTPException(400, "Chưa có base_url")
    if db.query(LlmProvider).filter(LlmProvider.name == name).first():
        raise HTTPException(400, f"Đã có provider '{name}'")
    p = LlmProvider(name=name, base_url=payload.base_url.strip().rstrip("/"),
                    api_key=(payload.api_key or "").strip() or None,
                    extra_headers=payload.extra_headers or None,
                    timeout_s=payload.timeout_s or 120,
                    allow_passthrough=bool(payload.allow_passthrough), kind=kind,
                    enabled=True if payload.enabled is None else payload.enabled)
    db.add(p)
    db.commit()
    return _provider_out(db, p)


@router.put("/providers/{pid}")
def update_provider(pid: int, payload: ProviderIn, db: Session = Depends(get_db)):
    p = db.get(LlmProvider, pid)
    if not p:
        raise HTTPException(404, "Không có provider")
    if payload.name is not None and _clean_name(payload.name) != p.name:
        name = _clean_name(payload.name)
        if db.query(LlmProvider).filter(LlmProvider.name == name).first():
            raise HTTPException(400, f"Đã có provider '{name}'")
        p.name = name
    if payload.base_url is not None and payload.base_url.strip() and p.kind not in gw.CLI_KINDS:
        p.base_url = payload.base_url.strip().rstrip("/")
    if payload.clear_api_key:
        p.api_key = None
    elif (payload.api_key or "").strip():
        p.api_key = payload.api_key.strip()
    if payload.extra_headers is not None:
        p.extra_headers = payload.extra_headers or None
    if payload.timeout_s:
        p.timeout_s = payload.timeout_s
    if payload.allow_passthrough is not None:
        p.allow_passthrough = payload.allow_passthrough
    if payload.enabled is not None:
        p.enabled = payload.enabled
    db.commit()
    return _provider_out(db, p)


@router.delete("/providers/{pid}")
def delete_provider(pid: int, db: Session = Depends(get_db)):
    p = db.get(LlmProvider, pid)
    if not p:
        raise HTTPException(404, "Không có provider")
    # Không dựa vào ON DELETE CASCADE: SQLite mặc định không bật foreign key.
    db.query(LlmModel).filter(LlmModel.provider_id == pid).delete()
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/providers/{pid}/remote-models")
def provider_remote_models(pid: int, db: Session = Depends(get_db)):
    p = db.get(LlmProvider, pid)
    if not p:
        raise HTTPException(404, "Không có provider")
    try:
        return {"models": gw.remote_models(p)}
    except gw.GatewayError as e:
        raise _http(e)


# ── Models (alias) ─────────────────────────────────────────────────────────

class ModelIn(BaseModel):
    alias: Optional[str] = None
    provider_id: Optional[int] = None
    upstream_model: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    params: Optional[dict] = None
    enabled: Optional[bool] = None


def _model_out(m: LlmModel, providers: dict) -> dict:
    p = providers.get(m.provider_id)
    return {"id": m.id, "alias": m.alias, "provider_id": m.provider_id,
            "provider": p.name if p else None, "upstream_model": m.upstream_model,
            "description": m.description or "", "system_prompt": m.system_prompt or "",
            "params": m.params or {}, "enabled": bool(m.enabled)}


def _clean_alias(alias: str) -> str:
    alias = (alias or "").strip()
    if not alias or " " in alias:
        raise HTTPException(400, "Alias không được rỗng hay có dấu cách (vd. viet-kich-ban)")
    return alias


def _clean_params(params: Optional[dict]) -> Optional[dict]:
    if not params:
        return None
    bad = [k for k in params if k not in gw.PASSTHROUGH_PARAMS]
    if bad:
        raise HTTPException(400, f"Tham số không hỗ trợ: {', '.join(bad)}")
    return params


@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    providers = {p.id: p for p in db.query(LlmProvider).all()}
    return [_model_out(m, providers) for m in db.query(LlmModel).order_by(LlmModel.alias).all()]


@router.post("/models")
def create_model(payload: ModelIn, db: Session = Depends(get_db)):
    alias = _clean_alias(payload.alias or "")
    if db.query(LlmModel).filter(LlmModel.alias == alias).first():
        raise HTTPException(400, f"Đã có alias '{alias}'")
    if not payload.provider_id or not db.get(LlmProvider, payload.provider_id):
        raise HTTPException(400, "Chọn provider")
    if not (payload.upstream_model or "").strip():
        raise HTTPException(400, "Chưa có model gốc")
    m = LlmModel(alias=alias, provider_id=payload.provider_id,
                 upstream_model=payload.upstream_model.strip(),
                 description=(payload.description or "").strip() or None,
                 system_prompt=(payload.system_prompt or "").strip() or None,
                 params=_clean_params(payload.params),
                 enabled=True if payload.enabled is None else payload.enabled)
    db.add(m)
    db.commit()
    return _model_out(m, {p.id: p for p in db.query(LlmProvider).all()})


@router.put("/models/{mid}")
def update_model(mid: int, payload: ModelIn, db: Session = Depends(get_db)):
    m = db.get(LlmModel, mid)
    if not m:
        raise HTTPException(404, "Không có model")
    if payload.alias is not None and _clean_alias(payload.alias) != m.alias:
        alias = _clean_alias(payload.alias)
        if db.query(LlmModel).filter(LlmModel.alias == alias).first():
            raise HTTPException(400, f"Đã có alias '{alias}'")
        m.alias = alias
    if payload.provider_id is not None:
        if not db.get(LlmProvider, payload.provider_id):
            raise HTTPException(400, "Provider không tồn tại")
        m.provider_id = payload.provider_id
    if payload.upstream_model is not None and payload.upstream_model.strip():
        m.upstream_model = payload.upstream_model.strip()
    if payload.description is not None:
        m.description = payload.description.strip() or None
    if payload.system_prompt is not None:
        m.system_prompt = payload.system_prompt.strip() or None
    if payload.params is not None:
        m.params = _clean_params(payload.params)
    if payload.enabled is not None:
        m.enabled = payload.enabled
    db.commit()
    return _model_out(m, {p.id: p for p in db.query(LlmProvider).all()})


@router.delete("/models/{mid}")
def delete_model(mid: int, db: Session = Depends(get_db)):
    m = db.get(LlmModel, mid)
    if not m:
        raise HTTPException(404, "Không có model")
    db.delete(m)
    db.commit()
    return {"ok": True}


# ── Clients (API key cho hệ thống ngoài) ───────────────────────────────────

class ClientIn(BaseModel):
    name: Optional[str] = None
    allowed_models: Optional[List[str]] = None
    enabled: Optional[bool] = None


def _client_out(c: ApiClient, key: Optional[str] = None) -> dict:
    out = {"id": c.id, "name": c.name, "key_prefix": c.key_prefix,
           "allowed_models": c.allowed_models or [], "enabled": bool(c.enabled),
           "created_at": c.created_at.isoformat() if c.created_at else None,
           "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None}
    if key:
        out["api_key"] = key            # chỉ có trong response tạo / đổi key
    return out


def _issue_key(c: ApiClient) -> str:
    key = gw.new_key()
    c.key_hash = gw.hash_key(key)
    c.key_prefix = key[:len(gw.KEY_PREFIX) + 4] + "…"
    return key


@router.get("/clients")
def list_clients(db: Session = Depends(get_db)):
    return [_client_out(c) for c in db.query(ApiClient).order_by(desc(ApiClient.id)).all()]


@router.post("/clients")
def create_client(payload: ClientIn, db: Session = Depends(get_db)):
    if not (payload.name or "").strip():
        raise HTTPException(400, "Đặt tên cho hệ thống dùng key này")
    c = ApiClient(name=payload.name.strip(), allowed_models=payload.allowed_models or [],
                  enabled=True if payload.enabled is None else payload.enabled)
    key = _issue_key(c)
    db.add(c)
    db.commit()
    return _client_out(c, key)


@router.put("/clients/{cid}")
def update_client(cid: int, payload: ClientIn, db: Session = Depends(get_db)):
    c = db.get(ApiClient, cid)
    if not c:
        raise HTTPException(404, "Không có client")
    if payload.name is not None and payload.name.strip():
        c.name = payload.name.strip()
    if payload.allowed_models is not None:
        c.allowed_models = payload.allowed_models
    if payload.enabled is not None:
        c.enabled = payload.enabled
    db.commit()
    return _client_out(c)


@router.post("/clients/{cid}/rotate")
def rotate_client_key(cid: int, db: Session = Depends(get_db)):
    """Key cũ chết ngay khi đổi — hệ thống ngoài phải cập nhật key mới."""
    c = db.get(ApiClient, cid)
    if not c:
        raise HTTPException(404, "Không có client")
    key = _issue_key(c)
    db.commit()
    return _client_out(c, key)


@router.delete("/clients/{cid}")
def delete_client(cid: int, db: Session = Depends(get_db)):
    c = db.get(ApiClient, cid)
    if not c:
        raise HTTPException(404, "Không có client")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ── Usage ──────────────────────────────────────────────────────────────────

@router.get("/usage")
def usage(days: int = 7, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 90)))
    names = {c.id: c.name for c in db.query(ApiClient).all()}
    rows = (db.query(LlmUsage.client_id, LlmUsage.model,
                     func.count(LlmUsage.id),
                     func.sum(func.coalesce(LlmUsage.prompt_tokens, 0)),
                     func.sum(func.coalesce(LlmUsage.completion_tokens, 0)),
                     func.sum(func.coalesce(LlmUsage.cost_usd, 0.0)),
                     func.sum(case((LlmUsage.status == "error", 1), else_=0)))
              .filter(LlmUsage.created_at >= since)
              .group_by(LlmUsage.client_id, LlmUsage.model).all())
    summary = [{"client_id": cid, "client": names.get(cid, "Thử trên dashboard" if cid is None else f"#{cid} (đã xoá)"),
                "model": model, "requests": n, "prompt_tokens": int(pt or 0),
                "completion_tokens": int(ct or 0), "cost_usd": round(float(cost or 0), 6),
                "errors": int(errs or 0)}
               for cid, model, n, pt, ct, cost, errs in rows]
    recent = (db.query(LlmUsage).order_by(desc(LlmUsage.id)).limit(50).all())
    return {"summary": sorted(summary, key=lambda r: -r["requests"]),
            "recent": [{"id": u.id, "client": names.get(u.client_id, "dashboard" if u.client_id is None else f"#{u.client_id}"),
                        "model": u.model, "provider": u.provider, "upstream_model": u.upstream_model,
                        "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
                        "cost_usd": u.cost_usd, "latency_ms": u.latency_ms, "status": u.status,
                        "error": u.error,
                        "created_at": u.created_at.isoformat() if u.created_at else None}
                       for u in recent]}


# ── Playground ─────────────────────────────────────────────────────────────

class PlaygroundIn(BaseModel):
    model: str
    messages: List[dict]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.post("/playground")
def playground(payload: PlaygroundIn, db: Session = Depends(get_db)):
    try:
        return gw.chat(db, None, payload.model_dump(exclude_none=True))
    except gw.GatewayError as e:
        raise _http(e)


# ── Hàng đợi `claude -p` / `grok -p` cho provider kind=*_cli (worker.py gọi) ──

class CliCompleteIn(BaseModel):
    status: str                      # done | error
    text: Optional[str] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None
    usage: Optional[dict] = None


# Request HTTP của client chờ tối đa timeout_s của provider; job chạy quá lâu hơn
# thế thì chắc worker đã chết giữa chừng.
_CLI_STALE = timedelta(minutes=15)


@router.post("/cli-jobs/claim")
def claim_cli_job(db: Session = Depends(get_db)) -> Optional[dict]:
    import worker_heartbeat
    from routers.assistant import _claude_prefs
    worker_heartbeat.touch()
    now = datetime.utcnow()
    for j in (db.query(LlmCliJob).filter(LlmCliJob.status == "running",
                                         LlmCliJob.started_at < now - _CLI_STALE).all()):
        j.status, j.finished_at, j.error, j.files = "error", now, "Worker không trả lời kịp.", None
    db.commit()

    j = (db.query(LlmCliJob).filter(LlmCliJob.status == "pending")
           .order_by(LlmCliJob.id).first())
    if not j:
        return None
    j.status, j.started_at = "running", now
    db.commit()
    # Tài khoản Claude theo Settings (dùng chung với khung chat); model theo alias.
    prefs = _claude_prefs(db)
    # Tài khoản/model mặc định trong Settings là của Claude — job grok bỏ qua.
    if (j.cli or "claude") != "claude":
        return {"id": j.id, "cli": j.cli, "system": j.system or "", "prompt": j.prompt,
                "model": j.model, "files": j.files or []}
    return {"id": j.id, "cli": "claude", "system": j.system or "", "prompt": j.prompt,
            "files": j.files or [],
            "claude_account": prefs["claude_account"],
            "claude_auto_switch": prefs["claude_auto_switch"],
            "model": j.model or prefs["model"]}


@router.post("/cli-jobs/{jid}/complete")
def complete_cli_job(jid: int, payload: CliCompleteIn, db: Session = Depends(get_db)) -> dict:
    j = db.get(LlmCliJob, jid)
    if not j:
        raise HTTPException(404, "Không có job")
    if j.status not in ("pending", "running"):      # đã timeout phía gateway
        return {"ok": False}
    j.status = "done" if payload.status == "done" else "error"
    j.result, j.error = payload.text, payload.error
    j.model_used, j.cost_usd, j.usage = payload.model_used, payload.cost_usd, payload.usage
    j.files = None                                  # nội dung file không giữ lại sau khi trả lời
    j.finished_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
