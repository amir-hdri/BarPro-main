"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
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

  useEffect(() => {
    api.get<AuditEntry[]>("/management/sync/logs").then((res) => {
      if (res.data) setEntries(res.data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <h2 className="text-xl font-bold text-slate-100">لاگ فعالیت‌ها</h2>

      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 bg-slate-800/50">
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
              ) : entries.length === 0 ? (
                <tr><td colSpan={5} className="py-8 text-center text-slate-400">لاگی یافت نشد</td></tr>
              ) : (
                (entries || []).map((e) => (
                  <tr key={e.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-4 py-3 text-slate-300">{e.created_at.slice(0, 19).replace("T", " ")}</td>
                    <td className="px-4 py-3 text-slate-200">{e.user_type}</td>
                    <td className="px-4 py-3 font-mono text-xs text-amber-300">{e.action}</td>
                    <td className="px-4 py-3 text-slate-300">{e.description || "-"}</td>
                    <td className="px-4 py-3 text-slate-400 font-mono text-xs">{e.ip_address || "-"}</td>
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
