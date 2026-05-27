# Code Review Report — E-Commerce Platform

**Reviewed:** Fullstack Agent 1 (Backend)  
**Date:** 2026-04-29  
**Scope:** Cart feature implementation + Authentication foundation

---

## Tổng quan

FS1 Backend đã implement đúng **Cart feature** (US-001 đến US-004) với architecture sạch, dependency injection đúng pattern, và authentication middleware sẵn sàng. Tuy nhiên thiếu **Login feature** và **Payment feature** — các core endpoints theo API contract.

---

## BE Agent 1 (fullstack/fs1/backend/) — **needs-fix**

### ✅ Điểm tốt

| Area | Đánh giá |
|------|----------|
| **Architecture** | Router tách biệt `/api/v1/cart`, có dependency injection `get_current_user` |
| **Security** | JWT authentication với `HTTPBearer`, password hashing bằng bcrypt |
| **Error Handling** | HTTPException đúng status codes (400, 404), global exception handler có logging |
| **Code Quality** | Helper functions (`_get_or_create_cart`, `_cart_totals`), naming rõ ràng |
| **CORS** | Config đúng chuẩn `allow_origins=["http://localhost:5173"]` |
| **Models** | Relationships đúng (User ↔ Cart ↔ CartItem ↔ Product), indexing đầy đủ |
| **Schemas** | Pydantic schemas tách biệt request/response, có field descriptions |

---

### ⚠️ Cần sửa

#### [severity: high] Missing Authentication Endpoints (US-005, US-006, US-007, US-008)

**Vấn đề:**
- Có `core/jwt.py` và `api/dependencies.py` nhưng **không có endpoint `/auth/login`**
- Không có endpoint `/auth/refresh`, `/auth/forgot-password`, `/auth/reset-password`
- Model `PasswordResetToken` có trong data_models.md nhưng chưa implement

**Fix:**
```python
# routers/auth.py
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.email == payload.email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail={
            "error": "invalid_credentials",
            "message": "Invalid email or password"
        })
    
    access_token = create_access_token(user.id, user.email)
    refresh_token, expires_at = create_refresh_token(user.id)
    
    # Lưu refresh token vào DB
    rt = RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires_at)
    db.add(rt)
    db.commit()
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=3600,
        user=UserResponse(id=user.id, email=user.email, name=user.name)
    )
```

---

#### [severity: high] Missing Payment Endpoints (US-009 đến US-013)

**Vấn đề:**
- Không có router `/payments`
- Models `Payment`, `PaymentMethod`, `Order`, `OrderItem` chưa implement
- Enums `PaymentStatus`, `OrderStatus`, `PaymentMethodType` chưa define

**Fix:**
1. Tạo `models/payment.py` với các models theo data_models.md
2. Tạo `routers/payment.py` với endpoints:
   - `POST /api/v1/payments/checkout`
   - `GET /api/v1/payments/history`
   - `GET /api/v1/payments/{id}`
   - `GET /api/v1/payment-methods`
   - `POST /api/v1/payment-methods`
   - `DELETE /api/v1/payment-methods/{id}`

---

#### [severity: high] Schema Mismatch — Error Response Format

**Vấn đề:**
API contract yêu cầu:
```json
{
  "error": "invalid_credentials",
  "message": "Invalid email or password"
}
```

Code hiện tại:
```python
raise HTTPException(status_code=401, detail="Invalid or expired token")
# FastAPI trả: {"detail": "Invalid or expired token"}
```

**Fix:**
```python
# Tạo custom exception handler
class APIException(HTTPException):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail={"error": error_code, "message": message})

# Usage
raise APIException("invalid_credentials", "Invalid email or password", 401)
```

---

#### [severity: medium] Cart Response Thiếu `updated_at` Format Chuẩn

**Vấn đề:**
Code:
```python
updated_at=cart.updated_at.isoformat() + "Z"
```

API contract:
```json
"updated_at": "2026-04-29T10:30:00Z"
```

**Fix:** ✅ OK — Code đã đúng format ISO 8601 với `Z` suffix

---

#### [severity: medium] Không Có Validation cho `quantity` Âm

