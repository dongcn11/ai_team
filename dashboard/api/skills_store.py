"""
Skill Store
===========
Kho skill dạng FILE, đọc/ghi thẳng trong `skills/` theo đúng quy ước skill của
Claude Code và BMAD: mỗi skill mở đầu bằng khối frontmatter YAML khai `name` +
`description`, phần thân là hướng dẫn cho agent đọc.

    skills/<category>/<slug>/SKILL.md   ← skill "thư mục": kèm được file phụ
                                          (workflow.md, templates/…) như BMAD
    skills/<category>/<slug>.md         ← skill "1 file": định dạng cũ của repo,
                                          vẫn đọc/sửa/xoá được như skill thường

VÌ SAO VẪN CÒN LỚP <category>: pipeline `ai_team/` và node workflow đang chọn
skill theo THƯ MỤC VAI TRÒ (be/fe/pm/leader…, xem AGENT_SKILL_DIRS). Bỏ lớp đó
thì mọi workflow đã vẽ mất sạch skill. Nên category giữ nguyên nghĩa "cụm skill
của một vai trò", còn skill là đơn vị nhỏ hơn nằm trong cụm — node chọn được cả
cụm lẫn từng skill lẻ.

VÌ SAO KHÔNG LƯU DB: skill phải đọc được bởi CLI chạy trên máy thật (`claude`,
`opencode`) và bởi pipeline, không riêng API. Nguồn sự thật là file trên đĩa;
API chỉ là một cách sửa file đó cho tiện.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import yaml

from system_config import SKILLS_DIR

# Tên thư mục/file hợp lệ. Cố tình hẹp: id skill đi vào URL, vào tên file và vào
# prompt — ký tự lạ ở một trong ba chỗ đó là một lỗi khó đoán.
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)

SKILL_FILE = "SKILL.md"

# Một skill KHÔNG chỉ là văn bản. Skill thật (vd udom-screen-spec) là SKILL.md
# vài chục KB + mấy script Python mà chính skill bảo agent chạy, có cả test và
# thư mục con. Nên chỗ này không lọc theo đuôi file nữa: nhận mọi thứ, chỉ chặn
# rác và file quá to. Đọc/sửa trên web thì chỉ file văn bản; file nhị phân vẫn
# được liệt kê, tải về và xoá.
_SCRIPT_SUFFIXES = {".py", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".js", ".mjs",
                    ".ts", ".rb", ".pl", ".php", ".sql"}
_DOC_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
# Rác sinh ra lúc chạy — copy vào kho skill chỉ tổ bẩn repo và làm `git diff` ồn.
_IGNORED_DIRS = {"__pycache__", ".git", ".svn", ".hg", "node_modules", ".venv",
                 "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea", ".vscode"}
_IGNORED_SUFFIXES = {".pyc", ".pyo", ".class", ".o", ".obj", ".log"}
_IGNORED_NAMES = {".DS_Store", "Thumbs.db"}

_MAX_RESOURCES = 300              # đủ cho skill có thư mục con, vẫn chặn được nhầm
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 1 file
_MAX_IMPORT_FILES = 300
_MAX_IMPORT_BYTES = 30 * 1024 * 1024
_SNIFF = 8192                      # số byte đọc thử để đoán file văn bản


class SkillError(Exception):
    """Lỗi người dùng sửa được (tên sai, trùng, không tồn tại, thư mục chỉ đọc)."""


# ── frontmatter ───────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Tách (meta, body). File không có frontmatter → ({}, nguyên văn)."""
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}, (text or "").strip()
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, (text or "")[m.end():].strip()


def dump_frontmatter(meta: dict, body: str) -> str:
    """Ghép lại thành file SKILL.md. Giữ name/description lên đầu cho giống skill
    của Claude — người mở file bằng editor đọc được ngay."""
    ordered: dict = {}
    for key in ("name", "description"):
        if meta.get(key) is not None:
            ordered[key] = meta[key]
    for key, val in meta.items():
        if key not in ordered and val not in (None, "", [], {}):
            ordered[key] = val
    front = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{front}\n---\n\n{(body or '').strip()}\n"


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (text or "").strip().lower()).strip("-._")
    return s or "skill"


