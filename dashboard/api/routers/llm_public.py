"""
API công khai cho hệ thống ngoài — chuẩn OpenAI, mount ở /v1
=============================================================

    GET  /v1/models              alias được phép dùng với key này
    POST /v1/chat/completions    chat (stream=false)

Lỗi trả đúng dạng OpenAI `{"error": {"message", "type", "code"}}` để SDK của
client hiểu được. Logic nằm ở llm_gateway.py.

Chỉ PUBLIC đường /v1 ra ngoài — /api/* của dashboard không có đăng nhập.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import llm_gateway as gw
from database import get_db

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
        body = await _json(request)
        # Gọi upstream là urllib chặn tới vài phút → đẩy sang threadpool, không
        # để treo event loop (kéo theo cả dashboard).
        return await run_in_threadpool(gw.chat, db, client, body)
    except gw.GatewayError as e:
        return _err(e)


async def _json(request: Request) -> dict:
    try:
        body = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        raise gw.GatewayError(400, "Body không phải JSON", code="invalid_json")
    if not isinstance(body, dict):
        raise gw.GatewayError(400, "Body phải là object JSON", code="invalid_json")
    return body
