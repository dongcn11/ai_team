"""
Kết nối Google (OAuth) cho MCP server của từng dự án — bấm nút trên dashboard
==============================================================================

Thay cho `python tools/google_login.py`: tab MCP của dự án có nút "Kết nối
Google", đăng nhập bằng tài khoản Google của CHÍNH dự án đó. Mỗi dự án một tài
khoản, không ai thấy Drive của dự án khác.

Vì sao OAuth chứ không chỉ service account: service account không có dung lượng
lưu trữ, Gmail cá nhân không có Shared Drive ⇒ service account không tạo nổi một
file nào trong "Drive của tôi" dù đã được share quyền Người chỉnh sửa.

Luồng:
  1. Admin dán 1 lần file JSON của OAuth client (Google Cloud → Credentials → OAuth
     client ID, loại "Web application", redirect URI = GET /client trả về). Lưu
     trong bảng settings, khoá `google_oauth_client` — cùng chỗ token bot chat.
  2. POST /{slug}/{server}/connect → URL đăng nhập Google (PKCE + state).
  3. Google chuyển trình duyệt về GET /callback. Cookie phiên là SameSite=Lax nên
     vẫn đăng nhập dashboard như thường; state ràng buộc với đúng người + dự án.
  4. Đổi code lấy refresh token → ghi clients/<slug>/secrets/google-oauth-<server>.json
     (định dạng `authorized_user` chuẩn của Google, server MCP đọc thẳng) và đặt
     [mcp.<server>] credentials_path trong clients/<slug>/settings.local.toml.

RANH GIỚI BÍ MẬT — ngoại lệ có chủ đích so với mcp_store.py: API ở đây GHI file
token và MỘT khoá của settings.local.toml, vì luồng OAuth của trình duyệt chỉ về
được tới API. Nhưng KHÔNG endpoint nào trả token ra: trạng thái chỉ có email tài
khoản đã kết nối. clients/ đã nằm trong .gitignore.
"""
import base64
import hashlib
import html
import json
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import mcp_store
from database import get_db
from models import Setting

router = APIRouter()

SETTING_KEY = "google_oauth_client"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Toàn quyền Drive: drive.file chỉ thấy file do chính ứng dụng tạo, không ghi được
# vào thư mục có sẵn của người dùng. Hàng rào thật là danh sách tool của server MCP.
SCOPES = ["https://www.googleapis.com/auth/drive", "openid", "email"]
STATE_TTL_S = 600
CALLBACK_PATH = "/api/mcp/google/callback"

# state → {slug, server, verifier, redirect, user_id, exp}. Trong bộ nhớ: mất khi API
# restart thì người dùng bấm Kết nối lại — chấp nhận được cho một thao tác 1 phút.
_pending: dict[str, dict] = {}


# ── Cấu hình OAuth client (1 cái cho cả hệ thống) ────────────────────────────

def _client(db: Session) -> Optional[dict]:
    row = db.query(Setting).filter(Setting.key == SETTING_KEY).first()
    if not row or not row.value:
        return None
    try:
        return json.loads(row.value)
    except ValueError:
        return None


