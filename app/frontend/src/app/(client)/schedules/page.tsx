"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Calendar,
  Clock,
  Plus,
  Trash2,
  Edit,
  Loader2,
  AlertTriangle,
  CheckCircle,
  ToggleLeft,
  ToggleRight,
  FileText,
  HelpCircle
} from "lucide-react";
import { Driver, DriverSchedule } from "@/lib/types";

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<DriverSchedule[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const [formData, setFormData] = useState({
    driver_id: "",
    title: "",
    run_time: "08:00",
    frequency: "daily",
    is_active: true,
    
    // Waybill template fields
    origin: "",
    destination: "",
    cargo_type: "",
    cargo_weight: "",
    vehicle_type: "کامیون",
    plate_number: "",
    driver_phone: "",
    notes: ""
  });

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError("");

      const driversRes = await api.get<Driver[]>("/api/v1/drivers");
      if (driversRes.data) setDrivers(driversRes.data);

      const schedulesRes = await api.get<DriverSchedule[]>("/api/v1/driver-schedules");
      if (schedulesRes.data) setSchedules(schedulesRes.data);
    } catch (err: any) {
      setError(err?.message || "خطا در دریافت اطلاعات از سرور");
    } finally {
      setLoading(false);
    }
  }

  const handleToggleActive = async (schedule: DriverSchedule) => {
    try {
      setError("");
      setSuccess("");
      const res = await api.put(`/api/v1/driver-schedules/${schedule.id}`, {
        is_active: !schedule.is_active
      });
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess(`وضعیت زمان‌بندی "${schedule.title}" با موفقیت تغییر کرد.`);
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در تغییر وضعیت زمان‌بندی");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("آیا از حذف این زمان‌بندی مطمئن هستید؟")) return;
    try {
      setError("");
      setSuccess("");
      const res = await api.del(`/api/v1/driver-schedules/${id}`);
      if (res.error) {
        setError(res.error);
      } else {
        setSuccess("زمان‌بندی با موفقیت حذف شد.");
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در حذف زمان‌بندی");
    }
  };

  const handleEdit = (schedule: DriverSchedule) => {
    const template = schedule.payload_template || {};
    setFormData({
      driver_id: String(schedule.driver_id),
      title: schedule.title,
      run_time: schedule.run_time,
      frequency: schedule.frequency,
      is_active: schedule.is_active,
      
      origin: template.origin || "",
      destination: template.destination || "",
      cargo_type: template.cargo_type || "",
      cargo_weight: template.cargo_weight ? String(template.cargo_weight) : "",
      vehicle_type: template.vehicle_type || "کامیون",
      plate_number: template.plate_number || "",
      driver_phone: template.driver_phone || "",
      notes: template.notes || ""
    });
    setEditingId(schedule.id);
    setIsModalOpen(true);
  };

  const handleSelectDriver = (driverId: string) => {
    const selected = drivers.find(d => String(d.id) === driverId);
    setFormData(prev => ({
      ...prev,
      driver_id: driverId,
      driver_phone: selected?.phone || prev.driver_phone
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setError("");
      setSuccess("");

      const payload = {
        driver_id: Number(formData.driver_id),
        title: formData.title,
        run_time: formData.run_time,
        frequency: formData.frequency,
        is_active: formData.is_active,
        timezone: "Asia/Tehran",
        payload_template: {
          driver_national_code: drivers.find(d => d.id === Number(formData.driver_id))?.driver_national_code || "",
          origin: formData.origin,
          destination: formData.destination,
          cargo_type: formData.cargo_type,
          cargo_weight: Number(formData.cargo_weight),
          vehicle_type: formData.vehicle_type,
          plate_number: formData.plate_number,
          driver_phone: formData.driver_phone,
          notes: formData.notes || undefined
        }
      };

      let res;
      if (editingId) {
        res = await api.put(`/api/v1/driver-schedules/${editingId}`, payload);
      } else {
        res = await api.post("/api/v1/driver-schedules", payload);
      }

      if (res.error) {
        setError(res.error);
      } else {
        setSuccess(editingId ? "تغییرات با موفقیت ذخیره شد." : "زمان‌بندی جدید با موفقیت ایجاد شد.");
        setIsModalOpen(false);
        setEditingId(null);
        setFormData({
          driver_id: "",
          title: "",
          run_time: "08:00",
          frequency: "daily",
          is_active: true,
          origin: "",
          destination: "",
          cargo_type: "",
          cargo_weight: "",
          vehicle_type: "کامیون",
          plate_number: "",
          driver_phone: "",
          notes: ""
        });
        fetchData();
      }
    } catch (err: any) {
      setError(err?.message || "خطا در ذخیره زمان‌بندی");
    }
  };

  const getDriverName = (driverId: number) => {
    const d = drivers.find(drv => drv.id === driverId);
    return d ? d.full_name : `راننده شناسه ${driverId}`;
  };

  return (
    <div className="space-y-6 text-right animate-fade-in" dir="rtl">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">برنامه‌ریزی و زمان‌بندی خودکار</h2>
          <p className="mt-1 text-sm text-slate-400">
            تعریف برنامه‌های زمانی برای صدور خودکار بارنامه برای رانندگان
          </p>
        </div>

        <button
          onClick={() => {
            setEditingId(null);
            setFormData({
              driver_id: drivers[0]?.id ? String(drivers[0].id) : "",
              title: "",
              run_time: "08:00",
              frequency: "daily",
              is_active: true,
              origin: "",
              destination: "",
              cargo_type: "",
              cargo_weight: "",
              vehicle_type: "کامیون",
              plate_number: "",
              driver_phone: drivers[0]?.phone || "",
              notes: ""
            });
            setIsModalOpen(true);
          }}
          disabled={drivers.length === 0}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-2.5 text-sm font-medium text-slate-950 transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="h-4 w-4" />
          زمان‌بندی جدید
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {success && (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-emerald-400">
          <CheckCircle className="h-5 w-5 shrink-0" />
          <p className="text-sm">{success}</p>
        </div>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-white/10 bg-white/5 text-slate-300">
                <tr>
                  <th className="p-4 font-medium text-right">عنوان زمان‌بندی</th>
                  <th className="p-4 font-medium text-right">راننده</th>
                  <th className="p-4 font-medium text-center">زمان اجرا</th>
                  <th className="p-4 font-medium text-center">دوره تناوب</th>
                  <th className="p-4 font-medium text-center">آخرین اجرا</th>
                  <th className="p-4 font-medium text-center">اجرای بعدی</th>
                  <th className="p-4 font-medium text-center">وضعیت</th>
                  <th className="p-4 font-medium text-center">عملیات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10 text-slate-400">
                {schedules.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-8 text-center">
                      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white/5">
                        <Calendar className="h-6 w-6 text-slate-500" />
                      </div>
                      <p className="mt-4 text-slate-400">هیچ زمان‌بندی فعالی یافت نشد.</p>
                    </td>
                  </tr>
                ) : (
                  schedules.map((sched) => (
                    <tr key={sched.id} className="transition-colors hover:bg-white/5">
                      <td className="p-4 font-medium text-slate-200 text-right">{sched.title}</td>
                      <td className="p-4 text-right">{getDriverName(sched.driver_id)}</td>
                      <td className="p-4 text-center font-mono tabular-nums">{sched.run_time}</td>
                      <td className="p-4 text-center">
                        {sched.frequency === "daily" ? "روزانه" : sched.frequency === "weekly" ? "هفتگی" : sched.frequency}
                      </td>
                      <td className="p-4 text-center text-xs font-mono">
                        {sched.last_run_at ? new Date(sched.last_run_at).toLocaleString("fa-IR") : "-"}
                      </td>
                      <td className="p-4 text-center text-xs font-mono">
                        {sched.next_run_at ? new Date(sched.next_run_at).toLocaleString("fa-IR") : "-"}
                      </td>
                      <td className="p-4 text-center">
                        <button
                          onClick={() => handleToggleActive(sched)}
                          className="focus:outline-none transition-colors"
                          title={sched.is_active ? "غیرفعال کردن" : "فعال کردن"}
                        >
                          {sched.is_active ? (
                            <ToggleRight className="h-7 w-7 text-emerald-400" />
                          ) : (
                            <ToggleLeft className="h-7 w-7 text-slate-500" />
                          )}
                        </button>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => handleEdit(sched)}
                            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-cyan-400"
                            title="ویرایش زمان‌بندی"
                          >
                            <Edit className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => handleDelete(sched.id)}
                            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-white/10 hover:text-red-400"
                            title="حذف زمان‌بندی"
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
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm overflow-y-auto">
          <div className="w-full max-w-2xl my-8 rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-xl text-right">
            <h3 className="text-xl font-bold text-slate-100 mb-6">
              {editingId ? "ویرایش زمان‌بندی" : "ثبت زمان‌بندی جدید"}
            </h3>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Basic Schedule config */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">عنوان برنامه زمانی *</label>
                  <input
                    type="text"
                    required
                    value={formData.title}
                    onChange={e => setFormData({...formData, title: e.target.value})}
                    placeholder="مثلا صدور روزانه بارنامه آروند"
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 text-right"
                    dir="rtl"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">انتخاب راننده *</label>
                  <select
                    required
                    value={formData.driver_id}
                    onChange={e => handleSelectDriver(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="">انتخاب کنید...</option>
                    {drivers.map(d => (
                      <option key={d.id} value={d.id}>{d.full_name} ({d.driver_national_code})</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">ساعت اجرای روزانه *</label>
                  <input
                    type="time"
                    required
                    value={formData.run_time}
                    onChange={e => setFormData({...formData, run_time: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-left"
                    dir="ltr"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">دوره تناوب *</label>
                  <select
                    value={formData.frequency}
                    onChange={e => setFormData({...formData, frequency: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
                  >
                    <option value="daily">روزانه</option>
                    <option value="weekly">هفتگی</option>
                  </select>
                </div>
              </div>

              {/* Waybill Template Section */}
              <div className="border-t border-white/10 pt-4 space-y-4">
                <h4 className="text-md font-bold text-slate-200 flex items-center gap-2">
                  <FileText className="h-5 w-5 text-cyan-400" />
                  قالب بارنامه (Waybill Template)
                </h4>
                <p className="text-xs text-slate-400">
                  اطلاعات وارد شده در زیر به طور خودکار در زمان اجرای برنامه برای صدور بارنامه استفاده خواهد شد.
                </p>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">شماره پلاک کامیون *</label>
                    <input
                      type="text"
                      required
                      value={formData.plate_number}
                      onChange={e => setFormData({...formData, plate_number: e.target.value})}
                      placeholder="۱۲ع۳۴۵ایران۶۷ یا ۱۲۳۴۵منطقه آزاد"
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-left"
                      dir="ltr"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">شماره تماس راننده *</label>
                    <input
                      type="text"
                      required
                      value={formData.driver_phone}
                      onChange={e => setFormData({...formData, driver_phone: e.target.value})}
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-left"
                      dir="ltr"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">مبدأ حرکت *</label>
                    <input
                      type="text"
                      required
                      value={formData.origin}
                      onChange={e => setFormData({...formData, origin: e.target.value})}
                      placeholder="استان، شهر"
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">مقصد حرکت *</label>
                    <input
                      type="text"
                      required
                      value={formData.destination}
                      onChange={e => setFormData({...formData, destination: e.target.value})}
                      placeholder="استان، شهر"
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">نوع کالا *</label>
                    <input
                      type="text"
                      required
                      value={formData.cargo_type}
                      onChange={e => setFormData({...formData, cargo_type: e.target.value})}
                      placeholder="مثلا سیمان فله"
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">وزن بار (تن) *</label>
                    <input
                      type="number"
                      step="0.1"
                      required
                      value={formData.cargo_weight}
                      onChange={e => setFormData({...formData, cargo_weight: e.target.value})}
                      className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-left"
                      dir="ltr"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">یادداشت داخلی زمان‌بندی (اختیاری)</label>
                  <input
                    type="text"
                    value={formData.notes}
                    onChange={e => setFormData({...formData, notes: e.target.value})}
                    className="w-full rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none text-right"
                  />
                </div>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <input
                  type="checkbox"
                  id="modal_is_active"
                  checked={formData.is_active}
                  onChange={e => setFormData({...formData, is_active: e.target.checked})}
                  className="w-5 h-5 rounded border-white/10 bg-white/5 text-cyan-500 focus:ring-cyan-500"
                />
                <label htmlFor="modal_is_active" className="text-sm font-medium text-slate-300">
                  زمان‌بندی فعال باشد
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-6 border-t border-white/10">
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
                  ذخیره زمان‌بندی
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