def _valid_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise SkillError(
            f"'{name}' không hợp lệ — chỉ dùng chữ/số/dấu chấm/gạch, bắt đầu bằng chữ hoặc số"
        )
    return name


# ── đọc ───────────────────────────────────────────────────────────────────

def _first_paragraph(body: str) -> str:
    """Mô tả dự phòng cho file cũ chưa có frontmatter: đoạn văn đầu tiên.

    Bỏ khối ``` trước khi cắt — skill của repo này phần lớn là code mẫu, lấy đại
    đoạn đầu sẽ ra một dòng `SECRET_KEY = ...` làm mô tả, vô nghĩa trên UI."""
    body = re.sub(r"```.*?```", "", body or "", flags=re.DOTALL)
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block or block.startswith("#") or block.startswith("```"):
            continue
        one_line = " ".join(block.split())
        return one_line[:200] + ("…" if len(one_line) > 200 else "")
    return ""


def _title_from_body(body: str, fallback: str) -> str:
    m = _HEADING_RE.search(body or "")
    if m:
        # "# Skill: JWT Authentication" → "JWT Authentication"
        return re.sub(r"^skill:\s*", "", m.group(1).strip(), flags=re.IGNORECASE)
    return fallback.replace("_", " ").replace("-", " ").strip().title()