**Vấn đề:**
```python
@router.post("/cart/items")
def add_to_cart(payload: AddToCartRequest):
    # payload.quantity có thể = 0 hoặc âm nếu schema không validate
```

**Fix:**
```python
# schemas/cart.py
class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1, description="Quantity must be at least 1")
```

---

#### [severity: medium] Logging Không Đủ Context

**Vấn đề:**
```python
logger = logging.getLogger(__name__)
# Nhưng không log user_id, cart_id khi có lỗi
```

**Fix:**
```python
@router.post("/cart/items")
def add_to_cart(payload: AddToCartRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    logger.info(f"Adding to cart: user_id={current_user.id}, product_id={payload.product_id}, quantity={payload.quantity}")
    try:
        # ... logic
    except HTTPException as e:
        logger.warning(f"Add to cart failed: user_id={current_user.id}, error={e.detail}")
        raise
```

---

#### [severity: medium] Race Condition — Stock Check vs Add to Cart

**Vấn đề:**
```python
if product.stock_quantity < payload.quantity:
    raise HTTPException(...)
# Giữa check và add, user khác có thể mua hết stock
```

**Fix:**
- Dùng database transaction với row-level locking:
```python
from sqlmodel import update

# Lock product row
product = db.exec(select(Product).where(Product.id == payload.product_id).with_for_update()).first()
```

---

#### [severity: low] Hardcode `datetime.utcnow()`

**Vấn đề:**
Code dùng `datetime.utcnow()` ở nhiều chỗ — khó mock khi test

**Fix:**
```python
# utils/time.py
from datetime import datetime

def now() -> datetime:
    return datetime.utcnow()

# Usage
item.updated_at = now()
```

---

#### [severity: low] Thiếu Docstrings cho Router Functions

**Vấn đề:**
```python
@router.get("")
def get_cart(current_user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    """Return the authenticated user's cart with all items and totals."""
```

**Fix:** ✅ OK — Code đã có docstring

---

#### [severity: low] Không Có Unit Tests

**Vấn đề:**
- Không có test files cho cart endpoints
- Không có integration tests cho auth flow

**Fix:**
```python
# tests/test_cart.py
def test_add_to_cart(client, auth_headers, test_product):
    response = client.post(
        "/api/v1/cart/items",
        json={"product_id": test_product.id, "quantity": 1},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["product_id"] == test_product.id
```

---

## BE ↔ FE Integration

### ❌ Missing Endpoints — FE Sẽ Lỗi

| Endpoint | Status | FE Impact |
|----------|--------|-----------|
| `POST /api/v1/auth/login` | ❌ Missing | Login page không hoạt động |
| `POST /api/v1/auth/refresh` | ❌ Missing | Token refresh không hoạt động |
| `POST /api/v1/auth/forgot-password` | ❌ Missing | Password reset flow không hoạt động |
| `POST /api/v1/payments/checkout` | ❌ Missing | Checkout page không hoạt động |
| `GET /api/v1/payments/history` | ❌ Missing | Payment history page không hoạt động |
| `GET /api/v1/cart` | ✅ Implemented | Cart page hoạt động |
| `POST /api/v1/cart/items` | ✅ Implemented | Add to cart hoạt động |

### ✅ Data Types Khớp

| Schema | Backend | Frontend | Status |
|--------|---------|----------|--------|
| `CartItem` | `id, product_id, product_name, price, quantity, subtotal` | Same | ✅ |
| `CartResponse` | `id, user_id, items, total_items, total_price, updated_at` | Same | ✅ |
| `AddToCartResponse` | `id, product_id, product_name, price, quantity, subtotal, cart_total_items, cart_total_price` | Same | ✅ |

---

## API Contract Compliance

