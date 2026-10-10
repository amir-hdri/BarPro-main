'use client';
/* eslint-disable @next/next/no-img-element */

import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RecordFilters } from '@/components/RecordFilters';
import { ErrorState } from '@/components/layout/States';
import { EMPTY_RECORD_FILTERS, recordFilterParams, recordFiltersFromSearch, parseApiDate, tehranDateKey, type RecordFilters as Filters } from '@/lib/record-filters';
import { nextUnobservedInquiry } from '@/lib/fuel-polling';
import { sessionQueryKey } from '@/lib/session-query';
import { useCallback, useEffect, useState, useRef, useMemo, memo } from 'react';
import {
  FireIcon,
  ClockIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  EyeIcon,
  SparklesIcon,
  TruckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProgressBar } from '@/components/ProgressBar';
import { api } from '@/lib/api';
import {
  formatDateTime,
  formatFuelTrackingCode,
  parseQuotaData,
  toPersianDigitsPreserveZero,
} from '@/lib/format';
import { useSession } from '@/hooks/useSession';
import type { Driver, FuelInquiry, WaybillJob, Plate } from '@/lib/types';
import { toast } from 'react-hot-toast';



const MAX_POLLING_ATTEMPTS = 60;
const TOTAL_SECONDS_EST = 50;

