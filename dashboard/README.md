# AI Team Dashboard

Giao diện web theo dõi tiến độ các AI coding agents theo thời gian thực.

## Kiến trúc

```
PostgreSQL 16  ←──  FastAPI (port 8000)  ←──  task_manager.py (orchestrator)
                           ↑
                    React + Vite (port 3000)
```

## Yêu cầu

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) đã cài và đang chạy
- (Tuỳ chọn) Node.js 20+ nếu muốn chạy dev mode

---

## Cài đặt & Chạy

### 1. Build và start toàn bộ stack

```bash
cd dashboard
docker compose up --build
```

Lần đầu build mất ~3-5 phút. Các lần sau nhanh hơn.

| Service    | URL                          |
|------------|------------------------------|
| Dashboard  | http://localhost:3000        |
| API docs   | http://localhost:8000/docs   |
| PostgreSQL | localhost:5432               |

### 2. Stop

```bash
docker compose down
```

Dữ liệu PostgreSQL được lưu trong Docker volume `pgdata`, không mất khi stop.

### 3. Xoá toàn bộ dữ liệu (reset)

```bash
docker compose down -v
```

---

## Dev mode (React hot reload)

Chạy PostgreSQL + API bằng Docker, React chạy local với Vite:

```bash
# Terminal 1 — chỉ start DB + API
cd dashboard
docker compose up db api

# Terminal 2 — React dev server
cd dashboard
npm install
npm run dev
```

Dashboard mở tại http://localhost:5173 với hot reload.

---

## Biến môi trường

| Biến                 | Default                                              | Mô tả                            |
|----------------------|------------------------------------------------------|----------------------------------|
| `DATABASE_URL`       | `postgresql://dashboard:dashboard123@db:5432/ai_team_dashboard` | Connection string PostgreSQL |
| `DASHBOARD_API_URL`  | `http://localhost:8000`                              | URL API gọi từ orchestrator      |
| `CLIENT_NAME`        | Tên thư mục hiện tại                                 | Tên client hiển thị trong history |

Tạo file `.env` tại root project để override:

```env
DASHBOARD_API_URL=http://localhost:8000
CLIENT_NAME=my-project
```

---

## Tích hợp với Orchestrator

`task_manager.py` tự động gửi updates lên API khi orchestrator chạy.  
Nếu API offline, orchestrator **không bị ảnh hưởng** — calls là fire-and-forget.

Thứ tự khởi động đúng:

```bash
# 1. Start dashboard trước
cd dashboard && docker compose up -d

# 2. Chạy orchestrator bình thường
cd .. && python main.py
```

---

## Cấu trúc thư mục

```
dashboard/
├── api/                    # FastAPI backend
│   ├── main.py
│   ├── database.py         # SQLAlchemy + retry logic
│   ├── models.py           # runs / tasks / issues
│   ├── schemas.py
│   ├── routers/
│   │   ├── runs.py
│   │   ├── tasks.py
│   │   └── issues.py
│   ├── requirements.txt
│   └── Dockerfile
├── src/                    # React frontend
│   ├── App.tsx
│   ├── components/
│   │   ├── TaskCard.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── IssuesList.tsx
│   │   └── RunHistory.tsx
│   ├── hooks/
│   │   └── useTasks.ts     # Polling 3s
│   └── types.ts
├── docker-compose.yml
├── Dockerfile              # React multi-stage build
├── nginx.conf
├── package.json
├── vite.config.ts
└── README.md
```

---

## API Endpoints

| Method | Endpoint                   | Mô tả                        |
|--------|----------------------------|------------------------------|
| POST   | `/api/runs`                | Tạo run mới                  |
| GET    | `/api/runs`                | Danh sách runs (history)     |
| GET    | `/api/runs/current`        | Run đang active              |
| GET    | `/api/runs/{id}`           | Chi tiết 1 run               |
| POST   | `/api/tasks/update`        | Cập nhật trạng thái task     |
| POST   | `/api/issues`              | Tạo issue                    |
| GET    | `/api/issues/{run_id}`     | Issues của 1 run             |

Xem đầy đủ tại **http://localhost:8000/docs** (Swagger UI).
