---
title: 'Chuyển tài khoản Claude Pro trên dashboard + tự chuyển khi hết quota'
type: 'feature'
created: '2026-09-18'
status: 'done'
baseline_commit: 'b7a3c5fbc46adac388487703a2275b83629920e1'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Worker chạy `claude -p` bằng đăng nhập trong `~/.claude/.credentials.json`. Hết quota 5h là phải ra terminal `claude auth login` sang tài khoản Pro khác và xác nhận trên trình duyệt — mỗi lần, mỗi tài khoản.

**Approach:** Worker đọc danh sách tài khoản (tên + token dài hạn từ `claude setup-token`) trong `config/claude_accounts.local.toml` và bơm `CLAUDE_CODE_OAUTH_TOKEN` vào env khi spawn — đã xác nhận trên CLI 2.1.273 env này ghi đè `.credentials.json` (`authMethod: oauth_token`). Dashboard chỉ chọn *tên* tài khoản (Setting), worker báo trạng thái từng tài khoản qua heartbeat. Gặp `rate_limit_event` bị từ chối → worker đánh dấu tài khoản đang nghỉ tới `resetsAt`, chuyển sang tài khoản kế tiếp và chạy lại bước nếu chưa gọi tool nào.

## Boundaries & Constraints

**Always:**
- Token chỉ sống trong file local trên host và env của tiến trình con — không qua API, không vào DB, không hiện lên UI. API/UI chỉ thấy `name` + trạng thái.
- Không có file tài khoản → hành vi y hệt hiện tại (dùng `.credentials.json`), snapshot rỗng, không lỗi.
- Chỉ tự chạy lại bước khi chưa có `tool_use` nào trong luồng sự kiện — Claude đã sửa file thì fail như cũ, lỗi ghi rõ đã chuyển sang tài khoản nào để người dùng bấm "chạy lại".
- Tài khoản chọn trên dashboard áp cho bước *kế tiếp*; bước đang chạy giữ nguyên.
- Sửa file TOML không cần khởi động lại worker (đọc lại theo mtime); trạng thái nghỉ/lỗi giữ theo `name`.
- Giữ nguyên tuần tự 1 bước/lần và mọi giới hạn trong docstring `worker.py`.

**Ask First:**
- Muốn đổi sang `CLAUDE_CONFIG_DIR` (phương án A) nếu token OAuth không được chấp nhận khi chạy thật.
- Muốn áp tài khoản Claude cho pipeline `main.py` (`/api/run-jobs`) — ngoài phạm vi này.

**Never:**
- Không tự đăng nhập/`setup-token` hộ; không lưu token vào `Setting`; không đụng `.credentials.json`.
- Không thêm `--dangerously-skip-permissions`; không chạy song song 2 tài khoản.
- Không sửa `ActiveTasks.tsx`, `RunConsole.tsx` (đang có thay đổi chưa commit của người dùng).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chọn tay | Setting `claude_account=pro-2`, pro-2 sẵn sàng | Bước kế tiếp spawn với token pro-2; log `🔑 Tài khoản Claude: pro-2` | N/A |
| Tên không có trong file | Setting `claude_account=xyz` | Dùng tài khoản sẵn sàng đầu tiên theo thứ tự file; log cảnh báo | N/A |
| Hết quota, chưa tool_use | `rate_limit_event.status=rejected` hoặc result lỗi khớp `usage limit \| rate limit \| hit your limit`; `auto_switch=true`; còn tài khoản khác | Đánh dấu nghỉ tới `resetsAt` (thiếu → +30 phút); log `🔁 pro-1 hết quota → pro-2`; chạy lại cùng lệnh, tối đa = số tài khoản | Hết tài khoản → `failed`, lỗi nêu giờ reset sớm nhất |
| Hết quota, đã tool_use | như trên nhưng đã có `tool_use` | `failed`, lỗi: "pro-1 hết quota (reset HH:MM). Đã chuyển sang pro-2 — bấm chạy lại" | Người dùng retry |
| Token hỏng | result lỗi khớp `authentication \| 401 \| invalid.*token` | Tài khoản → `error` (không hết hạn theo giờ), chuyển như case hết quota | Mở lại khi mtime file đổi |
| `auto_switch=false` | hết quota | Không chuyển; chỉ đánh dấu nghỉ và `failed` với lỗi rõ | Người dùng chọn tay |
| Không có file | `config/claude_accounts.local.toml` vắng | Env không đổi; heartbeat `accounts: []`; UI hiện hướng dẫn tạo file | N/A |
| resetsAt đơn vị | epoch giây hoặc mili-giây | > 1e12 coi là ms | N/A |

