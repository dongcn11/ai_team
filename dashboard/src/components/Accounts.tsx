import React, { useCallback, useEffect, useState } from "react";
import { AuthUser, useAuth } from "../auth";
import { TAB_INFO } from "../tabs";
import { useProjects } from "../hooks/useProjects";
import type { ChatModel } from "./AssistantHome";

/* Quản lý tài khoản (chỉ admin): tạo, đặt quyền vào từng màn hình, gán dự án,
   đặt lại mật khẩu, khoá, xoá. Tài khoản mới mặc định chỉ vào được Dashboard và
   chưa có dự án nào (chỉ chat tự do, cột Công việc trống). */

const SCREENS = TAB_INFO.filter(t => t.key !== "accounts");

async function call<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(url, body === undefined ? { method }
    : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data as T;
}

const fmt = (s: string | null) =>
  s ? new Date(/Z|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z").toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" }) : "chưa";

interface Form {
  id: number | null;           // null = tạo mới
  username: string;
  display_name: string;
  password: string;
  is_admin: boolean;
  is_active: boolean;
  permissions: string[];
  projects: string[];
  models: string[] | null;     // null = mọi model, kể cả model thêm sau
}

const EMPTY: Form = { id: null, username: "", display_name: "", password: "", is_admin: false,
                      is_active: true, permissions: ["dashboard"], projects: [], models: null };

