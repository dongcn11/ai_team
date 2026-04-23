# PRD: AlowWeb — Premium Web Solutions Platform

## Thông tin dự án

| Mục | Chi tiết |
|-----|----------|
| **Repo** | https://github.com/dongcn11/v0-html-css-template |
| **Kiến trúc** | Laravel 12 full-stack MVC (Blade templates, không phải API + SPA) |
| **Auth** | Session-based (Laravel Auth + Middleware), Admin có login riêng |
| **Deploy** | Docker + AWS CodeDeploy |
| **Ngôn ngữ** | Tiếng Việt (lang/vi/messages.php) |

---

## Tổng quan

AlowWeb là website công ty cung cấp dịch vụ thiết kế web cao cấp. Nền tảng bao gồm:
- Trang public showcase dịch vụ, portfolio, blog, giải pháp
- Hệ thống đặt hàng dịch vụ trực tiếp (Service Orders)
- Giỏ hàng + checkout cho sản phẩm/gói (Cart Orders)
- Admin panel quản lý toàn bộ nội dung và đơn hàng

**Clone và làm tiếp:** https://github.com/dongcn11/v0-html-css-template

---

## Tech Stack

| Layer | Stack |
|-------|-------|
| **Backend** | PHP 8.2 + Laravel 12 |
| **Template** | Blade (full-stack MVC, không dùng JS framework) |
| **Database** | MySQL |
| **Cache** | File/Redis |
| **Auth** | Laravel Session Auth + EnsureUserIsAdmin middleware |
| **Frontend** | HTML5 + CSS3 + Vanilla JavaScript (trong Blade views) |
| **Deploy** | Docker + docker-compose + AWS CodeDeploy (appspec.yml) |

---

## Cấu trúc hiện có (đã implement)

### Models đã có

| Model | Table | Mô tả |
|-------|-------|-------|
| `User` | `users` | Có `role` (user/admin) |
| `Service` | `services` | slug, description, full_description, icon, features (JSON), price, price_type, is_featured, is_active, SoftDeletes |
| `Solution` | `solutions` | Giải pháp kinh doanh |
| `Portfolio` | `portfolios` | Dự án đã làm |
| `Blog` | `blogs` | Bài viết |
| `Category` | `categories` | Danh mục (dùng chung) |
| `Coupon` | `coupons` | Mã giảm giá |
| `Cart` | `carts` | Giỏ hàng (session_id hoặc user_id) |
| `CartItem` | `cart_items` | Item trong giỏ |
| `Order` | `orders` | Đơn hàng cart (có billing address, payment info) |
| `OrderItem` | `order_items` | Item của order |
| `ServiceOrder` | `service_orders` | Đặt dịch vụ trực tiếp (inquiry + order) |
| `ContactMessage` | `contact_messages` | Tin nhắn liên hệ |

### Routes đã có

#### Public
| Route | Controller | Mô tả |
|-------|-----------|-------|
| `GET /` | HomeController | Trang chủ |
| `GET /solutions` | SolutionController | Danh sách giải pháp |
| `GET /solutions/{id}` | SolutionController | Chi tiết giải pháp |
| `GET /services` | ServiceController | Danh sách dịch vụ |
| `GET /services/{slug}` | ServiceController | Chi tiết dịch vụ |
| `GET /portfolio` | PortfolioController | Portfolio |
| `GET /portfolio/{slug}` | PortfolioController | Chi tiết portfolio |
| `GET /blog` | BlogController | Danh sách blog |
| `GET /blog/{slug}` | BlogController | Bài viết |
| `GET /contact` | ContactController | Form liên hệ |
| `POST /contact` | ContactController | Gửi liên hệ |

#### Auth (Session)
| Route | Mô tả |
|-------|-------|
| `GET/POST /login` | Đăng nhập user |
| `GET/POST /register` | Đăng ký user |
| `POST /logout` | Đăng xuất |

#### Cart & Checkout
| Route | Auth | Mô tả |
|-------|------|-------|
| `GET /cart` | Guest OK | Xem giỏ hàng |
| `POST /cart/add/{solutionId}` | Guest OK | Thêm vào giỏ |
| `PATCH /cart/{id}` | Guest OK | Cập nhật số lượng |
| `DELETE /cart/{id}` | Guest OK | Xoá item |
| `GET /checkout` | Auth | Trang checkout |
| `POST /checkout/process` | Auth | Xử lý đặt hàng |