</frozen-after-approval>

## Code Map

- `worker.py` -- `_run_step_job` (spawn `claude -p`, env merge), `_run_streaming` (đọc stream-json), `_summarize_event` (đã có nhánh `rate_limit_event`), `_claim_step` (POST body `{}`), `_project_git_env` (mẫu đọc TOML local)
- `dashboard/api/worker_heartbeat.py` -- `touch()` / `status()` in-memory; nơi giữ snapshot tài khoản
- `dashboard/api/routers/workflow_jobs.py` -- `claim_job` (trả `WorkflowStepJobOut`), `worker_status` (GET `/worker`)
- `dashboard/api/schemas.py` -- `WorkflowStepJobOut`, thêm schema body claim
- `dashboard/api/routers/settings.py` -- CRUD `Setting` đã đủ dùng cho `claude_account`, `claude_auto_switch`
- `dashboard/src/hooks/useWorkflows.ts` -- `useWorkerStatus` (poll `/api/workflow-jobs/worker` 5s)
- `dashboard/src/hooks/useSettings.ts` -- `getValue`/`saveSetting`
- `dashboard/src/components/Settings.tsx` -- thêm card; `dashboard/src/App.css` -- append class mới
- `.gitignore` -- thêm `claude_accounts.local.toml`

## Tasks & Acceptance

**Execution:**
- [x] `config/claude_accounts.example.toml` -- mẫu `[[account]] name/token` + hướng dẫn `claude setup-token`; `.gitignore` thêm `claude_accounts.local.toml` -- token không lọt git
- [x] `worker.py` -- thêm `_Accounts` (load theo mtime, `pick(preferred)`, `cool(name, until)`, `mark_error(name)`, `snapshot()`), `_StepWatch.feed(ev)` (tool_used / limit_hit / resets_at / auth_failed), `_run_streaming` nhận `watch`, `_claim_step` gửi `{"accounts": snapshot}`, `_run_step_job` vòng lặp chuyển tài khoản theo ma trận -- lõi tính năng
- [x] `tests/test_worker_accounts.py` -- pytest cho `_StepWatch` (từng dòng ma trận) và `_Accounts.pick/cool/reload` với file tạm -- ma trận có test
- [x] `dashboard/api/worker_heartbeat.py` -- `touch(accounts=None)` lưu snapshot; `status()` trả thêm `accounts` -- UI đọc trạng thái
- [x] `dashboard/api/schemas.py` + `routers/workflow_jobs.py` -- `WorkflowStepJobClaim(accounts)`; claim trả `claude_account`, `claude_auto_switch` từ `Setting` (mặc định `""`/`true`) -- đường xuống
- [x] `dashboard/src/hooks/useWorkflows.ts` -- kiểu `WorkerStatus` thêm `accounts`; `Settings.tsx` -- card "Tài khoản Claude": danh sách (🟢 sẵn sàng / ⏳ nghỉ tới HH:MM / 🔴 lỗi), radio chọn → `claude_account`, checkbox → `claude_auto_switch`, hướng dẫn khi rỗng/worker offline; `App.css` append `.claude-acc-*` -- người dùng chọn không cần terminal

