"use client";

import { Fragment, useEffect, useState } from "react";
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
  Layers,
  ChevronDown,
  ChevronUp,
  BarChart3,
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

interface ClientDetail {
  total_jobs: number;
  success_jobs: number;
  failed_jobs: number;
  success_rate: number;
  total_drivers: number;
  active_drivers: number;
  total_plates: number;
  failure_reasons: Record<string, number>;
  driver_breakdown: Array<{
    driver_name: string;
    total_jobs: number;
    success: number;
    failed: number;
    success_rate: number;
  }>;
}

export default function AdminClientsPage() {
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientItem | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [clientDetails, setClientDetails] = useState<Record<number, ClientDetail>>({});
  const [detailLoading, setDetailLoading] = useState<Record<number, boolean>>({});

  useEffect(() => {
    loadClients();
  }, []);

  async function loadClients() {
    setLoading(true);
    setMsg(null);
    try {
      const res = await api.get<ClientItem[]>("/api/v1/admin/clients");
      if (res.data) setClients(res.data);
      else setMsg({ type: "error", text: res.error || 'خطا در بارگذاری کاربران' });
    } catch {
      setMsg({ type: "error", text: 'خطا در ارتباط با سرور' });
    }
    setLoading(false);
  }

  async function loadClientDetail(id: number) {
    if (clientDetails[id]) return;
    setDetailLoading(prev => ({ ...prev, [id]: true }));
    const res = await api.get<ClientDetail>(`/api/v1/admin/reports/clients/${id}/detail`);
    if (res.data) {
      setClientDetails(prev => ({ ...prev, [id]: res.data as ClientDetail }));
    }
    setDetailLoading(prev => ({ ...prev, [id]: false }));
  }

  function toggleExpand(id: number) {
    if (expandedId === id) {
      setExpandedId(null);
    } else {
      setExpandedId(id);
      loadClientDetail(id);
    }
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
    setDeleteConfirmId(null);
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
          <div className="relative flex items-center gap-2 rounded-[11px] bg-slate-950 px-5 py-3.5 text-sm font-bold text-white group-hover:bg-slate-900 transition-colors">
            <Plus className="h-4 w-4 text-cyan-400" />
            افزودن کاربر جدید
          </div>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
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

      <div className="overflow-hidden rounded-3xl border border-white/10 bg-slate-900/30 backdrop-blur-md shadow-2xl hidden md:block">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-slate-300">
            <thead className="border-b border-white/10 bg-slate-950/60 whitespace-nowrap">
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
                  <Fragment key={c.id}>
                    <tr className="border-b border-white/5 hover:bg-white/5 transition-colors duration-200 cursor-pointer" onClick={() => toggleExpand(c.id)}>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          {expandedId === c.id ? <ChevronUp className="h-4 w-4 text-cyan-400 shrink-0" /> : <ChevronDown className="h-4 w-4 text-slate-500 shrink-0" />}
                          <span className="font-mono text-[13px] font-black text-cyan-300">{c.client_code}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-bold text-slate-200">{c.name}</div>
                        <div className="mt-1 text-xs text-slate-400 font-mono">{c.email}</div>
                        <div className="mt-0.5 text-xs text-slate-500 font-mono">{c.phone || "بدون تلفن"}</div>
                      </td>
                      <td className="px-6 py-4">{accessLevelBadge(c.access_level)}</td>
                      <td className="px-6 py-4">
                        <button
                          onClick={(e) => { e.stopPropagation(); handleToggleStatus(c.id, c.status); }}
                          className={`inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold transition-all duration-300 ${
                            c.status === "active"
                              ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 hover:bg-emerald-500/20 active:scale-95"
                              : "bg-slate-500/10 border border-white/5 text-slate-400 hover:bg-slate-500/20 active:scale-95"
                          }`}
                        >
                          <span className={`h-2 w-2 rounded-full transition-all duration-300 ${c.status === "active" ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]" : "bg-slate-500"}`} />
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
                            onClick={(e) => { e.stopPropagation(); setEditingClient(c); setIsModalOpen(true); }} 
                            className="rounded-xl p-3 text-slate-400 hover:bg-white/10 hover:text-cyan-400 transition"
                            title="ویرایش کاربر"
                          >
                            <Pencil className="h-4.5 w-4.5" />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(c.id); }}
                            className="rounded-xl p-3 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 transition"
                            title="حذف کاربر"
                          >
                            <Trash2 className="h-4.5 w-4.5" />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleExpand(c.id); }}
                            className="rounded-xl p-3 text-slate-400 hover:bg-cyan-500/10 hover:text-cyan-400 transition"
                            title="مشاهده جزئیات"
                          >
                            <BarChart3 className="h-4.5 w-4.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedId === c.id && (
                      <tr key={`${c.id}-detail`} className="bg-slate-900/60">
                        <td colSpan={7} className="p-0">
                          <div className="border-t border-white/5 px-6 py-5 animate-in slide-in-from-top-1 duration-200">
                            {detailLoading[c.id] ? (
                              <div className="flex items-center justify-center py-6">
                                <Loader2 className="h-6 w-6 animate-spin text-cyan-400" />
                              </div>
                            ) : clientDetails[c.id] ? (
                              (() => {
                                const d = clientDetails[c.id];
                                return (
                                  <div className="space-y-4">
                                    {/* Stats row */}
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                      <div className="rounded-xl bg-slate-800/50 border border-white/5 p-3 text-center">
                                        <div className="text-xs text-slate-400">کل بارنامه</div>
                                        <div className="text-xl font-bold text-slate-100 font-mono mt-1">{d.total_jobs.toLocaleString("fa-IR")}</div>
                                      </div>
                                      <div className="rounded-xl bg-slate-800/50 border border-white/5 p-3 text-center">
                                        <div className="text-xs text-slate-400">موفق</div>
                                        <div className="text-xl font-bold text-emerald-300 font-mono mt-1">{d.success_jobs.toLocaleString("fa-IR")}</div>
                                      </div>
                                      <div className="rounded-xl bg-slate-800/50 border border-white/5 p-3 text-center">
                                        <div className="text-xs text-slate-400">ناموفق</div>
                                        <div className="text-xl font-bold text-red-300 font-mono mt-1">{d.failed_jobs.toLocaleString("fa-IR")}</div>
                                      </div>
                                      <div className="rounded-xl bg-slate-800/50 border border-white/5 p-3 text-center">
                                        <div className="text-xs text-slate-400">نرخ موفقیت</div>
                                        <div className={`text-xl font-bold font-mono mt-1 ${d.success_rate >= 80 ? "text-emerald-300" : d.success_rate >= 50 ? "text-amber-300" : "text-red-300"}`}>
                                          {d.success_rate}%
                                        </div>
                                      </div>
                                    </div>

                                    {/* Drivers breakdown */}
                                    <div>
                                      <h4 className="text-sm font-bold text-slate-300 mb-2">
                                        رانندگان ({d.total_drivers} فعال از {d.total_drivers})
                                      </h4>
                                      <div className="overflow-x-auto">
                                        <table className="w-full text-xs">
                                          <thead>
                                            <tr className="border-b border-white/5 text-slate-400">
                                              <th className="px-3 py-2 text-right font-medium">نام راننده</th>
                                              <th className="px-3 py-2 text-right font-medium">کل</th>
                                              <th className="px-3 py-2 text-right font-medium">موفق</th>
                                              <th className="px-3 py-2 text-right font-medium">ناموفق</th>
                                              <th className="px-3 py-2 text-right font-medium">نرخ موفقیت</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {d.driver_breakdown.map((dr) => (
                                              <tr key={dr.driver_name} className="border-b border-white/5">
                                                <td className="px-3 py-2 text-slate-200">{dr.driver_name}</td>
                                                <td className="px-3 py-2 text-slate-200 font-mono">{dr.total_jobs}</td>
                                                <td className="px-3 py-2 text-emerald-400 font-mono">{dr.success}</td>
                                                <td className="px-3 py-2 text-red-400 font-mono">{dr.failed}</td>
                                                <td className="px-3 py-2">
                                                  <span className={`font-mono ${dr.success_rate >= 80 ? "text-emerald-300" : dr.success_rate >= 50 ? "text-amber-300" : "text-red-300"}`}>
                                                    {dr.success_rate}%
                                                  </span>
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </div>

                                    {/* Failure reasons */}
                                    {Object.keys(d.failure_reasons).length > 0 && (
                                      <div>
                                        <h4 className="text-sm font-bold text-slate-300 mb-2">دلایل شکست</h4>
                                        <div className="flex flex-wrap gap-2">
                                          {Object.entries(d.failure_reasons).map(([reason, count]) => (
                                            <span key={reason} className="inline-flex items-center gap-1.5 rounded-lg bg-red-500/10 border border-red-500/20 px-2.5 py-1 text-xs text-red-300">
                                              {reason}
                                              <span className="font-mono text-red-400">{count}</span>
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                );
                              })()
                            ) : (
                              <div className="text-center text-sm text-slate-500 py-4">خطا در بارگذاری جزئیات</div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="block md:hidden space-y-3">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
            <p className="text-xs font-bold text-slate-500">در حال بارگذاری کاربران...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <Layers className="h-10 w-10 text-slate-600" />
            <p className="font-bold text-slate-500">هیچ کاربری یافت نشد</p>
          </div>
        ) : (
          filtered.map((c) => (
            <div key={c.id} className="rounded-2xl border border-white/10 bg-slate-900/40 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[13px] font-black text-cyan-300">{c.client_code}</span>
                  {accessLevelBadge(c.access_level)}
                </div>
                <button
                  onClick={() => handleToggleStatus(c.id, c.status)}
                  className={`inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-xs font-bold transition-all ${
                    c.status === "active"
                      ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
                      : "bg-slate-500/10 border border-white/5 text-slate-400"
                  }`}
                >
                  <span className={`h-2 w-2 rounded-full ${c.status === "active" ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]" : "bg-slate-500"}`} />
                  {c.status === "active" ? "فعال" : "غیرفعال"}
                </button>
              </div>
              <div className="space-y-1">
                <p className="font-bold text-slate-200">{c.name}</p>
                <p className="text-xs text-slate-400">{c.email}</p>
                {c.phone && <p className="text-xs text-slate-500">{c.phone}</p>}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-medium text-slate-400">
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400/50"></span>
                  <span>راننده: <span className="font-mono text-slate-200 font-bold">{c.max_drivers}</span></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-400/50"></span>
                  <span>پلاک: <span className="font-mono text-slate-200 font-bold">{c.max_plates}</span></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-purple-400/50"></span>
                  <span>همزمان: <span className="font-mono text-slate-200 font-bold">{c.max_concurrent_tasks}</span></span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-indigo-400/50"></span>
                  <span>روزانه: <span className="font-mono text-slate-200 font-bold">{c.max_daily_tasks}</span></span>
                </div>
              </div>
              <div className="flex items-center justify-between pt-1 border-t border-white/5">
                <span className="text-xs text-slate-500 font-mono">{c.created_at ? c.created_at.slice(0, 10) : "-"}</span>
                <div className="flex items-center gap-1">
                  <button onClick={(e) => { e.stopPropagation(); toggleExpand(c.id); }}
                    className="rounded-xl p-3 text-slate-400 hover:bg-cyan-500/10 hover:text-cyan-400 transition" title="مشاهده جزئیات">
                    <BarChart3 className="h-4 w-4" />
                  </button>
                  <button onClick={() => { setEditingClient(c); setIsModalOpen(true); }}
                    className="rounded-xl p-3 text-slate-400 hover:bg-white/10 hover:text-cyan-400 transition" title="ویرایش کاربر">
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button onClick={() => setDeleteConfirmId(c.id)}
                    className="rounded-xl p-3 text-slate-400 hover:bg-rose-500/10 hover:text-rose-400 transition" title="حذف کاربر">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {/* Mobile expanded detail */}
              {expandedId === c.id && (
                <div className="border-t border-white/5 pt-3 space-y-3 animate-in slide-in-from-top-1 duration-200">
                  {detailLoading[c.id] ? (
                    <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin text-cyan-400" /></div>
                  ) : clientDetails[c.id] ? (
                    (() => {
                      const d = clientDetails[c.id];
                      return (
                        <>
                          <div className="grid grid-cols-2 gap-2">
                            <div className="rounded-lg bg-slate-800/50 border border-white/5 p-2.5 text-center">
                              <div className="text-[10px] text-slate-400">کل</div>
                              <div className="text-sm font-bold text-slate-100">{d.total_jobs.toLocaleString("fa-IR")}</div>
                            </div>
                            <div className="rounded-lg bg-slate-800/50 border border-white/5 p-2.5 text-center">
                              <div className="text-[10px] text-slate-400">موفق</div>
                              <div className="text-sm font-bold text-emerald-300">{d.success_jobs.toLocaleString("fa-IR")}</div>
                            </div>
                            <div className="rounded-lg bg-slate-800/50 border border-white/5 p-2.5 text-center">
                              <div className="text-[10px] text-slate-400">ناموفق</div>
                              <div className="text-sm font-bold text-red-300">{d.failed_jobs.toLocaleString("fa-IR")}</div>
                            </div>
                            <div className="rounded-lg bg-slate-800/50 border border-white/5 p-2.5 text-center">
                              <div className="text-[10px] text-slate-400">نرخ موفقیت</div>
                              <div className={`text-sm font-bold ${d.success_rate >= 80 ? "text-emerald-300" : d.success_rate >= 50 ? "text-amber-300" : "text-red-300"}`}>
                                {d.success_rate}%
                              </div>
                            </div>
                          </div>
                          {d.driver_breakdown.length > 0 && (
                            <div>
                              <h4 className="text-xs font-bold text-slate-400 mb-1">رانندگان</h4>
                              <div className="space-y-1">
                                {d.driver_breakdown.slice(0, 5).map((dr) => (
                                  <div key={dr.driver_name} className="flex items-center justify-between text-xs bg-slate-800/30 rounded-lg px-2.5 py-1.5">
                                    <span className="text-slate-300">{dr.driver_name}</span>
                                    <span className={`font-mono ${dr.success_rate >= 80 ? "text-emerald-300" : dr.success_rate >= 50 ? "text-amber-300" : "text-red-300"}`}>
                                      {dr.success_rate}%
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      )
                    })()
                  ) : null}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setDeleteConfirmId(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl text-white" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-black">تأیید حذف کاربر</h3>
            <p className="mt-2 text-sm text-slate-400">تمام داده‌های مربوط به این کاربر حذف خواهد شد. مطمئن هستید؟</p>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setDeleteConfirmId(null)} className="rounded-xl border border-white/10 bg-slate-950 px-5 py-3.5 text-sm font-bold text-slate-300 hover:bg-slate-900 transition">
                انصراف
              </button>
              <button onClick={() => void handleDelete(deleteConfirmId)} className="rounded-xl bg-rose-500 px-5 py-3.5 text-sm font-bold text-white hover:bg-rose-600 transition">
                حذف شود
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