#### Service Orders (đặt dịch vụ trực tiếp)
| Route | Auth | Mô tả |
|-------|------|-------|
| `GET /services/{id}/order` | Guest OK | Form đặt dịch vụ |
| `POST /services/{id}/order` | Guest OK | Gửi yêu cầu đặt dịch vụ |
| `GET /service-orders` | Auth | Lịch sử service orders của user |
| `GET /service-orders/{id}` | Auth | Chi tiết service order |

#### Admin (auth + admin middleware)
| Module | Routes |
|--------|--------|
| Dashboard | `GET /admin/dashboard` |
| Orders | index, show, update-status, destroy |
| Service Orders | index, show, update-status, update-payment-status, destroy |
| Solutions | CRUD đầy đủ |
| Services | CRUD đầy đủ |
| Categories | CRUD đầy đủ |
| Portfolios | CRUD đầy đủ |
| Blogs | CRUD đầy đủ |
| Coupons | CRUD đầy đủ |
| Customers | index, show, update-status, destroy |
| Contact Messages | index, show, update-status, update-notes, destroy |

---

## Tính năng cần hoàn thiện

### FS1 — Core Content & Public Pages

#### 1. Trang chủ (`HomeController@index`)
- Hero section: headline, CTA button
- Featured services section (query `Service::where('is_featured', true)`)
- Solutions overview (query `Solution::take(3)`)
- Portfolio highlights (query `Portfolio::take(6)`)
- Blog preview (query `Blog::latest()->take(3)`)
- Testimonials section (static hoặc DB)
- Contact CTA section

#### 2. Services
- `services/index.blade.php` — grid cards, filter theo category, sort theo price
- `services/show.blade.php` — full detail: icon, name, features list, price badge, nút "Order Now"
- Service model: `price_type` có thể là `one-time | monthly | hourly | contact`

#### 3. Solutions
- `solutions/index.blade.php` — danh sách giải pháp kinh doanh
- `solutions/show.blade.php` — chi tiết giải pháp

#### 4. Portfolio
- `portfolio/index.blade.php` — grid portfolio
- `portfolio/show.blade.php` — chi tiết dự án (screenshots, tech used, description)

#### 5. Blog
- `blogs/index.blade.php` — danh sách bài viết có pagination
- `blogs/show.blade.php` — bài viết đầy đủ

#### 6. Contact
- `contact/index.blade.php` — form + thông tin liên hệ
- Lưu vào `contact_messages`, gửi email notification

#### 7. Auth Pages
- `auth/login.blade.php` — form đăng nhập
- `auth/register.blade.php` — form đăng ký

#### 8. Admin — Content Management
- Blog CRUD (create, edit, index, show)
- Category CRUD
- Solutions CRUD
- Portfolio CRUD
- Services CRUD (với upload icon, JSON features)
- Contact Messages (list, show, mark-as-read, notes, delete)
- Admin auth: `admin/auth/login.blade.php`
- Admin layout: sidebar navigation, responsive

---

### FS2 — Transactional & Ecommerce

#### 1. Cart (session-based, không cần login)
- `cart/index.blade.php` — danh sách items, quantity stepper, remove, subtotal
- Guest cart: dùng `session_id`; sau login merge vào user cart
- CartController đã có skeleton, cần implement đầy đủ

#### 2. Service Order (đặt dịch vụ trực tiếp)
- `services/order.blade.php` — form: tên, email, phone, yêu cầu, budget
- `services/my-orders.blade.php` — lịch sử service orders
- `services/order-confirmation.blade.php` — xác nhận đặt dịch vụ
- ServiceOrder: có `status` (pending/confirmed/in-progress/completed/cancelled) + `payment_status`

#### 3. Checkout & Orders
- `checkout/index.blade.php` — billing form (first_name, last_name, email, phone, address, city, state, zip, country), order summary, coupon field
- `CheckoutController@process` — validate → tạo Order + OrderItems → xoá cart → redirect confirmation
- Order: `order_number` auto-generate (`ORD-{UNIQID}`), `payment_method`, `payment_status`, subtotal/discount/tax/total

