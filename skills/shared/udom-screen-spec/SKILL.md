---
name: udom-screen-spec
description: Dùng khi cần sinh hoặc cập nhật tài liệu 画面仕様 Markdown cho một màn UDOM (中央総業) từ 基本設計書 · API設計書 · DB設計書 · 標準仕様設計書 · mã nguồn. Kích hoạt khi người dùng đưa mã màn LS_NN_XXX kèm ý "làm tài liệu màn", "sinh 画面仕様", "tạo file MD cho màn", "chuẩn bị cho dev", hoặc nhắc tới PREP / 画面仕様MD作成.
---

# UDOM — Sinh 画面仕様.md cho một màn

Dựng lại vai trò của `PREP_画面仕様MD作成.md` (bản gốc đã bị 【削除】), có bù ba nguồn mà
bản gốc không đọc: DB設計書 · 標準仕様設計書 · mã nguồn.

## Bắt đầu

```
udom-screen-spec LS_02_002_01          # sinh tài liệu cho một màn
udom-screen-spec LS_02_002_01 drift    # chỉ báo cáo phần trễ so với thiết kế
```

Mã màn phải **đầy đủ hậu tố** — `LS_02_001` không hợp lệ vì KB có cả `LS_02_001_01` và
`LS_02_001_02`.

**Một biến bắt buộc.** Không có thì skill không chạy được:

```bash
export UDOM_KB_DIR="<gốc gói>/kb"      # phải thấy $UDOM_KB_DIR/CLAUDE.md
```

Cài qua marketplace thì `kb/` nằm trong thư mục plugin:

```bash
export UDOM_KB_DIR="${CLAUDE_PLUGIN_ROOT}/kb"
```

Ba biến tuỳ chọn, chỉ cần khi muốn đo từ mã nguồn: `UDOM_FE_DIR` · `UDOM_BE_ROOT` ·
`MOR_BOT_DIR`.

**File đi kèm skill** (cùng thư mục với `SKILL.md` này):

| File | Dùng để |
|---|---|
| `check_closure.py` | kiểm bao đóng hai sổ nợ — §"Cách kiểm" |
| `make_qa.py` | sinh bảng QA gửi khách — §"Sinh bảng QA" |
| `spec_table_parser.py` | bóc bảng + đọc ba nhãn `ステータス` |
| `test_spec_table_parser.py` | test cho hai file trên |
| `BOT_PATCH.md` | cách nối bộ bóc bảng vào `mor-pr-review-bot` (GĐ2) |

**Đọc thêm khi cần:**

| Cần gì | Đọc |
|---|---|
| Quy trình đầy đủ hai giai đoạn, từng bước | `MANUAL.md` ở gốc gói |
| Luật cho khâu review PR (8 luật) | `rules/pr-review-rules.md` |
| Tài liệu mẫu để đối chiếu | `samples/LS_*.md` |

## Bắt buộc đọc trước
`$UDOM_KB_DIR/CLAUDE.md` — đặc biệt **§0 (luật normalize)**,
**§5 (3 luật khớp 区分)**, **§7 (điều tuyệt đối không làm)**.

## Vị trí trong luồng

```
基本設計書 · API設計書 · DB設計書 · 標準仕様 · mã nguồn
        │
        ▼  ★ skill này ★
docs/<機能カテゴリ>/<画面ID>_<screen-name>_v<N>.md   ← chính bản
        │
        ▼  người xem, sửa, chép ❓ sang Backlog/QA
   01_仕様確認 → 02_実装計画 → 03/04/05 → 06_検証 → 07_PR前レビュー
```

Đầu ra của skill là **thước đo** mà bước 07 dùng để soi diff. Sai ở đây thì 07 mù.

## Đầu vào — 5 đầu mục

| Đầu mục | Nguồn | Ghi chú |
|---|---|---|
| Screen spec | `01-3.画面設計書` của màn (`01-3-<画面ID>.画面設計書_…_v<X.Y>.xlsx`) | bản **sống**, không lấy trong `Report_DD-MM-YYYY` (§7.5) |
| API design | `07-1.API一覧` `1dmy7deTSuvRGg3PKp4922SUH1tAHorW_IIycj4BSw8c` · `apis.tsv` | 384 API; **設計書 phần lớn chỉ ghi method, không ghi path** |
| DB design | `db_tables.tsv` (10.518) · `kubun.tsv` (1.256) · `00-2.区分値一覧` | dùng cho 桁数 và giải 区分種別 |
| 標準仕様 | `標準仕様設計書_v1.0.xlsx` `1qFKBYHXa870ORiEbR9e2UTzuX5NcwFxe` | ⚠ KB đang `未参照` — chưa trích. Xem §"Giới hạn cứng" |
| Source code | `be_endpoints.tsv` (160 đường) · `UDOM_FE_DIR` · `UDOM_BE_ROOT` | dùng để **đo** endpoint, không để suy |

