---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
inputDocuments:
  - '_bmad-output/planning-artifacts/prd-mcp-per-project.md'
  - '_bmad-output/planning-artifacts/research-mcp-per-project.md'
  - '_bmad-output/implementation-artifacts/spec-claude-account-switch.md'
  - 'README.md'
  - 'worker.py'
  - 'dashboard/README.md'
workflowType: 'architecture'
lastStep: 8
status: 'complete'
completedAt: '2026-09-22'
project_name: 'ai_team_clean'
feature: 'MCP per-project'
user_name: 'mor_dong.bd'
date: '2026-09-22'
prdSource: '_bmad-output/planning-artifacts/prd-mcp-per-project.md'
prdExcluded: '_bmad-output/planning-artifacts/prd.md (PRD e-commerce cua du an khach — khong lien quan)'
---

# Architecture Decision Document — MCP theo từng dự án (ai_team_clean)

**Author:** mor_dong.bd · **Date:** 2026-09-22

**Nguồn:** PRD `prd-mcp-per-project.md` (34 FR) · bằng chứng thực nghiệm `research-mcp-per-project.md`
· ràng buộc đã đóng băng `spec-claude-account-switch.md`.

## Project Context Analysis

### Requirements Overview

**Functional Requirements — 34 FR, 7 nhóm, ánh xạ thành 6 thành phần kiến trúc:**

| Nhóm FR | Thành phần | Có mẫu sẵn trong repo? |
|---|---|---|
| FR1–8 Khai báo cấu hình | Bộ đọc cấu hình theo dự án, cache theo mtime | ✅ `_Accounts` trong `worker.py` — sao khuôn |
| FR9–13 Bí mật | Bơm credential vào env tiến trình con | ✅ `_project_git_env` — mở rộng, không phát minh |
| FR14–19 Thực thi | Dịch cấu hình → config native + 3 cờ CLI | ⚠️ mới, nhưng chỗ nối đã có (`_run_step_job`) |
| FR20–23 Giới hạn ghi | **Chưa có chỗ đặt** — xem "Vấn đề kiến trúc chưa giải" | ❌ |
| FR24–29 Quan sát | Đọc `system/init`, log, heartbeat, phân loại lỗi | ✅ `_StepWatch`, `_summarize_event`, `worker_heartbeat` |
| FR30–32 Cô lập | `--strict-mcp-config` + nghiệm thu từ `init` | ✅ đã kiểm chứng thực nghiệm |
| FR33–34 Vận hành | Metrics + công tắc tắt | ✅ `_run_streaming` đã trả metrics |

Năm trong bảy nhóm **đã có khuôn mẫu trong mã nguồn**. Đây là đặc điểm quan trọng nhất của tính năng
này: phần lớn công việc là nhân bản một mẫu đã chạy được, không phải thiết kế mới.

**Non-Functional Requirements dẫn dắt kiến trúc:**

- *Bí mật không qua API/DB* → quyết định ranh giới dữ liệu giữa host và dashboard. Đây là NFR định
  hình kiến trúc mạnh nhất; nó loại bỏ mọi thiết kế lưu cấu hình đầy đủ trong PostgreSQL.
- *Tương thích ngược tuyệt đối* → mọi thay đổi trong `_run_step_job` phải nằm sau một cổng: không có
  `mcp.json` thì không một tham số nào đổi.
- *Bộ tool độc lập tài khoản Claude* → cấu hình MCP phải được phân giải theo **dự án của job**, không
  theo phiên đăng nhập. Ràng buộc này tự thoả mãn nếu đọc từ `clients/<slug>/`.
- *Khởi động server ≤ 20s, ngắn hơn `STEP_TIMEOUT_S`* → cần một mốc thời gian riêng, nghĩa là phải
  phát hiện được thời điểm `init` tới trong luồng stream-json.
- *Nạp lại cấu hình ≤ 50ms, không chặn vòng claim 3s* → cache theo (mtime, size), đúng cách `_Accounts`
  đang làm.

### Scale & Complexity

- **Primary domain:** hạ tầng CLI/tiến trình trên host — không phải web, không phải API.
- **Complexity:** Medium. Không có thuật toán khó, không có mô hình dữ liệu mới, không có đồng thời.
  Độ khó nằm ở **ranh giới tin cậy** và **chẩn đoán lỗi**, không ở logic.
- **Thành phần kiến trúc ước tính:** 6 (bảng trên), trong đó 1 chưa có chỗ đặt.
- **Quy mô vận hành:** ≤ 20 dự án × ≤ 5 server, một máy, một worker, tuần tự một bước.

### Technical Constraints & Dependencies

Đã được kiểm chứng bằng thực nghiệm, không phải đọc tài liệu:

| Ràng buộc | Trạng thái |
|---|---|
| `--mcp-config` + `--strict-mcp-config` chạy headless trên Windows | ✅ đã chạy thật |
| `--strict-mcp-config` loại bỏ connector claude.ai | ✅ đã chạy thật |
| `acceptEdits` KHÔNG tự duyệt MCP tool; cần `--allowedTools mcp__<server>` | ✅ đã chạy thật |
| MCP server con **thừa kế env** của tiến trình Claude Code | ✅ đã chạy thật (2026-09-22) |
| Google service account + domain-wide delegation | ❌ phụ thuộc admin ngoài — đường găng |
| CLI ≥ 2.1.273 | ✅ máy đang dùng 2.1.273 |

### Cross-Cutting Concerns Identified

1. **Xử lý bí mật** — xuyên qua cấu hình, env, log, heartbeat, API, UI. Một chỗ hở là hỏng cả tính
   năng. Cần một điểm duy nhất chịu trách nhiệm che, không rải rác.
