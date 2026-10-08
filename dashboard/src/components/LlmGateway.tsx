import React, { useCallback, useEffect, useState } from "react";

/**
 * Tab "API" — LLM gateway cho hệ thống khác dùng AI bên này (chat, viết kịch bản...).
 *
 *   Provider   nơi gọi model thật: OpenRouter (Claude, Grok, GPT...), Ollama (local), xAI...
 *   Model      alias tự đặt → provider + model gốc + system prompt + tham số mặc định
 *   API key    cấp cho từng hệ thống ngoài, giới hạn được alias nào
 *   Sử dụng    số request / token / chi phí — không lưu nội dung hội thoại
 *
 * Hệ thống ngoài gọi /v1/chat/completions chuẩn OpenAI (xem api/llm_gateway.py).
 */

type Provider = {
  id: number; name: string; base_url: string; key_hint: string; has_key: boolean;
  extra_headers: Record<string, string>; timeout_s: number; allow_passthrough: boolean;
  enabled: boolean; model_count: number; kind: "openai" | "claude_cli";
};
type Model = {
  id: number; alias: string; provider_id: number; provider: string | null; upstream_model: string;
  description: string; system_prompt: string; params: Record<string, any>; enabled: boolean;
};
type Client = {
  id: number; name: string; key_prefix: string; allowed_models: string[]; enabled: boolean;
  created_at: string | null; last_used_at: string | null; api_key?: string;
};

const PRESETS: { name: string; label: string; base_url: string; note: string;
                 headers?: Record<string, string>; kind?: "claude_cli" }[] = [
  { name: "openrouter", label: "OpenRouter", base_url: "https://openrouter.ai/api/v1",
    note: "Một key cho Claude, Grok, GPT, Gemini... Model gốc dạng anthropic/claude-sonnet-5-5, x-ai/grok-4.",
    headers: { "X-Title": "AI Team Gateway" } },
  { name: "ollama", label: "Ollama (local)", base_url: "http://host.docker.internal:11434/v1",
    note: "Model chạy trên máy này, không tốn tiền. Không cần key. Model gốc dạng qwen3:8b." },
  { name: "xai", label: "xAI (Grok)", base_url: "https://api.x.ai/v1", note: "Gọi thẳng Grok bằng key của xAI." },
  { name: "openai", label: "OpenAI", base_url: "https://api.openai.com/v1", note: "" },
  { name: "claude-cli", label: "Claude Code CLI (test)", base_url: "", kind: "claude_cli",
    note: "worker.py trên máy này chạy `claude -p` bằng đăng nhập Claude Code — như khung chat. "
        + "CHỈ ĐỂ TEST lâu lâu: dùng subscription cá nhân làm backend cho hệ thống khác là trái "
        + "điều khoản Anthropic, có thể bị khoá tài khoản. Model gốc: sonnet / opus / haiku." },
];

const PARAM_KEYS = ["temperature", "top_p", "max_tokens"] as const;

