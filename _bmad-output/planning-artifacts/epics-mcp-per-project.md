---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: 'complete'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd-mcp-per-project.md'
  - '_bmad-output/planning-artifacts/architecture-mcp-per-project.md'
  - '_bmad-output/planning-artifacts/research-mcp-per-project.md'
inputDocumentsExcluded:
  - '_bmad-output/planning-artifacts/prd.md (PRD e-commerce cua du an khach)'
uxDocument: none
project_name: 'ai_team_clean'
feature: 'MCP per-project'
date: '2026-09-22'
---

# ai_team_clean — MCP theo từng dự án — Epic Breakdown

## Overview

Chẻ yêu cầu từ PRD và Architecture thành story thực thi được. Nguồn: `prd-mcp-per-project.md` (34 FR)
và `architecture-mcp-per-project.md` (AD1–AD12, G1–G6, thứ tự triển khai 6 bước).

Không có tài liệu UX — tính năng chỉ thêm một tab quản trị, không có mẫu tương tác cần đặc tả riêng.

## Requirements Inventory

### Functional Requirements

**Khai báo cấu hình theo dự án**
- FR1: Người vận hành có thể khai báo một hoặc nhiều MCP server riêng cho từng dự án
- FR2: Người vận hành có thể bật hoặc tắt từng server mà không phải xoá khai báo
- FR3: Người vận hành có thể chọn server từ danh sách mẫu dựng sẵn
- FR4: Người vận hành có thể giới hạn danh sách tool mà mỗi server được phép dùng
- FR5: Người vận hành có thể khai vùng ghi cho phép của từng server
- FR6: Hệ thống có thể áp cấu hình mới mà không cần khởi động lại worker
- FR7: Hệ thống có thể giữ nguyên cấu hình đang chạy khi file sai cú pháp, và báo lỗi
- FR8: Người vận hành có thể thực hiện mọi thao tác cấu hình bằng cách sửa file trực tiếp

**Bí mật và credential**
- FR9: Người vận hành có thể khai credential cho từng server của từng dự án, tách khỏi cấu hình chung
- FR10: Hệ thống có thể cung cấp credential cho MCP server mà không ghi bí mật vào file cấu hình, DB, hay phản hồi API
- FR11: Hệ thống có thể che giá trị bí mật đã biết trước khi log hay dữ liệu rời tiến trình worker
- FR12: Người vận hành có thể biết server đã có hay còn thiếu credential, mà không thấy giá trị
- FR13: Hai dự án dùng cùng loại server có thể dùng hai credential khác nhau

**Thực thi bước có MCP**
- FR14: Hệ thống có thể cấp cho bước đang chạy đúng những server đang bật của dự án đó
- FR15: Hệ thống có thể cấp sẵn quyền gọi tool cho server đã bật, không đòi người duyệt lúc chạy
- FR16: Hệ thống có thể chạy bước với bộ tool không phụ thuộc tài khoản Claude đang dùng
- FR17: Hệ thống có thể chạy bước của dự án không khai MCP đúng như trước khi có tính năng này
- FR18: Hệ thống có thể từ chối khởi động server đòi xác thực tương tác, kèm lý do rõ ràng
- FR19: Hệ thống có thể bỏ cuộc khi server không khởi động được trong thời hạn riêng, ngắn hơn thời hạn bước

**Giới hạn phạm vi ghi**
- FR20: Hệ thống có thể chặn mọi thao tác ghi ra ngoài vùng đã khai của server
- FR21: Hệ thống có thể từ chối ghi đè hoặc xoá đối tượng đã tồn tại
- FR22: Hệ thống có thể ghi nhật ký cho từng thao tác ghi, kèm định danh đối tượng đích
- FR23: Người vận hành có thể trả lời cho khách biết chính xác server đọc được gì và ghi vào đâu

**Quan sát và chẩn đoán**
- FR24: Người vận hành có thể thấy server nào đang hoạt động và bao nhiêu tool, trong log sống của bước
- FR25: Người vận hành có thể thấy trạng thái kết nối của từng server trên dashboard
- FR26: Hệ thống có thể phân biệt và báo riêng bốn nguyên nhân hỏng
- FR27: Hệ thống có thể chỉ đúng tên file và tên khoá cần sửa trong thông báo lỗi cấu hình
- FR28: Hệ thống có thể không quy lỗi xác thực của MCP server thành lỗi tài khoản Claude
- FR29: Người vận hành có thể đối chiếu bộ server thực tế của một lần chạy với cấu hình đã khai

