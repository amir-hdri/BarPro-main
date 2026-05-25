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
    if (isReady && !isAuthenticated) {
      router.replace('/auth');
      return;
    }
    if (isReady && isAuthenticated && requiredRole && !hasRequiredRole) {
      router.replace(role === 'master_admin' ? '/admin' : '/');
    }
  }, [hasRequiredRole, isAuthenticated, isReady, requiredRole, role, router]);

  if (!isReady) {
    return <div className="rounded-[28px] border border-white/20 bg-white/70 p-8 text-sm text-slate-500">در حال آماده‌سازی پنل...</div>;
  }

  if (!isAuthenticated) {
    return (
      <div className="rounded-[28px] border border-amber-200 bg-amber-50 p-8 text-right shadow-sm">
        <h3 className="text-lg font-semibold text-amber-900">برای ادامه وارد حساب شوید</h3>
        <p className="mt-2 text-sm leading-6 text-amber-800">این بخش به توکن JWT چندمستاجره متصل است و بدون ورود امکان بارگذاری داده‌ها ندارد.</p>
        <Link href="/auth" className="mt-5 inline-flex rounded-2xl bg-amber-500 px-5 py-3 text-sm font-medium text-white">
          رفتن به صفحه ورود
        </Link>
      </div>
    );
  }

  if (requiredRole && !hasRequiredRole) {
    return (
      <div className="rounded-[28px] border border-rose-200 bg-rose-50 p-8 text-right shadow-sm">
        <h3 className="text-lg font-semibold text-rose-900">دسترسی این بخش محدود است</h3>
        <p className="mt-2 text-sm leading-6 text-rose-800">
          این صفحه فقط برای {requiredRole === 'master_admin' ? 'ادمین اصلی سیستم' : 'کاربران مشتری'} در دسترس است.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
