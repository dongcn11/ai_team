import { useState, useEffect, useCallback, useRef } from "react";
import { Workflow, WorkflowRun, ActiveTask } from "../types";

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
