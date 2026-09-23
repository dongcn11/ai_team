"""MCP theo từng dự án: _McpConfig đọc clients/<slug>/mcp.json.

Bám đúng acceptance criteria của Story 1.2 trong
_bmad-output/planning-artifacts/epics-mcp-per-project.md.

Chạy:  python -m pytest tests/test_worker_mcp.py -q
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import worker  # noqa: E402


_WRITE_N = [0]


def _write(path: Path, body) -> None:
    """Ghi mcp.json. mtime độ phân giải có thể là 1s nên ép mốc tăng dần, giống
    cách test_worker_accounts.py làm — không thì _McpConfig tưởng file chưa đổi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    _WRITE_N[0] += 1
    st = path.stat()
    os.utime(path, (st.st_atime, 1_700_000_000 + 10 * _WRITE_N[0]))


@pytest.fixture
def cfg(tmp_path):
    """_McpConfig trỏ vào một gốc repo giả."""
    return worker._McpConfig(tmp_path), tmp_path


def _path(root: Path, slug: str) -> Path:
    return root / "clients" / slug / "mcp.json"


GDRIVE = {
    "enabled": True,
    "servers": {
        "gdrive": {
            "template": "google-workspace",
            "enabled": True,
            "profile": "read-create",
            "declared_write_scope": {"shared_drive_id": "0ABC"},
        }
    },
}


# ── AC: server đang bật thì trả về ───────────────────────────────────────────

def test_server_dang_bat_thi_tra_ve(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    servers = c.servers("udom")
    assert [s.name for s in servers] == ["gdrive"]
    s = servers[0]
    assert s.template == "google-workspace"
    assert s.profile == "read-create"
    assert s.declared_write_scope == {"shared_drive_id": "0ABC"}


# ── AC: công tắc cấp dự án (FR34) ────────────────────────────────────────────

def test_enabled_goc_false_thi_tat_het(cfg):
    c, root = cfg
    body = dict(GDRIVE, enabled=False)
    _write(_path(root, "udom"), body)
    assert c.servers("udom") == []


def test_thieu_enabled_goc_thi_coi_nhu_bat(cfg):
    """Không khai `enabled` ở gốc = bật. Bắt người ta khai thừa một dòng chỉ để
    dùng được là thiết kế tồi."""
    c, root = cfg
    body = {"servers": GDRIVE["servers"]}
    _write(_path(root, "udom"), body)
    assert [s.name for s in c.servers("udom")] == ["gdrive"]


# ── AC: không có gì thì im lặng trả rỗng ─────────────────────────────────────

def test_khong_co_file_thi_rong(cfg):
    c, _ = cfg
    assert c.servers("chua-khai") == []


def test_slug_none_thi_rong(cfg):
    c, _ = cfg
    assert c.servers(None) == []


def test_khong_server_nao_bat_thi_rong(cfg):
    c, root = cfg
    body = {"enabled": True, "servers": {"gdrive": dict(GDRIVE["servers"]["gdrive"], enabled=False)}}
    _write(_path(root, "udom"), body)
    assert c.servers("udom") == []


def test_servers_rong_thi_rong(cfg):
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {}})
    assert c.servers("udom") == []


# ── AC: file hỏng thì GIỮ cấu hình cũ, worker không chết ─────────────────────

def test_json_hong_thi_giu_cau_hinh_cu(cfg, capsys):
    c, root = cfg
    p = _path(root, "udom")
    _write(p, GDRIVE)
    assert len(c.servers("udom")) == 1

    _write(p, "{ day khong phai json hop le")
    servers = c.servers("udom")
    assert [s.name for s in servers] == ["gdrive"], "phải giữ cấu hình cũ, không rơi về rỗng"
    assert "lỗi cú pháp" in capsys.readouterr().out


def test_json_hong_ngay_tu_dau_thi_rong_khong_nem(cfg):
    c, root = cfg
    _write(_path(root, "udom"), "{{{")
    assert c.servers("udom") == []


def test_canh_bao_chi_in_mot_lan(cfg, capsys):
    """Dấu (mtime, size) ghi TRƯỚC khi parse — file hỏng không được spam terminal
    mỗi 3 giây theo vòng poll."""
    c, root = cfg
    _write(_path(root, "udom"), "{{{")
    c.servers("udom")
    capsys.readouterr()
    for _ in range(5):
        c.servers("udom")
    assert capsys.readouterr().out == ""


