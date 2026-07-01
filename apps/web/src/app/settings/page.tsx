'use client';

import { memo, useEffect, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, toPersianDigits } from '@/lib/format';
import type { ClientProfile, ReadyzResponse } from '@/lib/types';
import { useSession } from "@/hooks/useSession";
import { 
  Settings, 
  Shield, 
  Activity, 
  RefreshCw, 
  Check, 
  AlertCircle, 
  Database, 
  Cpu, 
  Layers, 
  Lock,
  Server
} from 'lucide-react';

interface CacheItem {
  cached: boolean;
  count: number;
  last_updated?: string | null;
  is_stale?: boolean;
}

interface CacheStatus {
  status: string;
  meta: {
    cache_ttl_seconds: number;
    validation_enabled: boolean;
    live_probe_enabled: boolean;
  };
  items: Record<string, CacheItem>;
}

interface CircuitBreakerStatus {
  state: string;
  failure_count: number;
  retry_after_seconds: number;
  enabled: boolean;
}

export default function SettingsPage() {
  const { role } = useSession();
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [activeTab, setActiveTab] = useState<'account' | 'system'>('account');
  const [error, setError] = useState<string | null>(null);

  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
  const [circuitStatus, setCircuitStatus] = useState<CircuitBreakerStatus | null>(null);
  const [loadingCache, setLoadingCache] = useState(false);
  const [refreshingCache, setRefreshingCache] = useState(false);
  const [togglingCB, setTogglingCB] = useState(false);
  const [systemMessage, setSystemMessage] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      if (role !== "client") return;

      const response = await api.get<ClientProfile>('/api/v1/auth/me');
      if (!response.success || !response.data) {
        setError(response.error || 'پروفایل مشتری بارگذاری نشد');
        return;
      }
      setProfile(response.data);
    }

    loadProfile();
  }, [role]);

  const loadSystemStatus = async () => {
    if (role !== "client") return;
    setLoadingCache(true);
    
    const cacheRes = await api.get<CacheStatus>('/waybill/baseinfo/status');
    if (cacheRes.success && cacheRes.data) {
      setCacheStatus(cacheRes.data);
    }

    const readyzRes = await api.get<ReadyzResponse>('/readyz');
    if (readyzRes.success && readyzRes.data) {
      const cb = readyzRes.data?.details?.circuit_breaker?.status;
      if (cb) {
        setCircuitStatus({
          state: cb.state,
          failure_count: cb.failure_count,
          retry_after_seconds: cb.retry_after_seconds,
          enabled: cb.enabled,
        });
      }
    }
    setLoadingCache(false);
  };

  useEffect(() => {
    if (activeTab === 'system') {
      void loadSystemStatus().catch(e => console.error("Failed to load system status:", e));
    }
  }, [activeTab]);

  const handleRefreshCache = async () => {
    setRefreshingCache(true);
    setSystemMessage(null);
    
    const response = await api.post('/waybill/baseinfo/refresh', {});
    if (response.success) {
      setSystemMessage('کش اطلاعات پایه وب‌سرویس ITMB با موفقیت بروزرسانی شد.');
      void loadSystemStatus().catch(e => console.error("Failed to load system status:", e));
    } else {
      setSystemMessage(`بروزرسانی کش ناموفق بود: ${response.error || 'خطای سرور'}`);
    }
    setRefreshingCache(false);
  };

  const handleToggleCircuitBreaker = async (currentEnabled: boolean) => {
    setTogglingCB(true);
    setSystemMessage(null);
    const targetEnabled = !currentEnabled;
    const response = await api.post(`/circuit-breaker/toggle?enabled=${targetEnabled}`, {});
    if (response.success) {
      setSystemMessage(`سیستم قطع‌کننده مدار با موفقیت ${targetEnabled ? 'فعال' : 'غیرفعال'} شد.`);
      void loadSystemStatus().catch(e => console.error("Failed to load system status:", e));
    } else {
      setSystemMessage(`خطا در تغییر وضعیت قطع‌کننده مدار: ${response.error || 'خطای سرور'}`);
    }
    setTogglingCB(false);
  };

  const getCacheKeyLabel = (key: string) => {
    const map: Record<string, string> = {
      goods: 'کالاهای تعریف شده',
      packing_types: 'انواع بسته‌بندی',
      origins: 'مبداهای مجاز',
      destinations: 'مقصدهای مجاز',
      plaque_types: 'انواع پلاک‌ها',
    };
    return map[key] || key;
  };

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <div className="mx-auto max-w-7xl px-3 py-4 sm:px-6 sm:py-8 lg:px-8">
          
          <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <h1 className="text-3xl font-black text-white bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                پیکربندی و تنظیمات سیستم
              </h1>
              <p className="mt-2 text-sm text-slate-400">
                مدیریت اشتراک، کنترل وضعیت کش وب‌سرویس و پایش لحظه‌ای پایداری سیستم
              </p>
            </div>
          </div>

          <div className="mb-8 flex border-b border-white/5 pb-2 gap-6">
            <button
              onClick={() => setActiveTab('account')}
              className={`flex items-center gap-2 pb-4 py-3 text-sm font-bold transition-all relative ${
                activeTab === 'account' ? 'text-cyan-400' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Lock className="h-4 w-4" />
              <span>مشخصات حساب و اشتراک</span>
              {activeTab === 'account' && (
                <span className="absolute bottom-0 right-0 left-0 h-0.5 bg-cyan-400 rounded-full animate-fade-in" />
              )}
            </button>
            <button
              onClick={() => setActiveTab('system')}
              className={`flex items-center gap-2 pb-4 py-3 text-sm font-bold transition-all relative ${
                activeTab === 'system' ? 'text-cyan-400' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Cpu className="h-4 w-4" />
              <span>مدیریت کش و پایداری سیستم</span>
              {activeTab === 'system' && (
                <span className="absolute bottom-0 right-0 left-0 h-0.5 bg-cyan-400 rounded-full animate-fade-in" />
              )}
            </button>
          </div>

          {activeTab === 'account' && (
            <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr] animate-in fade-in duration-300">
              <div className="rounded-[2.5rem] border border-white/10 bg-slate-950 p-8 text-white shadow-2xl relative overflow-hidden">
                <div className="absolute -left-20 -top-20 h-40 w-40 rounded-full bg-cyan-500/10 blur-[50px]" />
                <h2 className="text-2xl font-black flex items-center gap-3 relative z-10">
                  <Server className="h-6 w-6 text-cyan-400" />
                  حساب کاربری مشتری
                </h2>
                <p className="mt-4 text-sm leading-7 text-slate-300 relative z-10">
                  این بخش به پرتال اصلی احراز هویت متصل است و ظرفیت مجاز عملیاتی و حجم تراکنش‌ها را به صورت مستقیم از بک‌اند دریافت می‌کند.
                </p>
                <div className="mt-8 space-y-4 text-sm text-slate-300 relative z-10 border-t border-white/5 pt-6">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">وضعیت حساب مشتری</span>
                    <span className="font-bold text-white bg-cyan-500/10 border border-cyan-500/20 px-3 py-1 rounded-xl">
                      {profile ? statusLabel(profile.status) : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">آخرین ورود به سیستم</span>
                    <span className="font-bold text-white font-mono">
                      {profile ? formatDateTime(profile.last_login_at) : '-'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">تاریخ ثبت نام مجموعه</span>
                    <span className="font-bold text-white font-mono">
                      {profile ? formatDateTime(profile.created_at) : '-'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-[2.5rem] border border-white/5 bg-slate-900/40 backdrop-blur-xl p-8 shadow-2xl text-white">
                <h2 className="text-2xl font-black text-white flex items-center gap-3">
                  <Shield className="h-6 w-6 text-cyan-400" />
                  اشتراک و سقف‌های مصرف
                </h2>
                {profile ? (
                  <div className="mt-8 grid gap-4 sm:grid-cols-2">
                    <InfoCard label="نام مجموعه" value={profile.name} />
                    <InfoCard label="کد اختصاصی مشتری" value={profile.client_code} />
                    <InfoCard label="پست الکترونیک" value={profile.email} />
                    <InfoCard label="تلفن همراه" value={profile.phone || 'ثبت نشده'} />
                    <InfoCard label="سقف ناوگان (راننده)" value={toPersianDigits(profile.max_drivers)} />
                    <InfoCard label="پردازش همزمان (Concurrent)" value={toPersianDigits(profile.max_concurrent_tasks)} />
                    <InfoCard label="سقف مجاز روزانه" value={toPersianDigits(profile.max_daily_tasks)} />
                    <InfoCard label="وضعیت عملیاتی اشتراک" value={statusLabel(profile.status)} />
                  </div>
                ) : (
                  <div className="mt-8 flex items-center justify-center rounded-3xl border border-dashed border-white/5 bg-slate-950/20 py-20 text-sm text-slate-400">
                    <RefreshCw className="h-6 w-6 animate-spin text-cyan-400 mr-2" />
                    <span>در حال بارگذاری مشخصات مشتری...</span>
                  </div>
                )}
                {error && (
                  <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400 flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 shrink-0" />
                    <p>{error}</p>
                  </div>
                )}
              </div>
            </section>
          )}

          {activeTab === 'system' && (
            <div className="space-y-8 animate-in fade-in duration-300">
              
              <section className="grid gap-6 md:grid-cols-3">
                <div className="md:col-span-2 rounded-[2.5rem] border border-white/5 bg-slate-900/40 backdrop-blur-xl p-8 text-white shadow-2xl relative overflow-hidden">
                  <div className="absolute -left-20 -top-20 h-40 w-40 rounded-full bg-emerald-500/10 blur-[50px] pointer-events-none" />
                  
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-white/5 pb-6 mb-6">
                    <div>
                      <h2 className="text-xl font-black flex items-center gap-3">
                        <Activity className="h-6 w-6 text-cyan-400" />
                        قطع‌کننده مدار وب‌سرویس (Circuit Breaker)
                      </h2>
                      <p className="text-xs text-slate-400 mt-1">مانیتورینگ خودکار پایداری و سلامت ارتباط با پرتال UTCMS</p>
                    </div>
                    {circuitStatus && (
                      <span className={`inline-flex items-center rounded-xl px-4 py-2 text-xs font-black shadow-sm border ${
                        circuitStatus.state === 'closed' 
                          ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' 
                          : circuitStatus.state === 'open' 
                          ? 'bg-rose-500/10 border-rose-500/20 text-rose-400' 
                          : 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                      }`}>
                        وضعیت: {circuitStatus.state === 'closed' ? 'سالم (Closed)' : circuitStatus.state === 'open' ? 'قطع شده (Open)' : 'تست مجدد (Half-Open)'}
                      </span>
                    )}
                  </div>

                  {circuitStatus ? (
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="bg-slate-950/60 border border-white/5 rounded-3xl p-5 flex flex-col justify-between">
                        <div>
                          <p className="text-xs text-slate-400">وضعیت پایش</p>
                          <p className="mt-2 text-lg font-black text-white">{circuitStatus.enabled ? 'فعال خودکار' : 'غیرفعال'}</p>
                        </div>
                        <button
                          type="button"
                          disabled={togglingCB}
                          onClick={() => void handleToggleCircuitBreaker(circuitStatus.enabled)}
                          className={`mt-4 w-full rounded-xl px-4 py-3.5 text-[10px] sm:text-xs font-bold transition-all active:scale-95 text-center ${
                            circuitStatus.enabled 
                              ? 'bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20' 
                              : 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20'
                          }`}
                        >
                          {togglingCB ? 'در حال تغییر...' : (circuitStatus.enabled ? 'غیرفعال کردن' : 'فعال کردن')}
                        </button>
                      </div>
                      <div className="bg-slate-950/60 border border-white/5 rounded-3xl p-5">
                        <p className="text-xs text-slate-400">تعداد خطاهای متوالی</p>
                        <p className="mt-3 text-lg font-black text-white">{toPersianDigits(circuitStatus.failure_count)} خطای ثبت‌شده</p>
                      </div>
                      <div className="bg-slate-950/60 border border-white/5 rounded-3xl p-5">
                        <p className="text-xs text-slate-400">زمان بازیابی باقیمانده</p>
                        <p className="mt-3 text-lg font-black text-white font-mono">
                          {circuitStatus.retry_after_seconds > 0 
                            ? `${toPersianDigits(Math.round(circuitStatus.retry_after_seconds))} ثانیه` 
                            : 'ارتباط مستقیم'
                          }
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="py-8 text-center text-slate-400">در حال بارگذاری وضعیت مدار...</div>
                  )}
                </div>

                <div className="rounded-[2.5rem] border border-white/10 bg-slate-950 p-8 text-white shadow-2xl relative overflow-hidden flex flex-col justify-between">
                  <div className="absolute -left-20 -top-20 h-40 w-40 rounded-full bg-cyan-500/5 blur-[50px] pointer-events-none" />
                  <div>
                    <h2 className="text-lg font-black flex items-center gap-3">
                      <Database className="h-5 w-5 text-cyan-400" />
                      عملیات دستی کش
                    </h2>
                    <p className="mt-3 text-xs leading-6 text-slate-400">
                      پایگاه داده به طور خودکار اطلاعات پایه وب‌سرویس UTCMS (مانند مبداها، مقصدها و کالاها) را کش می‌کند. در صورت ایجاد تغییر در سامانه کشوری، می‌توانید کش سیستم را به صورت دستی بروزرسانی کنید.
                    </p>
                  </div>
                  <div className="mt-6">
                    <button
                      onClick={handleRefreshCache}
                      disabled={refreshingCache}
                      className="w-full flex items-center justify-center gap-2 rounded-2xl bg-cyan-500 px-6 py-3.5 text-sm font-bold text-slate-950 transition hover:bg-cyan-400 active:scale-95 disabled:opacity-50 shadow-[0_10px_20px_-10px_rgba(6,182,212,0.4)] min-h-[44px]"
                    >
                      <RefreshCw className={`h-4 w-4 ${refreshingCache ? 'animate-spin' : ''}`} />
                      <span>{refreshingCache ? 'در حال بروزرسانی...' : 'بارگذاری مجدد کش اطلاعات پایه'}</span>
                    </button>
                  </div>
                </div>
              </section>

              {systemMessage && (
                <div className="rounded-2xl bg-cyan-500/10 border border-cyan-500/20 px-6 py-4 text-sm text-cyan-400 flex items-center gap-3 animate-in slide-in-from-bottom-4 shadow-md">
                  <Check className="h-5 w-5 shrink-0" />
                  <span>{systemMessage}</span>
                </div>
              )}

              <section className="rounded-[2.5rem] border border-white/5 bg-slate-900/40 backdrop-blur-xl p-8 text-white shadow-2xl">
                <div className="border-b border-white/5 pb-6 mb-6">
                  <h2 className="text-xl font-black flex items-center gap-3">
                    <Layers className="h-6 w-6 text-cyan-400" />
                    جزئیات داده‌های کش شده
                  </h2>
                  <p className="text-xs text-slate-400 mt-1">لیست جداول اطلاعات پایه بارگذاری شده در سیستم</p>
                </div>

                {loadingCache ? (
                  <div className="py-12 flex items-center justify-center text-slate-400">
                    <RefreshCw className="h-6 w-6 animate-spin text-cyan-400 mr-2" />
                    <span>در حال واکشی اطلاعات جداول...</span>
                  </div>
                ) : cacheStatus ? (
                  <div className="overflow-hidden rounded-2xl border border-white/5 bg-slate-950/40">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="border-b border-white/5 bg-slate-950/80">
                          <tr>
                            <th className="px-6 py-4 text-right font-bold text-slate-300">نوع داده</th>
                            <th className="px-6 py-4 text-right font-bold text-slate-300">وضعیت کش</th>
                            <th className="px-6 py-4 text-right font-bold text-slate-300">تعداد آیتم‌ها</th>
                            <th className="px-6 py-4 text-right font-bold text-slate-300">آخرین بروزرسانی</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(cacheStatus.items).map(([key, item]) => (
                            <tr key={key} className="border-b border-white/5 transition-colors hover:bg-white/5">
                              <td className="px-6 py-4 text-slate-200 font-bold">{getCacheKeyLabel(key)}</td>
                              <td className="px-6 py-4">
                                <span className={`inline-flex rounded-xl px-3 py-1 text-xs font-bold ${
                                  item.cached && !item.is_stale
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                                }`}>
                                  {item.cached ? (item.is_stale ? 'منقضی شده' : 'کش شده') : 'خالی'}
                                </span>
                              </td>
                              <td className="px-6 py-4 text-slate-200 font-mono">{toPersianDigits(item.count)} آیتم</td>
                              <td className="px-6 py-4 text-slate-400 font-mono">
                                {item.last_updated ? formatDateTime(item.last_updated) : 'ثبت نشده'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="py-12 text-center text-slate-400">خطا در بارگذاری جزئیات کش</div>
                )}
              </section>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  );
}

const InfoCard = memo(function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-3xl bg-slate-950/60 p-6 border border-white/5 shadow-sm group hover:border-cyan-500/20 transition-all duration-300">
      <p className="text-xs text-slate-400 font-medium">{label}</p>
      <p className="mt-3 text-base font-bold text-white group-hover:text-cyan-400 transition-colors">{value}</p>
    </article>
  );
});
