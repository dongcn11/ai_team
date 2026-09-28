import { useEffect, useState } from "react";
import { ProjectSummary } from "../types";

/* Nháp task Claude soạn từ cuộc trò chuyện. Người dùng sửa, chọn dự án/workflow/
   agent rồi bấm Tạo → thành Feature thật của dự án (api: /assistant/messages/{id}/create-task). */

export interface Draft {
  name: string;
  description: string;
  acceptance_criteria: string;
  priority: "high" | "medium" | "low";
  project: string;
}

export interface Created {
  client_folder: string;
  task_id: number;
  name: string;
  workflow_id: number | null;
  run_id: number | null;
  run_error: string | null;
}

interface WorkflowLite { id: number; name: string; is_active?: boolean }
interface AgentLite { key: string; name: string; tool?: string; model?: string }

// Giống Projects.tsx — chỉ agent dev mới nhận feature.
const DEV_AGENT_KEYS = ["be1", "be2", "fe1", "fe2", "fs1", "fs2"];

export default function TaskDraftCard({ msgId, draft, created, projects, onCreated, onOpenProject }: {
  msgId: number;
  draft: Draft;
  created: Created | null;
  projects: ProjectSummary[];
  onCreated: () => void;
  onOpenProject?: (slug: string) => void;
}) {
  const [f, setF] = useState<Draft>(draft);
  const [workflows, setWorkflows] = useState<WorkflowLite[]>([]);
  const [agents, setAgents] = useState<AgentLite[]>([]);
  const [workflowId, setWorkflowId] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [runNow, setRunNow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // KHÔNG đồng bộ lại theo prop `draft`: màn hình poll vài giây/lần, mỗi lần là
  // object mới — đồng bộ theo nó thì chữ người dùng đang sửa bị xoá liên tục.
  const isCreated = !!created;

  // Đổi dự án → nạp lại workflow + agent của đúng dự án đó.
  useEffect(() => {
    setWorkflowId(""); setAgentKey(""); setWorkflows([]); setAgents([]);
    if (!f.project || isCreated) return;
    let alive = true;
    fetch(`/api/workflows/?client_folder=${encodeURIComponent(f.project)}`)
      .then(r => r.ok ? r.json() : []).then(ws => { if (alive) setWorkflows(ws); }).catch(() => null);
    fetch(`/api/projects/${encodeURIComponent(f.project)}/settings-agents`)
      .then(r => r.ok ? r.json() : []).then(as => { if (alive) setAgents(as); }).catch(() => null);
    return () => { alive = false; };
  }, [f.project, isCreated]);

  const set = (patch: Partial<Draft>) => setF(prev => ({ ...prev, ...patch }));

  const submit = async () => {
    if (!f.project || !f.name.trim()) return;
    setSaving(true); setErr(null);
    try {
      const res = await fetch(`/api/assistant/messages/${msgId}/create-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_folder: f.project, name: f.name, description: f.description,
          acceptance_criteria: f.acceptance_criteria, priority: f.priority,
          workflow_id: workflowId ? Number(workflowId) : null,
          agent_key: agentKey || null,
          run_now: runNow && !!workflowId,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Không tạo được task");
    } finally {
      setSaving(false);
    }
  };

  if (created) {
    const pname = projects.find(p => p.id === created.client_folder)?.name ?? created.client_folder;
    return (
      <div className="ah-draft done">
        <div className="ah-draft-head">✅ Đã tạo task <b>#{created.task_id}</b> cho dự án <b>{pname}</b></div>
        <div className="ah-draft-title">{created.name}</div>
        {created.run_id && <div className="ah-draft-note">▶️ Đã chạy workflow — lần chạy #{created.run_id} (xem ở cột Công việc)</div>}
        {created.run_error && <div className="ah-draft-err">Task đã tạo nhưng chưa chạy được workflow: {created.run_error}</div>}
        {onOpenProject && (
          <button className="ah-link" onClick={() => onOpenProject(created.client_folder)}>Mở ở tab Projects →</button>
        )}
      </div>
    );
  }

  const devAgents = agents.filter(a => DEV_AGENT_KEYS.includes(a.key));
  return (
    <div className="ah-draft">
      <div className="ah-draft-head">📋 Nháp task — sửa lại nếu cần rồi bấm Tạo</div>

      <label>Dự án</label>
      <select value={f.project} onChange={e => set({ project: e.target.value })}>
        <option value="">— chọn dự án —</option>
        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <label>Tên task</label>
      <input value={f.name} onChange={e => set({ name: e.target.value })} />

      <label>Mô tả</label>
      <textarea rows={5} value={f.description} onChange={e => set({ description: e.target.value })} />

      <label>Tiêu chí nghiệm thu</label>
      <textarea rows={3} value={f.acceptance_criteria} onChange={e => set({ acceptance_criteria: e.target.value })} />

      <div className="ah-draft-row">
        <div>
          <label>Ưu tiên</label>
          <select value={f.priority} onChange={e => set({ priority: e.target.value as Draft["priority"] })}>
            <option value="high">Cao</option>
            <option value="medium">Trung bình</option>
            <option value="low">Thấp</option>
          </select>
        </div>
        <div>
          <label>Workflow</label>
          <select value={workflowId} onChange={e => setWorkflowId(e.target.value)} disabled={!f.project}>
            <option value="">— chưa chọn —</option>
            {workflows.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        </div>
        <div>
          <label>Agent dev</label>
          <select value={agentKey} onChange={e => setAgentKey(e.target.value)} disabled={!f.project}>
            <option value="">— theo workflow —</option>
            {devAgents.map(a => <option key={a.key} value={a.key}>{a.name} ({a.key})</option>)}
          </select>
        </div>
      </div>

      {workflowId && (
        <label className="ah-draft-check">
          <input type="checkbox" checked={runNow} onChange={e => setRunNow(e.target.checked)} />
          Chạy workflow ngay sau khi tạo
        </label>
      )}

      {err && <div className="ah-draft-err">{err}</div>}
      <div className="ah-draft-foot">
        {!f.project && <span>Chọn dự án để tạo task</span>}
        <button className="ah-send" disabled={!f.project || !f.name.trim() || saving} onClick={submit}>
          {saving ? "Đang tạo…" : runNow && workflowId ? "Tạo & chạy" : "Tạo task"}
        </button>
      </div>
    </div>
  );
}
