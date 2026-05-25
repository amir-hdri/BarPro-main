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
    <aside className="flex h-full flex-col rounded-[28px] border border-white/10 bg-slate-950/80 p-5 text-white shadow-2xl shadow-slate-950/30 backdrop-blur xl:p-6">
      <div className="mb-8 rounded-3xl border border-cyan-400/20 bg-gradient-to-br from-cyan-400/15 via-sky-400/10 to-amber-300/10 p-5">
        <p className="text-xs uppercase tracking-[0.35em] text-cyan-200/80">UTCMS Control</p>
        <h1 className="mt-3 text-2xl font-semibold text-white">{isAdmin ? 'کنسول مدیریت مشتری‌ها' : 'پنل عملیات بارنامه'}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-300">
          {isAdmin
            ? 'ساخت، ویرایش و حذف حساب‌های مشتری فقط برای ادمین اصلی سیستم.'
            : 'ورود، ثبت، پایش و پیگیری تمام ماموریت‌ها در یک نمای فارسی و واکنش‌گرا.'}
        </p>
      </div>

      <nav className="flex-1 space-y-2">
        {navigation.map((item) => {
          const active = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={[
                'group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition',
                active
                  ? 'bg-white text-slate-950 shadow-lg shadow-cyan-500/10'
                  : 'text-slate-300 hover:bg-white/10 hover:text-white',
              ].join(' ')}
            >
              <item.icon className={['h-5 w-5', active ? 'text-cyan-600' : 'text-slate-400 group-hover:text-cyan-200'].join(' ')} />
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
        <p className="font-medium text-white">{isAdmin ? 'نکته مدیریتی' : 'نکته عملیاتی'}</p>
        <p className="mt-2 leading-6">
          {isAdmin
            ? 'ثبت‌نام عمومی بسته است؛ ساخت هر مشتری جدید فقط از همین پنل انجام می‌شود.'
            : 'اگر وضعیت کاری روی «OTP» بایستد، از بخش تاریخچه روی همان کار کلیک کنید و زمان تلاش بعدی را بررسی کنید.'}
        </p>
      </div>
    </aside>
  );
}
