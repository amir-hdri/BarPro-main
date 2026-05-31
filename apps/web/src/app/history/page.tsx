'use client';

import { useEffect, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone, toPersianDigits } from '@/lib/format';
import type { JobTimelineResponse, WaybillJob, WaybillTaskListResponse } from '@/lib/types';
import { ClockIcon, Activity, ListChecks } from 'lucide-react';

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
        <section className="grid gap-8 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[40px] border border-slate-200 bg-white p-8 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-50 pb-6">
              <div>
                <h1 className="text-2xl font-black text-slate-900">پیگیری عملیات</h1>
                <p className="mt-1 text-sm text-slate-500">مشاهده صف، خطاها و روند پیشرفت هر ماموریت</p>
              </div>
              <span className="rounded-full bg-slate-900 px-4 py-1.5 text-xs font-bold text-white shadow-lg shadow-slate-900/10">
                {toPersianDigits(jobs.length)} مورد
              </span>
            </div>

            {loading ? (
              <div className="mt-6 space-y-4">
                {[1, 2, 3, 4].map((item) => (
                  <div key={item} className="h-28 animate-pulse rounded-[28px] bg-slate-50" />
                ))}
              </div>
            ) : jobs.length === 0 ? (
              <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border-2 border-dashed border-slate-100 py-16">
                <p className="text-sm font-medium text-slate-400">هنوز ماموریتی برای نمایش وجود ندارد.</p>
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {jobs.map((job) => (
                  <button
                    key={job.job_id}
                    type="button"
                    onClick={() => setSelectedJobId(job.job_id)}
                    className={[
                      'group w-full rounded-[28px] border p-5 text-right transition-all duration-200',
                      selectedJobId === job.job_id 
                        ? 'border-cyan-200 bg-cyan-50 shadow-md' 
                        : 'border-slate-50 bg-slate-50/50 hover:border-slate-200 hover:bg-white hover:shadow-sm',
                    ].join(' ')}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-black text-slate-900 group-hover:text-cyan-600">#{job.job_id}</p>
                        <p className="mt-0.5 text-xs font-medium text-slate-400">ایجاد در {formatDateTime(job.created_at)}</p>
                      </div>
                      <span className={['rounded-xl px-4 py-2 text-xs font-bold shadow-sm', statusTone(job.status)].join(' ')}>
                        {statusLabel(job.status)}
                      </span>
                    </div>
                    <div className="mt-4 flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      <div className="flex items-center gap-2">
                        <span>بروزرسانی:</span>
                        <span className="text-slate-600">{formatDateTime(job.updated_at)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span>تلاش:</span>
                        <span className="text-slate-600">{toPersianDigits(job.attempt_count)} از {toPersianDigits(job.max_retries)}</span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {error && (
              <div className="mt-6 rounded-2xl bg-rose-50 p-4 text-sm font-bold text-rose-700 shadow-sm shadow-rose-100">
                {error}
              </div>
            )}
          </div>

          <div className="relative overflow-hidden rounded-[40px] border border-slate-200 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-900/10">
            <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
            
            <div className="relative z-10">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                  <Activity className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-xl font-bold">تایم‌لاین اجرایی</h2>
                  <p className="text-xs font-medium text-slate-400">رهگیری لحظه‌ای گام‌های عملیاتی ربات</p>
                </div>
              </div>

              {!selectedJobId ? (
                <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-white/5 py-20 text-center">
                  <ListChecks className="h-12 w-12 text-slate-600" />
                  <p className="mt-4 text-sm font-medium text-slate-400">برای مشاهده جزئیات، یکی از ماموریت‌ها را انتخاب کنید.</p>
                </div>
              ) : timelineLoading ? (
                <div className="mt-10 space-y-4">
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="h-24 animate-pulse rounded-3xl bg-white/5" />
                  ))}
                </div>
              ) : !timeline || timeline.entries.length === 0 ? (
                <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-white/5 py-20 text-center">
                  <p className="text-sm font-medium text-slate-400">هنوز رویدادی برای این ماموریت ثبت نشده است.</p>
                </div>
              ) : (
                <div className="mt-10 space-y-4">
                  {timeline.entries.map((entry) => (
                    <article key={entry.entry_id} className="group relative rounded-3xl border border-white/10 bg-white/5 p-6 transition-all hover:bg-white/10">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`h-2 w-2 rounded-full ${entry.status === 'success' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.5)]'}`}></div>
                          <h4 className="text-sm font-bold text-slate-200">{entry.step_label || entry.step}</h4>
                        </div>
                        <time className="text-[10px] font-bold tracking-widest text-slate-500">{formatDateTime(entry.timestamp)}</time>
                      </div>
                      <p className="mt-3 text-sm leading-relaxed text-slate-400">{entry.message}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      </AuthGuard>
    </AppShell>
  );
}
