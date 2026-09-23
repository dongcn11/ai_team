import { useState } from "react";
import { useMcp, McpConfig, McpServer } from "../hooks/useMcp";

/**
 * Tab MCP của một dự án.
 *
 * Nguồn sự thật là file clients/<slug>/mcp.json — sửa ở đây hay sửa bằng editor
 * đều được. Credential KHÔNG đi qua đây: nó nằm trong settings.local.toml trên
 * host, giao diện chỉ hiện "đã khai / chưa khai".
 */
export default function ProjectMcp({ slug }: { slug: string }) {
  const { config, setConfig, templates, runtime, workerOn, saving, error, save } = useMcp(slug);
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
        Mỗi dự án có bộ MCP server riêng. Bước của dự án này chỉ thấy những server khai ở đây —
        không thấy server của dự án khác, và cũng không thấy connector gắn với tài khoản Claude.
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
              {t?.needs_credential && !s.credential_declared && (
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
          <select value={newTemplate} onChange={e => setNewTemplate(e.target.value)}>
            <option value="">— chọn mẫu —</option>
            {templates.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
          </select>
          <button onClick={addServer} disabled={!newName.trim() || !newTemplate}>Thêm</button>
          <button className="ghost" onClick={() => setAdding(false)}>Huỷ</button>
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
