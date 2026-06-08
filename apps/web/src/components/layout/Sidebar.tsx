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
} from '@heroicons/react/24/outline';
import { SparklesIcon } from '@heroicons/react/24/solid';

import { useSession } from '@/hooks/useSession';

const clientNavigation = [
  { href: '/', icon: HomeIcon, label: 'داشبورد', badge: null },
  { href: '/new', icon: DocumentPlusIcon, label: 'ثبت بارنامه', badge: 'جدید' },
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
    <aside className="flex h-full flex-col rounded-[2rem] border border-white/10 bg-slate-950 p-5 text-white shadow-2xl shadow-slate-950/40">
      {/* Logo */}
      <div className="mb-8 px-1">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-400 to-cyan-600 shadow-[0_0_24px_rgba(6,182,212,0.4)]">
            <SparklesIcon className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-white">BarPro</h1>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400">UTCMS Automation</p>
          </div>
        </div>

        {/* automation status dot */}
        <div className="mt-4 flex items-center gap-2 rounded-xl bg-white/5 border border-white/5 px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_6px_rgba(52,211,153,0.6)]" />
          <span className="text-[11px] font-semibold text-slate-300">اتوماسیون فعال</span>
          <span className="mr-auto text-[10px] text-slate-500 font-mono">utcms_direct ✓</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1">
        {navigation.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={[
                'group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all duration-200',
                active
                  ? 'bg-white text-slate-950 shadow-xl shadow-white/10'
                  : 'text-slate-400 hover:bg-white/5 hover:text-white',
              ].join(' ')}
            >
              <item.icon
                className={[
                  'h-5 w-5 transition-colors shrink-0',
                  active ? 'text-cyan-600' : 'text-slate-500 group-hover:text-cyan-400',
                ].join(' ')}
              />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="rounded-full bg-cyan-400 px-2 py-0.5 text-[9px] font-black text-slate-950 leading-none">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer info */}
      <div className="mt-6 rounded-2xl bg-gradient-to-br from-cyan-500/10 to-transparent border border-cyan-500/10 p-4">
        <div className="flex items-start gap-2">
          <Cog6ToothIcon className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-[11px] font-bold text-white">
              {isAdmin ? 'وضعیت سیستم' : 'موتور اتوماسیون v2'}
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-400">
              {isAdmin
                ? 'تمامی سرویس‌های اتوماسیون و مانیتورینگ در وضعیت عملیاتی قرار دارند.'
                : 'انتخاب مستقیم ddStateSource / ddCitySource با اولویت Fast-Path فعال است.'}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
