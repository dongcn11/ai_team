# Skill: JWT Authentication

## Setup
```
pip install python-jose[cryptography] passlib[bcrypt]
```

## auth.py hoàn chỉnh
```python
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select
from database import get_db
from models import User

SECRET_KEY    = "change-this-in-production"   # dùng env var thực tế
ALGORITHM     = "HS256"
ACCESS_EXPIRE = 30    # phút
REFRESH_EXPIRE = 7    # ngày

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token không hợp lệ",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, user_id)
    if not user:
        raise credentials_exception
    return user
```

## Login endpoint
```python
@router.post("/login", response_model=TokenResponse)
def login(form: LoginRequest, db: Session = Depends(get_db)):
    user = db.exec(select(User).where(User.username == form.username)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Username hoặc password sai")

    return {"access_token": create_access_token(user.id), "token_type": "bearer"}
```
