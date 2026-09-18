import React, { useEffect, useMemo, useState } from "react";
import { useActiveTasks } from "../hooks/useWorkflows";
import { ActiveTask } from "../types";
import { TYPE_ICON, useCopy, useMarkDone } from "./RunSteps";

/**
 * Hộp "việc chờ bạn" — gom mọi bước đang chờ người chạy, từ mọi workflow.
 *
 * Bản cũ mỗi việc là một thẻ to kèm nguyên dòng lệnh: 7 việc đã chiếm cả màn
 * hình, vài trăm việc thì không lần ra cái nào của project nào. Bản này là danh
 * sách dòng mỏng gom theo project, có ô lọc, nhóm gập/mở được, khung cuộn riêng
 * và mỗi nhóm chỉ vẽ PAGE dòng đầu — nghìn việc vẫn không làm trang nặng.
 *
 * Lệnh và nội dung file chỉ bung ra khi bấm ▸ ở đầu dòng. Bấm vào dòng thì màn
 * hình bên dưới mở đúng lần chạy đó — ở đó lệnh hiện cỡ thật, có log worker.
 */

const OPEN_KEY = "rc.inbox.open";
const PAGE = 30;            // số dòng vẽ mỗi nhóm trước khi phải bấm "hiện thêm"
const AUTO_OPEN_MAX = 40;   // tổng việc ≤ số này thì mở sẵn mọi nhóm; nhiều hơn chỉ mở nhóm đang xem
const NO_PROJECT = "(chưa gắn project)";

/** "5 phút", "3 giờ", "2 ngày" — API trả UTC không kèm "Z" (xem useElapsed). */
function fmtAgo(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return "vừa xong";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} phút`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} giờ`;
  return `${Math.floor(h / 24)} ngày`;
}

/** Mọi từ trong ô lọc đều phải xuất hiện đâu đó: tên bước, workflow, project, task, #run. */
function matches(t: ActiveTask, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const hay = [
    t.node_label, t.workflow_name, t.client_folder ?? "", t.task_name ?? "",
    `#${t.run_id}`, `run${t.run_id}`, t.task_id != null ? `#${t.task_id}` : "",
  ].join(" ").toLowerCase();
  return words.every(w => hay.includes(w));
}

function InboxRow({ task, active, onChanged, onOpenRun }: {
  task: ActiveTask;
  /** Dòng này thuộc lần chạy đang mở ở bảng dưới */
  active: boolean;
  onChanged: () => void;
  onOpenRun?: (workflowId: number, runId: number) => void;
}) {
  const [open, setOpen]         = useState(false);
  const [fileOpen, setFileOpen] = useState(false);
  const [content, setContent]   = useState<string | null>(null);
  const { copied, copy }        = useCopy(task.command);
  const { busy, markDone }      = useMarkDone(task.run_id, task.node_id, onChanged);
  const isCondition = task.node_type === "logic.condition";

  const toggleFile = async () => {
    const next = !fileOpen;
    setFileOpen(next);
    if (next && content === null) {
      const res = await fetch(`/api/workflows/runs/${task.run_id}/nodes/${task.node_id}/file`);
      setContent(res.ok ? (await res.json()).content : "(không đọc được file)");
    }
  };

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  return (
    <div className={`ibx-row${active ? " active" : ""}`}>
      <div className="ibx-line"
        onClick={onOpenRun ? () => onOpenRun(task.workflow_id, task.run_id) : undefined}
        title={onOpenRun ? "Mở lần chạy này ở bảng bên dưới" : undefined}>
        <button className="ibx-chev" onClick={e => { stop(e); setOpen(o => !o); }}
          title={open ? "Ẩn lệnh" : "Xem lệnh / file task"}>
          {open ? "▾" : "▸"}
        </button>
        <span className="ibx-icon">{TYPE_ICON[task.node_type] || "📄"}</span>
        <span className="ibx-main">
          <span className="ibx-label">{task.node_label}</span>
          <span className="ibx-meta">
            {task.workflow_name} · #{task.run_id}
            {task.task_name && <> · <span title={`Task #${task.task_id} đã kích hoạt bước này`}>🎯 {task.task_name}</span></>}
          </span>
        </span>
        <span className="ibx-age" title={task.created_at ? "Lần chạy tạo lúc " + new Date(task.created_at + "Z").toLocaleString("vi-VN") : ""}>
          {fmtAgo(task.created_at)}
        </span>
        <span className="ibx-actions" onClick={stop}>
          <button className="ibx-btn" onClick={copy} title="Copy lệnh chạy">{copied ? "✓" : "📋"}</button>
          {isCondition ? (
            <>
              <button className="ibx-btn ok" disabled={busy} onClick={() => markDone("true")}>✔ Đúng</button>
              <button className="ibx-btn no" disabled={busy} onClick={() => markDone("false")}>✘ Sai</button>
            </>
          ) : (
            <button className="ibx-btn ok" disabled={busy} onClick={() => markDone()}>
              {busy ? "…" : "✓ Xong"}
            </button>
          )}
        </span>
      </div>

      {open && (
        <div className="ibx-detail" onClick={stop}>
          <code className="ibx-cmd">{task.command}</code>
          <div className="ibx-detail-foot">
            <span className="ibx-path">
              {task.file_path}{!task.file_exists && <span style={{ color: "#f87171" }}> — file chưa có</span>}
            </span>
            <button className="ibx-btn" onClick={toggleFile}>{fileOpen ? "Ẩn file" : "Xem file"}</button>
            <button className="ibx-btn" onClick={copy}>{copied ? "✓ Đã chép" : "📋 Copy lệnh"}</button>
          </div>
          {fileOpen && <pre className="ibx-file">{content ?? "Đang tải..."}</pre>}
        </div>
      )}
    </div>
  );
}

