import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import "./auth.css";

/* Đăng nhập dashboard. Phiên nằm trong cookie httpOnly do API đặt (xem
   api/auth.py) — trình duyệt tự gửi cho mọi fetch cùng origin, nên các màn hình
   không phải sửa gì. Chỉ cần: hễ API trả 401 (phiên hết hạn / bị khoá) thì quay
   về màn đăng nhập — fetch được bọc 1 lần ở đây để bắt điều đó. */

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  permissions: string[];
  projects: string[];          // slug dự án được gán (admin: bỏ qua, thấy hết)
  models: string[] | null;     // khoá model chat được dùng; null = tất cả
  created_at: string | null;
  last_login_at: string | null;
}

interface AuthCtx {
  user: AuthUser;
  tabs: string[];
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);
export const useAuth = () => useContext(Ctx)!;

const EXPIRED = "auth:expired";

// Bọc fetch đúng 1 lần: 401 từ /api/* (trừ chính các lệnh đăng nhập) → báo hết phiên.
const w = window as unknown as { __authFetch?: boolean };
if (!w.__authFetch) {
  w.__authFetch = true;
  const orig = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const res = await orig(input, init);
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (res.status === 401 && /\/api\//.test(url) && !/\/api\/auth\/(login|status)/.test(url))
      window.dispatchEvent(new Event(EXPIRED));
    return res;
  };
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data as T;
}

interface Status { user: AuthUser | null; tabs: string[] }

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [st, setSt] = useState<Status | null>(null);
  const [netErr, setNetErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSt(await res.json());
      setNetErr(null);
    } catch (e) {
      setNetErr(e instanceof Error ? e.message : "Không kết nối được API");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const onExpired = () => setSt(s => (s?.user ? { ...s, user: null } : s));
    window.addEventListener(EXPIRED, onExpired);
    return () => window.removeEventListener(EXPIRED, onExpired);
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    setSt(s => (s ? { ...s, user: null } : s));
  }, []);

  if (!st) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          {netErr ? <><b>Không kết nối được API</b><p className="auth-sub">{netErr}</p>
                      <button className="btn-primary" onClick={refresh}>Thử lại</button></>
                  : <p className="auth-sub">Đang tải…</p>}
        </div>
      </div>
    );
  }
  if (!st.user) {
    return <LoginForm onDone={user => setSt({ ...st, user })} />;
  }
  return <Ctx.Provider value={{ user: st.user, tabs: st.tabs, logout, refresh }}>{children}</Ctx.Provider>;
}

// Chỉ đăng nhập — không có đăng ký. Tài khoản do admin tạo ở màn Tài khoản.
function LoginForm({ onDone }: { onDone: (u: AuthUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      onDone(await post<AuthUser>("/api/auth/login", { username, password }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Đăng nhập không được");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-logo">🤖</div>
        <h1>AI Team Dashboard</h1>
        <p className="auth-sub">Đăng nhập để tiếp tục. Chưa có tài khoản? Liên hệ quản trị viên.</p>
        <label>Tên đăng nhập
          <input autoFocus autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} />
        </label>
        <label>Mật khẩu
          <input type="password" autoComplete="current-password" value={password}
            onChange={e => setPassword(e.target.value)} />
        </label>
        {err && <div className="settings-msg err">{err}</div>}
        <button className="btn-primary auth-submit" disabled={busy || !username.trim() || !password}>
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}

/* Menu tài khoản ở góc phải header: tên, đổi mật khẩu, đăng xuất. */
export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [open]);

  return (
    <div className="user-menu" onClick={e => e.stopPropagation()}>
      <button className="user-menu-btn" onClick={() => setOpen(o => !o)} title={user.username}>
        <span className="user-avatar">{(user.display_name || user.username).slice(0, 1).toUpperCase()}</span>
        <span className="user-name">{user.display_name || user.username}</span>
        {user.is_admin && <span className="user-role">admin</span>}
      </button>
      {open && (
        <div className="user-pop">
          <div className="user-pop-head">
            <b>{user.display_name || user.username}</b>
            <span>@{user.username}</span>
          </div>
          <button onClick={() => { setOpen(false); setPwOpen(true); }}>🔑 Đổi mật khẩu</button>
          <button onClick={logout}>↩ Đăng xuất</button>
        </div>
      )}
      {pwOpen && <ChangePassword onClose={() => setPwOpen(false)} />}
    </div>
  );
}

function ChangePassword({ onClose }: { onClose: () => void }) {
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw !== pw2) { setMsg({ ok: false, text: "Hai lần nhập mật khẩu mới không khớp" }); return; }
    setBusy(true);
    try {
      await post("/api/auth/password", { current_password: cur, new_password: pw });
      setMsg({ ok: true, text: "Đã đổi mật khẩu. Các máy khác đang đăng nhập đã bị đăng xuất." });
      setCur(""); setPw(""); setPw2("");
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Không đổi được" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-modal" onClick={onClose}>
      <form className="auth-card" onClick={e => e.stopPropagation()} onSubmit={submit}>
        <h1>Đổi mật khẩu</h1>
        <label>Mật khẩu hiện tại
          <input type="password" autoFocus autoComplete="current-password" value={cur} onChange={e => setCur(e.target.value)} />
        </label>
        <label>Mật khẩu mới
          <input type="password" autoComplete="new-password" value={pw} onChange={e => setPw(e.target.value)} />
        </label>
        <label>Nhập lại mật khẩu mới
          <input type="password" autoComplete="new-password" value={pw2} onChange={e => setPw2(e.target.value)} />
        </label>
        {msg && <div className={`settings-msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
        <div className="auth-actions">
          <button type="button" className="btn-muted" onClick={onClose}>Đóng</button>
          <button className="btn-primary" disabled={busy || !cur || !pw}>Lưu</button>
        </div>
      </form>
    </div>
  );
}
