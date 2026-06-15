"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  FileText,
  Search,
  Plus,
  Loader2,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Eye,
  X,
  Play,
  Truck,
  ArrowLeft
} from "lucide-react";
import { Driver, WaybillJobResponse } from "@/lib/types";

interface TimelineEvent {
  status: string;
  message: string;
  created_at: string;
}

export default function WaybillsPage() {
  const [jobs, setJobs] = useState<WaybillJobResponse[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [driverFilter, setDriverFilter] = useState("");

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<WaybillJobResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [detailLogs, setDetailLogs] = useState<string>("");
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    driver_national_code: "",
    origin: "",
    destination: "",
    cargo_type: "",
    cargo_weight: "",
    vehicle_type: "کامیون",
    plate_number: "",
    driver_phone: "",
    cargo_description: "",
    notes: ""
  });

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError("");

      const driversRes = await api.get<Driver[]>("/api/v1/drivers");
      if (driversRes.data) setDrivers(driversRes.data);

      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      if (driverFilter) params.driver_id = driverFilter;

      const jobsRes = await api.get<{ tasks: WaybillJobResponse[] }>("/api/v1/waybill-jobs", params);
      if (jobsRes.data?.tasks) setJobs(jobsRes.data.tasks);
    } catch (err: any) {
      setError(err?.message || "خطا در دریافت اطلاعات");
    } finally {
      setLoading(false);
    }
  }

  // Refetch when filters change
  useEffect(() => {
    fetchData();
  }, [statusFilter, driverFilter]);

  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError("");
      setSuccess("");

      const payload = {
        driver_national_code: formData.driver_national_code,
        payload: {
          driver_national_code: formData.driver_national_code,
          origin: formData.origin,
          destination: formData.destination,
          cargo_type: formData.cargo_type,
          cargo_weight: Number(formData.cargo_weight),
          vehicle_type: formData.vehicle_type,
          plate_number: formData.plate_number,
          driver_phone: formData.driver_phone,
          cargo_description: formData.cargo_description || undefined,
          notes: formData.notes || undefined
        },
        max_retries: 3,
        priority: 5
      };

      const res = await api.post("/api/v1/waybill-jobs", payload);
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess("عملیات صدور بارنامه جدید با موفقیت ایجاد و به صف ارسال شد.");
        setIsCreateOpen(false);
        setFormData({
          driver_national_code: "",
          origin: "",
          destination: "",
          cargo_type: "",
          cargo_weight: "",
          vehicle_type: "کامیون",
          plate_number: "",
          driver_phone: "",
          cargo_description: "",
          notes: ""
        });
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در ثبت بارنامه");
    }
  };

  const handleRetryJob = async (id: number) => {
    try {
      setError("");
      setSuccess("");
      const res = await api.post(`/api/v1/waybill-jobs/${id}/retry`, {});
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess("درخواست تلاش مجدد با موفقیت ارسال شد.");
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در اجرای مجدد تسک");
    }
  };

  const handleViewDetails = async (job: WaybillJobResponse) => {
    setSelectedJob(job);
    setIsDetailOpen(true);
    setLoadingDetail(true);
    setTimeline([]);
    setDetailLogs("");
    try {
      const timelineRes = await api.get<{ events: TimelineEvent[] }>(`/api/v1/waybill-jobs/${job.id}/timeline`);
      if (timelineRes.data?.events) setTimeline(timelineRes.data.events);

      const logsRes = await api.get<{ logs: string }>(`/api/v1/waybill-jobs/${job.id}/logs`);
      if (logsRes.data?.logs) setDetailLogs(logsRes.data.logs);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingDetail(false);
    }
  };

  // Pre-fill form when choosing a driver
  const handleSelectDriverForForm = (driverId: string) => {
    const selected = drivers.find(d => String(d.id) === driverId);
    if (selected) {
      setFormData(prev => ({
        ...prev,
        driver_national_code: selected.driver_national_code,
        driver_phone: selected.phone || "",
        plate_number: selected.plates?.[0]?.plate_number || prev.plate_number
      }));
    }
  };

  const filteredJobs = jobs.filter(
    (job) =>
      job.job_id.toLowerCase().includes(search.toLowerCase()) ||
      (job.last_error && job.last_error.includes(search))
  );

  return (
    <div className="space-y-6 text-right animate-fade-in" dir="rtl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">مدیریت و پیگیری بارنامه‌ها</h2>
          <p className="mt-1 text-sm text-slate-400">
            لیست درخواست‌ها، پیگیری وضعیت زنده، مشاهده لاگ‌ها و ثبت بارنامه جدید
          </p>
        </div>

        <button
          onClick={() => setIsCreateOpen(true)}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-2.5 text-sm font-medium text-slate-950 transition-all hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          ثبت بارنامه جدید
        </button>
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

      {/* Filters bar */}
      <div className="grid gap-4 sm:grid-cols-4 bg-slate-900/30 border border-white/10 rounded-2xl p-4 items-center">
        <div className="sm:col-span-2 relative">
          <Search className="absolute right-3 top-3.5 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="جستجوی شناسه تسک یا پیام خطا..."
            className="w-full rounded-xl border border-white/10 bg-slate-950/40 py-2.5 pr-10 pl-4 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 outline-none"
          />
        </div>

        <div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-slate-900 p-2.5 text-sm text-slate-200 focus:border-cyan-400 focus:outline-none"
          >
            <option value="">همه وضعیت‌ها</option>
            <option value="pending">در صف انتظار</option>
            <option value="in_progress">در حال اجرا</option>
            <option value="success">موفقیت‌آمیز</option>
            <option value="failed">خطا / شکست</option>
            <option value="waiting_auth">نیاز به احراز هویت</option>
          </select>
        </div>

        <div>
          <select
            value={driverFilter}
            onChange={(e) => setDriverFilter(e.target.value)}
            className="w-full rounded-xl border border-white/10 bg-slate-900 p-2.5 text-sm text-slate-200 focus:border-cyan-400 focus:outline-none"
          >
            <option value="">همه رانندگان</option>
            {drivers.map(d => (
              <option key={d.id} value={d.id}>{d.full_name}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-white/10 bg-white/5 text-slate-300">
                <tr>
                  <th className="p-4 font-medium text-right">شناسه تسک</th>
                  <th className="p-4 font-medium text-right">منبع</th>
                  <th className="p-4 font-medium text-center">وضعیت</th>
                  <th className="p-4 font-medium text-center">تعداد تلاش</th>
                  <th className="p-4 font-medium text-right">آخرین خطا</th>
                  <th className="p-4 font-medium text-left">تاریخ ایجاد</th>
                  <th className="p-4 font-medium text-center">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10 text-slate-400">
                {filteredJobs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-8 text-center">
                      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white/5">
                        <FileText className="h-6 w-6 text-slate-500" />
                      </div>
                      <p className="mt-4 text-slate-400">هیچ تسکی یافت نشد.</p>
                    </td>
                  </tr>
                ) : (
                  filteredJobs.map((job) => (
                    <tr key={job.id} className="transition-colors hover:bg-white/5">
                      <td className="p-4 font-mono text-xs text-slate-300 text-right">{job.job_id}</td>
                      <td className="p-4 text-right">
                        {job.source === "manual" ? "دستی" : job.source === "excel" ? "اکسل" : "زمان‌بندی"}
                      </td>
                      <td className="p-4 text-center">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
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
                        </span>
                      </td>
                      <td className="p-4 text-center font-mono tabular-nums">{job.attempt_count} / {job.max_retries}</td>
                      <td className="p-4 text-right text-xs max-w-xs truncate text-red-300" title={job.last_error || ""}>
                        {job.last_error || "-"}
                      </td>
                      <td className="p-4 text-left font-mono text-xs">
                        {new Date(job.created_at).toLocaleString("fa-IR")}
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => handleViewDetails(job)}
                            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-cyan-400"
                            title="مشاهده جزئیات و لاگ"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          {job.status === "failed" && (
                            <button
                              onClick={() => handleRetryJob(job.id)}
                              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-emerald-400"
                              title="تلاش مجدد صدور"
                            >
                              <Play className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Manual Waybill Creation Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm overflow-y-auto">
          <div className="w-full max-w-2xl my-8 rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-xl text-right">
            <h3 className="text-xl font-bold text-slate-100 mb-6">ثبت درخواست جدید صدور بارنامه</h3>

            <form onSubmit={handleCreateJob} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">راننده از پیش تعریف شده</label>
                  <select
                    onChange={(e) => handleSelectDriverForForm(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="">انتخاب کنید...</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>{d.full_name}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">کد ملی راننده *</label>
                  <input
                    type="text"
                    required
                    value={formData.driver_national_code}
                    onChange={e => setFormData({...formData, driver_national_code: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">شماره پلاک کامیون *</label>
                  <input
                    type="text"
                    required
                    value={formData.plate_number}
                    onChange={e => setFormData({...formData, plate_number: e.target.value})}
                    placeholder="۱۲ع۳۴۵ایران۶۷ یا ۱۲۳۴۵منطقه آزاد"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-left"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">شماره تماس راننده *</label>
                  <input
                    type="text"
                    required
                    value={formData.driver_phone}
                    onChange={e => setFormData({...formData, driver_phone: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">مبدأ حرکت *</label>
                  <input
                    type="text"
                    required
                    value={formData.origin}
                    onChange={e => setFormData({...formData, origin: e.target.value})}
                    placeholder="استان، شهر"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-right"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">مقصد حرکت *</label>
                  <input
                    type="text"
                    required
                    value={formData.destination}
                    onChange={e => setFormData({...formData, destination: e.target.value})}
                    placeholder="استان، شهر"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-right"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">نوع کالا *</label>
                  <input
                    type="text"
                    required
                    value={formData.cargo_type}
                    onChange={e => setFormData({...formData, cargo_type: e.target.value})}
                    placeholder="مثلا سیمان فله"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-right"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">وزن بار (تن) *</label>
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={formData.cargo_weight}
                    onChange={e => setFormData({...formData, cargo_weight: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">توضیحات کالا</label>
                <textarea
                  value={formData.cargo_description}
                  onChange={e => setFormData({...formData, cargo_description: e.target.value})}
                  className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                  rows={2}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">یادداشت‌های داخلی</label>
                <input
                  type="text"
                  value={formData.notes}
                  onChange={e => setFormData({...formData, notes: e.target.value})}
                  className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                />
              </div>

              <div className="flex justify-end gap-3 pt-6 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="rounded-xl px-4 py-2 text-sm font-medium text-slate-300 hover:bg-white/10 transition-colors"
                >
                  انصراف
                </button>
                <button
                  type="submit"
                  className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-6 py-2 text-sm font-medium text-slate-950 hover:opacity-90 transition-opacity"
                >
                  ثبت و صف‌بندی صدور
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Details & Logs Modal */}
      {isDetailOpen && selectedJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm overflow-y-auto">
          <div className="w-full max-w-4xl my-8 rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-xl text-right">
            <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
              <h3 className="text-xl font-bold text-slate-100">جزئیات و لاگ‌های تسک {selectedJob.job_id.slice(0, 8)}...</h3>
              <button onClick={() => setIsDetailOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="h-5 w-5" />
              </button>
            </div>

            {loadingDetail ? (
              <div className="flex h-64 items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
              </div>
            ) : (
              <>
                <div className="grid gap-6 md:grid-cols-3">
                  {/* Timeline */}
                  <div className="md:col-span-1 border-l border-white/10 pl-4 space-y-4">
                    <h4 className="font-bold text-slate-200 mb-2">روند رویدادها</h4>
                    <div className="relative pr-4 border-r border-white/10 space-y-4 text-right">
                      {timeline.length === 0 ? (
                        <p className="text-xs text-slate-500">رویدادی ثبت نشده است.</p>
                      ) : (
                        timeline.map((evt, idx) => (
                          <div key={idx} className="relative">
                            <span className="absolute -right-[21px] top-1 h-3.5 w-3.5 rounded-full border border-slate-900 bg-cyan-400"></span>
                            <p className="text-xs font-semibold text-slate-200">{evt.status}</p>
                            <p className="text-xs text-slate-400 mt-0.5">{evt.message}</p>
                            <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                              {new Date(evt.created_at).toLocaleTimeString("fa-IR")}
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Automation Log */}
                  <div className="md:col-span-2 space-y-4">
                    <h4 className="font-bold text-slate-200">لاگ کامل اتوماسیون (Worker Log)</h4>
                    <pre className="w-full h-80 overflow-y-auto rounded-xl border border-white/10 bg-slate-950 p-4 text-left text-xs leading-5 text-slate-300 font-mono" dir="ltr">
                      {detailLogs || "لاگی در دسترس نیست."}
                    </pre>
                  </div>
                </div>

                {selectedJob.result_json?.waybill_screenshot && (
                  <div className="mt-6 border-t border-white/10 pt-4">
                    <h4 className="font-bold text-slate-200 mb-3">تصویر سند بارنامه</h4>
                    <div className="relative overflow-hidden rounded-xl border border-white/10 bg-slate-950/50 p-2 flex justify-center">
                      <img
                        src={selectedJob.result_json.waybill_screenshot.startsWith("http")
                          ? selectedJob.result_json.waybill_screenshot
                          : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "") + selectedJob.result_json.waybill_screenshot
                        }
                        alt="سند بارنامه"
                        className="max-h-[500px] object-contain rounded-lg shadow-md hover:scale-[1.01] transition-transform duration-300"
                      />
                    </div>
                  </div>
                )}
              </>
            )}

            <div className="flex justify-end gap-3 pt-6 border-t border-white/10 mt-6">
              <button
                onClick={() => setIsDetailOpen(false)}
                className="rounded-xl border border-white/10 px-6 py-2 text-sm font-medium text-slate-300 hover:bg-white/5 transition-colors"
              >
                بستن صفحه
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
