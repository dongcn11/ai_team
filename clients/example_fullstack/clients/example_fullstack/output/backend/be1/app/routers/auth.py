from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlmodel import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import get_session
from app.schemas.auth import RegisterRequest, LoginRequest, UserResponse, LoginResponse
from app.services.auth_service import register, authenticate, EmailExistsError, InvalidCredentialsError
from app.security import create_access_token
from app.deps import get_current_user, oauth2_scheme
from app.models.user import User
from app.models.token_blacklist import TokenBlacklist
from app.config import settings
from jose import jwt
from datetime import datetime, timezone

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserResponse, status_code=201)
def register_endpoint(data: RegisterRequest, db: Session = Depends(get_session)):
    try:
        user = register(db, data.email, data.password)
    except EmailExistsError:
        raise HTTPException(
            status_code=409,
            detail={"detail": "Email đã được sử dụng", "code": "EMAIL_EXISTS"},
        )
    return user


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
def login_endpoint(request: Request, data: LoginRequest, db: Session = Depends(get_session)):
    try:
        user = authenticate(db, data.email, data.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail={"detail": "Email hoặc mật khẩu không đúng", "code": "INVALID_CREDENTIALS"},
        )
    token, jti = create_access_token(user.id, user.email)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        user=UserResponse(id=user.id, email=user.email, created_at=user.created_at),
    )


@router.post("/logout", status_code=204)
def logout_endpoint(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    raw_token: str = Depends(oauth2_scheme),
):
    payload = jwt.decode(raw_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    if isinstance(expires_at, (int, float)):
        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    entry = TokenBlacklist(jti=jti, user_id=current_user.id, expires_at=expires_at)
    db.add(entry)
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
