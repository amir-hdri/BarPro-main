"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
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

function getAdminWsUrl(): string {
  if (typeof window === "undefined") return "";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (window.location.port === "3000") {
    return `${protocol}//${window.location.hostname}:8000/ws/waybill`;
  }
  return `${protocol}//${window.location.host}/ws/waybill`;
}

export default function AdminAlertsPage() {
  const [alerts, setAlerts] = useState<AdminAlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [ackFilter, setAckFilter] = useState<string>("unacknowledged");
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    const params: Record<string, string> = { limit: "100" };
    if (severityFilter) params.severity = severityFilter;
    if (ackFilter === "unacknowledged") params.is_acknowledged = "false";
    if (ackFilter === "acknowledged") params.is_acknowledged = "true";

    try {
      const res = await api.get<AlertListResponse>("/api/v1/admin/alerts", params);
      if (res.data?.items) {
        setAlerts(res.data.items);
      }
    } catch {
      toast.error("خطا در بارگذاری هشدارهای سیستم");
    } finally {
      setLoading(false);
    }
  }, [severityFilter, ackFilter]);

  useEffect(() => {
    loadAlerts();
    const interval = setInterval(loadAlerts, 15000);
    return () => clearInterval(interval);
  }, [loadAlerts]);

  // Real-time WebSocket for admin alerts
  const { lastMessage, readyState } = useWebSocket(
    typeof window !== "undefined" ? getAdminWsUrl() : null,
    {
      reconnectInterval: 5000,
      onOpen: () => {
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.log("AdminAlerts WebSocket connected");
        }
      },
      onClose: () => {
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.log("AdminAlerts WebSocket disconnected");
        }
      },
      onError: (e) => {
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.error("AdminAlerts WebSocket error:", e);
        }
      },
    }
  );

  useEffect(() => {
    if (!lastMessage) return;
    try {
      const event = JSON.parse(lastMessage.data);
      if (event.event_type === "admin_alert_created") {
        setAlerts((prev) => [event, ...prev]);
      } else if (event.event_type === "admin_alert_acknowledged") {
        setAlerts((prev) =>
          prev.map((a) =>
            a.id === event.alert_id ? { ...a, is_acknowledged: true } : a
          )
        );
      }
    } catch (e) {
      if (process.env.NODE_ENV !== "production") {
        // eslint-disable-next-line no-console
        console.error("Failed to parse WebSocket message:", e);
      }
    }
  }, [lastMessage]);

  const handleAcknowledge = async (alertId: number) => {
    setActionLoading(alertId);
    try {
      const res = await api.post<{ status: string }>(`/api/v1/admin/alerts/${alertId}/acknowledge`, {});
      if (res.data?.status === "success") {
        toast.success("هشدار با موفقیت تأیید و بسته شد");
        setAlerts((prev) =>
          prev.map((a) => (a.id === alertId ? { ...a, is_acknowledged: true } : a))
        );
      } else {
        toast.error("خطا در تأیید هشدار");
      }
    } catch {
      toast.error("خطا در ارتباط با سرور");
    } finally {
      setActionLoading(null);
    }
  };

  const handleReconcile = async (jobId: number) => {
    setActionLoading(jobId);
    try {
      const res = await api.post<{ status: string; current_status: string }>(
        `/api/v1/admin/reconcile/${jobId}`,
        {}
      );
      if (res.data?.status === "success") {
        toast.success(`تطبیق انجام شد. وضعیت جدید: ${res.data.current_status}`);
        loadAlerts();
      } else {
        toast.error("خطا در تطبیق بارنامه");
      }
    } catch {
      toast.error("خطا در درخواست تطبیق");
    } finally {
      setActionLoading(null);
    }
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

  const isWsConnected = readyState === WebSocket.OPEN;

  return (
    <div className="p-6 space-y-6 dir-rtl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-7 h-7 text-amber-500" />
            مدیریت هشدارهای سیستم و تطبیق (Admin Alerts)
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            پایش هوشمند هشدارهای بحرانی، عدم قطعیت بارنامه‌ها و موتور تطبیق خودکار UTCMS
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* WebSocket connection status */}
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
            onClick={loadAlerts}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl transition text-sm font-medium border border-slate-700"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            به‌روزرسانی
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900/60 border border-rose-500/20 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">خطاهای بحرانی</p>
            <p className="text-2xl font-bold text-rose-500 mt-1">{counts.critical}</p>
          </div>
          <ShieldAlert className="w-8 h-8 text-rose-500/40" />
        </div>

        <div className="bg-slate-900/60 border border-amber-500/20 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">هشدارهای بالا (High)</p>
            <p className="text-2xl font-bold text-amber-500 mt-1">{counts.high}</p>
          </div>
          <AlertTriangle className="w-8 h-8 text-amber-500/40" />
        </div>

        <div className="bg-slate-900/60 border border-yellow-500/20 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">هشدار عمومی</p>
            <p className="text-2xl font-bold text-yellow-500 mt-1">{counts.warning}</p>
          </div>
          <Bell className="w-8 h-8 text-yellow-500/40" />
        </div>

        <div className="bg-slate-900/60 border border-blue-500/20 rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">اطلاعیه‌ها</p>
            <p className="text-2xl font-bold text-blue-500 mt-1">{counts.info}</p>
          </div>
          <Info className="w-8 h-8 text-blue-500/40" />
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Filter className="w-4 h-4" />
          <span>فیلترها:</span>
        </div>

        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="bg-slate-800 text-slate-200 border border-slate-700 text-sm rounded-xl px-3 py-1.5 focus:outline-none focus:border-amber-500"
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
          className="bg-slate-800 text-slate-200 border border-slate-700 text-sm rounded-xl px-3 py-1.5 focus:outline-none focus:border-amber-500"
        >
          <option value="unacknowledged">فقط باز (Unacknowledged)</option>
          <option value="acknowledged">فقط تأیید شده (Acknowledged)</option>
          <option value="all">همه موارد</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
            <span>در حال دریافت لیست هشدارها...</span>
          </div>
        ) : alerts.length === 0 ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
            <ShieldCheck className="w-12 h-12 text-emerald-500/40" />
            <span className="text-lg font-medium text-slate-300">هیچ هشداری یافت نشد</span>
            <span className="text-xs text-slate-500">تمامی زیرسیستم‌ها در وضعیت عادی قرار دارند.</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/40 text-slate-400 text-xs">
                  <th className="p-4 font-semibold">کد / شناسه</th>
                  <th className="p-4 font-semibold">شدت</th>
                  <th className="p-4 font-semibold">دسته‌بندی</th>
                  <th className="p-4 font-semibold">پیام هشدار</th>
                  <th className="p-4 font-semibold">زمان ثبت</th>
                  <th className="p-4 font-semibold text-center">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {alerts.map((alert) => {
                  const jobId = alert.details?.job_id;
                  return (
                    <tr key={alert.id} className="hover:bg-slate-800/30 transition">
                      <td className="p-4 font-mono text-xs text-slate-400">#{alert.id}</td>
                      <td className="p-4">{getSeverityBadge(alert.severity)}</td>
                      <td className="p-4 font-medium text-slate-200">{alert.category}</td>
                      <td className="p-4 leading-relaxed">{alert.message}</td>
                      <td className="p-4 text-xs text-slate-400 dir-ltr text-right">
                        {new Date(alert.created_at).toLocaleString("fa-IR")}
                      </td>
                      <td className="p-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          {!alert.is_acknowledged ? (
                            <button
                              onClick={() => handleAcknowledge(alert.id)}
                              disabled={actionLoading === alert.id}
                              className="px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 rounded-lg transition text-xs font-medium flex items-center gap-1"
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
                              onClick={() => handleReconcile(jobId)}
                              disabled={actionLoading === jobId}
                              className="px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-lg transition text-xs font-medium flex items-center gap-1"
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
        )}
      </div>
    </div>
  );
}
