'use client';

import { useCallback, useEffect, useState, useRef, useMemo, memo } from 'react';
import {
  FireIcon,
  ClockIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  EyeIcon,

  ArrowDownTrayIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  PrinterIcon,
  SparklesIcon,
  ChartBarIcon,
  CheckIcon
} from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { api } from '@/lib/api';
import { formatDateTime, toPersianDigits } from '@/lib/format';
import { useSession } from '@/hooks/useSession';

interface Driver {
  id: number;
  full_name: string;
  driver_national_code: string;
  utcms_username: string;
  status: string;
}

interface FuelInquiry {
  id: number;
  client_id: number;
  driver_id: number;
  driver_name?: string;
  status: 'pending' | 'processing' | 'success' | 'failed';
  error_message?: string;
  quota_data?: {
    tables?: Array<{
      table_index: number;
      headers: string[];
      rows: string[][];
    }>;
    key_values?: Record<string, string>;
    summary?: {
      base_quota?: string;
      performance_quota?: string;
      card_number?: string;
    };
  };
  screenshot_url?: string;
  created_at: string;
  updated_at: string;
}

const MAX_POLLING_ATTEMPTS = 60;
const TOTAL_SECONDS_EST = 50;

const STEP_ESTIMATES = [
  { label: 'آماده‌سازی مرورگر و پروکسی', desc: 'راه‌اندازی نشست Playwright اختصاصی و تخصیص پروکسی امن' },
  { label: 'حل کپچا و ورود به پرتال', desc: 'تشخیص نوع کپچا (تیک‌باکس/ریاضی)، حل خودکار با هوش مصنوعی و ورود' },
  { label: 'بارگذاری اطلاعات سهمیه', desc: 'ناوبری هوشمند به پرتال سهمیه سوخت UTCMS و استخراج سطرها' },
  { label: 'تصویربرداری و نهایی‌سازی', desc: 'ثبت اسکرین‌شات پرتال و ذخیره‌سازی داده‌های استخراج شده در پایگاه داده' }
];