def test_goc_khong_phai_object_thi_giu_cu(cfg):
    c, root = cfg
    p = _path(root, "udom")
    _write(p, GDRIVE)
    c.servers("udom")
    _write(p, "[1, 2, 3]")
    assert [s.name for s in c.servers("udom")] == ["gdrive"]


# ── AC: nạp lại theo mtime, không cần restart ────────────────────────────────

def test_sua_file_thi_nap_lai_khong_can_restart(cfg):
    c, root = cfg
    p = _path(root, "udom")
    _write(p, GDRIVE)
    assert [s.name for s in c.servers("udom")] == ["gdrive"]

    body = {"enabled": True, "servers": {
        "gdrive": GDRIVE["servers"]["gdrive"],
        "jira":   {"template": "jira", "enabled": True, "profile": "read-only"},
    }}
    _write(p, body)
    assert sorted(s.name for s in c.servers("udom")) == ["gdrive", "jira"]


def test_xoa_file_thi_quay_ve_rong(cfg):
    c, root = cfg
    p = _path(root, "udom")
    _write(p, GDRIVE)
    c.servers("udom")
    p.unlink()
    assert c.servers("udom") == []


# ── AC: cô lập giữa các dự án ────────────────────────────────────────────────

def test_hai_du_an_khong_thay_cua_nhau(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    _write(_path(root, "ieltskey"), {"enabled": True, "servers": {
        "jira": {"template": "jira", "enabled": True, "profile": "read-only"}}})
    assert [s.name for s in c.servers("udom")] == ["gdrive"]
    assert [s.name for s in c.servers("ieltskey")] == ["jira"]


# ── Khai báo sai thì bỏ qua server đó, không làm hỏng cả file ────────────────

def test_ten_server_sai_ky_tu_thi_bo_qua(cfg, capsys):
    """Tên server thành tên tool mcp__<server>__<tool>; ký tự lạ hỏng lặng lẽ."""
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "G Drive!": {"template": "google-workspace", "enabled": True},
        "ok-1":     {"template": "google-workspace", "enabled": True},
    }})
    assert [s.name for s in c.servers("udom")] == ["ok-1"]
    assert "G Drive!" in capsys.readouterr().out


def test_thieu_template_thi_bo_qua(cfg, capsys):
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "a": {"enabled": True},
        "b": {"template": "jira", "enabled": True},
    }})
    assert [s.name for s in c.servers("udom")] == ["b"]
    assert "thiếu `template`" in capsys.readouterr().out


def test_profile_mac_dinh_la_read_only(cfg):
    """Quên khai hồ sơ quyền thì phải rơi về cái ÍT quyền nhất, không phải ngược lại."""
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "a": {"template": "google-workspace", "enabled": True}}})
    assert c.servers("udom")[0].profile == "read-only"


def test_write_scope_sai_kieu_thi_thanh_rong(cfg):
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "a": {"template": "x", "enabled": True, "declared_write_scope": "0ABC"}}})
    assert c.servers("udom")[0].declared_write_scope == {}


def test_server_khong_phai_object_thi_bo_qua(cfg):
    c, root = cfg
    _write(_path(root, "udom"), {"enabled": True, "servers": {"a": "google-workspace"}})
    assert c.servers("udom") == []


# ── NFR11: không làm chậm vòng poll claim 3 giây ─────────────────────────────

