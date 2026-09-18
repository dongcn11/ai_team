"""Kiểm bao đóng hai sổ nợ của một tài liệu 画面仕様.

Thay hai lệnh `grep` trong `SKILL.md` §"Cách kiểm" và `MANUAL.md` B5②. Lệnh cũ:

    grep -oE '^\\| *\\*{0,2}[0-9]+' <file>

gộp số hiệu của **cả hai sổ** thành một danh sách phẳng `1 2 3 … 11`, nên `No.7` của
`確認事項一覧` lẫn với `No.7` của `想定一覧`. Đo trên `LS_01_070_02` ngày 2026-08-13:
lệnh cũ bỏ sót **9 mục mồ côi**, trong đó **4 mục vi phạm** luật `出自 = 方針`.

Kiểm hai luật của §"Bao đóng hai sổ nợ":

1. Số hiệu thân trỏ tới mà sổ không có ⇒ mục bị bỏ quên
2. Mục trong sổ không ai trỏ tới ⇒ phải mang `出自 = 方針`; ghi `観察` là sai

Luật thứ ba — "đếm số lượng KHÔNG chứng minh được gì" — là lý do script này so theo
từng số hiệu chứ không so tổng.

Chạy: `python3 check_closure.py <file.md> [file2.md …]`
Mã thoát 1 nếu có vi phạm — dùng được trong CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_table_parser import parse_spec_tables  # noqa: E402

# Tên sổ ↔ từ khoá dùng trong mũi tên `→ 確認事項 No.N`
_LEDGERS = {
    "確認事項一覧": "確認事項",
    "想定一覧": "想定",
}

# `出自` hợp lệ cho mục KHÔNG có neo trong thân. Ba loại, đều là lý do chính đáng:
#
#   方針        — mục từ hai danh sách chính sách (10 mục được 想定 / 9 mục cấm 想定).
#                 Luôn phải xét dù tài liệu có nói hay không.
#   観察（欠落） — quan sát thấy tài liệu THIẾU thứ gì đó. Không neo được vì ô cần neo
#                 chính là ô không tồn tại. Ví dụ: `金額端数処理区分` được `■アクション`
#                 tham chiếu nhưng `■画面項目` không có (tìm `price_rounding` ra 0 kết quả).
#   観察（文書） — quan sát về CHÍNH tài liệu nguồn, không thuộc ô nội dung nào.
#                 Ví dụ: 項番の信頼性・版数の不整合.
#
# `観察` trơn thì PHẢI có neo — nó khẳng định "quan sát được ở chỗ này", nên phải chỉ ra
# chỗ nào. Không có neo mà ghi `観察` trơn là mục mồ côi thật.
_ORPHAN_OK = ("方針", "観察（欠落）", "観察（文書）")


def _refs(text: str, keyword: str) -> set[int]:
    """Số hiệu mà THÂN tài liệu trỏ tới, theo từng sổ."""
    return {int(m) for m in re.findall(rf"→ *{keyword} *No\.(\d+)", text)}


def _entries(text: str, section: str) -> dict[int, str]:
    """Số hiệu có trong SỔ → giá trị cột `出自`."""
    out: dict[int, str] = {}
    for item in parse_spec_tables(text):
        if item.section != section:
            continue
        digits = re.sub(r"\D", "", item.key)
        if digits:
            out[int(digits)] = item.columns.get("出自", "")
    return out


def check_file(path: Path) -> list[str]:
    """Trả danh sách vi phạm. Rỗng ⇒ đạt."""
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    for section, keyword in _LEDGERS.items():
        refs = _refs(text, keyword)
        entries = _entries(text, section)

        print(f"  {section}")
        print(f"    sổ có   : {sorted(entries) or '(trống)'}")
        print(f"    thân trỏ: {sorted(refs) or '(không có)'}")

        # Luật 1 — thân trỏ tới số không tồn tại trong sổ
        for n in sorted(refs - set(entries)):
            problems.append(f"{path.name}: thân trỏ {keyword} No.{n} nhưng sổ không có")

        # Luật 2 — mục mồ côi phải nêu được lý do trong cột 出自
        for n in sorted(set(entries) - refs):
            src = entries[n] or "(cột 出自 trống)"
            if not any(ok in src for ok in _ORPHAN_OK):
                problems.append(
                    f"{path.name}: {section} No.{n} không ai trỏ tới "
                    f"nhưng 出自={src} — phải là một trong {' / '.join(_ORPHAN_OK)}"
                )
            else:
                print(f"    · No.{n} mồ côi, 出自={src} — hợp lệ")

    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("dùng: python3 check_closure.py <file.md> [file2.md …]", file=sys.stderr)
        return 2

    all_problems: list[str] = []
    for arg in argv[1:]:
        path = Path(arg)
        print(f"{path.name}")
        all_problems.extend(check_file(path))
        print()

    if all_problems:
        print(f"VI PHẠM ({len(all_problems)}):")
        for p in all_problems:
            print(f"  - {p}")
        return 1

    print("bao đóng đạt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
