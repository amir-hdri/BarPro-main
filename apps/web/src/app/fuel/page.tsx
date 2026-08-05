'use client';
/* eslint-disable @next/next/no-img-element */

import { useCallback, useEffect, useState, useRef, useMemo, memo } from 'react';
import {
  FireIcon,
  ClockIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  EyeIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  SparklesIcon,
  ChartBarIcon,
  CheckIcon,
  UserIcon,
  FunnelIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProgressBar } from '@/components/ProgressBar';
import { api } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { useSession } from '@/hooks/useSession';
import type { Driver, FuelInquiry, WaybillJob, Plate, WaybillTaskListResponse } from '@/lib/types';
import { toast } from 'react-hot-toast';

const toPersianDigitsPreserveZero = (str: string | number): string => {
  if (str === undefined || str === null) return '';
  const map: Record<string, string> = {
    '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
    '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
  };
  return str.toString().replace(/[0-9]/g, (w) => map[w] || w);
};

const getTrackingCode = (inquiry: FuelInquiry): string => {
  const yy = inquiry.year ? inquiry.year.toString().slice(-2) : '00';
  const mm = inquiry.month ? inquiry.month.toString().padStart(2, '0') : '00';
  const idStr = inquiry.id.toString().padStart(4, '0');
  return toPersianDigitsPreserveZero(`UTC-${yy}${mm}-${idStr}`);
};



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
  const summary = item.quota_data?.summary;
  return (
    <div className="p-4 space-y-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-slate-900 border border-white/5 flex items-center justify-center text-slate-400 text-xs font-black shrink-0">
            {item.driver_name ? getDriverInitials(item.driver_name) : 'ن/م'}
          </div>
          <div>
            <span className="font-bold text-white block text-sm">{item.driver_name || 'نامشخص'}</span>
            <span className="text-[10px] text-slate-400 font-sans font-medium">کد رهگیری: {getTrackingCode(item)}</span>
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
        <div>کد رهگیری: <strong className="text-slate-200 font-sans font-semibold">{getTrackingCode(item)}</strong></div>
        <div>دوره: <strong className="text-cyan-400 font-sans font-semibold">{item.year && item.month ? `${toPersianDigitsPreserveZero(item.year.toString())}/${toPersianDigitsPreserveZero(item.month.toString().padStart(2, '0'))}` : 'جاری'}</strong></div>
        <div>پایه: <strong className="text-cyan-400 font-sans font-semibold">{summary?.base_quota ? `${toPersianDigitsPreserveZero(summary.base_quota)} لیتر` : '۰'}</strong></div>
        <div>عملکردی: <strong className="text-blue-400 font-sans font-semibold">{summary?.performance_quota ? `${toPersianDigitsPreserveZero(summary.performance_quota)} لیتر` : '۰'}</strong></div>
        <div className="col-span-2 text-[9px] text-slate-500 font-sans font-medium">زمان: {toPersianDigitsPreserveZero(formatDateTime(item.created_at))}</div>
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
  const { role } = useSession();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [inquiries, setInquiries] = useState<FuelInquiry[]>([]);
  const isAdmin = role === 'master_admin';

  const [selectedDriverId, setSelectedDriverId] = useState<number>(0);
  const [activeInquiryId, setActiveInquiryId] = useState<number | null>(null);

  const [selectedYear, setSelectedYear] = useState<number>(1403);
  const [selectedMonth, setSelectedMonth] = useState<number>(5);

  // Multi-Filter toolbar state
  const [filterDriverName, setFilterDriverName] = useState('');
  const [filterPlate, setFilterPlate] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');

  // Initialize with current Jalali date on mount
  useEffect(() => {
    const now = new Date();
    const tehranOffset = 3.5 * 60 * 60 * 1000;
    const tehranTime = new Date(now.getTime() + tehranOffset);
    const gy = tehranTime.getUTCFullYear();
    const gm = tehranTime.getUTCMonth() + 1;
    const gd = tehranTime.getUTCDate();

    let jy = gy - 621;
    let jm = 0;

    const days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 335];
    let gDayNo = 365 * (gy - 1) + Math.floor((gy - 1) / 4) - Math.floor((gy - 1) / 100) + Math.floor((gy - 1) / 400) + days[gm - 1] + gd;
    if (gm > 2 && ((gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0)) gDayNo++;

    let jDayNo = gDayNo - (365 * (jy + 620) + Math.floor((jy + 620) / 4) - Math.floor((jy + 620) / 100) + Math.floor((jy + 620) / 400)) - 79;
    if (jDayNo < 0) {
      jy--;
      jDayNo += ((jy % 33) === 1 || (jy % 33) === 5 || (jy % 33) === 9 || (jy % 33) === 13 || (jy % 33) === 17 || (jy % 33) === 22 || (jy % 33) === 26 || (jy % 33) === 30) ? 366 : 365;
    }

    if (jDayNo < 186) {
      jm = 1 + Math.floor(jDayNo / 31);
    } else {
      jm = 7 + Math.floor((jDayNo - 186) / 30);
    }

    setSelectedYear(jy);
    setSelectedMonth(jm);
  }, []);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selectedInquiry, setSelectedInquiry] = useState<FuelInquiry | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const [elapsedTime, setElapsedTime] = useState(0);

  const [driverWaybills, setDriverWaybills] = useState<WaybillJob[]>([]);
  const [driverPlates, setDriverPlates] = useState<Plate[]>([]);
  const [loadingWaybills, setLoadingWaybills] = useState(false);
  const [selectedPlateFilter, setSelectedPlateFilter] = useState<string | null>(null);

  // Filtered inquiries calculation
  const filteredInquiries = useMemo(() => {
    return inquiries.filter((item) => {
      // Driver selection in creation form (if selected)
      if (selectedDriverId > 0 && item.driver_id !== selectedDriverId) {
        return false;
      }
      // Plate filter pill
      if (selectedPlateFilter && item.plate_number !== selectedPlateFilter) {
        return false;
      }
      // Driver Name toolbar filter
      if (filterDriverName.trim()) {
        const dName = item.driver_name || '';
        if (!dName.toLowerCase().includes(filterDriverName.trim().toLowerCase())) return false;
      }
      // Plate Number toolbar filter
      if (filterPlate.trim()) {
        const pNum = item.plate_number || '';
        if (!pNum.includes(filterPlate.trim()) && !toPersianDigitsPreserveZero(pNum).includes(filterPlate.trim())) return false;
      }
      // Status filter
      if (filterStatus && item.status !== filterStatus) {
        return false;
      }
      // Date Range filter
      if (filterDateFrom) {
        if (new Date(item.created_at) < new Date(filterDateFrom)) return false;
      }
      if (filterDateTo) {
        if (new Date(item.created_at) > new Date(filterDateTo + 'T23:59:59')) return false;
      }
      return true;
    });
  }, [inquiries, selectedDriverId, selectedPlateFilter, filterDriverName, filterPlate, filterStatus, filterDateFrom, filterDateTo]);

  const stats = useMemo(() => {
    const total = filteredInquiries.length;
    const successList = filteredInquiries.filter(i => i.status === 'success');
    const success = successList.length;
    const failed = filteredInquiries.filter(i => i.status === 'failed').length;
    const rate = total > 0 ? Math.round((success / total) * 100) : 0;

    let baseSum = 0;
    let perfSum = 0;
    successList.forEach(i => {
      const baseStr = i.quota_data?.summary?.base_quota || '0';
      const perfStr = i.quota_data?.summary?.performance_quota || '0';

      const baseNum = parseInt(baseStr.replace(/[^\d]/g, ''), 10);
      const perfNum = parseInt(perfStr.replace(/[^\d]/g, ''), 10);

      if (!isNaN(baseNum)) baseSum += baseNum;
      if (!isNaN(perfNum)) perfSum += perfNum;
    });

    return {
      total,
      success,
      failed,
      rate,
      totalQuota: baseSum + perfSum
    };
  }, [filteredInquiries]);

  const groupedInquiries = useMemo(() => {
    const groups: Record<string, { driverName: string; plateNumber: string; clientInfo?: string; items: FuelInquiry[] }> = {};
    filteredInquiries.forEach((item) => {
      const driverName = item.driver_name || 'نامشخص';
      const plateNumber = item.plate_number || 'بدون پلاک';
      const key = `${driverName}-${plateNumber}`;
      if (!groups[key]) {
        let clientInfo = '';
        if (isAdmin && item.client_name) {
          clientInfo = ` (مشتری: ${item.client_name} - ${item.client_code})`;
        }
        groups[key] = {
          driverName,
          plateNumber,
          clientInfo,
          items: [],
        };
      }
      groups[key].items.push(item);
    });

    return Object.values(groups).map((group) => {
      group.items.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      return group;
    });
  }, [filteredInquiries, isAdmin]);

  // Load driver waybills and plates when a driver is picked in creation panel
  useEffect(() => {
    const controller = new AbortController();
    const fetchDriverData = async () => {
      if (selectedDriverId === 0) {
        setDriverWaybills([]);
        setDriverPlates([]);
        setSelectedPlateFilter(null);
        return;
      }
      setLoadingWaybills(true);
      setSelectedPlateFilter(null);
      try {
        const [waybillsRes, platesRes] = await Promise.all([
          api.get<WaybillTaskListResponse>('/api/v1/waybill-jobs', { driver_id: selectedDriverId, page_size: 100 }, { signal: controller.signal }),
          api.get<Plate[]>('/api/v1/plates', { driver_id: selectedDriverId }, { signal: controller.signal }),
        ]);
        if (waybillsRes.success && waybillsRes.data) {
          setDriverWaybills(waybillsRes.data.tasks || []);
        } else {
          setDriverWaybills([]);
        }
        if (platesRes.success && platesRes.data) {
          setDriverPlates(platesRes.data || []);
        } else {
          setDriverPlates([]);
        }
      } catch {
        setDriverWaybills([]);
        setDriverPlates([]);
      } finally {
        setLoadingWaybills(false);
      }
    };
    fetchDriverData();
    return () => controller.abort();
  }, [selectedDriverId]);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const pollingAttemptsRef = useRef(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Load all drivers and all fuel inquiries
  const loadData = useCallback(async (signal?: AbortSignal) => {
    if (role !== 'client' && role !== 'master_admin') {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const [driversResponse, inquiriesResponse] = await Promise.all([
        api.get<Driver[]>('/api/v1/drivers', { page_size: 1000 }, { signal }),
        api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries', { page_size: 200 }, { signal }),
      ]);

      if (driversResponse.success && driversResponse.data) {
        setDrivers(driversResponse.data);
      } else {
        setError(driversResponse.error || 'خطا در بارگذاری لیست رانندگان');
      }

      if (inquiriesResponse.success && inquiriesResponse.data) {
        setInquiries(inquiriesResponse.data.items || []);
      } else {
        setInquiries([]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'خطا در بارگذاری اطلاعات');
    } finally {
      setLoading(false);
    }
  }, [role]);

  useEffect(() => {
    const controller = new AbortController();
    void loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  useEffect(() => {
    if (submitting && activeInquiryId) {
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
  }, [submitting, activeInquiryId]);

  const startPolling = (inquiryId: number) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    setActiveInquiryId(inquiryId);
    pollingAttemptsRef.current = 0;

    pollingRef.current = setInterval(async () => {
      pollingAttemptsRef.current += 1;

      if (pollingAttemptsRef.current > MAX_POLLING_ATTEMPTS) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setActiveInquiryId(null);
        setSubmitting(false);
        return;
      }

      const response = await api.get<FuelInquiry>(`/api/v1/fuel-inquiries/${inquiryId}`);
      if (response.success && response.data) {
        const updated = response.data;

        setInquiries(prev => prev.map(item => item.id === inquiryId ? updated : item));

        if (updated.status === 'success' || updated.status === 'failed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          if (updated.status === 'success') {
            toast.success('استعلام با موفقیت تکمیل شد');
          } else if (updated.status === 'failed') {
            toast.error('استعلام با خطا مواجه شد');
          }
          setActiveInquiryId(null);
          setSubmitting(false);
          void refreshHistory();
        }
      }
    }, 3000);
  };

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  const refreshHistory = async () => {
    const inquiriesResponse = await api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries', { page_size: 200 });
    if (inquiriesResponse.success && inquiriesResponse.data) {
      setInquiries(inquiriesResponse.data.items || []);
    }
  };

  const handleStartInquiry = async () => {
    if (selectedDriverId === 0) return;
    setSubmitting(true);
    setError(null);
    setDropdownOpen(false);

    const response = await api.post<FuelInquiry>('/api/v1/fuel-inquiries', {
      driver_id: selectedDriverId,
      year: selectedYear,
      month: selectedMonth,
    });

    if (response.success && response.data) {
      const newInquiry = response.data;
      setInquiries(prev => [newInquiry, ...prev]);
      toast.success('استعلام جدید آغاز شد');
      startPolling(newInquiry.id);
    } else {
      const msg = response.error || 'خطا در ایجاد استعلام جدید';
      if (/فعال|تکرار|در جریان|duplicate/i.test(msg)) {
        setError('یک استعلام فعال برای این راننده و دوره در جریان است. لطفاً منتظر تکمیل آن بمانید.');
        toast.error('یک استعلام فعال برای این راننده و دوره در جریان است.');
      } else {
        setError(msg);
        toast.error(msg);
      }
      setSubmitting(false);
    }
  };

  const handleResetFilters = () => {
    setFilterDriverName('');
    setFilterPlate('');
    setFilterStatus('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setSelectedDriverId(0);
    setSelectedPlateFilter(null);
  };

  const activeInquiry = inquiries.find(i => i.id === activeInquiryId);
  const progressPercent = Math.min((elapsedTime / TOTAL_SECONDS_EST) * 100, 98);

  const selectedDriver = useMemo(() => {
    return drivers.find(d => d.id === selectedDriverId) || null;
  }, [drivers, selectedDriverId]);

  const filteredDrivers = useMemo(() => {
    return drivers.filter(d =>
      d.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.driver_national_code.includes(searchQuery)
    );
  }, [drivers, searchQuery]);

  useEffect(() => {
    // Reset selected inquiry to first on driver change
  }, [selectedInquiry]);

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
              <p className="mt-2 text-xs sm:text-sm text-slate-400">
                دریافت آنلاین و خودکار سهمیه‌های پایه و عملکردی خودرو از پورتال ملی UTCMS با جستجو و فیلترهای پیشرفته
              </p>
            </div>
            <button
              onClick={() => void loadData()}
              className="inline-flex items-center gap-2 self-start rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-xs font-bold text-slate-300 transition hover:bg-slate-800 hover:scale-105 active:scale-95 shadow-lg"
            >
              <ArrowPathIcon className="h-4 w-4" />
              بروزرسانی اطلاعات
            </button>
          </div>

          {error && (
            <div className="mb-6 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4 text-xs sm:text-sm font-semibold text-rose-400 backdrop-blur-md flex items-center gap-3">
              <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Metric Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6 md:mb-8">
            {[
              { label: 'کل سهمیه استعلام‌شده', value: `${toPersianDigitsPreserveZero(stats.totalQuota)} لیتر`, desc: 'مجموع سهمیه پایه و عملکردی', icon: FireIcon, color: 'text-cyan-400' },
              { label: 'درصد موفقیت ربات', value: `${toPersianDigitsPreserveZero(stats.rate)}٪`, desc: 'نرخ استعلام‌های موفق', icon: ChartBarIcon, color: 'text-emerald-400' },
              { label: 'استعلام‌های موفق', value: toPersianDigitsPreserveZero(stats.success), desc: 'تعداد تراکنش‌های موفق', icon: CheckCircleIcon, color: 'text-sky-400' },
              { label: 'تعداد کل استعلام‌ها', value: toPersianDigitsPreserveZero(stats.total), desc: 'مجموع موارد در تاریخچه', icon: ClockIcon, color: 'text-slate-400' }
            ].map((st) => (
              <div key={st.label} className="stat-card group relative overflow-hidden flex flex-col justify-between rounded-3xl border border-white/5 bg-slate-950/60 p-5 backdrop-blur-xl shadow-xl">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] sm:text-xs font-bold text-slate-400 block">{st.label}</span>
                    <span className={`text-lg sm:text-xl font-black mt-1 block ${st.color}`}>{st.value}</span>
                  </div>
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/5 border border-white/10 text-slate-300">
                    <st.icon className="h-5 w-5" />
                  </div>
                </div>
                <span className="text-[10px] text-slate-500 font-medium mt-3 block">{st.desc}</span>
              </div>
            ))}
          </div>

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
                    <label className="block text-[11px] font-black uppercase text-slate-400 mb-2">انتخاب راننده</label>
                    <button
                      type="button"
                      onClick={() => setDropdownOpen(!dropdownOpen)}
                      className="w-full flex items-center justify-between rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-right text-xs font-bold text-white outline-none hover:bg-slate-800 transition"
                    >
                      <div className="flex items-center gap-3">
                        <div className="h-7 w-7 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 flex items-center justify-center text-[10px] font-black shrink-0">
                          {selectedDriver ? getDriverInitials(selectedDriver.full_name) : <UserIcon className="h-4 w-4" />}
                        </div>
                        <span className="truncate">{selectedDriver ? selectedDriver.full_name : 'انتخاب راننده از لیست...'}</span>
                      </div>
                      <ChevronDownIcon className="h-4 w-4 text-slate-400" />
                    </button>

                    {dropdownOpen && (
                      <div className="fixed inset-0 z-10" onClick={() => setDropdownOpen(false)} />
                    )}

                    {dropdownOpen && (
                      <div className="absolute right-0 left-0 mt-2 z-20 glass-dropdown p-3 animate-in duration-200">
                        <div className="relative mb-3">
                          <MagnifyingGlassIcon className="absolute right-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                          <input
                            type="text"
                            placeholder="جستجوی نام یا کدملی راننده..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full rounded-xl border border-white/5 bg-slate-950 pr-10 pl-4 py-2.5 text-xs font-bold text-white outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
                          />
                        </div>

                        <div className="max-h-60 overflow-y-auto space-y-1 pr-1">
                          {filteredDrivers.length === 0 ? (
                            <div className="text-center py-6 text-xs text-slate-500 font-bold">موردی یافت نشد</div>
                          ) : (
                            filteredDrivers.map((d) => (
                              <button
                                key={d.id}
                                type="button"
                                onClick={() => {
                                  setSelectedDriverId(d.id);
                                  setDropdownOpen(false);
                                  setSearchQuery('');
                                }}
                                className={`w-full flex items-center justify-between rounded-xl px-3 py-2 text-right transition ${
                                  selectedDriverId === d.id ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' : 'text-slate-300 hover:bg-white/5'
                                }`}
                              >
                                <div className="flex items-center gap-3">
                                  <div className={`h-8 w-8 rounded-lg text-[10px] font-black flex items-center justify-center shrink-0 ${
                                    selectedDriverId === d.id ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-300'
                                  }`}>
                                    {getDriverInitials(d.full_name)}
                                  </div>
                                  <div>
                                    <span className="text-xs font-bold block">{d.full_name}</span>
                                    <span className="text-[9px] text-slate-400 font-sans font-medium mt-0.5 block">{toPersianDigitsPreserveZero(d.driver_national_code)}</span>
                                  </div>
                                </div>
                                {selectedDriverId === d.id && <CheckIcon className="h-4 w-4 text-cyan-400" />}
                              </button>
                            ))
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-black uppercase text-slate-400 mb-2">سال استعلام</label>
                      <select
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
                      <label className="block text-[11px] font-black uppercase text-slate-400 mb-2">ماه استعلام</label>
                      <select
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

                  <button
                    onClick={handleStartInquiry}
                    disabled={submitting || selectedDriverId === 0 || loading}
                    className="w-full flex items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-cyan-600 px-4 py-3.5 text-sm font-black text-slate-950 transition hover:opacity-90 active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-[0_0_35px_rgba(6,182,212,0.3)]"
                  >
                    {submitting ? (
                      <>
                        <ArrowPathIcon className="h-5 w-5 animate-spin" />
                        در حال استعلام...
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

              {submitting && activeInquiry && activeInquiry.driver_id === selectedDriverId && (
                <div className="rounded-3xl border border-cyan-500/20 bg-slate-950 p-6 shadow-xl relative overflow-hidden animate-in duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-black text-cyan-400 uppercase tracking-wider bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-lg">
                      در حال اجرا
                    </span>
                    <span className="text-[10px] font-bold text-slate-400 font-sans">
                      کد رهگیری: {getTrackingCode(activeInquiry)}
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-white mb-4">
                    استعلام سهمیه راننده: <strong className="text-cyan-400">{activeInquiry.driver_name || selectedDriver?.full_name}</strong>
                  </h3>

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
                  </div>
                </div>
              )}

              {selectedDriver && (
                <div className="rounded-3xl border border-white/10 bg-slate-950 p-6 shadow-xl relative overflow-hidden animate-in duration-300">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <ClockIcon className="h-4 w-4 text-cyan-400" />
                      بارنامه‌های ثبت شده راننده
                    </h3>
                    <span className="text-[10px] font-bold text-slate-400 bg-slate-900 px-2 py-1 rounded-lg">
                      تعداد کل: {toPersianDigitsPreserveZero(driverWaybills.length)}
                    </span>
                  </div>

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
                    {selectedDriverId > 0 && (
                      <button
                        type="button"
                        onClick={() => setSelectedDriverId(0)}
                        className="text-[10px] font-bold text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-3 py-1 rounded-xl hover:bg-cyan-500/20 transition flex items-center gap-1"
                      >
                        <XMarkIcon className="h-3 w-3" />
                        نمایش همه رانندگان
                      </button>
                    )}
                    <span className="text-[10px] sm:text-xs font-bold text-slate-400 bg-slate-900 px-3 py-1 rounded-xl border border-white/5">
                      {toPersianDigitsPreserveZero(filteredInquiries.length)} مورد
                    </span>
                  </div>
                </div>

                {/* MULTI-FILTER TOOLBAR */}
                <div className="p-4 border-b border-white/5 bg-slate-900/30 text-white space-y-3">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-300 mb-1">
                    <FunnelIcon className="h-4 w-4 text-cyan-400" />
                    <span>فیلتر و جستجوی پیشرفته تاریخچه سوخت</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 mb-1">نام راننده</label>
                      <input
                        type="text"
                        value={filterDriverName}
                        onChange={(e) => setFilterDriverName(e.target.value)}
                        placeholder="جستجو با نام راننده..."
                        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-xs text-white outline-none placeholder:text-slate-500 focus:border-cyan-400 transition"
                      />
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 mb-1">پلاک خودرو</label>
                      <input
                        type="text"
                        value={filterPlate}
                        onChange={(e) => setFilterPlate(e.target.value)}
                        placeholder="مثال: ۴۵ع۶۴۵"
                        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-xs text-white outline-none placeholder:text-slate-500 focus:border-cyan-400 transition"
                      />
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 mb-1">وضعیت</label>
                      <select
                        value={filterStatus}
                        onChange={(e) => setFilterStatus(e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400 transition"
                      >
                        <option value="">همه وضعیت‌ها</option>
                        <option value="success" className="bg-slate-950">موفق</option>
                        <option value="processing" className="bg-slate-950">در حال اجرا</option>
                        <option value="pending" className="bg-slate-950">در صف</option>
                        <option value="failed" className="bg-slate-950">ناموفق</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[10px] font-bold text-slate-400 mb-1">از تاریخ</label>
                      <input
                        type="date"
                        value={filterDateFrom}
                        onChange={(e) => setFilterDateFrom(e.target.value)}
                        className="w-full rounded-xl border border-white/10 bg-slate-950 px-3 py-2 text-xs text-white outline-none focus:border-cyan-400 transition"
                      />
                    </div>
                  </div>

                  {(filterDriverName || filterPlate || filterStatus || filterDateFrom || filterDateTo || selectedDriverId > 0) && (
                    <div className="flex justify-end pt-1">
                      <button
                        type="button"
                        onClick={handleResetFilters}
                        className="text-[11px] font-bold text-rose-400 hover:text-rose-300 transition flex items-center gap-1 bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 rounded-xl"
                      >
                        <XMarkIcon className="h-3.5 w-3.5" />
                        پاک کردن همه فیلترها
                      </button>
                    </div>
                  )}
                </div>

                {loading && inquiries.length === 0 ? (
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
                    {groupedInquiries.map((group, idx) => (
                      <div key={`${group.driverName}-${group.plateNumber}-${idx}`} className="mx-6 rounded-2xl border border-white/5 bg-slate-900/20 overflow-hidden shadow-sm">
                        <div className="bg-slate-900/40 px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5">
                          <div className="flex flex-wrap items-center gap-3">
                            <span className="text-sm font-black text-white">راننده: {group.driverName}</span>
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

                        <div className="hidden md:block overflow-x-auto min-w-[600px]">
                          <table className="w-full border-collapse text-right min-w-[600px]">
                            <thead>
                              <tr className="border-b border-white/5 bg-white/[0.01] text-xs font-bold text-slate-400">
                                <th className="px-6 py-4">زمان استعلام</th>
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
                                    {toPersianDigitsPreserveZero(formatDateTime(item.created_at))}
                                  </td>
                                  <td className="px-6 py-4 text-xs font-sans font-medium text-slate-300">
                                    {item.year && item.month ? (
                                      <span className="text-cyan-400 font-sans font-semibold">{toPersianDigitsPreserveZero(item.year.toString())}/{toPersianDigitsPreserveZero(item.month.toString().padStart(2, '0'))}</span>
                                    ) : (
                                      <span className="text-slate-500 font-sans font-semibold">جاری</span>
                                    )}
                                  </td>
                                  <td className="px-6 py-4 text-xs font-sans font-semibold text-slate-300">
                                    {getTrackingCode(item)}
                                  </td>
                                  <td className="px-6 py-4 text-xs">
                                    {item.quota_data?.summary?.base_quota || item.quota_data?.summary?.performance_quota ? (
                                      <div className="flex flex-col gap-1 font-sans font-medium text-slate-300">
                                        <span>پایه: <strong className="text-cyan-400 font-sans font-semibold">{item.quota_data.summary.base_quota ? `${toPersianDigitsPreserveZero(item.quota_data.summary.base_quota)} لیتر` : '۰'}</strong></span>
                                        <span>عملکردی: <strong className="text-blue-400 font-sans font-semibold">{item.quota_data.summary.performance_quota ? `${toPersianDigitsPreserveZero(item.quota_data.summary.performance_quota)} لیتر` : '۰'}</strong></span>
                                      </div>
                                    ) : (
                                      <span className="text-slate-500 font-sans font-semibold">—</span>
                                    )}
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
                  onClick={() => setSelectedInquiry(null)}
                  className="rounded-2xl border border-white/10 bg-slate-900 p-2 text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              {selectedInquiry.quota_data?.summary && (
                <div className="mb-6 grid grid-cols-2 sm:grid-cols-3 gap-3 bg-slate-900/50 p-4 rounded-2xl border border-white/5">
                  <div>
                    <span className="text-[10px] text-slate-400 block font-bold">سهمیه پایه</span>
                    <span className="text-sm font-bold text-cyan-400 mt-1 block">
                      {selectedInquiry.quota_data.summary.base_quota ? `${toPersianDigitsPreserveZero(selectedInquiry.quota_data.summary.base_quota)} لیتر` : '۰'}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block font-bold">سهمیه عملکردی</span>
                    <span className="text-sm font-bold text-blue-400 mt-1 block">
                      {selectedInquiry.quota_data.summary.performance_quota ? `${toPersianDigitsPreserveZero(selectedInquiry.quota_data.summary.performance_quota)} لیتر` : '۰'}
                    </span>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <span className="text-[10px] text-slate-400 block font-bold">شماره کارت سوخت</span>
                    <span className="text-sm font-bold text-slate-200 mt-1 block font-sans">
                      {selectedInquiry.quota_data.summary.card_number ? toPersianDigitsPreserveZero(selectedInquiry.quota_data.summary.card_number) : '—'}
                    </span>
                  </div>
                </div>
              )}

              {selectedInquiry.screenshot_url && (
                <div className="mb-6">
                  <span className="text-xs font-bold text-slate-400 block mb-2">تصویر مدرک استعلام پورتال:</span>
                  <div className="rounded-2xl border border-white/10 overflow-hidden max-h-60 bg-slate-900 flex items-center justify-center">
                    <img src={selectedInquiry.screenshot_url} alt="اسکرین‌شات استعلام" className="w-full h-auto object-contain max-h-60" />
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
