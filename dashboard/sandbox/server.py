"""
Sandbox tạo file cho khung "Trò chuyện"
=======================================

Model viết script Python (khối ```python-file```), API gửi sang đây chạy và nhận
lại các file script ghi vào `out/`. Chạy trong container riêng (docker-compose):
không có mạng ra ngoài, không mount ổ đĩa nào, root fs chỉ đọc, user thường,
giới hạn RAM/CPU/số tiến trình. Ở đây chặn thêm từng lần chạy: thời gian, RAM,
cỡ file, số file.

    POST /run  {"code": "...", "files": [{"name", "data"(base64)}]}
         →     {"ok", "files": [{"name", "mime", "data"}], "stdout", "stderr", "error"}

Chỉ dùng thư viện chuẩn — server không cần gì ngoài Python.
"""

import base64
import json
import mimetypes
import os
import resource
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TIMEOUT_S = int(os.getenv("SANDBOX_TIMEOUT_S", "90"))
MEM_BYTES = int(os.getenv("SANDBOX_MEM_MB", "1024")) * 1024 * 1024
OUT_MAX_FILES = 10
OUT_MAX_BYTES = 25 * 1024 * 1024
BODY_MAX = 64 * 1024 * 1024
_TAIL = 4000

mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx")
mimetypes.add_type("text/markdown", ".md")


def _limits():
    """Chạy trong tiến trình con trước khi exec script."""
    resource.setrlimit(resource.RLIMIT_AS, (MEM_BYTES, MEM_BYTES))
    resource.setrlimit(resource.RLIMIT_FSIZE, (OUT_MAX_BYTES, OUT_MAX_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S + 5))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    os.setsid()


def run(code: str, files: list) -> dict:
    work = Path(tempfile.mkdtemp(prefix="job-", dir="/tmp"))
    try:
        (work / "in").mkdir()
        (work / "out").mkdir()
        for f in files or []:
            name = Path(str(f.get("name") or "")).name
            if name:
                (work / "in" / name).write_bytes(base64.b64decode(f.get("data") or ""))
        (work / "script.py").write_text(code, encoding="utf-8")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(work),
               "MPLCONFIGDIR": str(work / ".mpl"), "MPLBACKEND": "Agg",
               "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}
        try:
            p = subprocess.run(["python", "-I", "script.py"], cwd=work, env=env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=TIMEOUT_S, preexec_fn=_limits)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Script chạy quá {TIMEOUT_S}s", "files": []}
        out, total = [], 0
        for f in sorted((work / "out").rglob("*")):
            if not f.is_file():
                continue
            if len(out) >= OUT_MAX_FILES:
                break
            data = f.read_bytes()
            total += len(data)
            if total > OUT_MAX_BYTES:
                break
            out.append({"name": f.name, "data": base64.b64encode(data).decode(),
                        "mime": mimetypes.guess_type(f.name)[0] or "application/octet-stream"})
        err = None
        if p.returncode in (-9, -24):     # SIGKILL / SIGXCPU: vượt giới hạn RAM hoặc CPU
            err = f"Script bị dừng vì vượt giới hạn ({TIMEOUT_S}s CPU / {MEM_BYTES // 1024 // 1024}MB RAM)"
        elif p.returncode != 0:
            err = (p.stderr or "").strip()[-_TAIL:] or f"Script thoát với mã {p.returncode}"
        elif not out:
            err = "Script chạy xong nhưng không ghi file nào vào thư mục out/"
        return {"ok": err is None, "error": err, "files": out,
                "stdout": (p.stdout or "")[-_TAIL:], "stderr": (p.stderr or "")[-_TAIL:]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send(200, {"ok": True}) if self.path == "/health" else self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > BODY_MAX:
            return self._send(413, {"error": "body quá lớn"})
        try:
            req = json.loads(self.rfile.read(n))
            self._send(200, run(str(req.get("code") or ""), req.get("files") or []))
        except Exception as e:
            self._send(500, {"ok": False, "error": f"sandbox lỗi: {e}", "files": []})

    def log_message(self, fmt, *args):
        print("[sandbox]", fmt % args, flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
