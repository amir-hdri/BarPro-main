'use client';

import { useEffect, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone, toPersianDigits } from '@/lib/format';
import type { JobTimelineResponse, WaybillJob, WaybillJobUpdateRequest, WaybillTaskListResponse } from '@/lib/types';
import { ClockIcon, Activity, ListChecks, MoreVertical, Edit2, Trash2, RefreshCw, X, Check, AlertCircle } from 'lucide-react';

export default function HistoryPage() {
  const { client } = useSession();
  const [jobs, setJobs] = useState<WaybillJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<JobTimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  
  // Action menu states
  const [actionMenuJobId, setActionMenuJobId] = useState<string | null>(null);
  
  // Delete modal states
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  
  // Edit modal states
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
    if (!selectedJobId) {
      setSelectedJobId(response.data.tasks[0]?.job_id || null);
    }
    setError(null);
    setLoading(false);
  }

  useEffect(() => {
    loadJobs();
  }, [client?.role]);

  async function handleRetry(jobId: string) {
    setRetryingJobId(jobId);
    const response = await api.post(`/api/v1/waybill-jobs/${jobId}/retry`, { dispatch_now: true });
    setRetryingJobId(null);
    if (response.success) {
      await loadJobs();
    } else {
      alert(response.error || 'تلاش مجدد ناموفق بود');
    }
  }
  
  // Open action menu
  const handleActionMenuOpen = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActionMenuJobId(actionMenuJobId === jobId ? null : jobId);
  };
  
  // Close action menu
  const handleActionMenuClose = (e: React.MouseEvent) => {
    e.stopPropagation();
    setActionMenuJobId(null);
  };
  
  // Open delete modal
  const handleDeleteModalOpen = (jobId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingJobId(jobId);
    setDeleteModalOpen(true);
    setActionMenuJobId(null);
  };
  
  // Close delete modal
  const handleDeleteModalClose = () => {
    setDeleteModalOpen(false);
    setDeletingJobId(null);
    setDeleteError(null);
  };
  
  // Confirm delete
  async function handleDelete(jobId: string) {
    const response = await api.delete(`/api/v1/waybill-jobs/${jobId}`);
    if (response.success) {
      await loadJobs();
      handleDeleteModalClose();
    } else {
      setDeleteError(response.error || 'حذف ناموفق بود');
    }
  }
  
  // Open edit modal
  const handleEditModalOpen = (job: WaybillJob, e: React.MouseEvent) => {
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
  };
  
  // Close edit modal
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
  
  // Confirm edit
  async function handleEdit(jobId: string) {
    const response = await api.patch(`/api/v1/waybill-jobs/${jobId}`, editForm);
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
                  <div
                    key={job.job_id}
                    onClick={() => setSelectedJobId(job.job_id)}
                    className={[
                      'group w-full cursor-pointer rounded-[28px] border p-5 text-right transition-all duration-200',
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
                      <div className="flex items-center gap-2">
                        {(job.status === 'failed' || job.status === 'needs_review' || job.status === 'waiting_auth' || job.status === 'waiting_retry') && (
                          <button
                            onClick={(e) => { e.stopPropagation(); void handleRetry(job.job_id); }}
                            disabled={retryingJobId === job.job_id}
                            className="rounded-lg bg-cyan-500 px-3 py-1.5 text-[10px] font-bold text-white shadow-sm transition hover:bg-cyan-600 disabled:opacity-50"
                          >
                            {retryingJobId === job.job_id ? '...' : 'تلاش مجدد'}
                          </button>
                        )}
                        
                        {/* Action menu dropdown */}
                        <div className="relative">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleActionMenuOpen(job.job_id, e); }}
                            className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-100 hover:bg-slate-200 transition-colors"
                          >
                            <MoreVertical className="h-4 w-4 text-slate-600" />
                          </button>
                          
                          {actionMenuJobId === job.job_id && (
                            <div className="absolute right-0 top-full mt-1 w-48 rounded-2xl border border-slate-200 bg-white p-2 shadow-lg z-50" onClick={(e) => e.stopPropagation()}>
                              <div className="flex items-center justify-end px-3 py-2">
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleActionMenuClose(e); }}
                                  className="text-slate-400 hover:text-slate-600"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              </div>
                              
                              <button
                                onClick={(e) => { e.stopPropagation(); handleEditModalOpen(job, e); }}
                                className="w-full flex items-center gap-3 rounded-xl px-4 py-2.5 text-right text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                              >
                                <Edit2 className="h-4 w-4 text-slate-500" />
                                ویرایش
                              </button>
                              
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteModalOpen(job.job_id, e); }}
                                className="w-full flex items-center gap-3 rounded-xl px-4 py-2.5 text-right text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors"
                              >
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
                    {job.last_error && (
                      <div className="mt-3 rounded-xl bg-rose-50/50 p-3 text-[11px] font-medium text-rose-600 border border-rose-100/50">
                        <span className="font-bold">علت خطا:</span> {job.last_error}
                      </div>
                    )}
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
                  </div>
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
                          <h4 className="text-sm font-bold text-slate-200">{entry.title || entry.event_type}</h4>
                        </div>
                        <time className="text-[10px] font-bold tracking-widest text-slate-500">{formatDateTime(entry.created_at)}</time>
                      </div>
                      <p className="mt-3 text-sm leading-relaxed text-slate-400">{entry.message}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Delete Confirmation Modal */}
          {deleteModalOpen && deletingJobId && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
              <div className="w-full max-w-md rounded-[40px] border border-slate-200 bg-white p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/10 text-rose-500 ring-1 ring-rose-500/20">
                      <AlertCircle className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-slate-900">تایید حذف ماموریت</h3>
                      <p className="mt-1 text-sm text-slate-500">آیا از حذف ماموریت #{deletingJobId} مطمئن هستید؟</p>
                    </div>
                  </div>
                  <button onClick={handleDeleteModalClose} className="text-slate-400 hover:text-slate-600">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                
                {deleteError && (
                  <div className="mt-4 rounded-xl bg-rose-50 p-3 text-sm font-medium text-rose-600">
                    {deleteError}
                  </div>
                )}
                
                <div className="mt-6 flex justify-end gap-3">
                  <button onClick={handleDeleteModalClose} className="rounded-xl bg-slate-100 px-6 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-200 transition-colors">
                    انصراف
                  </button>
                  <button
                    onClick={() => void handleDelete(deletingJobId)}
                    className="rounded-xl bg-rose-500 px-6 py-2.5 text-sm font-bold text-white hover:bg-rose-600 transition-colors"
                  >
                    حذف ماموریت
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Edit Job Modal */}
          {editModalOpen && editingJob && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
              <div className="w-full max-w-md rounded-[40px] border border-slate-200 bg-white p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-500 ring-1 ring-cyan-500/20">
                      <Edit2 className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-slate-900">ویرایش ماموریت</h3>
                      <p className="mt-1 text-sm text-slate-500">ویرایش مشخصات ماموریت #{editingJob.job_id}</p>
                    </div>
                  </div>
                  <button onClick={handleEditModalClose} className="text-slate-400 hover:text-slate-600">
                    <X className="h-5 w-5" />
                  </button>
                </div>
                
                {editSuccess && (
                  <div className="mt-4 rounded-xl bg-emerald-50 p-3 text-sm font-medium text-emerald-600">
                    <Check className="h-4 w-4 inline ml-1" />
                    {editSuccess}
                  </div>
                )}
                
                {editError && (
                  <div className="mt-4 rounded-xl bg-rose-50 p-3 text-sm font-medium text-rose-600">
                    {editError}
                  </div>
                )}
                
                <div className="mt-6 space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700">اولویت (0-9)</label>
                    <input
                      type="number"
                      min="0"
                      max="9"
                      value={editForm.priority}
                      onChange={(e) => setEditForm({...editForm, priority: Number(e.target.value)})}
                      className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm transition-colors focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 outline-none"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-slate-700">حداکثر تلاش مجدد (0-10)</label>
                    <input
                      type="number"
                      min="0"
                      max="10"
                      value={editForm.max_retries}
                      onChange={(e) => setEditForm({...editForm, max_retries: Number(e.target.value)})}
                      className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm transition-colors focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 outline-none"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-slate-700">دلیل پایان (اختیاری)</label>
                    <input
                      value={editForm.terminal_reason || ''}
                      onChange={(e) => setEditForm({...editForm, terminal_reason: e.target.value})}
                      className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm transition-colors focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 outline-none"
                      placeholder="مثال: درخواست کاربر"
                    />
                  </div>
                </div>
                
                <div className="mt-6 flex justify-end gap-3">
                  <button onClick={handleEditModalClose} className="rounded-xl bg-slate-100 px-6 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-200 transition-colors">
                    انصراف
                  </button>
                  <button
                    onClick={() => void handleEdit(editingJob.job_id)}
                    className="rounded-xl bg-cyan-500 px-6 py-2.5 text-sm font-bold text-white hover:bg-cyan-600 transition-colors"
                  >
                    ذخیره تغییرات
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>
      </AuthGuard>
    </AppShell>
  );
}
