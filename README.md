# AI Team Orchestrator

Hệ thống 7 AI agents làm việc như một team dev thật — từ đọc PRD đến viết code hoàn chỉnh, có Slack integration để trao đổi khi gặp vấn đề.

## Kiến trúc

```
PRD (prd.md)
    │
    ▼
📋 PM Agent          →  docs/user_stories.md
                        docs/acceptance.md
    │
    ▼
🏃 Scrum Master      →  docs/backlog.md
                        docs/sprint_plan.md
    │
    ▼
🧠 Analyst           →  docs/api_contract.md
                        docs/data_models.md
                        docs/be1_task.md  docs/be2_task.md
                        docs/fe1_task.md  docs/fe2_task.md
    │
    ├──────────────────────────────┐
    ▼                              ▼
⚙️  BE Agent 1        ⚙️  BE Agent 2    (song song)
    │                              │
    └──────────┬───────────────────┘
               ▼
    ┌──────────────────────────────┐
    ▼                              ▼
🖥️  FE Agent 1        🖥️  FE Agent 2    (song song)
```

Mỗi agent task có 1 **Slack thread** riêng — agent tự báo cáo tiến độ và raise issue khi tài liệu có vấn đề.

## Cấu trúc project

```
ai-team-orchestrator/
├── main.py                    ← Entry point
├── prd.md                     ← PRD của bạn (sửa file này)
├── requirements.txt
├── config/
│   └── settings.toml          ← Tất cả config (model, Slack, output)
├── ai_team/
│   ├── __init__.py
│   ├── config.py              ← Config loader
│   ├── orchestrator.py        ← Logic điều phối chính
│   ├── runner.py              ← Chạy Claude Code / OpenCode subprocess
│   ├── task_manager.py        ← Theo dõi status → tasks.json
│   └── slack_bridge.py        ← Giao tiếp Slack API
└── output/                    ← Project được tạo ra (auto)
    ├── docs/                  ← Tài liệu từ PM/Scrum/Analyst
    ├── backend/               ← Code từ BE agents
    ├── frontend/              ← Code từ FE agents
    └── tasks.json             ← Status 7 agents real-time
```

## Skills — quy ước nghề, dùng chung cho cả 2 làn

`skills/` là kho quy ước mà agent phải đọc trước khi làm. **Một skill = một
thư mục có `SKILL.md` mở đầu bằng frontmatter `name` + `description`**, bên cạnh
là mọi thứ skill cần: script, test, mẫu, thư mục con — đúng định dạng skill của
Claude Code và BMAD, nên skill viết cho Claude bê thẳng vào đây được.

```
skills/
├── shared/                    ← mọi vai trò đều đọc
│   └── code_quality.md        ← skill 1 file (dạng cũ, vẫn chạy)
├── be/                        ← "cụm" skill = thư mục vai trò
│   └── screen-spec/           ← skill thư mục
│       ├── SKILL.md           ← frontmatter + hướng dẫn
│       ├── check_closure.py   ← script skill bảo agent chạy
│       ├── make_qa.py
│       └── templates/         ← thư mục con cũng được
└── fe/ · pm/ · scrum/ · analyst/ · leader/
```

Quản lý trên dashboard ở tab **Skills**: tạo/sửa/xoá/nhân bản, tải script lên,
sửa từng file, đổi cụm, và **nhập skill có sẵn** — chọn nguyên thư mục
`.claude/skills/<tên>` hoặc file `.zip`, SKILL.md + script + thư mục con vào hết
(rác kiểu `__pycache__`, `.pyc` bị bỏ). Skill 1 file cũ bấm *Chuyển sang thư mục*
là chứa được script.

Nguồn sự thật là file trên đĩa (không phải DB) nên `git diff` vẫn đọc ra và sửa
bằng editor vẫn được.

Skill quá dài thì **không** bị nhồi vào file task: bước chỉ nhận tên, mô tả,
đường dẫn `SKILL.md` và danh sách script (chạy với cwd = gốc repo) — agent tự mở
đọc khi cần, đúng cách skill của Claude hoạt động.

Skill được dùng ở cả hai làn:

| Làn | Cách nhận skill |
|-----|-----------------|
| Pipeline (`python main.py`) | Vai trò nào đọc cụm nào — xem `ai_team/skill_loader.py`, nội dung nhét thẳng vào prompt agent |
| Workflow (dashboard) | Mỗi node tự chọn: **cả cụm** (`be`) và/hoặc **từng skill lẻ** (`be/auth_jwt`) — một node chọn bao nhiêu skill cũng được. Node chọn agent thì tự nhận cụm của vai trò đó. Nội dung nhúng vào file task của bước |

> Sửa skill trên dashboard cần `skills/` ghi được: mount trong
> `dashboard/docker-compose.yml` phải là `../skills:/skills` (không `:ro`).

## ⚠️ Chính sách: pipeline không dùng Claude Code

Pipeline này chạy nền qua `worker.py`, nhiều project trong hàng đợi, agent song
song, không ai giám sát. **Không được dùng subscription Claude cho nó** — đó là
truy cập tự động bằng account cá nhân, và sẽ bị khoá account.

