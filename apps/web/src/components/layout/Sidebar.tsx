'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BuildingOffice2Icon, ChartBarIcon, ClockIcon, DocumentPlusIcon, HomeIcon, TruckIcon, UserCircleIcon } from '@heroicons/react/24/outline';

import { useSession } from '@/hooks/useSession';

const clientNavigation = [
  { href: '/', icon: HomeIcon, label: 'داشبورد' },
  { href: '/new', icon: DocumentPlusIcon, label: 'ثبت بارنامه' },
  { href: '/history', icon: ClockIcon, label: 'پیگیری کارها' },
  { href: '/drivers', icon: TruckIcon, label: 'رانندگان' },
  { href: '/reports', icon: ChartBarIcon, label: 'گزارش‌ها' },
  { href: '/settings', icon: UserCircleIcon, label: 'حساب کاربری' },
];

const adminNavigation = [
  { href: '/admin', icon: BuildingOffice2Icon, label: 'مدیریت مشتری‌ها' },
];

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const pathname = usePathname();
  const { isAdmin } = useSession();
  const navigation = isAdmin ? adminNavigation : clientNavigation;

  return (
    <aside className="flex h-full flex-col rounded-[32px] border border-white/10 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-950/40">
      <div className="mb-10 px-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500 shadow-[0_0_20px_rgba(6,182,212,0.3)]">
            <BuildingOffice2Icon className="h-6 w-6 text-slate-950" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-white">BarPro</h1>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-400">Automation Stack</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1.5">
        {navigation.map((item) => {
          const active = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={[
                'group flex items-center gap-3 rounded-2xl px-4 py-3.5 text-sm font-semibold transition-all duration-200',
                active
                  ? 'bg-white text-slate-950 shadow-xl shadow-white/5'
                  : 'text-slate-400 hover:bg-white/5 hover:text-white',
              ].join(' ')}
            >
              <item.icon className={['h-5 w-5 transition-colors', active ? 'text-cyan-600' : 'text-slate-500 group-hover:text-cyan-400'].join(' ')} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-8 rounded-[24px] bg-gradient-to-br from-white/5 to-transparent p-5">
        <p className="text-xs font-bold text-slate-200">{isAdmin ? 'وضعیت سیستم' : 'پشتیبانی هوشمند'}</p>
        <p className="mt-2 text-[11px] leading-5 text-slate-400">
          {isAdmin
            ? 'تمامی سرویس‌های اتوماسیون و مانیتورینگ در وضعیت عملیاتی قرار دارند.'
            : 'در صورت نیاز به راهنمایی یا بروز اختلال در ثبت، با ادمین ارشد در ارتباط باشید.'}
        </p>
      </div>
    </aside>
  );
}

