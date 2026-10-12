"""
API công khai cho hệ thống ngoài — chuẩn OpenAI, mount ở /v1
=============================================================

    GET  /v1/models              alias được phép dùng với key này
    POST /v1/chat/completions    chat (stream=false) — body JSON chuẩn OpenAI, HOẶC
                                 multipart/form-data để upload file thẳng (curl -F);
                                 thêm `output: "html"` → AI tạo file, trả link tải
    GET  /v1/files/<token>/<tên> file AI tạo — link bí mật, không cần key, hết hạn sau 24h

Lỗi trả đúng dạng OpenAI `{"error": {"message", "type", "code"}}` để SDK của
client hiểu được. Logic nằm ở llm_gateway.py.

Chỉ PUBLIC đường /v1 ra ngoài — /api/* của dashboard không có đăng nhập.
"""

import base64
import json
import mimetypes
import os
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
# request.form() trả UploadFile của starlette — fastapi.UploadFile là lớp con, isinstance hụt.
from starlette.datastructures import UploadFile

import llm_gateway as gw
from database import get_db
from models import LlmFile

router = APIRouter()


def _err(e: gw.GatewayError) -> JSONResponse:
    return JSONResponse(status_code=e.status, content=e.body())


@router.get("/models")
def models(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    try:
        client = gw.authenticate(db, authorization)
    except gw.GatewayError as e:
        return _err(e)
    return {"object": "list", "data": gw.list_models(db, client)}


@router.post("/chat/completions")
async def chat_completions(request: Request, authorization: Optional[str] = Header(None),
                           db: Session = Depends(get_db)):
    try:
        client = gw.authenticate(db, authorization)
        ctype = request.headers.get("content-type", "").lower()
        body = await (_form(request) if ctype.startswith("multipart/form-data") else _json(request))
        # Gọi upstream là urllib chặn tới vài phút → đẩy sang threadpool, không
        # để treo event loop (kéo theo cả dashboard).
        return await run_in_threadpool(gw.chat, db, client, body, _public_base(request))
    except gw.GatewayError as e:
        return _err(e)


def _public_base(request: Request) -> str:
    """Gốc URL để dựng link tải file — đúng host client đã gọi tới (qua nginx :3100
    hay thẳng :8100). Public qua tên miền/proxy khác thì đặt LLM_PUBLIC_BASE_URL."""
    env = os.getenv("LLM_PUBLIC_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


@router.get("/files/{token}/{name}")
@router.get("/files/{token}")
def download_file(token: str, name: str = "", download: bool = False, db: Session = Depends(get_db)):
    """Không đòi API key: link phải mở được trong trình duyệt và gửi đi được. Token
    24 byte ngẫu nhiên là chìa khoá; hết hạn thì 404 như không tồn tại."""
    f = db.query(LlmFile).filter(LlmFile.token == token).first()
    if not f or f.expires_at < datetime.utcnow():
        return _err(gw.GatewayError(404, "File không tồn tại hoặc đã hết hạn", code="file_not_found"))
    disp = "attachment" if download else "inline"
    return Response(f.data, media_type=f.mime, headers={
        "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(f.name)}",
        # HTML do AI viết chạy trong origin riêng (sandbox): script vẫn chạy nhưng
        # không đụng được cookie/API của dashboard cùng host.
        "Content-Security-Policy": "sandbox allow-scripts allow-popups allow-forms allow-modals allow-downloads",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
    })


async def _json(request: Request) -> dict:
    try:
        body = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        raise gw.GatewayError(400, "Body không phải JSON", code="invalid_json")
    if not isinstance(body, dict):
        raise gw.GatewayError(400, "Body phải là object JSON", code="invalid_json")
    return body


# ── multipart/form-data: upload file thẳng, không phải tự base64 ───────────
#
#   curl …/v1/chat/completions -H "Authorization: Bearer $KEY" #        -F model=grok-test -F prompt="Tóm tắt các file" #        -F files=@hop-dong.pdf -F files=@anh.png
#
# Đổi sang đúng body JSON chuẩn OpenAI (file → part image_url / file data URL)
# rồi đi chung đường với request JSON — kiểm tra, giới hạn, provider y hệt.

_FORM_NUM = {"temperature": float, "top_p": float, "max_tokens": int,
             "max_completion_tokens": int, "seed": int,
             "presence_penalty": float, "frequency_penalty": float}


async def _form(request: Request) -> dict:
    try:
        # Giới hạn số part để form rác không ngốn RAM; dung lượng do nginx chặn (20m).
        form = await request.form(max_files=gw.MAX_FILES + 1, max_fields=50)
    except Exception as e:
        if "too many files" in str(e).lower():
            raise gw.GatewayError(400, f"Tối đa {gw.MAX_FILES} file mỗi request", code="too_many_files")
        raise gw.GatewayError(400, f"Form không đọc được: {e}", code="invalid_form")

    body: dict = {"model": str(form.get("model") or "")}
    if form.get("messages"):
        try:
            messages = json.loads(str(form["messages"]))
        except json.JSONDecodeError:
            raise gw.GatewayError(400, "Trường `messages` phải là JSON", code="invalid_messages")
        if not isinstance(messages, list) or not messages:
            raise gw.GatewayError(400, "`messages` phải là danh sách không rỗng", code="invalid_messages")
    elif str(form.get("prompt") or "").strip():
        messages = [{"role": "user", "content": str(form["prompt"])}]
    else:
        raise gw.GatewayError(400, "Thiếu `prompt` (hoặc `messages` dạng JSON)", code="invalid_messages")
    if str(form.get("system") or "").strip():
        messages = [{"role": "system", "content": str(form["system"])}] + messages

    # File: mọi trường là file upload, tên trường nào cũng được (files, file, files[]…).
    parts = []
    for _, v in form.multi_items():
        if not isinstance(v, UploadFile):
            continue
        data = await v.read()
        if not data:
            continue
        mime = (v.content_type or "").split(";")[0].strip().lower()
        if not mime or mime == "application/octet-stream":
            mime = mimetypes.guess_type(v.filename or "")[0] or "application/octet-stream"
        url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        parts.append({"type": "image_url", "image_url": {"url": url}} if mime.startswith("image/")
                     else {"type": "file", "file": {"filename": v.filename or "", "file_data": url}})
    if parts:
        # Gắn vào tin user CUỐI — câu đang hỏi về các file này.
        last = next((m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "user"), None)
        if last is None:
            raise gw.GatewayError(400, "Gửi file thì phải có tin nhắn user", code="invalid_messages")
        text = last.get("content")
        last["content"] = ([{"type": "text", "text": text}] if isinstance(text, str) and text
                           else list(text) if isinstance(text, list) else []) + parts
    body["messages"] = messages

    for k, cast in _FORM_NUM.items():
        if form.get(k) not in (None, ""):
            try:
                body[k] = cast(form[k])
            except ValueError:
                raise gw.GatewayError(400, f"`{k}` phải là số", code="invalid_param")
    if form.get("stop"):
        body["stop"] = str(form["stop"])
    for k in ("output", "output_name"):
        if str(form.get(k) or "").strip():
            body[k] = str(form[k]).strip()
    return body
