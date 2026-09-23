import { useEffect, useState } from "react";
import {
  Schedule, ScheduleDraft, emptyDraft, previewCron, useSchedules,
} from "../hooks/useSchedules";

/**
 * Tab "Lịch chạy" của một dự án.
 *
 * Đồng hồ nằm ở API (xem dashboard/api/scheduler.py) — giao diện này chỉ khai
 * lịch. Ô cron luôn kèm 5 mốc chạy kế tiếp: lịch sai cú pháp mà lưu được thì tới
 * 6h sáng mới phát hiện, lúc đó không ai ngồi xem.
 */

const CRON_PRESETS: { label: string; cron: string }[] = [
  { label: "6h sáng hằng ngày", cron: "0 6 * * *" },
  { label: "Mỗi giờ", cron: "0 * * * *" },
  { label: "8h sáng thứ Hai", cron: "0 8 * * 1" },
  { label: "6h sáng mùng 1", cron: "0 6 1 * *" },
];

const STATUS_LABEL: Record<string, string> = {
  fired: "✅ đã chạy",
  no_change: "💤 không đổi",
  skipped: "⏭️ bỏ qua",
  missed: "⚠️ lỡ nhịp",
  error: "🔴 lỗi",
  dry_run: "🧪 chạy thử",
};

function fmtLocal(iso: string | null): string {
  if (!iso) return "—";
  // Backend trả UTC; chuỗi không có hậu tố Z thì trình duyệt hiểu nhầm là giờ máy.
  const d = new Date(/[Zz+]|\d{2}:\d{2}$/.test(iso.slice(10)) ? iso : `${iso}Z`);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function ProjectSchedules({ slug }: { slug: string }) {
  const { items, saving, error, setError, create, update, remove, runNow } =
    useSchedules(slug);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<ScheduleDraft>(emptyDraft);
  const [runs, setRuns] = useState<string[]>([]);
  const [cronError, setCronError] = useState<string | null>(null);

  // Gõ cron tới đâu, xem trước tới đó.
  useEffect(() => {
    if (editing === null) return;
    let alive = true;
    previewCron(draft.cron_expression, draft.timezone).then(r => {
      if (!alive) return;
      setRuns(r.runs);
      setCronError(r.error);
    });
    return () => { alive = false; };
  }, [editing, draft.cron_expression, draft.timezone]);

  const startNew = () => { setDraft(emptyDraft); setEditing("new"); setError(null); };

  const startEdit = (s: Schedule) => {
    setDraft({
      name: s.name, cron_expression: s.cron_expression, timezone: s.timezone,
      enabled: s.enabled, job_kind: s.job_kind, misfire_policy: s.misfire_policy,
      concurrency_policy: s.concurrency_policy, on_change: s.on_change, jitter_s: s.jitter_s,
    });
    setEditing(s.id);
    setError(null);
  };

  const submit = async () => {
    const ok = editing === "new" ? await create(draft) : await update(editing as number, draft);
    if (ok) setEditing(null);
  };

  const patch = (next: Partial<ScheduleDraft>) => setDraft({ ...draft, ...next });

  return (
    <div className="sched-tab">
      <p className="sched-hint">
        Lịch quét tài liệu trong <code>clients/{slug}/</code> của dự án này. Chỉ khi tài liệu
        <strong> thực sự đổi </strong> mới báo hoặc tạo lần chạy — không đổi thì không đánh
        thức pipeline.
      </p>

      {error && <div className="sched-hint warn">{error}</div>}

      <div className="sched-list">
        {items.length === 0 && editing === null && (
          <div className="sched-empty">Chưa có lịch nào. Thêm một lịch để bắt đầu.</div>
        )}

        {items.map(s => (
          <div key={s.id} className={`sched-row${s.enabled ? "" : " off"}`}>
            <div className="sched-row-main">
              <span className="sched-name">{s.name}</span>
              <code className="sched-cron">{s.cron_expression}</code>
              <span className="sched-tz">{s.timezone}</span>
            </div>
            <div className="sched-row-meta">
              <span>Kế tiếp: {fmtLocal(s.next_run_at)}</span>
              <span>
                Gần nhất: {fmtLocal(s.last_run_at)}
                {s.last_status && ` — ${STATUS_LABEL[s.last_status] || s.last_status}`}
              </span>
              {s.last_detail && <span className="sched-detail">{s.last_detail}</span>}
            </div>
            <div className="sched-row-actions">
              <button onClick={() => startEdit(s)}>Sửa</button>
              <button onClick={() => runNow(s.id)} disabled={!s.enabled}>Chạy ngay</button>
              <button className="danger" onClick={() => remove(s.id)}>Xoá</button>
            </div>
          </div>
        ))}
      </div>

      {editing === null ? (
        <button className="sched-add" onClick={startNew}>+ Thêm lịch</button>
      ) : (
        <div className="sched-form">
          <label>
            Tên
            <input value={draft.name} onChange={e => patch({ name: e.target.value })} />
          </label>

          <label>
            Biểu thức cron (5 trường)
            <input
              value={draft.cron_expression}
              onChange={e => patch({ cron_expression: e.target.value })}
              placeholder="0 6 * * *"
            />
          </label>

          <div className="sched-presets">
            {CRON_PRESETS.map(p => (
              <button key={p.cron} type="button" onClick={() => patch({ cron_expression: p.cron })}>
                {p.label}
              </button>
            ))}
          </div>

          <label>
            Múi giờ
            <input value={draft.timezone} onChange={e => patch({ timezone: e.target.value })} />
          </label>

          {/* Người dùng tự kiểm chứng trước khi lưu — đây là điểm quan trọng nhất của form. */}
          <div className={`sched-preview${cronError ? " warn" : ""}`}>
            {cronError ? cronError : (
              <>
                <strong>5 lần chạy kế tiếp:</strong>
                <ul>{runs.map(r => <li key={r}>{new Date(r).toLocaleString()}</li>)}</ul>
              </>
            )}
          </div>

          <label>
            Máy tắt đúng giờ hẹn thì
            <select
              value={draft.misfire_policy}
              onChange={e => patch({ misfire_policy: e.target.value as ScheduleDraft["misfire_policy"] })}
            >
              <option value="catchup_once">Chạy bù 1 lần khi bật lại (trong 24h)</option>
              <option value="skip">Bỏ qua, đợi lần sau</option>
            </select>
          </label>

          <label>
            Khi tài liệu đổi
            <select
              value={draft.on_change}
              onChange={e => patch({ on_change: e.target.value as ScheduleDraft["on_change"] })}
            >
              <option value="notify">Chỉ báo qua chat</option>
              <option value="run_pipeline">Chạy pipeline</option>
              <option value="both">Báo và chạy pipeline</option>
            </select>
          </label>

          <label>
            Nếu dự án còn job đang chạy
            <select
              value={draft.concurrency_policy}
              onChange={e => patch({ concurrency_policy: e.target.value as ScheduleDraft["concurrency_policy"] })}
            >
              <option value="forbid">Bỏ qua nhịp này (khuyên dùng)</option>
              <option value="allow">Vẫn xếp thêm vào hàng đợi</option>
            </select>
          </label>

          <label className="sched-check">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={e => patch({ enabled: e.target.checked })}
            />
            Bật lịch này
          </label>

          <div className="sched-form-actions">
            <button onClick={submit} disabled={saving || !!cronError}>
              {saving ? "Đang lưu…" : "Lưu"}
            </button>
            <button onClick={() => { setEditing(null); setError(null); }}>Huỷ</button>
          </div>
        </div>
      )}
    </div>
  );
}
