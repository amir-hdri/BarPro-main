"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  Activity,
  AlertCircle,
  Cpu,
  Clock,
  Database,
  RefreshCw,
  Zap,
  PowerOff,
  CheckCircle,
} from "lucide-react";
import toast from "react-hot-toast";

interface WorkerInfo {
  worker_id: string;
  hostname: string;
  status: "active" | "draining" | "offline" | "stalled";
  last_heartbeat_at: number;
  capabilities: string[];
  capacity: number;
}

interface WorkerHeartbeatResponse {
  active: Record<string, WorkerInfo>;
  stalled: Record<string, WorkerInfo>;
  stall_timeout_seconds: number;
}

export default function AdminWorkersPage() {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [stalledCount, setStalledCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  const loadWorkers = useCallback(async () => {
    try {
      const res = await api.get<WorkerHeartbeatResponse>("/api/v1/admin/workers/heartbeats");
      if (res.data) {
        const workerList = Object.values(res.data.active);
        setWorkers(workerList);
        setStalledCount(Object.keys(res.data.stalled).length);
        setLastRefreshed(new Date());
      }
    } catch {
      toast.error("خطا در بارگذاری اطلاعات Workerها");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWorkers();
    const interval = setInterval(loadWorkers, 10000); // 10s auto refresh
    return () => clearInterval(interval);
  }, [loadWorkers]);

  const handleRecover = async () => {
    setRecovering(true);
    try {
      const res = await api.post<{ recovered: string[]; count: number }>(
        "/api/v1/admin/workers/recover-stalled",
        {}
      );
      if (res.data) {
        toast.success(`بازیابی موفقیت‌آمیز بود. ${res.data.count} کار بازیابی شدند.`);
        loadWorkers();
      }
    } catch {
      toast.error("خطا در اجرای بازیابی کارهای متوقف شده");
    } finally {
      setRecovering(false);
    }
  };

  const formatLastHeartbeat = (timestamp: number) => {
    const diff = Math.floor(Date.now() / 1000 - timestamp);
    if (diff < 5) return "هم‌اکنون";
    if (diff < 60) return `${diff} ثانیه پیش`;
    const mins = Math.floor(diff / 60);
    if (mins < 60) return `${mins} دقیقه پیش`;
    const hours = Math.floor(mins / 60);
    return `${hours} ساعت پیش`;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Cpu className="text-emerald-500 w-7 h-7" />
            سیستم مدیریت Worker‌ها
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            مشاهده وضعیت زمان‌بندی، بررسی سلامت پروکسی‌ها و بار پردازشی هر Worker به صورت زنده
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setLoading(true);
              loadWorkers();
            }}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-sm transition-colors border border-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            به‌روزرسانی
          </button>

          <button
            onClick={handleRecover}
            disabled={recovering || stalledCount === 0}
            className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-850 disabled:text-slate-500 disabled:border-slate-800 text-white font-medium rounded-lg text-sm transition-colors border border-amber-700 disabled:cursor-not-allowed"
          >
            <Zap className={`w-4 h-4 ${recovering ? "animate-pulse" : ""}`} />
            بازیابی کارهای Stalled ({stalledCount})
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-slate-400 text-sm">کل Worker‌های رجیستر شده</p>
            <h3 className="text-3xl font-extrabold mt-1 text-slate-100">{workers.length}</h3>
          </div>
          <div className="bg-slate-850 p-3 rounded-lg border border-slate-850">
            <Cpu className="w-6 h-6 text-indigo-400" />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-slate-400 text-sm">پیوند خوردگان فعال</p>
            <h3 className="text-3xl font-extrabold mt-1 text-emerald-400">
              {workers.filter((w) => w.status === "active").length}
            </h3>
          </div>
          <div className="bg-slate-850 p-3 rounded-lg border border-slate-850">
            <Activity className="w-6 h-6 text-emerald-400" />
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex items-center justify-between shadow-lg">
          <div>
            <p className="text-slate-400 text-sm">وضعیت هشدار / متوقف شده (Stalled)</p>
            <h3 className={`text-3xl font-extrabold mt-1 ${stalledCount > 0 ? "text-rose-500" : "text-slate-400"}`}>
              {stalledCount}
            </h3>
          </div>
          <div className="bg-slate-850 p-3 rounded-lg border border-slate-850">
            <AlertCircle className={`w-6 h-6 ${stalledCount > 0 ? "text-rose-500 animate-bounce" : "text-slate-400"}`} />
          </div>
        </div>
      </div>

      {/* Grid of Workers */}
      {loading && workers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20">
          <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
          <p className="text-slate-400 mt-4 text-sm">در حال بارگذاری وضعیت زیرساخت...</p>
        </div>
      ) : workers.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center shadow-lg">
          <PowerOff className="w-12 h-12 text-slate-600 mx-auto" />
          <h3 className="text-lg font-bold text-slate-300 mt-4">هیچ Worker‌ای ثبت نشده است</h3>
          <p className="text-slate-500 text-sm mt-2 max-w-md mx-auto">
            هیچ کانتینر یا پردازش Worker فعالی به پایگاه‌داده متصل نشده است. لطفا کانتینرهای celery_worker را بررسی کنید.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {workers.map((worker) => {
            const isStalled = stalledCount > 0 && workers.some((w) => w.worker_id === worker.worker_id && Math.floor(Date.now() / 1000 - w.last_heartbeat_at) > 90);
            return (
              <div
                key={worker.worker_id}
                className={`bg-slate-900 border ${
                  isStalled
                    ? "border-rose-950 bg-slate-950 shadow-rose-950/10"
                    : worker.status === "draining"
                    ? "border-amber-900/50"
                    : "border-slate-800"
                } rounded-xl p-5 shadow-lg flex flex-col justify-between hover:border-slate-700 transition-colors`}
              >
                {/* Worker Top Info */}
                <div className="space-y-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-bold text-lg text-slate-100 flex items-center gap-2">
                        {worker.worker_id}
                      </h3>
                      <p className="text-slate-400 text-xs mt-0.5 font-mono">{worker.hostname}</p>
                    </div>

                    <span
                      className={`px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5 ${
                        worker.status === "active"
                          ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          : worker.status === "draining"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse"
                          : "bg-slate-800 text-slate-400 border border-slate-700"
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          worker.status === "active"
                            ? "bg-emerald-500"
                            : worker.status === "draining"
                            ? "bg-amber-500"
                            : "bg-slate-500"
                        }`}
                      />
                      {worker.status === "active" ? "فعال" : worker.status === "draining" ? "در حال تخلیه (Drain)" : "آفلاین"}
                    </span>
                  </div>

                  {/* Meta Indicators */}
                  <div className="grid grid-cols-2 gap-4 bg-slate-950 p-3 rounded-lg border border-slate-850 text-sm">
                    <div className="flex items-center gap-2 text-slate-300">
                      <Clock className="w-4 h-4 text-slate-500" />
                      <div>
                        <span className="text-xs text-slate-500 block">آخرین Heartbeat</span>
                        <span className="font-medium text-xs">
                          {formatLastHeartbeat(worker.last_heartbeat_at)}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 text-slate-300">
                      <Database className="w-4 h-4 text-slate-500" />
                      <div>
                        <span className="text-xs text-slate-500 block">ظرفیت پردازشی</span>
                        <span className="font-semibold text-xs">{worker.capacity} تسک موازی</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Capabilities */}
                <div className="mt-5 pt-4 border-t border-slate-800 flex items-center justify-between">
                  <div className="flex flex-wrap gap-1.5 items-center">
                    <span className="text-xs text-slate-500 mr-1">تخصص‌ها:</span>
                    {worker.capabilities.length > 0 ? (
                      worker.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="px-2 py-0.5 bg-slate-800 text-slate-300 border border-slate-700 text-xs rounded"
                        >
                          {cap}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-600">بدون تخصص خاص</span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    تست پروکسی پاس شده
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Footer Timestamp */}
      <div className="text-center text-xs text-slate-500 pt-4">
        آخرین به‌روزرسانی در {lastRefreshed.toLocaleTimeString("fa-IR")}
      </div>
    </div>
  );
}
