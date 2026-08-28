import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useWorkflows, useStepJobs, useWorkerStatus } from "../hooks/useWorkflows";
import { STATUS_META, TYPE_ICON, StepRow, fmtTime, useCopy, useMarkDone } from "./RunSteps";
import { RunDetail, RunStep, WorkflowRun, WorkflowStepJob } from "../types";

/**
 * Màn hình chạy riêng.
 *
 * Bảng "Lần chạy" nằm dưới canvas chỉ cao ~42vh: lệnh copy-paste bị bó thành 1-2 dòng,
 * danh sách bước phải cuộn, muốn xem nội dung file task thì không còn chỗ. Màn hình này
 * tách hẳn phần chạy ra: lệnh to rõ, xem được file task ngay tại chỗ, timeline đầy đủ.
 *
 * Dùng 2 kiểu:
 *  - mode="page"    → tab "Lần chạy" trên thanh nav, tự chọn workflow.
 *  - mode="overlay" → mở đè lên trình soạn workflow, có nút quay lại sơ đồ.
 */

const POLL_MS = 4000;

function useRunDetail(runId: number | null) {
  const [detail, setDetail] = useState<RunDetail | null>(null);

  const load = useCallback(async () => {
    if (runId === null) { setDetail(null); return; }
    const res = await fetch(`/api/workflows/runs/${runId}/steps`);
    if (res.ok) setDetail(await res.json());
  }, [runId]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!detail || detail.status !== "running") return;
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [detail, load]);

  return { detail, reload: load };
}

function useRunList(workflowId: number | null) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);

  const load = useCallback(async () => {
    if (workflowId === null) { setRuns([]); return; }
    const res = await fetch(`/api/workflows/${workflowId}/runs?limit=30`);
    if (res.ok) setRuns(await res.json());
  }, [workflowId]);

  useEffect(() => { load(); }, [load]);
  return { runs, reload: load };
}

const JOB_META: Record<string, { label: string; color: string; bg: string }> = {
  queued:   { label: "đang chờ worker",       color: "#93c5fd", bg: "#0b1e3a" },
  running:  { label: "worker đang chạy...",   color: "#fbbf24", bg: "#422006" },
  done:     { label: "worker chạy xong",      color: "#4ade80", bg: "#052e16" },
  failed:   { label: "worker chạy lỗi",       color: "#f87171", bg: "#450a0a" },
  canceled: { label: "đã huỷ",                color: "#94a3b8", bg: "#1e293b" },
};

