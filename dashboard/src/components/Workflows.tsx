import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useWorkflows, useWorkflowRun, useSkills, useLatestRun, useConfigAgents } from "../hooks/useWorkflows";
import { useProjects } from "../hooks/useProjects";
import RunSteps from "./RunSteps";
import RunConsole from "./RunConsole";
import {
  Workflow, WorkflowNodeType, WorkflowNodeData, NodeRunStatus, ConfigAgent,
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
  blocked: "#f59e0b",
};

const STATUS_BADGE: Partial<Record<NodeRunStatus, string>> = {
  running: "tới lượt bạn",
  ok:      "xong",
  error:   "lỗi",
  skipped: "bỏ qua",
  blocked: "chờ bạn xác nhận",
};

/** Nhãn trạng thái gắn trên node lúc chạy. Trước đây trạng thái chỉ thể hiện
 *  bằng màu viền, mà viền lại bị màu "đang chọn" đè lên → nhìn canvas không
 *  biết bước nào đang chờ mình. */
function StatusBadge({ status }: { status: NodeRunStatus }) {
  const text = STATUS_BADGE[status];
  if (!text) return null;
  return (
    <span style={{
      fontSize: 9, padding: "1px 6px", borderRadius: 9, whiteSpace: "nowrap",
      color: STATUS_COLOR[status], border: `1px solid ${STATUS_COLOR[status]}`,
    }}>{text}</span>
  );
}

const OPERATOR_LABEL: Record<string, string> = {
  contains:     "chứa",
  not_contains: "không chứa",
  equals:       "bằng đúng",
  regex:        "khớp regex",
  is_empty:     "rỗng",
};

function nodeSummary(type: WorkflowNodeType, data: any): string {
  if (type === "trigger.slack_mention") return `#${(data.channel || "").replace(/^#/, "")}${data.keyword ? ` · "${data.keyword}"` : ""}`;
  const withAgent = (base: string) =>
    data.agent_key ? `${base} · 🤖 ${data.agent_key}` : base;
  if (type === "action.generate_code")  return withAgent((data.skill_dirs || []).join("+") || "no skill");
  if (type === "action.create_mr")      return `${(data.provider || "").toUpperCase()} · ${data.repo || "no repo"}`;
  if (type === "action.code_review")    return withAgent((data.skill_dirs || []).join("+") || "no skill");
  if (type === "action.custom")         return withAgent((data.skill_dirs || []).join("+") || "no skill");
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
      border: `2px solid ${STATUS_COLOR[status]}`,
      outline: selected ? "2px solid #60a5fa" : undefined,
      outlineOffset: 2,
      borderRadius: 10,
      padding: "10px 14px",
      minWidth: 180,
      opacity: status === "skipped" ? 0.45 : 1,
    }}>
      {!isTrigger && <Handle type="target" position={Position.Left} style={PLAIN_HANDLE} />}
      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", display: "flex", alignItems: "center", gap: 6 }}>
        <span>{def?.icon}</span>
        <span style={{ flex: 1 }}>{(data as any).label || def?.label}</span>
        <StatusBadge status={status} />
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        {nodeSummary(type as WorkflowNodeType, data)}
      </div>
      <Handle type="source" position={Position.Right} style={PLAIN_HANDLE} />
    </div>
  );
}

/** Vị trí (theo chiều cao node) của 2 chấm ra nhánh — dùng chung cho handle và nhãn. */
const BRANCH_TOP = { true: "31%", false: "77%" } as const;

