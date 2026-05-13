from sqlmodel import Session, select
from app.models.user import User
from app.security import hash_password, verify_password


class EmailExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


def register(db: Session, email: str, password: str) -> User:
    normalized_email = email.lower().strip()
    existing = db.exec(select(User).where(User.email == normalized_email)).first()
    if existing:
        raise EmailExistsError()
    user = User(email=normalized_email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    normalized_email = email.lower().strip()
    user = db.exec(select(User).where(User.email == normalized_email)).first()
    if not user or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return user
