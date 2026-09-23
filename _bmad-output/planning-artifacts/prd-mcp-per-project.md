---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation (skipped)', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments:
  - '_bmad-output/planning-artifacts/research-mcp-per-project.md'
  - '_bmad-output/implementation-artifacts/spec-claude-account-switch.md'
  - 'README.md'
  - 'dashboard/README.md'
  - '.claude/README.md'
documentCounts:
  briefs: 0
  research: 1
  brainstorming: 0
  projectDocs: 4
workflowType: 'prd'
status: 'complete'
project_name: 'ai_team_clean'
feature: 'MCP per-project'
projectContext: 'brownfield'
classification:
  projectType: cli_tool
  domain: general
  complexity: Medium
  projectContext: brownfield
  note: 'cli_tool nhung KHONG bo qua cac muc giao dien — dashboard sua duoc cau hinh MCP'
decisions:
  scope: 'Ha tang MCP dung chung theo tung du an; Google la ca dau tien'
  accountRotation: 'Xoay vong nhieu tai khoan Claude Pro VAN CON hieu luc'
  configSurface: 'Dashboard sua duoc cau hinh MCP'
  secretSplit: 'De xuat: cau hinh trong clients/<slug>/mcp.json (dashboard sua duoc); bi mat trong settings.local.toml [mcp.<server>] (khong qua API/DB) — cho xac nhan lai'
decisions_step03:
  readWrite: 'Doc VA ghi ngay tu MVP — ghi bi gioi han vung khai truoc, MVP khong ghi de'
  primaryMetric: 'Het dan tay tai lieu khach (>=90% buoc tu lay duoc)'
  mvpBoundary: 'MVP PHAI co Google chay that — lich phu thuoc cap quyen service account'
openQuestions:
  - 'Co chap nhan tach bi mat ra khoi duong ghi cua dashboard khong?'
  - 'Da co thoa thuan voi khach ve viec tai lieu cua ho di qua dich vu AI ben thu ba chua?'
  - 'Tai lieu khach co chua du lieu ca nhan khong — pham vi nghia vu den dau?'
---

# Product Requirements Document — MCP theo từng dự án (ai_team_clean)

**Author:** mor_dong.bd
**Date:** 2026-09-22

**Đọc kèm:** `research-mcp-per-project.md` (bằng chứng thực nghiệm cho mọi khẳng định kỹ thuật ở đây) ·
`_bmad-output/implementation-artifacts/spec-claude-account-switch.md` (ràng buộc đã đóng băng mà PRD
này kế thừa).

## Executive Summary

Mỗi bước agent trong `ai_team_clean` hiện là một hộp kín: tiến trình `claude -p` do `worker.py` sinh ra
chỉ thấy đĩa local cộng nội dung đã nhét sẵn vào file task. Tài liệu thật của khách — spec, backlog,
brief — nằm ngoài, trong Google Drive/Sheets/Docs của từng khách. Người vận hành phải làm giao liên:
tải về, dán vào, dán lại mỗi lần khách sửa. Nút cổ chai đó cũng chính là chỗ dữ liệu cũ lọt vào
pipeline — agent làm việc trên bản sao đúng-hồi-thứ-Ba.

Tính năng này cấp cho mỗi dự án trong `clients/<slug>/` một bộ MCP server riêng: agent làm dự án nào
với tay được đúng tới nguồn ngoài của dự án đó, không hơn. Google Workspace là ca hiện thực đầu tiên;
cơ chế không gắn với Google.

Hai nhóm người dùng: **người vận hành** khai báo và bật/tắt server cho từng dự án; **các agent AI thực
thi bước workflow** là bên tiêu thụ thật sự — chúng nhận thêm tool mà không phải sửa prompt hay sửa
file task.

Nền tảng kỹ thuật đã được kiểm chứng bằng thực nghiệm trên CLI 2.1.273, không phải suy đoán từ tài
liệu (xem `research-mcp-per-project.md`): `--mcp-config` + `--strict-mcp-config` chạy được headless
trên Windows và cô lập thật sự. Điểm chặn duy nhất đã lộ diện là `--allowedTools` — thiếu nó, mọi lời
gọi MCP bị từ chối dưới `--permission-mode acceptEdits` mà worker đang dùng.

### What Makes This Special

Connector claude.ai — cách duy nhất hệ thống đang chạm tới Google hôm nay — gắn với **tài khoản
Claude**, không gắn với dự án. Bật Drive là mọi phiên của mọi khách đều thấy Drive. Với một xưởng chạy
nhiều khách trên cùng một máy, all-or-nothing không phải là bất tiện cấu hình; đó là vấn đề bảo mật
thông tin khách hàng. Nặng hơn: worker xoay vòng nhiều tài khoản Pro khi hết quota, nên bộ tool khả
dụng đổi theo tài khoản đang dùng — sinh ra lỗi không tất định ngay giữa một run.

Cô lập theo dự án mới là sản phẩm. "Cắm được Google" chỉ là hệ quả đầu tiên của nó.

Điều khiến nó khả thi ngay lúc này là mô hình cô lập theo dự án đã dựng xong từ trước: thư mục code
riêng, tài khoản git riêng cho từng agent dev, token đọc từ `settings.local.toml` và chỉ sống trong
env của tiến trình con. MCP treo lên đúng cái giá đó — không phải xây giá mới.

