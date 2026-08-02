import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Handle,
  Position,
  MarkerType,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useWorkflows, useWorkflowRun, useSkills, useLatestRun } from "../hooks/useWorkflows";
import { useProjects } from "../hooks/useProjects";
import ActiveTasks from "./ActiveTasks";
import RunSteps from "./RunSteps";
import {
  Workflow, WorkflowNodeType, WorkflowNodeData, NodeRunStatus,
} from "../types";

// ── Node palette ──────────────────────────────────────────────────────────

const NODE_DEFS: { type: WorkflowNodeType; icon: string; label: string; defaultData: WorkflowNodeData }[] = [
  { type: "trigger.slack_mention", icon: "💬", label: "Slack Mention", defaultData: { label: "Slack Mention", channel: "#general", keyword: "" } },
  { type: "action.generate_code",  icon: "⚙️", label: "Generate Code",  defaultData: { label: "Generate Code", skill_dirs: [], prompt: "" } },
  { type: "action.create_mr",      icon: "🔀", label: "Create MR",      defaultData: { label: "Create MR", provider: "gitlab", repo: "", base_branch: "main", title_template: "", description_template: "" } },
  { type: "action.code_review",    icon: "👀", label: "Code Review",    defaultData: { label: "Code Review", skill_dirs: ["leader"], prompt: "" } },
  { type: "action.custom",         icon: "🧩", label: "Custom Action",  defaultData: { label: "Custom Action", skill_dirs: [], prompt: "" } },
];

const STATUS_COLOR: Record<NodeRunStatus, string> = {
  pending: "#334155",
  running: "#fbbf24",
  ok:      "#4ade80",
  error:   "#f87171",
};

function nodeSummary(type: WorkflowNodeType, data: any): string {
  if (type === "trigger.slack_mention") return `#${(data.channel || "").replace(/^#/, "")}${data.keyword ? ` · "${data.keyword}"` : ""}`;
  if (type === "action.generate_code")  return (data.skill_dirs || []).join("+") || "no skill";
  if (type === "action.create_mr")      return `${(data.provider || "").toUpperCase()} · ${data.repo || "no repo"}`;
  if (type === "action.code_review")    return (data.skill_dirs || []).join("+") || "no skill";
  if (type === "action.custom")         return (data.skill_dirs || []).join("+") || "no skill";
  return "";
}

