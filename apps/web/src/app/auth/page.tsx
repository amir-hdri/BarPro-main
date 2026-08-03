'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { api } from '@/lib/api';
import { persistSession } from '@/lib/auth';
import type { AdminLoginResponse, AuthLoginResponse } from '@/lib/types';
import { TruckIcon, ShieldCheckIcon } from '@heroicons/react/24/solid';

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'admin'>('login');
  const [login, setLogin] = useState({ email: '', password: '' });
  const [adminLogin, setAdminLogin] = useState({ username: '', password: '' });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const completeClientLogin = async (payload: AuthLoginResponse) => {
    const client = payload.client;
    await persistSession({
      id: client.id,
      name: client.name,
      email: client.email,
      client_code: client.client_code,
      role: 'client',
    });
    router.push('/');
    router.refresh();
  };

  const completeAdminLogin = async (payload: AdminLoginResponse) => {
    await persistSession({
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

    await completeClientLogin(response.data);
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

    await completeAdminLogin(response.data);
  };

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-[#030712] text-white selection:bg-cyan-500/30 overflow-hidden relative flex flex-col items-center justify-center p-4">
      
      {/* ─── Premium Animated Background ─── */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        {/* Dynamic mesh gradient */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#030712] to-[#030712]"></div>
        
        {/* Animated glowing orbs */}
        <div className="absolute top-[20%] left-[20%] w-[500px] h-[500px] rounded-full bg-cyan-600/10 blur-[120px] animate-[pulse-glow_8s_ease-in-out_infinite]" />
        <div className="absolute bottom-[20%] right-[20%] w-[600px] h-[600px] rounded-full bg-blue-600/10 blur-[130px] animate-[pulse-glow_10s_ease-in-out_infinite_reverse]" />
        
        {/* Subtle noise texture */}
        <div className="absolute inset-0 opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')] mix-blend-overlay"></div>
      </div>

      <main className="relative z-10 w-full max-w-[420px] mx-auto animate-in fade-in-up duration-1000 slide-in-from-bottom-8">
        
        {/* ─── Premium Logo Section ─── */}
        <div className="flex flex-col items-center justify-center mb-10 text-center relative group">
          <div className="relative mb-6">
            {/* Outer rotating ring */}
            <div className="absolute -inset-4 rounded-full bg-gradient-to-tr from-cyan-500/0 via-cyan-400/40 to-blue-500/0 animate-[spin_4s_linear_infinite] blur-md group-hover:via-cyan-400/60 transition-all duration-500"></div>
            
            {/* Inner solid ring */}
            <div className="absolute -inset-1 rounded-full bg-gradient-to-b from-cyan-400 to-blue-600 opacity-50 blur-sm"></div>
            
            {/* Main logo circle */}
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-slate-950 border border-white/10 shadow-[inset_0_2px_20px_rgba(255,255,255,0.1)] overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/20 to-transparent"></div>
              <TruckIcon className="h-9 w-9 text-cyan-400 transform transition-transform duration-500 group-hover:scale-110 drop-shadow-[0_0_15px_rgba(34,211,238,0.5)]" />
            </div>
          </div>
          
          <h1 className="text-4xl sm:text-5xl font-black bg-clip-text text-transparent bg-gradient-to-b from-white via-slate-200 to-slate-500 drop-shadow-sm">
            Bar Pro
          </h1>
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="h-px w-8 bg-gradient-to-r from-transparent to-cyan-500/50"></span>
            <p className="text-[11px] font-bold uppercase text-cyan-400/90 tracking-widest">
              Enterprise Edition
            </p>
            <span className="h-px w-8 bg-gradient-to-l from-transparent to-cyan-500/50"></span>
          </div>
        </div>

        {/* ─── Glassmorphism Login Card ─── */}
        <div className="relative rounded-[2rem] p-[1px] bg-gradient-to-b from-white/10 to-white/5 shadow-2xl backdrop-blur-2xl transition-all duration-500 hover:shadow-[0_0_80px_rgba(6,182,212,0.15)]">
          
          <div className="relative rounded-[2rem] bg-slate-950/60 p-6 sm:p-8 overflow-hidden h-full">
            {/* Inner top highlight line */}
            <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent"></div>

            {/* Mode Switcher */}
            <div className="relative flex rounded-[1rem] bg-slate-900/80 p-1 mb-8 shadow-inner border border-white/5">
              <button
                type="button"
                onClick={() => setMode('login')}
                className={[
                  'relative flex-1 rounded-[0.85rem] py-3 text-[13px] font-bold transition-all duration-300 z-10 flex items-center justify-center gap-2',
                  mode === 'login' ? 'text-white shadow-lg border border-white/10 bg-slate-800' : 'text-slate-400 hover:text-slate-200'
                ].join(' ')}
              >
                <TruckIcon className="h-4 w-4" />
                ورود کاربر
                {mode === 'login' && <div className="absolute inset-0 rounded-[0.85rem] bg-gradient-to-b from-white/5 to-transparent pointer-events-none"></div>}
              </button>
              
              <button
                type="button"
                onClick={() => setMode('admin')}
                className={[
                  'relative flex-1 rounded-[0.85rem] py-3 text-[13px] font-bold transition-all duration-300 z-10 flex items-center justify-center gap-2',
                  mode === 'admin' ? 'text-white shadow-lg border border-white/10 bg-slate-800' : 'text-slate-400 hover:text-slate-200'
                ].join(' ')}
              >
                <ShieldCheckIcon className="h-4 w-4" />
                ورود ادمین
                {mode === 'admin' && <div className="absolute inset-0 rounded-[0.85rem] bg-gradient-to-b from-white/5 to-transparent pointer-events-none"></div>}
              </button>
            </div>

            {/* Client Login Form */}
            {mode === 'login' && (
              <form className="space-y-5 animate-in slide-in-from-left-4 fade-in duration-500" onSubmit={handleClientLogin}>
                <div className="space-y-1.5">
                  <label className="text-[12px] font-bold text-slate-400 px-1">ایمیل کاربر</label>
                  <div className="relative group">
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-cyan-500/20 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity blur-sm"></div>
                    <input
                      type="email"
                      autoComplete="email"
                      required
                      placeholder="user@company.com"
                      value={login.email}
                      onChange={(event) => setLogin((current) => ({ ...current, email: event.target.value }))}
                      className="relative w-full rounded-2xl border border-white/10 bg-slate-900/50 px-5 py-4 text-[14px] text-white outline-none transition-all placeholder:text-slate-600 focus:border-cyan-500/50 focus:bg-slate-900 focus:shadow-[0_0_20px_rgba(6,182,212,0.1)]"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center px-1">
                    <label className="text-[12px] font-bold text-slate-400">رمز عبور</label>
                  </div>
                  <div className="relative group">
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-cyan-500/20 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity blur-sm"></div>
                    <input
                      type="password"
                      autoComplete="current-password"
                      required
                      placeholder="••••••••"
                      value={login.password}
                      onChange={(event) => setLogin((current) => ({ ...current, password: event.target.value }))}
                      className="relative w-full rounded-2xl border border-white/10 bg-slate-900/50 px-5 py-4 text-[14px] text-white outline-none transition-all placeholder:text-slate-600 focus:border-cyan-500/50 focus:bg-slate-900 focus:shadow-[0_0_20px_rgba(6,182,212,0.1)]"
                    />
                  </div>
                </div>
                <div className="pt-2">
                  <button 
                    type="submit" 
                    disabled={loading} 
                    className="relative group w-full overflow-hidden rounded-2xl p-[1px] disabled:opacity-60 disabled:hover:scale-100 active:scale-[0.98] transition-all"
                  >
                    <span className="absolute inset-0 bg-gradient-to-r from-cyan-400 via-blue-500 to-cyan-400 rounded-2xl animate-[shimmer_2s_linear_infinite] bg-[length:200%_auto]"></span>
                    <div className="relative flex items-center justify-center h-14 bg-slate-950 rounded-[15px] group-hover:bg-slate-900 transition-colors">
                      {loading ? (
                        <span className="h-5 w-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></span>
                      ) : (
                        <span className="text-sm font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400">ورود به سیستم یکپارچه</span>
                      )}
                    </div>
                  </button>
                </div>
              </form>
            )}

            {/* Admin Login Form */}
            {mode === 'admin' && (
              <form className="space-y-5 animate-in slide-in-from-right-4 fade-in duration-500" onSubmit={handleAdminLogin}>
                <div className="space-y-1.5">
                  <label className="text-[12px] font-bold text-slate-400 px-1">شناسه سیستم</label>
                  <div className="relative group">
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-blue-500/20 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity blur-sm"></div>
                    <input
                      type="text"
                      autoComplete="username"
                      required
                      placeholder="admin_root"
                      value={adminLogin.username}
                      onChange={(event) => setAdminLogin((current) => ({ ...current, username: event.target.value }))}
                      className="relative w-full rounded-2xl border border-white/10 bg-slate-900/50 px-5 py-4 text-[14px] text-white outline-none transition-all placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-900 focus:shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center px-1">
                    <label className="text-[12px] font-bold text-slate-400">کلید امنیتی</label>
                  </div>
                  <div className="relative group">
                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-blue-500/20 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity blur-sm"></div>
                    <input
                      type="password"
                      autoComplete="current-password"
                      required
                      placeholder="••••••••"
                      value={adminLogin.password}
                      onChange={(event) => setAdminLogin((current) => ({ ...current, password: event.target.value }))}
                      className="relative w-full rounded-2xl border border-white/10 bg-slate-900/50 px-5 py-4 text-[14px] text-white outline-none transition-all placeholder:text-slate-600 focus:border-blue-500/50 focus:bg-slate-900 focus:shadow-[0_0_20px_rgba(59,130,246,0.1)]"
                    />
                  </div>
                </div>
                <div className="pt-2">
                  <button 
                    type="submit" 
                    disabled={loading} 
                    className="relative group w-full overflow-hidden rounded-2xl p-[1px] disabled:opacity-60 disabled:hover:scale-100 active:scale-[0.98] transition-all"
                  >
                    <span className="absolute inset-0 bg-gradient-to-r from-slate-400 via-white to-slate-400 rounded-2xl animate-[shimmer_2s_linear_infinite] bg-[length:200%_auto]"></span>
                    <div className="relative flex items-center justify-center h-14 bg-white text-slate-950 rounded-[15px] group-hover:bg-slate-100 transition-colors shadow-[0_0_30px_rgba(255,255,255,0.1)]">
                      {loading ? (
                        <span className="h-5 w-5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
                      ) : (
                        <span className="text-sm font-black">ورود به کنسول ارشد</span>
                      )}
                    </div>
                  </button>
                </div>
              </form>
            )}

            {(error || message) && (
              <div className={`mt-6 animate-in fade-in slide-in-from-bottom-2 rounded-xl border p-3.5 text-[13px] font-bold text-center backdrop-blur-md ${error ? 'bg-rose-500/10 border-rose-500/20 text-rose-400' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'}`}>
                {error || message}
              </div>
            )}
          </div>
        </div>

        {/* ─── Footer ─── */}
        <p className="mt-8 text-center text-[11px] font-medium text-slate-500">
          تمامی حقوق برای سیستم هوشمند BarPro محفوظ است
        </p>
      </main>
    </div>
  );
}
