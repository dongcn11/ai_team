# Skill: API Design

## Nguyên tắc RESTful
- URL dùng noun, không dùng verb: `/tasks` không phải `/getTasks`
- Số nhiều cho collection: `/tasks`, `/users`
- Nested resource khi có quan hệ: `/users/{id}/tasks`
- HTTP method đúng nghĩa: GET đọc, POST tạo, PUT/PATCH sửa, DELETE xóa

## Format api_contract.md chuẩn
```markdown
## POST /api/auth/register
**Mô tả:** Đăng ký tài khoản mới

**Request Body:**
| Field    | Type   | Required | Validation          |
|----------|--------|----------|---------------------|
| username | string | ✓        | 3-50 chars          |
| email    | string | ✓        | valid email format  |
| password | string | ✓        | min 8 chars         |

**Response 201:**
```json
{
  "id": "uuid",
  "username": "string",
  "email": "string",
  "created_at": "ISO8601"
}
```

**Response 409:** Email hoặc username đã tồn tại
**Response 422:** Validation error
```

## Checklist API design
- [ ] Tất cả endpoints cần auth đã có ghi rõ chưa?
- [ ] Response schema có expose thông tin nhạy cảm không? (password, internal ids)
- [ ] Error cases đã được định nghĩa chưa?
- [ ] Pagination cho list endpoints nếu có thể nhiều items?
- [ ] Filter params cho list endpoints?

## Data model checklist
- [ ] Mỗi table có `id` (uuid), `created_at`, `updated_at`
- [ ] Foreign key relationships rõ ràng
- [ ] Index cho các fields hay query (user_id, status)
- [ ] Không store sensitive data dạng plain text
