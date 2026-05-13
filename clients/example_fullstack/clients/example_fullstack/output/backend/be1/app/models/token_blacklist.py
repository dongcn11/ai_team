from datetime import datetime
from sqlmodel import SQLModel, Field


class TokenBlacklist(SQLModel, table=True):
    __tablename__ = "token_blacklist"

    jti: str = Field(primary_key=True)
    user_id: str = Field(nullable=False, index=True)
    expires_at: datetime = Field(nullable=False, index=True)
    revoked_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
