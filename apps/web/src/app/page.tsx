"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowTrendingUpIcon,
  ChartBarIcon,
  ClockIcon,
  TruckIcon,
} from "@heroicons/react/24/outline";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { useSession } from "@/hooks/useSession";
import { api } from "@/lib/api";
import {
  formatDateTime,
  formatRelativePercent,
  statusLabel,
  statusTone,
  toPersianDigits,
} from "@/lib/format";
import type {
  ClientStats,
  WaybillJob,
  WaybillTaskListResponse,
} from "@/lib/types";
import { Zap, ShieldCheck, XCircle } from 'lucide-react';

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

export default function DashboardPage() {
  const { client } = useSession();
  const [stats, setStats] = useState<ClientStats>(emptyStats);
  const [recentJobs, setRecentJobs] = useState<WaybillJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (client?.role === 'master_admin') {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    const [statsResponse, jobsResponse] = await Promise.all([
      api.get<ClientStats>("/api/v1/auth/stats"),
      api.get<WaybillTaskListResponse>("/api/v1/waybill-jobs", {
        page: 1,
        page_size: 5,
      }),
    ]);

    if (!statsResponse.success || !statsResponse.data) {
      setError(statsResponse.error || "آمار داشبورد بارگذاری نشد");
    } else {
      setStats(statsResponse.data);
    }

    if (jobsResponse.success && jobsResponse.data) {
      setRecentJobs(jobsResponse.data.tasks);
    }

    setLoading(false);
  }, [client?.role]);

  useEffect(() => {
    loadDashboard();
  }, [client?.role, loadDashboard]);

  async function handleRetry(jobId: string) {
    setRetryingJobId(jobId);
    const response = await api.post(`/api/v1/waybill-jobs/${jobId}/retry`, { dispatch_now: true });
    setRetryingJobId(null);
    if (response.success) {
      void loadDashboard();
    } else {
      alert(response.error || 'تلاش مجدد ناموفق بود');
    }
  }

  const cards = useMemo(
    () => [
      {
        icon: ChartBarIcon,
        label: "کل ماموریت‌ها",
        value: toPersianDigits(stats.total_jobs),
        hint: `${toPersianDigits(stats.today_jobs)} مورد جدید امروز`,
        color: "text-blue-500",
        bg: "bg-blue-50"
      },
      {
        icon: ArrowTrendingUpIcon,
        label: "پایداری عملیات",
        value: formatRelativePercent(stats.success_rate),
        hint: `${toPersianDigits(stats.success_jobs)} ثبت موفق نهایی`,
        color: "text-emerald-500",
        bg: "bg-emerald-50"
      },
      {
        icon: TruckIcon,
        label: "ناوگان تحت مدیریت",
        value: toPersianDigits(stats.active_drivers),
        hint: `از ${toPersianDigits(stats.total_drivers)} راننده احراز شده`,
        color: "text-cyan-500",
        bg: "bg-cyan-50"
      },
      {
        icon: ClockIcon,
        label: "در حال پردازش",
        value: toPersianDigits(stats.pending_jobs + stats.in_progress_jobs),
        hint: `${toPersianDigits(stats.pending_jobs)} در صف / ${toPersianDigits(stats.in_progress_jobs)} در حال اجرا`,
        color: "text-amber-500",
        bg: "bg-amber-50"
      },
    ],
    [stats],
  );

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="relative overflow-hidden rounded-[40px] border border-slate-200 bg-slate-950 px-8 py-12 text-white shadow-2xl shadow-slate-900/10">
            <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
            <div className="relative z-10">
              <span className="inline-flex items-center gap-2 rounded-full bg-cyan-500/10 px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-cyan-400">
                Dashboard Overview
              </span>
              <h1 className="mt-6 text-4xl font-bold tracking-tight">
                مدیریت هوشمند عملیات بارنامه
              </h1>
              <p className="mt-4 max-w-xl text-lg leading-relaxed text-slate-400">
                مشاهده لحظه‌ای وضعیت ثبت، مانیتورینگ ناوگان و تحلیل دقیق نرخ موفقیت در یک نگاه هوشمند.
              </p>
              <div className="mt-10 flex flex-wrap gap-4">
                <Link
                  href="/new"
                  className="inline-flex items-center justify-center rounded-2xl bg-cyan-400 px-8 py-4 text-sm font-bold text-slate-950 transition hover:bg-cyan-300 active:scale-[0.98]"
                >
                  ثبت بارنامه جدید
                </Link>
                <Link
                  href="/drivers"
                  className="inline-flex items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-8 py-4 text-sm font-bold text-white transition hover:bg-white/10 active:scale-[0.98]"
                >
                  مدیریت ناوگان
                </Link>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
            {cards.map((card) => (
              <article
                key={card.label}
                className="group flex flex-col justify-between rounded-[32px] border border-slate-100 bg-white p-6 shadow-sm transition-all duration-300 hover:shadow-xl hover:shadow-slate-200/50"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-500">{card.label}</p>
                    <p className="mt-2 text-3xl font-bold text-slate-900">
                      {card.value}
                    </p>
                  </div>
                  <div className={`rounded-2xl ${card.bg} p-3.5 ${card.color} transition-transform duration-300 group-hover:scale-110`}>
                    <card.icon className="h-6 w-6" />
                  </div>
                </div>
                <div className="mt-6 flex items-center gap-2">
                  <div className="h-1 w-1 rounded-full bg-slate-300"></div>
                  <p className="text-xs font-medium text-slate-400">{card.hint}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-10 grid gap-8 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-[40px] border border-slate-200 bg-white p-8 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-50 pb-6">
              <div>
                <h2 className="text-xl font-bold text-slate-900">
                  آخرین تراکنش‌ها
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  وضعیت لحظه‌ای ۵ درخواست اخیر ثبت شده در سامانه
                </p>
              </div>
              <Link
                href="/history"
                className="inline-flex items-center gap-1 text-sm font-bold text-cyan-600 hover:text-cyan-700"
              >
                مشاهده آرشیو کامل
              </Link>
            </div>

            {loading ? (
              <div className="mt-6 space-y-4">
                {[1, 2, 3].map((item) => (
                  <div
                    key={item}
                    className="h-24 animate-pulse rounded-3xl bg-slate-50"
                  />
                ))}
              </div>
            ) : recentJobs.length === 0 ? (
              <div className="mt-10 flex flex-col items-center justify-center rounded-[32px] border-2 border-dashed border-slate-100 py-16">
                <div className="rounded-full bg-slate-50 p-4 text-slate-300">
                  <ClockIcon className="h-10 w-10" />
                </div>
                <p className="mt-4 text-sm font-medium text-slate-400">
                  هنوز هیچ فعالیتی برای این حساب ثبت نشده است.
                </p>
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {recentJobs.map((job) => (
                  <div
                    key={job.job_id}
                    className="group flex flex-wrap items-center justify-between gap-4 rounded-[28px] border border-slate-50 bg-slate-50/50 p-5 transition-all hover:border-cyan-100 hover:bg-white hover:shadow-md"
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-slate-400 shadow-sm transition-colors group-hover:text-cyan-500">
                        <TruckIcon className="h-6 w-6" />
                      </div>
                      <div>
                        <p className="font-bold text-slate-900">
                          #{job.job_id}
                        </p>
                        <p className="mt-0.5 text-xs font-medium text-slate-400">
                          ثبت شده در {formatDateTime(job.created_at)}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-6">
                      <div className="hidden text-left sm:block">
                        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">منبع درخواست</p>
                        <p className="mt-0.5 text-xs font-bold text-slate-600">{statusLabel(job.source)}</p>
                      </div>
                      {(job.status === 'failed' || job.status === 'needs_review') && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); void handleRetry(job.job_id); }}
                          disabled={retryingJobId === job.job_id}
                          className="rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-cyan-600 disabled:opacity-50 active:scale-[0.97]"
                        >
                          {retryingJobId === job.job_id ? '...' : 'تلاش مجدد'}
                        </button>
                      )}
                      <span
                        className={[
                          "inline-flex items-center rounded-xl px-4 py-2 text-xs font-bold shadow-sm",
                          statusTone(job.status),
                        ].join(" ")}
                      >
                        {statusLabel(job.status)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-8">
            <div className="rounded-[40px] border border-slate-200 bg-white p-8 shadow-sm">
              <h2 className="text-xl font-bold text-slate-900">
                جمع‌بندی عملکرد امروز
              </h2>
              <div className="mt-8 space-y-4">
                {[
                  { label: "کل درخواست‌ها", value: toPersianDigits(stats.today_jobs), icon: Zap, color: "text-blue-500" },
                  { label: "ثبت‌های موفق", value: toPersianDigits(stats.today_success), icon: ShieldCheck, color: "text-emerald-500" },
                  { label: "تراکنش‌های ناموفق", value: toPersianDigits(stats.today_failed), icon: XCircle, color: "text-rose-500" },
                ].map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between rounded-2xl border border-slate-50 bg-slate-50/50 px-5 py-4 transition-colors hover:bg-slate-50"
                  >
                    <div className="flex items-center gap-3">
                      <item.icon className={`h-5 w-5 ${item.color}`} />
                      <span className="text-sm font-semibold text-slate-600">{item.label}</span>
                    </div>
                    <span className="text-base font-black text-slate-900">
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
              
              <div className="mt-10 rounded-3xl bg-slate-900 p-6 text-white shadow-xl shadow-slate-900/20">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold text-slate-400">آخرین بروزرسانی</p>
                  <p className="text-xs font-medium text-cyan-400">{formatDateTime(stats.created_at)}</p>
                </div>
                <div className="mt-4 flex items-center gap-4">
                  <div className="h-2 flex-1 rounded-full bg-white/10">
                    <div 
                      className="h-full rounded-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.5)] transition-all duration-1000" 
                      style={{ width: `${stats.success_rate}%` }}
                    ></div>
                  </div>
                  <span className="text-sm font-black text-cyan-400">{toPersianDigits(Math.round(stats.success_rate))}%</span>
                </div>
              </div>
            </div>

            {error && (
              <div className="animate-in fade-in slide-in-from-bottom-4 rounded-[32px] bg-rose-50 p-6 text-sm font-bold text-rose-700 shadow-sm shadow-rose-100">
                {error}
              </div>
            )}
          </div>
        </section>
      </AuthGuard>
    </AppShell>
  );
}

