import { useCallback, useEffect, useState } from "react";

export interface McpProfile { name: string; tools: string[] }

export interface McpTemplate {
  name: string;
  version: string;
  needs_credential: boolean;
  profiles: McpProfile[];
}

export interface McpServer {
  name: string;
  template: string;
  profile: string;
  enabled: boolean;
  declared_write_scope: Record<string, unknown>;
  /** Credential đã được KHAI trong settings.local.toml chưa. KHÔNG phải "dùng
   *  được" — API chạy trong container, không thấy đường dẫn trên host. */
  credential_declared: boolean;
}

export interface McpConfig {
  slug: string;
  enabled: boolean;
  servers: McpServer[];
  exists: boolean;
  writable: boolean;
  parse_error: string | null;
}

/** Trạng thái nối của lần chạy gần nhất, worker gửi kèm nhịp tim. */
export interface McpRuntime { slug: string; server: string; status: string; at: string | null }

export function useMcp(slug: string | null) {
  const [config,    setConfig]    = useState<McpConfig | null>(null);
  const [templates, setTemplates] = useState<McpTemplate[]>([]);
  const [runtime,   setRuntime]   = useState<McpRuntime[]>([]);
  const [workerOn,  setWorkerOn]  = useState<boolean | null>(null);
  const [saving,    setSaving]    = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!slug) return;
    setError(null);
    try {
      const [c, t] = await Promise.all([
        fetch(`/api/mcp/${slug}`),
        fetch(`/api/mcp/templates`),
      ]);
      if (c.ok) setConfig(await c.json());
      if (t.ok) setTemplates(await t.json());
    } catch {
      setError("Không gọi được API.");
    }
  }, [slug]);

  /** Đi ké endpoint nhịp tim sẵn có — không thêm vòng poll mới. */
  const loadRuntime = useCallback(async () => {
    try {
      const res = await fetch("/api/workflow-jobs/worker");
      if (!res.ok) return;
      const d = await res.json();
      setWorkerOn(!!d.online);
      setRuntime((d.mcp || []) as McpRuntime[]);
    } catch { /* im lặng: worker offline là chuyện bình thường */ }
  }, []);

  useEffect(() => { load(); loadRuntime(); }, [load, loadRuntime]);

  const save = async (next: McpConfig) => {
    if (!slug) return false;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/mcp/${slug}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: next.enabled,
          servers: next.servers.map(s => ({
            name: s.name, template: s.template, profile: s.profile,
            enabled: s.enabled, declared_write_scope: s.declared_write_scope,
          })),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || `Lưu thất bại (HTTP ${res.status}).`);
        return false;
      }
      setConfig(await res.json());
      return true;
    } catch {
      setError("Không gọi được API.");
      return false;
    } finally {
      setSaving(false);
    }
  };

  return { config, setConfig, templates, runtime, workerOn, saving, error, load, save };
}
