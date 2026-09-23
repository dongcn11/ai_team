"""
Cấu hình MCP theo từng dự án — đọc/ghi `clients/<slug>/mcp.json`
================================================================

Nguồn sự thật là FILE, không phải PostgreSQL. Dashboard ghi xuống file rồi đọc
lại; `git diff` vẫn đọc ra, sửa bằng editor vẫn được — cùng triết lý `skills/`.

RANH GIỚI BÍ MẬT (đây là phần quan trọng nhất của file này):

    clients/<slug>/mcp.json             ← module này đọc VÀ ghi. KHÔNG bí mật.
    clients/<slug>/settings.local.toml  ← module này CHỈ ĐỌC, và chỉ để biết
                                          credential đã được KHAI hay chưa.
                                          Không bao giờ trả giá trị ra API.

VÌ SAO KHÔNG KIỂM TRA FILE CREDENTIAL CÓ TỒN TẠI KHÔNG:
`credentials_path` là đường dẫn trên HOST (vd `C:/secure/udom.json`). API chạy
trong container, không thấy được cây thư mục đó. Nên ở đây chỉ trả lời "đã khai
hay chưa"; còn "có dùng được thật không" thì worker chạy trên host mới biết, và
nó báo qua heartbeat.

KHÔNG import worker.py: hai tiến trình khác nhau, một trong Docker một trên host.
Logic đọc lược đồ bị lặp lại có chủ ý — lược đồ được chốt trong
_bmad-output/planning-artifacts/architecture-mcp-per-project.md.
"""
import json
import os
import re
import tomllib
from pathlib import Path

CLIENTS_DIR   = Path(os.getenv("CLIENTS_DIR", "/clients"))
TEMPLATES_FILE = Path(os.getenv("MCP_TEMPLATES_FILE", "/config/mcp_templates.toml"))

# Giống hệt ràng buộc bên worker: tên server chui vào mcp__<server>__<tool>.
NAME_RE = re.compile(r"^[a-z0-9_-]+$")


class McpError(Exception):
    """Lỗi người dùng sửa được → router đổi thành 400 kèm nguyên văn."""


def writable() -> bool:
    """`clients/` có ghi được không. Mount :ro thì mọi nút Lưu đều hỏng — UI cần
    biết trước để nói thẳng thay vì để người dùng bấm rồi mới lỗi."""
    return CLIENTS_DIR.is_dir() and os.access(CLIENTS_DIR, os.W_OK)


# ── Danh sách mẫu ────────────────────────────────────────────────────────────

def templates() -> list[dict]:
    """Mẫu server dựng sẵn + hồ sơ quyền của từng mẫu.

    Trả cả `tools` của từng hồ sơ để UI nói được cho người dùng biết hồ sơ này
    cho phép làm gì — không thì "read-create" chỉ là một chữ vô nghĩa."""
    if not TEMPLATES_FILE.exists():
        return []
    try:
        with open(TEMPLATES_FILE, "rb") as fh:
            raw = tomllib.load(fh).get("template") or {}
    except Exception as e:
        raise McpError(f"Không đọc được {TEMPLATES_FILE.name}: {e}")
    out = []
    for name, row in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(row, dict):
            continue
        profiles = row.get("profiles") if isinstance(row.get("profiles"), dict) else {}
        out.append({
            "name":     name,
            "version":  str(row.get("version") or ""),
            "needs_credential": bool(str(row.get("credential_env") or "").strip()),
            "profiles": [{"name": p, "tools": [str(t) for t in (tools or [])]}
                         for p, tools in sorted(profiles.items())],
        })
    return sorted(out, key=lambda t: t["name"])


def _profile_names(template: str) -> list[str]:
    for t in templates():
        if t["name"] == template:
            return [p["name"] for p in t["profiles"]]
    return []


# ── Đọc cấu hình của một dự án ───────────────────────────────────────────────

def _path(slug: str) -> Path:
    if not slug or "/" in slug or "\\" in slug or slug.startswith("."):
        raise McpError(f"Tên dự án không hợp lệ: {slug!r}")
    return CLIENTS_DIR / slug / "mcp.json"


