"""
Slack Bridge
============
Giao tiếp với Slack API.
Khi chưa có token → chạy offline, log ra terminal.
"""

import json
import urllib.request
from datetime import datetime
from ai_team.config import get as get_config

ROLE_EMOJI = {
    "PM Agent": "📋", "Scrum Master": "🏃", "Analyst": "🧠",
    "BE Agent 1": "⚙️", "BE Agent 2": "⚙️",
    "FE Agent 1": "🖥️", "FE Agent 2": "🖥️",
    "Orchestrator": "🤖",
}


def _cfg():
    return get_config()


def _post(endpoint: str, payload: dict) -> dict:
    cfg = _cfg()
    if not cfg.slack_enabled:
        return {"ok": False, "error": "slack_disabled"}

    url  = f"https://slack.com/api/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {cfg.slack_token}",
            "Content-Type":  "application/json; charset=utf-8",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _log(action: str, role: str, msg: str):
    print(f"  [Slack/{action}] [{role}] {msg[:100]}")


def create_task_thread(role: str, task_summary: str, model: str) -> str | None:
    emoji = ROLE_EMOJI.get(role, "🤖")
    text  = (
        f"{emoji} *{role}* bắt đầu task\n"
        f">  {task_summary[:200]}\n"
        f"Model: `{model}` — {datetime.now().strftime('%H:%M:%S')}"
    )
    _log("create_thread", role, task_summary[:60])

    cfg  = _cfg()
    resp = _post("chat.postMessage", {"channel": cfg.slack_channel, "text": text, "mrkdwn": True})
    return resp.get("ts") if resp.get("ok") else None


def post_to_thread(thread_ts: str | None, role: str, message: str):
    emoji = ROLE_EMOJI.get(role, "🤖")
    _log("post", role, message[:80])
    if not thread_ts:
        return
    cfg = _cfg()
    _post("chat.postMessage", {
        "channel": cfg.slack_channel, "thread_ts": thread_ts,
        "text": f"{emoji} *{role}*: {message}", "mrkdwn": True,
    })


def post_issue(thread_ts: str | None, role: str, issue: str, mention: str = "Analyst"):
    emoji = ROLE_EMOJI.get(role, "🤖")
    text  = f"{emoji} *{role}* gặp vấn đề ❓\n>  {issue}\n@{mention} cần review"
    _log("issue", role, issue[:80])
    if not thread_ts:
        return
    cfg = _cfg()
    _post("chat.postMessage", {
        "channel": cfg.slack_channel, "thread_ts": thread_ts,
        "text": text, "mrkdwn": True,
    })


def post_done(thread_ts: str | None, role: str, files: list[str], duration_s: int):
    emoji     = ROLE_EMOJI.get(role, "🤖")
    files_str = "\n".join(f"  • `{f}`" for f in files[:10])
    text      = f"{emoji} *{role}* hoàn thành ✅ ({duration_s}s)\n{files_str}"
    _log("done", role, f"{len(files)} files, {duration_s}s")
    if not thread_ts:
        return
    cfg = _cfg()
    _post("chat.postMessage", {
        "channel": cfg.slack_channel, "thread_ts": thread_ts,
        "text": text, "mrkdwn": True,
    })


def post_failed(thread_ts: str | None, role: str, error: str):
    emoji = ROLE_EMOJI.get(role, "🤖")
    _log("failed", role, error[:80])
    if not thread_ts:
        return
    cfg = _cfg()
    _post("chat.postMessage", {
        "channel": cfg.slack_channel, "thread_ts": thread_ts,
        "text": f"{emoji} *{role}* thất bại ❌\n>  {error[:300]}", "mrkdwn": True,
    })


def post_sprint_summary(roles_status: dict):
    done  = sum(1 for v in roles_status.values() if v == "done")
    total = len(roles_status)
    lines = [f"🤖 *Sprint hoàn thành* — {done}/{total} tasks done\n"]
    for role, status in roles_status.items():
        lines.append(f"{'✅' if status == 'done' else '❌'} {role}")
    _log("summary", "Orchestrator", f"{done}/{total} done")
    cfg = _cfg()
    _post("chat.postMessage", {
        "channel": cfg.slack_channel,
        "text": "\n".join(lines), "mrkdwn": True,
    })
