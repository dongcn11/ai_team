import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  reconnectEdge,
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
  { type: "logic.condition",       icon: "🔀", label: "Điều kiện If/Else", defaultData: {
      label: "Điều kiện", mode: "manual", expression: "", operator: "contains", value: "",
      true_label: "Đúng", false_label: "Sai",
    } },
];

const STATUS_COLOR: Record<NodeRunStatus, string> = {
  pending: "#334155",
  running: "#fbbf24",
  ok:      "#4ade80",
  error:   "#f87171",
  skipped: "#475569",
};

const OPERATOR_LABEL: Record<string, string> = {
  contains:     "chứa",
  not_contains: "không chứa",
  equals:       "bằng đúng",
  regex:        "khớp regex",
  is_empty:     "rỗng",
};

function nodeSummary(type: WorkflowNodeType, data: any): string {
  if (type === "trigger.slack_mention") return `#${(data.channel || "").replace(/^#/, "")}${data.keyword ? ` · "${data.keyword}"` : ""}`;
  if (type === "action.generate_code")  return (data.skill_dirs || []).join("+") || "no skill";
  if (type === "action.create_mr")      return `${(data.provider || "").toUpperCase()} · ${data.repo || "no repo"}`;
  if (type === "action.code_review")    return (data.skill_dirs || []).join("+") || "no skill";
  if (type === "action.custom")         return (data.skill_dirs || []).join("+") || "no skill";
  if (type === "logic.condition") {
    if (data.mode === "auto") {
      const op = OPERATOR_LABEL[data.operator] || data.operator;
      return `tự động: kết quả ${op}${data.operator === "is_empty" ? "" : ` "${data.value || "…"}"`}`;
    }
    return data.expression ? `hỏi tôi: ${data.expression}` : "hỏi tôi khi chạy";
  }
  return "";
}

/** Chấm nối của node thường — to hơn mặc định cho dễ bắt chuột */
const PLAIN_HANDLE: React.CSSProperties = {
  width: 14, height: 14, borderRadius: "50%",
  background: "#64748b", border: "3px solid #0f172a", cursor: "crosshair",
};

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
      opacity: status === "skipped" ? 0.45 : 1,
      boxShadow: selected ? "0 0 0 2px rgba(96,165,250,0.3)" : undefined,
    }}>
      {!isTrigger && <Handle type="target" position={Position.Top} style={PLAIN_HANDLE} />}
      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", display: "flex", alignItems: "center", gap: 6 }}>
        <span>{def?.icon}</span>
        <span>{(data as any).label || def?.label}</span>
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        {nodeSummary(type as WorkflowNodeType, data)}
      </div>
      <Handle type="source" position={Position.Bottom} style={PLAIN_HANDLE} />
    </div>
  );
}

