# Skill: Security

## Không bao giờ
- Không log password, token, secret key
- Không trả về password hash trong API response
- Không để sensitive data trong URL query params
- Không trust input từ client — luôn validate server-side

## Authentication
- JWT token expire sau 30 phút
- Refresh token expire sau 7 ngày, lưu httpOnly cookie
- Luôn verify token signature trước khi dùng claims

## Input Validation
```python
# Dùng Pydantic — không validate thủ công
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    deadline: datetime | None = None

    @validator("deadline")
    def deadline_must_be_future(cls, v):
        if v and v < datetime.now():
            raise ValueError("Deadline phải là ngày trong tương lai")
        return v
```

## Password
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash khi tạo user
hashed = pwd_context.hash(plain_password)

# Verify khi login
is_valid = pwd_context.verify(plain_password, hashed_password)
```

## CORS
```python
# Chỉ allow origin cụ thể, không dùng "*" trong production
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