## Quy trình

**1. Chốt màn.** Tra `screens.tsv` lấy `screen_id` · `name` · `kind` · `doc_status`.
Nếu người dùng đưa mã cụt hậu tố (`LS_02_001`) thì hỏi lại — KB có `LS_02_001_01` và
`LS_02_001_02` là hai màn khác nhau.

**2. Đọc 基本設計書 của màn.** Lấy `■画面項目` · `■入力チェック` · `■処理内容`.
Loại cột `O`(出力のみ) khỏi 入力項目 — giữ ở 一覧項目 hoặc bỏ.

⚠ **隠し項目 KHÔNG bỏ máy móc.** Bản gốc dặn "O／隠し項目は原則除外" — luật đó quá thô.
Nếu cột `処理内容`/`備考` của một 隠し項目 **không rỗng** thì giữ lại trong 入力項目,
ghi `備考: 隠し項目`, cột `必須` để `-`.
Đã đo: `sales_tax_rate 消費税率` là 隠し項目 nhưng mang luật
`提出日に基づき、システム設定の消費税率を設定` — bỏ đi là mất một mục nghiệp vụ,
và bước 07 sẽ không bao giờ phát hiện thiếu.

**3. Gán nhãn từng dòng** theo §"Ba nhãn".

**4. Lấp `未定` bằng đo, không bằng đoán** — xem §"Luật lấp".

**5. Dựng khung 13 mục** — giữ nguyên thứ tự và tên cột (bước 01/07 dựa vào đó).

**6. Sinh hai sổ nợ**, mỗi dòng có cột `出自` (`観察` hay `方針`) — xem §"Bao đóng".

**6b. Hỏi bản dịch** — xem §"Bản dịch cho dev". Hỏi **trước** khi ghi file, không hỏi lại sau.

**7. Lưu** `docs/<機能カテゴリ>/<画面ID>_<screen-name>_v<N>.md` — xem §"Đánh version".
`機能カテゴリ` dùng slug tiếng Anh (`common`, `estimate`, `contract`…).
Nếu repo đã có thư mục thì theo repo, không tự đổi.

## Chế độ `drift` — bắt chính bản trễ so với thiết kế

Chạy khi file `.md` đã tồn tại, **trước** khi sinh lại. Rẻ hơn sinh lại nhiều lần.

**Cơ chế:** `画面設計書` tự đánh dấu dòng nào đổi ở version nào — có tag version ngay
trong bảng `■画面項目` và `■入力チェック`:

```
…|sales_tax_calculation_category|消費税計算区分|I|プルダウン|DBの値|"…"|v1.3
…|mutual_aid_contribution_rate  |建退共掛率  |I|テキスト  |DBの値|999.999%|v1.4
…|161|見積明細備考|-|200|-|-|-|-|v1.5
```

**Cách làm:**
1. Lấy `最終更新` trong `.md` hiện có.
2. Đọc `更新履歴` của bản sống → bảng `版数 / 更新日時 / 更新シート / 内容`.
3. Mọi bản có `更新日時 > 最終更新` là **kỳ trôi**.
4. Lọc mọi dòng trong thân mang tag của các kỳ đó → đó chính là danh sách phải sửa.

Không cần diff hai file Excel, không cần `Report_DD-MM-YYYY`.

⚠ **`表紙` nói dối.** Trang bìa của `LS_02_002_01` ghi `第1.1版` trong khi bản thật là
v1.5. Lấy version từ **tên file + `更新履歴` + `modifiedTime`**, không lấy từ 表紙 (§7.5).

**Đầu ra chế độ drift:** bảng `mục · giá trị trong .md · giá trị trong 設計書 · kỳ đổi ·
mức`, không sinh lại file. Người quyết vá tay hay dựng lại.

## Đánh version — không ghi đè bản cũ

**Spec sửa thì sinh file mới, không sửa vào file đã có.** Lý do: một PR được review bằng
bản spec tại thời điểm nó viết. Ghi đè bản cũ ⇒ PR mở tháng trước bị soi bằng thước đo
tháng này, mà không ai biết thước đã đổi.

```
docs/estimate/LS_02_002_01_estimate-create_v1.md
docs/estimate/LS_02_002_01_estimate-create_v2.md   ← bản mới, v1 giữ nguyên
```

Không dùng revision history của Drive/git để thay việc này: link Drive mặc định trỏ bản
**mới nhất**, nên link dán vào PR hôm nay vẫn đọc ra nội dung khác vào tháng sau. File
riêng thì `file_id` riêng — không trôi được.

### Khối 版数 — bắt buộc, ngay dưới tiêu đề

```markdown
# LS_02_002_01 見積作成

| 版数 | 作成日 | 前版 | 変更理由 | 出典 |
|---|---|---|---|---|
| v2 | 2026-08-13 | v1 | 基本設計書 v1.5 で入力チェック追加 | `01-3-LS_02_002_01.画面設計書_…_v1.5.xlsx` (Drive 更新 2026-08-12T01:19Z) |
```

