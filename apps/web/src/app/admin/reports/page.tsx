"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DriverReport, FailureAnalysis } from "@/lib/types";
import { Filter, Loader2 } from "lucide-react";

export default function AdminReportsPage() {
  const [activeTab, setActiveTab] = useState<"driver" | "failure">("driver");

  // Driver report state
  const [driverReport, setDriverReport] = useState<DriverReport | null>(null);
  const [driverLoading, setDriverLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [driverFilter] = useState("");

  // Failure analysis state
  const [failureAnalysis, setFailureAnalysis] = useState<FailureAnalysis | null>(null);
  const [failureLoading, setFailureLoading] = useState(false);

  const loadDriverReport = useCallback(async () => {
    setDriverLoading(true);
    const params: Record<string, string> = { page: "1", page_size: "50" };
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (statusFilter) params.status = statusFilter;
    if (driverFilter) params.driver_id = driverFilter;

    const res = await api.get<DriverReport>("/admin/reports/drivers/report", params);
    if (res.data) setDriverReport(res.data);
    setDriverLoading(false);
  }, [dateFrom, dateTo, statusFilter, driverFilter]);

  const loadFailureAnalysis = useCallback(async () => {
    setFailureLoading(true);
    const params: Record<string, string> = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;

    const res = await api.get<FailureAnalysis>("/admin/reports/failure-analysis", params);
    if (res.data) setFailureAnalysis(res.data);
    setFailureLoading(false);
  }, [dateFrom, dateTo]);

  useEffect(() => {
    if (activeTab === "driver") loadDriverReport();
    else loadFailureAnalysis();
  }, [activeTab, loadDriverReport, loadFailureAnalysis]);

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold text-slate-100">گزارش عملکرد</h2>

      {/* Tab selector */}
      <div className="flex rounded-xl border border-white/10 bg-slate-800/50 p-1">
        {(["driver", "failure"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-lg py-2.5 text-sm font-medium transition-all ${
              activeTab === tab
                ? "bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {tab === "driver" ? "گزارش رانندگان" : "تحلیل شکست‌ها"}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-4">
        <Filter className="h-5 w-5 text-slate-400" />
        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400" />
        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400" />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-2 text-sm text-slate-100 focus:border-cyan-400">
          <option value="">همه وضعیت‌ها</option>
          <option value="success">موفق</option>
          <option value="failed">ناموفق</option>
          <option value="in_progress">در حال پردازش</option>
          <option value="pending">در انتظار</option>
        </select>
        <button onClick={() => activeTab === "driver" ? loadDriverReport() : loadFailureAnalysis()}
          className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-5 py-2.5 text-sm font-medium text-slate-950">
          فیلتر
        </button>
      </div>

      {activeTab === "driver" && (
        <div className="space-y-4">
          {driverLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
          ) : driverReport ? (
            <>
              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4 text-sm text-slate-300">
                کل نتایج: <strong>{driverReport.total.toLocaleString("fa-IR")}</strong> | صفحه {driverReport.page} از {driverReport.total_pages}
              </div>
              <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-white/10 bg-slate-800/50">
                      <tr>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">شناسه</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">مشتری</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">راننده</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">وضعیت</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">منبع</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">خطا</th>
                        <th className="px-4 py-3 text-right font-medium text-slate-300">تاریخ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(driverReport?.jobs || []).map((j) => (
                        <tr key={j.job_id} className="border-b border-white/5 hover:bg-white/5">
                          <td className="px-4 py-3 font-mono text-xs text-slate-400">{j.job_id.slice(0, 16)}</td>
                          <td className="px-4 py-3 text-slate-200">{j.client_name || `#${j.client_id}`}</td>
                          <td className="px-4 py-3 text-slate-200">{j.driver_name || "-"}</td>
                          <td className="px-4 py-3">
                            <StatusBadge status={j.status} />
                          </td>
                          <td className="px-4 py-3 text-slate-300">{j.source}</td>
                          <td className="px-4 py-3">
                            {j.last_error ? (
                              <span className="text-xs text-red-300">{j.last_error.slice(0, 40)}{j.last_error.length > 40 ? "..." : ""}</span>
                            ) : "-"}
                          </td>
                          <td className="px-4 py-3 text-slate-300">{j.created_at.slice(0, 10)}</td>
                        </tr>
                      ))}
                      {(driverReport?.jobs || []).length === 0 && (
                        <tr><td colSpan={7} className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}

      {activeTab === "failure" && (
        <div className="space-y-4">
          {failureLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>
          ) : failureAnalysis ? (
            <>
              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4 text-sm text-slate-300">
                کل شکست‌ها: <strong className="text-red-300">{failureAnalysis.total_failed}</strong>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5">
                  <h3 className="mb-3 font-semibold text-slate-200">تفکیک بر اساس نوع خطا</h3>
                  {Object.entries((failureAnalysis?.by_category || {})).map(([cat, count]) => (
                    <div key={cat} className="mb-2 flex items-center justify-between text-sm">
                      <span className="text-slate-300">{cat}</span>
                      <span className="font-mono text-red-300">{count}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5">
                  <h3 className="mb-3 font-semibold text-slate-200">تفکیک بر اساس مشتری</h3>
                  {Object.entries((failureAnalysis?.by_client || {})).map(([name, count]) => (
                    <div key={name} className="mb-2 flex items-center justify-between text-sm">
                      <span className="text-slate-300">{name}</span>
                      <span className="font-mono text-red-300">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-slate-900/30 p-5">
                <h3 className="mb-3 font-semibold text-slate-200">نمونه خطاها</h3>
                {Object.entries((failureAnalysis?.examples || {})).map(([cat, items]) => (
                  <details key={cat} className="mb-3 rounded-lg border border-white/5 bg-slate-800/30 p-3">
                    <summary className="cursor-pointer text-sm font-medium text-amber-300">{cat} ({items.length})</summary>
                    <div className="mt-2 space-y-2">
                      {(items as any[]).map((ex: any, i: number) => (
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
