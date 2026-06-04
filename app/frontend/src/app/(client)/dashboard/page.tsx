"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Users,
  Briefcase,
  CheckCircle,
  XCircle,
  TrendingUp,
  Loader2,
  AlertTriangle,
  Play,
  Clock,
  ArrowUpRight,
  FileText
} from "lucide-react";
import Link from "next/link";
import { ClientStatsResponse, WaybillJobResponse } from "@/lib/types";

interface StatsData {
  total_drivers: number;
  active_drivers: number;
  total_jobs: number;
  pending_jobs: number;
  in_progress_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  today_jobs: number;
  today_success: number;
  today_failed: number;
  success_rate: number;
}

export default function ClientDashboardPage() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [recentJobs, setRecentJobs] = useState<WaybillJobResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDashboardData();
  }, []);

  async function fetchDashboardData() {
    try {
      setLoading(true);
      setError("");

      const statsRes = await api.get<StatsData>("/api/v1/auth/stats");
      if (statsRes.data) setStats(statsRes.data);

      const jobsRes = await api.get<{ tasks: WaybillJobResponse[] }>("/api/v1/waybill-jobs", {
        page: "1",
        page_size: "5"
      });
      if (jobsRes.data?.tasks) setRecentJobs(jobsRes.data.tasks);
    } catch (err: any) {
      setError(err?.message || "خطا در بارگذاری اطلاعات داشبورد");
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in text-right" dir="rtl">
      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Overview stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="کل رانندگان"
          value={stats?.total_drivers || 0}
          icon={Users}
          sub={`رانندگان فعال: ${stats?.active_drivers || 0}`}
          color="cyan"
        />
        <StatCard
          title="کل عملیات‌ها"
          value={stats?.total_jobs || 0}
          icon={Briefcase}
          sub={`در صف: ${stats?.pending_jobs || 0} | در حال اجرا: ${stats?.in_progress_jobs || 0}`}
          color="amber"
        />
        <StatCard
          title="صدورهای موفق"
          value={stats?.success_jobs || 0}
          icon={CheckCircle}
          sub={`امروز: ${stats?.today_success || 0}`}
          color="emerald"
        />
        <StatCard
          title="نرخ موفقیت"
          value={`${stats?.success_rate ? Math.round(stats.success_rate) : 0}%`}
          icon={TrendingUp}
          sub={`امروز شکست خورده: ${stats?.today_failed || 0}`}
          color="violet"
        />
      </div>

      {/* Main dashboard content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Recent waybills list */}
        <div className="lg:col-span-2 rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <h3 className="text-lg font-bold text-slate-100">آخرین عملیات‌های صدور</h3>
            <Link
              href="/client/waybills"
              className="text-xs font-semibold text-cyan-400 hover:underline flex items-center gap-1"
            >
              مشاهده همه
              <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5 text-slate-400">
                  <th className="pb-3 text-right">شناسه تسک</th>
                  <th className="pb-3 text-right">راننده</th>
                  <th className="pb-3 text-center">وضعیت</th>
                  <th className="pb-3 text-center">تعداد تلاش</th>
                  <th className="pb-3 text-left">تاریخ ثبت</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {recentJobs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-slate-500">
                      هیچ درخواستی تاکنون ثبت نشده است.
                    </td>
                  </tr>
                ) : (
                  recentJobs.map((job) => (
                    <tr key={job.id} className="hover:bg-white/5 transition-colors">
                      <td className="py-3 font-mono text-xs text-slate-400">{job.job_id.slice(0, 8)}...</td>
                      <td className="py-3">{job.driver_id ? `شناسه راننده ${job.driver_id}` : "ثبت مستقیم"}</td>
                      <td className="py-3 text-center">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          job.status === "success"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : job.status === "failed"
                            ? "bg-red-500/10 text-red-400"
                            : job.status === "in_progress"
                            ? "bg-amber-500/10 text-amber-400 animate-pulse"
                            : "bg-slate-500/10 text-slate-400"
                        }`}>
                          {job.status === "success" && "موفق"}
                          {job.status === "failed" && "ناموفق"}
                          {job.status === "in_progress" && "در حال اجرا"}
                          {job.status === "pending" && "در صف"}
                          {job.status === "queued" && "در صف اجرا"}
                          {job.status === "waiting_auth" && "نیاز به رمز پویا"}
                          {job.status === "waiting_retry" && "انتظار مجدد"}
                        </span>
                      </td>
                      <td className="py-3 text-center tabular-nums">{job.attempt_count} / {job.max_retries}</td>
                      <td className="py-3 text-left text-xs text-slate-400 font-mono">
                        {new Date(job.created_at).toLocaleDateString("fa-IR")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick Actions and guidelines */}
        <div className="space-y-6">
          <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 space-y-4">
            <h3 className="text-lg font-bold text-slate-100 border-b border-white/10 pb-4">دسترسی سریع</h3>
            <div className="grid grid-cols-1 gap-3">
              <Link
                href="/client/drivers"
                className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 px-4 py-3.5 text-sm font-medium text-slate-200 transition-all hover:bg-white/10"
              >
                <Users className="h-5 w-5 text-cyan-400" />
                مدیریت رانندگان و پلاک‌ها
              </Link>
              <Link
                href="/client/schedules"
                className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 px-4 py-3.5 text-sm font-medium text-slate-200 transition-all hover:bg-white/10"
              >
                <Clock className="h-5 w-5 text-amber-400" />
                تنظیمات زمان‌بندی روزانه
              </Link>
              <Link
                href="/client/waybills"
                className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 px-4 py-3.5 text-sm font-medium text-slate-200 transition-all hover:bg-white/10"
              >
                <FileText className="h-5 w-5 text-emerald-400" />
                ثبت و پیگیری بارنامه‌ها
              </Link>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-indigo-900/30 to-purple-900/30 backdrop-blur-xl p-6 space-y-3">
            <h4 className="font-semibold text-slate-100 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-400" />
              راهنمای استفاده امن
            </h4>
            <ul className="list-disc list-inside text-xs leading-5 text-slate-400 space-y-2">
              <li>برای صدور اتوماتیک، مطمئن شوید اطلاعات ورود راننده در UTCMS صحیح است.</li>
              <li>در صورت نیاز به رمز پویا (OTP)، وضعیت تسک به حالت <b>نیاز به رمز پویا</b> تغییر خواهد کرد.</li>
              <li>پلاک‌های منطقه آزاد به طور کامل پشتیبانی می‌شوند (سریال پلاک وارد فیلد سوم می‌شود).</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  sub,
  color,
}: {
  title: string;
  value: number | string;
  icon: any;
  sub?: string;
  color: "cyan" | "amber" | "emerald" | "violet";
}) {
  const bgMap = {
    cyan: "from-cyan-500/10 to-cyan-500/5 text-cyan-300 border-cyan-500/20",
    amber: "from-amber-500/10 to-amber-500/5 text-amber-300 border-amber-500/20",
    emerald: "from-emerald-500/10 to-emerald-500/5 text-emerald-300 border-emerald-500/20",
    violet: "from-violet-500/10 to-violet-500/5 text-violet-300 border-violet-500/20",
  };

  return (
    <div className={`rounded-2xl border bg-gradient-to-br p-5 ${bgMap[color]}`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium opacity-80">{title}</span>
        <Icon className="h-5 w-5 opacity-60" />
      </div>
      <div className="text-3xl font-bold font-mono">{value}</div>
      {sub && <p className="mt-1 text-xs opacity-60 font-sans">{sub}</p>}
    </div>
  );
}