**Cô lập giữa các dự án**
- FR30: Hệ thống có thể bảo đảm bước của một dự án không thấy MCP server của dự án khác
- FR31: Hệ thống có thể loại bỏ kết nối MCP ở mức tài khoản khỏi bước có khai MCP riêng
- FR32: Người vận hành có thể kiểm chứng sự cô lập từ dữ liệu của lần chạy, không cần đọc mã

**Chi phí và vận hành**
- FR33: Người vận hành có thể đo thời gian và chi phí token của bước trước và sau khi bật MCP
- FR34: Người vận hành có thể tắt toàn bộ MCP của một dự án bằng một thao tác

### NonFunctional Requirements

**Security**
- NFR1: Giá trị bí mật không xuất hiện trong `mcp.json`, DB, phản hồi API, heartbeat, log worker, log bước
- NFR2: Credential của dự án A không nằm trong env của tiến trình chạy bước dự án B
- NFR3: Quyền tool tối thiểu — chỉ tool thuộc hồ sơ của server đang bật
- NFR4: `--dangerously-skip-permissions` không xuất hiện ở bất kỳ nhánh mã nào
- NFR5: MVP chỉ chạy server từ danh sách mẫu; khai lệnh tự do phải sửa file trên host
- NFR6: Nhật ký thao tác ghi giữ tối thiểu 30 ngày
- NFR7: Thu hồi quyền có hiệu lực chậm nhất ở bước kế tiếp, không cần restart

**Performance**
- NFR8: Phụ trội thời gian cố định ≤ 3,0 giây mỗi bước có MCP (sửa 2026-09-22, xem baseline-mcp.md)
- NFR9: Phụ trội ≤ 200 token mỗi bước có MCP; vượt ngưỡng thì cảnh báo
- NFR10: Khởi động toàn bộ server ≤ 20 giây; quá hạn thì bỏ cuộc, không chờ `STEP_TIMEOUT_S`
- NFR11: Kiểm tra và nạp lại cấu hình ≤ 50ms, không làm chậm vòng poll claim 3 giây

**Reliability**
- NFR12: File cấu hình hỏng không làm chết worker; giữ bản cũ, cảnh báo, tiếp tục nhận job
- NFR13: MCP server chết giữa chừng thì bước fail đúng nguyên nhân; worker vẫn nhận job kế tiếp
- NFR14: Tương thích ngược tuyệt đối — dự án không có `mcp.json` cho hành vi y hệt
- NFR15: Bật/tắt server không cần khởi động lại worker; hiệu lực trong vòng 1 bước

**Scalability**
- NFR16: Ít nhất 20 dự án, mỗi dự án tối đa 5 server, không làm chậm vòng claim
- NFR17: Dashboard hiển thị tới 100 server mà không thêm vòng poll mới

**Integration**
- NFR18: Claude Code CLI >= 2.1.273; thấp hơn thì báo rõ, không âm thầm bỏ cờ
- NFR19: Chỉ chấp nhận server xác thực bằng credential tĩnh
- NFR20: Google Workspace service account; mất quyền thì lỗi phân biệt được với lỗi tài khoản Claude
- NFR21: Windows — server stdio khởi động qua shim `npx`/`node` phải chạy được

### Additional Requirements

Từ Architecture:

- **AR1: KHÔNG có starter template.** Brownfield. Epic 1 Story 1 **không phải** lệnh scaffold — việc đầu tiên là **đo baseline hiệu năng** (gap G4), vì NFR8/NFR9 vô nghĩa nếu không có số nền.
- AR2: Cài sẵn `@us-all/google-drive-mcp` đã ghim phiên bản tại `vendor/mcp/`; **cấm `npx -y`** (AD6)
- AR3: `dashboard/docker-compose.yml` mount `../clients:/clients` cho ghi (AD8)
- AR4: Thêm `vendor/mcp/` vào `.gitignore` (G6)
- AR5: Kiểm phiên bản CLI lúc worker khởi động, nhớ kết quả (G3, phục vụ NFR18)
- AR6: Khoá `enabled` ở **gốc** `mcp.json` làm công tắc cấp dự án (G2, phục vụ FR34)
- AR7: Khoá vùng ghi đặt tên `declared_write_scope` — nó là **khai báo**, không phải hàng rào (G1)
- AR8: `config/mcp_templates.toml` chứa danh sách mẫu server và ba hồ sơ quyền
- AR9: Việc ngoài mã — khách tạo Shared Drive và thêm email service account làm Content Manager (AD7)
- AR10: `tests/test_worker_accounts.py` **không được sửa**; dùng làm test hồi quy tương thích ngược
- AR11: **Không đụng** `main.py`, `ai_team/`, `skills/`, `ActiveTasks.tsx`, `RunConsole.tsx`
- AR12: `dashboard/api` **không được import** `worker.py` — hai tiến trình, chép chứ không import
- AR13: Che bí mật chỉ qua `_redact` sẵn có; cấm thêm điểm che thứ hai
- AR14: Mọi tham số CLI mới nằm sau một cổng duy nhất `if servers:`

