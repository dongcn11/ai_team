import { useCallback, useEffect, useState } from "react";
import { Skill, SkillCategory, SkillDetail } from "../types";

/**
 * Kho skill (`skills/` trên đĩa) — xem dashboard/api/skills_store.py.
 *
 * Không cache toàn cục: file có thể bị sửa ngoài dashboard (git pull, editor),
 * nên mỗi trang tự lấy lại danh sách khi mở.
 */

async function jsonOrThrow(res: Response) {
  if (res.ok) return res.json();
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch { /* giữ nguyên HTTP code */ }
  throw new Error(detail);
}

const enc = (id: string) => id.split("/").map(encodeURIComponent).join("/");

export function useSkillCatalog() {
  const [skills, setSkills]         = useState<Skill[]>([]);
  const [categories, setCategories] = useState<SkillCategory[]>([]);
  /** `skills/` có ghi được không — mount :ro thì mọi nút Lưu sẽ hỏng */
  const [writable, setWritable]     = useState(true);
  const [root, setRoot]             = useState("");
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState<string | null>(null);

  const refetch = useCallback(async () => {
    try {
      const [list, meta] = await Promise.all([
        fetch("/api/skills/").then(jsonOrThrow),
        fetch("/api/skills/categories").then(jsonOrThrow),
      ]);
      setSkills(list);
      setCategories(meta.categories || []);
      setWritable(!!meta.writable);
      setRoot(meta.root || "");
      setError(null);
    } catch (e: any) {
      setError(e?.message || "Không tải được danh sách skill");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refetch(); }, [refetch]);

  return { skills, categories, writable, root, loading, error, refetch };
}

export async function fetchSkill(id: string): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}`).then(jsonOrThrow);
}

export async function createSkill(payload: {
  category: string; name: string; description?: string; body?: string;
  slug?: string; tags?: string[]; format?: "folder" | "file";
}): Promise<SkillDetail> {
  return fetch("/api/skills/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(jsonOrThrow);
}

export async function saveSkill(id: string, payload: {
  name?: string; description?: string; body?: string; tags?: string[];
  category?: string; slug?: string;
}): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(jsonOrThrow);
}

export async function deleteSkill(id: string): Promise<void> {
  await fetch(`/api/skills/${enc(id)}`, { method: "DELETE" }).then(jsonOrThrow);
}

export async function duplicateSkill(id: string): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}/duplicate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  }).then(jsonOrThrow);
}

export async function fetchResource(id: string, filename: string): Promise<string> {
  const data = await fetch(`/api/skills/${enc(id)}/files/${enc(filename)}`).then(jsonOrThrow);
  return data.content ?? "";
}

export async function saveResource(id: string, filename: string, content: string): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}/files/${enc(filename)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  }).then(jsonOrThrow);
}

export async function deleteResource(id: string, filename: string): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}/files/${enc(filename)}`, { method: "DELETE" }).then(jsonOrThrow);
}

/** Link tải file phụ — đường duy nhất xem được file nhị phân */
export function resourceUrl(id: string, filename: string): string {
  return `/api/skills/${enc(id)}/raw/${enc(filename)}`;
}

/** Skill 1 file .md → skill thư mục, để chứa được script */
export async function toFolderSkill(id: string): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}/to-folder`, { method: "POST" }).then(jsonOrThrow);
}

/**
 * Đường dẫn tương đối phải gửi riêng: multipart chỉ giữ TÊN file, nên kéo cả
 * thư mục vào mà không có `paths` là mất sạch cấu trúc thư mục con của skill.
 */
function formOf(files: File[], extra: Record<string, string> = {}): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(extra)) fd.append(k, v);
  fd.append("paths", JSON.stringify(files.map(f => (f as any).webkitRelativePath || f.name)));
  for (const f of files) fd.append("files", f);
  return fd;
}

/** Thêm file phụ (script, mẫu…) vào 1 skill thư mục */
export async function uploadResources(id: string, files: File[]): Promise<SkillDetail> {
  return fetch(`/api/skills/${enc(id)}/files`, { method: "POST", body: formOf(files) }).then(jsonOrThrow);
}

/** Mang nguyên 1 thư mục skill có sẵn (hoặc file .zip) vào kho */
export async function importSkill(
  category: string, files: File[], slug?: string,
): Promise<SkillDetail> {
  const extra: Record<string, string> = { category };
  if (slug) extra.slug = slug;
  return fetch("/api/skills/import", { method: "POST", body: formOf(files, extra) }).then(jsonOrThrow);
}