#### 4. Coupon
- Validate coupon code trong checkout
- `Coupon` model: code, type (percentage/fixed), value, min_order, max_uses, used_count, expires_at

#### 5. Admin — Orders & Customers
- `admin/orders/index.blade.php` — list với filter status, search
- `admin/orders/show.blade.php` — chi tiết đơn hàng + items
- `admin/service-orders/index.blade.php` — list service orders
- `admin/service-orders/show.blade.php` — chi tiết + update status/payment
- `admin/customers/index.blade.php` — danh sách users
- `admin/customers/show.blade.php` — profile + order history
- `admin/coupons/` — CRUD coupon

#### 6. Admin Dashboard
- `admin/dashboard.blade.php` — stats: tổng orders, revenue, customers, services; biểu đồ đơn giản; recent orders

---

## Data Models chi tiết

### Order (đơn hàng từ cart)
```
id, order_number (ORD-xxx), user_id (nullable), session_id,
first_name, last_name, email, phone,
address, city, state, zip, country,
payment_method, payment_status, payment_transaction_id,
subtotal, discount, tax, total, currency,
status (pending/confirmed/processing/completed/cancelled), notes,
deleted_at, timestamps
```

### ServiceOrder (đặt dịch vụ trực tiếp)
```
id, service_id, user_id (nullable),
name, email, phone, requirements, budget,
status (pending/confirmed/in-progress/completed/cancelled),
payment_status (unpaid/partial/paid),
admin_notes, timestamps
```

### Service
```
id, name, slug, description, full_description,
icon (class name), features (JSON array),
price (decimal), price_type (one-time/monthly/hourly/contact),
sort_order, is_featured, is_active,
deleted_at, timestamps
```

### Coupon
```
id, code (unique), type (percentage/fixed), value,
min_order_amount, max_uses, used_count,
expires_at, is_active, timestamps
```

---

## Seeding Data

```bash
php artisan db:seed
```

| Seeder | Dữ liệu |
|--------|---------|
| `AdminUserSeeder` | Admin: `admin@aloweb.com` / `password` |
| `CategorySeeder` | 5 categories (Web Design, E-commerce, Mobile App, SEO, Consulting) |
| `ServiceSeeder` | 8 services với price, features, icon |
| `SolutionSeeder` | 4 solutions kinh doanh |
| `PortfolioSeeder` | 6 portfolio items |
| `BlogSeeder` | 5 bài viết mẫu |
| `CouponSeeder` | 3 coupon mẫu (WELCOME10, SUMMER20, FIXED50) |

---

## Phân chia task

### Fullstack Agent 1 — Core Content & Admin Content
- Homepage, Services, Solutions, Portfolio, Blog, Contact pages
- Auth pages (login, register)
- Admin: Blog, Category, Solutions, Portfolio, Services, Contact Messages CRUD
- Admin layout (sidebar, header, responsive)
- Static pages hoàn thiện (tích hợp Blade layout)

### Fullstack Agent 2 — Ecommerce & Admin Transactional
- Cart (session-based, guest + user merge)
- Service Order flow (form → confirm → admin manage)
- Checkout + Order creation (với billing form, coupon)
- Admin: Orders, Service Orders, Customers, Coupons, Dashboard stats
- Email notifications (order confirm, contact)

---

## Yêu cầu phi chức năng

- Responsive design — mobile first (≥320px)
- Tiếng Việt là ngôn ngữ chính (`lang/vi/messages.php`)
- Admin panel có sidebar navigation rõ ràng
- Soft delete cho Service, Order (đã có trong model)
- Không dùng JS framework — Vanilla JS + Alpine.js (optional, nhẹ)
- Docker-ready: `Dockerfile` + `docker-compose.yml` đã có sẵn

---

## Lưu ý khi clone và làm tiếp

1. **Không thay đổi kiến trúc** — giữ nguyên Laravel MVC + Blade, không chuyển sang API
2. **Migrations đã có** — chạy `php artisan migrate` trước khi code
3. **Admin auth riêng** — `AdminLoginController` tách biệt với user auth
4. **Cart session** — `CartController` dùng `session_id` cho guest, merge sau khi login
5. **ServiceOrder ≠ Order** — hai luồng đặt hàng khác nhau (đặt dịch vụ tư vấn vs mua sản phẩm qua cart)
