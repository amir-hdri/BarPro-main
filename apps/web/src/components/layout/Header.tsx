'use client';

import { Bars3Icon, ArrowRightStartOnRectangleIcon, SignalIcon } from '@heroicons/react/24/outline';
import type { StoredClient } from '@/lib/auth';

interface HeaderProps {
  client: StoredClient | null;
  role: StoredClient['role'] | null;
  onLogout: () => void;
  onOpenMenu: () => void;
}

export function Header({ client, role, onLogout, onOpenMenu }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 mb-3 md:mb-5 flex items-center justify-between rounded-2xl md:rounded-[2.5rem] border border-white/10 bg-slate-900/40 px-4 py-3 md:px-8 md:py-5 shadow-[0_10px_40px_-10px_rgba(0,0,0,0.4)] backdrop-blur-xl transition-all duration-400 hover:bg-slate-900/50 hover:border-white/15">
      <div className="flex items-center gap-3 md:gap-5">
        <button
          type="button"
          onClick={onOpenMenu}
          className="inline-flex h-11 w-11 md:h-12 md:w-12 items-center justify-center rounded-xl md:rounded-[1.25rem] border border-white/10 bg-slate-950/60 text-slate-300 shadow-sm transition-all hover:bg-slate-900 hover:border-white/20 hover:scale-105 active:scale-95 xl:hidden"
        >
          <Bars3Icon className="h-5 w-5 md:h-6 md:w-6" />
        </button>
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 md:px-3 md:py-1 shadow-sm">
              <span className="relative flex h-1.5 w-1.5 md:h-2 md:w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 md:h-2 md:w-2 bg-emerald-500"></span>
              </span>
              <span className="text-[9px] md:text-[10px] font-black text-emerald-400 tracking-wider">ربات سامانه ملی آنلاین</span>
            </div>
          </div>
          <h2 className="text-base md:text-xl font-black text-slate-100 bg-clip-text text-transparent bg-gradient-to-r from-slate-100 to-slate-400">کنسول عملیاتی و اتوماسیون بارنامه BarPro</h2>
        </div>
      </div>

      <div className="flex items-center gap-3 md:gap-4">
        <div className="hidden items-center gap-2 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-2 sm:flex shadow-sm">
          <SignalIcon className="h-4 w-4 text-cyan-400 animate-pulse" />
          <span className="text-xs font-bold text-cyan-400">سیستم آنلاین</span>
        </div>

        <div className="hidden flex-col items-end rounded-[1.25rem] bg-slate-950 px-5 py-3 text-white shadow-[0_5px_15px_-5px_rgba(2,6,23,0.5)] md:flex border border-slate-800">
          <p className="text-sm font-black">{client?.name || 'مهمان'}</p>
          <p className="mt-1 text-[10px] font-bold text-cyan-400 opacity-90 uppercase">
            {client
              ? `${role === 'master_admin' ? 'مدیر ارشد' : 'کاربر'} • ${client.email}`
              : 'احراز هویت نشده'}
          </p>
        </div>

        {client && (
          <button
            type="button"
            onClick={onLogout}
            className="group relative inline-flex h-11 w-11 md:h-12 md:w-12 items-center justify-center gap-2 rounded-xl md:rounded-[1.25rem] bg-rose-500/15 border border-rose-500/30 text-rose-400 transition-all hover:bg-rose-600 hover:text-white hover:border-rose-600 shadow-sm hover:shadow-[0_0_20px_rgba(225,29,72,0.4)] sm:w-auto sm:px-5 active:scale-95"
          >
            <ArrowRightStartOnRectangleIcon className="h-4 w-4 md:h-5 md:w-5 transition-transform group-hover:-translate-x-1" />
            <span className="hidden text-sm font-bold sm:inline">خروج</span>
          </button>
        )}
      </div>
    </header>
  );
}
