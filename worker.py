"""
AI Team Queue Worker
====================
Chạy TRÊN HOST (không dockerize) — nơi có `main.py`, Claude/OpenCode CLI,
git và thư mục `clients/`. Poll Dashboard API lấy job đang chờ rồi chạy
pipeline tuần tự, thay cho việc gõ tay:

    python main.py --config clients/<slug>/settings.toml --prd clients/<slug>/prd.md

Cách dùng — mở 1 terminal, chạy 1 lần rồi để đó:

    python worker.py

Từ đó về sau chỉ cần bấm nút ▶ Run trên Dashboard.

Chỉ dùng thư viện chuẩn (urllib) → không cần cài thêm gì.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API   = os.getenv("DASHBOARD_API_URL", "http://localhost:8000")
ROOT  = Path(__file__).resolve().parent
POLL  = int(os.getenv("WORKER_POLL_S", "3"))


def _req(path: str, body: dict | None = None, method: str = "GET"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def _claim() -> dict | None:
    # Trả null khi rỗng hoặc đang có job chạy (server giữ tuần tự)
    return _req("/api/run-jobs/claim", body={}, method="POST")


def _complete(job_id: int, status: str, error: str = ""):
    try:
        _req(f"/api/run-jobs/{job_id}/complete",
             body={"status": status, "error": error[:1000]}, method="POST")
    except Exception as e:
        print(f"[worker] ⚠️  Không báo được complete cho job #{job_id}: {e}")


def _run_job(job: dict):
    job_id = job["id"]
    slug   = job["client_folder"]
    cfg    = ROOT / "clients" / slug / "settings.toml"
    prd    = ROOT / "clients" / slug / "prd.md"

    if not cfg.exists():
        print(f"[worker] ❌ Job #{job_id}: không tìm thấy {cfg}")
        _complete(job_id, "failed", f"Không tìm thấy {cfg}")
        return
    if not prd.exists():
        print(f"[worker] ❌ Job #{job_id}: không tìm thấy {prd}")
        _complete(job_id, "failed", f"Không tìm thấy {prd}")
        return

    env = os.environ.copy()
    env["CLIENT_NAME"]        = slug
    env["AI_TEAM_PROJECT_ID"] = str(job.get("project_id") or "")
    env["FEATURE_IDS"]        = job.get("feature_ids") or ""
    env.setdefault("DASHBOARD_API_URL", API)

    cmd = [
        sys.executable, "main.py",
        "--config", f"clients/{slug}/settings.toml",
        "--prd",    f"clients/{slug}/prd.md",
    ]
    if job.get("profile"):
        cmd += ["--profile", job["profile"]]

    print(f"\n[worker] ▶ Job #{job_id} ({slug}) → {' '.join(cmd)}")
    try:
        # stdout/stderr kế thừa terminal → xem log pipeline trực tiếp
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    except Exception as e:
        print(f"[worker] ❌ Job #{job_id} lỗi khi spawn: {e}")
        _complete(job_id, "failed", str(e))
        return

    if proc.returncode == 0:
        print(f"[worker] ✅ Job #{job_id} ({slug}) hoàn thành")
        _complete(job_id, "done")
    else:
        print(f"[worker] ❌ Job #{job_id} ({slug}) thất bại (exit {proc.returncode})")
        _complete(job_id, "failed", f"main.py exit code {proc.returncode}")


def main():
    print(f"[worker] AI Team queue worker khởi động")
    print(f"[worker]   API  = {API}")
    print(f"[worker]   root = {ROOT}")
    print(f"[worker]   poll = {POLL}s")
    print(f"[worker] Đang chờ job... (Ctrl+C để dừng)\n")

    while True:
        job = None
        try:
            job = _claim()
        except urllib.error.URLError as e:
            print(f"[worker] ⏳ API chưa sẵn sàng ({e.reason}); thử lại sau {POLL}s")
        except Exception as e:
            print(f"[worker] ⚠️  claim lỗi: {e}")

        if job:
            _run_job(job)
            continue  # chạy ngay job kế tiếp nếu còn, không chờ POLL

        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[worker] Dừng theo yêu cầu. Tạm biệt 👋")
