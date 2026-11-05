import { useCallback, useEffect, useState } from "react";
import { useMcp, McpConfig, McpServer, AccountConnector } from "../hooks/useMcp";

/**
 * Tab MCP của một dự án.
 *
 * Nguồn sự thật là file clients/<slug>/mcp.json — sửa ở đây hay sửa bằng editor
 * đều được. Credential KHÔNG đi qua đây: nó nằm trong settings.local.toml trên
 * host, giao diện chỉ hiện "đã khai / chưa khai".
 */
const SUGGESTED_NAME: Record<string, string> = {
  "google-workspace": "gdrive",
  "google-drive-files": "gfiles",
  filesystem: "fs",
  figma: "figma",
};

/** Mẫu có nút kết nối riêng trên giao diện — không hiện lời nhắc sửa settings.local.toml. */
const CONNECT_UI = new Set(["google-drive-files", "figma"]);

/** Tên gợi ý cho server mới theo mẫu; trùng tên đã có thì thêm số. */
function suggestName(template: string, servers: McpServer[]): string {
  if (!template) return "";
  const base = SUGGESTED_NAME[template] || template.toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  const taken = new Set(servers.map(s => s.name));
  let name = base;
  for (let i = 2; taken.has(name); i++) name = `${base}${i}`;
  return name;
}

