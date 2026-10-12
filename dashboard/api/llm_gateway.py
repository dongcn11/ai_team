"""
LLM gateway — cho hệ thống khác dùng AI bên này (chat, viết kịch bản...)
=======================================================================

Hệ thống ngoài gọi `POST /v1/chat/completions` đúng chuẩn OpenAI, nên SDK OpenAI
của bất kỳ ngôn ngữ nào dùng được ngay, chỉ đổi `base_url` + `api_key`:

    client = OpenAI(base_url="http://<host>:8100/v1", api_key="sk-ait-…")
    client.chat.completions.create(model="viet-kich-ban", messages=[...])

`model` được phân giải theo thứ tự:
    1. alias trong bảng llm_models   → provider + model gốc + system prompt + tham số
    2. "<provider>/<model gốc>"      → chỉ khi provider bật allow_passthrough

Provider `kind`:
    openai      HTTP chuẩn OpenAI tới base_url — OpenRouter, Ollama, xAI, OpenAI...
    claude_cli  xếp hàng LlmCliJob → worker.py chạy `claude -p` bằng đăng nhập
                Claude Code trên host (như khung chat). CHỈ ĐỂ TEST: subscription
                cá nhân làm backend cho hệ thống khác là trái điều khoản Anthropic.
    grok_cli    như claude_cli nhưng worker chạy `grok -p` (Grok Build CLI của xAI)
                bằng đăng nhập grok / XAI_API_KEY trên host. Cũng chỉ để test.

Gọi upstream bằng urllib (chặn) — endpoint khai `def` thường nên FastAPI chạy nó
trong threadpool, không treo event loop.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import Optional
from urllib.parse import quote

from sqlalchemy.orm import Session

import sandbox_client
from models import ApiClient, LlmCliJob, LlmFile, LlmModel, LlmProvider, LlmUsage

KEY_PREFIX = "sk-ait-"

# Tham số chuẩn OpenAI được chuyển tiếp. Danh sách trắng: client không nhét được
# thứ provider tính tiền riêng (vd. `models` fallback của OpenRouter) qua gateway.
PASSTHROUGH_PARAMS = (
    "temperature", "top_p", "max_tokens", "max_completion_tokens", "stop",
    "presence_penalty", "frequency_penalty", "seed", "response_format",
    "tools", "tool_choice", "user", "n",
)


class GatewayError(Exception):
    """Lỗi trả cho client theo dạng lỗi của OpenAI: {"error": {...}}."""

    def __init__(self, status: int, message: str, type_: str = "invalid_request_error",
                 code: Optional[str] = None):
        super().__init__(message)
        self.status, self.message, self.type, self.code = status, message, type_, code

    def body(self) -> dict:
        return {"error": {"message": self.message, "type": self.type, "code": self.code}}


# ── API key của client ─────────────────────────────────────────────────────

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def authenticate(db: Session, authorization: Optional[str]) -> ApiClient:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise GatewayError(401, "Thiếu API key (header Authorization: Bearer sk-ait-…)",
                           "authentication_error", "missing_api_key")
    client = db.query(ApiClient).filter(ApiClient.key_hash == hash_key(token)).first()
    if not client:
        raise GatewayError(401, "API key không hợp lệ", "authentication_error", "invalid_api_key")
    if not client.enabled:
        raise GatewayError(403, "API key đã bị tắt", "permission_error", "key_disabled")
    return client


# ── Phân giải model ────────────────────────────────────────────────────────

@dataclass
class Target:
    alias: str                      # tên client gửi lên — trả lại đúng tên này
    provider: LlmProvider
    upstream_model: str
    system_prompt: Optional[str] = None
    params: Optional[dict] = None


def resolve(db: Session, model: str) -> Target:
    model = (model or "").strip()
    if not model:
        raise GatewayError(400, "Thiếu `model`", code="missing_model")

    m = db.query(LlmModel).filter(LlmModel.alias == model).first()
    if m:
        p = db.get(LlmProvider, m.provider_id)
        if not m.enabled or not p or not p.enabled:
            raise GatewayError(404, f"Model '{model}' đang tắt", code="model_not_found")
        return Target(model, p, m.upstream_model, m.system_prompt, m.params or {})

    if "/" in model:
        pname, upstream = model.split("/", 1)
        p = db.query(LlmProvider).filter(LlmProvider.name == pname).first()
        if p and p.enabled and p.allow_passthrough and upstream:
            return Target(model, p, upstream)

    raise GatewayError(404, f"Không có model '{model}' — xem GET /v1/models",
                       code="model_not_found")


def allowed(client: Optional[ApiClient], alias: str) -> bool:
    """Client giới hạn model thì chỉ được dùng alias nằm trong danh sách — model
    passthrough "<provider>/…" cũng phải được liệt kê đúng tên đó."""
    if client is None or not client.allowed_models:
        return True
    return alias in client.allowed_models


def list_models(db: Session, client: Optional[ApiClient]) -> list:
    rows = (db.query(LlmModel, LlmProvider)
              .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
              .filter(LlmModel.enabled == True, LlmProvider.enabled == True)   # noqa: E712
              .order_by(LlmModel.alias).all())
    return [{"id": m.alias, "object": "model", "owned_by": p.name,
             "description": m.description or "",
             "created": int(m.created_at.timestamp()) if m.created_at else 0}
            for m, p in rows if allowed(client, m.alias)]


# ── Gọi upstream ───────────────────────────────────────────────────────────

def build_payload(target: Target, body: dict) -> dict:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise GatewayError(400, "`messages` phải là danh sách không rỗng", code="invalid_messages")
    if target.system_prompt:
        # System prompt của alias đứng TRƯỚC system của client: alias định vai,
        # client bổ sung chi tiết cho từng lần gọi.
        messages = [{"role": "system", "content": target.system_prompt}] + messages

    payload = {k: v for k, v in (target.params or {}).items() if k in PASSTHROUGH_PARAMS}
    payload.update({k: body[k] for k in PASSTHROUGH_PARAMS if body.get(k) is not None})
    payload["model"] = target.upstream_model
    payload["messages"] = messages
    payload["stream"] = False
    return payload


def _post(provider: LlmProvider, path: str, payload: Optional[dict]) -> dict:
    url = provider.base_url.rstrip("/") + path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if (provider.api_key or "").strip():
        headers["Authorization"] = f"Bearer {provider.api_key.strip()}"
    for k, v in (provider.extra_headers or {}).items():
        headers[str(k)] = str(v)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=provider.timeout_s or 120) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            msg = json.loads(raw).get("error", {})
            msg = msg.get("message") if isinstance(msg, dict) else msg
        except Exception:
            msg = None
        raise GatewayError(502, f"{provider.name} trả lỗi {e.code}: {msg or raw[:500]}",
                           "upstream_error", f"upstream_{e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise GatewayError(502, f"Không gọi được {provider.name} ({url}): {reason}",
                           "upstream_error", "upstream_unreachable")
    except json.JSONDecodeError:
        raise GatewayError(502, f"{provider.name} trả về không phải JSON",
                           "upstream_error", "upstream_bad_response")


# kind provider → CLI worker chạy + gợi ý model gốc. `claude --model` hiểu alias
# sonnet/opus/haiku; grok nhận id model (`grok models` trên host liệt kê đủ).
CLI_KINDS = {
    "claude_cli": ("claude", ["sonnet", "opus", "haiku"]),
    "grok_cli":   ("grok",   ["grok-4.7"]),
}
CLI_POLL_S = 1.0


def remote_models(provider: LlmProvider) -> list:
    """Danh sách model provider đang có — để chọn model gốc khi khai alias."""
    if provider.kind in CLI_KINDS:
        return CLI_KINDS[provider.kind][1]
    data = _post(provider, "/models", None)
    return sorted(str(m.get("id")) for m in data.get("data", []) if m.get("id"))


def chat(db: Session, client: Optional[ApiClient], body: dict, base_url: str = "") -> dict:
    """Một lượt chat completion trọn vẹn + ghi usage (cả khi lỗi). `base_url` (vd.
    http://host:8100) để dựng link tải khi request đòi `output` là file."""
    if body.get("stream"):
        raise GatewayError(400, "Chưa hỗ trợ stream=true — gửi stream=false", code="stream_unsupported")
    output = _output_spec(body)
    if output:
        body = {**body, "messages": [{"role": "system", "content": _output_instruction(output)},
                                     *(body.get("messages") or [])]}

    alias = str(body.get("model") or "")
    log = LlmUsage(client_id=client.id if client else None, model=alias, status="ok")
    t0 = time.monotonic()
    try:
        target = resolve(db, alias)
        if not allowed(client, target.alias):
            raise GatewayError(403, f"Key này không được dùng model '{alias}'",
                               "permission_error", "model_not_allowed")
        log.provider, log.upstream_model = target.provider.name, target.upstream_model
        resp = _call(db, target, body)

        usage = resp.get("usage") or {}
        log.prompt_tokens = usage.get("prompt_tokens")
        log.completion_tokens = usage.get("completion_tokens")
        if isinstance(usage.get("cost"), (int, float)):
            log.cost_usd = float(usage["cost"])
        # Trả lại đúng alias client gửi — đổi model gốc phía sau không lộ ra ngoài.
        resp["model"] = target.alias
        if output in GEN_OUTPUTS:
            _attach_generated(db, client, target, body, resp, body.get("output_name"), base_url)
        elif output:
            _attach_output(db, client, resp, output, body.get("output_name"), base_url)
        return resp
    except GatewayError as e:
        log.status, log.error = "error", e.message[:2000]
        raise
    finally:
        log.latency_ms = int((time.monotonic() - t0) * 1000)
        if client:
            client.last_used_at = datetime.utcnow()
        db.add(log)
        db.commit()


# ── File đầu ra: AI viết nội dung, gateway cất thành file + trả link tải ─────
#
# Client gửi thêm `"output": "<loại>"` (form: -F output=docx). Kết quả cất vào
# llm_files, trả `files: [{name, url, …}]` cạnh `choices`. AI không cần quyền ghi
# đĩa nên mọi provider (CLI lẫn HTTP) đều dùng được.
#   html        AI trả nguyên tài liệu trong 1 khối ```html``` → cất thẳng (nhanh).
#   docx, xlsx, pptx, pdf, png, csv, file
#               AI viết script ```python-file```, container `sandbox` chạy rồi trả
#               file (sandbox_client.py — chung với khung chat). File client gửi
#               kèm nằm trong in/. Script lỗi → đưa lỗi lại cho AI sửa 1 lần.

OUTPUTS = {
    "html": {
        "mime": "text/html; charset=utf-8", "ext": ".html", "fence": "html",
        "instruction": (
            "Yêu cầu này cần kết quả là MỘT FILE HTML. Trả về đúng một tài liệu HTML hoàn chỉnh, "
            "dùng được ngay khi mở bằng trình duyệt (<!DOCTYPE html>, <meta charset=\"utf-8\">, "
            "<meta name=\"viewport\" …>, CSS và JS viết thẳng trong file, ảnh/thư viện chỉ lấy từ "
            "CDN công khai), đặt TRỌN trong MỘT khối ```html … ```. Ngoài khối đó chỉ viết tối đa "
            "1–2 câu mô tả file. Không hỏi lại, không chia nhiều khối."),
    },
}
# output → mô tả định dạng dặn AI (đi qua sandbox).
GEN_OUTPUTS = {
    "docx": "MỘT file Word .docx (python-docx)",
    "xlsx": "MỘT file Excel .xlsx (openpyxl hoặc xlsxwriter; giữ công thức khi hợp lý)",
    "pptx": "MỘT file PowerPoint .pptx (python-pptx)",
    "pdf":  "MỘT file PDF (reportlab, nhớ font DejaVu Sans cho tiếng Việt)",
    "png":  "ảnh PNG (biểu đồ / hình vẽ bằng matplotlib hoặc pillow)",
    "csv":  "MỘT file CSV UTF-8 có BOM (utf-8-sig) để Excel mở đúng tiếng Việt",
    "file": "file có định dạng phù hợp nhất với yêu cầu",
}
GEN_FIX_TRIES = 1
FILE_TTL = timedelta(hours=float(os.getenv("LLM_FILE_TTL_H", "24")))


def _output_spec(body: dict) -> Optional[str]:
    out = body.get("output")
    if out in (None, "", "text"):
        return None
    out = str(out).strip().lower()
    if out not in OUTPUTS and out not in GEN_OUTPUTS:
        raise GatewayError(400, f"`output` chưa hỗ trợ '{out}' — dùng: "
                                f"{', '.join([*OUTPUTS, *GEN_OUTPUTS])}", code="unsupported_output")
    return out


def _output_instruction(kind: str) -> str:
    if kind in OUTPUTS:
        return OUTPUTS[kind]["instruction"]
    return (f"Yêu cầu này cần kết quả là {GEN_OUTPUTS[kind]}. " + sandbox_client.GUIDE +
            "\nLuôn trả khối python-file, không hỏi lại, không chia nhiều khối.")


def _extract(kind: str, text: str) -> tuple[Optional[str], str]:
    """(nội dung file, phần chữ còn lại). Lấy khối ```html dài nhất; AI quên rào
    mà cả câu trả lời là HTML thì lấy nguyên."""
    fence = re.compile(r"```" + OUTPUTS[kind]["fence"] + r"[^\n]*\n(.*?)(?:```|\Z)", re.S | re.I)
    blocks = fence.findall(text)
    if blocks:
        doc = max(blocks, key=len).strip()
        rest = fence.sub("", text).strip()
        return doc, rest
    t = text.strip()
    if re.match(r"(<!doctype html|<html)", t, re.I):
        return t, ""
    return None, text


def _file_name(name, kind: str) -> str:
    ext = OUTPUTS[kind]["ext"]
    base = re.sub(r"[^\w.\- ]+", "_", PurePath(str(name or "").replace("\\", "/")).name).strip(" .")
    base = base or "ket-qua"
    return base if base.lower().endswith(ext) else base + ext


def _attach_output(db: Session, client: Optional[ApiClient], resp: dict, kind: str,
                   name, base_url: str) -> None:
    msg = ((resp.get("choices") or [{}])[0].get("message") or {})
    doc, rest = _extract(kind, msg.get("content") or "")
    if not doc:
        raise GatewayError(502, f"AI không trả về nội dung {kind.upper()} — thử lại hoặc nói rõ hơn yêu cầu",
                           "upstream_error", "no_output_file")
    now = datetime.utcnow()
    db.query(LlmFile).filter(LlmFile.expires_at < now).delete()    # dọn file hết hạn
    f = LlmFile(token=secrets.token_urlsafe(24), client_id=client.id if client else None,
                name=_file_name(name, kind), mime=OUTPUTS[kind]["mime"],
                data=doc.encode("utf-8"), expires_at=now + FILE_TTL)
    db.add(f)
    db.commit()
    url = f"{base_url.rstrip('/')}/v1/files/{f.token}/{f.name}"
    resp["files"] = [{"name": f.name, "mime": f.mime.split(";")[0], "size": len(f.data),
                      "url": url, "download_url": url + "?download=1",
                      "expires_at": f.expires_at.isoformat() + "Z"}]
    msg["content"] = rest or f"Đã tạo file {f.name}."


def _call(db: Session, target: Target, body: dict) -> dict:
    if target.provider.kind in CLI_KINDS:
        return _run_cli(db, target, body)
    return _post(target.provider, "/chat/completions", build_payload(target, body))


def _input_files(messages) -> list:
    """File client gửi kèm (data URL trong messages) → [{name, data(base64)}] cho in/
    của sandbox — cùng cách đặt tên với lúc gửi model, nên script gọi đúng tên."""
    files, taken = [], set()
    for m in messages or []:
        if isinstance(m, dict) and m.get("role") not in ("system", "developer"):
            _content(m.get("content"), files, taken)
    return [{"name": f["name"], "data": base64.b64encode(f["_raw"]).decode()} for f in files]


def _store_file(db: Session, client: Optional[ApiClient], name: str, mime: str, data: bytes,
                base_url: str) -> dict:
    now = datetime.utcnow()
    f = LlmFile(token=secrets.token_urlsafe(24), client_id=client.id if client else None,
                name=name, mime=mime, data=data, expires_at=now + FILE_TTL)
    db.add(f)
    db.commit()
    url = f"{base_url.rstrip('/')}/v1/files/{f.token}/{quote(f.name)}"
    return {"name": f.name, "mime": f.mime.split(";")[0], "size": len(f.data),
            "url": url, "download_url": url + "?download=1",
            "expires_at": f.expires_at.isoformat() + "Z"}


def _attach_generated(db: Session, client: Optional[ApiClient], target: Target, body: dict,
                      resp: dict, name, base_url: str) -> None:
    """AI viết script → sandbox chạy → cất file. Script lỗi thì gửi lỗi lại cho AI
    sửa (GEN_FIX_TRIES lần) — client gọi API không có cơ hội nhắn lại như khung chat."""
    inputs = _input_files(body.get("messages"))
    messages = list(body.get("messages") or [])
    for attempt in range(GEN_FIX_TRIES + 1):
        msg = ((resp.get("choices") or [{}])[0].get("message") or {})
        code, rest = sandbox_client.split(msg.get("content") or "")
        if not code:
            raise GatewayError(502, "AI không trả về script tạo file — thử lại hoặc nói rõ hơn yêu cầu",
                               "upstream_error", "no_output_file")
        res = sandbox_client.run(code, inputs)
        if res.get("ok") or attempt == GEN_FIX_TRIES:
            break
        messages += [{"role": "assistant", "content": msg.get("content") or ""},
                     {"role": "user", "content": "Script trên chạy lỗi:\n" + str(res.get("error"))[-3000:] +
                      "\nSửa lỗi và trả lại TOÀN BỘ script trong một khối python-file."}]
        fixed = _call(db, target, {**body, "messages": messages})
        # Cộng token của lần sửa vào usage trả client.
        u0, u1 = resp.get("usage") or {}, fixed.get("usage") or {}
        fixed["usage"] = {k: (u0.get(k) or 0) + (u1.get(k) or 0)
                          for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
                          if k in u0 or k in u1}
        resp.clear()
        resp.update(fixed)
    if not res.get("files"):
        raise GatewayError(502, f"Sandbox không tạo được file: {str(res.get('error'))[-1500:]}",
                           "upstream_error", "sandbox_error")
    db.query(LlmFile).filter(LlmFile.expires_at < datetime.utcnow()).delete()   # dọn file hết hạn
    gen = res["files"]
    out = []
    for i, f in enumerate(gen):
        fname = _gen_name(name, f.get("name") or "", len(gen), i)
        out.append(_store_file(db, client, fname, f.get("mime") or "application/octet-stream",
                               base64.b64decode(f.get("data") or ""), base_url))
    resp["files"] = out
    msg["content"] = rest or f"Đã tạo {len(out)} file."
    resp.setdefault("choices", [{}])[0]["message"] = msg


def _gen_name(wanted, got: str, count: int, i: int) -> str:
    """`output_name` của client đặt cho file (giữ đuôi thật script ghi ra);
    nhiều file thì thêm -2, -3…"""
    got = PurePath(got).name or "ket-qua"
    if not wanted:
        return got
    ext = PurePath(got).suffix
    base = re.sub(r"[^\w.\- ]+", "_", PurePath(str(wanted).replace("\\", "/")).name).strip(" .") or "ket-qua"
    if ext and base.lower().endswith(ext.lower()):
        base = base[: -len(ext)]
    return f"{base}{'' if i == 0 else f'-{i + 1}'}{ext}"


# ── claude_cli / grok_cli: chạy `<cli> -p` qua worker ──────────────────────

# File đính kèm theo chuẩn OpenAI — client dùng SDK OpenAI gửi y như gửi GPT:
#   {"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}}
#   {"type": "file", "file": {"filename": "hd.pdf", "file_data": "data:application/pdf;base64,…"}}
# Worker ghi ra thư mục riêng của job rồi cho CLI đọc (chỉ đọc). Giới hạn theo
# client_max_body_size 20m của nginx: base64 phình ~4/3 nên ~15 MB file thật.
MAX_FILES = 20
MAX_FILE_BYTES = 15 * 1024 * 1024
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp",
        "application/pdf": ".pdf", "text/plain": ".txt", "text/markdown": ".md",
        "text/csv": ".csv", "application/json": ".json"}