Cột `出典` là cột quan trọng nhất — nó ghi **bản nguồn nào** đã dựng ra bản spec này.
Lấy `modifiedTime` từ Drive, không lấy mtime trên máy (mtime lệch giả do múi giờ và NFD).

### Ba luật

**① Sinh lại ≠ version mới.** Trước khi ghi, quét thư mục đích tìm `_v<N>` lớn nhất, đọc
bản đó, so nội dung. **Giống hệt ⇒ không tạo file mới**, báo "không đổi so với v<N>".
Chỉ khi khác mới `N+1`. Nếu không có bản nào thì bắt đầu từ `_v1`.

**② Số `確認事項 No.N` đã cấp thì không tái sử dụng.** Đây là chỗ dễ vỡ nhất: bước 07 đã
comment lên PR *"→ 確認事項 No.7"*; sang v2 nếu đánh số lại từ đầu thì No.7 trỏ sang mục
khác — comment cũ thành sai mà không ai phát hiện. Luật:

- Mục đã giải quyết → **giữ nguyên số**, đổi cột `優先度` thành `解決済み（v<N> 時点）`,
  **không xoá khỏi bảng**
- Mục mới → cấp số tiếp theo số lớn nhất **từng dùng**, kể cả số của mục đã xoá
- Áp dụng y hệt cho `想定 No.N`

**③ `変更履歴` phải là diff thật với v(N-1)**, không phải mô tả chung chung. Skill có sẵn
cột `出自` cho từng ô nên diff theo dòng làm được. Ghi thành mục cuối file:

```markdown
## 変更履歴（v1 → v2）

| 箇所 | v1 | v2 | 出典 |
|---|---|---|---|
| 入力項目.消費税率 | （なし） | 隠し項目・自動設定 | 画面設計書 v1.3 |
| 確認事項 No.3 | 優先度 高 | 解決済み（v2 時点） | 2026-08-10 打合せ |
```

### Khi nào KHÔNG lên version

- Sửa lỗi chính tả, đổi format bảng, đổi tên cột slug → sửa tại chỗ bản hiện hành
- Chế độ `drift` chỉ **báo cáo**, không sinh file ⇒ không đụng version

Ranh giới: đổi thứ mà bước 07 dùng để soi diff (項目・バリデーション・API・区分・sổ nợ)
⇒ lên version. Đổi thứ chỉ người đọc thấy ⇒ sửa tại chỗ.

## Khung 13 mục (giữ nguyên bản gốc)

Đếm cho khỏi nhầm khi kiểm: **13 mục nội dung** + 2 mục kèm (`ステータス記号の意味` ·
`作成後のチェックリスト`) = **15 tiêu đề `##`** ở bản v1; từ v2 thêm `変更履歴` thành **16**.
Tên "13 mục" chỉ đếm phần nội dung — đó là cách gọi kế thừa từ bản gốc, giữ nguyên.

```
# <画面ID> <画面名>
<bảng 版数>                          ← khối version, xem §"Đánh version"
最終更新：<ngày>   ステータス：草案（未確認事項あり）

## 画面概要        ## 検索条件       ## 入力項目      ## 一覧項目
## ボタン・操作     ## 画面遷移       ## 使用API       ## バリデーション
## 表示・活性制御   ## 権限制御       ## エラー処理
## 確認事項一覧     ## 想定一覧
## ステータス記号の意味   ## 作成後のチェックリスト（人間側）
## 変更履歴（v<N-1> → v<N>）          ← chỉ có từ v2 trở đi
```

Cột bắt buộc:
- 入力項目 `項目 / 型 / 必須 / バリデーション / 備考 / ステータス`
- 使用API `タイミング / API名 / エンドポイント / 備考 / ステータス`
- 確認事項一覧 `No / 確認事項 / 影響範囲 / 優先度 / 出自`
- 想定一覧 `No / 項目 / 想定内容 / 根拠 / 優先度 / 出自`

Cột `出自`, khối `版数` và mục `変更履歴` là bổ sung so với bản gốc. Không đổi gì khác.

## Ba nhãn

| Nhãn | Điều kiện | Bước sau xử |
|---|---|---|
| ✅ 確認済み | **có ghi trong 設計書** | code luôn |
| 🔴 不一致 | **hai nguồn nói khác nhau** — trích được nguyên văn cả hai bên | **dừng, hỏi khách**; vào bảng QA với Priority = High |
| 🔶 想定 | không ghi trong 設計書 — suy từ thông lệ **hoặc đo từ code**; bắt buộc kèm 根拠 | để TODO; ưu tiên 高 phải hỏi trước |
| ❓ 要確認 | cần phán đoán nghiệp vụ | cấm code trước khi hỏi |

