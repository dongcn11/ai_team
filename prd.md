# Product Requirements Document

## Tên sản phẩm
Todo App

## Mục tiêu
Xây dựng web app quản lý công việc cá nhân, đơn giản và dễ dùng.

## Người dùng mục tiêu
- Cá nhân muốn quản lý công việc hàng ngày
- Nhóm nhỏ cần theo dõi tiến độ

## Tính năng

### 1. Xác thực
- Đăng ký tài khoản (username, email, password)
- Đăng nhập / đăng xuất
- JWT access token + refresh token
- Bảo vệ routes cần đăng nhập

### 2. Quản lý Tasks
- Tạo task mới: title, description, deadline, priority
- Xem danh sách tasks của mình
- Cập nhật task: title, description, status, deadline
- Xóa task
- Status workflow: todo → in-progress → done

### 3. Lọc và Tìm kiếm
- Filter theo status (todo / in-progress / done)
- Filter theo priority (low / medium / high)
- Search theo title

### 4. UI/UX
- Responsive (mobile + desktop)
- Dark mode / Light mode
- Loading states khi gọi API
- Error messages rõ ràng

## Yêu cầu phi chức năng
- API response time < 500ms
- Xử lý lỗi đầy đủ (validation, 404, 500)
- Code có comment, dễ đọc
