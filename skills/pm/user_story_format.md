# Skill: User Story Format

## Template chuẩn
```
## Epic: [Tên epic — nhóm các story liên quan]

### US-001: [Tên ngắn gọn]
**As a** [role: user/admin/guest]
**I want** [hành động cụ thể]
**So that** [lợi ích, mục tiêu]

**Story Points:** [1 / 2 / 3 / 5 / 8]
**Priority:** [High / Medium / Low]
**Assignee:** [BE1 / BE2 / FE1 / FE2]
```

## Story points guideline
- **1 point** — Thay đổi nhỏ, rõ ràng, < 2 giờ
- **2 points** — Task đơn giản, ít dependency, ~2-4 giờ
- **3 points** — Task trung bình, có một chút phức tạp, ~4-8 giờ
- **5 points** — Task phức tạp, nhiều file, cần coordination, ~1-2 ngày
- **8 points** — Task lớn, nên xem xét tách nhỏ hơn

## Ví dụ tốt vs xấu

### ❌ Xấu — quá chung chung
```
As a user, I want to manage tasks so that I can be productive.
```

### ✅ Tốt — cụ thể, đo lường được
```
As a logged-in user,
I want to create a new task with title, description, and deadline,
So that I can track what I need to do and when.
```

## Checklist trước khi submit
- [ ] Story có thể test được không?
- [ ] Story đủ nhỏ để hoàn thành trong 1 sprint không?
- [ ] Assignee rõ ràng chưa?
- [ ] Có đủ thông tin để developer implement không?
