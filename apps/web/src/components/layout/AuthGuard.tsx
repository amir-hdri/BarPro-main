'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { useSession } from '@/hooks/useSession';

interface AuthGuardProps {
  children: React.ReactNode;
  requiredRole?: 'client' | 'master_admin';
}

export function AuthGuard({ children, requiredRole }: AuthGuardProps) {
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useSession();
  const hasRequiredRole = requiredRole ? role === requiredRole : true;

  useEffect(() => {
    if (!isReady) return;

    if (!isAuthenticated) {
      router.replace('/auth');
      return;
    }
    if (isAuthenticated && requiredRole && !hasRequiredRole) {
      router.replace(role === 'master_admin' ? '/admin' : '/');
    }
  }, [hasRequiredRole, isAuthenticated, isReady, requiredRole, role, router]);

  if (!isReady) {
    return <div className="rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-8 text-sm text-slate-300 font-bold">در حال آماده‌سازی پنل...</div>;
  }

  if (!isAuthenticated) {
    return (
      <div className="rounded-[2rem] border border-amber-500/20 bg-amber-500/5 p-8 text-right shadow-2xl backdrop-blur-xl">
        <h3 className="text-lg font-bold text-amber-400">برای ادامه وارد حساب شوید</h3>
        <p className="mt-2 text-sm leading-6 text-slate-300 font-medium">این بخش به توکن JWT چندمستاجره متصل است و بدون ورود امکان بارگذاری داده‌ها ندارد.</p>
        <Link href="/auth" className="mt-6 inline-flex rounded-2xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 px-6 py-3.5 text-sm font-black text-slate-950 transition shadow-lg shadow-amber-500/20 active:scale-95">
          رفتن به صفحه ورود
        </Link>
      </div>
    );
  }

  if (requiredRole && !hasRequiredRole) {
    return (
      <div className="rounded-[2rem] border border-rose-500/20 bg-rose-500/5 p-8 text-right shadow-2xl backdrop-blur-xl">
        <h3 className="text-lg font-bold text-rose-400">دسترسی این بخش محدود است</h3>
        <p className="mt-2 text-sm leading-6 text-slate-300 font-medium">
          این صفحه فقط برای {requiredRole === 'master_admin' ? 'ادمین اصلی سیستم' : 'کاربران مشتری'} در دسترس است.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
