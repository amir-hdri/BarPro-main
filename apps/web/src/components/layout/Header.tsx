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
    <header className="sticky top-0 z-30 mb-6 flex items-center justify-between rounded-[28px] border border-white/10 bg-white/70 px-4 py-4 shadow-lg shadow-slate-900/5 backdrop-blur md:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenMenu}
          className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 text-slate-700 xl:hidden"
        >
          <Bars3Icon className="h-6 w-6" />
        </button>
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Automation Console</p>
          <h2 className="text-lg font-semibold text-slate-900">وضعیت زنده عملیات بارنامه</h2>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden rounded-2xl bg-slate-900 px-4 py-3 text-right text-white md:block">
          <p className="text-sm font-medium">{client?.name || 'مهمان'}</p>
          <p className="text-xs text-slate-300">
            {client ? `${role === 'master_admin' ? 'ادمین اصلی' : 'مشتری'} • ${client.email}` : 'برای کار با پنل وارد شوید'}
          </p>
        </div>
        {client && (
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 transition hover:bg-rose-100"
          >
            <ArrowLeftOnRectangleIcon className="h-5 w-5" />
            خروج
          </button>
        )}
      </div>
    </header>
  );
}