def test_doc_lai_duoi_50ms(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    c.servers("udom")                      # nạp lần đầu
    t0 = time.perf_counter()
    for _ in range(100):
        c.servers("udom")                  # 100 lần = 100 vòng poll
    elapsed_ms = (time.perf_counter() - t0) * 1000 / 100
    assert elapsed_ms < 50, f"{elapsed_ms:.2f}ms mỗi lần kiểm tra"


# ═══ Story 1.3: credential theo từng dự án, bơm vào env ═════════════════════

def _toml(root: Path, slug: str, body: str, name: str = "settings.local.toml") -> None:
    p = root / "clients" / slug / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _keyfile(tmp_path: Path, name: str = "sa.json") -> Path:
    f = tmp_path / name
    f.write_text('{"type": "service_account"}', encoding="utf-8")
    return f


def test_doc_duoc_duong_dan_credential(cfg, tmp_path):
    c, root = cfg
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')

    paths, problems = c.secrets("udom", c.servers("udom"))
    assert problems == []
    assert paths == {"gdrive": key.as_posix()}


def test_thieu_muc_mcp_thi_bao_ro_file_va_khoa(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    _, problems = c.secrets("udom", c.servers("udom"))
    assert len(problems) == 1
    msg = problems[0]
    assert "[mcp.gdrive]" in msg and "settings.local.toml" in msg, "lỗi phải nêu đủ file + khoá"


def test_thieu_credentials_path_thi_bao_ro(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", '[mcp.gdrive]\nnote = "quen khai duong dan"\n')
    _, problems = c.secrets("udom", c.servers("udom"))
    assert "credentials_path" in problems[0]


def test_file_credential_khong_ton_tai_thi_bao_ro(cfg):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", '[mcp.gdrive]\ncredentials_path = "C:/khong/co/that.json"\n')
    paths, problems = c.secrets("udom", c.servers("udom"))
    assert paths == {}
    assert "Không thấy file credential" in problems[0]


def test_settings_local_thang_settings_toml(cfg, tmp_path):
    c, root = cfg
    dung = _keyfile(tmp_path, "dung.json")
    sai  = _keyfile(tmp_path, "sai.json")
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{sai.as_posix()}"\n', "settings.toml")
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{dung.as_posix()}"\n')
    paths, _ = c.secrets("udom", c.servers("udom"))
    assert paths["gdrive"] == dung.as_posix()


def test_hai_du_an_hai_credential_khac_nhau(cfg, tmp_path):
    """FR13 — hai khách dùng cùng loại server nhưng không dùng chung credential."""
    c, root = cfg
    k1, k2 = _keyfile(tmp_path, "udom.json"), _keyfile(tmp_path, "ielts.json")
    for slug, key in (("udom", k1), ("ieltskey", k2)):
        _write(_path(root, slug), GDRIVE)
        _toml(root, slug, f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    p1, _ = c.secrets("udom", c.servers("udom"))
    p2, _ = c.secrets("ieltskey", c.servers("ieltskey"))
    assert p1["gdrive"] != p2["gdrive"]


def test_toml_hong_khong_lam_chet(cfg, capsys):
    c, root = cfg
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", "[mcp.gdrive\nkhong dong ngoac")
    _, problems = c.secrets("udom", c.servers("udom"))
    assert problems, "TOML hỏng thì coi như thiếu credential, không được ném"
    assert "Không đọc được [mcp]" in capsys.readouterr().out


def test_mcp_json_khong_chua_bi_mat(cfg, tmp_path):
    """mcp.json là file dashboard sửa được và có thể commit — không được chứa gì."""
    c, root = cfg
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    c.secrets("udom", c.servers("udom"))
    assert key.as_posix() not in _path(root, "udom").read_text(encoding="utf-8")


def test_redact_che_duong_dan_credential(cfg, tmp_path, monkeypatch):
    """AR13 — che qua đúng một điểm là _redact, không thêm điểm thứ hai."""
    c, root = cfg
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), GDRIVE)
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    c.secrets("udom", c.servers("udom"))

    monkeypatch.setattr(worker, "MCP", c)
    out = worker._redact(f"agent lo in ra: {key.as_posix()} roi day")
    assert key.as_posix() not in out
    assert "***" in out


# ═══ Story 1.4 + 1.5: mẫu, hồ sơ quyền, và dựng lệnh ════════════════════════
# Dùng mẫu `filesystem` thật trong config/mcp_templates.toml — nó không cần
# credential nên test chạy được mà không phải giả lập gì.

FS = {"enabled": True, "servers": {
    "fs": {"template": "filesystem", "enabled": True, "profile": "read-only",
           "declared_write_scope": {"paths": ["C:/tmp/x"]}}}}


@pytest.fixture
def plan(cfg, monkeypatch):
    """_mcp_plan chạy trên gốc repo giả, nhưng dùng danh sách mẫu THẬT."""
    c, root = cfg
    monkeypatch.setattr(worker, "MCP", c)
    return c, root


def test_khong_khai_gi_thi_lenh_khong_doi(plan):
    """Cổng duy nhất: dự án không khai MCP thì không thêm một tham số nào."""
    _, _ = plan
    assert worker._mcp_plan("chua-khai") == ([], {}, [])
    assert worker._mcp_plan(None) == ([], {}, [])


def test_dung_lenh_day_du(plan):
    _, root = plan
    _write(_path(root, "udom"), FS)
    cmd, env, problems = worker._mcp_plan("udom")
    assert problems == []
    assert "--strict-mcp-config" in cmd, "phải cắt connector mức tài khoản"
    assert "--mcp-config" in cmd and "--allowedTools" in cmd

    native = json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert list(native["mcpServers"]) == ["fs"]
    assert native["mcpServers"]["fs"]["command"] == "node"


def test_bo_tool_khong_phu_thuoc_tai_khoan_claude(plan, monkeypatch):
    """Story 1.6 — chứng minh CẤU TRÚC thay vì thực nghiệm: máy này chỉ có một
    phiên đăng nhập nên không chạy thử hai tài khoản được. Nhưng _mcp_plan không
    đọc ACCOUNTS và không đọc env token, nên kết quả không thể phụ thuộc tài khoản.
    Test này sẽ vỡ ngay nếu ai đó nối hai thứ đó vào nhau."""
    _, root = plan
    _write(_path(root, "udom"), FS)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tai-khoan-mot")
    a = worker._mcp_plan("udom")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tai-khoan-hai")
    b = worker._mcp_plan("udom")
    assert a == b


def test_khong_mau_nao_dung_npx_y():
    """Rào chuỗi cung ứng, kiểm bằng chính file mẫu thật đang dùng."""
    for name in worker.MCP_TEMPLATES.names():
        tpl = worker.MCP_TEMPLATES.get(name)
        assert tpl.get("command") != "npx", f"mẫu '{name}' dùng npx"
        assert not any(str(a) in ("-y", "--yes") for a in (tpl.get("args") or [])), \
            f"mẫu '{name}' có cờ -y"


def test_npx_y_bi_tu_choi_luc_chay(plan, monkeypatch):
    """Cưỡng chế bằng mã, không chỉ bằng lời dặn trong comment."""
    _, root = plan
    _write(_path(root, "udom"), FS)
    monkeypatch.setattr(worker.MCP_TEMPLATES, "get",
                        lambda n: {"command": "npx", "args": ["-y", "pkg"],
                                   "profiles": {"read-only": ["x"]}})
    cmd, _, problems = worker._mcp_plan("udom")
    assert cmd == []
    assert "npx -y" in problems[0]


def test_allowed_tools_dung_ho_so(plan):
    _, root = plan
    _write(_path(root, "udom"), FS)
    cmd, _, _ = worker._mcp_plan("udom")
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert "mcp__fs__read_text_file" in allowed
    assert "mcp__fs__write_file" not in allowed, "read-only không được có tool ghi"
    assert all(a.startswith("mcp__fs__") for a in allowed)


def test_doi_ho_so_thi_doi_danh_sach_tool(plan):
    """Đây là cách FR21 được cưỡng chế — đã kiểm chứng CLI chặn thật ở mức tool."""
    _, root = plan
    body = {"enabled": True, "servers": {
        "fs": {"template": "filesystem", "enabled": True, "profile": "read-create"}}}
    _write(_path(root, "udom"), body)
    cmd, _, _ = worker._mcp_plan("udom")
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    assert "mcp__fs__write_file" in allowed
    assert "mcp__fs__move_file" not in allowed, "read-create không được có tool sửa"


def test_args_from_scope_noi_duong_dan(plan):
    _, root = plan
    _write(_path(root, "udom"), FS)
    cmd, _, _ = worker._mcp_plan("udom")
    native = json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert native["mcpServers"]["fs"]["args"][-1] == "C:/tmp/x"


def test_template_la_dang_thi_bao_ro_mau_hop_le(plan):
    _, root = plan
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "x": {"template": "khong-co-mau-nay", "enabled": True}}})
    cmd, _, problems = worker._mcp_plan("udom")
    assert cmd == []
    assert "khong-co-mau-nay" in problems[0]
    assert "filesystem" in problems[0], "lỗi phải liệt kê mẫu hợp lệ"


