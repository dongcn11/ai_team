---
title: 'Baseline hiệu năng trước/sau khi bật MCP'
type: 'measurement'
story: 'Epic 1 / Story 1.1'
created: '2026-09-22'
status: 'done — nhưng đã đổi cách đo so với AC ban đầu'
---

# Baseline hiệu năng cho tính năng MCP per-project

## Tóm tắt

Phụ trội của MCP là **cố định**, không theo tỷ lệ: **+0,31 giây** và **+13 token** cho mỗi bước,
bất kể bước dài hay ngắn. Chi phí tiền không đổi ở mức đo được.

## Vì sao KHÔNG dùng baseline theo dân số như AC ban đầu

AC gốc của Story 1.1 nói: truy vấn lịch sử `workflow_step_jobs`, lấy trung vị, so sánh. Đã thử —
và cách đó **không dùng được**.

Lịch sử có 48 bước, 31 bước `done`, nhưng chỉ **4 bước có số liệu** (cột `duration_ms`/`usage` mới
được thêm cùng tính năng xoay tài khoản). Bốn mẫu đó:

| id | model | thời gian | chi phí | lượt |
|---|---|---|---|---|
| 52 | opus-5[1m] | 3,9 s | $0,46 | 2 |
| 53 | opus-5[1m] | **1.126 s** | **$13,25** | 181 |
| 54 | opus-5[1m] | 149,9 s | $0,95 | 23 |
| 55 | opus-5[1m] | 68,5 s | $0,48 | 14 |

Chênh **285 lần** về thời gian và **28 lần** về chi phí. Biến thiên đến từ *nội dung công việc*
(2 lượt so với 181 lượt), không từ hạ tầng. Lấy trung vị của phân bố này rồi đòi phát hiện chênh
lệch 15% là đo nhiễu, không đo tín hiệu.

**Thay bằng A/B có kiểm soát:** cùng một prompt, cùng model, chạy 3 lần không MCP và 3 lần có MCP.
Nội dung công việc bị giữ cố định nên phần chênh còn lại đúng là phụ trội hạ tầng.

## Cách đo

- Prompt: `Reply with exactly one word: ok` (không gọi tool — đo phụ trội của việc *có* MCP,
  không phải chi phí *dùng* MCP)
- Model: `haiku` · CLI 2.1.273 · Windows 11 · 3 lần mỗi nhánh
- Nhánh có MCP: một stdio server local (`env-probe-server.js`, 1 tool) + `--strict-mcp-config`
  + `--allowedTools`
- Script: `scratchpad/bench.py`; số liệu thô: `scratchpad/bench-raw.json`

## Kết quả (trung vị của 3 lần)

| Chỉ số | Không MCP | Có MCP | Chênh |
|---|---|---|---|
| Thời gian tổng | 3,44 s | 3,75 s | **+0,31 s** |
| Tới lúc `system/init` | 1,02 s | 1,30 s | **+0,28 s** |
| Chi phí | $0,0142 | $0,0142 | ~0 |
| cache_write token | 5.053 | 5.066 | **+13** |
| cache_read token | 29.072 | 29.072 | 0 |
| output token | 45 | 44 | 0 |

**Đọc số:** gần như toàn bộ phụ trội nằm ở lúc khởi động server (+0,28 s trong tổng +0,31 s). Token
gần như không tăng vì MCP tool nằm sau `ToolSearch` — chỉ tên tool vào prompt, không phải schema
đầy đủ.

## Hệ quả: NFR8 và NFR9 phải viết lại

Ngưỡng theo phần trăm vừa sai bản chất vừa không đo được:

| Bước | +15% nghĩa là | Phụ trội thật |
|---|---|---|
| 3,4 giây | 0,5 giây | 0,31 giây → **đạt** |
| 68 giây | 10 giây | 0,31 giây → đạt quá dễ, ngưỡng vô nghĩa |
| 1.126 giây | **169 giây** | 0,31 giây → ngưỡng vô dụng hoàn toàn |

Ngưỡng nên là **tuyệt đối**:

- **NFR8 (mới):** phụ trội thời gian cố định **≤ 1,0 giây** mỗi bước có MCP
- **NFR9 (mới):** phụ trội **≤ 200 token** mỗi bước có MCP

Số đo hôm nay (0,31 s · 13 token) nằm sâu trong cả hai ngưỡng.

## Đo lại bằng server Google thật (Story 4.1, 2026-09-22)

`@us-all/google-drive-mcp@1.15.8`, 100 tool, hồ sơ `read-only` cho phép 15 tool. Cùng phương pháp,
3 lần mỗi nhánh.

| Chỉ số | Không MCP | Google (100 tool) | Chênh |
|---|---|---|---|
| Thời gian tổng | 3,50 s | 5,25 s | **+1,75 s** |
| Tới `system/init` | 1,02 s | 2,97 s | +1,95 s |
| cache_write token | 5.214 | 5.346 | **+132** |
| Chi phí | $0,01450 | $0,01477 | +$0,0003 |

**So với ngưỡng:**

| NFR | Ngưỡng | Đo được | Kết quả |
|---|---|---|---|
| NFR9 token | ≤ 200 | +132 | ✅ đạt |
| NFR8 thời gian | ≤ 3,0 s (đã nâng) | +1,75 s | ✅ đạt |

Nguyên nhân gần như toàn bộ nằm ở khởi động: tiến trình Node nạp 160 package mất ~2 giây, và mỗi
bước là một tiến trình mới nên trả phí đó mỗi lần. Không tối ưu được từ phía ta — đó là server của
bên thứ ba.

**Đặt trong bối cảnh:** các bước thật trong lịch sử dài 68 s đến 1.126 s. Phí cố định 1,75 s là
0,2%–2,6% của chúng. Bước ngắn nhất từng ghi nhận là 3,9 s, ở đó 1,75 s là 45%.

**Đã quyết định (2026-09-22, chủ sản phẩm):** nâng NFR8 lên **≤ 3,0 giây**. Phí 1,75 s là chi phí
cố định của việc khởi động tiến trình Node, không tối ưu được từ phía ta; ngưỡng 3 s chừa chỗ cho
server thứ hai. Với mức mới: **✅ đạt (+1,75 s / 3,0 s)**.

Hạn 20 giây của `MCP_START_TIMEOUT_S` vẫn rất rộng so với 3 giây khởi động thật.
