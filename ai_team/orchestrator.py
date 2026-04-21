"""
Orchestrator
============
Logic điều phối toàn bộ AI team.
Stage 1: PM → Stage 2: Scrum → Stage 3: Analyst → Stage 4: BE+FE
"""

import asyncio
import json
import time
from pathlib import Path

from ai_team import task_manager as tm
from ai_team import slack_bridge as slack
from ai_team.runner import run
from ai_team.config import get as get_config
from ai_team.skill_loader import load_skills, get_skills_summary


def _docs_dir(output_dir: str) -> Path:
    return Path(output_dir) / "docs"


def _read_doc(output_dir: str, filename: str) -> str:
    path = _docs_dir(output_dir) / filename
    return path.read_text(encoding="utf-8") if path.exists() else f"(chưa có {filename})"


def _new_files(work_dir: Path, before: set) -> list[str]:
    after = {str(f.relative_to(work_dir)) for f in work_dir.rglob("*") if f.is_file()}
    return sorted(after - before)


# ── Stage agents ──────────────────────────────────────────────────────────────

async def _run_stage(role: str, prompt: str, work_dir: Path, summary: str):
    cfg = get_config()
    print(f"\n[{role} / {cfg.agents[role].label}]...")
    tm.set_running(role)

    thread_ts = slack.create_task_thread(role, summary, cfg.agents[role].label)
    slack.post_to_thread(thread_ts, role, "Bắt đầu...")

    work_dir.mkdir(parents=True, exist_ok=True)
    before = {str(f.relative_to(work_dir)) for f in work_dir.rglob("*") if f.is_file()}
    start  = time.time()

    try:
        await run(role, prompt, work_dir)
        duration  = int(time.time() - start)
        new_files = _new_files(work_dir, before)
        tm.set_done(role)
        slack.post_done(thread_ts, role, new_files, duration)
        print(f"  [{role}] ✅ Xong! ({duration}s)")
    except Exception as e:
        tm.set_failed(role, str(e))
        slack.post_failed(thread_ts, role, str(e))
        print(f"  [{role}] ❌ {e}")


# ── Coding agents ─────────────────────────────────────────────────────────────

async def _coding_agent(role: str, task_doc: str, work_dir: Path, output_dir: str):
    cfg         = get_config()
    agent_cfg   = cfg.agents[role]
    task_content = _read_doc(output_dir, task_doc)
    api_contract = _read_doc(output_dir, "api_contract.md")
    data_models  = _read_doc(output_dir, "data_models.md")
    summary      = task_content.split("\n")[0].replace("#", "").strip()[:120]

    print(f"\n[{role} / {agent_cfg.label}] Bắt đầu coding...")
    tm.set_running(role)

    thread_ts = slack.create_task_thread(role, summary, agent_cfg.label)
    slack.post_to_thread(thread_ts, role, f"Đọc `{task_doc}`...")

    work_dir.mkdir(parents=True, exist_ok=True)
    before     = {str(f.relative_to(work_dir)) for f in work_dir.rglob("*") if f.is_file()}
    start      = time.time()
    issue_file = work_dir / f"_issue_{role.replace(' ', '_')}.json"

    task_prompt = f"""Bạn là {role} trong AI development team.

TASK CỦA BẠN:
{task_content}

API CONTRACT:
{api_contract}

DATA MODELS:
{data_models}

Tech stack: {cfg.tech_backend} (backend) / {cfg.tech_frontend} (frontend)

Yêu cầu:
- Áp dụng đúng skills đã học ở trên khi viết code
- Implement đúng theo tài liệu task, viết code đầy đủ vào working directory
- Nếu phát hiện vấn đề với tài liệu (API sai, thiếu field, logic không khả thi):
  1. Vẫn implement theo hiểu biết tốt nhất
  2. Tạo file {issue_file}:
     {{"issues": [{{"severity": "high/medium/low", "description": "...", "suggestion": "..."}}]}}
- Không hỏi lại, implement thẳng"""

    # Inject skills vào đầu prompt
    skills = load_skills(role)
    prompt = (skills + "\n" + task_prompt) if skills else task_prompt

    try:
        await run(role, prompt, work_dir)
        duration  = int(time.time() - start)
        new_files = _new_files(work_dir, before)

        # Xử lý issue nếu agent report
        if issue_file.exists():
            try:
                issues = json.loads(issue_file.read_text())["issues"]
                for issue in issues:
                    sev  = issue.get("severity", "medium")
                    desc = issue.get("description", "")
                    sugg = issue.get("suggestion", "")
                    icon = "🔴" if sev == "high" else "🟡"
                    msg  = f"{icon} [{sev.upper()}] {desc}"
                    if sugg:
                        msg += f"\n💡 Đề xuất: {sugg}"
                    slack.post_issue(thread_ts, role, msg, mention="Analyst")
                    print(f"  [{role}] Issue {sev}: {desc[:60]}")
                issue_file.unlink()
            except Exception:
                pass

        code_files = [f for f in new_files if not f.startswith("_")]
        tm.set_done(role)
        slack.post_done(thread_ts, role, code_files, duration)
        print(f"  [{role}] ✅ Xong! ({duration}s, {len(code_files)} files)")

    except Exception as e:
        tm.set_failed(role, str(e))
        slack.post_failed(thread_ts, role, str(e))
        print(f"  [{role}] ❌ {e}")

    tm.print_status()


