"use client";

import { useEffect, useState, useMemo } from "react";
import { Search, Loader2, Filter, Activity, Users, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";

interface AuditEntry {
  id: number;
  user_type: string;
  user_id: number;
  action: string;
  entity_type?: string;
  entity_id?: number;
  description?: string;
  ip_address?: string;
  created_at: string;
}

export default function AdminAuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  useEffect(() => {
    api.get<AuditEntry[]>("/management/sync/logs").then((res) => {
      if (res.data) setEntries(res.data);
      setLoading(false);
    });
  }, []);

  const actionTypes = useMemo(() => {
    const types = new Set(entries.map((e) => e.action));
    return Array.from(types).sort();
  }, [entries]);

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (search && !e.description?.toLowerCase().includes(search.toLowerCase()) && !e.action?.toLowerCase().includes(search.toLowerCase())) return false;
      if (actionFilter && e.action !== actionFilter) return false;
      return true;
    });
  }, [entries, search, actionFilter]);

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold text-slate-100">لاگ فعالیت‌ها</h2>

      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400">کل رویدادها</span>
            <Activity className="h-4 w-4 text-cyan-400/60" />
          </div>
          <div className="text-xl font-bold text-slate-100">{entries.length.toLocaleString("fa-IR")}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400">نوع عملیات</span>
            <Filter className="h-4 w-4 text-amber-400/60" />
          </div>
          <div className="text-xl font-bold text-slate-100">{actionTypes.length.toLocaleString("fa-IR")}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400">کاربران</span>
            <Users className="h-4 w-4 text-emerald-400/60" />
          </div>
          <div className="text-xl font-bold text-slate-100">
            {new Set(entries.map(e => e.user_type)).size.toLocaleString("fa-IR")}
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-slate-900/30 p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-400">نتیجه فیلتر</span>
            <ShieldAlert className="h-4 w-4 text-purple-400/60" />
          </div>
          <div className="text-xl font-bold text-slate-100">{filtered.length.toLocaleString("fa-IR")}</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-4">
        <Search className="h-5 w-5 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجو در شرح رویداد..."
          className="flex-1 min-w-[150px] bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
        />
        <div className="h-5 w-px bg-white/10" />
        <Filter className="h-5 w-5 text-slate-400" />
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="rounded-lg border border-white/10 bg-slate-900/50 px-3 py-3.5 text-sm text-slate-100 focus:border-cyan-400"
        >
          <option value="">همه عملیات‌ها</option>
          {actionTypes.map((action) => (
            <option key={action} value={action}>{action}</option>
          ))}
        </select>
        <span className="text-xs text-slate-500 mr-auto">
          {filtered.length} از {entries.length} رویداد
        </span>
      </div>

      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30 hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 bg-slate-800/50 whitespace-nowrap">
              <tr>
                <th className="px-4 py-3 text-right font-medium text-slate-300">تاریخ</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">نوع کاربر</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">عملیات</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">شرح</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">آدرس IP</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="py-8 text-center text-slate-400"><Loader2 className="mx-auto h-6 w-6 animate-spin" /></td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={5} className="py-8 text-center text-slate-400">لاگی یافت نشد</td></tr>
              ) : (
                (filtered || []).map((e) => (
                  <tr key={e.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{e.created_at.slice(0, 19).replace("T", " ")}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded-full bg-slate-500/10 px-2.5 py-1 text-xs font-medium text-slate-300">
                        {e.user_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs rounded bg-amber-500/10 px-2 py-1 text-amber-300">
                        {e.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-xs truncate">{e.description || "—"}</td>
                    <td className="px-4 py-3 text-slate-400 font-mono text-xs">{e.ip_address || "—"}</td>
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
          <div className="py-8 text-center text-slate-400">لاگی یافت نشد</div>
        ) : (
          (filtered || []).map((e) => (
            <div key={e.id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs rounded bg-amber-500/10 px-2 py-1 text-amber-300">{e.action}</span>
                <span className="inline-flex rounded-full bg-slate-500/10 px-2.5 py-1 text-xs text-slate-300">{e.user_type}</span>
              </div>
              <p className="text-sm text-slate-200">{e.description || "—"}</p>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 font-mono">{e.ip_address || "—"}</span>
                <span className="text-slate-500">{e.created_at.slice(0, 19).replace("T", " ")}</span>
              </div>
            </div>
          ))
        )}
      </div>

    </div>
  );
}