## Project Classification

| Thuộc tính | Giá trị |
|---|---|
| Project Type | `cli_tool` — lược đồ cấu hình + đường dây tham số CLI trong tiến trình headless |
| Domain | `general` — không thuộc ngành có quy định riêng |
| Complexity | **Medium** (nâng từ mức `low` của bảng tham chiếu) |
| Context | Brownfield — hệ thống đang chạy, có chính sách và tiền lệ ràng buộc |
| Ngoại lệ phân loại | Không bỏ qua các mục giao diện: dashboard sẽ sửa được cấu hình MCP |

Bốn lý do nâng complexity lên Medium: bí mật sống trên host; nới quyền có chủ ý trong hàng rào
`acceptEdits` mà README dựng lên; mã bên thứ ba chạy trên máy vận hành với quyền vào thư mục dự án;
và một đường ghi cấu hình mới qua API.

## Success Criteria

### User Success

Người dùng có hai lớp: **người vận hành** cấu hình, và **agent** tiêu thụ.

- Cắm xong một dự án — khai server, đặt credential, bật — trong **≤ 15 phút**, không sửa code, không
  restart worker (đọc lại theo mtime như `claude_accounts.local.toml` đang làm).
- **≥ 90% số bước cần tài liệu khách lấy được trực tiếp, không có người dán tay.** Đây là thước đo chính.
- Khoảnh khắc xác nhận chạy được: bấm ▶, log sống hiện `🔌 MCP: gdrive · 6 tool` — cùng chỗ, cùng kiểu
  với dòng `🔑 Tài khoản Claude` đã quen.
- Thiếu credential hoặc server chết → bước fail với thông báo **chỉ đúng tên file và khoá cần sửa**,
  không bắt người vận hành đọc log CLI thô.

### Business Success

Công cụ nội bộ, nên "business" = năng lực của xưởng.

- Trong **1 tháng**: ít nhất **1 dự án thật đang chạy** không còn cần người làm giao liên tài liệu — về 0.
- Cắm **dự án thứ 2** với bộ server khác: ≤ 15 phút, **0 dòng code**.
- **0 sự cố lộ chéo** giữa khách — kiểm chứng được, không phải cảm tính.
- **0 lần ghi nhầm** vào tài liệu khách.

### Technical Success

Tất cả đo bằng sự kiện `system/init` và log, không cần tin lời ai:

| Tiêu chí | Cách đo |
|---|---|
| Server nối được | `mcp_servers[].status == "connected"`, số lượng khớp số server đang bật trong `mcp.json` |
| Quyền đã mở đúng | **0 bước** fail với `"requested permissions ... haven't granted it yet"` |
| Cô lập thật | `--strict-mcp-config` bật → **0 connector claude.ai** lọt vào phiên |
| Không phụ thuộc tài khoản | Chạy cùng một bước bằng 2 tài khoản Pro khác nhau → `init` cho bộ tool **giống hệt** |
| Bí mật không rò | Credential không xuất hiện trong: response API, DB, log worker, log bước — test hồi quy |
| 401 của MCP không bị đổ oan | Hồi quy cho `worker.py:756` — MCP trả 401 **không** kết luận là token Claude hỏng |
| Không âm thầm đắt lên | A/B có kiểm soát cùng prompt; ngưỡng **3,0 giây / 200 token** tuyệt đối |

**Giới hạn ghi (MVP có quyền ghi):**

- Chỉ ghi vào **vùng khai trước** trong `mcp.json` (folder ID / spreadsheet ID). Ngoài vùng → từ chối.
- **MVP không ghi đè.** Chỉ tạo mới hoặc append. Sửa/xoá thứ đã tồn tại không thuộc MVP.
- Mỗi lần ghi để lại một dòng log kèm ID đối tượng đích — lần ngược được khi có sự cố.

### Measurable Outcomes

| Chỉ số | Hôm nay | Đích (1 tháng) |
|---|---|---|
| Bước lấy được tài liệu khách không cần người | 0% | ≥ 90% |
| Thời gian cắm 1 dự án | chưa làm được | ≤ 15 phút |
| Dòng code phải sửa khi thêm server mới | không xác định | 0 |
| Sự cố lộ chéo giữa khách | — | 0 |
| Ghi nhầm ngoài vùng cho phép | — | 0 |
| Phụ trội thời gian mỗi bước | — | ≤ 3,0 giây (tuyệt đối) |

## Product Scope

