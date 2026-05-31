'use client';

import { Bars3Icon, ArrowLeftOnRectangleIcon } from '@heroicons/react/24/outline';

import type { StoredClient } from '@/lib/auth';

interface HeaderProps {
  client: StoredClient | null;
  role: StoredClient['role'] | null;
  onLogout: () => void;
  onOpenMenu: () => void;
}

export function Header({ client, role, onLogout, onOpenMenu }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 mb-8 flex items-center justify-between rounded-[32px] border border-white/20 bg-white/80 px-6 py-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onOpenMenu}
          className="inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-slate-100 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50 xl:hidden"
        >
          <Bars3Icon className="h-6 w-6" />
        </button>
        <div>
          <p className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-400">Live Operation</p>
          <h2 className="text-xl font-black tracking-tight text-slate-900">کنسول مدیریتی باربر</h2>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden flex-col items-end rounded-[22px] bg-slate-950 px-5 py-3 text-white shadow-lg shadow-slate-950/20 md:flex">
          <p className="text-xs font-black tracking-wide">{client?.name || 'مهمان'}</p>
          <p className="mt-0.5 text-[10px] font-bold text-cyan-400 opacity-80">
            {client ? `${role === 'master_admin' ? 'مدیر ارشد' : 'پنل مشتری'} • ${client.email}` : 'احراز هویت نشده'}
          </p>
        </div>
        {client && (
          <button
            type="button"
            onClick={onLogout}
            className="group inline-flex h-12 items-center gap-2 rounded-2xl border border-rose-100 bg-rose-50 px-5 text-sm font-bold text-rose-600 transition-all hover:bg-rose-600 hover:text-white hover:shadow-lg hover:shadow-rose-600/20"
          >
            <ArrowLeftOnRectangleIcon className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
            <span className="hidden sm:inline">خروج</span>
          </button>
        )}
      </div>
    </header>
  );
}

