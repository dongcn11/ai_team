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
  tech_stack: { backend?: string; frontend?: string };
  agents: AgentFS[];
  agent_count: number;
  output_dir: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  tech_stack: { backend?: string; frontend?: string };
  agent_count: number;
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
  | "action.generate_code"
  | "action.create_mr"
  | "action.code_review"
  | "action.custom"
  | "logic.condition";

export interface SlackMentionData {
  label: string;
  channel: string;
  keyword?: string;
}

export interface GenerateCodeData {
  label: string;
  skill_dirs: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
}

export interface CreateMrData {
  label: string;
  provider: "gitlab" | "github";
  repo: string;
  base_branch: string;
  title_template: string;
  description_template: string;
}

export interface CodeReviewData {
  label: string;
  skill_dirs: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
}

export interface CustomActionData {
  label: string;
  skill_dirs: string[];
  prompt: string;
  /** Key agent pipeline (pm/be1/leader...) chạy bước này bằng opencode.
   *  Bỏ trống = Claude headless hoặc bạn chạy tay. */
  agent_key?: string | null;
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
}

export type WorkflowNodeData =
  | SlackMentionData | GenerateCodeData | CreateMrData | CodeReviewData | CustomActionData | ConditionData;

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
export type NodeRunStatus = "pending" | "running" | "ok" | "error" | "skipped";

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
