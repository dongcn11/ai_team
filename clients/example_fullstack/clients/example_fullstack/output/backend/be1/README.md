# Task Manager API — Backend

## Setup

```bash
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Run Tests

```bash
pytest --cov=app.routers.auth --cov=app.services.auth_service --cov=app.security --cov=app.deps --cov-fail-under=80
```

## Health Check

```bash
curl http://localhost:8000/api/v1/health
```

## Production Notes

- `JWT_SECRET` must be a random string of at least 32 bytes
- bcrypt cost factor is set to 12 (adjust for production hardware)