### 🔴 不一致 — nhãn dễ bỏ sót nhất

`❓` là *"tài liệu không nói"*. `🔴` là *"tài liệu nói **hai** thứ"* — nguy hiểm hơn hẳn, vì
đọc riêng từng nguồn thì **cả hai đều hợp lý**, dev code theo một bên mà không biết bên kia.

Bốn cặp nguồn phải đối chiếu, đã gặp thật:

| Cặp | Ví dụ đo được |
|---|---|
| 設計書 ↔ DB設計書 | 桁数 ở `■入力チェック` vs `db_tables.tsv` |
| 設計書 ↔ mã nguồn | `承認ルート名` 100 (設計書・BE) vs 50 (`workflowFilterSchema` FE) |
| 画面A ↔ 画面B | `LS_01_070_01` ghi 従業員選択画面 = chính nó; `LS_01_070_02` ghi `LS_01_009_05` |
| **bên trong một file** | 表紙 `第1.4版` ／ 更新履歴 `1.0` ／ tên file `v1.0` |

Cặp cuối hay bị bỏ qua nhất vì chỉ có một tài liệu.

**Luật:** gắn `🔴` khi trích được **nguyên văn cả hai bên**. Không trích được cả hai ⇒ đó là
`❓`, không phải `🔴`. Ô mang `🔴` phải ghi rõ **bên nào nói gì**, và thêm một dòng
`確認事項` với `出自 = 観察（不一致）`.

Nhãn kép có `🔴` thì `🔴` thắng: `✅ 確認済み／🔴` nghĩa là *"設計書 ghi rõ, NHƯNG code nói
khác"* — phải nổi lên thành câu hỏi, không được chìm xuống thành `確認済み`.

Ô mang **nhãn kép theo chiều** là hợp lệ và nên dùng:
`✅ 確認済み（遷移先）／❓ 要確認（パラメータ）`.

## Danh sách chính sách — phần không được mất

Đây là tài sản của bản gốc. Bơm vào sổ nợ **kể cả khi 設計書 im lặng**.

### 10 mục ĐƯỢC phép 想定

| Mục | Hướng suy |
|---|---|
| 初期表示時の検索実行 | 一覧系 → tìm thủ công / 詳細系 → tự lấy |
| 文字列検索の一致方式 | 部分一致 |
| 登録成功後の遷移先 | về 一覧画面 |
| 更新成功後の再取得 | lấy lại 詳細 |
| 削除成功後の遷移先 | về 一覧画面 |
| 削除の確認ダイアログ | あり (thao tác không hoàn tác) |
| Loading 表示 | hiện khi đang gọi API |
| エラー時の表示方法 | toast hoặc inline |
| 日付範囲の境界 | `From ≦ x ≦ To` |
| テキスト桁数上限 | **đo từ `db_tables.tsv`**, không còn là 推測 |

### 9 mục CẤM 想定 — luôn thành 確認事項

`ステータス遷移条件・遷移可否のルール` · `承認・否認の条件と権限` ·
`金額・数量の計算ロジック・端数処理` · `排他制御・二重送信対策の要否` ·
`画面遷移時に渡すキー・パラメータの詳細` · `エラーメッセージの文言` ·
`ページサイズ・ソートの初期値` · `モーダルを閉じた後の再取得有無` ·
`検索条件の保持・復元方式`

Mục nào **không áp dụng cho màn này** thì bỏ, nhưng phải bỏ có ý thức — đừng quên xét.

## Luật lấp `未定`

### Hai mức bằng chứng — không được trộn

| Mức | Điều kiện | Ghi |
|---|---|---|
| **実測** | join **chính xác** bằng khoá có thật | `根拠: BEコード実測 GET /api/v1/…` |
| **候補** | khớp bằng **nghĩa tên** (tên JP ↔ path tiếng Anh) | `根拠: BEコード候補・名前一致` + bắt buộc sinh 確認事項 |

**Cách phân biệt cho endpoint:** `operation_id` khớp `^\d+_.*API$` (vd `240_工事区分一覧取得API`)
⇒ **実測**. Tên tự sinh (`v1_employees_departments_list`) ⇒ **候補**.

> ⚠ Đã đo trên `be_endpoints.tsv`: **6/160 dòng** có mã số + tên JP. 154 dòng còn lại là
> tên tự sinh. Nghĩa là **~96% trường hợp chỉ đạt mức 候補** — 実測 là ngoại lệ, không
> phải mặc định. Đừng viết `実測` theo quán tính.

### Bảng lấp

