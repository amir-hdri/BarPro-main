"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import {
  Activity,
  Server,
  Cpu,
  RefreshCw,
  AlertTriangle,
  RotateCcw,
  Zap,
  Globe,
  Settings,
} from "lucide-react";
import toast from "react-hot-toast";

// ── Types for API responses ───────────────────────────────────────────

interface ReadyzResponse {
  status: string;
  checks: Record<string, string>;
  details: Record<string, any>;
}

interface BrowserPoolHealth {
  enabled: boolean;
  status: string;
  pool?: {
    active_contexts: number;
    idle_contexts: number;
    unhealthy_contexts: number;
    total_recycles: number;
    oldest_context_age_seconds: number;
  };
  summary?: {
    total_contexts: number;
    healthy: number;
    unhealthy: number;
    available: number;
    utilization_percent: number;
    total_errors: number;
    total_successes: number;
  };
}

interface WorkerHeartbeats {
  active: Record<string, string>;
  stalled: string[];
  stall_timeout_seconds: number;
}

interface ProxyHealthItem {
  name: string;
  url: string;
  status: "healthy" | "unhealthy" | "dead";
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
}

interface ProxyHealthResponse {
  status: string;
  proxies: ProxyHealthItem[];
}

interface CaptchaMonitorResponse {
  totals: {
    attempts: number;
    successes: number;
    failures: number;
    success_rate: number;
    failure_rate: number;
  };
  window: {
    size: number;
    sample_size: number;
    failures: number;
    failure_rate: number;
  };
  attempts_by_strategy: Record<string, number>;
  successes_by_strategy: Record<string, number>;
  failures_by_reason: Record<string, number>;
  last_failure_reason: string | null;
  alert: {
    level: string;
    high_failure_threshold: number;
    low_failure_threshold: number;
    min_samples: number;
  };
  recent_history: Array<{
    timestamp: number;
    status: string;
    strategy: string;
    reason: string | null;
    phase: string;
    confidence: number | null;
    latency_seconds: number | null;
    attempt: number | null;
  }>;
}

