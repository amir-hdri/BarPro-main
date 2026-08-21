'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ErrorState } from '@/components/layout/States';
import { ProgressBar } from '@/components/ProgressBar';
import { useSession } from '@/hooks/useSession';
import { api } from '@/lib/api';
import {
  errorCategoryLabel,
  formatDateTime,
  formatFuelTrackingCode,
  parseQuotaData,
  parseWaybillPayload,
  statusLabel,
  statusTone,
  toPersianDigits,
  toPersianDigitsPreserveZero,
  trackingCodeFromResult,
  confirmedTrackingCode,
} from '@/lib/format';
import type {
  FuelInquiryItem,
  FuelInquiryListResponse,
  JobTimelineResponse,
  WaybillJob,
  WaybillJobUpdateRequest,
  WaybillTaskListResponse,
} from '@/lib/types';
import {
  Activity,
  AlertCircle,
  Check,
  ChevronRight,
  Copy,
  CreditCard,
  Edit2,
  Eye,
  FileText,
  Filter,
  Fuel,
  Gauge,
  ListChecks,
  MapPin,
  MoreVertical,
  Package,
  RotateCcw,
  Search,
  Trash2,
  Truck,
  X,
} from 'lucide-react';

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
  const payload = parseWaybillPayload(job.payload_json);

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
              className="rounded-lg bg-cyan-500 px-3.5 py-2 text-[11px] font-bold text-slate-950 shadow-sm transition hover:bg-cyan-400 disabled:opacity-50"
            >
              {retryingJobId === job.job_id ? '...' : 'تلاش مجدد'}
            </button>
          )}

          <div className="relative">
            <button
              data-job-id={job.job_id}
              onClick={handleActionOpen}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 hover:bg-slate-800 transition-colors border border-white/5 text-slate-300"
              aria-label="عملیات بیشتر"
            >
              <MoreVertical className="h-4 w-4" />
            </button>

            {actionMenuJobId === job.job_id && (
              <div className="absolute left-0 top-full mt-1 w-44 rounded-2xl border border-white/10 bg-slate-950 p-2 shadow-2xl z-50 text-right" onClick={(e) => e.stopPropagation()}>
                 <div className="flex items-center justify-between px-3 py-1 border-b border-white/5 mb-1">
                   <span className="text-[10px] font-bold text-slate-400">عملیات</span>
                   <button onClick={handleActionClose} className="p-2 text-slate-500 hover:text-slate-300 rounded-lg hover:bg-white/5 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بستن">
                     <X className="h-4 w-4" />
                   </button>
                 </div>

                 <button onClick={handleEditOpen} className="w-full flex items-center gap-2.5 rounded-xl px-4 py-3 text-right text-xs font-bold text-slate-300 hover:bg-white/5 transition-colors touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">
                   <Edit2 className="h-4 w-4 text-cyan-400" />
                   ویرایش مشخصات
                 </button>

                 <button data-job-id={job.job_id} onClick={handleDeleteOpen} className="w-full flex items-center gap-2.5 rounded-xl px-4 py-3 text-right text-xs font-bold text-rose-400 hover:bg-rose-500/10 transition-colors touch-target focus:outline-none focus:ring-2 focus:ring-rose-500">
                   <Trash2 className="h-4 w-4" />
                   حذف ماموریت
                 </button>
              </div>
            )}
          </div>

          <span className={['rounded-xl px-3.5 py-1.5 text-xs font-bold shadow-sm', statusTone(job.status)].join(' ')}>
            {statusLabel(job.status)}
          </span>
        </div>
      </div>

      {/* Waybill Payload Metadata Badges */}
      {(payload.plateNumber || payload.originCity || payload.destinationCity || payload.cargoName) && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
          {payload.plateNumber && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-slate-900 border border-white/10 px-2.5 py-1 text-slate-200 font-bold">
              <Truck className="h-3.5 w-3.5 text-cyan-400" />
              پلاک: {toPersianDigitsPreserveZero(payload.plateNumber)}
            </span>
          )}
          {(payload.originCity || payload.destinationCity) && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-slate-900 border border-white/10 px-2.5 py-1 text-slate-300">
              <MapPin className="h-3.5 w-3.5 text-cyan-400" />
              {payload.originCity || '—'} ← {payload.destinationCity || '—'}
            </span>
          )}
          {payload.cargoName && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-slate-900 border border-white/10 px-2.5 py-1 text-slate-300">
              <Package className="h-3.5 w-3.5 text-cyan-400" />
              {payload.cargoName} {payload.cargoWeight ? `(${toPersianDigitsPreserveZero(payload.cargoWeight)} تن)` : ''}
            </span>
          )}
        </div>
      )}

      {(() => {
        const provisionalCode = trackingCodeFromResult(job.result_json);
        const tc = confirmedTrackingCode(job.result_json, job.status, job.mutation_status, job.reconciled_at);
        if (tc) {
          return (
            <div className="mt-3 rounded-xl bg-emerald-500/10 p-3 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
              <span className="font-bold">کد رهگیری UTCMS:</span> {tc}
            </div>
          );
        }
        if (provisionalCode) {
          return (
            <div className="mt-3 rounded-xl bg-amber-500/10 p-3 text-[11px] font-medium text-amber-400 border border-amber-500/20">
              در انتظار تطبیق با سوابق UTCMS
            </div>
          );
        }
        return null;
      })()}

      {isAdmin && job.error_category && (
        <div className="mt-3 rounded-xl bg-amber-500/10 p-3 text-[11px] font-medium text-amber-400 border border-amber-500/20">
          <span className="font-bold">دسته خطا:</span> {errorCategoryLabel(job.error_category)}
        </div>
      )}
      {isAdmin && job.last_error && (
        <div className="mt-3 rounded-xl bg-rose-500/10 p-3 text-[11px] font-medium text-rose-400 border border-rose-500/20">
          <span className="font-bold">علت خطا:</span> {job.last_error}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between text-[11px] font-bold uppercase text-slate-500">
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
      
      <div className="mb-8">
        <div className="flex justify-between items-center text-xs font-bold text-slate-400 mb-2">
          <span>درصد پیشرفت: {toPersianDigits(progress.toString())}٪</span>
          <span className={status === 'success' ? 'text-emerald-400' : status === 'failed' ? 'text-rose-400' : 'text-cyan-400'}>
            وضعیت: {statusLabel(status)}
          </span>
        </div>
        <ProgressBar
          value={progress}
          tone={status === 'failed' ? 'rose' : status === 'success' ? 'emerald' : 'cyan'}
          label="پیشرفت عملیات ربات"
        />
      </div>

      <div className="relative border-r-2 border-white/10 pr-6 mr-3 space-y-8">
        {steps.map((step, idx) => {
          const isCompleted = progress >= step.minProgress || (status === 'success' && idx === steps.length - 1);
          const isFailed = status === 'failed' && progress < step.minProgress && (idx === 0 || progress >= steps[idx - 1]?.minProgress);
          const isActive = !isCompleted && !isFailed && (idx === 0 || progress >= steps[idx - 1]?.minProgress);

          return (
            <div key={idx} className="relative">
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

  // Category Tab state: 'waybills' or 'fuel'
  const [activeCategory, setActiveCategory] = useState<'waybills' | 'fuel'>('waybills');

  // Multi-Filter & Pagination toolbar state
  const [currentPage, setCurrentPage] = useState(1);
  const [driverNameFilter, setDriverNameFilter] = useState('');
  const [plateFilter, setPlateFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFromFilter, setDateFromFilter] = useState('');
  const [dateToFilter, setDateToFilter] = useState('');

  // Waybill Jobs state
  const [jobs, setJobs] = useState<WaybillJob[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<JobTimelineResponse | null>(null);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [actionMenuJobId, setActionMenuJobId] = useState<string | null>(null);

  const selectedJob = jobs.find((j) => j.job_id === selectedJobId) || null;
  const selectedJobPayload = selectedJob ? parseWaybillPayload(selectedJob.payload_json) : null;

  // Fuel Inquiries state
  const [fuelInquiries, setFuelInquiries] = useState<FuelInquiryItem[]>([]);
  const [fuelTotal, setFuelTotal] = useState(0);
  const [loadingFuel, setLoadingFuel] = useState(true);
  const [fuelError, setFuelError] = useState<string | null>(null);
  const [retryingFuelId, setRetryingFuelId] = useState<number | null>(null);
  const [screenshotModalUrl, setScreenshotModalUrl] = useState<string | null>(null);
  const [selectedFuelInquiry, setSelectedFuelInquiry] = useState<FuelInquiryItem | null>(null);

  // Edit Modals state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<WaybillJob | null>(null);
  const [editForm, setEditForm] = useState<WaybillJobUpdateRequest>({
    priority: 5,
    max_retries: 3,
    terminal_reason: '',
    business_date: '',
    correlation_id: '',
  });
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);

  // Load Waybill Jobs
  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    setJobsError(null);
    const params: Record<string, string> = { page: String(currentPage), page_size: '20' };
    if (statusFilter) params.status = statusFilter;
    if (driverNameFilter.trim()) params.driver_name = driverNameFilter.trim();
    if (plateFilter.trim()) params.plate_number = plateFilter.trim();
    if (dateFromFilter) params.date_from = dateFromFilter;
    if (dateToFilter) params.date_to = dateToFilter;

    const response = await api.get<WaybillTaskListResponse>('/api/v1/waybill-jobs', params);

    if (!response.success || !response.data) {
      setJobsError(response.error || 'تاریخچه کارهای بارنامه بارگذاری نشد.');
      setJobs([]);
      setJobsTotal(0);
      setLoadingJobs(false);
      return;
    }

    const jobList = Array.isArray(response.data.tasks) ? response.data.tasks : [];
    setJobs(jobList);
    setJobsTotal(typeof response.data.total === 'number' ? response.data.total : jobList.length);
    const firstJobId = jobList[0]?.job_id || null;
    setSelectedJobId((prev) => prev || firstJobId);
    setLoadingJobs(false);
  }, [currentPage, statusFilter, driverNameFilter, plateFilter, dateFromFilter, dateToFilter]);

  // Load Fuel Inquiries
  const loadFuelInquiries = useCallback(async () => {
    setLoadingFuel(true);
    setFuelError(null);
    const params: Record<string, string> = { page: String(currentPage), page_size: '20' };
    if (statusFilter) params.status = statusFilter;
    if (driverNameFilter.trim()) params.driver_name = driverNameFilter.trim();
    if (plateFilter.trim()) params.plate_number = plateFilter.trim();
    if (dateFromFilter) params.date_from = dateFromFilter;
    if (dateToFilter) params.date_to = dateToFilter;

    const response = await api.get<FuelInquiryListResponse>('/api/v1/fuel-inquiries', params);

    if (!response.success || !response.data) {
      setFuelError(response.error || 'تاریخچه استعلام‌های سوخت بارگذاری نشد.');
      setFuelInquiries([]);
      setFuelTotal(0);
      setLoadingFuel(false);
      return;
    }

    const fuelList = Array.isArray(response.data.items) ? response.data.items : [];
    setFuelInquiries(fuelList);
    setFuelTotal(typeof response.data.total === 'number' ? response.data.total : fuelList.length);
    setLoadingFuel(false);
  }, [currentPage, statusFilter, driverNameFilter, plateFilter, dateFromFilter, dateToFilter]);

  useEffect(() => {
    if (role) {
      if (activeCategory === 'waybills') {
        loadJobs();
      } else {
        loadFuelInquiries();
      }
    }
  }, [role, activeCategory, loadJobs, loadFuelInquiries]);

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    if (activeCategory === 'waybills') {
      void loadJobs();
    } else {
      void loadFuelInquiries();
    }
  };

  const handleResetFilters = () => {
    setDriverNameFilter('');
    setPlateFilter('');
    setStatusFilter('');
    setDateFromFilter('');
    setDateToFilter('');
    setTimeout(() => {
      if (activeCategory === 'waybills') void loadJobs();
      else void loadFuelInquiries();
    }, 50);
  };

  const handleRetryJob = useCallback(async (jobId: string) => {
    setRetryingJobId(jobId);
    const response = await api.post(`/api/v1/waybill-jobs/${jobId}/retry`, { dispatch_now: true });
    setRetryingJobId(null);
    if (response.success) {
      toast.success('درخواست اجرای مجدد ثبت شد.');
      await loadJobs();
    } else {
      toast.error(response.error || 'تلاش مجدد ناموفق بود');
    }
  }, [loadJobs]);

  const handleRetryFuelInquiry = useCallback(async (inquiry: FuelInquiryItem) => {
    setRetryingFuelId(inquiry.id);
    const response = await api.post('/api/v1/fuel-inquiries', {
      driver_id: inquiry.driver_id,
      year: inquiry.year || undefined,
      month: inquiry.month || undefined,
      force_retry: true,
      plate_number: inquiry.plate_number || undefined,
    });
    setRetryingFuelId(null);
    if (response.success) {
      toast.success('استعلام جدید سوخت ثبت شد و در حال پردازش است.');
      await loadFuelInquiries();
    } else {
      toast.error(response.error || 'ثبت استعلام جدید ناموفق بود');
    }
  }, [loadFuelInquiries]);

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

  const handleDeleteJob = useCallback(async (jobId: string) => {
    const response = await api.delete(`/api/v1/waybill-jobs/${jobId}`);
    if (response.success) {
      toast.success('ماموریت حذف شد');
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
  };

  async function handleEditJob(jobId: string) {
    const payload = { ...editForm };
    if (!payload.terminal_reason) delete payload.terminal_reason;
    if (!payload.business_date) delete payload.business_date;
    if (!payload.correlation_id) delete payload.correlation_id;
    const response = await api.patch(`/api/v1/waybill-jobs/${jobId}`, payload);
    if (response.success) {
      setEditSuccess('تغییرات ماموریت با موفقیت ذخیره شد');
      setTimeout(() => {
        handleEditModalClose();
        void loadJobs();
      }, 1200);
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
      page: '1',
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
    if (selectedJobId && activeCategory === 'waybills') {
      void loadTimeline(selectedJobId);
    }
  }, [selectedJobId, activeCategory, loadTimeline]);

  const handleCardClick = useCallback((jobId: string) => {
    setSelectedJobId(jobId);
  }, []);

  return (
    <AuthGuard>
      <AppShell>
        <section className="flex flex-col gap-6">

          {/* Header and Category Switcher Tabs */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 rounded-[2rem] border border-white/10 bg-slate-950/70 p-6 shadow-2xl backdrop-blur-xl">
            <div>
              <h1 className="text-2xl font-black text-white">پیگیری و مدیریت عملیات</h1>
              <p className="mt-1 text-xs font-medium text-slate-400">
                تفکیک هوشمند کارهای ثبت بارنامه و استعلام سهمیه سوخت به همراه فیلترهای پیشرفته
              </p>
            </div>

            <div className="flex rounded-2xl bg-slate-900/80 p-1 border border-white/10 shadow-inner">
              <button
                type="button"
                onClick={() => setActiveCategory('waybills')}
                className={`flex items-center gap-2 rounded-xl px-5 py-3 text-xs font-black transition-all ${
                  activeCategory === 'waybills'
                    ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileText className="h-4 w-4" />
                ثبت بارنامه
                <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] text-cyan-400 border border-cyan-500/20">
                  {toPersianDigits(jobsTotal)}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setActiveCategory('fuel')}
                className={`flex items-center gap-2 rounded-xl px-5 py-3 text-xs font-black transition-all ${
                  activeCategory === 'fuel'
                    ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Fuel className="h-4 w-4" />
                استعلام سوخت
                <span className="rounded-full bg-cyan-500/10 px-2 py-0.5 text-[10px] text-cyan-400 border border-cyan-500/20">
                  {toPersianDigits(fuelTotal)}
                </span>
              </button>
            </div>
          </div>

          {/* Advanced Multi-Filter Toolbar */}
          <form
            onSubmit={handleApplyFilters}
            className="rounded-[2rem] border border-white/5 bg-slate-900/40 p-6 shadow-xl backdrop-blur-md text-white"
          >
            <div className="flex items-center gap-2 border-b border-white/5 pb-4 mb-4 text-xs font-bold text-slate-300">
              <Filter className="h-4 w-4 text-cyan-400" />
              <span>فیلترهای جستجو و جستجوی پیشرفته ({activeCategory === 'waybills' ? 'ثبت بارنامه' : 'استعلام سوخت'})</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1.5">نام راننده</label>
                <div className="relative">
                  <input
                    type="text"
                    value={driverNameFilter}
                    onChange={(e) => setDriverNameFilter(e.target.value)}
                    placeholder="مثال: علی رضایی"
                    className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3.5 py-2.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-cyan-400 transition"
                  />
                  {driverNameFilter && (
                    <button
                      type="button"
                      onClick={() => setDriverNameFilter('')}
                      className="absolute left-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1.5">پلاک خودرو</label>
                <div className="relative">
                  <input
                    type="text"
                    value={plateFilter}
                    onChange={(e) => setPlateFilter(e.target.value)}
                    placeholder="مثال: ۱۲ب۳۴۵"
                    className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3.5 py-2.5 text-xs text-white outline-none placeholder:text-slate-500 focus:border-cyan-400 transition"
                  />
                  {plateFilter && (
                    <button
                      type="button"
                      onClick={() => setPlateFilter('')}
                      className="absolute left-2.5 top-2.5 text-slate-500 hover:text-slate-300"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1.5">وضعیت کار</label>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3.5 py-2.5 text-xs text-white outline-none focus:border-cyan-400 transition"
                >
                  <option value="">همه وضعیت‌ها</option>
                  <option value="success" className="bg-slate-950">موفق (Completed)</option>
                  <option value="pending" className="bg-slate-950">در صف (Pending)</option>
                  <option value="in_progress" className="bg-slate-950">در حال اجرا (Running)</option>
                  <option value="failed" className="bg-slate-950">خطا (Failed)</option>
                  <option value="needs_review" className="bg-slate-950">نیازمند بررسی (Needs Review)</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1.5">از تاریخ (YYYY-MM-DD)</label>
                <input
                  type="date"
                  value={dateFromFilter}
                  onChange={(e) => setDateFromFilter(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3.5 py-2.5 text-xs text-white outline-none focus:border-cyan-400 transition"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-slate-300 mb-1.5">تا تاریخ (YYYY-MM-DD)</label>
                <input
                  type="date"
                  value={dateToFilter}
                  onChange={(e) => setDateToFilter(e.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3.5 py-2.5 text-xs text-white outline-none focus:border-cyan-400 transition"
                />
              </div>
            </div>

            <div className="mt-4 flex justify-end gap-3 border-t border-white/5 pt-4">
              <button
                type="button"
                onClick={handleResetFilters}
                className="rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-xs font-bold text-slate-300 hover:bg-slate-900 transition flex items-center gap-1.5"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                پاک کردن فیلترها
              </button>
              <button
                type="submit"
                className="rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-2.5 text-xs font-black shadow-lg transition flex items-center gap-1.5"
              >
                <Search className="h-3.5 w-3.5" />
                اعمال فیلترها
              </button>
            </div>
          </form>

          {/* MAIN CATEGORY TAB CONTENT */}
          {activeCategory === 'waybills' ? (
            /* TAB 1: WAYBILL REGISTRATION TASKS */
            <section className="grid gap-8 xl:grid-cols-[0.9fr_1.1fr]">
              <div className={`relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white ${
                selectedJobId ? 'hidden xl:block' : 'block'
              }`}>
                <div className="flex items-center justify-between border-b border-white/5 pb-6">
                  <div>
                    <h2 className="text-xl font-black text-white">صف ثبت بارنامه</h2>
                    <p className="mt-1 text-xs text-slate-400">مشاهده صف، خطاها و روند پیشرفت هر بارنامه</p>
                  </div>
                  <span className="rounded-full bg-cyan-500/10 border border-cyan-500/20 px-4 py-1.5 text-xs font-black text-cyan-400 shadow-sm">
                    {toPersianDigits(jobsTotal)} مورد
                  </span>
                </div>

                {loadingJobs ? (
                  <div className="mt-6 space-y-4">
                    {[1, 2, 3, 4].map((item) => (
                      <div key={item} className="h-28 skeleton rounded-2xl" />
                    ))}
                  </div>
                ) : jobs.length === 0 ? (
                  <div className="mt-10 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 bg-slate-950/20 py-16">
                    <FileText className="h-10 w-10 text-slate-600 mb-3" />
                    <p className="text-sm font-medium text-slate-400">هیچ ماموریت ثبت بارنامه‌ای با این فیلترها یافت نشد.</p>
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
                        onRetry={handleRetryJob}
                        onActionMenuOpen={handleActionMenuOpen}
                        onActionMenuClose={handleActionMenuClose}
                        onEditModalOpen={handleEditModalOpen}
                        onDeleteModalOpen={handleDeleteModalOpen}
                        isAdmin={isAdmin}
                      />
                    ))}
                  </div>
                )}

                {/* Pagination Controls */}
                {jobsTotal > 20 && (
                  <div className="mt-6 flex items-center justify-between rounded-2xl border border-white/5 bg-slate-950/60 p-4 text-xs">
                    <span className="font-bold text-slate-400">
                      صفحه {toPersianDigits(currentPage)} از {toPersianDigits(Math.ceil(jobsTotal / 20))} ({toPersianDigits(jobsTotal)} مورد)
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={currentPage <= 1 || loadingJobs}
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        className="rounded-xl border border-white/10 bg-slate-900 px-3.5 py-1.5 font-bold text-slate-300 hover:bg-slate-800 disabled:opacity-40 transition"
                      >
                        قبلی
                      </button>
                      <button
                        type="button"
                        disabled={currentPage >= Math.ceil(jobsTotal / 20) || loadingJobs}
                        onClick={() => setCurrentPage((p) => p + 1)}
                        className="rounded-xl border border-white/10 bg-slate-900 px-3.5 py-1.5 font-bold text-slate-300 hover:bg-slate-800 disabled:opacity-40 transition"
                      >
                        بعدی
                      </button>
                    </div>
                  </div>
                )}

                {jobsError && (
                  <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs font-bold text-rose-400 shadow-sm">
                    {jobsError}
                  </div>
                )}
              </div>

              {/* Waybill Timeline & Progress Panel */}
              <div className={`${
                selectedJobId ? 'block' : 'hidden xl:block'
              } relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-950 p-6 sm:p-8 text-white shadow-2xl w-full`}>
                <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>

                <div className="relative z-10 space-y-6">
                  {selectedJobId && (
                    <button
                      type="button"
                      onClick={() => setSelectedJobId(null)}
                      className="xl:hidden flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900 px-4 py-2.5 text-xs font-bold text-slate-300 transition hover:bg-slate-800"
                    >
                      <ChevronRight className="h-4 w-4" />
                      بازگشت به لیست ماموریت‌ها
                    </button>
                  )}

                  {!selectedJob ? (
                    <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border border-white/10 bg-white/5 py-20 text-center">
                      <ListChecks className="h-12 w-12 text-slate-600" />
                      <p className="mt-4 text-sm font-medium text-slate-400">برای مشاهده جزئیات، یکی از ماموریت‌ها را انتخاب کنید.</p>
                    </div>
                  ) : (
                    <>
                      {/* Waybill Selected Job Header & Summary */}
                      <div className="rounded-[2rem] border border-white/10 bg-slate-900/60 p-6 backdrop-blur-xl">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 pb-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded">
                                #{selectedJob.job_id.slice(0, 12)}
                              </span>
                              <span className={['rounded-xl px-3 py-1 text-xs font-bold shadow-sm', statusTone(selectedJob.status)].join(' ')}>
                                {statusLabel(selectedJob.status)}
                              </span>
                            </div>
                            <h3 className="mt-2 text-lg font-black text-white">
                              {selectedJob.driver_name ? `ماموریت بارنامه: ${selectedJob.driver_name}` : 'جزئیات ماموریت بارنامه'}
                            </h3>
                            {isAdmin && selectedJob.client_name && (
                              <p className="text-xs text-cyan-400 font-medium mt-0.5">
                                مشتری: {selectedJob.client_name} ({selectedJob.client_code})
                              </p>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {(selectedJob.status === 'failed' || selectedJob.status === 'needs_review' || selectedJob.status === 'waiting_auth' || selectedJob.status === 'waiting_retry') && (
                              <button
                                onClick={() => void handleRetryJob(selectedJob.job_id)}
                                disabled={retryingJobId === selectedJob.job_id}
                                className="rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-slate-950 shadow-md transition hover:bg-cyan-400 disabled:opacity-50 flex items-center gap-1.5"
                              >
                                <RotateCcw className="h-3.5 w-3.5" />
                                {retryingJobId === selectedJob.job_id ? '...' : 'تلاش مجدد'}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Waybill Detailed Attributes Grid */}
                        <div className="mt-4 grid gap-3 sm:grid-cols-2 text-xs">
                          <div className="rounded-xl bg-slate-950/60 p-3 border border-white/5 space-y-1">
                            <span className="text-[10px] text-slate-400 block font-bold">مسیر حمل و نقل:</span>
                            <span className="text-slate-200 font-bold text-sm block">
                              {selectedJobPayload?.originCity || 'نامشخص'} ← {selectedJobPayload?.destinationCity || 'نامشخص'}
                            </span>
                          </div>

                          <div className="rounded-xl bg-slate-950/60 p-3 border border-white/5 space-y-1">
                            <span className="text-[10px] text-slate-400 block font-bold">مشخصات ناوگان و پلاک:</span>
                            <span className="text-slate-200 font-bold text-sm block">
                              {selectedJobPayload?.plateNumber ? toPersianDigitsPreserveZero(selectedJobPayload.plateNumber) : 'ثبت نشده'}
                              {selectedJobPayload?.vehicleType && ` (${selectedJobPayload.vehicleType})`}
                            </span>
                          </div>

                          <div className="rounded-xl bg-slate-950/60 p-3 border border-white/5 space-y-1">
                            <span className="text-[10px] text-slate-400 block font-bold">مشخصات محموله:</span>
                            <span className="text-slate-200 font-medium block">
                              {selectedJobPayload?.cargoName || '—'}
                              {selectedJobPayload?.cargoWeight ? ` | وزن: ${toPersianDigitsPreserveZero(selectedJobPayload.cargoWeight)} تن` : ''}
                            </span>
                            {selectedJobPayload?.cargoDescription && (
                              <span className="text-[11px] text-slate-400 block">{selectedJobPayload.cargoDescription}</span>
                            )}
                          </div>

                          <div className="rounded-xl bg-slate-950/60 p-3 border border-white/5 space-y-1">
                            <span className="text-[10px] text-slate-400 block font-bold">اطلاعات راننده و تماس:</span>
                            <span className="text-slate-200 font-medium block">
                              {selectedJob.driver_name || '—'}
                              {selectedJobPayload?.driverPhone ? ` | ${toPersianDigitsPreserveZero(selectedJobPayload.driverPhone)}` : ''}
                            </span>
                            {selectedJobPayload?.driverNationalCode && (
                              <span className="text-[11px] text-slate-400 block">
                                کد ملی: {toPersianDigitsPreserveZero(selectedJobPayload.driverNationalCode)}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Confirmed Tracking Code */}
                        {(() => {
                          const provisionalCode = trackingCodeFromResult(selectedJob.result_json);
                          const tc = confirmedTrackingCode(selectedJob.result_json, selectedJob.status, selectedJob.mutation_status, selectedJob.reconciled_at);
                          if (tc) {
                            return (
                              <div className="mt-4 flex items-center justify-between rounded-xl bg-emerald-500/10 p-3 text-xs text-emerald-400 border border-emerald-500/20 font-medium">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold">کد رهگیری قطعی سامانه UTCMS:</span>
                                  <span className="font-mono font-bold text-sm bg-emerald-500/20 px-2 py-0.5 rounded">{tc}</span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    void navigator.clipboard.writeText(tc);
                                    toast.success('کد رهگیری کپی شد');
                                  }}
                                  className="rounded-lg bg-emerald-500/20 p-1.5 hover:bg-emerald-500/30 transition text-emerald-300"
                                  title="کپی کد رهگیری"
                                >
                                  <Copy className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            );
                          }
                          if (provisionalCode) {
                            return (
                              <div className="mt-4 rounded-xl bg-amber-500/10 p-3 text-xs text-amber-400 border border-amber-500/20 font-medium">
                                در انتظار تطبیق و استخراج کد رهگیری قطعی از سوابق پورتال UTCMS
                              </div>
                            );
                          }
                          return null;
                        })()}

                        {selectedJob.last_error && (
                          <div className="mt-4 rounded-xl bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20 font-medium">
                            <span className="font-bold">علت خطا:</span> {selectedJob.last_error}
                            {selectedJob.error_category && ` (${errorCategoryLabel(selectedJob.error_category)})`}
                          </div>
                        )}
                      </div>

                      {/* Robot Progress Chart */}
                      <JobProgressChart
                        progress={
                          timeline?.progress_percent ||
                          (selectedJob.status === 'success'
                            ? 100
                            : selectedJob.status === 'in_progress'
                            ? 60
                            : selectedJob.status === 'failed'
                            ? 40
                            : 15)
                        }
                        status={selectedJob.status}
                      />

                      {/* Timeline Events List */}
                      {timelineLoading ? (
                        <div className="space-y-4">
                          {[1, 2, 3].map((item) => (
                            <div key={item} className="h-20 animate-pulse rounded-2xl bg-white/5" />
                          ))}
                        </div>
                      ) : timelineError ? (
                        <ErrorState
                          className="mt-6"
                          message={timelineError}
                          onRetry={() => void loadTimeline(selectedJob.job_id)}
                        />
                      ) : timeline && timeline.entries.length > 0 ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
                            <Activity className="h-4 w-4 text-cyan-400" />
                            <span>رخدادهای ثبت‌شده اتوماسیون</span>
                          </div>
                          {timeline.entries.map((entry) => (
                            <article key={entry.entry_id} className="group relative rounded-2xl border border-white/10 bg-white/5 p-4 transition-all hover:bg-white/10 text-right">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2.5">
                                  <div className={`h-2 w-2 rounded-full ${entry.status === 'success' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' : 'bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.5)]'}`}></div>
                                  <h4 className="text-xs font-bold text-slate-200">{entry.title || entry.event_type}</h4>
                                </div>
                                <time className="text-[10px] font-bold text-slate-500">{formatDateTime(entry.created_at)}</time>
                              </div>
                              <p className="mt-2 text-xs leading-relaxed text-slate-400">{entry.message}</p>
                            </article>
                          ))}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            </section>
          ) : (
            /* TAB 2: FUEL INQUIRY TASKS */
            <section className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
              <div className="flex items-center justify-between border-b border-white/5 pb-6">
                <div>
                  <h2 className="text-xl font-black text-white">تاریخچه و پیگیری استعلام‌های سوخت</h2>
                  <p className="mt-1 text-xs text-slate-400">لیست کلیه استعلام‌های سهمیه سوخت ناوگان همراه با کد پیگیری UTCMS</p>
                </div>
                <span className="rounded-full bg-cyan-500/10 border border-cyan-500/20 px-4 py-1.5 text-xs font-black text-cyan-400 shadow-sm">
                  {toPersianDigits(fuelTotal)} مورد
                </span>
              </div>

              {loadingFuel ? (
                <div className="mt-6 space-y-4">
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="h-28 skeleton rounded-2xl" />
                  ))}
                </div>
              ) : fuelInquiries.length === 0 ? (
                <div className="mt-10 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 bg-slate-950/20 py-16">
                  <Fuel className="h-10 w-10 text-slate-600 mb-3" />
                  <p className="text-sm font-medium text-slate-400">هیچ استعلام سوختی با فیلترهای انتخابی یافت نشد.</p>
                </div>
              ) : (
                <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {fuelInquiries.map((inquiry) => {
                    const trackingCode = formatFuelTrackingCode(inquiry);
                    const parsed = parseQuotaData(inquiry.quota_data);

                    return (
                      <div
                        key={inquiry.id}
                        className="group relative rounded-2xl border border-white/5 bg-slate-950/40 p-5 transition-all hover:border-cyan-500/30 hover:bg-slate-950/70 shadow-lg text-right flex flex-col justify-between"
                      >
                        <div>
                          <div className="flex items-center justify-between gap-2 border-b border-white/5 pb-3">
                            <span className="font-mono text-xs font-black text-cyan-400 dir-ltr bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-md">
                              {trackingCode}
                            </span>
                            <span className={['rounded-xl px-3 py-1 text-[11px] font-bold shadow-sm', statusTone(inquiry.status)].join(' ')}>
                              {statusLabel(inquiry.status)}
                            </span>
                          </div>

                          <div className="mt-3 space-y-1.5 text-xs text-slate-300">
                            <p className="font-bold text-slate-100 text-sm">
                              {inquiry.driver_name || `راننده #${inquiry.driver_id}`}
                            </p>
                            {inquiry.plate_number && (
                              <p className="text-slate-400">
                                پلاک: <span className="text-slate-200 font-bold">{toPersianDigitsPreserveZero(inquiry.plate_number)}</span>
                              </p>
                            )}
                            {inquiry.year && inquiry.month && (
                              <p className="text-slate-400">
                                دوره: <span className="text-cyan-400 font-semibold">{toPersianDigitsPreserveZero(inquiry.year)}/{toPersianDigitsPreserveZero(inquiry.month.toString().padStart(2, '0'))}</span>
                              </p>
                            )}
                            {isAdmin && inquiry.client_name && (
                              <p className="text-[11px] text-cyan-400">
                                مشتری: {inquiry.client_name} ({inquiry.client_code})
                              </p>
                            )}
                            <p className="text-[11px] text-slate-400">
                              تاریخ ثبت: {formatDateTime(inquiry.created_at)}
                            </p>
                          </div>

                          {/* Quota Information Section */}
                          {(parsed.baseQuota !== null || parsed.performanceQuota !== null) ? (
                            <div className="mt-3 rounded-xl bg-slate-900/80 border border-white/5 p-3 text-[11px] space-y-1.5 text-slate-300">
                              <p className="font-bold text-cyan-300">اطلاعات سهمیه اختصاص‌یافته:</p>
                              <div className="grid grid-cols-2 gap-2 pt-1 border-t border-white/5">
                                <div>
                                  <span className="text-slate-400 block text-[10px]">سهمیه پایه:</span>
                                  <span className="text-cyan-400 font-bold text-xs mt-0.5 block">
                                    {toPersianDigitsPreserveZero(parsed.baseQuota || '0')} لیتر
                                  </span>
                                </div>
                                <div>
                                  <span className="text-slate-400 block text-[10px]">سهمیه عملکردی:</span>
                                  <span className="text-blue-400 font-bold text-xs mt-0.5 block">
                                    {toPersianDigitsPreserveZero(parsed.performanceQuota || '0')} لیتر
                                  </span>
                                </div>
                              </div>
                              {parsed.cardNumber && (
                                <div className="pt-1 border-t border-white/5 flex justify-between text-slate-400 text-[10px]">
                                  <span>شماره کارت:</span>
                                  <span className="text-slate-200 font-mono font-bold">{toPersianDigitsPreserveZero(parsed.cardNumber)}</span>
                                </div>
                              )}
                            </div>
                          ) : parsed.keyValues.length > 0 ? (
                            <div className="mt-3 rounded-xl bg-slate-900/80 border border-white/5 p-3 text-[11px] space-y-1 text-slate-300">
                              <p className="font-bold text-cyan-300">اطلاعات سهمیه اختصاص‌یافته:</p>
                              {parsed.keyValues.slice(0, 3).map((kv) => (
                                <div key={kv.key} className="flex justify-between text-slate-400">
                                  <span>{kv.key}:</span>
                                  <span className="text-slate-200 font-medium">{toPersianDigitsPreserveZero(kv.value)}</span>
                                </div>
                              ))}
                            </div>
                          ) : inquiry.status === 'success' ? (
                            <div className="mt-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-2.5 text-[11px] font-medium text-emerald-400">
                              اطلاعات استعلام سهمیه سوخت با موفقیت ثبت شد
                            </div>
                          ) : null}

                          {inquiry.error_message && (
                            <div className="mt-3 rounded-xl bg-rose-500/10 border border-rose-500/20 p-2.5 text-[11px] font-medium text-rose-400">
                              علت خطا: {inquiry.error_message}
                            </div>
                          )}
                        </div>

                        <div className="mt-4 flex items-center justify-end gap-2 border-t border-white/5 pt-3">
                          <button
                            type="button"
                            onClick={() => setSelectedFuelInquiry(inquiry)}
                            className="rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-slate-300 hover:bg-slate-800 transition flex items-center gap-1"
                          >
                            <Eye className="h-3 w-3 text-cyan-400" />
                            جزئیات کامل
                          </button>
                          {inquiry.screenshot_url && (
                            <button
                              type="button"
                              onClick={() => setScreenshotModalUrl(inquiry.screenshot_url || null)}
                              className="rounded-xl border border-white/10 bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-slate-300 hover:bg-slate-800 transition flex items-center gap-1"
                            >
                              تصویر
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => void handleRetryFuelInquiry(inquiry)}
                            disabled={retryingFuelId === inquiry.id}
                            className="rounded-xl bg-cyan-500 px-3 py-1.5 text-[11px] font-bold text-slate-950 hover:bg-cyan-400 transition disabled:opacity-50 flex items-center gap-1"
                          >
                            <RotateCcw className="h-3 w-3" />
                            {retryingFuelId === inquiry.id ? '...' : 'استعلام مجدد'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Fuel Inquiries Pagination */}
              {fuelTotal > 20 && (
                <div className="mt-6 flex items-center justify-between rounded-2xl border border-white/5 bg-slate-950/60 p-4 text-xs">
                  <span className="font-bold text-slate-400">
                    صفحه {toPersianDigits(currentPage)} از {toPersianDigits(Math.ceil(fuelTotal / 20))} ({toPersianDigits(fuelTotal)} مورد)
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={currentPage <= 1 || loadingFuel}
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      className="rounded-xl border border-white/10 bg-slate-900 px-3.5 py-1.5 font-bold text-slate-300 hover:bg-slate-800 disabled:opacity-40 transition"
                    >
                      قبلی
                    </button>
                    <button
                      type="button"
                      disabled={currentPage >= Math.ceil(fuelTotal / 20) || loadingFuel}
                      onClick={() => setCurrentPage((p) => p + 1)}
                      className="rounded-xl border border-white/10 bg-slate-900 px-3.5 py-1.5 font-bold text-slate-300 hover:bg-slate-800 disabled:opacity-40 transition"
                    >
                      بعدی
                    </button>
                  </div>
                </div>
              )}

              {fuelError && (
                <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs font-bold text-rose-400 shadow-sm">
                  {fuelError}
                </div>
              )}
            </section>
          )}

          {/* Fuel Inquiry Full Details Modal */}
          {selectedFuelInquiry && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4" role="dialog" aria-modal="true" onClick={() => setSelectedFuelInquiry(null)}>
              <div
                className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[2rem] border border-white/10 bg-slate-950 p-6 md:p-8 shadow-2xl text-right text-white"
                onClick={(e) => e.stopPropagation()}
              >
                {/* Modal Header */}
                <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
                  <div>
                    <h3 className="text-lg font-black text-white">
                      جزئیات استعلام سهمیه سوخت: <span className="text-cyan-400">{selectedFuelInquiry.driver_name || `راننده #${selectedFuelInquiry.driver_id}`}</span>
                    </h3>
                    <p className="mt-1 text-xs text-slate-400">
                      کد پیگیری: <span className="font-mono font-bold text-cyan-400">{formatFuelTrackingCode(selectedFuelInquiry)}</span>
                      {selectedFuelInquiry.plate_number && ` | پلاک: ${toPersianDigitsPreserveZero(selectedFuelInquiry.plate_number)}`}
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedFuelInquiry(null)}
                    className="p-2.5 text-slate-400 hover:text-white rounded-xl hover:bg-white/5 transition"
                    aria-label="بستن پنجره"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Status and Metadata */}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-900/60 p-4 border border-white/5 mb-6 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400">وضعیت:</span>
                    <span className={['rounded-xl px-3 py-1 font-bold text-xs shadow-sm', statusTone(selectedFuelInquiry.status)].join(' ')}>
                      {statusLabel(selectedFuelInquiry.status)}
                    </span>
                  </div>
                  <div className="text-slate-400 text-[11px]">
                    زمان استعلام: {formatDateTime(selectedFuelInquiry.created_at)}
                  </div>
                  {isAdmin && selectedFuelInquiry.client_name && (
                    <div className="text-cyan-400 text-[11px] w-full pt-2 border-t border-white/5">
                      مشتری: {selectedFuelInquiry.client_name} ({selectedFuelInquiry.client_code})
                    </div>
                  )}
                </div>

                {/* Quota Metric Cards */}
                {(() => {
                  const parsed = parseQuotaData(selectedFuelInquiry.quota_data);
                  return (
                    <div className="space-y-6">
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-4 text-right">
                          <div className="flex items-center gap-2 text-cyan-400 text-xs font-bold mb-1">
                            <Fuel className="h-4 w-4" />
                            <span>سهمیه پایه</span>
                          </div>
                          <p className="text-lg font-black text-cyan-300">
                            {parsed.baseQuota ? `${toPersianDigitsPreserveZero(parsed.baseQuota)} لیتر` : '۰ لیتر'}
                          </p>
                        </div>

                        <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-4 text-right">
                          <div className="flex items-center gap-2 text-blue-400 text-xs font-bold mb-1">
                            <Gauge className="h-4 w-4" />
                            <span>سهمیه عملکردی</span>
                          </div>
                          <p className="text-lg font-black text-blue-300">
                            {parsed.performanceQuota ? `${toPersianDigitsPreserveZero(parsed.performanceQuota)} لیتر` : '۰ لیتر'}
                          </p>
                        </div>

                        <div className="col-span-2 sm:col-span-1 rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-right">
                          <div className="flex items-center gap-2 text-slate-400 text-xs font-bold mb-1">
                            <CreditCard className="h-4 w-4 text-cyan-400" />
                            <span>شماره کارت سوخت</span>
                          </div>
                          <p className="text-sm font-mono font-bold text-slate-200 mt-1">
                            {parsed.cardNumber ? toPersianDigitsPreserveZero(parsed.cardNumber) : '—'}
                          </p>
                        </div>
                      </div>

                      {/* Breakdown Data Tables if present */}
                      {parsed.tables.length > 0 && (
                        <div className="space-y-4">
                          <h4 className="text-xs font-bold text-slate-300">ریز جزئیات جدول سامانه:</h4>
                          {parsed.tables.map((table, tIdx) => (
                            <div key={tIdx} className="overflow-x-auto rounded-2xl border border-white/10 bg-slate-900/40">
                              <table className="w-full text-right text-xs">
                                <thead>
                                  <tr className="border-b border-white/10 bg-slate-900 text-slate-300 font-bold">
                                    {table.headers.map((h, hIdx) => (
                                      <th key={hIdx} className="p-3">{h}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 text-slate-300 font-medium">
                                  {table.rows.map((row, rIdx) => (
                                    <tr key={rIdx} className="hover:bg-white/[0.02]">
                                      {row.map((cell, cIdx) => (
                                        <td key={cIdx} className="p-3">
                                          {toPersianDigitsPreserveZero(cell)}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Screenshot Preview */}
                      {selectedFuelInquiry.screenshot_url && (
                        <div>
                          <span className="text-xs font-bold text-slate-400 block mb-2">تصویر مدرک استعلام پرتال UTCMS:</span>
                          <div
                            onClick={() => setScreenshotModalUrl(selectedFuelInquiry.screenshot_url || null)}
                            className="cursor-pointer group relative rounded-2xl border border-white/10 bg-slate-900/60 overflow-hidden max-h-56 flex items-center justify-center hover:border-cyan-500/40 transition"
                          >
                            {/* eslint-disable-next-line @next/next/no-img-element -- dynamic backend URL */}
                            <img
                              src={selectedFuelInquiry.screenshot_url}
                              alt="اسکرین‌شات استعلام سوخت"
                              className="w-full h-auto object-contain max-h-56"
                            />
                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition text-xs font-bold text-white gap-1.5">
                              <Eye className="h-4 w-4 text-cyan-400" />
                              کلیک جهت مشاهده در ابعاد بزرگ
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {selectedFuelInquiry.error_message && (
                  <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs font-bold text-rose-400">
                    علت خطا: {selectedFuelInquiry.error_message}
                  </div>
                )}

                <div className="mt-6 flex justify-between items-center border-t border-white/10 pt-4">
                  <button
                    type="button"
                    onClick={() => {
                      const inquiry = selectedFuelInquiry;
                      setSelectedFuelInquiry(null);
                      void handleRetryFuelInquiry(inquiry);
                    }}
                    className="rounded-xl bg-cyan-500 px-5 py-2.5 text-xs font-bold text-slate-950 hover:bg-cyan-400 transition flex items-center gap-1.5"
                  >
                    <RotateCcw className="h-4 w-4" />
                    استعلام مجدد
                  </button>
                  <button
                    onClick={() => setSelectedFuelInquiry(null)}
                    className="rounded-xl border border-white/10 bg-slate-900 px-5 py-2.5 text-xs font-bold text-slate-300 hover:bg-slate-800 transition"
                  >
                    بستن پنجره
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Delete Job Modal */}
          {deleteModalOpen && deletingJobId && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" role="dialog" aria-modal="true">
              <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-slate-900 p-6 shadow-2xl text-white text-right" onClick={(e) => e.stopPropagation()}>
                 <div className="flex items-center justify-between border-b border-white/5 pb-3">
                   <h3 className="text-lg font-black text-white">تأیید حذف ماموریت</h3>
                   <button onClick={handleDeleteModalClose} className="p-3 text-slate-400 hover:text-slate-200 rounded-xl hover:bg-white/5 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بستن">
                     <X className="h-5 w-5" />
                   </button>
                 </div>
                 <p className="mt-4 text-sm text-slate-400">آیا از حذف ماموریت #{deletingJobId} اطمینان دارید؟</p>
                 {deleteError && (
                   <div className="mt-3 rounded-xl bg-rose-500/10 p-3 text-xs font-bold text-rose-400">
                     {deleteError}
                   </div>
                 )}
                 <div className="mt-6 flex justify-end gap-3">
                   <button onClick={handleDeleteModalClose} className="rounded-xl bg-slate-950 border border-white/5 px-5 py-3 text-xs font-bold text-slate-300 touch-target focus:outline-none focus:ring-2 focus:ring-white">
                     انصراف
                   </button>
                   <button onClick={() => void handleDeleteJob(deletingJobId)} className="rounded-xl bg-rose-500 px-5 py-3 text-xs font-bold text-white hover:bg-rose-600 transition touch-target focus:outline-none focus:ring-2 focus:ring-rose-500">
                     حذف شود
                   </button>
                 </div>
              </div>
            </div>
          )}

          {/* Edit Job Modal */}
          {editModalOpen && editingJob && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" role="dialog" aria-modal="true">
              <div className="w-full max-w-md rounded-[2rem] border border-white/10 bg-slate-900 p-6 shadow-2xl text-white text-right" onClick={(e) => e.stopPropagation()}>
                 <div className="flex items-center justify-between border-b border-white/5 pb-3">
                   <h3 className="text-lg font-black text-white">ویرایش مشخصات ماموریت</h3>
                   <button onClick={handleEditModalClose} className="p-3 text-slate-400 hover:text-slate-200 rounded-xl hover:bg-white/5 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بستن">
                     <X className="h-5 w-5" />
                   </button>
                 </div>

                {editSuccess && (
                  <div className="mt-3 rounded-xl bg-emerald-500/10 p-3 text-xs font-bold text-emerald-400">
                    {editSuccess}
                  </div>
                )}
                {editError && (
                  <div className="mt-3 rounded-xl bg-rose-500/10 p-3 text-xs font-bold text-rose-400">
                    {editError}
                  </div>
                )}

                 <div className="mt-4 space-y-3">
                   <div>
                     <label className="block text-xs font-bold text-slate-400 mb-1">اولویت (0 الی 9)</label>
                     <input
                       type="number"
                       min="0"
                       max="9"
                       value={editForm.priority}
                       onChange={(e) => setEditForm({ ...editForm, priority: Number(e.target.value) })}
                       className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-xs text-white outline-none focus:border-cyan-400 touch-target"
                     />
                   </div>

                   <div>
                     <label className="block text-xs font-bold text-slate-400 mb-1">حداکثر تعداد تلاش مجدد</label>
                     <input
                       type="number"
                       min="0"
                       max="10"
                       value={editForm.max_retries}
                       onChange={(e) => setEditForm({ ...editForm, max_retries: Number(e.target.value) })}
                       className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-xs text-white outline-none focus:border-cyan-400 touch-target"
                     />
                   </div>

                   <div>
                     <label className="block text-xs font-bold text-slate-400 mb-1">علت پایان / یادداشت</label>
                     <input
                       type="text"
                       value={editForm.terminal_reason || ''}
                       onChange={(e) => setEditForm({ ...editForm, terminal_reason: e.target.value })}
                       placeholder="مثال: ویرایش اولویت توسط مدیر سیستم"
                       className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-3 text-xs text-white outline-none focus:border-cyan-400 touch-target"
                     />
                   </div>
                 </div>

                 <div className="mt-6 flex justify-end gap-3">
                   <button onClick={handleEditModalClose} className="rounded-xl bg-slate-950 border border-white/5 px-5 py-3 text-xs font-bold text-slate-300 touch-target focus:outline-none focus:ring-2 focus:ring-white">
                     انصراف
                   </button>
                   <button onClick={() => void handleEditJob(editingJob.job_id)} className="rounded-xl bg-cyan-500 px-5 py-3 text-xs font-bold text-slate-950 hover:bg-cyan-400 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">
                     ذخیره تغییرات
                   </button>
                 </div>
              </div>
            </div>
          )}

          {/* Screenshot Modal */}
          {screenshotModalUrl && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4" onClick={() => setScreenshotModalUrl(null)}>
               <div className="relative max-w-4xl max-h-[90vh] overflow-hidden rounded-2xl border border-white/10 bg-slate-950 p-2 shadow-2xl" onClick={(e) => e.stopPropagation()}>
                 <button onClick={() => setScreenshotModalUrl(null)} className="absolute left-4 top-4 z-10 rounded-full bg-slate-900/80 p-3 text-white hover:bg-slate-800 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بستن">
                   <X className="h-6 w-6" />
                 </button>
                {/* eslint-disable-next-line @next/next/no-img-element -- dynamic backend URL */}
                <img src={screenshotModalUrl} alt="تصویر استعلام سوخت" className="max-h-[85vh] w-auto rounded-xl object-contain" />
              </div>
            </div>
          )}

        </section>
      </AppShell>
    </AuthGuard>
  );
}