| Ô | Nguồn | Mức | Nhãn ghi |
|---|---|---|---|
| Endpoint (operation_id có mã JP) | `be_endpoints.tsv` | 実測 | `🔶 想定` · `根拠: BEコード実測 <method> <path>` |
| Endpoint (operation_id tự sinh) | `be_endpoints.tsv` | **候補** | `🔶 想定` · `根拠: BEコード候補・名前一致` **+ 確認事項** |
| 桁数 / 型 | `db_tables.tsv` cột `col_physical` | 実測 | `🔶 想定` · `根拠: DB設計書 <table_logical>.<col>` |
| Giá trị 区分 | `kubun.tsv` qua **3 luật §5** | luật 1 = 実測 · luật 2 = 候補 | 1 ứng viên → `🔶` kèm mã hằng; ≥2 → `❓` liệt kê hết |
| 文言 message | `messages.tsv` theo `I_/E_/W_NNNNN` | 実測 | `✅` nếu khớp **từng chữ** |

**Đo được ≠ đã chốt.** Code có endpoint mà 設計書 chưa ghi thì đó là **lệch giữa hai đầu
mục**, không phải xác nhận. Ghi `🔶`, và sinh thêm một dòng 確認事項:
> "BE có `GET /api/v1/…`, 設計書 để 未定 — chốt theo cái nào?"

Không bao giờ nâng `🔶` thành `✅` chỉ vì code có (§7.2).

## Bao đóng hai sổ nợ

### Luật bắt buộc: mọi ô có nhãn phải trỏ về số hiệu sổ

**Mỗi ô mang `🔶` hoặc `❓` trong thân BẮT BUỘC ghi kèm số hiệu mục sổ:**

```
| 承認ルート名 | … | 🔴 不一致 → 確認事項 No.2 |
| 宛名 (…)     | … | ✅ 確認済み（呼出）／❓ 要確認 → 確認事項 No.8 |
| 明細削除     | … | 🔶 想定 → 想定 No.1 |
```

Không có mũi tên ⇒ **coi như thiếu sót**, phải bổ sung trước khi lưu.
Nhiều ô được phép trỏ về **cùng một** số hiệu (5 dòng `画面遷移` cùng trỏ `No.2` là hợp lệ).

### Cách kiểm — cơ học, không phán đoán

`check_closure.py` nằm **cùng thư mục với `SKILL.md` này**, nên đường dẫn là nơi skill được cài:

```bash
python3 ~/.claude/skills/udom-screen-spec/check_closure.py <file.md>
# hoặc nếu cài project-level:
python3 <dự án>/.claude/skills/udom-screen-spec/check_closure.py <file.md>
```

Mã thoát 1 nếu có vi phạm — cắm vào CI được.

- Số hiệu có ở thân mà **không có** trong sổ → mục bị bỏ quên
- Mục trong sổ **không ai trỏ tới** → phải nêu được lý do ở cột `出自`

### Bốn giá trị của cột `出自`

| Giá trị | Khi nào | Cần neo? |
|---|---|---|
| `観察` | quan sát được **ở một ô cụ thể** trong thân | **có** — không neo là mục mồ côi thật |
| `方針` | mục từ hai danh sách chính sách (10 mục được 想定 / 9 mục cấm 想定) | không |
| `観察（欠落）` | quan sát thấy tài liệu **thiếu** thứ gì đó | không — ô cần neo chính là ô không tồn tại |
| `観察（文書）` | quan sát về **chính tài liệu nguồn** (項番の信頼性・版数の不整合) | không — không thuộc ô nội dung nào |
| `観察（不一致）` | **hai nguồn nói khác nhau** — đi kèm ô mang `🔴` trong thân | **có** — phải trỏ về ô `🔴` |

> ⚠ **Thêm 2026-08-13.** Bản trước chỉ có `観察` và `方針`, và dặn "mục mồ côi phải mang
> `出自 = 方針`". Chạy trên ba tài liệu thật cho thấy luật đó ép sai: 7/12 mục mồ côi nói về
> thứ tài liệu **không có** (`金額端数処理区分` được `■アクション` tham chiếu nhưng
> `■画面項目` không có — tìm `price_rounding` ra 0 kết quả). Gọi chúng là `方針` là nói dối:
> chúng không phải chính sách, mà là phát hiện thiếu sót — thứ giá trị nhất trong cả tài liệu.

⚠ **Đừng kiểm bằng `grep` gộp.** Bản trước của skill dặn:

```bash
grep -oE '^\| *\*{0,2}[0-9]+' <file>       # ✗ SAI
```

Lệnh này gộp số hiệu của **cả hai sổ** thành một danh sách phẳng, nên `No.7` của
`確認事項一覧` lẫn với `No.7` của `想定一覧`. Đo ngày 2026-08-13 trên ba tài liệu thật: lệnh
gộp bỏ sót **12 vi phạm** — cả ba file đều có mục mồ côi ghi `出自 = 観察`.

> ⚠ **Không kiểm bằng cách đếm số lượng.** Đã đo trên `LS_02_002_01`: 17 dấu `❓` trong thân
> vs 16 dòng sổ — con số khớp với "có lỗi" chỉ là **trùng hợp**, vì nhiều ô dồn vào một mục
> (5 dòng `画面遷移` → 1 mục). Ô mồ côi thật là `背景色・画面上部メッセージ`. Ba file khác báo
> `sổ ≥ thân` nên trông sạch, nhưng phép đếm **không chứng minh được** điều đó.