def test_ho_so_la_dang_thi_bao_ro_ho_so_hop_le(plan):
    _, root = plan
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "fs": {"template": "filesystem", "enabled": True, "profile": "toan-quyen"}}})
    cmd, _, problems = worker._mcp_plan("udom")
    assert cmd == []
    assert "toan-quyen" in problems[0] and "read-only" in problems[0]


def test_google_chua_co_ho_so_read_write(plan):
    """Sửa/xoá tài liệu khách bị hoãn sang Phase 2 — khai bừa là mở đường sớm."""
    _, root = plan
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "gdrive": {"template": "google-workspace", "enabled": True, "profile": "read-write"}}})
    cmd, _, problems = worker._mcp_plan("udom")
    assert cmd == []
    assert "read-write" in problems[0]


def test_co_loi_thi_khong_tra_lenh_nao(plan, tmp_path):
    """Fail đóng: một server hỏng thì cả bước dừng, không chạy nửa vời."""
    _, root = plan
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "fs":     {"template": "filesystem", "enabled": True, "profile": "read-only"},
        "gdrive": {"template": "google-workspace", "enabled": True, "profile": "read-only"},
    }})
    # gdrive thiếu credential → phải chặn cả fs, không chạy một nửa
    cmd, env, problems = worker._mcp_plan("udom")
    assert cmd == [] and env == {}
    assert problems


