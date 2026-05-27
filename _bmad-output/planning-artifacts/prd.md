---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments: ['clients/e-commerce_platform/settings.toml']
workflowType: 'prd'
classification:
  projectType: Web Application (E-Commerce)
  domain: E-Commerce / Retail
  complexity: Medium
  projectContext: greenfield
  team: 1 Fullstack Developer + 1 PM
---

# Product Requirements Document — Hệ Thống Đăng Nhập E-Commerce Platform

**Author:** PhamLeo
**Date:** 2026-04-28
**Tech Stack:** Laravel + MySQL / Blade + TailwindCSS

---

## Executive Summary

Dự án xây dựng hệ thống xác thực người dùng (Authentication) cho nền tảng thương mại điện tử sử dụng **Laravel Session Authentication**. Đây là greenfield project, tạo nền tảng bảo mật và đơn giản cho luồng đăng nhập/đăng ký khách hàng B2C.

### What Makes This Special

Session-based authentication của Laravel cung cấp CSRF protection tích hợp sẵn, quản lý session tập trung phía server, giảm độ phức tạp so với JWT. Phù hợp với kiến trúc monolithic Blade + TailwindCSS, lý tưởng cho team nhỏ (1 Fullstack + 1 PM) cần triển khai nhanh và bảo mật.

## Project Classification

| Thuộc tính | Giá trị |
|---|---|
| Project Type | Web Application — E-Commerce |
| Domain | E-Commerce / Retail |
| Complexity | Medium |
| Context | Greenfield |
| Team | 1 PM + 1 Fullstack Developer |
| Tech Stack | Laravel + MySQL / Blade + TailwindCSS |

---

## Success Criteria

### User Success

- Người dùng hoàn thành đăng nhập trong vòng **3 giây** (từ submit đến redirect)
- Tỷ lệ đăng nhập thành công lần đầu ≥ **90%** (không bị lỗi CSRF, session timeout)
- Người dùng tự reset mật khẩu thành công mà không cần hỗ trợ admin
- Form đăng nhập hiển thị lỗi rõ ràng, người dùng biết cần làm gì tiếp theo

### Business Success

- Tỷ lệ đăng ký tài khoản hoàn thành ≥ **70%** (không bỏ giữa chừng)
- Zero security incident liên quan đến session hijacking hoặc brute-force trong 3 tháng đầu
- Hệ thống hỗ trợ **100 người dùng đồng thời** không giảm hiệu năng

### Technical Success

- Session timeout sau **120 phút** không hoạt động
- CSRF token được validate trên tất cả form POST
- Password được hash bằng **bcrypt** (Laravel default)
- Rate limiting: tối đa **5 lần đăng nhập thất bại** trước khi khóa tạm 15 phút

---

## Product Scope

### MVP — Minimum Viable Product

- Đăng ký tài khoản (email, password, tên)
- Đăng nhập bằng email + password
- Đăng xuất
- Quên mật khẩu (gửi email reset link)
- Remember Me (session kéo dài 30 ngày)
- Bảo vệ route — redirect về login nếu chưa xác thực

### Growth Features (Post-MVP)

- Xác thực email sau đăng ký (email verification)
- Đăng nhập bằng Google / Facebook (OAuth)
- Xem lịch sử phiên đăng nhập (active sessions)
- Đăng xuất khỏi tất cả thiết bị

### Vision (Future)

- Two-factor authentication (2FA)
- Single Sign-On (SSO) cho hệ thống doanh nghiệp
- Biometric login trên thiết bị di động

---

## User Journeys

### Journey 1 — Khách Hàng Mới Đăng Ký (Happy Path)

**Persona:** Minh, 28 tuổi, muốn mua hàng lần đầu trên sàn.

- Minh vào trang chủ, click "Đăng ký"
- Điền email, họ tên, mật khẩu (có hiển thị strength indicator)
- Submit → Laravel tạo user, tạo session, redirect về trang chủ đã đăng nhập
- Minh thấy tên mình hiển thị góc phải, tiếp tục mua hàng

**Cảm xúc:** Nhanh chóng → Tự tin → Hài lòng