export default function ActiveTasks({ onOpenRun, activeRunId = null }: {
  /** Có thì mỗi dòng bấm được để mở đúng lần chạy đó */
  onOpenRun?: (workflowId: number, runId: number) => void;
  /** Lần chạy đang mở ở bảng dưới — để tô dòng và mở sẵn nhóm project của nó */
  activeRunId?: number | null;
} = {}) {
  const { tasks, loading, refetch } = useActiveTasks();

  const [panelOpen, setPanelOpen] = useState(() => {
    try { return localStorage.getItem(OPEN_KEY) !== "0"; } catch { return true; }
  });
  const togglePanel = () => setPanelOpen(o => {
    try { localStorage.setItem(OPEN_KEY, o ? "0" : "1"); } catch { /* private mode */ }
    return !o;
  });

  const [q, setQ] = useState("");
  // Nhóm nào đã bấm gập/mở tay thì nhớ; chưa bấm thì theo mặc định (defaultOpen).
  const [groupState, setGroupState] = useState<Record<string, boolean>>({});
  const [shown, setShown]           = useState<Record<string, number>>({});
  useEffect(() => { setGroupState({}); }, [q]);   // đổi từ khoá lọc thì bỏ trạng thái gập tay

  const activeKey = useMemo(() => {
    const t = activeRunId !== null ? tasks.find(x => x.run_id === activeRunId) : undefined;
    return t ? (t.client_folder || NO_PROJECT) : null;
  }, [tasks, activeRunId]);

  const groups = useMemo(() => {
    const map = new Map<string, ActiveTask[]>();
    for (const t of tasks) {
      if (!matches(t, q)) continue;
      const key = t.client_folder || NO_PROJECT;
      const arr = map.get(key);
      if (arr) arr.push(t); else map.set(key, [t]);
    }
    // Theo tên cho ổn định — sắp theo "đang xem" thì bấm dòng nào nhóm nhảy chỗ đó.
    return [...map.entries()]
      .sort(([a], [b]) => (a === NO_PROJECT ? 1 : b === NO_PROJECT ? -1 : a.localeCompare(b)))
      .map(([key, items]) => ({ key, items }));
  }, [tasks, q]);

  if (loading) return null;

  const total      = tasks.length;
  const shownTotal = groups.reduce((n, g) => n + g.items.length, 0);
  const projectCount = new Set(tasks.map(t => t.client_folder || NO_PROJECT)).size;
  const defaultOpen = (key: string) => q.trim() !== "" || shownTotal <= AUTO_OPEN_MAX || key === activeKey;
  const setAll = (open: boolean) => setGroupState(Object.fromEntries(groups.map(g => [g.key, open])));

  return (
    <section className="ibx">
      <div className="ibx-head">
        <button className="ibx-chev" onClick={togglePanel} title={panelOpen ? "Thu gọn" : "Mở ra"}>
          {panelOpen ? "▾" : "▸"}
        </button>
        <strong>Việc chờ bạn chạy</strong>
        <span className={`ibx-count${total ? " hot" : ""}`}>{total}</span>
        {total > 0 && <span className="ibx-sub">· {projectCount} project</span>}
        {panelOpen && total > 0 && (
          <>
            <input className="ibx-search" value={q} onChange={e => setQ(e.target.value)}
              placeholder="Lọc: tên bước, workflow, project, #run…" spellCheck={false} />
            {q && <span className="ibx-sub">{shownTotal}/{total}</span>}
            {groups.length > 1 && (
              <>
                <button className="ibx-btn" onClick={() => setAll(true)}>Mở hết</button>
                <button className="ibx-btn" onClick={() => setAll(false)}>Gập hết</button>
              </>
            )}
          </>
        )}
      </div>

      {panelOpen && (
        total === 0 ? (
          <div className="ibx-empty">Không có việc nào đang chờ. Bấm ▶ Bắt đầu trong một workflow để tạo.</div>
        ) : shownTotal === 0 ? (
          <div className="ibx-empty">Không có việc nào khớp "{q}".</div>
        ) : (
          <div className="ibx-body">
            {groups.map(g => {
              const open  = groupState[g.key] ?? defaultOpen(g.key);
              const limit = shown[g.key] ?? PAGE;
              const rest  = g.items.length - limit;
              return (
                <div key={g.key} className="ibx-group">
                  <button className="ibx-group-head"
                    onClick={() => setGroupState(s => ({ ...s, [g.key]: !open }))}>
                    <span className="ibx-chev">{open ? "▾" : "▸"}</span>
                    <span className="ibx-group-name">📁 {g.key}</span>
                    <span className="ibx-count">{g.items.length}</span>
                    {g.key === activeKey && <span className="ibx-sub">· đang xem</span>}
                  </button>
                  {open && g.items.slice(0, limit).map(t => (
                    <InboxRow key={`${t.run_id}-${t.node_id}`} task={t}
                      active={t.run_id === activeRunId}
                      onChanged={refetch} onOpenRun={onOpenRun} />
                  ))}
                  {open && rest > 0 && (
                    <button className="ibx-more"
                      onClick={() => setShown(s => ({ ...s, [g.key]: limit + PAGE }))}>
                      Hiện thêm {Math.min(PAGE, rest)} · còn {rest} việc
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )
      )}
    </section>
  );
}
