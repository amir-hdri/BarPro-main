'use client';

import { useEffect, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone, toPersianDigits } from '@/lib/format';
import type { JobTimelineResponse, WaybillJob, WaybillTaskListResponse } from '@/lib/types';

export default function HistoryPage() {
  const { client } = useSession();
  const [jobs, setJobs] = useState<WaybillJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<JobTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadJobs() {
      if (client?.role === 'master_admin') { setLoading?.(false); return; }
      setLoading(true);
      const response = await api.get<WaybillTaskListResponse>('/api/v1/waybill-jobs', { page: '1', page_size: '25' });

      if (!response.success || !response.data) {
        setError(response.error || 'تاریخچه کارها بارگذاری نشد');
        setLoading(false);
        return;
      }

      setJobs(response.data.tasks);
      setSelectedJobId(response.data.tasks[0]?.job_id || null);
      setError(null);
      setLoading(false);
    }

    loadJobs();
  }, [client?.role]);

  useEffect(() => {
    async function loadTimeline(jobId: string) {
      setTimelineLoading(true);
      const response = await api.get<JobTimelineResponse>(`/api/v1/waybill-jobs/${jobId}/timeline`, {
        include_payload: 'true',
        page:' 1',
        page_size: '20',
      });
      setTimelineLoading(false);
      if (response.success && response.data) {
        setTimeline(response.data);
      }
    }

    if (selectedJobId) {
      void loadTimeline(selectedJobId);
    }
  }, [selectedJobId]);

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[32px] border border-white/20 bg-white/75 p-6 shadow-lg shadow-slate-900/5 backdrop-blur">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold text-slate-950">پیگیری کارها</h1>
                <p className="mt-1 text-sm text-slate-500">صف فعلی، خطاها و وضعیت اجرای هر ماموریت</p>
              </div>
              <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">{toPersianDigits(jobs.length)} مورد</span>
            </div>

            {loading ? (
              <div className="mt-6 space-y-3">{[1, 2, 3, 4].map((item) => <div key={item} className="h-24 animate-pulse rounded-3xl bg-slate-100" />)}</div>
            ) : jobs.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-slate-200 px-5 py-8 text-sm text-slate-500">هنوز ماموریتی برای نمایش وجود ندارد.</div>
            ) : (
              <div className="mt-6 space-y-3">
                {jobs.map((job) => (
                  <button
                    key={job.job_id}
                    type="button"
                    onClick={() => setSelectedJobId(job.job_id)}
                    className={[
                      'w-full rounded-3xl border px-5 py-4 text-right transition',
                      selectedJobId === job.job_id ? 'border-cyan-300 bg-cyan-50' : 'border-slate-100 bg-slate-50 hover:border-slate-200',
                    ].join(' ')}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-900">#{job.job_id}</p>
                        <p className="mt-1 text-sm text-slate-500">شروع: {formatDateTime(job.started_at || job.created_at)}</p>
                      </div>
                      <span className={['rounded-full px-3 py-1 text-xs font-semibold', statusTone(job.status)].join(' ')}>{statusLabel(job.status)}</span>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-slate-600 md:grid-cols-2">
                      <span>آخرین بروزرسانی: {formatDateTime(job.updated_at)}</span>
                      <span>تعداد تلاش: {toPersianDigits(job.attempt_count)} از {toPersianDigits(job.max_retries)}</span>
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                      <span>دسته خطا: {job.error_category ? statusLabel(job.error_category) : '-'}</span>
                      <span>کد علت نهایی: {job.terminal_reason || '-'}</span>
                    </div>
                    {job.last_error && <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{job.last_error}</p>}
                  </button>
                ))}
              </div>
            )}

            {error && <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>}
          </div>

          <div className="rounded-[32px] border border-white/20 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/20">
            <h2 className="text-2xl font-semibold">تایم‌لاین اجرایی</h2>
            <p className="mt-2 text-sm text-slate-300">برای هر job، رویدادها و لاگ‌های یکپارچه نشان داده می‌شود.</p>

            {!selectedJobId ? (
              <div className="mt-6 rounded-3xl border border-white/10 px-5 py-8 text-sm text-slate-300">یکی از کارها را از ستون سمت راست انتخاب کنید.</div>
            ) : timelineLoading ? (
              <div className="mt-6 space-y-3">{[1, 2, 3].map((item) => <div key={item} className="h-20 animate-pulse rounded-3xl bg-white/10" />)}</div>
            ) : !timeline || timeline.entries.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-white/10 px-5 py-8 text-sm text-slate-300">هنوز رویدادی برای این کار ثبت نشده است.</div>
            ) : (
              <div className="mt-6 space-y-3">
                {timeline.entries.map((entry) => (
                  <article key={entry.entry_id} className="rounded-3xl border border-white/10 bg-white/5 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-white">{entry.title}</p>
                        <p className="mt-1 text-sm text-slate-300">{formatDateTime(entry.created_at)}</p>
                      </div>
                      {entry.status && <span className={['rounded-full px-3 py-1 text-xs font-semibold', statusTone(entry.status)].join(' ')}>{statusLabel(entry.status)}</span>}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-400">
                      <span>فاز: {entry.phase || '-'}</span>
                      <span>منبع: {entry.source}</span>
                      <span>نوع رویداد: {entry.event_type}</span>
                    </div>
                    {entry.message && <p className="mt-3 text-sm leading-6 text-slate-200">{entry.message}</p>}
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      </AuthGuard>
    </AppShell>
  );
}
