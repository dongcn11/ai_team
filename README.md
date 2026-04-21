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

## Setup

### 1. Yêu cầu hệ thống

- Python 3.11+
- Claude Code CLI (đã cài và đăng nhập)
- OpenCode CLI

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
