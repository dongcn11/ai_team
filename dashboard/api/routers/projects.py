from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
import io
import json
import os
import re
import shutil
import tomllib
import uuid
import yaml
import zipfile
from datetime import datetime
from pathlib import Path


# ── Profiles loader ──────────────────────────────────────────────────────────
# Đọc profiles từ profiles.yaml (single source of truth). File được mount vào
# /profiles.yaml trong docker-compose. Fallback paths cho dev local.

def _profiles_candidates() -> list[Path]:
    """Build candidate paths for profiles.yaml, defensive against shallow trees."""
    cands: list[Path] = []
    env_path = os.getenv("PROFILES_YAML", "")
    if env_path:
        cands.append(Path(env_path))
    cands.append(Path("/profiles.yaml"))  # docker mount point
    here = Path(__file__).resolve()
    for p in here.parents:  # walk up safely
        cands.append(p / "profiles.yaml")
    return cands


def _load_profiles_yaml() -> dict[str, dict]:
    for cand in _profiles_candidates():
        if cand and cand.exists():
            with open(cand, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("profiles", {}) or {}
    return {}


def _profile_agents() -> dict[str, list[str]]:
    """profile_name → [agent_key list]. Load fresh mỗi lần để pick up yaml changes."""
    profiles = _load_profiles_yaml()
    return {name: cfg.get("agents", []) for name, cfg in profiles.items() if cfg.get("agents")}


# Chỉ "opencode". Claude Code bị chặn trong pipeline tự động — subscription cá
# nhân không được dùng cho automation chạy nền. Xem ai_team/runner.py.
DEFAULT_MODEL = {
    "opencode": "opencode/qwen3.5-plus",
}
BLOCKED_TOOLS = {"claude"}
CLAUDE_BLOCKED_DETAIL = (
    "Tool 'claude' bị chặn: pipeline tự động không được dùng subscription Claude "
    "(rủi ro khoá account). Dùng 'opencode'."
)

from system_config import get_system_agents, WORKSPACE_AREAS
from database import get_db
from models import Project, ProjectTask, FeatureFile, Workflow, WorkflowRun

CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/clients"))
OUTPUT_DIR  = Path(os.getenv("OUTPUT_DIR",  "/output"))
# Thu muc chua code cac du an TREN MAY HOST. clients/<slug>/ chi giu tai lieu
# (prd, task, settings); code de rieng ra ngoai nen mac dinh la duong dan tuyet
# doi — duong dan tuong doi bi ai_team/config.py giai theo clients/<slug>/ nen
# khong the tro ra ngoai do duoc.
CODE_ROOT   = os.getenv("CODE_ROOT", "C:/www").replace(chr(92), "/").rstrip("/")

VALID_AGENT_KEYS = ["pm", "scrum", "analyst", "be1", "be2", "fe1", "fe2", "fs1", "fs2", "leader"]

_SKIP_EXTS = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico",
              ".woff", ".woff2", ".ttf", ".eot", ".map", ".bin", ".lock", ".cache"}
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
              "node_modules", ".venv", "venv", ".git"}

router = APIRouter()


# ── TOML helpers ──────────────────────────────────────────────────────────────

def _toml_error(folder: Path) -> Optional[str]:
    """Mô tả lỗi cú pháp của settings.toml, None nếu file ổn."""
    f = folder / "settings.toml"
    if not f.exists():
        return None
    try:
        with open(f, "rb") as fh:
            tomllib.load(fh)
        return None
    except tomllib.TOMLDecodeError as e:
        return str(e)
    except OSError as e:
        return f"không đọc được file: {e}"


def _read_toml(folder: Path) -> dict:
    """Đọc settings.toml, file hỏng thì trả {} thay vì ném.

    Một project có settings.toml sai cú pháp từng làm CẢ trang Projects trắng
    (500 ở /api/projects) — hỏng 1 folder mà mất hết. Giờ folder hỏng vẫn hiện,
    kèm cờ config_error để biết mà sửa. Đường ghi dùng _read_toml_strict."""
    f = folder / "settings.toml"
    if not f.exists():
        return {}
    try:
        with open(f, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _read_toml_strict(folder: Path) -> dict:
    """Dùng trước khi GHI: file hỏng thì báo lỗi rõ, tuyệt đối không ghi đè.

    Nếu để _read_toml lenient chạy ở đường ghi, ta sẽ lấy {} rồi _write_toml
    ghi lại file rỗng — xoá sạch cấu hình của người ta chỉ vì 1 dấu backslash."""
    err = _toml_error(folder)
    if err:
        raise HTTPException(
            status_code=400,
            detail=f"clients/{folder.name}/settings.toml sai cú pháp TOML ({err}). "
                   f"Sửa file rồi thử lại — API không ghi đè để tránh mất cấu hình.",
        )
    return _read_toml(folder)


def _toml_str(v) -> str:
    """Chuoi TOML basic-string da escape.

    Dung json.dumps vi bo escape cua JSON trung voi TOML o dung nhung ky tu can:
    dau gach nguoc, dau nhay kep, xuong dong, tab. Truoc day ghi tran nen duong
    dan Windows kieu C:(gach nguoc)www lam file TOML hong -> ca trang Projects 500.
    ensure_ascii=False de giu nguyen tieng Viet.
    """
    return json.dumps(str(v), ensure_ascii=False)


def _write_toml(folder: Path, raw: dict):
    lines = []
    section_order = ["agents", "slack", "output", "timeouts", "tech_stack", "project"]
    ordered = [s for s in section_order if s in raw] + [s for s in raw if s not in section_order]
    for section in ordered:
        lines.append(f"[{section}]")
        for k, v in raw[section].items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, int):
                lines.append(f"{k} = {v}")
            else:
                # Escape thật sự: đường dẫn Windows "C:\www\x" mà ghi trần sẽ
                # tạo TOML hỏng (\w không phải escape hợp lệ) và làm 500 cả trang.
                lines.append(f"{k} = {_toml_str(v)}")
        lines.append("")
    (folder / "settings.toml").write_text("\n".join(lines), encoding="utf-8")


def _write_local_template(folder: Path, slug: str):
    """Tạo settings.local.toml — override cục bộ, KHÔNG commit vào git.

    File chỉ chứa comment mẫu; bỏ comment key cần override cho riêng máy mình.
    Không ghi đè nếu file đã tồn tại.
    """
    target = folder / "settings.local.toml"
    if target.exists():
        return
    template = (
        f"# settings.local.toml — override cục bộ cho project '{slug}'\n"
        "# File này KHÔNG nên commit vào git (đặc thù từng máy / chứa secret).\n"
        "# Bỏ comment các key bên dưới để ghi đè giá trị trong settings.toml.\n"
        "\n"
        "# [output]\n"
        f'# directory = "D:/local/output/{slug}"\n'
        "\n"
        "# [slack]\n"
        '# bot_token = "xoxb-..."\n'
        '# channel = "#ai-team"\n'
        "\n"
        "# [agents]\n"
        '# pm_model = "opencode/qwen3.6-plus"\n'
        "\n"
        "# Token GitHub RIENG cho project nay — worker.py doc roi truyen vao tien trinh\n"
        "# agent qua env, khong ghi vao .git/config. Moi project mot token nen day len\n"
        "# to chuc / tai khoan nao cung duoc, khong phai chot cung 1 tai khoan o\n"
        "# git config --global.\n"
        "# [git]\n"
        '# token = "ghp_..."\n'
        '# username = "ten-tai-khoan"   # tuy chon, mac dinh x-access-token\n'
    )
    target.write_text(template, encoding="utf-8")


