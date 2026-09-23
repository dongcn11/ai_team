---
title: 'Lịch chạy định kỳ theo dự án (cron) + quét thay đổi tài liệu'
type: 'feature'
created: '2026-09-23'
status: 'implemented'
baseline_commit: 'a3f5402f84ed69ee712119b192fca78611ebdbf4'
context:
  - '_bmad-output/planning-artifacts/research/technical-per-project-cron-scheduler-research-2026-09-22.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Mọi lần chạy pipeline đều phải có người bấm ▶. Không có cách hẹn "6h sáng hàng ngày, quét tài liệu dự án X xem có đổi gì không". Tài liệu trong `clients/{slug}/` là đầu vào điều khiển agent — tài liệu lệch mà không ai biết thì agent làm sai việc, và hiện không có gì phát hiện điều đó ngoài việc tình cờ vấp phải.

**Approach:** Thêm **schedule store** (bảng `schedules` trong Postgres) và **tick coordinator** (vòng lặp nền trong API, cạnh `_workflow_run_poll_loop`) — hai mảnh duy nhất còn thiếu; `run_jobs` đã là hàng đợi và `worker.py` đã là executor. Tick loop 60s đọc lịch đến hạn, quét tài liệu so với snapshot lần trước (`sha256` theo file), và **chỉ khi có thay đổi thật** mới thông báo và/hoặc chèn `run_jobs`. `croniter` + `zoneinfo` tính `next_run_at`; UNIQUE `(schedule_id, fire_time)` khoá mọi trường hợp bắn trùng. **`worker.py` không sửa một dòng.**

## Boundaries & Constraints

**Always:**
- `worker.py` giữ nguyên tuyệt đối — không thêm dependency, không sửa logic. Scheduler chỉ chèn `run_jobs`; worker `_claim()` như thường lệ.
- Chống bắn trùng do **database phân xử**: UNIQUE `(schedule_id, fire_time)` + `INSERT ... ON CONFLICT DO NOTHING`. Không dùng kiểu "SELECT kiểm tra rồi mới INSERT".
- Thời gian lưu **UTC** trong DB; `timezone` là trường riêng, tên tz database (mặc định `Asia/Ho_Chi_Minh`). Không dùng `datetime.utcnow()`; dùng `datetime.now(timezone.utc)` và `zoneinfo`.
- Tick loop chỉ làm việc DB (truy vấn có index). **Mọi thao tác quét file chạy qua `asyncio.to_thread`** — hash hàng trăm file trong event loop sẽ treo cả API (cùng lý do `slack_bot`/`telegram_bot` phải ở thread riêng, xem `main.py:189-195`).
- Quét trước, tạo job sau: tài liệu không đổi → **không** tạo `run_jobs`, không thông báo. Chi phí thật của tính năng này là token và thời gian máy của pipeline.
- `concurrency_policy=forbid` mặc định: project còn job `queued`/`running` thì bỏ qua nhịp này, ghi log lý do. Worker chạy tuần tự tuyệt đối (`run_jobs.py:90-92`).
- Catch-up **có chặn trên**: tối đa **1** lần bù, và chỉ khi mốc lỡ nằm trong `SCHEDULER_CATCHUP_WINDOW_H` (mặc định 24h). Máy tắt 3 ngày → 1 job, không phải 3.
- Mọi tick ghi log **quyết định** (bắn / bỏ vì forbid / bù / bỏ ngoài cửa sổ / không đổi). Đây là loại code chạy lúc không ai nhìn.
- `SCHEDULER_DRY_RUN=1` → tick chạy đủ, log đủ, nhưng **không** `INSERT` và **không** thông báo. Mặc định BẬT dry-run ở lần triển khai đầu.
- Job do lịch tạo phải truy vết được: `run_jobs.source='schedule'` + `schedule_id` + `fire_time`.
- Không có lịch nào `enabled` → hành vi hệ thống y hệt hiện tại, không lỗi, không log rác.

