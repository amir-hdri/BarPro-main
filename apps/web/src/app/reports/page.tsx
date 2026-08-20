'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  Filter,
  RefreshCw,
  Search,
  Truck,
  User,
  X,
  XCircle,
} from 'lucide-react';
import { toast } from 'react-hot-toast';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProgressBar, type ProgressTone } from '@/components/ProgressBar';
import { api } from '@/lib/api';
import { downloadCSV, formatRelativePercent, statusLabel, statusTone, toPersianDigits } from '@/lib/format';
import type {
  ClientStats,
  UserFilterOptions,
  UserWaybillHistoryResponse,
} from '@/lib/types';

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

type ActiveTab = 'overview' | 'waybills' | 'drivers' | 'errors';

export default function UserReportsPage() {
  // Tab State
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview');

  // Stats & Options State
  const [stats, setStats] = useState<ClientStats>(emptyStats);
  const [filterOptions, setFilterOptions] = useState<UserFilterOptions | null>(null);

  // Filters State
  const [driverFilter, setDriverFilter] = useState('');
  const [plateFilter, setPlateFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Waybills & Performance Data State
  const [waybillData, setWaybillData] = useState<UserWaybillHistoryResponse | null>(null);
  const [driverPerfData, setDriverPerfData] = useState<any[]>([]);
  const [errorDetailsData, setErrorDetailsData] = useState<any[]>([]);
  const [page, setPage] = useState(1);

  // Loading & Error States
  const [isLoading, setIsLoading] = useState(false);
  const [isStatsLoading, setIsStatsLoading] = useState(false);

  // Load Filter Options & General Dashboard Stats
  const fetchDashboardStats = useCallback(async (signal?: AbortSignal) => {
    setIsStatsLoading(true);
    try {
      const [statsRes, optionsRes] = await Promise.all([
        api.get<ClientStats>('/api/v1/auth/stats', undefined, { signal }),
        api.get<UserFilterOptions>('/api/v1/user/reports/filter-options', undefined, { signal }),
      ]);

      if (statsRes.success && statsRes.data) {
        setStats(statsRes.data);
      }
      if (optionsRes.success && optionsRes.data) {
        setFilterOptions(optionsRes.data);
      }
    } catch {
      toast.error('خطا در دریافت آمار داشبورد');
    } finally {
      setIsStatsLoading(false);
    }
  }, []);

  // Fetch Waybill History with Filters
  const fetchWaybillHistory = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const params: Record<string, any> = {
        page,
        page_size: 20,
      };
      if (driverFilter) params.driver_name = driverFilter;
      if (plateFilter) params.plate_number = plateFilter;
      if (statusFilter) params.status = statusFilter;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const res = await api.get<UserWaybillHistoryResponse>('/api/v1/user/reports/waybills', params, { signal });
      if (res.success && res.data) {
        setWaybillData(res.data);
      }
    } catch {
      toast.error('خطا در دریافت تاریخچه بارنامه‌ها');
    } finally {
      setIsLoading(false);
    }
  }, [page, driverFilter, plateFilter, statusFilter, dateFrom, dateTo]);

  // Fetch Driver Performance Summary
  const fetchDriverPerformance = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const res = await api.get<any[]>('/api/v1/user/reports/driver-performance', undefined, { signal });
      if (res.success && res.data && Array.isArray(res.data)) {
        setDriverPerfData(res.data);
      } else {
        setDriverPerfData([]);
      }
    } catch {
      toast.error('خطا در دریافت گزارش عملکرد رانندگان');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch Error Details
  const fetchErrorDetails = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const res = await api.get<any[]>('/api/v1/user/reports/errors', undefined, { signal });
      if (res.success && res.data && Array.isArray(res.data)) {
        setErrorDetailsData(res.data);
      } else {
        setErrorDetailsData([]);
      }
    } catch {
      toast.error('خطا در دریافت جزئیات خطاها');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial Load
  useEffect(() => {
    const controller = new AbortController();
    void fetchDashboardStats(controller.signal);
    return () => controller.abort();
  }, [fetchDashboardStats]);

  // Trigger Data Fetching per Active Tab
  useEffect(() => {
    const controller = new AbortController();
    if (activeTab === 'waybills') {
      void fetchWaybillHistory(controller.signal);
    } else if (activeTab === 'drivers') {
      void fetchDriverPerformance(controller.signal);
    } else if (activeTab === 'errors') {
      void fetchErrorDetails(controller.signal);
    }
    return () => controller.abort();
  }, [activeTab, fetchWaybillHistory, fetchDriverPerformance, fetchErrorDetails]);

  // Reset Filters
  const handleClearFilters = useCallback(() => {
    setDriverFilter('');
    setPlateFilter('');
    setStatusFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  }, []);

  // Export CSV Handler
  const handleExportCSV = useCallback(() => {
    if (activeTab === 'waybills') {
      if (!waybillData || !waybillData.jobs || waybillData.jobs.length === 0) {
        toast.error('داده‌ای برای خروجی وجود ندارد');
        return;
      }
      const headers = [
        'شناسه ماموریت',
        'نام راننده',
        'کد ملی راننده',
        'پلاک خودرو',
        'وضعیت',
        'منبع ثبت',
        'تعداد تلاش',
        'آخرین خطا',
        'تاریخ ایجاد',
      ];
      const rows = waybillData.jobs.map((j) => [
        j.job_id,
        j.driver_name || '',
        j.driver_national_code || '',
        j.plate_number || '',
        j.status,
        j.source || '',
        j.attempt_count || 1,
        j.last_error || '',
        j.created_at,
      ]);
      downloadCSV('user_waybill_report.csv', headers, rows);
      toast.success('خروجی CSV بارنامه‌ها با موفقیت دریافت شد');
    } else if (activeTab === 'drivers') {
      if (!driverPerfData || driverPerfData.length === 0) {
        toast.error('داده‌ای برای خروجی وجود ندارد');
        return;
      }
      const headers = ['نام راننده', 'کد ملی', 'وضعیت', 'کل بارنامه‌ها', 'موفق', 'ناموفق', 'درصد موفقیت'];
      const rows = driverPerfData.map((d) => [
        d.driver_name,
        d.national_code,
        d.status,
        d.total_jobs,
        d.success_jobs,
        d.failed_jobs,
        `${d.success_rate}%`,
      ]);
      downloadCSV('drivers_performance_report.csv', headers, rows);
      toast.success('خروجی CSV عملکرد رانندگان با موفقیت دریافت شد');
    } else {
      toast.error('امکان دریافت خروجی برای این تب وجود ندارد');
    }
  }, [activeTab, waybillData, driverPerfData]);

  // Active Filter Counter
  const activeFiltersCount = useMemo(() => {
    let count = 0;
    if (driverFilter) count++;
    if (plateFilter) count++;
    if (statusFilter) count++;
    if (dateFrom) count++;
    if (dateTo) count++;
    return count;
  }, [driverFilter, plateFilter, statusFilter, dateFrom, dateTo]);

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <div className="space-y-6 pb-12">
          {/* Header & Page Title */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-3xl border border-white/10 bg-slate-900/60 p-6 backdrop-blur-xl shadow-2xl">
            <div>
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
                <p className="text-xs uppercase tracking-widest text-cyan-300 font-semibold">پنل گزارش عملکرد مشتری</p>
              </div>
              <h1 className="mt-1 text-2xl sm:text-3xl font-black text-white">گزارش‌ها و مانیتورینگ آنلاین</h1>
              <p className="mt-1 text-sm text-slate-300">
                مشاهده لحظه‌ای آمار ثبت بارنامه، گزارش عملکرد رانندگان و فیلترهای هوشمند ناوگان
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  fetchDashboardStats();
                  if (activeTab === 'waybills') fetchWaybillHistory();
                  if (activeTab === 'drivers') fetchDriverPerformance();
                  if (activeTab === 'errors') fetchErrorDetails();
                  toast.success('داده‌ها به‌روزرسانی شدند');
                }}
                disabled={isStatsLoading || isLoading}
                className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-xs font-medium text-slate-200 hover:bg-white/10 hover:text-white transition disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 text-cyan-400 ${isStatsLoading || isLoading ? 'animate-spin' : ''}`} />
                به‌روزرسانی
              </button>
              <button
                onClick={handleExportCSV}
                className="flex items-center gap-2 rounded-2xl bg-cyan-500/20 border border-cyan-500/30 px-4 py-2.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/30 hover:text-cyan-200 transition"
              >
                <Download className="h-4 w-4" />
                خروجی CSV
              </button>
            </div>
          </div>

          {/* Navigation Category Tabs */}
          <div className="flex overflow-x-auto gap-2 border-b border-white/10 pb-2 scrollbar-none">
            <TabButton
              active={activeTab === 'overview'}
              onClick={() => setActiveTab('overview')}
              icon={BarChart3}
              label="خلاصه عملکرد"
            />
            <TabButton
              active={activeTab === 'waybills'}
              onClick={() => setActiveTab('waybills')}
              icon={Filter}
              label="تاریخچه بارنامه‌ها"
              badge={waybillData?.total ? toPersianDigits(waybillData.total) : undefined}
            />
            <TabButton
              active={activeTab === 'drivers'}
              onClick={() => setActiveTab('drivers')}
              icon={Truck}
              label="عملکرد رانندگان"
            />
            <TabButton
              active={activeTab === 'errors'}
              onClick={() => setActiveTab('errors')}
              icon={AlertTriangle}
              label="تحلیل خطاها"
              badge={errorDetailsData.length > 0 ? toPersianDigits(errorDetailsData.length) : undefined}
            />
          </div>

          {/* TAB 1: OVERVIEW & DASHBOARD METRICS */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Primary Rate & Quick Metrics */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard
                  title="نرخ موفقیت کل"
                  value={formatRelativePercent(stats.success_rate)}
                  hint="نسبت ماموریت‌های موفق به کل"
                  icon={CheckCircle2}
                  color="emerald"
                />
                <MetricCard
                  title="موفق امروز"
                  value={toPersianDigits(stats.today_success)}
                  hint="ثبت کامل بدون خطا در امروز"
                  icon={CheckCircle2}
                  color="cyan"
                />
                <MetricCard
                  title="ناموفق امروز"
                  value={toPersianDigits(stats.today_failed)}
                  hint="نیازمند بررسی یا تلاش مجدد"
                  icon={XCircle}
                  color="rose"
                />
                <MetricCard
                  title="ماموریت‌های در حال اجرا"
                  value={toPersianDigits(stats.pending_jobs + stats.in_progress_jobs)}
                  hint="در صف انتظار و پردازش ربات"
                  icon={Clock}
                  color="amber"
                />
              </div>

              {/* Fleet & Executive Metrics */}
              <div className="grid gap-6 md:grid-cols-3">
                <MetricCard
                  title="کل رانندگان تعریف‌شده"
                  value={toPersianDigits(stats.total_drivers)}
                  hint="رانندگان فعال و آماده کار"
                  icon={User}
                  color="purple"
                />
                <MetricCard
                  title="رانندگان فعال"
                  value={toPersianDigits(stats.active_drivers)}
                  hint="دارای نشست و اعتبار فعال"
                  icon={User}
                  color="emerald"
                />
                <MetricCard
                  title="کل ماموریت‌های ثبت‌شده"
                  value={toPersianDigits(stats.total_jobs)}
                  hint="مجموع کل درخواست‌های سیستم"
                  icon={BarChart3}
                  color="cyan"
                />
              </div>

              {/* Status Distribution Progress Bars */}
              <div className="rounded-3xl border border-white/10 bg-slate-900/50 p-6 backdrop-blur-xl space-y-4">
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-cyan-400" />
                  توزیع وضعیت درخواست‌ها
                </h2>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 pt-2">
                  <StatusProgressBox
                    label="موفق"
                    count={stats.success_jobs}
                    total={stats.total_jobs}
                    tone="emerald"
                  />
                  <StatusProgressBox
                    label="ناموفق / خطا"
                    count={stats.failed_jobs}
                    total={stats.total_jobs}
                    tone="rose"
                  />
                  <StatusProgressBox
                    label="در حال اجرا"
                    count={stats.in_progress_jobs}
                    total={stats.total_jobs}
                    tone="cyan"
                  />
                  <StatusProgressBox
                    label="در صف انتظار"
                    count={stats.pending_jobs}
                    total={stats.total_jobs}
                    tone="amber"
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: WAYBILL HISTORY WITH SEARCH & FILTERS */}
          {activeTab === 'waybills' && (
            <div className="space-y-6">
              {/* Comprehensive Filter Bar */}
              <div className="rounded-3xl border border-white/10 bg-slate-900/60 p-5 backdrop-blur-xl space-y-4 shadow-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
                    <Filter className="h-4 w-4 text-cyan-400" />
                    <span>فیلترهای پیشرفته جستجوی بارنامه</span>
                    {activeFiltersCount > 0 && (
                      <span className="rounded-full bg-cyan-500/20 px-2 py-0.5 text-xs text-cyan-300 border border-cyan-500/30">
                        {toPersianDigits(activeFiltersCount)} فیلتر فعال
                      </span>
                    )}
                  </div>
                  {activeFiltersCount > 0 && (
                    <button
                      onClick={handleClearFilters}
                      className="text-xs text-rose-400 hover:text-rose-300 flex items-center gap-1 transition"
                    >
                      <X className="h-3.5 w-3.5" />
                      پاکسازی فیلترها
                    </button>
                  )}
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  {/* Driver Filter */}
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">نام یا کد ملی راننده</label>
                    <div className="relative">
                      <input
                        type="text"
                        value={driverFilter}
                        onChange={(e) => {
                          setDriverFilter(e.target.value);
                          setPage(1);
                        }}
                        placeholder="جستجوی نام یا کد راننده..."
                        className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 pr-9 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                      />
                      <User className="absolute right-2.5 top-2.5 h-4 w-4 text-slate-500" />
                    </div>
                  </div>

                  {/* Vehicle Plate Filter */}
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">پلاک خودرو</label>
                    <div className="relative">
                      <input
                        type="text"
                        value={plateFilter}
                        onChange={(e) => {
                          setPlateFilter(e.target.value);
                          setPage(1);
                        }}
                        placeholder="مثال: 12ع345ایران77..."
                        className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 pr-9 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                      />
                      <Truck className="absolute right-2.5 top-2.5 h-4 w-4 text-slate-500" />
                    </div>
                  </div>

                  {/* Status Filter */}
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">وضعیت بارنامه</label>
                    <select
                      value={statusFilter}
                      onChange={(e) => {
                        setStatusFilter(e.target.value);
                        setPage(1);
                      }}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    >
                      <option value="">همه وضعیت‌ها</option>
                      <option value="success">موفق (SUCCESS)</option>
                      <option value="failed">ناموفق (FAILED)</option>
                      <option value="in_progress">در حال اجرا (IN_PROGRESS)</option>
                      <option value="pending">در انتظار (PENDING)</option>
                      <option value="queued">در صف (QUEUED)</option>
                      <option value="needs_review">نیازمند بازبینی (NEEDS_REVIEW)</option>
                      <option value="submission_unconfirmed">ثبت غیرقطعی (UNCONFIRMED)</option>
                    </select>
                  </div>

                  {/* Date From */}
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">از تاریخ</label>
                    <input
                      type="date"
                      value={dateFrom}
                      onChange={(e) => {
                        setDateFrom(e.target.value);
                        setPage(1);
                      }}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    />
                  </div>

                  {/* Date To */}
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">تا تاریخ</label>
                    <input
                      type="date"
                      value={dateTo}
                      onChange={(e) => {
                        setDateTo(e.target.value);
                        setPage(1);
                      }}
                      className="w-full rounded-xl border border-white/10 bg-slate-950/80 px-3 py-2 text-xs text-white focus:border-cyan-500 focus:outline-none"
                    />
                  </div>
                </div>

                {/* Dropdown Quick Pickers if available */}
                {filterOptions && filterOptions.drivers.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-2 border-t border-white/5 text-xs text-slate-400">
                    <span className="py-1">انتخاب سریع راننده:</span>
                    {filterOptions.drivers.slice(0, 5).map((d) => (
                      <button
                        key={d.id}
                        onClick={() => {
                          setDriverFilter(d.full_name);
                          setPage(1);
                        }}
                        className={`rounded-lg px-2.5 py-1 border transition ${
                          driverFilter === d.full_name
                            ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                            : 'bg-white/5 text-slate-300 border-white/10 hover:bg-white/10'
                        }`}
                      >
                        {d.full_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>

               {/* Waybills Data Table */}
               <div className="rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl overflow-hidden shadow-2xl">
                 {isLoading ? (
                   <div className="p-12 text-center text-slate-400">
                     <RefreshCw className="h-8 w-8 text-cyan-400 animate-spin mx-auto mb-3" />
                     <span>در حال بارگذاری بارنامه‌ها...</span>
                   </div>
                 ) : !waybillData || !waybillData.jobs || waybillData.jobs.length === 0 ? (
                   <div className="p-12 text-center text-slate-400">
                     <Search className="h-10 w-10 text-slate-500 mx-auto mb-3" />
                     <p className="text-base font-semibold text-slate-200">هیچ بارنامه‌ای با این فیلترها یافت نشد</p>
                     <p className="text-xs text-slate-400 mt-1">
                       می‌توانید فیلترهای جستجو را تغییر دهید یا پاک کنید.
                     </p>
                   </div>
                 ) : (
                   <>
                     {/* Desktop Table */}
                     <div className="hidden md:block overflow-x-auto">
                       <table className="w-full text-right text-sm">
                        <thead className="bg-slate-950/80 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-white/10">
                          <tr>
                            <th className="py-4 px-4">شناسه ماموریت</th>
                            <th className="py-4 px-4">نام راننده</th>
                            <th className="py-4 px-4">پلاک خودرو</th>
                            <th className="py-4 px-4">وضعیت</th>
                            <th className="py-4 px-4">تعداد تلاش</th>
                            <th className="py-4 px-4">منبع ثبت</th>
                            <th className="py-4 px-4">تاریخ ثبت</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-slate-300">
                          {waybillData.jobs.map((job) => (
                            <tr key={job.job_id} className="hover:bg-white/[0.02] transition">
                              <td className="py-3.5 px-4 font-mono text-xs text-cyan-300">{job.job_id}</td>
                              <td className="py-3.5 px-4">
                                <div className="font-semibold text-slate-100">{job.driver_name || 'نامشخص'}</div>
                                {job.driver_national_code && (
                                  <div className="text-xs text-slate-400">کد ملی: {job.driver_national_code}</div>
                                )}
                              </td>
                              <td className="py-3.5 px-4">
                                {job.plate_number ? (
                                  <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-300 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">
                                    <Truck className="h-3.5 w-3.5" />
                                    {job.plate_number}
                                  </span>
                                ) : (
                                  <span className="text-xs text-slate-500">-</span>
                                )}
                              </td>
                              <td className="py-3.5 px-4">
                                <StatusBadge status={job.status} />
                              </td>
                              <td className="py-3.5 px-4 font-mono text-xs">
                                {toPersianDigits(job.attempt_count || 1)}
                              </td>
                              <td className="py-3.5 px-4 text-xs text-slate-400">{job.source}</td>
                              <td className="py-3.5 px-4 text-xs text-slate-400">
                                {new Date(job.created_at).toLocaleString('fa-IR')}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                       </table>
                     </div>

                     {/* Mobile Cards */}
                     <div className="md:hidden space-y-3 p-4">
                       {waybillData.jobs.map((job) => (
                         <div key={job.job_id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 space-y-3">
                           <div className="flex items-center justify-between">
                             <div>
                               <p className="font-mono text-xs text-cyan-300">{job.job_id}</p>
                               <p className="mt-1 font-semibold text-slate-200">{job.driver_name || 'نامشخص'}</p>
                               {job.driver_national_code && (
                                 <p className="text-xs text-slate-400">کد ملی: {job.driver_national_code}</p>
                               )}
                             </div>
                             <StatusBadge status={job.status} />
                           </div>
                           <div className="grid grid-cols-2 gap-3 text-sm">
                             <div>
                               <span className="text-xs text-slate-400">پلاک:</span>
                               {job.plate_number ? (
                                 <div className="inline-flex items-center gap-1 text-xs font-medium text-emerald-300 bg-emerald-500/10 px-2 py-0.5 rounded-lg border border-emerald-500/20 mt-1">
                                   <Truck className="h-3 w-3" />
                                   {job.plate_number}
                                 </div>
                               ) : (
                                 <span className="text-xs text-slate-500 mt-1 block">-</span>
                               )}
                             </div>
                             <div>
                               <span className="text-xs text-slate-400">تلاش‌ها:</span>
                               <div className="font-mono text-xs text-slate-200 mt-1">{toPersianDigits(job.attempt_count || 1)}</div>
                             </div>
                           </div>
                           <div className="grid grid-cols-2 gap-3 text-sm">
                             <div>
                               <span className="text-xs text-slate-400">منبع:</span>
                               <div className="text-xs text-slate-300 mt-1">{job.source}</div>
                             </div>
                             <div>
                               <span className="text-xs text-slate-400">تاریخ:</span>
                               <div className="text-xs text-slate-300 mt-1">{new Date(job.created_at).toLocaleString('fa-IR')}</div>
                             </div>
                           </div>
                         </div>
                       ))}
                     </div>

                     {/* Pagination Bar */}
                     <div className="flex items-center justify-between border-t border-white/10 px-6 py-4 bg-slate-950/60">
                      <div className="text-xs text-slate-400">
                        نمایش صفحه {toPersianDigits(waybillData.page)} از {toPersianDigits(waybillData.total_pages)} (کل{' '}
                        {toPersianDigits(waybillData.total)} ردیف)
                      </div>
                       <div className="flex items-center gap-2">
                         <button
                           disabled={page <= 1}
                           onClick={() => setPage((p) => Math.max(1, p - 1))}
                           className="rounded-xl border border-white/10 bg-white/5 p-3 text-slate-300 hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-white/5 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                           aria-label="صفحه قبل"
                         >
                           <ChevronRight className="h-5 w-5" />
                         </button>
                         <button
                           disabled={page >= waybillData.total_pages}
                           onClick={() => setPage((p) => p + 1)}
                           className="rounded-xl border border-white/10 bg-white/5 p-3 text-slate-300 hover:bg-white/10 disabled:opacity-30 disabled:hover:bg-white/5 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                           aria-label="صفحه بعد"
                         >
                           <ChevronLeft className="h-5 w-5" />
                         </button>
                       </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: DRIVER PERFORMANCE SUMMARY */}
          {activeTab === 'drivers' && (
            <div className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 shadow-2xl">
                <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                  <Truck className="h-5 w-5 text-purple-400" />
                  خلاصه عملکرد رانندگان ناوگان
                </h2>
                {isLoading ? (
                  <div className="p-12 text-center text-slate-400">
                    <RefreshCw className="h-8 w-8 text-cyan-400 animate-spin mx-auto mb-3" />
                    <span>در حال بارگذاری آمار رانندگان...</span>
                  </div>
                ) : driverPerfData.length === 0 ? (
                  <div className="p-8 text-center text-slate-400">راننده‌ای یافت نشد.</div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {driverPerfData.map((d) => (
                      <div
                        key={d.driver_id}
                        className="rounded-2xl border border-white/10 bg-slate-950/60 p-5 space-y-3 hover:border-cyan-500/30 transition"
                      >
                        <div className="flex items-center justify-between">
                          <div className="font-bold text-slate-100">{d.driver_name}</div>
                          <span className="text-xs text-slate-400">کد ملی: {d.national_code}</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 py-2 text-center border-y border-white/5">
                          <div>
                            <div className="text-xs text-slate-400">کل</div>
                            <div className="text-base font-bold text-white">{toPersianDigits(d.total_jobs)}</div>
                          </div>
                          <div>
                            <div className="text-xs text-emerald-400">موفق</div>
                            <div className="text-base font-bold text-emerald-400">{toPersianDigits(d.success_jobs)}</div>
                          </div>
                          <div>
                            <div className="text-xs text-rose-400">ناموفق</div>
                            <div className="text-base font-bold text-rose-400">{toPersianDigits(d.failed_jobs)}</div>
                          </div>
                        </div>
                        <div className="flex items-center justify-between pt-1">
                          <span className="text-xs text-slate-400">درصد موفقیت:</span>
                          <span className="text-xs font-bold text-cyan-300 font-mono">{d.success_rate}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: ERROR ANALYSIS & TROUBLESHOOTING */}
          {activeTab === 'errors' && (
            <div className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 shadow-2xl">
                <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-rose-400" />
                  جزئیات خطاهای ثبت بارنامه و گام‌های ربات
                </h2>
                {isLoading ? (
                  <div className="p-12 text-center text-slate-400">
                    <RefreshCw className="h-8 w-8 text-cyan-400 animate-spin mx-auto mb-3" />
                    <span>در حال دریافت جزئیات خطاها...</span>
                  </div>
                ) : errorDetailsData.length === 0 ? (
                  <div className="p-8 text-center text-emerald-400 flex items-center justify-center gap-2">
                    <CheckCircle2 className="h-5 w-5" />
                    <span>هیچ خطایی در ماموریت‌های اخیر ثبت نشده است.</span>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {errorDetailsData.map((err) => (
                      <div
                        key={err.job_id}
                        className="rounded-2xl border border-rose-500/20 bg-rose-950/10 p-5 space-y-3"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rose-500/20 pb-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-rose-300 font-bold">{err.job_id}</span>
                            <span className="text-sm font-semibold text-slate-200">
                              (راننده: {err.driver_name || 'نامشخص'})
                            </span>
                          </div>
                          <span className="text-xs text-slate-400">
                            {new Date(err.created_at).toLocaleString('fa-IR')}
                          </span>
                        </div>
                        {err.last_error && (
                          <div className="rounded-xl bg-slate-950/80 p-3 text-xs text-rose-300 font-mono leading-relaxed border border-rose-500/30">
                            <span className="font-bold text-rose-400">خطای رخ‌داده: </span>
                            {err.last_error}
                          </div>
                        )}
                        {err.steps && err.steps.length > 0 && (
                          <div className="space-y-1.5 pt-2">
                            <div className="text-xs text-slate-400 font-semibold mb-2">گام‌های اجرای اتوماسیون:</div>
                            {err.steps.map((s: { step: string; message: string; status: string }, idx: number) => (
                              <div key={idx} className="flex items-center justify-between text-xs text-slate-300 bg-slate-950/40 px-3 py-1.5 rounded-lg border border-white/5">
                                <span>{s.step}: {s.message}</span>
                                <span className={s.status === 'success' ? 'text-emerald-400' : 'text-rose-400'}>
                                  {s.status}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  );
}

// ── Sub-components for UI Cleanliness ──────────────────
function TabButton({
  active,
  badge,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  badge?: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2.5 rounded-2xl px-5 py-3 text-sm font-bold transition whitespace-nowrap ${
        active
          ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
          : 'bg-slate-900/60 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200 border border-white/5'
      }`}
    >
      <Icon className={`h-4 w-4 ${active ? 'text-slate-950' : 'text-cyan-400'}`} />
      <span>{label}</span>
      {badge && (
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            active ? 'bg-slate-950/20 text-slate-950 font-black' : 'bg-white/10 text-cyan-300'
          }`}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

function MetricCard({
  color,
  hint,
  icon: Icon,
  title,
  value,
}: {
  color: 'emerald' | 'cyan' | 'rose' | 'amber' | 'purple';
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  value: string;
}) {
  const colorStyles = {
    emerald: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    cyan: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    rose: 'text-rose-400 bg-rose-500/10 border-rose-500/20',
    amber: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    purple: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl shadow-xl flex flex-col justify-between">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400 font-semibold">{title}</span>
        <span className={`p-2 rounded-xl border ${colorStyles[color]}`}>
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <div className="mt-4">
        <div className="text-2xl sm:text-3xl font-black text-white">{value}</div>
        <p className="mt-1 text-xs text-slate-400 leading-relaxed">{hint}</p>
      </div>
    </div>
  );
}

function StatusProgressBox({
  tone,
  count,
  label,
  total,
}: {
  tone: ProgressTone;
  count: number;
  label: string;
  total: number;
}) {
  const percent = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="rounded-2xl border border-white/5 bg-slate-950/60 p-4 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300 font-medium">{label}</span>
        <span className="font-bold text-white font-mono">{toPersianDigits(count)} ({toPersianDigits(percent)}%)</span>
      </div>
      <ProgressBar value={percent} tone={tone} label={`سهم وضعیت ${label}`} />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-semibold ${statusTone(status)}`}>
      {statusLabel(status)}
    </span>
  );
}
