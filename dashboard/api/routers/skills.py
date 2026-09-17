"""
Skills API
==========
CRUD cho kho skill trong `skills/` (xem docstring skills_store.py).

Id skill có dấu `/` (`be/auth_jwt`) nên mọi route dùng converter `:path`. Route
tĩnh (`/categories`) phải khai TRƯỚC route `{skill_id:path}`, nếu không FastAPI
khớp "categories" thành một skill id.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import skills_store
from schemas import (SkillOut, SkillDetailOut, SkillCreate, SkillUpdate,
                     SkillDuplicate, SkillResourceWrite)

router = APIRouter()


def _guard(fn, *args, **kwargs):
    """SkillError = lỗi người dùng sửa được → 400 kèm nguyên văn thông báo."""
    try:
        return fn(*args, **kwargs)
    except skills_store.SkillError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[SkillOut])
def list_skills(category: Optional[str] = None, q: Optional[str] = None):
    return skills_store.list_skills(category=category, q=q)


@router.get("/categories")
def list_categories():
    """Cụm skill (= thư mục vai trò). `writable` để UI biết trước có sửa được không."""
    return {
        "categories": skills_store.list_categories(),
        "writable":   skills_store.writable(),
        "root":       str(skills_store.SKILLS_DIR),
    }


@router.post("/", response_model=SkillDetailOut)
def create_skill(payload: SkillCreate):
    return _guard(
        skills_store.create_skill,
        category=payload.category,
        name=payload.name,
        description=payload.description or "",
        body=payload.body or "",
        slug=payload.slug,
        tags=payload.tags,
        fmt=payload.format,
    )


@router.post("/import", response_model=SkillDetailOut)
async def import_skill(
    category: str = Form(...),
    slug: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    paths: str = Form(""),          # JSON list, cùng thứ tự với `files`
    files: List[UploadFile] = File(...),
):
    """Mang nguyên một thư mục skill có sẵn vào kho (SKILL.md + script + thư mục con).

    Trình duyệt gửi đường dẫn tương đối trong `paths` (webkitRelativePath) vì
    `filename` của multipart chỉ còn tên file — mất lớp thư mục là mất cấu trúc
    skill."""
    try:
        rel_paths = json.loads(paths) if paths else []
    except json.JSONDecodeError:
        rel_paths = []

    payload: list[tuple[str, bytes]] = []
    for i, f in enumerate(files):
        rel = rel_paths[i] if i < len(rel_paths) and rel_paths[i] else (f.filename or f"file{i}")
        payload.append((rel, await f.read()))
    return _guard(skills_store.import_files, category, payload, slug or None, name or None)


@router.post("/{skill_id:path}/to-folder", response_model=SkillDetailOut)
def to_folder(skill_id: str):
    """Skill 1 file → skill thư mục, để chứa được script và file phụ."""
    return _guard(skills_store.to_folder, skill_id)


@router.post("/{skill_id:path}/files", response_model=SkillDetailOut)
async def upload_resources(skill_id: str, paths: str = Form(""),
                           files: List[UploadFile] = File(...)):
    """Thêm file phụ (script, mẫu, dữ liệu) vào skill thư mục."""
    try:
        rel_paths = json.loads(paths) if paths else []
    except json.JSONDecodeError:
        rel_paths = []
    for i, f in enumerate(files):
        rel = rel_paths[i] if i < len(rel_paths) and rel_paths[i] else (f.filename or f"file{i}")
        _guard(skills_store.save_upload, skill_id, rel, await f.read())
    return _guard(skills_store.get_skill, skill_id)


@router.get("/{skill_id:path}/raw/{filename:path}")
def download_resource(skill_id: str, filename: str):
    """Tải file phụ về — đường duy nhất để xem file nhị phân."""
    path = _guard(skills_store.resource_file, skill_id, filename)
    return FileResponse(path, filename=path.name)


@router.get("/{skill_id:path}/files/{filename:path}")
def read_resource(skill_id: str, filename: str):
    return {"filename": filename, "content": _guard(skills_store.read_resource, skill_id, filename)}


@router.put("/{skill_id:path}/files/{filename:path}")
def write_resource(skill_id: str, filename: str, payload: SkillResourceWrite):
    _guard(skills_store.write_resource, skill_id, filename, payload.content)
    return _guard(skills_store.get_skill, skill_id)


@router.delete("/{skill_id:path}/files/{filename:path}")
def delete_resource(skill_id: str, filename: str):
    _guard(skills_store.delete_resource, skill_id, filename)
    return _guard(skills_store.get_skill, skill_id)


@router.post("/{skill_id:path}/duplicate", response_model=SkillDetailOut)
def duplicate_skill(skill_id: str, payload: SkillDuplicate | None = None):
    payload = payload or SkillDuplicate()
    return _guard(skills_store.duplicate_skill, skill_id, payload.slug, payload.category)


@router.get("/{skill_id:path}", response_model=SkillDetailOut)
def get_skill(skill_id: str):
    try:
        return skills_store.get_skill(skill_id)
    except skills_store.SkillError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{skill_id:path}", response_model=SkillDetailOut)
def update_skill(skill_id: str, payload: SkillUpdate):
    return _guard(
        skills_store.update_skill,
        skill_id,
        name=payload.name,
        description=payload.description,
        body=payload.body,
        tags=payload.tags,
        category=payload.category,
        slug=payload.slug,
    )


@router.delete("/{skill_id:path}")
def delete_skill(skill_id: str):
    _guard(skills_store.delete_skill, skill_id)
    return {"ok": True}