# ── Main orchestrate ──────────────────────────────────────────────────────────

async def orchestrate(prd: str, output_dir: str = "./output"):
    cfg      = get_config()
    out      = Path(output_dir)
    docs_dir = out / "docs"
    be_dir   = out / "backend"
    fe_dir   = out / "frontend"

    out.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AI TEAM ORCHESTRATOR")
    print("-" * 60)
    for role, a in cfg.agents.items():
        print(f"  {role:14} → {a.label}")
    slack_st = "✅ Connected" if cfg.slack_enabled else "⚠️  Offline (điền token để bật)"
    print(f"\nSlack:  {slack_st}")
    print(f"Output: {out.resolve()}")
    print("=" * 60)

    tm.init({
        "PM Agent":     "Viết user stories và acceptance criteria",
        "Scrum Master": "Tạo backlog và sprint plan",
        "Analyst":      "Thiết kế API, data model, chia task",
        "BE Agent 1":   "Implement backend theo be1_task.md",
        "BE Agent 2":   "Implement backend theo be2_task.md",
        "FE Agent 1":   "Implement frontend theo fe1_task.md",
        "FE Agent 2":   "Implement frontend theo fe2_task.md",
    })
    tm.print_status()

    # Stage 1: PM
    await _run_stage("PM Agent", f"""Bạn là Product Manager AI.

PRD:
{prd}

Tạo 2 file trong docs/:
1. docs/user_stories.md — User stories: As a/I want/So that + story points
2. docs/acceptance.md   — Acceptance criteria: Given/When/Then""",
        out, "Viết user stories từ PRD")
    tm.print_status()

    # Stage 2: Scrum
    await _run_stage("Scrum Master", f"""Bạn là Scrum Master AI.

USER STORIES:
{_read_doc(output_dir, 'user_stories.md')}

ACCEPTANCE:
{_read_doc(output_dir, 'acceptance.md')}

Tạo 2 file trong docs/:
1. docs/backlog.md      — Backlog có priority, points, assignee (BE1/BE2/FE1/FE2)
2. docs/sprint_plan.md  — Sprint plan chia task chi tiết cho từng agent""",
        out, "Tạo backlog và sprint plan")
    tm.print_status()

    # Stage 3: Analyst
    await _run_stage("Analyst", f"""Bạn là Tech Lead AI.

USER STORIES:
{_read_doc(output_dir, 'user_stories.md')}

SPRINT PLAN:
{_read_doc(output_dir, 'sprint_plan.md')}

Tech stack: {cfg.tech_backend} / {cfg.tech_frontend}

Tạo trong docs/:
- docs/api_contract.md  — Tất cả endpoints, request/response schema
- docs/data_models.md   — Database schema đầy đủ
- docs/be1_task.md      — Task chi tiết BE Agent 1
- docs/be2_task.md      — Task chi tiết BE Agent 2
- docs/fe1_task.md      — Task chi tiết FE Agent 1
- docs/fe2_task.md      — Task chi tiết FE Agent 2""",
        out, "Thiết kế kỹ thuật và chia task")
    tm.print_status()

    # Stage 4a: BE song song
    print("\n[Orchestrator] Stage 4a — BE agents song song...")
    await asyncio.gather(
        _coding_agent("BE Agent 1", "be1_task.md", be_dir, output_dir),
        _coding_agent("BE Agent 2", "be2_task.md", be_dir, output_dir),
    )

    # Stage 4b: FE song song
    print("\n[Orchestrator] Stage 4b — FE agents song song...")
    await asyncio.gather(
        _coding_agent("FE Agent 1", "fe1_task.md", fe_dir, output_dir),
        _coding_agent("FE Agent 2", "fe2_task.md", fe_dir, output_dir),
    )

    # Sprint summary
    all_files  = [f for f in out.rglob("*") if f.is_file()]
    code_files = [f for f in all_files if f.suffix in [".py", ".ts", ".tsx", ".json", ".toml"]]
    doc_files  = [f for f in all_files if f.suffix == ".md"]

    slack.post_sprint_summary({r: t["status"] for r, t in tm.get_all().items()})

    print("\n" + "=" * 60)
    print(f"XONG! {out.resolve()}")
    print(f"  Docs: {len(doc_files)} files  |  Code: {len(code_files)} files")
    tm.print_status()