### UX Design Requirements

Không có tài liệu UX. Yêu cầu giao diện nằm trong FR3, FR12, FR25, FR34 và mẫu đặt tên `.mcp-*` ở
Architecture.

### FR Coverage Map

FR1: Epic 1 — khai báo server trong mcp.json
FR2: Epic 1 — cờ `enabled` từng server
FR3: Epic 3 — chọn từ danh sách mẫu trên dashboard
FR4: Epic 1 — hồ sơ quyền quyết định danh sách tool (AD5)
FR5: Epic 1 — lược đồ `declared_write_scope` (Epic 4 dùng tới)
FR6: Epic 1 — nạp lại theo mtime
FR7: Epic 1 — file hỏng thì giữ bản cũ
FR8: Epic 1 — file là nguồn sự thật
FR9: Epic 1 — mục `[mcp.<server>]` trong settings.local.toml
FR10: Epic 1 — credential đi env, không vào cấu hình/DB/API
FR11: Epic 1 — che qua `_redact` sẵn có
FR12: Epic 3 — hiện `credential: có/thiếu`
FR13: Epic 1 — credential tách theo dự án
FR14: Epic 1 — dựng lệnh theo dự án của job
FR15: Epic 1 — `--allowedTools` từ hồ sơ
FR16: Epic 1 — bộ tool không phụ thuộc tài khoản Claude
FR17: Epic 1 — cổng `if servers:` giữ tương thích ngược
FR18: Epic 2 — giới hạn ở danh sách mẫu + hạn khởi động (phủ một phần, xem G/FR18)
FR19: Epic 2 — hạn 20s cho `system/init`
FR20: Epic 4 — Google cưỡng chế qua phạm vi chia sẻ
FR21: Epic 4 — hồ sơ `read-create`, không có tool sửa/xoá
FR22: Epic 4 — nhật ký ghi kèm ID đối tượng đích
FR23: Epic 4 — trả lời được cho khách từ cấu hình đang chạy
FR24: Epic 1 — dòng log `🔌 MCP: <server> · N tool`
FR25: Epic 3 — trạng thái kết nối trên dashboard
FR26: Epic 2 — phân biệt bốn nguyên nhân hỏng
FR27: Epic 2 — lỗi chỉ đúng file và khoá
FR28: Epic 2 — 401 của MCP không bị quy thành token Claude hỏng
FR29: Epic 2 — đối chiếu `system/init` với cấu hình
FR30: Epic 1 — cấu hình theo dự án, không dùng chung
FR31: Epic 1 — `--strict-mcp-config`
FR32: Epic 2 — kiểm chứng cô lập từ dữ liệu lần chạy
FR33: Epic 1 — baseline đo trước (Epic 4 đối chiếu sau)
FR34: Epic 1 — khoá `enabled` ở gốc (Epic 3 thêm nút bấm)

## Epic List

### Epic 1: Một dự án với tay được ra ngoài

Người vận hành khai một MCP server cho một dự án bằng cách sửa file, và bước của dự án đó dùng được
tool từ server ấy. Dự án khác không thấy gì. Chưa có UI, chưa có Google — nhưng đã dùng được thật.
**Đây là epic duy nhất không phụ thuộc epic nào.**

**FRs covered:** FR1, FR2, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR13, FR14, FR15, FR16, FR17,
FR24, FR30, FR31, FR33, FR34

### Epic 2: Hỏng thì biết hỏng ở đâu

Bước chết vì MCP thì thông báo chỉ thẳng nguyên nhân và chỗ sửa. Phân biệt được bốn loại hỏng, và lỗi
xác thực của Google không còn làm worker đánh dấu oan tài khoản Claude Pro.

**FRs covered:** FR18, FR19, FR26, FR27, FR28, FR29, FR32

### Epic 3: Cắm dự án mà không mở editor

Thêm server, chọn hồ sơ quyền, bật/tắt, xem trạng thái kết nối và `credential: có/thiếu` — toàn bộ
trên dashboard. File vẫn là nguồn sự thật.

**FRs covered:** FR3, FR12, FR25