**Ask First:**
- ~~Tài liệu nằm ở đâu~~ — **ĐÃ CHỐT**: `docker-compose.yml:39` ghi rõ *"`clients/<slug>/` chỉ giữ tài liệu; project mới mặc định lấy thư mục code là `<CODE_ROOT>/<slug>`"*. API container thấy được qua `/clients`. Nếu SAU NÀY cần quét cả thư mục code (`CODE_ROOT`, chỉ host thấy) thì phải đổi kiến trúc: việc quét thành job do worker thực thi, API chỉ giữ vai đồng hồ.
- Gắn tab/card lịch vào `Projects.tsx` — file đang có thay đổi chưa commit của người dùng (feature MCP). Spec này tạo component riêng và **không** tự sửa `Projects.tsx`.
- ~~Alembic hay không~~ — **ĐÃ CHỐT**: repo dùng `Base.metadata.create_all()` + `_ensure_column()`/`_COLUMN_MIGRATIONS` trong `main.py`. Đã bám đúng cách đó, cộng `_ensure_scheduler_unique_index()` cho ràng buộc UNIQUE (create_all không thêm ràng buộc vào bảng đã tồn tại).
- Mở rộng `job_kind` ngoài `scan_docs` (chạy test định kỳ, dọn log, báo cáo tuần) — ngoài phạm vi này.

**Never:**
- Không dùng APScheduler (dựng job store + executor thứ hai chồng lên `run_jobs`), không thêm Redis, không thêm broker, không thêm container.
- Không để scheduler tự gọi `claude`/`opencode`/`git` hay tự sửa file tài liệu. Mọi tác dụng phụ đi qua `worker.py`, nơi đã có timeout và log.
- Không dùng Windows Task Scheduler làm scheduler chính (không cấu hình per-project, không truy vết trong DB). Chỉ dùng để khởi động Docker Desktop + worker lúc boot.
- Không sửa `worker.py`, `ActiveTasks.tsx`, `RunConsole.tsx`, `Projects.tsx` (đang có thay đổi chưa commit).
- Không chạy nhiều uvicorn worker cho API khi chưa có leader election — mỗi worker sẽ tự khởi tạo scheduler riêng.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Đến giờ, tài liệu đổi | `0 6 * * *` TZ `Asia/Ho_Chi_Minh`, sha256 khác snapshot | Cập nhật `doc_snapshots`; `INSERT run_jobs(source='schedule', schedule_id, fire_time)`; notify qua `chat_router`; `last_status='fired'` | Lỗi quét → `last_status='error'`, `next_run_at` vẫn tiến, có log |
| Đến giờ, tài liệu không đổi | sha256 trùng toàn bộ | **Không** tạo job, **không** notify; `last_status='no_change'`; `next_run_at` tiến | N/A |
| Tick chạy 2 lần cùng `fire_time` | API `--reload` restart giữa chừng | UNIQUE chặn, `ON CONFLICT DO NOTHING` → đúng **1** dòng `run_jobs` | Không coi là lỗi, log `duplicate suppressed` |
| Máy tắt 3 ngày, `catchup_once` | bật lại, 3 mốc đã lỡ | Tạo **1** job cho mốc **gần nhất**; `next_run_at` nhảy tới mốc tương lai kế tiếp | N/A |
| Máy tắt 30 ngày, `catchup_once` | mốc lỡ ngoài cửa sổ 24h | **Không** tạo job; log `missed, outside window`; `next_run_at` nhảy tới tương lai | N/A |
| `misfire_policy=skip` | có mốc lỡ | Không tạo job; chỉ dời `next_run_at`; log `skipped` | N/A |
| Project còn job chạy | `concurrency_policy=forbid`, `run_jobs` có `queued`/`running` cùng `project_id` | Bỏ qua nhịp; `next_run_at` vẫn tiến; log `skipped: forbid` | N/A |
| Nhiều lịch cùng 6h | N project cùng `0 6 * * *` | Áp `jitter_s` (mặc định 0, cấu hình được) khi tính `fire_time` thực thi | Worker tuần tự tự xếp hàng |
| Cron sai cú pháp | `POST/PATCH` với `cron_expression` rác | HTTP 422, thông báo rõ; **không** lưu | `croniter` ném → bắt tại router |
| Timezone sai | `timezone='Asia/Saigon_X'` | HTTP 422; `ZoneInfoNotFoundError` bắt tại router | Không lưu |
| Xem trước lịch | `GET /api/schedules/preview?cron=&tz=` | Trả 5 mốc chạy kế tiếp (ISO, có offset) để người dùng tự kiểm chứng | 422 nếu cron/tz sai |
| `enabled=false` | lịch tắt | Tick bỏ qua hoàn toàn, không tính `next_run_at` | N/A |
| Dry-run | `SCHEDULER_DRY_RUN=1` | Log đầy đủ quyết định, **không** INSERT, **không** notify; `next_run_at` **vẫn** tiến | N/A |
| Thư mục `clients/{slug}` không tồn tại | project mới, chưa có tài liệu | `last_status='error'` + log rõ; không tạo job | Không làm chết tick loop |
| Xoá project | `project_id` bị xoá | Lịch xoá theo (`ondelete='CASCADE'`) | N/A |
| Worker offline | không ai claim | Job nằm `queued`; `forbid` chặn nhịp sau → không dồn ứ | N/A |

