"""
Task Manager
============
Theo dõi trạng thái từng agent, lưu vào tasks.json.
Đồng thời gửi updates lên Dashboard API (PostgreSQL).
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

TASKS_FILE        = Path("./tasks.json")
_CURRENT_RUN_FILE = Path("./_dashboard_run.json")
_API_URL          = os.getenv("DASHBOARD_API_URL", "http://localhost:8000")

_run_id: int | None = None


# ── Local JSON helpers ────────────────────────────────────────

def _load() -> dict:
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict):
    TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Dashboard API helpers ─────────────────────────────────────

def _get_run_id() -> int | None:
    global _run_id
    if _run_id is not None:
        return _run_id
    if _CURRENT_RUN_FILE.exists():
        try:
            _run_id = json.loads(_CURRENT_RUN_FILE.read_text())["run_id"]
        except Exception:
            pass
    return _run_id


def _set_run_id(rid: int):
    global _run_id
    _run_id = rid
    _CURRENT_RUN_FILE.write_text(json.dumps({"run_id": rid}), encoding="utf-8")


def _api_post(path: str, body: dict) -> dict | None:
    """Fire-and-forget POST — never raises, never blocks the orchestrator."""
    try:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{_API_URL}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        pass
    return None


# ── Public API ────────────────────────────────────────────────

def init(roles: dict[str, str]):
    """Khởi tạo tasks.json. roles = {agent_name: description}"""
    tasks = {
        role: {
            "role": role, "description": desc,
            "status": "pending",
            "started_at": None, "finished_at": None,
            "duration_s": None, "error": None,
        }
        for role, desc in roles.items()
    }
    _save(tasks)
    print(f"[TaskManager] Khởi tạo {len(tasks)} tasks → {TASKS_FILE}")

    # Create run in Dashboard API
    try:
        from ai_team.config import get as get_config
        cfg     = get_config()
        profile = cfg.profile
        client  = os.getenv("CLIENT_NAME", Path(".").resolve().name)
    except Exception:
        profile = None
        client  = Path(".").resolve().name

    result = _api_post("/api/runs", {
        "client":  client,
        "profile": profile,
        "tasks":   [{"role": r, "description": d} for r, d in roles.items()],
    })
    if result and "id" in result:
        _set_run_id(result["id"])
        print(f"[TaskManager] Dashboard run #{result['id']} created → {_API_URL}")


def set_running(role: str):
    data = _load()
    if role in data:
        data[role]["status"]     = "running"
        data[role]["started_at"] = datetime.now().strftime("%H:%M:%S")
    _save(data)

    run_id = _get_run_id()
    if run_id:
        _api_post("/api/tasks/update", {
            "run_id":     run_id,
            "role":       role,
            "status":     "running",
            "started_at": data.get(role, {}).get("started_at"),
        })


def set_done(role: str):
    data = _load()
    if role in data:
        data[role]["status"]      = "done"
        data[role]["finished_at"] = now = datetime.now().strftime("%H:%M:%S")
        if data[role]["started_at"]:
            fmt = "%H:%M:%S"
            s   = datetime.strptime(data[role]["started_at"], fmt)
            e   = datetime.strptime(now, fmt)
            data[role]["duration_s"] = int((e - s).total_seconds())
    _save(data)

    run_id = _get_run_id()
    if run_id:
        t = data.get(role, {})
        _api_post("/api/tasks/update", {
            "run_id":      run_id,
            "role":        role,
            "status":      "done",
            "started_at":  t.get("started_at"),
            "finished_at": t.get("finished_at"),
            "duration_s":  t.get("duration_s"),
        })


def set_failed(role: str, error: str):
    data = _load()
    if role in data:
        data[role]["status"]      = "failed"
        data[role]["finished_at"] = datetime.now().strftime("%H:%M:%S")
        data[role]["error"]       = error[:200]
    _save(data)

    run_id = _get_run_id()
    if run_id:
        t = data.get(role, {})
        _api_post("/api/tasks/update", {
            "run_id":      run_id,
            "role":        role,
            "status":      "failed",
            "finished_at": t.get("finished_at"),
            "error":       error[:200],
        })


def report_issue(role: str, severity: str, description: str, suggestion: str = ""):
    """Gửi issue lên Dashboard API."""
    run_id = _get_run_id()
    if run_id:
        _api_post("/api/issues", {
            "run_id":      run_id,
            "role":        role,
            "severity":    severity,
            "description": description,
            "suggestion":  suggestion,
        })


def get_all() -> dict:
    return _load()


def print_status():
    data = _load()
    if not data:
        return

    icons = {"pending": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}
    print("\n┌────────────────┬──────────────┬──────────┬───────────┐")
    print("│ Agent          │ Status       │ Start    │ Duration  │")
    print("├────────────────┼──────────────┼──────────┼───────────┤")
    for role, t in data.items():
        icon     = icons.get(t["status"], "?")
        status   = f"{icon} {t['status']}"
        start    = t["started_at"]  or "-"
        duration = f"{t['duration_s']}s" if t["duration_s"] else "-"
        print(f"│ {role:14} │ {status:12} │ {start:8} │ {duration:9} │")
    print("└────────────────┴──────────────┴──────────┴───────────┘")
    statuses = [t["status"] for t in data.values()]
    print(f"  ✅{statuses.count('done')} done  🔄{statuses.count('running')} running  "
          f"⏳{statuses.count('pending')} pending  ❌{statuses.count('failed')} failed\n")