### Epic 4: Đọc và ghi tài liệu thật của khách

Agent đọc spec từ Drive của khách và ghi báo cáo vào Shared Drive. Đây là giá trị đích — ba epic trước
là đường dẫn tới đây.

**FRs covered:** FR20, FR21, FR22, FR23

### Phụ thuộc và thứ tự giao

Epic 2, 3, 4 đều chỉ cần Epic 1, không cần lẫn nhau. Epic 1–3 là **lát 1A** trong PRD (không cần
Google, không chờ khách). Epic 4 là **lát 1B**. Cả bốn hợp thành MVP.

## Epic 1: Một dự án với tay được ra ngoài

Người vận hành khai một MCP server cho một dự án bằng cách sửa file, và bước của dự án đó dùng được
tool từ server ấy. Dự án khác không thấy gì. Chưa có UI, chưa có Google — nhưng đã dùng được thật.

### Story 1.1: Đo baseline hiệu năng trước khi chạm vào mã

As a người vận hành,
I want biết một bước hiện tốn bao nhiêu thời gian và bao nhiêu token khi chưa có MCP,
So that sau này tôi biết MCP làm nó chậm và đắt thêm bao nhiêu, thay vì đoán.

**Acceptance Criteria:**

**Given** bảng `workflow_step_jobs` đã lưu sẵn `duration_ms`, `cost_usd`, `usage`, `model_used` cho mọi bước đã chạy
**When** truy vấn các bước `status='done'`, `tool='claude'` trong lịch sử
**Then** tính trung vị thời gian và trung vị token, nhóm theo model, ghi vào `_bmad-output/implementation-artifacts/baseline-mcp.md`
**And** tài liệu ghi rõ số mẫu, khoảng thời gian lấy mẫu, model, phiên bản CLI, ngày tính

**Given** lịch sử có dưới 10 bước `done` cho một model
**When** tính baseline cho model đó
**Then** đánh dấu là chưa đủ mẫu và bổ sung bằng cách chạy thêm cho đủ 10

**Given** bộ số baseline đã có
**When** tính trung vị thời gian và trung vị token
**Then** hai con số đó trở thành mốc so sánh cho NFR8 (+15%) và NFR9 (+10%)

**Given** chưa có file baseline
**When** ai đó định bắt đầu Story 1.2
**Then** dừng lại — không story nào khác của epic này được bắt đầu trước khi 1.1 xong

### Story 1.2: Đọc cấu hình MCP của một dự án

As a người vận hành,
I want khai MCP server trong `clients/<slug>/mcp.json` và sửa file đó bất cứ lúc nào,
So that thay đổi có hiệu lực ngay mà không phải khởi động lại worker.

**Acceptance Criteria:**

**Given** `clients/<slug>/mcp.json` khai `enabled: true` ở gốc và một server `x` cũng `enabled: true`
**When** worker đọc cấu hình của dự án đó
**Then** trả về danh sách chứa server `x`

**Given** khoá `enabled` ở gốc file là `false`
**When** worker đọc cấu hình
**Then** trả về danh sách rỗng — đây là công tắc cấp dự án của FR34

**Given** file không tồn tại, hoặc không server nào bật
**When** worker đọc cấu hình
**Then** trả về danh sách rỗng, không ném lỗi, không in cảnh báo

**Given** file sai cú pháp JSON
**When** worker đọc lại sau khi mtime đổi
**Then** giữ nguyên cấu hình cũ trong bộ nhớ, in cảnh báo ra terminal kèm tên file, worker tiếp tục nhận job

**Given** file vừa bị sửa
**When** worker kiểm tra trước lần claim kế tiếp
**Then** nhận cấu hình mới mà không cần restart, và việc kiểm tra tốn dưới 50ms

### Story 1.3: Khai credential theo từng dự án và bơm vào tiến trình con

As a người vận hành,
I want khai đường dẫn credential trong `settings.local.toml` của từng dự án,
So that hai khách khác nhau dùng hai credential khác nhau, và bí mật không bao giờ rời khỏi máy.

**Acceptance Criteria:**

**Given** `clients/udom/settings.local.toml` có mục `[mcp.gdrive]` với `credentials_path`
**When** worker spawn một bước của dự án `udom`
**Then** env của tiến trình con có biến trỏ tới đúng đường dẫn đó
**And** `mcp.json` không chứa bất kỳ giá trị bí mật nào

**Given** hai dự án khai hai `credentials_path` khác nhau
**When** chạy một bước của từng dự án
**Then** env mỗi tiến trình chỉ chứa credential của dự án mình

