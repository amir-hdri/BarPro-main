"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { AdminClientSummary } from "@/lib/types";
import {
  Users,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Search,
} from "lucide-react";



export default function AdminDashboardPage() {
  const [summary, setSummary] = useState<AdminClientSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");


  useEffect(() => {
    loadSummary();
  }, []);

  async function loadSummary() {
    setLoading(true);
    const res = await api.get<AdminClientSummary>("/admin/reports/clients/summary", {
      page: "1",
      page_size: "50",
    });
    if (res.data) setSummary(res.data);
    setLoading(false);
  }

  const filtered = (summary?.rows || []).filter((c) =>
    c.name.includes(search) || c.client_code.includes(search) || c.email.includes(search)
  ) || [];

  const totalClients = summary?.total_clients || 0;
  const activeClients = summary?.active_clients || 0;
  const totalDrivers = (summary?.rows || []).reduce((a, c) => a + c.total_drivers, 0) || 0;

  const totalSuccess = (summary?.rows || []).reduce((a, c) => a + c.success_jobs, 0) || 0;
  const totalFailed = (summary?.rows || []).reduce((a, c) => a + c.failed_jobs, 0) || 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="کل مشتریان"
          value={totalClients}
          icon={Users}
          sub={`فعال: ${activeClients}`}
          color="cyan"
        />
        <StatCard
          title="کل رانندگان"
          value={totalDrivers}
          icon={Users}
          color="amber"
        />
        <StatCard
          title="بارنامه‌های موفق"
          value={totalSuccess}
          icon={CheckCircle}
          color="emerald"
        />
        <StatCard
          title="بارنامه‌های ناموفق"
          value={totalFailed}
          icon={AlertTriangle}
          color="red"
        />
      </div>

      {/* Search */}
      <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-3">
        <Search className="h-5 w-5 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجوی مشتری..."
          className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
        />
      </div>

      {/* Client table */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 bg-slate-800/50 whitespace-nowrap">
              <tr>
                <th className="px-4 py-3 text-right font-medium text-slate-300">کد مشتری</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">نام</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">وضعیت</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">رانندگان</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">پلاک‌ها</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">کل بارنامه</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">موفق</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">ناموفق</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">نرخ موفقیت</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-400">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</td>
                </tr>
              ) : (
                (filtered || []).map((c) => (
                  <tr key={c.client_id} className="border-b border-white/5 transition-colors hover:bg-white/5 whitespace-nowrap">
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
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
  value: number;
  icon: typeof Users;
  sub?: string;
  color: "cyan" | "amber" | "emerald" | "red";
}) {
  const bgMap = {
    cyan: "from-cyan-500/10 to-cyan-500/5 text-cyan-300",
    amber: "from-amber-500/10 to-amber-500/5 text-amber-300",
    emerald: "from-emerald-500/10 to-emerald-500/5 text-emerald-300",
    red: "from-red-500/10 to-red-500/5 text-red-300",
  };


  return (
    <div className={`rounded-2xl border border-white/10 bg-gradient-to-br p-5 ${bgMap[color]}`}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium opacity-80">{title}</span>
        <Icon className="h-5 w-5 opacity-60" />
      </div>
      <div className="text-3xl font-bold">{value.toLocaleString("fa-IR")}</div>
      {sub && <p className="mt-1 text-xs opacity-60">{sub}</p>}
    </div>
  );
}