Bảng nhìn nhanh. Chi tiết từng lát, năng lực bắt buộc và chiến lược rủi ro nằm ở
[Project Scoping & Phased Development](#project-scoping--phased-development).

| Giai đoạn | Nội dung cốt lõi |
|---|---|
| **MVP** | Cấu hình MCP theo dự án + worker truyền cờ + dashboard quản lý + **Google Workspace chạy thật** (đọc Drive/Docs/Sheets, ghi giới hạn vùng) + log và lỗi chẩn đoán được + test hồi quy bảo mật |
| **Growth** | Server thứ hai không phải Google · ghi đè có xác nhận · MCP theo từng agent · đo chi phí token theo server |
| **Vision** | Danh sách trắng package · khách tự cấp quyền qua OAuth của họ · bộ tool theo từng node workflow |

## User Journeys

### Journey 1 — Người vận hành cắm dự án đầu tiên (Happy Path)

**Persona:** Dũng, chủ một xưởng phần mềm bốn người rưỡi, trong đó "rưỡi" là chính Dũng kiêm luôn vận
hành pipeline AI. Đang chạy song song 6 dự án khách trong `clients/`.

**Cảnh mở.** Khách `udom` vừa cập nhật spec lần thứ tư trong tuần — trong Google Docs. Dũng mở Docs,
copy, dán vào `clients/udom/_tasks/`, chạy lại bước Analyst. Lần thứ tư. Vừa dán vừa biết rõ đến thứ
Sáu sẽ phải làm lại.

**Diễn tiến.** Dũng mở dashboard, vào dự án `udom`, tab MCP mới. Thêm một server: tên `gdrive`, chọn
từ danh sách mẫu, điền ID thư mục Drive của khách. Dashboard báo `credential: thiếu`. Dũng mở
`clients/udom/settings.local.toml`, dán đường dẫn file service account JSON vào mục `[mcp.gdrive]`.
Không restart gì cả — worker đọc lại theo mtime.

**Cao trào.** Quay lại dashboard: dòng `gdrive` chuyển xanh, "đã kết nối · 6 tool". Dũng bấm ▶ một
bước. Log sống hiện `🔌 MCP: gdrive · 6 tool`, rồi agent tự đọc spec từ Docs.

**Kết.** Thứ Sáu khách sửa spec lần thứ năm. Dũng không làm gì cả.

**Cảm xúc:** Bực mình lặp lại → Tò mò → Nhẹ cả người.

### Journey 2 — Agent thực thi một bước có MCP (bên tiêu thụ thật sự)

**Persona:** Bước `analyst` trong workflow của `udom`. Không phải người — nhưng đây là bên *dùng*
tính năng này, nên bỏ qua là bỏ sót yêu cầu thật.

**Cảnh mở.** Bước được claim. `worker.py` dựng lệnh: `--mcp-config clients/udom/mcp.json`,
`--strict-mcp-config`, `--allowedTools mcp__gdrive`, kèm `--add-dir` như cũ và token của tài khoản
Pro đang tới lượt.

**Diễn tiến.** Sự kiện `init` trả về đúng một server: `gdrive`. Không có `zaico`, không có Drive của
khách khác, không có connector claude.ai nào. Agent tìm thấy `mcp__gdrive__read_file`, đọc spec,
viết file task.

**Cao trào.** Agent cần ghi báo cáo tiến độ vào Sheets của khách. Nó gọi tool ghi với một spreadsheet
ID **không** nằm trong vùng đã khai. Bị từ chối ngay tại chỗ, kèm lý do. Agent chuyển sang ID đúng,
ghi thành công, một dòng log ghi lại ID đích.

**Kết.** Bước xong. Không có prompt nào phải sửa, không có file task nào phải soạn tay.

### Journey 3 — Chẩn đoán một bước chết vì MCP (Troubleshooting)

**Persona:** vẫn là Dũng, nhưng lúc 11 giờ đêm, và mọi bước của `ieltskey` đều fail.

**Cảnh mở.** Ba bước liên tiếp `failed`. Log bước chỉ có một dòng: "Permission is required to call
this tool." Không nói tool nào, không nói vì sao.

Đây là cái bẫy đã được kiểm chứng trong `research-mcp-per-project.md`: dưới `--permission-mode
acceptEdits`, thiếu `--allowedTools` thì mọi lời gọi MCP bị từ chối. Nếu hệ thống không nói rõ,
người vận hành sẽ đi nghi ngờ ba thứ vô tội: service account, mạng, và Google.

**Diễn tiến.** Thông báo lỗi phải là: "Server `gdrive` chưa được cấp quyền gọi tool. Bật ở Dashboard
→ dự án ieltskey → MCP, hoặc thêm `allowed_tools` trong `clients/ieltskey/mcp.json`."

**Cao trào.** Dũng bật, chạy lại, xong trong hai phút.

**Cảm xúc:** Hoảng → Bực → Xong.

### Journey 4 — Hết quota giữa chừng, và server chết (Edge Case)

**Persona:** bước `be1` của `udom`, đang chạy dở.

**Diễn tiến.** Tài khoản `pro-1` hết quota. Worker chuyển sang `pro-2` và chạy lại bước. **Bộ tool
phải y hệt** — vì `mcp.json` thuộc về dự án, không thuộc về tài khoản. Đây chính là thứ connector
claude.ai không làm được, và là lý do tính năng này tồn tại.

**Nhánh hỏng thứ hai.** Server `gdrive` trả 401 vì service account bị thu quyền. Worker **không**
được kết luận đó là token Claude hỏng rồi đánh dấu `pro-2` lỗi oan. `worker.py:756` đã lường trước
chuyện này; PRD này biến nó thành test hồi quy.

**Kết.** Bước fail với đúng nguyên nhân: credential Google, không phải tài khoản Claude.

### Journey 5 — Khách hàng cấp quyền (Stakeholder thường bị quên)

**Persona:** Lan, quản lý dự án bên phía khách `udom`. Chưa từng nghe tới MCP, sẽ không bao giờ mở
dashboard.

**Cảnh mở.** Dũng xin Lan chia sẻ một thư mục Drive cho một địa chỉ email lạ dạng
`...@....iam.gserviceaccount.com`. Lan hỏi: "Cái này là ai, và nó làm được gì trong Drive của tôi?"

**Diễn tiến.** Dũng trả lời được, cụ thể: chỉ thư mục này, đọc mọi file trong đó, và ghi **chỉ** vào
một thư mục con tên `ai-output` — vì vùng ghi đã khai trước trong cấu hình, và MVP không ghi đè bất
cứ thứ gì có sẵn.

**Cao trào.** Một tuần sau Lan thấy file mới trong `ai-output`. Không có file cũ nào bị đổi.

**Kết.** Lan cấp thêm quyền cho thư mục thứ hai. Niềm tin lớn dần theo bằng chứng, không theo lời hứa.

**Cảm xúc:** Nghi ngại → Được giải thích rõ → Tin.

### Journey Requirements Summary

| Journey | Năng lực mà nó đòi hỏi |
|---|---|
| 1 — Cắm dự án | Tab MCP trên dashboard; mẫu server dựng sẵn; tách cấu hình / bí mật; nạp lại theo mtime; chỉ báo trạng thái kết nối |
| 2 — Agent thực thi | Dựng lệnh trong worker; `--strict-mcp-config`; whitelist tool; **kiểm tra vùng ghi**; log ID đối tượng đã ghi |
| 3 — Chẩn đoán | Thông báo lỗi chỉ đúng file + khoá; phân biệt "chưa cấp quyền" với "server chết"; bật quyền ngay trên dashboard |
| 4 — Hết quota / 401 | Bộ tool độc lập với tài khoản Claude; không nhầm 401 của MCP thành token hỏng; nêu đúng nguyên nhân khi fail |
| 5 — Khách cấp quyền | Vùng ghi khai trước và **giải thích được cho người ngoài**; không ghi đè ở MVP; nhật ký ghi để đối chiếu |

## Domain-Specific Requirements

Không có cơ quan quản lý ngành. Ràng buộc thật đến từ chính sách nội bộ, nghĩa vụ với khách, và việc
chạy mã bên thứ ba trên máy vận hành.

### Compliance & Regulatory

- **Chính sách dùng Claude subscription.** `README.md` đặt hàng rào rõ: pipeline nền không dùng
  subscription; ngoại lệ `auto_run` chỉ đứng được nhờ ba điều kiện — người dùng tự bật từng workflow,
  chạy trên máy của chính họ, tuần tự một bước một lúc. **Tính năng này không được làm suy yếu điều
  kiện nào trong ba.** MCP khiến mỗi bước làm được nhiều việc hơn, nên cám dỗ chạy song song sẽ lớn
  hơn — đây là điều cấm, không phải khuyến nghị.

- **Nghĩa vụ bảo mật với khách.** Từ khi bật tính năng này, tài liệu của khách chảy thẳng vào prompt
  và đi qua API của Anthropic. Trước đây người vận hành *chọn* dán gì; sau này agent tự lấy. Đây là
  thay đổi về bản chất, không phải về mức độ — cần thoả thuận với khách TRƯỚC khi cắm dự án thật.

- **Dữ liệu cá nhân trong tài liệu khách.** Nếu Drive của khách chứa CV, danh sách khách hàng, thông
  tin liên hệ thì việc tự động đọc chúng chạm tới nghĩa vụ bảo vệ dữ liệu cá nhân. Phải xác định
  phạm vi nghĩa vụ **trước khi** cắm dự án thuộc loại đó. (Câu hỏi còn mở tại thời điểm viết PRD.)

### Technical Constraints

Kế thừa nguyên vẹn từ `spec-claude-account-switch.md`, không thương lượng:

- Bí mật chỉ sống trong file local trên host và env của tiến trình con. Không qua API, không vào DB,
  không lên UI.
- Không có file cấu hình → hành vi y hệt hiện tại. Không lỗi, không cảnh báo ồn ào.
- Không `--dangerously-skip-permissions`. Nới quyền tối thiểu: chỉ tool của server đã bật.
- Tuần tự một bước một lúc, giữ nguyên.

Thêm mới cho tính năng này:

- Cô lập giữa các dự án phải **kiểm chứng được từ bên ngoài** — qua sự kiện `init`, không phải bằng
  niềm tin vào code.
- Bộ tool của một bước chỉ phụ thuộc `mcp.json` của dự án, **không** phụ thuộc tài khoản Claude.

### Integration Requirements

| Phụ thuộc | Ràng buộc |
|---|---|
| Claude Code CLI | >= 2.1.273 (`--mcp-config`, `--strict-mcp-config`) — đã xác nhận trên máy |
| Google Workspace | Service account + domain-wide delegation — **phụ thuộc admin bên ngoài, đường găng của lịch** |
| Runtime MCP stdio | node/npx trên host Windows — đã chạy thật |
| Tương thích ngược | Dự án không có `mcp.json` phải chạy đúng như hôm nay |

### Risk Mitigations

| Rủi ro | Mức | Biện pháp |
|---|---|---|
| **Chuỗi cung ứng** — `mcp.json` khai `npx <package>` là tải và chạy mã lạ trên máy vận hành, với quyền vào thư mục dự án và credential khách | Cao | MVP: chỉ cho chọn từ **danh sách mẫu dựng sẵn**; khai lệnh tự do phải sửa file tay, không qua dashboard. Danh sách trắng đầy đủ để ở Vision |
| Agent ghi nhầm vào tài liệu khách | Cao | Vùng ghi khai trước; MVP không ghi đè; nhật ký ID đối tượng đích |
| Credential rò qua API/DB/log | Cao | Tách bí mật khỏi `mcp.json`; test hồi quy che bí mật theo khuôn đã có |
| 401 của MCP bị chẩn đoán nhầm thành token Claude hỏng | Trung bình | Hồi quy cho `worker.py:756` |
| Chi phí token phình âm thầm theo số server | Trung bình | Đo baseline trước khi bật; ngưỡng cảnh báo +15% |
| Server MCP treo → bước treo tới `STEP_TIMEOUT_S` (1800s) | Trung bình | Timeout riêng cho lúc khởi động server, ngắn hơn timeout của bước |
| Cám dỗ chạy song song nhiều bước | Trung bình | Ghi trong PRD như điều cấm |

## Project-Type Requirements (cli_tool)

### Project-Type Overview

Sản phẩm không phải một CLI mới cho người gõ. Nó là **lớp cấu hình** quyết định tiến trình `claude -p`
của `worker.py` được sinh ra với những tham số nào. Người dùng không gõ lệnh; họ sửa cấu hình, và cấu
hình biến thành tham số. Vì vậy "shell completion" không áp dụng.

### Technical Architecture Considerations

**Hoàn toàn không tương tác.** Tiến trình con chạy nền, không ai bấm gì. Mọi cơ chế đòi tương tác bị
loại từ đầu: `claude mcp login` (cần trình duyệt), MCP server hỏi mật khẩu trên stdin, prompt xác nhận.
`research-mcp-per-project.md` đã xác nhận `--no-browser` vẫn cần người dán URL.

Hệ quả cứng: **mọi MCP server dùng trong pipeline phải xác thực được bằng credential tĩnh** (service
account, API key, token dài hạn). Server chỉ hỗ trợ OAuth tương tác thì không dùng được ở đây.

### Config Schema

Hai file, tách theo đúng ranh giới bí mật.

`clients/<slug>/mcp.json` — không chứa bí mật, dashboard sửa được:

```json
{
  "servers": {
    "gdrive": {
      "template": "google-workspace",
      "enabled": true,
      "allowed_tools": ["read_file", "search_files", "create_file"],
      "write_scope": { "folder_ids": ["1AbC..."] }
    }
  }
}
```

`clients/<slug>/settings.local.toml` — đã gitignore, chỉ sửa tay trên host:

```toml
[mcp.gdrive]
credentials_path = "C:/secure/udom-service-account.json"
```

Kể cả file này cũng **không chứa bí mật** — nó chứa *đường dẫn tới* bí mật. File service account không
di chuyển, không bị copy, không nằm trong thứ gì dashboard đọc được.

`mcp.json` **không phải** định dạng native của Claude Code. Worker dịch sang định dạng native lúc
spawn. Đổi lại ta có ba thứ định dạng native không có chỗ chứa: `enabled`, `allowed_tools`,
`write_scope`.

### Command Structure

Worker dựng lệnh, nối vào ngay sau chỗ đang nối `--add-dir`:

```
claude -p "<prompt>"
  --permission-mode acceptEdits
  --output-format stream-json --verbose
  --mcp-config <native config>          <- dich tu mcp.json
  --strict-mcp-config                   <- cat connector claude.ai
  --allowedTools mcp__gdrive            <- thieu dong nay thi moi loi goi MCP chet
  --add-dir ...                         <- nhu cu
```

Không có `mcp.json`, hoặc không server nào `enabled` → **không thêm cờ nào**. Bước chạy y hệt hôm nay.

### Output Formats

| Kênh | Nội dung |
|---|---|
| Log sống của bước | `🔌 MCP: gdrive · 6 tool` — cùng vị trí, cùng kiểu với `🔑 Tài khoản Claude` |
| `system/init` (stream-json) | Nguồn sự thật để nghiệm thu: `mcp_servers[].status`, danh sách tool |
| Heartbeat → dashboard | Tên server, đã kết nối hay chưa, `credential: có/thiếu`. **Không bao giờ có giá trị bí mật** |
| Log khi ghi | Một dòng mỗi lần ghi, kèm ID đối tượng đích |

### Scripting Support

- Cấu hình đọc lại theo **mtime**, không cần restart worker — đúng khuôn `claude_accounts.local.toml`.
- File hỏng cú pháp → **giữ cấu hình cũ** + cảnh báo terminal, không làm chết worker.
- Mọi thứ dashboard làm được đều làm được bằng sửa file tay. File là nguồn sự thật, không phải DB —
  giống cách `skills/` đang hoạt động.

### Implementation Considerations

**Credential không cần đi vào file cấu hình nào cả — đã kiểm chứng.** Worker đã bơm token git vào env
tiến trình con (`_project_git_env`). MCP server là tiến trình con *của* Claude Code và **thừa kế env
đó**. Vậy worker chỉ cần đặt `GOOGLE_APPLICATION_CREDENTIALS=<path>` vào env như đang làm với
`GH_TOKEN`, và `mcp.json` sạch trơn — không có gì để rò rỉ kể cả khi lỡ commit.

✅ **Đã xác minh bằng thực nghiệm (2026-09-22, CLI 2.1.273).** Một stdio MCP server tí hon trả về
`process.env.MCP_PROBE_VAR`; biến đặt ở tiến trình cha tới được server con nguyên vẹn. Chi tiết trong
`research-mcp-per-project.md`.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach: Problem-solving MVP.** Đích không phải "có hạ tầng MCP" mà là "một dự án thật hết cần
người dán tài liệu". Hạ tầng suông không chứng minh được gì; thước đo chính (≥90% bước tự lấy được tài
liệu) chỉ đo được khi có một nguồn thật cắm vào.

