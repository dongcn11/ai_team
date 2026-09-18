"""Bóc bảng Markdown của 画面仕様 thành mục đặc tả, và đọc ba nhãn ステータス.

Vá hai lỗ đã đo ngày 2026-08-13 trên `mor-pr-review-bot`:

1. `context_types.parse_items` chỉ khớp khuôn `khoá: giá trị` theo dòng nên không
   bóc được bảng — 203 dòng spec ra 9 mục, 2 trong đó là dòng phân cách `|---|`.
2. Bot không biết ba nhãn `✅ 確認済み` / `🔶 想定` / `❓ 要確認`
   (`grep 'ステータス|確認済み|要確認' scripts/*.py` = 0 dòng), nên QĐ9 chưa có hiệu lực:
   không gì chặn một dòng `🔶 想定` bị gán Critical.

Module **không sửa file nào của `mor-pr-review-bot`** — `scripts/context_*.py` thuộc
agent `specctx` và README của repo đó cấm ghi chéo. Xem `BOT_PATCH.md` để biết
hai dòng cần nối.

Chạy độc lập: `python3 spec_table_parser.py <file.md>`
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

# ── Ba nhãn ─────────────────────────────────────────────────────────────────
STATUS_CONFIRMED = "確認済み"
STATUS_ASSUMED = "想定"
STATUS_TOCHECK = "要確認"
STATUS_CONFLICT = "不一致"
STATUS_UNKNOWN = "不明"

# Trần mức nghiêm trọng theo QĐ9: không trích được nguyên văn ⇒ không gán Critical.
SEVERITY_CEILING: dict[str, str] = {
    STATUS_CONFIRMED: "critical",  # được gán tới Critical/Major
    STATUS_CONFLICT: "major",      # hai nguồn đá nhau — có bằng chứng cả hai bên,
                                   # nhưng CHƯA biết bên nào đúng ⇒ không tới Critical
    STATUS_ASSUMED: "minor",       # chỉ nhắc, KHÔNG được FAIL
    STATUS_TOCHECK: "info",        # không phải luật — ghi chú cho người
    STATUS_UNKNOWN: "minor",       # thiếu nhãn ⇒ xử như 想定, không tin hơn
}

_SEVERITY_ORDER = ("info", "minor", "major", "critical")

# Nhãn có thể mang hậu tố phạm vi `✅ 確認済み（遷移先）`, version `✅ 確認済み〔v1.4〕`,
# hoặc in đậm `❓ **要確認**` — tìm theo chuỗi con nên bắt được cả ba dạng.
# Ô nhãn kép `✅ 確認済み（遷移先）／❓ 要確認（パラメータ）` là hợp lệ và phải lấy mức YẾU nhất.
#
# Đã kiểm kê trên 3 mẫu thật (273 ô có nhãn): ba nhãn chuẩn chiếm 260, còn lại là
# `⚠️ 未確認` (đồng nghĩa 要確認) và `🔴 …` (kết quả đối chiếu, không phải nhãn tin cậy).
_STATUS_RE = re.compile(r"(確認済み|未確認|想定|要確認|不一致|🔴)")

# `未確認` là cách viết khác của `要確認`; `🔴` là ký hiệu của `不一致`. Gom về một mức.
_STATUS_ALIAS = {"未確認": STATUS_TOCHECK, "🔴": STATUS_CONFLICT}

# Bảng không có cột `ステータス` nhưng bản thân mục đã nói rõ mức tin cậy.
_SECTION_STATUS = {
    "確認事項一覧": STATUS_TOCHECK,
    "想定一覧": STATUS_ASSUMED,
}

# Bảng chú giải — không phải luật, bỏ khỏi kết quả.
_SKIP_SECTIONS = ("ステータス記号の意味",)

_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_FENCE_RE = re.compile(r"^\s*```")

# Cột mang nhãn. `ステータス` là tên chuẩn trong khung 13 mục.
_STATUS_COL_NAMES = ("ステータス", "状態", "status")


@dataclass(frozen=True)
class TableItem:
    """Một dòng bảng đã bóc.

    `raw` giữ NGUYÊN VĂN dòng Markdown — dùng làm `evidence` của `Finding`, cùng
    quy ước với `SpecItem.raw` của bot.
    """

    section: str
    key: str
    value: str
    raw: str
    status: str
    columns: dict[str, str]

    @property
    def ceiling(self) -> str:
        """Mức nghiêm trọng cao nhất được phép gán cho mục này."""
        return SEVERITY_CEILING.get(self.status, "minor")

    def allows(self, severity: str) -> bool:
        """`severity` có nằm trong trần của mục này không."""
        want = severity.strip().lower()
        if want not in _SEVERITY_ORDER:
            return False
        return _SEVERITY_ORDER.index(want) <= _SEVERITY_ORDER.index(self.ceiling)


def read_status(cell: str) -> str:
    """Đọc nhãn từ một ô. Ô nhãn kép ⇒ lấy mức YẾU nhất (an toàn hơn).

    >>> read_status("✅ 確認済み")
    '確認済み'
    >>> read_status("✅ 確認済み（遷移先）／❓ 要確認（パラメータ）")
    '要確認'
    >>> read_status("—")
    '不明'
    """
    found = [_STATUS_ALIAS.get(x, x) for x in _STATUS_RE.findall(cell or "")]
    if not found:
        return STATUS_UNKNOWN

    # `不一致` thắng tất cả: hai nguồn đá nhau là sự thật đã quan sát được, không phải
    # mức tin cậy. Một ô vừa `✅ 確認済み` vừa `🔴` nghĩa là "設計書 ghi rõ, NHƯNG code
    # nói khác" — phải nổi lên thành câu hỏi, không được chìm xuống thành 確認済み.
    if STATUS_CONFLICT in found:
        return STATUS_CONFLICT

    # Còn lại: yếu nhất thắng — 要確認 < 想定 < 確認済み
    for weakest in (STATUS_TOCHECK, STATUS_ASSUMED, STATUS_CONFIRMED):
        if weakest in found:
            return weakest
    return STATUS_UNKNOWN


def _split_row(line: str) -> list[str]:
    """Tách một dòng bảng Markdown thành các ô, bỏ `|` đầu và cuối."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def parse_spec_tables(text: str) -> list[TableItem]:
    """Bóc mọi bảng Markdown trong `text`, gắn tên mục `##` bao quanh.

    Bỏ qua khối mã. Dòng phân cách `|---|` KHÔNG thành mục (đây chính là lỗi
    `parse_items` mắc phải). Bảng không có dòng tiêu đề thì bỏ qua cả bảng —
    không đoán tên cột.
    """
    items: list[TableItem] = []
    section = ""
    header: list[str] | None = None
    in_fence = False

    for line in (text or "").splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            header = None
            continue
        if in_fence:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(2).strip()
            header = None
            continue

        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue

        if _TABLE_SEP_RE.match(stripped):
            continue  # dòng phân cách — không phải dữ liệu

        cells = _split_row(stripped)
        if header is None:
            header = cells
            continue

        # Dòng lệch số cột: cắt/đệm cho khớp tiêu đề, không bỏ dòng.
        cols = dict(zip(header, cells + [""] * (len(header) - len(cells))))

        if section in _SKIP_SECTIONS:
            continue  # bảng chú giải, không phải luật

        status_cell = ""
        for name in _STATUS_COL_NAMES:
            if name in cols:
                status_cell = cols[name]
                break

        status = read_status(status_cell)
        if status == STATUS_UNKNOWN and section in _SECTION_STATUS:
            # Hai sổ nợ không có cột `ステータス` — mức tin cậy nằm ở chính tên mục.
            status = _SECTION_STATUS[section]

        key = cells[0] if cells else ""
        value = " | ".join(c for c in cells[1:] if c)
        if not key or key in ("-", "—"):
            continue

        items.append(
            TableItem(
                section=section,
                key=key,
                value=value,
                raw=line.rstrip(),
                status=status,
                columns=cols,
            )
        )

    return items


def summarize(items: list[TableItem]) -> dict[str, int]:
    """Đếm mục theo nhãn — dùng để báo cáo và để test."""
    out = {
        STATUS_CONFIRMED: 0,
        STATUS_CONFLICT: 0,
        STATUS_ASSUMED: 0,
        STATUS_TOCHECK: 0,
        STATUS_UNKNOWN: 0,
    }
    for it in items:
        out[it.status] = out.get(it.status, 0) + 1
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("dùng: python3 spec_table_parser.py <file.md>", file=sys.stderr)
        return 2
    text = open(argv[1], encoding="utf-8").read()
    items = parse_spec_tables(text)
    print(f"bóc được {len(items)} mục từ {len(text.splitlines())} dòng")
    for label, n in summarize(items).items():
        print(f"  {label:8} {n}")
    print()
    for it in items[:5]:
        print(f"  [{it.section}] {it.key[:40]:40} {it.status:6} trần={it.ceiling}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