/** Trạng thái job tự chạy của 1 bước + nút chạy lại khi lỗi. */
function StepJobStatus({ job, onChanged }: { job: WorkflowStepJob; onChanged: () => void }) {
  const engine = job.tool === "opencode"
    ? `opencode${job.model ? ` · ${job.model}` : ""}`
    : "Claude headless";
  const [busy, setBusy] = useState(false);
  const meta = JOB_META[job.status] || JOB_META.queued;

  const retry = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/api/workflow-jobs/${job.id}/retry`, { method: "POST" });
      if (res.ok) onChanged();
    } finally { setBusy(false); }
  };

  return (
    <div style={{
      marginTop: 10, padding: "8px 10px", borderRadius: 8,
      background: meta.bg, border: `1px solid ${meta.color}44`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: meta.color }}>
        <span>🤖 {engine}: <b>{meta.label}</b></span>
        <div style={{ flex: 1 }} />
        {(job.status === "failed" || job.status === "canceled") && (
          <button className="btn-muted" style={{ fontSize: 11, padding: "2px 10px" }}
            disabled={busy} onClick={retry}>{busy ? "..." : "↻ Chạy lại bước này"}</button>
        )}
      </div>
      {job.status === "queued" && (
        <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
          Job đã xếp hàng. Nó chỉ chạy khi trên máy bạn có 1 terminal đang mở:{" "}
          <code style={{ color: "#93c5fd" }}>cd c:/www/ai_team_clean && python worker.py</code>
        </div>
      )}
      {job.error && (
        <pre style={{
          margin: "6px 0 0", fontSize: 11, color: "#fca5a5", whiteSpace: "pre-wrap",
          maxHeight: 120, overflow: "auto",
        }}>{job.error}</pre>
      )}
    </div>
  );
}

/** Thẻ bước đang chờ — bản đầy đủ: lệnh cỡ thật + xem được nội dung file task. */
function ConsoleActionCard({ step, runId, job, onChanged }: {
  step: RunStep; runId: number; job?: WorkflowStepJob; onChanged: () => void;
}) {
  const { copied, copy }   = useCopy(step.command);
  const { busy, markDone } = useMarkDone(runId, step.node_id, onChanged);
  const [fileOpen, setFileOpen] = useState(false);
  const [content, setContent]   = useState<string | null>(null);

  const toggleFile = async () => {
    const next = !fileOpen;
    setFileOpen(next);
    if (next && content === null) {
      const res = await fetch(`/api/workflows/runs/${runId}/nodes/${step.node_id}/file`);
      setContent(res.ok ? (await res.json()).content : "(không đọc được file)");
    }
  };

  return (
    <div style={{
      background: "#1c1408", border: "1px solid #78350f", borderLeft: "3px solid #f59e0b",
      borderRadius: 10, padding: "16px 18px", marginBottom: 14,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 18 }}>{TYPE_ICON[step.node_type] || "📄"}</span>
        <strong style={{ fontSize: 16, color: "#fde68a" }}>{step.label}</strong>
        <span style={{ fontSize: 12, color: "#a16207" }}>bước {step.order}</span>
        {step.skills.length > 0 && (
          <span style={{ fontSize: 12, color: "#93c5fd" }}>{step.skills.join(" + ")}</span>
        )}
        {step.agent && (
          <span style={{
            fontSize: 11, color: "#c4b5fd", background: "#1e1b4b",
            border: "1px solid #4338ca", borderRadius: 10, padding: "1px 8px",
          }} title={`Bước này chạy bằng ${step.agent.tool} · ${step.agent.model}`}>
            🤖 {step.agent.name}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {step.is_condition ? (
          <>
            <button className="btn-primary" style={{ fontSize: 13, padding: "6px 16px" }}
              disabled={busy} onClick={() => markDone("true")}>{busy ? "..." : "✔ Đúng"}</button>
            <button className="btn-danger" style={{ fontSize: 13, padding: "6px 16px" }}
              disabled={busy} onClick={() => markDone("false")}>{busy ? "..." : "✘ Sai"}</button>
          </>
        ) : (
          <button className="btn-primary" style={{ fontSize: 13, padding: "6px 16px" }}
            disabled={busy} onClick={() => markDone()}>{busy ? "..." : "✓ Đã chạy xong"}</button>
        )}
      </div>

      {step.command ? (
        <>
          <div style={{ fontSize: 12, color: "#d1a054", marginBottom: 6 }}>
            Mở terminal trên máy bạn và dán lệnh này:
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <code style={{
              flex: 1, fontSize: 13, lineHeight: 1.7, color: "#bfdbfe", background: "#0b1220",
              border: "1px solid #1e3a5f", borderRadius: 8, padding: "12px 14px",
              whiteSpace: "pre-wrap", wordBreak: "break-all", userSelect: "all",
            }}>{step.command}</code>
            <button className="btn-muted" style={{ fontSize: 13, padding: "10px 16px", whiteSpace: "nowrap" }}
              onClick={copy}>{copied ? "✓ Đã chép" : "📋 Copy"}</button>
          </div>
        </>
      ) : step.is_condition ? (
        <div style={{ fontSize: 13, color: "#d1a054" }}>
          Bước điều kiện — chọn nhánh bằng nút ✔ Đúng / ✘ Sai ở trên.
        </div>
      ) : (
        <div style={{
          fontSize: 13, color: "#fca5a5", background: "#1f0f0f", border: "1px solid #7f1d1d",
          borderRadius: 8, padding: "10px 12px",
        }}>
          Chưa có file task cho bước này — workflow đang <b>không gắn project</b> (đang là "Mẫu")
          nên hệ thống không soạn được lệnh. Vào tab Workflows → mở workflow → chọn project ở ô
          trên cùng, rồi bấm 🔄 Làm mới.
        </div>
      )}

      {step.file_path && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
          <span style={{ fontSize: 11, color: "#78716c", flex: 1, wordBreak: "break-all" }}>
            File task: {step.file_path}
          </span>
          <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }} onClick={toggleFile}>
            {fileOpen ? "Ẩn nội dung" : "Xem nội dung file"}
          </button>
        </div>
      )}

      {fileOpen && (
        <pre style={{
          margin: "10px 0 0", fontSize: 12, lineHeight: 1.6, color: "#9ca3af", background: "#0b1220",
          border: "1px solid #1e293b", borderRadius: 8, padding: 12,
          maxHeight: 380, overflow: "auto", whiteSpace: "pre-wrap",
        }}>{content ?? "Đang tải..."}</pre>
      )}

      {job && <StepJobStatus job={job} onChanged={onChanged} />}
    </div>
  );
}

export default function RunConsole({ mode = "page", initialWorkflowId = null, initialRunId = null, onClose }: {
  mode?: "page" | "overlay";
  initialWorkflowId?: number | null;
  initialRunId?: number | null;
  /** Có thì hiện nút quay lại (overlay mở từ trình soạn workflow) */
  onClose?: () => void;
}) {
  const { workflows, refetch: refetchWorkflows } = useWorkflows();
  const [workflowId, setWorkflowId] = useState<number | null>(initialWorkflowId);
  const [runId, setRunId]           = useState<number | null>(initialRunId);

  // Mở từ nav mà chưa chọn gì → nhảy vào workflow đầu tiên cho khỏi màn hình trống.
  // Nếu đã có sẵn runId (mở từ 1 task) thì để `detail` quyết định workflow, đừng
  // đoán bừa workflow đầu danh sách rồi kéo luôn cả ô chọn run đi theo.
  useEffect(() => {
    if (workflowId === null && initialRunId === null && workflows.length > 0) {
      setWorkflowId(workflows[0].id);
    }
  }, [workflows, workflowId, initialRunId]);

  const { runs, reload: reloadRuns } = useRunList(workflowId);

  useEffect(() => {
    if (runId === null && runs.length > 0) setRunId(runs[0].id);
  }, [runs, runId]);

  const { detail, reload: reloadDetail } = useRunDetail(runId);
  const refresh = useCallback(() => { reloadDetail(); reloadRuns(); }, [reloadDetail, reloadRuns]);

  // Ô chọn workflow luôn khớp với run đang xem
  useEffect(() => {
    if (detail && detail.workflow_id !== workflowId) setWorkflowId(detail.workflow_id);
  }, [detail, workflowId]);

  const [cancelling, setCancelling] = useState(false);
  const [cancelErr, setCancelErr]   = useState<string | null>(null);

  const workflow  = workflows.find(w => w.id === workflowId) || null;
  const autoRun   = Boolean(workflow?.auto_run);
  const { jobs, refetch: refetchJobs } = useStepJobs(runId, autoRun);
  const workerStatus = useWorkerStatus(autoRun);
  const jobByNode = useMemo(() => {
    const out: Record<string, WorkflowStepJob> = {};
    for (const j of jobs) if (!out[j.node_id]) out[j.node_id] = j;   // id giảm dần → job mới nhất
    return out;
  }, [jobs]);

  /** Bật/tắt tự chạy bằng Claude headless cho workflow đang xem. */
  const [savingAuto, setSavingAuto] = useState(false);
  const toggleAutoRun = async () => {
    if (!workflow) return;
    setSavingAuto(true);
    try {
      const res = await fetch(`/api/workflows/${workflow.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_run: !workflow.auto_run }),
      });
      if (res.ok) { await refetchWorkflows(); refetchJobs(); }
    } finally { setSavingAuto(false); }
  };

  /** Huỷ lần chạy đang dở — hệ thống chỉ ngừng chờ, file task vẫn còn trên đĩa. */
  const cancelRun = async () => {
    if (!detail) return;
    if (!window.confirm(
      `Huỷ run #${detail.run_id}?

` +
      "Các bước đang chờ bạn chạy sẽ bị bỏ qua. File task đã ghi vẫn giữ nguyên; " +
      "chạy lại workflow sẽ tạo lần chạy mới."
    )) return;
    setCancelling(true);
    setCancelErr(null);
    try {
      const res = await fetch(`/api/workflows/runs/${detail.run_id}/cancel`, { method: "POST" });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setCancelErr(d.detail || `Lỗi ${res.status}`);
        return;
      }
      refresh();
    } finally {
      setCancelling(false);
    }
  };

  const waiting = useMemo(
    () => (detail?.steps || []).filter(s => s.status === "running"),
    [detail],
  );

  const pct = detail && detail.total_steps > 0
    ? Math.round((detail.done_steps / detail.total_steps) * 100) : 0;
  const statusText = detail?.status === "done" ? "hoàn thành"
    : detail?.status === "cancelled" ? "đã huỷ"
    : detail?.status === "failed" ? "lỗi"
    : waiting.length > 0 ? `${waiting.length} bước chờ bạn`
    : detail ? "đang chạy" : "";
  const statusColor = detail?.status === "done" ? "#4ade80"
    : detail?.status === "failed" ? "#f87171"
    : detail?.status === "cancelled" ? "#6b7280"
    : waiting.length > 0 ? "#fbbf24" : "#6b7280";

  const shell: React.CSSProperties = mode === "overlay"
    ? { position: "fixed", inset: 0, zIndex: 50, background: "#0b1120", display: "flex", flexDirection: "column" }
    : { display: "flex", flexDirection: "column", minHeight: "calc(100vh - 180px)" };

  return (
    <div style={shell}>
      {/* Thanh chọn workflow / lần chạy + tiến độ */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        padding: mode === "overlay" ? "10px 16px" : "0 0 14px",
        borderBottom: "1px solid #1e293b", background: mode === "overlay" ? "#0f172a" : undefined,
      }}>
        {onClose && (
          <button className="btn-muted" style={{ fontSize: 12, padding: "4px 10px" }}
            onClick={onClose}>← Sơ đồ</button>
        )}
        <strong style={{ fontSize: 14 }}>Màn hình chạy</strong>

        <select className="setting-select" style={{ width: 250, fontSize: 12 }}
          value={workflowId ?? ""}
          onChange={e => { setWorkflowId(Number(e.target.value)); setRunId(null); }}
          title="Workflow muốn theo dõi">
          {workflows.length === 0 && <option value="">— chưa có workflow nào —</option>}
          {workflows.map(w => (
            <option key={w.id} value={w.id}>
              {w.client_folder ? `📁 ${w.client_folder} · ` : "📋 "}{w.name}
            </option>
          ))}
        </select>

        <select className="setting-select" style={{ width: 240, fontSize: 12 }}
          value={runId ?? ""} onChange={e => setRunId(Number(e.target.value))}
          title="Lần chạy">
          {runs.length === 0 && <option value="">— chưa có lần chạy nào —</option>}
          {runs.map(r => (
            <option key={r.id} value={r.id}>
              #{r.id} · {r.status} · {new Date(r.created_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}
            </option>
          ))}
        </select>

        {detail && (
          <>
            <div style={{ width: 160, background: "#1e293b", borderRadius: 4, height: 7, overflow: "hidden" }}>
              <div style={{
                width: `${pct}%`, height: "100%", borderRadius: 4,
                background: detail.status === "done" ? "#4ade80"
                  : detail.status === "running" ? "#fbbf24" : "#475569",
              }} />
            </div>
            <span style={{ fontSize: 12, color: "#6b7280" }}>{detail.done_steps}/{detail.total_steps} bước</span>
            <span style={{ fontSize: 12, color: statusColor, fontWeight: 600 }}>{statusText}</span>
          </>
        )}

        <div style={{ flex: 1 }} />
        {cancelErr && <span style={{ fontSize: 12, color: "#f87171" }}>{cancelErr}</span>}
        {detail?.status === "running" && (
          <button className="btn-danger" style={{ fontSize: 12, padding: "4px 10px" }}
            disabled={cancelling} onClick={cancelRun}
            title="Ngừng chờ lần chạy này — các bước đang chờ bạn sẽ bị bỏ qua">
            {cancelling ? "Đang huỷ..." : "⛔ Huỷ lần chạy"}
          </button>
        )}
        <button className="btn-muted" style={{ fontSize: 12, padding: "4px 10px" }} onClick={refresh}>
          🔄 Làm mới
        </button>
      </div>

      {/* Thân: cột trái = việc phải làm, cột phải = toàn bộ bước */}
      <div style={{
        flex: 1, display: "flex", gap: 18, minHeight: 0, alignItems: "flex-start",
        padding: mode === "overlay" ? "14px 16px" : "16px 0 0",
      }}>
        <div style={{ flex: 1, minWidth: 0, overflowY: "auto", maxHeight: mode === "overlay" ? "100%" : undefined }}>
          {!detail && (
            <div style={{ fontSize: 13, color: "#4b5563", padding: "40px 0", textAlign: "center" }}>
              {workflows.length === 0
                ? "Chưa có workflow nào."
                : "Workflow này chưa chạy lần nào — mở nó trong tab Workflows và bấm ▶ Bắt đầu."}
            </div>
          )}

          {detail && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
              fontSize: 12, marginBottom: 12, padding: "8px 12px", borderRadius: 8,
              background: autoRun ? "#0b1e3a" : "#1c1408",
              border: `1px solid ${autoRun ? "#1e40af" : "#78350f"}`,
              color: autoRun ? "#bfdbfe" : "#a16207",
            }}>
              <span style={{ flex: 1, minWidth: 280, lineHeight: 1.5 }}>
                {autoRun ? (
                  <>🤖 <b>Tự chạy bằng Claude headless: BẬT</b> — hệ thống soạn file task rồi xếp hàng
                  cho <code>worker.py</code> trên máy bạn chạy <code>claude -p</code> từng bước một.
                  Worker phải đang mở trong 1 terminal thì bước mới chạy.</>
                ) : (
                  <>👉 Hệ thống <b>không tự gọi Claude</b> — nó chỉ soạn sẵn file task rồi dừng.
                  Bạn chạy lệnh trong terminal của mình, xong thì bấm ✓ để mở bước kế tiếp.</>
                )}
              </span>
              {autoRun && workerStatus && (
                <span style={{
                  fontSize: 11, padding: "3px 9px", borderRadius: 10, whiteSpace: "nowrap",
                  color: workerStatus.online ? "#4ade80" : "#fca5a5",
                  background: workerStatus.online ? "#052e16" : "#450a0a",
                  border: `1px solid ${workerStatus.online ? "#166534" : "#7f1d1d"}`,
                }} title={workerStatus.online
                  ? "worker.py đang poll hàng đợi"
                  : "Không thấy worker hỏi việc — hoặc chưa chạy `python worker.py`, hoặc nó đang bận 1 job pipeline"}>
                  {workerStatus.online ? "● worker đang chạy" : "○ worker chưa chạy"}
                </span>
              )}
              {workflow && (
                <label style={{
                  display: "flex", alignItems: "center", gap: 6, cursor: savingAuto ? "wait" : "pointer",
                  color: "#e2e8f0", whiteSpace: "nowrap",
                }} title="Bật thì worker trên máy bạn tự chạy từng bước bằng claude -p; tắt thì bạn tự chạy tay">
                  <input type="checkbox" checked={autoRun} disabled={savingAuto}
                    onChange={toggleAutoRun} style={{ margin: 0 }} />
                  Tự chạy (Claude headless)
                </label>
              )}
            </div>
          )}

          {detail && waiting.map(s => (
            <ConsoleActionCard key={s.node_id} step={s} runId={detail.run_id}
              job={jobByNode[s.node_id]}
              onChanged={() => { refresh(); refetchJobs(); }} />
          ))}

          {detail && waiting.length === 0 && (
            <div style={{
              fontSize: 13, color: detail.status === "done" ? "#4ade80"
                : detail.status === "failed" ? "#fca5a5" : "#9ca3af",
              background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: "18px 20px",
            }}>
              {detail.status === "done"
                ? "✓ Lần chạy này đã hoàn thành — không còn bước nào chờ bạn."
                : detail.status === "cancelled"
                ? "⛔ Lần chạy này đã bị huỷ. File task đã ghi vẫn còn trên đĩa; chạy lại workflow sẽ tạo lần chạy mới."
                : detail.status === "failed"
                ? "Lần chạy này đã dừng vì lỗi."
                : "Không có bước nào chờ bạn — các bước còn lại đang đợi bước trước hoàn tất."}
            </div>
          )}

          {/* Kết quả các bước đã xong — đọc lại được mà không phải bung từng dòng */}
          {detail && detail.steps.some(s => s.result) && (
            <div style={{ marginTop: 20 }}>
              <h4 style={{ fontSize: 12, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 1, margin: "0 0 10px" }}>
                Kết quả đã ghi
              </h4>
              {detail.steps.filter(s => s.result).map(s => (
                <div key={s.node_id} style={{
                  background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8,
                  padding: "10px 14px", marginBottom: 8,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span>{TYPE_ICON[s.node_type] || "📄"}</span>
                    <strong style={{ fontSize: 13, color: "#e2e8f0" }}>{s.label}</strong>
                    <span style={{ fontSize: 11, color: STATUS_META[s.status].color }}>
                      {STATUS_META[s.status].label}
                    </span>
                    <div style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, color: "#4b5563" }}>
                      {fmtTime(s.finished_at)}{s.duration_s !== null ? ` · ${s.duration_s}s` : ""}
                    </span>
                  </div>
                  <pre style={{
                    margin: 0, fontSize: 12, lineHeight: 1.6, color: "#cbd5e1", background: "#0b1220",
                    border: "1px solid #1e293b", borderRadius: 6, padding: 10,
                    maxHeight: 220, overflow: "auto", whiteSpace: "pre-wrap",
                  }}>{s.result}</pre>
                </div>
              ))}
            </div>
          )}
        </div>

        {detail && <div style={{
          width: 420, flexShrink: 0, background: "#0f172a", border: "1px solid #1e293b",
          borderRadius: 10, padding: "12px 14px",
          maxHeight: mode === "overlay" ? "100%" : undefined, overflowY: "auto",
        }}>
          <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 10, textTransform: "uppercase", letterSpacing: 1 }}>
            Toàn bộ các bước
          </div>
          {detail.steps.map(s => <StepRow key={s.node_id} step={s} />)}

          {(
            <div style={{ fontSize: 11, color: "#4b5563", marginTop: 12, borderTop: "1px solid #1e293b", paddingTop: 10 }}>
              Run #{detail.run_id} · {detail.workflow_name}
              {detail.client_folder ? ` · 📁 ${detail.client_folder}` : ""}<br />
              bắt đầu {fmtTime(detail.created_at)}
              {detail.finished_at ? ` · xong ${fmtTime(detail.finished_at)}` : ""}
            </div>
          )}
        </div>}
      </div>
    </div>
  );
}