### Cart Endpoints — **95% Compliance**

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api/v1/cart` | GET | ✅ | Khớp 100% |
| `/api/v1/cart/items` | POST | ✅ | Khớp 100% |
| `/api/v1/cart/items/{id}` | PUT | ✅ | Khớp 100% |
| `/api/v1/cart/items/{id}` | DELETE | ✅ | Khớp 100% |
| `/api/v1/cart` | DELETE | ✅ | Khớp 100% |

### Auth Endpoints — **0% Compliance**

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/v1/auth/login` | POST | ❌ Missing |
| `/api/v1/auth/refresh` | POST | ❌ Missing |
| `/api/v1/auth/forgot-password` | POST | ❌ Missing |
| `/api/v1/auth/reset-password` | POST | ❌ Missing |

### Payment Endpoints — **0% Compliance**

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/v1/payments/checkout` | POST | ❌ Missing |
| `/api/v1/payments/history` | GET | ❌ Missing |
| `/api/v1/payments/{id}` | GET | ❌ Missing |
| `/api/v1/payment-methods` | GET | ❌ Missing |
| `/api/v1/payment-methods` | POST | ❌ Missing |
| `/api/v1/payment-methods/{id}` | DELETE | ❌ Missing |

---

## Security Checklist

| Check | Status | Notes |
|-------|--------|-------|
| Password hashing | ✅ | Dùng bcrypt qua `passlib` |
| JWT token expiry | ✅ | 30 phút access, 7 ngày refresh |
| CORS config | ✅ | Chỉ allow `localhost:5173` |
| Input validation | ⚠️ | Cần thêm validation cho quantity |
| SQL injection | ✅ | Dùng SQLModel parameterized queries |
| Sensitive data logging | ✅ | Không log password, token |
| Authentication middleware | ✅ | `get_current_user` dependency |
| Authorization checks | ✅ | Cart ownership check (`cart.user_id == current_user.id`) |

---

## Kết Luận

### Tổng số vấn đề: **10**

| Severity | Count |
|----------|-------|
| **High** | 3 |
| **Medium** | 4 |
| **Low** | 3 |

### Sẵn sàng ship: **No**

---

## Priority Fixes Trước Khi Ship

### P0 — Blocker (Phải có trước khi test FE)

1. **Implement Auth Endpoints** (US-005, US-006, US-007, US-008)
   - `POST /api/v1/auth/login`
   - `POST /api/v1/auth/refresh`
   - `POST /api/v1/auth/forgot-password`
   - `POST /api/v1/auth/reset-password`
   - Tạo `PasswordResetToken` model

2. **Implement Payment Endpoints** (US-009 đến US-013)
   - `POST /api/v1/payments/checkout`
   - `GET /api/v1/payments/history`
   - `GET /api/v1/payment-methods`
   - Tạo `Payment`, `PaymentMethod`, `Order`, `OrderItem` models

3. **Fix Error Response Format**
   - Tạo `APIException` class để trả về `{error, message}` thay vì `{detail}`

### P1 — High Priority

4. **Add Input Validation**
   - `quantity >= 1` trong `AddToCartRequest`
   - Email format validation trong login

5. **Add Logging Context**
   - Log `user_id`, `cart_id`, `product_id` trong cart operations

6. **Fix Race Condition**
   - Dùng `with_for_update()` khi check stock

### P2 — Medium Priority

7. **Refactor Hardcoded Datetime**
   - Tạo `utils/time.py` với `now()` function

8. **Add Unit Tests**
   - Test cart endpoints với các scenarios: add, update, remove, clear
   - Test auth flow: login, refresh, invalid credentials

---

## Recommendations

1. **Tạo file `docs/implementation_status.md`** để track progress từng endpoint
2. **Setup CI/CD pipeline** với pytest, mypy, black, flake8
3. **Add OpenAPI/Swagger docs** — FastAPI auto-generate tại `/docs`
4. **Integration testing** — Test BE + FE cùng nhau trước khi ship
5. **Consider Stripe/PayPal integration** cho payment thay vì self-hosted

---

## Next Steps cho FS1

1. ✅ **Cart feature** — Done
2. ⏳ **Auth feature** — Implement trong sprint tới
3. ⏳ **Payment feature** — Implement trong sprint tới
4. ⏳ **Unit tests** — Viết tests song song với implementation

---

**Reviewer:** Leader Agent (Tech Lead)  
**Review Date:** 2026-04-29  
**Next Review:** Sau khi implement Auth & Payment features
