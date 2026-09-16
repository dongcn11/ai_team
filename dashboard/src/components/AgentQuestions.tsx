import { useCallback, useEffect, useState } from "react";

/**
 * Việc agent đang chờ dev chốt.
 *
 * Agent gặp chỗ cần người quyết thì ghi mục "## Cần xác nhận" vào file task và
 * đặt `status: blocked`; API dựng thành câu hỏi ở đây thay vì để agent đoán bừa
 * rồi làm sai cả bước. Trả lời xong, câu trả lời được ghi ngược vào chính file
 * task và bước đó chạy tiếp.
 *
 * Dùng ở 2 chỗ: banner chung trên đầu các tab (component mặc định) và thẻ ngay
 * trong màn hình chạy (`QuestionCard`) — cùng một hook, cùng một cách trả lời.
 */
export type AgentQuestion = {
  id: number;
  run_id: number;
  workflow_id: number | null;
  node_id: string;
  node_label: string | null;
  client_folder: string | null;
  task_file: string | null;
  question: string;
  status: string;
  created_at: string;
};

const POLL_MS = 5000;

/** Câu hỏi đang mở; `runId` để lọc theo 1 lần chạy. */
export function useOpenQuestions(runId?: number | null) {
  const [items, setItems] = useState<AgentQuestion[]>([]);

  const load = useCallback(async () => {
    const qs = runId != null ? `&run_id=${runId}` : "";
    try {
      const res = await fetch(`/api/workflows/questions?status=open${qs}`);
      if (res.ok) setItems(await res.json());
    } catch {
      /* mất mạng tạm thời — vòng poll sau tự lấy lại */
    }
  }, [runId]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  return { questions: items, reload: load };
}

/** 1 câu hỏi + ô trả lời. `onAnswered` để màn ngoài refresh lại trạng thái bước. */
export function QuestionCard({ q, onAnswered }: { q: AgentQuestion; onAnswered?: () => void }) {
  const [draft,  setDraft]  = useState("");
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState("");

  const post = async (path: string, body?: object) => {
    setSaving(true);
    setError("");
    const res = await fetch(`/api/workflows/questions/${q.id}/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.ok) {
      setDraft("");
      onAnswered?.();
    } else {
      const d = await res.json().catch(() => ({}));
      setError(d.detail || "Không gửi được");
    }
    setSaving(false);
  };

  const send = () => { if (draft.trim()) post("answer", { answer: draft.trim() }); };

  // Bỏ qua = bước này không chạy nữa (đánh dấu skipped). Không chạy lại gì cả.
  const dismiss = () => {
    if (window.confirm("Huỷ câu hỏi này? Bước sẽ bị bỏ qua, agent không chạy tiếp bước này nữa.")) {
      post("dismiss");
    }
  };

  return (
    <div className="aq-item">
      <div className="aq-meta">
        {q.client_folder && <code>{q.client_folder}</code>}
        <span>· bước <strong>{q.node_label || q.node_id}</strong></span>
        <span>· run #{q.run_id}</span>
        {q.task_file && <span>· <code>{q.task_file}</code></span>}
      </div>
      <div className="aq-question">{q.question}</div>
      {error && <div className="aq-error" style={{ marginTop: 6 }}>{error}</div>}
      <div className="aq-answer">
        <textarea
          className="aq-input"
          rows={3}
          placeholder="Trả lời cho agent — chốt phạm vi, chọn phương án, cấp thông tin còn thiếu… (Ctrl+Enter để gửi)"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }} />
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <button className="btn-primary" disabled={saving || !draft.trim()} onClick={send}
            title="Ghi câu trả lời vào file task rồi cho bước này chạy tiếp">
            {saving ? "Đang gửi..." : "Gửi & chạy tiếp"}
          </button>
          <button className="btn-muted" disabled={saving} onClick={dismiss}
            style={{ fontSize: 12 }}
            title="Bỏ qua câu hỏi — bước này bị đánh dấu bỏ qua, không chạy nữa">
            Huỷ
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AgentQuestions() {
  const { questions, reload } = useOpenQuestions();

  if (questions.length === 0) return null;

  return (
    <div className="aq-panel">
      <div className="aq-head">
        <span className="aq-badge">{questions.length}</span>
        Agent đang chờ bạn xác nhận
      </div>
      {questions.map(q => <QuestionCard key={q.id} q={q} onAnswered={reload} />)}
    </div>
  );
}