export default function ProjectMcp({ slug }: { slug: string }) {
  const { config, setConfig, templates, runtime, connectors, workerOn, saving, error, save } = useMcp(slug);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTemplate, setNewTemplate] = useState("");

  if (!config) return <div className="mcp-empty">Đang tải…</div>;

  const patch = (next: Partial<McpConfig>) => setConfig({ ...config, ...next });

  const patchServer = (i: number, next: Partial<McpServer>) =>
    patch({ servers: config.servers.map((s, j) => (j === i ? { ...s, ...next } : s)) });

  const tpl = (name: string) => templates.find(t => t.name === name);

  const addServer = () => {
    const t = tpl(newTemplate) || templates[0];
    if (!t || !newName.trim()) return;
    patch({
      servers: [...config.servers, {
        name: newName.trim(), template: t.name,
        // Mặc định là hồ sơ ít quyền nhất. Quên đổi thì thiệt hại bằng không.
        profile: t.profiles.find(p => p.name === "read-only")?.name || t.profiles[0]?.name || "read-only",
        enabled: true, declared_write_scope: {}, credential_declared: false,
      }],
    });
    setNewName(""); setAdding(false);
  };

  const statusOf = (server: string) =>
    runtime.find(r => r.slug === slug && r.server === server)?.status || null;

  return (
    <div className="mcp-tab">
      <p className="mcp-hint">
        Bước của dự án này chỉ dùng được những gì bật ở đây: connector của tài khoản Claude mà bạn
        tick, và các MCP server riêng khai bên dưới. Dự án khác không tick thì không dùng được.
      </p>

      {!config.writable && (
        <div className="mcp-hint warn">
          Thư mục <code>clients/</code> đang chỉ-đọc nên nút Lưu sẽ hỏng. Kiểm tra mount
          <code> ../clients:/clients</code> trong <code>dashboard/docker-compose.yml</code>.
        </div>
      )}
      {config.parse_error && (
        <div className="mcp-hint warn">
          File <code>clients/{slug}/mcp.json</code> hỏng cú pháp: {config.parse_error}.
          Worker vẫn đang chạy bằng cấu hình cũ trong bộ nhớ nó.
        </div>
      )}
      {workerOn === false && (
        <div className="mcp-hint">
          Worker đang tắt nên không có trạng thái kết nối để hiện. Mở terminal và chạy
          <code> python worker.py</code>.
        </div>
      )}

      <label className="mcp-master">
        <input type="checkbox" checked={config.enabled}
               onChange={e => patch({ enabled: e.target.checked })} />
        <span>Bật MCP cho dự án này</span>
        <em>tắt ở đây là tắt hết, không phải tắt từng server</em>
      </label>

      <AccountConnectors
        connectors={connectors}
        selected={config.account_connectors || []}
        workerOn={workerOn}
        onChange={next => patch({ account_connectors: next })} />

      <h4 className="mcp-section">MCP server riêng của dự án <em>(nâng cao — cần credential)</em></h4>
      {config.servers.length === 0 && (
        <div className="mcp-empty">Chưa khai server nào.</div>
      )}

      {config.servers.map((s, i) => {
        const t = tpl(s.template);
        const st = statusOf(s.name);
        const prof = t?.profiles.find(p => p.name === s.profile);
        return (
          <div key={i} className={"mcp-row" + (s.enabled ? "" : " off")}>
            <div className="mcp-row-head">
              <label className="mcp-on">
                <input type="checkbox" checked={s.enabled}
                       onChange={e => patchServer(i, { enabled: e.target.checked })} />
              </label>
              <strong>{s.name}</strong>
              <span className="mcp-tpl">{s.template}</span>
              {st && <span className={"mcp-state " + (st === "connected" ? "ok" : "bad")}>{st}</span>}
              {t?.needs_credential && (
                <span className={"mcp-cred " + (s.credential_declared ? "ok" : "bad")}>
                  credential: {s.credential_declared ? "đã khai" : "thiếu"}
                </span>
              )}
              <button className="mcp-del"
                      onClick={() => patch({ servers: config.servers.filter((_, j) => j !== i) })}>
                Xoá
              </button>
            </div>

            <div className="mcp-row-body">
              <label>
                Hồ sơ quyền
                <select value={s.profile} onChange={e => patchServer(i, { profile: e.target.value })}>
                  {(t?.profiles || []).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
              </label>
              {prof && (
                <span className="mcp-tools" title={prof.tools.join(", ")}>
                  {prof.tools.length} tool được phép
                </span>
              )}
              {s.template === "google-drive-files" && (
                <GoogleConnect slug={slug} server={s.name} />
              )}
              {s.template === "figma" && <FigmaConnect slug={slug} server={s.name} />}
              {t?.needs_credential && !s.credential_declared && !CONNECT_UI.has(s.template) && (
                <span className="mcp-hint warn inline">
                  Thêm <code>[mcp.{s.name}]</code> với khoá <code>credentials_path</code> vào
                  <code> clients/{slug}/settings.local.toml</code> trên host.
                </span>
              )}
            </div>
          </div>
        );
      })}

      {adding ? (
        <div className="mcp-add">
          <input placeholder="tên server (a-z, 0-9, _, -)" value={newName}
                 onChange={e => setNewName(e.target.value)} />
          <select value={newTemplate} onChange={e => {
            const next = e.target.value;
            // Tên do mình tự đặt — gợi ý sẵn theo mẫu, nhưng không đè tên người dùng đã gõ.
            if (!newName.trim() || newName === suggestName(newTemplate, config.servers)) {
              setNewName(suggestName(next, config.servers));
            }
            setNewTemplate(next);
          }}>
            <option value="">— chọn mẫu —</option>
            {templates.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
          <button onClick={addServer} disabled={!newName.trim() || !newTemplate}>Thêm</button>
          <button className="ghost" onClick={() => setAdding(false)}>Huỷ</button>
          <p className="mcp-hint" style={{ flexBasis: "100%", margin: "6px 0 0" }}>
            Tên server là tên <b>bạn tự đặt</b> để phân biệt các server trong dự án, không phải lấy từ đâu.
            Tên này phải trùng với mục <code>[mcp.&lt;tên&gt;]</code> khai <code>credentials_path</code> trong{" "}
            <code>clients/{slug}/settings.local.toml</code>, và agent sẽ thấy tool dạng{" "}
            <code>mcp__&lt;tên&gt;__…</code>.
          </p>
        </div>
      ) : (
        <button className="mcp-add-btn" onClick={() => setAdding(true)}>+ Thêm server</button>
      )}

      <div className="mcp-actions">
        <button onClick={() => save(config)} disabled={saving || !config.writable}>
          {saving ? "Đang lưu…" : "Lưu"}
        </button>
        {error && <span className="mcp-err">{error}</span>}
      </div>

      <p className="mcp-hint small">
        Chỉ chạy được server có trong danh sách mẫu. Thêm mẫu mới phải sửa
        <code> config/mcp_templates.toml</code> trên host — cố ý, vì mỗi mẫu là một tiến trình
        chạy trên máy bạn.
      </p>
    </div>
  );
}

const CONNECTOR_STATE: Record<string, { label: string; cls: string }> = {
  connected:    { label: "đã kết nối", cls: "ok" },
  "needs-auth": { label: "chưa cấp quyền", cls: "bad" },
  failed:       { label: "lỗi", cls: "bad" },
  unknown:      { label: "chưa rõ", cls: "" },
};

/**
 * Connector claude.ai (Google Drive, Gmail…) của tài khoản Claude mà worker đăng
 * nhập. Kết nối/cấp quyền làm ở phía Claude — chỗ này chỉ chọn dự án nào được dùng.
 */
function AccountConnectors({ connectors, selected, workerOn, onChange }: {
  connectors: AccountConnector[];
  selected: string[];
  workerOn: boolean | null;
  onChange: (next: string[]) => void;
}) {
  // Connector đã tick nhưng worker không còn báo (đổi tài khoản…) vẫn phải hiện để bỏ tick được.
  const rows: AccountConnector[] = [
    ...connectors,
    ...selected.filter(n => !connectors.some(c => c.name === n))
               .map(n => ({ name: n, status: "unknown" as const })),
  ];
  const toggle = (name: string, on: boolean) =>
    onChange(on ? [...selected, name] : selected.filter(n => n !== name));
  const needsAuth = rows.some(c => c.status === "needs-auth");

  return (
    <div className="mcp-connectors">
      <h4 className="mcp-section">Connector của tài khoản Claude</h4>
      {rows.length === 0 ? (
        <div className="mcp-empty">
          {workerOn === false
            ? "Worker đang tắt nên chưa có danh sách connector. Chạy python worker.py rồi tải lại."
            : "Worker chưa báo danh sách connector (dò mỗi 10 phút, lần đầu ngay khi khởi động). Tải lại sau ít giây."}
        </div>
      ) : (
        <div className="mcp-conn-list">
          {rows.map(c => {
            const st = CONNECTOR_STATE[c.status] || CONNECTOR_STATE.unknown;
            const on = selected.includes(c.name);
            return (
              <label key={c.name} className={"mcp-conn" + (on ? " on" : "")}>
                <input type="checkbox" checked={on}
                       disabled={!on && c.status !== "connected"}
                       onChange={e => toggle(c.name, e.target.checked)} />
                <span>{c.name}</span>
                <span className={"mcp-state " + st.cls}>{st.label}</span>
              </label>
            );
          })}
        </div>
      )}
      {needsAuth && (
        <p className="mcp-hint small">
          Connector <b>chưa cấp quyền</b> thì chưa tick được. Trên máy chạy worker: mở terminal, chạy
          <code> claude</code>, gõ <code>/mcp</code> → chọn connector → <b>Authenticate</b>. Kết nối trên
          claude.ai cũng được, miễn là đúng tài khoản worker đang đăng nhập (<code>claude auth status</code>).
        </p>
      )}
    </div>
  );
}

/**
 * Nút "Kết nối Google" của 1 server google-drive-files: đăng nhập bằng tài khoản
 * Google của CHÍNH dự án này (OAuth). Token nằm trên máy (clients/<slug>/secrets/),
 * giao diện chỉ thấy email đã kết nối.
 */
function GoogleConnect({ slug, server }: { slug: string; server: string }) {
  const [client, setClient] = useState<{ configured: boolean; redirect_uri: string } | null>(null);
  const [st, setSt] = useState<{ connected: boolean; account: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [jsonText, setJsonText] = useState("");
  const base = `/api/mcp/google/${encodeURIComponent(slug)}/${encodeURIComponent(server)}`;

  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([fetch("/api/mcp/google/client"), fetch(base)]);
      if (c.ok) setClient(await c.json());
      if (s.ok) setSt(await s.json());
    } catch { /* API tạm mất — giữ trạng thái cũ */ }
  }, [base]);

  useEffect(() => {
    load();
    // Tab Google báo xong (postMessage) hoặc người dùng quay lại tab này → đọc lại.
    const onMsg = (e: MessageEvent) => { if (e.data === "google-oauth-done") load(); };
    window.addEventListener("message", onMsg);
    window.addEventListener("focus", load);
    return () => { window.removeEventListener("message", onMsg); window.removeEventListener("focus", load); };
  }, [load]);

  const call = async (url: string, init?: RequestInit) => {
    setBusy(true); setErr(null);
    try {
      const res = await fetch(url, init);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(body.detail || `Lỗi HTTP ${res.status}`); return null; }
      return body;
    } catch { setErr("Không gọi được API."); return null; }
    finally { setBusy(false); }
  };

  const connect = async () => {
    const body = await call(`${base}/connect`, { method: "POST" });
    if (body?.url) window.open(body.url, "_blank");   // giữ opener: tab Google postMessage báo xong
  };
  const disconnect = async () => {
    if (!confirm(`Ngắt kết nối Google của server "${server}"? Token sẽ bị thu hồi.`)) return;
    const body = await call(`${base}/disconnect`, { method: "POST" });
    if (body) setSt(body);
  };
  const saveClient = async () => {
    const body = await call("/api/mcp/google/client", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_text: jsonText }),
    });
    if (body) { setClient(body); setJsonText(""); }
  };

  if (!client || !st) return null;

  if (!client.configured) {
    return (
      <div className="mcp-google setup">
        <b>Kết nối Google — cần cấu hình 1 lần cho cả hệ thống (admin)</b>
        <ol>
          <li>Google Cloud Console → <i>Google Auth Platform</i> (OAuth consent screen): User type
            <b> External</b>, rồi <b>Publish app</b> sang <b>In production</b> — để ở Testing thì
            token tự hết hạn sau 7 ngày.</li>
          <li><i>Credentials → Create credentials → OAuth client ID</i>, loại <b>Web application</b>.
            Ở <i>Authorized redirect URIs</i> thêm đúng:<br />
            <code className="copy" onClick={() => navigator.clipboard?.writeText(client.redirect_uri)}
                  title="Bấm để chép">{client.redirect_uri}</code></li>
          <li>Bấm <b>Download JSON</b>, mở file bằng Notepad, dán toàn bộ nội dung vào ô dưới rồi Lưu.</li>
        </ol>
        <textarea rows={3} placeholder='{"web":{"client_id":"…","client_secret":"…", …}}'
                  value={jsonText} onChange={e => setJsonText(e.target.value)} />
        <div className="mcp-google-row">
          <button onClick={saveClient} disabled={busy || !jsonText.trim()}>Lưu OAuth client</button>
          {err && <span className="mcp-err">{err}</span>}
        </div>
      </div>
    );
  }

  return (
    <div className="mcp-google">
      {st.connected ? (
        <div className="mcp-google-row">
          <span className="mcp-state ok">Google: {st.account || "đã kết nối"}</span>
          <button className="ghost" onClick={connect} disabled={busy}>Đổi tài khoản</button>
          <button className="ghost" onClick={disconnect} disabled={busy}>Ngắt kết nối</button>
        </div>
      ) : (
        <div className="mcp-google-row">
          <button onClick={connect} disabled={busy}>🔗 Kết nối Google</button>
          <span className="mcp-hint inline">
            Đăng nhập tài khoản Google của dự án này. Màn hình "Google chưa xác minh ứng dụng" →
            <b> Nâng cao → Tiếp tục</b>, tick quyền Google Drive.
          </span>
        </div>
      )}
      {err && <span className="mcp-err">{err}</span>}
    </div>
  );
}