</frozen-after-approval>

## Code Map

- `dashboard/api/models.py` -- thêm `Schedule`, `DocSnapshot`; `RunJob` thêm `source` / `schedule_id` / `fire_time` + `UniqueConstraint('schedule_id','fire_time')`
- `dashboard/api/schemas.py` -- `ScheduleIn` / `ScheduleOut` / `SchedulePreviewOut` (mẫu: các schema MCP vừa thêm)
- `dashboard/api/routers/schedules.py` -- **mới**; CRUD theo `project_id`, `POST /{id}/run-now`, `GET /preview`
- `dashboard/api/scheduler.py` -- **mới**; `tick()` (đồng bộ, cả DB lẫn quét — người gọi đẩy sang `to_thread`), `next_fire` / `prev_fire` / `preview` / `validate`, `backfill_next_run_at()`
- `dashboard/api/doc_scan.py` -- **mới**; `snapshot_dir(path)` → `{rel_path: sha256}`, `diff(old, new)` → added/removed/changed
- `dashboard/api/main.py` -- `include_router(schedules...)` prefix `/api/schedules`; `_schedule_tick_loop()` cạnh `_workflow_run_poll_loop` trong `@app.on_event("startup")` (`main.py:185`)
- `dashboard/api/chat_router.py` -- dùng lại `send_to()` (`:298`) + `ChatBot` khớp `client_folder`, KHÔNG sửa file này. (`notify_run()` không dùng được: nó chỉ trả lời cuộc chat đã kích hoạt một WorkflowRun, lịch không có chat nguồn.)
- `dashboard/api/requirements.txt` -- thêm `croniter==6.2.4` (ghim); `zoneinfo` là stdlib Python 3.12
- `dashboard/src/hooks/useSchedules.ts` -- **mới**, mẫu: `useMcp.ts`
- `dashboard/src/components/ProjectSchedules.tsx` -- **mới**, mẫu: `ProjectMcp.tsx`
- `dashboard/src/App.css` -- append `.sched-*` cuối file
- `tests/test_scheduler.py` -- **mới**

## Tasks & Acceptance

