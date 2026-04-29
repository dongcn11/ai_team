import React, { useState, useCallback, useEffect } from "react";
import { useProjects } from "../hooks/useProjects";
import { Project, AgentFS, RunSummary } from "../types";

const VALID_KEYS = ["pm","scrum","analyst","be1","be2","fe1","fe2","fs1","fs2","leader"];
const DEFAULT_MODELS: Record<string,string> = { opencode: "opencode/qwen3.5-plus", claude: "" };

export default function ProjectsPage() {
  const { projects, loading, error, refetch } = useProjects();
  const [selected,    setSelected]    = useState<Project | null>(null);
  const [projRuns,    setProjRuns]    = useState<RunSummary[]>([]);
  const [activeTab,   setActiveTab]   = useState<"agents" | "prd" | "runs" | "docs">("agents");

  // Agent management
  const [settingsAgents, setSettingsAgents] = useState<AgentFS[]>([]);
  const [showAddAgent,   setShowAddAgent]   = useState(false);
  const [addKey,         setAddKey]         = useState("be1");
  const [addTool,        setAddTool]        = useState("opencode");
  const [addModel,       setAddModel]       = useState("opencode/qwen3.5-plus");
  const [addSaving,      setAddSaving]      = useState(false);

  // PRD
  const [prdContent,  setPrdContent]  = useState<string | null>(null);
  const [prdExists,   setPrdExists]   = useState(false);
  const [prdEditing,  setPrdEditing]  = useState(false);
  const [prdDraft,    setPrdDraft]    = useState("");
  const [prdSaving,   setPrdSaving]   = useState(false);

  // Docs
  const [docFiles,    setDocFiles]    = useState<{path: string; name: string; size: number}[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [docContent,  setDocContent]  = useState<string | null>(null);
  const [docLoading,  setDocLoading]  = useState(false);

  const openProject = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}`);
    if (res.ok) {
      setSelected(await res.json());
      setActiveTab("agents");
      setPrdContent(null); setPrdEditing(false);
      setDocFiles([]); setSelectedDoc(null); setDocContent(null);
      setShowAddAgent(false);
    }
  }, []);

  const loadSettingsAgents = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/settings-agents`);
    if (res.ok) setSettingsAgents(await res.json());
  }, []);

  useEffect(() => {
    if (selected) loadSettingsAgents(selected.id);
  }, [selected, loadSettingsAgents]);

  useEffect(() => {
    if (!selected) return;
    (async () => {
      const res = await fetch(`/api/runs?client=${selected.id}&limit=10`);
      if (res.ok) setProjRuns(await res.json());
    })();
  }, [selected]);

  const handleAddAgent = async () => {
    if (!selected) return;
    setAddSaving(true);
    const res = await fetch(`/api/projects/${selected.id}/settings-agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: addKey, tool: addTool, model: addModel }),
    });
    if (res.ok) { setSettingsAgents(await res.json()); setShowAddAgent(false); }
    setAddSaving(false);
  };

  const handleRemoveAgent = async (key: string) => {
    if (!selected) return;
    const res = await fetch(`/api/projects/${selected.id}/settings-agents/${key}`, { method: "DELETE" });
    if (res.ok) setSettingsAgents(await res.json());
  };

  const loadPrd = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/prd`);
    if (res.ok) {
      const data = await res.json();
      setPrdExists(data.exists);
      setPrdContent(data.content);
      setPrdDraft(data.content);
    }
  }, []);

  const savePrd = async () => {
    if (!selected) return;
    setPrdSaving(true);
    const res = await fetch(`/api/projects/${selected.id}/prd`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: prdDraft }),
    });
    if (res.ok) { setPrdContent(prdDraft); setPrdExists(true); setPrdEditing(false); }
    setPrdSaving(false);
  };

  const deletePrd = async () => {
    if (!selected || !window.confirm("Xóa prd.md?")) return;
    const res = await fetch(`/api/projects/${selected.id}/prd`, { method: "DELETE" });
    if (res.ok) { setPrdContent(""); setPrdExists(false); setPrdEditing(false); }
  };

  const loadDocs = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/docs`);
    if (res.ok) setDocFiles(await res.json());
  }, []);

  const loadDocContent = async (id: string, path: string) => {
    setDocLoading(true);
    setSelectedDoc(path);
    const res = await fetch(`/api/projects/${id}/docs/content?path=${encodeURIComponent(path)}`);
    if (res.ok) { const d = await res.json(); setDocContent(d.content); }
    setDocLoading(false);
  };

  const availableKeys = VALID_KEYS.filter(k => !settingsAgents.find(a => a.key === k));

  if (loading) return <div className="state">Loading projects...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Projects</h2>
        <button className="btn-muted" onClick={refetch}>↻ Refresh</button>
      </div>

      {selected && (
        <div className="card" style={{ marginBottom: 20 }}>
          {/* Header */}
          <div className="project-detail-header">
            <div>
              <h3>{selected.name}</h3>
              <div className="project-meta-links">
                <span className="project-link" style={{ background: "#172554", borderColor: "#3b82f655" }}>
                  <span className="project-link-icon">&#x1f4c1;</span> clients/{selected.id}
                </span>
                {selected.tech_stack?.backend && (
                  <span className="project-link" style={{ background: "#1a2e1a", borderColor: "#22c55e55" }}>
                    BE: {selected.tech_stack.backend}
                  </span>
                )}
                {selected.tech_stack?.frontend && (
                  <span className="project-link" style={{ background: "#1e1a2e", borderColor: "#a855f755" }}>
                    FE: {selected.tech_stack.frontend}
                  </span>
                )}
              </div>
            </div>
            <button className="btn-muted" onClick={() => { setSelected(null); setShowAddAgent(false); setPrdEditing(false); }}>Close</button>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, marginTop: 16, borderBottom: "1px solid #1e293b" }}>
            {(["agents","prd","runs","docs"] as const).map(tab => (
              <button key={tab}
                onClick={() => {
                  setActiveTab(tab);
                  if (tab === "prd" && prdContent === null) loadPrd(selected.id);
                  if (tab === "docs" && docFiles.length === 0) loadDocs(selected.id);
                }}
                style={{ padding: "6px 16px", background: activeTab === tab ? "#1e293b" : "none", border: "none",
                  borderRadius: "6px 6px 0 0", color: activeTab === tab ? "#f1f5f9" : "#6b7280",
                  cursor: "pointer", fontSize: 13, fontWeight: activeTab === tab ? 600 : 400 }}>
                {tab === "agents" ? `Agents (${settingsAgents.length})`
                  : tab === "prd" ? "PRD"
                  : tab === "runs" ? `Runs (${projRuns.length})`
                  : `Docs${docFiles.length > 0 ? ` (${docFiles.length})` : ""}`}
              </button>
            ))}
          </div>

          {/* Agents tab */}
          {activeTab === "agents" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Agents ({settingsAgents.length})</h4>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 11, color: "#4b5563" }}>
                    <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>
                      clients/{selected.id}/settings.toml
                    </code>
                  </span>
                  {availableKeys.length > 0 && (
                    <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}
                      onClick={() => { setAddKey(availableKeys[0]); setShowAddAgent(v => !v); }}>
                      + Add Agent
                    </button>
                  )}
                </div>
              </div>

              {showAddAgent && (
                <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginTop: 8, display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Key</label>
                    <select className="setting-select" value={addKey} onChange={e => setAddKey(e.target.value)}>
                      {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tool</label>
                    <select className="setting-select" value={addTool}
                      onChange={e => { setAddTool(e.target.value); setAddModel(DEFAULT_MODELS[e.target.value] ?? ""); }}>
                      <option value="opencode">opencode</option>
                      <option value="claude">claude</option>
                    </select>
                  </div>
                  <div>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Model</label>
                    <input className="setting-input" style={{ width: 220 }} value={addModel}
                      onChange={e => setAddModel(e.target.value)} placeholder="e.g. opencode/qwen3.5-plus" />
                  </div>
                  <button className="btn-primary" disabled={addSaving || (addTool === "opencode" && !addModel.trim())} onClick={handleAddAgent}>
                    {addSaving ? "Saving..." : "Add"}
                  </button>
                  <button className="btn-muted" onClick={() => setShowAddAgent(false)}>Cancel</button>
                </div>
              )}

              {settingsAgents.length === 0
                ? <p style={{ color: "#6b7280", fontSize: 13, marginTop: 8 }}>No agents in settings.toml</p>
                : (
                  <div className="agent-chip-list" style={{ marginTop: 8 }}>
                    {settingsAgents.map(a => (
                      <div key={a.key} className="agent-chip" style={{ position: "relative", paddingRight: 28 }}>
                        <span>{a.name}</span>
                        <span className="agent-chip-role">{a.key}</span>
                        <span style={{ fontSize: 10, color: "#6b7280" }}>{a.tool} · {a.model}</span>
                        <button onClick={() => handleRemoveAgent(a.key)}
                          style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14, lineHeight: 1 }}
                          title="Remove">✕</button>
                      </div>
                    ))}
                  </div>
                )
              }
            </div>
          )}

          {/* PRD tab */}
          {activeTab === "prd" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>PRD — <code style={{ fontSize: 12, background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>clients/{selected.id}/prd.md</code></h4>
                <div style={{ display: "flex", gap: 8 }}>
                  {prdExists && !prdEditing && (
                    <>
                      <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setPrdDraft(prdContent ?? ""); setPrdEditing(true); }}>✏️ Edit</button>
                      <button className="btn-danger"  style={{ fontSize: 12, padding: "4px 10px" }} onClick={deletePrd}>Delete</button>
                    </>
                  )}
                  {prdEditing && (
                    <>
                      <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} disabled={prdSaving} onClick={savePrd}>{prdSaving ? "Saving..." : "💾 Save"}</button>
                      <button className="btn-muted"   style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setPrdEditing(false)}>Cancel</button>
                    </>
                  )}
                  {!prdExists && !prdEditing && (
                    <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { setPrdDraft("# PRD\n\n## Tổng quan\n\n"); setPrdEditing(true); }}>+ Tạo PRD</button>
                  )}
                </div>
              </div>
              {prdEditing ? (
                <textarea value={prdDraft} onChange={e => setPrdDraft(e.target.value)}
                  style={{ width: "100%", minHeight: 500, marginTop: 12, background: "#0f172a", color: "#e2e8f0", border: "1px solid #1e293b", borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 13, lineHeight: 1.6, resize: "vertical", boxSizing: "border-box" }} />
              ) : prdExists && prdContent ? (
                <pre style={{ marginTop: 12, background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 16, fontFamily: "monospace", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#e2e8f0", maxHeight: 600, overflowY: "auto" }}>
                  {prdContent}
                </pre>
              ) : (
                <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>Chưa có prd.md. Bấm "+ Tạo PRD" để bắt đầu.</p>
              )}
            </div>
          )}

          {/* Runs tab */}
          {activeTab === "runs" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Orchestrator Runs ({projRuns.length})</h4>
                <span style={{ fontSize: 11, color: "#4b5563" }}>
                  <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>
                    python main.py --config clients/{selected.id}/settings.toml --prd clients/{selected.id}/prd.md
                  </code>
                </span>
              </div>
              {projRuns.length === 0
                ? <p style={{ color: "#6b7280", fontSize: 12 }}>No runs yet.</p>
                : (
                  <div className="history-list">
                    {projRuns.map(r => (
                      <div key={r.id} className="history-row">
                        <span className="history-id">#{r.id}</span>
                        <span className="history-meta">{r.total_tasks} tasks</span>
                        <div className="history-bars">
                          {r.done_tasks > 0 && <span className="history-bar done" style={{ flex: r.done_tasks }} />}
                          {r.failed_tasks > 0 && <span className="history-bar failed" style={{ flex: r.failed_tasks }} />}
                          {r.total_tasks - r.done_tasks - r.failed_tasks > 0 && (
                            <span className="history-bar pending" style={{ flex: r.total_tasks - r.done_tasks - r.failed_tasks }} />
                          )}
                        </div>
                        <span className={`project-status-badge status-${r.status === "running" ? "active" : r.status === "done" ? "completed" : "archived"}`}>
                          {r.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )
              }
            </div>
          )}

          {/* Docs tab */}
          {activeTab === "docs" && (
            <div style={{ marginTop: 16 }}>
              {docFiles.length === 0 ? (
                <p style={{ color: "#6b7280", fontSize: 13 }}>Chưa có file output. Chạy orchestrator để tạo tài liệu.</p>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: selectedDoc ? "260px 1fr" : "1fr", gap: 12 }}>
                  <div style={{ borderRight: selectedDoc ? "1px solid #1e293b" : "none", paddingRight: selectedDoc ? 12 : 0 }}>
                    {docFiles.map(f => (
                      <div key={f.path} onClick={() => loadDocContent(selected.id, f.path)}
                        style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, fontSize: 12,
                          background: selectedDoc === f.path ? "#1e293b" : "transparent",
                          color: selectedDoc === f.path ? "#f1f5f9" : "#9ca3af",
                          fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                        title={f.path}>
                        {f.path}
                      </div>
                    ))}
                  </div>
                  {selectedDoc && (
                    <div>
                      <div style={{ fontSize: 11, color: "#4b5563", marginBottom: 8, fontFamily: "monospace" }}>{selectedDoc}</div>
                      {docLoading ? (
                        <div style={{ color: "#6b7280", fontSize: 13 }}>Loading...</div>
                      ) : (
                        <pre style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 16,
                          fontFamily: "monospace", fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap",
                          wordBreak: "break-word", color: "#e2e8f0", maxHeight: 600, overflowY: "auto", margin: 0 }}>
                          {docContent}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!selected && projects.length === 0 && (
        <div className="state">Không tìm thấy folder nào trong clients/. Tạo folder và thêm settings.toml.</div>
      )}

      <div className="project-grid">
        {projects.map(p => (
          <div key={p.id} className="project-card" onClick={() => openProject(p.id)}>
            <div className="project-card-top">
              <span className="project-card-name">{p.name}</span>
              <span className="project-link" style={{ fontSize: 10, padding: "2px 6px" }}>{p.id}</span>
            </div>
            {p.tech_stack?.backend && (
              <p className="project-card-desc" style={{ color: "#22c55e" }}>{p.tech_stack.backend}</p>
            )}
            <div className="project-card-meta">
              <span>{p.agent_count} agent{p.agent_count !== 1 ? "s" : ""}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
