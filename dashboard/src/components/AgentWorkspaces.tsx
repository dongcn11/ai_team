import { useCallback, useEffect, useState } from "react";

/**
 * Thư mục & tài khoản git RIÊNG cho từng agent dev của 1 project.
 *
 * Một project có thể có 3 "ông dev" (BE, FE, fullstack), mỗi ông một repo và một
 * tài khoản GitHub. Không khai gì thì BE làm trong backend/, FE trong frontend/,
 * fullstack ở gốc, và cả ba dùng token chung của project. Khai ở đây thì agent
 * đó thắng.
 *
 * Thư mục → settings.toml [agents] <key>_directory (commit được).
 * Token   → settings.local.toml [git.<key>] (không vào git, không qua DB).
 */
type AgentGit = { configured: boolean; hint: string; username: string; own: boolean };
type AgentWs = {
  key: string; name: string;
  directory: string;                 // giá trị khai riêng ("" = chưa khai)
  effective: string;                 // thư mục thật sự sẽ dùng
  source: "own" | "area" | "root";
  git: AgentGit;
};

const SOURCE_LABEL: Record<AgentWs["source"], string> = {
  own:  "riêng",
  area: "theo vùng BE/FE",
  root: "gốc thư mục code",
};

export default function AgentWorkspaces({ projectId }: { projectId: string }) {
  const [items,   setItems]   = useState<AgentWs[] | null>(null);
  const [editDir, setEditDir] = useState<string | null>(null);   // key đang sửa thư mục
  const [editGit, setEditGit] = useState<string | null>(null);   // key đang sửa token
  const [dirDraft,  setDirDraft]  = useState("");
  const [tokDraft,  setTokDraft]  = useState("");
  const [userDraft, setUserDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState("");

  const load = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/agent-workspaces`);
    if (res.ok) setItems(await res.json());
  }, [projectId]);

  useEffect(() => { load(); setEditDir(null); setEditGit(null); }, [load]);

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
      setEditDir(null); setEditGit(null);
      setTokDraft(""); setUserDraft("");
    } else {
      const d = await res.json().catch(() => ({}));
      setError(d.detail || "Không lưu được");
    }
    setSaving(false);
  };

  if (items === null) return null;
  if (items.length === 0) {
    return <div className="pd-field-note" style={{ marginTop: 0 }}>Project chưa có agent dev nào (be1/fe1/fs1…).</div>;
  }

  return (
    <div className="aw-list">
      {error && <div className="pd-field-warn">{error}</div>}
      {items.map(a => (
        <div key={a.key} className="aw-row">
          <div className="aw-name">
            <strong>{a.name}</strong>
            <code>{a.key}</code>
          </div>

          {/* Thư mục */}
          <div className="aw-cell">
            <div className="pd-field-label">Thư mục</div>
            {editDir === a.key ? (
              <div className="pd-field-edit">
                <input className="pd-field-input" autoFocus placeholder="C:/www/my_api — trống = theo vùng mặc định"
                  value={dirDraft} onChange={e => setDirDraft(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter") put(a.key, { directory: dirDraft });
                    if (e.key === "Escape") setEditDir(null);
                  }} />
                <button className="pd-icon-btn ok" disabled={saving} onClick={() => put(a.key, { directory: dirDraft })}>✓</button>
                <button className="pd-icon-btn" disabled={saving} onClick={() => setEditDir(null)}>✕</button>
              </div>
            ) : (
              <button type="button" className="pd-field-value"
                onClick={() => { setDirDraft(a.directory); setEditDir(a.key); }}
                title={`Đang dùng: ${a.effective} (${SOURCE_LABEL[a.source]}). Nhấn để đổi.`}>
                <span className={a.source === "own" ? "" : "pd-field-empty"}>
                  📂 {a.effective}
                  {a.source !== "own" && <> · {SOURCE_LABEL[a.source]}</>}
                </span>
                <span className="pd-field-pen">✏️</span>
              </button>
            )}
          </div>

          {/* Tài khoản git */}
          <div className="aw-cell">
            <div className="pd-field-label">Tài khoản git</div>
            {editGit === a.key ? (
              <div className="pd-field-edit">
                <input className="pd-field-input" type="password" autoFocus
                  placeholder="ghp_… (token riêng của agent này)"
                  value={tokDraft} onChange={e => setTokDraft(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && tokDraft.trim()) put(a.key, { token: tokDraft.trim(), username: userDraft });
                    if (e.key === "Escape") setEditGit(null);
                  }} />
                <input className="pd-field-input pd-field-input-sm" placeholder="tài khoản"
                  value={userDraft} onChange={e => setUserDraft(e.target.value)} />
                <button className="pd-icon-btn ok" disabled={saving || !tokDraft.trim()}
                  onClick={() => put(a.key, { token: tokDraft.trim(), username: userDraft })}
                  title="Lưu vào settings.local.toml [git.<key>]">✓</button>
                {a.git.own && (
                  <button className="pd-icon-btn danger" disabled={saving} onClick={() => put(a.key, { token: "" })}
                    title="Xoá token riêng — agent này dùng lại token chung của project">Xoá</button>
                )}
                <button className="pd-icon-btn" disabled={saving} onClick={() => setEditGit(null)}>✕</button>
              </div>
            ) : (
              <button type="button" className="pd-field-value"
                onClick={() => { setUserDraft(a.git.own ? a.git.username : ""); setEditGit(a.key); }}
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
      ))}
      <div className="pd-field-note">
        Không khai thì BE làm trong <code>backend/</code>, FE trong <code>frontend/</code>, fullstack ở
        gốc, và dùng token chung ở mục GitHub bên dưới. Khai riêng khi mỗi agent là một repo /
        một tài khoản khác nhau.
      </div>
    </div>
  );
}