export default function AdminHealthPage() {
  const [activeTab, setActiveTab] = useState<"overview" | "browser" | "workers" | "proxies" | "captcha">("overview");

  // ── States ──────────────────────────────────────────────────────────
  const [readyz, setReadyz] = useState<ReadyzResponse | null>(null);
  const [browserPool, setBrowserPool] = useState<BrowserPoolHealth | null>(null);
  const [workers, setWorkers] = useState<WorkerHeartbeats | null>(null);
  const [proxies, setProxies] = useState<ProxyHealthResponse | null>(null);
  const [captcha, setCaptcha] = useState<CaptchaMonitorResponse | null>(null);

  const [loading, setLoading] = useState(false);

  // ── Diagnostics form state ──────────────────────────────────────────
  const [captchaText, setCaptchaText] = useState("");
  const [diagnoseResult, setDiagnoseResult] = useState<any>(null);
  const [diagnoseLoading, setDiagnoseLoading] = useState(false);

  // ── Fetchers ────────────────────────────────────────────────────────
  const fetchOverview = useCallback(async () => {
    const res = await api.get<ReadyzResponse>("/readyz");
    if (res.success && res.data) setReadyz(res.data);
  }, []);

  const fetchBrowserPool = useCallback(async () => {
    const res = await api.get<BrowserPoolHealth>("/browser-pool/health");
    if (res.success && res.data) setBrowserPool(res.data);
  }, []);

  const fetchWorkers = useCallback(async () => {
    const res = await api.get<WorkerHeartbeats>("/workers/heartbeats");
    if (res.success && res.data) setWorkers(res.data);
  }, []);

  const fetchProxies = useCallback(async () => {
    const res = await api.get<ProxyHealthResponse>("/proxies/health");
    if (res.success && res.data) setProxies(res.data);
  }, []);

  const fetchCaptcha = useCallback(async () => {
    const res = await api.get<CaptchaMonitorResponse>("/captcha/monitor");
    if (res.success && res.data) setCaptcha(res.data);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([
        fetchOverview(),
        fetchBrowserPool(),
        fetchWorkers(),
        fetchProxies(),
        fetchCaptcha(),
      ]);
    } catch {
      toast.error("خطا در بارگذاری اطلاعات سلامت سیستم");
    } finally {
      setLoading(false);
    }
  }, [fetchOverview, fetchBrowserPool, fetchWorkers, fetchProxies, fetchCaptcha]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Actions ─────────────────────────────────────────────────────────
  async function handleToggleCircuitBreaker(currentState: boolean) {
    const nextState = !currentState;
    const res = await api.post<any>(`/circuit-breaker/toggle?enabled=${nextState}`);
    if (res.success) {
      toast.success(nextState ? "قطع‌کننده مدار فعال شد" : "قطع‌کننده مدار غیرفعال شد");
      fetchOverview();
    } else {
      toast.error(res.error || "خطا در تغییر وضعیت قطع‌کننده مدار");
    }
  }

  async function handleHealBrowserPool() {
    const loadToast = toast.loading("در حال بازسازی استخر مرورگرها...");
    const res = await api.post<any>("/browser-pool/heal");
    toast.dismiss(loadToast);
    if (res.success) {
      toast.success(res.data?.message || "استخر مرورگرها با موفقیت بازسازی شد");
      fetchBrowserPool();
    } else {
      toast.error(res.error || "خطا در بازسازی استخر مرورگرها");
    }
  }

  async function handleRecoverStalledWorkers() {
    const loadToast = toast.loading("در حال بازیابی تسک‌های معلق...");
    const res = await api.post<any>("/workers/recover-stalled");
    toast.dismiss(loadToast);
    if (res.success) {
      toast.success(`بازیابی با موفقیت انجام شد. ${res.data?.count || 0} تسک بازیابی گردید.`);
      fetchWorkers();
    } else {
      toast.error(res.error || "خطا در بازیابی تسک‌های معلق");
    }
  }

  async function handleDiagnoseCaptcha(e: React.FormEvent) {
    e.preventDefault();
    if (!captchaText.trim()) return;
    setDiagnoseLoading(true);
    setDiagnoseResult(null);
    const res = await api.post<any>("/captcha/diagnose", { text: captchaText });
    if (res.success && res.data) {
      setDiagnoseResult(res.data);
    } else {
      toast.error(res.error || "خطا در بررسی عیب‌یابی کپچا");
    }
    setDiagnoseLoading(false);
  }

  const isCBEnabled = readyz?.details?.circuit_breaker?.status?.enabled ?? false;
  const isCBOpen = readyz?.details?.circuit_breaker?.status?.state === "open";

  return (
    <div className="space-y-6 animate-fade-in text-slate-200" dir="rtl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Server className="h-6 w-6 text-cyan-400" />
            سلامت و مانیتورینگ سیستم
          </h2>
          <p className="text-xs text-slate-400 mt-1">نظارت زنده بر منابع سیستمی، استخر مرورگر، ورکرها و پروکسی‌های خروجی</p>
        </div>
        <button
          onClick={loadAll}
          disabled={loading}
          className="flex items-center justify-center gap-2 rounded-xl bg-white/5 hover:bg-white/10 hover:text-cyan-300 px-4 py-2.5 text-sm font-medium text-slate-200 transition disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          بروزرسانی داده‌ها
        </button>
      </div>

      {/* ── Navigation Tabs ────────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1.5 rounded-xl border border-white/5 bg-slate-900/60 p-1">
        {[
          { id: "overview", label: "وضعیت کلی", icon: Activity },
          { id: "browser", label: "استخر مرورگر", icon: Cpu },
          { id: "workers", label: "ورکرها و صف‌ها", icon: Settings },
          { id: "proxies", label: "پروکسی‌های خروجی", icon: Globe },
          { id: "captcha", label: "کپچاشکن", icon: Zap },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-xs font-semibold transition-all ${
                isActive
                  ? "bg-gradient-to-r from-cyan-500/20 to-amber-400/10 text-cyan-300 border border-cyan-500/20"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200 border border-transparent"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── TAB CONTENT: OVERVIEW ───────────────────────────────────────────── */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Circuit Breaker Status Banner */}
          <div className={`rounded-2xl border p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-gradient-to-br ${
            isCBOpen 
              ? "from-red-500/10 to-red-950/20 border-red-500/20 text-red-300"
              : "from-emerald-500/10 to-emerald-950/20 border-emerald-500/20 text-emerald-300"
          }`}>
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-xl ${isCBOpen ? "bg-red-500/20" : "bg-emerald-500/20"}`}>
                <Zap className="h-6 w-6 animate-pulse" />
              </div>
              <div>
                <h3 className="text-base font-bold">وضعیت قفل مدار (ITMB Circuit Breaker)</h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed max-w-xl">
                  {isCBOpen 
                    ? "مدار قطع است! تعداد زیادی از درخواست‌ها به سامانه پایانه در زمان مقرر پاسخ نداده یا با خطا مواجه شده‌اند. جهت محافظت از منابع، درخواست‌های جدید مسدود شده‌اند."
                    : "مدار بسته و سیستم سالم است. درخواست‌ها به وب‌سرویس و درگاه بدون وقفه ارسال می‌گردند."}
                </p>
                <div className="mt-2 flex items-center gap-2 text-xs" dir="ltr">
                  <span className="text-slate-400">:وضعیت فعلی</span>
                  <strong className={`font-mono px-2 py-0.5 rounded ${isCBOpen ? "bg-red-500/20 text-red-400" : "bg-emerald-500/20 text-emerald-400"}`}>
                    {readyz?.details?.circuit_breaker?.status?.state.toUpperCase() || "CLOSED"}
                  </strong>
                  <span className="text-slate-500">|</span>
                  <span className="text-slate-400">:کلید موقت قطع‌کننده</span>
                  <strong className={isCBEnabled ? "text-emerald-400" : "text-amber-400"}>
                    {isCBEnabled ? "فعال (محافظ خودکار)" : "غیرفعال"}
                  </strong>
                </div>
              </div>
            </div>
            <button
              onClick={() => handleToggleCircuitBreaker(isCBEnabled)}
              className={`rounded-xl px-4 py-2.5 text-xs font-bold transition whitespace-nowrap ${
                isCBEnabled 
                  ? "bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/20"
                  : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/20"
              }`}
            >
              {isCBEnabled ? "غیرفعال کردن محافظت" : "فعال کردن محافظ خودکار"}
            </button>
          </div>

          {/* Checks Grid */}
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {readyz && Object.entries(readyz.checks).map(([key, status]) => {
              const info = readyz.details[key] || {};
              const isOk = status === "ok" || status === "skipped";
              const isSkipped = status === "skipped";

              return (
                <div key={key} className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold capitalize text-slate-300">{key.replace("_", " ")}</span>
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold ${
                      isSkipped 
                        ? "bg-slate-500/10 text-slate-400 border border-slate-500/20" 
                        : isOk 
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" 
                          : "bg-red-500/10 text-red-400 border border-red-500/20"
                    }`}>
                      {status.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed min-h-[32px]">{info.message || "بدون جزئیات اضافی"}</p>
                  
                  {/* Dynamic internal details */}
                  {key === "captcha_model" && info.provider && (
                    <div className="border-t border-white/5 pt-2 text-[10px] text-slate-500 flex justify-between" dir="ltr">
                      <span>موتور کپچا: <strong className="text-cyan-400">{info.provider}</strong></span>
                      <span>حالت: <strong className="text-cyan-400">{info.mode}</strong></span>
                    </div>
                  )}
                  {key === "database" && info.message && (
                    <div className="border-t border-white/5 pt-2 text-[10px] text-slate-500">
                      <span>اتصال فعال به دیتابیس PostgreSQL 16</span>
                    </div>
                  )}
                  {key === "queue" && info.broker && (
                    <div className="border-t border-white/5 pt-2 text-[10px] text-slate-500 truncate" title={info.broker} dir="ltr">
                      صف Celery: <strong className="text-cyan-400">ردیس</strong>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── TAB CONTENT: BROWSER POOL ───────────────────────────────────────── */}
      {activeTab === "browser" && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-200">وضعیت استخر مرورگرها (Playwright contexts)</h3>
                <p className="text-xs text-slate-400 mt-0.5">مدیریت نمونه‌های پس‌زمینه کرومیوم جهت افزایش بازدهی و کاهش نشت حافظه</p>
              </div>
              <button
                onClick={handleHealBrowserPool}
                className="flex items-center gap-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/20 px-3 py-1.5 text-xs transition font-semibold"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                بازسازی استخر (Heal)
              </button>
            </div>

            {browserPool ? (
              <div className="space-y-5">
                <div className="grid gap-4 grid-cols-2 md:grid-cols-4">
                  <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5">
                    <div className="text-[10px] text-slate-400">سالم / فعال</div>
                    <div className="text-2xl font-black text-emerald-400 mt-1" dir="ltr">
                      {browserPool.summary?.healthy ?? 0} <span className="text-slate-500 text-sm">/ {browserPool.summary?.total_contexts ?? 0}</span>
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5">
                    <div className="text-[10px] text-slate-400">معیوب (Unhealthy)</div>
                    <div className="text-2xl font-black text-rose-400 mt-1">
                      {browserPool.summary?.unhealthy ?? 0}
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5">
                    <div className="text-[10px] text-slate-400">درصد اشغال (Utilization)</div>
                    <div className="text-2xl font-black text-cyan-300 mt-1">
                      {browserPool.summary?.utilization_percent ?? 0}%
                    </div>
                  </div>
                  <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5">
                    <div className="text-[10px] text-slate-400">تعداد کل چرخه بازیافت (Recycle)</div>
                    <div className="text-2xl font-black text-slate-200 mt-1">
                      {browserPool.pool?.total_recycles ?? 0}
                    </div>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-800/20 border border-white/5 p-4 space-y-2">
                  <h4 className="text-xs font-semibold text-slate-300">جزئیات آماری تراکنش‌های مرورگر:</h4>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    <div className="flex justify-between py-1 border-b border-white/5">
                      <span className="text-slate-400">عملیات موفقیت‌آمیز:</span>
                      <strong className="text-emerald-400 font-mono">{browserPool.summary?.total_successes ?? 0}</strong>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/5">
                      <span className="text-slate-400">خطاهای مرورگر:</span>
                      <strong className="text-rose-400 font-mono">{browserPool.summary?.total_errors ?? 0}</strong>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/5">
                      <span className="text-slate-400">عمر قدیمی‌ترین Context:</span>
                      <strong className="text-slate-300 font-mono">{(browserPool.pool?.oldest_context_age_seconds ?? 0).toLocaleString("fa-IR")} ثانیه</strong>
                    </div>
                    <div className="flex justify-between py-1 border-b border-white/5">
                      <span className="text-slate-400">سقف مجاز حافظه V8 مرورگر:</span>
                      <strong className="text-slate-300 font-mono">1 گیگابایت</strong>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400">در حال دریافت داده‌های استخر مرورگر...</div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB CONTENT: WORKERS ────────────────────────────────────────────── */}
      {activeTab === "workers" && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-200">وضعیت ورکرهای Celery و صف تسک‌ها</h3>
                <p className="text-xs text-slate-400 mt-0.5">بررسی ورکر‌های فعال و پاکسازی خودکار تسک‌های قفل‌شده در ردیس</p>
              </div>
              <button
                onClick={handleRecoverStalledWorkers}
                className="flex items-center gap-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/20 px-3 py-1.5 text-xs transition font-semibold"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                آزاد سازی تسک‌های معلق (Recover)
              </button>
            </div>

            {workers ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-white/5 bg-slate-950/40 p-4 space-y-3">
                  <h4 className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    ورکرهای آنلاین در صف ({Object.keys(workers.active).length} ورکر)
                  </h4>
                  <div className="space-y-2">
                    {Object.entries(workers.active).map(([name, timestamp]) => (
                      <div key={name} className="flex justify-between items-center bg-slate-800/30 p-2.5 rounded-lg border border-white/5 text-xs" dir="ltr">
                        <span className="font-mono text-cyan-400">{name}</span>
                        <span className="text-slate-400">آخرین سیگنال: <strong className="text-slate-300 font-mono">{timestamp.slice(11, 19)}</strong></span>
                      </div>
                    ))}
                    {Object.keys(workers.active).length === 0 && (
                      <div className="text-center text-slate-500 py-3 text-xs">هیچ ورکری یافت نشد!</div>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-white/5 bg-slate-950/40 p-4 space-y-3">
                  <h4 className="text-xs font-semibold text-slate-300 flex items-center gap-2 text-rose-400">
                    <AlertTriangle className="h-4 w-4" />
                    تسک‌های معیوب یا قفل‌شده (Stalled Tasks)
                  </h4>
                  {workers.stalled.length > 0 ? (
                    <div className="space-y-2">
                      {workers.stalled.map((stalledId) => (
                        <div key={stalledId} className="flex justify-between items-center bg-rose-500/5 border border-rose-500/10 p-2.5 rounded-lg text-xs" dir="ltr">
                          <span className="font-mono text-rose-400">{stalledId}</span>
                          <span className="text-rose-400 font-semibold">قفل شده</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center text-slate-500 py-3 text-xs">تسک قفل‌شده‌ای در حال حاضر وجود ندارد.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400">در حال دریافت وضعیت ورکرها...</div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB CONTENT: PROXIES ────────────────────────────────────────────── */}
      {activeTab === "proxies" && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-200">وضعیت سلامت پروکسی‌های خروجی (Squid Proxies)</h3>
                <p className="text-xs text-slate-400 mt-0.5">تست کیفیت و سرعت پینگ به درگاه پایانه UTCMS از روی هر آی‌پی خروجی</p>
              </div>
            </div>

            {proxies ? (
              <div className="space-y-3">
                {proxies.proxies.map((p) => (
                  <div key={p.name} className="rounded-xl border border-white/5 bg-slate-950/40 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <strong className="text-sm text-slate-200">{p.name}</strong>
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-[9px] font-bold ${
                          p.status === "healthy"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-red-500/10 text-red-400 border border-red-500/20"
                        }`}>
                          {p.status.toUpperCase()}
                        </span>
                      </div>
                      <div className="font-mono text-xs text-slate-500" dir="ltr">{p.url}</div>
                    </div>
                    
                    <div className="flex items-center gap-4 text-xs" dir="ltr">
                      {p.latency_ms !== null && (
                        <div>
                          <span className="text-slate-400">تاخیر شبکه (Latency):</span>
                          <strong className="text-cyan-400 font-mono ml-1">{p.latency_ms} ms</strong>
                        </div>
                      )}
                      {p.status_code !== null && (
                        <div>
                          <span className="text-slate-400">کد پاسخ:</span>
                          <strong className="text-slate-300 font-mono ml-1">{p.status_code}</strong>
                        </div>
                      )}
                      {p.error && (
                        <div className="text-rose-400 text-xs truncate max-w-xs" title={p.error}>
                          خطا: {p.error}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400">در حال بررسی کیفیت اتصال پروکسی‌ها...</div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB CONTENT: CAPTCHA ────────────────────────────────────────────── */}
      {activeTab === "captcha" && (
        <div className="space-y-6">
          <div className="grid gap-6 grid-cols-1 lg:grid-cols-2">
            
            {/* Live Stats */}
            <div className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-4">
              <h3 className="text-base font-bold text-slate-200 border-b border-white/5 pb-3">کارآیی مدل‌های کپچاشکن</h3>
              
              {captcha ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5 text-center">
                      <div className="text-[10px] text-slate-400">کل تلاش‌های کپچا</div>
                      <div className="text-2xl font-black text-slate-200 mt-1">{(captcha.totals.attempts).toLocaleString("fa-IR")}</div>
                    </div>
                    <div className="rounded-xl bg-slate-800/30 p-4 border border-white/5 text-center">
                      <div className="text-[10px] text-slate-400 font-semibold text-emerald-400">دقت حل زنده (موفقیت)</div>
                      <div className="text-2xl font-black text-emerald-400 mt-1">{Math.round(captcha.totals.success_rate * 100)}%</div>
                    </div>
                  </div>

                  <div className="space-y-2 text-xs">
                    <h4 className="font-semibold text-slate-300">تفکیک استفاده از استراتژی‌ها:</h4>
                    {Object.entries(captcha.attempts_by_strategy).map(([strategy, count]) => {
                      const successCount = captcha.successes_by_strategy[strategy] || 0;
                      const rate = count > 0 ? Math.round((successCount / count) * 100) : 0;
                      return (
                        <div key={strategy} className="flex items-center justify-between bg-slate-850 p-2 rounded border border-white/5" dir="ltr">
                          <span className="font-mono text-cyan-400">{strategy}</span>
                          <span className="text-slate-400">
                            استفاده: <strong className="text-slate-200">{count}</strong> | دقت: <strong className="text-emerald-400">{rate}%</strong>
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center text-slate-400">در حال دریافت داده‌های مانیتورینگ کپچا...</div>
              )}
            </div>

            {/* Diagnostics Form */}
            <div className="rounded-2xl border border-white/5 bg-slate-900/40 p-5 space-y-4">
              <h3 className="text-base font-bold text-slate-200 border-b border-white/5 pb-3">تست زنده عیب‌یابی موتور کپچا</h3>
              
              <form onSubmit={handleDiagnoseCaptcha} className="space-y-4">
                <div>
                  <label className="block text-xs text-slate-400 mb-1.5">متن خروجی یا عبارت کپچا جهت راستی‌آزمایی ریاضی:</label>
                  <input
                    type="text"
                    value={captchaText}
                    onChange={(e) => setCaptchaText(e.target.value)}
                    placeholder="مثلا 2+3 یا یک عبارت متنی"
                    className="w-full rounded-xl border border-white/10 bg-slate-900/60 px-4 py-3 text-sm text-slate-200 placeholder:text-slate-500 focus:border-cyan-400 outline-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={diagnoseLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950 font-bold py-3 text-sm transition hover:brightness-110 disabled:opacity-50"
                >
                  {diagnoseLoading ? "در حال پردازش تست..." : "شروع ارزیابی و استعلام"}
                </button>
              </form>

              {diagnoseResult && (
                <div className="rounded-xl bg-slate-950/60 border border-white/5 p-4 space-y-2 text-xs" dir="ltr">
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">نتیجه حل ریاضی:</span>
                    <strong className="text-cyan-400 font-mono">{diagnoseResult.solved_value || "—"}</strong>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">درجه اطمینان (Confidence):</span>
                    <strong className="text-cyan-400 font-mono">{Math.round(diagnoseResult.confidence * 100)}%</strong>
                  </div>
                  <div className="flex justify-between border-b border-white/5 pb-1">
                    <span className="text-slate-400">استراتژی حل:</span>
                    <strong className="text-slate-200 font-mono">{diagnoseResult.strategy}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">تایید نهایی پذیرش (Accepted):</span>
                    <span className={`font-semibold ${diagnoseResult.accepted ? "text-emerald-400" : "text-rose-400"}`}>
                      {diagnoseResult.accepted ? "تایید شده" : "رد شده"}
                    </span>
                  </div>
                </div>
              )}
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
