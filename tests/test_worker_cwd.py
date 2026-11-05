"""cwd của `claude -p` cho 1 bước workflow.

Claude Code chỉ nạp .claude/settings*.json của thư mục cwd. --add-dir không mang
quyền Bash theo, nên chạy từ gốc ai_team thì allow git/php của project bị bỏ qua.
"""
from pathlib import Path

import worker


def test_chon_goc_du_an_khong_chon_vung_con(tmp_path):
    root = tmp_path / "aloweb"
    (root / "backend").mkdir(parents=True)
    (root / "frontend").mkdir()
    dirs = [str(root / "backend"), str(root), str(root / "frontend")]
    assert worker._step_cwd(dirs) == root


def test_khong_co_thu_muc_thi_ve_goc_repo():
    assert worker._step_cwd([]) == worker.ROOT


def test_thu_muc_chua_ton_tai_thi_bo_qua(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    assert worker._step_cwd([str(tmp_path / "chua-tao"), str(real)]) == real
    assert worker._step_cwd([str(tmp_path / "chua-tao")]) == worker.ROOT


def test_hai_thu_muc_roi_nhau_lay_duong_ngan_hon(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "bbbbbb"
    a.mkdir()
    b.mkdir()
    assert worker._step_cwd([str(b), str(a)]) == a


def test_doi_mention_thanh_duong_dan_tuyet_doi():
    rel = "clients/aloweb/_tasks/run-1/step.md"
    prompt = f"@{rel} Thực hiện task trong file này."
    out = worker._retarget_prompt(prompt, rel)
    assert out == f"@{(worker.ROOT / rel).as_posix()} Thực hiện task trong file này."


def test_khong_co_file_thi_giu_nguyen_prompt():
    assert worker._retarget_prompt("@x làm đi", None) == "@x làm đi"
