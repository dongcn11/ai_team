# Skill: Error Handling

## Nguyên tắc
- Xử lý lỗi ở đúng layer — không để lỗi leak qua các tầng
- Luôn có fallback, không để app crash im lặng
- Log đủ context để debug được: user_id, input, timestamp

## Backend (FastAPI)

### HTTP Error codes chuẩn
- `400` — input không hợp lệ (validation error)
- `401` — chưa đăng nhập
- `403` — không có quyền
- `404` — không tìm thấy resource
- `409` — conflict (ví dụ: email đã tồn tại)
- `422` — Unprocessable entity (Pydantic validation)
- `500` — lỗi server không mong đợi

### Pattern chuẩn
```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def get_task(task_id: str, current_user: User, db: Session):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task không tồn tại")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập")
    return task
```

### Global exception handler
```python
@app.exception_handler(Exception)
async def global_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Lỗi server"})
```

## Frontend (React)

### API call pattern
```typescript
const fetchTasks = async () => {
  try {
    setLoading(true)
    setError(null)
    const data = await api.getTasks()
    setTasks(data)
  } catch (err) {
    const message = err instanceof ApiError ? err.message : "Có lỗi xảy ra"
    setError(message)
  } finally {
    setLoading(false)
  }
}
```

### Luôn có 3 states
- `loading` — đang fetch
- `error` — có lỗi, hiển thị message
- `data` — thành công, hiển thị UI