const getDriverInitials = (name: string) => {
  const parts = name.split(' ');
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`;
  return name.slice(0, 2);
};

const FuelInquiryRow = memo(function FuelInquiryRow({
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
    <tr className="hover:bg-white/[0.02] transition">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-slate-900 border border-white/5 flex items-center justify-center text-slate-400 text-xs font-black shrink-0">
            {item.driver_name ? getDriverInitials(item.driver_name) : 'ن/م'}
          </div>
          <div>
            <span className="font-bold text-white block">{item.driver_name || 'نامشخص'}</span>
            <span className="text-[10px] text-slate-500 font-mono">شناسه: #{item.id}</span>
          </div>
        </div>
      </td>
      <td className="px-6 py-4 text-xs font-mono text-slate-400">
        {formatDateTime(item.created_at)}
      </td>
      <td className="px-6 py-4 text-xs font-mono text-slate-300">
        {summary?.card_number || '—'}
      </td>
      <td className="px-6 py-4 text-xs">
        {summary?.base_quota || summary?.performance_quota ? (
          <div className="flex flex-col gap-1 font-mono">
            <span>پایه: <strong className="text-cyan-400">{summary.base_quota || '۰'}</strong></span>
            <span>عملکردی: <strong className="text-blue-400">{summary.performance_quota || '۰'}</strong></span>
          </div>
        ) : (
          <span className="text-slate-500">—</span>
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
          onClick={() => onSelect(item)}
          disabled={item.status === 'pending' || item.status === 'processing'}
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/5 bg-slate-900 hover:bg-slate-800 px-3 py-3.5 text-xs font-bold text-slate-300 disabled:opacity-40 disabled:pointer-events-none transition"
        >
          <EyeIcon className="h-4 w-4" />
          جزئیات
        </button>
      </td>
    </tr>
  );
});

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
            <span className="text-[9px] text-slate-500 font-mono">شناسه: #{item.id}</span>
          </div>
        </div>
        <div>
          {item.status === 'success' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2.5 text-[10px] font-bold text-emerald-400">
              موفق
            </span>
          )}
          {item.status === 'failed' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-2.5 text-[10px] font-bold text-rose-400">
              ناموفق
            </span>
          )}
          {item.status === 'processing' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-3 py-2.5 text-[10px] font-bold text-cyan-400">
              در حال اجرا
            </span>
          )}
          {item.status === 'pending' && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-slate-500/10 border border-slate-500/20 px-3 py-2.5 text-[10px] font-bold text-slate-400">
              در صف
            </span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400 bg-slate-900/30 p-3 rounded-2xl border border-white/5 font-mono">
        <div>کارت سوخت: <strong className="text-slate-200">{summary?.card_number || '—'}</strong></div>
        <div>زمان: <strong className="text-slate-300">{formatDateTime(item.created_at)}</strong></div>
        <div>پایه: <strong className="text-cyan-400">{summary?.base_quota || '۰'}</strong></div>
        <div>عملکردی: <strong className="text-blue-400">{summary?.performance_quota || '۰'}</strong></div>
      </div>
      <button
        onClick={() => onSelect(item)}
        disabled={item.status === 'pending' || item.status === 'processing'}
        className="w-full flex items-center justify-center gap-1.5 rounded-xl border border-white/5 bg-slate-900 hover:bg-slate-800 py-2.5 text-xs font-bold text-slate-300 disabled:opacity-40 disabled:pointer-events-none transition"
      >
        <EyeIcon className="h-4 w-4" />
        مشاهده جزئیات کامل
      </button>
    </div>
  );
});

export default function FuelInquiryPage() {
  const { role } = useSession();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [inquiries, setInquiries] = useState<FuelInquiry[]>([]);
  const [selectedDriverId, setSelectedDriverId] = useState<number>(0);
  const [activeInquiryId, setActiveInquiryId] = useState<number | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selectedInquiry, setSelectedInquiry] = useState<FuelInquiry | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [searchQuery, setSearchQuery] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  
  const [elapsedTime, setElapsedTime] = useState(0);
  
  const [lightboxOpen, setLightboxOpen] = useState(false);
  
  const [modalTabIdx, setModalTabIdx] = useState(0);

    const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const pollingAttemptsRef = useRef(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const loadData = useCallback(async () => {
    if (role !== 'client') {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    const [driversResponse, inquiriesResponse] = await Promise.all([
      api.get<Driver[]>('/api/v1/drivers'),
      api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries?page=1&page_size=30'),
    ]);

    if (driversResponse.success && driversResponse.data) {
      setDrivers(driversResponse.data);
      if (driversResponse.data.length > 0) {
        setSelectedDriverId(driversResponse.data[0].id);
      }
    } else {
      setError(driversResponse.error || 'خطا در بارگذاری لیست رانندگان');
    }

    if (inquiriesResponse.success && inquiriesResponse.data) {
      setInquiries(inquiriesResponse.data.items || []);
    }

    setLoading(false);
  }, [role]);

  useEffect(() => {
    void loadData();
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
    const inquiriesResponse = await api.get<{ items: FuelInquiry[] }>('/api/v1/fuel-inquiries?page=1&page_size=30');
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
    });

    if (response.success && response.data) {
      const newInquiry = response.data;
      setInquiries(prev => [newInquiry, ...prev]);
      startPolling(newInquiry.id);
    } else {
      setError(response.error || 'خطا در ایجاد استعلام جدید');
      setSubmitting(false);
    }
  };

  const activeInquiry = inquiries.find(i => i.id === activeInquiryId);

  const stats = useMemo(() => {
    const total = inquiries.length;
    const successList = inquiries.filter(i => i.status === 'success');
    const success = successList.length;
    const failed = inquiries.filter(i => i.status === 'failed').length;
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
  }, [inquiries]);

  const progressPercent = Math.min((elapsedTime / TOTAL_SECONDS_EST) * 100, 98);

  const activeStepIdx = useMemo(() => {
    if (elapsedTime < 10) return 0;
    if (elapsedTime < 25) return 1;
    if (elapsedTime < 40) return 2;
    return 3;
  }, [elapsedTime]);

  const selectedDriver = useMemo(() => {
    return drivers.find(d => d.id === selectedDriverId) || null;
  }, [drivers, selectedDriverId]);

  const filteredDrivers = useMemo(() => {
    return drivers.filter(d => 
      d.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.driver_national_code.includes(searchQuery)
    );
  }, [drivers, searchQuery]);

  const getTabTitle = (tbl: any, idx: number) => {
    const headersStr = (tbl.headers || []).join(' ');
    if (headersStr.includes('سهمیه') || headersStr.includes('پایه')) return 'خلاصه سهمیه';
    if (headersStr.includes('تراکنش') || headersStr.includes('تاریخ')) return 'تراکنش‌های اخیر';
    if (headersStr.includes('خودرو') || headersStr.includes('پلاک')) return 'مشخصات ناوگان';
    return `جدول جزئیات ${idx + 1}`;
  };

  useEffect(() => {
    setModalTabIdx(0);
  }, [selectedInquiry]);

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <div className="mx-auto max-w-7xl px-3 py-4 sm:px-6 sm:py-8 lg:px-8">
          <div className="mb-6 md:mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-3.5 py-1.5 text-xs font-bold text-cyan-400 border border-cyan-500/20 mb-3">
                <SparklesIcon className="h-4 w-4" />
                <span>سرویس خودکار UTCMS</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                استعلام سهمیه سوخت ناوگان
              </h1>
              <p className="mt-2 text-xs sm:text-sm text-slate-400">
                دریافت آنلاین و خودکار سهمیه‌های پایه و عملکردی خودرو از پرتال خدمات شهری UTCMS
              </p>
            </div>
            <button
              onClick={() => void loadData()}
              className="inline-flex items-center gap-2 self-start rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-xs font-bold text-slate-300 transition hover:bg-slate-800 hover:scale-105 active:scale-95 shadow-lg"
            >
              <ArrowPathIcon className="h-4 w-4" />
              بروزرسانی صفحه
            </button>
          </div>

          {error && (
            <div className="mb-6 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4 text-xs sm:text-sm font-semibold text-rose-400 backdrop-blur-md flex items-center gap-3">
              <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6 md:mb-8">
            {[
              { label: 'کل سهمیه استعلام شده', value: `${toPersianDigits(stats.totalQuota)} لیتر`, desc: 'مجموع پایه و عملکردی', icon: FireIcon, color: 'text-cyan-400', bg: 'bg-cyan-500/10 border-cyan-500/20' },
              { label: 'درصد موفقیت ربات', value: `${toPersianDigits(stats.rate)}٪`, desc: 'نرخ ورود و دریافت موفق', icon: ChartBarIcon, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
              { label: 'استعلام‌های موفق', value: toPersianDigits(stats.success), desc: 'تعداد کل واکشی‌های موفق', icon: CheckCircleIcon, color: 'text-sky-400', bg: 'bg-sky-500/10 border-sky-500/20' },
              { label: 'تعداد کل تلاش‌ها', value: toPersianDigits(stats.total), desc: 'مجموع تراکنش‌های ثبت‌شده', icon: ClockIcon, color: 'text-slate-400', bg: 'bg-slate-500/10 border-slate-500/20' }
            ].map((st) => (
              <div key={st.label} className="stat-card group relative overflow-hidden flex flex-col justify-between">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] sm:text-xs font-bold text-slate-400 block">{st.label}</span>
                    <span className="text-lg sm:text-2xl font-black text-white mt-1 sm:mt-2 block">{st.value}</span>
                  </div>
                  <div className={`p-2 rounded-xl border ${st.bg} ${st.color}`}>
                    <st.icon className="h-5 w-5" />
                  </div>
                </div>
                <span className="text-[9px] sm:text-xs text-slate-500 font-medium mt-3 block">{st.desc}</span>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-1 space-y-6">
              <div className="rounded-3xl border border-white/10 bg-slate-950 p-6 shadow-xl backdrop-blur-md relative">
                <div className="absolute inset-0 overflow-hidden rounded-3xl pointer-events-none">
                  <div className="absolute -top-20 -left-20 h-40 w-40 rounded-full bg-cyan-500/10 blur-[50px]" />
                </div>
                
                <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-3 mb-6 relative z-10">
                  <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                    <FireIcon className="h-5 w-5" />
                  </div>
                  استعلام جدید
                </h2>

                <div className="space-y-5 relative z-10">
                  <div className="relative">
                    <label className="block text-[11px] font-black uppercase text-slate-400 mb-2">انتخاب راننده</label>
                    
                    <button
                      type="button"
                      disabled={submitting || loading || drivers.length === 0}
                      onClick={() => setDropdownOpen(!dropdownOpen)}
                      className="w-full flex items-center justify-between rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-right text-white shadow-sm transition hover:bg-slate-800 focus:border-cyan-500 focus:outline-none"
                    >
                      {selectedDriver ? (
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-500 text-[11px] font-black text-slate-950 flex items-center justify-center shrink-0">
                            {getDriverInitials(selectedDriver.full_name)}
                          </div>
                          <div>
                            <span className="text-sm font-bold text-white block">{selectedDriver.full_name}</span>
                            <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">{selectedDriver.driver_national_code}</span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-sm text-slate-400 font-bold">راننده‌ای انتخاب نشده است</span>
                      )}
                      <ChevronDownIcon className="h-5 w-5 text-slate-400 shrink-0" />
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
                                    <span className="text-[9px] text-slate-400 font-mono mt-0.5 block">{d.driver_national_code}</span>
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

                  <button
                    onClick={handleStartInquiry}
                    disabled={submitting || selectedDriverId === 0 || loading}
                    className="w-full flex items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-cyan-400 to-cyan-600 px-4 py-3.5 text-sm font-black text-white transition hover:opacity-90 active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-[0_0_35px_rgba(6,182,212,0.3)]"
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

              {submitting && activeInquiry && (
                <div className="rounded-3xl border border-cyan-500/20 bg-slate-950 p-6 shadow-xl relative overflow-hidden animate-in duration-300">
                  <div className="absolute -top-10 -right-10 h-30 w-30 rounded-full bg-cyan-500/20 blur-[40px] pointer-events-none" />
                  
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-black text-cyan-400 uppercase tracking-wider bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 rounded-lg">
                      در حال اجرا
                    </span>
                    <span className="text-[10px] font-bold text-slate-400 font-mono">
                      شناسه کار: #{activeInquiry.id}
                    </span>
                  </div>

                  <h3 className="text-sm font-bold text-white mb-4">
                    استعلام سهمیه راننده: <strong className="text-cyan-400">{activeInquiry.driver_name || selectedDriver?.full_name}</strong>
                  </h3>

                  <div className="space-y-4">
                    <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-cyan-400 to-blue-500 h-full shadow-[0_0_10px_rgba(6,182,212,0.5)] transition-all duration-1000 ease-out"
                        style={{ width: `${progressPercent}%` }}
                      ></div>
                    </div>
                    <div className="flex justify-between items-center text-[10px] font-mono text-slate-500">
                      <span>زمان سپری شده: {toPersianDigits(elapsedTime)} ثانیه</span>
                      <span>پیشرفت تخمینی: {toPersianDigits(Math.round(progressPercent))}٪</span>
                    </div>
                  </div>

                  <div className="mt-6 border-r-2 border-white/5 pr-4 space-y-5">
                    {STEP_ESTIMATES.map((st, sIdx) => {
                      const isCompleted = sIdx < activeStepIdx;
                      const isActive = sIdx === activeStepIdx;
                      return (
                        <div key={st.label} className="relative">
                          <div className={`absolute -right-[23px] top-1 h-3.5 w-3.5 rounded-full border-2 transition ${
                            isCompleted ? 'bg-cyan-500 border-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.5)]' :
                            isActive ? 'bg-slate-950 border-cyan-400 animate-pulse' :
                            'bg-slate-900 border-white/10'
                          }`} />
                          
                          <div className={`${isCompleted ? 'opacity-50' : isActive ? 'opacity-100' : 'opacity-35'} transition`}>
                            <h4 className="text-xs font-black text-white">{st.label}</h4>
                            <p className="text-[10px] text-slate-400 font-medium mt-1 leading-4">{st.desc}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <div className="lg:col-span-2">
              <div className="rounded-3xl border border-white/10 bg-slate-950 shadow-xl overflow-hidden">
                <div className="px-6 py-5 border-b border-white/5 flex items-center justify-between bg-white/[0.01]">
                  <h2 className="text-base sm:text-lg font-black text-white flex items-center gap-3">
                    <ClockIcon className="h-5 w-5 text-slate-400" />
                    تاریخچه استعلام‌ها
                  </h2>
                  <span className="text-[10px] sm:text-xs font-bold text-slate-400 bg-slate-900 px-3 py-1 rounded-xl">
                    آخرین ۳۰ استعلام
                  </span>
                </div>

                {loading && inquiries.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
                    <ArrowPathIcon className="h-8 w-8 animate-spin text-cyan-500" />
                    <span className="text-xs font-bold">در حال بارگذاری اطلاعات...</span>
                  </div>
                ) : inquiries.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-2">
                    <FireIcon className="h-12 w-12 text-slate-600 animate-pulse" />
                    <span className="text-sm font-bold text-slate-500">هیچ موردی ثبت نشده است</span>
                    <span className="text-xs text-slate-600">اولین استعلام خود را با استفاده از پنل سمت راست ثبت کنید.</span>
                  </div>
                ) : (
                  <>
                    <div className="hidden md:block overflow-x-auto">
                      <table className="w-full border-collapse text-right">
                        <thead>
                          <tr className="border-b border-white/5 bg-white/[0.01] text-xs font-bold text-slate-400">
                            <th className="px-6 py-4">راننده</th>
                            <th className="px-6 py-4">زمان استعلام</th>
                            <th className="px-6 py-4">کارت سوخت</th>
                            <th className="px-6 py-4">سهمیه پایه / عملکردی</th>
                            <th className="px-6 py-4">وضعیت</th>
                            <th className="px-6 py-4">عملیات</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 text-sm font-medium text-slate-200">
                          {inquiries.map((item) => (
                            <FuelInquiryRow key={item.id} item={item} onSelect={setSelectedInquiry} getDriverInitials={getDriverInitials} />
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="md:hidden divide-y divide-white/5">
                      {inquiries.map((item) => (
                        <FuelInquiryCard key={item.id} item={item} onSelect={setSelectedInquiry} getDriverInitials={getDriverInitials} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {selectedInquiry && (
          <div id="print-modal-portal" className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto" role="dialog" aria-modal="true" aria-label="جزئیات استعلام سوخت">
            <div
              id="print-modal-content"
              className="relative w-full max-w-4xl rounded-t-3xl sm:rounded-3xl border-t sm:border border-white/10 bg-slate-950 p-6 md:p-8 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col transition-all duration-300 animate-in slide-in-from-bottom-8 sm:slide-in-from-bottom-4"
            >
              <div className="absolute -top-32 -left-32 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px] pointer-events-none no-print" />
              
              <div className="flex items-center justify-between border-b border-white/10 pb-5 mb-6 relative z-10 no-print">
                <div>
                  <h3 className="text-lg sm:text-xl font-black text-white">
                    جزئیات استعلام سوخت: <span className="text-cyan-400">{selectedInquiry.driver_name}</span>
                  </h3>
                  <p className="mt-1.5 text-xs text-slate-400 font-medium">
                    زمان استعلام: {formatDateTime(selectedInquiry.created_at)}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedInquiry(null)}
                  className="rounded-xl border border-white/10 bg-slate-900 p-3 text-slate-400 hover:text-white transition hover:scale-105 active:scale-95"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="hidden print:block border-b border-slate-300 pb-5 mb-6 text-right" dir="rtl">
                <h2 className="text-xl font-black text-black">رسید استعلام سهمیه سوخت ناوگان (سامانه BarPro)</h2>
                <div className="grid grid-cols-2 gap-4 mt-4 text-sm text-slate-700">
                  <div>نام راننده: <strong>{selectedInquiry.driver_name}</strong></div>
                  <div>کد پیگیری استعلام: <strong className="font-mono">#{selectedInquiry.id}</strong></div>
                  <div>زمان اجرای استعلام: <strong>{formatDateTime(selectedInquiry.created_at)}</strong></div>
                  <div>شماره کارت سوخت: <strong className="font-mono">{selectedInquiry.quota_data?.summary?.card_number || 'نامشخص'}</strong></div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto space-y-8 pr-1 relative z-10 text-right" dir="rtl">
                {selectedInquiry.status === 'failed' ? (
                  <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 p-5 text-sm font-bold text-rose-400 flex items-start gap-4">
                    <ExclamationTriangleIcon className="h-6 w-6 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-base font-black">فرآیند استعلام ناموفق بود</h4>
                      <p className="mt-1.5 font-medium leading-6">{selectedInquiry.error_message || 'دلیل نامشخص است.'}</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="rounded-2xl bg-white/5 border border-white/10 p-5 print:border-slate-300 print:bg-slate-50">
                        <span className="text-xs font-bold text-slate-400 print:text-slate-600 block">سهمیه پایه</span>
                        <div className="mt-2 text-2xl font-black text-white print:text-black">
                          {selectedInquiry.quota_data?.summary?.base_quota || 'پیدا نشد'}
                        </div>
                      </div>

                      <div className="rounded-2xl bg-white/5 border border-white/10 p-5 print:border-slate-300 print:bg-slate-50">
                        <span className="text-xs font-bold text-slate-400 print:text-slate-600 block">سهمیه عملکردی</span>
                        <div className="mt-2 text-2xl font-black text-cyan-400 print:text-black">
                          {selectedInquiry.quota_data?.summary?.performance_quota || 'پیدا نشد'}
                        </div>
                      </div>

                      <div className="rounded-2xl bg-white/5 border border-white/10 p-5 print:border-slate-300 print:bg-slate-50">
                        <span className="text-xs font-bold text-slate-400 print:text-slate-600 block">شماره کارت سوخت</span>
                        <div className="mt-2 text-lg font-black text-slate-300 font-mono print:text-black">
                          {selectedInquiry.quota_data?.summary?.card_number || 'نامشخص'}
                        </div>
                      </div>
                    </div>

                    {selectedInquiry.quota_data?.tables && selectedInquiry.quota_data.tables.length > 0 && (
                      <div className="space-y-4">
                        <h4 className="text-base font-black text-white print:text-black">جزئیات دریافتی پرتال</h4>
                        
                        {selectedInquiry.quota_data.tables.length > 1 && (
                          <div className="flex border-b border-white/5 gap-1.5 no-print">
                            {selectedInquiry.quota_data.tables.map((tbl, idx) => (
                              <button
                                key={getTabTitle(tbl, idx)}
                                onClick={() => setModalTabIdx(idx)}
                                className={`px-4 py-2.5 text-xs font-black transition-all border-b-2 rounded-t-lg ${
                                  modalTabIdx === idx ? 'border-cyan-400 text-cyan-400 bg-cyan-400/5' : 'border-transparent text-slate-400 hover:text-white hover:bg-white/5'
                                }`}
                              >
                                {getTabTitle(tbl, idx)}
                              </button>
                            ))}
                          </div>
                        )}

                        {selectedInquiry.quota_data.tables.map((tbl, tIdx) => {
                          const isVisible = tIdx === modalTabIdx;
                          return (
                            <div
                              key={getTabTitle(tbl, tIdx)}
                              className={`overflow-hidden rounded-2xl border border-white/10 bg-slate-900 print:border-slate-300 print:bg-white print:block ${
                                isVisible ? 'block' : 'hidden print:block'
                              }`}
                            >
                              {/* Print only label */}
                              <div className="hidden print:block bg-slate-100 px-4 py-2 border-b border-slate-300 text-xs font-bold text-slate-700">
                                {getTabTitle(tbl, tIdx)}
                              </div>
                              <div className="overflow-x-auto">
                                <table className="w-full border-collapse text-right text-xs">
                                  <thead>
                                    <tr className="bg-white/5 text-slate-300 border-b border-white/5 font-bold print:bg-slate-50 print:text-black print:border-slate-300">
                                      {tbl.headers.map((hdr) => (
                                        <th key={hdr} className="px-4 py-3">{hdr}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-white/5 text-slate-400 print:divide-slate-300 print:text-black">
                                    {tbl.rows.length === 0 ? (
                                      <tr>
                                        <td colSpan={tbl.headers.length || 1} className="px-4 py-6 text-center text-slate-500 font-bold">
                                          سطری در این جدول یافت نشد
                                        </td>
                                      </tr>
                                    ) : (
                                      tbl.rows.map((row, rIdx) => (
                                        <tr key={row.join('-')} className="hover:bg-white/[0.01]">
                                          {row.map((cell, cIdx) => (
                                            <td key={`${cIdx}-${cell}`} className="px-4 py-3 font-medium">{cell}</td>
                                          ))}
                                        </tr>
                                      ))
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {selectedInquiry.quota_data?.key_values && Object.keys(selectedInquiry.quota_data.key_values).length > 0 && (
                      <div className="space-y-4">
                        <h4 className="text-base font-black text-white print:text-black">سایر اطلاعات پرتال</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {Object.entries(selectedInquiry.quota_data.key_values).map(([k, v]) => (
                            <div key={k} className="flex justify-between items-center rounded-xl bg-white/[0.02] border border-white/5 px-4 py-3 print:border-slate-300">
                              <span className="text-xs font-bold text-slate-400 print:text-slate-600">{k}</span>
                              <span className="text-sm font-bold text-white print:text-black">{v}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {selectedInquiry.screenshot_url && (
                      <div className="space-y-4 no-print">
                        <div className="flex items-center justify-between">
                          <h4 className="text-base font-black text-white">تصویر پرتال UTCMS (اسکرین‌شات)</h4>
                          <div className="flex gap-4 flex-wrap sm:flex-nowrap">
                            <button
                              onClick={() => setLightboxOpen(true)}
                              className="inline-flex items-center gap-1.5 text-xs text-cyan-400 font-bold hover:underline"
                            >
                              <EyeIcon className="h-4 w-4" />
                              بزرگنمایی تصویر
                            </button>
                            <a
                              href={selectedInquiry.screenshot_url}
                              download={`fuel-screenshot-${selectedInquiry.id}.png`}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="inline-flex items-center gap-1.5 text-xs text-slate-400 font-bold hover:underline hover:text-white"
                            >
                              <ArrowDownTrayIcon className="h-4 w-4" />
                              دانلود مستقیم تصویر
                            </a>
                          </div>
                        </div>
                        
                        <div className="relative group overflow-hidden rounded-2xl border border-white/10 bg-slate-900 shadow-lg p-2 max-h-[400px] flex items-center justify-center">
                          <img
                            src={selectedInquiry.screenshot_url}
                            alt="UTCMS Fuel Portal Screenshot"
                            className="max-w-full max-h-[380px] object-contain rounded-lg transition-transform duration-500 group-hover:scale-105 cursor-zoom-in"
                            onClick={() => setLightboxOpen(true)}
                          />
                          <div className="absolute inset-0 bg-slate-950/60 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center gap-3 no-print">
                            <button
                              onClick={() => setLightboxOpen(true)}
                              className="p-3.5 bg-slate-900 rounded-full border border-white/10 text-cyan-400 hover:bg-slate-800 transition"
                              title="بزرگنمایی تصویر"
                            >
                              <EyeIcon className="h-5 w-5" />
                            </button>
                            <a
                              href={selectedInquiry.screenshot_url}
                              download={`fuel-screenshot-${selectedInquiry.id}.png`}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="p-3.5 bg-slate-900 rounded-full border border-white/10 text-slate-300 hover:bg-slate-800 transition"
                              title="دانلود تصویر"
                            >
                              <ArrowDownTrayIcon className="h-5 w-5" />
                            </a>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>

              <div className="mt-8 flex justify-end gap-3 border-t border-white/10 pt-5 relative z-10 no-print">
                <button
                  onClick={() => window.print()}
                  disabled={selectedInquiry.status === 'failed'}
                  className="rounded-2xl border border-white/10 bg-slate-900 hover:bg-slate-800 px-6 py-3 text-xs font-bold text-cyan-400 transition hover:scale-105 active:scale-95 flex items-center gap-2 disabled:opacity-40"
                >
                  <PrinterIcon className="h-4.5 w-4.5" />
                  چاپ رسید سهمیه
                </button>
                <button
                  onClick={() => setSelectedInquiry(null)}
                  className="rounded-2xl border border-white/10 bg-slate-900 hover:bg-slate-800 px-6 py-3 text-xs font-bold text-slate-300 transition hover:scale-105 active:scale-95"
                >
                  بستن پنجره
                </button>
              </div>
            </div>
          </div>
        )}

        {lightboxOpen && selectedInquiry?.screenshot_url && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/95 backdrop-blur-md no-print" role="dialog" aria-modal="true" aria-label="مشاهده اسکرین‌شات پرتال">
            <button
              onClick={() => setLightboxOpen(false)}
              className="absolute top-6 right-6 rounded-full bg-slate-900 p-3 text-slate-400 hover:text-white border border-white/10 transition"
            >
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <div className="max-w-5xl max-h-[90vh] overflow-auto flex items-center justify-center">
              <img
                src={selectedInquiry.screenshot_url}
                alt="Full resolution UTCMS Fuel Portal Screenshot"
                className="max-w-full max-h-[85vh] object-contain rounded-xl shadow-2xl"
              />
            </div>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}
