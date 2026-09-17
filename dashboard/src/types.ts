export type TaskStatus = "pending" | "running" | "done" | "failed";
export type RunStatus  = "running" | "done" | "failed";
export type Severity   = "high" | "medium" | "low";

export interface Task {
  id: number;
  run_id: number;
  role: string;
  description: string | null;
  status: TaskStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  error: string | null;
}

export interface Issue {
  id: number;
  run_id: number;
  role: string;
  severity: Severity;
  description: string | null;
  suggestion: string | null;
  created_at: string;
}

export interface Run {
  id: number;
  project_id: number | null;
  client: string | null;
  profile: string | null;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  tasks: Task[];
  issues: Issue[];
}

export interface RunSummary {
  id: number;
  project_id: number | null;
  client: string | null;
  profile: string | null;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  total_tasks: number;
  done_tasks: number;
  failed_tasks: number;
}

// ── Projects & Agents ──

export type AgentStatus = "available" | "busy" | "offline";

export interface AgentFS {
  key: string;
  name: string;
  role: string;
  tool: string;
  model: string;
  description: string | null;
}

/** Agent đọc từ config/settings.toml — nguồn sự thật của pipeline (làn A) */
export interface ConfigAgent {
  key: string;
  name: string;
  role: string;
  model: string;
  tool: string;
  status: string;
  description: string;
  /** Skill mặc định của vai trò (chưa gồm `shared`) — node chọn agent thì nhận luôn */
  skill_dirs: string[];
}

/** 1 skill trong kho `skills/` — xem dashboard/api/skills_store.py.
 *  Cùng quy ước với skill của Claude Code / BMAD: SKILL.md + frontmatter. */
export interface Skill {
  /** "<cụm>/<slug>", vd "be/auth_jwt" — cũng là thứ node workflow lưu lại */
  id: string;
  category: string;
  slug: string;
  name: string;
  description: string;
  tags: string[];
  /** folder = SKILL.md (kèm được file phụ) · file = 1 file .md kiểu cũ */
  format: "folder" | "file";
  path: string;
  chars: number;
  updated_at: string | null;
  has_frontmatter: boolean;
  /** file phụ trong skill thư mục: script, mẫu, thư mục con… */
  resources: SkillResource[];
}

/** 1 file đi kèm skill. Skill thật hay có script mà chính SKILL.md bảo agent chạy. */
export interface SkillResource {
  /** đường dẫn tương đối trong thư mục skill (có thể lồng: templates/story.md) */
  path: string;
  size: number;
  /** false = nhị phân, chỉ tải về được chứ không sửa trên web */
  is_text: boolean;
  kind: "doc" | "script" | "data" | "binary";
}

export interface SkillDetail extends Skill {
  /** phần thân, đã bỏ frontmatter */
  body: string;
  /** nguyên văn file */
  content: string;
}

export interface SkillCategory {
  name: string;
  count: number;
}

/** Profile trong profiles.yaml — quyết định agent nào được bật */
export interface Profile {
  key: string;
  label: string;
  agents: string[];
}

/** @deprecated bảng `agents` trong DB — bản sao chép tay, pipeline không đọc.
 *  Chỉ còn dùng cho ProjectTask.assigned_agent_id. Xem components/Agents.tsx. */
export interface AgentSimple {
  id: number;
  name: string;
  role: string;
  model: string;
  status: AgentStatus;
  description: string | null;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  profile?: string;
  tech_stack: { backend?: string; frontend?: string; server_side?: string };
  agents: AgentFS[];
  agent_count: number;
  output_dir: string;
  /** "split" = tách backend/frontend, "mono" = dự án gộp 1 thư mục (Laravel Blade…) */
  code_layout?: "split" | "mono";
  /** Thư mục riêng cho từng vùng; trống = <output_dir>/backend, <output_dir>/frontend */
  backend_dir?: string;
  frontend_dir?: string;
  /** Thư mục tài liệu KHÁCH CUNG CẤP. Trống = clients/<slug>/docs */
  client_docs_dir?: string;
  /** settings.toml sai cú pháp TOML — project vẫn hiện nhưng không đọc được cấu hình */
  config_error?: string | null;
}

export interface ProjectSummary {
  id: string;
  name: string;
  tech_stack: { backend?: string; frontend?: string; server_side?: string };
  agent_count: number;
  /** settings.toml sai cú pháp TOML — project vẫn hiện để còn biết mà sửa */
  config_error?: string | null;
}

export interface AgentDetail {
  id: number;
  name: string;
  role: string;
  model: string;
  status: AgentStatus;
  description: string | null;
  created_at: string;
  projects: ProjectSummary[];
}

// ── Project Tasks ──

export type TaskPriority = "high" | "medium" | "low";
export type TaskDocType   = "note" | "spec" | "log" | "result";

