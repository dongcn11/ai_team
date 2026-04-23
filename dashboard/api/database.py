import os
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://dashboard:dashboard123@localhost:5432/ai_team_dashboard",
)

Base = declarative_base()


def _create_engine(url: str, retries: int = 15, delay: int = 3):
    for i in range(retries):
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect():
                pass
            return engine
        except Exception as e:
            if i < retries - 1:
                print(f"[DB] Not ready, retrying in {delay}s... ({i+1}/{retries}): {e}")
                time.sleep(delay)
            else:
                raise


engine = _create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