2. **Phân loại lỗi** — đụng thẳng vào bộ dò hết-quota/token-hỏng đã có. Rủi ro thật: MCP trả 401 làm
   worker đánh dấu oan tài khoản Pro. `worker.py:756` đã có phòng tuyến; tính năng này phải củng cố
   chứ không được làm yếu đi.
3. **Tương thích ngược** — mọi đường dẫn mã bị chạm đều phải có nhánh "không cấu hình = y hệt cũ".
4. **Nguồn sự thật là file, không phải DB** — dashboard ghi xuống file rồi đọc lại, chứ không giữ bản
   sao trong PostgreSQL. Cùng triết lý với `skills/`.

### Vấn đề kiến trúc chưa giải

**FR20–FR23 (giới hạn vùng ghi) không có chỗ đặt trong kiến trúc hiện tại.**

Claude Code không biết "folder ID nào được phép ghi" — với nó, `mcp__gdrive__create_file` chỉ là một
tool. `--allowedTools` cấp quyền ở mức *tool*, không ở mức *tham số*. Và `mcp.json` là cấu hình tĩnh,
nó không chặn được gì lúc chạy.

Nghĩa là việc kiểm tra vùng ghi **phải nằm bên trong MCP server**, hoặc không tồn tại. Đây là quyết
định kiến trúc lớn nhất của tính năng, và nó quyết định luôn việc ta *dùng* một server Google có sẵn
hay *viết* một cái. Giải ở Bước 4.

## Starter Template Evaluation

### Primary Technology Domain

**Brownfield — không có starter template.** Nền tảng đã chốt từ lâu và không đưa ra bàn lại: worker là
Python 3.11+ chỉ dùng thư viện chuẩn; dashboard là FastAPI + SQLAlchemy + PostgreSQL; frontend là React
+ TypeScript + Vite; cấu hình là TOML; nguồn sự thật là file trên đĩa.

Câu hỏi kiểu-starter thật sự của tính năng này là khác: **lấy MCP server Google có sẵn hay tự viết?**

### Starter Options Considered

Tra cứu tháng 9/2026:

| Lựa chọn | Đặc điểm | Đánh giá |
|---|---|---|
| `taylorwilsdon/google_workspace_mcp` | 12 dịch vụ, 120+ tool, OAuth 2.1 + service account DWD | Được duy trì tốt nhất. Quá nhiều tool so với nhu cầu — nhưng ta whitelist được |
| `us-all/google-drive-mcp-server` | ~96 tool, tập trung Drive/Docs/Sheets/Slides, hỗ trợ DWD | Sát nhu cầu nhất về phạm vi |
| `obe711/google-workspace-mcp` | **Chỉ đọc**, service account + DWD | Đáng cân nhắc nếu về sau tách một hồ sơ chỉ-đọc |
| Tự viết | Kiểm soát tuyệt đối | **Loại.** Viết lại client Google API là công việc lớn, không có giá trị khác biệt |

**Quyết định: dùng server có sẵn, không tự viết.** Nhưng kèm hai điều kiện bắt buộc bên dưới.

### Điều kiện bắt buộc khi dùng server bên thứ ba

1. **Ghim phiên bản, cài sẵn, không `npx -y` lúc chạy.** `npx -y <package>` tải bản mới nhất tại thời
   điểm spawn — đúng rủi ro chuỗi cung ứng đã ghi trong PRD. Server phải được cài sẵn tại một đường
   dẫn cố định trên host, ghim commit/phiên bản, và `mcp.json` trỏ thẳng vào đó.
2. **Đọc mã trước khi cắm vào dự án khách.** Nó sẽ chạy trên máy vận hành với credential của khách.

### Kiến trúc quyền: đẩy ranh giới xuống Google, không tự canh trong mã

Đây là thay đổi lớn nhất so với giả định ban đầu của PRD.

PRD giả định phải **domain-wide delegation** (DWD) và tự kiểm tra vùng ghi trong mã. Cả hai đều không
cần thiết, và cả hai đều tệ hơn phương án thật:

**DWD là công cụ sai.** DWD cho phép service account *mạo danh bất kỳ người dùng nào trong domain* —
quyền lớn khủng khiếp so với nhu cầu, và nó cần admin của khách bật, tạo ra phụ thuộc đường găng.

**Service account thường thì không cần admin nào cả.** Nó có địa chỉ email riêng; khách chỉ việc chia
sẻ đúng thư mục cho email đó, y như chia sẻ cho một đồng nghiệp. Google tự chặn mọi thứ ngoài phạm vi
đã chia sẻ. **Ranh giới đọc do Google cưỡng chế, không do mã của ta.**

Việc này khớp chính xác với Journey 5 trong PRD — và nó **xoá bỏ phụ thuộc Workspace admin**, tức là
lát 1B không còn nằm chờ ai nữa.

**Nhưng ghi thì có một cái bẫy đã được xác nhận:** service account **không có hạn mức lưu trữ và không
sở hữu được file**. Ghi thẳng vào My Drive của khách sẽ hỏng với `storageQuotaExceeded`, kể cả khi thư
mục đã được chia sẻ quyền Editor.

Đường ghi khả dụng, theo thứ tự ưu tiên:

| Cách | Cần gì từ khách | Ràng buộc |
|---|---|---|
| **A. Shared Drive** (khuyến nghị) | Tạo Shared Drive (hoặc thư mục trong đó), thêm service account làm Content Manager | Cần gói Workspace có Shared Drive. File thuộc sở hữu tổ chức, không đụng hạn mức |
| **B. DWD mạo danh người dùng** | Admin bật domain-wide delegation | Quyền quá rộng, phụ thuộc admin. **Chỉ dùng khi A bất khả thi** |

**Hệ quả cho FR20–FR23 — vấn đề "chưa có chỗ đặt" ở Bước 2 đã giải:**