**Resource Requirements:** một người vận hành kiêm reviewer, cộng chính pipeline này thực thi. Phụ
thuộc ngoài đội: **Google Workspace admin cấp domain-wide delegation** cho service account.

**Chia MVP làm hai lát, để phụ thuộc ngoài không khoá toàn bộ tiến độ:**

| Lát | Nội dung | Nghiệm thu độc lập |
|---|---|---|
| **1A — Khung** | `mcp.json` + dịch sang config native + 3 cờ CLI + dashboard + log + lỗi rõ ràng | Bằng một MCP server vô hại (ví dụ filesystem server trỏ vào thư mục dự án). Không cần Google, không cần admin |
| **1B — Google thật** | Server Google Workspace qua service account: đọc Drive/Docs/Sheets + ghi giới hạn vùng | Bằng dự án khách thật |

MVP = 1A + 1B. Nhưng 1A làm được và nghiệm thu được **ngay**, song song với việc xin quyền. Nếu đảo thứ
tự, cả tính năng nằm chờ một email từ admin.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:** Journey 1 (cắm dự án), Journey 2 (agent thực thi), Journey 3 (chẩn
đoán lỗi), Journey 4 (hết quota / 401), Journey 5 (khách cấp quyền). Cả năm đều thuộc MVP — journey 3
và 4 là journey hỏng, và bỏ chúng ra khỏi MVP nghĩa là giao một tính năng không debug được.

