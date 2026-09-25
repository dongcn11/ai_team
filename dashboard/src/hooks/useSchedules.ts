import { useCallback, useEffect, useState } from "react";

/** Lịch chạy định kỳ của một dự án. Xem dashboard/api/models.py::Schedule. */
export interface Schedule {
  id: number;
  project_id: number;
  name: string;
  /** unix-cron 5 trường: phút giờ ngày tháng thứ. */
  cron_expression: string;
  /** Tên tz database, ví dụ "Asia/Ho_Chi_Minh". */
  timezone: string;
  enabled: boolean;
  job_kind: "scan_docs";
  /** Máy tắt đúng giờ hẹn thì làm gì. */
  misfire_policy: "catchup_once" | "skip";
  /** Worker chạy tuần tự — mặc định không chất chồng job. */
  concurrency_policy: "forbid" | "allow";
  on_change: "notify" | "run_workflow" | "both";
  /** Workflow của dự án được chạy khi on_change là run_workflow/both. */
  workflow_id: number | null;
  jitter_s: number;
  /** UTC. Null nghĩa là chưa tính được mốc (cron hỏng). */
  next_run_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  last_detail: string | null;
}

export type ScheduleDraft = Omit<
  Schedule,
  "id" | "project_id" | "next_run_at" | "last_run_at" | "last_status" | "last_detail"
>;

export const emptyDraft: ScheduleDraft = {
  name: "Quét tài liệu hằng ngày",
  cron_expression: "0 6 * * *",
  timezone: "Asia/Ho_Chi_Minh",
  enabled: true,
  job_kind: "scan_docs",
  misfire_policy: "catchup_once",
  concurrency_policy: "forbid",
  // Mặc định chỉ BÁO, không tự chạy workflow. Đổi sang run_workflow là quyết
  // định có chi phí (token + thời gian máy), nên phải do người dùng bấm.
  on_change: "notify",
  workflow_id: null,
  jitter_s: 0,
};

/**
 * `slug` là TÊN THƯ MỤC trong clients/ — cùng thứ ProjectMcp nhận.
 * `/api/projects` là filesystem-backed nên giao diện không có id số của bảng
 * `projects`; API schedules tự quy đổi slug -> project_id.
 */
export function useSchedules(slug: string | null) {
  const [items, setItems] = useState<Schedule[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!slug) return;
    setError(null);
    try {
      const res = await fetch(`/api/schedules?slug=${encodeURIComponent(slug)}`);
      if (res.ok) setItems(await res.json());
    } catch {
      setError("Không gọi được API.");
    }
  }, [slug]);

  useEffect(() => { load(); }, [load]);

  const fail = async (res: Response) => {
    const body = await res.json().catch(() => ({}));
    // 422 từ router mang câu giải thích cron/timezone sai ở đâu — hiện nguyên văn.
    setError(typeof body.detail === "string" ? body.detail : `Thất bại (HTTP ${res.status}).`);
    return false;
  };

  const create = async (draft: ScheduleDraft) => {
    if (!slug) return false;
    setSaving(true); setError(null);
    try {
      const res = await fetch(`/api/schedules?slug=${encodeURIComponent(slug)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) return await fail(res);
      await load();
      return true;
    } catch {
      setError("Không gọi được API."); return false;
    } finally { setSaving(false); }
  };

  const update = async (id: number, draft: ScheduleDraft) => {
    setSaving(true); setError(null);
    try {
      const res = await fetch(`/api/schedules/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) return await fail(res);
      await load();
      return true;
    } catch {
      setError("Không gọi được API."); return false;
    } finally { setSaving(false); }
  };

  const remove = async (id: number) => {
    setError(null);
    try {
      const res = await fetch(`/api/schedules/${id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) return await fail(res);
      await load();
      return true;
    } catch {
      setError("Không gọi được API."); return false;
    }
  };

  /** Đẩy mốc về quá khứ để nhịp tick kế tiếp xử lý — KHÔNG tự chèn job ở client. */
  const runNow = async (id: number) => {
    setError(null);
    try {
      const res = await fetch(`/api/schedules/${id}/run-now`, { method: "POST" });
      if (!res.ok) return await fail(res);
      await load();
      return true;
    } catch {
      setError("Không gọi được API."); return false;
    }
  };

  return { items, saving, error, setError, load, create, update, remove, runNow };
}

/** Xem trước N mốc chạy kế tiếp. Trả [] khi cron/timezone sai. */
export async function previewCron(
  cron: string, tz: string, count = 5,
): Promise<{ runs: string[]; error: string | null }> {
  try {
    const qs = new URLSearchParams({ cron, tz, count: String(count) });
    const res = await fetch(`/api/schedules/preview?${qs}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { runs: [], error: typeof body.detail === "string" ? body.detail : "Cron không hợp lệ." };
    }
    const d = await res.json();
    return { runs: d.next_runs || [], error: null };
  } catch {
    return { runs: [], error: "Không gọi được API." };
  }
}
