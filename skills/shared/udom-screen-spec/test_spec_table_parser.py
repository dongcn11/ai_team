"""Test cho `spec_table_parser`. Chạy: `python3 test_spec_table_parser.py`

Không dùng pytest để chạy được ở mọi máy dev không cài thêm gì.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_table_parser import (  # noqa: E402
    STATUS_ASSUMED,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_TOCHECK,
    STATUS_UNKNOWN,
    parse_spec_tables,
    read_status,
    summarize,
)

# …/udom-spec-kit/skills/udom-screen-spec/ → …/udom-spec-kit/samples/
_SAMPLES = Path(__file__).resolve().parents[2] / "samples"
_FAILED: list[str] = []


def check(name: str, got, want) -> None:
    if got == want:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}\n       got : {got!r}\n       want: {want!r}")
        _FAILED.append(name)


# ── read_status ─────────────────────────────────────────────────────────────
def test_read_status() -> None:
    print("read_status")
    check("nhãn thường", read_status("✅ 確認済み"), STATUS_CONFIRMED)
    check("想定", read_status("🔶 想定"), STATUS_ASSUMED)
    check("要確認", read_status("❓ 要確認"), STATUS_TOCHECK)
    check("ô rỗng", read_status(""), STATUS_UNKNOWN)
    check("không có nhãn", read_status("—"), STATUS_UNKNOWN)

    # Biến thể đo được trên mẫu thật
    check("in đậm", read_status("❓ **要確認**"), STATUS_TOCHECK)
    check("kèm version", read_status("✅ 確認済み〔v1.4〕"), STATUS_CONFIRMED)
    check("kèm phạm vi", read_status("✅ 確認済み（IO）"), STATUS_CONFIRMED)
    check("未確認 = 要確認", read_status("⚠️ 未確認 → 確認事項 No.3"), STATUS_TOCHECK)

    # Nhãn kép: mức YẾU nhất thắng — đây là luật an toàn, không phải chi tiết cài đặt
    check(
        "nhãn kép lấy mức yếu",
        read_status("✅ 確認済み（遷移先）／❓ 要確認（パラメータ）"),
        STATUS_TOCHECK,
    )
    check(
        "nhãn kép ✅ + 🔶",
        read_status("✅ 確認済み／🔶 想定"),
        STATUS_ASSUMED,
    )

    # 🔴 不一致 — hai nguồn đá nhau. Thắng MỌI nhãn khác, kể cả ✅:
    # "設計書 ghi rõ, NHƯNG code nói khác" phải nổi lên thành câu hỏi.
    check("🔴 ký hiệu", read_status("🔴 FE が 50"), STATUS_CONFLICT)
    check("不一致 chữ", read_status("🔴 不一致"), STATUS_CONFLICT)
    check("🔴 thắng ✅", read_status("✅ 確認済み／🔴 コード相違"), STATUS_CONFLICT)


# ── trần mức nghiêm trọng (QĐ9) ─────────────────────────────────────────────
def test_ceiling() -> None:
    print("trần mức nghiêm trọng")
    md = """## 入力項目

| 項目 | 備考 | ステータス |
|---|---|---|
| A | - | ✅ 確認済み |
| B | - | 🔶 想定 |
| C | - | ❓ 要確認 |
| D | - | - |
"""
    items = {i.key: i for i in parse_spec_tables(md)}
    check("確認済み → critical", items["A"].ceiling, "critical")
    check("想定 → minor", items["B"].ceiling, "minor")
    check("要確認 → info", items["C"].ceiling, "info")
    check("thiếu nhãn → minor", items["D"].ceiling, "minor")

    # QĐ9: 🔶 想定 KHÔNG được FAIL
    check("想定 chặn critical", items["B"].allows("critical"), False)
    check("想定 chặn major", items["B"].allows("major"), False)
    check("想定 cho minor", items["B"].allows("minor"), True)
    check("確認済み cho critical", items["A"].allows("critical"), True)
    check("要確認 chỉ cho info", items["C"].allows("minor"), False)


# ── bóc bảng ────────────────────────────────────────────────────────────────
def test_table_parsing() -> None:
    print("bóc bảng")
    md = """# Tiêu đề