# Thu muc code cua project. Hai kieu bo tri, khai bang [output] layout:
#   - "split" (mac dinh): code chia theo vung — <root>/backend, <root>/frontend, ...
#     Tung vung con co the tro sang thu muc rieng qua [output] <key>_directory.
#   - "mono": du an khong tach BE/FE (Laravel Blade, WordPress...) — code nam thang
#     trong <root>, khong dung thu muc con nao.
# Dashboard khong tu tao thu muc — chi soat xem co chua roi bao lai (_check_workspace).
# Cung quy uoc voi pipeline (ai_team/orchestrator.py::_work_dir_for_role) va voi khoi "Noi lam
# viec" trong file task (dashboard/api/routers/workflows.py::_workspace_section).
def _is_abs_path(p: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\/]", p)) or p.startswith("/")


def _norm_path(p: str) -> str:
    """Chuan hoa duong dan nguoi dung go: dau gach nguoc -> /, bo ./ dau va / cuoi."""
    d = (p or "").replace(chr(92), "/").strip().rstrip("/")
    return d if _is_abs_path(d) else d.lstrip("./").rstrip("/")


def _code_layout(raw: dict) -> str:
    """"mono" = du an gop 1 thu muc; con lai coi nhu "split" (mac dinh, tuong thich cu)."""
    val = str((raw.get("output") or {}).get("layout") or "").strip().lower()
    return "mono" if val == "mono" else "split"


def _code_root(raw: dict, slug: str) -> str:
    """Thu muc code, quy ve duong dan tinh tu GOC REPO de con di soat.

    ai_team/config.py giai duong dan tuong doi theo THU MUC PROJECT
    (clients/<slug>/), nen o day phai cong lai tien to do. Truoc kia doc thang
    chuoi trong settings.toml nen bao sai cho: gia tri "./clients/x/output"
    thuc te ra clients/x/clients/x/output.
    """
    raw_dir = _norm_path(str((raw.get("output") or {}).get("directory") or ""))
    if not raw_dir:
        return f"clients/{slug}/output"
    return raw_dir if _is_abs_path(raw_dir) else f"clients/{slug}/{raw_dir}"


def _area_dirs(raw: dict, slug: str) -> dict:
    """Vung code -> thu muc that. Tra ve {} khi du an de kieu gop (mono).

    Chi liet ke vung project that su khai tech stack; chua khai gi thi lay
    backend + frontend cho co cho bat dau."""
    if _code_layout(raw) == "mono":
        return {}
    out  = raw.get("output") or {}
    root = _code_root(raw, slug)
    tech = raw.get("tech_stack") or {}
    keys = [k for k in WORKSPACE_AREAS if str(tech.get(k) or "").strip()] or ["backend", "frontend"]
    return {k: (_norm_path(str(out.get(f"{k}_directory") or "")) or f"{root}/{WORKSPACE_AREAS[k][0]}")
            for k in keys}


def _apply_output_settings(raw: dict, slug: str, *, directory=None, layout=None,
                           backend_dir=None, frontend_dir=None) -> None:
    """Ghi [output] theo input cua form. None = khong dong toi truong do."""
    out = raw.setdefault("output", {})
    if directory is not None:
        out["directory"] = directory.strip() or f"{CODE_ROOT}/{slug}"
    if layout is not None:
        out["layout"] = _code_layout({"output": {"layout": layout}})
    mono = _code_layout(raw) == "mono"
    for key, val in (("backend", backend_dir), ("frontend", frontend_dir)):
        if val is None and not mono:
            continue
        path = _norm_path(val or "")
        if path and not mono:
            out[f"{key}_directory"] = path
        else:
            # Bo trong = quay ve <root>/<vung>; kieu gop thi khong co vung nao ca.
            out.pop(f"{key}_directory", None)


def _check_workspace(folder: Path, raw: dict) -> dict:
    """Kiem tra thu muc code cua project da co chua — KHONG tu tao ho.

    Dashboard khong sinh thu muc thay dev: thieu cai nao thi bao lai kem lenh mkdir
    de dev tu tao dung cho minh muon, thay vi im lang de ra thu muc rac trong repo.

    API lai chay trong container nen chi nhin thay cac mount: clients/ (ghi duoc),
    output/ (chi doc). Duong dan tuyet doi kieu C:/www/x nam ngoai container -> khong
    kiem tra duoc, xep vao "unknown" va van nhac dev tu kiem.
    """
    root    = _code_root(raw, folder.name)
    targets = list(_area_dirs(raw, folder.name).values()) or [root]

    exists, missing, unknown = [], [], []
    for t in targets:
        if _is_abs_path(t) or not t.startswith("clients/"):
            unknown.append(t)
            continue
        (exists if (CLIENTS_DIR / Path(t).relative_to("clients")).is_dir() else missing).append(t)

    todo = missing + unknown
    return {
        "ok":        not todo,
        "path":      root,
        "targets":   targets,
        "exists":    exists,
        "missing":   missing,
        "unknown":   unknown,
        "mkdir_cmd": ("mkdir " + " ".join(f'"{t}"' for t in todo)) if todo else "",
    }


def _resolve_dir(folder: Path, key: str, fallback: Path) -> Path:
    """Resolve a directory from settings.toml. Relative paths → relative to project folder."""
    raw     = _read_toml(folder)
    dir_str = raw.get("output", {}).get(key, "")
    if not dir_str:
        return fallback
    p = Path(dir_str)
    if p.is_absolute():
        return fallback  # absolute Windows paths not accessible in Docker
    return (folder / p).resolve()


def _resolve_output_dir(folder: Path) -> Path:
    return _resolve_dir(folder, "directory", OUTPUT_DIR / folder.name)


def _resolve_docs_dir(folder: Path) -> Path:
    code_dir = _resolve_output_dir(folder)
    return _resolve_dir(folder, "docs_directory", code_dir / "docs")