export interface TaskDocument {
  id: number;
  task_id: number;
  title: string;
  content: string;
  doc_type: TaskDocType;
  created_at: string;
  updated_at: string;
}

export interface ProjectTask {
  id: number;
  project_id: number;
  assigned_agent_id: number | null;
  name: string;
  description: string | null;
  status: string;       // todo / in_progress / review / done
  priority: TaskPriority;
  progress: number;     // 0-100
  due_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  agent: AgentSimple | null;
  documents: TaskDocument[];
  comments: TaskComment[];
  subtasks: SubTask[];
}

export interface TaskComment {
  id: number;
  task_id: number;
  author: string;
  content: string;
  created_at: string;
}

export interface SubTask {
  id: number;
  task_id: number;
  name: string;
  status: string;       // todo / done
  assigned_agent_id: number | null;
  created_at: string;
  agent: AgentSimple | null;
}

// ── Workflows ──

export type WorkflowNodeType =
  | "trigger.slack_mention"
  | "trigger.chat_message"
  | "action.generate_code"
  | "action.create_mr"
  | "action.code_review"
  | "action.custom"
  | "logic.condition";

/** Trigger từ app chat (hiện có Telegram; Slack dùng SlackMentionData cũ). */
export interface ChatMessageData {
  label: string;
  platform: "telegram";
  /** Chat id / tên. Bỏ trống = nhận mọi chat được phép của nền tảng đó. */
  chat: string;
  keyword?: string;
}

export interface SlackMentionData {
  label: string;
  channel: string;
  keyword?: string;
}

export interface GenerateCodeData {
  label: string;
  /** Cụm skill = thư mục vai trò (`skills/be/`) — áp trọn skill nằm trong đó */
  skill_dirs: string[];
  /** Skill lẻ, id `<cụm>/<slug>` (vd "be/auth_jwt"). 1 node chọn được nhiều skill. */
  skill_ids?: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
  /** Bậc model khi bước chạy bằng Claude: "haiku" | "sonnet" | "opus".
   *  Bỏ trống = theo mặc định của CLI trên máy chạy worker. */
  claude_model?: string | null;
}

export interface CreateMrData {
  label: string;
  provider: "gitlab" | "github";
  repo: string;
  base_branch: string;
  title_template: string;
  description_template: string;
  /** Bậc model khi bước chạy bằng Claude: "haiku" | "sonnet" | "opus". */
  claude_model?: string | null;
}

export interface CodeReviewData {
  label: string;
  /** Cụm skill = thư mục vai trò (`skills/be/`) — áp trọn skill nằm trong đó */
  skill_dirs: string[];
  /** Skill lẻ, id `<cụm>/<slug>` (vd "be/auth_jwt"). 1 node chọn được nhiều skill. */
  skill_ids?: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
  /** Bậc model khi bước chạy bằng Claude: "haiku" | "sonnet" | "opus".
   *  Bỏ trống = theo mặc định của CLI trên máy chạy worker. */
  claude_model?: string | null;
}

export interface CustomActionData {
  label: string;
  /** Cụm skill = thư mục vai trò (`skills/be/`) — áp trọn skill nằm trong đó */
  skill_dirs: string[];
  /** Skill lẻ, id `<cụm>/<slug>` (vd "be/auth_jwt"). 1 node chọn được nhiều skill. */
  skill_ids?: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
  /** Bậc model khi bước chạy bằng Claude: "haiku" | "sonnet" | "opus".
   *  Bỏ trống = theo mặc định của CLI trên máy chạy worker. */
  claude_model?: string | null;
}

/** Cách quyết định nhánh của node điều kiện */
export type ConditionMode = "manual" | "auto";
/** Phép so sánh khi mode = auto (áp lên phần '## Kết quả' của các node trước) */
export type ConditionOperator = "contains" | "not_contains" | "equals" | "regex" | "is_empty";

export interface ConditionData {
  label: string;
  mode: ConditionMode;
  /** Mô tả điều kiện cho người/agent đọc khi mode = manual */
  expression: string;
  operator: ConditionOperator;
  value: string;
  true_label: string;
  false_label: string;
  /** Bậc model khi bước chạy bằng Claude: "haiku" | "sonnet" | "opus". */
  claude_model?: string | null;
}

export type WorkflowNodeData =
  | SlackMentionData | ChatMessageData | GenerateCodeData | CreateMrData | CodeReviewData | CustomActionData | ConditionData;