def test_credential_vao_env_dung_ten_bien(plan, tmp_path):
    _, root = plan
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "gdrive": {"template": "google-workspace", "enabled": True, "profile": "read-only"}}})
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    cmd, env, problems = worker._mcp_plan("udom")
    assert problems == []
    assert env == {"GOOGLE_SERVICE_ACCOUNT_KEY_PATH": key.as_posix()}
    assert "GOOGLE_IMPERSONATE_USER" not in env, "đó là đường DWD mà kiến trúc đã loại"


def test_duong_dan_js_thanh_tuyet_doi(plan, tmp_path):
    _, root = plan
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "gdrive": {"template": "google-workspace", "enabled": True, "profile": "read-only"}}})
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    cmd, _, _ = worker._mcp_plan("udom")
    native = json.loads(cmd[cmd.index("--mcp-config") + 1])
    arg = native["mcpServers"]["gdrive"]["args"][0]
    assert Path(arg).is_absolute(), "cwd của tiến trình con không nên quyết định được đường dẫn"


def test_json_config_khong_chua_credential(plan, tmp_path):
    """Chuỗi inline nằm trên dòng lệnh — ai xem tiến trình cũng thấy."""
    _, root = plan
    key = _keyfile(tmp_path)
    _write(_path(root, "udom"), {"enabled": True, "servers": {
        "gdrive": {"template": "google-workspace", "enabled": True, "profile": "read-only"}}})
    _toml(root, "udom", f'[mcp.gdrive]\ncredentials_path = "{key.as_posix()}"\n')
    cmd, _, _ = worker._mcp_plan("udom")
    assert key.as_posix() not in cmd[cmd.index("--mcp-config") + 1]


# ── FR24 + FR29: log đối chiếu bộ server thực tế ────────────────────────────

def test_log_init_hien_server_va_so_tool():
    ev = {"type": "system", "subtype": "init", "model": "haiku",
          "mcp_servers": [{"name": "gdrive", "status": "connected"}],
          "tools": ["Read", "mcp__gdrive__read-file", "mcp__gdrive__list-files"]}
    lines = worker._summarize_event(ev)
    assert any("🔌 MCP: gdrive" in l and "connected" in l and "2 tool" in l for l in lines)


def test_log_init_hien_server_khong_noi_duoc():
    ev = {"type": "system", "subtype": "init",
          "mcp_servers": [{"name": "gdrive", "status": "failed"}], "tools": []}
    lines = worker._summarize_event(ev)
    assert any("failed" in l for l in lines), "server chết phải hiện, không lặng lẽ chạy tiếp"


def test_log_init_khong_co_mcp_thi_khong_doi():
    ev = {"type": "system", "subtype": "init", "model": "haiku"}
    assert worker._summarize_event(ev) == ["🚀 Claude bắt đầu · model haiku"]


# ═══ Epic 2: hỏng thì biết hỏng ở đâu ═══════════════════════════════════════

def _init_ev(*servers):
    return {"type": "system", "subtype": "init",
            "mcp_servers": [{"name": n, "status": s} for n, s in servers]}


def _tool_use(tool_id, name):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": name}]}}


def _tool_err(tool_id, text):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": True, "content": text}]}}