### Ba luật còn lại

1. Mục từ hai danh sách chính sách không có neo trong thân → vẫn ghi, `出自 = 方針`
2. Không được để một thứ vừa `🔶` trong thân vừa `❓` trong sổ — chọn một tầng
3. Mục nào không áp dụng cho màn này → ghi rõ **「対象外と判断」** kèm lý do, không im lặng bỏ

Cột `出自` tồn tại để người đọc phân biệt *"tài liệu không nói"* với
*"luôn phải hỏi dù tài liệu có nói hay không"*. Bản gốc trộn hai loại này.

## Bản dịch cho dev

Hỏi **trước khi ghi file** (bước 6b), một lần, không hỏi lại:

```
Sinh tài liệu cho <画面ID>. Chọn bản dịch:

  1. Chỉ 日本語                        1 file — mặc định
  2. 日本語 + Tiếng Việt               2 file
  3. 日本語 + English                  2 file
  4. 日本語 + Tiếng Việt + English     3 file

  [Enter = 1]
```

Mặc định là **1**: bản Nhật là thước đo bắt buộc, dev chỉ trả thêm chi phí khi thật cần đọc.

### Bản dịch là file riêng, KHÔNG phải cột thêm

```
docs/common/LS_01_070_02_approval-route-create_v1.md      ← gốc, bot đọc bản này
docs/common/LS_01_070_02_approval-route-create_v1.vi.md   ← bản đọc
docs/common/LS_01_070_02_approval-route-create_v1.en.md
```

Ba lý do:

1. Bảng spec đã 6 cột; thêm hai cột dịch thành 8, mỗi ô lại dài — vỡ trên màn hình.
   (Bảng QA chịu được vì mỗi dòng chỉ một câu hỏi, spec thì không.)
2. **`parse_spec_tables` sẽ bóc cả dòng dịch thành mục** nếu để cùng file — 54 mục thành
   108, và trần severity QĐ9 đếm sai.
3. Tiền lệ đã có: `07_PR前レビュー.vi.md` trong bộ template gốc.

### Bốn nhóm TUYỆT ĐỐI không dịch

Sai chỗ này thì bản dịch thành bẫy, không phải trợ giúp.

| Giữ nguyên | Ví dụ | Vì sao |
|---|---|---|
| Mã định danh | `LS_01_070_02` · `F-01-070-02` · `E_00051` | dịch là mất khả năng tra ngược |
| Tên trong code | `workflowFilterSchema` · `btn_viewr_add` · `approve_route_name` | dev phải grep được |
| Số hiệu sổ nợ | `→ 確認事項 No.7` | comment của bot trỏ tới số này |
| **Bốn nhãn** | `✅ 確認済み` · `🔴 不一致` · `🔶 想定` · `❓ 要確認` | `spec_table_parser` nhận diện theo đúng chuỗi này — dịch là **hỏng công cụ** |

Tên mục `##` cũng giữ nguyên (`## 入力項目`, `## 確認事項一覧`) — bot nạp spec theo tên mục.

### Dòng cảnh báo bắt buộc ở đầu mỗi bản dịch

```markdown
> ⚠ Bản đọc tham khảo. Thước đo chính thức là bản 日本語.
> Bot review PR đối chiếu với `<画面ID>_<screen-name>_v<N>.md`, không đọc file này.
> Lệch nhau ⇒ bản 日本語 đúng.
```

Không có dòng này thì sẽ có ngày dev code theo bản dịch, bot báo lỗi, và không ai hiểu vì sao.

### Sửa bản gốc thì phải dịch lại

File riêng có rủi ro lệch. Sau mỗi lần sửa, chạy:

```bash
python3 ~/.claude/skills/udom-screen-spec/check_translation.py <file gốc .md>
```

Nó so số dòng bảng, danh sách số hiệu `No.N` và bộ nhãn giữa bản gốc và mọi bản dịch.
Mã thoát 1 nếu lệch — cắm được vào CI.

**Dùng được cho cả hai loại tài liệu.** Script tự nhận diện theo nhãn nào xuất hiện nhiều hơn:

| Loại | Bộ nhãn phải giữ nguyên | Tên mục `##` |
|---|---|---|
| Spec `画面仕様` | `確認済み` · `不一致` · `想定` · `要確認` | **phải giữ nguyên** — bot nạp spec theo tên mục |
| Báo cáo review | `Critical` · `Major` · `Minor` · `Suggestion` | dịch được — chỉ cần đủ số mục |

Bản dịch luôn được soi bằng **bộ nhãn của bản gốc**, không tự đoán lại. Nếu để bản dịch tự
đoán, một bản đã dịch hết nhãn sẽ đoán ra bộ khác và script báo "khớp" một cách sai lầm.

