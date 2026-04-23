"""
Orchestrator
============
Logic điều phối toàn bộ AI team.
Stage 1: PM → Stage 2: Scrum (optional) → Stage 3: Analyst → Stage 4: BE+FE → Stage 5: Leader Review
"""

import asyncio
import json
import re
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


def _extract_repo_url(text: str) -> str | None:
    match = re.search(r'https://github\.com/[\w\-]+/[\w\-]+', text)
    return match.group(0) if match else None


def _branch_name(role: str) -> str:
    mapping = {
        "BE Agent 1":         "feature/be1",
        "BE Agent 2":         "feature/be2",
        "FE Agent 1":         "feature/fe1",
        "FE Agent 2":         "feature/fe2",
        "Fullstack Agent 1":  "feature/fs1",
        "Fullstack Agent 2":  "feature/fs2",
    }
    return mapping.get(role, f"feature/{role.lower().replace(' ', '-')}")


def _new_files(work_dir: Path, before: set) -> list[str]:
    after = set()
    for f in work_dir.rglob("*"):
        try:
            if f.is_file():
                after.add(str(f.relative_to(work_dir)))
        except OSError:
            pass
    return sorted(after - before)


def _enabled(role: str) -> bool:
    return role in get_config().enabled_agents


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
        err = str(e) or type(e).__name__
        tm.set_failed(role, err)
        slack.post_failed(thread_ts, role, err)
        print(f"  [{role}] ❌ {err}")


# ── Progress reporter ─────────────────────────────────────────────────────────

async def _progress_reporter(role: str, work_dir: Path, start: float, interval: int = 60):
    """In tiến độ mỗi `interval` giây: số files + file mới nhất."""
    prev_count = 0
    while True:
        await asyncio.sleep(interval)
        try:
            candidates = []
            for f in work_dir.rglob("*"):
                try:
                    if f.is_file():
                        candidates.append(f)
                except OSError:
                    pass
            all_files = sorted(candidates, key=lambda f: f.stat().st_mtime)
            count    = len(all_files)
            elapsed  = int(time.time() - start)
            new      = count - prev_count
            latest   = all_files[-1].name if all_files else "-"
            print(f"  [{role}] ⏳ {elapsed}s | {count} files (+{new}) | latest: {latest}")
            prev_count = count
        except Exception:
            pass


# ── Coding agents ─────────────────────────────────────────────────────────────

async def _coding_agent(role: str, task_doc: str, work_dir: Path, output_dir: str, repo_url: str | None = None):
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

    role_prefix = _branch_name(role)  # e.g. "feature/fs1"
    git_workflow = f"""GIT WORKFLOW — bắt buộc thực hiện theo từng feature:

1. Clone repo (chỉ làm 1 lần đầu):
     git clone {repo_url} .

2. Với MỖI feature trong task, tạo branch riêng rồi implement:
     git checkout -b {role_prefix}/<feature-slug>
     # Ví dụ: {role_prefix}/auth-system, {role_prefix}/services-crud, {role_prefix}/contact-page

3. Sau khi feature đó xong, commit + push + tạo Pull Request:
     git add .
     git commit -m "feat: <mô tả feature>"
     git push origin {role_prefix}/<feature-slug>
     gh pr create \\
       --title "feat: <mô tả feature>" \\
       --body "## Summary\\n<mô tả chi tiết>\\n\\n## Checklist\\n- [ ] Đã test\\n- [ ] Theo đúng API contract" \\
       --label "review-needed"

4. Sau khi tạo PR xong, checkout về main/master rồi tiếp tục feature tiếp theo:
     git checkout main

Lặp lại bước 2-4 cho từng feature trong task của bạn.
""" if repo_url else f"""GIT WORKFLOW — bắt buộc thực hiện theo từng feature:

1. Với MỖI feature trong task, tạo branch riêng rồi implement:
     git checkout -b {role_prefix}/<feature-slug>
     # Ví dụ: {role_prefix}/cart-system, {role_prefix}/orders-api, {role_prefix}/admin-dashboard

2. Sau khi feature đó xong, commit + push + tạo Pull Request:
     git add .
     git commit -m "feat: <mô tả feature>"
     git push origin {role_prefix}/<feature-slug>
     gh pr create \\
       --title "feat: <mô tả feature>" \\
       --body "## Summary\\n<mô tả chi tiết>\\n\\n## Checklist\\n- [ ] Đã test\\n- [ ] Theo đúng API contract" \\
       --label "review-needed"

3. Checkout về main rồi tiếp tục feature tiếp theo:
     git checkout main

Lặp lại bước 1-3 cho từng feature trong task của bạn.
"""

    task_prompt = f"""Bạn là {role} trong AI development team.

{git_workflow}
TASK CỦA BẠN:
{task_content}

API CONTRACT:
{api_contract}

DATA MODELS:
{data_models}

Tech stack: {cfg.tech_backend} / {cfg.tech_frontend}

Yêu cầu:
- Áp dụng đúng skills đã học ở trên khi viết code
- Implement đúng theo tài liệu task, viết code đầy đủ vào working directory
- Nếu phát hiện vấn đề với tài liệu (API sai, thiếu field, logic không khả thi):
  1. Vẫn implement theo hiểu biết tốt nhất
  2. Tạo file {issue_file}:
     {{"issues": [{{"severity": "high/medium/low", "description": "...", "suggestion": "..."}}]}}
- Không hỏi lại, implement thẳng"""

    skills = load_skills(role)
    prompt = (skills + "\n" + task_prompt) if skills else task_prompt

    try:
        reporter = asyncio.create_task(_progress_reporter(role, work_dir, start))
        try:
            await run(role, prompt, work_dir)
        finally:
            reporter.cancel()
        duration  = int(time.time() - start)
        new_files = _new_files(work_dir, before)

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
        err = str(e) or type(e).__name__
        tm.set_failed(role, err)
        slack.post_failed(thread_ts, role, err)
        print(f"  [{role}] ❌ {err}")

    tm.print_status()


