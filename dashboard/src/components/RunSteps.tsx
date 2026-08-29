import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RunDetail, RunStep, WorkflowRun, NodeRunStatus } from "../types";

// "running" = hệ thống ĐÃ soạn xong file task và đang chờ NGƯỜI DÙNG tự chạy.
// Nhãn cũ ("chờ chạy") khiến người dùng tưởng hệ thống đang tự chạy và phải ngồi
// đợi, nên đổi thành lời kêu gọi hành động rõ ràng.
export const STATUS_META: Record<NodeRunStatus, { color: string; bg: string; label: string; dot: string }> = {
  pending: { color: "#64748b", bg: "#0f172a", label: "chưa tới",     dot: "○" },
  running: { color: "#fbbf24", bg: "#422006", label: "tới lượt bạn", dot: "◐" },
  ok:      { color: "#4ade80", bg: "#052e16", label: "xong",         dot: "●" },
  error:   { color: "#f87171", bg: "#450a0a", label: "lỗi",          dot: "✕" },
  skipped: { color: "#64748b", bg: "#0f172a", label: "bỏ qua",       dot: "⊘" },
  blocked: { color: "#fde68a", bg: "#1c1408", label: "chờ bạn xác nhận", dot: "?" },
};

export const TYPE_ICON: Record<string, string> = {
  "trigger.slack_mention": "💬",
  "action.generate_code":  "⚙️",
  "action.create_mr":      "🔀",
  "action.code_review":    "👀",
  "action.custom":         "🧩",
  "logic.condition":       "🔀",
};

export function fmtTime(iso: string | null) {
  return iso ? new Date(iso).toLocaleTimeString("vi-VN") : "—";
}

export function useCopy(text: string | null) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard bị chặn (http, quyền trình duyệt) */ }
  }, [text]);
  return { copied, copy };
}

export function useMarkDone(runId: number, nodeId: string, onChanged: () => void) {
  const [busy, setBusy] = useState(false);
  const markDone = useCallback(async (decision?: "true" | "false") => {
    setBusy(true);
    try {
      const qs = decision ? `?decision=${decision}` : "";
      const res = await fetch(`/api/workflows/runs/${runId}/nodes/${nodeId}/done${qs}`, { method: "POST" });
      if (res.ok) onChanged();
    } finally { setBusy(false); }
  }, [runId, nodeId, onChanged]);
  return { busy, markDone };
}

/** Thẻ nổi bật cho bước đang chờ người dùng. Lệnh copy-paste là thứ quan trọng
 *  nhất màn hình nên phải đọc được: xuống dòng, cỡ chữ thật — không phải dòng
 *  10px cuộn ngang lẫn giữa các badge. */
