import { useCallback, useEffect, useState } from "react";

/**
 * Bộ thư mục code & tài khoản git RIÊNG cho từng agent dev của 1 project.
 *
 * Mỗi agent có đủ bộ như project: thư mục gốc, bố trí (tách BE/FE hay gộp),
 * thư mục backend/frontend — và một tài khoản git. Khai cái nào thì cái đó
 * thắng, còn lại thừa kế từ project. Dùng khi 3 "ông dev" (BE, FE, fullstack)
 * mỗi ông một repo, một tài khoản.
 *
 * Thư mục → settings.toml [agents] <key>_directory / _layout / _backend_directory /
 *           _frontend_directory (commit được).
 * Token   → settings.local.toml [git.<key>] (không vào git, không qua DB).
 */
type AgentGit = { configured: boolean; hint: string; username: string; own: boolean };
type Own = { directory: string; layout: string; backend_directory: string; frontend_directory: string };
type AgentWs = {
  key: string; name: string;
  root: string;                            // thư mục gốc thật sự dùng
  layout: "split" | "mono";
  areas: { backend?: string; frontend?: string };
  workdir: string;                         // chỗ agent sẽ ghi code
  own: Own;                                // trường nào khai riêng ("" = thừa kế)
  git: AgentGit;
};
type DirField = "directory" | "backend_directory" | "frontend_directory";

const isAbs = (p: string) => /^[A-Za-z]:[\\/]/.test(p) || p.startsWith("/");

