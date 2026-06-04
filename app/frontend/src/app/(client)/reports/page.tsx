"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  BarChart3,
  Calendar,
  Users,
  CheckCircle,
  XCircle,
  TrendingUp,
  Loader2,
  AlertTriangle
} from "lucide-react";

interface DailySummaryItem {
  date: string;
  total: number;
  success: number;
  failed: number;
  pending: number;
}

interface DriverPerfItem {
  driver_id: number;
  driver_name: string;
  national_code: string;
  total_jobs: number;
  success: number;
  failed: number;
  success_rate: number;
}

export default function ReportsPage() {
  const [days, setDays] = useState(7);
  const [dailySummary, setDailySummary] = useState<DailySummaryItem[]>([]);
  const [driverPerf, setDriverPerf] = useState<DriverPerfItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchReportData();
  }, [days]);

  async function fetchReportData() {
    try {
      setLoading(true);
      setError("");

      const dailyRes = await api.get<{ summary: DailySummaryItem[] }>(
        "/api/v1/reports/daily-summary",
        { days: String(days) }
      );
      if (dailyRes.data?.summary) setDailySummary(dailyRes.data.summary);

      const perfRes = await api.get<{ drivers: DriverPerfItem[] }>(
        "/api/v1/reports/driver-performance"
      );
      if (perfRes.data?.drivers) setDriverPerf(perfRes.data.drivers);
    } catch (err: any) {
      setError(err?.message || "خطا در بارگذاری گزارش‌ها");
    } finally {
      setLoading(false);
    }
  }

  // Calculate totals
  const totalJobs = dailySummary.reduce((sum, item) => sum + item.total, 0);
  const totalSuccess = dailySummary.reduce((sum, item) => sum + item.success, 0);
  const totalFailed = dailySummary.reduce((sum, item) => sum + item.failed, 0);
  const totalPending = dailySummary.reduce((sum, item) => sum + item.pending, 0);
  const successRate = totalJobs > 0 ? Math.round((totalSuccess / totalJobs) * 100) : 0;

  return (
    <div className="space-y-6 text-right animate-fade-in" dir="rtl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">گزارش‌های عملکرد و نمودارها</h2>
          <p className="mt-1 text-sm text-slate-400">
            بررسی آمار روزانه، درصد موفقیت ربات و عملکرد رانندگان در بازه‌های مختلف
          </p>
        </div>

        {/* Days selector */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">بازه زمانی:</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-xl border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-cyan-400 focus:outline-none"
          >
            <option value="7">۷ روز اخیر</option>
            <option value="15">۱۵ روز اخیر</option>
            <option value="30">۳۰ روز اخیر</option>
            <option value="90">۹۰ روز اخیر</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex h-96 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryStatCard title="کل درخواست‌ها" value={totalJobs} color="cyan" />
            <SummaryStatCard title="صدور موفق" value={totalSuccess} color="emerald" />
            <SummaryStatCard title="صدور ناموفق" value={totalFailed} color="red" />
            <SummaryStatCard title="در صف انتظار" value={totalPending} color="amber" />
            <SummaryStatCard title="نرخ موفقیت" value={`${successRate}%`} color="violet" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Daily stats table */}
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Calendar className="h-5 w-5 text-cyan-400" />
                آمار روزانه صدور بارنامه
              </h3>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-white/10 text-slate-400">
                    <tr>
                      <th className="pb-3 text-right">تاریخ</th>
                      <th className="pb-3 text-center">کل درخواست‌ها</th>
                      <th className="pb-3 text-center">موفقیت‌آمیز</th>
                      <th className="pb-3 text-center">ناموفق</th>
                      <th className="pb-3 text-center font-semibold">نرخ موفقیت</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-slate-300">
                    {dailySummary.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          اطلاعاتی یافت نشد.
                        </td>
                      </tr>
                    ) : (
                      dailySummary.map((item) => {
                        const dayRate = item.total > 0 ? Math.round((item.success / item.total) * 100) : 0;
                        return (
                          <tr key={item.date} className="hover:bg-white/5 transition-colors">
                            <td className="py-3 text-right font-mono text-xs">{new Date(item.date).toLocaleDateString("fa-IR")}</td>
                            <td className="py-3 text-center font-mono tabular-nums">{item.total}</td>
                            <td className="py-3 text-center font-mono tabular-nums text-emerald-400">{item.success}</td>
                            <td className="py-3 text-center font-mono tabular-nums text-red-400">{item.failed}</td>
                            <td className="py-3 text-center">
                              <span className={`font-semibold font-mono ${
                                dayRate >= 80 ? "text-emerald-400" : dayRate >= 50 ? "text-amber-400" : "text-red-400"
                              }`}>
                                {dayRate}%
                              </span>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Drivers performance report */}
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl p-6 space-y-4">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Users className="h-5 w-5 text-amber-400" />
                عملکرد رانندگان و حساب‌های کاربری
              </h3>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-white/10 text-slate-400">
                    <tr>
                      <th className="pb-3 text-right">نام راننده</th>
                      <th className="pb-3 text-center font-semibold">تعداد کل</th>
                      <th className="pb-3 text-center text-emerald-400">موفق</th>
                      <th className="pb-3 text-center text-red-400">ناموفق</th>
                      <th className="pb-3 text-left">نرخ موفقیت</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-slate-300">
                    {driverPerf.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          راننده‌ای با فعالیت صدور یافت نشد.
                        </td>
                      </tr>
                    ) : (
                      driverPerf.map((driver) => (
                        <tr key={driver.driver_id} className="hover:bg-white/5 transition-colors">
                          <td className="py-3 text-right font-medium text-slate-200">{driver.driver_name}</td>
                          <td className="py-3 text-center font-mono tabular-nums">{driver.total_jobs}</td>
                          <td className="py-3 text-center font-mono tabular-nums text-emerald-400">{driver.success}</td>
                          <td className="py-3 text-center font-mono tabular-nums text-red-400">{driver.failed}</td>
                          <td className="py-3 text-left font-mono font-semibold">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 bg-white/10 rounded-full h-1.5 overflow-hidden hidden sm:block">
                                <div
                                  className={`h-full rounded-full ${
                                    driver.success_rate >= 80 ? "bg-emerald-400" : driver.success_rate >= 50 ? "bg-amber-400" : "bg-red-400"
                                  }`}
                                  style={{ width: `${driver.success_rate}%` }}
                                ></div>
                              </div>
                              <span className={
                                driver.success_rate >= 80 ? "text-emerald-400" : driver.success_rate >= 50 ? "text-amber-400" : "text-red-400"
                              }>
                                {driver.success_rate}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryStatCard({
  title,
  value,
  color
}: {
  title: string;
  value: string | number;
  color: "cyan" | "emerald" | "red" | "amber" | "violet";
}) {
  const colorMap = {
    cyan: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
    emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    red: "text-red-400 bg-red-500/10 border-red-500/20",
    amber: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    violet: "text-violet-400 bg-violet-500/10 border-violet-500/20",
  };

  return (
    <div className={`rounded-xl border p-4 text-center ${colorMap[color]}`}>
      <p className="text-xs font-medium opacity-80 mb-1">{title}</p>
      <p className="text-2xl font-bold font-mono">{value}</p>
    </div>
  );
}