def _redirect_uri(request: Request) -> str:
    """URL Google chuyển về — phải KHỚP ĐÚNG redirect URI khai trên Google Cloud.
    Dựng từ chính địa chỉ người dùng đang mở dashboard (nginx giữ Host + proto)."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}{CALLBACK_PATH}"


def _require_admin(request: Request) -> None:
    if auth.allowed_projects(request) is not None:        # None = admin (thấy mọi dự án)
        raise HTTPException(403, "Chỉ admin mới cấu hình được OAuth client.")


class ClientIn(BaseModel):
    json_text: str


@router.get("/client")
def get_client(request: Request, db: Session = Depends(get_db)):
    c = _client(db)
    return {"configured": bool(c), "client_id": (c or {}).get("client_id"),
            "redirect_uri": _redirect_uri(request)}


@router.put("/client")
def put_client(body: ClientIn, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    try:
        raw = json.loads(body.json_text)
    except ValueError:
        raise HTTPException(400, "Không phải JSON. Dán nguyên nội dung file tải về khi tạo OAuth client ID.")
    block = raw.get("web") or raw.get("installed") if isinstance(raw, dict) else None
    if not isinstance(block, dict) or not block.get("client_id") or not block.get("client_secret"):
        raise HTTPException(400, "File thiếu client_id/client_secret. Tải lại file JSON ở "
                                 "Google Cloud → Credentials → OAuth 2.0 Client IDs.")
    if "installed" in raw:
        raise HTTPException(400, "Đây là client loại \"Desktop app\" — kết nối qua web cần loại "
                                 "\"Web application\" (khai được redirect URI). Tạo client mới loại Web.")
    value = json.dumps({"client_id": block["client_id"], "client_secret": block["client_secret"]})
    row = db.query(Setting).filter(Setting.key == SETTING_KEY).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=SETTING_KEY, value=value))
    db.commit()
    return get_client(request, db)


# ── Trạng thái / kết nối / ngắt theo dự án ───────────────────────────────────

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _check(request: Request, slug: str, server: str) -> Path:
    if not _SLUG_RE.match(slug) or not mcp_store.NAME_RE.match(server):
        raise HTTPException(400, "Tên dự án hoặc server không hợp lệ.")
    if not auth.project_ok(request, slug):
        raise HTTPException(403, f"Bạn không được gán dự án '{slug}'.")
    proj = mcp_store.CLIENTS_DIR / slug
    if not proj.is_dir():
        raise HTTPException(404, f"Không có dự án '{slug}'.")
    return proj


def _token_file(proj: Path, server: str) -> Path:
    return proj / "secrets" / f"google-oauth-{server}.json"


@router.get("/{slug}/{server}")
def status(slug: str, server: str, request: Request):
    """Chỉ trả email đã kết nối — không bao giờ trả token."""
    f = _token_file(_check(request, slug, server), server)
    if not f.exists():
        return {"connected": False, "account": None}
    try:
        account = json.loads(f.read_text(encoding="utf-8")).get("account")
    except ValueError:
        account = None
    return {"connected": True, "account": account}


@router.post("/{slug}/{server}/connect")
def connect(slug: str, server: str, request: Request, db: Session = Depends(get_db)):
    _check(request, slug, server)
    c = _client(db)
    if not c:
        raise HTTPException(400, "Chưa cấu hình OAuth client — admin dán file JSON ở mục Kết nối Google trước.")
    now = time.time()
    for k in [k for k, v in _pending.items() if v["exp"] < now]:
        _pending.pop(k, None)
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    redirect = _redirect_uri(request)
    _pending[state] = {"slug": slug, "server": server, "verifier": verifier, "redirect": redirect,
                       "user_id": getattr(request.state, "user_id", None), "exp": now + STATE_TTL_S}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        # offline + consent: bắt Google trả refresh_token (thiếu thì token chết sau 1 giờ)
        "access_type": "offline", "prompt": "consent select_account",
    })
    return {"url": url}


@router.post("/{slug}/{server}/disconnect")
def disconnect(slug: str, server: str, request: Request):
    proj = _check(request, slug, server)
    f = _token_file(proj, server)
    if f.exists():
        try:
            tok = json.loads(f.read_text(encoding="utf-8")).get("refresh_token")
            if tok:   # thu hồi phía Google — hỏng cũng xoá file, đừng giữ token mồ côi
                _post(REVOKE_URL, {"token": tok})
        except Exception:
            pass
        f.unlink()
    _set_credentials_path(proj / "settings.local.toml", server, None)
    return {"connected": False, "account": None}


# ── Callback ─────────────────────────────────────────────────────────────────

def _page(title: str, body: str, ok: bool) -> HTMLResponse:
    color = "#16a34a" if ok else "#dc2626"
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>Kết nối Google</title>"
        "<body style='font:15px system-ui,sans-serif;background:#0b1220;color:#e2e8f0;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>"
        f"<div style='max-width:520px;padding:24px;border:1px solid #1e293b;border-radius:10px'>"
        f"<h2 style='margin:0 0 10px;color:{color}'>{html.escape(title)}</h2>"
        f"<p style='line-height:1.6'>{body}</p>"
        "<p style='color:#94a3b8'>Đóng tab này và quay lại dashboard (tab MCP tự cập nhật).</p>"
        "<script>try{window.opener&&window.opener.postMessage('google-oauth-done','*')}catch(e){}"
        "</script></div></body>", status_code=200 if ok else 400)


def _post(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    return json.loads(body) if body else {}


@router.get("/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = "",
             db: Session = Depends(get_db)):
    p = _pending.pop(state, None)
    if not p or p["exp"] < time.time():
        return _page("Phiên kết nối đã hết hạn", "Bấm <b>Kết nối Google</b> lại trên dashboard.", False)
    if p["user_id"] != getattr(request.state, "user_id", None) or not auth.project_ok(request, p["slug"]):
        return _page("Sai phiên đăng nhập", "Người bấm Kết nối và người hoàn tất không phải một.", False)
    if error:
        msg = "Bạn đã bấm Huỷ." if error == "access_denied" else f"Google báo lỗi: {html.escape(error)}."
        return _page("Chưa kết nối", msg, False)
    c = _client(db)
    if not c:
        return _page("Thiếu OAuth client", "Cấu hình OAuth client đã bị xoá giữa chừng.", False)

    try:
        tok = _post(TOKEN_URL, {"code": code, "client_id": c["client_id"],
                                "client_secret": c["client_secret"], "redirect_uri": p["redirect"],
                                "grant_type": "authorization_code", "code_verifier": p["verifier"]})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        return _page("Google từ chối đổi mã", html.escape(detail), False)
    if not tok.get("refresh_token"):
        return _page("Google không trả refresh token",
                     "Vào <a style='color:#93c5fd' href='https://myaccount.google.com/permissions'>"
                     "myaccount.google.com/permissions</a>, gỡ quyền của ứng dụng rồi kết nối lại.", False)
    if "https://www.googleapis.com/auth/drive" not in tok.get("scope", ""):
        return _page("Chưa cấp quyền Google Drive",
                     "Ở màn hình xin quyền phải tick ô Google Drive. Kết nối lại và tick đủ.", False)
    try:
        req = urllib.request.Request("https://www.googleapis.com/drive/v3/about?fields=user",
                                     headers={"Authorization": f"Bearer {tok['access_token']}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            account = json.loads(r.read())["user"].get("emailAddress")
    except Exception:
        account = None

    proj = mcp_store.CLIENTS_DIR / p["slug"]
    f = _token_file(proj, p["server"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({
        "type": "authorized_user", "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": tok["refresh_token"], "account": account,
    }, indent=2), encoding="utf-8")
    # Đường dẫn TƯƠNG ĐỐI gốc ai_team: API thấy /clients, worker thấy <repo>/clients —
    # worker tự đổi thành tuyệt đối (MCP.secrets).
    _set_credentials_path(proj / "settings.local.toml", p["server"],
                          f"clients/{p['slug']}/secrets/{f.name}")
    return _page("Đã kết nối Google",
                 f"Dự án <b>{html.escape(p['slug'])}</b> · server <b>{html.escape(p['server'])}</b> "
                 f"dùng tài khoản <b>{html.escape(account or '?')}</b>. Bước kế tiếp của dự án tự "
                 "dùng tài khoản này, không cần khởi động lại worker.", True)


def _set_credentials_path(settings: Path, server: str, value: Optional[str]) -> None:
    """Đặt (hoặc bỏ, khi value=None) [mcp.<server>] credentials_path; giữ nguyên mọi
    dòng khác của file — trong đó còn token git và các khoá bí mật khác."""
    text = settings.read_text(encoding="utf-8") if settings.exists() else ""
    m = re.search(rf"^\[mcp\.{re.escape(server)}\][ \t]*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    # [ \t]* chứ không \s*: \s nuốt cả dấu xuống dòng, dính dòng vào tiêu đề mục.
    key = re.compile(r"^[ \t]*credentials_path[ \t]*=.*\n?", re.M)
    if value is None:
        if m:
            text = text[:m.start(1)] + key.sub("", m.group(1), count=1) + text[m.end(1):]
    else:
        line = f'credentials_path = "{value}"\n'
        if not m:
            text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"[mcp.{server}]\n{line}"
        elif key.search(m.group(1)):
            text = text[:m.start(1)] + key.sub(line, m.group(1), count=1) + text[m.end(1):]
        else:
            text = text[:m.start(1)] + "\n" + line.rstrip("\n") + m.group(1) + text[m.end(1):]
    settings.write_text(text, encoding="utf-8")
