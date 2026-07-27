"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { AdminClientSummary } from "@/lib/types";
import {
  Users,
  CheckCircle,
  Loader2,
  Search,
  Activity,
  Clock,
  XCircle,
  TrendingUp,
  RefreshCw,
  Server,
  Download,
  ArrowUpDown,
} from "lucide-react";

export default function AdminDashboardPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<AdminClientSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"total_jobs" | "success_rate" | "name" | "active_drivers">("total_jobs");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    loadSummary();
  }, []);

  async function loadSummary() {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await api.get<AdminClientSummary>("/api/v1/admin/reports/clients/summary", {
        page: "1",
        page_size: "50",
      });
      if (res.data) setSummary(res.data);
      else setFetchError(res.error || 'خطا در بارگذاری گزارش');
    } catch {
      setFetchError('خطا در ارتباط با سرور');
    }
    setLoading(false);
  }

  const handleSort = (field: "total_jobs" | "success_rate" | "name" | "active_drivers") => {
    if (sortBy === field) {
      setSortOrder(prev => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  const exportCSV = () => {
    if (!summary?.rows || summary.rows.length === 0) return;
    const headers = ["کد مشتری", "نام", "ایمیل", "وضعیت", "رانندگان", "پلاک‌ها", "کل بارنامه", "موفق", "ناموفق", "نرخ موفقیت (%)", "آخرین فعالیت"];
    const rows = summary.rows.map(c => [
      c.client_code,
      c.name,
      c.email,
      c.status === "active" ? "فعال" : "غیرفعال",
      c.total_drivers,
      c.total_plates,
      c.total_jobs,
      c.success_jobs,
      c.failed_jobs,
      c.success_rate,
      c.last_activity || ""
    ]);

    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `barpro_clients_summary_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filtered = (summary?.rows || [])
    .filter((c) =>
      c.name.includes(search) || c.client_code.includes(search) || c.email.includes(search)
    )
    .sort((a, b) => {
      let aVal: any = a[sortBy];
      let bVal: any = b[sortBy];
      if (typeof aVal === "string") {
        return sortOrder === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortOrder === "asc" ? aVal - bVal : bVal - aVal;
    });

  const totalClients = summary?.total_clients || 0;
  const activeClients = summary?.active_clients || 0;

  const totalSuccess = (summary?.rows || []).reduce((a, c) => a + c.success_jobs, 0) || 0;
  const totalFailed = (summary?.rows || []).reduce((a, c) => a + c.failed_jobs, 0) || 0;
  const totalJobs = (summary?.rows || []).reduce((a, c) => a + c.total_jobs, 0) || 0;
  const pendingJobs = Math.max(0, totalJobs - totalSuccess - totalFailed);
  const successRate = totalJobs > 0 ? Math.round((totalSuccess / totalJobs) * 100) : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {fetchError && (
        <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400 flex items-center gap-2">
          <span className="font-bold">خطا:</span> {fetchError}
        </div>
      )}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <StatCard
          title="کل مشتریان"
          value={totalClients}
          icon={Users}
          sub={`فعال: ${activeClients}`}
          color="cyan"
        />
        <StatCard
          title="مشتریان فعال"
          value={activeClients}
          icon={Activity}
          color="emerald"
        />
        <StatCard
          title="کل بارنامه‌ها"
          value={totalJobs}
          icon={CheckCircle}
          color="blue"
        />
        <StatCard
          title="نرخ موفقیت"
          value={`${successRate}%`}
          icon={TrendingUp}
          color="green"
          sub={`${pendingJobs} در انتظار`}
        />
        <StatCard
          title="در انتظار پردازش"
          value={pendingJobs}
          icon={Clock}
          color="amber"
        />
        <StatCard
          title="ناموفق"
          value={totalFailed}
          icon={XCircle}
          color="red"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-slate-400 ml-2">اقدامات سریع:</span>
          <button
            onClick={loadSummary}
            className="flex items-center gap-2 rounded-lg bg-white/5 hover:bg-white/10 hover:text-cyan-300 px-4 py-2.5 text-sm text-slate-200 transition"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            بروزرسانی داده‌ها
          </button>
          <button
            onClick={() => router.push("/admin/health")}
            className="flex items-center gap-2 rounded-lg bg-white/5 hover:bg-white/10 hover:text-cyan-300 px-4 py-2.5 text-sm text-slate-200 transition"
          >
            <Server className="h-4 w-4" />
            سلامت سیستم
          </button>
          <button
            onClick={() => router.push("/admin/clients")}
            className="flex items-center gap-2 rounded-lg bg-white/5 hover:bg-white/10 hover:text-cyan-300 px-4 py-2.5 text-sm text-slate-200 transition"
          >
            <Users className="h-4 w-4" />
            مدیریت مستاجران
          </button>
        </div>

        <button
          onClick={exportCSV}
          disabled={!summary?.rows || summary.rows.length === 0}
          className="flex items-center gap-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 hover:bg-cyan-500/20 px-4 py-2.5 text-sm text-cyan-300 font-bold transition disabled:opacity-40"
        >
          <Download className="h-4 w-4" />
          خروجی CSV اکسل
        </button>
      </div>

      <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-3">
        <Search className="h-5 w-5 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجوی مشتری بر اساس نام، کد یا ایمیل..."
          className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
        />
      </div>

      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30 hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 bg-slate-800/50 whitespace-nowrap">
              <tr>
                <th className="px-4 py-3 text-right font-medium text-slate-300">کد مشتری</th>
                <th 
                  onClick={() => handleSort("name")}
                  className="px-4 py-3 text-right font-medium text-slate-300 cursor-pointer hover:text-cyan-300 transition"
                >
                  <div className="flex items-center gap-1">
                    نام
                    <ArrowUpDown className="h-3 w-3 opacity-60" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">وضعیت</th>
                <th 
                  onClick={() => handleSort("active_drivers")}
                  className="px-4 py-3 text-right font-medium text-slate-300 cursor-pointer hover:text-cyan-300 transition"
                >
                  <div className="flex items-center gap-1">
                    رانندگان
                    <ArrowUpDown className="h-3 w-3 opacity-60" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">پلاک‌ها</th>
                <th 
                  onClick={() => handleSort("total_jobs")}
                  className="px-4 py-3 text-right font-medium text-slate-300 cursor-pointer hover:text-cyan-300 transition"
                >
                  <div className="flex items-center gap-1">
                    کل بارنامه
                    <ArrowUpDown className="h-3 w-3 opacity-60" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">موفق</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">ناموفق</th>
                <th 
                  onClick={() => handleSort("success_rate")}
                  className="px-4 py-3 text-right font-medium text-slate-300 cursor-pointer hover:text-cyan-300 transition"
                >
                  <div className="flex items-center gap-1">
                    نرخ موفقیت
                    <ArrowUpDown className="h-3 w-3 opacity-60" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">آخرین فعالیت</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</td>
                </tr>
              ) : (
                (filtered || []).map((c) => (
                  <tr key={c.client_id} className="border-b border-white/5 transition-colors hover:bg-white/5">
                    <td className="px-4 py-3 text-slate-200">{c.client_code}</td>
                    <td className="px-4 py-3 text-slate-200">
                      <div className="font-medium">{c.name}</div>
                      <div className="text-xs text-slate-400">{c.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                        c.status === "active"
                          ? "bg-emerald-500/10 text-emerald-300"
                          : "bg-slate-500/10 text-slate-400"
                      }`}>
                        {c.status === "active" ? "فعال" : "غیرفعال"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-200">{c.total_drivers}</td>
                    <td className="px-4 py-3 text-slate-200">{c.total_plates}</td>
                    <td className="px-4 py-3 text-slate-200">{c.total_jobs}</td>
                    <td className="px-4 py-3 text-emerald-300">{c.success_jobs}</td>
                    <td className="px-4 py-3 text-red-300">{c.failed_jobs}</td>
                    <td className="px-4 py-3">
                      <span className={`font-medium ${
                        c.success_rate >= 80 ? "text-emerald-300" : c.success_rate >= 50 ? "text-amber-300" : "text-red-300"
                      }`}>
                        {c.success_rate}%
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      {c.last_activity ? c.last_activity.slice(0, 10) : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="block md:hidden space-y-3">
        {loading ? (
          <div className="py-8 text-center text-slate-400">
            <Loader2 className="mx-auto h-6 w-6 animate-spin" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</div>
        ) : (
          (filtered || []).map((c) => (
            <div key={c.client_id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-200">{c.name}</div>
                  <div className="text-xs text-slate-400">{c.client_code}</div>
                </div>
                <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                  c.status === "active"
                    ? "bg-emerald-500/10 text-emerald-300"
                    : "bg-slate-500/10 text-slate-400"
                }`}>
                  {c.status === "active" ? "فعال" : "غیرفعال"}
                </span>
              </div>
              <div className="flex items-center justify-around text-center text-sm">
                <div>
                  <div className="text-slate-400 text-xs">رانندگان</div>
                  <div className="font-bold text-slate-200">{c.total_drivers}</div>
                </div>
                <div>
                  <div className="text-slate-400 text-xs">پلاک‌ها</div>
                  <div className="font-bold text-slate-200">{c.total_plates}</div>
                </div>
                <div>
                  <div className="text-slate-400 text-xs">موفقیت</div>
                  <div className={`font-bold ${c.success_rate >= 80 ? "text-emerald-300" : c.success_rate >= 50 ? "text-amber-300" : "text-red-300"}`}>
                    {c.success_rate}%
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-around text-center text-sm">
                <div>
                  <div className="text-slate-400 text-xs">کل</div>
                  <div className="font-bold text-slate-200">{c.total_jobs}</div>
                </div>
                <div>
                  <div className="text-slate-400 text-xs">موفق</div>
                  <div className="font-bold text-emerald-300">{c.success_jobs}</div>
                </div>
                <div>
                  <div className="text-slate-400 text-xs">ناموفق</div>
                  <div className="font-bold text-red-300">{c.failed_jobs}</div>
                </div>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs text-slate-500">
                <span>آخرین فعالیت: {c.last_activity ? c.last_activity.slice(0, 10) : "—"}</span>
              </div>
            </div>
          ))
        )}
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
  icon: React.ComponentType<{ className?: string }>;
  sub?: string;
  color: "cyan" | "amber" | "emerald" | "red" | "blue" | "green";
}) {
  const bgMap = {
    cyan: "from-cyan-500/10 to-cyan-500/5 text-cyan-300 border-cyan-500/20",
    amber: "from-amber-500/10 to-amber-500/5 text-amber-300 border-amber-500/20",
    emerald: "from-emerald-500/10 to-emerald-500/5 text-emerald-300 border-emerald-500/20",
    red: "from-red-500/10 to-red-500/5 text-red-300 border-red-500/20",
    blue: "from-blue-500/10 to-blue-500/5 text-blue-300 border-blue-500/20",
    green: "from-green-500/10 to-green-500/5 text-green-300 border-green-500/20",
  };

  return (
    <div className={`rounded-2xl border bg-gradient-to-br p-5 ${bgMap[color]}`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium opacity-80">{title}</span>
        <Icon className="h-5 w-5 opacity-60" />
      </div>
      <div className="text-3xl font-bold">
        {typeof value === "number" ? value.toLocaleString("fa-IR") : value}
      </div>
      {sub && <p className="mt-1 text-xs opacity-60">{sub}</p>}
    </div>
  );
}
