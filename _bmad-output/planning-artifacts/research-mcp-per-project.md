---
title: 'Nghiên cứu khả thi — MCP theo từng dự án cho worker headless'
type: 'technical-research'
created: '2026-09-22'
author: 'Winston (Architect)'
status: 'verified'
subject_system: 'ai_team_clean'
verified_on: 'Claude Code CLI 2.1.273, Windows 11, node v22.14.0'
context:
  - '_bmad-output/implementation-artifacts/spec-claude-account-switch.md'
  - 'worker.py'
---

# Khả thi: cấu hình MCP riêng cho từng dự án

Tài liệu này ghi lại **kết quả chạy thật**, không phải suy đoán từ tài liệu. Mọi khẳng định
dưới đây đều kèm cách tái lập.

## Câu hỏi gốc

Có cắm được MCP server (kiểu Google Drive) riêng cho từng dự án trong `clients/<slug>/`
để các bước workflow chạy `claude -p` dùng được không?

## Kết luận

**Có** — nhưng KHÔNG đi bằng claude.ai connector đang có sẵn. Phải khai MCP riêng từng dự án
qua `--mcp-config`, và với Google thì phải dùng service account thay vì OAuth tương tác.

## Bằng chứng thực nghiệm

### 1. `--mcp-config` + `--strict-mcp-config` chạy được headless trên Windows

Lệnh chạy thật:

    claude -p "ok" --model haiku --strict-mcp-config --mcp-config <file> \
           --output-format stream-json --verbose --permission-mode acceptEdits

Sự kiện `system/init` trả về:

    mcp_servers: [{"name": "probe", "status": "connected"}]
    tools: mcp__probe__read_file, mcp__probe__write_file, ... (14 tool)

Server dùng để thử: stdio qua `npx -y @modelcontextprotocol/server-filesystem`.

**Suy ra:** stdio MCP kết nối được trong tiến trình con headless; shim `npx` trên Windows
không gây lỗi như shim `claude.CMD` từng gây (xem `_resolve_claude` trong `worker.py`).

### 2. `--strict-mcp-config` cô lập thật sự

Cùng lần chạy trên, 3 claude.ai connector (`Claude Docs`, `Google Drive`, `zaico`) **biến mất**
khỏi danh sách. Chỉ còn `probe`.

**Suy ra:** cô lập MCP theo dự án là có thật. Nhưng nó cắt cả connector của tài khoản — đây là
đánh đổi, không phải tác dụng phụ.

### 3. ĐIỂM CHẶN: `acceptEdits` KHÔNG tự duyệt MCP tool

Worker hiện chạy `--permission-mode acceptEdits` (`worker.py`, biến `CLAUDE_ARGS`).

| Cờ | Kết quả gọi `mcp__probe__list_allowed_directories` |
|---|---|
| `--permission-mode acceptEdits` | ❌ *"requested permissions ... but you haven't granted it yet"* |
| `+ --allowedTools "mcp__probe"` | ✅ chạy, trả kết quả bình thường |

**Suy ra:** nếu cắm MCP vào worker mà quên `--allowedTools mcp__<server>`, MỌI bước có gọi MCP
đều hỏng, và log chỉ báo "cần duyệt quyền" — dễ bị chẩn đoán nhầm thành lỗi MCP server.

### 4. Google hiện tại là connector mức TÀI KHOẢN, không phải mức dự án

- `~/.claude.json` có `mcpServers: []` — rỗng. Không có khai báo local nào.
- `claude mcp list` vẫn hiện `claude.ai Google Drive: https://drivemcp.googleapis.com/mcp/v1`
  → connector đến từ phía server theo token đăng nhập.
- Worker **luân phiên** `CLAUDE_CODE_OAUTH_TOKEN` giữa các tài khoản Pro khi hết quota
  (xem `spec-claude-account-switch.md`).

**Suy ra hai hệ quả:**
1. Không thể scope connector theo dự án.
2. Tool khả dụng đổi theo tài khoản đang dùng → bước rơi trúng tài khoản chưa bật Drive sẽ mất
   tool **giữa chừng một run**. Lỗi không tất định.

### 5. OAuth tương tác không dùng được cho worker

`claude mcp login --no-browser` vẫn cần người dán lại redirect URL. Không có đường chạy ngầm.

## So sánh đường đi cho Google

| Cách | Headless | Per-project | Sống sót khi xoay tài khoản |
|---|---|---|---|
| claude.ai connector (hiện tại) | ✓ | ✗ | ✗ |
| Remote Google MCP + `claude mcp login` | ✗ | ~ (creds theo user) | ? chưa kiểm |
| **Google MCP + service account** | ✓ | ✓ | ✓ |