### Journey 2 — Khách Hàng Đăng Nhập Lại (Returning User)

**Persona:** Lan, khách hàng cũ quay lại sau 2 tuần.

- Lan vào trang, bị redirect về `/login` khi truy cập giỏ hàng
- Nhập email + password, tick "Remember Me"
- Đăng nhập thành công, redirect về trang giỏ hàng ban đầu
- Lần sau mở trình duyệt — vẫn còn đăng nhập (remember me 30 ngày)

**Cảm xúc:** Nhẹ nhàng → Thuận tiện → Trung thành

### Journey 3 — Khách Hàng Quên Mật Khẩu

**Persona:** Hùng, không nhớ mật khẩu đã đặt 3 tháng trước.

- Click "Quên mật khẩu" trên trang login
- Nhập email → nhận link reset trong vòng 1 phút
- Click link → đặt mật khẩu mới → tự động đăng nhập
- Link reset hết hạn sau 60 phút (bảo mật)

**Cảm xúc:** Lo lắng → Nhẹ nhõm → Tiếp tục mua hàng

### Journey 4 — Brute Force Attack (Edge Case)

**Kẻ tấn công** thử đăng nhập sai 5 lần liên tiếp.

- Lần thứ 5 sai → Laravel Rate Limiter khóa IP trong 15 phút
- Người dùng thật nhận thông báo rõ ràng: "Thử lại sau 15 phút"
- Log ghi nhận sự kiện để admin theo dõi

### Journey Requirements Summary

| Journey | Capabilities cần có |
|---|---|
| Đăng ký | Form validation, password hashing, session creation, redirect |
| Đăng nhập | Credential check, session start, remember me cookie, intended redirect |
| Quên MK | Email gửi link, token lưu DB, reset + auto login |
| Bảo mật | Rate limiting, CSRF, session invalidation |

---

## Domain-Specific Requirements

### Bảo Mật E-Commerce

- **CSRF Protection:** Tất cả form phải có `@csrf` directive của Laravel
- **SQL Injection:** Dùng Eloquent ORM / Query Builder — không dùng raw SQL với user input
- **XSS Prevention:** Blade template tự động escape output với `{{ }}`, không dùng `{!! !!}` với dữ liệu user
- **Password Policy:** Tối thiểu 8 ký tự, bắt buộc có số hoặc ký tự đặc biệt
- **HTTPS:** Toàn bộ trang login/register chỉ chạy trên HTTPS (middleware `ForceHttps` trên production)

### Data & Privacy

- Không lưu password dạng plain text — bcrypt hash với cost factor 12
- Email là unique identifier — validate unique trước khi lưu
- Reset token lưu trong bảng `password_reset_tokens`, xóa sau khi dùng

---

## Web Application Specific Requirements

### Route Protection

- Middleware `auth` bảo vệ tất cả route yêu cầu đăng nhập (`/profile`, `/orders`, `/cart`)
- Middleware `guest` redirect user đã đăng nhập ra khỏi `/login`, `/register`
- `intended()` redirect — sau khi đăng nhập, về đúng trang người dùng định vào

### Session Configuration

- Driver: `database` (lưu session trong MySQL, không dùng file trên production)
- Lifetime: 120 phút (configurable qua `.env`)
- Secure cookie: `true` trên production
- SameSite: `lax`

### Email

- Dùng Laravel Mail + Queue để gửi email reset password bất đồng bộ
- Template email branded với logo e-commerce platform
- Fallback: nếu queue fail, gửi synchronous

---

## Project Scoping & Phased Development

### MVP Strategy

**Approach:** Problem-solving MVP — chứng minh authentication hoạt động đúng, bảo mật, và không chặn luồng mua hàng.

**Resource:** 1 Fullstack Developer, ~2 tuần phát triển.

### MVP Feature Set (Phase 1)

**Core User Journeys:**
- Đăng ký tài khoản mới
- Đăng nhập / Đăng xuất
- Quên mật khẩu + Reset