def _folder_to_project(folder: Path) -> dict:
    raw     = _read_toml(folder)
    agents  = get_system_agents(folder / "settings.toml")
    tech    = raw.get("tech_stack", {})
    project = raw.get("project", {})
    name    = project.get("name") or folder.name.replace("_", " ").replace("-", " ").title()
    return {
        "id":          folder.name,
        "name":        name,
        "profile":     project.get("profile", ""),
        "tech_stack":  tech,
        "agents":      agents,
        "agent_count": len(agents),
        "output_dir":   raw.get("output", {}).get("directory", f"./output/{folder.name}"),
        "code_layout":  _code_layout(raw),
        "backend_dir":  raw.get("output", {}).get("backend_directory", ""),
        "frontend_dir": raw.get("output", {}).get("frontend_directory", ""),
        "client_docs_dir": raw.get("output", {}).get("client_docs_directory", ""),
        "config_error": _toml_error(folder),
    }


# ── Project endpoints ─────────────────────────────────────────────────────────

@router.get("/defaults")
def project_defaults() -> dict:
    """Gia tri mac dinh cho form tao project — de UI khoi doan lai o frontend."""
    return {"code_root": CODE_ROOT}


@router.get("/profiles")
def list_profiles() -> List[dict]:
    """List tất cả profile từ profiles.yaml để dashboard render dropdown."""
    profiles = _load_profiles_yaml()
    result = []
    for name, cfg in profiles.items():
        agents = cfg.get("agents", []) or []
        label = cfg.get("label", name)
        # Hiển thị: "name — agent1+agent2+..."
        agents_display = "+".join(k.upper() if k in ("pm",) else k.capitalize() for k in agents)
        result.append({
            "name": name,
            "label": label,
            "agents": agents,
            "stages_disabled": cfg.get("stages_disabled", []) or [],
            "display": f"{name} — {agents_display}" if agents else name,
        })
    return result


@router.get("/")
def list_projects() -> List[dict]:
    if not CLIENTS_DIR.exists():
        return []
    return [
        _folder_to_project(f)
        for f in sorted(CLIENTS_DIR.iterdir())
        if f.is_dir() and (f / "settings.toml").exists()
    ]