Báo cáo review cũng theo quy ước file riêng: `PR140_review_v1.md` → `PR140_review_v1.vi.md`.

**Lên version thì dịch lại cả file**, không vá từng dòng: `_v2.md` phải có `_v2.vi.md` riêng,
`_v1.vi.md` giữ nguyên cho PR cũ.

## Sinh bảng QA gửi khách

Sổ nợ nằm rải trong tài liệu, khách không đọc `画面仕様.md`. Bước cuối là gom chúng thành
một bảng gửi đi:

```bash
python3 ~/.claude/skills/udom-screen-spec/make_qa.py \
        docs/common/LS_01_070_02_approval-route-create_v1.md \
        -o docs/qa/QA_LS_01_070_02_v1.md
```

Tám cột: `Question Date · Module · Priority · Question · Question (VN) · Answer ·
Answer (VN) · Status`. `Answer` để trống, `Status = Open` — khách điền.

### Hai cột dịch — script để trống, skill điền

| Cột | Điền lúc nào |
|---|---|
| `Question (VN)` | **ngay sau khi sinh** — để team đọc trước khi gửi |
| `Answer (VN)` | **sau khi khách trả lời** — dịch ngược nội dung `Answer` |

Chiều thứ hai quan trọng không kém: khách Nhật trả lời bằng tiếng Nhật, dev Việt là người
thực thi câu trả lời đó. Dịch sai chỗ này thì code sai.

Script chỉ gom text, **không dịch được**. Sau khi chạy `make_qa.py`, skill phải đọc lại file
và điền cột `Question (VN)` từ cột `Question`. Ba luật khi dịch:

1. **Giữ nguyên mọi định danh** — `LS_01_070_02`, `F-01-070-02`, `workflowFilterSchema`,
   `btn_viewr_add`, tên bảng/cột DB. Dịch chúng là làm mất khả năng tra ngược.
2. **Giữ nguyên con số và tên tài liệu** — `100`, `50`, `第1.4版`, `更新履歴`, `■画面項目`.
   Người đọc bản Việt vẫn phải mở đúng sheet tiếng Nhật.
3. **Dịch ý, không dịch từng chữ.** `項番の信頼性` → "Độ tin cậy của cột `項番`", không phải
   ghép nghĩa từng ký tự.

Hai cột này là **để nội bộ đọc cho nhanh**, không gửi khách — khách Nhật chỉ đọc `Question`
và điền `Answer`. Xoá `Question (VN)`, `Answer (VN)` và mục `出典` trước khi gửi đi.

**Hai nguồn câu hỏi, nguồn thứ hai là lý do script tồn tại:**

| Nguồn | Lấy từ đâu | Priority |
|---|---|---|
| ① `確認事項一覧` | sổ nợ — câu hỏi đã được nêu sẵn | theo cột `優先度` (高→High) |
| ② dòng `🔴 不一致` | **rải trong thân**, thường CHƯA vào sổ | luôn **High** |

Nguồn ② hay bị bỏ sót nhất: `不一致` nằm lẫn trong `入力項目`・`使用API`・`バリデーション`,
không ai gom lại, nên dev bỏ qua đúng thứ nguy hiểm nhất.

**Mục `出自 = 方針` bị loại khỏi bảng** — đó là chính sách nội bộ (10 mục được 想定 / 9 mục
cấm 想定), không phải câu hỏi cho khách. Ba giá trị còn lại (`観察`, `観察（欠落）`,
`観察（文書）`, `観察（不一致）`) đều là quan sát trên tài liệu của khách nên đều đi vào bảng.

Cuối file có mục `出典` ánh xạ mỗi câu hỏi về vị trí trong 仕様書 — dùng nội bộ khi khách hỏi
lại "câu này ở đâu ra", xoá được trước khi gửi.

**Khử trùng:** ô `🔴` đã có neo `→ 確認事項 No.N` thì mục N trong sổ đã bao nó — script
**nâng mục N lên `High`** rồi bỏ qua, thay vì thêm dòng riêng. Không có bước này thì khách
nhận hai câu hỏi cho cùng một việc (đã gặp: `承認ルート名` xuất hiện ở cả No.2 và No.10).

Đo trên ba mẫu: **31 câu hỏi** (11 / 9 / 11). Mẫu đầu ra ở
`samples/QA_LS_01_070_02_v1.md`.

## Bẫy đã kiểm chứng

1. **`tbl_*` trong 一覧項目 là ID lưới UI, KHÔNG phải bảng DB.** `db_tables.tsv` dùng
   `table_logical` tiếng Nhật (`現場別最終単価マスタ`). Tra `tbl_estimate_detail` sang DB
   sẽ ra rỗng và dẫn tới kết luận sai "thiếu bảng".