**Must-Have Capabilities:**
- `AuthController` với 6 actions: showLogin, login, showRegister, register, logout, showForgotPassword, sendResetLink, showResetForm, resetPassword
- Laravel built-in `Auth` facade + `Illuminate\Auth\Middleware`
- Database migration: `users`, `password_reset_tokens`, `sessions`
- Blade views: login, register, forgot-password, reset-password
- Email template cho reset password
- Rate limiting với `RateLimiter` facade

### Phase 2 (Post-MVP)

- Email verification (`MustVerifyEmail` contract)
- Social login (Laravel Socialite — Google)
- Active session management

### Phase 3 (Expansion)

- 2FA với Google Authenticator
- SSO integration

### Risk Mitigation

| Rủi ro | Biện pháp |
|---|---|
| Session fixation | `session()->regenerate()` sau mỗi lần login |
| Email không gửi được | Queue với retry + fallback sync |
| Database session quá tải | Index `sessions.last_activity`, cleanup job hằng ngày |

---

## Functional Requirements

### Quản Lý Tài Khoản

- FR1: Khách vãng lai có thể đăng ký tài khoản bằng email và password
- FR2: Hệ thống có thể validate email chưa tồn tại trước khi tạo tài khoản
- FR3: Người dùng có thể đăng nhập bằng email và password đã đăng ký
- FR4: Người dùng có thể đăng xuất và huỷ session hiện tại
- FR5: Người dùng có thể yêu cầu reset password qua email
- FR6: Người dùng có thể đặt mật khẩu mới bằng reset token hợp lệ

### Quản Lý Session

- FR7: Hệ thống có thể duy trì session đăng nhập trong 120 phút không hoạt động
- FR8: Người dùng có thể chọn "Remember Me" để kéo dài session 30 ngày
- FR9: Hệ thống có thể redirect người dùng về trang họ định truy cập sau khi đăng nhập
- FR10: Hệ thống có thể vô hiệu hoá session khi người dùng đăng xuất

### Bảo Vệ Route

- FR11: Hệ thống có thể chặn truy cập các trang yêu cầu xác thực nếu chưa đăng nhập
- FR12: Hệ thống có thể redirect người dùng đã đăng nhập ra khỏi trang login/register
- FR13: Hệ thống có thể validate CSRF token trên tất cả form POST

### Bảo Mật & Rate Limiting

- FR14: Hệ thống có thể khóa tạm đăng nhập sau 5 lần thất bại liên tiếp từ cùng IP
- FR15: Hệ thống có thể thông báo rõ thời gian chờ khi bị rate limit
- FR16: Hệ thống có thể tạo token reset password với thời hạn 60 phút
- FR17: Hệ thống có thể vô hiệu hoá reset token sau khi đã sử dụng

### Thông Báo & Phản Hồi

- FR18: Hệ thống có thể hiển thị thông báo lỗi cụ thể khi đăng nhập thất bại
- FR19: Hệ thống có thể gửi email reset password trong vòng 1 phút sau khi yêu cầu
- FR20: Hệ thống có thể hiển thị trạng thái strength của password khi đăng ký

---

## Non-Functional Requirements

### Performance

- Trang login/register load trong **< 1 giây** (TTFB < 200ms)
- Xử lý đăng nhập (validate + session create) trong **< 500ms**
- Hỗ trợ **100 request đồng thời** không degradation

### Security

- Password hash: bcrypt với cost factor **12**
- Session cookie: `HttpOnly`, `Secure` (production), `SameSite=lax`
- Reset token: cryptographically random, 64 ký tự
- Tất cả input được sanitize trước khi lưu DB
- Headers bảo mật: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`

### Reliability

- Uptime **99.5%** cho trang login (downtime < 3.6h/tháng)
- Email reset password được gửi thành công **≥ 99%** (queue với 3 lần retry)
- Session data không bị mất khi server restart (database driver)

### Accessibility

- Form login/register đạt chuẩn **WCAG 2.1 AA**
- Label rõ ràng cho tất cả input
- Thông báo lỗi được đọc bởi screen reader (ARIA live region)
- Keyboard navigation đầy đủ (Tab, Enter, Escape)
