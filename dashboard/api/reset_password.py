"""Quên mật khẩu quản trị viên → đặt lại từ dòng lệnh (không cần đăng nhập):

    docker compose exec api python reset_password.py <tên đăng nhập> <mật khẩu mới>

Tài khoản chưa có thì tạo mới làm quản trị viên. Mọi phiên cũ của người đó bị đăng xuất.
"""

import sys

import auth
from database import SessionLocal
from models import User, UserSession


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    name, pw = sys.argv[1].strip().lower(), sys.argv[2]
    if len(pw) < 6:
        sys.exit("Mật khẩu tối thiểu 6 ký tự")
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == name).first()
        if not u:
            u = User(username=name, display_name="", is_admin=True, permissions=list(auth.TABS))
            db.add(u)
        u.password_hash = auth.hash_password(pw)
        u.is_active = True
        db.flush()
        db.query(UserSession).filter(UserSession.user_id == u.id).delete()
        db.commit()
        print(f"Đã đặt mật khẩu cho '{name}'" + (" (quản trị viên)" if u.is_admin else ""))
    finally:
        db.close()


if __name__ == "__main__":
    main()
