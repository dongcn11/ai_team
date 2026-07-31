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

// ── Workflows ──

export type NodeStatus  = "pending" | "running" | "done" | "failed" | "waiting" | "skipped";
export type WfRunStatus = "queued" | "running" | "waiting" | "done" | "failed" | "canceled";

export interface WfNode {
  id: string;
  type: string;              // slack_listener | cron | webhook | manual_trigger | task | manual_gate | action
  label?: string;
  runtime?: string;          // code | opencode | claude  (chỉ với type="task")
  model?: string;
  prompt?: string;
  handler?: string;
  outward?: boolean;
  timeout_s?: number;
}

export interface WfEdge {
  from: string;
  to: string;
  label?: string;
}

export interface WfGraph {
  name?: string;
  nodes: WfNode[];
  edges: WfEdge[];
}

/** Kết quả validate. `bad_nodes` là node cần tô đỏ trên canvas. */
export interface WfValidation {
  ok: boolean;
  errors: string[];
  warnings: string[];
  bad_nodes: string[];
}

export interface WorkflowSummary {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  node_count: number;
  claude_nodes: string[];    // đều đã có manual_gate chắn trước, nếu không thì không lưu được
  created_at: string;
}

export interface WorkflowDetail {
  id: number;
  name: string;
  description: string | null;
  graph: WfGraph;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface WfApproval {
  node_id: string;
  approved_by: string | null;
  approved_at: string | null;
  note: string | null;
}

export interface WorkflowRun {
  id: number;
  workflow_id: number;
  trigger_type: string;
  status: WfRunStatus;
  payload: Record<string, unknown>;
  state: Record<string, NodeStatus>;
  outputs: Record<string, string>;
  waiting_on: string[];
  approvals: WfApproval[];
  log: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
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