| Yêu cầu | Cưỡng chế ở đâu | Ta phải viết gì |
|---|---|---|
| FR20 — không ghi/đọc ngoài vùng | **Google**, qua phạm vi chia sẻ | Không gì cả |
| FR21 — không ghi đè, không xoá | **Claude Code**, qua `--allowedTools` chỉ gồm tool tạo/append | Không gì cả |
| FR22 — nhật ký từng lần ghi | Worker, khi đọc `tool_use` trong stream-json | Một hàm nhỏ |
| FR23 — giải thích được cho khách | Chính trang chia sẻ của Google là câu trả lời | Không gì cả |

Không có lớp canh gác tự viết nào. Hai điểm cưỡng chế đều nằm ngoài mã của ta, đều kiểm chứng được từ
bên ngoài, và đều là thứ khách tự nhìn thấy được. Đây là phương án nhàm chán nhất, và vì thế là phương
án đúng.

### Architectural Decisions Inherited (không bàn lại)

| Quyết định | Nguồn |
|---|---|
| Worker chỉ dùng thư viện chuẩn Python — không thêm dependency | `worker.py` hiện tại |
| Cấu hình dạng TOML cho bí mật, JSON cho khai báo server | `settings.local.toml` đã có; JSON là định dạng MCP |
| Nguồn sự thật là file trên đĩa, không phải PostgreSQL | Cùng triết lý `skills/` |
| Trạng thái đi ké heartbeat, không thêm vòng poll | `spec-claude-account-switch.md` |
| Tuần tự một bước một lúc | Chính sách trong `README.md` |

## Core Architectural Decisions

### Decision Priority Analysis

**Critical — chặn triển khai nếu chưa chốt:** AD1–AD7
**Important — định hình kiến trúc:** AD8–AD12
**Deferred — có chủ ý, sang Phase 2+:** xem cuối mục

### AD1 — Hai file cấu hình, cắt theo ranh giới bí mật

`clients/<slug>/mcp.json` giữ khai báo server (dashboard sửa được). `clients/<slug>/settings.local.toml`
mục `[mcp.<server>]` giữ **đường dẫn tới** credential (chỉ sửa tay trên host).

*Vì sao:* NFR "bí mật không qua API/DB" là ràng buộc đã đóng băng. Một file duy nhất thì hoặc bí mật
lọt vào đường ghi của dashboard, hoặc dashboard không sửa được gì.

*Ảnh hưởng:* FR1–FR13 · bộ đọc cấu hình · API dashboard.

### AD2 — Credential đi qua env của tiến trình con, không qua file cấu hình

Worker đặt `GOOGLE_SERVICE_ACCOUNT_KEY_PATH=<path>` vào env khi spawn, đúng khuôn `GH_TOKEN` trong
`_project_git_env`.

*Vì sao:* **đã kiểm chứng thực nghiệm** (2026-09-22) rằng MCP server con thừa kế env của tiến trình
Claude Code. Nhờ đó `mcp.json` không chứa bí mật nào — kể cả khi ai đó lỡ commit nó.

*Ảnh hưởng:* FR10, FR11, FR13 · `_run_step_job`.

### AD3 — Config native truyền bằng chuỗi JSON inline, không file tạm

Worker dựng config native trong bộ nhớ và truyền thẳng vào `--mcp-config "<json>"`.

*Vì sao:* **đã kiểm chứng** chuỗi inline hoạt động. Không file tạm nghĩa là không có vòng đời file để
quản, không rác để dọn khi worker chết giữa chừng, và không có gì chạm đĩa. Dòng lệnh cũng sạch vì bí
mật đi đường env (AD2).

*Giới hạn đã biết:* dòng lệnh Windows tối đa 32767 ký tự. Với ≤ 5 server/dự án thì không tới ngưỡng;
nếu về sau chạm thì rơi về file tạm.

### AD4 — Cưỡng chế quyền nằm NGOÀI mã của ta

| Ranh giới | Ai cưỡng chế |
|---|---|
| Đọc/ghi ngoài vùng cho phép | **Google**, qua phạm vi chia sẻ của service account |
| Ghi đè, xoá | **Claude Code**, qua `--allowedTools` không chứa tool sửa/xoá |
| Nhật ký thao tác ghi | Worker, đọc `tool_use` từ stream-json |

*Vì sao:* server nền không có cơ chế giới hạn folder ID (đã xác nhận khi đọc tài liệu của nó). Tự viết
lớp canh gác nghĩa là ta phải chặn đúng ở mọi tool, mọi tham số, mọi phiên bản server — một cuộc đua
không thắng được. Hai điểm cưỡng chế trên đều nằm ngoài tầm với của agent, đều kiểm chứng được từ bên
ngoài, và ranh giới đọc thì chính khách hàng nhìn thấy trên trang chia sẻ của họ.

*Ảnh hưởng:* FR20–FR23. **Xoá bỏ toàn bộ lớp canh gác tự viết** khỏi phạm vi.

### AD5 — Hồ sơ quyền dựng sẵn, không chọn tool lẻ

Ba hồ sơ: `read-only` · `read-create` · `read-write`. Mỗi hồ sơ là một danh sách tool cố định, dịch
thành `--allowedTools`.

*Vì sao:* server nền có ~96 tool. Bắt người vận hành tick từng cái là mời gọi sai sót, và cái sai ở
đây là bật nhầm tool xoá file của khách. Hồ sơ cũng là thứ giải thích được cho khách trong một câu —
đúng nhu cầu của Journey 5.

*MVP dùng:* `read-create` (đọc mọi thứ trong vùng, chỉ tạo mới, không sửa không xoá) — khớp FR21.