export default function AccountsPage() {
  const { user: me, refresh: refreshMe } = useAuth();
  const { projects } = useProjects();            // admin → mọi dự án
  const projName = (slug: string) => projects.find(p => p.id === slug)?.name ?? slug;
  // Admin → /api/assistant/models trả toàn bộ danh mục.
  const [catalog, setCatalog] = useState<ChatModel[]>([]);
  useEffect(() => {
    call<ChatModel[]>("/api/assistant/models").then(setCatalog).catch(() => setCatalog([]));
  }, []);
  const modelName = (k: string) => catalog.find(m => m.key === k)?.label ?? k.replace(/^\w+:/, "");
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setUsers(await call<AuthUser[]>("/api/auth/users"));
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Không tải được" });
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const edit = (u: AuthUser) => setForm({
    id: u.id, username: u.username, display_name: u.display_name === u.username ? "" : u.display_name,
    password: "", is_admin: u.is_admin, is_active: u.is_active, permissions: u.permissions,
    projects: u.projects, models: u.models,
  });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setBusy(true);
    setMsg(null);
    try {
      const body = { display_name: form.display_name, is_admin: form.is_admin, is_active: form.is_active,
                     permissions: form.permissions, projects: form.projects, models: form.models,
                     ...(form.password ? { password: form.password } : {}) };
      if (form.id === null) {
        await call("/api/auth/users", "POST", { ...body, username: form.username, password: form.password });
        setMsg({ ok: true, text: `Đã tạo tài khoản ${form.username}` });
      } else {
        await call(`/api/auth/users/${form.id}`, "PATCH", body);
        setMsg({ ok: true, text: `Đã lưu ${form.username}` });
        if (form.id === me.id) refreshMe();
      }
      setForm(null);
      load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Không lưu được" });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (u: AuthUser) => {
    if (!confirm(`Xoá tài khoản "${u.username}"? Không hoàn tác được.`)) return;
    try {
      await call(`/api/auth/users/${u.id}`, "DELETE");
      setMsg({ ok: true, text: `Đã xoá ${u.username}` });
      load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Không xoá được" });
    }
  };

  const toggleProject = (k: string) => form && setForm({
    ...form, projects: form.projects.includes(k) ? form.projects.filter(p => p !== k) : [...form.projects, k],
  });

  const toggleModel = (k: string) => {
    if (!form) return;
    const cur = form.models ?? [];
    setForm({ ...form, models: cur.includes(k) ? cur.filter(x => x !== k) : [...cur, k] });
  };

  const togglePerm = (k: string) => form && setForm({
    ...form, permissions: form.permissions.includes(k) ? form.permissions.filter(p => p !== k) : [...form.permissions, k],
  });

  return (
    <div className="acc-page">
      <div className="acc-head">
        <div>
          <div className="settings-title">Tài khoản</div>
          <div className="settings-sub">Mỗi tài khoản chỉ thấy các màn hình được tick. Quản trị viên vào được hết và quản lý trang này.</div>
        </div>
        <button className="btn-primary" onClick={() => { setForm({ ...EMPTY }); setMsg(null); }}>＋ Thêm tài khoản</button>
      </div>

      {msg && <div className={`settings-msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}

      <div className="acc-table-wrap">
        <table className="acc-table">
          <thead>
            <tr><th>Tài khoản</th><th>Vai trò</th><th>Màn hình được vào</th><th>Dự án</th><th>Model chat</th><th>Đăng nhập gần nhất</th><th /></tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className={u.is_active ? "" : "off"}>
                <td>
                  <b>{u.display_name}</b>{u.id === me.id && <span className="acc-you">bạn</span>}
                  <div className="acc-muted">@{u.username}</div>
                </td>
                <td>
                  {u.is_admin ? <span className="acc-pill admin">Quản trị</span> : <span className="acc-pill">Thành viên</span>}
                  {!u.is_active && <span className="acc-pill locked">Đã khoá</span>}
                </td>
                <td className="acc-perms">
                  {u.is_admin ? <span className="acc-muted">Tất cả</span>
                    : u.permissions.map(p => <span key={p} className="acc-chip">{SCREENS.find(s => s.key === p)?.label ?? p}</span>)}
                </td>
                <td className="acc-perms">
                  {u.is_admin ? <span className="acc-muted">Tất cả</span>
                    : u.projects.length ? u.projects.map(p => <span key={p} className="acc-chip proj">{projName(p)}</span>)
                    : <span className="acc-muted">Chưa gán</span>}
                </td>
                <td className="acc-perms">
                  {u.is_admin || u.models === null ? <span className="acc-muted">Tất cả</span>
                    : u.models.length ? u.models.map(k => <span key={k} className="acc-chip model">{modelName(k)}</span>)
                    : <span className="acc-muted">Không có</span>}
                </td>
                <td className="acc-muted">{fmt(u.last_login_at)}</td>
                <td className="acc-actions">
                  <button className="btn-muted" onClick={() => edit(u)}>Sửa</button>
                  {u.id !== me.id && <button className="btn-danger" onClick={() => remove(u)}>Xoá</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {form && (
        <div className="auth-modal" onClick={() => setForm(null)}>
          <form className="auth-card acc-form" onClick={e => e.stopPropagation()} onSubmit={save}>
            <h1>{form.id === null ? "Thêm tài khoản" : `Sửa ${form.username}`}</h1>
            {form.id === null && (
              <label>Tên đăng nhập
                <input autoFocus value={form.username} placeholder="vd: nguyen.van.a"
                  onChange={e => setForm({ ...form, username: e.target.value.toLowerCase() })} />
              </label>
            )}
            <label>Tên hiển thị <span className="auth-opt">(tuỳ chọn)</span>
              <input value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} />
            </label>
            <label>{form.id === null ? "Mật khẩu" : <>Đặt lại mật khẩu <span className="auth-opt">(để trống = giữ nguyên)</span></>}
              <input type="password" autoComplete="new-password" value={form.password}
                onChange={e => setForm({ ...form, password: e.target.value })} />
            </label>

            <div className="acc-checks">
              <label className="acc-check">
                <input type="checkbox" checked={form.is_admin} onChange={e => setForm({ ...form, is_admin: e.target.checked })} />
                Quản trị viên <span className="auth-opt">— vào mọi màn hình, quản lý tài khoản</span>
              </label>
              <label className="acc-check">
                <input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                Đang hoạt động <span className="auth-opt">— bỏ tick để khoá, đăng xuất ngay</span>
              </label>
            </div>

            {!form.is_admin && (
              <fieldset className="acc-screens">
                <legend>Màn hình được vào</legend>
                {SCREENS.map(s => (
                  <label key={s.key} className="acc-check">
                    <input type="checkbox" checked={form.permissions.includes(s.key)} onChange={() => togglePerm(s.key)} />
                    {s.label}
                  </label>
                ))}
                {form.permissions.length === 0 && <div className="acc-muted">Không tick màn nào → mặc định Dashboard.</div>}
              </fieldset>
            )}

            {!form.is_admin && (
              <fieldset className="acc-screens">
                <legend>Dự án được làm việc</legend>
                {projects.map(p => (
                  <label key={p.id} className="acc-check" title={p.id}>
                    <input type="checkbox" checked={form.projects.includes(p.id)} onChange={() => toggleProject(p.id)} />
                    {p.name}
                  </label>
                ))}
                {projects.length === 0 && <div className="acc-muted">Chưa có dự án nào.</div>}
                <div className="acc-muted acc-span">Chỉ thấy các dự án này ở ô chọn dự án khi chat, tab Projects, cột Công việc và câu hỏi của agent.</div>
              </fieldset>
            )}

            {!form.is_admin && (
              <fieldset className="acc-screens">
                <legend>Model dùng trong chat</legend>
                <label className="acc-check acc-span">
                  <input type="checkbox" checked={form.models === null}
                    onChange={e => setForm({ ...form, models: e.target.checked ? null : catalog.map(m => m.key) })} />
                  Tất cả model <span className="auth-opt">— kể cả model thêm sau ở tab API</span>
                </label>
                {form.models !== null && catalog.map(m => (
                  <label key={m.key} className="acc-check" title={m.description}>
                    <input type="checkbox" checked={form.models!.includes(m.key)} onChange={() => toggleModel(m.key)} />
                    {m.label} <span className="auth-opt">{m.group === "Claude" ? "" : `· ${m.group}`}</span>
                  </label>
                ))}
                {form.models !== null && form.models.length === 0 && (
                  <div className="acc-muted acc-span">Không tick model nào → tài khoản không chat được.</div>
                )}
              </fieldset>
            )}

            <div className="auth-actions">
              <button type="button" className="btn-muted" onClick={() => setForm(null)}>Huỷ</button>
              <button className="btn-primary" disabled={busy || (form.id === null && (!form.username.trim() || !form.password))}>
                {busy ? "Đang lưu…" : "Lưu"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
