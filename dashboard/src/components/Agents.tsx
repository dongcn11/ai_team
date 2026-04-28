import React, { useState } from "react";
import { useAgents } from "../hooks/useAgents";
import { AgentSimple, AgentDetail } from "../types";

export default function AgentsPage() {
  const { agents, loading, error, refetch } = useAgents();
  const [showCreate, setShowCreate] = useState(false);
  const [selected,   setSelected]   = useState<AgentDetail | null>(null);
  const [saving,     setSaving]     = useState(false);
  const [name,       setName]       = useState("");
  const [role,       setRole]       = useState("");
  const [model,      setModel]      = useState("gpt-4o");
  const [status,     setStatus]     = useState("available");
  const [desc,       setDesc]       = useState("");

  const handleCreate = async () => {
    if (!name.trim() || !role.trim()) return;
    setSaving(true);
    try {
      await fetch("/api/agents/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          role: role.trim(),
          model,
          status,
          description: desc.trim() || null,
        }),
      });
      setName(""); setRole(""); setModel("gpt-4o"); setStatus("available"); setDesc("");
      setShowCreate(false);
      refetch();
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: number) => {
    await fetch(`/api/agents/${id}`, { method: "DELETE" });
    setSelected(null);
    refetch();
  };

  const openAgent = async (id: number) => {
    const res = await fetch(`/api/agents/${id}`);
    if (res.ok) setSelected(await res.json());
  };

  const updateStatus = async (id: number, newStatus: string) => {
    await fetch(`/api/agents/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (selected) openAgent(selected.id);
    refetch();
  };

  if (loading) return <div className="state">Loading agents...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Agents</h2>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New Agent</button>
      </div>

      {showCreate && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3>Create Agent</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Name</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="e.g. Code Reviewer" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Role</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="e.g. reviewer" value={role} onChange={e => setRole(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Model</label>
              <select className="setting-select" style={{ width: "100%" }} value={model} onChange={e => setModel(e.target.value)}>
                <option value="gpt-4o">gpt-4o</option>
                <option value="gpt-4-turbo">gpt-4-turbo</option>
                <option value="claude-sonnet-4">claude-sonnet-4</option>
                <option value="gemini-pro">gemini-pro</option>
              </select>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Status</label>
              <select className="setting-select" style={{ width: "100%" }} value={status} onChange={e => setStatus(e.target.value)}>
                <option value="available">Available</option>
                <option value="busy">Busy</option>
                <option value="offline">Offline</option>
              </select>
            </div>
          </div>
          <textarea className="setting-input" style={{ width: "100%", marginTop: 8, resize: "vertical", minHeight: 60 }}
            placeholder="Description (optional)" value={desc} onChange={e => setDesc(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn-primary" disabled={saving || !name.trim() || !role.trim()} onClick={handleCreate}>{saving ? "Creating..." : "Create"}</button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setRole(""); setDesc(""); }}>Cancel</button>
          </div>
        </div>
      )}

      {selected && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="project-detail-header">
            <div>
              <h3>{selected.name}</h3>
              <p style={{ fontSize: 13, color: "#6b7280" }}>{selected.role} &middot; {selected.model}</p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <select className="setting-select" style={{ width: 130 }} value={selected.status}
                onChange={e => updateStatus(selected.id, e.target.value)}>
                <option value="available">Available</option>
                <option value="busy">Busy</option>
                <option value="offline">Offline</option>
              </select>
              <button className="btn-muted" onClick={() => setSelected(null)}>Close</button>
              <button className="btn-danger" onClick={() => handleDelete(selected.id)}>Delete</button>
            </div>
          </div>
          {selected.description && <p className="setting-sub" style={{ marginBottom: 16 }}>{selected.description}</p>}

          {selected.projects.length > 0 && (
            <>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Assigned Projects</h4>
              <div className="project-grid" style={{ gridTemplateColumns: "1fr" }}>
                {selected.projects.map(p => (
                  <div key={p.id} className="project-card">
                    <div className="project-card-top">
                      <span>{p.name}</span>
                      <span className={`project-status-badge status-${p.status}`}>{p.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {!selected && agents.length === 0 && (
        <div className="state">No agents yet. Create one to get started.</div>
      )}

      <div className="project-grid">
        {agents.map(a => (
          <div key={a.id} className="project-card" onClick={() => openAgent(a.id)}>
            <div className="project-card-top">
              <span className="project-card-name">{a.name}</span>
              <span className={`agent-status-badge status-${a.status}`}>{a.status}</span>
            </div>
            <p className="project-card-desc" style={{ fontSize: 12 }}>
              {a.role} &middot; {a.model}
            </p>
            {a.description && <p className="project-card-desc">{a.description}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