*Ảnh hưởng:* FR4, FR21 · UI dashboard · danh sách mẫu.

### AD6 — Server nền: `@us-all/google-drive-mcp`, ghim phiên bản, cài sẵn

*Vì sao:* phạm vi đúng nhu cầu (Drive/Docs/Sheets/Slides, không kèm Gmail/Calendar), hỗ trợ service
account, truyền `supportsAllDrives: true` nên làm việc được với Shared Drive.

**Bắt buộc:** cài sẵn một phiên bản đã ghim tại đường dẫn cố định trên host, `mcp.json` trỏ thẳng vào
`node <path>/dist/index.js`. **Không dùng `npx -y @us-all/google-drive-mcp`** — nó tải bản mới nhất tại
thời điểm spawn, đúng rủi ro chuỗi cung ứng đã ghi trong PRD. Đọc mã trước khi cắm vào dự án khách.

*Biến môi trường server đọc:* `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`. **Cố ý KHÔNG đặt**
`GOOGLE_IMPERSONATE_USER` — đó là đường DWD mà AD7 loại bỏ.

### AD7 — Đường ghi duy nhất ở MVP: Shared Drive. Không dùng DWD

Khách tạo Shared Drive (hoặc thư mục trong đó), thêm email service account làm Content Manager.

*Vì sao:* service account **không có hạn mức lưu trữ và không sở hữu được file** — ghi vào My Drive
của khách sẽ hỏng với `storageQuotaExceeded` kể cả khi đã chia sẻ quyền Editor. Shared Drive thì file
thuộc sở hữu tổ chức nên không đụng hạn mức. DWD giải quyết được nhưng phải cho service account quyền
mạo danh người dùng trong domain — quyền lớn hơn nhu cầu rất nhiều, và cần admin của khách bật.

*Hệ quả phải chấp nhận:* khách dùng Gmail cá nhân hoặc gói Workspace không có Shared Drive thì
**không có đường ghi**. Với khách đó, cắm hồ sơ `read-only` và ghi rõ lý do. Không lặng lẽ rơi về DWD.

*Lợi ích kèm theo:* **không còn phụ thuộc Workspace admin** — lát 1B trong PRD hết nằm chờ.

### AD8 — Dashboard ghi thẳng xuống file, không qua DB

API ghi `clients/<slug>/mcp.json` trực tiếp; `docker-compose.yml` mount `../clients:/clients` cho ghi.

*Vì sao:* nguồn sự thật là file — cùng triết lý `skills/` đã chạy, `git diff` vẫn đọc ra, sửa bằng
editor vẫn được. Giữ bản sao trong PostgreSQL là tạo ra hai nguồn sự thật để rồi lệch nhau.

### AD9 — Mở rộng `_StepWatch`, tuyệt đối không viết watcher mới

Thêm trường nhận diện nguồn lỗi MCP; **giữ nguyên** toàn bộ regex quota/auth hiện có.

*Vì sao:* `worker.py:756` đã có phòng tuyến chống việc 401 của MCP bị quy thành token Claude hỏng. Hai
bộ theo dõi song song trên cùng một luồng sự kiện là cách chắc chắn nhất để làm hỏng nó.

*Ảnh hưởng:* FR26, FR28 · test hồi quy bắt buộc.

### AD10 — Mốc thời gian riêng cho khởi động server

`_run_streaming` đặt hạn 20 giây cho sự kiện `system/init`; quá hạn thì kết thúc tiến trình và báo lỗi
"server không khởi động được", không chờ tới `STEP_TIMEOUT_S`.

### AD11 — Cache cấu hình theo (mtime, size)

Sao khuôn `_Accounts`: đọc lại khi file đổi, file hỏng thì giữ bản cũ + cảnh báo terminal.

### AD12 — Trạng thái MCP đi ké heartbeat của `/claim`

Không endpoint mới, không vòng poll mới — đúng cách snapshot tài khoản Claude đang làm.

### Deferred Decisions

| Hoãn | Vì sao |
|---|---|
| Domain-wide delegation | AD7 làm nó không cần thiết. Chỉ mở lại nếu gặp khách không có Shared Drive *và* việc đó đáng |
| Ghi đè / xoá tài liệu khách | Rủi ro cao nhất trong tính năng; cần bước xác nhận mà MVP chưa có |
| MCP riêng theo từng agent | Khuôn `[git.be1]` đã có sẵn, thêm lúc nào cũng được |
| Danh sách trắng package | AD6 đã hạ rủi ro bằng ghim phiên bản; danh sách trắng đầy đủ là việc lớn hơn |
| Server thứ hai không phải Google | Chính là phép thử của "hạ tầng chung", nhưng không cần cho MVP |

### Decision Impact Analysis

**Thứ tự triển khai** (mỗi bước nghiệm thu được độc lập):

1. AD11 bộ đọc cấu hình + AD1 lược đồ hai file — nghiệm thu bằng unit test, chưa cần CLI
2. AD2 + AD3 dựng lệnh và bơm env — nghiệm thu bằng `envprobe` server tí hon đã có
3. AD5 hồ sơ quyền + AD10 mốc thời gian init — nghiệm thu bằng server filesystem vô hại
4. AD9 phân loại lỗi + test hồi quy — **cổng chặn: không qua thì không đi tiếp**
5. AD8 + AD12 dashboard và trạng thái
6. AD6 + AD7 cắm Google thật vào một dự án

Bước 1–5 là lát 1A trong PRD, không cần Google. Bước 6 là lát 1B.

**Phụ thuộc chéo:**

- AD2 cho phép AD3: vì bí mật đi env nên config inline mới an toàn
- AD4 phụ thuộc AD7: ranh giới đọc chỉ cưỡng chế được khi khách chia sẻ đúng phạm vi
- AD5 hiện thực hoá nửa còn lại của AD4: hồ sơ chính là `--allowedTools`
- AD9 là điều kiện an toàn cho mọi thứ còn lại: sai phân loại lỗi thì tài khoản Pro bị đánh dấu oan