**Given** một server đã khai nhưng thiếu mục `[mcp.<server>]` hoặc thiếu `credentials_path`
**When** worker dựng lệnh
**Then** bước fail với thông báo nêu đúng tên file và tên khoá còn thiếu, không spawn tiến trình

**Given** một bước đã chạy xong
**When** kiểm tra output gửi lên API, bản ghi trong DB, log worker và log bước
**Then** không nơi nào chứa nội dung file credential, và đường dẫn được che qua `_redact`

### Story 1.4: Danh sách mẫu server và ba hồ sơ quyền

As a người vận hành,
I want chọn server từ danh sách mẫu và chọn một hồ sơ quyền thay vì tick từng tool,
So that tôi không lỡ tay bật nhầm tool xoá file của khách.

**Acceptance Criteria:**

**Given** `config/mcp_templates.toml` khai các mẫu server và ba hồ sơ `read-only`, `read-create`, `read-write`
**When** `mcp.json` khai một `template` và một `profile`
**Then** worker phân giải ra danh sách tool cụ thể của hồ sơ đó

**Given** hồ sơ `read-create`
**When** phân giải danh sách tool
**Then** danh sách gồm tool đọc và tool tạo mới, không gồm tool sửa hay tool xoá

**Given** `mcp.json` khai một `template` không có trong danh sách mẫu
**When** worker dựng lệnh
**Then** bước fail, thông báo liệt kê các mẫu hợp lệ

**Given** bất kỳ mẫu nào trong `config/mcp_templates.toml`
**When** kiểm tra lệnh chạy của nó
**Then** không mẫu nào dùng `npx -y`; mọi mẫu trỏ vào đường dẫn đã cài sẵn trên host

### Story 1.5: Bước chạy được với MCP của đúng dự án mình

As a agent thực thi một bước workflow,
I want nhận đúng những MCP tool của dự án đang làm,
So that tôi đọc được nguồn ngoài mà không cần ai dán tài liệu vào prompt.

**Acceptance Criteria:**

**Given** dự án có ít nhất một server đang bật
**When** worker spawn `claude -p`
**Then** lệnh có `--mcp-config` dạng chuỗi JSON inline, có `--strict-mcp-config`, và có `--allowedTools mcp__<server>` cho từng server
**And** các tham số cũ như `--add-dir`, `--model`, `--permission-mode` giữ nguyên

**Given** dự án không có server nào bật
**When** worker spawn `claude -p`
**Then** lệnh không có thêm bất kỳ tham số mới nào, giống hệt trước khi có tính năng này

**Given** một server đã kết nối
**When** sự kiện `system/init` tới
**Then** log sống hiện một dòng dạng `🔌 MCP: <server> · N tool` cho mỗi server

**Given** agent gọi một tool thuộc hồ sơ đã bật
**When** tool chạy
**Then** không xuất hiện lỗi đòi cấp quyền thủ công cho tool đó

### Story 1.6: Chứng minh cô lập và tương thích ngược

As a người vận hành,
I want bằng chứng rằng dự án này không thấy được gì của dự án khác và mã cũ không bị ảnh hưởng,
So that tôi dám cắm tài liệu của khách vào mà không sợ lộ chéo.

**Acceptance Criteria:**

**Given** dự án A khai server `a`, dự án B khai server `b`
**When** chạy một bước của A rồi một bước của B
**Then** `system/init` của A chỉ liệt kê `a`, của B chỉ liệt kê `b`

**Given** tài khoản Claude có connector claude.ai đang bật
**When** chạy một bước có khai MCP riêng
**Then** `system/init` không liệt kê connector nào của tài khoản

**Given** cùng một bước và cùng cấu hình MCP
**When** chạy bằng tài khoản Pro thứ nhất rồi tài khoản Pro thứ hai
**Then** danh sách server và danh sách tool trong `system/init` giống hệt nhau

**Given** bộ test `tests/test_worker_accounts.py` chưa bị sửa
**When** chạy lại sau toàn bộ thay đổi của epic này
**Then** kết quả không khác gì trước: 0 test hỏng, 0 test phải sửa

## Epic 2: Hỏng thì biết hỏng ở đâu

Bước chết vì MCP thì thông báo chỉ thẳng nguyên nhân và chỗ sửa. Phân biệt được bốn loại hỏng, và lỗi
xác thực của Google không còn làm worker đánh dấu oan tài khoản Claude Pro.

### Story 2.1: Server không khởi động nổi thì bỏ cuộc sớm

