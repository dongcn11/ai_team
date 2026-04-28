import { useState, useEffect, useCallback } from "react";
import { AgentSimple } from "../types";

export function useAgents() {
  const [agents,  setAgents]  = useState<AgentSimple[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch("/api/agents/");
      if (res.ok) {
        setAgents(await res.json());
        setError(null);
      }
    } catch {
      setError("Cannot connect");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return { agents, loading, error, refetch: fetchAll };
}