def _data_url(url: str, what: str) -> tuple[str, bytes]:
    """'data:<mime>;base64,<…>' → (mime, bytes). URL http(s) không nhận: worker
    tải hộ thì thành cửa cho client bắt server đi gọi chỗ khác."""
    if not isinstance(url, str) or not url.startswith("data:") or ";base64," not in url:
        raise GatewayError(400, f"{what}: chỉ nhận data URL base64 (data:<mime>;base64,…), "
                                "không nhận link http hay file_id", code="invalid_file")
    head, b64 = url[5:].split(";base64,", 1)
    try:
        return head or "application/octet-stream", base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise GatewayError(400, f"{what}: base64 không hợp lệ", code="invalid_file")


def _safe_name(name: str, mime: str, n: int, taken: set) -> str:
    """Tên file client gửi → tên an toàn trong thư mục job (không '..', không '/')."""
    base = re.sub(r"[^\w.\- ]+", "_", PurePath(str(name or "").replace("\\", "/")).name).strip(" .")
    if not base:
        base = f"{'image' if mime.startswith('image/') else 'file'}-{n}{_EXT.get(mime, '')}"
    stem, dot, ext = base.rpartition(".")
    stem, ext = (stem, "." + ext) if dot and stem else (base, "")
    out, i = base, 1
    while out.lower() in taken:
        i += 1
        out = f"{stem}-{i}{ext}"
    taken.add(out.lower())
    return out


