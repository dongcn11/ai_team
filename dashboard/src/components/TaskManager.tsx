import React, { useState, useRef, useEffect } from "react";
import { useProjectTasks } from "../hooks/useProjectTasks";
import { ProjectTask, TaskDocument, AgentSimple, TaskComment, SubTask } from "../types";

interface Props {
  projectId: number;
  agents: AgentSimple[];
  onUpdate: () => void;
}

export default function TaskManager({ projectId, agents, onUpdate }: Props) {
  const { tasks, loading, error, refetch } = useProjectTasks(projectId);
  const [showCreate,  setShowCreate]  = useState(false);
  const [selected,    setSelected]    = useState<ProjectTask | null>(null);
  const [saving,      setSaving]      = useState(false);

  // create form
  const [name,     setName]     = useState("");
  const [desc,     setDesc]     = useState("");
  const [priority, setPriority] = useState("medium");
  const [agentId,  setAgentId]  = useState("");
  const [dueAt,    setDueAt]    = useState("");

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    await fetch(`/api/project-tasks/${projectId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        description: desc.trim() || null,
        priority,
        assigned_agent_id: agentId ? Number(agentId) : null,
        due_at: dueAt || null,
      }),
    });
    setName(""); setDesc(""); setPriority("medium"); setAgentId(""); setDueAt("");
    setShowCreate(false); setSaving(false);
    refetch();
    onUpdate();
  };

  const updateTask = async (taskId: number, payload: Record<string, unknown>) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    refetch();
    if (selected?.id === taskId) {
      const res = await fetch(`/api/project-tasks/${projectId}/${taskId}`);
      if (res.ok) setSelected(await res.json());
    }
  };

  const deleteTask = async (taskId: number) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}`, { method: "DELETE" });
    setSelected(null);
    refetch();
    onUpdate();
  };

  const openTask = async (taskId: number) => {
    const res = await fetch(`/api/project-tasks/${projectId}/${taskId}`);
    if (res.ok) setSelected(await res.json());
  };

  // Doc form
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");
  const [docType, setDocType] = useState("note");

  const addDoc = async () => {
    if (!selected || !docTitle.trim()) return;
    await fetch(`/api/project-tasks/${projectId}/${selected.id}/docs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: docTitle.trim(), content: docContent, doc_type: docType }),
    });
    setDocTitle(""); setDocContent(""); setDocType("note");
    openTask(selected.id);
  };

  const deleteDoc = async (taskId: number, docId: number) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}/docs/${docId}`, { method: "DELETE" });
    openTask(taskId);
  };

  // Comments
  const [commentAuthor, setCommentAuthor] = useState("");
  const [commentText,   setCommentText]   = useState("");
  const commentEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { commentEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [selected?.comments]);

  const addComment = async () => {
    if (!selected || !commentAuthor.trim() || !commentText.trim()) return;
    await fetch(`/api/project-tasks/${projectId}/${selected.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: commentAuthor.trim(), content: commentText.trim() }),
    });
    setCommentText("");
    openTask(selected.id);
  };

  const deleteComment = async (taskId: number, commentId: number) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}/comments/${commentId}`, { method: "DELETE" });
    openTask(taskId);
  };

  // SubTasks
  const [subName,    setSubName]    = useState("");
  const [subAgentId, setSubAgentId] = useState("");

  const addSubTask = async () => {
    if (!selected || !subName.trim()) return;
    await fetch(`/api/project-tasks/${projectId}/${selected.id}/subtasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: subName.trim(), assigned_agent_id: subAgentId ? Number(subAgentId) : null }),
    });
    setSubName(""); setSubAgentId("");
    openTask(selected.id);
  };

  const toggleSubTask = async (taskId: number, sub: SubTask) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}/subtasks/${sub.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: sub.status === "done" ? "todo" : "done" }),
    });
    openTask(taskId);
  };

  const deleteSubTask = async (taskId: number, subId: number) => {
    await fetch(`/api/project-tasks/${projectId}/${taskId}/subtasks/${subId}`, { method: "DELETE" });
    openTask(taskId);
  };

  const statusColors: Record<string, string> = { todo: "#6b7280", in_progress: "#3b82f6", review: "#eab308", done: "#22c55e" };
  const priorityColors: Record<string, string> = { high: "#ef4444", medium: "#eab308", low: "#22c55e" };
  const docTypeLabels: Record<string, string> = { note: "Note", spec: "Spec", log: "Log", result: "Result" };

  return (
    <div className="task-manager">
      <div className="task-manager-header">
        <h4>Tasks ({tasks.length})</h4>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New Task</button>
      </div>

      {showCreate && (
        <div className="card task-form" style={{ marginBottom: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Name</label>
              <input className="setting-input" style={{ width: "100%" }} placeholder="Task name" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Assign Agent</label>
              <select className="setting-select" style={{ width: "100%" }} value={agentId} onChange={e => setAgentId(e.target.value)}>
                <option value="">Unassigned</option>
                {agents.map(a => <option key={a.id} value={a.id}>{a.name} ({a.role})</option>)}
              </select>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Priority</label>
              <select className="setting-select" style={{ width: "100%" }} value={priority} onChange={e => setPriority(e.target.value)}>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
            <div>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Due date</label>
              <input type="date" className="setting-input" style={{ width: "100%", colorScheme: "dark" }} value={dueAt} onChange={e => setDueAt(e.target.value)} />
            </div>
          </div>
          <textarea className="setting-input" style={{ width: "100%", marginTop: 8, resize: "vertical", minHeight: 50 }}
            placeholder="Description" value={desc} onChange={e => setDesc(e.target.value)} />
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn-primary" disabled={saving || !name.trim()} onClick={handleCreate}>{saving ? "Creating..." : "Create"}</button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setDesc(""); }}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <div className="state" style={{ padding: 20 }}>Loading tasks...</div>}
      {error && <div className="state err">{error}</div>}

      {selected && (
        <div className="card task-detail" style={{ marginBottom: 12 }}>
          <div className="project-detail-header">
            <div>
              <h3 style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {selected.name}
                <span className="task-priority-badge" style={{ background: priorityColors[selected.priority] + "22", color: priorityColors[selected.priority], fontSize: 11, padding: "2px 8px", borderRadius: 10 }}>{selected.priority}</span>
              </h3>
              <p style={{ fontSize: 12, color: "#6b7280" }}>
                {selected.agent ? `${selected.agent.name} (${selected.agent.role})` : "Unassigned"}
                {selected.due_at && ` · Due: ${new Date(selected.due_at).toLocaleDateString()}`}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <select className="setting-select" style={{ width: 130 }} value={selected.status}
                onChange={e => updateTask(selected.id, { status: e.target.value })}>
                <option value="todo">Todo</option>
                <option value="in_progress">In Progress</option>
                <option value="review">Review</option>
                <option value="done">Done</option>
              </select>
              <button className="btn-muted" onClick={() => setSelected(null)}>Close</button>
              <button className="btn-danger" onClick={() => deleteTask(selected.id)}>Delete</button>
            </div>
          </div>

          {selected.description && <p className="setting-sub" style={{ marginBottom: 12 }}>{selected.description}</p>}

          <div className="task-progress-section">
            <span style={{ fontSize: 12, color: "#6b7280" }}>Progress: {selected.progress}%</span>
            <input type="range" min="0" max="100" value={selected.progress}
              onChange={e => updateTask(selected.id, { progress: Number(e.target.value) })}
              className="task-progress-slider" />
          </div>

          {/* ── Subtasks ── */}
          <div className="task-sub-section">
            <h5 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Subtasks ({selected.subtasks?.length || 0})
            </h5>
            {(selected.subtasks || []).length === 0 && (
              <p style={{ color: "#6b7280", fontSize: 12 }}>No subtasks</p>
            )}
            {(selected.subtasks || []).map(sub => (
              <div key={sub.id} className={`subtask-row ${sub.status === "done" ? "done" : ""}`}>
                <input type="checkbox" checked={sub.status === "done"} onChange={() => toggleSubTask(selected.id, sub)} />
                <span className="subtask-name">{sub.name}</span>
                {sub.agent && <span className="subtask-agent">{sub.agent.name}</span>}
                <button className="agent-chip-remove" onClick={() => deleteSubTask(selected.id, sub.id)}>x</button>
              </div>
            ))}
            <div className="subtask-add">
              <input className="setting-input" style={{ flex: 1 }} placeholder="New subtask" value={subName} onChange={e => setSubName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addSubTask()} />
              <select className="setting-select" style={{ width: 120 }} value={subAgentId} onChange={e => setSubAgentId(e.target.value)}>
                <option value="">Anyone</option>
                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
              <button className="btn-primary" disabled={!subName.trim()} onClick={addSubTask}>Add</button>
            </div>
          </div>

          {/* ── Comments / Chat ── */}
          <div className="task-comments-section">
            <h5 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Discussion ({selected.comments?.length || 0})
            </h5>
            <div className="comments-list">
              {(selected.comments || []).length === 0 && (
                <p style={{ color: "#6b7280", fontSize: 12, textAlign: "center", padding: 12 }}>No comments yet</p>
              )}
              {(selected.comments || []).map(c => (
                <div key={c.id} className="comment-bubble">
                  <div className="comment-header">
                    <span className="comment-author">{c.author}</span>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <span className="comment-time">{new Date(c.created_at).toLocaleTimeString()}</span>
                      <button className="agent-chip-remove" onClick={() => deleteComment(selected.id, c.id)}>x</button>
                    </div>
                  </div>
                  <p className="comment-content">{c.content}</p>
                </div>
              ))}
              <div ref={commentEndRef} />
            </div>
            <div className="comment-input-row">
              <input className="setting-input" style={{ width: 100 }} placeholder="Name" value={commentAuthor} onChange={e => setCommentAuthor(e.target.value)} />
              <input className="setting-input" style={{ flex: 1 }} placeholder="Write a comment..." value={commentText}
                onChange={e => setCommentText(e.target.value)}
                onKeyDown={e => e.key === "Enter" && addComment()} />
              <button className="btn-primary" disabled={!commentAuthor.trim() || !commentText.trim()} onClick={addComment}>Send</button>
            </div>
          </div>

          <div className="task-docs-section">
            <h5 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Documents ({selected.documents.length})</h5>
            {selected.documents.length === 0 && <p style={{ color: "#6b7280", fontSize: 12 }}>No documents yet</p>}
            {selected.documents.map(doc => (
              <div key={doc.id} className="task-doc-card">
                <div className="task-doc-header">
                  <span className="task-doc-title">{doc.title}</span>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span className="task-doc-type-badge">{docTypeLabels[doc.doc_type] || doc.doc_type}</span>
                    <button className="agent-chip-remove" onClick={() => deleteDoc(selected.id, doc.id)}>x</button>
                  </div>
                </div>
                {doc.content && <pre className="task-doc-content">{doc.content}</pre>}
                <span className="task-doc-date">{new Date(doc.created_at).toLocaleString()}</span>
              </div>
            ))}

            <div className="task-doc-add">
              <input className="setting-input" style={{ flex: 1 }} placeholder="Doc title" value={docTitle} onChange={e => setDocTitle(e.target.value)} />
              <select className="setting-select" style={{ width: 100 }} value={docType} onChange={e => setDocType(e.target.value)}>
                <option value="note">Note</option>
                <option value="spec">Spec</option>
                <option value="log">Log</option>
                <option value="result">Result</option>
              </select>
              <button className="btn-primary" disabled={!docTitle.trim()} onClick={addDoc}>Add Doc</button>
            </div>
            <textarea className="setting-input" style={{ width: "100%", marginTop: 6, resize: "vertical", minHeight: 60 }}
              placeholder="Document content (markdown)" value={docContent} onChange={e => setDocContent(e.target.value)} />
          </div>
        </div>
      )}

      {!selected && tasks.length === 0 && !loading && (
        <div className="state" style={{ padding: 20 }}>No tasks yet. Create one to get started.</div>
      )}

      <div className="task-list">
        {tasks.map(task => (
          <div key={task.id} className="task-row" onClick={() => openTask(task.id)}>
            <div className="task-row-left">
              <span className="task-status-dot" style={{ background: statusColors[task.status] }} />
              <div>
                <span className="task-row-name">{task.name}</span>
                {task.agent && <span className="task-row-agent">{task.agent.name}</span>}
              </div>
            </div>
            <div className="task-row-right">
              <span className="task-priority-dot" style={{ background: priorityColors[task.priority] }} title={task.priority} />
              <div className="task-mini-progress">
                <div className="task-mini-progress-bar" style={{ width: `${task.progress}%`, background: statusColors[task.status] }} />
              </div>
              <span style={{ fontSize: 12, color: "#6b7280", minWidth: 32, textAlign: "right" }}>{task.progress}%</span>
              <span className="task-row-status" style={{ color: statusColors[task.status] }}>{task.status.replace("_", " ")}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
