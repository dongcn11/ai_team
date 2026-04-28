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

export type ProjectStatus = "active" | "paused" | "completed" | "archived";
export type AgentStatus   = "available" | "busy" | "offline";

// AgentFS — agent đọc từ filesystem (settings.toml), dùng trong Projects
export interface AgentFS {
  key: string;
  name: string;
  role: string;
  model: string;
  tool: string;
  status: AgentStatus;
  description: string;
}

// AgentSimple — agent từ DB, dùng trong Agents page và TaskManager
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
  id: string;           // folder name
  name: string;
  tech_stack: { backend?: string; frontend?: string };
  output_dir: string;
  agents: AgentFS[];
  agent_count: number;
}

export interface ProjectSummary {
  id: string;           // folder name
  name: string;
  tech_stack: { backend?: string; frontend?: string };
  output_dir: string;
  agent_count: number;
  status?: string;      // optional, chỉ có khi từ DB agent detail
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