def _content(content, files: list, taken: set) -> str:
    """content OpenAI (chuỗi hoặc danh sách part) → văn bản; part ảnh/file được
    tách vào `files` và để lại dấu [Đính kèm: tên] đúng chỗ trong tin nhắn."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    out = []
    for p in content:
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if kind == "text":
            out.append(p.get("text") or "")
            continue
        if kind == "image_url":
            img = p.get("image_url")
            mime, data = _data_url(img.get("url") if isinstance(img, dict) else img, "image_url")
            name = None
        elif kind == "file":
            f = p.get("file") or {}
            if f.get("file_id") and not f.get("file_data"):
                raise GatewayError(400, "file_id chưa hỗ trợ — gửi nội dung qua file.file_data "
                                        "(data:<mime>;base64,…)", code="invalid_file")
            mime, data = _data_url(f.get("file_data"), f"file {f.get('filename') or ''}".strip())
            name = f.get("filename")
        else:
            raise GatewayError(400, f"Chưa hỗ trợ part type '{kind}' — dùng text, image_url, file",
                               code="unsupported_content")
        if len(files) >= MAX_FILES:
            raise GatewayError(400, f"Tối đa {MAX_FILES} file mỗi request", code="too_many_files")
        if sum(len(x["_raw"]) for x in files) + len(data) > MAX_FILE_BYTES:
            raise GatewayError(413, f"Tổng dung lượng file vượt {MAX_FILE_BYTES // 1024 // 1024} MB",
                               code="files_too_large")
        name = _safe_name(name, mime, len(files) + 1, taken)
        files.append({"name": name, "mime": mime, "_raw": data})
        out.append(f"[Đính kèm: {name}]")
    return "\n".join(x for x in out if x)


def cli_prompt(target: Target, messages: list) -> tuple[str, str, list]:
    """`claude -p` / `grok -p` chỉ nhận 1 prompt → system gom riêng, hội thoại dàn thành văn
    bản, cùng kiểu khung chat dashboard (routers/assistant._build_prompt). Trả kèm
    danh sách file [{name, mime, data(base64)}] để worker ghi ra đĩa."""
    if not isinstance(messages, list) or not messages:
        raise GatewayError(400, "`messages` phải là danh sách không rỗng", code="invalid_messages")
    system = [target.system_prompt] if target.system_prompt else []
    turns, files, taken = [], [], set()
    for m in messages:
        role, text = m.get("role"), _content(m.get("content"), files, taken).strip()
        if not text:
            continue
        if role in ("system", "developer"):
            system.append(text)
        else:
            turns.append(f"{'Người dùng' if role == 'user' else 'Trợ lý'}: {text}")
    if not turns:
        raise GatewayError(400, "Không có tin nhắn user nào", code="invalid_messages")
    if len(turns) == 1 and turns[0].startswith("Người dùng: "):
        prompt = turns[0][len("Người dùng: "):]
    else:
        prompt = ("Đây là cuộc trò chuyện tới giờ. Hãy viết câu trả lời TIẾP THEO của Trợ lý "
                  "cho tin cuối của Người dùng — chỉ nội dung câu trả lời, không thêm tiền tố "
                  "\"Trợ lý:\".\n\n" + "\n\n".join(turns))
    files = [{"name": f["name"], "mime": f["mime"], "data": base64.b64encode(f["_raw"]).decode()}
             for f in files]
    return "\n\n".join(system), prompt, files


def _run_cli(db: Session, target: Target, body: dict) -> dict:
    system, prompt, files = cli_prompt(target, body.get("messages"))
    cli = CLI_KINDS[target.provider.kind][0]
    job = LlmCliJob(cli=cli, model=target.upstream_model or None, system=system, prompt=prompt,
                    files=files or None)
    db.add(job)
    db.commit()

    deadline = time.monotonic() + (target.provider.timeout_s or 300)
    while time.monotonic() < deadline:
        time.sleep(CLI_POLL_S)
        db.refresh(job)
        if job.status in ("done", "error"):
            break
    else:
        if job.status == "pending":      # worker chưa nhặt → huỷ, đừng chạy vô ích
            job.status, job.error, job.files = "error", "timeout trước khi worker nhận", None
            db.commit()
            raise GatewayError(504, "Worker không nhận job — worker.py trên host có đang chạy?",
                               "upstream_error", "worker_offline")
        raise GatewayError(504, f"{cli} -p chưa xong sau {target.provider.timeout_s}s",
                           "upstream_error", "upstream_timeout")

    if job.status == "error":
        raise GatewayError(502, f"{cli} -p lỗi: {job.error or 'không rõ'}", "upstream_error", "cli_error")
    u = job.usage or {}
    pt = (u.get("input") or 0) + (u.get("cache_write") or 0) + (u.get("cache_read") or 0)
    ct = u.get("output") or 0
    return {
        "id": f"chatcmpl-cli-{job.id}", "object": "chat.completion",
        "created": int(time.time()), "model": target.alias,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": job.result or ""}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
                  **({"cost": job.cost_usd} if job.cost_usd is not None else {})},
    }
