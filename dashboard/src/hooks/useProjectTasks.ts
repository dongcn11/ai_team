import { useState, useEffect, useCallback, useRef } from "react";
import { ProjectTask } from "../types";

export function useProjectTasks(projectId: number | null) {
  const [tasks,   setTasks]   = useState<ProjectTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const firstRef = useRef(true);

  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    if (firstRef.current) setLoading(true);
    try {
      const res = await fetch(`/api/project-tasks/${projectId}`);
      if (res.ok) {
        setTasks(await res.json());
        setError(null);
      }
    } catch {
      if (firstRef.current) setError("Cannot load tasks");
    } finally {
      setLoading(false);
      firstRef.current = false;
    }
  }, [projectId]);

  useEffect(() => { firstRef.current = true; fetchAll(); }, [fetchAll]);

  return { tasks, loading, error, refetch: fetchAll };
}
