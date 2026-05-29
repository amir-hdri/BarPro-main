'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { api } from '@/lib/api';
import { persistSession } from '@/lib/auth';
import type { AdminLoginResponse, AuthLoginResponse } from '@/lib/types';

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'admin'>('login');
  const [login, setLogin] = useState({ email: '', password: '' });
  const [adminLogin, setAdminLogin] = useState({ username: '', password: '' });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const completeClientLogin = (payload: AuthLoginResponse) => {
    const client = payload.client;
    persistSession(payload.access_token, {
      id: client.id,
      name: client.name,
      email: client.email,
      client_code: client.client_code,
      role: 'client',
    });
    router.push('/');
    router.refresh();
  };

  const completeAdminLogin = (payload: AdminLoginResponse) => {
    persistSession(payload.access_token, {
      id: null,
      name: payload.admin.username,
      email: `${payload.admin.username}@local.admin`,
      client_code: payload.admin.username,
      role: 'master_admin',
    });
    router.push('/admin/dashboard');
    router.refresh();
  };

  const handleClientLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    const response = await api.post<AuthLoginResponse>('/api/v1/auth/login', login);
    setLoading(false);

    if (!response.success || !response.data) {
      setError(response.error || 'ورود انجام نشد');
      return;
    }

    completeClientLogin(response.data);
  };

  const handleAdminLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    const response = await api.post<AdminLoginResponse>('/api/v1/admin/login', adminLogin);
    setLoading(false);

    if (!response.success || !response.data) {
      setError(response.error || 'ورود ادمین انجام نشد');
      return;
    }

    completeAdminLogin(response.data);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(6,182,212,0.2),_transparent_35%),linear-gradient(135deg,_#020617_0%,_#0f172a_40%,_#1e293b_100%)] px-4 py-10 text-white">
      <main className="mx-auto grid max-w-6xl gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[36px] border border-white/10 bg-white/5 p-8 shadow-2xl shadow-black/20 backdrop-blur lg:p-12">
          <p className="text-sm uppercase tracking-[0.4em] text-cyan-200">Barname Automation</p>
          <h1 className="mt-5 text-4xl font-semibold leading-tight lg:text-6xl">ورود عملیاتی برای مشتری‌ها و ادمین اصلی</h1>
          <p className="mt-5 max-w-2xl text-base leading-8 text-slate-300 lg:text-lg">
            ثبت‌نام عمومی بسته شده است. از این پس فقط `master_bar` می‌تواند مشتری جدید بسازد، و هر مشتری فقط با حساب خودش وارد پنل عملیاتی می‌شود.
          </p>
          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {[
              ['Client Login', 'ورود مشتری و ادامه کار با راننده‌ها و jobها'],
              ['Master Admin', 'مدیریت کامل حساب‌های مشتری از یک پنل جدا'],
              ['Closed Signup', 'ساخت حساب جدید فقط از سوی ادمین اصلی'],
            ].map(([title, text]) => (
              <div key={title} className="rounded-3xl border border-white/10 bg-slate-950/40 p-5">
                <p className="text-sm font-semibold text-cyan-200">{title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <div className="rounded-[36px] border border-white/10 bg-white p-6 text-slate-900 shadow-2xl shadow-cyan-950/20 lg:p-8">
          <div className="flex rounded-2xl bg-slate-100 p-1 text-sm font-medium">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={['flex-1 rounded-2xl px-4 py-3 transition', mode === 'login' ? 'bg-slate-900 text-white' : 'text-slate-700'].join(' ')}
            >
              ورود مشتری
            </button>
            <button
              type="button"
              onClick={() => setMode('admin')}
              className={['flex-1 rounded-2xl px-4 py-3 transition', mode === 'admin' ? 'bg-slate-900 text-white' : 'text-slate-700'].join(' ')}
            >
              ورود ادمین اصلی
            </button>
          </div>

          {mode === 'login' ? (
            <form className="mt-6 space-y-4" onSubmit={handleClientLogin}>
              <Field label="ایمیل">
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={login.email}
                  onChange={(event) => setLogin((current) => ({ ...current, email: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none ring-0 transition focus:border-cyan-500"
                />
              </Field>
              <Field label="رمز عبور">
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={login.password}
                  onChange={(event) => setLogin((current) => ({ ...current, password: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none ring-0 transition focus:border-cyan-500"
                />
              </Field>
              <button type="submit" disabled={loading} className="w-full rounded-2xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60">
                {loading ? 'در حال ورود...' : 'ورود به پنل مشتری'}
              </button>
            </form>
          ) : (
            <form className="mt-6 space-y-4" onSubmit={handleAdminLogin}>
              <Field label="نام کاربری ادمین">
                <input
                  type="text"
                  autoComplete="username"
                  required
                  value={adminLogin.username}
                  onChange={(event) => setAdminLogin((current) => ({ ...current, username: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-cyan-500"
                />
              </Field>
              <Field label="رمز عبور ادمین">
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={adminLogin.password}
                  onChange={(event) => setAdminLogin((current) => ({ ...current, password: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 px-4 py-3 outline-none transition focus:border-cyan-500"
                />
              </Field>
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
                ساخت مشتری جدید فقط بعد از ورود با حساب `master_bar` از پنل مدیریت انجام می‌شود.
              </div>
              <button type="submit" disabled={loading} className="w-full rounded-2xl bg-cyan-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-60">
                {loading ? 'در حال ورود...' : 'ورود به پنل ادمین'}
              </button>
            </form>
          )}

          {error && <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
          {message && <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</p>}
        </div>
      </main>
    </div>
  );
}

function Field({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      <span className="mb-2 block">{label}</span>
      {children}
    </label>
  );
}
