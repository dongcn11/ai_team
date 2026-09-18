# patches — bộ vá chờ nối vào `mor-pr-review-bot`

Vá hai lỗ đo được ngày 2026-08-13 khi chạy thử luồng theo `MANUAL.md`.

## Vì sao là thư mục riêng, không sửa thẳng repo bot

`README.md` của `mor-pr-review-bot` (dòng 22–32) chia chủ sở hữu theo file:

| Vùng | File | Chủ |
|---|---|---|
| Ngữ cảnh đặc tả | `scripts/context_*.py` | agent **`specctx`** |

Nguyên văn: *"Mỗi agent chỉ ghi vào file của mình. Cần thứ gì ở vùng dùng chung mà chưa có thì
**báo, đừng tự sửa** — sửa file của người khác là tạo xung đột không ai gỡ được."*

Hai file cần vá — `context_types.py` và `context_priority.py` — đều thuộc `specctx`. Thêm nữa,
`mor-pr-review-bot` **không phải git repo** (`git status` → `fatal: not a git repository`), nên
sửa hỏng thì không revert được.

Nên: mã để sẵn ở đây, chạy được, có test. Việc nối là hai dòng, do `specctx` làm.

## Hai lỗ được vá

**① `parse_items` không bóc bảng Markdown.** Nó chỉ khớp khuôn `khoá: giá trị` theo từng dòng.

| | `parse_items` (bot) | `parse_spec_tables` (vá này) |
|---|---|---|
| `LS_01_070_01` (216 dòng) | — | **61 mục**, 0 mục thiếu nhãn |
| `LS_01_070_02` (203 dòng) | **9 mục**, 2 là rác `\|---\|` | **54 mục**, 1 mục thiếu nhãn |
| `LS_02_002_01` (336 dòng) | — | **195 mục**, 0 mục thiếu nhãn |

**② Bot không biết ba nhãn.** `grep 'ステータス\|確認済み\|要確認' scripts/*.py` = 0 dòng.
`TableItem.ceiling` và `.allows()` cài QĐ9 thành mã:

| Nhãn | Trần | Nghĩa |
|---|---|---|
| `✅ 確認済み` | `critical` | trích nguyên văn được ⇒ cho gán tới Critical |
| `🔶 想定` | `minor` | **không được FAIL** — spec tự khai là suy đoán |
| `❓ 要確認` | `info` | không phải luật ⇒ ghi chú cho người |
| thiếu nhãn | `minor` | không tin hơn `想定` |

## Ba quyết định trong bộ vá

**Nhãn kép lấy mức YẾU nhất.** `✅ 確認済み（遷移先）／❓ 要確認（パラメータ）` → `要確認`.
Nhãn kép theo chiều là hợp lệ (SKILL.md §"Ba nhãn"), và khi một chiều còn ngờ thì cả dòng chưa
đủ chắc để FAIL.

**Hai sổ nợ suy nhãn theo tên mục.** `確認事項一覧` và `想定一覧` không có cột `ステータス` —
mức tin cậy nằm ở chính tên mục. Không suy thì 18/57 mục của `LS_01_070_02` rơi vào `不明`.

**`ステータス記号の意味` bị bỏ khỏi kết quả** — bảng chú giải, không phải luật.

## Biến thể nhãn đã kiểm kê

Quét 3 mẫu thật: **273 ô có nhãn**, ba nhãn chuẩn chiếm **260**. Còn lại:

| Biến thể | Xử lý |
|---|---|
| `❓ **要確認**` (in đậm) | khớp — tìm theo chuỗi con |
| `✅ 確認済み〔v1.4〕` | khớp |
| `✅ 確認済み（IO）` | khớp |
| `⚠️ 未確認` | gom về `要確認` (đồng nghĩa) |
| `🔴 FE …` | **để `不明` ⇒ trần `minor`** — đây là *kết quả đối chiếu*, không phải nhãn tin cậy; dòng mang nó vẫn trỏ về `確認事項 No.N` nên không mất thông tin |

## Nối vào bot — ba chỗ

**Chỗ 1 — tầng `TIER_SPEC_KEY`** (`context_priority.py:193–200`), ngay chỗ đang gọi `parse_items`:

```python
items={
    item.norm_key: item
    for item in parse_items(spec_file.text if spec_file else "", ...)
},
```

Bổ sung mục bóc từ bảng vào cùng dict. `TableItem` có `key` · `value` · `raw` nên bọc sang
`SpecItem` là một dòng: `SpecItem(key=t.key, value=t.value, raw=t.raw, source=..., tier=...)`.

**Chỗ 2 — tầng `TIER_COMMENT`** (`context_comment.py:251`) nếu muốn người dán được cả bảng
vào comment. Không bắt buộc: khuôn `REVIEW_SPEC_TEMPLATE` vốn là danh sách một dòng một mục.