# ── Leader / Review agent ─────────────────────────────────────────────────────

async def _review_agent(output_dir: str):
    cfg       = get_config()
    role      = "Leader Agent"
    agent_cfg = cfg.agents[role]
    out       = Path(output_dir)
    docs_dir  = out / "docs"

    api_contract = _read_doc(output_dir, "api_contract.md")
    data_models  = _read_doc(output_dir, "data_models.md")
    user_stories = _read_doc(output_dir, "user_stories.md")

    def _collect_code(subdir: str) -> str:
        target = out / subdir
        if not target.exists():
            return f"(thư mục {subdir} không tồn tại)"
        parts = []
        for f in sorted(target.rglob("*")):
            try:
                is_file = f.is_file()
            except OSError:
                continue
            if is_file and f.suffix in {".py", ".ts", ".tsx", ".js", ".json", ".toml", ".yaml"}:
                rel = f.relative_to(out)
                try:
                    content = f.read_text(encoding="utf-8")
                    parts.append(f"### {rel}\n```\n{content}\n```")
                except Exception:
                    pass
        return "\n\n".join(parts) if parts else f"(không có file code trong {subdir})"

    # Chỉ thu thập code từ agents đang enabled
    code_sections = []
    if _enabled("BE Agent 1"):
        code_sections.append(f"CODE BE AGENT 1 (backend/be1/):\n{_collect_code('backend/be1')}")
    if _enabled("BE Agent 2"):
        code_sections.append(f"CODE BE AGENT 2 (backend/be2/):\n{_collect_code('backend/be2')}")
    if _enabled("FE Agent 1"):
        code_sections.append(f"CODE FE AGENT 1 (frontend/fe1/):\n{_collect_code('frontend/fe1')}")
    if _enabled("FE Agent 2"):
        code_sections.append(f"CODE FE AGENT 2 (frontend/fe2/):\n{_collect_code('frontend/fe2')}")
    if _enabled("Fullstack Agent 1"):
        code_sections.append(f"CODE FULLSTACK AGENT 1 (fullstack/fs1/):\n{_collect_code('fullstack/fs1')}")
    if _enabled("Fullstack Agent 2"):
        code_sections.append(f"CODE FULLSTACK AGENT 2 (fullstack/fs2/):\n{_collect_code('fullstack/fs2')}")

    code_block = "\n\n---\n\n".join(code_sections) if code_sections else "(không có code để review)"

    summary = "Review toàn bộ code của các coding agents"
    print(f"\n[{role} / {agent_cfg.label}] Bắt đầu review code...")
    tm.set_running(role)

    thread_ts = slack.create_task_thread(role, summary, agent_cfg.label)
    slack.post_to_thread(thread_ts, role, "Đang đọc và review code từ tất cả agents...")

    start  = time.time()
    before = {str(f.relative_to(docs_dir)) for f in docs_dir.rglob("*") if f.is_file()}

    task_prompt = f"""Bạn là Leader Agent — Tech Lead review toàn bộ code của AI development team.

USER STORIES:
{user_stories}

API CONTRACT:
{api_contract}

DATA MODELS:
{data_models}

---

{code_block}

---

Yêu cầu:
- Review kỹ từng agent theo skill guidelines
- Đánh giá sự nhất quán giữa các agents (API calls, data types, error handling)
- Tạo file docs/review_report.md theo đúng format trong skill
- Không sửa code, chỉ báo cáo
- Không hỏi lại"""

    skills = load_skills(role)
    prompt = (skills + "\n" + task_prompt) if skills else task_prompt

    try:
        await run(role, prompt, docs_dir)
        duration  = int(time.time() - start)
        new_files = _new_files(docs_dir, before)
        tm.set_done(role)
        slack.post_done(thread_ts, role, new_files, duration)
        print(f"  [{role}] ✅ Xong! ({duration}s)")
    except Exception as e:
        err = str(e) or type(e).__name__
        tm.set_failed(role, err)
        slack.post_failed(thread_ts, role, err)
        print(f"  [{role}] ❌ {err}")

    tm.print_status()


