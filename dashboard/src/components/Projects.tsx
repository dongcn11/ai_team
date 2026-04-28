import React, { useState, useCallback, useEffect } from "react";
import { useProjects } from "../hooks/useProjects";
import { useAgents } from "../hooks/useAgents";
import { Project, RunSummary } from "../types";
import TaskManager from "./TaskManager";

export default function ProjectsPage() {
  const { projects, loading, error, refetch } = useProjects();
  useAgents();
  const [showCreate, setShowCreate] = useState(false);
  const [selected,   setSelected]   = useState<Project | null>(null);
  const [editing,    setEditing]    = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [projRuns,   setProjRuns]   = useState<RunSummary[]>([]);
  const [profile,    setProfile]    = useState("fullstack");

  // create form
  const [name,         setName]         = useState("");
  const [desc,         setDesc]         = useState("");
  const [gitUrl,       setGitUrl]       = useState("");
  const [docUrl,       setDocUrl]       = useState("");
  const [clientFolder, setClientFolder] = useState("");

  // edit form
  const [editName,   setEditName]   = useState("");
  const [editDesc,   setEditDesc]   = useState("");
  const [editGit,    setEditGit]    = useState("");
  const [editDoc,    setEditDoc]    = useState("");
  const [editFolder, setEditFolder] = useState("");

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    await fetch("/api/projects/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        description: desc.trim() || null,
        client_folder: clientFolder.trim() || null,
        git_url: gitUrl.trim() || null,
        doc_url: docUrl.trim() || null,
      }),
    });
    setName(""); setDesc(""); setGitUrl(""); setDocUrl(""); setClientFolder(""); setShowCreate(false);
    setSaving(false);
    refetch();
  };

  const handleDelete = async (id: number) => {
    await fetch(`/api/projects/${id}`, { method: "DELETE" });
    setSelected(null);
    refetch();
  };

  const openProject = useCallback(async (id: number) => {
    const res = await fetch(`/api/projects/${id}`);
    if (res.ok) setSelected(await res.json());
  }, []);

  const toggleAgent = async (agentId: number, isAssigned: boolean) => {
    if (!selected) return;
    const method = isAssigned ? "DELETE" : "POST";
    await fetch(`/api/projects/${selected.id}/agents/${agentId}`, { method });
    openProject(selected.id);
    refetch();
  };

  useEffect(() => {
    if (!selected) return;
    (async () => {
      const res = await fetch(`/api/runs?project_id=${selected.id}&limit=10`);
      if (res.ok) setProjRuns(await res.json());
    })();
  }, [selected]);

  const updateStatus = async (id: number, status: string) => {
    await fetch(`/api/projects/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (selected) openProject(selected.id);
    refetch();
  };

  const startEdit = () => {
    if (!selected) return;
    setEditName(selected.name);
    setEditDesc(selected.description || "");
    setEditGit(selected.git_url || "");
    setEditDoc(selected.doc_url || "");
    setEditFolder(selected.client_folder || "");
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!selected || !editName.trim()) return;
    setSaving(true);
    await fetch(`/api/projects/${selected.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: editName.trim(),
        description: editDesc.trim() || null,
        client_folder: editFolder.trim() || null,
        git_url: editGit.trim() || null,
        doc_url: editDoc.trim() || null,
      }),
    });
    setEditing(false); setSaving(false);
    openProject(selected.id);
    refetch();
  };

  if (loading) return <div className="state">Loading projects...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Projects</h2>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New Project</button>
      </div>

      {showCreate && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3>Create Project</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Name</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="Project name" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Git URL</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="https://github.com/..." value={gitUrl} onChange={e => setGitUrl(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Client Folder</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="auto: project_name" value={clientFolder} onChange={e => setClientFolder(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Profile</label>
              <select className="setting-select" style={{ width: "100%" }} value={profile} onChange={e => setProfile(e.target.value)}>
                <option value="fullstack">Full-stack Web</option>
                <option value="backend_only">Backend Only</option>
                <option value="api_only">API Only</option>
                <option value="mobile_app">Mobile + Backend</option>
                <option value="frontend_only">Frontend Only</option>
                <option value="solo_backend">Solo Backend</option>
                <option value="solo_fullstack">Solo Full-stack</option>
                <option value="dual_fullstack">Dual Full-stack</option>
              </select>
            </div>
          </div>
          <textarea className="setting-input" style={{ width: "100%", marginTop: 8, resize: "vertical", minHeight: 60 }}
            placeholder="Description" value={desc} onChange={e => setDesc(e.target.value)} />
          <input className="setting-input" style={{ width: "100%", marginTop: 8 }} placeholder="Documentation URL" value={docUrl} onChange={e => setDocUrl(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn-primary" disabled={saving || !name.trim()} onClick={handleCreate}>{saving ? "Creating..." : "Create"}</button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setDesc(""); setGitUrl(""); setDocUrl(""); setClientFolder(""); }}>Cancel</button>
          </div>
        </div>
      )}

      {selected && (
        <div className="card" style={{ marginBottom: 20 }}>
          {editing ? (
            <div>
              <h3 style={{ marginBottom: 12 }}>Edit Project</h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Name</label>
                  <input className="setting-input" style={{ width: "100%" }} value={editName} onChange={e => setEditName(e.target.value)} />
                </div>
                <div>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Git URL</label>
                  <input className="setting-input" style={{ width: "100%" }} placeholder="https://github.com/..." value={editGit} onChange={e => setEditGit(e.target.value)} />
                </div>
                <div>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Client Folder</label>
                  <input className="setting-input" style={{ width: "100%" }} placeholder="Folder in clients/" value={editFolder} onChange={e => setEditFolder(e.target.value)} />
                </div>
              </div>
              <textarea className="setting-input" style={{ width: "100%", marginTop: 8, resize: "vertical", minHeight: 60 }}
                placeholder="Description" value={editDesc} onChange={e => setEditDesc(e.target.value)} />
              <input className="setting-input" style={{ width: "100%", marginTop: 8 }} placeholder="Documentation URL" value={editDoc} onChange={e => setEditDoc(e.target.value)} />
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button className="btn-primary" disabled={saving || !editName.trim()} onClick={saveEdit}>{saving ? "Saving..." : "Save"}</button>
                <button className="btn-muted" onClick={() => setEditing(false)}>Cancel</button>
              </div>
            </div>
          ) : (
            <>
              <div className="project-detail-header">
                <div>
                  <h3>{selected.name}</h3>
                  <div className="project-meta-links">
                    {selected.client_folder && (
                      <span className="project-link" style={{ background: "#172554", borderColor: "#3b82f655" }}>
                        <span className="project-link-icon">&#x1f4c1;</span> clients/{selected.client_folder}
                      </span>
                    )}
                    {selected.git_url && (
                      <a href={selected.git_url} target="_blank" rel="noreferrer" className="project-link">
                        <span className="project-link-icon">&#x1f4e6;</span> Git
                      </a>
                    )}
                    {selected.doc_url && (
                      <a href={selected.doc_url} target="_blank" rel="noreferrer" className="project-link">
                        <span className="project-link-icon">&#x1f4c4;</span> Docs
                      </a>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <select className="setting-select" style={{ width: 130 }} value={selected.status}
                    onChange={e => updateStatus(selected.id, e.target.value)}>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="completed">Completed</option>
                    <option value="archived">Archived</option>
                  </select>
                  <button className="btn-primary" onClick={startEdit}>Edit</button>
                  <button className="btn-muted" onClick={() => setSelected(null)}>Close</button>
                  <button className="btn-danger" onClick={() => handleDelete(selected.id)}>Delete</button>
                </div>
              </div>
              {selected.description && <p className="setting-sub" style={{ marginBottom: 16 }}>{selected.description}</p>}

              <div className="task-manager-header">
                <h4>Agents ({selected.agents.length})</h4>
                <span style={{ fontSize: 11, color: "#4b5563" }}>
                  Synced from <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>config/settings.toml</code>
                </span>
              </div>
              {selected.agents.length === 0 && <p style={{ color: "#6b7280", fontSize: 13 }}>No agents assigned. Auto-synced when project is created.</p>}
              <div className="agent-chip-list">
                {selected.agents.map(a => (
                  <div key={a.id} className="agent-chip">
                    <span>{a.name}</span>
                    <span className="agent-chip-role">{a.role}</span>
                    <span className="agent-chip-status" data-status={a.status}>{a.status}</span>
                  </div>
                ))}
              </div>

              {/* Orchestrator Runs */}
              <div style={{ borderTop: "1px solid #1e293b", marginTop: 20, paddingTop: 16 }}>
                <div className="task-manager-header">
                  <h4>Orchestrator Runs ({projRuns.length})</h4>
                  <span style={{ fontSize: 11, color: "#4b5563" }}>
                    Run: <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>
                      set AI_TEAM_PROJECT_ID={selected.id} && python main.py --config clients/{selected.client_folder || selected.name.toLowerCase().replace(" ", "_")}/settings.toml --text "your PRD"
                    </code>
                  </span>
                </div>
                {projRuns.length === 0 ? (
                  <p style={{ color: "#6b7280", fontSize: 12 }}>
                    No orchestrator runs yet. Run the command above to trigger ai_team agents.
                  </p>
                ) : (
                  <div className="history-list">
                    {projRuns.map(r => (
                      <div key={r.id} className="history-row">
                        <span className="history-id">#{r.id}</span>
                        <span className="history-meta">{r.client && `${r.client} · `}{r.total_tasks} tasks</span>
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
                )}
              </div>

              <div style={{ borderTop: "1px solid #1e293b", marginTop: 20, paddingTop: 20 }}>
                <TaskManager projectId={selected.id} agents={selected.agents} onUpdate={() => refetch()} />
              </div>
            </>
          )}
        </div>
      )}

      {!selected && projects.length === 0 && (
        <div className="state">No projects yet. Create one to get started.</div>
      )}

      <div className="project-grid">
        {projects.map(p => (
          <div key={p.id} className="project-card" onClick={() => openProject(p.id)}>
            <div className="project-card-top">
              <span className="project-card-name">{p.name}</span>
              <span className={`project-status-badge status-${p.status}`}>{p.status}</span>
            </div>
            {p.description && <p className="project-card-desc">{p.description}</p>}
            <div className="project-card-meta">
              <span>{p.agent_count} agent{p.agent_count !== 1 ? "s" : ""}</span>
              {p.git_url && <span className="project-card-meta-sep">|</span>}
              {p.git_url && <span className="project-card-meta-link">git</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