function WorkflowNodeView({ id, type, data, selected }: NodeProps) {
  const def = NODE_DEFS.find(d => d.type === type);
  const isTrigger = type === "trigger.slack_mention";
  const status: NodeRunStatus = (data as any)._runStatus || "pending";
  return (
    <div style={{
      background: "#0f172a",
      border: `2px solid ${selected ? "#60a5fa" : STATUS_COLOR[status]}`,
      borderRadius: 10,
      padding: "10px 14px",
      minWidth: 180,
      boxShadow: selected ? "0 0 0 2px rgba(96,165,250,0.3)" : undefined,
    }}>
      {!isTrigger && <Handle type="target" position={Position.Top} />}
      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", display: "flex", alignItems: "center", gap: 6 }}>
        <span>{def?.icon}</span>
        <span>{(data as any).label || def?.label}</span>
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        {nodeSummary(type as WorkflowNodeType, data)}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = {
  "trigger.slack_mention": WorkflowNodeView,
  "action.generate_code":  WorkflowNodeView,
  "action.create_mr":      WorkflowNodeView,
  "action.code_review":    WorkflowNodeView,
  "action.custom":         WorkflowNodeView,
};

// ── Config panel ──────────────────────────────────────────────────────────

function SkillPicker({ value, onChange, skills }: { value: string[]; onChange: (v: string[]) => void; skills: string[] }) {
  const toggle = (s: string) => {
    onChange(value.includes(s) ? value.filter(x => x !== s) : [...value, s]);
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {skills.map(s => (
        <label key={s} style={{
          display: "flex", alignItems: "center", gap: 4, fontSize: 12,
          background: value.includes(s) ? "#1e3a8a" : "#1e293b",
          border: "1px solid #334155", borderRadius: 6, padding: "3px 8px", cursor: "pointer",
        }}>
          <input type="checkbox" checked={value.includes(s)} onChange={() => toggle(s)} style={{ margin: 0 }} />
          {s}
        </label>
      ))}
      {skills.length === 0 && <span style={{ fontSize: 12, color: "#4b5563" }}>Không tải được danh sách skill</span>}
    </div>
  );
}

function ConfigPanel({ node, skills, onUpdate, onDelete, onClose }: {
  node: Node;
  skills: string[];
  onUpdate: (data: any) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const data = node.data as any;
  const set = (patch: any) => onUpdate({ ...data, ...patch });

  return (
    <div style={{ width: 320, borderLeft: "1px solid #1e293b", padding: 16, overflowY: "auto", background: "#0b1220" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={{ margin: 0, fontSize: 13 }}>Cấu hình node</h4>
        <button className="btn-muted" onClick={onClose} style={{ fontSize: 11, padding: "2px 8px" }}>✕</button>
      </div>

      <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên hiển thị</label>
      <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
        value={data.label || ""} onChange={e => set({ label: e.target.value })} />

      {node.type === "trigger.slack_mention" && (
        <>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Kênh Slack</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="#general" value={data.channel || ""} onChange={e => set({ channel: e.target.value })} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Từ khoá (tuỳ chọn)</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="vd: @bot deploy" value={data.keyword || ""} onChange={e => set({ keyword: e.target.value })} />
        </>
      )}

      {(node.type === "action.generate_code" || node.type === "action.code_review" || node.type === "action.custom") && (
        <>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Skill</label>
          <div style={{ marginBottom: 12 }}>
            <SkillPicker value={data.skill_dirs || []} skills={skills} onChange={v => set({ skill_dirs: v })} />
          </div>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Nội dung / prompt</label>
          <textarea className="setting-input" style={{ width: "100%", minHeight: 120, resize: "vertical", marginBottom: 12 }}
            placeholder="Mô tả yêu cầu cho agent..." value={data.prompt || ""} onChange={e => set({ prompt: e.target.value })} />
        </>
      )}

      {node.type === "action.create_mr" && (
        <>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Provider</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 12 }}
            value={data.provider || "gitlab"} onChange={e => set({ provider: e.target.value })}>
            <option value="gitlab">GitLab</option>
            <option value="github">GitHub</option>
          </select>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Repo</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="group/project hoặc owner/repo" value={data.repo || ""} onChange={e => set({ repo: e.target.value })} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Base branch</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="main" value={data.base_branch || ""} onChange={e => set({ base_branch: e.target.value })} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tiêu đề MR</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="feat: ..." value={data.title_template || ""} onChange={e => set({ title_template: e.target.value })} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Mô tả MR</label>
          <textarea className="setting-input" style={{ width: "100%", minHeight: 80, resize: "vertical", marginBottom: 12 }}
            value={data.description_template || ""} onChange={e => set({ description_template: e.target.value })} />
        </>
      )}

      <button className="btn-danger" style={{ width: "100%" }} onClick={onDelete}>Xoá node</button>
    </div>
  );
}

// ── Canvas editor ─────────────────────────────────────────────────────────

let idCounter = 0;
const nextId = () => `node_${Date.now()}_${idCounter++}`;

function WorkflowEditor({ workflow, onBack, onSaved }: {
  workflow: Workflow;
  onBack: () => void;
  onSaved: () => void;
}) {
  const skills = useSkills();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(
    workflow.definition.nodes.map(n => ({ ...n } as unknown as Node))
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    workflow.definition.edges.map(e => ({ ...e, markerEnd: { type: MarkerType.ArrowClosed } } as unknown as Edge))
  );

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [runId, setRunId] = useLatestRun(workflow.id);  // khôi phục run gần nhất sau reload
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [clientFolder, setClientFolder] = useState(workflow.client_folder || "");
  const { projects } = useProjects();

  const run = useWorkflowRun(runId);

  // Overlay run status onto nodes for rendering (transient, stripped before save)
  const displayNodes = useMemo(() => {
    if (!run) return nodes;
    return nodes.map(n => ({ ...n, data: { ...n.data, _runStatus: run.node_status[n.id] } }));
  }, [nodes, run]);

  const selectedNode = nodes.find(n => n.id === selectedNodeId) || null;

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed } }, eds));
  }, [setEdges]);

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    const type = event.dataTransfer.getData("application/x-workflow-node") as WorkflowNodeType;
    const def = NODE_DEFS.find(d => d.type === type);
    if (!def) return;
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const newNode: Node = {
      id: nextId(),
      type,
      position,
      data: { ...def.defaultData } as any,
    };
    setNodes(nds => [...nds, newNode]);
  }, [screenToFlowPosition, setNodes]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const updateSelectedData = (data: any) => {
    if (!selectedNodeId) return;
    setNodes(nds => nds.map(n => n.id === selectedNodeId ? { ...n, data } : n));
  };

  const deleteSelected = () => {
    if (!selectedNodeId) return;
    setNodes(nds => nds.filter(n => n.id !== selectedNodeId));
    setEdges(eds => eds.filter(e => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const cleanNodes = nodes.map(n => {
        const { _runStatus, ...rest } = n.data as any;
        return { id: n.id, type: n.type, position: n.position, data: rest };
      });
      const cleanEdges = edges.map(e => ({ id: e.id, source: e.source, target: e.target }));
      const res = await fetch(`/api/workflows/${workflow.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ definition: { nodes: cleanNodes, edges: cleanEdges } }),
      });
      if (res.ok) { setSaveMsg("Đã lưu"); onSaved(); }
      else { const err = await res.json().catch(() => ({})); setSaveMsg(`Lỗi: ${err.detail || res.status}`); }
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(null), 3000);
    }
  };

  const handleRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      // Save trước khi run để đảm bảo graph mới nhất được dùng
      await handleSave();
      const res = await fetch(`/api/workflows/${workflow.id}/run`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setRunId(data.id);
      } else {
        const err = await res.json().catch(() => ({}));
        setRunError(err.detail || `HTTP ${res.status}`);
      }
    } finally {
      setRunning(false);
    }
  };

  const handleRefresh = async () => {
    if (!runId) return;
    await fetch(`/api/workflows/runs/${runId}/refresh`, { method: "POST" });
  };

  const handleProjectChange = async (folder: string) => {
    setClientFolder(folder);
    const res = await fetch(`/api/workflows/${workflow.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_folder: folder }),
    });
    if (res.ok) { setSaveMsg(folder ? `Đã gắn project ${folder}` : "Đã chuyển sang chạy độc lập"); onSaved(); }
    else setSaveMsg("Lỗi khi đổi project");
    setTimeout(() => setSaveMsg(null), 3000);
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 140px)" }}>
      {/* Palette */}
      <div style={{ width: 200, borderRight: "1px solid #1e293b", padding: 12, overflowY: "auto" }}>
        <button className="btn-muted" onClick={onBack} style={{ marginBottom: 12, width: "100%" }}>← Danh sách</button>
        <h4 style={{ fontSize: 12, color: "#9ca3af", textTransform: "uppercase", margin: "8px 0" }}>Node</h4>
        {NODE_DEFS.map(def => (
          <div key={def.type} draggable
            onDragStart={e => e.dataTransfer.setData("application/x-workflow-node", def.type)}
            style={{
              background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
              padding: "8px 10px", marginBottom: 8, cursor: "grab", fontSize: 12,
              display: "flex", alignItems: "center", gap: 6,
            }}>
            <span>{def.icon}</span>
            <span>{def.label}</span>
          </div>
        ))}
        <p style={{ fontSize: 11, color: "#4b5563", marginTop: 16 }}>Kéo node vào canvas rồi nối các node bằng cách kéo từ handle trên/dưới.</p>
      </div>

      {/* Canvas */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 12px", borderBottom: "1px solid #1e293b" }}>
          <strong style={{ fontSize: 13 }}>{workflow.name}</strong>
          <select className="setting-select" style={{ width: 210, fontSize: 12 }}
            value={clientFolder} onChange={e => handleProjectChange(e.target.value)}
            title="Nơi ghi file task — chọn project hoặc để chạy độc lập">
            <option value="">📁 Chạy độc lập (workflow_tasks)</option>
            {projects.map(p => <option key={p.id} value={p.id}>📁 {p.name} ({p.id})</option>)}
          </select>
          <div style={{ flex: 1 }} />
          {saveMsg && <span style={{ fontSize: 12, color: "#6b7280" }}>{saveMsg}</span>}
          <button className="btn-muted" disabled={saving} onClick={handleSave}>{saving ? "Đang lưu..." : "Save"}</button>
          {run && run.status === "running" && (
            <button className="btn-muted" onClick={handleRefresh}>🔄 Kiểm tra ngay</button>
          )}
          <button className="btn-primary" disabled={running} onClick={handleRun}>{running ? "Đang xử lý..." : "▶ Run"}</button>
        </div>

        {runError && <div className="state err" style={{ margin: 8 }}>{runError}</div>}

        <div ref={wrapperRef} style={{ flex: 1 }} onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={displayNodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_, n) => setSelectedNodeId(n.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView
            colorMode="dark"
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>

        <RunSteps workflowId={workflow.id} runId={runId} onRunChange={setRunId} />
      </div>

      {selectedNode && (
        <ConfigPanel
          node={selectedNode}
          skills={skills}
          onUpdate={updateSelectedData}
          onDelete={deleteSelected}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </div>
  );
}

// ── Page (list + editor) ────────────────────────────────────────────────

export default function WorkflowsPage() {
  const { workflows, loading, error, refetch } = useWorkflows();
  const { projects } = useProjects();
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [clientFolder, setClientFolder] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const res = await fetch("/api/workflows/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), client_folder: clientFolder, definition: { nodes: [], edges: [] } }),
      });
      if (res.ok) {
        const wf = await res.json();
        setName("");
        setClientFolder("");
        setShowCreate(false);
        await refetch();
        setSelected(wf);
      }
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id: number) => {
    await fetch(`/api/workflows/${id}`, { method: "DELETE" });
    refetch();
  };

  if (selected) {
    return (
      <ReactFlowProvider>
        <WorkflowEditor
          workflow={selected}
          onBack={() => { setSelected(null); refetch(); }}
          onSaved={refetch}
        />
      </ReactFlowProvider>
    );
  }

  if (loading) return <div className="state">Loading workflows...</div>;
  if (error)   return <div className="state err">{error}</div>;

  return (
    <div className="projects-page">
      <div className="page-header">
        <h2>Workflows</h2>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New Workflow</button>
      </div>

      <ActiveTasks />

      {showCreate && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3>Create Workflow</h3>
          <input className="setting-input" style={{ width: "100%", marginBottom: 8 }}
            placeholder="vd: Slack → Code → MR → Review" value={name} onChange={e => setName(e.target.value)} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Project (tuỳ chọn — nơi ghi file task)</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 4 }}
            value={clientFolder} onChange={e => setClientFolder(e.target.value)}>
            <option value="">Chạy độc lập (workflow_tasks/wf&lt;id&gt;)</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
          </select>
          <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>
            Không chọn project → file task ghi vào <code>workflow_tasks/wf&lt;id&gt;/</code>, không liên quan project nào.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-primary" disabled={creating || !name.trim()} onClick={handleCreate}>
              {creating ? "Creating..." : "Create"}
            </button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setClientFolder(""); }}>Cancel</button>
          </div>
        </div>
      )}

      {workflows.length === 0 && !showCreate && (
        <div className="state">Chưa có workflow nào. Tạo mới để bắt đầu thiết kế kéo-thả.</div>
      )}

      <div className="project-grid">
        {workflows.map(wf => (
          <div key={wf.id} className="project-card" onClick={() => setSelected(wf)}>
            <div className="project-card-top">
              <span className="project-card-name">{wf.name}</span>
              <span style={{ fontSize: 11, color: "#6b7280" }}>{wf.definition.nodes.length} node(s)</span>
            </div>
            {wf.description && <p className="project-card-desc">{wf.description}</p>}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
              <button className="btn-danger" style={{ fontSize: 11, padding: "2px 8px" }}
                onClick={e => { e.stopPropagation(); handleDelete(wf.id); }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
