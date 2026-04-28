import { useState, useEffect, useCallback } from "react";

export interface Setting {
  key: string;
  value: string;
}

export function useSettings() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [saving,   setSaving]   = useState(false);
  const [msg,      setMsg]      = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/");
      if (res.ok) setSettings(await res.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const saveSetting = async (key: string, value: string) => {
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/settings/${key}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
      if (res.ok) {
        setMsg("Saved");
        setSettings(prev =>
          prev.some(s => s.key === key)
            ? prev.map(s => (s.key === key ? { key, value } : s))
            : [...prev, { key, value }]
        );
      }
    } catch {
      setMsg("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const getValue = (key: string, fallback = "") =>
    settings.find(s => s.key === key)?.value ?? fallback;

  return { settings, saving, msg, saveSetting, getValue, fetchAll };
}