/** Node điều kiện: 1 handle vào, 2 handle ra (Đúng bên trái, Sai bên phải). */
function ConditionNodeView({ data, selected }: NodeProps) {
  const d = data as any;
  const status: NodeRunStatus = d._runStatus || "pending";
  const branch: string | undefined = d._branch;   // nhánh đã chọn khi chạy
  // Chấm to hẳn cho dễ bắt chuột — chấm nhỏ mặc định rất dễ trượt thành kéo cả node
  const handleStyle = (color: string): React.CSSProperties => ({
    background: color, width: 18, height: 18, borderRadius: "50%",
    border: "3px solid #0f172a", cursor: "crosshair", zIndex: 5,
  });
  return (
    <div style={{
      background: "#0f172a",
      border: `2px solid ${selected ? "#60a5fa" : STATUS_COLOR[status]}`,
      borderRadius: 10,
      padding: "10px 14px 22px",
      minWidth: 220,
      opacity: status === "skipped" ? 0.45 : 1,
      boxShadow: selected ? "0 0 0 2px rgba(96,165,250,0.3)" : undefined,
    }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", display: "flex", alignItems: "center", gap: 6 }}>
        <span>🔀</span>
        <span>{d.label || "Điều kiện"}</span>
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        {nodeSummary("logic.condition", d)}
      </div>

      {/* Nhãn 2 nhánh — mỗi nhãn nằm ngay trên chấm tương ứng (25% / 75%) */}
      <div style={{ display: "flex", marginTop: 10, fontSize: 10 }}>
        <span style={{
          flex: 1, textAlign: "center",
          color: branch === "false" ? "#475569" : "#4ade80",
          fontWeight: branch === "true" ? 700 : 400,
        }}>✔ {d.true_label || "Đúng"}</span>
        <span style={{
          flex: 1, textAlign: "center",
          color: branch === "true" ? "#475569" : "#f87171",
          fontWeight: branch === "false" ? 700 : 400,
        }}>✘ {d.false_label || "Sai"}</span>
      </div>

      <Handle id="true"  type="source" position={Position.Bottom} style={{ ...handleStyle("#4ade80"), left: "25%" }} />
      <Handle id="false" type="source" position={Position.Bottom} style={{ ...handleStyle("#f87171"), left: "75%" }} />
    </div>
  );
}

const nodeTypes = {
  "trigger.slack_mention": WorkflowNodeView,
  "action.generate_code":  WorkflowNodeView,
  "action.create_mr":      WorkflowNodeView,
  "action.code_review":    WorkflowNodeView,
  "action.custom":         WorkflowNodeView,
  "logic.condition":       ConditionNodeView,
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

      {node.type === "logic.condition" && (
        <>
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Quyết định nhánh bằng</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 12 }}
            value={data.mode || "manual"} onChange={e => set({ mode: e.target.value })}>
            <option value="manual">Tôi tự chọn khi chạy (file task)</option>
            <option value="auto">Tự động theo kết quả bước trước</option>
          </select>

          {(data.mode || "manual") === "manual" ? (
            <>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Câu hỏi / điều kiện</label>
              <textarea className="setting-input" style={{ width: "100%", minHeight: 80, resize: "vertical", marginBottom: 4 }}
                placeholder="vd: Code review có phát hiện lỗi nghiêm trọng không?"
                value={data.expression || ""} onChange={e => set({ expression: e.target.value })} />
              <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 12 }}>
                Khi chạy tới bước này, hệ thống tạo file task; bạn điền <code>decision: true</code> hoặc
                {" "}<code>decision: false</code> (hoặc bấm nút Đúng/Sai ở danh sách bước).
              </p>
            </>
          ) : (
            <>
              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Kết quả bước trước…</label>
              <select className="setting-select" style={{ width: "100%", marginBottom: 8 }}
                value={data.operator || "contains"} onChange={e => set({ operator: e.target.value })}>
                <option value="contains">chứa chuỗi</option>
                <option value="not_contains">không chứa chuỗi</option>
                <option value="equals">bằng đúng chuỗi</option>
                <option value="regex">khớp regex</option>
                <option value="is_empty">rỗng (không ghi gì)</option>
              </select>
              {data.operator !== "is_empty" && (
                <input className="setting-input" style={{ width: "100%", marginBottom: 4 }}
                  placeholder={data.operator === "regex" ? "vd: (lỗi|error|fail)" : "vd: OK"}
                  value={data.value || ""} onChange={e => set({ value: e.target.value })} />
              )}
              <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 12 }}>
                So khớp trên phần <code>## Kết quả</code> của các node nối trực tiếp vào đây. Không phân biệt hoa/thường.
              </p>
            </>
          )}

          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Nhãn nhánh ĐÚNG</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="Đúng" value={data.true_label || ""} onChange={e => set({ true_label: e.target.value })} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Nhãn nhánh SAI</label>
          <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
            placeholder="Sai" value={data.false_label || ""} onChange={e => set({ false_label: e.target.value })} />

          <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 12 }}>
            Nối tiếp từ chấm <span style={{ color: "#4ade80" }}>xanh (trái)</span> cho nhánh Đúng và
            {" "}<span style={{ color: "#f87171" }}>đỏ (phải)</span> cho nhánh Sai. Nhánh không được chọn sẽ bị
            đánh dấu “bỏ qua”, không sinh file task.
          </p>
        </>
      )}

      <button className="btn-danger" style={{ width: "100%" }} onClick={onDelete}>Xoá node</button>
    </div>
  );
}