**Acceptance Criteria:**
- Given worker chạy với 2 tài khoản trong file, when mở Settings, then thấy 2 dòng đúng tên, trạng thái, và dòng đang chọn.
- Given chọn `pro-2` rồi Save, when bước kế tiếp được claim, then log sống của bước có `🔑 Tài khoản Claude: pro-2`.
- Given không có file tài khoản, when chạy bước, then bước chạy như trước và Settings hiện hướng dẫn, không lỗi console.
- Given `pytest tests/test_worker_accounts.py`, when chạy, then pass toàn bộ.

## Design Notes

Snapshot đi kèm body POST `/claim` (worker đã gọi mỗi 3s) thay vì endpoint mới — không thêm vòng poll. Body cũ `{}` vẫn hợp lệ nhờ default.

```python
# worker: env cho 1 bước
env = {**os.environ, **git_env, **(acc.env() if acc else {})}   # acc.env() = {"CLAUDE_CODE_OAUTH_TOKEN": token}
# claim trả về (pydantic copy, không đụng ORM):
out = WorkflowStepJobOut.model_validate(job).model_copy(update={"claude_account": ..., "claude_auto_switch": ...})
```

## Verification

**Commands:**
- `python -m py_compile worker.py dashboard/api/worker_heartbeat.py dashboard/api/routers/workflow_jobs.py dashboard/api/schemas.py` -- expected: không lỗi
- `python -m pytest tests/test_worker_accounts.py -q` -- expected: all passed
- `cd dashboard && npx tsc --noEmit` -- expected: 0 lỗi
- `CLAUDE_CODE_OAUTH_TOKEN=x claude auth status --json` -- expected: `authMethod: "oauth_token"` (đã xác nhận)

**Manual checks (if no CLI):**
- Tạo `config/claude_accounts.local.toml` 2 tài khoản, chạy `python worker.py`, mở Settings → thấy card, chọn tài khoản, Save; bấm ▶ 1 bước, log có dòng 🔑.

## Review Findings (3 reviewer, đã xử lý)

Không có intent_gap / bad_spec. Đã vá (patch): `resetsAt` đã qua → vẫn nghỉ mặc định + chặn "chuyển sang chính nó"; `_epoch` bỏ giá trị ngoài [-1 ngày, +30 ngày] để `snapshot()` không ném; TOML lỗi cú pháp / `[account]` đơn / sai kiểu / trùng tên → giữ danh sách cũ + cảnh báo; regex quota bỏ "limit reached" chung chung và bỏ qua `error_max_turns`; regex auth bỏ "401" trần, stderr chỉ kết luận token hỏng khi CLI chết trước khi có `result`; `watch.feed` bọc try/except (1 sự kiện lạ không được treo CLI); tự chuyển tắt + tài khoản chọn đang nghỉ → fail rõ, không lén dùng tài khoản khác; `_claude_prefs` đọc trước commit; schema claim `Literal` + tối đa 50; UI luôn có dòng "Tự động" để bỏ chọn tên cũ, mốc nghỉ đã qua coi là sẵn sàng, wording offline; che token đã biết trong log/output trước khi gửi API; docstring + example.toml nói đúng phạm vi bảo vệ.
Reject: bỏ metrics của lần chạy bị chặn (≈0 chi phí); API không có auth là thuộc tính sẵn có của dashboard localhost.
Để người dùng quyết (ngoài spec): gate "chưa gọi tool nào" theo spec là mọi tool_use kể cả Read/Grep — nới thành "chưa gọi tool ghi (Edit/Write/Bash…)" sẽ tự chuyển được nhiều ca hơn.

## Suggested Review Order

**Điểm vào — cơ chế chuyển tài khoản trong worker**

