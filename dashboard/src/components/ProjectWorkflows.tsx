import React, { useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { WorkflowEditor } from "./Workflows";
import { useProjectWorkflows, useWorkflowTemplates } from "../hooks/useWorkflows";
import { Workflow } from "../types";

/**
 * Danh sách workflow của RIÊNG 1 project.
 *
 * Mỗi project có bộ workflow riêng; task (feature) trong project chỉ được chọn
 * workflow nằm trong danh sách này (xem tab Features). Workflow tạo ở đây luôn
 * được gắn sẵn client_folder của project → file task ghi vào
 * `clients/<project>/_tasks/task<id>/`.
 */
export default function ProjectWorkflows({ clientFolder, onChanged }: {
  clientFolder: string;
  /** Gọi sau khi danh sách đổi — để tab Features nạp lại dropdown */
  onChanged?: () => void;
}) {
  const { workflows, loading, refetch } = useProjectWorkflows(clientFolder);
  const templates = useWorkflowTemplates();
  const [editing,    setEditing]    = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name,       setName]       = useState("");
  const [desc,       setDesc]       = useState("");
  const [creating,   setCreating]   = useState(false);
  const [error,      setError]      = useState("");
  // "" = tạo workflow trống; id mẫu = nhân bản mẫu đó vào project này
  const [fromTemplate, setFromTemplate] = useState("");

  const reload = async () => { await refetch(); onChanged?.(); };

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true); setError("");
    try {
      // Nhân bản mẫu là 1 endpoint riêng vì phải copy sâu definition ở server;
      // tạo trống thì POST bình thường.
      const res = fromTemplate
        ? await fetch(`/api/workflows/${fromTemplate}/clone?` + new URLSearchParams({
            client_folder: clientFolder, name: name.trim(),
          }), { method: "POST" })
        : await fetch("/api/workflows/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: name.trim(),
              description: desc.trim() || null,
              client_folder: clientFolder,
              definition: { nodes: [], edges: [] },
            }),
          });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || `Lỗi ${res.status}`);
        return;
      }
      const wf: Workflow = await res.json();
      setName(""); setDesc(""); setFromTemplate(""); setShowCreate(false);
      await reload();
      setEditing(wf);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (wf: Workflow) => {
    if (!window.confirm(
      `Xoá workflow "${wf.name}"?\nCác task đang chọn workflow này sẽ quay về "chưa chọn".`
    )) return;
    await fetch(`/api/workflows/${wf.id}`, { method: "DELETE" });
    reload();
  };

  const toggleActive = async (wf: Workflow) => {
    await fetch(`/api/workflows/${wf.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !wf.is_active }),
    });
    reload();
  };

  if (editing) {
    return (
      <ReactFlowProvider>
        <WorkflowEditor
          workflow={editing}
          lockProject
          onBack={() => { setEditing(null); reload(); }}
          onSaved={reload}
        />
      </ReactFlowProvider>
    );
  }

  return (
    <div style={{ marginTop: 16 }}>
      <div className="task-manager-header">
        <h4>Workflows của project ({workflows.length})</h4>
        <button className="btn-primary" style={{ fontSize: 12, padding: "4px 10px" }}
          onClick={() => { setShowCreate(true); setError(""); }}>
          + New Workflow
        </button>
      </div>

      <p style={{ fontSize: 12, color: "#6b7280", margin: "6px 0 0" }}>
        Task trong tab <b>Features</b> chọn 1 trong các workflow dưới đây để chạy.
        File task sẽ được ghi vào <code>clients/{clientFolder}/_tasks/task&lt;id&gt;/</code>.
      </p>

      {showCreate && (
        <div className="card" style={{ marginTop: 12 }}>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên workflow *</label>
          <input className="setting-input" style={{ width: "100%", boxSizing: "border-box", marginBottom: 8 }}
            autoFocus placeholder="VD: Code → Review → MR"
            value={name} onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleCreate()} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Bắt đầu từ</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 4 }}
            value={fromTemplate} onChange={e => setFromTemplate(e.target.value)}>
            <option value="">Workflow trống</option>
            {templates.map(t => (
              <option key={t.id} value={t.id}>
                📋 {t.name} ({t.definition.nodes.length} node)
              </option>
            ))}
          </select>
          <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 8px" }}>
            {fromTemplate
              ? "Sẽ tạo bản sao của mẫu trong project này — sửa bản sao không đụng tới mẫu."
              : "Mẫu là workflow chưa gắn project (tab Workflows chung), chỉ dùng để nhân bản."}
          </p>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Mô tả</label>
          <input className="setting-input" style={{ width: "100%", boxSizing: "border-box", marginBottom: 10 }}
            placeholder="Dùng khi nào / áp dụng cho loại task nào"
            disabled={Boolean(fromTemplate)}
            title={fromTemplate ? "Bản sao giữ nguyên mô tả của mẫu" : ""}
            value={desc} onChange={e => setDesc(e.target.value)} />
          {error && <p style={{ color: "#f87171", fontSize: 12, marginBottom: 8 }}>{error}</p>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-primary" disabled={creating || !name.trim()} onClick={handleCreate}>
              {creating ? "Đang tạo..." : "Tạo & mở editor"}
            </button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setDesc(""); setFromTemplate(""); }}>
              Huỷ
            </button>
          </div>
        </div>
      )}

      {loading && <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>Đang tải workflows...</p>}

      {!loading && workflows.length === 0 && !showCreate && (
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>
          Project này chưa có workflow nào. Bấm "+ New Workflow" để thiết kế quy trình kéo-thả.
        </p>
      )}

      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
        {workflows.map(wf => {
          const nodeCount = wf.definition?.nodes?.length ?? 0;
          const hasTrigger = (wf.definition?.nodes || []).some(n => String(n.type).startsWith("trigger."));
          return (
            <div key={wf.id}
              onClick={() => setEditing(wf)}
              style={{
                background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
                padding: "10px 14px", display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
              }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontWeight: 600, fontSize: 13, color: "#f1f5f9" }}>{wf.name}</span>
                  <span style={{ fontSize: 10, color: "#6b7280" }}>#{wf.id}</span>
                  <span style={{
                    fontSize: 10, padding: "2px 7px", borderRadius: 99,
                    background: wf.is_active ? "#14532d" : "#1e293b",
                    color: wf.is_active ? "#86efac" : "#9ca3af",
                  }}>{wf.is_active ? "active" : "tắt"}</span>
                  <span style={{ fontSize: 10, color: nodeCount === 0 ? "#f59e0b" : "#6b7280" }}>
                    {nodeCount} node
                  </span>
                  {nodeCount > 0 && hasTrigger && (
                    <span style={{ fontSize: 10, color: "#7dd3fc" }} title="Có trigger node — Slack mention khớp sẽ tự tạo run, ngoài việc bấm ▶ trên task">
                      💬 tự chạy qua Slack
                    </span>
                  )}
                </div>
                {wf.description && (
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af" }}>{wf.description}</p>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                <button onClick={() => setEditing(wf)}
                  style={{ background: "#1e293b", border: "1px solid #334155", color: "#cbd5e1", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}>
                  ✎ Sửa
                </button>
                <button onClick={() => toggleActive(wf)}
                  style={{ background: "none", border: "1px solid #334155", color: "#9ca3af", cursor: "pointer", fontSize: 11, padding: "3px 8px", borderRadius: 4 }}
                  title="Bật/tắt — workflow tắt sẽ không nhận trigger Slack">
                  {wf.is_active ? "⏸ Tắt" : "▶ Bật"}
                </button>
                <button onClick={() => handleDelete(wf)}
                  style={{ background: "none", border: "none", color: "#ef4444", cursor: "pointer", fontSize: 14, padding: "0 4px" }}
                  title="Xoá workflow">✕</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
