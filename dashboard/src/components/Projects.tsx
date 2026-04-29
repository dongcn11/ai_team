import React, { useState, useCallback, useEffect } from "react";
import { useProjects } from "../hooks/useProjects";
import { Project, AgentFS, RunSummary } from "../types";

const VALID_KEYS = ["pm","scrum","analyst","be1","be2","fe1","fe2","fs1","fs2","leader"];
const DEFAULT_MODELS: Record<string,string> = { opencode: "opencode-go/qwen3.5-plus", claude: "" };
const OPENCODE_GO_MODELS = [
  { value: "opencode-go/qwen3.5-plus",    label: "qwen3.5-plus   (Go plan)"  },
  { value: "opencode-go/qwen3.6-plus",    label: "qwen3.6-plus   (Go plan)"  },
  { value: "opencode-go/minimax-m2.7",    label: "minimax-m2.7   (Go plan)"  },
  { value: "opencode-go/deepseek-v4-pro", label: "deepseek-v4-pro (Go plan)" },
  { value: "opencode-go/glm-5.1",         label: "glm-5.1        (Go plan)"  },
  { value: "opencode-go/mimo-v2.5-pro",   label: "mimo-v2.5-pro  (Go plan)"  },
  { value: "opencode/qwen3.5-plus",       label: "⚠️ qwen3.5-plus   (pay-per-use)" },
  { value: "opencode/qwen3.6-plus",       label: "⚠️ qwen3.6-plus   (pay-per-use)" },
  { value: "opencode/minimax-m2.7",       label: "⚠️ minimax-m2.7   (pay-per-use)" },
  { value: "other",                       label: "Nhập tay..."   },
];