const getDriverInitials = (name: string) => {
  const parts = name.split(' ');
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`;
  return name.slice(0, 2);
};

const FuelInquiryCard = memo(function FuelInquiryCard({
  item,
  onSelect,
  getDriverInitials,
}: {
  item: FuelInquiry;
  onSelect: (item: FuelInquiry) => void;
  getDriverInitials: (name: string) => string;
}) {
  const parsed = parseQuotaData(item.quota_data);
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-slate-900 border border-white/5 flex items-center justify-center text-slate-400 text-xs font-black shrink-0">
            {item.driver_name ? getDriverInitials(item.driver_name) : 'ن/م'}
          </div>
          <div>
            <span className="font-bold text-white block text-sm">{item.driver_name || 'نامشخص'}</span>
            {item.driver_name_source === 'current_driver' && <span className="text-xs text-amber-300">نام فعلی راننده؛ نام تاریخی ثبت نشده</span>}
            <span className="text-[10px] text-slate-400 font-sans font-medium">کد رهگیری: {formatFuelTrackingCode(item)}</span>
          </div>
        </div>
        <div>
          {item.status === 'success' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 text-[10px] font-bold text-emerald-400">
              موفق
            </span>
          )}
          {item.status === 'failed' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 text-[10px] font-bold text-rose-400">
              ناموفق
            </span>
          )}
          {item.status === 'processing' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-3 py-1.5 text-[10px] font-bold text-cyan-400">
              در حال اجرا
            </span>
          )}
          {item.status === 'pending' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-slate-500/10 border border-slate-500/20 px-3 py-1.5 text-[10px] font-bold text-slate-400">
              در صف
            </span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400 bg-slate-900/30 p-3 rounded-2xl border border-white/5 font-sans font-medium">
        <div>کد رهگیری: <strong className="text-slate-200 font-sans font-semibold">{formatFuelTrackingCode(item)}</strong></div>
        <div>دوره: <strong className="text-cyan-400 font-sans font-semibold">{item.year && item.month ? `${toPersianDigitsPreserveZero(item.year.toString())}/${toPersianDigitsPreserveZero(item.month.toString().padStart(2, '0'))}` : 'جاری'}</strong></div>
        <div>پایه: <strong className="text-cyan-400 font-sans font-semibold">{parsed.baseQuota ? `${toPersianDigitsPreserveZero(parsed.baseQuota)} لیتر` : '۰'}</strong></div>
        <div>عملکردی: <strong className="text-blue-400 font-sans font-semibold">{parsed.performanceQuota ? `${toPersianDigitsPreserveZero(parsed.performanceQuota)} لیتر` : '۰'}</strong></div>
        <div className="col-span-2 text-xs text-slate-500 font-sans font-medium">زمان درخواست: {formatDateTime(item.created_at)}</div>
        {item.finished_at && <div className="col-span-2 text-xs text-cyan-300">دریافت نتیجه: {formatDateTime(item.finished_at)}</div>}
      </div>
       <button
         onClick={() => onSelect(item)}
         disabled={item.status === 'pending' || item.status === 'processing'}
         className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-white/5 bg-slate-900 hover:bg-slate-800 py-3.5 text-xs font-bold text-slate-300 disabled:opacity-40 disabled:pointer-events-none transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
         aria-label="مشاهده جزئیات کامل استعلام سوخت"
       >
         <EyeIcon className="h-5 w-5" />
         مشاهده جزئیات کامل
       </button>
    </div>
  );
});

export default function FuelInquiryPage() {
  const { role, client } = useSession();
  const queryClient = useQueryClient();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [inquiries, setInquiries] = useState<FuelInquiry[]>([]);
  const isAdmin = role === 'master_admin';

  const [selectedDriverId, setSelectedDriverId] = useState<number>(0);
  const [activeInquiryId, setActiveInquiryId] = useState<number | null>(null);

  const [selectedYear, setSelectedYear] = useState<number>(1403);
  const [selectedMonth, setSelectedMonth] = useState<number>(5);

  const [historyFilters, setHistoryFilters] = useState<Filters>({ ...EMPTY_RECORD_FILTERS });
  const [historyPage, setHistoryPage] = useState(1);
  const [historyReady, setHistoryReady] = useState(false);
  const changeHistoryFilters = (next: Filters) => { setHistoryPage(1); setHistoryFilters(next); };
  useEffect(() => {
    const initial = recordFiltersFromSearch(window.location.search);
    setHistoryFilters(initial);
    setHistoryReady(true);
    if (initial.driverId) setSelectedDriverId(Number(initial.driverId));
    const parts = new Intl.DateTimeFormat('en-u-ca-persian', {
      timeZone: 'Asia/Tehran', year: 'numeric', month: 'numeric',
    }).formatToParts(new Date());
    setSelectedYear(Number(parts.find(part => part.type === 'year')?.value));
    setSelectedMonth(Number(parts.find(part => part.type === 'month')?.value));
  }, []);

  const { data: historyData, isFetching: historyLoading, error: historyError, refetch: refetchHistory } = useQuery({
    queryKey: sessionQueryKey(client, 'fuel-history', historyPage, historyFilters),
    enabled: Boolean(client && historyReady),
    queryFn: async ({ signal }) => {
      const response = await api.get<{ items: FuelInquiry[]; total: number }>('/api/v1/fuel-inquiries', {
        page: historyPage, page_size: 20, ...recordFilterParams(historyFilters),
      }, { signal });
      if (!response.success || !response.data) throw new Error(response.error || 'تاریخچه استعلام‌ها دریافت نشد.');
      return response.data;
    },
  });
  const filteredInquiries = useMemo(() => historyData?.items || [], [historyData]);
  const historyTotal = historyData?.total || 0;

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selectedInquiry, setSelectedInquiry] = useState<FuelInquiry | null>(null);
  const [error, setError] = useState<string | null>(null);


  const [elapsedTime, setElapsedTime] = useState(0);

  const [driverWaybills, setDriverWaybills] = useState<WaybillJob[]>([]);
  const [driverPlates, setDriverPlates] = useState<Plate[]>([]);
  const [loadedDriverId, setLoadedDriverId] = useState(0);
  const [loadingWaybills, setLoadingWaybills] = useState(false);
  const selectedDriverPlate = drivers.find(driver => driver.id === selectedDriverId)?.active_plate
    || (loadedDriverId === selectedDriverId ? driverPlates[0]?.plate_number : undefined);

  const groupedInquiries = useMemo(() => {
    const groups: Record<string, { key: string; day: string; currentName: boolean; driverName: string; plateNumber: string; clientInfo?: string; items: FuelInquiry[] }> = {};
    filteredInquiries.forEach((item) => {
      const driverName = item.driver_name || 'نامشخص';
      const plateNumber = item.plate_number || 'پلاک تاریخی ثبت نشده';
      const day = tehranDateKey(item.created_at);
      const key = `${item.client_id}:${item.driver_id}:${plateNumber}:${day}`;
      if (!groups[key]) {
        let clientInfo = '';
        if (isAdmin && item.client_name) {
          clientInfo = ` (مشتری: ${item.client_name} - ${item.client_code})`;
        }
        groups[key] = {
          key, day, currentName: item.driver_name_source === 'current_driver', driverName,
          plateNumber,
          clientInfo,
          items: [],
        };
      }
      groups[key].items.push(item);
    });

    return Object.values(groups).map((group) => {
      group.items.sort((a, b) => parseApiDate(b.created_at).getTime() - parseApiDate(a.created_at).getTime());
      return group;
    });
  }, [filteredInquiries, isAdmin]);

  // Fetch driver recent waybills & plates when a driver is selected
  useEffect(() => {
    setLoadedDriverId(0);
    setDriverWaybills([]);
    setDriverPlates([]);
    if (selectedDriverId === 0) {
      setLoadingWaybills(false);
      return;
    }

    const controller = new AbortController();
    const fetchDriverData = async () => {
      setLoadingWaybills(true);
      try {
        const [wbRes, plRes] = await Promise.all([
          api.get<{ tasks: WaybillJob[] }>(`/api/v1/waybill-jobs?driver_id=${selectedDriverId}&page_size=5`, undefined, { signal: controller.signal }),
          api.get<Plate[]>(`/api/v1/plates?driver_id=${selectedDriverId}&page_size=20`, undefined, { signal: controller.signal }),
        ]);

        if (controller.signal.aborted) return;
        setLoadedDriverId(selectedDriverId);
        if (wbRes.success && wbRes.data) {
          setDriverWaybills(wbRes.data.tasks || []);
        } else {
          setDriverWaybills([]);
        }

        if (plRes.success && plRes.data) {
          setDriverPlates(Array.isArray(plRes.data) ? plRes.data : []);
        } else {
          setDriverPlates([]);
        }
      } catch {
        if (controller.signal.aborted) return;
        setDriverWaybills([]);
        setDriverPlates([]);
      } finally {
        if (!controller.signal.aborted) setLoadingWaybills(false);
      }
    };
    fetchDriverData();
    return () => controller.abort();
  }, [selectedDriverId]);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const pollingAttemptsRef = useRef(0);
  const resumedInquiryIds = useRef(new Set<number>());
  const pollingController = useRef<AbortController | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const dataController = useRef<AbortController | null>(null);
  const historyController = useRef<AbortController | null>(null);
  const submitController = useRef<AbortController | null>(null);

  // Load all drivers and all fuel inquiries
  const loadData = useCallback(async () => {
    dataController.current?.abort();
    const controller = new AbortController();
    dataController.current = controller;
    const signal = controller.signal;
    if (!client || (role !== 'client' && role !== 'master_admin')) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const [driversResponse, inquiriesResponse] = await Promise.all([
        api.get<Driver[]>('/api/v1/drivers', { page_size: 1000 }, { signal }),
        api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries', { page_size: 100 }, { signal }),
      ]);

      if (signal?.aborted) return;
      if (driversResponse.success && driversResponse.data) {
        setDrivers(Array.isArray(driversResponse.data) ? driversResponse.data : []);
      } else {
        setError(driversResponse.error || 'خطا در بارگذاری لیست رانندگان');
      }

      if (inquiriesResponse.success && inquiriesResponse.data) {
        setInquiries(Array.isArray(inquiriesResponse.data.items) ? inquiriesResponse.data.items : []);
      } else {
        setInquiries([]);
      }
    } catch (err: unknown) {
      if (signal.aborted) return;
      setError(err instanceof Error ? err.message : 'خطا در بارگذاری اطلاعات');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [role, client]);

  useEffect(() => {
    void loadData();
    return () => dataController.current?.abort();
  }, [loadData]);

  const refreshHistory = useCallback(async (): Promise<FuelInquiry[]> => {
    historyController.current?.abort();
    const controller = new AbortController();
    historyController.current = controller;
    void queryClient.invalidateQueries({ queryKey: sessionQueryKey(client, 'fuel-history') });
    try {
      const inquiriesResponse = await api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries', { page_size: 100 }, { signal: controller.signal });
      if (controller.signal.aborted) return [];
      if (inquiriesResponse.success && inquiriesResponse.data) {
        const items = inquiriesResponse.data.items || [];
        setInquiries(items);
        return items;
      }
    } catch {
      if (controller.signal.aborted) return [];
      toast.error('به‌روزرسانی استعلام‌ها انجام نشد. دوباره تلاش کنید.');
    }
    return [];
  }, [client, queryClient]);

  const startPolling = useCallback((inquiryId: number) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingController.current?.abort();
    const controller = new AbortController();
    pollingController.current = controller;
    resumedInquiryIds.current.add(inquiryId);
    let inFlight = false;

    setActiveInquiryId(inquiryId);
    pollingAttemptsRef.current = 0;
    let consecutiveErrors = 0;

    pollingRef.current = setInterval(async () => {
      if (inFlight || controller.signal.aborted) return;
      pollingAttemptsRef.current += 1;

      if (pollingAttemptsRef.current > MAX_POLLING_ATTEMPTS) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setActiveInquiryId(null);
        setSubmitting(false);
        toast.error('زمان انتظار برای دریافت نتیجه استعلام به پایان رسید.');
        void refreshHistory();
        return;
      }

      inFlight = true;
      try {
        const response = await api.get<FuelInquiry>(`/api/v1/fuel-inquiries/${inquiryId}`, undefined, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (response.success && response.data) {
          consecutiveErrors = 0;
          const updated = response.data;

          setInquiries(prev => prev.map(item => item.id === inquiryId ? updated : item));

          if (updated.status === 'success' || updated.status === 'failed' || updated.status === 'stale') {
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
            if (updated.status === 'success') {
              toast.success('استعلام با موفقیت تکمیل شد');
            } else if (updated.status === 'failed') {
              toast.error(updated.error_message || 'استعلام با خطا مواجه شد');
            }
            setActiveInquiryId(null);
            setSubmitting(false);
            void refreshHistory();
          }
        } else {
          consecutiveErrors += 1;
          if (consecutiveErrors >= 5) {
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
            setActiveInquiryId(null);
            setSubmitting(false);
            toast.error(response.error || 'خطا در ارتباط با سرور هنگام دریافت نتیجه استعلام');
          }
        }
      } catch {
        if (controller.signal.aborted) return;
        consecutiveErrors += 1;
        if (consecutiveErrors >= 5) {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          setActiveInquiryId(null);
          setSubmitting(false);
          toast.error('خطای شبکه در دریافت نتیجه استعلام');
        }
      } finally {
        inFlight = false;
      }
    }, 3000);
  }, [refreshHistory]);

  // Auto-resume polling for any active inquiry in the list
  useEffect(() => {
    const active = nextUnobservedInquiry(inquiries, resumedInquiryIds.current, activeInquiryId);
    if (active && !activeInquiryId) {
      startPolling(active.id);
    }
  }, [inquiries, activeInquiryId, startPolling]);

  useEffect(() => {
    if (activeInquiryId) {
      setElapsedTime(0);
      timerRef.current = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);
    } else {
      setElapsedTime(0);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [activeInquiryId]);

  useEffect(() => {
    return () => {
      pollingController.current?.abort();
      dataController.current?.abort();
      historyController.current?.abort();
      submitController.current?.abort();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const handleStartInquiry = async (forceRetry = false) => {
    if (selectedDriverId === 0) return;
    submitController.current?.abort();
    const controller = new AbortController();
    submitController.current = controller;
    setSubmitting(true);
    setError(null);

    const response = await api.post<FuelInquiry>('/api/v1/fuel-inquiries', {
      driver_id: selectedDriverId,
      year: selectedYear,
      month: selectedMonth,
      force_retry: forceRetry,
      plate_number: selectedDriverPlate,
    }, { signal: controller.signal });
    if (controller.signal.aborted) return;

    if (response.success && response.data) {
      void queryClient.invalidateQueries({ queryKey: sessionQueryKey(client, 'fuel-history') });
      const newInquiry = response.data;
      setInquiries(prev => [newInquiry, ...prev.filter(i => i.id !== newInquiry.id)]);
      toast.success(forceRetry ? 'استعلام مجدد آغاز شد' : 'استعلام جدید آغاز شد');
      startPolling(newInquiry.id);
    } else {
      const msg = response.error || 'خطا در ایجاد استعلام جدید';
      if (/فعال|تکرار|در جریان|duplicate|409/i.test(msg)) {
        const freshItems = await refreshHistory();
        if (controller.signal.aborted) return;
        const existing = freshItems.find(i => 
          i.driver_id === selectedDriverId && 
          (i.status === 'pending' || i.status === 'processing' || i.status === 'running')
        );
        if (existing) {
          startPolling(existing.id);
          toast('استعلام در حال اجرا بازیابی شد و در حال پایش وضعیت است.', { icon: 'ℹ️' });
        } else {
          setError(msg);
          toast.error(msg);
        }
      } else {
        setError(msg);
        toast.error(msg);
      }
      setSubmitting(false);
    }
  };

  const activeInquiry = inquiries.find(i => i.id === activeInquiryId);
  const progressPercent = Math.min((elapsedTime / TOTAL_SECONDS_EST) * 100, 98);

  const selectedDriver = useMemo(() => {
    return drivers.find(d => d.id === selectedDriverId) || null;
  }, [drivers, selectedDriverId]);

  const selectedDriverActiveInquiry = useMemo(() => {
    if (!selectedDriverId) return null;
    return inquiries.find(i => 
      i.driver_id === selectedDriverId && 
      (i.status === 'pending' || i.status === 'processing' || i.status === 'running')
    ) || null;
  }, [inquiries, selectedDriverId]);

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <div className="mx-auto max-w-7xl px-3 py-4 sm:px-6 sm:py-8 lg:px-8">
          <div className="mb-6 md:mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-3.5 py-1.5 text-xs font-bold text-cyan-400 border border-cyan-500/20 mb-3">
                <SparklesIcon className="h-4 w-4" />
                <span>سرویس هوشمند استعلام سوخت UTCMS</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                استعلام سهمیه سوخت ناوگان
              </h1>
            </div>
          </div>

          {error && (
            <div className="mb-6 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4 text-xs sm:text-sm font-semibold text-rose-400 backdrop-blur-md flex items-center gap-3">
              <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* RIGHT PANEL: CREATE NEW INQUIRY & DRIVER DETAILS */}
            <div className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-slate-950 p-6 shadow-xl relative overflow-hidden">
                <div className="absolute -top-20 -right-20 h-40 w-40 rounded-full bg-cyan-500/10 blur-[50px] pointer-events-none" />

                <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-3 mb-6">
                  <FireIcon className="h-5 w-5 text-cyan-400" />
                  استعلام جدید سهمیه سوخت
                </h2>

                <div className="space-y-4">
                  <div className="relative">
                    <label htmlFor="inquiry-driver" className="mb-2 block text-xs font-bold text-slate-300">راننده استعلام جدید</label>
                    <select id="inquiry-driver" className="field touch-target" value={selectedDriverId} disabled={submitting} onChange={event => {
                      const id = Number(event.target.value);
                      setSelectedDriverId(id);
                      changeHistoryFilters({ ...historyFilters, driverId: id ? String(id) : '' });
                    }}>
                      <option value={0}>انتخاب راننده…</option>
                      {drivers.map(driver => <option key={driver.id} value={driver.id}>{driver.full_name} — {driver.driver_national_code}</option>)}
                    </select>

                    {selectedDriver && (
                      <div className="mt-2 flex items-center justify-between rounded-xl bg-slate-900/80 border border-white/5 px-3.5 py-2.5">
                        <div className="flex items-center gap-2">
                          <TruckIcon className="h-4 w-4 text-cyan-400 shrink-0" />
                          <span className="text-[11px] text-slate-300">پلاک متصل خودرو:</span>
                        </div>
                        <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/20">
                          {selectedDriverPlate || 'بدون پلاک'}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="inquiry-year" className="block text-xs font-bold text-slate-300 mb-2">سال سهمیه (شمسی)</label>
                      <select
                        id="inquiry-year"
                        value={selectedYear}
                        onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                        disabled={submitting || loading}
                        className="field"
                      >
                        {Array.from({ length: 10 }, (_, i) => {
                          const baseYear = selectedYear && selectedYear > 1400 ? Math.max(selectedYear, 1405) : 1405;
                          return baseYear - i;
                        }).map((y) => (
                          <option key={y} value={y} className="bg-slate-900 text-white">{toPersianDigitsPreserveZero(y.toString())}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor="inquiry-month" className="block text-xs font-bold text-slate-300 mb-2">ماه سهمیه (شمسی)</label>
                      <select
                        id="inquiry-month"
                        value={selectedMonth}
                        onChange={(e) => setSelectedMonth(parseInt(e.target.value))}
                        disabled={submitting || loading}
                        className="field"
                      >
                        {[
                          { val: 1, name: 'فروردین' },
                          { val: 2, name: 'اردیبهشت' },
                          { val: 3, name: 'خرداد' },
                          { val: 4, name: 'تیر' },
                          { val: 5, name: 'مرداد' },
                          { val: 6, name: 'شهریور' },
                          { val: 7, name: 'مهر' },
                          { val: 8, name: 'آبان' },
                          { val: 9, name: 'آذر' },
                          { val: 10, name: 'دی' },
                          { val: 11, name: 'بهمن' },
                          { val: 12, name: 'اسفند' }
                        ].map((m) => (
                          <option key={m.val} value={m.val} className="bg-slate-900 text-white">{m.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {selectedDriverActiveInquiry && (
                    <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-300 flex flex-col gap-2.5 animate-in duration-200">
                      <div className="flex items-center justify-between">
                        <span className="font-bold flex items-center gap-1.5 text-[11px]">
                          <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
                          یک استعلام در حال پردازش برای این راننده وجود دارد ({formatFuelTrackingCode(selectedDriverActiveInquiry)})
                        </span>
                      </div>
                      <div className="flex gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => startPolling(selectedDriverActiveInquiry.id)}
                          className="flex-1 py-2 px-3 rounded-xl bg-cyan-500/20 text-cyan-300 font-bold hover:bg-cyan-500/30 transition text-center text-[11px]"
                        >
                          مشاهده و پایش زنده
                        </button>
                        <button
                          type="button"
                          onClick={() => handleStartInquiry(true)}
                          className="flex-1 py-2 px-3 rounded-xl bg-amber-500/20 text-amber-300 font-bold hover:bg-amber-500/30 transition text-center text-[11px]"
                        >
                          استعلام مجدد (لغو قبلی)
                        </button>
                      </div>
                    </div>
                  )}

                  <button
                    onClick={() => handleStartInquiry(selectedDriverActiveInquiry ? true : false)}
                    disabled={submitting || selectedDriverId === 0 || loading}
                    className="w-full flex items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-cyan-600 px-4 py-3.5 text-sm font-black text-slate-950 transition hover:opacity-90 active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-[0_0_35px_rgba(6,182,212,0.3)]"
                  >
                    {submitting ? (
                      <>
                        <ArrowPathIcon className="h-5 w-5 animate-spin" />
                        در حال استعلام...
                      </>
                    ) : selectedDriverActiveInquiry ? (
                      <>
                        <ArrowPathIcon className="h-5 w-5" />
                        استعلام مجدد (لغو قبلی و شروع مجدد)
                      </>
                    ) : (
                      <>
                        <FireIcon className="h-5 w-5" />
                        شروع فرآیند استعلام
                      </>
                    )}
                  </button>
                </div>
              </div>

              {activeInquiry && (activeInquiry.status === 'pending' || activeInquiry.status === 'processing' || activeInquiry.status === 'running') && (
                <div className="rounded-3xl border border-cyan-500/30 bg-slate-950 p-6 shadow-xl relative overflow-hidden animate-in fade-in duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-black text-cyan-400 uppercase tracking-wider bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-lg flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
                      در حال پردازش خودکار
                    </span>
                    <span className="text-[10px] font-bold text-slate-400 font-sans">
                      کد رهگیری: {formatFuelTrackingCode(activeInquiry)}
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-white mb-2">
                    استعلام سهمیه راننده: <strong className="text-cyan-400">{activeInquiry.driver_name || selectedDriver?.full_name}</strong>
                  </h3>
                  <p className="text-xs text-slate-400 mb-4">
                    دوره: {toPersianDigitsPreserveZero(activeInquiry.month || selectedMonth)} / {toPersianDigitsPreserveZero(activeInquiry.year || selectedYear)}
                    {activeInquiry.plate_number && (
                      <span className="mr-3 font-mono text-cyan-300 font-bold">پلاک: {activeInquiry.plate_number}</span>
                    )}
                  </p>

                  <div className="space-y-4">
                    <ProgressBar
                      value={progressPercent}
                      tone="cyan"
                      label="پیشرفت تخمینی استعلام سهمیه سوخت"
                    />
                    <div className="flex justify-between items-center text-[10px] font-sans font-medium text-slate-500">
                      <span>زمان سپری شده: {toPersianDigitsPreserveZero(elapsedTime)} ثانیه</span>
                      <span>پیشرفت تخمینی: {toPersianDigitsPreserveZero(Math.round(progressPercent))}٪</span>
                    </div>

                    <div className="pt-2 flex justify-end">
                      <button
                        type="button"
                        onClick={() => handleStartInquiry(true)}
                        className="text-xs font-bold text-amber-400 hover:text-amber-300 transition flex items-center gap-1.5 bg-amber-500/10 border border-amber-500/20 px-3 py-1.5 rounded-xl hover:bg-amber-500/20"
                      >
                        <ArrowPathIcon className="h-3.5 w-3.5" />
                        استعلام مجدد (لغو قبلی)
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {selectedDriver && (
                <div className="rounded-3xl border border-white/10 bg-slate-950 p-6 shadow-xl relative overflow-hidden animate-in duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <ClockIcon className="h-4 w-4 text-cyan-400" />
                      آخرین درخواست‌های بارنامه راننده
                    </h3>
                    <span className="text-[10px] font-bold text-slate-400 bg-slate-900 px-2 py-1 rounded-lg">
                      تا ۵ مورد اخیر
                    </span>
                  </div>

                  <Link href={`/history?driver_id=${selectedDriverId}`} className="mb-3 flex touch-target items-center text-xs font-bold text-cyan-300">مشاهده همه بارنامه‌های این راننده و انتخاب روز</Link>
                  {driverPlates.length > 0 && (
                    <div className="mb-4 bg-slate-900/50 rounded-2xl p-3 border border-white/5">
                      <span className="text-[10px] text-slate-400 font-bold block mb-1.5">پلاک‌های فعال:</span>
                      <div className="flex flex-wrap gap-2">
                        {driverPlates.map((pl) => (
                          <span key={pl.id} className="text-xs font-sans font-bold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/10">
                            {toPersianDigitsPreserveZero(pl.plate_number)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {loadingWaybills ? (
                    <div className="flex items-center justify-center py-6 text-slate-400 text-xs gap-2">
                      <ArrowPathIcon className="h-4 w-4 animate-spin text-cyan-400" />
                      در حال بارگذاری بارنامه‌ها...
                    </div>
                  ) : driverWaybills.length === 0 ? (
                    <div className="text-center py-6 text-slate-500 text-xs font-medium">
                      هیچ بارنامه‌ای برای این راننده یافت نشد.
                    </div>
                  ) : (
                    <div className="space-y-2.5 max-h-[250px] overflow-y-auto pr-1 custom-scrollbar">
                      {driverWaybills.slice(0, 10).map((wb) => {
                        let route = "مسیر نامشخص";
                        if (wb.payload_json) {
                          try {
                            const payload = typeof wb.payload_json === 'string' ? JSON.parse(wb.payload_json) : wb.payload_json;
                            if (payload && typeof payload === 'object' && 'origin' in payload && 'destination' in payload) {
                              route = `${(payload as { origin: string; destination: string }).origin} به ${(payload as { origin: string; destination: string }).destination}`;
                            }
                          } catch {
                            route = "مسیر نامشخص";
                          }
                        }

                        return (
                          <div key={wb.id} className="flex items-center justify-between p-3 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition">
                            <div className="space-y-1">
                              <span className="text-xs text-white font-bold block">{route}</span>
                              <span className="text-[9px] text-slate-400 block">{formatDateTime(wb.created_at)}</span>
                            </div>
                            <span className={`text-[9px] font-black px-2 py-0.5 rounded-lg uppercase ${
                              wb.status === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                              wb.status === 'failed' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                              'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                            }`}>
                              {wb.status === 'success' ? 'موفق' : wb.status === 'failed' ? 'ناموفق' : 'در صف'}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* LEFT PANEL: INQUIRY HISTORY TABLE WITH MULTI-FILTER TOOLBAR */}
            <div className="lg:col-span-2 space-y-4">
              <div className="rounded-3xl border border-white/10 bg-slate-950 shadow-xl overflow-hidden">
                <div className="px-6 py-5 border-b border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white/[0.01]">
                  <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-3">
                    <ClockIcon className="h-5 w-5 text-cyan-400" />
                    تاریخچه استعلام‌های سهمیه سوخت
                  </h2>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void refetchHistory()}
                      disabled={historyLoading}
                      title="بروزرسانی تاریخچه"
                      className="p-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-cyan-400 border border-white/5 transition active:scale-95 disabled:opacity-50"
                      aria-label="بروزرسانی تاریخچه استعلام‌ها"
                    >
                      <ArrowPathIcon className={`h-4 w-4 ${historyLoading ? 'animate-spin text-cyan-400' : ''}`} />
                    </button>
                    <span className="text-[10px] sm:text-xs font-bold text-slate-400 bg-slate-900 px-3 py-1 rounded-xl border border-white/5">
                      {toPersianDigitsPreserveZero(historyTotal)} رکورد
                    </span>
                  </div>
                </div>

                <div className="p-4">
                  <RecordFilters value={historyFilters} onChange={changeHistoryFilters} drivers={drivers} category="fuel" />
                </div>

                {historyError ? <ErrorState message={historyError.message} onRetry={() => void refetchHistory()} /> : historyLoading ? (
                  <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
                    <ArrowPathIcon className="h-8 w-8 animate-spin text-cyan-500" />
                    <span className="text-xs font-bold">در حال بارگذاری اطلاعات استعلام‌ها...</span>
                  </div>
                ) : filteredInquiries.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-2">
                    <FireIcon className="h-12 w-12 text-slate-600 animate-pulse" />
                    <span className="text-sm font-bold text-slate-500">هیچ استعلام سوختی با این فیلترها یافت نشد.</span>
                    <span className="text-xs text-slate-600">می‌توانید فیلترها را تغییر داده یا از پنل سمت راست استعلام جدید ثبت کنید.</span>
                  </div>
                ) : (
                  <div className="space-y-8 py-6">
                    {groupedInquiries.map((group) => (
                      <div key={group.key} className="mx-6 rounded-2xl border border-white/5 bg-slate-900/20 overflow-hidden shadow-sm">
                        <div className="bg-slate-900/40 px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5">
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="text-sm font-black text-white">راننده: {group.driverName}</span>
                            <span className="text-xs text-slate-300">روز ثبت: {toPersianDigitsPreserveZero(group.day)} (تهران)</span>
                            {group.currentName && <span className="text-xs text-amber-300">نام فعلی راننده؛ نام تاریخی ثبت نشده</span>}
                            <span className="inline-flex items-center rounded-lg bg-cyan-500/10 border border-cyan-500/25 px-2.5 py-1 text-xs font-sans font-semibold text-cyan-400">
                              پلاک: {toPersianDigitsPreserveZero(group.plateNumber)}
                            </span>
                          </div>
                          {group.clientInfo && (
                            <span className="text-xs text-cyan-400 font-bold bg-cyan-500/10 border border-cyan-500/20 px-2 py-1 rounded-lg">
                              {group.clientInfo}
                            </span>
                          )}
                        </div>

                        <div className="hidden md:block overflow-x-auto">
                          <table className="w-full border-collapse text-right min-w-[600px]">
                            <thead>
                              <tr className="border-b border-white/5 bg-white/[0.01] text-xs font-bold text-slate-400">
                                <th className="px-6 py-4">زمان درخواست / نتیجه</th>
                                <th className="px-6 py-4">دوره استعلام</th>
                                <th className="px-6 py-4">کد رهگیری</th>
                                <th className="px-6 py-4">سهمیه پایه / عملکردی</th>
                                <th className="px-6 py-4">وضعیت</th>
                                <th className="px-6 py-4">عملیات</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5 text-sm font-medium text-slate-200">
                              {group.items.map((item) => (
                                <tr key={item.id} className="hover:bg-white/[0.02] transition">
                                  <td className="px-6 py-4 text-xs font-sans font-medium text-slate-400">
                                    {formatDateTime(item.created_at)}
                                    {item.finished_at && <span className="mt-1 block text-cyan-300">دریافت نتیجه: {formatDateTime(item.finished_at)}</span>}
                                  </td>
                                  <td className="px-6 py-4 text-xs font-sans font-medium text-slate-300">
                                    {item.year && item.month ? (
                                      <span className="text-cyan-400 font-sans font-semibold">{toPersianDigitsPreserveZero(item.year.toString())}/{toPersianDigitsPreserveZero(item.month.toString().padStart(2, '0'))}</span>
                                    ) : (
                                      <span className="text-slate-500 font-sans font-semibold">جاری</span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4 text-xs font-sans font-semibold text-slate-300">
                                     {formatFuelTrackingCode(item)}
                                   </td>
                                   <td className="px-6 py-4 text-xs">
                                     {(() => {
                                       const parsed = parseQuotaData(item.quota_data);
                                       return parsed.baseQuota || parsed.performanceQuota ? (
                                         <div className="flex flex-col gap-1 font-sans font-medium text-slate-300">
                                           <span>پایه: <strong className="text-cyan-400 font-sans font-semibold">{parsed.baseQuota ? `${toPersianDigitsPreserveZero(parsed.baseQuota)} لیتر` : '۰'}</strong></span>
                                           <span>عملکردی: <strong className="text-blue-400 font-sans font-semibold">{parsed.performanceQuota ? `${toPersianDigitsPreserveZero(parsed.performanceQuota)} لیتر` : '۰'}</strong></span>
                                         </div>
                                       ) : (
                                         <span className="text-slate-500 font-sans font-semibold">—</span>
                                       );
                                     })()}
                                   </td>
                                  <td className="px-6 py-4">
                                    {item.status === 'success' && (
                                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 text-xs font-bold text-emerald-400">
                                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
                                        موفق
                                      </span>
                                    )}
                                    {item.status === 'failed' && (
                                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 px-2.5 py-1 text-xs font-bold text-rose-400">
                                        <span className="h-1.5 w-1.5 rounded-full bg-rose-400"></span>
                                        ناموفق
                                      </span>
                                    )}
                                    {item.status === 'processing' && (
                                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 text-xs font-bold text-cyan-400">
                                        <span className="relative flex h-1.5 w-1.5">
                                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                                          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500"></span>
                                        </span>
                                        در حال اجرا
                                      </span>
                                    )}
                                    {item.status === 'pending' && (
                                      <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-500/10 border border-slate-500/20 px-2.5 py-1 text-xs font-bold text-slate-400">
                                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400"></span>
                                        در انتظار صف
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4">
                                    <button
                                      onClick={() => setSelectedInquiry(item)}
                                      disabled={item.status === 'pending' || item.status === 'processing'}
                                      className="inline-flex items-center gap-1.5 rounded-xl border border-white/5 bg-slate-900 hover:bg-slate-800 px-3 py-2 text-xs font-bold text-slate-300 disabled:opacity-40 disabled:pointer-events-none transition"
                                    >
                                      <EyeIcon className="h-4 w-4" />
                                      جزئیات
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        <div className="md:hidden divide-y divide-white/5">
                          {group.items.map((item) => (
                            <FuelInquiryCard key={item.id} item={item} onSelect={setSelectedInquiry} getDriverInitials={getDriverInitials} />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                <nav aria-label="صفحه‌بندی تاریخچه سوخت" className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 p-4 text-xs text-slate-300">
                  <button type="button" disabled={historyPage <= 1 || historyLoading} onClick={() => setHistoryPage(page => page - 1)} className="touch-target rounded-xl border border-white/10 px-4 disabled:opacity-40">صفحه قبل</button>
                  <span>صفحه {toPersianDigitsPreserveZero(historyPage)} از {toPersianDigitsPreserveZero(Math.max(1, Math.ceil(historyTotal / 20)))}</span>
                  <button type="button" disabled={historyPage * 20 >= historyTotal || historyLoading} onClick={() => setHistoryPage(page => page + 1)} className="touch-target rounded-xl border border-white/10 px-4 disabled:opacity-40">صفحه بعد</button>
                </nav>
              </div>
            </div>
          </div>
        </div>

        {/* DETAILS MODAL */}
        {selectedInquiry && (
          <div id="print-modal-portal" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto" role="dialog" aria-modal="true" aria-label="جزئیات استعلام سوخت">
            <div
              id="print-modal-content"
              className="relative w-full max-w-4xl rounded-t-3xl sm:rounded-3xl border-t sm:border border-white/10 bg-slate-950 p-6 md:p-8 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col transition-all duration-300 animate-in slide-in-from-bottom-8 sm:slide-in-from-bottom-4"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-5 mb-6 relative z-10 no-print">
                <div>
                  <h3 className="text-lg sm:text-xl font-black text-white">
                    جزئیات استعلام سوخت: <span className="text-cyan-400 font-sans font-bold">{selectedInquiry.driver_name}</span>
                  </h3>
                  <p className="mt-1.5 text-xs text-slate-400 font-sans font-medium">
                    زمان استعلام: {toPersianDigitsPreserveZero(formatDateTime(selectedInquiry.created_at))}
                    {selectedInquiry.plate_number && ` | پلاک: ${toPersianDigitsPreserveZero(selectedInquiry.plate_number)}`}
                    {isAdmin && selectedInquiry.client_name && ` | مشتری: ${selectedInquiry.client_name} (${selectedInquiry.client_code})`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedInquiry(null)}
                  className="rounded-2xl border border-white/10 bg-slate-900 p-2 text-slate-400 hover:text-white hover:bg-slate-800 transition"
                  aria-label="بستن پنجره"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              {(() => {
                const parsed = parseQuotaData(selectedInquiry.quota_data);
                return (
                  <>
                    {(parsed.baseQuota || parsed.performanceQuota || parsed.cardNumber) && (
                      <div className="mb-6 grid grid-cols-2 sm:grid-cols-3 gap-3 bg-slate-900/50 p-4 rounded-2xl border border-white/5">
                        <div>
                          <span className="text-[10px] text-slate-400 block font-bold">سهمیه پایه</span>
                          <span className="text-sm font-bold text-cyan-400 mt-1 block">
                            {parsed.baseQuota ? `${toPersianDigitsPreserveZero(parsed.baseQuota)} لیتر` : '۰'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-400 block font-bold">سهمیه عملکردی</span>
                          <span className="text-sm font-bold text-blue-400 mt-1 block">
                            {parsed.performanceQuota ? `${toPersianDigitsPreserveZero(parsed.performanceQuota)} لیتر` : '۰'}
                          </span>
                        </div>
                        <div className="col-span-2 sm:col-span-1">
                          <span className="text-[10px] text-slate-400 block font-bold">شماره کارت سوخت</span>
                          <span className="text-sm font-bold text-slate-200 mt-1 block font-sans">
                            {parsed.cardNumber ? toPersianDigitsPreserveZero(parsed.cardNumber) : '—'}
                          </span>
                        </div>
                      </div>
                    )}

                    {parsed.tables.length > 0 && (
                      <div className="mb-6 space-y-4">
                        {parsed.tables.map((tbl, idx) => (
                          <div key={idx} className="bg-slate-900/40 rounded-2xl border border-white/5 overflow-hidden">
                            <div className="px-4 py-2.5 bg-white/[0.02] border-b border-white/5 text-xs font-bold text-slate-300">
                              {idx === 0 ? 'جدول سهمیه پایه' : 'جدول سهمیه عملکردی'}
                            </div>
                            <div className="overflow-x-auto">
                              <table className="w-full text-right text-xs">
                                <thead>
                                  <tr className="border-b border-white/5 text-[11px] text-slate-400">
                                    {tbl.headers.map((h, hIdx) => (
                                      <th key={hIdx} className="p-3 font-semibold">{h}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 text-slate-200">
                                  {tbl.rows.map((row, rIdx) => (
                                    <tr key={rIdx} className="hover:bg-white/[0.02]">
                                      {row.map((cell, cIdx) => (
                                        <td key={cIdx} className="p-3 font-sans">{toPersianDigitsPreserveZero(String(cell))}</td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                );
              })()}

              {selectedInquiry.screenshot_url && (
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-slate-400">تصویر مدرک استعلام پورتال:</span>
                    <a
                      href={selectedInquiry.screenshot_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 font-bold transition"
                    >
                      مشاهده تصویر در اندازه اصلی ↗
                    </a>
                  </div>
                  <div className="rounded-2xl border border-white/10 overflow-hidden max-h-80 bg-slate-900 flex items-center justify-center p-2">
                    <img src={selectedInquiry.screenshot_url} alt="اسکرین‌شات استعلام" className="w-full h-auto object-contain max-h-72 rounded-xl" />
                  </div>
                </div>
              )}

              <div className="flex justify-end pt-4 border-t border-white/10">
                <button
                  onClick={() => setSelectedInquiry(null)}
                  className="rounded-2xl bg-cyan-500 px-6 py-3 text-xs font-bold text-slate-950 hover:bg-cyan-400 transition shadow-lg"
                >
                  بستن پنجره
                </button>
              </div>
            </div>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}
