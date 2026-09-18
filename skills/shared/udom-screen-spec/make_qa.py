"""Sinh bảng QA (open question) gửi khách từ một tài liệu 画面仕様.

Ca dùng: tài liệu đầu vào mâu thuẫn hoặc thiếu, dev đọc một nguồn rồi code mà không
biết nguồn kia nói khác. Skill đã ghi sẵn những chỗ đó vào `確認事項一覧` và gắn nhãn
`🔴 不一致` trong thân — script này gom chúng thành bảng gửi khách.

Hai nguồn câu hỏi:

  1. Mục trong `確認事項一覧`   — câu hỏi đã được người viết tài liệu nêu
  2. Dòng mang nhãn `🔴 不一致`  — hai nguồn đá nhau, thường CHƯA có trong sổ

Nguồn 2 là lý do script tồn tại: `不一致` nằm rải trong thân (入力項目・使用API・
バリデーション), không ai gom lại, nên dev dễ bỏ sót đúng thứ nguy hiểm nhất.

Sáu cột: Question Date · Module · Priority · Question · Answer · Status
Answer để trống, Status = Open — khách điền vào.

Chạy: python3 make_qa.py <file.md> [--date YYYY-MM-DD] [-o <đích.md>]
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_table_parser import STATUS_CONFLICT, parse_spec_tables  # noqa: E402

# 優先度 trong sổ nợ → Priority của bảng QA
_PRIORITY = {"高": "High", "中": "Medium", "低": "Low"}

# Mục mang 出自 = 方針 là chính sách nội bộ, KHÔNG hỏi khách. Ba giá trị còn lại
# (`観察`, `観察（欠落）`, `観察（文書）`) đều là quan sát trên tài liệu của khách.
_SKIP_SOURCE = "方針"

_LEDGER = "確認事項一覧"

# Neo trong thân trỏ về sổ: `→ 確認事項 No.2`
_ANCHOR_RE = re.compile(r"→\s*確認事項\s*No\.(\d+)")
_SCREEN_ID_RE = re.compile(r"\b(L[SD]_\d{2}_\d{3}(?:_\d{2}){0,2})\b")


def _screen_id(text: str, path: Path) -> str:
    m = _SCREEN_ID_RE.search(path.name) or _SCREEN_ID_RE.search(text[:400])
    return m.group(1) if m else path.stem


def _clean(cell: str) -> str:
    """Bỏ markup Markdown để bảng gửi khách đọc được ở mọi nơi."""
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", cell)
    out = out.replace("`", "").replace("|", "／")
    return " ".join(out.split())


def collect(path: Path, date: str) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    items = parse_spec_tables(text)
    screen = _screen_id(text, path)
    rows: list[dict[str, str]] = []

    # ── nguồn 1: 確認事項一覧 ────────────────────────────────────────────
    for it in items:
        if it.section != _LEDGER:
            continue
        if _SKIP_SOURCE in it.columns.get("出自", ""):
            continue  # chính sách nội bộ — không hỏi khách
        no = re.sub(r"\D", "", it.key)
        rows.append(
            {
                "date": date,
                "module": f"{screen} / {_clean(it.columns.get('影響範囲', '')) or '—'}",
                "priority": _PRIORITY.get(it.columns.get("優先度", "").strip(), "Medium"),
                "question": _clean(it.columns.get("確認事項", "")),
                "ref": f"確認事項 No.{no}" if no else "確認事項",
            }
        )

    # ── nguồn 2: dòng 🔴 不一致 nằm rải trong thân ──────────────────────
    #
    # Ô `🔴` đã có neo `→ 確認事項 No.N` thì mục N trong sổ ĐÃ bao nó — thêm dòng
    # riêng là hỏi khách hai lần cùng một việc. Thay vì vậy, nâng mục N lên High
    # (不一致 luôn ưu tiên cao) rồi bỏ qua.
    for it in items:
        if it.status != STATUS_CONFLICT or it.section == _LEDGER:
            continue

        anchored = _ANCHOR_RE.search(it.raw)
        if anchored:
            no = anchored.group(1)
            for r in rows:
                if r["ref"] == f"確認事項 No.{no}":
                    r["priority"] = "High"
                    r["ref"] += f"（{it.section} の 🔴 と同件）"
                    break
            continue

        rows.append(
            {
                "date": date,
                "module": f"{screen} / {it.section}",
                "priority": "High",  # hai nguồn đá nhau ⇒ luôn ưu tiên cao
                "question": f"「{_clean(it.key)}」で資料間に不一致があります。"
                f"どちらを正とすべきかご確認ください（{_clean(it.value)[:160]}）",
                "ref": f"{it.section}（🔴 不一致）",
            }
        )

    return rows


def render(rows: list[dict[str, str]], screen: str, date: str) -> str:
    head = [
        f"# QA / Open Questions — {screen}",
        "",
        f"作成日：{date} ／ 対象：{screen} ／ 件数：{len(rows)}",
        "",
        "Answer と Status はお客様にご記入いただく欄です。",
        "Status: `Open` → `Answered` → `Closed`",
        "",
        "> `Question (VN)` `Answer (VN)` は社内確認用の翻訳欄です（お客様への送付時は削除可）。",
        "> Script は空欄で出力します — skill が日本語欄から訳して埋めます。",
        "> `Answer (VN)` はお客様から回答をいただいた後に埋めてください。",
        "",
        "| No | Question Date | Module | Priority | Question | Question (VN) "
        "| Answer | Answer (VN) | Status |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    body = [
        f"| {i} | {r['date']} | {r['module']} | {r['priority']} | {r['question']} "
        f"| {r.get('question_vi', '')} |  |  | Open |"
        for i, r in enumerate(rows, 1)
    ]
    tail = [
        "",
        "---",
        "",
        "## 出典（社内用・お客様への送付時は削除可）",
        "",
        "| No | 仕様書内の位置 |",
        "|---:|---|",
        *[f"| {i} | {r['ref']} |" for i, r in enumerate(rows, 1)],
        "",
    ]
    return "\n".join(head + body + tail)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Sinh bảng QA từ 画面仕様.md")
    ap.add_argument("spec", help="đường dẫn file 画面仕様 .md")
    ap.add_argument("--date", help="Question Date (mặc định: hôm nay)")
    ap.add_argument("-o", "--out", help="ghi ra file thay vì in ra màn hình")
    args = ap.parse_args(argv[1:])

    path = Path(args.spec)
    if not path.is_file():
        print(f"không thấy file: {path}", file=sys.stderr)
        return 2

    date = args.date or datetime.date.today().isoformat()
    rows = collect(path, date)
    if not rows:
        print("không có câu hỏi nào để gửi khách (sổ nợ trống hoặc toàn 出自=方針)")
        return 0

    screen = _screen_id(path.read_text(encoding="utf-8"), path)
    text = render(rows, screen, date)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        n_conflict = sum(1 for r in rows if "不一致" in r["ref"])
        print(f"{out} — {len(rows)} câu hỏi ({n_conflict} từ 🔴 不一致)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