**Execution:**
- [x] `dashboard/api/models.py` -- `Schedule` (`project_id` FK CASCADE, `name`, `cron_expression`, `timezone`, `enabled`, `job_kind='scan_docs'`, `misfire_policy`, `concurrency_policy`, `on_change`, `jitter_s`, `next_run_at` **index**, `last_run_at`, `last_status`, `version`, `created_at`, `updated_at`); `DocSnapshot` (`project_id`, `rel_path`, `sha256`, `scanned_at`, UNIQUE `(project_id, rel_path)`); `RunJob` +3 cột + UNIQUE `(schedule_id, fire_time)` -- nguồn sự thật bền vững
- [x] `dashboard/api/doc_scan.py` -- `snapshot_dir` / `diff`, bỏ qua `.git`, file nhị phân lớn, giới hạn số file; thuần đồng bộ, không import DB -- dễ test
- [x] `dashboard/api/scheduler.py` -- `next_fire()` (croniter + ZoneInfo, trả UTC aware), `tick()` (chọn lịch đến hạn `FOR UPDATE SKIP LOCKED`, áp misfire/concurrency, gọi scan qua `to_thread`, `INSERT ... ON CONFLICT DO NOTHING`, notify, tiến `next_run_at`), tôn trọng `SCHEDULER_DRY_RUN` -- lõi tính năng
- [x] `dashboard/api/schemas.py` + `routers/schedules.py` -- CRUD + `preview` + `run-now`; validate cron/tz tại router trả 422 -- đường vào
- [x] `dashboard/api/main.py` -- đăng ký router; `_schedule_tick_loop()` (`SCHEDULER_TICK_S`, mặc định 60) trong startup, bọc try/except như `_workflow_run_poll_loop` -- đồng hồ chạy
- [x] `dashboard/api/requirements.txt` -- `croniter==6.2.4`; **cần `docker compose build api`** (pip install ở bước build, không phải mount) -- dependency
- [x] `tests/test_scheduler.py` -- 6 ca ở mục Verification, dùng `freezegun` (hoặc tiêm clock), **không** `sleep` -- ma trận có test
- [x] `dashboard/src/hooks/useSchedules.ts` + `components/ProjectSchedules.tsx` + `App.css` -- danh sách lịch của project, form cron + timezone, **hiện 5 mốc chạy kế tiếp** khi gõ, toggle enabled, nút "Chạy ngay", hiện `last_run_at`/`last_status` -- người dùng tự kiểm chứng trước khi lưu

**Acceptance Criteria:**
- Given lịch `0 6 * * *` TZ `Asia/Ho_Chi_Minh`, when gọi `GET /api/schedules/preview`, then 5 mốc trả về đều là 06:00 giờ VN, cách nhau đúng 1 ngày.
- Given `SCHEDULER_DRY_RUN=1` và một lịch đến hạn, when tick chạy, then log có dòng quyết định nhưng `run_jobs` **không** thêm dòng nào.
- Given tick chạy hai lần liên tiếp với cùng `fire_time`, when kiểm tra DB, then `run_jobs` có **đúng 1** dòng cho `(schedule_id, fire_time)` đó.
- Given tài liệu `clients/{slug}/` không đổi so với `doc_snapshots`, when tick chạy, then không tạo job, `last_status='no_change'`.
- Given project còn job `running` và `concurrency_policy='forbid'`, when tick chạy, then không tạo job, log `skipped: forbid`, `next_run_at` vẫn tiến.
- Given `python -m pytest tests/test_scheduler.py`, when chạy, then pass toàn bộ.
- Given không có lịch nào `enabled`, when API chạy 10 phút, then không có log scheduler nào ngoài dòng khởi động.

## Design Notes

Tick loop bám đúng khuôn `_workflow_run_poll_loop` (`main.py:173-181`) — `while True` / `await asyncio.sleep` / `try-except` in lỗi, không để exception giết task.

```python
# Chọn lịch đến hạn — cùng pattern với run_jobs.py:96
q = (db.query(Schedule)
       .filter(Schedule.enabled.is_(True), Schedule.next_run_at <= now_utc)
       .order_by(Schedule.next_run_at))
try:
    rows = q.with_for_update(skip_locked=True).all()
except Exception:
    rows = q.all()          # sqlite/dev fallback, y hệt run_jobs.py

# Chèn job — DB phân xử, KHÔNG "select kiểm tra rồi insert"
stmt = pg_insert(RunJob).values(
    client_folder=proj.slug, project_id=proj.id,
    source="schedule", schedule_id=s.id, fire_time=fire,
    status="queued",
).on_conflict_do_nothing(index_elements=["schedule_id", "fire_time"])

# Quét file KHÔNG chạy trong event loop
new_snap = await asyncio.to_thread(snapshot_dir, docs_path)
```