## Implementation Patterns & Consistency Rules

Các hạng mục mặc định của bước này (đặt tên bảng DB, wrapper API, state management frontend) **không
áp dụng** — brownfield, quy ước đã tồn tại trong mã. Dưới đây là **11 điểm xung đột thật** của riêng
tính năng này: những chỗ hai agent dev sẽ chọn khác nhau nếu không chốt trước.

### Naming Patterns

**Khoá trong `mcp.json` — chốt cứng:**

```json
{ "enabled": true,
  "servers": { "<ten-server>": {
    "template": "<ten-mau>", "enabled": true,
    "profile": "read-create",
    "declared_write_scope": { "shared_drive_id": "..." } } } }
```

- Khoá gốc là `servers`, **không** phải `mcpServers` — cố ý khác định dạng native để không ai nhầm
  file này với config của Claude Code (AD1: đây là lược đồ của ta, worker dịch sang native).
- Mọi khoá `snake_case`.
- `enabled: true/false`, **không** dùng `disabled`.

**Tên server:** chỉ `[a-z0-9_-]`. Nó chui thẳng vào tên tool `mcp__<server>__<tool>` và vào tham số
`--allowedTools`; ký tự lạ sẽ hỏng lặng lẽ.

**Mục TOML bí mật:** `[mcp.<server>]`, khớp khuôn `[git.<agent>]` đã có. **Không** `[mcp_gdrive]`.

**Trường API:** `snake_case`, khớp `claude_account` / `claude_auto_switch` đã có trong
`schemas.py`. Tên mới: `mcp_servers`, `mcp_status`.

**Lớp CSS:** tiền tố `.mcp-*`, append cuối `App.css` — đúng cách `.claude-acc-*` đã làm.

**File test:** `tests/test_worker_mcp.py`, khớp `tests/test_worker_accounts.py`.

### Format Patterns

**Dòng log sống** — phải khớp giọng đang có (`🔑 Tài khoản Claude: pro-2`, `🔁 ... → ...`):

| Tình huống | Dòng log |
|---|---|
| Server đã nối | `🔌 MCP: gdrive · 6 tool` |
| Nhiều server | một dòng mỗi server, không gộp |
| Ghi ra ngoài | `📝 gdrive ghi: <ten> (id=<id>)` |
| Hỏng | `❌ <nguyên nhân>. <chỗ cần sửa>.` |

**Thông báo lỗi — luôn hai vế: nguyên nhân + chỗ sửa.** Ví dụ đúng:

> `❌ Server 'gdrive' chưa được cấp quyền gọi tool. Bật hồ sơ quyền ở Dashboard → udom → MCP, hoặc sửa "profile" trong clients/udom/mcp.json.`

Ví dụ sai: `❌ Permission denied` · `❌ MCP error` · `❌ Không gọi được tool`.

### Process Patterns

