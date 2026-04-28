from sqlmodel import SQLModel, Field
from pydantic import EmailStr, field_validator
from typing import Optional
from datetime import datetime
import uuid
import re


class UserRegister(SQLModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username chỉ chứa chữ cái, số và dấu gạch dưới")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password phải có ít nhất 8 ký tự")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password phải chứa ít nhất 1 chữ hoa")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password phải chứa ít nhất 1 chữ thường")
        if not re.search(r"\d", v):
            raise ValueError("Password phải chứa ít nhất 1 số")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password phải chứa ít nhất 1 ký tự đặc biệt")
        return v


class UserLogin(SQLModel):
    username: str
    password: str


class TokenResponse(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class TokenRefreshRequest(SQLModel):
    refresh_token: str


class UserResponse(SQLModel):
    id: uuid.UUID
    username: str
    email: str
    created_at: datetime


class LogoutResponse(SQLModel):
    message: str