Hệ thống tách 2 làn:

| Làn | Dùng gì | Ai điều khiển |
|-----|---------|---------------|
| **A — Automation** (`worker.py`, dashboard, `clients/`) | OpenCode / model local | Hàng đợi, chạy nền |
| **B — Claude Code** | Subscription của bạn | Bạn, gõ `claude` tay trong terminal |

`tool = "claude"` bị chặn cứng ở 3 chỗ: [config load](ai_team/config.py), [runner](ai_team/runner.py),
và [API tạo project](dashboard/api/routers/projects.py). Đừng gỡ chốt để "chạy nhanh một lần".

Tuyệt đối không: nhiều account, xoay vòng account, copy OAuth token trong
`~/.claude/.credentials.json` lên server, đổi IP qua proxy. Những việc đó biến
khoá tạm thành khoá vĩnh viễn.

### Ngoại lệ hẹp: workflow bật "Tự chạy (Claude headless)"

Workflow của dashboard có công tắc `auto_run` (mặc định **tắt**). Bật lên thì
mỗi bước được xếp vào hàng đợi [`workflow_step_jobs`](dashboard/api/routers/workflow_jobs.py)
và `worker.py` chạy `claude -p "<prompt>"` cho **1 bước một lúc**.

Đây vẫn là làn B chứ không phải làn A, vì 3 giới hạn được giữ nguyên:

- **bạn tự bật** cho từng workflow, không có mặc định bật;
- chạy trên **máy của chính bạn**, bằng phiên đăng nhập của bạn (`worker.py`
  không dockerize, không đọc token đi đâu);
- **tuần tự 1 bước/lần** — `/claim` không trả job mới khi còn job đang chạy —
  và log hiện ngay trong terminal worker để bạn giám sát.

Không dùng `--dangerously-skip-permissions`; mặc định là
`--permission-mode acceptEdits`, đổi được qua biến môi trường `CLAUDE_ARGS`.
Đừng biến công tắc này thành "chạy nền nhiều project song song" — lúc đó nó
đúng là cái mà chính sách trên cấm.

## Setup

### 1. Yêu cầu hệ thống

- Python 3.11+
- OpenCode CLI (pipeline chỉ dùng cái này)
- Claude Code CLI — tùy chọn, chỉ để bạn dùng tay ngoài pipeline

```powershell
# Cài OpenCode (Windows)
scoop install opencode
# hoặc
choco install opencode

# Đăng nhập Claude Pro account cho OpenCode
opencode auth login
```

### 2. Cài Ollama (cho FE agents — free)

Tải tại https://ollama.com/download/windows

```powershell
ollama pull qwen2.5-coder:7b
```

### 3. Cấu hình

Sửa `config/settings.toml`:

```toml
[agents]
be1_model = "anthropic/claude-sonnet-4-5"  # hoặc model khác
be2_model = "google/gemini-2.0-flash"
fe1_model = "ollama/qwen2.5-coder:7b"
```

### 4. Chạy

```powershell
# Dùng prd.md mặc định
python main.py

# Hoặc chỉ định file PRD
python main.py --prd ./my_product.md

# Hoặc chỉ định output directory
python main.py --prd ./my_product.md --output ./my_project
```

## Slack Setup (tùy chọn)

Không có Slack vẫn chạy được — chỉ log ra terminal.

1. Vào https://api.slack.com/apps → Create New App
2. Thêm Bot Token Scopes: `chat:write`, `chat:write.public`, `channels:read`
3. Install to Workspace → copy **Bot OAuth Token** (`xoxb-...`)
4. Invite bot: trong Slack gõ `/invite @YourBotName` trong `#ai-team`
5. Điền token vào `config/settings.toml`:

```toml
[slack]
bot_token = "xoxb-your-actual-token"
channel   = "#ai-team"
```

## Thay đổi model

Sửa `config/settings.toml` — không cần sửa code:

```toml
[agents]
# Dùng Gemini cho tất cả coding agents (free tier)
be1_model = "google/gemini-2.0-flash"
be2_model = "google/gemini-2.0-flash"
fe1_model = "google/gemini-2.0-flash"
fe2_model = "ollama/qwen2.5-coder:7b"
```

Xem danh sách model:
```powershell
opencode models
```

## Output

Sau khi chạy xong, `output/` chứa:

```
output/
├── docs/
│   ├── user_stories.md     ← PM Agent
│   ├── acceptance.md       ← PM Agent
│   ├── backlog.md          ← Scrum Master
│   ├── sprint_plan.md      ← Scrum Master
│   ├── api_contract.md     ← Analyst
│   ├── data_models.md      ← Analyst
│   ├── be1_task.md         ← Analyst → BE1 đọc
│   ├── be2_task.md         ← Analyst → BE2 đọc
│   ├── fe1_task.md         ← Analyst → FE1 đọc
│   └── fe2_task.md         ← Analyst → FE2 đọc
├── backend/                ← BE1 + BE2 viết
├── frontend/               ← FE1 + FE2 viết
└── tasks.json              ← Status real-time
```
