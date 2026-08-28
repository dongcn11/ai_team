import { useState, useEffect, useCallback, useRef } from "react";
import { Workflow, WorkflowRun, ActiveTask, WorkflowStepJob, ConfigAgent } from "../types";

export function useWorkflows() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error,   setError]       = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch("/api/workflows/");
      if (res.ok) {
        setWorkflows(await res.json());
        setError(null);
      }
    } catch {
      setError("Cannot connect");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return { workflows, loading, error, refetch: fetchAll };
}

/**
 * Danh sách workflow của RIÊNG 1 project (theo slug thư mục client).
 * Dùng cho tab Workflows trong project và cho dropdown chọn workflow ở mỗi task.
 */
export function useProjectWorkflows(clientFolder: string | null) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading,   setLoading]   = useState(true);

  const fetchAll = useCallback(async () => {
    if (!clientFolder) { setWorkflows([]); setLoading(false); return; }
    setLoading(true);
    try {
      const res = await fetch(`/api/workflows/?client_folder=${encodeURIComponent(clientFolder)}`);
      if (res.ok) setWorkflows(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  }, [clientFolder]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return { workflows, loading, refetch: fetchAll };
}

/** Mẫu = workflow chưa gắn project. Không chạy được, chỉ để nhân bản sang project. */
export function useWorkflowTemplates() {
  const [templates, setTemplates] = useState<Workflow[]>([]);

  useEffect(() => {
    fetch("/api/workflows/")
      .then(res => res.ok ? res.json() : [])
      .then((all: Workflow[]) => setTemplates(all.filter(w => !w.client_folder)))
      .catch(() => setTemplates([]));
  }, []);

  return templates;
}

const RUN_POLL_MS = 2000;

export function useWorkflowRun(runId: number | null) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const statusRef = useRef<string | null>(null);

  useEffect(() => {
    if (runId === null) { setRun(null); statusRef.current = null; return; }
    let cancelled = false;

    const fetch_ = async () => {
      try {
        const res = await fetch(`/api/workflows/runs/${runId}`);
        if (res.ok && !cancelled) {
          const data: WorkflowRun = await res.json();
          statusRef.current = data.status;
          setRun(data);
        }
      } catch { /* silent */ }
    };

    fetch_();
    const id = setInterval(() => {
      if (statusRef.current === "done" || statusRef.current === "failed") return;
      fetch_();
    }, RUN_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [runId]);

  return run;
}

const TASKS_POLL_MS = 4000;

/** Tất cả step đang chờ người dùng tự chạy, gom từ mọi workflow. */
export function useActiveTasks() {
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch("/api/workflows/tasks/active");
      if (res.ok) setTasks(await res.json());
    } catch { /* silent */ } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, TASKS_POLL_MS);
    return () => clearInterval(id);
  }, [fetchAll]);

  return { tasks, loading, refetch: fetchAll };
}

/** Run mới nhất của 1 workflow — để editor khôi phục trạng thái sau khi reload. */
export function useLatestRun(workflowId: number | null) {
  const [runId, setRunId] = useState<number | null>(null);

  useEffect(() => {
    if (workflowId === null) return;
    fetch(`/api/workflows/${workflowId}/runs?limit=1`)
      .then(res => res.ok ? res.json() : [])
      .then((runs: WorkflowRun[]) => { if (runs.length > 0) setRunId(runs[0].id); })
      .catch(() => { /* silent */ });
  }, [workflowId]);

  return [runId, setRunId] as const;
}

/** Job Claude headless của 1 lần chạy — để biết bước đang chờ worker hay chờ bạn. */
export function useStepJobs(runId: number | null, enabled: boolean) {
  const [jobs, setJobs] = useState<WorkflowStepJob[]>([]);

  const fetchAll = useCallback(async () => {
    if (runId === null || !enabled) { setJobs([]); return; }
    try {
      const res = await fetch(`/api/workflow-jobs?run_id=${runId}&limit=50`);
      if (res.ok) setJobs(await res.json());
    } catch { /* silent */ }
  }, [runId, enabled]);

  useEffect(() => {
    fetchAll();
    if (runId === null || !enabled) return;
    const id = setInterval(fetchAll, 4000);
    return () => clearInterval(id);
  }, [fetchAll, runId, enabled]);

  return { jobs, refetch: fetchAll };
}

/** Worker trên host có đang hỏi việc không — để UI nói rõ "chưa chạy worker.py". */
export function useWorkerStatus(enabled: boolean) {
  const [status, setStatus] = useState<{ online: boolean; silent_s: number | null } | null>(null);

  useEffect(() => {
    if (!enabled) { setStatus(null); return; }
    const load = async () => {
      try {
        const res = await fetch("/api/workflow-jobs/worker");
        if (res.ok) setStatus(await res.json());
      } catch { /* silent */ }
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [enabled]);

  return status;
}

/** Agent pipeline đọc từ config/settings.toml — node workflow chọn để chạy bằng opencode. */
export function useConfigAgents() {
  const [agents, setAgents] = useState<ConfigAgent[]>([]);

  useEffect(() => {
    fetch("/api/system/agents")
      .then(res => res.ok ? res.json() : [])
      .then((all: ConfigAgent[]) => setAgents(all.filter(a => a.tool !== "claude")))
      .catch(() => setAgents([]));
  }, []);

  return agents;
}

export function useSkills() {
  const [skills, setSkills] = useState<string[]>([]);

  useEffect(() => {
    fetch("/api/system/skills")
      .then(res => res.ok ? res.json() : [])
      .then(setSkills)
      .catch(() => setSkills([]));
  }, []);

  return skills;
}