async function call(url: string, method = "GET", body?: any) {
  const res = await fetch(url, {
    method, headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Lỗi ${res.status}`);
  return data;
}

const hint = { fontSize: 12, color: "#64748b", lineHeight: 1.7 } as const;

export default function LlmGatewayPage() {
  const [sub, setSub] = useState<"models" | "providers" | "keys" | "usage" | "docs">("models");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels]       = useState<Model[]>([]);
  const [clients, setClients]     = useState<Client[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, m, c] = await Promise.all([call("/api/llm/providers"), call("/api/llm/models"), call("/api/llm/clients")]);
      setProviders(p); setModels(m); setClients(c);
    } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn: () => Promise<any>, ok?: string) => {
    setErr(null); setMsg(null);
    try { const r = await fn(); if (ok) setMsg(ok); await load(); return r; }
    catch (e: any) { setErr(e.message); return null; }
  };

  const tabs = [
    ["models", "Model", models.length], ["providers", "Provider", providers.length],
    ["keys", "API key", clients.length], ["usage", "Sử dụng", null], ["docs", "Hướng dẫn", null],
  ] as const;

  return (
    <div className="projects-page">
      <div className="page-header"><h2>API cho hệ thống ngoài</h2></div>
      <p style={{ ...hint, marginTop: -10 }}>
        Hệ thống khác gọi <code>/v1/chat/completions</code> chuẩn OpenAI bằng API key cấp ở đây,
        chọn <b>model</b> theo alias bạn đặt — phía sau là Claude, Grok qua OpenRouter hay model
        local qua Ollama, đổi lúc nào cũng được mà bên gọi không phải sửa code.
      </p>

      <div className="pd-tabs" style={{ marginBottom: 16 }}>
        {tabs.map(([k, label, n]) => (
          <button key={k} className={`pd-tab ${sub === k ? "on" : ""}`} onClick={() => setSub(k)}>
            {label}{n !== null && <span className="pd-tab-count">{n}</span>}
          </button>
        ))}
      </div>

      {err && <div className="state err" style={{ marginBottom: 12 }}>{err}</div>}
      {msg && <div className="settings-msg ok" style={{ marginBottom: 12 }}>{msg}</div>}

      {sub === "providers" && <Providers providers={providers} run={run} />}
      {sub === "models"    && <Models models={models} providers={providers} run={run} goProviders={() => setSub("providers")} />}
      {sub === "keys"      && <Keys clients={clients} models={models} run={run} />}
      {sub === "usage"     && <Usage />}
      {sub === "docs"      && <Docs models={models} />}
    </div>
  );
}

type Run = (fn: () => Promise<any>, ok?: string) => Promise<any>;

// ── Provider ──────────────────────────────────────────────────────────────

function Providers({ providers, run }: { providers: Provider[]; run: Run }) {
  const [draft, setDraft] = useState<any>(null);
  const [del, setDel] = useState<number | null>(null);

  const save = async () => {
    const body = {
      name: draft.name, base_url: draft.base_url, api_key: draft.api_key,
      timeout_s: Number(draft.timeout_s) || 120, allow_passthrough: draft.allow_passthrough,
      extra_headers: parseHeaders(draft.headers), enabled: draft.enabled, kind: draft.kind,
    };
    const r = await run(() => draft.id ? call(`/api/llm/providers/${draft.id}`, "PUT", body)
                                       : call("/api/llm/providers", "POST", body), "Đã lưu provider");
    if (r) setDraft(null);
  };

  return (
    <>
      {!draft && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          {PRESETS.map(p => (
            <button key={p.name} className="btn-muted" onClick={() => setDraft({
              id: null, name: p.name, base_url: p.base_url, api_key: "",
              timeout_s: p.kind === "claude_cli" ? 300 : 120, kind: p.kind || "openai",
              allow_passthrough: false, enabled: true, note: p.note,
              headers: Object.entries(p.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n"),
            })}>+ {p.label}</button>
          ))}
          <button className="btn-muted" onClick={() => setDraft({
            id: null, name: "", base_url: "", api_key: "", timeout_s: 120, allow_passthrough: false, kind: "openai",
            enabled: true, headers: "", note: "Bất kỳ dịch vụ nào nói chuẩn OpenAI-compatible (vLLM, LM Studio, Groq, DeepSeek...).",
          })}>+ Tuỳ chỉnh</button>
        </div>
      )}

      {draft && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, marginBottom: 4 }}>{draft.id ? `Sửa provider ${draft.name}` : "Provider mới"}</h3>
          {draft.note && <p style={{ ...hint, marginBottom: 12, color: draft.kind === "claude_cli" ? "#fbbf24" : hint.color }}>{draft.note}</p>}
          <div className="np-grid">
            <Field label="Tên (dùng trong model passthrough)">
              <input className="setting-input" value={draft.name} placeholder="openrouter"
                onChange={e => setDraft({ ...draft, name: e.target.value })} />
            </Field>
            {draft.kind !== "claude_cli" && <>
            <Field label="Base URL">
              <input className="setting-input" value={draft.base_url} placeholder="https://…/v1"
                onChange={e => setDraft({ ...draft, base_url: e.target.value })} />
            </Field>
            <Field label={`API key${draft.id ? " (để trống = giữ nguyên)" : ""}`}>
              <input className="setting-input" type="password" value={draft.api_key}
                placeholder={draft.name === "ollama" ? "không cần" : "sk-…"}
                onChange={e => setDraft({ ...draft, api_key: e.target.value })} />
            </Field>
            </>}
            <Field label="Timeout (giây)">
              <input className="setting-input" type="number" value={draft.timeout_s}
                onChange={e => setDraft({ ...draft, timeout_s: e.target.value })} />
            </Field>
            {draft.kind !== "claude_cli" && (
            <Field label="Header thêm (mỗi dòng Tên: giá trị)">
              <textarea className="setting-input" rows={2} value={draft.headers}
                onChange={e => setDraft({ ...draft, headers: e.target.value })} />
            </Field>)}
          </div>
          <label className="setting-checkbox-label" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={draft.allow_passthrough}
              onChange={e => setDraft({ ...draft, allow_passthrough: e.target.checked })} />
            <span className="setting-checkbox-text">
              Cho gọi thẳng <code>{draft.name || "<tên>"}/&lt;model gốc&gt;</code> không cần khai alias
              — tiện nhưng bên gọi dùng được <b>mọi</b> model của provider (kể cả model đắt)
            </span>
          </label>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn-primary" onClick={save} disabled={!draft.name || !draft.base_url}>Lưu</button>
            <button className="btn-muted" onClick={() => setDraft(null)}>Huỷ</button>
          </div>
        </div>
      )}

      {providers.length === 0 && !draft && (
        <div className="card" style={{ ...hint, textAlign: "center" }}>
          Chưa có provider. Khuyên dùng <b>OpenRouter</b> — 1 key gọi được cả Claude lẫn Grok —
          và <b>Ollama</b> cho model chạy local.
        </div>
      )}

      <div className="project-grid" style={{ gridTemplateColumns: "1fr" }}>
        {providers.map(p => (
          <div key={p.id} className="card" style={{ padding: 16, opacity: p.enabled ? 1 : 0.6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 15 }}>{p.name}</strong>
              {p.kind === "claude_cli"
                ? <span className="pd-slug" style={{ color: "#fbbf24" }}>claude -p qua worker · chỉ để test</span>
                : <span className="pd-slug">{p.base_url}</span>}
              <span style={hint}>{p.model_count} model{p.kind !== "claude_cli" && <> · key {p.has_key ? <code>{p.key_hint}</code> : "không có"}</>}
                {p.allow_passthrough && " · cho passthrough"}</span>
              <div style={{ flex: 1 }} />
              <button className="pd-ghost-btn" onClick={() => run(() => call(`/api/llm/providers/${p.id}`, "PUT", { enabled: !p.enabled }))}>
                {p.enabled ? "Tắt" : "Bật"}</button>
              <button className="pd-ghost-btn" onClick={() => setDraft({
                ...p, api_key: "", headers: Object.entries(p.extra_headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n"), note: "",
              })}>Sửa</button>
              {del === p.id ? (
                <>
                  <button className="pd-ghost-btn danger" onClick={() => { setDel(null); run(() => call(`/api/llm/providers/${p.id}`, "DELETE"), "Đã xoá"); }}>
                    Xoá cả {p.model_count} model</button>
                  <button className="pd-ghost-btn" onClick={() => setDel(null)}>Thôi</button>
                </>
              ) : <button className="pd-ghost-btn danger" onClick={() => setDel(p.id)}>Xoá</button>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function parseHeaders(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of (text || "").split("\n")) {
    const i = line.indexOf(":");
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return out;
}

// ── Model (alias) ─────────────────────────────────────────────────────────

function Models({ models, providers, run, goProviders }: {
  models: Model[]; providers: Provider[]; run: Run; goProviders: () => void;
}) {
  const [draft, setDraft] = useState<any>(null);
  const [remote, setRemote] = useState<string[]>([]);
  const [del, setDel] = useState<number | null>(null);
  const [tryId, setTryId] = useState<number | null>(null);

  const open = (m: Model | null) => {
    setRemote([]);
    setDraft(m ? { ...m, ...Object.fromEntries(PARAM_KEYS.map(k => [k, m.params?.[k] ?? ""])) }
               : { id: null, alias: "", provider_id: providers[0]?.id ?? "", upstream_model: "",
                   description: "", system_prompt: "", enabled: true, temperature: "", top_p: "", max_tokens: "" });
  };

  const fetchRemote = async () => {
    const r = await run(() => call(`/api/llm/providers/${draft.provider_id}/remote-models`));
    if (r) setRemote(r.models);
  };

  const save = async () => {
    const params: Record<string, number> = {};
    for (const k of PARAM_KEYS) if (draft[k] !== "" && draft[k] !== null) params[k] = Number(draft[k]);
    const body = { alias: draft.alias, provider_id: Number(draft.provider_id), upstream_model: draft.upstream_model,
                   description: draft.description, system_prompt: draft.system_prompt, params, enabled: draft.enabled };
    const r = await run(() => draft.id ? call(`/api/llm/models/${draft.id}`, "PUT", body)
                                       : call("/api/llm/models", "POST", body), "Đã lưu model");
    if (r) setDraft(null);
  };

  if (providers.length === 0) {
    return (
      <div className="card" style={{ ...hint, textAlign: "center" }}>
        Cần khai ít nhất 1 provider trước. <button className="pd-ghost-btn" onClick={goProviders}>Thêm provider →</button>
      </div>
    );
  }

  return (
    <>
      {!draft && <button className="btn-primary" style={{ marginBottom: 16 }} onClick={() => open(null)}>+ Model mới</button>}

      {draft && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>{draft.id ? `Sửa ${draft.alias}` : "Model mới"}</h3>
          <div className="np-grid">
            <Field label="Alias — tên bên gọi gửi trong `model`">
              <input className="setting-input" value={draft.alias} placeholder="viet-kich-ban"
                onChange={e => setDraft({ ...draft, alias: e.target.value })} />
            </Field>
            <Field label="Provider">
              <select className="setting-select" value={draft.provider_id}
                onChange={e => { setRemote([]); setDraft({ ...draft, provider_id: e.target.value }); }}>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <Field label="Model gốc">
              <div style={{ display: "flex", gap: 6 }}>
                <input className="setting-input" list="llm-remote" value={draft.upstream_model}
                  placeholder="anthropic/claude-sonnet-5-5"
                  onChange={e => setDraft({ ...draft, upstream_model: e.target.value })} />
                <button className="pd-ghost-btn" onClick={fetchRemote} title="Lấy danh sách model của provider">Tải DS</button>
              </div>
              <datalist id="llm-remote">{remote.map(r => <option key={r} value={r} />)}</datalist>
              {remote.length > 0 && <div className="np-hint">{remote.length} model — gõ để lọc.</div>}
            </Field>
            <Field label="Mô tả (hiện trong GET /v1/models)">
              <input className="setting-input" value={draft.description}
                onChange={e => setDraft({ ...draft, description: e.target.value })} />
            </Field>
          </div>
          <div className="np-field" style={{ marginTop: 12 }}>
            <label className="setting-label">System prompt — vai trò cố định của model này</label>
            <textarea className="setting-input" rows={5} value={draft.system_prompt}
              placeholder="Bạn là biên kịch quảng cáo. Viết kịch bản có cảnh, lời thoại, thời lượng…"
              onChange={e => setDraft({ ...draft, system_prompt: e.target.value })} />
          </div>
          <div style={{ display: "flex", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
            {PARAM_KEYS.map(k => (
              <div key={k} className="np-field" style={{ width: 140 }}>
                <label className="setting-label">{k}</label>
                <input className="setting-input" type="number" step="any" value={draft[k]} placeholder="mặc định"
                  onChange={e => setDraft({ ...draft, [k]: e.target.value })} />
              </div>
            ))}
          </div>
          <div className="np-hint">Tham số mặc định — bên gọi gửi giá trị riêng thì giá trị đó thắng.</div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn-primary" onClick={save} disabled={!draft.alias || !draft.upstream_model}>Lưu</button>
            <button className="btn-muted" onClick={() => setDraft(null)}>Huỷ</button>
          </div>
        </div>
      )}

      <div className="project-grid" style={{ gridTemplateColumns: "1fr" }}>
        {models.map(m => (
          <div key={m.id} className="card" style={{ padding: 16, opacity: m.enabled ? 1 : 0.6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 15 }}><code>{m.alias}</code></strong>
              <span className="pd-slug">{m.provider} → {m.upstream_model}</span>
              {m.description && <span style={hint}>{m.description}</span>}
              <div style={{ flex: 1 }} />
              <button className="pd-ghost-btn" onClick={() => setTryId(tryId === m.id ? null : m.id)}>Thử</button>
              <button className="pd-ghost-btn" onClick={() => run(() => call(`/api/llm/models/${m.id}`, "PUT", { enabled: !m.enabled }))}>
                {m.enabled ? "Tắt" : "Bật"}</button>
              <button className="pd-ghost-btn" onClick={() => open(m)}>Sửa</button>
              {del === m.id ? (
                <>
                  <button className="pd-ghost-btn danger" onClick={() => { setDel(null); run(() => call(`/api/llm/models/${m.id}`, "DELETE"), "Đã xoá"); }}>Xoá thật</button>
                  <button className="pd-ghost-btn" onClick={() => setDel(null)}>Thôi</button>
                </>
              ) : <button className="pd-ghost-btn danger" onClick={() => setDel(m.id)}>Xoá</button>}
            </div>
            {m.system_prompt && (
              <div style={{ ...hint, marginTop: 6, whiteSpace: "pre-wrap" }}>
                {m.system_prompt.length > 200 ? m.system_prompt.slice(0, 200) + "…" : m.system_prompt}
              </div>
            )}
            {tryId === m.id && <Playground alias={m.alias} />}
          </div>
        ))}
      </div>
    </>
  );
}

function Playground({ alias }: { alias: string }) {
  const [text, setText] = useState("");
  const [out, setOut] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async () => {
    setBusy(true); setOut(null);
    try {
      const r = await call("/api/llm/playground", "POST", { model: alias, messages: [{ role: "user", content: text }] });
      const u = r.usage || {};
      setOut({ ok: true, text: (r.choices?.[0]?.message?.content || "(rỗng)")
        + `\n\n— ${u.prompt_tokens ?? "?"} + ${u.completion_tokens ?? "?"} token${u.cost != null ? ` · $${u.cost}` : ""}` });
    } catch (e: any) { setOut({ ok: false, text: e.message }); }
    setBusy(false);
  };

  return (
    <div style={{ marginTop: 12, borderTop: "1px solid #1e293b", paddingTop: 12 }}>
      <textarea className="setting-input" rows={3} value={text} placeholder="Nhập câu hỏi để thử…"
        onChange={e => setText(e.target.value)} style={{ width: "100%" }} />
      <button className="btn-primary" style={{ marginTop: 8 }} onClick={send} disabled={busy || !text.trim()}>
        {busy ? "Đang chờ model…" : "Gửi"}</button>
      {out && (
        <div style={{ marginTop: 10, fontSize: 13, whiteSpace: "pre-wrap", lineHeight: 1.6,
                      color: out.ok ? "#e2e8f0" : "#fca5a5" }}>{out.text}</div>
      )}
    </div>
  );
}

// ── API key ───────────────────────────────────────────────────────────────

function Keys({ clients, models, run }: { clients: Client[]; models: Model[]; run: Run }) {
  const [draft, setDraft] = useState<any>(null);
  const [fresh, setFresh] = useState<{ name: string; key: string } | null>(null);
  const [del, setDel] = useState<number | null>(null);

  const save = async () => {
    const body = { name: draft.name, allowed_models: draft.allowed_models };
    const r = await run(() => draft.id ? call(`/api/llm/clients/${draft.id}`, "PUT", body)
                                       : call("/api/llm/clients", "POST", body), "Đã lưu");
    if (r) { setDraft(null); if (r.api_key) setFresh({ name: r.name, key: r.api_key }); }
  };

  const rotate = async (c: Client) => {
    const r = await run(() => call(`/api/llm/clients/${c.id}/rotate`, "POST"), "Đã đổi key — key cũ ngừng hoạt động");
    if (r?.api_key) setFresh({ name: r.name, key: r.api_key });
  };

  return (
    <>
      {fresh && (
        <div className="card" style={{ marginBottom: 16, borderColor: "#2563eb" }}>
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            🔑 Key của <b>{fresh.name}</b> — <b style={{ color: "#fbbf24" }}>chỉ hiện lần này</b>, sao chép ngay:
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <code style={{ flex: 1, padding: 8, background: "#0b1220", borderRadius: 6, wordBreak: "break-all" }}>{fresh.key}</code>
            <button className="pd-ghost-btn" onClick={() => navigator.clipboard?.writeText(fresh.key)}>Sao chép</button>
            <button className="pd-ghost-btn" onClick={() => setFresh(null)}>Đã lưu</button>
          </div>
        </div>
      )}

      {!draft && <button className="btn-primary" style={{ marginBottom: 16 }}
        onClick={() => setDraft({ id: null, name: "", allowed_models: [] })}>+ Cấp key mới</button>}

      {draft && (
        <div className="card" style={{ marginBottom: 16 }}>
          <Field label="Tên hệ thống dùng key">
            <input className="setting-input" value={draft.name} placeholder="CRM, Website, App mobile…"
              onChange={e => setDraft({ ...draft, name: e.target.value })} />
          </Field>
          <div className="np-field" style={{ marginTop: 12 }}>
            <label className="setting-label">Model được dùng</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {models.map(m => {
                const on = draft.allowed_models.includes(m.alias);
                return (
                  <button key={m.id} type="button" className="pd-ghost-btn"
                    style={on ? { color: "#93c5fd", borderColor: "#2563eb", background: "#172554" } : undefined}
                    onClick={() => setDraft({ ...draft, allowed_models: on
                      ? draft.allowed_models.filter((a: string) => a !== m.alias) : [...draft.allowed_models, m.alias] })}>
                    {on ? "✓ " : ""}{m.alias}
                  </button>
                );
              })}
            </div>
            <div className="np-hint">Không tick cái nào = dùng được <b>mọi</b> model đang bật.</div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn-primary" onClick={save} disabled={!draft.name.trim()}>{draft.id ? "Lưu" : "Tạo key"}</button>
            <button className="btn-muted" onClick={() => setDraft(null)}>Huỷ</button>
          </div>
        </div>
      )}

      <div className="project-grid" style={{ gridTemplateColumns: "1fr" }}>
        {clients.map(c => (
          <div key={c.id} className="card" style={{ padding: 16, opacity: c.enabled ? 1 : 0.6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 15 }}>{c.name}</strong>
              <code style={{ color: "#93c5fd", fontSize: 12 }}>{c.key_prefix}</code>
              <span style={hint}>
                {c.allowed_models.length ? c.allowed_models.join(", ") : "mọi model"}
                {" · "}{c.last_used_at ? `dùng lần cuối ${new Date(c.last_used_at + "Z").toLocaleString()}` : "chưa dùng"}
              </span>
              <div style={{ flex: 1 }} />
              <button className="pd-ghost-btn" onClick={() => run(() => call(`/api/llm/clients/${c.id}`, "PUT", { enabled: !c.enabled }))}>
                {c.enabled ? "Tắt" : "Bật"}</button>
              <button className="pd-ghost-btn" onClick={() => setDraft({ id: c.id, name: c.name, allowed_models: c.allowed_models })}>Sửa</button>
              <button className="pd-ghost-btn" onClick={() => rotate(c)}>Đổi key</button>
              {del === c.id ? (
                <>
                  <button className="pd-ghost-btn danger" onClick={() => { setDel(null); run(() => call(`/api/llm/clients/${c.id}`, "DELETE"), "Đã thu hồi"); }}>Thu hồi thật</button>
                  <button className="pd-ghost-btn" onClick={() => setDel(null)}>Thôi</button>
                </>
              ) : <button className="pd-ghost-btn danger" onClick={() => setDel(c.id)}>Thu hồi</button>}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── Sử dụng ───────────────────────────────────────────────────────────────

function Usage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<any>(null);
  useEffect(() => { call(`/api/llm/usage?days=${days}`).then(setData).catch(() => setData(null)); }, [days]);
  if (!data) return <div className="state">Đang tải…</div>;

  const th = { textAlign: "left" as const, padding: "6px 10px", color: "#64748b", fontWeight: 500, fontSize: 12 };
  const td = { padding: "6px 10px", fontSize: 13, borderTop: "1px solid #1e293b" };
  const num = { ...td, textAlign: "right" as const, fontVariantNumeric: "tabular-nums" as const };

  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <select className="setting-select" value={days} onChange={e => setDays(Number(e.target.value))}>
          {[1, 7, 30, 90].map(d => <option key={d} value={d}>{d} ngày qua</option>)}
        </select>
      </div>
      <div className="card" style={{ padding: 0, overflowX: "auto", marginBottom: 16 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>
            <th style={th}>Hệ thống</th><th style={th}>Model</th><th style={{ ...th, textAlign: "right" }}>Request</th>
            <th style={{ ...th, textAlign: "right" }}>Lỗi</th><th style={{ ...th, textAlign: "right" }}>Token vào</th>
            <th style={{ ...th, textAlign: "right" }}>Token ra</th><th style={{ ...th, textAlign: "right" }}>Chi phí</th>
          </tr></thead>
          <tbody>
            {data.summary.length === 0 && <tr><td style={td} colSpan={7}>Chưa có request nào.</td></tr>}
            {data.summary.map((s: any, i: number) => (
              <tr key={i}>
                <td style={td}>{s.client}</td><td style={td}><code>{s.model}</code></td>
                <td style={num}>{s.requests}</td>
                <td style={{ ...num, color: s.errors ? "#fca5a5" : undefined }}>{s.errors}</td>
                <td style={num}>{s.prompt_tokens.toLocaleString()}</td>
                <td style={num}>{s.completion_tokens.toLocaleString()}</td>
                <td style={num}>{s.cost_usd ? `$${s.cost_usd.toFixed(4)}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 style={{ fontSize: 14, marginBottom: 8 }}>50 request gần nhất</h3>
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {data.recent.map((u: any) => (
              <tr key={u.id}>
                <td style={td}>{u.created_at ? new Date(u.created_at + "Z").toLocaleString() : ""}</td>
                <td style={td}>{u.client}</td>
                <td style={td}><code>{u.model}</code>{u.upstream_model && <span style={hint}> → {u.upstream_model}</span>}</td>
                <td style={num}>{u.latency_ms != null ? `${(u.latency_ms / 1000).toFixed(1)}s` : ""}</td>
                <td style={{ ...td, color: u.status === "ok" ? "#4ade80" : "#fca5a5" }}>
                  {u.status === "ok" ? `${u.prompt_tokens ?? "?"}+${u.completion_tokens ?? "?"} tok` : u.error}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Cách gọi — hướng dẫn tích hợp gửi cho dev hệ thống khác ────────────────
//
// Một nguồn duy nhất (GUIDE) dựng cả phần xem trên màn hình lẫn bản Markdown để
// sao chép / tải về — sửa nội dung một chỗ là hai bản khớp nhau. Bản gửi đi KHÔNG
// nhắc gì tới nội bộ (provider thật, /api, worker): người nhận chỉ cần biết /v1.

type Block =
  | { t: "p"; text: string }
  | { t: "code"; lang: string; label?: string; text: string }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "list"; items: string[] };
type Section = { title: string; blocks: Block[] };

const BASE_KEY = "llm-gateway-public-base";

function buildGuide(base: string, models: Model[]): { title: string; sections: Section[] } {
  const v1 = `${base.replace(/\/+$/, "")}/v1`;
  const active = models.filter(m => m.enabled);
  const m = active[0]?.alias || "ten-model";
  const prompt = "Viết kịch bản video 30 giây giới thiệu sản phẩm";

  return {
    title: "Hướng dẫn tích hợp AI API",
    sections: [
      { title: "Tổng quan", blocks: [
        { t: "p", text: "API theo chuẩn OpenAI Chat Completions. Bạn có thể gọi bằng HTTP thường hoặc dùng thư viện OpenAI chính thức của bất kỳ ngôn ngữ nào — chỉ cần đổi base URL và API key." },
        { t: "table", head: ["Thông tin", "Giá trị"], rows: [
          ["Base URL", v1],
          ["Xác thực", "Header `Authorization: Bearer <API_KEY>`"],
          ["API key", "Được gửi riêng — dạng `sk-ait-…`"],
          ["Định dạng", "JSON, UTF-8"],
        ]},
      ]},
      { title: "Model được dùng", blocks: [
        active.length
          ? { t: "table", head: ["model", "Mô tả"], rows: active.map(x => [`\`${x.alias}\``, x.description || "—"]) }
          : { t: "p", text: "(Chưa có model nào — liên hệ người cấp key.)" },
        { t: "p", text: `Danh sách đúng với key của bạn: \`GET ${v1}/models\`.` },
      ]},
      { title: "Gửi một câu hỏi", blocks: [
        { t: "p", text: `\`POST ${v1}/chat/completions\`` },
        { t: "code", lang: "bash", label: "curl", text:
`curl ${v1}/chat/completions \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${m}",
    "messages": [
      {"role": "user", "content": "${prompt}"}
    ]
  }'` },
        { t: "code", lang: "python", label: "Python (pip install openai)", text:
`from openai import OpenAI

client = OpenAI(base_url="${v1}", api_key="API_KEY", timeout=300)

r = client.chat.completions.create(
    model="${m}",
    messages=[{"role": "user", "content": "${prompt}"}],
)
print(r.choices[0].message.content)` },
        { t: "code", lang: "javascript", label: "Node.js (npm install openai)", text:
`import OpenAI from "openai";

const client = new OpenAI({ baseURL: "${v1}", apiKey: process.env.API_KEY, timeout: 300_000 });

const r = await client.chat.completions.create({
  model: "${m}",
  messages: [{ role: "user", content: "${prompt}" }],
});
console.log(r.choices[0].message.content);` },
        { t: "code", lang: "php", label: "PHP (không cần thư viện)", text:
`$ch = curl_init("${v1}/chat/completions");
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 300,
    CURLOPT_HTTPHEADER => [
        "Authorization: Bearer " . getenv("API_KEY"),
        "Content-Type: application/json",
    ],
    CURLOPT_POSTFIELDS => json_encode([
        "model" => "${m}",
        "messages" => [["role" => "user", "content" => "${prompt}"]],
    ]),
]);
$res = json_decode(curl_exec($ch), true);
echo $res["choices"][0]["message"]["content"];` },
      ]},
      { title: "Kết quả trả về", blocks: [
        { t: "code", lang: "json", text:
`{
  "id": "chatcmpl-…",
  "object": "chat.completion",
  "model": "${m}",
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "content": "Cảnh 1: …" },
    "finish_reason": "stop"
  }],
  "usage": { "prompt_tokens": 120, "completion_tokens": 450, "total_tokens": 570 }
}` },
        { t: "p", text: "Nội dung câu trả lời nằm ở `choices[0].message.content`." },
      ]},
      { title: "Trò chuyện nhiều lượt", blocks: [
        { t: "p", text: "API không lưu lịch sử. Muốn hỏi tiếp, gửi lại toàn bộ hội thoại trước đó trong `messages` theo đúng thứ tự:" },
        { t: "code", lang: "json", text:
`"messages": [
  {"role": "system",    "content": "Giọng văn trẻ trung, hài hước."},
  {"role": "user",      "content": "${prompt}"},
  {"role": "assistant", "content": "Cảnh 1: …"},
  {"role": "user",      "content": "Rút gọn còn 15 giây"}
]` },
        { t: "p", text: "`system` (tuỳ chọn) dùng để dặn thêm về giọng văn, định dạng, độ dài… cho riêng lần gọi đó." },
      ]},
      { title: "Tham số tuỳ chọn", blocks: [
        { t: "table", head: ["Tham số", "Ý nghĩa"], rows: [
          ["`temperature`", "0–2. Thấp = ổn định, cao = sáng tạo hơn"],
          ["`max_tokens`", "Giới hạn độ dài câu trả lời"],
          ["`top_p`", "Cách lấy mẫu khác thay cho temperature"],
          ["`stop`", "Chuỗi (hoặc mảng chuỗi) gặp thì dừng"],
          ["`response_format`", "`{\"type\": \"json_object\"}` để nhận JSON (tuỳ model)"],
        ]},
        { t: "p", text: "Không gửi thì dùng giá trị mặc định đã cấu hình cho model." },
      ]},
      { title: "Lỗi", blocks: [
        { t: "p", text: "Lỗi trả về dạng `{\"error\": {\"message\": \"…\", \"type\": \"…\", \"code\": \"…\"}}`." },
        { t: "table", head: ["HTTP", "code", "Nguyên nhân / cách xử lý"], rows: [
          ["400", "`invalid_messages`, `invalid_json`, `stream_unsupported`", "Sai định dạng request — sửa request"],
          ["401", "`missing_api_key`, `invalid_api_key`", "Thiếu hoặc sai API key"],
          ["403", "`key_disabled`, `model_not_allowed`", "Key bị tắt hoặc không được dùng model này"],
          ["404", "`model_not_found`", "Sai tên model — xem `GET /v1/models`"],
          ["502", "`upstream_…`", "Phía AI tạm lỗi — thử lại sau vài giây"],
          ["504", "`upstream_timeout`, `worker_offline`", "Quá thời gian chờ — thử lại sau"],
        ]},
      ]},
      { title: "Lưu ý", blocks: [
        { t: "list", items: [
          "Câu trả lời dài có thể mất **tới vài phút** — đặt timeout phía bạn tối thiểu **300 giây**.",
          "Chưa hỗ trợ `stream: true` — nhận nguyên câu trả lời một lần.",
          "Với lỗi 502/504, nên thử lại tối đa 2–3 lần, mỗi lần cách nhau vài giây.",
          "Giữ API key ở phía **server** của bạn (biến môi trường), **không** nhúng vào web/app phía người dùng.",
          "Nghi lộ key thì báo ngay để được cấp key mới — key cũ sẽ ngừng hoạt động.",
        ]},
      ]},
    ],
  };
}

function guideMarkdown(g: { title: string; sections: Section[] }): string {
  const out = [`# ${g.title}`, ""];
  for (const s of g.sections) {
    out.push(`## ${s.title}`, "");
    for (const b of s.blocks) {
      if (b.t === "p") out.push(b.text, "");
      else if (b.t === "code") out.push(...(b.label ? [`**${b.label}**`, ""] : []), "```" + b.lang, b.text, "```", "");
      else if (b.t === "list") out.push(...b.items.map(i => `- ${i}`), "");
      else out.push(`| ${b.head.join(" | ")} |`, `|${b.head.map(() => "---").join("|")}|`,
                    ...b.rows.map(r => `| ${r.join(" | ")} |`), "");
    }
  }
  return out.join("\n");
}

/** `code` và **đậm** trong chuỗi → JSX, đủ cho nội dung tự viết ở trên. */
function inline(text: string): React.ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code>
    : part.startsWith("**") && part.endsWith("**") ? <b key={i}>{part.slice(2, -2)}</b>
    : part);
}

function Docs({ models }: { models: Model[] }) {
  const [base, setBase] = useState<string>(() => {
    try { return localStorage.getItem(BASE_KEY) || window.location.origin; }
    catch { return window.location.origin; }
  });
  const [copied, setCopied] = useState(false);
  const saveBase = (v: string) => { setBase(v); try { localStorage.setItem(BASE_KEY, v); } catch { /* bỏ qua */ } };

  const guide = buildGuide(base, models);
  const md = guideMarkdown(guide);
  const isLocal = /localhost|127\.0\.0\.1|\[::1\]/.test(base);

  const copy = async () => {
    try { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { /* trình duyệt chặn clipboard — vẫn còn nút tải file */ }
  };
  const download = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown;charset=utf-8" }));
    a.download = "huong-dan-ai-api.md";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const pre = { background: "#0b1220", padding: 12, borderRadius: 6, fontSize: 12,
                overflowX: "auto" as const, lineHeight: 1.6, margin: "6px 0 10px" };
  const cell = { padding: "6px 10px", borderTop: "1px solid #1e293b", fontSize: 13, textAlign: "left" as const, verticalAlign: "top" as const };

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="np-field">
          <label className="setting-label">Địa chỉ public mà người nhận gọi tới</label>
          <input className="setting-input" value={base} placeholder="https://ai.congty.vn"
            onChange={e => saveBase(e.target.value)} />
          <div className="np-hint" style={isLocal ? { color: "#fbbf24" } : undefined}>
            {isLocal
              ? "Đang là localhost — người ở máy khác không gọi được. Điền domain/IP public (chỉ mở đường /v1)."
              : "Hướng dẫn bên dưới dùng địa chỉ này."}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
          <button className="btn-primary" onClick={copy}>{copied ? "✓ Đã sao chép" : "Sao chép hướng dẫn (Markdown)"}</button>
          <button className="btn-muted" onClick={download}>Tải file .md</button>
          <span style={hint}>API key <b>không</b> nằm trong hướng dẫn — gửi riêng cho từng người.</span>
        </div>
      </div>

      <div className="card" style={{ lineHeight: 1.7, fontSize: 13 }}>
        <h3 style={{ fontSize: 17, marginBottom: 8 }}>{guide.title}</h3>
        {guide.sections.map(s => (
          <section key={s.title} style={{ marginTop: 18 }}>
            <h4 style={{ fontSize: 14, marginBottom: 6, color: "#e2e8f0" }}>{s.title}</h4>
            {s.blocks.map((b, i) =>
              b.t === "p" ? <p key={i} style={{ margin: "6px 0" }}>{inline(b.text)}</p>
              : b.t === "list" ? <ul key={i} style={{ paddingLeft: 18, margin: "6px 0" }}>
                  {b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ul>
              : b.t === "code" ? <div key={i}>
                  {b.label && <div style={{ fontWeight: 600, marginTop: 8 }}>{b.label}</div>}
                  <pre style={pre}>{b.text}</pre></div>
              : <div key={i} style={{ overflowX: "auto", margin: "6px 0" }}>
                  <table style={{ borderCollapse: "collapse", width: "100%" }}>
                    <thead><tr>{b.head.map(h => <th key={h} style={{ ...cell, borderTop: "none", color: "#64748b", fontWeight: 500, fontSize: 12 }}>{h}</th>)}</tr></thead>
                    <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k} style={cell}>{inline(c)}</td>)}</tr>)}</tbody>
                  </table></div>
            )}
          </section>
        ))}
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="np-field"><label className="setting-label">{label}</label>{children}</div>;
}