function ActionCard({ step, runId, onChanged }: { step: RunStep; runId: number; onChanged: () => void }) {
  const { copied, copy } = useCopy(step.command);
  const { busy, markDone } = useMarkDone(runId, step.node_id, onChanged);

  return (
    <div style={{
      background: "#1c1408", border: "1px solid #78350f", borderLeft: "3px solid #f59e0b",
      borderRadius: 8, padding: "12px 14px", marginBottom: 10,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 14 }}>{TYPE_ICON[step.node_type] || "📄"}</span>
        <strong style={{ fontSize: 14, color: "#fde68a" }}>{step.label}</strong>
        {step.skills.length > 0 && (
          <span style={{ fontSize: 11, color: "#93c5fd" }}>{step.skills.join(" + ")}</span>
        )}
        <span style={{ fontSize: 11, color: "#a16207" }}>bước {step.order}</span>
        <div style={{ flex: 1 }} />
        {step.is_condition ? (
          <>
            <button className="btn-primary" style={{ fontSize: 12, padding: "4px 12px" }}
              disabled={busy} onClick={() => markDone("true")}>{busy ? "..." : "✔ Đúng"}</button>
            <button className="btn-danger" style={{ fontSize: 12, padding: "4px 12px" }}
              disabled={busy} onClick={() => markDone("false")}>{busy ? "..." : "✘ Sai"}</button>
          </>
        ) : (
          <button className="btn-primary" style={{ fontSize: 12, padding: "4px 12px" }}
            disabled={busy} onClick={() => markDone()}>{busy ? "..." : "✓ Đã chạy xong"}</button>
        )}
      </div>

      {step.command ? (
        <>
          <div style={{ fontSize: 11, color: "#d1a054", marginBottom: 5 }}>
            Mở terminal trên máy bạn và dán lệnh này:
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <code style={{
              flex: 1, fontSize: 12, lineHeight: 1.55, color: "#bfdbfe", background: "#0b1220",
              border: "1px solid #1e3a5f", borderRadius: 6, padding: "8px 10px",
              whiteSpace: "pre-wrap", wordBreak: "break-all", userSelect: "all",
            }}>{step.command}</code>
            <button className="btn-muted" style={{ fontSize: 12, padding: "6px 12px", whiteSpace: "nowrap" }}
              onClick={copy}>{copied ? "✓ Đã chép" : "📋 Copy"}</button>
          </div>
        </>
      ) : step.is_condition ? (
        <div style={{ fontSize: 12, color: "#d1a054" }}>
          Bước điều kiện — chọn nhánh bằng nút ✔ Đúng / ✘ Sai ở trên.
        </div>
      ) : (
        <div style={{
          fontSize: 12, color: "#fca5a5", background: "#1f0f0f", border: "1px solid #7f1d1d",
          borderRadius: 6, padding: "8px 10px",
        }}>
          Chưa có file task cho bước này — workflow đang <b>không gắn project</b> (đang là "Mẫu")
          nên hệ thống không soạn được lệnh. Vào tab Workflows → mở workflow → chọn project ở ô trên
          cùng, rồi bấm 🔄 Làm mới.
        </div>
      )}

      {step.file_path && (
        <div style={{ fontSize: 10, color: "#78716c", marginTop: 6 }}>File task: {step.file_path}</div>
      )}
    </div>
  );
}