/**
 * Kết nối Figma của 1 server mẫu `figma`: dán personal access token của dự án này.
 * API kiểm token với Figma rồi lưu trên máy — giao diện chỉ thấy email tài khoản.
 */
function FigmaConnect({ slug, server }: { slug: string; server: string }) {
  const [st, setSt] = useState<{ connected: boolean; account: string | null } | null>(null);
  const [tok, setTok] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const base = `/api/mcp/figma/${encodeURIComponent(slug)}/${encodeURIComponent(server)}`;

  useEffect(() => {
    fetch(base).then(r => (r.ok ? r.json() : null)).then(d => d && setSt(d)).catch(() => {});
  }, [base]);

  const call = async (url: string, body?: object) => {
    setBusy(true); setErr(null);
    try {
      const res = await fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setErr(d.detail || `Lỗi HTTP ${res.status}`); return; }
      setSt(d); setTok(""); setEditing(false);
    } catch { setErr("Không gọi được API."); }
    finally { setBusy(false); }
  };

  if (!st) return null;

  if (st.connected && !editing) {
    return (
      <div className="mcp-google">
        <div className="mcp-google-row">
          <span className="mcp-state ok">Figma: {st.account || "đã kết nối"}</span>
          <button className="ghost" onClick={() => setEditing(true)} disabled={busy}>Đổi token</button>
          <button className="ghost" disabled={busy}
                  onClick={() => confirm(`Ngắt kết nối Figma của server "${server}"?`) && call(`${base}/disconnect`)}>
            Ngắt kết nối
          </button>
        </div>
        {err && <span className="mcp-err">{err}</span>}
      </div>
    );
  }

  return (
    <div className="mcp-google setup">
      <b>Kết nối Figma cho dự án này</b>
      <ol>
        <li>Mở Figma → bấm avatar → <b>Settings</b> → tab <b>Security</b> → <i>Personal access tokens</i> →
          <b> Generate new token</b>.</li>
        <li>Đặt tên (vd <code>ai-team-{slug}</code>), chọn hạn dùng, ở <i>Scopes</i> cho
          <b> File content: Read</b> và <b>Comments: Read</b>. Bấm Generate rồi chép token (bắt đầu bằng
          <code> figd_</code>) — Figma chỉ hiện 1 lần.</li>
        <li>Dán vào ô dưới. Tài khoản Figma này phải <b>xem được</b> file thiết kế của dự án.</li>
      </ol>
      <div className="mcp-google-row">
        <input type="password" placeholder="figd_…" value={tok} autoComplete="off"
               onChange={e => setTok(e.target.value)} style={{ flex: 1, minWidth: 240 }} />
        <button onClick={() => call(base, { token: tok })} disabled={busy || !tok.trim()}>
          {busy ? "Đang kiểm tra…" : "Kết nối Figma"}
        </button>
        {editing && <button className="ghost" onClick={() => setEditing(false)}>Huỷ</button>}
      </div>
      {err && <span className="mcp-err">{err}</span>}
    </div>
  );
}