As a người vận hành,
I want bước dừng sau 20 giây nếu server không lên được,
So that tôi không mất nửa tiếng chờ một tiến trình đã chết.

**Acceptance Criteria:**

**Given** một server cấu hình sai nên không khởi động được
**When** worker spawn bước
**Then** sau tối đa 20 giây không thấy `system/init`, worker kết thúc tiến trình và fail bước
**And** thời gian chờ không kéo tới `STEP_TIMEOUT_S`

**Given** server khởi động bình thường trong vài giây
**When** `system/init` tới
**Then** mốc thời gian được huỷ và bước chạy tiếp không bị ảnh hưởng

### Story 2.2: Bốn nguyên nhân hỏng, mỗi nguyên nhân một thông báo

As a người vận hành lúc 11 giờ đêm,
I want thông báo lỗi nói thẳng nguyên nhân và chỗ sửa,
So that tôi không đi nghi ngờ mạng, Google và service account trong khi lỗi nằm ở cấu hình.

**Acceptance Criteria:**

**Given** một trong bốn tình huống hỏng xảy ra
**When** bước fail
**Then** thông báo nêu đúng một trong bốn nguyên nhân: chưa cấp quyền tool, thiếu credential, server không khởi động được, server trả lỗi

**Given** bất kỳ thông báo lỗi cấu hình nào
**When** người vận hành đọc nó
**Then** thông báo có đủ hai vế là nguyên nhân và chỗ cần sửa, trong đó chỗ cần sửa nêu tên file cùng tên khoá hoặc vị trí trên dashboard

**Given** bốn tình huống hỏng được dựng trong test
**When** chạy bộ test
**Then** mỗi tình huống cho ra đúng loại thông báo của nó, không nhầm lẫn

### Story 2.3: Lỗi xác thực của MCP không được đổ oan cho tài khoản Claude

As a người vận hành,
I want worker phân biệt được Google từ chối với token Claude hỏng,
So that tài khoản Pro của tôi không bị đánh dấu lỗi và loại khỏi vòng xoay vì một lỗi không phải của nó.

**Acceptance Criteria:**

**Given** service account bị thu quyền nên MCP server trả lỗi 401
**When** bước fail
**Then** thông báo nêu nguyên nhân là credential của server, không phải tài khoản Claude
**And** không tài khoản Claude nào bị đánh dấu lỗi hay bị cho nghỉ

**Given** tài khoản Claude thật sự hết quota
**When** bước fail
**Then** hành vi xoay tài khoản giữ nguyên y như trước khi có tính năng này

**Given** các regex nhận diện quota và auth hiện có trong `_StepWatch`
**When** xem diff của story này
**Then** không regex nào bị sửa, chỉ có trường mới được thêm

### Story 2.4: Đối chiếu bộ server thực tế với cấu hình đã khai

As a người vận hành,
I want so được cái đang chạy với cái tôi đã khai,
So that tôi kiểm chứng được sự cô lập bằng dữ liệu chứ không bằng niềm tin vào mã.

**Acceptance Criteria:**

**Given** một bước đã chạy xong
**When** xem log của bước
**Then** log chứa danh sách server thực tế mà `system/init` báo về

**Given** cấu hình khai ba server nhưng chỉ hai cái kết nối được
**When** bước chạy
**Then** log nêu rõ server nào không kết nối được, không lặng lẽ chạy tiếp với hai cái

### Story 2.5: Từ chối sớm những thứ chắc chắn không chạy được

As a người vận hành,
I want hệ thống chặn ngay từ đầu những cấu hình không thể hoạt động,
So that tôi không phát hiện ra lúc đang chạy dở một run quan trọng.

**Acceptance Criteria:**

**Given** phiên bản Claude Code CLI thấp hơn 2.1.273
**When** worker khởi động và có dự án khai MCP
**Then** in cảnh báo lúc khởi động, và bước có MCP fail với lý do phiên bản
**And** worker không âm thầm bỏ các cờ MCP rồi chạy tiếp

**Given** `mcp.json` khai một server không thuộc danh sách mẫu
**When** worker dựng lệnh
**Then** bước fail với lý do chỉ hỗ trợ server trong danh sách mẫu, kèm hướng dẫn cách khai thủ công trên host

## Epic 3: Cắm dự án mà không mở editor

Thêm server, chọn hồ sơ quyền, bật tắt, xem trạng thái — toàn bộ trên dashboard. File vẫn là nguồn sự thật.

### Story 3.1: API đọc và ghi cấu hình MCP của một dự án

As a dashboard,
I want đọc và ghi `clients/<slug>/mcp.json` qua API,
So that giao diện sửa được cấu hình mà không ai phải mở editor.