/** Hàng gọn trong danh sách — chỉ để nhìn tiến độ; chi tiết bung ra khi bấm. */
export function StepRow({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(false);
  const meta = STATUS_META[step.status] ?? STATUS_META.pending;
  const hasDetail = Boolean(step.result || step.command);

  return (
    <div style={{ display: "flex", gap: 8 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 16, paddingTop: 9 }}>
        <span style={{ color: meta.color, fontSize: 12, lineHeight: 1 }}>{meta.dot}</span>
        <div style={{ flex: 1, width: 1, background: "#1e293b", marginTop: 3 }} />
      </div>

      <div style={{ flex: 1, marginBottom: 4 }}>
        <div
          onClick={() => hasDetail && setOpen(o => !o)}
          style={{
            display: "flex", alignItems: "center", gap: 8, padding: "5px 10px",
            background: step.status === "running" ? "#1c1408" : "transparent",
            border: `1px solid ${step.status === "running" ? "#78350f" : "#1e293b"}`,
            borderRadius: 6, cursor: hasDetail ? "pointer" : "default",
          }}>
          <span style={{ fontSize: 11, color: "#4b5563", minWidth: 16 }}>{step.order}.</span>
          <span style={{ fontSize: 12 }}>{TYPE_ICON[step.node_type] || "📄"}</span>
          <span style={{
            fontSize: 12.5, flex: 1,
            color: step.status === "pending" ? "#64748b" : "#e2e8f0",
            textDecoration: step.status === "skipped" ? "line-through" : undefined,
          }}>{step.label}</span>

          {step.skills.length > 0 && (
            <span style={{ fontSize: 10, color: "#5b7fa8" }}>{step.skills.join("+")}</span>
          )}
          {step.duration_s !== null && (
            <span style={{ fontSize: 10, color: "#4b5563" }}>{step.duration_s}s</span>
          )}
          {step.branch && (
            <span style={{
              fontSize: 10, padding: "1px 7px", borderRadius: 10,
              color: step.branch === "true" ? "#4ade80" : "#f87171",
              background: step.branch === "true" ? "#052e16" : "#450a0a",
            }}>
              {step.branch === "true" ? "Đúng" : "Sai"}
            </span>
          )}
          <span style={{ fontSize: 10, color: meta.color, background: meta.bg, padding: "1px 8px", borderRadius: 10 }}>
            {meta.label}
          </span>
          <span style={{ fontSize: 9, color: "#374151", width: 8 }}>{hasDetail ? (open ? "▾" : "▸") : ""}</span>
        </div>

        {open && (
          <div style={{ padding: "6px 10px 2px 34px" }}>
            <div style={{ fontSize: 10, color: "#4b5563" }}>
              {step.started_at && <>bắt đầu {fmtTime(step.started_at)}</>}
              {step.finished_at && <> · xong {fmtTime(step.finished_at)}</>}
            </div>
            {step.command && (
              <code style={{
                display: "block", marginTop: 5, fontSize: 11, color: "#93c5fd", background: "#0b1220",
                border: "1px solid #1e293b", borderRadius: 5, padding: "6px 8px",
                whiteSpace: "pre-wrap", wordBreak: "break-all",
              }}>{step.command}</code>
            )}
            {step.result && (
              <pre style={{
                margin: "5px 0 0", fontSize: 11, color: "#cbd5e1", background: "#0b1220",
                border: "1px solid #1e293b", borderRadius: 5, padding: 8,
                maxHeight: 160, overflow: "auto", whiteSpace: "pre-wrap",
              }}>{step.result}</pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function RunSteps({ workflowId, runId, onRunChange, onOpenConsole, autoRun }: {
  workflowId: number;
  runId: number | null;
  onRunChange: (id: number) => void;
  /** Mở màn hình chạy riêng (toàn màn hình) — bảng dưới canvas chỉ đủ chỗ cho 1-2 bước */
  onOpenConsole?: () => void;
  /** Workflow đang bật tự chạy bằng Claude headless → đổi lời nhắc cho khớp */
  autoRun?: boolean;
}) {
  const [detail, setDetail]       = useState<RunDetail | null>(null);
  const [runs, setRuns]           = useState<WorkflowRun[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  const loadRuns = useCallback(async () => {
    const res = await fetch(`/api/workflows/${workflowId}/runs?limit=20`);
    if (res.ok) setRuns(await res.json());
  }, [workflowId]);

  const loadDetail = useCallback(async () => {
    if (runId === null) { setDetail(null); return; }
    const res = await fetch(`/api/workflows/runs/${runId}/steps`);
    if (res.ok) setDetail(await res.json());
  }, [runId]);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => { loadDetail(); }, [loadDetail]);

  // poll khi run chưa kết thúc
  useEffect(() => {
    if (!detail || detail.status !== "running") return;
    const id = setInterval(loadDetail, 4000);
    return () => clearInterval(id);
  }, [detail, loadDetail]);

  const refresh = useCallback(() => { loadDetail(); loadRuns(); }, [loadDetail, loadRuns]);

  // Mở 1 run đã xong thì không có gì để thao tác → gập lại, nhường chỗ cho canvas.
  // Chỉ quyết định 1 lần cho mỗi run, không tự gập ngay lúc user vừa bấm xong bước cuối.
  const decidedFor = useRef<number | null>(null);
  useEffect(() => {
    if (!detail || decidedFor.current === detail.run_id) return;
    decidedFor.current = detail.run_id;
    setCollapsed(detail.status === "done");
  }, [detail]);

  // Có thể nhiều bước cùng chờ (2 nhánh song song) — đưa hết lên đầu.
  const waiting = useMemo(
    () => (detail?.steps || []).filter(s => s.status === "running"),
    [detail],
  );

  if (runId === null) {
    return (
      <div style={{ padding: "8px 14px", fontSize: 12, color: "#4b5563", borderTop: "1px solid #1e293b" }}>
        Chưa có lần chạy nào — bấm <b style={{ color: "#6b7280" }}>▶ Bắt đầu</b> để hệ thống soạn file task cho bước đầu tiên.
      </div>
    );
  }

  const pct = detail && detail.total_steps > 0 ? Math.round((detail.done_steps / detail.total_steps) * 100) : 0;
  const statusText = detail?.status === "done" ? "hoàn thành"
    : detail?.status === "cancelled" ? "đã huỷ"
    : detail?.status === "failed" ? "lỗi"
    : waiting.length > 0 ? `${waiting.length} bước chờ bạn`
    : "đang chạy";
  const statusColor = detail?.status === "done" ? "#4ade80"
    : detail?.status === "failed" ? "#f87171"
    : detail?.status === "cancelled" ? "#6b7280"
    : waiting.length > 0 ? "#fbbf24" : "#6b7280";

  return (
    <div style={{ borderTop: "1px solid #1e293b", display: "flex", flexDirection: "column", flexShrink: 0 }}>
      {/* Thanh tóm tắt — luôn thấy; bấm để thu lại cho canvas rộng ra */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10, padding: "7px 14px",
        background: "#0b1220", cursor: "pointer",
      }} onClick={() => setCollapsed(c => !c)}
        title={collapsed ? "Mở bảng lần chạy" : "Thu bảng lần chạy cho canvas rộng ra"}>
        <span style={{ fontSize: 11, color: "#4b5563", width: 10 }}>{collapsed ? "▸" : "▾"}</span>
        <strong style={{ fontSize: 12, color: "#9ca3af" }}>Lần chạy</strong>
        <select className="setting-select" style={{ width: 230, fontSize: 11 }}
          value={runId} onClick={e => e.stopPropagation()}
          onChange={e => onRunChange(Number(e.target.value))}>
          {runs.map(r => (
            <option key={r.id} value={r.id}>
              #{r.id} · {r.status} · {new Date(r.created_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}
            </option>
          ))}
        </select>

        {detail && (
          <>
            <div style={{ width: 130, background: "#1e293b", borderRadius: 4, height: 6, overflow: "hidden" }}>
              <div style={{
                width: `${pct}%`, height: "100%", borderRadius: 4,
                background: detail.status === "done" ? "#4ade80"
                  : detail.status === "running" ? "#fbbf24" : "#475569",
              }} />
            </div>
            <span style={{ fontSize: 11, color: "#6b7280" }}>{detail.done_steps}/{detail.total_steps} bước</span>
            <span style={{ fontSize: 11, color: statusColor, fontWeight: 600 }}>{statusText}</span>
          </>
        )}
        <div style={{ flex: 1 }} />
        {onOpenConsole && (
          <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }}
            title="Mở màn hình chạy riêng — xem toàn bộ bước, lệnh và nội dung file task"
            onClick={e => { e.stopPropagation(); onOpenConsole(); }}>⤢ Màn hình chạy</button>
        )}
        <button className="btn-muted" style={{ fontSize: 11, padding: "3px 10px" }}
          onClick={e => { e.stopPropagation(); refresh(); }}>🔄 Làm mới</button>
      </div>

      {!collapsed && (
        <div style={{ maxHeight: "42vh", overflowY: "auto", padding: "10px 14px 12px" }}>
          {waiting.length > 0 && (
            autoRun ? (
              <div style={{ fontSize: 11, color: "#93c5fd", marginBottom: 8 }}>
                🤖 <b>Tự chạy bằng Claude headless đang BẬT</b> — bước này đã xếp hàng cho
                <code> worker.py</code> trên máy bạn. Mở <b>⤢ Màn hình chạy</b> để xem worker
                đã nhận chưa. Vẫn có thể tự chạy tay bằng lệnh dưới đây.
              </div>
            ) : (
              <div style={{ fontSize: 11, color: "#a16207", marginBottom: 8 }}>
                👉 Hệ thống <b>không tự gọi Claude</b> — nó chỉ soạn sẵn file task rồi dừng.
                Bạn chạy lệnh trong terminal của mình, xong thì bấm ✓ để mở bước kế tiếp.
              </div>
            )
          )}
          {detail && waiting.map(s => (
            <ActionCard key={s.node_id} step={s} runId={detail.run_id} onChanged={refresh} />
          ))}

          {detail && waiting.length === 0 && detail.status !== "done" && (
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
              Không có bước nào chờ bạn — các bước còn lại đang đợi bước trước hoàn tất.
            </div>
          )}

          <div style={{ fontSize: 11, color: "#4b5563", margin: "4px 0 6px" }}>Toàn bộ các bước</div>
          {detail?.steps.map(s => <StepRow key={s.node_id} step={s} />)}
        </div>
      )}
    </div>
  );
}