// ── Canvas editor ─────────────────────────────────────────────────────────

let idCounter = 0;
const nextId = () => `node_${Date.now()}_${idCounter++}`;

/** Kích thước node để tính hình học (dùng số đo thật nếu React Flow đã đo xong). */
function nodeSize(n: Node): { w: number; h: number } {
  const m = (n as any).measured || {};
  return { w: m.width ?? (n as any).width ?? 200, h: m.height ?? (n as any).height ?? 70 };
}

/** Khoảng cách từ 1 điểm tới đoạn thẳng AB. */
function distToSegment(p: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }): number {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2));
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/**
 * Tìm đường nối gần điểm thả nhất (để chèn node vào giữa).
 * Xấp xỉ đường bezier bằng đoạn thẳng từ đáy node nguồn tới đỉnh node đích — đủ chính xác
 * vì người dùng thả vào khoảng giữa 2 node.
 */
function findEdgeNearPoint(
  point: { x: number; y: number }, nodes: Node[], edges: Edge[], threshold = 90,
): Edge | null {
  const byId = new Map(nodes.map(n => [n.id, n]));
  let best: Edge | null = null;
  let bestDist = threshold;
  for (const e of edges) {
    const s = byId.get(e.source), t = byId.get(e.target);
    if (!s || !t) continue;
    const ss = nodeSize(s), ts = nodeSize(t);
    const from = { x: s.position.x + ss.w / 2, y: s.position.y + ss.h };
    const to   = { x: t.position.x + ts.w / 2, y: t.position.y };
    const d = distToSegment(point, from, to);
    if (d < bestDist) { bestDist = d; best = e; }
  }
  return best;
}

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
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [hoverEdgeId, setHoverEdgeId]       = useState<string | null>(null);
  const [edgeMsg, setEdgeMsg]               = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [runId, setRunId] = useLatestRun(workflow.id);  // khôi phục run gần nhất sau reload
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [clientFolder, setClientFolder] = useState(workflow.client_folder || "");
  const { projects } = useProjects();

  const run = useWorkflowRun(runId);

  // Nhánh mà mỗi node điều kiện đã chọn trong lần chạy hiện tại (suy ra từ log)
  const branchByNode = useMemo(() => {
    const out: Record<string, "true" | "false"> = {};
    for (const entry of run?.log || []) {
      if (entry.message.includes("[điều kiện]")) {
        out[entry.node_id] = entry.message.includes("ĐÚNG") ? "true" : "false";
      }
    }
    return out;
  }, [run]);

  // Overlay run status onto nodes for rendering (transient, stripped before save)
  const displayNodes = useMemo(() => {
    if (!run) return nodes;
    return nodes.map(n => ({
      ...n,
      data: { ...n.data, _runStatus: run.node_status[n.id], _branch: branchByNode[n.id] },
    }));
  }, [nodes, run, branchByNode]);

  // Edge của node điều kiện: tô màu + gắn nhãn nhánh, làm mờ nhánh không được chọn.
  // Ngoài ra tô sáng edge đang được rê node lên (sắp chèn vào giữa) và edge đang chọn.
  const displayEdges = useMemo(() => edges.map(e => {
    const src = nodes.find(n => n.id === e.source);
    const isHover    = e.id === hoverEdgeId;
    const isSelected = e.id === selectedEdgeId;
    let out: Edge = { ...e, reconnectable: true } as Edge;

    if (src?.type === "logic.condition") {
      const isTrue = (e.sourceHandle || "true") === "true";
      const data = src.data as any;
      const chosen = branchByNode[e.source];
      const dimmed = chosen !== undefined && chosen !== (isTrue ? "true" : "false");
      const color = isTrue ? "#4ade80" : "#f87171";
      out = {
        ...out,
        label: isTrue ? (data.true_label || "Đúng") : (data.false_label || "Sai"),
        labelStyle: { fill: dimmed ? "#475569" : color, fontSize: 11 },
        labelBgStyle: { fill: "#0b1220" },
        style: { stroke: dimmed ? "#334155" : color, strokeWidth: 2, opacity: dimmed ? 0.4 : 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: dimmed ? "#334155" : color },
      } as Edge;
    }

    if (isHover || isSelected) {
      out = {
        ...out,
        style: { ...(out.style || {}), stroke: isHover ? "#60a5fa" : "#93c5fd", strokeWidth: 4, opacity: 1 },
        animated: isHover,
      } as Edge;
    }
    return out;
  }), [edges, nodes, branchByNode, hoverEdgeId, selectedEdgeId]);

  const selectedNode = nodes.find(n => n.id === selectedNodeId) || null;
  const selectedEdge = edges.find(e => e.id === selectedEdgeId) || null;

  const onConnect = useCallback((conn: Connection) => {
    setEdges(eds => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed } }, eds));
  }, [setEdges]);

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setHoverEdgeId(null);
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

    // Thả trúng 1 đường nối → CHÈN node vào giữa: A→B thành A→mới→B
    const isTrigger = type.startsWith("trigger.");
    const target = isTrigger ? null : findEdgeNearPoint(position, nodes, edges);
    if (target) {
      // canh node mới nằm ngay trên đường nối
      newNode.position = { x: position.x - 100, y: position.y - 35 };
      setEdges(eds => [
        ...eds.filter(e => e.id !== target.id),
        // đoạn đầu giữ nguyên nhánh Đúng/Sai của đường nối cũ
        { id: `e_${target.source}_${newNode.id}`, source: target.source, target: newNode.id,
          sourceHandle: target.sourceHandle ?? null, markerEnd: { type: MarkerType.ArrowClosed } },
        { id: `e_${newNode.id}_${target.target}`, source: newNode.id, target: target.target,
          markerEnd: { type: MarkerType.ArrowClosed } },
      ]);
      const srcLabel = (nodes.find(n => n.id === target.source)?.data as any)?.label || "bước trước";
      const tgtLabel = (nodes.find(n => n.id === target.target)?.data as any)?.label || "bước sau";
      setSaveMsg(`Đã chèn "${def.label}" vào giữa ${srcLabel} → ${tgtLabel}`);
      setTimeout(() => setSaveMsg(null), 4000);
    }

    setNodes(nds => [...nds, newNode]);
  }, [screenToFlowPosition, setNodes, setEdges, nodes, edges]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    // tô sáng đường nối sẽ bị chèn vào, để biết trước sẽ chèn ở đâu
    const p = screenToFlowPosition({ x: event.clientX, y: event.clientY });
    const near = findEdgeNearPoint(p, nodes, edges);
    setHoverEdgeId(near?.id ?? null);
  }, [screenToFlowPosition, nodes, edges]);

  const onDragLeave = useCallback(() => setHoverEdgeId(null), []);

  /** Kéo đầu mút 1 đường nối sang node khác — đổi bước kế tiếp mà không phải xoá nối lại. */
  const onReconnect = useCallback((oldEdge: Edge, newConn: Connection) => {
    setEdges(eds => reconnectEdge(oldEdge, newConn, eds));
  }, [setEdges]);

  const deleteEdge = useCallback((id: string) => {
    setEdges(eds => eds.filter(e => e.id !== id));
    setSelectedEdgeId(null);
  }, [setEdges]);

  /** Đổi node nguồn/đích (hoặc nhánh Đúng/Sai) của 1 đường nối bằng ô chọn. */
  const rewireEdge = useCallback((id: string, patch: Partial<Pick<Edge, "source" | "target" | "sourceHandle">>) => {
    setEdgeMsg(null);
    setEdges(eds => {
      const cur = eds.find(e => e.id === id);
      if (!cur) return eds;
      const next = { ...cur, ...patch } as Edge;
      if (next.source === next.target) {
        setEdgeMsg("Không thể nối 1 node vào chính nó");
        return eds;
      }
      const dup = eds.some(e => e.id !== id && e.source === next.source && e.target === next.target
        && (e.sourceHandle ?? null) === (next.sourceHandle ?? null));
      if (dup) {
        setEdgeMsg("Đường nối này đã có rồi");
        return eds;
      }
      return eds.map(e => e.id === id ? next : e);
    });
    setTimeout(() => setEdgeMsg(null), 4000);
  }, [setEdges]);

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
        const { _runStatus, _branch, ...rest } = n.data as any;
        return { id: n.id, type: n.type, position: n.position, data: rest };
      });
      // sourceHandle bắt buộc phải giữ — đó là thứ phân biệt nhánh Đúng/Sai
      const cleanEdges = edges.map(e => ({
        id: e.id, source: e.source, target: e.target,
        sourceHandle: e.sourceHandle ?? null, targetHandle: e.targetHandle ?? null,
      }));
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
        <p style={{ fontSize: 11, color: "#4b5563", marginTop: 16 }}>
          Kéo node vào canvas. Nối 2 node: kéo từ chấm dưới của node này thả vào chấm trên của node kia —
          hoặc <b>bấm 1 phát vào chấm nguồn rồi bấm vào chấm đích</b> (khỏi phải giữ chuột).
        </p>
        <p style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>
          <b>Chèn bước vào giữa</b>: kéo node từ đây <b>thả thẳng lên đường nối</b> (đường sẽ sáng xanh) —
          A→B tự thành A→bước mới→B.<br />
          <b>Đổi bước kế tiếp</b>: bấm vào đường nối → chọn lại node nguồn/đích ở thanh phía trên canvas.<br />
          <b>Xoá nối</b>: bấm vào đường nối rồi bấm Xoá (hoặc phím Delete).
        </p>
        <p style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>
          Node <b>Điều kiện If/Else</b> có 2 chấm ra: <span style={{ color: "#4ade80" }}>xanh = Đúng</span>,{" "}
          <span style={{ color: "#f87171" }}>đỏ = Sai</span>. Nhánh không được chọn sẽ bị bỏ qua.
        </p>
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

        {selectedEdge && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", flexWrap: "wrap",
            background: "#0b1220", borderBottom: "1px solid #1e293b", fontSize: 12, color: "#93c5fd",
          }}>
            <span>Đường nối:</span>
            <select className="setting-select" style={{ width: 190, fontSize: 11 }}
              value={selectedEdge.source} onChange={e => rewireEdge(selectedEdge.id, { source: e.target.value })}>
              {nodes.map(n => <option key={n.id} value={n.id}>{(n.data as any).label || n.id}</option>)}
            </select>

            {nodes.find(n => n.id === selectedEdge.source)?.type === "logic.condition" && (
              <select className="setting-select" style={{ width: 110, fontSize: 11 }}
                value={selectedEdge.sourceHandle || "true"}
                onChange={e => rewireEdge(selectedEdge.id, { sourceHandle: e.target.value })}>
                <option value="true">nhánh Đúng</option>
                <option value="false">nhánh Sai</option>
              </select>
            )}

            <span>→</span>
            <select className="setting-select" style={{ width: 190, fontSize: 11 }}
              value={selectedEdge.target} onChange={e => rewireEdge(selectedEdge.id, { target: e.target.value })}>
              {nodes.map(n => <option key={n.id} value={n.id}>{(n.data as any).label || n.id}</option>)}
            </select>

            <button className="btn-danger" style={{ fontSize: 11, padding: "2px 10px" }}
              onClick={() => deleteEdge(selectedEdge.id)}>Xoá đường nối</button>
            <button className="btn-muted" style={{ fontSize: 11, padding: "2px 10px" }}
              onClick={() => setSelectedEdgeId(null)}>Bỏ chọn</button>
            {edgeMsg && <span style={{ color: "#f87171" }}>{edgeMsg}</span>}
          </div>
        )}

        <div ref={wrapperRef} style={{ flex: 1 }} onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave}>
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onNodeClick={(_, n) => { setSelectedNodeId(n.id); setSelectedEdgeId(null); }}
            onEdgeClick={(_, e) => { setSelectedEdgeId(e.id); setSelectedNodeId(null); }}
            onPaneClick={() => { setSelectedNodeId(null); setSelectedEdgeId(null); }}
            onReconnect={onReconnect}
            edgesReconnectable
            deleteKeyCode={["Delete", "Backspace"]}
            connectionRadius={45}
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
