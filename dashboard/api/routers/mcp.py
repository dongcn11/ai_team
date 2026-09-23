"""
MCP API
=======
Cấu hình MCP theo từng dự án (xem docstring mcp_store.py).

Route tĩnh `/templates` khai TRƯỚC `/{slug}`, nếu không FastAPI khớp "templates"
thành tên một dự án — đúng cái bẫy skills.py đã dẫm phải.

KHÔNG endpoint nào ở đây trả về giá trị credential. Chỉ có cờ `credential_declared`.
"""
from typing import List

from fastapi import APIRouter, HTTPException

import mcp_store
from schemas import McpConfigIn, McpConfigOut, McpTemplateOut

router = APIRouter()


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except mcp_store.McpError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/templates", response_model=List[McpTemplateOut])
def list_templates():
    """Mẫu server dựng sẵn. Chỉ chạy được server trong danh sách này — thêm mẫu
    mới phải sửa config/mcp_templates.toml trên host, có chủ đích."""
    return _guard(mcp_store.templates)


@router.get("/{slug}", response_model=McpConfigOut)
def read_config(slug: str):
    return _guard(mcp_store.read, slug)


@router.put("/{slug}", response_model=McpConfigOut)
def write_config(slug: str, body: McpConfigIn):
    return _guard(mcp_store.write, slug, body.model_dump())
