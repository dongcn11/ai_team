from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid
import re


def validate_email(v: str) -> str:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, v):
        raise ValueError("Invalid email format")
    return v


def validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r'[A-Z]', v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r'[0-9]', v):
        raise ValueError("Password must contain at least one number")
    return v


def validate_username(v: str) -> str:
    pattern = r'^[a-zA-Z0-9_]{3,50}$'
    if not re.match(pattern, v):
        raise ValueError("Username must be 3-50 characters, alphanumeric and underscore only")
    return v


class UserCreate(SQLModel):
    username: str = Field(min_length=3, max_length=50)
    email: str
    password: str = Field(min_length=8)

    def validate_all(self):
        self.username = validate_username(self.username)
        self.email = validate_email(self.email)
        self.password = validate_password(self.password)
        return self


class UserResponse(SQLModel):
    id: uuid.UUID
    username: str
    email: str
    created_at: datetime


class UserLogin(SQLModel):
    email: str
    password: str


class TokenResponse(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class RefreshTokenRequest(SQLModel):
    refresh_token: str


class LogoutResponse(SQLModel):
    message: str
