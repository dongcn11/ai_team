# Ieltskey — Chức năng tạo khóa học

Backend FastAPI + SQLModel + SQLite, frontend React + TypeScript + Vite + TailwindCSS.

## Chạy backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Swagger: http://localhost:8000/docs
- DB mặc định là file `backend/ieltskey.db`, đổi bằng env `IELTSKEY_DB_URL`.
- CORS mặc định mở cho `localhost:5173`, đổi bằng env `IELTSKEY_CORS_ORIGINS`.

Chạy test:

```bash
cd backend
python -m pytest -q
```

Test dùng SQLite in-memory (xem `conftest.py`) nên không đụng tới DB thật.

## Chạy frontend

```bash
cd frontend
npm install
npm run dev
```

Mở http://localhost:5173. Vite proxy `/api` sang `http://localhost:8000` nên không cần
đổi base URL; muốn trỏ backend khác thì set `VITE_API_TARGET`.

## API

| Method | Path                | Mô tả                                                |
| ------ | ------------------- | ---------------------------------------------------- |
| POST   | `/api/courses`      | Tạo khóa học — `201`, `409` slug trùng, `422` sai dữ liệu |
| GET    | `/api/courses`      | Danh sách, lọc `q` / `status` / `level` / `skill`, phân trang `limit` / `offset` |
| GET    | `/api/courses/{id}` | Chi tiết — `404` nếu không có                        |
| GET    | `/api/health`       | Health check                                         |

Lỗi ngoài dự tính được gom về một chỗ ở `main.py` (`unhandled_error_handler`): ghi log
kèm method + path rồi trả `500 {"detail": "Lỗi máy chủ, thử lại sau"}` — không đẩy nội
dung exception ra ngoài vì chuỗi đó hay lộ đường dẫn file và câu SQL.

### Ràng buộc nghiệp vụ khi tạo khóa

Toàn bộ nằm ở `backend/app/schemas.py` (`CourseCreate`), frontend kiểm tra lại y hệt
trong `CourseForm.validate()` để báo lỗi ngay mà không cần round-trip:

- `title`: 3–160 ký tự, tự gộp khoảng trắng thừa.
- `slug`: bỏ trống thì sinh từ `title` (bỏ dấu tiếng Việt, trùng thì thêm hậu tố `-2`,
  `-3`…). Nhập tay mà trùng thì trả `409` chứ không tự đổi — link đã phát ra ngoài
  không được âm thầm khác đi.
- `target_band`: 4.0–9.0 và phải là bội của 0.5.
- `duration_weeks` 1–104, `sessions_per_week` 1–14, `max_students` 1–500,
  `price_vnd` 0–1.000.000.000.
- `status = published` bắt buộc có `start_date` và `price_vnd > 0`; mặc định là `draft`.

## Cấu trúc

```
backend/
  app/
    main.py          # FastAPI app, CORS, lifespan tạo bảng
    database.py      # engine + dependency get_session
    models.py        # bảng courses (SQLModel table)
    schemas.py       # CourseCreate / CourseRead + ràng buộc nghiệp vụ
    routers/courses.py
    utils.py         # slugify tiếng Việt
  tests/test_courses.py
frontend/
  src/
    main.tsx, App.tsx, index.css
    api/client.ts    # gom lỗi FastAPI (chuỗi & 422) về một dạng cho UI
    api/courses.ts
    components/CourseForm.tsx
    components/CourseList.tsx
    lib/format.ts, types.ts
```
