'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BuildingOffice2Icon,
  ChartBarIcon,
  ClockIcon,
  DocumentPlusIcon,
  HomeIcon,
  TruckIcon,
  UserCircleIcon,
  Cog6ToothIcon,
  FireIcon,
} from '@heroicons/react/24/outline';
import { SparklesIcon } from '@heroicons/react/24/solid';

import { useSession } from '@/hooks/useSession';

const clientNavigation = [
  { href: '/', icon: HomeIcon, label: 'داشبورد', badge: null },
  { href: '/new', icon: DocumentPlusIcon, label: 'ثبت بارنامه', badge: 'جدید' },
  { href: '/fuel', icon: FireIcon, label: 'استعلام سوخت', badge: null },
  { href: '/history', icon: ClockIcon, label: 'پیگیری کارها', badge: null },
  { href: '/drivers', icon: TruckIcon, label: 'رانندگان', badge: null },
  { href: '/reports', icon: ChartBarIcon, label: 'گزارش‌ها', badge: null },
  { href: '/settings', icon: UserCircleIcon, label: 'حساب کاربری', badge: null },
];


const adminNavigation = [
  { href: '/admin', icon: BuildingOffice2Icon, label: 'مدیریت مشتری‌ها', badge: null },
];

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const { isAdmin } = useSession();
  const navigation = isAdmin ? adminNavigation : clientNavigation;

  return (
    <aside className="relative flex h-full flex-col rounded-[2.5rem] bg-slate-950 p-6 text-white shadow-[0_20px_60px_-15px_rgba(2,6,23,0.6)] border border-white/10 overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute -top-32 -left-32 h-64 w-64 rounded-full bg-cyan-500/20 blur-[80px] pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 h-64 w-64 rounded-full bg-blue-500/10 blur-[80px] pointer-events-none" />

      {/* Scrollable inner container for all content to prevent overflow on short viewports */}
      <div className="relative z-10 flex flex-col flex-1 overflow-y-auto overflow-x-hidden gap-6 scrollbar-none">
        {/* Logo */}
        <div className="px-2 pt-2">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-[1.25rem] bg-gradient-to-br from-cyan-400 to-cyan-600 shadow-[0_0_30px_rgba(6,182,212,0.5)]">
              <SparklesIcon className="h-6 w-6 text-white animate-pulse" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">BarPro</h1>
              <p className="text-[10px] font-bold uppercase text-cyan-400 mt-0.5">Enterprise</p>
            </div>
          </div>

          {/* automation status dot */}
          <div className="mt-6 flex items-center justify-between rounded-2xl bg-white/5 border border-white/10 px-4 py-3 backdrop-blur-md">
            <div className="flex items-center gap-3">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
              </span>
              <span className="text-[11px] font-bold text-slate-200">اتوماسیون فعال</span>
            </div>
            <span className="text-[10px] font-black text-emerald-400/80 uppercase bg-emerald-400/10 px-2 py-1 rounded-lg">LIVE</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="space-y-2 flex-1">
          {navigation.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={[
                  'group flex items-center gap-4 rounded-2xl px-5 py-3.5 text-sm font-bold transition-all duration-300 relative overflow-hidden',
                  active
                    ? 'bg-gradient-to-r from-cyan-500/10 to-transparent text-cyan-400 border border-cyan-500/20 shadow-[inset_4px_0_0_0_rgba(6,182,212,1)]'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white',
                ].join(' ')}
              >
                <item.icon
                  className={[
                    'h-5 w-5 transition-transform duration-300 shrink-0 group-hover:scale-110',
                    active ? 'text-cyan-400' : 'text-slate-500 group-hover:text-slate-300',
                  ].join(' ')}
                />
                <span className="flex-1 relative z-10">{item.label}</span>
                {item.badge && (
                  <span className="rounded-xl bg-cyan-400/20 border border-cyan-400/30 px-2.5 py-1 text-[10px] font-black text-cyan-400 leading-none shadow-[0_0_10px_rgba(6,182,212,0.2)]">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer info */}
        <div className="rounded-3xl bg-gradient-to-br from-cyan-900/40 to-slate-900/40 border border-cyan-500/20 p-5 backdrop-blur-md shrink-0">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 shrink-0">
              <Cog6ToothIcon className="h-4 w-4 text-cyan-400 animate-[spin_4s_linear_infinite]" />
            </div>
            <div>
              <p className="text-[12px] font-black text-white">
                {isAdmin ? 'وضعیت سیستم' : 'موتور اتوماسیون v2'}
              </p>
              <p className="mt-1.5 text-[11px] leading-5 text-slate-400 font-medium">
                {isAdmin
                  ? 'تمامی سرویس‌های اتوماسیون و مانیتورینگ در وضعیت عملیاتی قرار دارند.'
                  : 'مسیردهی مستقیم با اولویت Fast-Path فعال است.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
