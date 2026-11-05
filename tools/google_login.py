"""
Đăng nhập Google (OAuth) một lần cho MCP server của một dự án
=============================================================

Dùng khi Drive là của tài khoản Gmail CÁ NHÂN: service account không có dung
lượng lưu trữ và Gmail cá nhân không có Shared Drive, nên service account không
tạo được file nào trong "Drive của tôi" dù đã được share quyền Người chỉnh sửa.
Đăng nhập bằng chính tài khoản đó thì file tải lên thuộc về tài khoản đó.

    python tools/google_login.py <slug> <client_secret.json> [--server gfiles]

  <slug>               thư mục dự án trong clients/ (vd aloweb)
  <client_secret.json> file tải về từ Google Cloud → Credentials → OAuth client ID
                       (loại "Desktop app")
  --server             tên MCP server trong tab MCP của dự án (mặc định gfiles)

Kết quả:
  - clients/<slug>/secrets/google-oauth.json  — token dạng `authorized_user`
    (định dạng chuẩn của Google; thư viện google-auth đọc thẳng qua keyFile,
    giống hệt file key service account — server MCP không phải đổi gì).
  - [mcp.<server>] credentials_path trong clients/<slug>/settings.local.toml trỏ
    sang file đó.

clients/ đã nằm trong .gitignore — token không bị commit. Token cho phép vào TOÀN
BỘ Drive của tài khoản; ai cầm file là dùng được, đừng gửi đi đâu.

Chỉ dùng thư viện chuẩn (không cần pip install). Luồng: OAuth cho ứng dụng máy
tính + PKCE, nhận mã qua một cổng localhost tạm thời.
"""
import argparse
import base64
import hashlib
import http.server
import json
import re
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# Toàn quyền Drive: cần để tạo file trong thư mục có sẵn của người dùng (scope
# drive.file chỉ thấy file do chính ứng dụng tạo, không ghi vào "Aloweb" được).
# Hàng rào thật là danh sách tool của server: không có xoá, không có đổi quyền.
SCOPES = ["https://www.googleapis.com/auth/drive", "openid", "email"]
WAIT_S = 300


def load_client(path: Path) -> tuple[str, str]:
    if not path.is_file():
        sys.exit(f"Không thấy file {path}. Đây là file JSON tải về khi tạo OAuth client ID.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        sys.exit(f"{path} không phải file JSON.")
    block = data.get("installed") or data.get("web")
    if not block:
        sys.exit("File client_secret không đúng: thiếu mục 'installed'. Tạo OAuth client ID loại "
                 "\"Desktop app\" rồi tải lại file JSON.")
    if "web" in data:
        print("⚠️  Đây là client loại 'Web application'. Nên dùng loại 'Desktop app' — "
              "loại Web phải tự khai redirect URI http://127.0.0.1:<cổng>.")
    return block["client_id"], block["client_secret"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_code(port: int, state: str) -> str:
    """Mở cổng localhost, chờ Google chuyển trình duyệt về kèm ?code=…"""
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                body, got["error"] = "Sai state — đóng tab này và chạy lại lệnh.", "state"
            elif "error" in q:
                got["error"] = q["error"][0]
                body = f"Google báo lỗi: {got['error']}. Đóng tab này và xem terminal."
            else:
                got["code"] = q.get("code", [""])[0]
                body = "Đăng nhập xong. Đóng tab này và quay lại terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<p style='font:16px sans-serif'>{body}</p>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    srv.timeout = 1
    t = threading.Thread(target=lambda: [srv.handle_request() for _ in range(WAIT_S)
                                         if not got], daemon=True)
    t.start()
    t.join(WAIT_S + 5)
    srv.server_close()
    if "error" in got:
        sys.exit(f"Đăng nhập thất bại: {got['error']}.")
    if not got.get("code"):
        sys.exit(f"Hết {WAIT_S}s mà chưa đăng nhập xong. Chạy lại lệnh.")
    return got["code"]


def post(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Google từ chối ({e.code}): {e.read().decode(errors='replace')}")


def whoami(token: str) -> str:
    req = urllib.request.Request("https://www.googleapis.com/drive/v3/about?fields=user",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["user"].get("emailAddress", "?")


def set_credentials_path(settings: Path, server: str, value: str) -> None:
    """Đặt [mcp.<server>] credentials_path, giữ nguyên mọi dòng khác của file."""
    text = settings.read_text(encoding="utf-8") if settings.exists() else ""
    head = f"[mcp.{server}]"
    line = f'credentials_path = "{value}"'
    m = re.search(rf"^\[mcp\.{re.escape(server)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if not m:
        text = text.rstrip("\n") + ("\n\n" if text.strip() else "") + f"{head}\n{line}\n"
    else:
        body = m.group(1)
        # [ \t]* chứ không \s*: \s nuốt cả dấu xuống dòng, dính dòng vào tiêu đề mục.
        if re.search(r"^[ \t]*credentials_path[ \t]*=", body, re.M):
            body = re.sub(r"^[ \t]*credentials_path[ \t]*=.*$", line, body, count=1, flags=re.M)
        else:
            body = "\n" + line + body
        text = text[:m.start(1)] + body + text[m.end(1):]
    settings.write_text(text, encoding="utf-8")


def main() -> None:
    # Console Windows mặc định cp1252 — in tiếng Việt là nổ UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Đăng nhập Google (OAuth) cho MCP server của 1 dự án")
    ap.add_argument("slug")
    ap.add_argument("client_secret", type=Path)
    ap.add_argument("--server", default="gfiles")
    a = ap.parse_args()

    proj = ROOT / "clients" / a.slug
    if not proj.is_dir():
        sys.exit(f"Không có dự án clients/{a.slug}.")
    if not re.fullmatch(r"[a-z0-9_-]+", a.server):
        sys.exit("Tên server chỉ gồm a-z 0-9 _ -")
    client_id, client_secret = load_client(a.client_secret)

    port = free_port()
    redirect = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
        # offline + consent: bắt Google trả refresh_token (không có thì token chết sau 1 giờ)
        "access_type": "offline", "prompt": "consent",
    })

    print("Mở trình duyệt để đăng nhập Google… (không tự mở thì dán link này vào trình duyệt)")
    print(url, "\n")
    webbrowser.open(url)
    code = wait_for_code(port, state)

    tok = post(TOKEN_URL, {"code": code, "client_id": client_id, "client_secret": client_secret,
                           "redirect_uri": redirect, "grant_type": "authorization_code",
                           "code_verifier": verifier})
    if not tok.get("refresh_token"):
        sys.exit("Google không trả refresh_token. Vào https://myaccount.google.com/permissions gỡ "
                 "quyền của ứng dụng này rồi chạy lại.")
    if "https://www.googleapis.com/auth/drive" not in tok.get("scope", ""):
        sys.exit("Chưa cấp quyền Google Drive (bỏ tick ô Drive ở màn hình xin quyền?). Chạy lại "
                 "và tick đủ các ô.")
    email = whoami(tok["access_token"])

    out = proj / "secrets" / "google-oauth.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "type": "authorized_user",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tok["refresh_token"],
        "account": email,
    }, indent=2), encoding="utf-8")
    set_credentials_path(proj / "settings.local.toml", a.server, out.as_posix())

    print(f"✅ Đã đăng nhập: {email}")
    print(f"   token  → {out.relative_to(ROOT).as_posix()}")
    print(f"   cấu hình → [mcp.{a.server}] credentials_path trong clients/{a.slug}/settings.local.toml")
    print("   Bước sau của dự án tự dùng tài khoản này — không cần khởi động lại worker.")


if __name__ == "__main__":
    main()