def _is_text(path: Path) -> bool:
    """Đoán file văn bản bằng cách ngửi vài KB đầu — đủ để biết có mở được trong
    ô soạn thảo không, mà không phải đọc cả file."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_SNIFF)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError as e:
        # Lỗi ngay cuối mẫu thường chỉ là cắt giữa một ký tự nhiều byte
        return e.start >= len(chunk) - 4
    return True


def _ignored(rel: Path) -> bool:
    if any(part in _IGNORED_DIRS for part in rel.parts[:-1]):
        return True
    return rel.name in _IGNORED_NAMES or rel.suffix.lower() in _IGNORED_SUFFIXES


def _resource(folder: Path, path: Path) -> dict:
    rel = path.relative_to(folder)
    suffix = path.suffix.lower()
    text = _is_text(path)
    if suffix in _SCRIPT_SUFFIXES:
        kind = "script"
    elif not text:
        kind = "binary"
    elif suffix in _DOC_SUFFIXES:
        kind = "doc"
    else:
        kind = "data"
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"path": rel.as_posix(), "size": size, "is_text": text, "kind": kind}


def _resources(folder: Path) -> list[dict]:
    """Mọi file trong skill thư mục trừ SKILL.md — script, test, thư mục con đều
    tính. Bỏ rác (__pycache__, .pyc…) vì nó không phải nội dung skill."""
    out: list[dict] = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name == SKILL_FILE:
            continue
        rel = p.relative_to(folder)
        if _ignored(rel):
            continue
        out.append(_resource(folder, p))
        if len(out) >= _MAX_RESOURCES:
            break
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _build(category: str, slug: str, path: Path, fmt: str, with_content: bool) -> dict:
    try:
        raw = _read(path)
    except OSError as e:
        raw = ""
        meta, body = {}, f"(không đọc được file: {e})"
    else:
        meta, body = parse_frontmatter(raw)

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        mtime = None

    skill = {
        "id":          f"{category}/{slug}",
        "category":    category,
        "slug":        slug,
        "name":        str(meta.get("name") or _title_from_body(body, slug)),
        "description": str(meta.get("description") or _first_paragraph(body)),
        "tags":        [str(t) for t in tags],
        "format":      fmt,
        "path":        f"skills/{path.relative_to(SKILLS_DIR).as_posix()}",
        "chars":       len(body),
        "updated_at":  mtime,
        "has_frontmatter": bool(meta),
        "resources":   _resources(path.parent) if fmt == "folder" else [],
    }
    if with_content:
        skill["body"] = body
        skill["content"] = raw
    return skill


def _iter_skill_paths(category_dir: Path) -> Iterable[tuple[str, Path, str]]:
    """(slug, path SKILL.md/<file>.md, format) của mọi skill trong 1 category."""
    for child in sorted(category_dir.iterdir()):
        if child.is_dir():
            f = child / SKILL_FILE
            if f.is_file():
                yield child.name, f, "folder"
        elif child.suffix.lower() == ".md":
            yield child.stem, child, "file"


def list_categories() -> list[dict]:
    if not SKILLS_DIR.is_dir():
        return []
    out = []
    for d in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        out.append({"name": d.name, "count": sum(1 for _ in _iter_skill_paths(d))})
    return out


def list_skills(category: Optional[str] = None, q: Optional[str] = None) -> list[dict]:
    if not SKILLS_DIR.is_dir():
        return []
    needle = (q or "").strip().lower()
    out: list[dict] = []
    for d in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        if category and d.name != category:
            continue
        for slug, path, fmt in _iter_skill_paths(d):
            skill = _build(d.name, slug, path, fmt, with_content=False)
            if needle and needle not in " ".join([
                skill["id"], skill["name"], skill["description"], " ".join(skill["tags"]),
            ]).lower():
                continue
            out.append(skill)
    return out


def _locate(skill_id: str) -> tuple[str, str, Path, str]:
    """(category, slug, path, format) — ném SkillError nếu id sai hoặc không có."""
    parts = [p for p in (skill_id or "").split("/") if p]
    if len(parts) != 2:
        raise SkillError(f"Skill id phải dạng '<category>/<slug>', nhận '{skill_id}'")
    category, slug = _valid_name(parts[0]), _valid_name(parts[1])
    folder = SKILLS_DIR / category / slug
    if (folder / SKILL_FILE).is_file():
        return category, slug, folder / SKILL_FILE, "folder"
    flat = SKILLS_DIR / category / f"{slug}.md"
    if flat.is_file():
        return category, slug, flat, "file"
    raise SkillError(f"Không tìm thấy skill '{skill_id}'")


def get_skill(skill_id: str) -> dict:
    category, slug, path, fmt = _locate(skill_id)
    return _build(category, slug, path, fmt, with_content=True)


def exists(skill_id: str) -> bool:
    try:
        _locate(skill_id)
        return True
    except SkillError:
        return False


# ── ghi ───────────────────────────────────────────────────────────────────

def writable() -> bool:
    """`skills/` có ghi được không. Container mount :ro thì mọi nút Lưu đều
    hỏng — UI cần biết trước để nói thẳng thay vì để người dùng bấm rồi lỗi."""
    if not SKILLS_DIR.is_dir():
        return False
    return os.access(SKILLS_DIR, os.W_OK)


def _require_writable() -> None:
    if not writable():
        raise SkillError(
            "Thư mục skills/ đang chỉ-đọc với API. Sửa mount trong "
            "dashboard/docker-compose.yml thành '../skills:/skills' (bỏ ':ro') rồi "
            "chạy lại `docker compose up -d api`."
        )


def _write(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        raise SkillError(f"Không ghi được {path}: {e}")


def create_skill(category: str, name: str, description: str = "", body: str = "",
                 slug: Optional[str] = None, tags: Optional[list[str]] = None,
                 fmt: str = "folder") -> dict:
    _require_writable()
    category = _valid_name(category)
    slug = _valid_name(slug or slugify(name))
    skill_id = f"{category}/{slug}"
    if exists(skill_id):
        raise SkillError(f"Skill '{skill_id}' đã tồn tại")

    meta = {"name": (name or slug).strip(), "description": (description or "").strip()}
    if tags:
        meta["tags"] = list(tags)
    path = (SKILLS_DIR / category / slug / SKILL_FILE) if fmt == "folder" \
        else (SKILLS_DIR / category / f"{slug}.md")
    _write(path, dump_frontmatter(meta, body))
    return get_skill(skill_id)


def update_skill(skill_id: str, *, name: Optional[str] = None,
                 description: Optional[str] = None, body: Optional[str] = None,
                 tags: Optional[list[str]] = None, category: Optional[str] = None,
                 slug: Optional[str] = None) -> dict:
    """Sửa skill. Đổi category/slug = DI CHUYỂN file — id đổi theo, workflow đang
    trỏ tới id cũ sẽ mất skill đó, nên UI phải cảnh báo trước khi gọi."""
    _require_writable()
    cur_cat, cur_slug, path, fmt = _locate(skill_id)
    meta, cur_body = parse_frontmatter(_read(path))

    if name is not None:
        meta["name"] = name.strip()
    if description is not None:
        meta["description"] = description.strip()
    if tags is not None:
        if tags:
            meta["tags"] = list(tags)
        else:
            meta.pop("tags", None)
    meta.setdefault("name", cur_slug)
    new_body = cur_body if body is None else body

    new_cat  = _valid_name(category) if category else cur_cat
    new_slug = _valid_name(slug) if slug else cur_slug
    moved = (new_cat, new_slug) != (cur_cat, cur_slug)
    if moved and exists(f"{new_cat}/{new_slug}"):
        raise SkillError(f"Skill '{new_cat}/{new_slug}' đã tồn tại")

    _write(path, dump_frontmatter(meta, new_body))

    if moved:
        src = path.parent if fmt == "folder" else path
        dst = (SKILLS_DIR / new_cat / new_slug) if fmt == "folder" \
            else (SKILLS_DIR / new_cat / f"{new_slug}.md")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as e:
            raise SkillError(f"Không di chuyển được skill: {e}")
    return get_skill(f"{new_cat}/{new_slug}")


def delete_skill(skill_id: str) -> None:
    _require_writable()
    _, _, path, fmt = _locate(skill_id)
    try:
        if fmt == "folder":
            shutil.rmtree(path.parent)
        else:
            path.unlink()
    except OSError as e:
        raise SkillError(f"Không xoá được skill: {e}")


def duplicate_skill(skill_id: str, new_slug: Optional[str] = None,
                    category: Optional[str] = None) -> dict:
    """Nhân bản NGUYÊN thư mục skill — script, test, thư mục con đi theo hết.

    Copy thiếu file phụ thì bản sao của một skill kiểu udom-screen-spec
    ("chạy check_closure.py") trỏ vào hư không."""
    _require_writable()
    cur_cat, cur_slug, path, fmt = _locate(skill_id)
    cat  = _valid_name(category or cur_cat)
    slug = _valid_name(new_slug or f"{cur_slug}-copy")
    if exists(f"{cat}/{slug}"):
        raise SkillError(f"Skill '{cat}/{slug}' đã tồn tại")

    meta, body = parse_frontmatter(_read(path))
    meta["name"] = f"{meta.get('name') or cur_slug} (copy)"
    try:
        if fmt == "folder":
            shutil.copytree(
                path.parent, SKILLS_DIR / cat / slug,
                ignore=shutil.ignore_patterns(*_IGNORED_DIRS, "*.pyc", "*.pyo"),
            )
            _write(SKILLS_DIR / cat / slug / SKILL_FILE, dump_frontmatter(meta, body))
        else:
            _write(SKILLS_DIR / cat / f"{slug}.md", dump_frontmatter(meta, body))
    except OSError as e:
        raise SkillError(f"Không nhân bản được skill: {e}")
    return get_skill(f"{cat}/{slug}")


def to_folder(skill_id: str) -> dict:
    """Đổi skill 1 file thành skill thư mục (`<slug>/SKILL.md`).

    Cần bước này vì skill chỉ chứa được script/mẫu khi nó là một thư mục — mà
    hầu hết skill trong repo còn ở dạng cũ 1 file .md."""
    _require_writable()
    cat, slug, path, fmt = _locate(skill_id)
    if fmt == "folder":
        return get_skill(skill_id)
    content = _read(path)
    _write(SKILLS_DIR / cat / slug / SKILL_FILE, content)
    try:
        path.unlink()
    except OSError as e:
        raise SkillError(f"Đã tạo thư mục nhưng không xoá được file cũ: {e}")
    return get_skill(skill_id)


def _unzip(data: bytes) -> list[tuple[str, bytes]]:
    """Bung 1 file .zip thành [(đường dẫn, nội dung)].

    Chặn zip-slip (entry tên `../../x`) ngay ở đây chứ không tin vào lớp sau: một
    entry độc là ghi đè được file ngoài kho skill."""
    out: list[tuple[str, bytes]] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    continue
                total += info.file_size
                if len(out) >= _MAX_IMPORT_FILES or total > _MAX_IMPORT_BYTES:
                    raise SkillError(
                        f"File zip quá lớn (tối đa {_MAX_IMPORT_FILES} file / "
                        f"{_MAX_IMPORT_BYTES // (1024*1024)} MB sau khi bung)"
                    )
                out.append((name, zf.read(info)))
    except zipfile.BadZipFile:
        raise SkillError("File .zip hỏng hoặc không phải zip")
    if not out:
        raise SkillError("File zip rỗng")
    return out


def import_files(category: str, files: list[tuple[str, bytes]],
                 slug: Optional[str] = None, name: Optional[str] = None) -> dict:
    """Nhận NGUYÊN một thư mục skill (SKILL.md + script + thư mục con) và đặt nó
    vào `skills/<category>/<slug>/`.

    Đây là đường mang skill có sẵn từ nơi khác vào — `.claude/skills/<tên>` của
    Claude Code, skill BMAD, skill đồng nghiệp gửi. Không có nó thì skill nào có
    script đều phải copy tay ngoài repo, và trang Skills chỉ dùng được cho skill
    một file.

    `files` là [(đường dẫn tương đối, nội dung)]. Một file .zip duy nhất được bung
    ra trước — skill gửi qua chat/mail gần như luôn ở dạng zip. Lớp thư mục gốc
    chung (khi kéo cả thư mục vào) bị lược đi, và chính nó là slug mặc định."""
    _require_writable()
    category = _valid_name(category)

    if len(files) == 1 and files[0][0].lower().endswith(".zip"):
        files = _unzip(files[0][1])

    clean: list[tuple[Path, bytes]] = []
    total = 0
    for raw_name, data in files:
        try:
            rel = _safe_rel(raw_name)
        except SkillError:
            continue
        if _ignored(rel):
            continue
        total += len(data)
        if len(clean) >= _MAX_IMPORT_FILES or total > _MAX_IMPORT_BYTES:
            raise SkillError(
                f"Gói skill quá lớn (tối đa {_MAX_IMPORT_FILES} file / "
                f"{_MAX_IMPORT_BYTES // (1024*1024)} MB)"
            )
        clean.append((rel, data))
    if not clean:
        raise SkillError("Không có file nào dùng được trong thư mục đã chọn")

    # Bỏ lớp thư mục gốc chung: trình duyệt gửi "udom-screen-spec/SKILL.md"
    roots = {rel.parts[0] for rel, _ in clean if len(rel.parts) > 1}
    single_root = roots.pop() if len(roots) == 1 and not any(len(r.parts) == 1 for r, _ in clean) else None
    if single_root:
        clean = [(Path(*rel.parts[1:]), data) for rel, data in clean]

    skill_md = next((data for rel, data in clean if rel.as_posix() == SKILL_FILE), None)
    if skill_md is None:
        raise SkillError(
            "Thư mục không có SKILL.md ở gốc — đây không phải một skill. "
            "Chọn đúng thư mục chứa SKILL.md."
        )
    meta, _body = parse_frontmatter(skill_md.decode("utf-8", errors="replace"))

    slug = _valid_name(slug or single_root or slugify(str(meta.get("name") or "skill")))
    if exists(f"{category}/{slug}"):
        raise SkillError(f"Skill '{category}/{slug}' đã tồn tại — đổi slug hoặc xoá bản cũ trước")

    dest = SKILLS_DIR / category / slug
    for rel, data in clean:
        target = dest / rel
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as e:
            raise SkillError(f"Không ghi được {rel.as_posix()}: {e}")

    # Skill ngoài có thể thiếu name/description — bổ sung để nó hiện tử tế trên UI
    if name or not meta.get("name") or not meta.get("description"):
        meta.setdefault("description", "")
        if name:
            meta["name"] = name
        meta.setdefault("name", slug)
        _, body = parse_frontmatter(_read(dest / SKILL_FILE))
        _write(dest / SKILL_FILE, dump_frontmatter(meta, body))
    return get_skill(f"{category}/{slug}")


# ── file phụ trong skill thư mục ──────────────────────────────────────────

def _safe_rel(filename: str) -> Path:
    """Đường dẫn tương đối đã làm sạch: không tuyệt đối, không '..', không rác."""
    raw = (filename or "").replace("\\", "/").strip().strip("/")
    if not raw:
        raise SkillError("Thiếu tên file")
    rel = Path(raw)
    if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
        raise SkillError(f"Đường dẫn file không hợp lệ: '{filename}'")
    for part in rel.parts:
        if part.startswith("/") or ":" in part:
            raise SkillError(f"Đường dẫn file không hợp lệ: '{filename}'")
    return rel


def _resource_path(skill_id: str, filename: str) -> Path:
    _, _, path, fmt = _locate(skill_id)
    if fmt != "folder":
        raise SkillError(
            "Skill này đang là 1 file .md nên không chứa được file phụ. "
            "Đổi sang dạng thư mục trước (nút 'Chuyển sang thư mục')."
        )
    folder = path.parent
    target = (folder / _safe_rel(filename)).resolve()
    try:
        target.relative_to(folder.resolve())
    except ValueError:
        raise SkillError("Đường dẫn file không hợp lệ")
    if target.name == SKILL_FILE and target.parent == folder:
        raise SkillError("SKILL.md sửa ở phần nội dung chính, không qua file phụ")
    return target


def read_resource(skill_id: str, filename: str) -> str:
    target = _resource_path(skill_id, filename)
    if not target.is_file():
        raise SkillError(f"Không có file '{filename}'")
    if not _is_text(target):
        raise SkillError(f"'{filename}' là file nhị phân — tải về để xem, không sửa trên web được")
    return _read(target)


def resource_file(skill_id: str, filename: str) -> Path:
    """Đường dẫn thật của 1 file phụ — để tải về (kể cả file nhị phân)."""
    target = _resource_path(skill_id, filename)
    if not target.is_file():
        raise SkillError(f"Không có file '{filename}'")
    return target


def write_resource(skill_id: str, filename: str, content: str) -> None:
    _require_writable()
    _write(_resource_path(skill_id, filename), content)


def save_upload(skill_id: str, filename: str, data: bytes) -> dict:
    """Ghi 1 file bất kỳ (script, ảnh, mẫu…) vào skill thư mục."""
    _require_writable()
    if len(data) > _MAX_FILE_BYTES:
        raise SkillError(f"'{filename}' quá lớn (giới hạn {_MAX_FILE_BYTES // (1024*1024)} MB)")
    target = _resource_path(skill_id, filename)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as e:
        raise SkillError(f"Không ghi được {filename}: {e}")
    _, _, path, _ = _locate(skill_id)
    return _resource(path.parent, target)


def delete_resource(skill_id: str, filename: str) -> None:
    _require_writable()
    target = _resource_path(skill_id, filename)
    if not target.is_file():
        raise SkillError(f"Không có file '{filename}'")
    try:
        target.unlink()
    except OSError as e:
        raise SkillError(f"Không xoá được file: {e}")


# ── phân giải cho prompt ──────────────────────────────────────────────────

def resolve(categories: Optional[list[str]] = None,
            skill_ids: Optional[list[str]] = None) -> list[dict]:
    """Bung lựa chọn của 1 node thành danh sách skill THẬT, giữ thứ tự, bỏ trùng.

    Chọn cả cụm (category) = lấy mọi skill trong cụm đó; skill lẻ nào đã nằm
    trong cụm đã chọn thì không lặp lại. Mục thiếu trả về {"missing": lý do} để
    file task nói rõ "skill này không tồn tại" thay vì im lặng bỏ qua.

    SKILL LẺ ĐỨNG TRƯỚC CẢ CỤM. Người chọn lẻ là chọn có chủ đích cho đúng bước
    đó, còn cụm là bộ quy ước nền của vai trò. File task có hạn mức chữ (xem
    _SKILL_INLINE_BUDGET bên workflows.py) — xếp cụm trước thì cụm ăn hết hạn
    mức và đúng cái skill người ta cất công chọn lại bị đẩy xuống "tự mở mà đọc".
    """
    out: dict[str, dict] = {}
    for sid in dict.fromkeys(s for s in (skill_ids or []) if s):
        try:
            out[sid] = get_skill(sid)
        except SkillError as e:
            out[sid] = {"id": sid, "missing": str(e)}

    for cat in dict.fromkeys(c for c in (categories or []) if c):
        folder = SKILLS_DIR / cat
        if not folder.is_dir():
            out.setdefault(f"{cat}/*", {"id": cat, "missing": f"skills/{cat}/ không tồn tại"})
            continue
        found = False
        for slug, path, fmt in _iter_skill_paths(folder):
            found = True
            skill = _build(cat, slug, path, fmt, with_content=True)
            out.setdefault(skill["id"], skill)
        if not found:
            out.setdefault(f"{cat}/*", {"id": cat, "missing": f"skills/{cat}/ chưa có skill nào"})
    return list(out.values())
