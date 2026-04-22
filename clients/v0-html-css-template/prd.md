# PRD: AlowWeb — Premium Web Solutions Platform

## Tổng quan

Xây dựng website dịch vụ thiết kế web + nền tảng e-commerce cho công ty **AlowWeb**.
Tham khảo: https://github.com/dongcn11/v0-html-css-template

## Mục tiêu

- Showcase dịch vụ của công ty (web design, custom app, e-commerce solutions)
- Cho phép khách hàng đặt mua dịch vụ / gói sản phẩm qua giỏ hàng và checkout
- Admin quản lý sản phẩm, đơn hàng, khách hàng

---

## Tính năng

### 1. Frontend Pages

| Trang | Mô tả |
|-------|-------|
| `/` | Homepage: hero section, featured services, CTA |
| `/services` | Danh sách dịch vụ / sản phẩm (list.html) |
| `/services/:id` | Chi tiết dịch vụ (detail.html) |
| `/cart` | Giỏ hàng (shopping-cart.html) |
| `/checkout` | Thanh toán (checkout.html) |
| `/contact` | Form liên hệ |
| `/admin` | Dashboard quản trị (đăng nhập riêng) |

### 2. Backend API

#### Auth
- `POST /api/register` — đăng ký tài khoản
- `POST /api/login` — đăng nhập, trả JWT
- `POST /api/logout` — đăng xuất
- `GET  /api/me` — thông tin user hiện tại

#### Services / Products
- `GET  /api/services` — danh sách dịch vụ (có filter, sort, pagination)
- `GET  /api/services/:id` — chi tiết dịch vụ
- `POST /api/admin/services` — tạo dịch vụ mới (admin)
- `PUT  /api/admin/services/:id` — cập nhật (admin)
- `DELETE /api/admin/services/:id` — xoá (admin)

#### Cart
- `GET  /api/cart` — xem giỏ hàng
- `POST /api/cart/items` — thêm item vào giỏ
- `PUT  /api/cart/items/:id` — cập nhật số lượng
- `DELETE /api/cart/items/:id` — xoá item

#### Orders
- `POST /api/orders` — tạo đơn hàng từ giỏ hàng
- `GET  /api/orders` — lịch sử đơn hàng của user
- `GET  /api/orders/:id` — chi tiết đơn hàng
- `GET  /api/admin/orders` — tất cả đơn hàng (admin)
- `PUT  /api/admin/orders/:id/status` — cập nhật trạng thái (admin)

#### Contact
- `POST /api/contact` — gửi form liên hệ (lưu vào DB + gửi email)

### 3. Data Models

#### User
- id, name, email, password, role (user/admin), created_at

#### Service
- id, name, slug, description, price, category, thumbnail, is_featured, is_active

#### Cart
- id, user_id, created_at
- CartItem: id, cart_id, service_id, quantity, price_snapshot

#### Order
- id, user_id, total_amount, status (pending/confirmed/completed/cancelled), notes, created_at
- OrderItem: id, order_id, service_id, quantity, price

#### Contact
- id, name, email, phone, message, created_at, is_read

### 4. Phân chia task

#### Fullstack Agent 1 — Core & Public
- Auth system (register, login, JWT via Sanctum)
- Services CRUD + Admin endpoints
- Database migrations + seeders (10 services mẫu)
- Homepage (hero, featured services, CTA sections)
- Services listing (filter by category, sort by price)
- Service detail page
- Contact page + form validation
- Contact form API (save + email notification)

#### Fullstack Agent 2 — Transactional & Admin
- Cart system (full CRUD)
- Orders system (create, list, detail, admin manage)
- Redis caching cho services list
- Shopping cart (add/remove/update, live total)
- Checkout flow (form, order review, confirm)
- Login / Register pages
- Thông báo order success
- Admin dashboard (quản lý orders, services, contacts)

---

## Tech Stack

- **Backend:** PHP 8.2 + Laravel 12 + Laravel Sanctum + MySQL + Redis
- **Frontend:** HTML5 + CSS3 + Vanilla JavaScript (không dùng framework)
- **Deploy:** Docker + docker-compose

## Yêu cầu phi chức năng

- API trả JSON chuẩn `{ data, message, errors }`
- Auth header: `Authorization: Bearer {token}`
- Pagination: `?page=1&per_page=10`
- Responsive design — mobile first
- Dark/light mode toggle (nice to have)

## Seeding Data

Khi chạy `php artisan db:seed`:
- 1 admin account: `admin@aloweb.com / password`
- 10 services với đủ category
- 5 users mẫu với orders
