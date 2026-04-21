"""
Task Manager
============
Theo dõi trạng thái từng agent, lưu vào tasks.json.
"""

import json
from pathlib import Path
from datetime import datetime

TASKS_FILE = Path("./tasks.json")


def _load() -> dict:
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict):
    TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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


def set_running(role: str):
    data = _load()
    if role in data:
        data[role]["status"]     = "running"
        data[role]["started_at"] = datetime.now().strftime("%H:%M:%S")
    _save(data)


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


def set_failed(role: str, error: str):
    data = _load()
    if role in data:
        data[role]["status"]      = "failed"
        data[role]["finished_at"] = datetime.now().strftime("%H:%M:%S")
        data[role]["error"]       = error[:200]
    _save(data)


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
