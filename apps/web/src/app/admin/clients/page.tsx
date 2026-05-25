"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CreateClientModal } from "./CreateClientModal";
import { Search, Loader2, AlertCircle, CheckCircle, Pencil, Trash2, Plus } from "lucide-react";

interface ClientItem {
  id: number;
  client_code: string;
  name: string;
  email: string;
  phone: string;
  status: string;
  max_drivers: number;
  max_plates: number;
  max_concurrent_tasks: number;
  max_daily_tasks: number;
  created_at: string;
}

export default function AdminClientsPage() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);



  useEffect(() => {
    loadClients();
  }, []);

  async function loadClients() {
    setLoading(true);
    const res = await api.get<ClientItem[]>("/api/v1/admin/clients");
    if (res.data) setClients(res.data);
    setLoading(false);
  }


  async function handleToggleStatus(id: number, currentStatus: string) {
    const newStatus = currentStatus === "active" ? "inactive" : "active";
    const res = await api.put<ClientItem>(`/api/v1/admin/clients/${id}`, { status: newStatus });
    if (res.error) setMsg({ type: "error", text: res.error });
    else loadClients();
  }

  async function handleDelete(id: number) {
    if (!confirm("آیا مطمئن هستید؟")) return;
    const res = await api.delete(`/api/v1/admin/clients/${id}`);
    if (res.error) setMsg({ type: "error", text: res.error });
    else { setMsg({ type: "success", text: "کاربر حذف شد" }); loadClients(); }
  }

  const filtered = (clients || []).filter(
    (c) => c.name.includes(search) || c.client_code.includes(search) || c.email.includes(search)
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <CreateClientModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          setMsg({ type: "success", text: "کاربر با موفقیت ایجاد شد" });
          loadClients();
        }}
      />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-bold text-slate-100">مدیریت کاربران</h2>
        <button onClick={() => setIsModalOpen(true)} className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-2.5 text-sm font-medium text-slate-950 transition-all hover:opacity-90">
          <Plus className="h-4 w-4" />
          افزودن کاربر جدید
        </button>
      </div>

      {msg && (
        <div className={`flex items-center gap-3 rounded-xl p-4 text-sm ${msg.type === "success" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
          {msg.type === "success" ? <CheckCircle className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
          {msg.text}
        </div>
      )}

      {/* Search */}
      <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-3">
        <Search className="h-5 w-5 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجوی کاربر (کد، نام، ایمیل)..."
          className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-slate-300">
            <thead className="border-b border-white/10 bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 text-right font-medium">کد مشتری</th>
                <th className="px-4 py-3 text-right font-medium">اطلاعات</th>
                <th className="px-4 py-3 text-right font-medium">وضعیت</th>
                <th className="px-4 py-3 text-right font-medium">محدودیت‌ها</th>
                <th className="px-4 py-3 text-right font-medium">تاریخ عضویت</th>
                <th className="px-4 py-3 text-right font-medium">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin" />
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">مشتری یافت نشد</td>
                </tr>
              ) : (
                (filtered || []).map((c) => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/5">
                    <td className="px-4 py-3 font-mono text-cyan-300">{c.client_code}</td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-200">{c.name}</div>
                      <div className="text-xs text-slate-500">{c.email}</div>
                      <div className="text-xs text-slate-500">{c.phone || "-"}</div>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggleStatus(c.id, c.status)}
                        className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                          c.status === "active"
                            ? "bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20"
                            : "bg-slate-500/10 text-slate-400 hover:bg-slate-500/20"
                        }`}
                      >
                        {c.status === "active" ? "فعال" : "غیرفعال"}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <div>راننده: {c.max_drivers}</div>
                      <div>پلاک: {c.max_plates}</div>
                      <div>همزمان: {c.max_concurrent_tasks}</div>
                      <div>روزانه: {c.max_daily_tasks}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-400" dir="ltr">{c.created_at.slice(0, 10)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button className="rounded p-1.5 text-slate-400 hover:bg-white/10 hover:text-cyan-400 transition-colors">
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(c.id)}
                          className="rounded p-1.5 text-slate-400 hover:bg-red-500/20 hover:text-red-400 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
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
    </div>
  );
}
