"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { CreateClientModal } from "./CreateClientModal";
import { 
  Search, 
  Loader2, 
  AlertCircle, 
  CheckCircle, 
  Pencil, 
  Trash2, 
  Plus, 
  Users as UsersIcon, 
  UserCheck, 
  UserX, 
  ShieldCheck, 
  Cpu, 
  Activity, 
  Layers 
} from "lucide-react";

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
  access_level?: string;
  created_at: string;
}

export default function AdminClientsPage() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientItem | null>(null);

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
    if (res.error) {
      setMsg({ type: "error", text: res.error });
    } else {
      setMsg({ type: "success", text: "وضعیت کاربر به‌روزرسانی شد" });
      loadClients();
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("آیا از حذف این حساب کاربری اطمینان دارید؟ تمامی داده‌های مربوطه حذف خواهند شد.")) return;
    const res = await api.delete(`/api/v1/admin/clients/${id}`);
    if (res.error) {
      setMsg({ type: "error", text: res.error });
    } else {
      setMsg({ type: "success", text: "کاربر با موفقیت حذف شد" });
      loadClients();
    }
  }

  const filtered = (clients || []).filter(
    (c) => 
      c.name.toLowerCase().includes(search.toLowerCase()) || 
      c.client_code.toLowerCase().includes(search.toLowerCase()) || 
      c.email.toLowerCase().includes(search.toLowerCase())
  );

  // Compute Stats
  const totalClients = clients.length;
  const activeClients = clients.filter(c => c.status === "active").length;
  const inactiveClients = clients.filter(c => c.status !== "active").length;
  const enterpriseClients = clients.filter(c => c.access_level === "enterprise").length;

  const accessLevelBadge = (level?: string) => {
    switch (level) {
      case "enterprise":
        return <span className="inline-flex items-center gap-1 rounded-lg bg-purple-500/10 border border-purple-500/20 px-2.5 py-1 text-xs font-black text-purple-300">سازمانی</span>;
      case "premium":
        return <span className="inline-flex items-center gap-1 rounded-lg bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 text-xs font-black text-amber-300">پریمیوم</span>;
      default:
        return <span className="inline-flex items-center gap-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-2.5 py-1 text-xs font-black text-cyan-300">استاندارد</span>;
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      
      {/* Create/Edit Modal */}
      <CreateClientModal
        isOpen={isModalOpen}
        editingClient={editingClient}
        onClose={() => {
          setIsModalOpen(false);
          setEditingClient(null);
        }}
        onSuccess={() => {
          setMsg({ 
            type: "success", 
            text: editingClient ? "مشخصات کاربر با موفقیت ویرایش شد" : "کاربر جدید با موفقیت ایجاد شد" 
          });
          loadClients();
        }}
      />

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-black text-slate-100">مدیریت کاربران و مستاجران</h2>
          <p className="mt-1.5 text-xs sm:text-sm text-slate-400">تنظیم سطوح دسترسی، ایجاد حساب کاربری چند مستاجره و نظارت بر فعالیت‌ها</p>
        </div>
        <button 
          onClick={() => {
            setEditingClient(null);
            setIsModalOpen(true);
          }} 
          className="relative group overflow-hidden rounded-xl p-[1px] transition active:scale-95 shadow-[0_4px_20px_rgba(6,182,212,0.3)] self-start sm:self-auto"
        >
          <span className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-blue-500"></span>
          <div className="relative flex items-center gap-2 rounded-[11px] bg-slate-950 px-5 py-3 text-sm font-bold text-white group-hover:bg-slate-900 transition-colors">
            <Plus className="h-4 w-4 text-cyan-400" />
            افزودن کاربر جدید
          </div>
        </button>
      </div>

      {/* Stats Dashboard Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Stat 1 */}
        <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/40 p-5 backdrop-blur-md">
          <div className="absolute top-0 right-0 h-16 w-16 rounded-bl-full bg-cyan-500/5 blur-md"></div>
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-400">
              <UsersIcon className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400">کل کاربران</p>
              <h3 className="mt-1 text-2xl font-black text-white font-mono">{totalClients}</h3>
            </div>
          </div>
        </div>

        {/* Stat 2 */}
        <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/40 p-5 backdrop-blur-md">
          <div className="absolute top-0 right-0 h-16 w-16 rounded-bl-full bg-emerald-500/5 blur-md"></div>
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400">
              <UserCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400">کاربران فعال</p>
              <h3 className="mt-1 text-2xl font-black text-white font-mono">{activeClients}</h3>
            </div>
          </div>
        </div>

        {/* Stat 3 */}
        <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/40 p-5 backdrop-blur-md">
          <div className="absolute top-0 right-0 h-16 w-16 rounded-bl-full bg-rose-500/5 blur-md"></div>
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-500/10 text-rose-400">
              <UserX className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400">غیرفعال / معلق</p>
              <h3 className="mt-1 text-2xl font-black text-white font-mono">{inactiveClients}</h3>
            </div>
          </div>
        </div>

        {/* Stat 4 */}
        <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-900/40 p-5 backdrop-blur-md">
          <div className="absolute top-0 right-0 h-16 w-16 rounded-bl-full bg-purple-500/5 blur-md"></div>
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400">مشتریان سازمانی</p>
              <h3 className="mt-1 text-2xl font-black text-white font-mono">{enterpriseClients}</h3>
            </div>
          </div>
        </div>

      </div>

      {/* Messages */}
      {msg && (
        <div className={`flex items-start gap-3 rounded-2xl border p-4 text-sm font-bold shadow-lg animate-in slide-in-from-bottom-2 ${
          msg.type === "success" 
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
            : "bg-rose-500/10 border-rose-500/20 text-rose-400"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-5 w-5 shrink-0 mt-0.5" /> : <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />}
          <div>{msg.text}</div>
        </div>
      )}

      {/* Search & Filter Bar */}
      <div className="relative group">
        <div className="absolute -inset-0.5 rounded-2xl bg-gradient-to-r from-white/10 to-transparent opacity-0 group-focus-within:opacity-100 transition-opacity blur-sm"></div>
        <div className="relative flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-900/60 p-4">
          <Search className="h-5 w-5 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="جستجوی کاربر بر اساس کد مشتری، نام کامل یا ایمیل..."
            className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500 font-medium"
          />
        </div>
      </div>

      {/* Main Table Card */}
      <div className="overflow-hidden rounded-3xl border border-white/10 bg-slate-900/30 backdrop-blur-md shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-slate-300">
            <thead className="border-b border-white/10 bg-slate-950/60">
              <tr>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">کد مشتری</th>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">اطلاعات حساب</th>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">سطح دسترسی</th>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">وضعیت</th>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">سقف و محدودیت‌های سیستم</th>
                <th className="px-6 py-4.5 text-right font-black text-slate-200">تاریخ عضویت</th>
                <th className="px-6 py-4.5 text-center font-black text-slate-200">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-3">
                      <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
                      <p className="text-xs font-bold text-slate-500">در حال بارگذاری کاربران...</p>
                    </div>
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-16 text-center text-slate-400">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Layers className="h-10 w-10 text-slate-600" />
                      <p className="font-bold text-slate-500">هیچ کاربری یافت نشد</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/5 transition-colors duration-200">
                    <td className="px-6 py-4 font-mono text-[13px] font-black text-cyan-300">{c.client_code}</td>
                    <td className="px-6 py-4">
                      <div className="font-bold text-slate-200">{c.name}</div>
                      <div className="mt-1 text-xs text-slate-400 font-mono">{c.email}</div>
                      <div className="mt-0.5 text-xs text-slate-500 font-mono">{c.phone || "بدون تلفن"}</div>
                    </td>
                    <td className="px-6 py-4">{accessLevelBadge(c.access_level)}</td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => handleToggleStatus(c.id, c.status)}
                        className={`inline-flex rounded-lg px-2.5 py-1 text-xs font-bold transition-all ${
                          c.status === "active"
                            ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 hover:bg-emerald-500/20"
                            : "bg-slate-500/10 border border-white/5 text-slate-400 hover:bg-slate-500/20"
                        }`}
                      >
                        {c.status === "active" ? "فعال" : "غیرفعال"}
                      </button>
                    </td>
                    <td className="px-6 py-4">
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-medium text-slate-400">
                        <div className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-cyan-400/50"></span>
                          <span>راننده:</span>
                          <span className="font-mono text-slate-200 font-bold">{c.max_drivers}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-blue-400/50"></span>
                          <span>پلاک:</span>
                          <span className="font-mono text-slate-200 font-bold">{c.max_plates}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-purple-400/50"></span>
                          <span>همزمان:</span>
                          <span className="font-mono text-slate-200 font-bold">{c.max_concurrent_tasks}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400/50"></span>
                          <span>روزانه:</span>
                          <span className="font-mono text-slate-200 font-bold">{c.max_daily_tasks}</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs font-medium text-slate-400 font-mono" dir="ltr">
                      {c.created_at ? c.created_at.slice(0, 10) : "-"}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-center gap-1">
                        <button 
                          onClick={() => {
                            setEditingClient(c);
                            setIsModalOpen(true);
                          }} 
                          className="rounded-xl p-2.5 text-slate-400 hover:bg-white/10 hover:text-cyan-400 transition"
                          title="ویرایش کاربر"
                        >
                          <Pencil className="h-4.5 w-4.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(c.id)}
                          className="rounded-xl p-2.5 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 transition"
                          title="حذف کاربر"
                        >
                          <Trash2 className="h-4.5 w-4.5" />
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
