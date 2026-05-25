"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ClientUser } from "@/lib/types";
import { Users, Search, Loader2, AlertCircle, CheckCircle, Pencil, Trash2, Plus } from "lucide-react";

interface ClientItem {
  id: number;
  client_code: string;
  name: string;
  email: string;
  phone?: string;
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
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    client_code: "",
    name: "",
    email: "",
    phone: "",
    password: "",
    max_drivers: 10,
    max_plates: 20,
  });
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => { loadClients(); }, []);

  async function loadClients() {
    setLoading(true);
    const res = await api.get<ClientItem[]>("/api/v1/admin/clients");
    if (res.data) setClients(res.data);
    setLoading(false);
  }

  function resetForm() {
    setForm({ client_code: "", name: "", email: "", phone: "", password: "", max_drivers: 10, max_plates: 20 });
    setEditingId(null);
    setShowForm(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      if (editingId) {
        const res = await api.put(`/api/v1/admin/clients/${editingId}`, {
          client_code: form.client_code,
          name: form.name,
          email: form.email,
          phone: form.phone,
          password: form.password || undefined,
          max_drivers: form.max_drivers,
          max_plates: form.max_plates,
        });
        if (res.error) { setMsg({ type: "error", text: res.error }); }
        else { setMsg({ type: "success", text: "کاربر با موفقیت ویرایش شد" }); resetForm(); loadClients(); }
      } else {
        const res = await api.post<ClientItem>("/api/v1/admin/clients", form);
        if (res.error) { setMsg({ type: "error", text: res.error }); }
        else { setMsg({ type: "success", text: "کاربر با موفقیت اضافه شد" }); resetForm(); loadClients(); }
      }
    } catch (e: any) {
      setMsg({ type: "error", text: e?.message || "خطا" });
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("آیا مطمئن هستید؟")) return;
    const res = await api.del(`/api/v1/admin/clients/${id}`);
    if (res.error) setMsg({ type: "error", text: res.error });
    else { setMsg({ type: "success", text: "کاربر حذف شد" }); loadClients(); }
  }

  function startEdit(c: ClientItem) {
    setForm({
      client_code: c.client_code,
      name: c.name,
      email: c.email,
      phone: c.phone || "",
      password: "",
      max_drivers: c.max_drivers,
      max_plates: c.max_plates,
    });
    setEditingId(c.id);
    setShowForm(true);
  }

  const filtered = clients.filter((c) =>
    c.name.includes(search) || c.client_code.includes(search) || c.email.includes(search)
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-100">مدیریت کاربران</h2>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-2.5 text-sm font-medium text-slate-950"
        >
          <Plus className="h-4 w-4" />
          کاربر جدید
        </button>
      </div>

      {msg && (
        <div className={`flex items-center gap-3 rounded-xl border p-4 ${
          msg.type === "success"
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
            : "border-red-500/20 bg-red-500/10 text-red-300"
        }`}>
          {msg.type === "success" ? <CheckCircle className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
          <p className="text-sm">{msg.text}</p>
        </div>
      )}

      <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 p-3">
        <Search className="h-5 w-5 text-slate-400" />
        <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
          placeholder="جستجوی نام، کد یا ایمیل..."
          className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500" />
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-xl border border-white/10 bg-slate-900/30 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-slate-100">
            {editingId ? "ویرایش کاربر" : "افزودن کاربر جدید"}
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">کد مشتری *</span>
              <input type="text" required value={form.client_code} onChange={(e) => setForm({ ...form, client_code: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">نام *</span>
              <input type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">ایمیل *</span>
              <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">تلفن</span>
              <input type="text" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">رمز عبور</span>
              <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">حداکثر راننده</span>
              <input type="number" min={1} value={form.max_drivers} onChange={(e) => setForm({ ...form, max_drivers: +e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-300">حداکثر پلاک</span>
              <input type="number" min={1} value={form.max_plates} onChange={(e) => setForm({ ...form, max_plates: +e.target.value })}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none focus:border-cyan-400" />
            </label>
          </div>
          <div className="flex gap-3">
            <button type="submit" className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-6 py-2.5 text-sm font-medium text-slate-950">
              {editingId ? "ذخیره تغییرات" : "افزودن"}
            </button>
            <button type="button" onClick={resetForm} className="rounded-xl border border-white/10 px-6 py-2.5 text-sm font-medium text-slate-300 hover:bg-white/5">
              انصراف
            </button>
          </div>
        </form>
      )}

      <div className="overflow-hidden rounded-xl border border-white/10 bg-slate-900/30">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-white/10 bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 text-right font-medium text-slate-300">کد</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">نام</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">ایمیل</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">وضعیت</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">راننده</th>
                <th className="px-4 py-3 text-right font-medium text-slate-300">عملیات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="py-8 text-center text-slate-400"><Loader2 className="mx-auto h-6 w-6 animate-spin" /></td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} className="py-8 text-center text-slate-400">نتیجه‌ای یافت نشد</td></tr>
              ) : filtered.map((c) => (
                <tr key={c.id} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-4 py-3 text-slate-200">{c.client_code}</td>
                  <td className="px-4 py-3 text-slate-200 font-medium">{c.name}</td>
                  <td className="px-4 py-3 text-slate-300">{c.email}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      c.status === "active" ? "bg-emerald-500/10 text-emerald-300" : "bg-slate-500/10 text-slate-400"
                    }`}>
                      {c.status === "active" ? "فعال" : "غیرفعال"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-200">{c.max_drivers}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button onClick={() => startEdit(c)} className="rounded-lg bg-amber-500/10 p-2 text-amber-400 hover:bg-amber-500/20">
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="rounded-lg bg-red-500/10 p-2 text-red-400 hover:bg-red-500/20">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
