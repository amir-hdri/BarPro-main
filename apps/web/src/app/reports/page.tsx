'use client';

import { useEffect, useMemo, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import { formatRelativePercent, statusLabel, toPersianDigits } from '@/lib/format';
import type { ClientStats, WaybillTaskListResponse } from '@/lib/types';

const emptyStats: ClientStats = {
  client_id: 0,
  total_drivers: 0,
  active_drivers: 0,
  total_jobs: 0,
  pending_jobs: 0,
  in_progress_jobs: 0,
  success_jobs: 0,
  failed_jobs: 0,
  today_jobs: 0,
  today_success: 0,
  today_failed: 0,
  success_rate: 0,
  created_at: new Date(0).toISOString(),
};

export default function ReportsPage() {
  const { client } = useSession();
  const [stats, setStats] = useState<ClientStats>(emptyStats);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      if (client?.role === 'master_admin') {  return; }
      const [statsResponse, jobsResponse] = await Promise.all([
        api.get<ClientStats>('/api/v1/auth/stats'),
        api.get<WaybillTaskListResponse>('/api/v1/waybill-jobs', { page: 1, page_size: 100 }),
      ]);

      if (statsResponse.success && statsResponse.data) {
        setStats(statsResponse.data);
      } else {
        setError(statsResponse.error || 'گزارش‌ها بارگذاری نشدند');
      }

      if (jobsResponse.success && jobsResponse.data) {
        const counts = (jobsResponse.data?.tasks || []).reduce<Record<string, number>>((accumulator, job) => {
          accumulator[job.status] = (accumulator[job.status] || 0) + 1;
          return accumulator;
        }, {});
        setStatusCounts(counts);
      }
    }

    load();
  }, [client?.role]);

  const rateCards = useMemo(
    () => [
      ['نرخ موفقیت کل', formatRelativePercent(stats.success_rate), 'نسبت کل ماموریت‌های موفق به کل پردازش‌ها'],
      ['موفق امروز', toPersianDigits(stats.today_success), 'ماموریت‌هایی که امروز بدون خطا تمام شده‌اند'],
      ['ناموفق امروز', toPersianDigits(stats.today_failed), 'نیازمند پیگیری یا تلاش دوباره'],
      ['ماموریت‌های فعال', toPersianDigits(stats.pending_jobs + stats.in_progress_jobs), 'صف انتظار و ماموریت‌های در حال اجرا'],
    ],
    [stats],
  );

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-[32px] border border-white/20 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/20">
            <p className="text-xs uppercase  text-cyan-300">Analytics</p>
            <h1 className="mt-4 text-3xl font-semibold">گزارش عملکرد مشتری</h1>
            <p className="mt-3 text-sm leading-7 text-slate-300">این صفحه به جای mock، از آمار واقعی مشتری و jobهای ثبت‌شده ساخته می‌شود و برای مرور روزانه عملیات مناسب است.</p>
            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              {rateCards.map(([label, value, hint]) => (
                <article key={label} className="rounded-3xl border border-white/10 bg-white/5 p-5">
                  <p className="text-sm text-cyan-200">{label}</p>
                  <p className="mt-3 text-3xl font-semibold">{value}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-300">{hint}</p>
                </article>
              ))}
            </div>
          </div>

          <div className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 shadow-2xl text-white">
            <h2 className="text-2xl font-black text-white">توزیع وضعیت‌ها</h2>
            <p className="mt-1 text-sm text-slate-400">نمایی سریع از حجم کار بر اساس مرحله پردازش</p>
            <div className="mt-6 space-y-3">
              {Object.keys(statusCounts).length === 0 ? (
                <div className="rounded-3xl border border-dashed border-white/5 bg-slate-950/20 px-5 py-8 text-sm text-slate-400">هنوز داده‌ای برای گزارش وضعیت وجود ندارد.</div>
              ) : (
                Object.entries(statusCounts)
                  .sort((left, right) => right[1] - left[1])
                  .map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between rounded-2xl bg-slate-950/60 border border-white/5 px-4 py-3">
                      <span className="text-sm text-slate-300">{statusLabel(status)}</span>
                      <span className="text-sm font-bold text-white font-mono">{toPersianDigits(count)}</span>
                    </div>
                  ))
              )}
            </div>
          </div>
        </section>

        <section className="mt-6 relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 shadow-2xl text-white">
          <h2 className="text-2xl font-black text-white">شاخص‌های اجرایی</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            <Metric label="کل رانندگان" value={toPersianDigits(stats.total_drivers)} hint="رانندگان تعریف‌شده برای این مشتری" />
            <Metric label="رانندگان فعال" value={toPersianDigits(stats.active_drivers)} hint="رانندگانی که آماده پردازش هستند" />
            <Metric label="کل jobها" value={toPersianDigits(stats.total_jobs)} hint="مجموع ماموریت‌های ثبت‌شده" />
          </div>
          {error && <p className="mt-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400">{error}</p>}
        </section>
      </AuthGuard>
    </AppShell>
  );
}

function Metric({ hint, label, value }: { hint: string; label: string; value: string }) {
  return (
    <article className="rounded-3xl bg-slate-950/60 p-5 border border-white/5">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-3xl font-black text-white">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{hint}</p>
    </article>
  );
}