# ── Main orchestrate ──────────────────────────────────────────────────────────

async def orchestrate(prd: str, output_dir: str = "./output"):
    cfg      = get_config()
    out      = Path(output_dir)
    docs_dir = out / "docs"
    repo_url = _extract_repo_url(prd)

    out.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AI TEAM ORCHESTRATOR")
    print(f"Profile: {cfg.profile}")
    if repo_url:
        print(f"Repo:    {repo_url}")
    print("-" * 60)
    for role, a in cfg.agents.items():
        status = "✅" if role in cfg.enabled_agents else "⏭️  (skip)"
        print(f"  {role:14} → {a.label:30} {status}")
    slack_st = "✅ Connected" if cfg.slack_enabled else "⚠️  Offline (điền token để bật)"
    print(f"\nSlack:  {slack_st}")
    print(f"Output: {out.resolve()}")
    print("=" * 60)

    # Khởi tạo task manager chỉ với enabled agents
    tasks = {}
    if _enabled("PM Agent"):             tasks["PM Agent"]             = "Viết user stories và acceptance criteria"
    if _enabled("Scrum Master"):         tasks["Scrum Master"]         = "Tạo backlog và sprint plan"
    if _enabled("Analyst"):              tasks["Analyst"]              = "Thiết kế API, data model, chia task"
    if _enabled("BE Agent 1"):           tasks["BE Agent 1"]           = "Implement backend theo be1_task.md"
    if _enabled("BE Agent 2"):           tasks["BE Agent 2"]           = "Implement backend theo be2_task.md"
    if _enabled("FE Agent 1"):           tasks["FE Agent 1"]           = "Implement frontend theo fe1_task.md"
    if _enabled("FE Agent 2"):           tasks["FE Agent 2"]           = "Implement frontend theo fe2_task.md"
    if _enabled("Fullstack Agent 1"):    tasks["Fullstack Agent 1"]    = "Implement theo fs1_task.md (clone repo + làm tiếp)"
    if _enabled("Fullstack Agent 2"):    tasks["Fullstack Agent 2"]    = "Implement theo fs2_task.md (clone repo + làm tiếp)"
    if _enabled("Leader Agent"):         tasks["Leader Agent"]         = "Review toàn bộ code"

    tm.init(tasks)
    tm.print_status()

    # Stage 1: PM
    if _enabled("PM Agent"):
        await _run_stage("PM Agent", f"""Bạn là Product Manager AI.

PRD:
{prd}

Tạo 2 file trong docs/:
1. docs/user_stories.md — User stories: As a/I want/So that + story points
2. docs/acceptance.md   — Acceptance criteria: Given/When/Then""",
            out, "Viết user stories từ PRD")
        tm.print_status()

    # Stage 2: Scrum (optional)
    if _enabled("Scrum Master"):
        has_fs   = _enabled("Fullstack Agent 1") or _enabled("Fullstack Agent 2")
        has_be   = _enabled("BE Agent 1") or _enabled("BE Agent 2")
        has_fe   = _enabled("FE Agent 1") or _enabled("FE Agent 2")
        assignee_hint = (
            "FS1/FS2" if has_fs and not has_be and not has_fe
            else "BE1/BE2/FE1/FE2" if has_be or has_fe
            else "FS1/FS2"
        )
        await _run_stage("Scrum Master", f"""Bạn là Scrum Master AI.

USER STORIES:
{_read_doc(output_dir, 'user_stories.md')}

ACCEPTANCE:
{_read_doc(output_dir, 'acceptance.md')}

Tạo 2 file trong docs/:
1. docs/backlog.md      — Backlog có priority, points, assignee ({assignee_hint})
2. docs/sprint_plan.md  — Sprint plan chia task chi tiết cho từng agent""",
            out, "Tạo backlog và sprint plan")
        tm.print_status()

    # Stage 3: Analyst
    if _enabled("Analyst"):
        has_scrum  = _enabled("Scrum Master")
        be_agents  = [r for r in ["BE Agent 1", "BE Agent 2"] if _enabled(r)]
        fe_agents  = [r for r in ["FE Agent 1", "FE Agent 2"] if _enabled(r)]
        fs_agents  = [r for r in ["Fullstack Agent 1", "Fullstack Agent 2"] if _enabled(r)]

        task_files = []
        for r in be_agents:
            num = r.split()[-1]
            task_files.append(f"- docs/be{num}_task.md — Task cho {r}")
        for r in fe_agents:
            num = r.split()[-1]
            task_files.append(f"- docs/fe{num}_task.md — Task cho {r}")
        for r in fs_agents:
            num = r.split()[-1]
            task_files.append(f"- docs/fs{num}_task.md — Task cho {r} (fullstack, không chia BE/FE)")

        plan_section = f"""SPRINT PLAN:
{_read_doc(output_dir, 'sprint_plan.md')}""" if has_scrum else ""

        repo_note = f"\nRepo hiện có (agents sẽ clone và làm tiếp): {repo_url}" if repo_url and fs_agents else ""

        analyst_prompt = f"""Bạn là Tech Lead AI.

USER STORIES:
{_read_doc(output_dir, 'user_stories.md')}

{plan_section}

Tech stack: {cfg.tech_backend} / {cfg.tech_frontend}{repo_note}

Tạo trong docs/:
- docs/api_contract.md  — Tất cả endpoints, request/response schema
- docs/data_models.md   — Database schema đầy đủ
{chr(10).join(task_files)}"""

        await _run_stage("Analyst", analyst_prompt, out, "Thiết kế kỹ thuật và chia task")
        tm.print_status()

    # Stage 4a: BE agents
    be_tasks = []
    if _enabled("BE Agent 1"):
        be_tasks.append(_coding_agent("BE Agent 1", "be1_task.md", out / "backend" / "be1", output_dir))
    if _enabled("BE Agent 2"):
        be_tasks.append(_coding_agent("BE Agent 2", "be2_task.md", out / "backend" / "be2", output_dir))

    if be_tasks:
        print("\n[Orchestrator] Stage 4a — BE agents...")
        await asyncio.gather(*be_tasks)

    # Stage 4b: FE agents
    fe_tasks = []
    if _enabled("FE Agent 1"):
        fe_tasks.append(_coding_agent("FE Agent 1", "fe1_task.md", out / "frontend" / "fe1", output_dir))
    if _enabled("FE Agent 2"):
        fe_tasks.append(_coding_agent("FE Agent 2", "fe2_task.md", out / "frontend" / "fe2", output_dir))

    if fe_tasks:
        print("\n[Orchestrator] Stage 4b — FE agents...")
        await asyncio.gather(*fe_tasks)

    # Stage 4c: Fullstack agents (song song, mỗi agent clone repo riêng)
    fs_tasks = []
    if _enabled("Fullstack Agent 1"):
        fs_tasks.append(_coding_agent("Fullstack Agent 1", "fs1_task.md", out / "fullstack" / "fs1", output_dir, repo_url))
    if _enabled("Fullstack Agent 2"):
        fs_tasks.append(_coding_agent("Fullstack Agent 2", "fs2_task.md", out / "fullstack" / "fs2", output_dir, repo_url))

    if fs_tasks:
        print("\n[Orchestrator] Stage 4c — Fullstack agents (clone repo + implement)...")
        await asyncio.gather(*fs_tasks)

    # Stage 5: Leader review
    if _enabled("Leader Agent"):
        print("\n[Orchestrator] Stage 5 — Leader Agent review code...")
        await _review_agent(output_dir)

    # Sprint summary
    all_files  = [f for f in out.rglob("*") if f.is_file()]
    code_files = [f for f in all_files if f.suffix in [".py", ".ts", ".tsx", ".json", ".toml"]]
    doc_files  = [f for f in all_files if f.suffix == ".md"]

    slack.post_sprint_summary({r: t["status"] for r, t in tm.get_all().items()})

    print("\n" + "=" * 60)
    print(f"XONG! {out.resolve()}")
    print(f"  Docs: {len(doc_files)} files  |  Code: {len(code_files)} files")
    tm.print_status()