def _declared_credentials(slug: str) -> set[str]:
    """Tên các server đã khai `credentials_path` trong settings.local.toml.

    CHỈ trả về TÊN. Giá trị đường dẫn không bao giờ rời khỏi hàm này."""
    got: set[str] = set()
    for name in ("settings.toml", "settings.local.toml"):
        f = CLIENTS_DIR / slug / name
        if not f.exists():
            continue
        try:
            with open(f, "rb") as fh:
                mcp = tomllib.load(fh).get("mcp") or {}
        except Exception:
            continue          # TOML hỏng là chuyện của worker báo, không phải của UI
        for srv, row in (mcp.items() if isinstance(mcp, dict) else []):
            if isinstance(row, dict) and str(row.get("credentials_path") or "").strip():
                got.add(srv)
    return got


def read(slug: str) -> dict:
    """Cấu hình hiện tại + tình trạng credential (đã khai hay chưa).

    Dự án chưa khai gì → trả khung rỗng, không phải 404: UI cần hiện form trống
    để người dùng thêm server đầu tiên."""
    path = _path(slug)
    creds = _declared_credentials(slug)
    data: dict = {"enabled": True, "servers": {}}
    broken = None
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
            else:
                broken = "gốc file phải là một object JSON"
        except Exception as e:
            broken = str(e)

    servers = data.get("servers") if isinstance(data.get("servers"), dict) else {}
    out = []
    for name, row in servers.items():
        row = row if isinstance(row, dict) else {}
        out.append({
            "name":        name,
            "template":    str(row.get("template") or ""),
            "profile":     str(row.get("profile") or "read-only"),
            "enabled":     row.get("enabled") is not False,
            "declared_write_scope": row.get("declared_write_scope") or {},
            "credential_declared":  name in creds,
        })
    return {
        "slug":     slug,
        "enabled":  data.get("enabled") is not False,
        "servers":  sorted(out, key=lambda s: s["name"]),
        "exists":   path.exists(),
        "writable": writable(),
        # File hỏng cú pháp: nói thẳng cho UI. Worker vẫn đang chạy bằng bản cũ
        # trong bộ nhớ nó, nên đây là cảnh báo chứ không phải mất cấu hình.
        "parse_error": broken,
    }


# ── Ghi ──────────────────────────────────────────────────────────────────────

def write(slug: str, payload: dict) -> dict:
    """Ghi đè `mcp.json`. Validate trước để không bao giờ ghi ra file mà worker
    sẽ từ chối — người dùng phải biết ngay lúc bấm Lưu, không phải lúc chạy bước."""
    if not writable():
        raise McpError("Thư mục clients/ đang chỉ-đọc, không ghi được. Kiểm tra mount "
                       "`../clients:/clients` trong dashboard/docker-compose.yml (không có :ro).")
    path = _path(slug)
    if not path.parent.is_dir():
        raise McpError(f"Không có dự án '{slug}' trong clients/.")

    servers_in = payload.get("servers")
    if not isinstance(servers_in, list):
        raise McpError("`servers` phải là một mảng.")

    known = {t["name"] for t in templates()}
    servers: dict = {}
    for row in servers_in:
        row = row if isinstance(row, dict) else {}
        name = str(row.get("name") or "").strip()
        if not NAME_RE.match(name):
            raise McpError(f"Tên server '{name}' chỉ được dùng a-z, 0-9, _ và - "
                           f"(nó trở thành tên tool mcp__<server>__<tool>).")
        if name in servers:
            raise McpError(f"Server '{name}' khai hai lần.")
        template = str(row.get("template") or "").strip()
        if template not in known:
            raise McpError(f"Template '{template}' không có trong mcp_templates.toml. "
                           f"Mẫu hợp lệ: {', '.join(sorted(known)) or '(trống)'}.")
        profile = str(row.get("profile") or "read-only").strip()
        valid = _profile_names(template)
        if profile not in valid:
            raise McpError(f"Hồ sơ quyền '{profile}' không có ở template '{template}'. "
                           f"Hợp lệ: {', '.join(valid) or '(trống)'}.")
        scope = row.get("declared_write_scope")
        servers[name] = {
            "template": template,
            "enabled":  bool(row.get("enabled", True)),
            "profile":  profile,
            # Tên khoá nói rõ đây là KHAI BÁO, không phải hàng rào. Hàng rào thật
            # nằm ở phạm vi chia sẻ phía Google.
            "declared_write_scope": scope if isinstance(scope, dict) else {},
        }

    body = {"enabled": bool(payload.get("enabled", True)), "servers": servers}
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return read(slug)
