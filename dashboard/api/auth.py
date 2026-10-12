"""
Đăng nhập dashboard — tài khoản, phiên, quyền theo màn hình
============================================================

Phiên: token ngẫu nhiên trong cookie httpOnly `ait_session` (JS không đọc được),
DB chỉ giữ sha256 của token. Trình duyệt tự gửi cookie cho mọi fetch/<img> cùng
origin nên frontend không phải gắn header vào từng lần gọi.

Middleware `guard` chặn mọi /api/* khi chưa đăng nhập, trừ:
  - /api/auth/status|login        — để còn đăng nhập được (không có đăng ký)
  - /api/slack/*                  — Slack gọi vào, đã có chữ ký riêng
  - đường của MÁY (worker.py, pipeline main.py) — xem _MACHINE. Đặt env
    WORKER_TOKEN (cả API lẫn worker) thì các đường này đòi header X-Worker-Token;
    để trống thì mở như trước khi có đăng nhập — worker cũ vẫn chạy.
/v1/* (gateway, có API key riêng) và /health không đi qua đây.

Quyền theo dự án: `projects` = slug dự án được gán (admin thấy hết). Middleware
ghi request.state.projects (None = mọi dự án, set = chỉ các slug này) và chặn
/api/projects/<slug>/… ngoài danh sách; các router lọc danh sách qua
`allowed_projects(request)`.

Quyền theo màn hình: `permissions` = khoá tab (TABS). Ẩn tab là việc của
frontend; ở đây chỉ chặn thêm các API mà CHỈ màn hình đó dùng (_SCREEN_API) —
đọc lẫn ghi với màn hình chứa bí mật (settings, api, bots), chỉ ghi với phần còn
lại vì màn hình khác vẫn cần đọc (Workflows đọc danh sách skill…).
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from database import SessionLocal
from models import User, UserSession

COOKIE = "ait_session"
SESSION_DAYS = 30
WORKER_TOKEN = os.getenv("WORKER_TOKEN", "").strip()

# Khoá tab trong dashboard/src/App.tsx. Tài khoản mới mặc định chỉ có dashboard.
TABS = ["dashboard", "pipeline", "projects", "agents", "skills", "workflows",
        "runs", "bots", "api", "logs", "settings"]
DEFAULT_PERMISSIONS = ["dashboard"]

_PUBLIC = {"/api/auth/status", "/api/auth/login"}

# (method, regex) — các lần gọi của worker.py và ai_team/task_manager.py.
_MACHINE = [(m, re.compile(p)) for m, p in [
    ("POST", r"/api/assistant/claim"),
    ("POST", r"/api/assistant/messages/\d+/complete"),
    ("POST", r"/api/llm/cli-jobs/claim"),
    ("POST", r"/api/llm/cli-jobs/\d+/complete"),
    ("POST", r"/api/run-jobs/claim"),
    ("POST", r"/api/run-jobs/\d+/complete"),
    ("POST", r"/api/workflow-jobs/claim"),
    ("POST", r"/api/workflow-jobs/\d+/(complete|progress)"),
    ("POST", r"/api/runs/?"),
    ("POST", r"/api/tasks/update"),
    ("POST", r"/api/issues/?"),
]]

# tiền tố API → (màn hình, chặn cả đọc?)
_SCREEN_API = [
    ("/api/settings",      "settings", True),
    ("/api/llm",           "api",      True),
    ("/api/chat-bots",     "bots",     True),
    ("/api/mcp",           "projects", False),
    ("/api/projects",      "projects", False),
    ("/api/project-tasks", "projects", False),
    ("/api/schedules",     "projects", False),
    ("/api/skills",        "skills",   False),
    ("/api/agents",        "agents",   False),
]


_PROJECT_PATH = re.compile(r"/api/projects/([^/]+)")
_PROJECT_NON_SLUG = {"defaults", "profiles"}       # đường tĩnh của router projects


# ── Mật khẩu ────────────────────────────────────────────────────────────────
# pbkdf2 có sẵn trong hashlib — khỏi thêm thư viện vào image.

_ROUNDS = 260_000


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), _ROUNDS).hex()
    return f"pbkdf2_sha256${_ROUNDS}${salt}${h}"


def check_password(pw: str, stored: str) -> bool:
    try:
        algo, rounds, salt, h = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    got = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(got, h)


# ── Phiên ───────────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(db, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(UserSession(token_hash=_token_hash(token), user_id=user.id,
                       expires_at=now + timedelta(days=SESSION_DAYS)))
    db.query(UserSession).filter(UserSession.expires_at < now).delete()   # dọn phiên hết hạn
    user.last_login_at = now
    db.commit()
    return token


def drop_session(db, token: Optional[str]) -> None:
    if token:
        db.query(UserSession).filter(UserSession.token_hash == _token_hash(token)).delete()
        db.commit()


def user_from_token(db, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    s = db.query(UserSession).filter(UserSession.token_hash == _token_hash(token)).first()
    if not s or s.expires_at < datetime.utcnow():
        return None
    u = db.query(User).filter(User.id == s.user_id).first()
    return u if u and u.is_active else None


def set_cookie(response, request: Request, token: str) -> None:
    # Secure chỉ khi đi https (nginx báo qua X-Forwarded-Proto) — chạy http nội bộ
    # mà bật Secure thì trình duyệt vứt cookie, không đăng nhập được.
    https = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=https, path="/")


def permissions_of(u: User) -> list:
    if u.is_admin:
        return list(TABS)
    return [t for t in (u.permissions or DEFAULT_PERMISSIONS) if t in TABS]


def projects_of(u: User) -> Optional[set]:
    """None = mọi dự án (admin); set = chỉ các slug này."""
    return None if u.is_admin else set(u.projects or [])


def allowed_projects(request: Request) -> Optional[set]:
    return getattr(request.state, "projects", None)


def project_ok(request: Request, slug: Optional[str]) -> bool:
    allowed = allowed_projects(request)
    return allowed is None or (bool(slug) and slug in allowed)


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username,
            "is_admin": bool(u.is_admin), "is_active": bool(u.is_active),
            "permissions": permissions_of(u), "projects": sorted(u.projects or []),
            "models": None if u.models is None else list(u.models),   # None = tất cả
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}


# ── Chống dò mật khẩu ───────────────────────────────────────────────────────
# Trong RAM, theo IP: sai 8 lần trong 10 phút thì khoá IP đó 10 phút.

_FAILS: dict = {}
_FAIL_MAX, _FAIL_WINDOW = 8, 600


def login_blocked(ip: str) -> int:
    """Số giây còn bị khoá (0 = được thử)."""
    now = time.time()
    hits = [t for t in _FAILS.get(ip, []) if now - t < _FAIL_WINDOW]
    _FAILS[ip] = hits
    return int(_FAIL_WINDOW - (now - hits[0])) + 1 if len(hits) >= _FAIL_MAX else 0


def login_failed(ip: str) -> None:
    _FAILS.setdefault(ip, []).append(time.time())


def login_ok(ip: str) -> None:
    _FAILS.pop(ip, None)


def client_ip(request: Request) -> str:
    return (request.headers.get("x-real-ip")
            or (request.client.host if request.client else "") or "?")


# ── Middleware ──────────────────────────────────────────────────────────────

def _deny(code: int, msg: str) -> JSONResponse:
    return JSONResponse({"detail": msg}, status_code=code)


async def guard(request: Request, call_next):
    path, method = request.url.path, request.method
    if not path.startswith("/api/") or method == "OPTIONS" or path in _PUBLIC \
            or path.startswith("/api/slack/"):
        return await call_next(request)

    if any(m == method and rx.fullmatch(path) for m, rx in _MACHINE):
        if WORKER_TOKEN and not hmac.compare_digest(
                request.headers.get("x-worker-token", ""), WORKER_TOKEN):
            return _deny(401, "Thiếu hoặc sai X-Worker-Token")
        return await call_next(request)

    db = SessionLocal()
    try:
        u = user_from_token(db, request.cookies.get(COOKIE))
        if not u:
            return _deny(401, "Chưa đăng nhập")
        if path.startswith("/api/auth/users") and not u.is_admin:
            return _deny(403, "Chỉ quản trị viên mới quản lý tài khoản")
        if not u.is_admin:
            perms = set(permissions_of(u))
            for prefix, screen, all_methods in _SCREEN_API:
                if (path == prefix or path.startswith(prefix + "/")) \
                        and screen not in perms and (all_methods or method != "GET"):
                    return _deny(403, f"Tài khoản không có quyền màn hình '{screen}'")
            allowed = projects_of(u)
            m = _PROJECT_PATH.match(path)
            if m and m.group(1) not in _PROJECT_NON_SLUG and m.group(1) not in allowed:
                return _deny(403, f"Tài khoản không được gán dự án '{m.group(1)}'")
        request.state.user_id = u.id
        request.state.projects = projects_of(u)
    finally:
        db.close()
    return await call_next(request)