**Must-Have Capabilities:**

- Đọc `clients/<slug>/mcp.json`, nạp lại theo mtime, file hỏng thì giữ bản cũ + cảnh báo
- Dịch sang config native của Claude Code; bơm credential qua env tiến trình con
- Nối `--mcp-config`, `--strict-mcp-config`, `--allowedTools mcp__<server>` cho từng server đang bật
- Không có cấu hình → không thêm cờ nào, hành vi y hệt hôm nay
- Kiểm tra `write_scope` trước mọi thao tác ghi; ngoài vùng → từ chối
- Log: `🔌 MCP: <server> · N tool`; mỗi lần ghi một dòng kèm ID đích
- Dashboard: tab MCP theo dự án — thêm/sửa/bật/tắt server từ **danh sách mẫu**, xem trạng thái kết nối
  và `credential: có/thiếu`
- Thông báo lỗi phân biệt được: chưa cấp quyền tool · thiếu credential · server không khởi động được ·
  server trả lỗi
- Test hồi quy: che bí mật · 401 của MCP không bị quy thành token Claude hỏng · cô lập giữa dự án
- Server Google Workspace: `read_file`, `search_files`, `read_sheet`, `create_file`, `append_sheet`

### Post-MVP Features

**Phase 2 (Growth):**

- Server thứ hai không phải Google (Jira / Figma / Postgres) — phép thử thật cho "hạ tầng chung"
- Ghi đè và sửa tài liệu đã tồn tại, kèm bước xác nhận
- MCP riêng theo từng agent trong một dự án, đúng khuôn `[git.be1]`
- Đo và cảnh báo chi phí token theo từng server
- Khai lệnh tự do (ngoài danh sách mẫu) ngay trên dashboard, kèm cảnh báo rõ