2. **Mã màn ở 画面遷移 hay bị cụt hậu tố.** `LS_02_001` ≠ `LS_02_001_01`;
   `LS_09_004` có cả `_01`(新規作成) và `_02`(編集). Luôn ghi mã đầy đủ, và normalize
   trước khi so (§0).
3. **`区分種別="宛名"` là mơ hồ** — KB có ít nhất `ADDRESS_DELIVERY_CATEGORY` và
   `ADDRESS_OUTPUT_SUBJECT_CATEGORY`. Ghi ứng viên + `要確認`, đừng chọn bừa.
4. **Số API trong 設計書 không chắc join được** (`No.146` không có trong `apis.tsv`).
   Không kết luận "API không tồn tại" — ghi 確認事項.
5. **`■画面基本情報.URL` là route trình duyệt, KHÔNG phải API endpoint.** Hai không gian tên
   khác nhau. Thiết kế để **toàn bộ endpoint là `未定`**, chỉ định nghĩa tên API + IN/OUT.
   Đã đo: `LS_01_070_01` URL = `/approval-routes`, `LS_01_070_02` = `/approval-routes/create`
   (route FE, khớp `ROUTES.*` trong repo FE) — trong khi BE dùng `/api/v1/approve-routes/`.
   **Không được lấy URL màn để phán API path đúng hay sai.** Cũng không được lấy đa số trong
   code làm chuẩn — cả hai đều đã dẫn tới kết luận sai trong một lần chạy thật.

6. **Màn tính toán vượt khung 13 mục.** Màn có nhiều lưới ẩn/hiện và tính lại chéo
   (kiểu 見積) không có chỗ mô tả *quan hệ tính toán giữa các ô*. Đừng nhét vào 備考 —
   ghi thẳng thành 確認事項 về công thức.

## Checklist người (chép vào cuối file sinh ra)

- [ ] Không lệch với 基本設計書
- [ ] Đã chép `❓ 要確認` sang Backlog / QA表
- [ ] `🔶 想定` ưu tiên **高** đã đưa vào 確認事項
- [ ] Endpoint không có giá trị suy đoán — hoặc `未定`, hoặc `🔶` kèm 根拠 **ghi rõ 実測 hay 候補**
- [ ] Mỗi ô mức `候補` đều có một dòng 確認事項 tương ứng
- [ ] Không lẫn thông tin cá nhân / dữ liệu thật
- [ ] Đã lưu đúng `docs/<機能カテゴリ>/<画面ID>_<screen-name>_v<N>.md`, **không ghi đè bản cũ**
- [ ] Khối `版数` có đủ `前版` · `変更理由` · `出典` (kèm `modifiedTime` của nguồn)
- [ ] Số `確認事項 No.` / `想定 No.` không bị đánh lại — mục đã xong ghi `解決済み`, giữ số

## Giới hạn cứng — nói rõ với người dùng

- **`標準仕様設計書_v1.0.xlsx` đang `未参照` trong KB.** Tài liệu màn viện dẫn nó rất nhiều
  (`標準仕様No.3/4/7/11/12/19/21/27/30`). Chưa trích thì **không giải được** các số này —
  ghi nguyên `標準仕様No.N` kèm `❓ 要確認`, tuyệt đối không đoán nội dung.
  Muốn giải thì phải trích file đó vào KB trước.
- **Drive MCP không có tool ghi.** Skill chỉ sinh file `.md` trong repo, không sửa được
  Excel/Sheet gốc. Muốn tài liệu gốc đổi thì xuất phiếu việc cho người.
- **Claude Code đọc được `.xlsx`** — giả định cũ của bản gốc (phải chuyển tay qua
  Claude.ai chat) đã hết hiệu lực.

## Tuyệt đối không

1. Không điền ô trống bằng suy đoán. `未設計` / `未記入` / `未定` là **tín hiệu** (§7.1).
2. Không ghi ứng viên khớp tên thành dữ kiện — luôn kèm `要確認` (§7.2).
3. Không so khoá trực tiếp — qua `normalize.py` (§0).
4. Không bỏ qua 9 mục cấm 想定 chỉ vì 設計書 không nhắc tới.
5. Không nâng nhãn `🔶` → `✅` dựa trên mã nguồn.
6. **Không ghi `実測` cho một khớp theo nghĩa tên.** Chỉ 6/160 endpoint đạt mức 実測;
   mặc định là `候補`, và `候補` luôn kéo theo một dòng 確認事項 (§7.2).
7. Không tự sửa tài liệu gốc trên Drive hay Figma.
8. **Không ghi đè bản spec đã sinh.** Nội dung đổi ⇒ file `_v<N+1>` mới. Bản cũ là thước đo
   của những PR đã review bằng nó.
9. **Không đánh lại số `確認事項 No.` / `想定 No.` khi lên version.** Số đã cấp là khoá mà
   comment của bot trỏ tới.
