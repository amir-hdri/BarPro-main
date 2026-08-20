"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { buildWebSocketUrl } from "@/lib/ws";
import { useWebSocket, WS_READY_STATE } from "@/hooks/useWebSocket";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Filter,
  Info,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import toast from "react-hot-toast";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/layout/States";
import { toPersianDigits } from "@/lib/format";

interface AdminAlertItem {
  id: number;
  tenant_id: number | null;
  severity: "info" | "warning" | "high" | "critical";
  category: string;
  message: string;
  dedupe_key: string;
  details: Record<string, any> | null;
  is_acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by: number | null;
  created_at: string;
}

interface AlertListResponse {
  total: number;
  offset: number;
  limit: number;
  items: AdminAlertItem[];
}

export default function AdminAlertsPage() {
  const [alerts, setAlerts] = useState<AdminAlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [ackFilter, setAckFilter] = useState<string>("unacknowledged");
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    const params: Record<string, string> = { limit: "100" };
    if (severityFilter) params.severity = severityFilter;
    if (ackFilter === "unacknowledged") params.is_acknowledged = "false";
    if (ackFilter === "acknowledged") params.is_acknowledged = "true";

    const res = await api.get<AlertListResponse>("/api/v1/admin/alerts", params);
    if (res.success && res.data) {
      setAlerts(res.data.items);
    } else {
      setFetchError(res.error || "خطا در بارگذاری هشدارهای سیستم");
    }
    setLoading(false);
  }, [severityFilter, ackFilter]);

  useEffect(() => {
    loadAlerts();
    const interval = setInterval(loadAlerts, 15000);
    return () => clearInterval(interval);
  }, [loadAlerts]);

  // Real-time WebSocket for admin alerts
  const { lastMessage, readyState } = useWebSocket(
    typeof window !== "undefined" ? buildWebSocketUrl("/ws/waybill") : null,
    {
      reconnectInterval: 5000,
      onOpen: () => {
        if (process.env.NODE_ENV !== "production") {
          console.log("AdminAlerts WebSocket connected");
        }
      },
      onClose: () => {
        if (process.env.NODE_ENV !== "production") {
          console.log("AdminAlerts WebSocket disconnected");
        }
      },
      onError: (e) => {
        if (process.env.NODE_ENV !== "production") {
          console.error("AdminAlerts WebSocket error:", e);
        }
      },
    }
  );

  useEffect(() => {
    if (!lastMessage) return;
    try {
      const event = JSON.parse(lastMessage.data) as { event_type?: string };
      if (
        event.event_type === "admin_alert_created" ||
        event.event_type === "admin_alert_acknowledged"
      ) {
        void loadAlerts();
      }
    } catch (e) {
      if (process.env.NODE_ENV !== "production") {
        console.error("Failed to parse WebSocket message:", e);
      }
    }
  }, [lastMessage, loadAlerts]);

  const handleAcknowledge = async (alertId: number) => {
    setActionLoading(alertId);
    const res = await api.post<{ status: string }>(`/api/v1/admin/alerts/${alertId}/acknowledge`, {});
    if (res.success && res.data?.status === "success") {
      toast.success("هشدار با موفقیت تأیید و بسته شد");
      setAlerts((prev) =>
        prev.map((a) => (a.id === alertId ? { ...a, is_acknowledged: true } : a))
      );
    } else {
      toast.error(res.error || "خطا در تأیید هشدار");
    }
    setActionLoading(null);
  };

  const handleReconcile = async (jobId: number) => {
    setActionLoading(jobId);
    const res = await api.post<{ status: string; current_status: string }>(
      `/api/v1/admin/reconcile/${jobId}`,
      {}
    );
    if (res.success && res.data?.status === "success") {
      toast.success(`تطبیق انجام شد. وضعیت جدید: ${res.data.current_status}`);
      void loadAlerts();
    } else {
      toast.error(res.error || "خطا در درخواست تطبیق");
    }
    setActionLoading(null);
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case "critical":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">
            <ShieldAlert className="w-3.5 h-3.5" /> بحرانی
          </span>
        );
      case "high":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" /> بالا
          </span>
        );
      case "warning":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-500/10 text-yellow-500 border border-yellow-500/20">
            <Bell className="w-3.5 h-3.5" /> هشدار
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20">
            <Info className="w-3.5 h-3.5" /> اطلاع
          </span>
        );
    }
  };

  const counts = {
    critical: alerts.filter((a) => a.severity === "critical" && !a.is_acknowledged).length,
    high: alerts.filter((a) => a.severity === "high" && !a.is_acknowledged).length,
    warning: alerts.filter((a) => a.severity === "warning" && !a.is_acknowledged).length,
    info: alerts.filter((a) => a.severity === "info" && !a.is_acknowledged).length,
  };

  const isWsConnected = readyState === WS_READY_STATE.OPEN;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<ShieldAlert className="h-5 w-5" />}
        title="مدیریت هشدارهای سیستم و تطبیق"
        description="پایش هوشمند هشدارهای بحرانی، عدم قطعیت بارنامه‌ها و موتور تطبیق خودکار UTCMS"
        actions={
          <>
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition ${
                isWsConnected
                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  : "bg-slate-800 text-slate-400 border-slate-700"
              }`}
              title={isWsConnected ? "اتصال زنده" : "اتصال قطع — استفاده از polling"}
            >
              {isWsConnected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {isWsConnected ? "زنده" : "آفلاین"}
            </span>
            <button
              type="button"
              onClick={loadAlerts}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl transition text-sm font-medium border border-slate-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              به‌روزرسانی
            </button>
          </>
        }
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        <SummaryCard
          label="خطاهای بحرانی"
          value={counts.critical}
          icon={<ShieldAlert className="w-5 h-5" />}
          tone="rose"
        />
        <SummaryCard
          label="هشدارهای بالا"
          value={counts.high}
          icon={<AlertTriangle className="w-5 h-5" />}
          tone="amber"
        />
        <SummaryCard
          label="هشدار عمومی"
          value={counts.warning}
          icon={<Bell className="w-5 h-5" />}
          tone="yellow"
        />
        <SummaryCard
          label="اطلاعیه‌ها"
          value={counts.info}
          icon={<Info className="w-5 h-5" />}
          tone="blue"
        />
      </div>

      {/* Filter Bar */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-3 sm:p-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Filter className="w-4 h-4" />
          <span>فیلترها:</span>
        </div>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="bg-slate-800 text-slate-200 border border-slate-700 text-sm rounded-xl px-3 py-1.5 focus:outline-none focus:border-amber-500 cursor-pointer"
        >
          <option value="">همه شدت‌ها</option>
          <option value="critical">بحرانی (Critical)</option>
          <option value="high">بالا (High)</option>
          <option value="warning">هشدار (Warning)</option>
          <option value="info">اطلاع (Info)</option>
        </select>

        <select
          value={ackFilter}
          onChange={(e) => setAckFilter(e.target.value)}
          className="bg-slate-800 text-slate-200 border border-slate-700 text-sm rounded-xl px-3 py-1.5 focus:outline-none focus:border-amber-500 cursor-pointer"
        >
          <option value="unacknowledged">فقط باز (Unacknowledged)</option>
          <option value="acknowledged">فقط تأیید شده (Acknowledged)</option>
          <option value="all">همه موارد</option>
        </select>
      </div>

      {fetchError && alerts.length > 0 && (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs font-medium text-amber-200">
          <span>به‌روزرسانی ناموفق بود؛ آخرین داده دریافت‌شده نمایش داده می‌شود.</span>
          <button
            type="button"
            onClick={() => void loadAlerts()}
            className="shrink-0 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-1.5 font-bold transition-colors hover:bg-amber-500/20"
          >
            تلاش مجدد
          </button>
        </div>
      )}

      {/* Content */}
      {loading && alerts.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : fetchError && alerts.length === 0 ? (
        <ErrorState
          message={fetchError}
          onRetry={() => void loadAlerts()}
        />
      ) : alerts.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck className="w-7 h-7 text-emerald-400" />}
          title="هیچ هشداری یافت نشد"
          description="تمامی زیرسیستم‌ها در وضعیت عادی قرار دارند."
        />
       ) : (
         <>
           {/* Desktop Table */}
           <div className="hidden md:block bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
             <div className="overflow-x-auto">
               <table className="w-full text-sm border-collapse">
                 <thead>
                   <tr className="border-b border-slate-800 bg-slate-950/40 text-slate-400 text-xs">
                     <th className="p-4 font-semibold text-start">کد / شناسه</th>
                     <th className="p-4 font-semibold text-start">شدت</th>
                     <th className="p-4 font-semibold text-start">دسته‌بندی</th>
                     <th className="p-4 font-semibold text-start">پیام هشدار</th>
                     <th className="p-4 font-semibold text-start">زمان ثبت</th>
                     <th className="p-4 font-semibold text-center">عملیات</th>
                   </tr>
                 </thead>
                 <tbody className="divide-y divide-slate-800/60 text-slate-300">
                   {alerts.map((alert) => {
                     const jobId = alert.details?.job_id;
                     return (
                       <tr
                         key={alert.id}
                         className="hover:bg-slate-800/30 transition-colors"
                       >
                         <td className="p-4 font-mono text-xs text-slate-400">#{alert.id}</td>
                         <td className="p-4">{getSeverityBadge(alert.severity)}</td>
                         <td className="p-4 font-medium text-slate-200">{alert.category}</td>
                         <td className="p-4 leading-relaxed">{alert.message}</td>
                         <td className="p-4 text-xs text-slate-400 dir-ltr text-start">
                           {new Date(alert.created_at).toLocaleString("fa-IR")}
                         </td>
                         <td className="p-4 text-center">
                           <div className="flex items-center justify-center gap-2 flex-wrap">
                             {!alert.is_acknowledged ? (
                               <button
                                 type="button"
                                 onClick={() => handleAcknowledge(alert.id)}
                                 disabled={actionLoading === alert.id}
                                 className="px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 rounded-lg transition text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                               >
                                 {actionLoading === alert.id ? (
                                   <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                 ) : (
                                   <CheckCircle2 className="w-3.5 h-3.5" />
                                 )}
                                 تأیید و بستن
                               </button>
                             ) : (
                               <span className="text-xs text-slate-500 flex items-center gap-1">
                                 <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" /> تأیید شده
                               </span>
                             )}

                             {jobId && (
                               <button
                                 type="button"
                                 onClick={() => handleReconcile(jobId)}
                                 disabled={actionLoading === jobId}
                                 className="px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-lg transition text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                               >
                                 {actionLoading === jobId ? (
                                   <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                 ) : (
                                   <RefreshCw className="w-3.5 h-3.5" />
                                 )}
                                 تطبیق UTCMS
                               </button>
                             )}
                           </div>
                         </td>
                       </tr>
                     );
                   })}
                 </tbody>
               </table>
             </div>
           </div>

           {/* Mobile Cards */}
           <div className="md:hidden space-y-3">
             {alerts.map((alert) => {
               const jobId = alert.details?.job_id;
               return (
                 <div key={alert.id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                   <div className="flex items-start justify-between gap-3">
                     <div className="flex-1">
                       <div className="flex items-center gap-2">
                         <span className="font-mono text-xs text-slate-400">#{alert.id}</span>
                         {getSeverityBadge(alert.severity)}
                       </div>
                       <p className="mt-2 text-sm font-medium text-slate-200">{alert.category}</p>
                       <p className="mt-1 text-xs text-slate-400 leading-relaxed">{alert.message}</p>
                     </div>
                   </div>
                   <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                     <span className="text-xs text-slate-500 dir-ltr">{new Date(alert.created_at).toLocaleString("fa-IR")}</span>
                     <div className="flex items-center gap-2">
                       {!alert.is_acknowledged ? (
                         <button
                           type="button"
                           onClick={() => handleAcknowledge(alert.id)}
                           disabled={actionLoading === alert.id}
                           className="px-4 py-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 rounded-xl transition text-xs font-medium flex items-center gap-1 disabled:opacity-50 touch-target"
                           aria-label="تأیید و بستن هشدار"
                         >
                           {actionLoading === alert.id ? (
                             <Loader2 className="w-4 h-4 animate-spin" />
                           ) : (
                             <CheckCircle2 className="w-4 h-4" />
                           )}
                         </button>
                       ) : (
                         <span className="text-xs text-slate-500 flex items-center gap-1 px-3 py-2 bg-slate-800/50 rounded-xl">
                           <CheckCircle2 className="w-4 h-4 text-slate-500" />
                           تأیید شده
                         </span>
                       )}
                       {jobId && (
                         <button
                           type="button"
                           onClick={() => handleReconcile(jobId)}
                           disabled={actionLoading === jobId}
                           className="px-4 py-2 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-xl transition text-xs font-medium flex items-center gap-1 disabled:opacity-50 touch-target"
                           aria-label="تطبیق UTCMS"
                         >
                           {actionLoading === jobId ? (
                             <Loader2 className="w-4 h-4 animate-spin" />
                           ) : (
                             <RefreshCw className="w-4 h-4" />
                           )}
                         </button>
                       )}
                     </div>
                   </div>
                 </div>
               );
             })}
           </div>
         </>
       )}
    </div>
  );
}

type Tone = "rose" | "amber" | "yellow" | "blue";

const toneStyles: Record<Tone, { ring: string; text: string; bg: string; border: string }> = {
  rose: { ring: "ring-rose-500/20", text: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/20" },
  amber: { ring: "ring-amber-500/20", text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  yellow: { ring: "ring-yellow-500/20", text: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/20" },
  blue: { ring: "ring-blue-500/20", text: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
};

function SummaryCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  tone: Tone;
}) {
  const t = toneStyles[tone];
  return (
    <div
      role="status"
      aria-live="polite"
      className={`relative overflow-hidden bg-slate-900/60 border ${t.border} rounded-2xl p-4 flex items-center justify-between shadow-sm`}
    >
      <div className={`absolute -end-6 -top-6 h-16 w-16 rounded-full ${t.bg} blur-2xl opacity-60`} />
      <div className="relative">
        <p className="text-xs text-slate-400 font-medium">{label}</p>
        <p className={`mt-1 text-2xl sm:text-3xl font-black ${t.text}`}>
          {toPersianDigits(value)}
        </p>
      </div>
      <div className={`relative flex h-10 w-10 items-center justify-center rounded-xl ${t.bg} ${t.text} border ${t.border}`}>
        {icon}
      </div>
    </div>
  );
}
