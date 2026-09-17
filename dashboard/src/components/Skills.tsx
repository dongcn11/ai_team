import React, { useEffect, useMemo, useRef, useState } from "react";
import { Skill, SkillDetail, SkillResource } from "../types";
import {
  useSkillCatalog, fetchSkill, createSkill, saveSkill, deleteSkill, duplicateSkill,
  fetchResource, saveResource, deleteResource, uploadResources, importSkill,
  toFolderSkill, resourceUrl,
} from "../hooks/useSkills";

/**
 * Quản lý kho skill — cùng quy ước với skill của Claude Code và BMAD:
 * mỗi skill là một THƯ MỤC có `SKILL.md` mở đầu bằng frontmatter `name` +
 * `description`, bên cạnh là mọi thứ skill cần: script, test, mẫu, thư mục con.
 * Skill thật không phải một file chữ — udom-screen-spec có SKILL.md 24KB và 5
 * script Python mà chính nó bảo agent chạy; kho này phải chứa được đúng thứ đó.
 *
 * Skill nằm trong `skills/<cụm>/`; cụm chính là thư mục vai trò mà pipeline
 * `ai_team/` đang đọc (be/fe/pm/leader…). Nhờ vậy skill sửa ở đây áp cho CẢ HAI
 * làn: pipeline nhét vào prompt agent, node workflow nhúng vào file task.
 *
 * Nguồn sự thật là FILE, không phải DB (xem api/skills_store.py) — sửa bằng
 * editor hay bằng trang này đều được, và `git diff` vẫn đọc ra.
 */

const MONO = "ui-monospace, SFMono-Regular, Menlo, monospace";

const KIND_ICON: Record<SkillResource["kind"], string> = {
  script: "⚙️", doc: "📄", data: "🧾", binary: "📦",
};

function humanSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Chấm màu theo cụm — nhìn danh sách dài vẫn nhận ra nhóm */
function catColor(name: string): string {
  const palette = ["#60a5fa", "#4ade80", "#fbbf24", "#f472b6", "#a78bfa", "#22d3ee", "#fb923c"];
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 997;
  return palette[h % palette.length];
}

function Badge({ text, color, title }: { text: string; color: string; title?: string }) {
  return (
    <span title={title} style={{
      fontSize: 10, padding: "2px 7px", borderRadius: 10, whiteSpace: "nowrap",
      color, border: `1px solid ${color}55`, background: `${color}18`,
    }}>{text}</span>
  );
}

type Draft = {
  id: string | null;          // null = skill mới chưa lưu
  category: string;
  slug: string;
  name: string;
  description: string;
  tags: string;
  body: string;
};

const EMPTY_BODY = `## Khi nào dùng

(mô tả tình huống áp dụng)

## Quy ước

- …
`;

function draftOf(s: SkillDetail): Draft {
  return {
    id: s.id, category: s.category, slug: s.slug, name: s.name,
    description: s.description, tags: (s.tags || []).join(", "), body: s.body,
  };
}

