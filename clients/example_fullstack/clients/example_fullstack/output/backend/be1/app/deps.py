from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from jose import JWTError, jwt
from app.config import settings
from app.database import get_session
from app.models.user import User
from app.models.token_blacklist import TokenBlacklist

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        jti = payload.get("jti")
        if not user_id or not jti:
            raise HTTPException(status_code=401, detail={"detail": "Token không hợp lệ", "code": "INVALID_TOKEN"})
    except JWTError:
        raise HTTPException(status_code=401, detail={"detail": "Token không hợp lệ", "code": "INVALID_TOKEN"})

    blacklisted = db.get(TokenBlacklist, jti)
    if blacklisted:
        raise HTTPException(status_code=401, detail={"detail": "Token đã bị thu hồi", "code": "TOKEN_REVOKED"})

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail={"detail": "Token không hợp lệ", "code": "INVALID_TOKEN"})

    return user
