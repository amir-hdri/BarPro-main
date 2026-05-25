"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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

  useEffect(() => {
    async function loadDashboard() {
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
    }

    loadDashboard();
  }, [client?.role]);

  const cards = useMemo(
    () => [
      {
        icon: ChartBarIcon,
        label: "کل کارها",
        value: toPersianDigits(stats.total_jobs),
        hint: `${toPersianDigits(stats.today_jobs)} ماموریت در امروز`,
      },
      {
        icon: ArrowTrendingUpIcon,
        label: "نرخ موفقیت",
        value: formatRelativePercent(stats.success_rate),
        hint: `${toPersianDigits(stats.success_jobs)} موفق / ${toPersianDigits(stats.failed_jobs)} ناموفق`,
      },
      {
        icon: TruckIcon,
        label: "رانندگان فعال",
        value: toPersianDigits(stats.active_drivers),
        hint: `از ${toPersianDigits(stats.total_drivers)} راننده ثبت‌شده`,
      },
      {
        icon: ClockIcon,
        label: "در صف و اجرا",
        value: toPersianDigits(stats.pending_jobs + stats.in_progress_jobs),
        hint: `${toPersianDigits(stats.pending_jobs)} در صف / ${toPersianDigits(stats.in_progress_jobs)} در پردازش`,
      },
    ],
    [stats],
  );

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-[32px] border border-white/20 bg-slate-950 px-6 py-8 text-white shadow-2xl shadow-slate-900/20">
            <p className="text-xs uppercase tracking-[0.35em] text-cyan-300">
              Overview
            </p>
            <h1 className="mt-4 text-3xl font-semibold">
              پایش زنده صف ثبت بارنامه
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300">
              داشبورد حالا مستقیما از آمار مشتری و لیست واقعی کارها تغذیه
              می‌شود؛ بنابراین عددها، صف انتظار و موفقیت‌ها با بک‌اند یکسان
              هستند.
            </p>
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <Link
                href="/new"
                className="rounded-3xl bg-cyan-400 px-5 py-4 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
              >
                ثبت بارنامه جدید
              </Link>
              <Link
                href="/drivers"
                className="rounded-3xl border border-white/15 px-5 py-4 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                مدیریت رانندگان
              </Link>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
            {cards.map((card) => (
              <article
                key={card.label}
                className="rounded-[28px] border border-white/30 bg-white/70 p-5 shadow-lg shadow-slate-900/5 backdrop-blur"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-slate-500">{card.label}</p>
                    <p className="mt-3 text-3xl font-semibold text-slate-950">
                      {card.value}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-950 p-3 text-cyan-300">
                    <card.icon className="h-6 w-6" />
                  </div>
                </div>
                <p className="mt-4 text-sm text-slate-600">{card.hint}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="rounded-[32px] border border-white/20 bg-white/75 p-6 shadow-lg shadow-slate-900/5 backdrop-blur">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">
                  آخرین کارها
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  ۵ کار آخر ثبت‌شده با وضعیت واقعی پردازش
                </p>
              </div>
              <Link
                href="/history"
                className="text-sm font-medium text-cyan-700"
              >
                مشاهده همه
              </Link>
            </div>

            {loading ? (
              <div className="mt-6 space-y-3">
                {[1, 2, 3].map((item) => (
                  <div
                    key={item}
                    className="h-20 animate-pulse rounded-3xl bg-slate-100"
                  />
                ))}
              </div>
            ) : recentJobs.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-slate-200 px-5 py-8 text-sm text-slate-500">
                هنوز کاری برای این مشتری ثبت نشده است.
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {recentJobs.map((job) => (
                  <div
                    key={job.job_id}
                    className="rounded-3xl border border-slate-100 bg-slate-50 px-5 py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-900">
                          #{job.job_id}
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          ایجاد: {formatDateTime(job.created_at)}
                        </p>
                      </div>
                      <span
                        className={[
                          "rounded-full px-3 py-1 text-xs font-semibold",
                          statusTone(job.status),
                        ].join(" ")}
                      >
                        {statusLabel(job.status)}
                      </span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-600">
                      <span>
                        تلاش: {toPersianDigits(job.attempt_count)} /{" "}
                        {toPersianDigits(job.max_retries)}
                      </span>
                      <span>اولویت: {toPersianDigits(job.priority)}</span>
                      <span>منبع: {statusLabel(job.source)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-[32px] border border-white/20 bg-white/75 p-6 shadow-lg shadow-slate-900/5 backdrop-blur">
            <h2 className="text-xl font-semibold text-slate-950">
              جمع‌بندی امروز
            </h2>
            <div className="mt-6 space-y-4">
              {[
                ["ماموریت‌های امروز", toPersianDigits(stats.today_jobs)],
                ["موفق امروز", toPersianDigits(stats.today_success)],
                ["ناموفق امروز", toPersianDigits(stats.today_failed)],
                ["آخرین بروزرسانی", formatDateTime(stats.created_at)],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="flex items-center justify-between rounded-2xl bg-slate-50 px-4 py-3"
                >
                  <span className="text-sm text-slate-500">{label}</span>
                  <span className="text-sm font-semibold text-slate-900">
                    {value}
                  </span>
                </div>
              ))}
            </div>

            {error && (
              <p className="mt-5 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {error}
              </p>
            )}
          </div>
        </section>
      </AuthGuard>
    </AppShell>
  );
}
