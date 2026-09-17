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

Trong mỗi thư mục, 1 skill là:
  <ten>.md            ← 1 file (dạng cũ)
  <ten>/SKILL.md      ← 1 thư mục, kèm được file phụ — đúng quy ước skill của
                        Claude Code và BMAD, và là dạng mà trang Skills trên
                        dashboard tạo ra (xem dashboard/api/skills_store.py)

Thêm skill mới: tạo file .md, hoặc bấm "Skill mới" trên dashboard. Cả hai lane
(pipeline này và workflow của dashboard) đọc cùng một thư mục, nên skill thêm ở
đâu cũng thấy ở cả hai.
"""

import re
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


SKILL_FILE = "SKILL.md"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_NAME_RE = re.compile(r"^\s*name:\s*(.+?)\s*$", re.MULTILINE)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(tên khai trong frontmatter, phần thân). Không có frontmatter → ("", cả bài).

    Frontmatter là metadata cho người/UI chọn skill, không phải chỉ dẫn cho agent
    — nhét nguyên khối `---` vào prompt chỉ tốn token và làm agent tưởng đó là
    một phần yêu cầu."""
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return "", (text or "").strip()
    name = _NAME_RE.search(m.group(1))
    return (name.group(1).strip().strip("\"'") if name else ""), text[m.end():].strip()


def _iter_skill_files(skill_dir: Path):
    """(tên hiển thị mặc định, path) của mọi skill trong 1 thư mục — cả 2 dạng."""
    for path in sorted(skill_dir.iterdir()):
        if path.is_dir() and (path / SKILL_FILE).is_file():
            yield path.name, path / SKILL_FILE
        elif path.suffix.lower() == ".md":
            yield path.stem, path


# Rác sinh lúc chạy — không phải nội dung skill, đừng kể cho agent.
_IGNORED_DIRS = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}
_IGNORED_SUFFIXES = {".pyc", ".pyo", ".log"}

# Bao nhiêu ký tự của 1 skill thì còn nhét thẳng vào prompt. Skill thật có thể
# dài vài chục KB (SKILL.md của udom-screen-spec ~24KB); nhồi hết vào prompt mỗi
# agent là đốt token cho thứ agent chưa chắc dùng. Quá ngưỡng thì chỉ đưa tên,
# mô tả và ĐƯỜNG DẪN — agent tự mở đọc, đúng cách skill của Claude hoạt động.
# Cùng ngưỡng với làn workflow (_SKILL_INLINE_BUDGET, dashboard/api/routers/workflows.py).
_INLINE_BUDGET = 12000


def _companion_files(path: Path) -> list[str]:
    """File đi kèm skill thư mục (script, mẫu), đường dẫn tính từ gốc repo.

    Skill kiểu udom-screen-spec bảo agent 'chạy check_closure.py'. Không nói file
    đó nằm đâu thì agent đọc xong hướng dẫn vẫn không chạy được gì."""
    folder = path.parent
    if path.name != SKILL_FILE:
        return []
    out = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name == SKILL_FILE:
            continue
        rel = p.relative_to(folder)
        if any(part in _IGNORED_DIRS for part in rel.parts[:-1]) or rel.suffix.lower() in _IGNORED_SUFFIXES:
            continue
        out.append(p.relative_to(SKILLS_DIR.parent).as_posix())
        if len(out) >= 20:
            break
    return out


def _read_skill_dir(dir_name: str) -> list[tuple[str, str]]:
    """Đọc mọi skill trong 1 thư mục (file .md và thư mục có SKILL.md).
    Return [(tên skill, nội dung để đưa vào prompt)]"""
    skill_dir = SKILLS_DIR / dir_name
    if not skill_dir.exists():
        return []

    skills = []
    for fallback_name, path in _iter_skill_files(skill_dir):
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        name, content = _split_frontmatter(raw)
        if not content:
            continue
        rel = path.relative_to(SKILLS_DIR.parent).as_posix()
        files = _companion_files(path)
        if len(content) > _INLINE_BUDGET:
            content = (f"(Skill dài — MỞ VÀ ĐỌC `{rel}` trước khi làm phần liên quan.)")
        if files:
            content += "\n\nFile đi kèm skill này (đường dẫn tính từ gốc repo): " + \
                       ", ".join(f"`{f}`" for f in files)
        # Tên khai trong frontmatter giữ nguyên; tên suy từ file mới làm đẹp
        # ("auth_jwt" → "Auth Jwt"). Làm đẹp cả hai thì "JWT Authentication"
        # thành "Jwt Authentication".
        skills.append((name or fallback_name.replace("_", " ").title(), content))
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
        lines.append(f"\n### {skill_name}")
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
            result.extend(f"{dir_name}/{name}" for name, _ in _iter_skill_files(skill_dir))
    return result


def get_skills_summary() -> dict[str, list[str]]:
    """Tóm tắt tất cả skills đang có cho mọi role."""
    return {role: list_skills(role) for role in ROLE_SKILL_DIRS}
