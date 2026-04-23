import { useState, useEffect, useCallback } from "react";
import { Run, RunSummary } from "../types";

const POLL_MS      = 3000;
const HISTORY_MS   = 10000;

export function useCurrentRun() {
  const [run,     setRun]     = useState<Run | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch_ = useCallback(async () => {
    try {
      const res = await fetch("/api/runs/current");
      if (res.status === 404) { setRun(null); setError(null); return; }
      if (!res.ok) { setError(`API ${res.status}`); return; }
      setRun(await res.json());
      setError(null);
    } catch {
      setError("Cannot connect to API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch_();
    const id = setInterval(fetch_, POLL_MS);
    return () => clearInterval(id);
  }, [fetch_]);

  return { run, error, loading };
}

export function useRunHistory() {
  const [runs, setRuns] = useState<RunSummary[]>([]);

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await fetch("/api/runs?limit=10");
        if (res.ok) setRuns(await res.json());
      } catch { /* silent */ }
    };
    fetch_();
    const id = setInterval(fetch_, HISTORY_MS);
    return () => clearInterval(id);
  }, []);

  return runs;
}