**Chỗ 3 — dùng trần severity.** Nơi bộ chấm gán mức cho `Finding`, gọi `item.allows(severity)`;
`False` thì hạ xuống `item.ceiling`. Chỗ này thuộc agent `engine`, không phải `specctx`.

## `check_closure.py` — kiểm bao đóng hai sổ nợ (dùng cho GĐ1, không phải cho bot)

Thay hai lệnh `grep` cũ trong `SKILL.md` §"Cách kiểm" và `MANUAL.md` B5②. Lệnh cũ

```bash
grep -oE '^\| *\*{0,2}[0-9]+' <file>      # ✗ gộp cả hai sổ thành danh sách phẳng
```

trộn `No.7` của `確認事項一覧` với `No.7` của `想定一覧`. Chạy trên ba mẫu thật ngày
2026-08-13, lệnh gộp bỏ sót **12 vi phạm** — cả ba file đều có mục mồ côi ghi `出自 = 観察`
trong khi luật đòi `方針`:

| Mẫu | Vi phạm | Đã sửa |
|---|---|---|
| `LS_01_070_01` | 確認事項 No.9 · No.14 · 想定 No.4 | ✓ |
| `LS_01_070_02` | 確認事項 No.7 · No.8 · No.11 · 想定 No.5 | ✓ |
| `LS_02_002_01` | 確認事項 No.1 · No.3 · No.14 · No.16 · 想定 No.6 | ✓ |

Cả 12 đã sửa ngày 2026-08-13; `check_closure.py ../../samples/LS_*.md` giờ trả mã thoát 0.

**Sửa chúng làm lộ một lỗ trong luật.** Bản trước chỉ có hai giá trị `出自` và ép mọi mục
mồ côi phải là `方針`. Nhưng 7/12 mục nói về thứ tài liệu **không có** — gọi chúng là "chính
sách" là nói dối. Nay có bốn giá trị (xem `SKILL.md` §"Bốn giá trị của cột `出自`"):

| `出自` | Cần neo `→ No.N`? | Số ô trong 3 mẫu |
|---|---|---|
| `観察` | **có** | 23 |
| `方針` | không | 24 |
| `観察（欠落）` | không — ô cần neo chính là ô không tồn tại | 7 |
| `観察（文書）` | không — nói về chính tài liệu nguồn | 3 |

`出自 = 観察＋方針` cũng được chấp nhận (chứa `方針`).

## Đề xuất #3 — comment của bot cần chọn được ngôn ngữ

**Không thuộc phạm vi bộ vá này** (`publish_*.py` là của agent `publish`), ghi lại để bàn.

### Hiện trạng đo được 2026-08-14

`publish_comment.py` sinh comment **cứng bằng tiếng Việt**:

```
## 👁️ Checklist người kiểm
## Tổng kết
## 🔴 Critical · 🟠 Major
Không có mục nào ở hai mức này.
## ✅ Đã đạt
```

`grep -rn 'LANG\|locale\|language' scripts/ config/` → **0 dòng**. Không đổi được ngôn ngữ.

### Vì sao đáng bàn

Comment này **đăng lên PR trên GitHub** — nơi khách 中央総業 xem được. Với một PR bị chặn vì
Critical, khách thấy một khối tiếng Việt và không hiểu bot đang nói gì.

Nghịch lý hiện tại: **bot viết tiếng Việt, báo cáo review thủ công viết tiếng Nhật.** Hai loại
báo cáo cùng một việc, hai ngôn ngữ trái nhau, không cái nào chọn được.

### Đề xuất

Thêm biến môi trường, cùng kiểu với `MOR_BOT_SPECS_DIR` đã có ở `context_branch.py:27`:

```bash
MOR_BOT_LANG=ja|vi|both      # mặc định `both` cho comment công khai
```

Với `both`: phần tiếng Nhật ở ngoài, phần tiếng Việt gấp trong `<details>` — khách đọc được
ngay, dev bung ra khi cần.

**Bốn mức nghiêm trọng giữ nguyên tiếng Anh ở mọi ngôn ngữ** (`Critical` · `Major` · `Minor` ·
`Suggestion`). Chúng là khoá phân loại, không phải văn xuôi — `check_translation.py` trong
skill này đã coi việc dịch chúng là lỗi.

## Chạy

```bash
python3 spec_table_parser.py ../../samples/LS_02_002_01_estimate-create_v1.md
python3 check_closure.py ../../samples/LS_*.md
python3 test_spec_table_parser.py
```

Không phụ thuộc thư viện ngoài, không cần pytest. Chỉ đọc file, không ghi, không gọi mạng.
