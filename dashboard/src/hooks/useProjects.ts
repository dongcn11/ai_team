import { useState, useEffect, useCallback } from "react";
import { ProjectSummary } from "../types";

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch("/api/projects/");
      if (res.ok) {
        setProjects(await res.json());
        setError(null);
      }
    } catch {
      setError("Cannot connect");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return { projects, loading, error, refetch: fetchAll };
}