**Che bí mật — dùng `_redact` đã có ở [worker.py:713](worker.py#L713), không viết hàm mới.** Mọi
đường dữ liệu rời worker đã đi qua nó. Thêm giá trị cần che vào nguồn của `_redact`, đừng thêm điểm
che thứ hai — hai điểm che nghĩa là sẽ có một điểm bị quên.

**Đọc TOML: `tomllib` của thư viện chuẩn.** Worker không thêm dependency. `dashboard/api/system_config.py`
cũng đã dùng `tomllib`.

**Dashboard API không được import `worker.py`.** Hai tiến trình khác nhau, một trong Docker một trên
host. Logic đọc/ghi `mcp.json` dùng chung thì **chép**, đừng import — và giữ lược đồ ở một chỗ duy
nhất là tài liệu này.

**Cổng tương thích ngược.** Mọi nhánh mã mới đặt sau một điều kiện duy nhất:

```python
servers = _mcp_servers(job.get("client_folder"))   # [] neu khong co file / khong server nao bat
if servers:
    cmd += [...]      # chi o day moi co tham so moi
```

Không rải `if` rác khắp nơi. Một cổng, kiểm được bằng một test.

**Ngôn ngữ trong mã.** Bình luận và docstring bằng tiếng Việt, **theo đúng kiểu của hàm xung quanh**:
một số hàm trong `worker.py` viết tiếng Việt không dấu (`_resolve_claude`), số khác có dấu đầy đủ.
Không "chuẩn hoá" lại file đang có — chỉ khớp phần mình chạm vào.

### Enforcement Guidelines

**Mọi agent dev BẮT BUỘC:**

- Không thêm điểm che bí mật thứ hai — chỉ `_redact`
- Không thêm dependency vào `worker.py`
- Không sửa regex quota/auth hiện có trong `_StepWatch` (AD9)
- Không dùng `npx -y` trong bất kỳ `mcp.json` mẫu nào (AD6)
- Mọi tham số CLI mới nằm sau cổng `if servers:`
- Thông báo lỗi luôn hai vế: nguyên nhân + chỗ sửa

**Cách kiểm tra:**

| Quy tắc | Kiểm bằng |
|---|---|
| Không rò bí mật | Test: chạy bước với credential giả, grep giá trị đó trong toàn bộ output/API/DB |
| Tương thích ngược | Chạy lại `tests/test_worker_accounts.py` — 0 thay đổi kết quả |
| Không `npx -y` | grep trong thư mục mẫu |
| Không `--dangerously-skip-permissions` | grep toàn repo |
| Phân loại lỗi đúng | Test bảng bốn nguyên nhân, mỗi nguyên nhân một ca |

### Anti-Patterns

- ❌ Ghi credential vào `mcp.json` "cho tiện" — phá AD1, AD2 và toàn bộ NFR bảo mật
- ❌ Tự viết lớp kiểm tra folder ID trong worker — phá AD4, và không bao giờ chặn đủ
- ❌ Lưu bản sao cấu hình trong PostgreSQL để "đọc cho nhanh" — hai nguồn sự thật
- ❌ Thêm vòng poll mới cho trạng thái MCP — đã có heartbeat (AD12)
- ❌ Bắt người dùng restart worker sau khi đổi cấu hình — phá FR6
- ❌ Gộp lỗi MCP và lỗi tài khoản Claude vào một nhánh xử lý — phá AD9, đánh dấu oan tài khoản Pro

## Project Structure & Boundaries

Brownfield: không dựng cây thư mục mới. Dưới đây là **chính xác những file bị chạm và file được thêm**.

### Cây thay đổi

```
ai_team_clean/
├── worker.py                              ← SỬA (lõi tính năng)
│     _McpConfig        (THÊM)  đọc mcp.json + settings.local.toml, cache (mtime,size)
│     _mcp_env          (THÊM)  dựng env credential — khuôn _project_git_env
│     _mcp_native       (THÊM)  dịch sang config native, trả chuỗi JSON inline
│     _mcp_profiles     (THÊM)  ho so quyen -> danh sach tool
│     _run_step_job     (SỬA)   cổng `if servers:` — nối 3 cờ CLI
│     _run_streaming    (SỬA)   hạn 20s cho system/init
│     _StepWatch        (SỬA)   thêm nhận diện nguồn lỗi MCP (KHÔNG đụng regex cũ)
│     _redact           (SỬA)   nhận thêm giá trị bí mật của MCP
│
├── config/
│   └── mcp_templates.toml                 ← THÊM  danh sách mẫu server + hồ sơ quyền
│
├── clients/<slug>/
│   ├── mcp.json                           ← THÊM (mỗi dự án, dashboard ghi được)
│   └── settings.local.toml                ← SỬA  thêm mục [mcp.<server>]
│
├── tests/
│   ├── test_worker_accounts.py            ← KHÔNG SỬA (dùng làm test hồi quy)
│   └── test_worker_mcp.py                 ← THÊM
│
├── dashboard/
│   ├── docker-compose.yml                 ← SỬA  mount ../clients:/clients cho ghi
│   ├── api/
│   │   ├── routers/mcp.py                 ← THÊM  CRUD cấu hình MCP theo dự án
│   │   ├── routers/workflow_jobs.py       ← SỬA   claim trả mcp_servers; nhận mcp_status
│   │   ├── schemas.py                     ← SỬA   McpServerOut, McpConfigIn, mcp_status
│   │   ├── worker_heartbeat.py            ← SỬA   giữ snapshot trạng thái MCP
│   │   └── main.py                        ← SỬA   đăng ký router mcp
│   └── src/
│       ├── components/ProjectMcp.tsx      ← THÊM  tab MCP của dự án
│       ├── components/Projects.tsx        ← SỬA   gắn tab
│       ├── hooks/useMcp.ts                ← THÊM
│       ├── types.ts                       ← SỬA
│       └── App.css                        ← SỬA   append .mcp-*
│
└── vendor/mcp/google-drive-mcp/           ← THÊM  server đã ghim phiên bản, cài sẵn
```

**Không đụng tới:** `main.py`, `ai_team/` (làn A — pipeline OpenCode không dùng MCP), `skills/`,
`ActiveTasks.tsx`, `RunConsole.tsx`.

### Requirements to Structure Mapping

| Nhóm FR | Sống ở đâu |
|---|---|
| FR1–FR8 khai báo cấu hình | `worker.py::_McpConfig` · `routers/mcp.py` · `ProjectMcp.tsx` · `config/mcp_templates.toml` |
| FR9–FR13 bí mật | `worker.py::_mcp_env` + `_redact` · `clients/<slug>/settings.local.toml` |
| FR14–FR19 thực thi | `worker.py::_run_step_job` (cổng) · `_mcp_native` · `_run_streaming` (hạn init) |
| FR20–FR23 giới hạn ghi | **Ngoài mã:** phạm vi chia sẻ Google + `_mcp_profiles` → `--allowedTools`. Trong mã chỉ có nhật ký ghi ở `_StepWatch` |
| FR24–FR29 quan sát | `_StepWatch` · `progress.add` · `worker_heartbeat.py` · `ProjectMcp.tsx` |
| FR30–FR32 cô lập | `_mcp_native` (`--strict-mcp-config`) · nghiệm thu từ `system/init` |
| FR33–FR34 vận hành | metrics sẵn có của `_run_streaming` · cờ `enabled` trong `mcp.json` |

### Architectural Boundaries

**Ranh giới tin cậy — quan trọng nhất:**

```
┌─ Host (tin cậy) ─────────────────────────────────────────┐
│  settings.local.toml  →  đường dẫn credential            │
│  file service account JSON  (KHÔNG BAO GIỜ di chuyển)    │
│  worker.py  →  bơm vào env tiến trình con                │
│       │                                                   │
│       ├─→ claude -p  ─→  MCP server (thừa kế env)        │
│       │                        │                          │
└───────┼────────────────────────┼──────────────────────────┘
        │ HTTP (không bí mật)    │ HTTPS
        ▼                        ▼
   Dashboard/PostgreSQL     Google (cưỡng chế phạm vi)
   chỉ thấy: tên, trạng     chỉ trả về thứ đã được
   thái, có/thiếu cred      chia sẻ cho service account
```

**Ranh giới tiến trình:** `dashboard/api` (Docker) và `worker.py` (host) **không import lẫn nhau**.
Giao tiếp duy nhất qua HTTP API đã có và qua file trong `clients/`.

**Ranh giới dữ liệu:** `mcp.json` là nguồn sự thật. PostgreSQL **không** giữ bản sao cấu hình —
chỉ giữ trạng thái tạm thời trong heartbeat (in-memory, không bền).

### Integration Points

| Điểm | Giao thức | Ghi chú |
|---|---|---|
| worker → Claude Code | tham số dòng lệnh + env | `--mcp-config` chuỗi inline (AD3) |
| Claude Code → MCP server | stdio, JSON-RPC | server thừa kế env của tiến trình cha (đã kiểm chứng) |
| MCP server → Google | HTTPS, service account | phạm vi do Google cưỡng chế (AD4, AD7) |
| worker → dashboard | HTTP, body của `/claim` | đi ké, không endpoint mới (AD12) |
| dashboard → `clients/` | ghi file qua volume mount | `../clients:/clients` không `:ro` (AD8) |

### Data Flow — một bước có MCP, từ đầu tới cuối

1. Worker `/claim` một job → nhận `client_folder`
2. `_McpConfig` đọc `clients/<slug>/mcp.json` (cache theo mtime) → danh sách server đang bật
3. Không có server nào → **thoát nhánh, chạy y hệt hôm nay**
4. `_mcp_env` đọc `[mcp.<server>]` trong `settings.local.toml` → `GOOGLE_SERVICE_ACCOUNT_KEY_PATH`
5. `_mcp_native` dựng chuỗi JSON config; `_mcp_profiles` dựng danh sách `--allowedTools`
6. Spawn `claude -p` với env đã trộn (git + tài khoản Claude + MCP)
7. `system/init` tới trong ≤ 20s → log `🔌 MCP: gdrive · 6 tool`; quá hạn → kết thúc, báo lỗi
8. Agent gọi tool → Google cho hoặc từ chối theo phạm vi chia sẻ
9. `_StepWatch` thấy `tool_use` của tool ghi → ghi nhật ký kèm ID đích
10. Kết thúc: `_redact` toàn bộ output trước khi gửi API

## Architecture Validation Results

### Coherence Validation

**Tương thích giữa các quyết định:** không có mâu thuẫn. Ba quyết định đã kiểm chứng bằng thực nghiệm
(AD2 env thừa kế, AD3 chuỗi inline, và cơ chế cờ CLI) khớp nhau: vì bí mật đi đường env nên config
inline mới an toàn; vì config inline nên không cần vòng đời file tạm.

**Nhất quán mẫu:** các mẫu ở Bước 5 đều bắt nguồn từ mã đang chạy (`_redact`, `_Accounts`, `[git.*]`,
`.claude-acc-*`, `tomllib`), không có quy ước nào bịa mới.

**Cấu trúc khớp quyết định:** AD8 (file là nguồn sự thật) là lý do `mcp.json` nằm trong `clients/` chứ
không trong DB; AD4 là lý do **không có** module canh gác nào trong cây thư mục.

### Requirements Coverage Validation

**34/34 FR có chỗ đứng kiến trúc**, nhưng 3 FR được phủ *khác* với cách PRD hình dung. Ghi rõ ở đây để
agent dev không hiểu sai:

| FR | Trạng thái | Ghi chú |
|---|---|---|
| FR4 giới hạn tool | ⚠️ **thu hẹp có chủ ý** | AD5 chọn hồ sơ dựng sẵn thay vì tick từng tool. Phủ được ý định (giới hạn quyền), bỏ bớt độ linh hoạt |
| FR18 từ chối server đòi OAuth tương tác | ⚠️ **phủ một phần** | Không có cách phát hiện tổng quát. Thay bằng: MVP chỉ chạy server trong danh sách mẫu (toàn bộ dùng credential tĩnh); hạn 20s của AD10 bắt được trường hợp treo |
| FR11 che bí mật | ✅ **bề mặt nhỏ hơn dự tính** | Thiết kế chỉ truyền *đường dẫn*, nội dung file service account không bao giờ đi vào tiến trình của ta. Vẫn che đường dẫn trong output API để không lộ bố cục host |

**NFR:** tất cả có chỗ, trừ hai điều kiện tiền đề chưa tồn tại — xem Gap G4, G5.

### Gap Analysis Results

**G1 — `write_scope` là KHAI BÁO, không phải hàng rào. (Quan trọng)**

Trong `mcp.json`, `write_scope` chỉ dùng để (a) hiển thị cho người vận hành, (b) trả lời câu hỏi của
khách ở FR23, (c) làm thư mục cha mặc định. **Nó không chặn gì cả.** Hàng rào thật là phạm vi chia sẻ
phía Google (AD4/AD7).

*Vì sao phải nói to:* một agent dev đọc lướt sẽ tưởng đây là kiểm tra bảo mật và viết code dựa vào nó,
hoặc tệ hơn, nới lỏng phần chia sẻ Google vì "đã có `write_scope` canh rồi". Cả hai đều dẫn tới tính
năng *trông có vẻ* an toàn.

*Xử lý:* đổi tên khoá thành **`declared_write_scope`** để cái tên tự nói lên bản chất, và ghi một dòng
chú thích ngay trong file mẫu.

**G2 — FR34 (tắt toàn bộ MCP của dự án bằng một thao tác) chưa có chỗ trong lược đồ. (Quan trọng)**

Lược đồ hiện chỉ có `enabled` theo từng server; 5 server là 5 lần bấm.

*Xử lý:* thêm khoá `enabled` ở **gốc** `mcp.json`. Sai thì mặc định `true`. Worker kiểm khoá gốc trước,
`false` là thoát nhánh ngay như không có file.

```json
{ "enabled": true, "servers": { "gdrive": { "enabled": true, ... } } }
```

**G3 — Không có chỗ nào kiểm phiên bản CLI ≥ 2.1.273. (Quan trọng)**

NFR yêu cầu "phiên bản thấp hơn phải báo rõ, không âm thầm bỏ cờ". Chưa thành phần nào nhận việc.

*Xử lý:* `_McpConfig` kiểm một lần lúc worker khởi động (`claude --version`), nhớ kết quả. Thấp hơn
ngưỡng **và** có dự án khai MCP → in cảnh báo lúc khởi động và fail bước có MCP với lý do rõ, thay vì
chạy tiếp mà không có tool.

**G4 — Baseline hiệu năng chưa tồn tại. (Quan trọng)**

Hai NFR (+15% thời gian, +10% token) đo so với baseline, mà baseline chưa ai đo.

*Xử lý:* đo baseline là **việc đầu tiên của lát 1A**, trước khi viết dòng mã nào — chạy 10 lần một
bước tiêu biểu trên một dự án hiện có, ghi lại thời gian và token. Không có baseline thì hai NFR đó
không nghiệm thu được, chỉ là chữ.

**G5 — Khách không có Shared Drive thì mất đường ghi. (Đã chấp nhận, không phải lỗ hổng)**

AD7 đã ghi. Nhắc lại ở đây để lúc nghiệm thu không ai coi là bug.

**G6 — Thư mục `vendor/mcp/` chưa có trong `.gitignore`. (Nhỏ)**

Server đã cài (kèm `node_modules`) không nên vào git.

*Xử lý:* thêm `vendor/mcp/` vào `.gitignore`; ghi phiên bản đã ghim vào `config/mcp_templates.toml`
để tái lập được.

### Validation Issues Addressed

G1, G2, G3, G6 đã có cách xử lý cụ thể ở trên và **được coi là một phần của kiến trúc này**, không
phải việc để sau. G4 chuyển thành việc đầu tiên trong thứ tự triển khai. G5 là giới hạn đã chấp nhận.

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Bối cảnh dự án đã phân tích (brownfield, 5/7 nhóm FR có mẫu sẵn trong mã)
- [x] Quy mô và độ phức tạp đã đánh giá (Medium — khó ở ranh giới tin cậy, không ở logic)
- [x] Ràng buộc kỹ thuật đã xác định — 4/6 đã **kiểm chứng bằng thực nghiệm**
- [x] Mối quan tâm xuyên suốt đã ánh xạ (4 mối)

**Architectural Decisions**
- [x] 12 quyết định (AD1–AD12), mỗi cái có lý do và phạm vi ảnh hưởng
- [x] Server nền đã chọn và ghim; biến môi trường đã xác minh từ tài liệu của nó
- [x] 5 quyết định hoãn có chủ ý, kèm lý do
- [x] Hiệu năng: có ngưỡng, nhưng **phụ thuộc baseline chưa đo (G4)**

**Implementation Patterns**
- [x] 11 điểm xung đột đã chốt
- [x] Quy ước đặt tên lấy từ mã đang chạy, không bịa
- [x] Mẫu xử lý lỗi: luôn hai vế nguyên nhân + chỗ sửa
- [x] 6 anti-pattern, mỗi cái nêu rõ phá vỡ điều gì

**Project Structure**
- [x] Cây thay đổi đầy đủ: file nào sửa, file nào thêm, file nào cấm đụng
- [x] Ranh giới tin cậy có sơ đồ
- [x] 34 FR ánh xạ về vị trí cụ thể
- [x] Luồng dữ liệu 10 bước từ claim tới redact

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION** — với điều kiện G4 (đo baseline) làm trước.

**Confidence Level: CAO** đối với lát 1A, **TRUNG BÌNH** đối với lát 1B.

Lý do chênh lệch: mọi cơ chế của 1A đã được chạy thật trên đúng máy, đúng hệ điều hành, đúng phiên bản
CLI. Còn 1B phụ thuộc hai thứ chưa chạm được: hành vi thực tế của server bên thứ ba, và cấu hình
Shared Drive phía khách.

**Điểm mạnh:**

- Bốn cơ chế cốt lõi **đã kiểm chứng bằng thực nghiệm**, không phải đọc tài liệu rồi tin
- Cưỡng chế bảo mật nằm ngoài mã của ta → không có lớp canh gác tự viết để mà viết sai
- 5/7 nhóm FR nhân bản mẫu đã chạy trong repo
- Không phụ thuộc Workspace admin (AD7 gỡ được đường găng mà PRD tưởng là bắt buộc)

**Cần cải thiện về sau:**

- Danh sách trắng package (rủi ro chuỗi cung ứng mới hạ bằng ghim phiên bản, chưa khoá hẳn)
- Chưa có cách tổng quát phát hiện server đòi OAuth tương tác (G/FR18)
- Ghi đè và xoá vẫn nằm ngoài tầm với

### Implementation Handoff

**Mọi agent dev BẮT BUỘC:**

- Đọc mục *Implementation Patterns* trước khi viết dòng đầu tiên — nhất là 6 anti-pattern
- Không tự thêm lớp kiểm tra vùng ghi (G1)
- Không sửa regex quota/auth trong `_StepWatch` (AD9)
- Chạy `tests/test_worker_accounts.py` sau mỗi thay đổi worker — 0 khác biệt

**Việc đầu tiên: đo baseline (G4).** Chạy 10 lần một bước tiêu biểu trên một dự án hiện có, ghi lại
thời gian và token vào tài liệu này. Chưa có con số đó thì hai NFR hiệu năng không nghiệm thu được.

**Việc thứ hai:** `_McpConfig` + lược đồ hai file, nghiệm thu bằng unit test, chưa cần CLI.