/** Node điều kiện: 1 handle vào bên trái, 2 handle ra bên phải (Đúng trên, Sai dưới). */
function ConditionNodeView({ data, selected }: NodeProps) {
  const d = data as any;
  const status: NodeRunStatus = d._runStatus || "pending";
  const branch: string | undefined = d._branch;   // nhánh đã chọn khi chạy
  // Chấm to hẳn cho dễ bắt chuột — chấm nhỏ mặc định rất dễ trượt thành kéo cả node
  const handleStyle = (color: string): React.CSSProperties => ({
    background: color, width: 18, height: 18, borderRadius: "50%",
    border: "3px solid #0f172a", cursor: "crosshair", zIndex: 5,
  });
  const branchLabel = (kind: "true" | "false"): React.CSSProperties => ({
    position: "absolute", right: 12, top: BRANCH_TOP[kind], transform: "translateY(-50%)",
    fontSize: 10, whiteSpace: "nowrap",
    color: branch !== undefined && branch !== kind ? "#475569" : (kind === "true" ? "#4ade80" : "#f87171"),
    fontWeight: branch === kind ? 700 : 400,
  });
  return (
    <div style={{
      background: "#0f172a",
      border: `2px solid ${STATUS_COLOR[status]}`,
      outline: selected ? "2px solid #60a5fa" : undefined,
      outlineOffset: 2,
      borderRadius: 10,
      // chừa lề phải cho 2 nhãn nhánh, và cao tối thiểu để 2 chấm ra không dính nhau
      padding: "10px 84px 10px 14px",
      minWidth: 250,
      minHeight: 88,
      position: "relative",
      opacity: status === "skipped" ? 0.45 : 1,
    }}>
      <Handle type="target" position={Position.Left} style={PLAIN_HANDLE} />
      <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0", display: "flex", alignItems: "center", gap: 6 }}>
        <span>🔀</span>
        <span style={{ flex: 1 }}>{d.label || "Điều kiện"}</span>
        <StatusBadge status={status} />
      </div>
      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        {nodeSummary("logic.condition", d)}
      </div>

      {/* Nhãn 2 nhánh — mỗi nhãn nằm ngay bên trái chấm tương ứng */}
      <span style={branchLabel("true")}>✔ {d.true_label || "Đúng"}</span>
      <span style={branchLabel("false")}>✘ {d.false_label || "Sai"}</span>

      <Handle id="true"  type="source" position={Position.Right} style={{ ...handleStyle("#4ade80"), top: BRANCH_TOP.true }} />
      <Handle id="false" type="source" position={Position.Right} style={{ ...handleStyle("#f87171"), top: BRANCH_TOP.false }} />
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

function SkillPicker({ value, onChange, skills, locked = [] }: {
  value: string[]; onChange: (v: string[]) => void; skills: string[];
  /** Skill đến từ vai trò của agent — luôn áp, không bỏ tick được */
  locked?: string[];
}) {
  const toggle = (s: string) => {
    onChange(value.includes(s) ? value.filter(x => x !== s) : [...value, s]);
  };
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {skills.map(s => {
        const isLocked = locked.includes(s);
        const checked = isLocked || value.includes(s);
        return (
        <label key={s} style={{
          display: "flex", alignItems: "center", gap: 4, fontSize: 12,
          background: isLocked ? "#312e81" : checked ? "#1e3a8a" : "#1e293b",
          border: `1px solid ${isLocked ? "#4338ca" : "#334155"}`,
          borderRadius: 6, padding: "3px 8px", cursor: isLocked ? "not-allowed" : "pointer",
          opacity: isLocked ? 0.85 : 1,
        }} title={isLocked ? "Skill của vai trò agent đã chọn — luôn được áp" : undefined}>
          <input type="checkbox" checked={checked} disabled={isLocked}
            onChange={() => toggle(s)} style={{ margin: 0 }} />
          {isLocked ? `🔒 ${s}` : s}
        </label>
        );
      })}
      {skills.length === 0 && <span style={{ fontSize: 12, color: "#4b5563" }}>Không tải được danh sách skill</span>}
    </div>
  );
}

function ConfigPanel({ node, skills, agents, onUpdate, onDelete, onClose }: {
  node: Node;
  skills: string[];
  agents: ConfigAgent[];
  onUpdate: (data: any) => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const data = node.data as any;
  const set = (patch: any) => onUpdate({ ...data, ...patch });

  // Chọn agent = nhận luôn skill của vai trò đó, y như pipeline. Không cho bỏ tick
  // để khỏi rơi vào cảnh "PM Agent nhưng đọc quy ước của leader".
  const selectedAgent = agents.find(a => a.key === (data.agent_key || "")) || null;
  const lockedSkills = selectedAgent ? ["shared", ...(selectedAgent.skill_dirs || [])] : [];

  /** Đổi agent → bỏ những skill vai trò của agent KHÁC đang tick, giữ skill lạ do
   *  người dùng tự thêm. Không dọn thì đổi từ Leader sang PM vẫn còn tick "leader". */
  const changeAgent = (key: string) => {
    const next = agents.find(a => a.key === key) || null;
    const roleSkills = new Set(agents.flatMap(a => a.skill_dirs || []));
    const keepMine = new Set([...(next?.skill_dirs || []), "shared"]);
    const cleaned = (data.skill_dirs || []).filter(
      (sk: string) => !roleSkills.has(sk) || keepMine.has(sk),
    );
    set({ agent_key: key || null, skill_dirs: cleaned });
  };

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
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Ai chạy bước này</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 4 }}
            value={data.agent_key || ""} onChange={e => changeAgent(e.target.value)}
            title="Chọn agent pipeline → bước chạy bằng opencode với model của agent đó. Để trống → Claude headless (nếu bật tự chạy) hoặc bạn chạy tay.">
            <option value="">🤖 Claude headless / bạn chạy tay</option>
            {agents.map(a => (
              <option key={a.key} value={a.key}>{a.name} — {a.tool} · {a.model}</option>
            ))}
          </select>
          <p style={{ fontSize: 11, color: "#4b5563", marginTop: 0, marginBottom: 12 }}>
            Chọn agent = dùng đúng tool/model khai trong <code>config/settings.toml</code>, cùng đội với pipeline
            {selectedAgent && <> — và nhận luôn skill <b>{["shared", ...(selectedAgent.skill_dirs || [])].join(" + ")}</b> của vai trò đó</>}.
          </p>

          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
            {lockedSkills.length > 0 ? "Skill thêm (ngoài skill của vai trò)" : "Skill"}
          </label>
          <div style={{ marginBottom: 4 }}>
            <SkillPicker value={data.skill_dirs || []} skills={skills} locked={lockedSkills}
              onChange={v => set({ skill_dirs: v })} />
          </div>
          <p style={{ fontSize: 11, color: "#4b5563", marginTop: 0, marginBottom: 12 }}>
            {lockedSkills.length > 0
              ? <>🔒 = skill của <b>{selectedAgent?.name}</b>, luôn được áp (giống pipeline). Tick thêm ô khác
                 chỉ khi bước này thật sự cần quy ước của vai trò khác.</>
              : <>Nội dung <code>skills/&lt;tên&gt;/*.md</code> được nhúng thẳng vào file task (kèm <code>shared</code>).</>}
          </p>
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
 * Xấp xỉ đường bezier bằng đoạn thẳng từ cạnh phải node nguồn tới cạnh trái node đích
 * (sơ đồ chạy ngang trái→phải) — đủ chính xác vì người dùng thả vào khoảng giữa 2 node.
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
    const from = { x: s.position.x + ss.w, y: s.position.y + ss.h / 2 };
    const to   = { x: t.position.x,           y: t.position.y + ts.h / 2 };
    const d = distToSegment(point, from, to);
    if (d < bestDist) { bestDist = d; best = e; }
  }
  return best;
}

/** Xếp lại toàn bộ sơ đồ theo chiều ngang trái→phải.
 *  Cột = độ sâu xa nhất tính từ node gốc, trong 1 cột thì xếp dọc theo thứ tự y hiện tại.
 *  Cần cho các workflow lưu từ trước (toạ độ còn xếp dọc) và cho lúc sơ đồ rối. */
const COL_GAP = 110;   // khoảng trống giữa 2 cột
const ROW_GAP = 40;    // khoảng trống giữa 2 node cùng cột

function layoutHorizontal(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;
  const depth = new Map<string, number>(nodes.map(n => [n.id, 0]));
  const ids = new Set(nodes.map(n => n.id));
  // nới lỏng nhiều vòng thay vì đệ quy — sơ đồ có vòng lặp cũng không treo
  for (let i = 0; i < nodes.length; i++) {
    let changed = false;
    for (const e of edges) {
      if (!ids.has(e.source) || !ids.has(e.target)) continue;
      const d = (depth.get(e.source) ?? 0) + 1;
      if (d > (depth.get(e.target) ?? 0)) { depth.set(e.target, d); changed = true; }
    }
    if (!changed) break;
  }

  const cols = new Map<number, Node[]>();
  for (const n of nodes) {
    const d = depth.get(n.id) ?? 0;
    const list = cols.get(d);
    if (list) list.push(n); else cols.set(d, [n]);
  }

  const colKeys = [...cols.keys()].sort((a, b) => a - b);
  const colHeight = (list: Node[]) =>
    list.reduce((h, n) => h + nodeSize(n).h, 0) + ROW_GAP * (list.length - 1);
  const tallest = Math.max(...colKeys.map(k => colHeight(cols.get(k)!)));

  const moved = new Map<string, { x: number; y: number }>();
  let x = 0;
  for (const k of colKeys) {
    const list = cols.get(k)!.sort((a, b) => a.position.y - b.position.y || a.position.x - b.position.x);
    let y = (tallest - colHeight(list)) / 2;    // canh giữa theo cột cao nhất
    for (const n of list) {
      moved.set(n.id, { x, y });
      y += nodeSize(n).h + ROW_GAP;
    }
    x += Math.max(...list.map(n => nodeSize(n).w)) + COL_GAP;
  }
  return nodes.map(n => ({ ...n, position: moved.get(n.id) ?? n.position }));
}

/** Trình soạn workflow. Dùng chung cho tab Workflows toàn cục và tab
 *  Workflows bên trong 1 project — bọc sẵn ReactFlowProvider ở dưới. */
export function WorkflowEditor({ workflow, onBack, onSaved, lockProject }: {
  workflow: Workflow;
  onBack: () => void;
  onSaved: () => void;
  /** true khi mở từ trong 1 project — workflow đã thuộc project đó, không cho đổi */
  lockProject?: boolean;
}) {
  const skills = useSkills();
  const configAgents = useConfigAgents();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition, fitView } = useReactFlow();

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
  // Bảng node và khối hướng dẫn ngốn gần hết cột trái mà chỉ cần lúc mới học
  // → thu được về dải icon 48px, hướng dẫn mặc định gập lại.
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [helpOpen, setHelpOpen]       = useState(false);

  // Editor là overlay full màn hình → khoá cuộn trang nền, tránh trang phía sau
  // trôi lộ ra khi lăn chuột trên canvas.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);
  const [runId, setRunId] = useLatestRun(workflow.id);  // khôi phục run gần nhất sau reload
  const [consoleOpen, setConsoleOpen] = useState(false);   // màn hình chạy riêng
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [clientFolder, setClientFolder] = useState(workflow.client_folder || "");
  const [autoRun, setAutoRun] = useState(Boolean(workflow.auto_run));
  const [savingAuto, setSavingAuto] = useState(false);
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
      // canh tâm node mới nằm ngay trên đường nối
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

  /** Xếp lại sơ đồ theo hàng ngang — hữu ích với workflow cũ lưu theo chiều dọc. */
  const handleAutoLayout = useCallback(() => {
    setNodes(nds => layoutHorizontal(nds, edges));
    // đợi React Flow đo lại node rồi mới fit, không thì fit theo kích thước cũ
    setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 80);
    setSaveMsg("Đã sắp xếp ngang — nhớ bấm Save");
    setTimeout(() => setSaveMsg(null), 4000);
  }, [setNodes, edges, fitView]);

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

  /** Bật/tắt tự chạy từng bước bằng Claude headless (worker trên máy bạn thực thi). */
  const handleAutoRunChange = async (next: boolean) => {
    setSavingAuto(true);
    setAutoRun(next);                                  // phản hồi ngay, khỏi chờ round-trip
    try {
      const res = await fetch(`/api/workflows/${workflow.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_run: next }),
      });
      if (res.ok) {
        setSaveMsg(next
          ? "Đã bật tự chạy — cần mở 1 terminal chạy `python worker.py`"
          : "Đã tắt tự chạy — các bước lại chờ bạn chạy tay");
        onSaved();
      } else {
        setAutoRun(!next);
        setSaveMsg("Không đổi được chế độ tự chạy");
      }
    } catch {
      setAutoRun(!next);
      setSaveMsg("Không đổi được chế độ tự chạy");
    } finally {
      setSavingAuto(false);
      setTimeout(() => setSaveMsg(null), 5000);
    }
  };

  const handleProjectChange = async (folder: string) => {
    setClientFolder(folder);
    const res = await fetch(`/api/workflows/${workflow.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_folder: folder }),
    });
    if (res.ok) { setSaveMsg(folder ? `Đã gắn project ${folder}` : "Đã chuyển thành mẫu — không chạy được nữa"); onSaved(); }
    else setSaveMsg("Lỗi khi đổi project");
    setTimeout(() => setSaveMsg(null), 3000);
  };

  return (
    // Editor chiếm trọn viewport: .main giới hạn max-width 1280px + padding 32px,
    // canvas bị bó lại rất chật. Overlay fixed thoát khỏi khung đó — nút
    // "← Danh sách" vẫn là đường ra nên không mất điều hướng.
    <div style={{
      position: "fixed", inset: 0, zIndex: 40, background: "#0b1120",
      display: "flex", flexDirection: "column",
    }}>
      {/* Thanh công cụ — trải hết chiều ngang màn hình */}
      <div style={{
        display: "flex", gap: 8, alignItems: "center", padding: "8px 14px",
        borderBottom: "1px solid #1e293b", background: "#0f172a", flexShrink: 0,
      }}>
        <button className="btn-muted" style={{ fontSize: 12, padding: "4px 10px" }}
          onClick={onBack}>← Danh sách</button>
        <strong style={{ fontSize: 14 }}>{workflow.name}</strong>
        {lockProject ? (
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {clientFolder ? `📁 ${clientFolder}` : "📋 Mẫu"}
          </span>
        ) : (
          <select className="setting-select" style={{ width: 210, fontSize: 12 }}
            value={clientFolder} onChange={e => handleProjectChange(e.target.value)}
            title="Project sở hữu workflow này — cũng là nơi ghi file task. Không chọn project = mẫu, không chạy được.">
            <option value="">📋 Mẫu — không chạy được</option>
            {projects.map(p => <option key={p.id} value={p.id}>📁 {p.name} ({p.id})</option>)}
          </select>
        )}
        <label style={{
          display: "flex", alignItems: "center", gap: 6, fontSize: 12,
          color: autoRun ? "#bfdbfe" : "#6b7280", cursor: savingAuto ? "wait" : "pointer",
          background: autoRun ? "#0b1e3a" : "transparent",
          border: `1px solid ${autoRun ? "#1e40af" : "#1e293b"}`,
          borderRadius: 6, padding: "3px 9px", whiteSpace: "nowrap",
        }} title={autoRun
          ? "ĐANG BẬT: mỗi bước được worker.py trên máy bạn chạy bằng `claude -p`, tuần tự 1 bước/lần"
          : "ĐANG TẮT: hệ thống chỉ soạn file task, bạn tự dán lệnh vào terminal"}>
          <input type="checkbox" checked={autoRun} disabled={savingAuto}
            onChange={e => handleAutoRunChange(e.target.checked)} style={{ margin: 0 }} />
          🤖 Tự chạy (Claude headless)
        </label>
        <div style={{ flex: 1 }} />
        {saveMsg && <span style={{ fontSize: 12, color: "#6b7280" }}>{saveMsg}</span>}
        <button className="btn-muted" onClick={handleAutoLayout}
          title="Xếp lại các bước thành hàng ngang trái→phải theo thứ tự chạy">⇄ Sắp xếp ngang</button>
        <button className="btn-muted" disabled={saving} onClick={handleSave}>{saving ? "Đang lưu..." : "Save"}</button>
        {run && run.status === "running" && (
          <button className="btn-muted" onClick={handleRefresh}>🔄 Kiểm tra ngay</button>
        )}
        <button className="btn-primary" disabled={running || !clientFolder} onClick={handleRun}
          style={!clientFolder ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
          title={!clientFolder
            ? "Đây là mẫu — chọn project ở trên, hoặc bấm 'Dùng mẫu' ngoài danh sách để nhân bản vào 1 project rồi chạy bản sao."
            : "Tạo lần chạy và soạn file task cho bước đầu tiên. Hệ thống KHÔNG tự gọi Claude — bạn chạy lệnh trong terminal của mình."}>
          {running ? "Đang xử lý..." : "▶ Bắt đầu"}
        </button>
      </div>

      {runError && <div className="state err" style={{ margin: "8px 14px" }}>{runError}</div>}

      {/* Hàng giữa: palette | canvas | cấu hình node */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{
          width: paletteOpen ? 186 : 48, flexShrink: 0, background: "#0b1220",
          borderRight: "1px solid #1e293b", padding: paletteOpen ? "10px 12px" : "10px 6px",
          overflowY: "auto",
        }}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
            {paletteOpen && (
              <h4 style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase", margin: 0, letterSpacing: 1 }}>
                Node
              </h4>
            )}
            <div style={{ flex: 1 }} />
            <button className="btn-muted" style={{ fontSize: 11, padding: "2px 7px" }}
              onClick={() => setPaletteOpen(o => !o)}
              title={paletteOpen ? "Thu bảng node cho canvas rộng ra" : "Mở bảng node"}>
              {paletteOpen ? "«" : "»"}
            </button>
          </div>

          {NODE_DEFS.map(def => (
            <div key={def.type} draggable title={def.label}
              onDragStart={e => e.dataTransfer.setData("application/x-workflow-node", def.type)}
              style={{
                background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
                padding: paletteOpen ? "7px 10px" : "7px 0", marginBottom: 6,
                cursor: "grab", fontSize: 12, display: "flex", alignItems: "center", gap: 6,
                justifyContent: paletteOpen ? "flex-start" : "center",
              }}>
              <span>{def.icon}</span>
              {paletteOpen && <span>{def.label}</span>}
            </div>
          ))}

          {paletteOpen && (
            <>
              <button className="btn-muted" style={{ width: "100%", fontSize: 11, marginTop: 8, padding: "3px 8px" }}
                onClick={() => setHelpOpen(h => !h)}>
                {helpOpen ? "▾" : "▸"} Hướng dẫn
              </button>
              {helpOpen && (
                <>
                  <p style={{ fontSize: 11, color: "#4b5563", marginTop: 10 }}>
                    Kéo node vào canvas. Sơ đồ chạy <b>từ trái sang phải</b>. Nối 2 node: kéo từ chấm bên phải
                    của node này thả vào chấm bên trái của node kia — hoặc <b>bấm 1 phát vào chấm nguồn rồi bấm
                    vào chấm đích</b> (khỏi phải giữ chuột). Sơ đồ rối thì bấm <b>⇄ Sắp xếp ngang</b> trên thanh công cụ.
                  </p>
                  <p style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>
                    <b>Chèn bước vào giữa</b>: kéo node từ đây <b>thả thẳng lên đường nối</b> (đường sẽ sáng xanh) —
                    A→B tự thành A→bước mới→B.<br />
                    <b>Đổi bước kế tiếp</b>: bấm vào đường nối → chọn lại node nguồn/đích ở thanh phía trên canvas.<br />
                    <b>Xoá nối</b>: bấm vào đường nối rồi bấm Xoá (hoặc phím Delete).
                  </p>
                  <p style={{ fontSize: 11, color: "#4b5563", marginTop: 8 }}>
                    Node <b>Điều kiện If/Else</b> có 2 chấm ra bên phải: <span style={{ color: "#4ade80" }}>xanh (trên) = Đúng</span>,{" "}
                    <span style={{ color: "#f87171" }}>đỏ (dưới) = Sai</span>. Nhánh không được chọn sẽ bị bỏ qua.
                  </p>
                </>
              )}
            </>
          )}
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
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

          <div ref={wrapperRef} style={{ flex: 1, minHeight: 0 }}
            onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave}>
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
        </div>

        {selectedNode && (
          <ConfigPanel
            node={selectedNode}
            skills={skills}
            agents={configAgents}
            onUpdate={updateSelectedData}
            onDelete={deleteSelected}
            onClose={() => setSelectedNodeId(null)}
          />
        )}
      </div>

      <RunSteps workflowId={workflow.id} runId={runId} onRunChange={setRunId}
        autoRun={autoRun} onOpenConsole={() => setConsoleOpen(true)} />

      {consoleOpen && (
        <RunConsole mode="overlay" initialWorkflowId={workflow.id} initialRunId={runId}
          onClose={() => setConsoleOpen(false)} />
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
  const [cloneOf, setCloneOf]         = useState<Workflow | null>(null);
  const [cloneFolder, setCloneFolder] = useState("");
  const [cloneBusy, setCloneBusy]     = useState(false);
  const [cloneErr, setCloneErr]       = useState<string | null>(null);

  // Mỗi project có danh sách workflow riêng → gom theo project. Workflow không
  // gắn project là MẪU: không chạy được, chỉ để nhân bản vào project.
  const groups = useMemo(() => {
    const nameOf = new Map(projects.map(p => [p.id, p.name]));
    const byFolder = new Map<string, Workflow[]>();
    for (const wf of workflows) {
      const key = wf.client_folder || "";
      byFolder.set(key, [...(byFolder.get(key) || []), wf]);
    }
    const entries = [...byFolder.entries()].map(([folder, list]) => ({
      folder,
      title: folder ? `📁 ${nameOf.get(folder) || folder}` : "📋 Mẫu — nhân bản vào project để chạy",
      list,
    }));
    entries.sort((a, b) => (a.folder === "" ? 1 : b.folder === "" ? -1 : a.title.localeCompare(b.title)));
    return entries;
  }, [workflows, projects]);

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

  // Nhân bản mẫu vào 1 project — bản sao tách rời hẳn, sửa nó không đụng mẫu.
  const handleClone = async () => {
    if (!cloneOf || !cloneFolder) return;
    setCloneBusy(true);
    try {
      const qs = new URLSearchParams({ client_folder: cloneFolder });
      const res = await fetch(`/api/workflows/${cloneOf.id}/clone?${qs}`, { method: "POST" });
      if (res.ok) {
        const wf = await res.json();
        setCloneOf(null);
        setCloneFolder("");
        await refetch();
        setSelected(wf);
      } else {
        const d = await res.json().catch(() => ({}));
        setCloneErr(d.detail || `Lỗi ${res.status}`);
      }
    } finally {
      setCloneBusy(false);
    }
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

      {showCreate && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h3>Create Workflow</h3>
          <input className="setting-input" style={{ width: "100%", marginBottom: 8 }}
            placeholder="vd: Slack → Code → MR → Review" value={name} onChange={e => setName(e.target.value)} />
          <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Project sở hữu</label>
          <select className="setting-select" style={{ width: "100%", marginBottom: 4 }}
            value={clientFolder} onChange={e => setClientFolder(e.target.value)}>
            <option value="">📋 Không chọn — tạo làm mẫu</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
          </select>
          <p style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>
            Có project → chạy được: task trong project đó chọn workflow này rồi bấm ▶.<br />
            Không project → là <b>mẫu</b>: không chạy, chỉ dùng để nhân bản sang project.
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-primary" disabled={creating || !name.trim()} onClick={handleCreate}>
              {creating ? "Creating..." : "Create"}
            </button>
            <button className="btn-muted" onClick={() => { setShowCreate(false); setName(""); setClientFolder(""); }}>Cancel</button>
          </div>
        </div>
      )}

      {cloneOf && (
        <div className="card" style={{ marginBottom: 20, borderLeft: "3px solid #60a5fa" }}>
          <h3 style={{ marginTop: 0 }}>Dùng mẫu "{cloneOf.name}"</h3>
          <p style={{ fontSize: 12, color: "#9ca3af", marginTop: 0 }}>
            Tạo 1 bản sao trong project bạn chọn. Bản sao chạy được và <b>tách rời hẳn</b> —
            sửa nó không ảnh hưởng mẫu gốc.
          </p>
          <select className="setting-select" style={{ width: "100%", marginBottom: 8 }}
            value={cloneFolder} onChange={e => setCloneFolder(e.target.value)}>
            <option value="">— Chọn project —</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name} ({p.id})</option>)}
          </select>
          {cloneErr && <div className="state err" style={{ marginBottom: 8 }}>{cloneErr}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn-primary" disabled={cloneBusy || !cloneFolder} onClick={handleClone}>
              {cloneBusy ? "Đang tạo..." : "Nhân bản vào project"}
            </button>
            <button className="btn-muted" onClick={() => { setCloneOf(null); setCloneErr(null); }}>Huỷ</button>
          </div>
        </div>
      )}

      {workflows.length === 0 && !showCreate && (
        <div className="state">Chưa có workflow nào. Tạo mới để bắt đầu thiết kế kéo-thả.</div>
      )}

      {groups.map(group => (
        <div key={group.folder || "_standalone"} style={{ marginBottom: 22 }}>
          <h4 style={{
            margin: "0 0 10px", fontSize: 12, color: "#9ca3af",
            textTransform: "uppercase", letterSpacing: 1,
            display: "flex", alignItems: "center", gap: 8,
          }}>
            {group.title}
            <span style={{ color: "#4b5563", letterSpacing: 0 }}>({group.list.length})</span>
          </h4>
          <div className="project-grid">
            {group.list.map(wf => (
              <div key={wf.id} className="project-card" onClick={() => setSelected(wf)}>
                <div className="project-card-top">
                  <span className="project-card-name">{wf.name}</span>
                  <span style={{ fontSize: 11, color: "#6b7280" }}>{wf.definition.nodes.length} node(s)</span>
                </div>
                {wf.description && <p className="project-card-desc">{wf.description}</p>}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 6, marginTop: 8 }}>
                  {!wf.client_folder && (
                    <button className="btn-muted" style={{ fontSize: 11, padding: "2px 8px" }}
                      title="Tạo 1 bản sao của mẫu này trong danh sách workflow của 1 project"
                      onClick={e => { e.stopPropagation(); setCloneErr(null); setCloneFolder(""); setCloneOf(wf); }}>
                      ＋ Dùng mẫu
                    </button>
                  )}
                  <button className="btn-danger" style={{ fontSize: 11, padding: "2px 8px" }}
                    onClick={e => { e.stopPropagation(); handleDelete(wf.id); }}>Delete</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
