"""Kiểm bản dịch có lệch với bản gốc không.

Bản dịch nằm ở file riêng (`_v1.vi.md`, `_v1.en.md`) nên có rủi ro: sửa bản gốc rồi
quên dịch lại. Script này bắt bốn kiểu lệch, đều là kiểu làm dev đọc nhầm:

  1. Thiếu bản dịch cho một mục `##` — dev không biết mục đó tồn tại
  2. Số dòng bảng khác nhau — mất hoặc thừa dòng khi dịch
  3. Số hiệu sổ nợ khác nhau — `→ 確認事項 No.7` biến mất hoặc lệch số
  4. Nhãn bị dịch — `✅ 確認済み` thành "Đã xác nhận" ⇒ `spec_table_parser` mù

Kiểu 4 nguy hiểm nhất: bản dịch trông đẹp nhưng mọi công cụ đọc nó đều ra rỗng.

Chạy: python3 check_translation.py <file gốc .md> [file2.md …]
Mã thoát 1 nếu có lệch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Hai loại tài liệu, hai bộ nhãn. Cả hai đều PHẢI giữ nguyên khi dịch.
#
#   spec   — `spec_table_parser` nhận diện theo đúng chuỗi tiếng Nhật này
#   review — mức nghiêm trọng, là khoá phân loại; dịch "Critical" thành "Nghiêm trọng"
#            làm mọi phép lọc/đếm theo mức đều trượt
_LABELS_SPEC = ("確認済み", "不一致", "想定", "要確認")
_LABELS_REVIEW = ("Critical", "Major", "Minor", "Suggestion")


def detect_labels(text: str) -> tuple[str, tuple[str, ...]]:
    """Đoán loại tài liệu theo nhãn nào xuất hiện nhiều hơn.

    Trả `(tên loại, bộ nhãn)`. Không đoán được ⇒ dùng bộ spec, vì đó là loại
    tài liệu chính của gói này.
    """
    n_spec = sum(text.count(lb) for lb in _LABELS_SPEC)
    n_review = sum(text.count(lb) for lb in _LABELS_REVIEW)
    if n_review > n_spec:
        return "review", _LABELS_REVIEW
    return "spec", _LABELS_SPEC

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\|")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_ANCHOR_RE = re.compile(r"→\s*(確認事項|想定)\s*No\.(\d+)")
_FENCE_RE = re.compile(r"^\s*```")

_SUFFIXES = (".vi.md", ".en.md")


def profile(path: Path, label_set: tuple[str, ...] | None = None) -> dict:
    """Rút những thứ PHẢI giống nhau giữa bản gốc và bản dịch.

    `label_set` do bản GỐC quyết định — bản dịch phải soi bằng cùng bộ nhãn,
    không tự đoán lại (nếu tự đoán, bản dịch đã dịch hết nhãn sẽ đoán ra bộ
    khác và script báo "khớp" một cách sai lầm).
    """
    text = path.read_text(encoding="utf-8")
    kind, labels_used = detect_labels(text) if label_set is None else ("", label_set)

    headings: list[str] = []
    n_rows = 0
    anchors: set[str] = set()
    labels: dict[str, int] = {lb: 0 for lb in labels_used}
    in_fence = False

    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        h = _HEADING_RE.match(line)
        if h:
            headings.append(h.group(1))
            continue

        s = line.strip()
        if _TABLE_ROW_RE.match(s) and not _TABLE_SEP_RE.match(s):
            n_rows += 1

        for a_kind, no in _ANCHOR_RE.findall(line):
            anchors.add(f"{a_kind} No.{no}")
        for lb in labels_used:
            labels[lb] += line.count(lb)

    return {
        "kind": kind,
        "label_set": labels_used,
        "headings": headings,
        "rows": n_rows,
        "anchors": anchors,
        "labels": labels,
    }


def compare(src: Path, dst: Path) -> list[str]:
    a = profile(src)                          # bản gốc tự nhận diện loại
    b = profile(dst, label_set=a["label_set"])  # bản dịch soi bằng CÙNG bộ nhãn
    problems: list[str] = []
    tag = dst.name

    # 1. mục `##`
    #
    # Spec: tên mục LÀ khoá — bot nạp spec theo `## 入力項目`, `## 使用API`… nên phải
    #       trùng khít từng chữ.
    # Review report: tên mục chỉ để người đọc, dịch được. Chỉ cần ĐỦ SỐ mục, không
    #       cần trùng tên — nếu không, mọi bản dịch tử tế đều bị báo lệch.
    if a["kind"] == "spec":
        missing = [h for h in a["headings"] if h not in b["headings"]]
        extra = [h for h in b["headings"] if h not in a["headings"]]
        if missing:
            problems.append(f"{tag}: thiếu mục {missing} (tên mục `##` phải giữ nguyên)")
        if extra:
            problems.append(f"{tag}: thừa mục {extra}")
    elif len(a["headings"]) != len(b["headings"]):
        problems.append(
            f"{tag}: số mục `##` lệch — gốc {len(a['headings'])}, "
            f"bản dịch {len(b['headings'])}"
        )

    # 2. số dòng bảng
    if a["rows"] != b["rows"]:
        problems.append(
            f"{tag}: số dòng bảng lệch — gốc {a['rows']}, bản dịch {b['rows']}"
        )

    # 3. số hiệu sổ nợ
    lost = sorted(a["anchors"] - b["anchors"])
    if lost:
        problems.append(f"{tag}: mất neo sổ nợ {lost}")

    # 4. nhãn bị dịch — kiểu lệch nguy hiểm nhất
    for lb in a["label_set"]:
        if a["labels"][lb] and not b["labels"][lb]:
            problems.append(
                f"{tag}: nhãn `{lb}` biến mất ({a['labels'][lb]} lần ở gốc, 0 ở bản dịch) "
                f"— nhãn PHẢI giữ nguyên (loại `{a['kind']}`); dịch là làm công cụ đọc mù"
            )
        elif a["labels"][lb] != b["labels"][lb]:
            problems.append(
                f"{tag}: nhãn `{lb}` lệch số lượng — gốc {a['labels'][lb]}, "
                f"bản dịch {b['labels'][lb]}"
            )

    return problems


def check(src: Path) -> list[str]:
    if src.name.endswith(_SUFFIXES):
        return [f"{src.name}: đây là bản dịch, hãy truyền file GỐC"]

    stem = src.with_suffix("")  # bỏ `.md`
    found = [p for s in _SUFFIXES if (p := Path(f"{stem}{s}")).is_file()]

    print(f"{src.name}")
    if not found:
        print("  (không có bản dịch nào — bỏ qua)")
        return []

    problems: list[str] = []
    for dst in found:
        errs = compare(src, dst)
        print(f"  {dst.name}: {'lệch ' + str(len(errs)) if errs else 'khớp'}")
        problems.extend(errs)
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("dùng: python3 check_translation.py <file gốc .md> …", file=sys.stderr)
        return 2

    all_problems: list[str] = []
    for arg in argv[1:]:
        path = Path(arg)
        if not path.is_file():
            print(f"không thấy file: {path}", file=sys.stderr)
            return 2
        all_problems.extend(check(path))
    print()

    if all_problems:
        print(f"LỆCH ({len(all_problems)}):")
        for p in all_problems:
            print(f"  - {p}")
        return 1

    print("bản dịch khớp bản gốc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
