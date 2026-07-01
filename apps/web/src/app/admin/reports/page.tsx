"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DriverReport, FailureAnalysis } from "@/lib/types";
import { Filter, Loader2, Clock, CheckCircle2, XCircle, BarChart3 } from "lucide-react";

export default function AdminReportsPage() {
  const [activeTab, setActiveTab] = useState<"driver" | "failure">("driver");

  const [driverReport, setDriverReport] = useState<DriverReport | null>(null);
  const [driverLoading, setDriverLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [driverFilter] = useState("");

  const [failureAnalysis, setFailureAnalysis] = useState<FailureAnalysis | null>(null);
  const [failureLoading, setFailureLoading] = useState(false);
  const [failureError, setFailureError] = useState<string | null>(null);

  const [driverError, setDriverError] = useState<string | null>(null);

  const loadDriverReport = useCallback(async () => {
    setDriverLoading(true);
    setDriverError(null);
    const params: Record<string, string> = { page: "1", page_size: "50" };
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (statusFilter) params.status = statusFilter;
    if (driverFilter) params.driver_id = driverFilter;

    try {
      const res = await api.get<DriverReport>("/admin/reports/drivers/report", params);
      if (res.data) setDriverReport(res.data);
      else setDriverError(res.error || 'خطا در بارگذاری گزارش');
    } catch {
      setDriverError('خطا در ارتباط با سرور');
    }
    setDriverLoading(false);
  }, [dateFrom, dateTo, statusFilter, driverFilter]);

  const loadFailureAnalysis = useCallback(async () => {
    setFailureLoading(true);
    setFailureError(null);
    const params: Record<string, string> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;

    try {
      const res = await api.get<FailureAnalysis>("/admin/reports/failure-analysis", params);
      if (res.data) setFailureAnalysis(res.data);
      else setFailureError(res.error || 'خطا در بارگذاری تحلیل');
    } catch {
      setFailureError('خطا در ارتباط با سرور');
    }
    setFailureLoading(false);
  }, [dateFrom, dateTo]);

  useEffect(() => {
    if (activeTab === "driver") loadDriverReport();
    else loadFailureAnalysis();
  }, [activeTab, loadDriverReport, loadFailureAnalysis]);

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold text-slate-100">گزارش عملکرد</h2>

      {((activeTab === "driver" && driverReport) || (activeTab === "failure" && failureAnalysis)) && (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          <SummaryCard
            title="کل بارنامه‌ها"
            value={(driverReport?.total ?? failureAnalysis?.total_failed ?? 0).toLocaleString("fa-IR")}
            icon={BarChart3}
            color="cyan"
          />
          {activeTab === "driver" && driverReport ? (
            <>
              <SummaryCard
                title="موفق"
                value={driverReport.jobs.filter(j => j.status === "success").length.toLocaleString("fa-IR")}
                icon={CheckCircle2}
                color="emerald"
              />
              <SummaryCard
                title="ناموفق"
                value={driverReport.jobs.filter(j => ["failed", "dead_letter", "needs_review"].includes(j.status)).length.toLocaleString("fa-IR")}
                icon={XCircle}
                color="red"
              />
              <SummaryCard
                title="در حال پردازش"
                value={driverReport.jobs.filter(j => ["in_progress", "pending", "queued"].includes(j.status)).length.toLocaleString("fa-IR")}
                icon={Clock}
                color="amber"
              />
            </>
          ) : failureAnalysis ? (
            <>
              <SummaryCard
                title="دسته‌بندی خطاها"
                value={Object.keys(failureAnalysis.by_category).length.toLocaleString("fa-IR")}
                icon={CheckCircle2}
                color="emerald"
              />
              <SummaryCard
                title="مشتریان متأثر"
                value={Object.keys(failureAnalysis.by_client).length.toLocaleString("fa-IR")}
                icon={Filter}
                color="purple"
              />
              <SummaryCard
                title="میانگین هر دسته"
                value={failureAnalysis.total_failed > 0 ? Math.round(failureAnalysis.total_failed / Math.max(1, Object.keys(failureAnalysis.by_category).length)).toLocaleString("fa-IR") : "0"}
                icon={BarChart3}
                color="amber"
              />
            </>
          ) : null}
        </div>
      )}

      <div className="flex rounded-xl border border-white/10 bg-slate-800/50 p-1">
        {(["driver", "failure"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-lg py-3.5 text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab === "driver" ? "گزارش رانندگان" : "تحلیل شکست‌ها"}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-4">
        <Filter className="h-5 w-5 text-slate-400" />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-3.5 text-sm text-slate-100 focus:border-cyan-400" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-3.5 text-sm text-slate-100 focus:border-cyan-400" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-3.5 text-sm text-slate-100 focus:border-cyan-400">
          <option value="">همه وضعیت‌ها</option>
          <option value="success">موفق</option>
          <option value="failed">ناموفق</option>
          <option value="in_progress">در حال پردازش</option>
          <option value="pending">در انتظار</option>
        </select>
        <button onClick={() => activeTab === "driver" ? loadDriverReport() : loadFailureAnalysis()}
          className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-5 py-3.5 text-sm font-medium text-slate-950">
          فیلتر
        </button>
      </div>

      {activeTab === "driver" && (
        <div className="space-y-4">
          {driverError && (
            <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400 flex items-center gap-2">
              <span className="font-bold">خطا:</span> {driverError}
            </div>
          )}
          {driverLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
          ) : driverReport ? (
            <>
              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4 text-sm text-slate-300">
                کل نتایج: <strong>{driverReport.total.toLocaleString("fa-IR")}</strong> | صفحه {driverReport.page} از {driverReport.total_pages}
              </div>
              <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30 hidden md:block">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-white/10 bg-slate-800/50 whitespace-nowrap">
                      <tr>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">شناسه</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">مشتری</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">راننده</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">وضعیت</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">تلاش‌ها</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">مدت زمان</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">منبع</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">خطا</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">تاریخ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(driverReport?.jobs || []).map((j) => {
                        const duration = j.finished_at && j.created_at
                          ? Math.round((new Date(j.finished_at).getTime() - new Date(j.created_at).getTime()) / 1000)
                          : null;
                        return (
                        <tr key={j.job_id} className="border-b border-white/5 hover:bg-white/5">
                          <td className="px-4 py-3 font-mono text-xs text-slate-400">{j.job_id.slice(0, 16)}</td>
                          <td className="px-4 py-3 text-slate-200">{j.client_name || `#${j.client_id}`}</td>
                          <td className="px-4 py-3 text-slate-200">{j.driver_name || "-"}</td>
                          <td className="px-4 py-3">
                            <StatusBadge status={j.status} />
                          </td>
                          <td className="px-4 py-3">
                            <span className="font-mono text-xs text-slate-300">{j.attempt_count ?? "—"}</span>
                          </td>
                          <td className="px-4 py-3">
                            {duration !== null ? (
                              <span className={`font-mono text-xs ${duration > 120 ? "text-red-300" : duration > 60 ? "text-amber-300" : "text-slate-300"}`}>
                                {duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m ${duration % 60}s`}
                              </span>
                            ) : "—"}
                          </td>
                          <td className="px-4 py-3 text-slate-300">{j.source}</td>
                          <td className="px-4 py-3">
                            {j.last_error ? (
                              <span className="text-xs text-red-300">{j.last_error.slice(0, 40)}{j.last_error.length > 40 ? "..." : ""}</span>
                            ) : "-"}
                          </td>
                          <td className="px-4 py-3 text-slate-300">{j.created_at.slice(0, 10)}</td>
                        </tr>
                        );
                      })}
                      {(driverReport?.jobs || []).length === 0 && (
                        <tr><td colSpan={9} className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="block md:hidden space-y-3">
                {(driverReport?.jobs || []).length === 0 ? (
                  <div className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</div>
                ) : (
                  (driverReport?.jobs || []).map((j) => {
                    const duration = j.finished_at && j.created_at
                      ? Math.round((new Date(j.finished_at).getTime() - new Date(j.created_at).getTime()) / 1000)
                      : null;
                    return (
                    <div key={j.job_id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="font-mono text-xs text-slate-400">{j.job_id.slice(0, 12)}</div>
                        <StatusBadge status={j.status} />
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-400">مشتری:</span>
                          <span className="text-slate-200">{j.client_name || `#${j.client_id}`}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-400">راننده:</span>
                          <span className="text-slate-200">{j.driver_name || "-"}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-slate-400">تلاش‌ها:</span>
                          <span className="font-mono text-slate-300">{j.attempt_count ?? "—"}</span>
                        </div>
                        {duration !== null && (
                          <div className="flex justify-between text-xs">
                            <span className="text-slate-400">مدت زمان:</span>
                            <span className={`font-mono ${duration > 120 ? "text-red-300" : duration > 60 ? "text-amber-300" : "text-slate-300"}`}>
                              {duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m ${duration % 60}s`}
                            </span>
                          </div>
                        )}
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-400">منبع:</span>
                          <span className="text-slate-300">{j.source}</span>
                        </div>
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-400">تاریخ:</span>
                          <span className="text-slate-300">{j.created_at.slice(0, 10)}</span>
                        </div>
                        {j.last_error && (
                          <div className="text-xs text-red-300 mt-1">{j.last_error.slice(0, 60)}</div>
                        )}
                      </div>
                    </div>
                    );
                  })
                )}
              </div>

            </>
          ) : null}
        </div>
      )}

      {activeTab === "failure" && (
        <div className="space-y-4">
          {failureError && (
            <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400 flex items-center gap-2">
              <span className="font-bold">خطا:</span> {failureError}
            </div>
          )}
          {failureLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
          ) : failureAnalysis ? (
            <>
              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4 text-sm text-slate-300">
                کل شکست‌ها: <strong className="text-red-300">{failureAnalysis.total_failed}</strong>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5 overflow-x-auto">
                  <h3 className="mb-3 font-semibold text-slate-200">تفکیک بر اساس نوع خطا</h3>
                  {Object.entries((failureAnalysis?.by_category || {})).map(([cat, count]) => (
                    <div key={cat} className="mb-3">
                      <div className="flex items-center justify-between text-sm whitespace-nowrap gap-4">
                        <span className="text-slate-300">{cat}</span>
                        <span className="font-mono text-red-300">{count}</span>
                      </div>
                      <p className="mt-1 text-[10px] text-cyan-400/70 leading-relaxed">
                        {getRetrySuggestion(cat)}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="space-y-4">
                  <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5 overflow-x-auto">
                    <h3 className="mb-3 font-semibold text-slate-200">تفکیک بر اساس مشتری</h3>
                    {Object.entries((failureAnalysis?.by_client || {})).map(([name, count]) => (
                      <div key={name} className="mb-2 flex items-center justify-between text-sm whitespace-nowrap min-w-max gap-4">
                        <span className="text-slate-300">{name}</span>
                        <span className="font-mono text-red-300">{count}</span>
                      </div>
                    ))}
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5">
                    <h3 className="mb-3 font-semibold text-slate-200">راهنمای رفع خطا</h3>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      برای هر دسته خطا، پیشنهاد رفع مشکل در کنار آن نمایش داده شده است. در صورت تداوم خطا، لاگ‌های سرور را بررسی کنید.
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5">
                <h3 className="mb-3 font-semibold text-slate-200">نمونه خطاها</h3>
                {Object.entries((failureAnalysis?.examples || {})).map(([cat, items]) => (
                  <details key={cat} className="mb-3 rounded-lg border border-white/5 bg-slate-800/30 p-3">
                    <summary className="cursor-pointer text-sm font-medium text-amber-300">{cat} ({items.length})</summary>
                    <div className="mt-2 space-y-2">
                      {items.map((ex, i: number) => (
                        <div key={i} className="rounded bg-slate-900/50 p-2 text-xs text-slate-300">
                          <div>مشتری: {ex.client} | راننده: {ex.driver}</div>
                          <div className="text-red-300">{ex.error}</div>
                          <div className="text-slate-500">{ex.created_at}</div>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  color: "cyan" | "emerald" | "red" | "amber" | "purple";
}) {
  const bgMap = {
    cyan: "from-cyan-500/10 to-cyan-500/5 text-cyan-300 border-cyan-500/20",
    emerald: "from-emerald-500/10 to-emerald-500/5 text-emerald-300 border-emerald-500/20",
    red: "from-red-500/10 to-red-500/5 text-red-300 border-red-500/20",
    amber: "from-amber-500/10 to-amber-500/5 text-amber-300 border-amber-500/20",
    purple: "from-purple-500/10 to-purple-500/5 text-purple-300 border-purple-500/20",
  };

  return (
    <div className={`rounded-xl border bg-gradient-to-br p-4 ${bgMap[color]}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium opacity-80">{title}</span>
        <Icon className="h-4 w-4 opacity-60" />
      </div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}

function getRetrySuggestion(category: string): string {
  const cat = category.toLowerCase();
  if (cat.includes("timeout") || cat.includes("connection") || cat.includes("network")) return "بررسی اتصال اینترنت، افزایش timeout یا تغییر پروکسی";
  if (cat.includes("captcha") || cat.includes("recaptcha")) return "بررسی اعتبار API کپچا، انقضای توکن یا تغییر provider";
  if (cat.includes("auth") || cat.includes("login") || cat.includes("credential")) return "بررسی اعتبار حساب کاربری در سامانه UTCMS";
  if (cat.includes("not_found") || cat.includes("404") || cat.includes("missing")) return "بررسی صحت کد راننده، پلاک یا اطلاعات ورودی";
  if (cat.includes("rate") || cat.includes("limit") || cat.includes("throttle")) return "کاهش نرخ درخواست‌ها، افزایش تاخیر بین تسک‌ها";
  if (cat.includes("parse") || cat.includes("validation") || cat.includes("invalid")) return "بررسی فرمت داده‌های ورودی و تطابق با سامانه";
  if (cat.includes("otp") || cat.includes("sms")) return "بررسی سرویس پیامک و زمان انقضای رمز یکبارمصرف";
  if (cat.includes("server") || cat.includes("internal") || cat.includes("500")) return "بررسی وضعیت سامانه UTCMS — خطای سمت سرور";
  return "بررسی لاگ خطا و عیب‌یابی دستی";
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    success: "bg-emerald-500/10 text-emerald-300",
    failed: "bg-red-500/10 text-red-300",
    dead_letter: "bg-red-500/10 text-red-300",
    in_progress: "bg-cyan-500/10 text-cyan-300",
    pending: "bg-amber-500/10 text-amber-300",
    queued: "bg-amber-500/10 text-amber-300",
    waiting_retry: "bg-amber-500/10 text-amber-300",
    needs_review: "bg-orange-500/10 text-orange-300",
    otp_backoff: "bg-purple-500/10 text-purple-300",
  };
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${map[status] || "bg-slate-500/10 text-slate-400"}`}>
      {status}
    </span>
  );
}