@router.get("/{folder_name}")
def get_project(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return _folder_to_project(folder)


class ProjectCreate(BaseModel):
    folder_name: str
    profile: str = "fullstack"
    default_tool: str = "opencode"
    backend: str = ""
    frontend: str = ""
    server_side: str = ""
    # Thư mục code của dự án. Bỏ trống → ./clients/<slug>/output
    output_dir: str = ""
    # "split" = tách backend/frontend (mặc định), "mono" = gộp 1 thư mục (Laravel Blade…)
    layout: str = "split"
    # Chỉ dùng khi layout="split". Bỏ trống → <output_dir>/backend, <output_dir>/frontend
    backend_dir: str = ""
    frontend_dir: str = ""


@router.post("/")
def create_project(payload: ProjectCreate) -> dict:
    slug = re.sub(r"[^a-z0-9_-]", "_", payload.folder_name.strip().lower())
    if not slug:
        raise HTTPException(status_code=400, detail="Tên project không hợp lệ")
    profile_agents = _profile_agents()
    if payload.profile not in profile_agents:
        raise HTTPException(status_code=400, detail=f"Profile không hợp lệ. Chọn: {list(profile_agents)}")
    if payload.default_tool in BLOCKED_TOOLS:
        raise HTTPException(status_code=400, detail=CLAUDE_BLOCKED_DETAIL)
    if payload.default_tool not in DEFAULT_MODEL:
        raise HTTPException(status_code=400, detail=f"Tool phải là một trong: {sorted(DEFAULT_MODEL)}")

    folder = CLIENTS_DIR / slug
    if folder.exists():
        raise HTTPException(status_code=409, detail=f"Project '{slug}' đã tồn tại")

    folder.mkdir(parents=True)

    model = DEFAULT_MODEL[payload.default_tool]
    agents: dict[str, str] = {}
    for key in profile_agents[payload.profile]:
        agents[f"{key}_tool"]  = payload.default_tool
        agents[f"{key}_model"] = model

    raw: dict = {
        "project": {"name": slug.replace("_", " ").replace("-", " ").title(), "profile": payload.profile},
        "agents":  agents,
        "output":  {},
        "timeouts": {"claude_code": 600, "opencode": 600},
        "tech_stack": {
            "backend":  payload.backend  or "Python FastAPI + SQLModel + SQLite",
            "frontend": payload.frontend or "React + TypeScript + Vite + TailwindCSS",
            # Chỉ ghi khi có khai — dự án không có phần server-side thì đừng bịa ra
            # thư mục cho agent hiểu nhầm.
            **({"server_side": payload.server_side} if payload.server_side.strip() else {}),
        },
    }
    _apply_output_settings(raw, slug,
                           directory=payload.output_dir, layout=payload.layout,
                           backend_dir=payload.backend_dir, frontend_dir=payload.frontend_dir)
    _write_toml(folder, raw)
    _write_local_template(folder, slug)
    # Soát thư mục code ngay lúc tạo project để dev biết còn thiếu gì — dashboard
    # không tự tạo, chỉ báo lại kèm lệnh mkdir.
    workspace = _check_workspace(folder, raw)
    return {**_folder_to_project(folder), "workspace": workspace}


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    profile: Optional[str] = None
    backend: Optional[str] = None
    frontend: Optional[str] = None
    server_side: Optional[str] = None
    output_dir: Optional[str] = None
    # Thư mục tài liệu KHÁCH CUNG CẤP. Để riêng vì tài liệu thường rất nặng, không
    # nên nằm chung clients/. Rỗng = mặc định clients/<slug>/docs.
    client_docs_dir: Optional[str] = None
    layout: Optional[str] = None
    backend_dir: Optional[str] = None
    frontend_dir: Optional[str] = None


@router.patch("/{folder_name}")
def patch_project(folder_name: str, payload: ProjectPatch) -> dict:
    """Update mutable fields in settings.toml — folder slug stays immutable."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    raw = _read_toml_strict(folder)

    if payload.profile is not None:
        profile_agents = _profile_agents()
        if payload.profile and payload.profile not in profile_agents:
            raise HTTPException(status_code=400,
                                detail=f"Profile không hợp lệ. Chọn: {list(profile_agents)}")
        raw.setdefault("project", {})["profile"] = payload.profile

    if payload.name is not None:
        raw.setdefault("project", {})["name"] = payload.name.strip() or folder.name

    if payload.backend is not None:
        raw.setdefault("tech_stack", {})["backend"] = payload.backend.strip()

    if payload.frontend is not None:
        raw.setdefault("tech_stack", {})["frontend"] = payload.frontend.strip()

    if payload.server_side is not None:
        tech = raw.setdefault("tech_stack", {})
        if payload.server_side.strip():
            tech["server_side"] = payload.server_side.strip()
        else:
            tech.pop("server_side", None)     # xoá trắng = dự án không có vùng này

    workspace = None
    if payload.client_docs_dir is not None:
        out = raw.setdefault("output", {})
        val = payload.client_docs_dir.strip().replace(chr(92), "/").rstrip("/")
        if val:
            out["client_docs_directory"] = val
        else:
            out.pop("client_docs_directory", None)
    if any(v is not None for v in (payload.output_dir, payload.layout,
                                   payload.backend_dir, payload.frontend_dir)):
        _apply_output_settings(raw, folder_name,
                               directory=payload.output_dir, layout=payload.layout,
                               backend_dir=payload.backend_dir, frontend_dir=payload.frontend_dir)
        workspace = _check_workspace(folder, raw)

    _write_toml(folder, raw)
    out = _folder_to_project(folder)
    if workspace is not None:
        out["workspace"] = workspace
    return out


# ── Delete / Backup ───────────────────────────────────────────────────────────

def _zip_dir(base: Path, zip_buf: io.BytesIO, arcname_prefix: str = ""):
    """Nén toàn bộ base vào zip_buf."""
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(base.rglob("*")):
            if f.is_file():
                arc = Path(arcname_prefix) / f.relative_to(base)
                zf.write(f, arc)


@router.get("/{folder_name}/backup/docs")
def backup_docs(folder_name: str):
    """Tải ZIP chứa docs/ + prd.md của project."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    buf = io.BytesIO()
    docs_dir = folder / "docs"
    prd_file = folder / "prd.md"

    if not docs_dir.exists() and not prd_file.exists():
        raise HTTPException(status_code=404, detail="Chưa có docs để backup")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if docs_dir.exists():
            for f in sorted(docs_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, Path("docs") / f.relative_to(docs_dir))
        if prd_file.exists():
            zf.write(prd_file, "prd.md")

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder_name}_docs_{ts}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{folder_name}/backup/source")
def backup_source(folder_name: str):
    """Tải ZIP chứa toàn bộ source code (output dir) của project."""
    folder   = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    src_dir = _resolve_output_dir(folder)
    if not src_dir.exists():
        raise HTTPException(status_code=404, detail="Chưa có source code để backup")

    buf = io.BytesIO()
    _SKIP = {".pyc", ".pyo", ".cache"}
    _SKIP_D = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".git"}

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src_dir.rglob("*")):
            if not f.is_file():
                continue
            parts = f.relative_to(src_dir).parts
            if any(p in _SKIP_D for p in parts[:-1]):
                continue
            if f.suffix in _SKIP:
                continue
            zf.write(f, Path("source") / f.relative_to(src_dir))

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder_name}_source_{ts}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{folder_name}")
def delete_project(folder_name: str) -> dict:
    """Xóa project (clients/{folder}). Output dir không bị xóa (mounted read-only)."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(folder)
    return {"ok": True, "deleted": folder_name}


# ── Agent management (settings.toml) ─────────────────────────────────────────

@router.get("/{folder_name}/settings-agents")
def list_settings_agents(folder_name: str) -> List[dict]:
    folder = CLIENTS_DIR / folder_name
    return get_system_agents(folder / "settings.toml")


class AgentFsPayload(BaseModel):
    key: str
    tool: str = "opencode"
    model: str = "opencode/qwen3.5-plus"


@router.post("/{folder_name}/settings-agents")
def add_settings_agent(folder_name: str, payload: AgentFsPayload) -> List[dict]:
    if payload.key not in VALID_AGENT_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid key. Valid: {VALID_AGENT_KEYS}")
    if payload.tool in BLOCKED_TOOLS:
        raise HTTPException(status_code=400, detail=CLAUDE_BLOCKED_DETAIL)
    folder = CLIENTS_DIR / folder_name
    if not folder.exists():
        raise HTTPException(status_code=404, detail="Client folder not found")
    raw = _read_toml_strict(folder)
    agents = raw.setdefault("agents", {})
    if f"{payload.key}_tool" in agents:
        raise HTTPException(status_code=409, detail=f"Agent '{payload.key}' already exists")
    agents[f"{payload.key}_tool"]  = payload.tool
    agents[f"{payload.key}_model"] = payload.model
    _write_toml(folder, raw)
    return get_system_agents(folder / "settings.toml")


# Workspace sub-path cho từng coding agent (stage/PM/Scrum/Analyst/Leader dùng docs chung)
_AGENT_WORKSPACE: dict[str, str] = {
    "be1": "backend/be1",
    "be2": "backend/be2",
    "fe1": "frontend/fe1",
    "fe2": "frontend/fe2",
    "fs1": "fullstack/fs1",
    "fs2": "fullstack/fs2",
}


@router.delete("/{folder_name}/settings-agents/{agent_key}")
def remove_settings_agent(
    folder_name: str,
    agent_key: str,
    cleanup: bool = Query(False, description="Xóa workspace code của agent"),
) -> dict:
    folder = CLIENTS_DIR / folder_name
    raw = _read_toml_strict(folder)
    agents = raw.get("agents", {})
    if f"{agent_key}_tool" not in agents:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")
    agents.pop(f"{agent_key}_tool", None)
    agents.pop(f"{agent_key}_model", None)
    raw["agents"] = agents
    _write_toml(folder, raw)

    deleted_workspace: str | None = None
    if cleanup and agent_key in _AGENT_WORKSPACE:
        ws = _resolve_output_dir(folder) / _AGENT_WORKSPACE[agent_key]
        if ws.exists():
            shutil.rmtree(ws)
            deleted_workspace = str(ws)

    return {
        "agents": get_system_agents(folder / "settings.toml"),
        "deleted_workspace": deleted_workspace,
    }


# ── Token GitHub riêng từng project ───────────────────────────────────────────
# Nhiều tài khoản / nhiều tổ chức → chốt cứng 1 tài khoản trong `git config --global`
# là sai ngay project thứ hai. Mỗi project khai token riêng ở settings.local.toml
# (file đã nằm trong .gitignore); worker.py đọc rồi truyền vào env của tiến trình
# agent, không ghi vào .git/config và KHÔNG đi qua DB.

def _local_block(folder: Path, name: str) -> dict:
    """Đọc 1 khối trong settings.local.toml ([git], [telegram]...). File hỏng hoặc
    chưa có khối đó → {} (coi như chưa khai), không ném lỗi lên UI."""
    f = folder / "settings.local.toml"
    if not f.exists():
        return {}
    try:
        return tomllib.loads(f.read_text(encoding="utf-8")).get(name) or {}
    except Exception:
        return {}


def _write_local_block(folder: Path, name: str, values: dict) -> None:
    """Ghi/xoá 1 khối trong settings.local.toml.

    Chỉ thay đúng khối đó chứ không ghi đè cả file: phần comment mẫu và các
    override khác (output/git/telegram/agents) của người dùng phải còn nguyên.
    values rỗng = xoá hẳn khối."""
    f = folder / "settings.local.toml"
    body = f.read_text(encoding="utf-8") if f.exists() else ""
    pattern = re.compile(rf"^\[{re.escape(name)}\][^\[]*", re.MULTILINE)
    if values:
        block = f"[{name}]" + chr(10)
        for k, v in values.items():
            block += f"{k} = {_toml_str(str(v))}" + chr(10)
        # lambda chứ không truyền thẳng chuỗi: re.sub diễn giải \g, ... trong
        # phần thay thế, mà token người dùng dán vào là chuỗi tuỳ ý.
        body = (pattern.sub(lambda _m: block, body, count=1) if pattern.search(body)
                else body.rstrip() + chr(10) * 2 + block)
    else:
        body = pattern.sub("", body).rstrip() + chr(10)
    f.write_text(body, encoding="utf-8")


def _read_local_git(folder: Path) -> dict:
    return _local_block(folder, "git")


def _mask(token: str) -> str:
    """Chỉ lộ 4 ký tự cuối — đủ để nhận ra token nào, không đủ để dùng lại."""
    t = (token or "").strip()
    return f"…{t[-4:]}" if len(t) > 4 else ("…" if t else "")


@router.get("/{folder_name}/git")
def get_project_git(folder_name: str) -> dict:
    """Trạng thái token, KHÔNG bao giờ trả token ra ngoài."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    git = _read_local_git(folder)
    token = str(git.get("token") or "").strip()
    return {
        "configured": bool(token),
        "hint":       _mask(token),
        "username":   str(git.get("username") or ""),
    }