- Vòng chạy 1 bước: chọn tài khoản, spawn, đọc kết quả, quyết định chuyển hay fail
  [`worker.py:859`](../../worker.py#L859)

- Tự chuyển chỉ khi chưa có tool_use; đã gọi tool thì fail kèm tên tài khoản kế tiếp
  [`worker.py:925`](../../worker.py#L925)

- Ghi trạng thái tài khoản trước khi tính chuyện chuyển — kể cả khi bước vẫn xong
  [`worker.py:905`](../../worker.py#L905)

**Nhận diện hết quota / token hỏng từ stream-json**

- `_StepWatch`: tool_used / limit_hit / auth_failed / resets_at từ từng sự kiện
  [`worker.py:722`](../../worker.py#L722)

- stderr chỉ kết luận token hỏng khi CLI chết trước khi có `result` (tránh "401" của MCP)
  [`worker.py:756`](../../worker.py#L756)

- Regex bám câu CLI thật; không bắt "limit reached" chung chung
  [`worker.py:526`](../../worker.py#L526)

- `resetsAt` ngoài cửa sổ hợp lệ → None, không để 1 giá trị rác chặn worker
  [`worker.py:534`](../../worker.py#L534)

- `watch.feed` bọc try/except — thread đọc stdout chết là CLI treo tới timeout
  [`worker.py:384`](../../worker.py#L384)

**Danh sách tài khoản + trạng thái (host)**

- Đọc lại theo (mtime, size); file hỏng thì giữ danh sách cũ, không rơi về ~/.claude
  [`worker.py:604`](../../worker.py#L604)

- `pick(strict=)`: tự chuyển tắt thì không lén dùng tài khoản khác
  [`worker.py:645`](../../worker.py#L645)

- `cool()`: mốc reset đã qua → nghỉ mặc định; sau cool() tài khoản PHẢI hết usable
  [`worker.py:670`](../../worker.py#L670)

- Che token đã biết trước khi bất cứ gì lên API
  [`worker.py:713`](../../worker.py#L713)

- Snapshot đi kèm body `/claim` — không thêm endpoint, không thêm vòng poll
  [`worker.py:778`](../../worker.py#L778)

**API — đường xuống (Setting → claim) và đường lên (heartbeat)**

- Đọc `claude_account`/`claude_auto_switch` lúc claim, TRƯỚC commit
  [`workflow_jobs.py:62`](../../dashboard/api/routers/workflow_jobs.py#L62)

- Claim nhận snapshot, đẩy vào heartbeat; body `{}` của worker cũ vẫn hợp lệ
  [`workflow_jobs.py:74`](../../dashboard/api/routers/workflow_jobs.py#L74)

- Heartbeat giữ snapshot in-memory; `/run-jobs/claim` không gửi thì giữ bản cũ
  [`worker_heartbeat.py:38`](../../dashboard/api/worker_heartbeat.py#L38)

- Schema: `state` Literal, tối đa 50 tài khoản, không có trường token
  [`schemas.py:150`](../../dashboard/api/schemas.py#L150)

**UI — Settings**

- Card "Tài khoản Claude": radio chọn tên, checkbox tự chuyển, hint khi offline/rỗng
  [`Settings.tsx:116`](../../dashboard/src/components/Settings.tsx#L116)

- Mốc nghỉ đã qua coi là sẵn sàng; luôn có dòng "Tự động" để bỏ tên cũ
  [`Settings.tsx:127`](../../dashboard/src/components/Settings.tsx#L127)

- Gắn card vào trang, lưu qua `saveSetting` sẵn có
  [`Settings.tsx:83`](../../dashboard/src/components/Settings.tsx#L83)

**Phụ trợ**

- Test tích hợp vòng chuyển tài khoản bằng CLI giả (không cần Claude thật)
  [`test_worker_accounts.py:189`](../../tests/test_worker_accounts.py#L189)

- Test hồi quy cho từng finding của review
  [`test_worker_accounts.py:285`](../../tests/test_worker_accounts.py#L285)

- Kiểu `WorkerStatus.accounts` cho hook poll 5s
  [`useWorkflows.ts:164`](../../dashboard/src/hooks/useWorkflows.ts#L164)

- CSS card (append cuối file)
  [`App.css:1630`](../../dashboard/src/App.css#L1630)

- File mẫu + hướng dẫn `claude setup-token`; `.gitignore` chặn file local
  [`claude_accounts.example.toml:1`](../../config/claude_accounts.example.toml#L1)

