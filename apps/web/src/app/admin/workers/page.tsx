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
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/layout/States";
import { toPersianDigits } from "@/lib/format";

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
  const [fetchError, setFetchError] = useState<string | null>(null);

  const loadWorkers = useCallback(async () => {
    setFetchError(null);
    const res = await api.get<WorkerHeartbeatResponse>("/api/v1/admin/workers/heartbeats");
    if (res.success && res.data) {
      const stalledIds = new Set(Object.keys(res.data.stalled));
      const workerList = Object.values(res.data.active).map((worker) =>
        stalledIds.has(worker.worker_id) ? { ...worker, status: "stalled" as const } : worker
      );
      setWorkers(workerList);
      setStalledCount(Object.keys(res.data.stalled).length);
      setLastRefreshed(new Date());
    } else {
      setFetchError(res.error || "خطا در بارگذاری اطلاعات Workerها");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadWorkers();
    const interval = setInterval(loadWorkers, 10000); // 10s auto refresh
    return () => clearInterval(interval);
  }, [loadWorkers]);

  const handleRecover = async () => {
    setRecovering(true);
    const res = await api.post<{ recovered: string[]; count: number }>(
      "/api/v1/admin/workers/recover-stalled",
      {}
    );
    if (res.success && res.data) {
      toast.success(`بازیابی موفقیت‌آمیز بود. ${res.data.count} کار بازیابی شدند.`);
      void loadWorkers();
    } else {
      toast.error(res.error || "خطا در اجرای بازیابی کارهای متوقف شده");
    }
    setRecovering(false);
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
    <div className="space-y-6">
      <PageHeader
        icon={<Cpu className="h-5 w-5" />}
        title="سیستم مدیریت Worker‌ها"
        description="مشاهده وضعیت زمان‌بندی، بررسی سلامت پروکسی‌ها و بار پردازشی هر Worker به صورت زنده"
        badge={
          stalledCount > 0 ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-black rounded-full bg-rose-500/10 text-rose-300 border border-rose-500/20 animate-pulse">
              {toPersianDigits(stalledCount)} Stalled
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-black rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              سالم
            </span>
          )
        }
        actions={
          <>
            <button
              type="button"
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
              type="button"
              onClick={handleRecover}
              disabled={recovering || stalledCount === 0}
              className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-800 disabled:text-slate-500 disabled:border-slate-700 text-white font-medium rounded-lg text-sm transition-colors border border-amber-700 disabled:cursor-not-allowed"
            >
              <Zap className={`w-4 h-4 ${recovering ? "animate-pulse" : ""}`} />
              بازیابی کارهای Stalled ({toPersianDigits(stalledCount)})
            </button>
          </>
        }
      />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
        <StatCard
          label="کل Worker‌های رجیستر شده"
          value={workers.length}
          icon={<Cpu className="w-5 h-5" />}
          tone="indigo"
        />
        <StatCard
          label="Worker‌های فعال"
          value={workers.filter((w) => w.status === "active").length}
          icon={<Activity className="w-5 h-5" />}
          tone="emerald"
        />
        <StatCard
          label="Worker‌های متوقف شده"
          value={stalledCount}
          icon={<AlertCircle className="w-5 h-5" />}
          tone={stalledCount > 0 ? "rose" : "slate"}
        />
      </div>

      {fetchError && workers.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs font-medium text-amber-200">
          <span>به‌روزرسانی ناموفق بود؛ آخرین snapshot Workerها نمایش داده می‌شود.</span>
          <button
            type="button"
            onClick={() => {
              setLoading(true);
              void loadWorkers();
            }}
            className="shrink-0 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 font-bold transition-colors hover:bg-amber-500/20"
          >
            تلاش مجدد
          </button>
        </div>
      )}

      {/* Grid of Workers */}
      {loading && workers.length === 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      ) : fetchError && workers.length === 0 ? (
        <ErrorState
          message={fetchError}
          onRetry={() => {
            setLoading(true);
            void loadWorkers();
          }}
        />
      ) : workers.length === 0 ? (
        <EmptyState
          icon={<PowerOff className="w-7 h-7 text-slate-500" />}
          title="هیچ Worker‌ای ثبت نشده است"
          description="هیچ کانتینر یا پردازش Worker فعالی به پایگاه‌داده متصل نشده است. لطفا کانتینرهای celery_worker را بررسی کنید."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {workers.map((worker) => {
            const isStalled = worker.status === "stalled";
            return (
              <article
                key={worker.worker_id}
                className={`relative overflow-hidden bg-slate-900/60 border ${
                  isStalled
                    ? "border-rose-500/30 bg-rose-950/10"
                    : worker.status === "draining"
                    ? "border-amber-500/30"
                    : "border-slate-800 hover:border-slate-700"
                } rounded-2xl p-5 shadow-sm flex flex-col justify-between transition-colors`}
              >
                {/* Worker Top Info */}
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="font-black text-base sm:text-lg text-slate-100 flex items-center gap-2 truncate">
                        <Cpu className="h-4 w-4 text-indigo-400 shrink-0" />
                        {worker.worker_id}
                      </h3>
                      <p className="text-slate-400 text-xs mt-0.5 font-mono truncate" dir="ltr">
                        {worker.hostname}
                      </p>
                    </div>

                    <span
                      className={`shrink-0 px-2.5 py-1 rounded-full text-[10px] font-black flex items-center gap-1.5 border ${
                        worker.status === "active"
                          ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                          : worker.status === "draining"
                          ? "bg-amber-500/10 text-amber-400 border-amber-500/20 animate-pulse"
                          : worker.status === "stalled"
                          ? "bg-rose-500/10 text-rose-400 border-rose-500/20 animate-pulse"
                          : "bg-slate-800 text-slate-400 border-slate-700"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          worker.status === "active"
                            ? "bg-emerald-500 animate-pulse"
                            : worker.status === "draining"
                            ? "bg-amber-500"
                            : worker.status === "stalled"
                            ? "bg-rose-500"
                            : "bg-slate-500"
                        }`}
                      />
                      {worker.status === "active"
                        ? "فعال"
                        : worker.status === "draining"
                        ? "در حال تخلیه"
                        : worker.status === "stalled"
                        ? "متوقف شده"
                        : "آفلاین"}
                    </span>
                  </div>

                  {/* Meta Indicators */}
                  <div className="grid grid-cols-2 gap-3 bg-slate-950 p-3 rounded-xl border border-slate-800 text-sm">
                    <div className="flex items-center gap-2 text-slate-300 min-w-0">
                      <Clock className="w-4 h-4 text-slate-500 shrink-0" />
                      <div className="min-w-0">
                        <span className="text-[10px] text-slate-500 block">آخرین Heartbeat</span>
                        <span className="font-semibold text-xs truncate block">
                          {formatLastHeartbeat(worker.last_heartbeat_at)}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 text-slate-300 min-w-0">
                      <Database className="w-4 h-4 text-slate-500 shrink-0" />
                      <div className="min-w-0">
                        <span className="text-[10px] text-slate-500 block">ظرفیت پردازشی</span>
                        <span className="font-semibold text-xs truncate block">
                          {toPersianDigits(worker.capacity)} تسک موازی
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Capabilities */}
                <div className="mt-5 pt-4 border-t border-slate-800 flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex flex-wrap gap-1.5 items-center min-w-0">
                    <span className="text-xs text-slate-500 shrink-0">تخصص‌ها:</span>
                    {worker.capabilities.length > 0 ? (
                      worker.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="px-2 py-0.5 bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-bold rounded-md"
                        >
                          {cap}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-600">بدون تخصص خاص</span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 text-[10px] text-slate-500 shrink-0">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    تست پروکسی پاس شده
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Footer Timestamp */}
      <div className="text-center text-xs text-slate-500 pt-2">
        آخرین به‌روزرسانی در {lastRefreshed.toLocaleTimeString("fa-IR")}
      </div>
    </div>
  );
}

type StatTone = "indigo" | "emerald" | "rose" | "slate";

const statToneStyles: Record<StatTone, { text: string; bg: string; border: string }> = {
  indigo: { text: "text-indigo-400", bg: "bg-indigo-500/10", border: "border-indigo-500/20" },
  emerald: { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  rose: { text: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/20" },
  slate: { text: "text-slate-400", bg: "bg-slate-500/10", border: "border-slate-500/20" },
};

function StatCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone: StatTone;
}) {
  const t = statToneStyles[tone];
  return (
    <div className={`relative overflow-hidden bg-slate-900/60 border ${t.border} rounded-2xl p-5 flex items-center justify-between shadow-sm`}>
      <div className={`absolute -end-6 -top-6 h-16 w-16 rounded-full ${t.bg} blur-2xl opacity-60`} />
      <div className="relative">
        <p className="text-slate-400 text-xs sm:text-sm font-medium">{label}</p>
        <h3 className={`mt-1 text-2xl sm:text-3xl font-black ${t.text}`}>
          {toPersianDigits(value)}
        </h3>
      </div>
      <div className={`relative flex h-10 w-10 items-center justify-center rounded-xl ${t.bg} ${t.text} border ${t.border}`}>
        {icon}
      </div>
    </div>
  );
}