export default function SkillsPage() {
  const { skills, categories, writable, root, loading, error, refetch } = useSkillCatalog();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail]   = useState<SkillDetail | null>(null);
  const [draft, setDraft]     = useState<Draft | null>(null);
  const [filter, setFilter]   = useState("");
  const [catFilter, setCatFilter] = useState<string>("");
  const [busy, setBusy]       = useState(false);
  const [msg, setMsg]         = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  /** File phụ đang mở. null = đang sửa chính SKILL.md */
  const [resFile, setResFile] = useState<string | null>(null);
  const [resBody, setResBody] = useState("");

  const folderInput = useRef<HTMLInputElement>(null);   // nhập cả thư mục skill
  const zipInput    = useRef<HTMLInputElement>(null);   // nhập file .zip
  const addInput    = useRef<HTMLInputElement>(null);   // thêm file vào skill đang mở

  // Mở skill → lấy nội dung đầy đủ (danh sách không kèm body cho nhẹ)
  useEffect(() => {
    // Giữ lại bản nháp "skill mới" (id === null): startNew() vừa bỏ chọn skill
    // cũ vừa dựng nháp, effect chạy sau đó mà dọn sạch là form mới biến mất.
    if (!selectedId) { setDetail(null); setDraft(d => (d && d.id === null ? d : null)); return; }
    let cancelled = false;
    fetchSkill(selectedId)
      .then(d => { if (!cancelled) { setDetail(d); setDraft(draftOf(d)); setResFile(null); } })
      .catch(e => { if (!cancelled) setMsg({ kind: "err", text: e.message }); });
    return () => { cancelled = true; };
  }, [selectedId]);

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return skills.filter(s =>
      (!catFilter || s.category === catFilter) &&
      (!needle || `${s.id} ${s.name} ${s.description} ${s.tags.join(" ")}`.toLowerCase().includes(needle))
    );
  }, [skills, filter, catFilter]);

  const grouped = useMemo(() => {
    const map = new Map<string, Skill[]>();
    for (const s of shown) map.set(s.category, [...(map.get(s.category) || []), s]);
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [shown]);

  const startNew = () => {
    setSelectedId(null);
    setDetail(null);
    setResFile(null);
    setDraft({
      id: null,
      category: catFilter || categories[0]?.name || "shared",
      slug: "", name: "", description: "", tags: "", body: EMPTY_BODY,
    });
    setMsg(null);
  };

  const tagList = (raw: string) => raw.split(",").map(t => t.trim()).filter(Boolean);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); }
    catch (e: any) { setMsg({ kind: "err", text: e.message }); }
    finally { setBusy(false); }
  };

  const onSave = () => run(async () => {
    if (!draft) return;
    setMsg(null);
    if (draft.id === null) {
      const created = await createSkill({
        category: draft.category.trim(),
        name: draft.name.trim() || draft.slug.trim(),
        slug: draft.slug.trim() || undefined,
        description: draft.description,
        tags: tagList(draft.tags),
        body: draft.body,
      });
      await refetch();
      setSelectedId(created.id);
      setMsg({ kind: "ok", text: `Đã tạo ${created.path}` });
    } else {
      const saved = await saveSkill(draft.id, {
        name: draft.name, description: draft.description, body: draft.body,
        tags: tagList(draft.tags),
        category: draft.category.trim() || undefined,
        slug: draft.slug.trim() || undefined,
      });
      await refetch();
      setDetail(saved); setDraft(draftOf(saved));
      if (saved.id !== draft.id) setSelectedId(saved.id);
      setMsg({ kind: "ok", text: `Đã lưu ${saved.path}` });
    }
  });

  const onDelete = () => run(async () => {
    if (!detail) return;
    if (!confirm(`Xoá skill "${detail.name}" (${detail.path})?\n\nCả thư mục skill (kể cả script) sẽ mất. Node workflow đang chọn skill này sẽ báo "không tìm thấy" khi chạy.`)) return;
    await deleteSkill(detail.id);
    await refetch();
    setSelectedId(null);
    setMsg({ kind: "ok", text: "Đã xoá skill" });
  });

  const onDuplicate = () => run(async () => {
    if (!detail) return;
    const copy = await duplicateSkill(detail.id);
    await refetch();
    setSelectedId(copy.id);
    setMsg({ kind: "ok", text: `Đã nhân bản thành ${copy.id} (kèm toàn bộ file)` });
  });

  const onToFolder = () => run(async () => {
    if (!detail) return;
    const updated = await toFolderSkill(detail.id);
    await refetch();
    setDetail(updated); setDraft(draftOf(updated));
    setMsg({ kind: "ok", text: `Đã chuyển thành ${updated.path} — giờ thêm được script` });
  });

  const openResource = (r: SkillResource) => run(async () => {
    if (!detail) return;
    if (!r.is_text) { window.open(resourceUrl(detail.id, r.path), "_blank"); return; }
    setResBody(await fetchResource(detail.id, r.path));
    setResFile(r.path);
    setMsg(null);
  });

  const onSaveResource = () => run(async () => {
    if (!detail || !resFile) return;
    setDetail(await saveResource(detail.id, resFile, resBody));
    setMsg({ kind: "ok", text: `Đã lưu ${resFile}` });
  });

  const onNewResource = () => run(async () => {
    if (!detail) return;
    const name = prompt("Tên file mới (vd workflow.md, scripts/check.py, templates/story.md):", "workflow.md");
    if (!name) return;
    const seed = name.endsWith(".py") ? `#!/usr/bin/env python3\n"""${name}"""\n` : `# ${name}\n\n`;
    setDetail(await saveResource(detail.id, name, seed));
    setResFile(name); setResBody(seed);
    setMsg({ kind: "ok", text: `Đã tạo ${name}` });
  });

  const onDeleteResource = (name: string) => run(async () => {
    if (!detail || !confirm(`Xoá file "${name}" trong skill này?`)) return;
    setDetail(await deleteResource(detail.id, name));
    if (resFile === name) setResFile(null);
  });

  const onAddFiles = (files: FileList | null) => run(async () => {
    if (!detail || !files || files.length === 0) return;
    setDetail(await uploadResources(detail.id, Array.from(files)));
    await refetch();
    setMsg({ kind: "ok", text: `Đã thêm ${files.length} file` });
  });

  /** Nhập nguyên thư mục skill có sẵn (.claude/skills/<tên>) hoặc file .zip */
  const onImport = (files: FileList | null) => run(async () => {
    if (!files || files.length === 0) return;
    const category = prompt(
      "Nhập vào cụm nào? (thư mục vai trò: shared, be, fe, pm, leader… — gõ tên mới cũng được)",
      catFilter || "shared",
    );
    if (!category) return;
    const created = await importSkill(category.trim(), Array.from(files));
    await refetch();
    setSelectedId(created.id);
    setMsg({
      kind: "ok",
      text: `Đã nhập ${created.id} — ${created.resources.length} file kèm theo`,
    });
  });

  if (loading) return <div className="state">Đang đọc thư mục skills/…</div>;

  const dirty = !!draft && !!detail && (
    draft.name !== detail.name || draft.description !== detail.description ||
    draft.body !== detail.body || draft.category !== detail.category ||
    draft.slug !== detail.slug || draft.tags !== (detail.tags || []).join(", ")
  );
  const scripts = (detail?.resources || []).filter(r => r.kind === "script");

  return (
    <div className="projects-page">
      {/* input ẩn — nút bấm ở dưới kích hoạt, để không lộ ô file xấu trên trang */}
      <input ref={folderInput} type="file" multiple style={{ display: "none" }}
        // @ts-expect-error webkitdirectory chưa có trong typing của React
        webkitdirectory="" directory=""
        onChange={e => { onImport(e.target.files); e.target.value = ""; }} />
      <input ref={zipInput} type="file" accept=".zip" style={{ display: "none" }}
        onChange={e => { onImport(e.target.files); e.target.value = ""; }} />
      <input ref={addInput} type="file" multiple style={{ display: "none" }}
        onChange={e => { onAddFiles(e.target.files); e.target.value = ""; }} />

      <div className="page-header">
        <h2>Skills</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {skills.length} skill · {categories.length} cụm · <code>{root || "skills/"}</code>
          </span>
          <button className="btn-muted" onClick={() => folderInput.current?.click()} disabled={!writable}
            title="Chọn thư mục skill có sẵn (phải chứa SKILL.md) — script và thư mục con vào theo">
            📂 Nhập thư mục
          </button>
          <button className="btn-muted" onClick={() => zipInput.current?.click()} disabled={!writable}
            title="Nhập skill từ file .zip">📦 Nhập .zip</button>
          <button className="btn-primary" onClick={startNew} disabled={!writable}
            title={writable ? "Tạo skill mới" : "skills/ đang chỉ-đọc"}>+ Skill mới</button>
        </div>
      </div>

      <p style={{ fontSize: 12, color: "#9ca3af", marginTop: 0, marginBottom: 12, lineHeight: 1.6 }}>
        Mỗi skill là một thư mục có <code>SKILL.md</code> (frontmatter <code>name</code> +{" "}
        <code>description</code>) — đúng định dạng skill của Claude Code và BMAD, nên skill viết cho
        Claude bê thẳng vào đây được. Bên cạnh SKILL.md để được <b>script, test, mẫu, thư mục con</b>;
        đường dẫn script hiện luôn trong file task để agent chạy.
      </p>

      {error && <div className="state err">{error}</div>}
      {!writable && (
        <div style={{
          background: "#1c1408", border: "1px solid #78350f", borderRadius: 8,
          padding: "10px 12px", marginBottom: 12, fontSize: 12, color: "#fde68a", lineHeight: 1.7,
        }}>
          <b>Chỉ đọc.</b> API không ghi được vào <code>skills/</code>. Bỏ <code>:ro</code> ở dòng
          {" "}<code>../skills:/skills</code> trong <code>dashboard/docker-compose.yml</code> rồi chạy
          {" "}<code>docker compose up -d api</code>. Xem thì vẫn xem được bình thường.
        </div>
      )}
      {msg && (
        <div className={`settings-msg ${msg.kind}`} style={{ marginBottom: 12 }}>{msg.text}</div>
      )}

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        {/* ── Danh sách skill ───────────────────────────────────────── */}
        <div style={{ width: 300, flexShrink: 0 }}>
          <input className="setting-input" style={{ width: "100%", marginBottom: 8 }}
            placeholder="Tìm skill…" value={filter} onChange={e => setFilter(e.target.value)} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 10 }}>
            <button className="btn-muted" onClick={() => setCatFilter("")}
              style={{ fontSize: 11, padding: "2px 8px", opacity: catFilter ? 0.6 : 1 }}>
              tất cả ({skills.length})
            </button>
            {categories.map(c => (
              <button key={c.name} className="btn-muted" onClick={() => setCatFilter(catFilter === c.name ? "" : c.name)}
                style={{
                  fontSize: 11, padding: "2px 8px",
                  borderColor: catFilter === c.name ? catColor(c.name) : undefined,
                  color: catFilter === c.name ? catColor(c.name) : undefined,
                }}>
                {c.name} ({c.count})
              </button>
            ))}
          </div>

          <div style={{ maxHeight: "62vh", overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
            {grouped.map(([cat, list]) => (
              <div key={cat}>
                <div style={{
                  fontSize: 10, textTransform: "uppercase", letterSpacing: 1,
                  color: catColor(cat), margin: "8px 0 4px",
                }}>{cat}</div>
                {list.map(s => {
                  const nScript = s.resources.filter(r => r.kind === "script").length;
                  return (
                    <div key={s.id} onClick={() => setSelectedId(s.id)}
                      style={{
                        background: selectedId === s.id ? "#1e3a8a" : "#0f172a",
                        border: `1px solid ${selectedId === s.id ? "#2563eb" : "#1e293b"}`,
                        borderRadius: 8, padding: "8px 10px", marginBottom: 4, cursor: "pointer",
                      }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 13, color: "#e2e8f0", fontWeight: 500, flex: 1 }}>{s.name}</span>
                        {nScript > 0 && <Badge text={`⚙️${nScript}`} color="#fbbf24" title={`${nScript} script`} />}
                        {s.format === "folder"
                          ? <Badge text="📁" color="#a78bfa" title="Skill thư mục — chứa được script, file phụ" />
                          : <Badge text="📄" color="#64748b" title="1 file .md (dạng cũ)" />}
                      </div>
                      <div style={{ fontSize: 10, color: "#6b7280", fontFamily: MONO, marginTop: 2 }}>{s.id}</div>
                      {s.description && (
                        <div style={{
                          fontSize: 11, color: "#94a3b8", marginTop: 4, lineHeight: 1.4,
                          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                        }}>{s.description}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
            {shown.length === 0 && (
              <div style={{ fontSize: 12, color: "#4b5563", padding: "16px 0" }}>Không có skill nào khớp.</div>
            )}
          </div>
        </div>

        {/* ── Trình sửa ─────────────────────────────────────────────── */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!draft && (
            <div className="card" style={{ color: "#6b7280", fontSize: 13, lineHeight: 1.7 }}>
              Chọn một skill bên trái để xem/sửa, hoặc bấm <b>+ Skill mới</b>.
              <div style={{ marginTop: 10, fontSize: 12, color: "#4b5563" }}>
                Có sẵn skill ở chỗ khác (<code>.claude/skills/&lt;tên&gt;</code>, skill BMAD, file zip
                đồng nghiệp gửi)? Dùng <b>📂 Nhập thư mục</b> / <b>📦 Nhập .zip</b> — SKILL.md, script
                và thư mục con vào nguyên vẹn.
              </div>
            </div>
          )}

          {draft && (
            <div className="card">
              <div style={{ display: "flex", gap: 10, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
                <h3 style={{ margin: 0, fontSize: 15, flex: 1 }}>
                  {draft.id === null ? "Skill mới" : draft.name || draft.slug}
                </h3>
                {detail && <Badge text={detail.format === "folder" ? "thư mục · SKILL.md" : "1 file .md"} color="#a78bfa" />}
                {detail && !detail.has_frontmatter && (
                  <Badge text="chưa có frontmatter" color="#fbbf24"
                    title="File cũ chưa khai name/description. Lưu lại ở đây là tự thêm." />
                )}
                {detail && <span style={{ fontSize: 11, color: "#6b7280", fontFamily: MONO }}>{detail.path}</span>}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
                <div>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tên skill</label>
                  <input className="setting-input" style={{ width: "100%" }} value={draft.name}
                    placeholder="vd: JWT Authentication"
                    onChange={e => setDraft({ ...draft, name: e.target.value })} />
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <div style={{ flex: 1 }}>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Cụm</label>
                    <input className="setting-input" style={{ width: "100%" }} list="skill-categories"
                      value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })} />
                    <datalist id="skill-categories">
                      {categories.map(c => <option key={c.name} value={c.name} />)}
                    </datalist>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Slug</label>
                    <input className="setting-input" style={{ width: "100%", fontFamily: MONO }}
                      placeholder={draft.id === null ? "tự sinh từ tên" : ""}
                      value={draft.slug} onChange={e => setDraft({ ...draft, slug: e.target.value })} />
                  </div>
                </div>
              </div>

              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
                Mô tả — <span style={{ color: "#6b7280" }}>khi nào dùng skill này</span>
              </label>
              <textarea className="setting-input" style={{ width: "100%", minHeight: 54, resize: "vertical", marginBottom: 4 }}
                placeholder="Dùng khi cần dựng API đăng nhập có JWT…"
                value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} />
              <p style={{ fontSize: 11, color: "#4b5563", marginTop: 0, marginBottom: 12 }}>
                Vào thẳng <code>description:</code> của frontmatter, và hiện lên khi chọn skill cho node
                workflow — viết cho người khác biết <b>khi nào</b> chọn nó.
              </p>

              <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>Tags (cách nhau dấu phẩy)</label>
              <input className="setting-input" style={{ width: "100%", marginBottom: 12 }}
                placeholder="auth, security" value={draft.tags}
                onChange={e => setDraft({ ...draft, tags: e.target.value })} />

              {/* ── File trong skill ──────────────────────────────── */}
              {detail && (
                <div style={{
                  border: "1px solid #1e293b", borderRadius: 8, padding: 10, marginBottom: 12,
                  background: "#0b1220",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 12, color: "#cbd5e1", fontWeight: 600, flex: 1 }}>
                      File trong skill
                      {detail.format === "folder" && (
                        <span style={{ color: "#6b7280", fontWeight: 400 }}>
                          {" "}· {detail.resources.length + 1} file
                          {scripts.length > 0 && ` · ${scripts.length} script`}
                        </span>
                      )}
                    </span>
                    {detail.format === "folder" ? (
                      <>
                        <button className="btn-muted" style={{ fontSize: 11, padding: "2px 8px" }}
                          onClick={() => addInput.current?.click()} disabled={!writable || busy}
                          title="Tải script / mẫu / dữ liệu vào skill này">⬆ Tải file lên</button>
                        <button className="btn-muted" style={{ fontSize: 11, padding: "2px 8px" }}
                          onClick={onNewResource} disabled={!writable || busy}>+ File mới</button>
                      </>
                    ) : (
                      <button className="btn-muted" style={{ fontSize: 11, padding: "2px 8px" }}
                        onClick={onToFolder} disabled={!writable || busy}
                        title="Skill 1 file không chứa được script — chuyển thành thư mục <slug>/SKILL.md">
                        ⇄ Chuyển sang thư mục
                      </button>
                    )}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 200, overflowY: "auto" }}>
                    <button onClick={() => setResFile(null)}
                      style={{
                        textAlign: "left", fontSize: 12, fontFamily: MONO, padding: "4px 6px",
                        borderRadius: 4, cursor: "pointer",
                        background: resFile === null ? "#1e3a8a" : "transparent",
                        border: "none", color: resFile === null ? "#bfdbfe" : "#94a3b8",
                      }}>
                      📘 SKILL.md <span style={{ color: "#4b5563" }}>· nội dung chính</span>
                    </button>
                    {detail.resources.map(r => (
                      <div key={r.path} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <button onClick={() => openResource(r)}
                          title={r.is_text ? "Mở để sửa" : "File nhị phân — bấm để tải về"}
                          style={{
                            flex: 1, textAlign: "left", fontSize: 12, fontFamily: MONO, padding: "4px 6px",
                            borderRadius: 4, cursor: "pointer",
                            background: resFile === r.path ? "#1e3a8a" : "transparent",
                            border: "none", color: resFile === r.path ? "#bfdbfe" : "#94a3b8",
                          }}>
                          {KIND_ICON[r.kind]} {r.path}
                          <span style={{ color: "#4b5563" }}> · {humanSize(r.size)}</span>
                        </button>
                        <a href={resourceUrl(detail.id, r.path)} target="_blank" rel="noreferrer"
                          className="btn-muted" style={{ fontSize: 10, padding: "2px 6px", textDecoration: "none" }}
                          title="Tải về">⬇</a>
                        <button className="btn-muted" onClick={() => onDeleteResource(r.path)}
                          disabled={!writable || busy} title="Xoá file"
                          style={{ fontSize: 10, padding: "2px 6px", color: "#f87171" }}>✕</button>
                      </div>
                    ))}
                  </div>

                  {detail.format === "folder" && scripts.length > 0 && (
                    <p style={{ fontSize: 11, color: "#4b5563", margin: "8px 0 0", lineHeight: 1.6 }}>
                      Script được liệt kê trong file task kèm đường dẫn <code>skills/{detail.category}/{detail.slug}/…</code>{" "}
                      (agent chạy với cwd = gốc repo), nên trong SKILL.md cứ nhắc tên file là agent gọi được.
                    </p>
                  )}
                </div>
              )}

              {resFile === null ? (
                <>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
                    Nội dung SKILL.md (markdown, không cần gõ lại frontmatter)
                  </label>
                  <textarea className="setting-input" spellCheck={false}
                    style={{ width: "100%", minHeight: 320, resize: "vertical", fontFamily: MONO, fontSize: 12 }}
                    value={draft.body} onChange={e => setDraft({ ...draft, body: e.target.value })} />
                </>
              ) : (
                <>
                  <label className="setting-label" style={{ display: "block", marginBottom: 4 }}>
                    {resFile} — file trong skill
                  </label>
                  <textarea className="setting-input" spellCheck={false}
                    style={{ width: "100%", minHeight: 320, resize: "vertical", fontFamily: MONO, fontSize: 12 }}
                    value={resBody} onChange={e => setResBody(e.target.value)} />
                </>
              )}

              <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
                {resFile === null ? (
                  <button className="btn-primary" onClick={onSave} disabled={busy || !writable}>
                    {draft.id === null ? "Tạo skill" : busy ? "Đang lưu…" : dirty ? "Lưu thay đổi" : "Lưu"}
                  </button>
                ) : (
                  <button className="btn-primary" onClick={onSaveResource} disabled={busy || !writable}>
                    Lưu {resFile}
                  </button>
                )}
                {detail && (
                  <>
                    <button className="btn-muted" onClick={onDuplicate} disabled={busy || !writable}>Nhân bản</button>
                    <button className="btn-danger" onClick={onDelete} disabled={busy || !writable}>Xoá</button>
                  </>
                )}
                {draft.id === null && (
                  <button className="btn-muted" onClick={() => setDraft(null)}>Huỷ</button>
                )}
                {dirty && resFile === null && (
                  <span style={{ fontSize: 11, color: "#fbbf24" }}>• chưa lưu</span>
                )}
              </div>

              {detail && (draft.category !== detail.category || draft.slug !== detail.slug) && (
                <p style={{ fontSize: 11, color: "#fbbf24", marginTop: 10, marginBottom: 0, lineHeight: 1.6 }}>
                  ⚠ Đổi cụm/slug là <b>di chuyển cả thư mục skill</b> — id thành{" "}
                  <code>{draft.category}/{draft.slug}</code>. Node workflow đang chọn <code>{detail.id}</code>{" "}
                  sẽ báo "không tìm thấy skill" khi chạy; vào Workflows chọn lại skill cho những node đó.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