class ProjectGitPayload(BaseModel):
    token: str = ""
    username: str = ""


@router.put("/{folder_name}/git")
def set_project_git(folder_name: str, payload: ProjectGitPayload) -> dict:
    """Ghi [git] vào settings.local.toml. Token rỗng = xoá, quay về hỏi tay như cũ.

    Sửa đúng khối [git] chứ không ghi đè cả file — phần comment mẫu và các override
    khác (output/slack/agents) của người dùng phải còn nguyên."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    token = payload.token.strip()
    user  = payload.username.strip()
    values = {}
    if token:
        values["token"] = token
        if user:
            values["username"] = user
    _write_local_block(folder, "git", values)
    return get_project_git(folder_name)


# Bot Telegram/Slack của dự án KHÔNG nằm ở đây nữa: một dự án có nhiều quy trình
# nên có nhiều bot, mỗi bot buộc vào một hoặc vài workflow — quan hệ đó thuộc về
# DB chứ không phải một khối TOML cạnh thư mục. Xem models.ChatBot + tab Bots.

# ── Thư mục & tài khoản git RIÊNG từng agent dev ──────────────────────────────
# Một project có thể có 3 "ông dev" (BE, FE, fullstack) — mỗi ông một repo/thư mục
# và một tài khoản GitHub. Vùng backend/frontend theo tech stack là mặc định;
# agent nào khai riêng thì thắng.
#   settings.toml       [agents] be1_directory = "C:/www/my_api"   (thư mục)
#   settings.local.toml [git.be1] token = "ghp_..."                 (tài khoản)
# Không khai → rơi về vùng của vai trò (be→backend, fe→frontend), rồi về gốc;
# token rơi về [git] của project.

CODING_AGENTS = ["be1", "be2", "fe1", "fe2", "fs1", "fs2"]
_AGENT_AREA = {"be1": "backend", "be2": "backend", "fe1": "frontend", "fe2": "frontend"}


def _agent_workspace(raw: dict, slug: str, key: str) -> dict:
    """Bộ thư mục code của 1 agent dev — y hệt bộ của project nhưng riêng từng agent.

    Mỗi agent khai được đủ: thư mục gốc, bố trí (mono/split), thư mục backend/
    frontend. Khai cái nào thì cái đó thắng, còn lại thừa kế từ project:
        [agents]
        fs1_directory          = "C:/www/my_app"
        fs1_layout             = "split"
        fs1_backend_directory  = "C:/www/my_app/api"
        fs1_frontend_directory = "C:/www/my_app/web"
    Cùng quy ước với workflows.py::_agent_workspace — sửa một bên thì sửa cả hai.

    Trả về: root, layout, areas{backend, frontend}, workdir (thư mục agent sẽ
    ghi code), và own{...} = trường nào là khai riêng."""
    ag = raw.get("agents") or {}

    def g(field: str) -> str:
        return str(ag.get(f"{key}_{field}") or "").strip()

    def abs_or_client(p: str) -> str:
        return p if _is_abs_path(p) else f"clients/{slug}/{p}"

    own_root   = _norm_path(g("directory"))
    own_layout = g("layout").lower()
    root   = abs_or_client(own_root) if own_root else _code_root(raw, slug)
    layout = own_layout if own_layout in ("mono", "split") else _code_layout(raw)

    areas: dict = {}
    if layout != "mono":
        proj_areas = _area_dirs(raw, slug) if not own_root else {}
        for area in ("backend", "frontend"):
            own = _norm_path(g(f"{area}_directory"))
            if own:
                areas[area] = abs_or_client(own)
            elif area in proj_areas:
                areas[area] = proj_areas[area]
            else:
                areas[area] = f"{root}/{area}"

    role_area = _AGENT_AREA.get(key)
    workdir = areas.get(role_area) if role_area and role_area in areas else root
    return {
        "root": root, "layout": layout, "areas": areas, "workdir": workdir,
        "own": {
            "directory":          own_root,
            "layout":             own_layout if own_layout in ("mono", "split") else "",
            "backend_directory":  _norm_path(g("backend_directory")),
            "frontend_directory": _norm_path(g("frontend_directory")),
        },
    }


def _agent_git(folder: Path, key: str) -> dict:
    """[git.<key>] nếu có, không thì [git] của project."""
    git = _read_local_git(folder)
    own = git.get(key) if isinstance(git.get(key), dict) else None
    src = own if own and str(own.get("token") or "").strip() else None
    cfg = src if src is not None else git
    token = str(cfg.get("token") or "").strip()
    return {
        "configured": bool(token),
        "hint":       _mask(token),
        "username":   str(cfg.get("username") or ""),
        "own":        src is not None,     # token riêng hay thừa kế từ project
    }


@router.get("/{folder_name}/agent-workspaces")
def list_agent_workspaces(folder_name: str) -> List[dict]:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    raw = _read_toml(folder)
    agents = get_system_agents(folder / "settings.toml")
    present = {a["key"]: a for a in agents}
    out = []
    for key in CODING_AGENTS:
        if key not in present:
            continue
        ws = _agent_workspace(raw, folder_name, key)
        out.append({
            "key":  key,
            "name": present[key].get("name") or key,
            **ws,
            "git":  _agent_git(folder, key),
        })
    return out


class AgentWorkspacePayload(BaseModel):
    # None = giữ nguyên, "" = xoá (về mặc định của project)
    directory: Optional[str] = None
    layout: Optional[str] = None            # "split" | "mono" | ""
    backend_directory: Optional[str] = None
    frontend_directory: Optional[str] = None
    token: Optional[str] = None             # None = giữ nguyên, "" = xoá (về token project)
    username: Optional[str] = None


@router.put("/{folder_name}/agent-workspaces/{agent_key}")
def set_agent_workspace(folder_name: str, agent_key: str, payload: AgentWorkspacePayload) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir() or not (folder / "settings.toml").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    if agent_key not in CODING_AGENTS:
        raise HTTPException(status_code=400, detail=f"Chỉ cấu hình được agent dev: {CODING_AGENTS}")

    fields = {
        "directory":          payload.directory,
        "layout":             payload.layout,
        "backend_directory":  payload.backend_directory,
        "frontend_directory": payload.frontend_directory,
    }
    if any(v is not None for v in fields.values()):
        raw = _read_toml_strict(folder)
        agents = raw.setdefault("agents", {})
        for field, val in fields.items():
            if val is None:
                continue
            v = val.strip().lower() if field == "layout" else _norm_path(val)
            if field == "layout" and v not in ("mono", "split", ""):
                raise HTTPException(status_code=400, detail="layout phải là 'split' hoặc 'mono'")
            if v:
                agents[f"{agent_key}_{field}"] = v
            else:
                agents.pop(f"{agent_key}_{field}", None)
        _write_toml(folder, raw)

    if payload.token is not None:
        token = payload.token.strip()
        values = {}
        if token:
            values["token"] = token
            if (payload.username or "").strip():
                values["username"] = payload.username.strip()
        # Khối con [git.<key>] — regex của _write_local_block khớp đúng tên khối
        _write_local_block(folder, f"git.{agent_key}", values)
    elif payload.username is not None:
        git = _read_local_git(folder)
        own = git.get(agent_key) if isinstance(git.get(agent_key), dict) else {}
        if str(own.get("token") or "").strip():
            _write_local_block(folder, f"git.{agent_key}",
                               {"token": own["token"], **({"username": payload.username.strip()}
                                                         if payload.username.strip() else {})})

    for item in list_agent_workspaces(folder_name):
        if item["key"] == agent_key:
            return item
    raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' không có trong project")


# ── PRD ───────────────────────────────────────────────────────────────────────

class PrdPayload(BaseModel):
    content: str


@router.get("/{folder_name}/prd")
def get_prd(folder_name: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    prd = folder / "prd.md"
    if not prd.exists():
        return {"exists": False, "content": ""}
    return {"exists": True, "content": prd.read_text(encoding="utf-8")}


@router.put("/{folder_name}/prd")
def save_prd(folder_name: str, payload: PrdPayload) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    (folder / "prd.md").write_text(payload.content, encoding="utf-8")
    return {"ok": True}


@router.delete("/{folder_name}/prd")
def delete_prd(folder_name: str) -> dict:
    prd = CLIENTS_DIR / folder_name / "prd.md"
    if not prd.exists():
        raise HTTPException(status_code=404, detail="prd.md not found")
    prd.unlink()
    return {"ok": True}


# ── Features (ideas → ProjectTask + prd.md) ───────────────────────────────────

def _get_or_create_db_project(folder_name: str, db: Session) -> Project:
    proj = db.query(Project).filter(Project.client_folder == folder_name).first()
    if not proj:
        name = folder_name.replace("_", " ").replace("-", " ").title()
        proj = Project(name=name, client_folder=folder_name, status="active")
        db.add(proj)
        db.commit()
        db.refresh(proj)
    return proj


def _sync_features_to_prd(folder: Path, features: list):
    """Ghi/cập nhật section ## Features trong prd.md."""
    prd_path = folder / "prd.md"
    existing = prd_path.read_text(encoding="utf-8") if prd_path.exists() else "# PRD\n\n## Tổng quan\n\n"

    # Build features table
    rows = ["", "## Features", "",
            "| # | Tên | Mô tả | Priority | Status |",
            "|---|-----|-------|----------|--------|"]
    for f in features:
        icon = "✅" if f["status"] == "done" else "📋"
        desc = (f["description"] or "").replace("|", "/").replace("\n", " ").strip()
        rows.append(f"| {f['id']} | {f['name']} | {desc} | {f['priority']} | {icon} {f['status']} |")
    rows.append("")
    block = "\n".join(rows)

    if "## Features" in existing:
        existing = re.sub(r'\n## Features\b[\s\S]*?(?=\n## |\Z)', block, existing)
    else:
        existing = existing.rstrip("\n") + "\n" + block

    prd_path.write_text(existing, encoding="utf-8")


class FeatureCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    priority: str = "medium"
    acceptance_criteria: Optional[str] = ""
    # Workflow (trong danh sách của chính project này) mà task sẽ chạy theo.
    workflow_id: Optional[int] = None
    # Agent dev làm feature này (be1/fe1/fs1...). Node workflow chọn "agent của
    # feature" sẽ chạy bằng agent này.
    agent_key: Optional[str] = None


class FeatureUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    # None ở đây có nghĩa "bỏ chọn workflow", nên phải phân biệt với "không
    # gửi field" — dùng model_fields_set thay vì so sánh None.
    workflow_id: Optional[int] = None
    agent_key: Optional[str] = None


def _validated_agent_key(agent_key: Optional[str], folder: Path) -> Optional[str]:
    """Chỉ nhận agent có trong settings.toml của project; rỗng/lạ → None."""
    key = (agent_key or "").strip()
    if not key:
        return None
    if key not in {a["key"] for a in get_system_agents(folder / "settings.toml")}:
        raise HTTPException(status_code=400, detail=f"Agent '{key}' không có trong project này")
    return key


def _validated_workflow_id(workflow_id: Optional[int], proj_id: int,
                           db: Session) -> Optional[int]:
    """Task chỉ được chọn workflow nằm trong danh sách của CHÍNH project mình.

    Workflow chưa gắn project là mẫu — không chạy được, nên cho task chọn nó chỉ
    dẫn tới lỗi lúc bấm ▶. Muốn dùng mẫu thì nhân bản nó vào project trước
    (POST /api/workflows/{id}/clone)."""
    if not workflow_id:
        return None
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow không tồn tại")
    if wf.project_id is None:
        raise HTTPException(status_code=400,
                            detail="Đây là mẫu (chưa gắn project) — hãy nhân bản mẫu "
                                   "vào project này rồi chọn bản sao")
    if wf.project_id != proj_id:
        raise HTTPException(status_code=400,
                            detail="Workflow này thuộc project khác")
    return wf.id


def _file_out(f: FeatureFile) -> dict:
    return {
        "id": f.id,
        "filename": f.filename,
        "original_filename": f.original_filename,
        "description": f.description or "",
        "size": f.size or 0,
        "content_type": f.content_type or "",
        "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
    }