Cổng chặn của phương án service account **không nằm ở code**: cần Google Workspace admin bật
domain-wide delegation. Đó là phụ thuộc tổ chức, và nó quyết định lịch.

## Điểm chạm dự kiến trong mã nguồn

- `worker.py` → `_run_step_job`: nơi đang nối `--add-dir`, thêm `--mcp-config` /
  `--strict-mcp-config` / `--allowedTools`.
- `worker.py` → `_project_git_env`: **mẫu có sẵn** cho việc đọc cấu hình bí mật theo từng dự án
  (và theo từng agent) từ `clients/<slug>/settings.local.toml`.
- `clients/*` đã nằm trong `.gitignore` → chỗ chứa `mcp.json` an toàn sẵn.
- `dashboard/api/*`: chỉ hiển thị tên server + trạng thái. Bí mật không đi qua API/DB.

## Ràng buộc kế thừa từ spec-claude-account-switch

Những điều đã đóng băng ở tính năng trước, áp thẳng sang đây:

- Bí mật chỉ sống trong file local trên host và env tiến trình con. Không qua API, không vào DB,
  không hiện lên UI.
- Không có file cấu hình → hành vi y hệt hiện tại, không lỗi.
- Không thêm `--dangerously-skip-permissions`.
- Giữ tuần tự 1 bước/lần.

### 6. MCP server con THỪA KẾ env của tiến trình Claude Code

Viết một stdio MCP server tí hon (`env-probe-server.js`) chỉ có một tool: trả về
`process.env.MCP_PROBE_VAR`. Chạy:

    MCP_PROBE_VAR="gia-tri-tu-tien-trinh-cha-12345" claude -p "..."       --strict-mcp-config --mcp-config <file> --allowedTools "mcp__envprobe"

Kết quả tool trả về: `THAY-BIEN=gia-tri-tu-tien-trinh-cha-12345`.

**Suy ra:** worker bơm credential vào env tiến trình con — đúng khuôn `GH_TOKEN` trong
`_project_git_env` — thì MCP server nhận được. **File cấu hình MCP không cần chứa bí mật nào.** Đây là
phương án sạch nhất và nó khả thi.

### 7. --allowedTools chặn được ở MỨC TỪNG TOOL, và chặn thật

Cấp `mcp__fs__read_text_file` rồi bảo agent gọi `mcp__fs__write_file`:

    err=True | Claude requested permissions to use mcp__fs__write_file, but you haven't granted it yet.

Kiểm tra thư mục đích: **file không hề được tạo**. Không phải chỉ báo lỗi cho có.

Dạng phân tách bằng dấu phẩy cũng hoạt động: `--allowedTools "mcp__fs__a,mcp__fs__b"`.

**Suy ra:** hồ sơ quyền (danh sách tool) là cơ chế cưỡng chế thật cho FR21 "không ghi đè, không xoá".
Không cần viết lớp canh gác nào.

### 8. Claude Code ĐÈ phạm vi của server stdio bằng thư mục làm việc của nó

Truyền cho `@modelcontextprotocol/server-filesystem` một thư mục scratch qua argv, nhưng
`mcp__fs__list_directory` lại liệt kê **gốc repo**. Claude Code gửi thư mục làm việc của phiên (cwd +
`--add-dir`) xuống server qua giao thức *roots*, và server honor roots thay vì argv của nó.

**Suy ra hai điều:**

1. Với server local, `declared_write_scope` trong `mcp.json` **không** giới hạn được gì — đúng như
   gap G1 đã cảnh báo. Phạm vi thật của server local là thư mục làm việc của bước.
2. Với Google thì không ảnh hưởng: phạm vi do Google cưỡng chế qua chia sẻ, không qua roots.

### 9. Số tool trong log `init` là số server CUNG CẤP, không phải số được phép

`🔌 MCP: fs · connected · 14 tool` trong khi hồ sơ `read-only` chỉ cho 7. Sự kiện `init` liệt kê mọi
tool server đưa ra; `--allowedTools` lọc lúc GỌI. Đọc log nghiệm thu phải nhớ điều này.

## Câu hỏi còn mở (cần spike, đừng lên kế hoạch dựa trên giả định)

1. Server OAuth khai bằng `--mcp-config` có tự lấy được credential đã `claude mcp login` không?
2. Credential MCP lưu trong `~/.claude` có dùng chung được giữa các tài khoản Pro không?
3. Chi phí: MCP tool nằm sau `ToolSearch` (quan sát được trong log probe) nên không phình system
   prompt nhiều, nhưng tốn thêm 1 vòng gọi ở bước có dùng tool. Cần đo trước khi bật đại trà —
   `worker.py` đã ghi chú ~45K token tiền tố tính giá gấp đôi cho MỖI lần gọi `claude -p`.