`next_run_at` luôn tính từ **mốc lỡ gần nhất**, không phải từ `now()` — nếu không, một lần khởi động lại đúng lúc sẽ làm trôi mất nhịp. `croniter` khởi tạo bằng datetime **có timezone** (`ZoneInfo`), kết quả đổi về UTC trước khi ghi DB.

Bẫy đã biết: `timedelta(days=1)` cộng đúng 24 giờ — không giữ nguyên giờ đồng hồ khi đổi DST. Việt Nam không có DST nên rủi ro thấp, nhưng `next_fire()` vẫn phải đi qua `croniter` chứ không tự cộng ngày.

`on_change` nhận `notify` / `run_pipeline` / `both`, mặc định **`notify`** — lần đầu triển khai chỉ báo, không tự chạy pipeline. Đây là cách rẻ nhất để hoãn quyết định "phát hiện thay đổi rồi làm gì" mà không chặn việc xây.

## Verification

**Commands:**
- `python -m py_compile dashboard/api/models.py dashboard/api/scheduler.py dashboard/api/doc_scan.py dashboard/api/routers/schedules.py dashboard/api/main.py` -- expected: không lỗi
- `python -m pytest tests/test_scheduler.py -q` -- expected: all passed
- `cd dashboard && npx tsc --noEmit` -- expected: 0 lỗi
- `docker compose -f dashboard/docker-compose.yml build api && docker compose -f dashboard/docker-compose.yml up -d` -- expected: api healthy, log có `[scheduler] tick loop started (dry-run=1)`

**Bộ test tối thiểu (tests/test_scheduler.py):**
1. `next_fire('0 6 * * *', 'Asia/Ho_Chi_Minh', t)` → đúng 06:00 giờ VN, trả UTC aware
2. Máy tắt 3 ngày + `catchup_once` → tạo **1** job, `next_run_at` ở tương lai
3. `misfire_policy='skip'` → 0 job, `next_run_at` vẫn tiến
4. Tick 2 lần cùng `fire_time` → UNIQUE chặn, 1 dòng `run_jobs`
5. `concurrency_policy='forbid'` + job `running` → 0 job, log lý do
6. `snapshot_dir` không đổi → `diff` rỗng → 0 job, `last_status='no_change'`

**Manual checks:**
- Tạo lịch qua UI với cron `*/2 * * * *`, xem 5 mốc preview có đúng không; bật `SCHEDULER_DRY_RUN=1`, theo dõi log 5 phút; sửa một file trong `clients/{slug}/`, tắt dry-run, xác nhận job xuất hiện trong `run_jobs` với `source='schedule'`.
- Task Windows Task Scheduler ở mức logon: khởi động Docker Desktop + `python worker.py` — để catch-up có cơ hội chạy sau khi máy bật lại.

## Rollout

1. Dry-run ít nhất **một chu kỳ ngày đêm**, soát log quyết định.
2. Tắt dry-run cho **đúng một** project, `on_change='notify'`.
3. Xác nhận thông báo đúng và không nhiễu → mở rộng các project còn lại.
4. Chỉ sau khi ổn định mới cân nhắc `on_change='run_pipeline'`.

---

## Kết quả kiểm chứng (2026-09-23)

