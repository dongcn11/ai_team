"""
Skill Loader
============
Đọc skill files (.md) và inject vào prompt của từng agent.

Cấu trúc skills/:
  shared/     ← tất cả agents đọc
  be/         ← BE Agent 1, BE Agent 2
  fe/         ← FE Agent 1, FE Agent 2
  pm/         ← PM Agent
  scrum/      ← Scrum Master
  analyst/    ← Analyst

Thêm skill mới: chỉ cần tạo file .md trong đúng thư mục.
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Map role → các thư mục skill cần đọc
ROLE_SKILL_DIRS: dict[str, list[str]] = {
    "PM Agent":     ["shared", "pm"],
    "Scrum Master": ["shared", "scrum"],
    "Analyst":      ["shared", "analyst"],
    "BE Agent 1":   ["shared", "be"],
    "BE Agent 2":   ["shared", "be"],
    "FE Agent 1":   ["shared", "fe"],
    "FE Agent 2":   ["shared", "fe"],
    "Leader Agent": ["shared", "leader"],
}


def _read_skill_dir(dir_name: str) -> list[tuple[str, str]]:
    """Đọc tất cả .md files trong 1 thư mục skill. Return [(filename, content)]"""
    skill_dir = SKILLS_DIR / dir_name
    if not skill_dir.exists():
        return []

    skills = []
    for path in sorted(skill_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if content:
            skills.append((path.stem, content))
    return skills


def load_skills(role: str) -> str:
    """
    Load tất cả skills cho 1 role, trả về string để inject vào prompt.
    Nếu không có skill nào → trả về string rỗng.
    """
    dirs = ROLE_SKILL_DIRS.get(role, ["shared"])
    all_skills: list[tuple[str, str]] = []

    for dir_name in dirs:
        all_skills.extend(_read_skill_dir(dir_name))

    if not all_skills:
        return ""

    lines = ["=" * 50]
    lines.append("## SKILLS — Đọc kỹ và áp dụng khi làm việc")
    lines.append("=" * 50)

    for skill_name, content in all_skills:
        lines.append(f"\n### {skill_name.replace('_', ' ').title()}")
        lines.append(content)

    lines.append("\n" + "=" * 50)
    lines.append("## Bắt đầu task của bạn:")
    lines.append("=" * 50 + "\n")

    return "\n".join(lines)


def list_skills(role: str) -> list[str]:
    """Liệt kê tên các skills đang được load cho 1 role."""
    dirs    = ROLE_SKILL_DIRS.get(role, ["shared"])
    result  = []
    for dir_name in dirs:
        skill_dir = SKILLS_DIR / dir_name
        if skill_dir.exists():
            result.extend(f"{dir_name}/{p.name}" for p in sorted(skill_dir.glob("*.md")))
    return result


def get_skills_summary() -> dict[str, list[str]]:
    """Tóm tắt tất cả skills đang có cho mọi role."""
    return {role: list_skills(role) for role in ROLE_SKILL_DIRS}
