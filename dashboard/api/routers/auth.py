"""Đăng nhập / đăng xuất / đổi mật khẩu + quản lý tài khoản (chỉ admin).
Cơ chế phiên và phân quyền: xem auth.py."""

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
from database import get_db
from models import User, UserSession

router = APIRouter()

_USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{1,31}")
_PW_MIN = 6


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = None          # trống khi sửa = giữ mật khẩu cũ
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    permissions: Optional[List[str]] = None
    projects: Optional[List[str]] = None    # slug dự án được gán
    models: Optional[List[str]] = None      # khoá chat_models; null = mọi model


def _username(s: str) -> str:
    u = (s or "").strip().lower()
    if not _USERNAME.fullmatch(u):
        raise HTTPException(status_code=400, detail=(
            "Tên đăng nhập 2–32 ký tự: chữ thường không dấu, số, dấu . _ -"))
    return u


def _password(pw: Optional[str]) -> str:
    if not pw or len(pw) < _PW_MIN:
        raise HTTPException(status_code=400, detail=f"Mật khẩu tối thiểu {_PW_MIN} ký tự")
    return pw


def _perms(p: Optional[List[str]]) -> List[str]:
    out = [t for t in auth.TABS if t in set(p or [])]
    return out or list(auth.DEFAULT_PERMISSIONS)


def _projects(p: Optional[List[str]]) -> List[str]:
    """Chỉ giữ slug có thư mục dự án thật."""
    from routers.projects import CLIENTS_DIR
    return sorted({s for s in (p or []) if s and "/" not in s and "\\" not in s
                   and not s.startswith(".") and (CLIENTS_DIR / s).is_dir()})


def _models(m: Optional[List[str]]) -> Optional[List[str]]:
    """None = mọi model. Danh sách giữ nguyên khoá kể cả model đang tắt — bật lại
    là người đó dùng được tiếp, không phải gán lại."""
    return None if m is None else list(dict.fromkeys(k for k in m if isinstance(k, str) and k))


def _me(request: Request, db: Session) -> User:
    u = auth.user_from_token(db, request.cookies.get(auth.COOKIE))
    if not u:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")
    return u


def _other_admins(db: Session, user_id: int) -> int:
    return db.query(User).filter(User.is_admin.is_(True), User.is_active.is_(True),
                                 User.id != user_id).count()


@router.get("/status")
def status(request: Request, db: Session = Depends(get_db)) -> dict:
    """Màn hình đăng nhập gọi đầu tiên: user hiện tại (null = chưa đăng nhập).
    Không có đăng ký — tài khoản do admin tạo ở màn Tài khoản, tài khoản đầu
    tiên tạo bằng `python reset_password.py` trong container api."""
    u = auth.user_from_token(db, request.cookies.get(auth.COOKIE))
    return {"user": auth.user_out(u) if u else None,
            "tabs": auth.TABS}


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = auth.client_ip(request)
    wait = auth.login_blocked(ip)
    if wait:
        raise HTTPException(status_code=429, detail=f"Sai quá nhiều lần — thử lại sau {wait // 60 + 1} phút")
    u = db.query(User).filter(User.username == (payload.username or "").strip().lower()).first()
    if not u or not auth.check_password(payload.password or "", u.password_hash):
        auth.login_failed(ip)
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")
    if not u.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khoá — liên hệ quản trị viên")
    auth.login_ok(ip)
    auth.set_cookie(response, request, auth.new_session(db, u))
    return auth.user_out(u)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    auth.drop_session(db, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(payload: PasswordIn, request: Request, db: Session = Depends(get_db)) -> dict:
    u = _me(request, db)
    if not auth.check_password(payload.current_password or "", u.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    u.password_hash = auth.hash_password(_password(payload.new_password))
    # Đăng xuất mọi máy khác, giữ phiên đang dùng.
    keep = auth._token_hash(request.cookies.get(auth.COOKIE) or "")
    db.query(UserSession).filter(UserSession.user_id == u.id, UserSession.token_hash != keep).delete()
    db.commit()
    return {"ok": True}


# ── Quản lý tài khoản (middleware đã chặn người không phải admin) ──────────

@router.get("/users")
def list_users(db: Session = Depends(get_db)) -> List[dict]:
    return [auth.user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users")
def create_user(payload: UserIn, db: Session = Depends(get_db)) -> dict:
    name = _username(payload.username or "")
    if db.query(User.id).filter(User.username == name).first():
        raise HTTPException(status_code=409, detail=f"Tên đăng nhập '{name}' đã có")
    u = User(username=name, display_name=(payload.display_name or "").strip()[:80],
             password_hash=auth.hash_password(_password(payload.password)),
             is_admin=bool(payload.is_admin), is_active=payload.is_active is not False,
             permissions=_perms(payload.permissions), projects=_projects(payload.projects),
             models=_models(payload.models))
    db.add(u)
    db.commit()
    db.refresh(u)
    return auth.user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserIn, request: Request, db: Session = Depends(get_db)) -> dict:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không có tài khoản này")
    fields = payload.model_fields_set
    losing_admin = (("is_admin" in fields and not payload.is_admin)
                    or ("is_active" in fields and not payload.is_active))
    if u.is_admin and losing_admin and _other_admins(db, u.id) == 0:
        raise HTTPException(status_code=400, detail="Phải còn ít nhất 1 quản trị viên đang hoạt động")
    if "display_name" in fields:
        u.display_name = (payload.display_name or "").strip()[:80]
    if "is_admin" in fields:
        u.is_admin = bool(payload.is_admin)
    if "is_active" in fields:
        u.is_active = bool(payload.is_active)
    if "permissions" in fields:
        u.permissions = _perms(payload.permissions)
    if "projects" in fields:
        u.projects = _projects(payload.projects)
    if "models" in fields:
        u.models = _models(payload.models)
    if payload.password:
        u.password_hash = auth.hash_password(_password(payload.password))
    # Khoá tài khoản hoặc đặt lại mật khẩu → đá mọi phiên đang mở của người đó.
    if ("is_active" in fields and not payload.is_active) or payload.password:
        q = db.query(UserSession).filter(UserSession.user_id == u.id)
        me = _me(request, db)
        if me.id == u.id:              # tự đổi mật khẩu của mình: giữ phiên hiện tại
            q = q.filter(UserSession.token_hash != auth._token_hash(request.cookies.get(auth.COOKIE) or ""))
        q.delete()
    db.commit()
    db.refresh(u)
    return auth.user_out(u)


@router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không có tài khoản này")
    if u.id == _me(request, db).id:
        raise HTTPException(status_code=400, detail="Không tự xoá tài khoản đang đăng nhập")
    if u.is_admin and _other_admins(db, u.id) == 0:
        raise HTTPException(status_code=400, detail="Phải còn ít nhất 1 quản trị viên đang hoạt động")
    db.query(UserSession).filter(UserSession.user_id == u.id).delete()
    db.delete(u)
    db.commit()
    return {"deleted": user_id}
