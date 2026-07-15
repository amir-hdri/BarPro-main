'use client';

import { memo, useCallback, useEffect, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone, toPersianDigits } from '@/lib/format';
import type { JobTimelineResponse, WaybillJob, WaybillJobUpdateRequest, WaybillTaskListResponse } from '@/lib/types';
import { Activity, ListChecks, MoreVertical, Edit2, Trash2, X, Check, AlertCircle } from 'lucide-react';

const JobCard = memo(function JobCard({
  job,
  selectedJobId,
  retryingJobId,
  actionMenuJobId,
  onCardClick,
  onRetry,
  onActionMenuOpen,
  onActionMenuClose,
  onEditModalOpen,
  onDeleteModalOpen,
  isAdmin,
}: {
  job: WaybillJob;
  selectedJobId: string | null;
  retryingJobId: string | null;
  actionMenuJobId: string | null;
  onCardClick: (jobId: string) => void;
  onRetry: (jobId: string) => Promise<void>;
  onActionMenuOpen: (jobId: string, e: React.MouseEvent) => void;
  onActionMenuClose: (e: React.MouseEvent) => void;
  onEditModalOpen: (job: WaybillJob, e: React.MouseEvent) => void;
  onDeleteModalOpen: (jobId: string, e: React.MouseEvent) => void;
  isAdmin: boolean;
}) {
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const jobId = e.currentTarget.dataset.jobId;
    if (jobId) onCardClick(jobId);
  };

  const handleRetryClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const jobId = e.currentTarget.dataset.jobId;
    if (jobId) void onRetry(jobId);
  };

  const handleActionOpen = (e: React.MouseEvent<HTMLButtonElement>) => {
    const jobId = e.currentTarget.dataset.jobId;
    if (jobId) onActionMenuOpen(jobId, e);
  };

  const handleActionClose = (e: React.MouseEvent<HTMLButtonElement>) => {
    onActionMenuClose(e);
  };

  const handleEditOpen = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onEditModalOpen(job, e);
  };

  const handleDeleteOpen = (e: React.MouseEvent<HTMLButtonElement>) => {
    const jobId = e.currentTarget.dataset.jobId;
    if (jobId) onDeleteModalOpen(jobId, e);
  };

  return (
    <div
      data-job-id={job.job_id}
      onClick={handleClick}
      className={[
        'group w-full cursor-pointer rounded-2xl border p-5 text-right transition-all duration-200',
        selectedJobId === job.job_id
          ? 'border-cyan-500/30 bg-slate-950/60 shadow-[0_0_15px_rgba(6,182,212,0.1)]'
          : 'border-white/5 bg-slate-950/30 hover:border-white/10 hover:bg-slate-950/50 hover:shadow-md',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className={['font-black transition-colors', selectedJobId === job.job_id ? 'text-cyan-400' : 'text-white group-hover:text-cyan-400'].join(' ')}>
            {job.driver_name ? `ثبت بارنامه برای ${job.driver_name}` : `عملیات ثبت بارنامه`}
          </p>
          {isAdmin && job.client_name && (
            <p className="text-xs font-bold text-cyan-400 mt-0.5">مشتری: {job.client_name} ({job.client_code})</p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] font-medium text-slate-400">
            <span className="font-mono bg-slate-950/60 border border-white/5 text-slate-300 px-1.5 py-0.5 rounded">شناسه: #{job.job_id.slice(0, 8)}</span>
            <span>•</span>
            <span>ایجاد در {formatDateTime(job.created_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(job.status === 'failed' || job.status === 'needs_review' || job.status === 'waiting_auth' || job.status === 'waiting_retry') && (
            <button
              data-job-id={job.job_id}
              onClick={handleRetryClick}
              disabled={retryingJobId === job.job_id}
              className="rounded-lg bg-cyan-500 px-4 py-3 text-[10px] font-bold text-white shadow-sm transition hover:bg-cyan-600 disabled:opacity-50"
            >
              {retryingJobId === job.job_id ? '...' : 'تلاش مجدد'}
            </button>
          )}

          <div className="relative">
            <button
              data-job-id={job.job_id}
              onClick={handleActionOpen}
              className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-900 hover:bg-slate-800 transition-colors border border-white/5"
            >
              <MoreVertical className="h-4 w-4 text-slate-400" />
            </button>

            {actionMenuJobId === job.job_id && (
              <div className="absolute right-0 top-full mt-1 w-48 max-w-[calc(100vw-2rem)] rounded-2xl border border-white/10 bg-slate-950 p-2 shadow-2xl z-50" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-end px-3 py-1">
                  <button onClick={handleActionClose} className="text-slate-500 hover:text-slate-300">
                    <X className="h-4 w-4" />
                  </button>
                </div>

                <button onClick={handleEditOpen} className="w-full flex items-center gap-3 rounded-xl px-4 py-2.5 text-right text-sm font-medium text-slate-300 hover:bg-white/5 transition-colors">
                  <Edit2 className="h-4 w-4 text-slate-400" />
                  ویرایش
                </button>

                <button data-job-id={job.job_id} onClick={handleDeleteOpen} className="w-full flex items-center gap-3 rounded-xl px-4 py-2.5 text-right text-sm font-medium text-rose-400 hover:bg-rose-500/10 transition-colors">
                  <Trash2 className="h-4 w-4" />
                  حذف
                </button>
              </div>
            )}
          </div>

          <span className={['rounded-xl px-4 py-2 text-xs font-bold shadow-sm', statusTone(job.status)].join(' ')}>
            {statusLabel(job.status)}
          </span>
        </div>
      </div>
      {isAdmin && job.last_error && (
        <div className="mt-3 rounded-xl bg-rose-500/10 p-3 text-[11px] font-medium text-rose-400 border border-rose-500/20">
          <span className="font-bold">علت خطا:</span> {job.last_error}
        </div>
      )}
      <div className="mt-4 flex items-center justify-between text-[11px] font-bold uppercase r text-slate-500">
        <div className="flex items-center gap-2">
          <span>بروزرسانی:</span>
          <span className="text-slate-400">{formatDateTime(job.updated_at)}</span>
        </div>
        <div className="flex items-center gap-2">
          <span>تلاش:</span>
          <span className="text-slate-400">{toPersianDigits(job.attempt_count)} از {toPersianDigits(job.max_retries)}</span>
        </div>
      </div>
    </div>
  );
});

function JobProgressChart({ progress = 10, status = 'pending' }: { progress: number; status: string }) {
  const steps = [
    { label: 'ثبت درخواست اولیه بارنامه', description: 'درخواست در سیستم با موفقیت ثبت شد', minProgress: 10 },
    { label: 'در انتظار پردازش در صف اتوماسیون', description: 'تخصیص سرور و بررسی اطلاعات راننده', minProgress: 15 },
    { label: 'شبیه‌سازی رفتار انسان و حل کپچا', description: 'شروع شبیه‌ساز مرورگر و احراز هویت هوشمند', minProgress: 50 },
    { label: 'تایید نهایی و دریافت اطلاعات بارنامه', description: 'دریافت نسخه چاپی و ثبت نهایی در پورتال', minProgress: 100 },
  ];

  return (
    <div className="mt-10 rounded-[2.5rem] border border-white/5 bg-slate-900/30 backdrop-blur-xl p-8 text-right shadow-2xl relative overflow-hidden" dir="rtl">
      <div className="absolute -left-20 -top-20 h-40 w-40 rounded-full bg-cyan-500/5 blur-[50px] pointer-events-none" />
      
      <h3 className="text-lg font-black text-white mb-6">نمودار پیشرفت عملیات ربات</h3>
      
      {/* Horizontal Bar Chart representation */}
      <div className="mb-8">
        <div className="flex justify-between items-center text-xs font-bold text-slate-400 mb-2">
          <span>درصد پیشرفت: {toPersianDigits(progress.toString())}٪</span>
          <span className={status === 'success' ? 'text-emerald-400' : status === 'failed' ? 'text-rose-400' : 'text-cyan-400'}>
            وضعیت: {statusLabel(status)}
          </span>
        </div>
        <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
          <div 
            className={`h-full rounded-full transition-all duration-500 ${
              status === 'failed' 
                ? 'bg-gradient-to-r from-rose-500 to-rose-400 shadow-[0_0_10px_rgba(239,68,68,0.5)]' 
                : 'bg-gradient-to-r from-cyan-500 to-emerald-400 shadow-[0_0_10px_rgba(6,182,212,0.5)]'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Stepper Details */}
      <div className="relative border-r-2 border-white/10 pr-6 mr-3 space-y-8">
        {steps.map((step, idx) => {
          const isCompleted = progress >= step.minProgress || (status === 'success' && idx === steps.length - 1);
          const isFailed = status === 'failed' && progress < step.minProgress && (idx === 0 || progress >= steps[idx - 1]?.minProgress);
          const isActive = !isCompleted && !isFailed && (idx === 0 || progress >= steps[idx - 1]?.minProgress);

          return (
            <div key={idx} className="relative">
              {/* Stepper Indicator Dot */}
              <span className={`absolute -right-[31px] top-1 flex h-4 w-4 items-center justify-center rounded-full border transition-all duration-300 ${
                isCompleted 
                  ? 'bg-emerald-500 border-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.5)]' 
                  : isFailed 
                  ? 'bg-rose-500 border-rose-400 shadow-[0_0_8px_rgba(239,68,68,0.5)]'
                  : isActive
                  ? 'bg-cyan-500 border-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.5)] animate-pulse'
                  : 'bg-slate-950 border-white/10'
              }`}>
                {isCompleted && <Check className="h-2.5 w-2.5 text-white" />}
                {isFailed && <AlertCircle className="h-2.5 w-2.5 text-white" />}
              </span>

              {/* Stepper Content */}
              <div>
                <h4 className={`text-sm font-bold transition-colors duration-300 ${
                  isCompleted ? 'text-emerald-400' : isFailed ? 'text-rose-400' : isActive ? 'text-cyan-400 font-black' : 'text-slate-500'
                }`}>
                  {step.label}
                </h4>
                <p className="mt-1 text-xs text-slate-400 font-medium">
                  {isFailed ? 'خطا در اجرای این مرحله رخ داده است' : step.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const { isAdmin, role } = useSession();
  const [jobs, setJobs] = useState<WaybillJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [mobileTimelineOpen, setMobileTimelineOpen] = useState(false);
  const [timeline, setTimeline] = useState<JobTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  
  const [actionMenuJobId, setActionMenuJobId] = useState<string | null>(null);
  
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<WaybillJob | null>(null);
  const [editForm, setEditForm] = useState<WaybillJobUpdateRequest>({
    priority: 5,
    max_retries: 3,
    status: '',
    terminal_reason: '',
    business_date: '',
    correlation_id: '',
  });
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    const response = await api.get<WaybillTaskListResponse>('/api/v1/waybill-jobs', { page: '1', page_size: '25' });

    if (!response.success || !response.data) {
      setError(response.error || 'تاریخچه کارها بارگذاری نشد');
      setLoading(false);
      return;
    }

    setJobs(response.data.tasks);
    if (!selectedJobId) {
      setSelectedJobId(response.data.tasks[0]?.job_id || null);
    }
    setError(null);
    setLoading(false);
  }, [selectedJobId]);

  useEffect(() => {
    if (role) {
      loadJobs();
    }
  }, [role, loadJobs]);

  const handleRetry = useCallback(async (jobId: string) => {
    setRetryingJobId(jobId);
    const response = await api.post(`/api/v1/waybill-jobs/${jobId}/retry`, { dispatch_now: true });
    setRetryingJobId(null);
    if (response.success) {
      await loadJobs();
    } else {
      setError(response.error || 'تلاش مجدد ناموفق بود');
    }
  }, [loadJobs]);
  
  const handleActionMenuOpen = useCallback((jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActionMenuJobId(prev => prev === jobId ? null : jobId);
  }, []);
  
  const handleActionMenuClose = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setActionMenuJobId(null);
  }, []);
  
  const handleDeleteModalOpen = useCallback((jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingJobId(jobId);
    setDeleteModalOpen(true);
    setActionMenuJobId(null);
  }, []);
  
  const handleDeleteModalClose = useCallback(() => {
    setDeleteModalOpen(false);
    setDeletingJobId(null);
    setDeleteError(null);
  }, []);
  
  const handleDelete = useCallback(async (jobId: string) => {
    const response = await api.delete(`/api/v1/waybill-jobs/${jobId}`);
    if (response.success) {
      await loadJobs();
      handleDeleteModalClose();
    } else {
      setDeleteError(response.error || 'حذف ناموفق بود');
    }
  }, [loadJobs, handleDeleteModalClose]);
  
  const handleEditModalOpen = useCallback((job: WaybillJob, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingJob(job);
    setEditForm({
      priority: job.priority,
      max_retries: job.max_retries,
      status: job.status,
      terminal_reason: job.terminal_reason || '',
      business_date: job.business_date || '',
      correlation_id: job.correlation_id || '',
    });
    setEditModalOpen(true);
    setActionMenuJobId(null);
  }, []);
  
  const handleEditModalClose = () => {
    setEditModalOpen(false);
    setEditingJob(null);
    setEditError(null);
    setEditSuccess(null);
    setEditForm({
      priority: 5,
      max_retries: 3,
      status: '',
      terminal_reason: '',
      business_date: '',
      correlation_id: '',
    });
  };
  
  async function handleEdit(jobId: string) {
    const payload = { ...editForm };
    if (payload.status === '') delete payload.status;
    const response = await api.patch(`/api/v1/waybill-jobs/${jobId}`, payload);
    if (response.success) {
      setEditSuccess('تغییرات با موفقیت ذخیره شد');
      setTimeout(() => {
        handleEditModalClose();
        void loadJobs();
      }, 1500);
    } else {
      setEditError(response.error || 'ویرایش ناموفق بود');
    }
  }

  const loadTimeline = useCallback(async (jobId: string) => {
    setTimelineLoading(true);
    setTimelineError(null);
    setTimeline(null);
    const response = await api.get<JobTimelineResponse>(`/api/v1/waybill-jobs/${jobId}/timeline`, {
      include_payload: 'true',
      page:' 1',
      page_size: '20',
    });
    if (response.success && response.data) {
      setTimeline(response.data);
    } else {
      setTimelineError(response.error || 'تایم‌لاین بارگذاری نشد');
    }
    setTimelineLoading(false);
  }, []);

  useEffect(() => {
    if (selectedJobId) {
      void loadTimeline(selectedJobId);
    }
  }, [selectedJobId, loadTimeline]);

  const handleCardClick = useCallback((jobId: string) => {
    setSelectedJobId(jobId);
    setMobileTimelineOpen(true);
  }, []);

  return (
    <AuthGuard>
      <AppShell>
        <section className="grid gap-8 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
            <div className="flex items-center justify-between border-b border-white/5 pb-6">
              <div>
                <h1 className="text-2xl font-black text-white">پیگیری عملیات</h1>
                <p className="mt-1 text-sm text-slate-400">مشاهده صف، خطاها و روند پیشرفت هر ماموریت</p>
              </div>
              <span className="rounded-full bg-cyan-500/10 border border-cyan-500/20 px-4 py-1.5 text-xs font-black text-cyan-400 shadow-sm">
                {toPersianDigits(jobs.length)} مورد
              </span>
            </div>

            {loading ? (
              <div className="mt-6 space-y-4">
                {[1, 2, 3, 4].map((item) => (
                  <div key={item} className="h-28 skeleton rounded-2xl" />
                ))}
              </div>
            ) : jobs.length === 0 ? (
              <div className="mt-10 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 bg-slate-950/20 py-16">
                <p className="text-sm font-medium text-slate-400">هنوز ماموریتی برای نمایش وجود ندارد.</p>
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {jobs.map((job) => (
                  <JobCard
                    key={job.job_id}
                    job={job}
                    selectedJobId={selectedJobId}
                    retryingJobId={retryingJobId}
                    actionMenuJobId={actionMenuJobId}
                    onCardClick={handleCardClick}
                    onRetry={handleRetry}
                    onActionMenuOpen={handleActionMenuOpen}
                    onActionMenuClose={handleActionMenuClose}
                    onEditModalOpen={handleEditModalOpen}
                    onDeleteModalOpen={handleDeleteModalOpen}
                    isAdmin={isAdmin}
                  />
                ))}
              </div>
            )}

            {error && (
              <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-sm font-bold text-rose-400 shadow-sm shadow-rose-950/20">
                {error}
              </div>
            )}
          </div>

          <div className="hidden xl:block relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-900/10">
            <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
            
            <div className="relative z-10">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                  <Activity className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-xl font-bold">{isAdmin ? 'تایم‌لاین اجرایی' : 'وضعیت پیشرفت ماموریت'}</h2>
                  <p className="text-xs font-medium text-slate-400">{isAdmin ? 'رهگیری لحظه‌ای گام‌های عملیاتی ربات' : 'گزارش کلی پیشرفت اتوماسیون بارنامه'}</p>
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
              ) : timelineError ? (
                <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-rose-500/20 py-20 text-center">
                  <AlertCircle className="h-12 w-12 text-rose-400" />
                  <p className="mt-4 text-sm font-medium text-rose-400">{timelineError}</p>
                  <button onClick={() => selectedJobId && void loadTimeline(selectedJobId)} className="mt-4 rounded-xl bg-cyan-500 px-6 py-3 text-xs font-bold text-white hover:bg-cyan-600 transition">
                    تلاش مجدد
                  </button>
                </div>
              ) : !isAdmin ? (
                <JobProgressChart 
                  progress={timeline?.progress_percent || 10} 
                  status={jobs.find(j => j.job_id === selectedJobId)?.status || 'pending'} 
                />
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
                          <h4 className="text-sm font-bold text-slate-200">{entry.title || entry.event_type}</h4>
                        </div>
                        <time className="text-[10px] font-bold  text-slate-500">{formatDateTime(entry.created_at)}</time>
                      </div>
                      <p className="mt-3 text-sm leading-relaxed text-slate-400">{entry.message}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div
            className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-300 xl:hidden ${
              mobileTimelineOpen && selectedJobId ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
            }`}
            onClick={() => setMobileTimelineOpen(false)}
          />

          <div
            className={`fixed bottom-0 left-0 right-0 z-50 max-h-[85vh] rounded-t-[2rem] border-t border-white/10 bg-slate-950 p-6 sm:p-8 shadow-2xl transition-transform duration-300 ease-out xl:hidden overflow-y-auto text-right ${
              mobileTimelineOpen && selectedJobId ? 'translate-y-0' : 'translate-y-full'
            }`}
          >
            <div className="flex justify-center mb-4">
              <div className="w-12 h-1.5 rounded-full bg-white/10" />
            </div>

            <div className="flex items-center justify-between border-b border-white/5 pb-4 mb-6">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                  <Activity className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">{isAdmin ? 'تایم‌لاین اجرایی' : 'وضعیت پیشرفت ماموریت'}</h2>
                  <p className="text-xs font-medium text-slate-400">{isAdmin ? 'رهگیری لحظه‌ای گام‌های عملیاتی ربات' : 'گزارش کلی پیشرفت اتوماسیون بارنامه'}</p>
                </div>
              </div>
              <button
                onClick={() => setMobileTimelineOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 border border-white/5 text-slate-400 hover:text-white transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {timelineLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((item) => (
                  <div key={item} className="h-24 animate-pulse rounded-3xl bg-white/5" />
                ))}
              </div>
            ) : timelineError ? (
              <div className="flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-rose-500/20 py-20 text-center">
                <AlertCircle className="h-12 w-12 text-rose-400" />
                <p className="mt-4 text-sm font-medium text-rose-400">{timelineError}</p>
                <button onClick={() => selectedJobId && void loadTimeline(selectedJobId)} className="mt-4 rounded-xl bg-cyan-500 px-6 py-3 text-xs font-bold text-white hover:bg-cyan-600 transition">
                  تلاش مجدد
                </button>
              </div>
            ) : !isAdmin ? (
              <div className="pb-8">
                <JobProgressChart 
                  progress={timeline?.progress_percent || 10} 
                  status={jobs.find(j => j.job_id === selectedJobId)?.status || 'pending'} 
                />
              </div>
            ) : !timeline || timeline.entries.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-white/5 py-20 text-center">
                <p className="text-sm font-medium text-slate-400">هنوز رویدادی برای این ماموریت ثبت نشده است.</p>
              </div>
            ) : (
              <div className="space-y-4 pb-8">
                {timeline.entries.map((entry) => (
                  <article key={entry.entry_id} className="group relative rounded-3xl border border-white/10 bg-white/5 p-6 transition-all hover:bg-white/10 text-right">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`h-2 w-2 rounded-full ${entry.status === 'success' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.5)]'}`}></div>
                        <h4 className="text-sm font-bold text-slate-200">{entry.title || entry.event_type}</h4>
                      </div>
                      <time className="text-[10px] font-bold text-slate-500">{formatDateTime(entry.created_at)}</time>
                    </div>
                    <p className="mt-3 text-sm leading-relaxed text-slate-400">{entry.message}</p>
                  </article>
                ))}
              </div>
            )}
          </div>

          {deleteModalOpen && deletingJobId && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm overflow-y-auto p-4" role="dialog" aria-modal="true" aria-label="تایید حذف ماموریت">
              <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-2xl text-white my-auto" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400 border border-rose-500/20">
                      <AlertCircle className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-white">تایید حذف ماموریت</h3>
                      <p className="mt-1 text-sm text-slate-400">آیا از حذف ماموریت #{deletingJobId} مطمئن هستید؟</p>
                    </div>
                  </div>
                  <button onClick={handleDeleteModalClose} className="text-slate-400 hover:text-slate-200 transition">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                
                {deleteError && (
                  <div className="mt-4 rounded-xl bg-rose-500/10 border border-rose-500/20 p-3 text-sm font-medium text-rose-400">
                    {deleteError}
                  </div>
                )}
                
                <div className="mt-6 flex justify-end gap-3">
                  <button onClick={handleDeleteModalClose} className="rounded-xl bg-slate-950 border border-white/5 px-6 py-3.5 text-sm font-bold text-slate-300 hover:bg-slate-900 transition-colors">
                    انصراف
                  </button>
                  <button
                    onClick={() => void handleDelete(deletingJobId)}
                    className="rounded-xl bg-rose-500 px-6 py-3.5 text-sm font-bold text-white hover:bg-rose-600 transition-colors"
                  >
                    حذف ماموریت
                  </button>
                </div>
              </div>
            </div>
          )}

          {editModalOpen && editingJob && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm overflow-y-auto p-4" role="dialog" aria-modal="true" aria-label="ویرایش ماموریت">
              <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-2xl text-white my-auto" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between border-b border-white/5 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                      <Edit2 className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-white">ویرایش ماموریت</h3>
                      <p className="mt-1 text-sm text-slate-400">ویرایش مشخصات ماموریت #{editingJob.job_id}</p>
                    </div>
                  </div>
                  <button onClick={handleEditModalClose} className="text-slate-400 hover:text-slate-200 transition">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                
                {editSuccess && (
                  <div className="mt-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3 text-sm font-medium text-emerald-400">
                    <Check className="h-4 w-4 inline ml-1" />
                    {editSuccess}
                  </div>
                )}
                
                {editError && (
                  <div className="mt-4 rounded-xl bg-rose-500/10 border border-rose-500/20 p-3 text-sm font-medium text-rose-400">
                    {editError}
                  </div>
                )}
                
                <div className="mt-6 space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-400">اولویت (0-9)</label>
                    <input
                      type="number"
                      min="0"
                      max="9"
                      value={editForm.priority}
                      onChange={(e) => setEditForm({...editForm, priority: Number(e.target.value)})}
                      className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-2.5 text-sm text-white outline-none focus:border-cyan-500 transition-all"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-slate-400">حداکثر تلاش مجدد (0-10)</label>
                    <input
                      type="number"
                      min="0"
                      max="10"
                      value={editForm.max_retries}
                      onChange={(e) => setEditForm({...editForm, max_retries: Number(e.target.value)})}
                      className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-2.5 text-sm text-white outline-none focus:border-cyan-500 transition-all"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-slate-400">دلیل پایان (اختیاری)</label>
                    <input
                      value={editForm.terminal_reason || ''}
                      onChange={(e) => setEditForm({...editForm, terminal_reason: e.target.value})}
                      className="mt-1 w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-2.5 text-sm text-white outline-none focus:border-cyan-500 transition-all"
                      placeholder="مثال: درخواست کاربر"
                    />
                  </div>
                </div>
                
                <div className="mt-6 flex justify-end gap-3 border-t border-white/5 pt-4">
                  <button onClick={handleEditModalClose} className="rounded-xl bg-slate-950 border border-white/5 px-6 py-3.5 text-sm font-bold text-slate-300 hover:bg-slate-900 transition-colors">
                    انصراف
                  </button>
                  <button
                    onClick={() => void handleEdit(editingJob.job_id)}
                    className="rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-3.5 text-sm font-bold transition-all shadow-lg"
                  >
                    ذخیره تغییرات
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      </AppShell>
    </AuthGuard>
  );
}