## 入力項目

| 項目 | 型 | ステータス |
|---|---|---|
| 承認ルート名 | string | ✅ 確認済み |

Một đoạn văn xuôi.

```
| trong khối mã | không được bóc | ✅ 確認済み |
```

## 使用API

| タイミング | API名 | ステータス |
|:---|---:|---|
| 初期表示 | 区分一覧取得API | 🔶 想定 |
"""
    items = parse_spec_tables(md)
    check("số mục", len(items), 2)
    check("bỏ dòng phân cách", [i.key for i in items], ["承認ルート名", "初期表示"])
    check("gắn đúng section", [i.section for i in items], ["入力項目", "使用API"])
    check("bỏ khối mã", any("khối mã" in i.raw for i in items), False)
    check("giữ nguyên văn", items[0].raw.startswith("| 承認ルート名"), True)
    check("phân cách căn lề :---", items[1].key, "初期表示")

    # Bảng không có dòng tiêu đề đứng trước ⇒ dòng đầu LÀ tiêu đề, không thành mục
    check("dòng đầu là tiêu đề", "項目" not in [i.key for i in items], True)


def test_section_fallback() -> None:
    print("suy nhãn theo mục")
    md = """## 確認事項一覧

| No | 確認事項 | 優先度 | 出自 |
|---|---|---|---|
| 1 | API接頭辞をどちらに揃えるか | 高 | 観察 |

## 想定一覧

| No | 項目 | 想定内容 | 根拠 | 出自 |
|---|---|---|---|---|
| 1 | 削除確認 | ダイアログあり | 慣例 | 方針 |

## ステータス記号の意味

| 記号 | 意味 |
|---|---|
| ✅ | 確認済み |
"""
    items = parse_spec_tables(md)
    by_section = {i.section: i for i in items}
    check("確認事項一覧 → 要確認", by_section["確認事項一覧"].status, STATUS_TOCHECK)
    check("想定一覧 → 想定", by_section["想定一覧"].status, STATUS_ASSUMED)
    check("bỏ bảng chú giải", "ステータス記号の意味" in by_section, False)


# ── chạy trên tài liệu thật ─────────────────────────────────────────────────
def test_real_samples() -> None:
    print("mẫu thật")
    files = sorted(_SAMPLES.glob("LS_*.md"))

    # Khi skill được cài lẻ (`~/.claude/skills/udom-screen-spec/`) thì `samples/`
    # không đi kèm — bỏ qua, KHÔNG báo hỏng. Nói rõ là đã bỏ qua, không im lặng.
    if not files:
        print(f"  BỎ QUA — không thấy mẫu ở {_SAMPLES}")
        print("         (chạy từ gốc gói udom-spec-kit để test phần này)")
        return

    check("có mẫu để chạy", len(files) >= 3, True)

    for path in files:
        text = path.read_text(encoding="utf-8")
        items = parse_spec_tables(text)
        n_lines = len(text.splitlines())
        counts = summarize(items)

        # Mốc so với `parse_items` của bot: 203 dòng → 9 mục, 2 trong đó là rác `|---|`
        check(f"{path.name[:28]} bóc > 40 mục", len(items) > 40, True)
        check(
            f"{path.name[:28]} không có rác |---|",
            any(set(i.key) <= {"-", ":"} for i in items),
            False,
        )
        check(
            f"{path.name[:28]} phần lớn có nhãn",
            counts[STATUS_UNKNOWN] <= 2,
            True,
        )
        print(f"       {n_lines} dòng → {len(items)} mục · {counts}")


if __name__ == "__main__":
    test_read_status()
    test_ceiling()
    test_table_parsing()
    test_section_fallback()
    test_real_samples()

    print()
    if _FAILED:
        print(f"HỎNG {len(_FAILED)} test: {', '.join(_FAILED)}")
        raise SystemExit(1)
    print("tất cả test đạt")