def test_watch_ghi_nhan_server_tu_init():
    w = worker._StepWatch()
    w.feed(_init_ev(("gdrive", "connected"), ("jira", "failed")))
    assert w.saw_init is True
    assert w.mcp_servers == [("gdrive", "connected"), ("jira", "failed")]


def test_watch_phan_biet_chua_cap_quyen_voi_server_tra_loi():
    w = worker._StepWatch()
    w.feed(_tool_use("t1", "mcp__gdrive__create-file"))
    w.feed(_tool_err("t1", "Claude requested permissions to use mcp__gdrive__create-file, "
                           "but you haven't granted it yet."))
    w.feed(_tool_use("t2", "mcp__gdrive__read-file"))
    w.feed(_tool_err("t2", "Google API error: file not found"))
    assert w.mcp_denied == ["mcp__gdrive__create-file"]
    assert len(w.mcp_errors) == 1 and "read-file" in w.mcp_errors[0]


def test_watch_bo_qua_loi_cua_tool_noi_bo():
    """Lỗi của Bash/Read không phải chuyện của MCP."""
    w = worker._StepWatch()
    w.feed(_tool_use("t1", "Bash"))
    w.feed(_tool_err("t1", "command not found"))
    assert w.mcp_denied == [] and w.mcp_errors == []


# ── Story 2.3: cổng chặn — 401 của MCP không được đổ oan tài khoản Claude ───

def test_401_cua_mcp_khong_lam_hong_tai_khoan_claude():
    """Google thu quyền service account → MCP trả 401 → agent thuật lại trong
    result. Nếu quy thành token Claude hỏng thì tài khoản Pro bị loại oan."""
    w = worker._StepWatch()
    w.feed(_tool_use("t1", "mcp__gdrive__read-file"))
    w.feed(_tool_err("t1", "Google Drive API: status 401 unauthorized"))
    assert w.mcp_auth_error is True
    w.feed({"type": "result", "is_error": True, "subtype": "error",
            "result": "Toi khong doc duoc file: status 401 unauthorized"})
    assert w.auth_failed is False, "tài khoản Claude không được đánh dấu hỏng vì lỗi của Google"


def test_401_that_cua_claude_van_lam_hong_tai_khoan():
    """Không có lỗi MCP nào trước đó → 401 trong result là của chính CLI."""
    w = worker._StepWatch()
    w.feed({"type": "result", "is_error": True, "subtype": "error",
            "result": "authentication_error: invalid oauth token"})
    assert w.auth_failed is True


def test_stderr_truoc_result_van_duoc_tin_du_co_loi_mcp():
    """Token hỏng là chết ngay từ đầu, chưa kịp có result. Quy tắc cũ giữ nguyên."""
    w = worker._StepWatch()
    w.feed(_tool_use("t1", "mcp__gdrive__read-file"))
    w.feed(_tool_err("t1", "status 401 from Google"))
    w.feed_text("authentication_error: token revoked", from_stderr=True)
    assert w.auth_failed is True


def test_het_quota_van_hoat_dong_nhu_cu():
    w = worker._StepWatch()
    w.feed({"type": "rate_limit_event",
            "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour"}})
    assert w.limit_hit is True and w.auth_failed is False


# ── Story 2.2 + 2.4: bốn nguyên nhân, mỗi cái một thông báo ─────────────────

def test_mcp_problem_uu_tien_chua_cap_quyen():
    w = worker._StepWatch()
    w.feed(_init_ev(("gdrive", "connected")))
    w.feed(_tool_use("t1", "mcp__gdrive__create-file"))
    w.feed(_tool_err("t1", "requested permissions ... haven't granted it yet"))
    msg = w.mcp_problem()
    assert "chưa được cấp quyền" in msg
    assert "profile" in msg and "mcp.json" in msg, "phải nêu chỗ sửa"


def test_mcp_problem_server_khong_khoi_dong_duoc():
    w = worker._StepWatch()
    w.feed(_init_ev(("gdrive", "connected"), ("jira", "failed")))
    msg = w.mcp_problem()
    assert "jira" in msg and "gdrive" not in msg
    assert "mcp_templates.toml" in msg


def test_mcp_problem_server_tra_loi():
    w = worker._StepWatch()
    w.feed(_init_ev(("gdrive", "connected")))
    w.feed(_tool_use("t1", "mcp__gdrive__read-file"))
    w.feed(_tool_err("t1", "Google API error: quota exceeded"))
    msg = w.mcp_problem()
    assert "trả lỗi" in msg
    assert "không phải lỗi tài khoản Claude" in msg


