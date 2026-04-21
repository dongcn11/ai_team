# Skill: Sprint Planning

## Nguyên tắc chia task
- Sprint 1 nên tập trung vào **core features** — auth + 1 feature chính
- Chia task sao cho BE xong trước, FE có thể làm song song dựa vào API contract
- Mỗi agent không nên có quá 15 story points trong 1 sprint
- Task nào > 8 points thì tách nhỏ

## Format backlog.md
```markdown
# Product Backlog

| ID     | Story                    | Points | Priority | Assignee | Status  |
|--------|--------------------------|--------|----------|----------|---------|
| US-001 | Đăng ký tài khoản        | 3      | High     | BE2      | Todo    |
| US-002 | Đăng nhập / JWT          | 3      | High     | BE2      | Todo    |
| US-003 | CRUD tasks               | 5      | High     | BE1      | Todo    |
| US-004 | Login page UI            | 2      | High     | FE2      | Todo    |
| US-005 | Task list UI             | 3      | High     | FE1      | Todo    |
```

## Format sprint_plan.md
```markdown
# Sprint 1

**Goal:** User có thể đăng ký, đăng nhập và quản lý tasks cơ bản
**Duration:** 2 tuần
**Total:** 24 points

## BE Agent 1 (8 points)
- [ ] US-003: CRUD tasks API (5 pts)
- [ ] US-007: Filter tasks by status (3 pts)

## BE Agent 2 (6 points)
- [ ] US-001: Đăng ký user (3 pts)
- [ ] US-002: Đăng nhập + JWT (3 pts)

## FE Agent 1 (5 points)
- [ ] US-005: Task list page + TaskCard component (3 pts)
- [ ] US-008: Filter UI (2 pts)

## FE Agent 2 (5 points)
- [ ] US-004: Login + Register pages (3 pts)
- [ ] US-009: API client + useAuth hook (2 pts)

## Dependencies
- FE Agent 2 cần BE Agent 2 xong auth API trước
- FE Agent 1 cần BE Agent 1 xong tasks API trước

## Definition of Done
- Code hoạt động đúng theo acceptance criteria
- Không có console error
- Responsive trên mobile và desktop
```
