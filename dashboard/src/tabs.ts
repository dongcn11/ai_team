// Các màn hình (tab) của dashboard — khoá ở đây trùng với auth.TABS bên API,
// là đơn vị phân quyền của tài khoản. "accounts" chỉ admin thấy, không phân quyền.
export type Tab = "dashboard" | "pipeline" | "projects" | "agents" | "skills" | "workflows"
  | "runs" | "bots" | "api" | "logs" | "settings" | "accounts";

export const TAB_INFO: { key: Tab; label: string; title?: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "pipeline",  label: "Pipeline",  title: "Lần chạy pipeline main.py hiện tại + lịch sử" },
  { key: "projects",  label: "Projects" },
  { key: "agents",    label: "Agents" },
  { key: "skills",    label: "Skills",    title: "Kho skill (SKILL.md + frontmatter) — node workflow và pipeline cùng đọc" },
  { key: "workflows", label: "Workflows" },
  { key: "runs",      label: "Lần chạy",  title: "Màn hình chạy — lệnh cần chạy, file task và tiến độ từng bước" },
  { key: "bots",      label: "Bots",      title: "Bot Telegram/Slack — nhận câu hỏi của agent và chạy workflow từ điện thoại" },
  { key: "api",       label: "API",       title: "API chuẩn OpenAI cho hệ thống khác dùng AI bên này — Claude, Grok, Ollama…" },
  { key: "logs",      label: "Logs" },
  { key: "settings",  label: "Settings" },
  { key: "accounts",  label: "Tài khoản", title: "Quản lý tài khoản đăng nhập và quyền vào từng màn hình" },
];
