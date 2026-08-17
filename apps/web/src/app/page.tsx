"use client";

import { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { EmptyState, ErrorState, Skeleton } from "@/components/layout/States";
import { ProgressBar } from "@/components/ProgressBar";
import { useSession } from "@/hooks/useSession";
import { useWaybillJob } from "@/hooks/useWaybillJob";
import { confirmedTrackingCode, formatDateTime, statusLabel, statusTone, toPersianDigits, trackingCodeFromResult } from "@/lib/format";
import type { ClientStats, WaybillJob } from "@/lib/types";
import {
  ClockIcon,
  TruckIcon,
  CheckCircleIcon,
  XCircleIcon,
  UsersIcon,
  QueueListIcon,
  FireIcon,
  ChartBarIcon,
} from "@heroicons/react/24/outline";
import { XCircle, Zap, ShieldCheck } from "lucide-react";

export default function DashboardPage() {
  const { client } = useSession();
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { lastEvent } = useWaybillJob();

  const {
    data: stats = {
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
    } as ClientStats,
    isLoading: statsLoading,
    isError: statsFailed,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ["client-stats"],
    queryFn: async () => {
      const res = await api.get<ClientStats>("/api/v1/auth/stats");
      if (!res.success || !res.data) {
        throw new Error(res.error || "Query data cannot be undefined");
      }
      return res.data;
    },
    staleTime: 30000,
    gcTime: 60000,
    enabled: !!client,
  });

  const {
    data: recentJobs = [] as WaybillJob[],
    isLoading,
    isError: jobsFailed,
    refetch: refetchJobs,
  } = useQuery({
    queryKey: ["recent-jobs"],
    queryFn: async () => {
      const res = await api.get<{ tasks: WaybillJob[] }>(
        "/api/v1/waybill-jobs?page=1&page_size=5"
      );
      if (!res.success || !res.data) {
        return [];
      }
      return (res.data && Array.isArray(res.data.tasks)) ? res.data.tasks : [];
    },
    staleTime: 30000,
    gcTime: 60000,
    enabled: !!client,
  });

  // Auto refetch stats and jobs on real-time event
  useEffect(() => {
    if (lastEvent) {
      void refetchJobs();
      void refetchStats();
    }
  }, [lastEvent, refetchJobs, refetchStats]);

  async function handleRetry(jobId: string) {
    setRetryingJobId(jobId);
    setError(null);
    const res = await api.post(`/api/v1/waybill-jobs/${jobId}/retry`, {});
    setRetryingJobId(null);
    if (!res.success) {
      setError(res.error || "خطا در ارسال مجدد درخواست");
    } else {
      void refetchJobs().catch(e => console.error("Failed to refetch jobs:", e));
      void refetchStats().catch(e => console.error("Failed to refetch stats:", e));
    }
  }

  const cards = useMemo(
    () => [
      {
        label: "رانندگان فعال",
        value: `${toPersianDigits(stats.active_drivers)} / ${toPersianDigits(stats.total_drivers)}`,
        icon: UsersIcon,
        hint: "تعداد رانندگان دارای توکن فعال به کل",
        color: "text-cyan-400",
        bg: "bg-cyan-500/10 border-cyan-500/20",
        glow: "bg-cyan-400",
      },
      {
        label: "کل بارنامه‌ها",
        value: toPersianDigits(stats.total_jobs),
        icon: QueueListIcon,
        hint: "مجموع درخواست‌های ثبت شده در سیستم",
        color: "text-blue-400",
        bg: "bg-blue-500/10 border-blue-500/20",
        glow: "bg-blue-400",
      },
      {
        label: "ثبت‌های موفق",
        value: toPersianDigits(stats.success_jobs),
        icon: CheckCircleIcon,
        hint: "بارنامه‌های با موفقیت صادر شده",
        color: "text-emerald-400",
        bg: "bg-emerald-500/10 border-emerald-500/20",
        glow: "bg-emerald-400",
      },
      {
        label: "ناموفق / نیازمند بازبینی",
        value: toPersianDigits(stats.failed_jobs + stats.pending_jobs),
        icon: XCircleIcon,
        hint: "درخواست‌های ناموفق یا متوقف شده",
        color: "text-amber-400",
        bg: "bg-amber-500/10 border-amber-500/20",
        glow: "bg-amber-400",
      },
    ],
    [stats],
  );

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <section className="grid gap-6 sm:gap-8 xl:grid-cols-[1.3fr_0.7fr] mb-8 md:mb-12">
          <div className="relative overflow-hidden rounded-[2.5rem] lg:rounded-[3.5rem] border border-white/10 bg-slate-900/40 backdrop-blur-2xl px-6 py-8 sm:px-10 sm:py-12 lg:px-12 lg:py-16 shadow-2xl transition-all hover:border-white/20">
            <div className="absolute -right-32 -top-32 h-96 w-96 rounded-full bg-gradient-to-br from-cyan-400/10 to-blue-500/10 blur-[100px] animate-pulse-glow"></div>
            <div className="relative z-10">
              <span className="inline-flex items-center gap-2 rounded-2xl bg-cyan-500/10 px-4 py-2 text-[11px] font-black uppercase text-cyan-400 border border-cyan-500/20 shadow-sm animate-in fade-in slide-in-from-bottom-4">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
                </span>
                نمای کلی داشبورد عملیات
              </span>
              <h1 className="mt-6 lg:mt-10 text-4xl md:text-5xl lg:text-6xl font-black leading-[1.1] tracking-tight text-white animate-in fade-in slide-in-from-bottom-6">
                مدیریت هوشمند <br className="hidden sm:block" />
                <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-500 bg-clip-text text-transparent">عملیات بارنامه</span>
              </h1>
              <p className="mt-4 lg:mt-6 max-w-xl text-sm md:text-base lg:text-lg leading-relaxed text-slate-300 font-medium animate-in fade-in slide-in-from-bottom-8">
                سیستم جامع مانیتورینگ ناوگان، استعلام خودکار سهمیه سوخت و ثبت آنلاین بارنامه‌ها با بالاترین سرعت و پایداری.
              </p>
              <div className="mt-8 md:mt-10 flex flex-wrap gap-4 animate-in fade-in slide-in-from-bottom-10">
                 <Link
                   href="/new"
                   className="group relative flex-1 sm:flex-none inline-flex items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-r from-cyan-600 to-blue-600 border border-cyan-400/30 px-6 lg:px-8 py-3.5 lg:py-4 text-sm font-bold text-white transition-all hover:scale-105 active:scale-95 shadow-[0_15px_30px_-10px_rgba(6,182,212,0.4)] hover:shadow-[0_20px_40px_-10px_rgba(6,182,212,0.6)] touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                   aria-label="ثبت بارنامه جدید"
                 >
                   <span className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-blue-400 opacity-0 transition-opacity duration-300 group-hover:opacity-20"></span>
                   <span className="relative z-10 flex items-center gap-2">ثبت بارنامه جدید</span>
                 </Link>
                 <Link
                   href="/fuel"
                   className="inline-flex flex-1 sm:flex-none items-center justify-center gap-2 rounded-2xl border border-amber-500/30 bg-amber-500/10 backdrop-blur-sm px-6 lg:px-8 py-3.5 lg:py-4 text-sm font-bold text-amber-300 transition-all hover:bg-amber-500/20 hover:border-amber-500/50 hover:shadow-lg active:scale-95 touch-target focus:outline-none focus:ring-2 focus:ring-amber-500"
                   aria-label="استعلام سوخت"
                 >
                   <FireIcon className="h-5 w-5" />
                   استعلام سوخت
                 </Link>
                 <Link
                   href="/drivers"
                   className="inline-flex flex-1 sm:flex-none items-center justify-center rounded-2xl border border-white/20 bg-slate-900/60 backdrop-blur-sm px-6 lg:px-8 py-3.5 lg:py-4 text-sm font-bold text-slate-100 transition-all hover:bg-slate-800 hover:border-white/30 hover:shadow-lg active:scale-95 touch-target focus:outline-none focus:ring-2 focus:ring-white"
                   aria-label="مدیریت ناوگان"
                 >
                   مدیریت ناوگان
                 </Link>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:gap-5 sm:grid-cols-2 xl:grid-cols-1">
            {statsLoading ? (
              <>
                {[1, 2, 3, 4].map((item) => (
                  <Skeleton key={item} className="h-32 rounded-[2rem]" />
                ))}
              </>
            ) : statsFailed ? (
              <ErrorState
                className="sm:col-span-2 xl:col-span-1"
                message="آمار داشبورد دریافت نشد. اتصال شبکه یا وضعیت سرویس را بررسی کنید."
                onRetry={() => void refetchStats()}
              />
            ) : (
              cards.map((card) => (
                <article
                  key={card.label}
                  className="stat-card group relative overflow-hidden animate-in fade-in-up"
                >
                  <div
                    className={`absolute -right-8 -top-8 h-24 w-24 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-100 ${card.glow}`}
                  ></div>
                  <div className="relative z-10 flex items-start justify-between">
                    <div>
                      <p className="text-sm font-bold text-slate-400">{card.label}</p>
                      <p className="mt-2 text-3xl xl:text-4xl font-black text-white group-hover:text-transparent group-hover:bg-clip-text group-hover:bg-gradient-to-r group-hover:from-white group-hover:to-slate-300 transition-all">
                        {card.value}
                      </p>
                    </div>
                    <div className={`rounded-[1.25rem] ${card.bg} border p-4 ${card.color} transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-3 shadow-sm`}>
                      <card.icon className="h-7 w-7" strokeWidth={2} />
                    </div>
                  </div>
                  <div className="relative z-10 mt-6 flex items-center gap-2">
                    <div className={`h-1.5 w-1.5 rounded-full ${card.color.replace('text-', 'bg-')}`}></div>
                    <p className="text-xs font-bold text-slate-400">{card.hint}</p>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="grid gap-4 sm:gap-6 lg:gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="section-card">
            <div className="flex items-center justify-between border-b border-white/5 pb-6 mb-6">
              <div>
                <h2 className="text-2xl font-black text-white flex items-center gap-2">
                  <ClockIcon className="h-6 w-6 text-cyan-400" /> آخرین تراکنش‌ها
                </h2>
                <p className="mt-1 text-sm font-medium text-slate-400">
                  وضعیت لحظه‌ای ۵ درخواست اخیر ثبت شده در سامانه
                </p>
              </div>
               <Link
                 href="/history"
                 className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-3.5 text-xs font-bold text-slate-400 transition hover:bg-slate-900 hover:text-white border border-white/5 touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                 aria-label="مشاهده آرشیو کامل"
               >
                 مشاهده آرشیو کامل
               </Link>
            </div>

            {isLoading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((item) => (
                  <Skeleton
                    key={item}
                    className="h-28"
                  />
                ))}
              </div>
            ) : jobsFailed ? (
              <ErrorState
                message="آخرین تراکنش‌ها دریافت نشدند. برای دریافت دوباره تلاش کنید."
                onRetry={() => void refetchJobs()}
              />
            ) : recentJobs.length === 0 ? (
              <EmptyState
                icon={<ClockIcon className="h-7 w-7" />}
                title="هنوز هیچ فعالیتی ثبت نشده است"
                description="با ثبت اولین بارنامه، وضعیت عملیات در این بخش نمایش داده می‌شود."
                action={
                  <Link
                    href="/new"
                    className="inline-flex items-center rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-2 text-xs font-bold text-cyan-300 transition-colors hover:bg-cyan-500/20"
                  >
                    ثبت اولین بارنامه
                  </Link>
                }
              />
            ) : (
              <div className="space-y-4">
                {recentJobs.map((job) => (
                  <div
                    key={job.job_id}
                    className="group relative flex flex-wrap items-center justify-between gap-4 rounded-[1.5rem] border border-white/5 bg-slate-900/40 p-5 transition-all duration-300 hover:bg-slate-900/60 hover:shadow-xl hover:border-cyan-500/30 animate-in fade-in-up"
                  >
                    <div className="flex items-center gap-5">
                      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 text-slate-500 shadow-sm transition-transform duration-300 group-hover:scale-110 group-hover:text-cyan-400 border border-white/5">
                        <TruckIcon className="h-6 w-6" strokeWidth={1.5} />
                      </div>
                      <div>
                        <p className="text-base sm:text-lg font-black text-white ">
                          {job.driver_name ? `ثبت بارنامه برای ${job.driver_name}` : `عملیات ثبت بارنامه`}
                        </p>
                        <p className="mt-0.5 text-[10px] font-mono text-slate-400">
                          شناسه: #{job.job_id.slice(0, 8)}
                        </p>
                        <div className="mt-1 flex items-center gap-2">
                          <p className="text-xs font-bold text-slate-400 bg-slate-950/60 border border-white/5 inline-block px-2 py-0.5 rounded-md">
                            {formatDateTime(job.created_at)}
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-6">
                      <div className="hidden text-left sm:block">
                        <p className="text-[10px] font-black uppercase text-slate-500">منبع</p>
                        <p className="mt-0.5 text-xs font-bold text-slate-300">{statusLabel(job.source)}</p>
                      </div>
                       {(job.status === 'failed' || job.status === 'needs_review') && (
                         <button
                           type="button"
                           onClick={(e) => { e.stopPropagation(); void handleRetry(job.job_id).catch(e => console.error("Failed to retry job:", e)); }}
                           disabled={retryingJobId === job.job_id}
                           className="rounded-xl bg-slate-950 border border-white/10 px-5 py-3.5 text-xs font-bold text-white shadow-md transition hover:bg-slate-900 disabled:opacity-50 active:scale-95 touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                           aria-label="تلاش مجدد"
                         >
                           {retryingJobId === job.job_id ? 'در حال ارسال...' : 'تلاش مجدد'}
                         </button>
                       )}
                      <span
                        className={[
                          "inline-flex items-center rounded-xl px-4 py-2.5 text-xs font-black shadow-sm border",
                          statusTone(job.status),
                        ].join(" ")}
                      >
                        {statusLabel(job.status)}
                      </span>
                    </div>
                    {(() => {
                      const provisionalCode = trackingCodeFromResult(job.result_json);
                      const tc = confirmedTrackingCode(job.result_json, job.status, job.mutation_status, job.reconciled_at);
                      return tc ? (
                        <p className="mt-2 text-[11px] font-bold text-emerald-400">
                          کد رهگیری UTCMS: {tc}
                        </p>
                      ) : provisionalCode ? (
                        <p className="mt-2 text-[11px] font-bold text-amber-400">
                          در انتظار تطبیق با سوابق UTCMS
                        </p>
                      ) : null;
                    })()}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-6">
            <div className="section-card">
              <h2 className="text-xl font-black text-white flex items-center gap-2">
                <ChartBarIcon className="h-6 w-6 text-emerald-400" /> عملکرد امروز
              </h2>
              <div className="mt-8 space-y-4">
                {[
                  { label: "کل درخواست‌ها", value: toPersianDigits(stats.today_jobs), icon: Zap, color: "text-blue-400", bg: "bg-blue-500/10 border-blue-500/20" },
                  { label: "ثبت‌های موفق", value: toPersianDigits(stats.today_success), icon: ShieldCheck, color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20" },
                  { label: "تراکنش‌های ناموفق", value: toPersianDigits(stats.today_failed), icon: XCircle, color: "text-rose-400", bg: "bg-rose-500/10 border-rose-500/20" },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="group flex items-center justify-between rounded-[1.25rem] border border-white/5 bg-slate-900/40 px-5 py-4 transition-all hover:bg-slate-900/60 hover:shadow-md animate-in fade-in-up"
                  >
                    <div className="flex items-center gap-4">
                      <div className={`p-2.5 rounded-xl border ${item.bg} ${item.color} group-hover:scale-110 transition-transform`}>
                        <item.icon className="h-5 w-5" strokeWidth={2.5} />
                      </div>
                      <span className="text-sm font-bold text-slate-400">{item.label}</span>
                    </div>
                    <span className="text-xl font-black text-white">
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
              
              <div className="relative mt-8 overflow-hidden rounded-[1.5rem] bg-slate-950 p-5 lg:p-6 text-white shadow-xl">
                <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-cyan-500/20 blur-2xl"></div>
                <div className="relative z-10 flex items-center justify-between">
                  <p className="text-xs font-bold text-slate-400">نرخ موفقیت هوشمند</p>
                  <p className="text-[10px] font-bold text-cyan-400 bg-cyan-400/10 px-2 py-1 rounded-md">{formatDateTime(stats.created_at)}</p>
                </div>
                <div className="relative z-10 mt-6 flex items-center gap-5">
                  <ProgressBar
                    value={stats.success_rate}
                    tone="emerald"
                    size="md"
                    label="نرخ موفقیت عملیات"
                    className="flex-1"
                  />
                  <span className="text-lg font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-emerald-400">
                    {toPersianDigits(Math.round(stats.success_rate))}%
                  </span>
                </div>
              </div>
            </div>

            {error && (
              <div className="animate-in fade-in slide-in-from-bottom-4 rounded-[1.5rem] bg-rose-500/10 border border-rose-500/20 p-6 text-sm font-bold text-rose-400 shadow-sm flex items-start gap-3">
                <XCircle className="h-5 w-5 shrink-0" />
                <p>{error}</p>
              </div>
            )}
          </div>
        </section>
      </AppShell>
    </AuthGuard>
  );
}