**Acceptance Criteria:**

**Given** `docker-compose.yml` mount `../clients:/clients` cho ghi
**When** API ghi `mcp.json` của một dự án
**Then** file trên đĩa đổi, và `git diff` đọc ra được thay đổi đó

**Given** API trả về cấu hình của một dự án
**When** xem payload
**Then** payload có tên server, trạng thái bật tắt, hồ sơ quyền, và cờ cho biết credential có hay thiếu
**And** payload không chứa đường dẫn hay nội dung credential

**Given** mã của `dashboard/api`
**When** xem các câu lệnh import
**Then** không chỗ nào import `worker.py`

### Story 3.2: Tab MCP của dự án trên dashboard

As a người vận hành,
I want thêm server, chọn hồ sơ quyền, bật tắt ngay trên dashboard,
So that cắm xong một dự án trong 15 phút mà không đụng tới editor.

**Acceptance Criteria:**

**Given** một dự án chưa khai MCP
**When** mở tab MCP và thêm một server từ danh sách mẫu
**Then** `clients/<slug>/mcp.json` được tạo với server đó và hồ sơ quyền đã chọn

**Given** một server đang bật
**When** bấm tắt
**Then** cờ `enabled` của server đó thành `false`, và bước kế tiếp không còn server đó

**Given** một dự án có nhiều server
**When** bấm công tắc cấp dự án
**Then** khoá `enabled` ở gốc file thành `false` và toàn bộ MCP của dự án tắt bằng một thao tác

### Story 3.3: Trạng thái kết nối và tình trạng credential

As a người vận hành,
I want nhìn dashboard là biết server nào nối được và server nào còn thiếu credential,
So that tôi sửa đúng chỗ trước khi bấm chạy.

**Acceptance Criteria:**

**Given** worker đang chạy và đã chạy ít nhất một bước có MCP
**When** mở tab MCP
**Then** mỗi server hiện trạng thái kết nối của lần gần nhất và tình trạng credential có hay thiếu

**Given** trạng thái MCP được gửi lên
**When** xem đường truyền
**Then** nó đi ké body của `/claim` và heartbeat sẵn có, không endpoint mới, không vòng poll mới

**Given** worker đang tắt
**When** mở tab MCP
**Then** giao diện nói rõ worker offline thay vì hiện trạng thái cũ như thể đang sống

## Epic 4: Đọc và ghi tài liệu thật của khách

Agent đọc spec từ Drive của khách và ghi báo cáo vào Shared Drive. Đây là giá trị đích.

### Story 4.1: Cài và ghim server Google trên host

As a người vận hành,
I want server Google được cài sẵn ở một phiên bản cố định,
So that mỗi lần chạy không tải mã mới từ internet về máy tôi.

**Acceptance Criteria:**

**Given** server được cài tại `vendor/mcp/google-drive-mcp/` ở một phiên bản đã ghim
**When** `mcp.json` trỏ tới nó
**Then** lệnh chạy là `node <path>/dist/index.js`, không phải `npx -y`

**Given** phiên bản đã cài
**When** xem `config/mcp_templates.toml`
**Then** phiên bản đó được ghi lại để tái lập được

**Given** `.gitignore`
**When** kiểm tra
**Then** `vendor/mcp/` đã được loại khỏi git

### Story 4.2: Agent đọc tài liệu khách từ thư mục được chia sẻ

As a agent thực thi bước analyst,
I want đọc trực tiếp spec của khách trong Drive,
So that tôi làm việc trên bản mới nhất chứ không phải bản ai đó dán vào tuần trước.

**Acceptance Criteria:**

**Given** khách đã chia sẻ một thư mục cho email của service account
**When** agent gọi tool đọc trên một file trong thư mục đó
**Then** nội dung trả về đúng

**Given** một file nằm ngoài phạm vi đã chia sẻ
**When** agent gọi tool đọc trên file đó
**Then** Google từ chối, và bước báo lỗi nêu đúng nguyên nhân là phạm vi truy cập

**Given** cấu hình đang chạy của một dự án
**When** người vận hành cần trả lời khách rằng hệ thống đọc được những gì
**Then** câu trả lời rút ra được từ `declared_write_scope` và trang chia sẻ của Google, không cần đọc mã

### Story 4.3: Agent ghi vào Shared Drive và không ghi đè thứ gì

As a khách hàng,
I want chắc chắn hệ thống chỉ thêm file mới chứ không sửa tài liệu sẵn có của tôi,
So that tôi dám cấp quyền ghi.