**Phase 3 (Expansion):**

- Danh sách trắng package được phép chạy — khoá rủi ro chuỗi cung ứng
- Khách tự cấp quyền bằng OAuth của chính họ thay cho service account của xưởng
- Bộ tool theo từng node workflow, không chỉ theo dự án

### Risk Mitigation Strategy

Bảng rủi ro chi tiết theo từng nguy cơ nằm ở [Domain-Specific Requirements → Risk Mitigations](#risk-mitigations).
Mục này chỉ nói chiến lược ở tầng dự án.

**Technical Risks.** Phần rủi ro kỹ thuật lớn nhất đã được hạ xuống trước khi viết PRD: cơ chế
`--mcp-config` + `--strict-mcp-config` + `--allowedTools` đã chạy thật trên máy đích, đúng hệ điều
hành, đúng phiên bản CLI. Còn đúng một giả định chưa kiểm: **MCP server con có thừa kế env của tiến
trình Claude Code không** — spike trước khi code, có đường lui (khai `env` trong config native).

**Market Risks.** Không có thị trường; đây là công cụ nội bộ. Rủi ro tương đương là **tính năng làm
xong nhưng không ai cắm**, vì khách không đồng ý cho tài liệu đi qua dịch vụ AI bên thứ ba. Giảm
thiểu: hỏi ít nhất một khách **trước** khi bắt đầu 1B — câu trả lời đó rẻ hơn nhiều so với làm xong
mới hỏi.

**Resource Risks.** Nếu phải cắt: giữ 1A, hoãn 1B. Trong 1A nếu vẫn phải cắt nữa thì bỏ tab dashboard
và cấu hình bằng file tay — mất tiện lợi, không mất năng lực. Thứ **không được cắt**: kiểm tra
`write_scope`, che bí mật, và thông báo lỗi phân biệt được nguyên nhân. Cắt ba thứ đó là giao một tính
năng nguy hiểm hoặc không debug được.

## Functional Requirements

Đây là **hợp đồng năng lực**. Năng lực nào không có tên ở đây thì sẽ không tồn tại trong sản phẩm.

### Khai báo cấu hình theo dự án

- FR1: Người vận hành có thể khai báo một hoặc nhiều MCP server riêng cho từng dự án
- FR2: Người vận hành có thể bật hoặc tắt từng server mà không phải xoá khai báo
- FR3: Người vận hành có thể chọn server từ danh sách mẫu dựng sẵn
- FR4: Người vận hành có thể giới hạn danh sách tool mà mỗi server được phép dùng
- FR5: Người vận hành có thể khai vùng ghi cho phép của từng server
- FR6: Hệ thống có thể áp cấu hình mới mà không cần khởi động lại worker
- FR7: Hệ thống có thể giữ nguyên cấu hình đang chạy khi file cấu hình sai cú pháp, và báo lỗi ra cho
  người vận hành
- FR8: Người vận hành có thể thực hiện mọi thao tác cấu hình bằng cách sửa file trực tiếp, không bắt
  buộc qua giao diện

### Bí mật và credential

- FR9: Người vận hành có thể khai credential cho từng server của từng dự án, tách khỏi phần cấu hình
  dùng chung
- FR10: Hệ thống có thể cung cấp credential cho MCP server mà không ghi giá trị bí mật vào file cấu
  hình, cơ sở dữ liệu, hay phản hồi API
- FR11: Hệ thống có thể che giá trị bí mật đã biết trước khi bất kỳ log hay dữ liệu nào rời khỏi tiến
  trình worker
- FR12: Người vận hành có thể biết một server đã có hay còn thiếu credential, mà không nhìn thấy giá trị
- FR13: Hai dự án dùng cùng loại server có thể dùng hai credential khác nhau

### Thực thi bước có MCP

- FR14: Hệ thống có thể cấp cho bước đang chạy đúng những server đang bật của dự án đó
- FR15: Hệ thống có thể cấp sẵn quyền gọi tool cho các server đã bật, không đòi người duyệt lúc chạy
- FR16: Hệ thống có thể chạy bước với bộ tool không phụ thuộc vào tài khoản Claude đang dùng
- FR17: Hệ thống có thể chạy bước của dự án không khai MCP đúng như trước khi có tính năng này
- FR18: Hệ thống có thể từ chối khởi động server đòi xác thực tương tác, kèm lý do rõ ràng
- FR19: Hệ thống có thể bỏ cuộc khi một server không khởi động được trong thời hạn riêng, ngắn hơn
  thời hạn của cả bước

### Giới hạn phạm vi ghi

- FR20: Hệ thống có thể chặn mọi thao tác ghi ra ngoài vùng đã khai của server
- FR21: Hệ thống có thể từ chối ghi đè hoặc xoá đối tượng đã tồn tại
- FR22: Hệ thống có thể ghi nhật ký cho từng thao tác ghi, kèm định danh đối tượng đích
- FR23: Người vận hành có thể trả lời cho khách hàng biết chính xác server đọc được gì và ghi vào đâu,
  dựa trên cấu hình đang chạy

### Quan sát và chẩn đoán

- FR24: Người vận hành có thể thấy server nào đang hoạt động và bao nhiêu tool khả dụng, trong log sống
  của bước
- FR25: Người vận hành có thể thấy trạng thái kết nối của từng server trên dashboard
- FR26: Hệ thống có thể phân biệt và báo riêng bốn nguyên nhân hỏng: chưa cấp quyền tool · thiếu
  credential · server không khởi động được · server trả lỗi
- FR27: Hệ thống có thể chỉ đúng tên file và tên khoá cần sửa trong thông báo lỗi cấu hình
- FR28: Hệ thống có thể không quy lỗi xác thực của MCP server thành lỗi tài khoản Claude
- FR29: Người vận hành có thể đối chiếu bộ server thực tế của một lần chạy với cấu hình đã khai

### Cô lập giữa các dự án

- FR30: Hệ thống có thể bảo đảm bước của một dự án không thấy MCP server của dự án khác
- FR31: Hệ thống có thể loại bỏ các kết nối MCP ở mức tài khoản khỏi bước có khai MCP riêng
- FR32: Người vận hành có thể kiểm chứng sự cô lập từ dữ liệu của lần chạy, không cần đọc mã nguồn

### Chi phí và vận hành

- FR33: Người vận hành có thể đo thời gian và chi phí token của bước trước và sau khi bật MCP
- FR34: Người vận hành có thể tắt toàn bộ MCP của một dự án bằng một thao tác

## Non-Functional Requirements

Chỉ ghi những nhóm thật sự áp dụng. **Accessibility bị bỏ có chủ ý**: đây là công cụ nội bộ, một người
vận hành, không phục vụ công chúng, không chịu quy định tiếp cận nào.

### Security

Nhóm quan trọng nhất của tính năng này.

- Giá trị bí mật **không được xuất hiện** trong: `mcp.json`, cơ sở dữ liệu, phản hồi API, heartbeat,
  log worker, log bước. Kiểm bằng test tự động, không bằng rà soát mắt thường.
- Credential của dự án A **không được** nằm trong env của tiến trình chạy bước dự án B.
- Quyền tool theo nguyên tắc tối thiểu: chỉ những tool khai trong `allowed_tools` của server đang bật.
- `--dangerously-skip-permissions` **không được xuất hiện** ở bất kỳ nhánh mã nào. Kiểm bằng test.
- MVP chỉ chạy server từ danh sách mẫu. Khai lệnh tự do phải sửa file trực tiếp trên host — không
  đường nào từ dashboard tạo được một tiến trình tuỳ ý trên máy vận hành.
- Mọi thao tác ghi để lại nhật ký đủ để lần ngược, giữ tối thiểu **30 ngày**.
- Thu hồi quyền có hiệu lực chậm nhất ở **bước kế tiếp**: tắt server hoặc gỡ credential không đòi
  restart, và bước đang chạy dở không bị can thiệp giữa chừng.

### Performance

- Phụ trội thời gian cố định do MCP: **≤ 3,0 giây** mỗi bước có MCP.
- Phụ trội token: **≤ 200 token** mỗi bước có MCP. Vượt ngưỡng → cảnh báo, không âm thầm.

  *Sửa ngày 2026-09-22 từ "+15% / +10%" sang ngưỡng tuyệt đối.* Phép đo A/B có kiểm soát cho thấy
  phụ trội là **cố định** (~0,31 s, ~13 token), không tỷ lệ với độ dài bước. Ngưỡng phần trăm vừa
  quá chặt với bước ngắn vừa vô dụng với bước dài: +15% của một bước 1.126 giây là 169 giây. Chi
  tiết và số liệu: `_bmad-output/implementation-artifacts/baseline-mcp.md`.

  *Sửa lần hai ngày 2026-09-22 từ 1,0 s lên 3,0 s.* Đo bằng server Google thật cho +1,75 s,
  gần như toàn bộ là thời gian khởi động tiến trình Node nạp 160 package — không tối ưu được
  từ phía ta. Ngưỡng 3,0 s chừa chỗ cho server thứ hai. Quyết định của chủ sản phẩm sau khi
  xem số đo, không phải người đo tự nới.
- Khởi động toàn bộ server của một dự án: **≤ 20 giây**. Quá hạn → bỏ cuộc và báo lỗi, **không** chờ
  tới `STEP_TIMEOUT_S` (1800s).
- Kiểm tra và nạp lại cấu hình theo mtime: **≤ 50ms**, không làm chậm vòng poll claim 3 giây.

### Reliability

- File cấu hình hỏng cú pháp **không được làm chết worker**: giữ cấu hình cũ, cảnh báo, tiếp tục nhận
  job. 0 lần crash trong bộ test hỏng có chủ đích.
- MCP server chết giữa chừng → bước fail với đúng nguyên nhân; worker vẫn nhận job kế tiếp bình thường.
- **Tương thích ngược tuyệt đối**: dự án không có `mcp.json` phải cho hành vi y hệt trước tính năng
  này. Kiểm bằng bộ test hồi quy hiện có, 0 thay đổi kết quả.
- Bật/tắt server không cần khởi động lại worker; có hiệu lực trong vòng 1 bước.

### Scalability

Không phải quy mô người dùng — quy mô **dự án × server** trên một máy.

- Hỗ trợ ít nhất **20 dự án**, mỗi dự án tối đa **5 server**, không làm chậm vòng claim.
- Dashboard hiển thị trạng thái tới **100 server** tổng mà **không thêm vòng poll mới** — đi ké
  heartbeat, đúng cách snapshot tài khoản Claude đang làm.

### Integration

- Claude Code CLI **≥ 2.1.273**. Phiên bản thấp hơn → báo rõ ràng, **không** âm thầm bỏ cờ và chạy tiếp
  như không có gì.
- Chỉ chấp nhận MCP server xác thực bằng **credential tĩnh**. Server đòi OAuth tương tác bị từ chối
  kèm lý do.
- Google Workspace: service account + domain-wide delegation. Khi quyền bị thu hồi, lỗi phải phân biệt
  được với lỗi tài khoản Claude.
- Windows: server stdio khởi động qua shim `npx`/`node` phải chạy được — áp dụng bài học đã có ở
  `_resolve_claude` (CreateProcess không áp PATHEXT).
