"""
Gọi container `sandbox` (dashboard/sandbox/server.py) chạy script Python model viết
để tạo file. Dùng chung cho khung Trò chuyện (routers/assistant.py) và LLM gateway
(`output: "docx"`… — llm_gateway.py).

Model trả về 1 khối ```python-file```; GUIDE là quy ước dặn model (thư mục, thư
viện, font) — sửa thư viện trong sandbox/Dockerfile thì sửa luôn ở đây.
"""

import json
import os
import re
import urllib.error
import urllib.request

SANDBOX_URL = os.getenv("SANDBOX_URL", "http://sandbox:8000").rstrip("/")
BLOCK = re.compile(r"```python-file[^\n]*\n(.*?)```", re.S)

GUIDE = (
    "Viết MỘT khối code bắt đầu bằng ```python-file chứa script Python 3.12 hoàn chỉnh; "
    "hệ thống chạy script trong sandbox rồi giao file kết quả. Quy ước:\n"
    "- Ghi file kết quả vào thư mục `out/` (đường dẫn tương đối, vd `out/bao-cao.docx`), "
    "đặt tên file có nghĩa; tối đa 10 file, 25MB.\n"
    "- File người dùng gửi kèm nằm ở thư mục `in/` (cùng tên).\n"
    "- Thư viện có sẵn: python-docx, openpyxl, xlsxwriter, python-pptx, reportlab, "
    "matplotlib, pillow, pandas + thư viện chuẩn. KHÔNG có mạng, không cài thêm được gì.\n"
    "- Chữ tiếng Việt trong PDF/ảnh/biểu đồ: dùng font DejaVu Sans tại "
    "`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (đậm: `DejaVuSans-Bold.ttf`) — "
    "reportlab phải registerFont font này, matplotlib đặt rcParams['font.family']='DejaVu Sans'.\n"
    "- Ngoài khối code chỉ viết 1–3 câu nói file có gì; đừng dán lại nội dung file."
)


def split(text: str) -> tuple:
    """(script hoặc None, phần chữ còn lại sau khi bỏ khối python-file)."""
    m = BLOCK.search(text or "")
    if not m:
        return None, text
    return m.group(1).strip(), BLOCK.sub("", text).strip()


def run(code: str, files: list) -> dict:
    """files = [{"name", "data"(base64)}] → {"ok", "files": [{"name","mime","data"}], "error"}."""
    req = urllib.request.Request(f"{SANDBOX_URL}/run", method="POST",
                                 data=json.dumps({"code": code, "files": files}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "files": [],
                "error": f"Không gọi được sandbox tạo file ({e}) — container `sandbox` có đang chạy?"}