**Acceptance Criteria:**

**Given** service account đã là Content Manager của một Shared Drive
**When** agent tạo một file mới trong đó
**Then** file được tạo thành công, không gặp lỗi hết hạn mức lưu trữ

**Given** hồ sơ quyền `read-create` đang bật
**When** agent thử gọi một tool sửa hoặc xoá
**Then** lời gọi bị từ chối vì tool đó không nằm trong `--allowedTools`

**Given** một thư mục My Drive thường được chia sẻ quyền Editor, không phải Shared Drive
**When** agent thử tạo file
**Then** lỗi được báo kèm hướng dẫn chuyển sang Shared Drive, không để người vận hành tự đoán

### Story 4.4: Nhật ký từng thao tác ghi

As a người vận hành,
I want mỗi lần agent ghi gì đó đều để lại dấu vết,
So that khi khách hỏi file này ở đâu ra thì tôi lần ngược được.

**Acceptance Criteria:**

**Given** agent gọi một tool ghi
**When** thao tác hoàn tất
**Then** log của bước có một dòng kèm tên và định danh của đối tượng đích

**Given** nhật ký của một lần chạy
**When** tra cứu sau 30 ngày
**Then** thông tin vẫn còn và đủ để đối chiếu với nội dung trên Drive

### Story 4.5: Đối chiếu chi phí sau khi bật MCP

As a người vận hành,
I want biết bật MCP làm mỗi bước chậm và đắt thêm bao nhiêu,
So that tôi quyết định được có nên bật cho mọi dự án hay không.

**Acceptance Criteria:**

**Given** baseline từ Story 1.1 và một dự án đã cắm Google
**When** chạy cùng bước đó 10 lần có MCP
**Then** ghi lại thời gian và token rồi so với baseline

**Given** kết quả đo
**When** phụ trội thời gian vượt 3,0 giây hoặc phụ trội token vượt 200
**Then** ghi cảnh báo vào tài liệu kết quả, nêu server nào gây tốn nhất

**Given** kết quả đo nằm trong ngưỡng
**When** kết thúc
**Then** NFR8 và NFR9 được đánh dấu đã nghiệm thu, kèm số thật


## Final Validation

### FR Coverage — 34/34

Mỗi FR có ít nhất một story với acceptance criteria phủ nó:

| Epic | FR → Story |
|---|---|
| 1 | FR1→1.2 · FR2→1.2 · FR4→1.4 · FR5→1.4 · FR6→1.2 · FR7→1.2 · FR8→1.2+3.1 · FR9→1.3 · FR10→1.3 · FR11→1.3 · FR13→1.3 · FR14→1.5 · FR15→1.5 · FR16→1.6 · FR17→1.5+1.6 · FR24→1.5 · FR30→1.6 · FR31→1.5+1.6 · FR33→1.1 · FR34→1.2 |
| 2 | FR18→2.5 · FR19→2.1 · FR26→2.2 · FR27→2.2 · FR28→2.3 · FR29→2.4 · FR32→2.4 |
| 3 | FR3→3.2 · FR12→3.3 · FR25→3.3 |
| 4 | FR20→4.2 · FR21→4.3 · FR22→4.4 · FR23→4.2 |

### Architecture Implementation Validation

- **Starter template:** Architecture xác nhận **không có** (brownfield). Epic 1 Story 1 vì vậy là
  *đo baseline*, không phải lệnh khởi tạo dự án. Đây là sai lệch có chủ ý so với mặc định của
  workflow, lý do ghi ở AR1.
- **Tạo bảng dữ liệu:** tính năng này **không tạo bảng mới nào**. Cấu hình nằm trong file, trạng thái
  nằm trong heartbeat in-memory. Không có công việc dựng schema nào để mà làm sớm.

### Story Quality & Dependency Validation

- 19 story, mỗi story vừa một phiên làm việc của một agent dev
- Trong từng epic, story thứ M chỉ dựa vào story trước nó — không có phụ thuộc ngược
- Epic 2, 3, 4 chỉ cần Epic 1; không epic nào cần epic tương lai

### Điểm yếu đã biết, chấp nhận có ý thức

- **FR8** (sửa file trực tiếp) không có story riêng. Nó là hệ quả của thiết kế "file là nguồn sự thật"
  và được nghiệm thu gián tiếp qua AC của Story 1.2 và 3.1.
- **FR18** phủ một phần, đúng như Architecture đã ghi: không có cách tổng quát phát hiện server đòi
  OAuth tương tác. Story 2.5 thay bằng giới hạn ở danh sách mẫu.
