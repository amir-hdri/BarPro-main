'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { api } from '@/lib/api';
import { persistSession } from '@/lib/auth';
import type { AdminLoginResponse, AuthLoginResponse } from '@/lib/types';

import { BarChart3, ShieldCheck, Zap } from 'lucide-react';

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
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(6,182,212,0.15),_transparent_40%),linear-gradient(135deg,_#020617_0%,_#0f172a_40%,_#1e293b_100%)] px-4 py-10 text-white selection:bg-cyan-500/30">
      <main className="mx-auto mt-10 grid max-w-6xl items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="relative overflow-hidden rounded-[48px] border border-white/10 bg-white/5 p-8 shadow-2xl shadow-black/20 backdrop-blur-xl lg:p-14">
          <div className="absolute -left-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
          
          <div className="relative z-10">
            <p className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/5 px-4 py-1.5 text-xs font-medium uppercase tracking-widest text-cyan-300">
              <Zap className="h-3.5 w-3.5" />
              BarPro Automation
            </p>
            
            <h1 className="mt-8 text-4xl font-bold leading-tight tracking-tight lg:text-6xl">
              مدیریت هوشمند و <br />
              <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">اتوماسیون بارنامه</span>
            </h1>
            
            <p className="mt-8 max-w-xl text-lg leading-relaxed text-slate-400">
              راهکاری جامع و یکپارچه برای مدیریت ناوگان، ثبت خودکار بارنامه و مانیتورینگ لحظه‌ای عملیات حمل و نقل در سامانه UTCMS.
            </p>
            
            <div className="mt-12 space-y-6">
              {[
                { icon: Zap, title: "سرعت و دقت بالا", desc: "ثبت خودکار بارنامه با کمترین ضریب خطا و بالاترین سرعت ممکن." },
                { icon: ShieldCheck, title: "امنیت چندلایه", desc: "حفاظت کامل از داده‌های حساس و مدیریت ایزوله هر مستاجر." },
                { icon: BarChart3, title: "گزارش‌گیری زنده", desc: "تحلیل دقیق عملکرد ناوگان و رانندگان در لحظه." }
              ].map((feature, idx) => (
                <div key={idx} className="flex items-start gap-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                    <feature.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-slate-200">{feature.title}</h3>
                    <p className="mt-1 text-sm text-slate-400">{feature.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="w-full max-w-md justify-self-center lg:justify-self-end">
          <div className="overflow-hidden rounded-[40px] border border-white/10 bg-white p-2 text-slate-900 shadow-2xl shadow-cyan-950/20">
            <div className="p-6 lg:p-8">
              <div className="mb-8 flex rounded-2xl bg-slate-100 p-1.5 text-sm font-medium">
                <button
                  type="button"
                  onClick={() => setMode('login')}
                  className={['flex-1 rounded-xl px-4 py-2.5 transition-all duration-200', mode === 'login' ? 'bg-slate-950 text-white shadow-lg' : 'text-slate-600 hover:text-slate-900'].join(' ')}
                >
                  ورود مشتری
                </button>
                <button
                  type="button"
                  onClick={() => setMode('admin')}
                  className={['flex-1 rounded-xl px-4 py-2.5 transition-all duration-200', mode === 'admin' ? 'bg-slate-950 text-white shadow-lg' : 'text-slate-600 hover:text-slate-900'].join(' ')}
                >
                  ورود مدیر اصلی
                </button>
              </div>

              {mode === 'login' ? (
                <form className="space-y-5" onSubmit={handleClientLogin}>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">ایمیل</label>
                    <input
                      type="email"
                      autoComplete="email"
                      required
                      placeholder="example@domain.com"
                      value={login.email}
                      onChange={(event) => setLogin((current) => ({ ...current, email: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-sm outline-none ring-cyan-500/20 transition focus:border-cyan-500 focus:bg-white focus:ring-4"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">رمز عبور</label>
                    <input
                      type="password"
                      autoComplete="current-password"
                      required
                      placeholder="••••••••"
                      value={login.password}
                      onChange={(event) => setLogin((current) => ({ ...current, password: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-sm outline-none ring-cyan-500/20 transition focus:border-cyan-500 focus:bg-white focus:ring-4"
                    />
                  </div>
                  <button type="submit" disabled={loading} className="mt-4 w-full rounded-2xl bg-slate-950 py-4 text-sm font-bold text-white shadow-xl shadow-slate-950/20 transition hover:bg-slate-800 active:scale-[0.98] disabled:opacity-60">
                    {loading ? 'در حال ورود...' : 'ورود به پنل عملیاتی'}
                  </button>
                </form>
              ) : (
                <form className="space-y-5" onSubmit={handleAdminLogin}>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">نام کاربری ادمین</label>
                    <input
                      type="text"
                      autoComplete="username"
                      required
                      value={adminLogin.username}
                      onChange={(event) => setAdminLogin((current) => ({ ...current, username: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-sm outline-none ring-cyan-500/20 transition focus:border-cyan-500 focus:bg-white focus:ring-4"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-semibold text-slate-700">رمز عبور ادمین</label>
                    <input
                      type="password"
                      autoComplete="current-password"
                      required
                      value={adminLogin.password}
                      onChange={(event) => setAdminLogin((current) => ({ ...current, password: event.target.value }))}
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-sm outline-none ring-cyan-500/20 transition focus:border-cyan-500 focus:bg-white focus:ring-4"
                    />
                  </div>
                  <button type="submit" disabled={loading} className="mt-4 w-full rounded-2xl bg-cyan-500 py-4 text-sm font-bold text-slate-950 shadow-xl shadow-cyan-500/20 transition hover:bg-cyan-400 active:scale-[0.98] disabled:opacity-60">
                    {loading ? 'در حال ورود...' : 'ورود به پنل مدیریت'}
                  </button>
                </form>
              )}

              {(error || message) && (
                <div className={`mt-6 animate-in fade-in slide-in-from-top-2 rounded-2xl p-4 text-sm font-medium ${error ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'}`}>
                  {error || message}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