def test_mcp_problem_none_khi_mcp_vo_can():
    w = worker._StepWatch()
    w.feed(_init_ev(("gdrive", "connected")))
    assert w.mcp_problem() is None


# ── Story 2.5: CLI quá cũ thì từ chối, không âm thầm bỏ cờ ─────────────────

def test_cli_qua_cu_thi_tu_choi(plan, monkeypatch):
    _, root = plan
    _write(_path(root, "udom"), FS)
    monkeypatch.setattr(worker, "_claude_version", lambda: (2, 0, 9))
    cmd, _, problems = worker._mcp_plan("udom")
    assert cmd == [], "không được chạy tiếp mà bỏ mất cờ MCP"
    assert "2.0.9" in problems[0] and "2.1.273" in problems[0]


def test_khong_doc_duoc_phien_ban_thi_van_chay(plan, monkeypatch):
    """Không đọc được phiên bản không phải lý do chặn — có thể là bản build lạ."""
    _, root = plan
    _write(_path(root, "udom"), FS)
    monkeypatch.setattr(worker, "_claude_version", lambda: None)
    cmd, _, problems = worker._mcp_plan("udom")
    assert problems == [] and cmd


# ═══ Story 4.4: nhật ký từng thao tác ghi ═══════════════════════════════════

def test_ghi_de_lai_dau_vet_kem_dinh_danh():
    line = worker._describe_tool("mcp__gdrive__create-file",
                                 {"name": "bao-cao.md", "parentId": "1AbC", "content": "x" * 900})
    assert line.startswith("📝")
    assert "parentId=1AbC" in line and "name=bao-cao.md" in line
    assert "x" * 900 not in line, "nội dung file không được đổ vào log"


def test_append_sheets_cung_la_ghi():
    line = worker._describe_tool("mcp__gdrive__sheets-append-values",
                                 {"spreadsheetId": "1XYZ", "values": [[1, 2]]})
    assert line.startswith("📝") and "spreadsheetId=1XYZ" in line


def test_tool_doc_khong_bi_danh_dau_ghi():
    for name in ("mcp__gdrive__read-file", "mcp__gdrive__list-files",
                 "mcp__gdrive__search-files", "mcp__gdrive__get-folder-tree"):
        assert not worker._describe_tool(name, {"fileId": "1"}).startswith("📝"), name


def test_tool_noi_bo_khong_bi_anh_huong():
    assert worker._describe_tool("Bash", {"command": "git status"}).startswith("🧰") or \
           "Bash" in worker._describe_tool("Bash", {"command": "git status"})


def test_ghi_khong_co_id_van_co_dau_vet():
    line = worker._describe_tool("mcp__gdrive__create-folder", {"parent": "root"})
    assert line.startswith("📝")


# ── Story 2.1: hạn khởi động riêng, ngắn hơn hạn của cả bước ───────────────

class _FakeProgress:
    def __init__(self):
        self.lines = []

    def add(self, line):
        self.lines.append(line)

    def flush(self):
        pass


def test_server_khong_len_thi_bo_cuoc_som():
    """CLI giả: chạy lâu nhưng không bao giờ phát system/init."""
    w = worker._StepWatch()
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    t0 = time.time()
    with pytest.raises(worker._McpStartTimeout):
        worker._run_streaming(cmd, dict(os.environ), _FakeProgress(), parse_json=True,
                              timeout=1800, watch=w, init_timeout=1)
    assert time.time() - t0 < 10, "phải bỏ cuộc theo hạn riêng, không chờ hết 1800s"


def test_co_init_thi_khong_bo_cuoc():
    """Phát init rồi mới làm việc lâu → hạn riêng bị huỷ, bước chạy bình thường."""
    w = worker._StepWatch()
    code = ('import json,sys,time;'
            'print(json.dumps({"type":"system","subtype":"init","mcp_servers":[]}),flush=True);'
            'time.sleep(2)')
    cmd = [sys.executable, "-c", code]
    rc, _, _, _ = worker._run_streaming(cmd, dict(os.environ), _FakeProgress(), parse_json=True,
                                        timeout=60, watch=w, init_timeout=1)
    assert rc == 0 and w.saw_init is True