def _run_out(run: Optional[WorkflowRun]) -> Optional[dict]:
    """Tóm tắt lần chạy workflow gần nhất của 1 task — đủ để vẽ badge tiến độ
    trên danh sách task mà không phải gọi thêm API."""
    if not run:
        return None
    node_status = run.node_status or {}
    return {
        "id": run.id,
        "status": run.status,
        "total_steps": len(node_status),
        "done_steps": sum(1 for v in node_status.values() if v in ("ok", "skipped")),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _latest_runs_by_task(db: Session, task_ids: List[int]) -> dict:
    """{task_id: WorkflowRun mới nhất} — 1 query cho cả danh sách."""
    if not task_ids:
        return {}
    runs = (db.query(WorkflowRun)
              .filter(WorkflowRun.task_id.in_(task_ids))
              .order_by(WorkflowRun.id).all())
    return {r.task_id: r for r in runs}  # id tăng dần → cái cuối là mới nhất


def _feature_out(t: ProjectTask, run: Optional[WorkflowRun] = None) -> dict:
    return {
        "id": t.id, "name": t.name, "description": t.description,
        "status": t.status, "priority": t.priority,
        "acceptance_criteria": t.acceptance_criteria or "",
        "workflow_id": t.workflow_id,
        "workflow_name": t.workflow.name if t.workflow else None,
        "agent_key": t.agent_key,
        "latest_run": _run_out(run),
        "files": [_file_out(f) for f in (t.files or [])],
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _feature_out_one(t: ProjectTask, db: Session) -> dict:
    return _feature_out(t, _latest_runs_by_task(db, [t.id]).get(t.id))


def _all_features(proj_id: int, db: Session) -> list:
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == proj_id)\
               .order_by(ProjectTask.created_at).all()
    latest = _latest_runs_by_task(db, [t.id for t in tasks])
    return [_feature_out(t, latest.get(t.id)) for t in tasks]


@router.get("/{folder_name}/features")
def list_features(folder_name: str, db: Session = Depends(get_db)) -> List[dict]:
    proj = _get_or_create_db_project(folder_name, db)
    return _all_features(proj.id, db)


@router.post("/{folder_name}/features")
def create_feature(folder_name: str, payload: FeatureCreate,
                   db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = ProjectTask(project_id=proj.id, name=payload.name,
                         description=payload.description, priority=payload.priority,
                         acceptance_criteria=payload.acceptance_criteria or None,
                         workflow_id=_validated_workflow_id(payload.workflow_id, proj.id, db),
                         agent_key=_validated_agent_key(payload.agent_key, folder))
    db.add(task)
    db.commit()
    db.refresh(task)
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return _feature_out_one(task, db)


@router.put("/{folder_name}/features/{task_id}")
def update_feature(folder_name: str, task_id: int, payload: FeatureUpdate,
                   db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")
    if payload.name        is not None: task.name        = payload.name
    if payload.description is not None: task.description = payload.description
    if payload.status      is not None: task.status      = payload.status
    if payload.priority    is not None: task.priority    = payload.priority
    if payload.acceptance_criteria is not None:
        task.acceptance_criteria = payload.acceptance_criteria or None
    if "workflow_id" in payload.model_fields_set:
        task.workflow_id = _validated_workflow_id(payload.workflow_id, proj.id, db)
    if "agent_key" in payload.model_fields_set:
        task.agent_key = _validated_agent_key(payload.agent_key, folder)
    db.commit()
    db.refresh(task)
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return _feature_out_one(task, db)


@router.delete("/{folder_name}/features/{task_id}")
def delete_feature(folder_name: str, task_id: int, db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")
    feature_dir = _feature_files_dir(folder, task_id)
    if feature_dir.exists():
        shutil.rmtree(feature_dir, ignore_errors=True)
    db.delete(task)
    db.commit()
    _sync_features_to_prd(folder, _all_features(proj.id, db))
    return {"ok": True}


# ── Feature file attachments ──────────────────────────────────────────────────

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB per file


def _feature_files_dir(folder: Path, task_id: int) -> Path:
    return folder / "feature_files" / str(task_id)


def _safe_filename(name: str) -> str:
    """Strip path components and keep a reasonable, filesystem-safe name."""
    base = Path(name).name  # drop any directory part
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-") or "file"
    return base[:120]


@router.post("/{folder_name}/features/{task_id}/files")
async def upload_feature_file(
    folder_name: str,
    task_id: int,
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
) -> dict:
    folder = CLIENTS_DIR / folder_name
    proj   = _get_or_create_db_project(folder_name, db)
    task   = db.query(ProjectTask).filter(ProjectTask.id == task_id,
                                           ProjectTask.project_id == proj.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Feature not found")

    feature_dir = _feature_files_dir(folder, task_id)
    feature_dir.mkdir(parents=True, exist_ok=True)

    safe_name   = _safe_filename(file.filename or "file")
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    target      = feature_dir / stored_name

    total = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_FILE_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File quá lớn (giới hạn {_MAX_FILE_BYTES // (1024*1024)} MB)")
            out.write(chunk)

    row = FeatureFile(
        task_id=task_id,
        filename=stored_name,
        original_filename=file.filename or safe_name,
        description=description.strip() or None,
        size=total,
        content_type=file.content_type or "",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _file_out(row)


@router.get("/{folder_name}/features/{task_id}/files/{file_id}/download")
def download_feature_file(folder_name: str, task_id: int, file_id: int,
                          db: Session = Depends(get_db)):
    folder = CLIENTS_DIR / folder_name
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    path = _feature_files_dir(folder, task_id) / row.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=row.original_filename,
                        media_type=row.content_type or "application/octet-stream")


class FeatureFileUpdate(BaseModel):
    description: Optional[str] = None


@router.put("/{folder_name}/features/{task_id}/files/{file_id}")
def update_feature_file(folder_name: str, task_id: int, file_id: int,
                        payload: FeatureFileUpdate,
                        db: Session = Depends(get_db)) -> dict:
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if payload.description is not None:
        row.description = payload.description.strip() or None
    db.commit()
    db.refresh(row)
    return _file_out(row)


@router.delete("/{folder_name}/features/{task_id}/files/{file_id}")
def delete_feature_file(folder_name: str, task_id: int, file_id: int,
                        db: Session = Depends(get_db)) -> dict:
    folder = CLIENTS_DIR / folder_name
    row = db.query(FeatureFile).filter(FeatureFile.id == file_id,
                                       FeatureFile.task_id == task_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    path = _feature_files_dir(folder, task_id) / row.filename
    if path.exists():
        path.unlink(missing_ok=True)
    db.delete(row)
    db.commit()
    return {"ok": True}


# ── Docs (output files) ───────────────────────────────────────────────────────

def _scan_dir(base: Path, source: str) -> List[dict]:
    if not base.exists():
        return []
    files = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(base).parts
        if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts[:-1]):
            continue
        if f.suffix.lower() in _SKIP_EXTS:
            continue
        files.append({
            "path":     str(f.relative_to(base)).replace("\\", "/"),
            "name":     f.name,
            "size":     f.stat().st_size,
            "modified": f.stat().st_mtime,
            "source":   source,
        })
    return files


# ── Tài liệu khách hàng cung cấp ──────────────────────────────────────────────
# clients/<slug>/docs/ — API design, đặc tả, sơ đồ, file Excel… thứ KHÁCH ĐƯA VÀO.
#
# Cố ý tách khỏi tab Docs sẵn có: tab đó đọc thư mục CODE, nơi agent tự sinh
# api_contract.md và bạn bè. Trộn hai thứ vào một chỗ là sớm muộn agent ghi đè
# mất tài liệu gốc của khách — thứ duy nhất không tạo lại được.
#
# Chỉ lưu trên đĩa, không có bảng DB: nhờ vậy khách gửi cả thư mục thì bạn chép
# thẳng vào `clients/<slug>/docs/` bằng Explorer là dashboard thấy ngay, không
# phải upload từng file. Danh sách quét đệ quy nên thư mục con vẫn hiện.

def _client_docs_setting(folder: Path) -> str:
    """Giá trị thô người dùng khai. Rỗng = mặc định clients/<slug>/docs."""
    raw = _read_toml(folder).get("output", {}) or {}
    return str(raw.get("client_docs_directory") or "").strip()


def _project_docs_dir(folder: Path) -> tuple[str, Optional[Path]]:
    """(đường dẫn để HIỂN THỊ, đường dẫn THẬT đọc được từ container hoặc None).

    Tài liệu khách thường rất nặng nên để ngoài clients/ là đúng — nhưng dashboard
    chạy trong Docker, chỉ nhìn thấy các mount (clients/, output/, config/,
    skills/, workflow_tasks/). Đường dẫn tuyệt đối kiểu D:/tai-lieu nằm ngoài đó:
    agent trên máy thật đọc tốt, dashboard thì mù.

    Trả None cho vế sau thay vì lặng lẽ rơi về thư mục khác — hiện danh sách rỗng
    mà không nói lý do là kiểu hỏng khó chịu nhất."""
    raw = _client_docs_setting(folder)
    if not raw:
        return f"clients/{folder.name}/docs", folder / "docs"
    norm = raw.replace(chr(92), "/").rstrip("/")
    if _is_abs_path(norm):
        return norm, None                      # ngoài container — không đọc được
    return f"clients/{folder.name}/{norm.lstrip('./')}", (folder / norm).resolve()


def _safe_rel(base: Path, rel: str) -> Path:
    """Chặn '../' thoát ra ngoài thư mục tài liệu."""
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="Đường dẫn không hợp lệ")
    return target


@router.get("/{folder_name}/project-docs")
def list_project_docs(folder_name: str) -> dict:
    """Tài liệu khách cung cấp của 1 dự án."""
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    shown, real = _project_docs_dir(folder)
    return {
        # Đường dẫn để bạn tự chép file vào bằng Explorer thay vì upload từng cái
        "dir":      shown,
        "readable": real is not None,
        "exists":   bool(real and real.is_dir()),
        "files":    _scan_dir(real, "project-docs") if real else [],
    }


@router.post("/{folder_name}/project-docs")
async def upload_project_doc(folder_name: str, file: UploadFile = File(...),
                             subdir: str = Form("")) -> dict:
    folder = CLIENTS_DIR / folder_name
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    _, docs = _project_docs_dir(folder)
    if docs is None:
        raise HTTPException(status_code=400, detail=(
            "Thư mục tài liệu nằm ngoài container nên dashboard không ghi vào được. "
            "Chép file bằng Explorer, hoặc đổi sang đường dẫn tương đối trong repo."))
    # subdir cho phép gom theo nhóm ("api", "thiet-ke"), nhưng vẫn phải nằm trong docs/
    target_dir = _safe_rel(docs, subdir.strip().strip("/")) if subdir.strip() else docs
    target_dir.mkdir(parents=True, exist_ok=True)

    name = _safe_filename(file.filename or "file")
    target = target_dir / name
    # Trùng tên thì thêm hậu tố thay vì ghi đè — tài liệu khách không được phép mất
    if target.exists():
        stem, suf = Path(name).stem, Path(name).suffix
        target = target_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suf}"

    total = 0
    with open(target, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_FILE_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413,
                                    detail=f"File quá lớn (giới hạn {_MAX_FILE_BYTES // (1024*1024)} MB)")
            out.write(chunk)
    return {"path": str(target.relative_to(docs)).replace("\\", "/"),
            "name": target.name, "size": total}


@router.get("/{folder_name}/project-docs/content")
def get_project_doc(folder_name: str, path: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    _, docs = _project_docs_dir(folder)
    if docs is None:
        raise HTTPException(status_code=400, detail="Thư mục tài liệu nằm ngoài container — dashboard không đọc được")
    target = _safe_rel(docs, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Không có file này")
    try:
        return {"path": path, "content": target.read_text(encoding="utf-8"), "text": True}
    except (UnicodeDecodeError, OSError):
        # Ảnh, PDF, Excel… xem không được thì tải về
        return {"path": path, "content": "", "text": False}


@router.get("/{folder_name}/project-docs/download")
def download_project_doc(folder_name: str, path: str):
    folder = CLIENTS_DIR / folder_name
    _, docs = _project_docs_dir(folder)
    if docs is None:
        raise HTTPException(status_code=400, detail="Thư mục tài liệu nằm ngoài container — dashboard không đọc được")
    target = _safe_rel(docs, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Không có file này")
    return FileResponse(str(target), filename=target.name)


@router.delete("/{folder_name}/project-docs")
def delete_project_doc(folder_name: str, path: str) -> dict:
    folder = CLIENTS_DIR / folder_name
    _, docs = _project_docs_dir(folder)
    if docs is None:
        raise HTTPException(status_code=400, detail="Thư mục tài liệu nằm ngoài container — dashboard không đọc được")
    target = _safe_rel(docs, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Không có file này")
    target.unlink()
    return {"ok": True}


@router.get("/{folder_name}/docs")
def list_docs(folder_name: str) -> List[dict]:
    folder   = CLIENTS_DIR / folder_name
    code_dir = _resolve_output_dir(folder)
    docs_dir = _resolve_docs_dir(folder)

    # Nếu docs_dir trùng với code_dir/docs thì chỉ scan code_dir (backward compat)
    if docs_dir == code_dir / "docs" and not docs_dir.exists():
        return _scan_dir(code_dir, "code")

    return _scan_dir(docs_dir, "docs") + _scan_dir(code_dir, "code")


@router.get("/{folder_name}/docs/content")
def get_doc_content(folder_name: str, path: str = "", source: str = "code") -> dict:
    folder   = CLIENTS_DIR / folder_name
    base_dir = _resolve_docs_dir(folder) if source == "docs" else _resolve_output_dir(folder)
    target   = (base_dir / path).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        content = target.read_text(encoding="utf-8")
    except Exception:
        content = f"[Binary file: {target.name}]"
    return {"path": path, "content": content}
