"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  AlertTriangle,
  Play,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  ShieldAlert,
  Search
} from "lucide-react";
import { Driver, WaybillJobResponse } from "@/lib/types";

export default function ErrorsPage() {
  const [failedJobs, setFailedJobs] = useState<WaybillJobResponse[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError("");

      const driversRes = await api.get<Driver[]>("/api/v1/drivers");
      if (driversRes.data) setDrivers(driversRes.data);

      const jobsRes = await api.get<{ tasks: WaybillJobResponse[] }>("/api/v1/waybill-jobs", {
        status: "failed",
        page_size: "100"
      });
      if (jobsRes.data?.tasks) setFailedJobs(jobsRes.data.tasks);
    } catch (err: any) {
      setError(err?.message || "خطا در دریافت اطلاعات خطاها");
    } finally {
      setLoading(false);
    }
  }

  const handleRetryJob = async (id: number) => {
    try {
      setError("");
      setSuccess("");
      const res = await api.post(`/api/v1/waybill-jobs/${id}/retry`, {});
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess("تسک جهت صدور مجدد به صف ارسال شد.");
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در اجرای مجدد تسک");
    }
  };

  const getDriverName = (driverId: number | null) => {
    if (!driverId) return "ثبت دستی";
    const d = drivers.find(drv => drv.id === driverId);
    return d ? d.full_name : `راننده شناسه ${driverId}`;
  };

  // Group failed jobs by error category
  const errorStats = failedJobs.reduce((acc, job) => {
    const cat = job.error_category || "UNKNOWN";
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const filteredJobs = failedJobs.filter(
    (job) =>
      job.job_id.toLowerCase().includes(search.toLowerCase()) ||
      (job.last_error && job.last_error.includes(search))
  );

  return (
    <div className="space-y-6 text-right animate-fade-in" dir="rtl">
      <div>
        <h2 className="text-2xl font-bold text-slate-100">رصد و عیب‌یابی خطاهای صدور</h2>
        <p className="mt-1 text-sm text-slate-400">
          بررسی دلایل شکست صدور بارنامه در سامانه UTCMS و ارسال دستور تلاش مجدد
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {success && (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-emerald-400">
          <CheckCircle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{success}</p>
        </div>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : (
        <>
          {/* Error category summary boxes */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ErrorCard title="خطای احراز هویت (Login)" count={errorStats["login_failed"] || 0} category="login_failed" />
            <ErrorCard title="خطای حل کپچا (Captcha)" count={errorStats["captcha_failed"] || 0} category="captcha_failed" />
            <ErrorCard title="خطای پر کردن فرم (Form)" count={errorStats["form_fill_failed"] || 0} category="form_fill_failed" />
            <ErrorCard title="سایر خطاها (Network/Unknown)" count={(errorStats["network_error"] || 0) + (errorStats["UNKNOWN"] || 0)} category="network" />
          </div>

          {/* Search/filter box */}
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-3">
            <Search className="h-5 w-5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="جستجو در متن خطا یا شناسه تسک..."
              className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
            />
          </div>

          {/* Failed tasks table */}
          <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-white/10 bg-white/5 text-slate-300">
                  <tr>
                    <th className="p-4 font-medium text-right">شناسه تسک</th>
                    <th className="p-4 font-medium text-right">راننده</th>
                    <th className="p-4 font-medium text-center">دسته‌بندی خطا</th>
                    <th className="p-4 font-medium text-right">جزئیات خطا</th>
                    <th className="p-4 font-medium text-center">آخرین تلاش</th>
                    <th className="p-4 font-medium text-center">عملیات</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10 text-slate-400">
                  {filteredJobs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-500">
                        موردی یافت نشد.
                      </td>
                    </tr>
                  ) : (
                    filteredJobs.map((job) => (
                      <tr key={job.id} className="transition-colors hover:bg-white/5">
                        <td className="p-4 font-mono text-xs text-slate-300 text-right">{job.job_id}</td>
                        <td className="p-4 text-right">{getDriverName(job.driver_id)}</td>
                        <td className="p-4 text-center">
                          <span className="inline-flex rounded-full bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-400">
                            {job.error_category === "login_failed" && "عدم ورود به سامانه"}
                            {job.error_category === "captcha_failed" && "شکست حل کپچا"}
                            {job.error_category === "form_fill_failed" && "خطای فیلدهای فرم"}
                            {job.error_category === "network_error" && "خطای ارتباط شبکه"}
                            {(!job.error_category || job.error_category === "unknown") && "خطای نامشخص"}
                          </span>
                        </td>
                        <td className="p-4 text-right text-xs text-slate-300 max-w-sm" title={job.last_error || ""}>
                          {job.last_error}
                        </td>
                        <td className="p-4 text-center text-xs font-mono">
                          {job.updated_at ? new Date(job.updated_at).toLocaleString("fa-IR") : "-"}
                        </td>
                        <td className="p-4">
                          <div className="flex items-center justify-center">
                            <button
                              onClick={() => handleRetryJob(job.id)}
                              className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-all"
                              title="صدور مجدد"
                            >
                              <Play className="h-3.5 w-3.5" />
                              تلاش مجدد
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ErrorCard({
  title,
  count,
  category
}: {
  title: string;
  count: number;
  category: string;
}) {
  return (
    <div className={`rounded-2xl border p-5 bg-gradient-to-br from-red-500/10 to-red-500/5 text-red-300 border-red-500/20`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium opacity-80">{title}</span>
        <AlertTriangle className="h-5 w-5 opacity-60 text-red-400" />
      </div>
      <div className="text-3xl font-bold font-mono">{count}</div>
      <p className="mt-1 text-xs opacity-60">تعداد کل خطاهای رخ داده</p>
    </div>
  );
}
