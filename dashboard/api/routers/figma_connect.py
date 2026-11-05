"""
Kết nối Figma cho MCP server `figma` của từng dự án — dán token trên dashboard
==============================================================================

Nối THẲNG ai_team với Figma, không qua connector của tài khoản Claude: mỗi dự án
dùng personal access token Figma của chính nó (Figma → Settings → Security →
Personal access tokens). Chọn token thay vì OAuth vì OAuth của Figma cũng bắt
đăng ký app trên figma.com — token thì người dùng tự tạo trong 30 giây.

POST /{slug}/{server}  {token}  → gọi GET /v1/me để kiểm token, rồi ghi
     clients/<slug>/secrets/figma-<server>.json và đặt [mcp.<server>]
     credentials_path trong settings.local.toml (cùng cách routers/google_oauth.py).
GET  /{slug}/{server}           → {connected, account} — KHÔNG trả token.
POST /{slug}/{server}/disconnect → xoá file + bỏ credentials_path.
"""
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from routers.google_oauth import _check, _set_credentials_path

router = APIRouter()


class TokenIn(BaseModel):
    token: str


def _token_file(proj, server: str):
    return proj / "secrets" / f"figma-{server}.json"


def _me(token: str) -> dict:
    req = urllib.request.Request("https://api.figma.com/v1/me", headers={"X-Figma-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise HTTPException(400, "Figma từ chối token này (sai, hết hạn, hoặc thiếu quyền "
                                     "\"File content: Read\"). Tạo token mới rồi dán lại.")
        raise HTTPException(502, f"Figma trả lỗi {e.code} khi kiểm token.")
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Không gọi được Figma: {e.reason}")


@router.get("/{slug}/{server}")
def status(slug: str, server: str, request: Request):
    f = _token_file(_check(request, slug, server), server)
    if not f.exists():
        return {"connected": False, "account": None}
    try:
        account = json.loads(f.read_text(encoding="utf-8")).get("account")
    except ValueError:
        account = None
    return {"connected": True, "account": account}


@router.post("/{slug}/{server}")
def connect(slug: str, server: str, body: TokenIn, request: Request):
    proj = _check(request, slug, server)
    token = body.token.strip()
    if not token or len(token) > 200 or any(c.isspace() for c in token):
        raise HTTPException(400, "Token không hợp lệ — dán đúng chuỗi Figma hiện ra lúc tạo (figd_…).")
    me = _me(token)
    account = me.get("email") or me.get("handle")
    f = _token_file(proj, server)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"type": "figma_pat", "token": token, "account": account,
                             "handle": me.get("handle")}, indent=2), encoding="utf-8")
    # Tương đối gốc ai_team — worker/server tự đổi sang tuyệt đối.
    _set_credentials_path(proj / "settings.local.toml", server, f"clients/{slug}/secrets/{f.name}")
    return {"connected": True, "account": account}


@router.post("/{slug}/{server}/disconnect")
def disconnect(slug: str, server: str, request: Request):
    proj = _check(request, slug, server)
    f = _token_file(proj, server)
    if f.exists():
        f.unlink()
    _set_credentials_path(proj / "settings.local.toml", server, None)
    return {"connected": False, "account": None}