**Đã chạy, đã pass:**

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/test_scheduler.py -q` | **16 passed**, 0 cảnh báo |
| `cd dashboard && npx tsc --noEmit` | **0 lỗi** |
| `python -c "import main"` (sqlite tạm) | app nạp OK, 5 route `/api/schedules*` đăng ký đủ |
| Smoke test end-to-end qua `TestClient` | xem bảng dưới |

**Smoke test end-to-end:**

| Bước | Kết quả thực tế |
|---|---|
| `GET /preview` cron `0 6 * * *` TZ VN | `2026-09-24T06:00:00+07:00`, `2026-09-25T06:00:00+07:00` ✅ |
| `GET /preview` cron rác | HTTP **422** ✅ |
| `GET /preview` timezone rác | HTTP **422** ✅ |
| `POST /api/schedules` | HTTP **201**, `next_run_at=2026-09-23T23:00:00` (UTC) = 06:00 VN ✅ |
| tick #1 (lần quét đầu) | `last_status='no_change'`, chỉ lưu ảnh chụp ✅ |
| tick #2 (sửa `prd.md`) | `last_status='fired'`, tạo **1** `run_job` `queued` ✅ |
| tick #3 (chạy lại ngay) | `last_status='skipped'` — `forbid` chặn vì job trước còn `queued` ✅ |
| Tổng số job sau 3 tick | **1** ✅ |
| `DELETE /api/schedules/{id}` | HTTP **204** ✅ |

**Lệch so với spec ban đầu (có chủ đích):**

1. **Cả `tick()` chạy trong `asyncio.to_thread`**, không chỉ riêng lời gọi `snapshot_dir`. Ràng buộc "không chặn event loop" được giữ chặt hơn, và code một đường thay vì async/sync xen kẽ.
2. **Thông báo dùng `chat_router.send_to()`** với `ChatBot` khớp `client_folder` (hẹp nhất thắng), KHÔNG dùng `notify_run()`. Lý do: `notify_run` đọc `run.chat_bot_id`/`run.chat_id` của một `WorkflowRun` để **trả lời đúng cuộc chat đã kích hoạt** — lịch không có chat nguồn nên hàm đó sẽ lặng lẽ return. Tài liệu nghiên cứu đã được đính chính tương ứng.
3. **UNIQUE bằng `CREATE UNIQUE INDEX IF NOT EXISTS`** thay vì table constraint, vì `create_all()` không thêm ràng buộc vào bảng `run_jobs` đã tồn tại. Cả PostgreSQL lẫn SQLite đều hiểu, và NULL không bị coi là trùng nên job bấm tay không ảnh hưởng.
4. **`jitter_s` mới chỉ là cột + ô cấu hình**, chưa áp vào lúc tính `fire_time`. Chưa cần: `concurrency_policy=forbid` đã chặn dồn ứ, và số project hiện tại chưa biết. Ghi lại để không quên.

**Còn phải làm bằng tay (cố ý không tự động):**

- Gắn `<ProjectSchedules projectId={...} />` vào `Projects.tsx` — file đang có thay đổi chưa commit của feature MCP, spec cấm đụng.
- `docker compose -f dashboard/docker-compose.yml build api` — `croniter==6.2.4` cài ở bước build, `--reload` không đủ.
- Tạo task Windows Task Scheduler mức logon để khởi động Docker Desktop + `python worker.py`.
- Giữ `SCHEDULER_DRY_RUN=1` (mặc định) ít nhất một chu kỳ ngày đêm trước khi bật thật.

---

## Phát hiện khi chạy thật trên Docker + Postgres (2026-09-23)

Build lại image và chạy trên dữ liệu thật đã lộ ra **4 lỗi mà test không bắt được** — đều thuộc loại chỉ hiện ra khi chạm dữ liệu thật:

### 1. 🔴 Vòng lặp tự nuôi qua `output/` (nghiêm trọng nhất)

Lần tick đầu trên dự án `booking` báo **"thêm 28 file"**: `composer.json`, `docker-compose.yml`, `README.md`… nằm trong `clients/booking/.../output/backend/be1/` — tức **code Laravel do chính pipeline sinh ra**.

Hậu quả nếu không sửa: pipeline chạy → ghi code vào `output/` → lần quét sau thấy "tài liệu đổi" → chạy pipeline tiếp → **lặp vô tận, đốt token liên tục**.

**Sửa:** `output` và `vendor` vào `SKIP_DIRS` của `doc_scan.py` + test hồi quy.

### 2. 🔴 Vòng lặp tự nuôi qua `_tasks/`

Cùng lớp lỗi. `routers/workflows.py:11` ghi **một file `.md` vào `clients/<slug>/_tasks/` cho MỖI node của MỖI lần chạy workflow** (nội dung có `status`, `run_id`, `node_id`). Dự án `udom` có 11 file như vậy, tất cả bị tính là "tài liệu".

**Sửa:** `_tasks` vào `SKIP_DIRS` + test hồi quy.

### 3. 🟠 File cấu hình chứa credential bị coi là tài liệu

Sau khi loại `output/`, file duy nhất còn lại của `booking` là **`settings.local.toml`** — nơi giữ credential MCP. Đổi một cái token sẽ kích hoạt "tài liệu thay đổi".

**Sửa:** `SKIP_FILES = {settings.toml, settings.local.toml, mcp.json, package-lock.json, composer.lock, yarn.lock}` + test hồi quy.

### 4. 🟠 API projects dùng slug, không dùng id số

`/api/projects` là **filesystem-backed** (`routers/projects.py:373` liệt kê `clients/<slug>/` có `settings.toml`) và trả `id` = **tên thư mục**. Nhưng `run_jobs.project_id` / `project_tasks.project_id` lại trỏ `projects.id` kiểu **số**. Component nhận `projectId: number` sẽ không bao giờ lấy được id đó từ trang Projects.

**Sửa:** router nhận **cả** `project_id` lẫn `slug` (`_resolve_project`), hook và component chuyển sang `slug` — đúng khuôn `ProjectMcp({ slug })`.

### 5. 🟡 Log bị đệm, không hiện trong `docker compose logs`

Container không đặt `PYTHONUNBUFFERED`, `print()` trong `_schedule_tick_loop` bị đệm nên banner scheduler không bao giờ xuất hiện. **Cả kế hoạch chạy dry-run dựa vào việc đọc được log này.**

**Sửa:** `flush=True` ở mọi `print` của scheduler trong `main.py` (`scheduler._log` vốn đã có).

---

## Kiểm chứng trên môi trường thật

| Hạng mục | Kết quả |
|---|---|
| `docker compose build api` | thành công, `croniter-6.2.4` đã cài |
| Khởi động API | `[scheduler] tick loop started (tick=60s, dry_run=1, catchup=24h)` |
| Migration trên Postgres | `run_jobs` có `source`/`schedule_id`/`fire_time`; index `uq_run_jobs_schedule_fire` UNIQUE (schedule_id, fire_time) |
| Bảng mới | `schedules`, `doc_snapshots` đã tạo |
| `POST /api/schedules?slug=booking` | 201, quy đổi đúng sang `project_id=49` |
| `POST /api/schedules?slug=udom` | 201, `project_id=52` |
| Tick thật, tài liệu không đổi | `#3 -> dry_run: … — không có thay đổi` |
| Tick thật, sửa `prd.md` | `#3 -> dry_run: … — sửa 1: prd.md` |
| `pytest tests/` | **115 passed** (18 test scheduler, 97 test cũ vẫn xanh) |
| `npx tsc --noEmit` | 0 lỗi |
| Dọn dẹp sau kiểm thử | 3 lịch test đã xoá, `doc_snapshots` rỗng, `prd.md` hoàn nguyên, **0 job do lịch tạo** |

## Ghi chú về dữ liệu hiện tại

Sau khi loại các thư mục máy sinh, số **tài liệu người viết** trong `clients/` hiện rất ít:

| Dự án | Số file tài liệu |
|---|---|
| `react-js-movie-web-application` | 1 (`prd.md`) |
| `sample_project` | 1 (`prd.md`) |
| `udom`, `booking`, `ieltskey` | **0** |

Không phải lỗi của tính năng — nhưng nghĩa là **lịch quét hiện chưa có nhiều thứ để canh**. Nếu tài liệu thật của bạn nằm chỗ khác (thư mục code `CODE_ROOT`, Google Drive, Confluence…), đó là cuộc trao đổi tiếp theo: xem mục "Ask First" về ranh giới container/host.
