"""Entrypoint FastAPI.

Chạy dev:  uvicorn app.main:app --reload --port 8000   (đứng ở thư mục backend/)
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import init_db
from .routers import courses

logger = logging.getLogger(__name__)

# Vite dev server mặc định cổng 5173. Deploy thật thì set IELTSKEY_CORS_ORIGINS.
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
ORIGINS = [o.strip() for o in os.getenv("IELTSKEY_CORS_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Ieltskey API",
    version="0.1.0",
    description="Backend quản lý khóa học IELTS",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(courses.router)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lỗi ngoài dự tính: log đủ ngữ cảnh để lần lại, trả client thông báo chung.

    Cố ý KHÔNG đưa nội dung exception ra response — chuỗi đó hay lộ đường dẫn
    file, câu SQL hoặc tên cột. Chi tiết nằm trong log của server.
    """
    logger.exception("Lỗi không xử lý được: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Lỗi máy chủ, thử lại sau"})


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}
