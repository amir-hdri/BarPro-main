'use client';

import { Bars3Icon, ArrowLeftOnRectangleIcon, SignalIcon } from '@heroicons/react/24/outline';
import type { StoredClient } from '@/lib/auth';

interface HeaderProps {
  client: StoredClient | null;
  role: StoredClient['role'] | null;
  onLogout: () => void;
  onOpenMenu: () => void;
}

export function Header({ client, role, onLogout, onOpenMenu }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 mb-8 flex items-center justify-between rounded-[2rem] border border-white/60 bg-white/80 px-6 py-4 shadow-lg shadow-slate-900/5 backdrop-blur-xl">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onOpenMenu}
          className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-100 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 xl:hidden"
        >
          <Bars3Icon className="h-5 w-5" />
        </button>
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <div className="flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-100 px-2.5 py-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-bold text-emerald-700">UTCMS Bot Active</span>
            </div>
          </div>
          <h2 className="text-lg font-black tracking-tight text-slate-900">کنسول عملیاتی BarPro</h2>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* System status pill */}
        <div className="hidden items-center gap-1.5 rounded-full border border-slate-100 bg-slate-50 px-3 py-1.5 sm:flex">
          <SignalIcon className="h-3.5 w-3.5 text-cyan-500" />
          <span className="text-[10px] font-bold text-slate-600">سیستم آنلاین</span>
        </div>

        {/* User info */}
        <div className="hidden flex-col items-end rounded-2xl bg-slate-950 px-4 py-2.5 text-white shadow-lg shadow-slate-950/20 md:flex">
          <p className="text-xs font-black tracking-wide">{client?.name || 'مهمان'}</p>
          <p className="mt-0.5 text-[10px] font-bold text-cyan-400 opacity-80">
            {client
              ? `${role === 'master_admin' ? 'مدیر ارشد' : 'کاربر'} • ${client.email}`
              : 'احراز هویت نشده'}
          </p>
        </div>

        {client && (
          <button
            type="button"
            onClick={onLogout}
            className="group inline-flex h-11 items-center gap-2 rounded-2xl border border-rose-100 bg-rose-50 px-4 text-sm font-bold text-rose-600 transition-all hover:bg-rose-600 hover:text-white hover:shadow-lg hover:shadow-rose-600/20"
          >
            <ArrowLeftOnRectangleIcon className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
            <span className="hidden sm:inline">خروج</span>
          </button>
        )}
      </div>
    </header>
  );
}