/** 1 bot chat (Telegram/Slack) và phạm vi nó phụ trách. Xem models.ChatBot. */
export interface ChatBot {
  id: number;
  platform: string;              // telegram | slack
  name: string;
  chats: string;
  /** null = mọi dự án */
  client_folder: string | null;
  /** [] = mọi workflow của dự án đó */
  workflow_ids: number[];
  enabled: boolean;
  created_at?: string | null;
  token_hint: string;
  has_token: boolean;
  has_secret: boolean;
  has_app_token: boolean;
  /** Slack: "socket" = WebSocket đi ra (không cần URL công khai) · "webhook" = Slack gọi vào */
  mode: string | null;
  scope_label: string;
  /** chỉ Slack — Request URL riêng của bot này */
  request_path: string | null;
  running: boolean;
  me: string | null;
  last_error: string | null;
  /** workflow_ids trỏ tới workflow đã bị xoá */
  stale_workflow_ids: number[];
}

/** 1 bậc model cho node chạy bằng Claude (GET /api/workflows/claude-models) */
export interface ClaudeModelOption {
  value: string;
  label: string;
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  position: { x: number; y: number };
  data: WorkflowNodeData;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  /** "true" | "false" khi source là node điều kiện */
  sourceHandle?: string | null;
  targetHandle?: string | null;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

/** Tóm tắt lần chạy workflow gần nhất của 1 task — hiển thị trên hàng task */
export interface TaskRunSummary {
  id: number;
  status: WorkflowRunStatus;
  total_steps: number;
  done_steps: number;
  created_at: string | null;
}

export interface Workflow {
  id: number;
  project_id: number | null;
  client_folder: string | null;
  name: string;
  description: string | null;
  definition: WorkflowDefinition;
  is_active: boolean;
  /** Bật = mỗi bước được worker trên máy bạn tự chạy bằng `claude -p` */
  auto_run: boolean;
  created_at: string;
  updated_at: string;
}

export type WorkflowRunStatus = "running" | "done" | "failed" | "cancelled";
/** "blocked" = agent đã hỏi và đang chờ dev xác nhận trên web (xem AgentQuestions) */
export type NodeRunStatus = "pending" | "running" | "ok" | "error" | "skipped" | "blocked";

export interface WorkflowRunLogEntry {
  node_id: string;
  message: string;
  ts: string;
}

export interface WorkflowRun {
  id: number;
  workflow_id: number;
  /** Task (feature) đã kích hoạt run này — null nếu chạy tay trong editor */
  task_id: number | null;
  status: WorkflowRunStatus;
  node_status: Record<string, NodeRunStatus>;
  log: WorkflowRunLogEntry[];
  created_at: string;
  finished_at: string | null;
}

/** 1 bước trong 1 lần chạy, kèm kết quả người dùng ghi lại */
export interface RunStep {
  order: number;
  node_id: string;
  label: string;
  node_type: string;
  is_trigger: boolean;
  is_condition: boolean;
  /** "true" | "false" — nhánh mà node điều kiện đã chọn */
  branch: string | null;
  status: NodeRunStatus;
  skills: string[];
  file_path: string | null;
  command: string | null;
  /** Agent pipeline chạy bước này (null = Claude headless / bạn chạy tay) */
  agent: { key: string; name: string; tool: string; model: string } | null;
  result: string;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  /** Số liệu đo được của lần chạy bước này (worker gửi lên lúc hoàn tất) */
  run_metrics?: {
    model: string | null;
    cost_usd: number | null;
    duration_ms: number | null;
    tool: string | null;
    usage: { input?: number; output?: number; cache_write?: number; cache_read?: number; turns?: number };
  } | null;
}

export interface RunDetail {
  run_id: number;
  workflow_id: number;
  workflow_name: string;
  client_folder: string | null;
  status: WorkflowRunStatus;
  created_at: string | null;
  finished_at: string | null;
  total_steps: number;
  done_steps: number;
  steps: RunStep[];
}

/** 1 bước đã xếp hàng cho worker chạy bằng Claude headless */
export interface WorkflowStepJob {
  id: number;
  run_id: number;
  node_id: string;
  node_label: string | null;
  client_folder: string | null;
  file_path: string | null;
  prompt: string;
  /** "claude" (headless) hoặc "opencode" khi node chọn agent pipeline */
  tool: string;
  model: string | null;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  output: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/** Log sống của 1 job (GET /api/workflow-jobs/:id/progress) — tách khỏi WorkflowStepJob
    để list job poll 4s không phải kéo theo cả log. */
export interface WorkflowStepJobProgress {
  id: number;
  status: WorkflowStepJob["status"];
  progress: string | null;
  started_at: string | null;
  finished_at: string | null;
}

/** 1 step đang chờ người dùng tự chạy bằng tay */
export interface ActiveTask {
  workflow_id: number;
  workflow_name: string;
  client_folder: string | null;
  /** Task (feature) đã kích hoạt bước này — null nếu chạy tay từ editor */
  task_id: number | null;
  task_name: string | null;
  run_id: number;
  node_id: string;
  node_label: string;
  node_type: string;
  file_path: string;
  command: string;
  file_exists: boolean;
  created_at: string | null;
}
