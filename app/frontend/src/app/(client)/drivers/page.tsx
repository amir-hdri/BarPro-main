"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Plus,
  Search,
  Edit,
  Trash2,
  Truck,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Calendar
} from "lucide-react";
import { Driver, DriverPlate, ClientUser } from "@/lib/types";

export default function DriversPage() {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [user, setUser] = useState<ClientUser | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    national_code: "",
    full_name: "",
    phone: "",
    license_number: "",
    utcms_username: "",
    utcms_password: "",
    status: "active",
    plate_number: "",
    schedule_enabled: false,
    schedule_run_time: "08:00"
  });

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError("");

      const userRes = await api.get<ClientUser>("/api/v1/auth/me");
      setUser(userRes.data || null);

      const driversRes = await api.get<Driver[]>("/api/v1/drivers");
      setDrivers(driversRes.data || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || "خطا در دریافت اطلاعات");
    } finally {
      setLoading(false);
    }
  }

  const isLimitReached = user && drivers.length >= user.max_drivers;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError("");
      await api.post("/api/v1/drivers", formData);
      setIsModalOpen(false);
      fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || "خطا در ثبت راننده");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">مدیریت رانندگان و پلاک‌ها</h2>
          <p className="mt-1 text-sm text-slate-400">
            ثبت و مدیریت رانندگان و پلاک‌های متصل به حساب کاربری
          </p>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <div className="text-sm text-slate-400">
              ظرفیت: <span className="text-slate-200">{drivers.length}</span> / {user.max_drivers}
            </div>
          )}
          <button
            onClick={() => setIsModalOpen(true)}
            disabled={!!isLimitReached}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-2.5 text-sm font-medium text-slate-950 transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus className="h-4 w-4" />
            ثبت راننده جدید
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-white/5 text-slate-300">
                <tr>
                  <th className="p-4 font-medium">نام راننده</th>
                  <th className="p-4 font-medium text-right">کد ملی</th>
                  <th className="p-4 font-medium text-right">شماره تماس</th>
                  <th className="p-4 font-medium text-center">نام کاربری UTCMS</th>
                  <th className="p-4 font-medium text-center">پلاک پیش‌فرض</th>
                  <th className="p-4 font-medium text-center">زمان‌بندی</th>
                  <th className="p-4 font-medium text-center">وضعیت</th>
                  <th className="p-4 font-medium text-center">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10 text-slate-400">
                {drivers.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center">
                      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white/5">
                        <Truck className="h-6 w-6 text-slate-500" />
                      </div>
                      <p className="mt-4 text-slate-400">هیچ راننده‌ای ثبت نشده است</p>
                    </td>
                  </tr>
                ) : (
                  drivers.map((driver) => (
                    <tr key={driver.id} className="transition-colors hover:bg-white/5 text-right">
                      <td className="p-4 font-medium text-slate-200 text-right">{driver.full_name}</td>
                      <td className="p-4 tabular-nums">{driver.driver_national_code}</td>
                      <td className="p-4 tabular-nums">{driver.phone || "-"}</td>
                      <td className="p-4 text-center">{driver.utcms_username}</td>
                      <td className="p-4 text-center">-</td>
                      <td className="p-4 text-center">
                        <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium bg-slate-500/10 text-slate-400">
                          تنظیم نشده
                        </span>
                      </td>
                      <td className="p-4 text-center">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                          driver.status === 'active'
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "bg-red-500/10 text-red-400"
                        }`}>
                          {driver.status === 'active' ? "فعال" : "غیرفعال"}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-cyan-400"
                            title="ویرایش راننده/پلاک"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button
                            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-amber-400"
                            title="زمان‌بندی"
                          >
                            <Calendar className="h-4 w-4" />
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
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-xl">
            <h3 className="text-xl font-bold text-slate-100 mb-6">ثبت راننده و پلاک جدید</h3>

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">نام کامل راننده</label>
                  <input
                    type="text"
                    required
                    value={formData.full_name}
                    onChange={e => setFormData({...formData, full_name: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-right"
                    dir="rtl"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">کد ملی</label>
                  <input
                    type="text"
                    required
                    value={formData.national_code}
                    onChange={e => setFormData({...formData, national_code: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">شماره پلاک</label>
                  <input
                    type="text"
                    value={formData.plate_number}
                    onChange={e => setFormData({...formData, plate_number: e.target.value})}
                    placeholder="مثلا 12ع345-67"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">شماره تماس (اختیاری)</label>
                  <input
                    type="text"
                    value={formData.phone}
                    onChange={e => setFormData({...formData, phone: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">نام کاربری سامانه UTCMS</label>
                  <input
                    type="text"
                    required
                    value={formData.utcms_username}
                    onChange={e => setFormData({...formData, utcms_username: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">رمز عبور سامانه UTCMS</label>
                  <input
                    type="password"
                    required
                    value={formData.utcms_password}
                    onChange={e => setFormData({...formData, utcms_password: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                    dir="ltr"
                  />
                  <p className="text-xs text-slate-500">رمز عبور به‌صورت رمزنگاری شده ذخیره می‌شود.</p>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="schedule_enabled"
                    checked={formData.schedule_enabled}
                    onChange={e => setFormData({...formData, schedule_enabled: e.target.checked})}
                    className="w-5 h-5 rounded border-white/10 bg-white/5 text-cyan-500 focus:ring-cyan-500"
                  />
                  <label htmlFor="schedule_enabled" className="text-sm font-medium text-slate-300">
                    فعال‌سازی ثبت خودکار بارنامه (زمان‌بندی)
                  </label>
                </div>

                {formData.schedule_enabled && (
                  <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-2 bg-white/5 p-4 rounded-xl border border-white/5">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-300">زمان اجرای روزانه</label>
                      <input
                        type="time"
                        value={formData.schedule_run_time}
                        onChange={e => setFormData({...formData, schedule_run_time: e.target.value})}
                        className="w-full rounded-xl border border-white/10 bg-slate-900 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                        dir="ltr"
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-6">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-xl px-4 py-2 text-sm font-medium text-slate-300 hover:bg-white/10 transition-colors"
                >
                  انصراف
                </button>
                <button
                  type="submit"
                  className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-6 py-2 text-sm font-medium text-slate-950 hover:opacity-90 transition-opacity"
                >
                  ذخیره اطلاعات
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
