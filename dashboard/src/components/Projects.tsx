import React, { useState, useCallback, useEffect } from "react";
import { useProjects } from "../hooks/useProjects";
import { Project, AgentFS, RunSummary } from "../types";
import TaskManager from "./TaskManager";

export default function ProjectsPage() {
  const { projects, loading, error, refetch } = useProjects();
  const [selected, setSelected] = useState<Project | null>(null);
  const [projRuns, setProjRuns] = useState<RunSummary[]>([]);

  const openProject = useCallback(async (id: string) => {
    const res = await fetch(`/api/projects/${id}`);
    if (res.ok) setSelected(await res.json());
  }, []);

  useEffect(() => {
    if (!selected) return;
    (async () => {
      const res = await fetch(`/api/runs?client=${selected.id}&limit=10`);
      if (res.ok) setProjRuns(await res.json());
    })();
  }, [selected]);

  const syncAgents = async (id: string) => {
    await fetch(`/api/projects/${id}/sync-agents`, { method: "POST" });
    openProject(id);
  };

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
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn-muted" onClick={() => syncAgents(selected.id)}>↻ Sync Agents</button>
              <button className="btn-muted" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>

          {/* Agents */}
          <div className="task-manager-header" style={{ marginTop: 16 }}>
            <h4>Agents ({selected.agents.length})</h4>
            <span style={{ fontSize: 11, color: "#4b5563" }}>
              Synced from <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4 }}>
                clients/{selected.id}/settings.toml
              </code>
            </span>
          </div>
          {selected.agents.length === 0
            ? <p style={{ color: "#6b7280", fontSize: 13 }}>No agents in settings.toml</p>
            : (
              <div className="agent-chip-list">
                {selected.agents.map(a => (
                  <div key={a.key} className="agent-chip">
                    <span>{a.name}</span>
                    <span className="agent-chip-role">{a.role}</span>
                    <span style={{ fontSize: 10, color: "#6b7280" }}>{a.model}</span>
                  </div>
                ))}
              </div>
            )
          }

          {/* Run command */}
          <div style={{ borderTop: "1px solid #1e293b", marginTop: 20, paddingTop: 16 }}>
            <div className="task-manager-header">
              <h4>Orchestrator Runs ({projRuns.length})</h4>
              <span style={{ fontSize: 11, color: "#4b5563" }}>
                <code style={{ background: "#1e293b", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>
                  python main.py --config clients/{selected.id}/settings.toml --text "your PRD"
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

          <div style={{ borderTop: "1px solid #1e293b", marginTop: 20, paddingTop: 20 }}>
            <TaskManager projectId={selected.id} agents={selected.agents} onUpdate={refetch} />
          </div>
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