export default function AgentWorkspaces({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<AgentWs[] | null>(null);
  // Ô đang sửa: "<key>:<field>" — mỗi lúc một ô, giống hàng cấu hình của project
  const [editing, setEditing] = useState<string | null>(null);
  const [draft,   setDraft]   = useState("");
  const [tokDraft,  setTokDraft]  = useState("");
  const [userDraft, setUserDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState("");

  const load = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/agent-workspaces`);
    if (res.ok) setItems(await res.json());
  }, [projectId]);

  useEffect(() => { load(); setEditing(null); }, [load]);

  const put = async (key: string, body: object) => {
    setSaving(true);
    setError("");
    const res = await fetch(`/api/projects/${projectId}/agent-workspaces/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      await load();
      setEditing(null);
      setTokDraft(""); setUserDraft("");
    } else {
      const d = await res.json().catch(() => ({}));
      setError(d.detail || "Không lưu được");
    }
    setSaving(false);
  };

  const cancel = () => { setEditing(null); setDraft(""); };

  /** Ô đường dẫn: hiện giá trị đang dùng, mờ nếu thừa kế từ project. */
  const dirField = (a: AgentWs, field: DirField, label: string, effective: string, hint: string) => {
    const id  = `${a.key}:${field}`;
    const own = a.own[field];
    return (
      <div className="pd-field" key={id}>
        <div className="pd-field-label">{label}</div>
        {editing === id ? (
          <div className="pd-field-edit">
            <input className="pd-field-input" autoFocus placeholder={`trống = ${hint}`}
              value={draft} onChange={e => setDraft(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") put(a.key, { [field]: draft });
                if (e.key === "Escape") cancel();
              }} />
            <button className="pd-icon-btn ok" disabled={saving} onClick={() => put(a.key, { [field]: draft })}>✓</button>
            {own && (
              <button className="pd-icon-btn danger" disabled={saving} onClick={() => put(a.key, { [field]: "" })}
                title="Xoá — quay về thừa kế từ project">Xoá</button>
            )}
            <button className="pd-icon-btn" disabled={saving} onClick={cancel}>✕</button>
          </div>
        ) : (
          <button type="button" className="pd-field-value"
            onClick={() => { setDraft(own); setEditing(id); }}
            title={own ? "Khai riêng cho agent này. Nhấn để sửa hoặc xoá." : `Thừa kế: ${hint}. Nhấn để khai riêng.`}>
            <span className={own ? "" : "pd-field-empty"}>
              📂 {effective}{own ? "" : " · thừa kế"}
            </span>
            {own && isAbs(own) && <span className="pd-field-flag" title="Đường dẫn tuyệt đối — dashboard trong Docker không đọc được, chỉ agent trên máy bạn ghi được">⚠</span>}
            <span className="pd-field-pen">✏️</span>
          </button>
        )}
      </div>
    );
  };

  if (items === null) return null;
  if (items.length === 0) {
    return <div className="pd-field-note" style={{ marginTop: 0 }}>Project chưa có agent dev nào (be1/fe1/fs1…).</div>;
  }

  return (
    <div className="aw-list">
      {error && <div className="pd-field-warn">{error}</div>}
      {items.map(a => {
        const gitId = `${a.key}:git`;
        const custom = Boolean(a.own.directory || a.own.layout || a.own.backend_directory || a.own.frontend_directory);
        return (
          <div key={a.key} className="aw-card">
            <div className="aw-card-head">
              <strong>{a.name}</strong>
              <code>{a.key}</code>
              <span className="aw-card-work" title="Thư mục agent này sẽ ghi code vào">
                → làm trong <code>{a.workdir}</code>
              </span>
              {!custom && <span className="aw-card-tag">theo project</span>}
            </div>

            <div className="pd-config-grid">
              {dirField(a, "directory", "Thư mục code", a.root, "thư mục code của project")}

              <div className="pd-field">
                <div className="pd-field-label">Bố trí code</div>
                <div className="pd-seg">
                  <button type="button" disabled={saving}
                    className={a.layout !== "mono" ? "on" : ""}
                    onClick={() => put(a.key, { layout: "split" })}
                    title="Code của agent này tách backend/ và frontend/">🧩 Tách BE/FE</button>
                  <button type="button" disabled={saving}
                    className={a.layout === "mono" ? "on" : ""}
                    onClick={() => put(a.key, { layout: "mono" })}
                    title="Code nằm thẳng trong thư mục code (Laravel Blade, WordPress…)">🧱 Gộp 1 thư mục</button>
                  {a.own.layout && (
                    <button type="button" disabled={saving} className="aw-seg-reset"
                      onClick={() => put(a.key, { layout: "" })}
                      title="Bỏ khai riêng — theo bố trí của project">↺</button>
                  )}
                </div>
              </div>

              {a.layout !== "mono" && (
                <>
                  {dirField(a, "backend_directory", "Thư mục backend", a.areas.backend || "", `${a.root}/backend`)}
                  {dirField(a, "frontend_directory", "Thư mục frontend", a.areas.frontend || "", `${a.root}/frontend`)}
                </>
              )}

              {/* Tài khoản git */}
              <div className="pd-field">
                <div className="pd-field-label">Tài khoản git</div>
                {editing === gitId ? (
                  <div className="pd-field-edit">
                    <input className="pd-field-input" type="password" autoFocus
                      placeholder="ghp_… (token riêng của agent này)"
                      value={tokDraft} onChange={e => setTokDraft(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && tokDraft.trim()) put(a.key, { token: tokDraft.trim(), username: userDraft });
                        if (e.key === "Escape") cancel();
                      }} />
                    <input className="pd-field-input pd-field-input-sm" placeholder="tài khoản"
                      value={userDraft} onChange={e => setUserDraft(e.target.value)} />
                    <button className="pd-icon-btn ok" disabled={saving || !tokDraft.trim()}
                      onClick={() => put(a.key, { token: tokDraft.trim(), username: userDraft })}
                      title="Lưu vào settings.local.toml [git.<key>]">✓</button>
                    {a.git.own && (
                      <button className="pd-icon-btn danger" disabled={saving} onClick={() => put(a.key, { token: "" })}
                        title="Xoá token riêng — dùng lại token chung của project">Xoá</button>
                    )}
                    <button className="pd-icon-btn" disabled={saving} onClick={cancel}>✕</button>
                  </div>
                ) : (
                  <button type="button" className="pd-field-value"
                    onClick={() => { setUserDraft(a.git.own ? a.git.username : ""); setEditing(gitId); }}
                    title={a.git.own
                      ? "Token riêng của agent này (settings.local.toml). Nhấn để thay hoặc xoá."
                      : a.git.configured
                      ? "Đang dùng token chung của project. Nhấn để cấp token riêng."
                      : "Chưa có token nào — push sẽ bị Git Credential Manager hỏi. Nhấn để dán."}>
                    <span className={a.git.own ? "" : "pd-field-empty"}>
                      {a.git.configured
                        ? `🔑 ${a.git.hint}${a.git.username ? ` · ${a.git.username}` : ""}${a.git.own ? "" : " · chung project"}`
                        : "chưa có token"}
                    </span>
                    <span className="pd-field-pen">✏️</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
      <div className="pd-field-note">
        Ô mờ = đang thừa kế từ cấu hình project ở trên. Khai riêng khi agent đó làm ở một repo
        khác — vd ông fullstack có repo <code>C:/www/my_app</code> tách <code>api/</code> + <code>web/</code>,
        ông BE làm repo legacy gộp 1 thư mục.
      </div>
    </div>
  );
}
