---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Scheduled task (cron-like) theo từng dự án cho ai_team_clean — quét thay đổi tài liệu định kỳ'
research_goals: 'Chọn phương án scheduler & vị trí đặt scheduler; xử lý missed runs khi máy tắt; timezone; chống trùng/chồng lịch với worker tuần tự; cách phát hiện thay đổi tài liệu'
user_name: 'mor_dong.bd'
date: '2026-09-22'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-09-22
**Author:** mor_dong.bd
**Research Type:** technical

---

## Research Overview

Nghiên cứu này trả lời câu hỏi: làm thế nào để thêm scheduled task kiểu cron cho từng dự án trong `ai_team_clean` — ví dụ 6h sáng hàng ngày quét tài liệu xem có thay đổi gì không. Phương pháp gồm hai tuyến song song: khảo sát trực tiếp mã nguồn dự án (models, routers, `worker.py`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`) và tra cứu 15 truy vấn web trên tài liệu chính thức, bài phân tích thiết kế hệ thống, cùng issue/PR thực chiến. Mọi khuyến nghị đều phải đồng thời có nguồn ngoài xác nhận và tương thích với ràng buộc đã kiểm chứng trong mã nguồn.

Kết luận trung tâm: `ai_team_clean` không thiếu một hệ thống scheduler, nó thiếu đúng một mảnh ghép. Ngành phân rã scheduler thành bốn thành phần — schedule store, tick coordinator, execution queue, executor — và dự án đã có hai thành phần cuối đang chạy ổn định (`run_jobs` + `worker.py`). Vì vậy phản xạ thông thường "cần lịch thì cài APScheduler" là cái bẫy kiến trúc lớn nhất ở đây: nó dựng song song một job store và một executor thứ hai chồng lên thứ đã có. Khuyến nghị là bổ sung bảng `schedules` trong Postgres cùng một tick loop trong API container, dùng `croniter` để tính `next_run_at`, và khoá chống bắn trùng bằng UNIQUE `(schedule_id, fire_time)`.

Ba ràng buộc từ chính mã nguồn định hình toàn bộ kết luận: `worker.py` tuyên bố thành văn rằng chỉ dùng thư viện chuẩn; API đã là nhà của các tiến trình nền (`_workflow_run_poll_loop` cùng hai bot thread); và hệ thống bị chia đôi giữa Docker container với host Windows, tạo ra ranh giới khả kiến quyết định thành phần nào quét được tài liệu nào. Xem **Executive Summary** trong phần Research Synthesis phía dưới để có bản tóm tắt đầy đủ, bảng quyết định nhanh, lộ trình 6 giai đoạn và danh sách 8 rủi ro kèm biện pháp giảm thiểu.

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** Scheduled task (cron-like) theo từng dự án cho ai_team_clean — quét thay đổi tài liệu định kỳ

**Research Goals:**
1. Chọn engine scheduler (APScheduler vs tick-loop tự viết vs Windows Task Scheduler vs cron parser)
2. Chọn nơi đặt scheduler (tiến trình worker.py vs backend FastAPI)
3. Xử lý missed runs khi máy Windows tắt lúc giờ hẹn
4. Timezone — lưu & diễn giải giờ chạy
5. Chống trùng/chồng lịch khi nhiều project cùng giờ, worker chạy tuần tự
6. Cơ chế phát hiện thay đổi tài liệu (git diff vs snapshot mtime/hash)

**Ràng buộc thực tế đã khảo sát trong codebase:**
- Chưa có scheduler nào trong repo (grep `cron|schedule|apscheduler` → 0 kết quả)
- Đã có bảng `run_jobs` (dashboard/api/models.py) làm hàng đợi trigger pipeline
- `worker.py` chạy trên host, vòng `while True` poll `run_jobs`, thực thi TUẦN TỰ qua `python main.py` (worker.py:1495)
- Backend FastAPI có 17 routers theo pattern rõ ràng → dễ thêm `schedules.py`
- Môi trường: Windows 11, worker chạy trên host (máy có thể tắt lúc giờ hẹn)

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-09-22

---

## Technology Stack Analysis

> **Ràng buộc nền tảng phát hiện thêm khi khảo sát (quan trọng, ảnh hưởng mọi lựa chọn bên dưới):**
> - `dashboard/docker-compose.yml`: **API + Postgres 16 + web chạy trong Docker**, `api` dùng `uvicorn --reload`, `restart: unless-stopped`
> - `worker.py` chạy **trên host Windows**, KHÔNG trong container
> - `clients/` được mount vào API container tại `/clients` (read-write); `CODE_ROOT` trỏ `C:/www` chỉ tồn tại trên host
> - DB thật là **PostgreSQL 16**, không phải SQLite (`dashboard/api/database.py:6-9`)
> - `run_jobs.py` đã dùng `with_for_update(skip_locked=True)` + guard "chỉ 1 job `running` tại một thời điểm"

### Programming Languages

Toàn bộ bài toán nằm gọn trong **Python** (backend FastAPI + `worker.py`) và **TypeScript/React** (dashboard UI) — không có lý do kỹ thuật nào để đưa ngôn ngữ thứ ba vào chỉ để chạy lịch.

- _Popular Languages:_ Python thống trị mảng in-process scheduling nhờ hệ sinh thái APScheduler/Celery; cron cấp OS (crontab / Windows Task Scheduler) là lựa chọn ngôn ngữ-trung tính.
- _Emerging Languages:_ Không liên quan — đây là hạ tầng nội bộ, không phải dịp chọn stack mới.
- _Language Evolution:_ APScheduler `CronTrigger` hỗ trợ 8 trường (có cả giây và tuần-trong-năm) và xử lý timezone thật, mạnh hơn crontab nhưng **không tương thích cú pháp crontab**.
- _Performance Characteristics:_ Khối lượng tính toán của scheduler gần như bằng 0; nút cổ chai thật sự là `python main.py` do worker chạy tuần tự.

_Source: [crontap.com/guides/python-cron-jobs](https://crontap.com/guides/python-cron-jobs)_

### Development Frameworks and Libraries

Bốn ứng viên khả dĩ, xếp theo mức độ "nặng":

| Ứng viên | Bản chất | Persistence | Phù hợp với ai_team_clean |
|---|---|---|---|
| **APScheduler** | Scheduler in-process đầy đủ | Có (`SQLAlchemyJobStore`) | Mạnh, nhưng chồng lấn hạ tầng `run_jobs` đã có |
| **croniter** | Chỉ parse cron rồi tính `next_run_at` | Không (tự lo) | Ghép rất gọn vào vòng poll sẵn có của worker |
| **schedule** | API kiểu tiếng Anh, siêu nhẹ | **Không có** | Loại — không nhớ lịch qua restart |
| **Windows Task Scheduler** | Bộ lịch cấp OS | Có (OS lo) | Ứng viên duy nhất chạy được khi máy đang ngủ |

- _Major Frameworks:_ APScheduler là "câu trả lời mặc định cho cron-style scheduling bên trong tiến trình Python", hỗ trợ one-off / interval / cron, job lưu bền được.
- _Micro-frameworks:_ Thư viện `schedule` **không có cơ chế nhớ lịch qua restart, không chạy bù job lỡ** — không đáp ứng yêu cầu "máy tắt lúc 6h" của bạn.
- _Evolution Trends:_ APScheduler 4.0 **đại tu toàn bộ job store**, dữ liệu job cũ **không tương thích ngược**; `coalesce` chuyển sang enum `CoalescePolicy`. Rủi ro migration nếu chọn 4.0 sớm.
- _Ecosystem Maturity:_ APScheduler trưởng thành, tài liệu tốt; `croniter` nhỏ, ổn định, chỉ làm đúng một việc.

_Độ tin cậy: CAO (tài liệu chính thức + PyPI/GitHub)._
_Source: [apscheduler.readthedocs.io/en/3.x/userguide.html](https://apscheduler.readthedocs.io/en/3.x/userguide.html), [apscheduler.readthedocs.io/en/master/migration.html](https://apscheduler.readthedocs.io/en/master/migration.html), [aimultiple.com/python-job-scheduling](https://aimultiple.com/python-job-scheduling), [github.com/agronholm/apscheduler](https://github.com/agronholm/apscheduler)_

### Database and Storage Technologies

- _Relational Databases:_ **PostgreSQL 16** (container `db`, volume `pgdata`) là nơi lưu lịch hợp lý nhất — cùng chỗ với `run_jobs`, đảm bảo lịch và hàng đợi nhìn thấy nhau trong cùng một transaction.
- _NoSQL / In-Memory:_ Redis thường được khuyến nghị làm distributed job store kèm lock cho scheduler đa tiến trình — **nhưng dự án chưa có Redis**; thêm vào chỉ để khoá lịch là chi phí không tương xứng.
- _Điểm mạnh sẵn có:_ Postgres cho phép `SELECT ... FOR UPDATE SKIP LOCKED` — pattern mà `dashboard/api/routers/run_jobs.py` **đã dùng rồi**. Cùng cơ chế đó đủ để bảng `schedules` chống double-fire mà không cần Redis.
- _Data Warehousing:_ Không áp dụng.

_Độ tin cậy: CAO (đọc trực tiếp từ codebase)._
_Source: [github.com/fastapi/fastapi/issues/12010](https://github.com/fastapi/fastapi/issues/12010), [sentry.io/answers/schedule-tasks-with-fastapi](https://sentry.io/answers/schedule-tasks-with-fastapi/)_

### Development Tools and Platforms

- _Version Control:_ Repo là git, nên `git diff --name-only --diff-filter=ACMR` là cách phát hiện thay đổi tài liệu rẻ và chính xác **nếu** thư mục tài liệu nằm trong git.
- _Snapshot tooling:_ Nếu tài liệu **không** được version-control, pattern chuẩn là snapshot thư mục: dict `{path: hash|mtime}` rồi so hai snapshot (`hashlib.sha256`, `os.stat`). Các thư viện `watchdog` (`DirectorySnapshotDiff`), `filespy`, `DirTracker` đều hiện thực đúng ý tưởng này.
- _Cảnh báo:_ `watchdog` thiên về theo dõi **thời gian thực** (observer chạy liên tục), trong khi bạn cần **quét theo lịch** — chỉ nên mượn lớp `DirectorySnapshot`, không cần chạy observer.
- _Testing:_ Repo đã có `tests/` (ví dụ `tests/test_worker_mcp.py`) — có sẵn chỗ đặt test cho logic tính `next_run_at`.

_Độ tin cậy: TRUNG BÌNH-CAO (nguồn how-to phổ thông + tài liệu thư viện)._
_Source: [geeksforgeeks.org/python/how-to-detect-file-changes-using-python](https://www.geeksforgeeks.org/python/how-to-detect-file-changes-using-python/), [pypi.org/project/filespy](https://pypi.org/project/filespy), [github.com/PythonHubStudio/DirTracker](https://github.com/PythonHubStudio/DirTracker), [datacamp.com/tutorial/git-diff-guide](https://www.datacamp.com/tutorial/git-diff-guide)_

### Deployment Topology (thay cho "Cloud Infrastructure")

Dự án **không chạy trên cloud** — đây là triển khai host-local, nên phần này quy về câu hỏi "tiến trình nào sống lâu nhất":

| Tiến trình | Nơi chạy | Sống qua reboot? | Thấy `clients/`? | Thấy `CODE_ROOT` trên host? |
|---|---|---|---|---|
| `api` (uvicorn) | Docker container | Có (`restart: unless-stopped`, nếu Docker Desktop bật) | Có (`/clients`) | **Không** |
| `db` (Postgres 16) | Docker container | Có | — | — |
| `worker.py` | **Host Windows** | Chỉ khi người dùng/OS khởi động lại | Có | **Có** |

- _Container Technologies:_ Docker Compose v3.9, 3 service. API mount `./api:/app` kèm `--reload`, nên **mỗi lần sửa code API là tiến trình nạp lại**; scheduler đặt trong API sẽ restart theo và có nguy cơ double-fire khi reloader sinh tiến trình con.
- _Vấn đề multi-worker:_ Khi FastAPI chạy nhiều worker, **mỗi worker tự khởi tạo scheduler riêng, khiến job bắn trùng nhiều lần**. Hiện `api` chạy đơn worker nên chưa vỡ, nhưng đây là bẫy chờ sẵn nếu sau này scale.
- _Serverless / CDN:_ Không áp dụng.

_Độ tin cậy: CAO (docker-compose.yml + Dockerfile đọc trực tiếp)._
_Source: [github.com/fastapi/fastapi/discussions/10603](https://github.com/fastapi/fastapi/discussions/10603), [github.com/fastapi/fastapi/issues/12010](https://github.com/fastapi/fastapi/issues/12010)_

### Technology Adoption Trends

- _Migration Patterns:_ Khuyến nghị phổ biến hiện nay: "chọn crontab cho một máy đơn, APScheduler cho đồng hồ in-process, platform cron cho serverless, external HTTP cron khi muốn retry và cảnh báo mà không cần tiến trình chạy liên tục."
- _Emerging Technologies:_ APScheduler 4.0 là hướng tiến hoá nhưng **phá vỡ tương thích job store**; nhiều dự án còn ở 3.x.
- _Legacy Technology:_ Job store kiểu `Shelve` đã bị khuyến nghị thay bằng `SQLAlchemyJobStore`.
- _Ràng buộc OS đặc thù (phát hiện then chốt):_ Windows Task Scheduler có **"Run task as soon as possible after a scheduled start is missed"** (tab Settings) để chạy bù, và **"Wake the computer to run this task"** (tab Conditions) để đánh thức máy đang ngủ — nhưng wake timer đòi bật "Allow wake timers" ở cả AC lẫn DC, và **không cứu được trường hợp máy tắt hẳn**. Nhiều báo cáo cộng đồng cho thấy task ban đêm bị bỏ lỡ do thiết lập power.

_Độ tin cậy: CAO cho tài liệu Microsoft; TRUNG BÌNH cho mức độ phổ biến của lỗi wake (nguồn là Q&A cộng đồng)._
_Source: [crontap.com/guides/python-cron-jobs](https://crontap.com/guides/python-cron-jobs), [learn.microsoft.com — Task Properties](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2008-R2-and-2008/cc775003), [learn.microsoft.com — missed night tasks](https://learn.microsoft.com/en-us/answers/questions/362393/task-scheduler-misses-all-tasks-scheduled-to-run-a), [learn.microsoft.com — Win11 wake](https://learn.microsoft.com/en-us/answers/questions/651690/windows-11-does-not-wake-computer-to-run-scheduled)_

### Cross-Technology Analysis

Ba sợi dây nối các phát hiện lại với nhau:

1. **Bạn không thiếu executor — bạn thiếu "đồng hồ".** `run_jobs` cộng `worker.py` đã là một job queue hoàn chỉnh, có claim, lock, timeout. Mọi framework scheduler đầy đủ kèm job store riêng sẽ **dựng song song một hệ thống thứ hai làm đúng việc đó** — trùng lặp kiến trúc.
2. **Persistence là bắt buộc, không phải tuỳ chọn.** Vì máy có thể tắt lúc 6h, lịch phải nằm trong Postgres với `next_run_at` tường minh. Đây chính là điểm loại thư viện `schedule` và làm giảm giá trị của scheduler chỉ chạy trong bộ nhớ.
3. **Vị trí đặt scheduler bị ràng buộc bởi topology, không phải sở thích.** API sống trong container với `--reload` (nguy cơ double-fire, không thấy `CODE_ROOT` trên host); worker sống trên host (thấy mọi thứ, nhưng tắt là hết). Đây là trade-off trung tâm mà bước 3 và 4 phải giải.

### Quality Assessment

- **CAO** — đặc tính thư viện, bẫy multi-worker của FastAPI, cơ chế missed-run của Windows Task Scheduler, topology thực tế của dự án.
- **TRUNG BÌNH** — mức độ ổn định thực chiến của APScheduler 4.0 (tài liệu migration rõ ràng, nhưng thiếu báo cáo vận hành dài hạn).
- **Khoảng trống còn lại (dành cho bước 3-5):** cơ chế bầu chọn "single owner" cụ thể, hợp đồng API giữa scheduler và `run_jobs`, và thiết kế chi tiết cho việc phát hiện thay đổi tài liệu.

---

## Integration Patterns Analysis

> **Hai phát hiện tích hợp then chốt từ codebase (định hình toàn bộ phần này):**
> 1. **`worker.py` cố ý chỉ dùng thư viện chuẩn** — docstring ghi rõ: *"Chỉ dùng thư viện chuẩn (urllib) → không cần cài thêm gì"* (`worker.py:45`). Nhét APScheduler/croniter vào worker là **phá vỡ nguyên tắc thiết kế đã tuyên bố**.
> 2. **API đã có sẵn chỗ chạy vòng lặp nền** — `dashboard/api/main.py:185-195` dùng `@app.on_event("startup")` để chạy `asyncio.create_task(_workflow_run_poll_loop())` cùng hai thread riêng `telegram_bot.start()` / `slack_bot.start()`. Tức là **tiền lệ cho một scheduler loop trong API đã tồn tại và đang chạy ổn định**.

### API Design Patterns

Giao diện tích hợp cần thiết kế gồm hai nhóm: CRUD lịch (cho UI) và tick/claim (cho scheduler).

- _RESTful APIs:_ Theo chuẩn ngành, một schedule resource nên mang tối thiểu `cronExpression` + `timezone` tách rời, cộng thêm `state` (enabled/disabled) và `target`. Các API thực tế (Cron To Go, cron-job.org, AWS EventBridge Scheduler) đều hội tụ về bộ trường: `Id`, `ScheduleExpression`, `Timezone`, `State`, `Target`, `CreatedAt`.
- _Ánh xạ vào dự án:_ Thêm router `dashboard/api/routers/schedules.py` theo đúng pattern 17 router hiện có, đăng ký ở `main.py` với prefix `/api/schedules` — CRUD gắn `project_id`, cộng `POST /{id}/run-now` để chạy thử tay.
- _RPC và gRPC:_ **Không áp dụng.** Toàn hệ đang là HTTP/JSON; thêm gRPC là chi phí vô ích cho một tiến trình đơn.
- _GraphQL:_ **Không áp dụng** — dashboard đang gọi REST, không có lý do đổi.
- _Webhook Patterns:_ Không cần webhook ngoài; "sự kiện" ở đây là nội bộ và đã có đường ra riêng (xem mục Event-Driven bên dưới).

_Độ tin cậy: CAO (nhiều API thương mại đồng thuận về bộ trường)._
_Source: [cloud.google.com/scheduler — cron format & time zone](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules), [crontogo.com REST API reference](https://crontogo.com/blog/api-reference/), [docs.cron-job.org/rest-api.html](https://docs.cron-job.org/rest-api.html), [kubernetes.io — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)_

### Communication Protocols

- _HTTP/HTTPS:_ Kênh tích hợp duy nhất giữa worker và API. `worker.py:72` đặt `API = os.getenv("DASHBOARD_API_URL", "http://localhost:8100")`, hàm `_req()` (`worker.py:91-101`) gói `urllib.request` với timeout 15s, header `Content-Type: application/json`. Worker gọi `POST /api/run-jobs/claim` để nhận việc và `POST /{job_id}/complete` để báo xong.
- _Hệ quả thiết kế:_ Scheduler **không cần giao thức mới**. Nếu nó chỉ chèn dòng vào `run_jobs`, worker tiếp tục dùng đúng `_claim()` cũ — **thay đổi phía worker bằng 0**.
- _WebSocket:_ Đã dùng, nhưng cho mục đích khác — Slack Socket Mode chạy thread riêng vì `recv()` là lệnh chặn, để trong event loop sẽ treo cả API (`main.py:192-195`). Bài học này áp dụng trực tiếp cho scheduler: **vòng lặp chặn phải ở thread riêng, hoặc phải là `async` thuần**.
- _Message Queue Protocols (AMQP/MQTT):_ **Không áp dụng** — không có broker trong stack, và `run_jobs` đã đóng vai hàng đợi.

_Độ tin cậy: CAO (đọc trực tiếp mã nguồn)._

### Data Formats and Standards

- _Cron expression:_ Chuẩn phổ quát là **unix-cron 5 trường** (`phút giờ ngày tháng thứ`). Các phương ngữ mở rộng (Quartz, AWS EventBridge, Cloudflare) thêm `L` (last), `W` (nearest weekday), `#` (nth weekday) — nhưng 5 trường gốc là mẫu số chung. Lưu ý APScheduler dùng biến thể 8 trường **không tương thích crontab**, nên nếu chọn APScheduler thì cú pháp người dùng nhập sẽ khác chuẩn họ quen.
- _Timezone:_ Khuyến nghị nhất quán từ mọi nguồn: **lưu `timezone` thành trường riêng** theo tên tz database (ví dụ `Asia/Ho_Chi_Minh`), mặc định UTC, **không** dựa vào timezone hệ thống. Đây là điểm quyết định trực tiếp câu hỏi "6h sáng là 6h ở đâu" của bạn.
- _JSON:_ Định dạng trao đổi duy nhất, đã dùng xuyên suốt (`json.dumps`/`json.loads` trong `_req`).
- _Protobuf/MessagePack/CSV:_ **Không áp dụng.**

_Độ tin cậy: CAO (Google Cloud Scheduler + Kubernetes + nhiều nhà cung cấp đồng thuận)._
_Source: [cloud.google.com/scheduler — cron format & time zone](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules), [alltools.dev — Cron Expression Cheat Sheet](https://alltools.dev/reference/tech/cron-expression-cheat-sheet/), [integrate.io — Scheduling With Cron Expressions](https://www.integrate.io/blog/scheduling-with-cron-expressions/)_

### System Interoperability Approaches

- _Point-to-Point Integration:_ Kiến trúc hiện tại và phù hợp — worker ↔ API trực tiếp qua HTTP, không trung gian.
- _API Gateway / Service Mesh / ESB:_ **Không áp dụng.** Hệ có 3 service trên một máy; thêm tầng định tuyến là over-engineering thuần tuý.
- _Ranh giới khả kiến (điểm nghẽn tích hợp thật sự):_

| Thành phần | Thấy `clients/` | Thấy `CODE_ROOT` (`C:/www`) | Chạy nền được? |
|---|---|---|---|
| API container | ✅ (`/clients`) | ❌ | ✅ (đã có tiền lệ startup task) |
| `worker.py` (host) | ✅ | ✅ | ✅ (vòng poll 3s) |

  → **Đây là ngã ba quyết định:** nếu "tài liệu cần quét" nằm trong `clients/`, API tự quét được. Nếu nằm trong thư mục code của dự án (`CODE_ROOT`), **chỉ worker chạm tới được** — khi đó việc quét buộc phải là một job do worker thực thi, còn API chỉ giữ vai "đồng hồ".

_Độ tin cậy: CAO (docker-compose.yml mount list)._

### Job Queue Integration Patterns (thay cho "Microservices Integration")

Dự án **không phải microservices**, nên phần này quy về cách scheduler ghép vào hàng đợi sẵn có:

- _Transactional enqueue:_ Vì lịch và `run_jobs` cùng nằm trong Postgres, việc "đến giờ thì tạo job" có thể gói trong **một transaction**: cập nhật `last_run_at`/`next_run_at` và `INSERT INTO run_jobs` cùng lúc — không có cửa sổ mất/nhân đôi.
- _Idempotency key:_ Pattern chuẩn được đồng thuận rộng rãi: **unique constraint trên khoá idempotency + `INSERT ... ON CONFLICT DO NOTHING` trong cùng transaction** là cách *duy nhất* an toàn trước race. Kiểm tra kiểu "đã thấy khoá này chưa?" rồi mới insert **không an toàn** — hai tiến trình đều có thể thấy "chưa có" trước khi bên nào kịp ghi; phải để database phân xử quyền sở hữu.
  → Áp dụng: khoá dạng `(schedule_id, fire_time)` đặt unique. Dù tick chạy hai lần, dù máy restart giữa chừng, mỗi mốc giờ chỉ đẻ đúng một `run_jobs`.
- _Circuit Breaker / fault tolerance:_ **Đã có sẵn** — `run_jobs.py:76-88` tự đánh `failed` cho job `running` quá 2 giờ ("worker không báo complete sau 2 giờ"). Scheduler thừa hưởng cơ chế này miễn phí.
- _Backpressure (rủi ro thật):_ `run_jobs.py:90-92` chặn claim khi còn job `running` → **worker chạy tuần tự tuyệt đối**. Nếu 5 project cùng đặt 6h sáng, 5 job xếp hàng nối đuôi. Cần chính sách rõ: bỏ qua lần chạy nếu project đó còn job đang chờ, hoặc rải giờ (jitter) — AWS EventBridge Scheduler có hẳn trường `Jitter` cho đúng vấn đề này.
- _Service Discovery / Saga:_ **Không áp dụng.**

_Độ tin cậy: CAO cho idempotency pattern (nhiều nguồn độc lập nhấn mạnh cùng một kết luận)._
_Source: [oneuptime.com — Deduplicating with Idempotency Keys and Unique Constraints](https://oneuptime.com/blog/post/2026-07-21-deduplicate-idempotency-unique-constraint/view), [algomaster.io — Idempotency](https://algomaster.io/learn/system-design/idempotency), [backendbytes.com — Idempotency Patterns](https://backendbytes.com/articles/idempotency-patterns-distributed-systems/), [sqlserverscience.com — Idempotency Is a Contract](https://www.sqlserverscience.com/data-architecture/idempotency-keys-database/)_

### Event-Driven Integration

- _Publish-Subscribe:_ Không có broker, và không cần. Mô hình đúng ở đây là **polling trên bảng DB** — chính là cách `worker.py` và `_workflow_run_poll_loop` đang vận hành.
- _Đường ra cho sự kiện "phát hiện thay đổi":_ `chat_router.py` có sẵn hạ tầng gửi chat (`send_to(db, bot, chat_id, text)` tại `:298`, `fmt_for` tại `:310`). **ĐÍNH CHÍNH sau khi đọc kỹ mã nguồn:** `notify_run(run_id, ...)` (`:313`) KHÔNG dùng được cho lịch — nó chỉ TRẢ LỜI đúng cuộc chat đã kích hoạt một `WorkflowRun` (đọc `run.chat_bot_id`/`run.chat_id`, không có thì lặng lẽ return), mà lịch thì không có chat nguồn. Cách đúng: chọn `ChatBot` khớp `client_folder` của dự án (hẹp nhất thắng — xem docstring `models.ChatBot`) rồi gọi thẳng `send_to` cho từng id trong `bot.chats`. Vẫn **không phải dựng kênh mới**, nhưng không phải chỉ cắm một hàm là xong.
- _Event Sourcing / CQRS:_ **Không áp dụng** — quá nặng so với nhu cầu.
- _Message Broker (Kafka/RabbitMQ):_ **Không áp dụng** — `run_jobs` + Postgres đã đủ cho tải một máy đơn.

_Độ tin cậy: CAO (đọc trực tiếp mã nguồn)._

### Integration Security Patterns

- _Trạng thái hiện tại:_ `main.py:147-148` chỉ gắn `CORSMiddleware`; **không thấy middleware xác thực, không có `HTTPBearer`/API key dependency**. API mở ở cổng host `8100`.
- _Hệ quả cho scheduler:_ Endpoint `/api/schedules` sẽ thừa hưởng đúng mức bảo mật hiện tại — **không làm hệ thống kém an toàn hơn**, nhưng cũng nghĩa là bất kỳ ai chạm được `localhost:8100` đều tạo/sửa lịch được. Với triển khai host-local cá nhân thì chấp nhận được; **nếu máy này từng expose ra mạng thì đây là rủi ro cần xử lý riêng, nằm ngoài phạm vi nghiên cứu này.**
- _Provenance (nên có):_ Job do scheduler tạo cần phân biệt được với job do người bấm nút — thêm trường kiểu `source` (`manual` / `schedule`) và `schedule_id` vào `run_jobs` để truy vết và để UI hiển thị đúng.
- _OAuth/JWT/mTLS:_ **Không áp dụng** ở quy mô hiện tại.

_Độ tin cậy: CAO cho hiện trạng (đọc mã); khuyến nghị provenance là suy luận thiết kế, không phải trích dẫn._

### Cross-Integration Analysis

1. **Hợp đồng tích hợp đã tồn tại — chỉ thiếu người gọi.** `run_jobs` là điểm nối duy nhất cần chạm. Scheduler chèn dòng, worker `_claim()` như thường lệ. **Không sửa `worker.py`, không thêm dependency cho worker** — giữ nguyên nguyên tắc "chỉ stdlib".
2. **Tiền lệ kỹ thuật đã có trong API.** `_workflow_run_poll_loop` + hai bot thread chứng minh API là nơi các tiến trình nền đang sống. Scheduler tick loop đặt cùng chỗ là đi theo pattern của chính dự án, không phải sáng tạo mới.
3. **Ba trường dữ liệu quyết định mọi thứ:** `cron_expression` (5 trường unix-cron), `timezone` (tên tz database), và `next_run_at` (mốc bền vững trong DB). Thiếu trường thứ ba thì không thể chạy bù sau khi máy tắt.
4. **Idempotency là tuyến phòng thủ, không phải tính năng phụ.** Unique `(schedule_id, fire_time)` + `ON CONFLICT DO NOTHING` xử lý gọn cả ba rủi ro: tick chạy trùng, API reload giữa chừng, và chạy bù sau khi khởi động lại.

### Quality Assessment

- **CAO** — hợp đồng HTTP worker↔API, tiền lệ background task trong API, pattern idempotency, chuẩn trường cron/timezone, hiện trạng bảo mật.
- **TRUNG BÌNH** — chính sách backpressure tối ưu khi nhiều project trùng giờ (phụ thuộc số lượng project thực tế, cần bạn xác nhận).
- **Khoảng trống còn lại:** tài liệu cần quét nằm ở `clients/` hay `CODE_ROOT` — câu trả lời quyết định scheduler chỉ làm "đồng hồ" hay làm luôn "người quét". Sẽ chốt ở bước 4-5.

---

## Architectural Patterns and Design

### System Architecture Patterns

**Phát hiện xác nhận mạnh nhất của cả nghiên cứu:** ngành đã hội tụ về việc **tách "đồng hồ" (dispatcher/clock) khỏi "người thực thi" (executor)**:

> *"Dispatcher publish vào queue còn executor pull từ queue. Một job chạy 4 tiếng không chặn dispatcher — nó chặn executor worker. Đây chính là lý do dispatcher và executor là hai thành phần khác nhau."*

Đối chiếu với `ai_team_clean`: **bạn đã có executor (`worker.py`) và đã có queue (`run_jobs`). Thứ duy nhất còn thiếu là dispatcher.** Đây không phải suy đoán — nó khớp chính xác với mô hình tham chiếu.

Một scheduler đầy đủ gồm 4 mảnh ghép; dự án đã có 3:

| Mảnh | Vai trò | Trạng thái trong dự án |
|---|---|---|
| **Schedule store** | Nguồn sự thật bền vững: cái gì chạy, lúc nào | ❌ **THIẾU** — cần bảng `schedules` |
| **Tick coordinator** | Định kỳ thức dậy, tìm job đến hạn, đẩy sang queue | ❌ **THIẾU** — cần vòng lặp trong API |
| **Execution queue** | Hàng đợi việc đến hạn | ✅ `run_jobs` |
| **Executor** | Thực thi thật | ✅ `worker.py` |

_Các pattern bị loại và lý do:_
- **APScheduler với job store riêng:** dựng mảnh 1+3 song song với `run_jobs` → hai nguồn sự thật, hai nơi phải sửa khi đổi logic. Trùng lặp kiến trúc.
- **Windows Task Scheduler làm scheduler chính:** không cấu hình per-project từ UI được, không truy vết được trong DB, và **nếu máy tắt thì Docker Desktop cũng tắt** → API + Postgres chết theo, nên lợi thế "wake máy" chỉ có ý nghĩa khi máy *ngủ*, không phải *tắt*.
- **Microservices/serverless/event-driven broker:** vượt xa quy mô một máy đơn.

_Độ tin cậy: CAO (nhiều nguồn thiết kế hệ thống độc lập mô tả cùng một phân rã)._
_Source: [dev.to — Design a Job Scheduler at 10M Jobs/Day](https://dev.to/gabrielanhaia/design-a-job-scheduler-at-10m-jobsday-4-components-3-failure-modes-28hn), [dzone.com — How to Design a Distributed Job Scheduler](https://dzone.com/articles/design-a-distributed-job-scheduler), [bunqueue.dev — Cron Scheduler architecture](https://bunqueue.dev/architecture/cron-scheduler)_

### Design Principles and Best Practices

- **Schedule store cần đúng ba thứ:** *"durability, một index trên thời điểm bắn kế tiếp, và khả năng cập nhật cả hai một cách atomic khi job chạy."* → bảng `schedules` với `next_run_at` **có index**, cập nhật cùng transaction với `INSERT run_jobs`.
- **Misfire policy phải tường minh, đặt theo từng lịch:** *"đội nào để ngầm định thì đều bị bất ngờ sau sự cố đầu tiên."* Không được để hành vi "máy tắt lúc 6h" là chuyện tình cờ.
- **Người dùng không nghĩ theo ngôn ngữ "misfire":** *"họ chỉ mong scheduler nhận ra là đã lỡ, rồi chạy sớm sau khi máy bật lại, hoặc nói rõ là bỏ qua."* → UI nên hỏi bằng tiếng người: *"Máy tắt lúc tới giờ thì: [Chạy bù khi bật lại] / [Bỏ qua, đợi lần sau]"*.
- **Tái dụng pattern của chính dự án** thay vì nhập khẩu pattern mới: vòng tick nên bắt chước `_workflow_run_poll_loop` (`main.py:185-187`), việc claim nên bắt chước `with_for_update(skip_locked=True)` (`run_jobs.py:96`).

_Độ tin cậy: CAO._
_Source: [n8n Docs — Durable scheduler](https://docs.n8n.io/deploy/host-n8n/configure-n8n/durable-scheduler), [github.com/slothflowlabs/duckle#296 — overlap, misfire, catch-up policies](https://github.com/slothflowlabs/duckle/issues/296), [github.com/openai/codex#24327 — missed-run catch-up after offline](https://github.com/openai/codex/issues/24327)_

### Scalability and Performance Patterns

Quy mô ở đây là **vài chục lịch, một máy** — nên "scalability" quy về đúng một rủi ro: **dồn ứ hàng đợi**.

- **Concurrency policy (giải pháp trực diện):** mô hình tham chiếu dùng cột `concurrency_policy` với ba giá trị **`allow` / `forbid` / `replace`**, để dispatcher kiểm tra lần chạy gần nhất *trước khi* publish, ngăn job dài chồng lên nhau.
  → Với `ai_team_clean`, `forbid` là mặc định đúng: **nếu project đó còn job `queued`/`running`, bỏ qua nhịp này** thay vì chất chồng.
- **Jitter / rải giờ:** AWS EventBridge Scheduler có hẳn trường `Jitter` cho tình huống nhiều lịch trùng mốc. Với worker tuần tự của bạn, rải lệch vài phút giữa các project là biện pháp rẻ và hiệu quả.
- **Giới hạn catch-up (bắt buộc):** *"phải có giới hạn để một server quay lại sau một năm không bất ngờ bắn ra hàng nghìn job."* → chạy bù **tối đa 1 lần**, và chỉ khi mốc lỡ nằm trong cửa sổ hợp lý (ví dụ 24 giờ).
- **Chi phí tick:** một truy vấn `SELECT ... WHERE next_run_at <= now()` trên cột có index, mỗi 30–60 giây → không đáng kể.
- **Horizontal scaling:** không áp dụng và không nên theo đuổi.

_Độ tin cậy: CAO cho pattern; TRUNG BÌNH cho tham số cụ thể (24h, 30–60s) — đây là khuyến nghị khởi điểm, nên chỉnh theo thực tế._
_Source: [bunqueue.dev — concurrency_policy allow/forbid/replace](https://bunqueue.dev/architecture/cron-scheduler), [github.com/DigitalMeld/agentmeld#117 — missed-run policy, budgets](https://github.com/DigitalMeld/agentmeld/issues/117)_

### Integration and Communication Patterns

- **Điểm nối duy nhất:** dispatcher → `INSERT INTO run_jobs`. Worker không đổi một dòng nào.
- **Ship `scheduled_for` kèm job:** khuyến nghị từ mô hình tham chiếu là *"đính `scheduled_for` vào mọi message và cho executor so đồng hồ của chính nó với mốc đó khi nhận"* — để executor phát hiện lệch giờ mà từ chối hoặc chờ.
  → Áp dụng: thêm cột `fire_time` (hoặc `scheduled_for`) vào `run_jobs`, hữu ích cả cho log lẫn debug DST.
- **Optimistic concurrency:** mô hình tham chiếu dùng cột `version` để xử lý khi hai scheduler tranh nhau đẩy cùng một cron job. Dự án bạn chỉ có một API instance, nên `SKIP LOCKED` là đủ — nhưng `version` là bảo hiểm rẻ nếu sau này chạy nhiều worker uvicorn.
- **Kênh thông báo:** tái dụng `chat_router.notify_run()` (Telegram/Slack) — đã phân tích ở bước 3.

_Độ tin cậy: CAO._
_Source: [bunqueue.dev — Cron Scheduler](https://bunqueue.dev/architecture/cron-scheduler), [github.com/kagkarlsson/db-scheduler](https://github.com/kagkarlsson/db-scheduler)_

### Security Architecture Patterns

- **Hiện trạng:** API chỉ có `CORSMiddleware`, không có tầng xác thực (`main.py:147-148`). Scheduler không làm thay đổi bề mặt tấn công — nó chỉ thêm một router CRUD nữa sau cùng một cánh cửa.
- **Rủi ro mới duy nhất, và nó có thật:** lịch là **thực thi tự động, không người giám sát**. Một lịch bị sửa sai (hoặc cố ý) sẽ âm thầm chạy `python main.py` mỗi ngày mà không ai bấm nút. → Cần **audit trail**: `created_by`, `updated_at`, và `run_jobs.source = 'schedule'` + `schedule_id` để mọi run tự động đều truy nguyên được.
- **Nguyên tắc đặc quyền tối thiểu:** scheduler **chỉ được phép chèn `run_jobs`** — không tự gọi `claude`, không tự sửa file. Mọi tác dụng phụ đi qua worker, nơi đã có timeout và log.
- **OAuth/JWT/mTLS:** không áp dụng ở quy mô host-local.

_Độ tin cậy: CAO cho hiện trạng (đọc mã); khuyến nghị audit là suy luận thiết kế._

### Data Architecture Patterns

Thiết kế bảng `schedules` đề xuất (tổng hợp từ chuẩn ngành + ràng buộc dự án):

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `id` | PK | |
| `project_id` | FK → projects | Lịch gắn theo dự án (đúng yêu cầu gốc) |
| `name` | String | Tên người đọc được |
| `cron_expression` | String | **unix-cron 5 trường** — chuẩn người dùng đã quen |
| `timezone` | String | Tên tz database, mặc định `Asia/Ho_Chi_Minh` |
| `enabled` | Bool | Bật/tắt không cần xoá |
| `job_kind` | String | `scan_docs` trước, mở đường cho loại khác sau |
| `misfire_policy` | String | `catchup_once` / `skip` — **tường minh, theo từng lịch** |
| `concurrency_policy` | String | `forbid` (mặc định) / `allow` |
| `next_run_at` | DateTime **có INDEX** | UTC. Cột trung tâm của toàn bộ thiết kế |
| `last_run_at` | DateTime | UTC |
| `last_status` | String | Kết quả lần gần nhất |
| `version` | Int | Optimistic concurrency (bảo hiểm) |
| `created_at` / `updated_at` | DateTime | Audit |

Và một bảng/ràng buộc phụ cho idempotency: **UNIQUE `(schedule_id, fire_time)`** — đã phân tích ở bước 3.

- _Lưu trữ thời gian:_ **luôn UTC trong DB**, quy đổi sang `timezone` chỉ khi tính `next_run_at` và khi hiển thị. Đây là đồng thuận tuyệt đối giữa các nguồn.
- _Snapshot tài liệu:_ cần một nơi lưu "lần quét trước thấy gì" — hoặc bảng `doc_snapshots` (`project_id`, `path`, `sha256`, `scanned_at`), hoặc một file JSON trong `clients/{slug}/`. Bảng DB dễ truy vấn và so sánh hơn.

_Độ tin cậy: CAO cho nguyên tắc (UTC, index, atomic update); thiết kế cột cụ thể là tổng hợp của tôi, cần review khi làm PRD._
_Source: [bunqueue.dev — schedule store design](https://bunqueue.dev/architecture/cron-scheduler), [cloud.google.com/scheduler — timezone](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules), [github.com/kagkarlsson/db-scheduler](https://github.com/kagkarlsson/db-scheduler)_

### Deployment and Operations Architecture

**Quyết định đặt scheduler ở đâu — bảng cân nhắc cuối cùng:**

| Tiêu chí | Trong API container | Trong `worker.py` (host) | Windows Task Scheduler |
|---|---|---|---|
| Có tiền lệ trong dự án | ✅ `_workflow_run_poll_loop` + 2 bot thread | ✅ vòng poll 3s | ❌ |
| Giữ được nguyên tắc "worker chỉ dùng stdlib" | ✅ | ❌ **phá vỡ** | ✅ |
| Cấu hình per-project từ UI | ✅ tự nhiên | ⚠️ được, nhưng lệch vai | ❌ rất khó |
| Truy vết trong DB | ✅ | ✅ | ❌ |
| Chạy được khi máy **ngủ** | ❌ | ❌ | ✅ (cần bật wake timer) |
| Chạy được khi máy **tắt** | ❌ | ❌ | ❌ |
| Rủi ro double-fire do `--reload` | ⚠️ **có thật** | ✅ không | ✅ không |

**Kết luận kiến trúc: đặt tick loop trong API container**, vì đó là nơi duy nhất hội đủ (tiền lệ + UI + truy vết + không phá nguyên tắc worker). Rủi ro `--reload` được vô hiệu hoá bởi **UNIQUE `(schedule_id, fire_time)`** — reload có làm tick chạy lại thì DB vẫn chỉ nhận đúng một job.

_Vận hành:_
- **Bổ sung (không thay thế):** một task Windows Task Scheduler ở mức boot/logon để **khởi động Docker Desktop + `worker.py`** — đây là cách đúng để dùng WTS trong kiến trúc này: lo phần "bật máy lên thì hệ thống sống lại", không lo phần "lịch nào chạy lúc nào".
- **Quan sát:** log mỗi lần tick quyết định gì (bắn / bỏ qua vì `forbid` / chạy bù), nếu không sẽ không ai debug nổi khi lịch "không chạy".
- **DST:** Việt Nam không có DST nên rủi ro thấp, nhưng lưu UTC + tên timezone vẫn là cách duy nhất đúng nếu sau này có dự án ở múi giờ khác.

_Độ tin cậy: CAO cho bảng so sánh (dựa trên mã nguồn + tài liệu Microsoft đã trích ở bước 2)._

---

## Implementation Approaches and Technology Adoption

> **Ràng buộc triển khai xác minh thêm:** `dashboard/api/Dockerfile` dùng `python:3.12-slim`, `dashboard/api/requirements.txt` ghim phiên bản chặt (`fastapi==0.115.0`, `sqlalchemy==2.0.35`, `psycopg2-binary==2.9.9`...). **Python 3.12 nghĩa là `zoneinfo` nằm trong thư viện chuẩn — không cần `pytz`.**

### Technology Adoption Strategies

- **Chiến lược đúng ở đây là "gradual", không phải "big bang".** Thứ tự an toàn: bảng + API CRUD → tick loop ở chế độ **chỉ ghi log** → bật bắn job thật cho *một* project → mở rộng.
- **Dependency mới tối thiểu:** chỉ **một** gói — `croniter` — và **chỉ thêm vào `dashboard/api/requirements.txt`**, không đụng tới `worker.py` (giữ nguyên tắc "chỉ stdlib"). `croniter` hiện do **pallets-eco** duy trì, hỗ trợ khởi tạo bằng datetime có timezone qua `zoneinfo`.
- **Bằng chứng thực chiến về DST:** có báo cáo dùng **croniter 6.2.4 cùng `ZoneInfo`** giữ đúng lịch 11:00 thứ Sáu và 06:30 hằng ngày xuyên qua chuyển DST của Melbourne — kèm khuyến nghị **ghim phiên bản và tự kiểm chứng**. Phù hợp với thói quen ghim version sẵn có của dự án.
- **Lưu ý vận hành khi thêm dep:** Dockerfile chạy `pip install` ở bước build, nên thêm `croniter` đòi **`docker compose build api`**, không chỉ `--reload`.
- **Phương án không-dependency (dự phòng):** nếu muốn tuyệt đối không thêm gói, có thể tự tính `next_run_at` cho tập biểu thức hẹp (chỉ `phút giờ * * *`). Rẻ hơn nhưng mất tính tổng quát — chỉ nên chọn nếu yêu cầu thực sự chỉ là "mỗi ngày lúc HH:MM".

_Độ tin cậy: CAO cho tình trạng croniter; TRUNG BÌNH cho kết quả DST (một báo cáo thực chiến, nên tự kiểm chứng)._
_Source: [pypi.org/project/croniter](https://pypi.org/project/croniter/), [github.com/pallets-eco/croniter](https://github.com/pallets-eco/croniter), [dev.to — When does this cron run next?](https://dev.to/sendotltd/when-does-this-cron-run-next-give-it-its-own-70-mb-container-2ool)_

### Development Workflows and Tooling

- **Bám pattern sẵn có, không phát minh:** router mới `dashboard/api/routers/schedules.py` theo khuôn 17 router hiện tại; model thêm vào `dashboard/api/models.py`; schema vào `schemas.py`; hook React `dashboard/src/hooks/useSchedules.ts` theo mẫu `useMcp.ts`; UI `ProjectSchedules.tsx` theo mẫu `ProjectMcp.tsx` (đều đang có trong working tree).
- **Vòng tick đặt cạnh `_workflow_run_poll_loop`** trong `main.py` — cùng một `@app.on_event("startup")`, cùng kiểu `asyncio.create_task`.
- **Migration DB:** dự án chưa thấy dùng Alembic; `main.py` có nhánh xử lý theo `dialect` khi khởi tạo. Cần chốt cách tạo bảng mới cho nhất quán với cách `run_jobs`/`mcp` đã làm.

_Độ tin cậy: CAO (đọc trực tiếp cấu trúc repo)._

### Testing and Quality Assurance

Đây là phần dễ bị bỏ qua nhất và cũng là nơi lỗi lịch hay trốn.

- **Nguyên tắc số một: tiêm đồng hồ (clock injection), không `sleep`.** Thay vì chờ thời gian thật, test khởi đầu từ một mốc cố định rồi **nhảy thẳng tới `next_run_at` mà chính hàm báo về**.
- **Vì sao bắt buộc:** trên CI tải nặng, event loop có thể bị trễ qua mốc đã hẹn, khiến hành vi **đúng** vẫn fail ngẫu nhiên. Đồng hồ giả làm test tuần tự theo nhân quả, tải máy không thể tạo ra hay bỏ lỡ cửa sổ lịch.
- **Công cụ:** `freezegun` cho Python — đóng băng thời gian để kiểm thử logic phụ thuộc ngày giờ.
- **Với integration test: gọi thẳng hàm được hẹn lịch**, đừng chờ đồng hồ.
- **Bộ ca kiểm thử tối thiểu nên có** (đặt trong `tests/`, cạnh `test_worker_mcp.py`):
  1. `next_run_at` đúng cho `0 6 * * *` ở `Asia/Ho_Chi_Minh`
  2. Máy tắt 3 ngày, `misfire_policy=catchup_once` → tạo **đúng 1** job, không phải 3
  3. `misfire_policy=skip` → không tạo job nào, chỉ dời `next_run_at`
  4. Tick chạy hai lần liên tiếp cùng `fire_time` → **UNIQUE chặn**, chỉ 1 dòng `run_jobs`
  5. `concurrency_policy=forbid` + project còn job `running` → bỏ qua, có log
  6. Quét tài liệu không đổi → không tạo job / không báo

_Độ tin cậy: CAO (pattern được nhiều nguồn kiểm thử độc lập khẳng định)._
_Source: [betterstack.com — Beginner's Guide to Unit Testing with Freezegun](https://betterstack.com/community/guides/testing/freezegun-unit-testing/), [github.com/strapi/strapi#27659 — make cron timer tests deterministic](https://github.com/strapi/strapi/pull/27659), [cronbase.dev — Testing Cron Expressions](https://cronbase.dev/guides/testing-cron-expressions/)_

### Deployment and Operations Practices

- **Dry-run là yêu cầu bắt buộc, không phải tính năng xa xỉ.** Khuyến nghị nhất quán: *"mọi script tự động hoá mới đều nên có cờ dry-run ghi lại hành động dự định mà không thực thi, để lịch được soát trước khi chạy thật."*
  → Áp dụng: tick loop chạy trước ở chế độ `SCHEDULER_DRY_RUN=1` — ghi log "đáng lẽ tạo job cho project X lúc T" mà không `INSERT`. Soát log vài ngày rồi mới bật thật.
- **Lộ trình rollout an toàn** (rút gọn từ chuỗi dry-run → shadow → canary → 100% cho quy mô của bạn): **dry-run → bật cho 1 project → bật cho tất cả**.
- **Log để replay, không chỉ để đọc:** mỗi tick phải ghi *quyết định* — bắn / bỏ qua vì `forbid` / chạy bù / lệch giờ. Không có dòng log này thì lúc "lịch không chạy" sẽ không ai dựng lại được chuyện gì đã xảy ra.
- **Khởi động lại sau khi máy tắt:** một task Windows Task Scheduler ở mức boot/logon để bật Docker Desktop + `worker.py` — đảm bảo catch-up thực sự có cơ hội chạy.

_Độ tin cậy: CAO._
_Source: [github.com/ajmarkow/nix-components#48 — dry-run flag for automation scripts](https://github.com/ajmarkow/nix-components/pull/48), [oneuptime.com — Safe Dry Runs for Destructive Automation](https://oneuptime.com/blog/post/2026-08-05-safe-dry-run-destructive-automation/view), [dev.to — dry-run / shadow / canary / rollout](https://dev.to/kanaria007/make-ab-tests-operable-goal-surface-deterministic-logs-safe-automation-dry-run-shadow-canary-9hc)_

### Team Organization and Skills

Đây là dự án một người vận hành, nên phần này quy về **kỹ năng cần có, không phải tổ chức đội**:

- **Đã có sẵn trong repo:** FastAPI router, SQLAlchemy model, React hook + component, vòng poll nền — mọi mẫu cần dùng đều đã tồn tại để sao chép.
- **Cần bổ sung:** hiểu `zoneinfo` và bẫy DST (đặc biệt: **`datetime.utcnow()` là sai**, và `timedelta(days=1)` cộng đúng 24 giờ chứ không giữ nguyên giờ đồng hồ khi có DST).
- **Rủi ro nhân sự:** logic lịch là loại code "chạy lúc không ai nhìn". Nếu không viết test và không log, lỗi sẽ chỉ lộ ra sau vài tuần im lặng.

_Độ tin cậy: CAO cho bẫy `utcnow`/`timedelta` (nhiều nguồn cảnh báo giống nhau)._
_Source: [timeandtool.com — Python datetime Done Right](https://www.timeandtool.com/blog/python-datetime-timezone-guide), [medium — Python datetime Part 4: Time Zones, zoneinfo, DST](https://medium.com/engineering-playbook/python-datetime-part-4-time-zones-zoneinfo-and-daylight-saving-time-c06d9c18f4f8)_

### Cost Optimization and Resource Management

- **Chi phí tiền bạc: gần như bằng 0** — không thêm service, không thêm container, không dịch vụ cloud. Chỉ thêm một gói Python và một bảng DB.
- **Chi phí tài nguyên: một truy vấn có index mỗi 30–60 giây.** Không đáng kể so với `python main.py` mà nó kích hoạt.
- **Chi phí thật nằm ở chỗ khác — token và thời gian máy.** Một lịch quét hằng ngày cho mỗi project nghĩa là mỗi ngày có N lần chạy pipeline tự động. **Đây mới là khoản cần kiểm soát**, và là lý do `concurrency_policy=forbid` cùng bước "kiểm tra có thay đổi thật không **trước khi** tạo job" quan trọng đến vậy.
- **Tối ưu quyết định:** nên **quét trước, tạo job sau** — nếu tài liệu không đổi thì đừng đánh thức cả pipeline.

_Độ tin cậy: CAO (suy luận trực tiếp từ kiến trúc đã xác minh)._

### Risk Assessment and Mitigation

| # | Rủi ro | Mức | Biện pháp giảm thiểu |
|---|---|---|---|
| 1 | **Double-fire do `uvicorn --reload`** khởi động lại tick loop | Cao | UNIQUE `(schedule_id, fire_time)` + `ON CONFLICT DO NOTHING` |
| 2 | **Máy tắt lúc 6h sáng** → lịch không chạy | Cao | `misfire_policy` tường minh + catch-up **có giới hạn** (tối đa 1 lần, trong cửa sổ 24h) + task WTS khởi động hệ thống lúc boot |
| 3 | **Dồn ứ hàng đợi** khi nhiều project trùng giờ (worker tuần tự) | Trung bình-Cao | `concurrency_policy=forbid` + rải giờ (jitter) |
| 4 | **Bão job** khi máy tắt lâu ngày rồi bật lại | Trung bình | Chặn trên catch-up — *"server quay lại sau một năm không được bắn ra hàng nghìn job"* |
| 5 | **Sai giờ do timezone/DST** | Trung bình | Lưu UTC + tên tz database; `zoneinfo`; **không dùng `datetime.utcnow()`**; test DST |
| 6 | **Lịch chạy âm thầm không ai biết** | Trung bình | Log mọi quyết định tick + `run_jobs.source='schedule'` + `schedule_id`; thông báo qua `chat_router.send_to()` |
| 7 | **Bật nhiều uvicorn worker sau này** → scheduler nhân bản | Thấp (hiện tại) | Postgres advisory lock cho leader election — tự nhả khi kết nối đóng, không cần heartbeat/TTL |
| 8 | **Quét tài liệu sai chỗ** (tài liệu nằm ngoài tầm nhìn container) | Chưa xác định | **Cần bạn xác nhận** vị trí tài liệu; nếu ở `CODE_ROOT` thì việc quét phải do worker làm |

_Độ tin cậy: CAO cho rủi ro 1-6; rủi ro 8 phụ thuộc thông tin bạn chưa cung cấp._
_Source: [dev.to — Postgres Advisory Locks for Distributed Cron](https://dev.to/mukesh_13/postgres-advisory-locks-for-distributed-cron-killing-duplicate-job-runs-without-a-redis-dependency-1bfl), [tedkim.dev — Leader Election with PostgreSQL](https://tedkim.dev/posts/leader-election-with-postgresql/)_

---

## Technical Research Recommendations

### Implementation Roadmap

**Giai đoạn 1 — Nền tảng dữ liệu (nhỏ, không rủi ro)**
1. Model `Schedule` trong `dashboard/api/models.py` (cột theo thiết kế ở bước 4), index trên `next_run_at`
2. Thêm `source` + `schedule_id` + `fire_time` vào `RunJob`; UNIQUE `(schedule_id, fire_time)`
3. Schema Pydantic trong `schemas.py`

**Giai đoạn 2 — API CRUD (chưa có gì tự chạy)**
4. `dashboard/api/routers/schedules.py`, đăng ký prefix `/api/schedules` trong `main.py`
5. Validate `cron_expression` + `timezone` ngay tại API, trả về **bản xem trước 5 lần chạy kế tiếp** để người dùng tự kiểm chứng trước khi lưu

**Giai đoạn 3 — Đồng hồ ở chế độ câm (dry-run)**
6. Thêm `croniter` vào `dashboard/api/requirements.txt`, `docker compose build api`
7. Tick loop trong `@app.on_event("startup")` cạnh `_workflow_run_poll_loop`, chu kỳ 30–60s
8. Chạy với `SCHEDULER_DRY_RUN=1` — **chỉ ghi log**, không `INSERT`. Soát log ít nhất một chu kỳ ngày đêm

**Giai đoạn 4 — Bắn thật, phạm vi hẹp**
9. Tắt dry-run, bật cho **đúng một** project
10. Kiểm chứng: job xuất hiện trong `run_jobs`, worker nhận, UI hiển thị nguồn "schedule"

**Giai đoạn 5 — Quét tài liệu**
11. Bảng `doc_snapshots` (`project_id`, `path`, `sha256`, `scanned_at`)
12. Logic so sánh: `git diff --name-only --diff-filter=ACMR` nếu tài liệu trong git; ngược lại snapshot `{path: sha256}`
13. **Quét trước, tạo job sau** — không đổi thì không đánh thức pipeline
14. Thông báo qua `chat_router.send_to()`

**Giai đoạn 6 — UI + hoàn thiện**
15. `useSchedules.ts` + `ProjectSchedules.tsx` theo mẫu `useMcp.ts` / `ProjectMcp.tsx`
16. Task Windows Task Scheduler khởi động Docker Desktop + worker lúc boot
17. Bộ test theo 6 ca đã liệt kê

### Technology Stack Recommendations

| Quyết định | Khuyến nghị | Lý do cốt lõi |
|---|---|---|
| **Engine lịch** | `croniter` (ghim version) + tick loop tự viết | Chỉ cần tính `next_run_at`; không dựng job store thứ hai chồng lên `run_jobs` |
| **Nơi đặt scheduler** | **Trong API container** | Nơi duy nhất hội đủ: đã có tiền lệ background task, thấy được UI/DB, **không phá nguyên tắc "worker chỉ stdlib"** |
| **Nguồn sự thật** | Bảng `schedules` trong Postgres, `next_run_at` có index | Bền vững qua restart — điều kiện cần để chạy bù |
| **Chống double-fire** | UNIQUE `(schedule_id, fire_time)` + `ON CONFLICT DO NOTHING` | Để DB phân xử; kiểm tra ở tầng ứng dụng **không** an toàn trước race |
| **Chống dồn ứ** | `concurrency_policy=forbid` + jitter | Worker tuần tự tuyệt đối |
| **Missed run** | `misfire_policy` theo từng lịch, catch-up **có chặn trên** | Phải tường minh, nếu không sẽ bị bất ngờ sau sự cố đầu tiên |
| **Timezone** | UTC trong DB + tên tz database, dùng `zoneinfo` (stdlib Python 3.12) | Không cần `pytz`; tránh bẫy `utcnow()` |
| **Phát hiện thay đổi** | `git diff` nếu có git; nếu không, snapshot `sha256` | Rẻ, chính xác, không cần observer chạy liên tục |
| **Thông báo** | Tái dụng `chat_router.send_to()` + bot khớp `client_folder` | Kênh Telegram/Slack đã có sẵn (KHÔNG dùng `notify_run` — hàm đó chỉ trả lời chat đã kích hoạt run) |
| **APScheduler** | ❌ **Không dùng** | Dựng song song job store + executor với `run_jobs`; bản 4.0 còn phá tương thích job store |
| **Windows Task Scheduler** | ⚠️ **Chỉ dùng bổ trợ** | Khởi động hệ thống lúc boot — không làm scheduler chính (không cấu hình per-project, không truy vết được) |
| **Redis** | ❌ **Không cần** | Postgres advisory lock / `SKIP LOCKED` làm được việc tương đương, và pattern đó đã có trong repo |

### Skill Development Requirements

1. **`zoneinfo` và DST** — bẫy `datetime.utcnow()`, bẫy `timedelta(days=1)` khi đổi giờ
2. **Test với đồng hồ giả** — `freezegun`, tiêm clock, tuyệt đối không `sleep` trong test
3. **Ngữ nghĩa `ON CONFLICT` của Postgres** — vì sao unique constraint mới là thứ chặn race, không phải câu `SELECT` kiểm tra trước
4. **Đọc lại chính repo mình** — mọi mẫu cần dùng (`_workflow_run_poll_loop`, `with_for_update(skip_locked=True)`, `useMcp.ts`) đều đã có sẵn

### Success Metrics and KPIs

| Chỉ số | Mục tiêu | Cách đo |
|---|---|---|
| Độ chính xác giờ chạy | Job tạo trong vòng **±1 chu kỳ tick** so với giờ hẹn | So `fire_time` với `run_jobs.created_at` |
| Tỉ lệ trùng lặp | **0** job trùng cho cùng `(schedule_id, fire_time)` | Đếm vi phạm UNIQUE trong log |
| Xử lý lỡ nhịp | 100% lần lỡ **trong cửa sổ** được xử lý đúng theo policy đã đặt | Log quyết định của tick sau mỗi lần khởi động lại |
| Nhiễu vô ích | Tỉ lệ lần quét **không** tạo job khi tài liệu không đổi | Đếm `scan → no-change` so với tổng số lần quét |
| Sức khoẻ hàng đợi | Độ sâu `run_jobs` ở trạng thái `queued` **không tăng đơn điệu** | Truy vấn định kỳ |
| Khả năng truy vết | 100% run tự động có `source='schedule'` + `schedule_id` | Truy vấn `run_jobs` |

---
---

# Đồng Hồ Còn Thiếu: Nghiên Cứu Kỹ Thuật Toàn Diện về Scheduled Task Theo Dự Án cho `ai_team_clean`

## Executive Summary

Yêu cầu ban đầu nghe như một tính năng mới: *"thêm task chạy schedule như cron job cho mỗi dự án, ví dụ 6h sáng hàng ngày quét tài liệu xem có gì thay đổi không."* Nhưng sau khi khảo sát mã nguồn và đối chiếu với các mô hình tham chiếu của ngành, kết luận trung tâm là: **`ai_team_clean` không thiếu một hệ thống scheduler — nó thiếu đúng một mảnh ghép.**

Ngành đã hội tụ về việc phân rã scheduler thành bốn thành phần: *schedule store* (nguồn sự thật bền vững), *tick coordinator* (đồng hồ), *execution queue* (hàng đợi), và *executor* (người thực thi). Dự án của bạn **đã có hai thành phần cuối và chúng đang chạy tốt**: bảng `run_jobs` là hàng đợi hoàn chỉnh có claim, lock và timeout; `worker.py` là executor với vòng poll 3 giây. Thứ còn thiếu là hai thành phần đầu — và cả hai đều nhỏ. Điều này lật ngược trực giác thông thường "cần scheduler thì cài APScheduler": làm vậy sẽ dựng song song một job store và một executor thứ hai chồng lên thứ đã có, tạo ra hai nguồn sự thật cho cùng một khái niệm.

Nghiên cứu cũng phát hiện hai ràng buộc từ chính mã nguồn mà mọi thiết kế phải tôn trọng. Thứ nhất, `worker.py` tuyên bố thành văn rằng nó **chỉ dùng thư viện chuẩn** — nên scheduler không thuộc về đó. Thứ hai, API container **đã chạy các tiến trình nền** (`_workflow_run_poll_loop` cùng hai bot thread), nghĩa là tiền lệ kỹ thuật cho một tick loop đã tồn tại và đã được kiểm chứng trong chính dự án này. Vị trí đặt scheduler vì thế không phải câu hỏi sở thích, mà đã được cấu trúc hệ thống trả lời sẵn.

**Key Technical Findings:**

- **Kiến trúc:** Tách "đồng hồ" khỏi "người thực thi" là pattern chuẩn — dispatcher publish, executor pull. Dự án đã có nửa sau; chỉ cần bổ sung nửa trước.
- **Vị trí:** Tick loop thuộc về **API container** — nơi duy nhất hội đủ tiền lệ background task, khả năng cấu hình từ UI, truy vết trong DB, và không phá nguyên tắc "worker chỉ stdlib".
- **An toàn dữ liệu:** Chống bắn trùng **phải** do database phân xử — UNIQUE `(schedule_id, fire_time)` + `ON CONFLICT DO NOTHING`. Kiểm tra ở tầng ứng dụng không an toàn trước race, và điều này xử lý luôn rủi ro `uvicorn --reload` khởi động lại tick loop.
- **Sự thật về "6h sáng":** Nếu máy tắt, **toàn bộ hệ thống tắt** — cả Docker lẫn worker. Không phương án nào chạy được đúng giờ; vì vậy **chạy bù có giới hạn** là giải pháp duy nhất đúng, và nó bắt buộc phải có `next_run_at` bền vững trong Postgres.
- **Điểm nghẽn thật:** Worker chạy **tuần tự tuyệt đối**. Nhiều project cùng 6h sáng sẽ xếp hàng nối đuôi — cần `concurrency_policy=forbid` và rải giờ.
- **Chi phí thật không nằm ở hạ tầng** mà ở token và thời gian máy của các lần chạy pipeline tự động — nên phải **quét trước, tạo job sau**.

**Technical Recommendations:**

1. **Thêm bảng `schedules` trong Postgres** với `next_run_at` có index, `cron_expression` (unix-cron 5 trường), `timezone` (tên tz database), `misfire_policy` và `concurrency_policy` tường minh theo từng lịch.
2. **Đặt tick loop trong API container**, cạnh `_workflow_run_poll_loop`, dùng `croniter` (ghim version) để tính `next_run_at`. **Không dùng APScheduler.**
3. **Bảo vệ bằng UNIQUE `(schedule_id, fire_time)`** — một ràng buộc duy nhất khoá được cả ba rủi ro: tick trùng, reload giữa chừng, chạy bù sau khởi động lại.
4. **Triển khai theo lộ trình dry-run trước**: chạy tick ở chế độ chỉ ghi log ít nhất một chu kỳ ngày đêm, rồi bật thật cho một project, rồi mở rộng.
5. **Dùng Windows Task Scheduler đúng vai** — khởi động Docker Desktop và worker lúc boot, **không** làm scheduler chính.

---

## Table of Contents

1. [Giới thiệu và Phương pháp nghiên cứu](#1-giới-thiệu-và-phương-pháp-nghiên-cứu)
2. [Bối cảnh kỹ thuật và Phân tích kiến trúc](#2-bối-cảnh-kỹ-thuật-và-phân-tích-kiến-trúc)
3. [Phương án triển khai và Thực hành tốt](#3-phương-án-triển-khai-và-thực-hành-tốt)
4. [Technology Stack và Xu hướng](#4-technology-stack-và-xu-hướng)
5. [Tích hợp và Khả năng liên thông](#5-tích-hợp-và-khả-năng-liên-thông)
6. [Hiệu năng và Khả năng mở rộng](#6-hiệu-năng-và-khả-năng-mở-rộng)
7. [Bảo mật và Tuân thủ](#7-bảo-mật-và-tuân-thủ)
8. [Khuyến nghị kỹ thuật chiến lược](#8-khuyến-nghị-kỹ-thuật-chiến-lược)
9. [Lộ trình triển khai và Đánh giá rủi ro](#9-lộ-trình-triển-khai-và-đánh-giá-rủi-ro)
10. [Triển vọng và Cơ hội mở rộng](#10-triển-vọng-và-cơ-hội-mở-rộng)
11. [Phương pháp nghiên cứu và Xác minh nguồn](#11-phương-pháp-nghiên-cứu-và-xác-minh-nguồn)
12. [Phụ lục kỹ thuật](#12-phụ-lục-kỹ-thuật)

---

## 1. Giới thiệu và Phương pháp nghiên cứu

### Ý nghĩa kỹ thuật của nghiên cứu

Tài liệu mục ruỗng một cách thầm lặng. Mô tả vấn đề từ nghiên cứu thực tiễn rất sát với hoàn cảnh của `ai_team_clean`: *"Tài liệu phân rã vì code thay đổi nhanh hơn tốc độ cập nhật thủ công — chữ ký API tiến hoá, đội thêm tuỳ chọn cấu hình, mô tả hành vi lỗi thời, và khoảng cách giữa code với tài liệu lớn dần trong im lặng cho đến khi có người vấp phải một hướng dẫn sai."*

Điều này đặc biệt nghiêm trọng với một hệ thống mà **tài liệu chính là đầu vào điều khiển AI agent**. Trong `ai_team_clean`, `clients/{slug}/` giữ tài liệu và pipeline đọc chúng để sinh code — tài liệu lệch không chỉ gây hiểu nhầm cho người, mà **trực tiếp làm agent làm sai việc**. Một ca thực tế được ghi nhận: tài liệu onboarding hướng dẫn dùng một cách tiếp cận API, trong khi code đã chuyển sang phiên bản khác từ hai đời trước — **mọi kiểm tra tự động đều xanh** cho đến khi có bước đối chiếu tài liệu với hiện thực.

Giải pháp được ngành áp dụng chính là thứ bạn đang muốn xây: *"kiểm toán tài liệu kích hoạt theo lịch, chạy theo cron, mỗi lần quét toàn bộ bề mặt tài liệu và đề xuất chỉnh sửa cho mọi sai lệch phát hiện được."*

- _Technical Importance:_ Biến việc phát hiện lệch tài liệu từ **phản ứng thụ động** (ai đó tình cờ vấp phải) thành **giám sát chủ động** (hệ thống tự báo).
- _Business Impact:_ Với hệ thống agent tự động, tài liệu lệch tạo ra code sai — chi phí phát hiện muộn cao hơn nhiều so với chi phí quét định kỳ.

_Source: [zylos.ai — Documentation-Contract Drift Detection in Evolving Agent Systems](https://zylos.ai/research/2026-08-21-documentation-contract-drift-detection-agent-systems/), [agentpatterns.ai — Continuous Documentation as an Agent-Driven Practice](https://www.agentpatterns.ai/workflows/continuous-documentation/), [github.com/TommyE123/docker-autoheal#217 — scheduled AI documentation drift detection](https://github.com/TommyE123/docker-autoheal/issues/217)_

### Phương pháp nghiên cứu

- **Technical Scope:** Kiến trúc hệ thống, phương án triển khai, technology stack, pattern tích hợp, hiệu năng/khả năng mở rộng, bảo mật.
- **Data Sources:** Hai tuyến song song — (a) **khảo sát trực tiếp mã nguồn** `ai_team_clean` (models, routers, worker, docker-compose, Dockerfile, requirements), và (b) **tra cứu web hiện hành** trên tài liệu chính thức (APScheduler, Google Cloud Scheduler, Kubernetes, Microsoft Learn), bài phân tích thiết kế hệ thống, và issue/PR thực chiến.
- **Analysis Framework:** Mọi khuyến nghị phải đồng thời (1) có nguồn ngoài xác nhận và (2) tương thích với ràng buộc đã kiểm chứng trong mã nguồn. Khuyến nghị nào chỉ thoả một vế đều bị đánh dấu rõ.
- **Time Period:** Dữ liệu web hiện hành tính đến tháng 9/2026.
- **Technical Depth:** Đủ chi tiết để chuyển thẳng sang PRD và thiết kế bảng.

### Mục tiêu và Kết quả đạt được

**Mục tiêu ban đầu:**
1. Chọn engine scheduler · 2. Chọn nơi đặt scheduler · 3. Xử lý missed runs · 4. Timezone · 5. Chống trùng/chồng lịch · 6. Cơ chế phát hiện thay đổi tài liệu

**Kết quả:**

| # | Mục tiêu | Kết luận | Cơ sở |
|---|---|---|---|
| 1 | Engine | **`croniter` + tick loop tự viết**; loại APScheduler | Tránh dựng job store thứ hai chồng `run_jobs` |
| 2 | Vị trí | **API container** | Tiền lệ `_workflow_run_poll_loop`; giữ nguyên tắc worker-chỉ-stdlib |
| 3 | Missed runs | **`misfire_policy` theo từng lịch, catch-up có chặn trên** | Máy tắt thì cả hệ tắt; chạy bù là lựa chọn duy nhất khả thi |
| 4 | Timezone | **UTC trong DB + tên tz database, `zoneinfo`** | Python 3.12 có sẵn; tránh bẫy `utcnow()` |
| 5 | Trùng/chồng | **UNIQUE `(schedule_id, fire_time)` + `concurrency_policy=forbid`** | DB phải là trọng tài; worker tuần tự tuyệt đối |
| 6 | Phát hiện thay đổi | **`git diff` nếu có git, ngược lại snapshot `sha256`** | Quét theo lịch, không cần observer thời gian thực |

**Phát hiện ngoài dự kiến (không nằm trong mục tiêu ban đầu):**
- `worker.py` có **ràng buộc thiết kế thành văn** về việc không thêm dependency — làm thay đổi hẳn phương án "scheduler trong worker".
- API **đã** chạy background task — biến câu hỏi "có nên đặt ở API không" thành "đi theo pattern có sẵn".
- Kênh thông báo Telegram/Slack **đã tồn tại** qua `chat_router.notify_run()` — không cần xây mới.
- Hệ thống bị **chia đôi giữa container và host**, tạo ra ranh giới khả kiến quyết định ai quét được tài liệu nào.

---

## 2. Bối cảnh kỹ thuật và Phân tích kiến trúc

Chi tiết đầy đủ ở mục **Architectural Patterns and Design** phía trên. Tóm tắt kết luận:

- _Dominant Patterns:_ Phân rã 4 thành phần (schedule store / tick coordinator / execution queue / executor). Dự án đã có 2, thiếu 2.
- _Architectural Evolution:_ Xu hướng rời bỏ scheduler in-memory sang **database-backed durable scheduler** — vì chỉ có nguồn sự thật trên đĩa mới trả lời được "lịch nào phải chạy" sau khi tiến trình chết.
- _Architectural Trade-offs:_ Đánh đổi trung tâm là **đặt đồng hồ trong container (mất khả năng thấy `CODE_ROOT`, có rủi ro reload) hay trên host (phá nguyên tắc stdlib của worker)**. Nghiên cứu nghiêng về container, với rủi ro reload được vô hiệu hoá bằng ràng buộc UNIQUE.
- _Quality Attributes:_ Ưu tiên theo thứ tự — **đúng đắn** (không bắn trùng, không mất nhịp) > **khả quan sát** (log mọi quyết định) > hiệu năng (vốn không phải vấn đề ở quy mô này).

---

## 3. Phương án triển khai và Thực hành tốt

Chi tiết ở mục **Implementation Approaches and Technology Adoption**. Điểm cốt lõi:

- _Development Approaches:_ Gradual, không big bang. Dry-run trước khi bắn thật.
- _Code Organization:_ Sao chép khuôn có sẵn — router theo mẫu 17 router hiện tại, hook React theo `useMcp.ts`, component theo `ProjectMcp.tsx`, vòng nền theo `_workflow_run_poll_loop`.
- _Quality Assurance:_ **Tiêm đồng hồ, không `sleep`.** Test phải nhảy thẳng tới `next_run_at` mà hàm báo về, vì trên CI tải nặng hành vi đúng vẫn có thể fail ngẫu nhiên.
- _Deployment:_ Thêm `croniter` vào `requirements.txt` đòi `docker compose build api` (pip install nằm ở bước build).

---

## 4. Technology Stack và Xu hướng

Chi tiết ở mục **Technology Stack Analysis**. Tóm tắt phán quyết:

| Công nghệ | Phán quyết | Lý do một dòng |
|---|---|---|
| `croniter` (pallets-eco) | ✅ **Chọn** | Chỉ làm đúng việc cần: tính `next_run_at`, hỗ trợ `zoneinfo` |
| `zoneinfo` (stdlib 3.12) | ✅ **Chọn** | Có sẵn, không cần `pytz` |
| PostgreSQL 16 | ✅ **Dùng tiếp** | Đã có; `SKIP LOCKED` và advisory lock đủ thay Redis |
| APScheduler 3.x | ❌ Loại | Dựng job store + executor song song với `run_jobs` |
| APScheduler 4.0 | ❌ Loại | Như trên, cộng thêm phá tương thích job store |
| `schedule` | ❌ Loại | Không persistence, không chạy bù |
| Windows Task Scheduler | ⚠️ Bổ trợ | Chỉ để khởi động hệ thống lúc boot |
| Redis | ❌ Không cần | Postgres làm được việc tương đương |
| Celery / broker | ❌ Không cần | Vượt xa quy mô một máy đơn |

---

## 5. Tích hợp và Khả năng liên thông

Chi tiết ở mục **Integration Patterns Analysis**. Điểm quyết định:

- _API Design:_ `/api/schedules` CRUD gắn `project_id`, kèm endpoint **xem trước 5 lần chạy kế tiếp** để người dùng tự kiểm chứng biểu thức cron trước khi lưu.
- _Service Integration:_ Điểm nối duy nhất là `INSERT INTO run_jobs`. **`worker.py` không đổi một dòng.**
- _Data Integration:_ Đính `fire_time`/`scheduled_for` vào job để executor kiểm tra chéo đồng hồ của chính nó — khuyến nghị trực tiếp từ mô hình tham chiếu.
- _Integration Challenges:_ **Ranh giới khả kiến container/host** là thách thức tích hợp thật sự duy nhất và vẫn đang chờ bạn xác nhận vị trí tài liệu.

---

## 6. Hiệu năng và Khả năng mở rộng

- _Performance:_ Một truy vấn có index mỗi 30–60 giây. Không đáng kể.
- _Điểm nghẽn thật:_ `run_jobs.py` chặn claim khi còn job `running` → **tuần tự tuyệt đối**. Đây không phải lỗi mà là thiết kế có chủ đích, nhưng nó biến "nhiều lịch cùng giờ" thành hàng đợi nối đuôi.
- _Optimization:_ `concurrency_policy=forbid` + jitter + **quét trước tạo job sau**.
- _Capacity Planning:_ Chi phí cần dự trù không phải CPU/RAM mà là **token và thời gian máy** của N lần chạy pipeline mỗi ngày.
- _Auto-scaling:_ Không áp dụng và không nên theo đuổi ở quy mô này.

---

## 7. Bảo mật và Tuân thủ

- _Hiện trạng:_ API chỉ gắn `CORSMiddleware`, không có tầng xác thực. Scheduler **không làm thay đổi bề mặt tấn công**.
- _Rủi ro mới thật sự:_ lịch là **thực thi tự động không người giám sát**. Cần audit trail (`created_by`, `updated_at`, `run_jobs.source='schedule'`, `schedule_id`).
- _Nguyên tắc đặc quyền tối thiểu:_ scheduler chỉ được chèn `run_jobs` — mọi tác dụng phụ đi qua worker, nơi đã có timeout và log.
- _Ràng buộc an toàn đặc thù cho pipeline AI (khuyến nghị quan trọng):_ thực hành tốt được ghi nhận là **"đầu ra an toàn": giới hạn agent ghi vào PR có thể review, tiêu đề gắn nhãn tiền tố — không bao giờ commit tự động**, và **không để agent tự đánh giá bản cập nhật tài liệu của chính nó là đúng**. Nếu lịch quét sau này tiến tới chỗ *tự sửa* tài liệu, đây là lằn ranh phải giữ.
- _Regulatory Compliance:_ **Không áp dụng** — hệ thống nội bộ, không xử lý dữ liệu chịu quản lý.

_Source: [agentpatterns.ai — Continuous Documentation](https://www.agentpatterns.ai/workflows/continuous-documentation/), [zylos.ai — Documentation-Contract Drift Detection](https://zylos.ai/research/2026-08-21-documentation-contract-drift-detection-agent-systems/)_

---

## 8. Khuyến nghị kỹ thuật chiến lược

- _Architecture Recommendations:_ Bổ sung **schedule store + tick coordinator**; giữ nguyên queue và executor. Không nhập khẩu framework làm lại việc đã có.
- _Technology Selection:_ `croniter` + `zoneinfo` + Postgres. Một dependency mới, một bảng mới, một vòng lặp mới.
- _Implementation Strategy:_ Dry-run → một project → toàn bộ. Không bỏ qua giai đoạn dry-run, vì đây là loại code chạy lúc không ai nhìn.
- _Điểm khác biệt đáng theo đuổi:_ **quét trước, tạo job sau** — nhiều hệ thống lịch chỉ đơn thuần bắn job theo giờ; việc kiểm tra "có thay đổi thật không" trước khi đánh thức pipeline vừa tiết kiệm token vừa giảm nhiễu, và rất hợp với bản chất bài toán của bạn.
- _Competitive Technical Advantage:_ **Không áp dụng** — đây là công cụ nội bộ, không phải sản phẩm cạnh tranh thị trường.

---

## 9. Lộ trình triển khai và Đánh giá rủi ro

Lộ trình 6 giai đoạn (17 bước) và bảng 8 rủi ro đã trình bày đầy đủ ở mục **Implementation Roadmap** và **Risk Assessment and Mitigation** phía trên.

Ba rủi ro cần để mắt nhất:
1. **Double-fire do `--reload`** → khoá bằng UNIQUE constraint (bắt buộc, không thương lượng)
2. **Máy tắt lúc 6h** → `misfire_policy` tường minh + catch-up có chặn trên + WTS khởi động hệ thống lúc boot
3. **Dồn ứ hàng đợi** → `concurrency_policy=forbid` + jitter

---

## 10. Triển vọng và Cơ hội mở rộng

- _Near-term (ngay sau khi xong):_ `job_kind` mở đường cho các loại lịch khác ngoài `scan_docs` — ví dụ chạy test định kỳ, dọn log, tổng hợp báo cáo tuần.
- _Medium-term:_ Nếu số project tăng, điểm cần xem lại đầu tiên là **worker tuần tự** — có thể cho phép chạy song song theo project thay vì toàn cục.
- _Nếu API chuyển sang nhiều uvicorn worker:_ bổ sung **Postgres advisory lock** để bầu chọn leader — ưu điểm là **tự nhả khi kết nối đóng, không cần heartbeat hay TTL**.
- _Innovation Opportunities:_ Hướng "kiểm toán tài liệu bằng agent rồi mở PR để người review" là bước tiến tự nhiên sau khi cơ chế lịch đã ổn định — nhưng chỉ nên làm sau khi có audit trail và dry-run đã chứng minh độ tin cậy.

---

## 11. Phương pháp nghiên cứu và Xác minh nguồn

### Truy vấn tìm kiếm đã thực hiện

1. APScheduler 4.0 vs 3.x persistent job store SQLAlchemy misfire_grace_time coalesce 2026
2. Python cron scheduling library comparison APScheduler croniter schedule 2026
3. FastAPI background scheduler multiple workers duplicate job execution problem
4. Windows Task Scheduler missed run "start when available" wake computer vs in-process scheduler catch-up
5. detect file changes directory python hash snapshot vs git diff document change detection scheduled scan
6. idempotency key pattern scheduled job enqueue exactly-once dedup database unique constraint
7. PostgreSQL advisory lock leader election single scheduler instance prevent duplicate cron fire
8. REST API design CRUD cron schedule resource cron expression timezone field best practice
9. missed scheduled runs after downtime catch-up vs skip policy scheduler design misfire
10. separate scheduler clock from executor job queue architecture pattern database polling next_run_at
11. database-backed cron scheduler design pattern durable schedule table tick loop vs in-memory
12. croniter python get_next timezone aware zoneinfo DST pitfalls maintained 2026
13. testing scheduled jobs unit test cron next run time freezegun deterministic clock injection
14. rolling out automated scheduled jobs safely dry-run mode feature flag observability logging
15. documentation drift detection automated scheduled scan AI agent pipeline stale docs problem

### Nguồn từ mã nguồn (kiểm chứng trực tiếp)

`dashboard/api/models.py` · `dashboard/api/database.py` · `dashboard/api/main.py` · `dashboard/api/routers/run_jobs.py` · `dashboard/api/chat_router.py` · `dashboard/api/requirements.txt` · `dashboard/api/Dockerfile` · `dashboard/docker-compose.yml` · `worker.py`

### Đảm bảo chất lượng

- _Xác minh nguồn:_ Mọi khẳng định về hành vi hệ thống hiện tại đều **đọc trực tiếp từ mã nguồn**, có dẫn file và dòng. Mọi khẳng định về thực hành ngành đều có ít nhất một nguồn web, phần lớn có nhiều nguồn độc lập đồng thuận.
- _Mức độ tin cậy:_
  - **CAO** — kiến trúc, pattern idempotency, hiện trạng dự án, chuẩn trường cron/timezone, cơ chế Windows Task Scheduler, bẫy `utcnow()`/`timedelta`.
  - **TRUNG BÌNH** — độ chín thực chiến của APScheduler 4.0; kết quả DST của croniter 6.2.4 (một báo cáo thực chiến, nên tự kiểm chứng); các tham số cụ thể (chu kỳ tick 30–60s, cửa sổ catch-up 24h) là **khuyến nghị khởi điểm**, không phải con số được nguồn nào ấn định.
- _Giới hạn nghiên cứu (nói rõ):_
  1. **Vị trí tài liệu cần quét chưa được xác nhận** — `clients/` hay `CODE_ROOT`. Đây là ẩn số lớn nhất còn lại, quyết định API tự quét được hay phải giao cho worker.
  2. **Hành vi khi phát hiện thay đổi chưa được chốt** — tạo ProjectTask, báo Slack, hay chạy nguyên pipeline.
  3. **Số lượng project thực tế chưa biết** — ảnh hưởng mức độ nghiêm trọng của vấn đề dồn ứ hàng đợi.
  4. Thiết kế cột bảng `schedules` là **tổng hợp của người nghiên cứu**, cần review khi làm PRD.
  5. Chưa khảo sát cách dự án tạo bảng mới (chưa thấy Alembic) — cần chốt để nhất quán.

---

## 12. Phụ lục kỹ thuật

### Bảng quyết định nhanh

| Câu hỏi | Trả lời | Mức tin cậy |
|---|---|---|
| Dùng framework scheduler nào? | `croniter` + tick loop tự viết | CAO |
| Đặt ở đâu? | API container, cạnh `_workflow_run_poll_loop` | CAO |
| Máy tắt lúc 6h thì sao? | Chạy bù tối đa 1 lần trong cửa sổ 24h, policy đặt theo từng lịch | CAO |
| Lưu giờ thế nào? | UTC trong DB + tên tz database riêng | CAO |
| Chống bắn trùng? | UNIQUE `(schedule_id, fire_time)` + `ON CONFLICT DO NOTHING` | CAO |
| Nhiều project cùng 6h? | `concurrency_policy=forbid` + jitter | CAO |
| Phát hiện thay đổi tài liệu? | `git diff` nếu có git; ngược lại snapshot `sha256` | TRUNG BÌNH-CAO |
| Cần Redis không? | Không | CAO |
| Sửa `worker.py` không? | **Không** | CAO |

### Tài nguyên tham khảo tiếp

- **Chuẩn cron & timezone:** [Google Cloud Scheduler](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules) · [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- **Thư viện:** [croniter (pallets-eco)](https://github.com/pallets-eco/croniter) · [APScheduler](https://github.com/agronholm/apscheduler) · [db-scheduler (tham khảo thiết kế bảng)](https://github.com/kagkarlsson/db-scheduler)
- **Thiết kế scheduler:** [bunqueue — Cron Scheduler architecture](https://bunqueue.dev/architecture/cron-scheduler) · [DZone — Design a Distributed Job Scheduler](https://dzone.com/articles/design-a-distributed-job-scheduler)
- **Idempotency:** [OneUptime](https://oneuptime.com/blog/post/2026-07-21-deduplicate-idempotency-unique-constraint/view) · [AlgoMaster](https://algomaster.io/learn/system-design/idempotency)
- **Postgres coordination:** [Leader Election with PostgreSQL](https://tedkim.dev/posts/leader-election-with-postgresql/) · [Advisory Locks for Distributed Cron](https://dev.to/mukesh_13/postgres-advisory-locks-for-distributed-cron-killing-duplicate-job-runs-without-a-redis-dependency-1bfl)
- **Kiểm thử:** [Freezegun guide](https://betterstack.com/community/guides/testing/freezegun-unit-testing/) · [Strapi PR — deterministic cron tests](https://github.com/strapi/strapi/pull/27659)
- **Windows:** [Task Properties](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2008-R2-and-2008/cc775003) · [Missed night tasks](https://learn.microsoft.com/en-us/answers/questions/362393/task-scheduler-misses-all-tasks-scheduled-to-run-a)
- **Doc drift:** [Continuous Documentation](https://www.agentpatterns.ai/workflows/continuous-documentation/) · [Documentation-Contract Drift Detection](https://zylos.ai/research/2026-08-21-documentation-contract-drift-detection-agent-systems/)

---

## Kết luận nghiên cứu

### Tóm tắt phát hiện chính

Bài toán này nhỏ hơn vẻ ngoài của nó, nhưng chỉ khi được đặt đúng chỗ. `ai_team_clean` đã sở hữu một job queue hoàn chỉnh (`run_jobs`) và một executor đáng tin (`worker.py`); thứ còn thiếu là một bảng lịch bền vững và một vòng lặp đọc nó. Phản xạ thông thường — cài APScheduler — sẽ dựng song song một hệ thống thứ hai làm đúng việc đã có, và đó là cái bẫy kiến trúc lớn nhất trong bài toán này.

Ba ràng buộc từ chính mã nguồn đã định hình toàn bộ kết luận: `worker.py` cam kết không thêm dependency; API đã là nhà của các tiến trình nền; và hệ thống bị chia đôi giữa container với host, tạo ra ranh giới khả kiến mà mọi thiết kế phải tôn trọng.

### Đánh giá tác động

- **Phạm vi thay đổi:** một bảng mới, một router mới, một vòng lặp mới, một dependency mới, một component UI mới. **Không sửa `worker.py`.**
- **Rủi ro tổng thể:** **Thấp đến trung bình** — với điều kiện có UNIQUE constraint và giai đoạn dry-run. Bỏ qua một trong hai thì rủi ro tăng đáng kể.
- **Giá trị:** chuyển việc phát hiện tài liệu lệch từ thụ động sang chủ động, trong một hệ thống mà tài liệu là đầu vào điều khiển AI agent.

### Bước tiếp theo đề xuất

1. **Trả lời ba câu hỏi còn treo** (vị trí tài liệu · hành vi khi phát hiện thay đổi · số project thực tế) — ba câu này quyết định phạm vi PRD.
2. **Chuyển sang PRD** với John (`bmad-agent-pm` → `bmad-create-prd`) để chốt phạm vi và yêu cầu nghiệp vụ.
3. **Hoặc sang kiến trúc** với Winston (`bmad-agent-architect` → `bmad-create-architecture`) nếu muốn chốt thiết kế bảng và hợp đồng API trước.
4. **Rồi mới** `bmad-create-epics-and-stories` để cắt thành story theo lộ trình 6 giai đoạn đã vạch.

---

**Technical Research Completion Date:** 2026-09-23
**Research Period:** Phân tích kỹ thuật toàn diện, dữ liệu hiện hành tháng 9/2026
**Source Verification:** Mọi khẳng định về hệ thống hiện tại dẫn từ mã nguồn; mọi khẳng định về thực hành ngành dẫn nguồn web
**Technical Confidence Level:** CAO cho kết luận kiến trúc và pattern; TRUNG BÌNH cho tham số vận hành cụ thể và ba ẩn số còn treo

_Tài liệu này là tham chiếu kỹ thuật cho việc bổ sung scheduled task theo dự án vào `ai_team_clean`, và là đầu vào trực tiếp cho bước PRD hoặc thiết kế kiến trúc tiếp theo._