export default function ProjectsPage() {
  const { projects, loading, error, refetch } = useProjects();
  const [selected,    setSelected]    = useState<Project | null>(null);
  const [projRuns,    setProjRuns]    = useState<RunSummary[]>([]);
  const [activeTab,   setActiveTab]   = useState<"features" | "agents" | "prd" | "runs" | "docs">("features");

  // Remove agent confirm dialog
  const AGENTS_WITH_WORKSPACE = ["be1","be2","fe1","fe2","fs1","fs2"];
  const [removeAgentKey,      setRemoveAgentKey]      = useState<string | null>(null);
  const [removeWithCleanup,   setRemoveWithCleanup]   = useState(false);
  const [removedWorkspaceMsg, setRemovedWorkspaceMsg] = useState<string | null>(null);

  // New project form
  const [showNewProject,   setShowNewProject]   = useState(false);
  const [npFolderName,     setNpFolderName]     = useState("");
  const [npProfile,        setNpProfile]        = useState("fullstack");
  const [npTool,           setNpTool]           = useState("claude");
  const [npBackend,        setNpBackend]        = useState("");
  const [npFrontend,       setNpFrontend]       = useState("");
  const [npSaving,         setNpSaving]         = useState(false);
  const [npError,          setNpError]          = useState("");

  // Agent management
  const [settingsAgents, setSettingsAgents] = useState<AgentFS[]>([]);
  const [showAddAgent,   setShowAddAgent]   = useState(false);
  const [addKey,         setAddKey]         = useState("be1");
  const [addTool,        setAddTool]        = useState("opencode");
  const [addModel,       setAddModel]       = useState("opencode-go/qwen3.5-plus");
  const [addSaving,      setAddSaving]      = useState(false);

  // PRD
  const [prdContent,  setPrdContent]  = useState<string | null>(null);
  const [prdExists,   setPrdExists]   = useState(false);
  const [prdEditing,  setPrdEditing]  = useState(false);
  const [prdDraft,    setPrdDraft]    = useState("");
  const [prdSaving,   setPrdSaving]   = useState(false);

  // Features
  type Feature = { id: number; name: string; description: string | null; status: string; priority: string; created_at: string };
  const [features,        setFeatures]        = useState<Feature[]>([]);
  const [featuresLoaded,  setFeaturesLoaded]  = useState(false);
  const [showAddFeature,  setShowAddFeature]  = useState(false);
  const [featureName,     setFeatureName]     = useState("");
  const [featureDesc,     setFeatureDesc]     = useState("");
  const [featurePriority, setFeaturePriority] = useState("medium");
  const [featureSaving,   setFeatureSaving]   = useState(false);

  // Docs
  const [docFiles,    setDocFiles]    = useState<{path: string; name: string; size: number}[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [docContent,  setDocContent]  = useState<string | null>(null);
  const [docLoading,  setDocLoading]  = useState(false);

  const openProject = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}`);
    if (res.ok) {
      const proj = await res.json();
      setSelected(proj);
      setActiveTab("features");
      loadFeatures(proj.id);
      setPrdContent(null); setPrdEditing(false);
      setDocFiles([]); setSelectedDoc(null); setDocContent(null);
      setShowAddAgent(false);
      setFeatures([]); setFeaturesLoaded(false); setShowAddFeature(false);
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

  const confirmRemoveAgent = (key: string) => {
    setRemoveAgentKey(key);
    setRemoveWithCleanup(false);
    setRemovedWorkspaceMsg(null);
  };

  const handleRemoveAgent = async () => {
    if (!selected || !removeAgentKey) return;
    const url = `/api/projects/${selected.id}/settings-agents/${removeAgentKey}?cleanup=${removeWithCleanup}`;
    const res = await fetch(url, { method: "DELETE" });
    if (res.ok) {
      const data = await res.json();
      setSettingsAgents(data.agents);
      setRemovedWorkspaceMsg(data.deleted_workspace
        ? `Đã xóa workspace: ${data.deleted_workspace}`
        : null);
    }
    setRemoveAgentKey(null);
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

  const loadFeatures = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/features`);
    if (res.ok) { setFeatures(await res.json()); setFeaturesLoaded(true); }
  }, []);

  const addFeature = async () => {
    if (!selected || !featureName.trim()) return;
    setFeatureSaving(true);
    const res = await fetch(`/api/projects/${selected.id}/features`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: featureName.trim(), description: featureDesc.trim(), priority: featurePriority }),
    });
    if (res.ok) {
      const created = await res.json();
      setFeatures(prev => [...prev, created]);
      setFeatureName(""); setFeatureDesc(""); setFeaturePriority("medium");
      setShowAddFeature(false);
    }
    setFeatureSaving(false);
  };

  const deleteFeature = async (id: number) => {
    if (!selected || !window.confirm("Xóa feature này?")) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${id}`, { method: "DELETE" });
    if (res.ok) setFeatures(prev => prev.filter(f => f.id !== id));
  };

  const updateFeatureStatus = async (id: number, status: string) => {
    if (!selected) return;
    const res = await fetch(`/api/projects/${selected.id}/features/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (res.ok) {
      const updated = await res.json();
      setFeatures(prev => prev.map(f => f.id === id ? updated : f));
    }
  };

  const markFeatureDone = (id: number) => updateFeatureStatus(id, "done");

  const loadDocs = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}/docs`);
    if (res.ok) setDocFiles(await res.json());
  }, []);

  const loadDocContent = async (id: string, path: string, source: string = "code") => {
    setDocLoading(true);
    setSelectedDoc(path);
    const res = await fetch(`/api/projects/${id}/docs/content?path=${encodeURIComponent(path)}&source=${source}`);
    if (res.ok) { const d = await res.json(); setDocContent(d.content); }
    setDocLoading(false);
  };

  const availableKeys = VALID_KEYS.filter(k => !settingsAgents.find(a => a.key === k));

  const createProject = async () => {
    if (!npFolderName.trim()) return;
    setNpSaving(true); setNpError("");
    const res = await fetch("/api/projects/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder_name: npFolderName.trim(),
        profile:     npProfile,
        default_tool: npTool,
        backend:     npBackend.trim(),
        frontend:    npFrontend.trim(),
      }),
    });
    if (res.ok) {
      setShowNewProject(false);
      setNpFolderName(""); setNpBackend(""); setNpFrontend("");
      await refetch();
    } else {
      const d = await res.json().catch(() => ({}));
      setNpError(d.detail || "Lỗi tạo project");
    }
    setNpSaving(false);
  };

  if (loading) return <div className="state">Loading projects...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Projects</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-primary" onClick={() => { setShowNewProject(v => !v); setNpError(""); }}>+ New Project</button>
          <button className="btn-muted"   onClick={refetch}>↻ Refresh</button>
        </div>
      </div>

      {showNewProject && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h4 style={{ marginTop: 0, marginBottom: 16 }}>Tạo Project mới</h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên folder (slug) *</label>
              <input className="setting-input" placeholder="vd: my_project"
                value={npFolderName} onChange={e => setNpFolderName(e.target.value.toLowerCase().replace(/\s+/g, "_"))}
                onKeyDown={e => e.key === "Enter" && createProject()} />
              <div style={{ fontSize: 11, color: "#4b5563", marginTop: 4 }}>
                → clients/<strong>{npFolderName || "folder_name"}</strong>/
              </div>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Profile</label>
              <select className="setting-select" value={npProfile} onChange={e => setNpProfile(e.target.value)}>
                <option value="fullstack">fullstack — PM+Scrum+Analyst+BE1+BE2+FE1+FE2+Leader</option>
                <option value="dual_fullstack">dual_fullstack — PM+Scrum+Analyst+FS1+FS2+Leader</option>
                <option value="backend_only">backend_only — PM+Scrum+Analyst+BE1+BE2+Leader</option>
              </select>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Default tool</label>
              <select className="setting-select" value={npTool} onChange={e => setNpTool(e.target.value)}>
                <option value="claude">claude (Claude Code)</option>
                <option value="opencode">opencode</option>
              </select>
            </div>
            <div />
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Backend tech stack</label>
              <input className="setting-input" placeholder="Python FastAPI + SQLModel + SQLite"
                value={npBackend} onChange={e => setNpBackend(e.target.value)} />
            </div>
            {npProfile !== "backend_only" && (
              <div>
                <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Frontend tech stack</label>
                <input className="setting-input" placeholder="React + TypeScript + Vite + TailwindCSS"
                  value={npFrontend} onChange={e => setNpFrontend(e.target.value)} />
              </div>
            )}
          </div>
          {npError && <p style={{ color: "#ef4444", fontSize: 13, marginTop: 8 }}>{npError}</p>}
          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <button className="btn-primary" disabled={npSaving || !npFolderName.trim()} onClick={createProject}>
              {npSaving ? "Đang tạo..." : "Tạo Project"}
            </button>
            <button className="btn-muted" onClick={() => { setShowNewProject(false); setNpError(""); }}>Huỷ</button>
          </div>
        </div>
      )}

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
                <span className="project-link" style={{ background: "#1a1a1a", borderColor: "#374151", fontSize: 10 }}
                  title="Output directory (override bằng settings.local.toml)">
                  📂 {selected.output_dir}
                </span>
              </div>
            </div>
            <button className="btn-muted" onClick={() => { setSelected(null); setShowAddAgent(false); setPrdEditing(false); }}>Close</button>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, marginTop: 16, borderBottom: "1px solid #1e293b" }}>
            {(["features","agents","prd","runs","docs"] as const).map(tab => (
              <button key={tab}
                onClick={() => {
                  setActiveTab(tab as typeof activeTab);
                  if (tab === "prd" && prdContent === null) loadPrd(selected.id);
                  if (tab === "docs" && docFiles.length === 0) loadDocs(selected.id);
                  if (tab === "features" && !featuresLoaded) loadFeatures(selected.id);
                }}
                style={{ padding: "6px 16px", background: activeTab === tab ? "#1e293b" : "none", border: "none",
                  borderRadius: "6px 6px 0 0", color: activeTab === tab ? "#f1f5f9" : "#6b7280",
                  cursor: "pointer", fontSize: 13, fontWeight: activeTab === tab ? 600 : 400 }}>
                {tab === "features" ? `Features (${features.length})`
                  : tab === "agents" ? `Agents (${settingsAgents.length})`
                  : tab === "prd" ? "PRD"
                  : tab === "runs" ? `Runs (${projRuns.length})`
                  : `Docs${docFiles.length > 0 ? ` (${docFiles.length})` : ""}`}
              </button>
            ))}
          </div>

          {/* Features tab */}
          {activeTab === "features" && (
            <div style={{ marginTop: 16 }}>
              <div className="task-manager-header">
                <h4>Features / Ý tưởng ({features.length})</h4>
                <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}
                  onClick={() => setShowAddFeature(v => !v)}>
                  + Add Feature
                </button>
              </div>

              {showAddFeature && (
                <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                  <input className="setting-input" placeholder="Tên feature (VD: Chức năng login)"
                    value={featureName} onChange={e => setFeatureName(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && addFeature()} />
                  <textarea className="setting-input" placeholder="Mô tả chi tiết (tuỳ chọn)"
                    value={featureDesc} onChange={e => setFeatureDesc(e.target.value)}
                    rows={2} style={{ resize: "vertical", fontFamily: "inherit" }} />
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <label className="setting-label">Priority:</label>
                    <select className="setting-select" value={featurePriority} onChange={e => setFeaturePriority(e.target.value)}>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                    <button className="btn-primary" disabled={featureSaving || !featureName.trim()} onClick={addFeature}>
                      {featureSaving ? "Saving..." : "Add"}
                    </button>
                    <button className="btn-muted" onClick={() => { setShowAddFeature(false); setFeatureName(""); setFeatureDesc(""); }}>Cancel</button>
                  </div>
                </div>
              )}

              {features.length === 0 ? (
                <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>
                  Chưa có feature nào. Bấm "+ Add Feature" để thêm ý tưởng.
                </p>
              ) : (
                <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                  {features.map(f => {
                    const statusColor = f.status === "done" ? "#14532d" : f.status === "in_progress" ? "#92400e" : f.status === "todo" ? "#1e293b" : "#7f1d1d";
                    const statusLabel = f.status === "done" ? "✅ done" : f.status === "in_progress" ? "⏳ running" : f.status === "todo" ? "📋 todo" : "❌ failed";
                    const priorityColor = f.priority === "high" ? "#ef4444" : f.priority === "medium" ? "#f59e0b" : "#6b7280";
                    return (
                      <div key={f.id} style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "flex-start", gap: 10 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 600, fontSize: 13, color: "#f1f5f9" }}>{f.name}</span>
                            <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 99, background: statusColor, color: "#e2e8f0" }}>{statusLabel}</span>
                            <span style={{ fontSize: 10, color: priorityColor }}>{f.priority}</span>
                          </div>
                          {f.description && (
                            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af", lineHeight: 1.5 }}>{f.description}</p>
                          )}
                        </div>
                        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                          {f.status !== "done" ? (
                            <button onClick={() => markFeatureDone(f.id)}
                              style={{ background: "#14532d", border: "none", color: "#86efac", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}
                              title="Đánh dấu hoàn thành">✓ Done</button>
                          ) : (
                            <button onClick={() => updateFeatureStatus(f.id, "todo")}
                              style={{ background: "#1e293b", border: "1px solid #374151", color: "#9ca3af", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}
                              title="Reopen">↩ Reopen</button>
                          )}
                          {f.status !== "done" && (
                            <button onClick={() => deleteFeature(f.id)}
                              style={{ background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14, padding: "0 4px" }}
                              title="Xóa">✕</button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

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
                    {addTool === "opencode" ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <select className="setting-select" style={{ width: 260 }}
                          value={OPENCODE_GO_MODELS.find(m => m.value === addModel) ? addModel : "other"}
                          onChange={e => { if (e.target.value !== "other") setAddModel(e.target.value); else setAddModel(""); }}>
                          {OPENCODE_GO_MODELS.map(m => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        {(!OPENCODE_GO_MODELS.find(m => m.value === addModel && m.value !== "other") || addModel === "") && (
                          <input className="setting-input" style={{ width: 260 }} value={addModel}
                            onChange={e => setAddModel(e.target.value)} placeholder="vd: opencode-go/model-name" />
                        )}
                      </div>
                    ) : (
                      <input className="setting-input" style={{ width: 220 }} value={addModel}
                        onChange={e => setAddModel(e.target.value)} placeholder="để trống = dùng claude mặc định" />
                    )}
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
                        <button onClick={() => confirmRemoveAgent(a.key)}
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
          {activeTab === "docs" && (() => {
            type DocFile = { path: string; name: string; size: number; source: string };
            const planningFiles = (docFiles as DocFile[]).filter(f => f.source === "docs");
            const codeFiles     = (docFiles as DocFile[]).filter(f => f.source === "code");
            const selectedFile  = (docFiles as DocFile[]).find(f => f.path === selectedDoc);
            return (
              <div style={{ marginTop: 16 }}>
                {docFiles.length === 0 ? (
                  <p style={{ color: "#6b7280", fontSize: 13 }}>Chưa có file output. Chạy orchestrator để tạo tài liệu.</p>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: selectedDoc ? "260px 1fr" : "1fr", gap: 12 }}>
                    <div style={{ borderRight: selectedDoc ? "1px solid #1e293b" : "none", paddingRight: selectedDoc ? 12 : 0 }}>
                      {planningFiles.length > 0 && (
                        <>
                          <div style={{ fontSize: 10, color: "#6b7280", padding: "6px 8px 2px", textTransform: "uppercase", letterSpacing: 1 }}>📋 Planning Docs</div>
                          {planningFiles.map(f => (
                            <div key={f.path} onClick={() => loadDocContent(selected.id, f.path, "docs")}
                              style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, fontSize: 12,
                                background: selectedDoc === f.path ? "#1e293b" : "transparent",
                                color: selectedDoc === f.path ? "#f1f5f9" : "#9ca3af",
                                fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                              title={f.path}>{f.path}</div>
                          ))}
                        </>
                      )}
                      {codeFiles.length > 0 && (
                        <>
                          <div style={{ fontSize: 10, color: "#6b7280", padding: "10px 8px 2px", textTransform: "uppercase", letterSpacing: 1 }}>💻 Source Code</div>
                          {codeFiles.map(f => (
                            <div key={f.path} onClick={() => loadDocContent(selected.id, f.path, "code")}
                              style={{ padding: "4px 8px", cursor: "pointer", borderRadius: 4, fontSize: 12,
                                background: selectedDoc === f.path ? "#1e293b" : "transparent",
                                color: selectedDoc === f.path ? "#f1f5f9" : "#9ca3af",
                                fontFamily: "monospace", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                              title={f.path}>{f.path}</div>
                          ))}
                        </>
                      )}
                    </div>
                    {selectedDoc && (
                      <div>
                        <div style={{ fontSize: 11, color: "#4b5563", marginBottom: 8, fontFamily: "monospace" }}>
                          {selectedFile?.source === "docs" ? "📋" : "💻"} {selectedDoc}
                        </div>
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
            );
          })()}
        </div>
      )}

      {/* Remove agent confirm dialog */}
      {removeAgentKey && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "#0f172a", border: "1px solid #374151", borderRadius: 12, padding: 24, minWidth: 360, maxWidth: 480 }}>
            <h4 style={{ margin: "0 0 12px", color: "#f1f5f9" }}>Xóa agent <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>{removeAgentKey}</code>?</h4>
            <p style={{ fontSize: 13, color: "#9ca3af", margin: "0 0 16px" }}>
              Agent sẽ bị xóa khỏi <code style={{ background: "#1e293b", padding: "1px 5px", borderRadius: 3, fontSize: 11 }}>settings.toml</code> và không chạy trong các lần orchestrate tiếp theo.
            </p>
            {AGENTS_WITH_WORKSPACE.includes(removeAgentKey) && (
              <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", background: "#1e293b", border: "1px solid #374151", borderRadius: 8, padding: "10px 12px", marginBottom: 16 }}>
                <input type="checkbox" checked={removeWithCleanup} onChange={e => setRemoveWithCleanup(e.target.checked)}
                  style={{ marginTop: 2, accentColor: "#ef4444", flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, color: "#f1f5f9", fontWeight: 500 }}>Xóa workspace code</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>
                    Xóa toàn bộ folder <code style={{ background: "#0f172a", padding: "1px 4px", borderRadius: 3 }}>output/{selected?.id}/{removeAgentKey.startsWith("be") ? "backend" : removeAgentKey.startsWith("fe") ? "frontend" : "fullstack"}/{removeAgentKey}/</code>
                  </div>
                </div>
              </label>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn-muted" onClick={() => setRemoveAgentKey(null)}>Huỷ</button>
              <button className="btn-danger" onClick={handleRemoveAgent}>
                {removeWithCleanup ? "Xóa agent + workspace" : "Xóa agent"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workspace deleted toast */}
      {removedWorkspaceMsg && (
        <div style={{ position: "fixed", bottom: 24, right: 24, background: "#14532d", border: "1px solid #166534", borderRadius: 8, padding: "10px 16px", fontSize: 13, color: "#86efac", zIndex: 200, maxWidth: 400 }}>
          ✓ {removedWorkspaceMsg}
          <button onClick={() => setRemovedWorkspaceMsg(null)} style={{ marginLeft: 12, background: "none", border: "none", color: "#86efac", cursor: "pointer", fontSize: 16, lineHeight: 1 }}>✕</button>
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
