'use client';

import { useCallback, useEffect, useState } from 'react';
import { PlusIcon, UserCircleIcon } from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { PlateInput } from '@/components/PlateInput';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone } from '@/lib/format';
import { useSession } from "@/hooks/useSession";
import type {
  Driver,
  DriverCreateRequest,
  DriverSchedule,
  DriverScheduleCreateRequest,
  DriverUpdateRequest,
  Plate,
  PlateCreateRequest,
} from '@/lib/types';

const initialDriver: DriverCreateRequest = {
  driver_national_code: '',
  full_name: '',
  phone: '',
  license_number: '',
  utcms_username: '',
  utcms_password: '',
};

export default function DriversPage() {
  const { role } = useSession();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [plates, setPlates] = useState<Plate[]>([]);
  const [schedules, setSchedules] = useState<DriverSchedule[]>([]);
  const [form, setForm] = useState<DriverCreateRequest>(initialDriver);
  const [plateForm, setPlateForm] = useState<PlateCreateRequest>({ driver_id: 0, plate_number: '', vehicle_type: '', notes: '' });
  const [scheduleForm, setScheduleForm] = useState<DriverScheduleCreateRequest>({
    driver_id: 0,
    title: '',
    frequency: 'daily',
    run_time: '08:00',
    run_times: ['08:00'],
    weekdays: [0],
    specific_dates: [],
    start_date: '',
    end_date: '',
    timezone: 'Asia/Tehran',
    payload_template: {},
    is_active: true,
  });
  const [editDriver, setEditDriver] = useState<{ id: number; payload: DriverUpdateRequest } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDrivers = useCallback(async () => {
      if (role !== "client") { setLoading(false); return; }

    setLoading(true);
    const [driversResponse, platesResponse, schedulesResponse] = await Promise.all([
      api.get<Driver[]>('/api/v1/drivers'),
      api.get<Plate[]>('/api/v1/plates'),
      api.get<DriverSchedule[]>('/api/v1/driver-schedules'),
    ]);

    if (!driversResponse.success || !driversResponse.data) {
      setError(driversResponse.error || 'لیست رانندگان بارگذاری نشد');
      setDrivers([]);
      setLoading(false);
      return;
    }

    setDrivers(driversResponse.data);
    setPlates(platesResponse.data || []);
    setSchedules(schedulesResponse.data || []);
    setError(null);
    setLoading(false);
  }, [role]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^\d{10}$/.test(form.driver_national_code)) {
      setError('کد ملی راننده باید دقیقاً ۱۰ رقم باشد.');
      return;
    }
    if (!form.utcms_username.trim() || form.utcms_password.length < 4) {
      setError('نام کاربری و رمز UTCMS معتبر وارد کنید.');
      return;
    }
    setSaving(true);
    const response = await api.post<Driver>('/api/v1/drivers', form);
    setSaving(false);

    if (!response.success) {
      setError(response.error || 'ثبت راننده ناموفق بود');
      return;
    }

    setForm(initialDriver);
    setError(null);
    await loadDrivers();
  }

  async function handleDriverUpdate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editDriver) {
      return;
    }
    setSaving(true);
    const response = await api.put<Driver>(`/api/v1/drivers/${editDriver.id}`, editDriver.payload);
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'ویرایش راننده ناموفق بود');
      return;
    }
    setEditDriver(null);
    await loadDrivers();
  }

  async function handleDriverDelete(driverId: number) {
    if (!window.confirm('راننده حذف شود؟')) {
      return;
    }
    setSaving(true);
    const response = await api.delete<void>(`/api/v1/drivers/${driverId}`);
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'حذف راننده ناموفق بود');
      return;
    }
    await loadDrivers();
  }

  async function handleCreatePlate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!plateForm.driver_id) {
      setError('برای ثبت پلاک باید راننده انتخاب شود.');
      return;
    }
    if (!plateForm.plate_number.trim()) {
      setError('پلاک نمی‌تواند خالی باشد.');
      return;
    }
    setSaving(true);
    const response = await api.post<Plate>('/api/v1/plates', plateForm);
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'ثبت پلاک ناموفق بود');
      return;
    }
    setPlateForm({ driver_id: 0, plate_number: '', vehicle_type: '', notes: '' });
    await loadDrivers();
  }

  async function handleScheduleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scheduleForm.driver_id || !scheduleForm.title.trim()) {
      setError('راننده و عنوان زمان‌بندی الزامی است.');
      return;
    }
    if (!/^\d{2}:\d{2}$/.test(scheduleForm.run_time)) {
      setError('فرمت ساعت اجرا باید HH:MM باشد.');
      return;
    }
    if (scheduleForm.run_times && scheduleForm.run_times.some((value) => !/^\d{2}:\d{2}$/.test(value))) {
      setError('همه ساعت‌های اجرا باید با فرمت HH:MM باشند.');
      return;
    }
    setSaving(true);
    const payload: DriverScheduleCreateRequest = {
      ...scheduleForm,
      run_times: (scheduleForm.run_times || []).filter(Boolean),
      specific_dates: (scheduleForm.specific_dates || []).filter(Boolean),
      start_date: scheduleForm.start_date || undefined,
      end_date: scheduleForm.end_date || undefined,
    };
    const response = await api.post<DriverSchedule>('/api/v1/driver-schedules', payload);
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'ثبت زمان‌بندی ناموفق بود');
      return;
    }
    setScheduleForm({
      driver_id: 0,
      title: '',
      frequency: 'daily',
      run_time: '08:00',
      run_times: ['08:00'],
      weekdays: [0],
      specific_dates: [],
      start_date: '',
      end_date: '',
      timezone: 'Asia/Tehran',
      payload_template: {},
      is_active: true,
    });
    await loadDrivers();
  }

  async function runSchedulesNow() {
    setSaving(true);
    const response = await api.post<{ created_count: number }>('/api/v1/driver-schedules/run-due', {});
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'اجرای زمان‌بندی ناموفق بود');
      return;
    }
    await loadDrivers();
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDrivers();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [role, loadDrivers]);

    return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="flex flex-col gap-10">
          <form onSubmit={handleSubmit} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl px-6 py-8 lg:px-10 lg:py-10 shadow-2xl">
            <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
            
            <div className="relative z-10">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                  <PlusIcon className="h-6 w-6" />
                </div>
                <div>
                  <h1 className="text-2xl font-black text-white">ثبت راننده جدید</h1>
                  <p className="mt-1 text-sm text-slate-400">اطلاعات هویتی و دسترسی‌های مورد نیاز برای اتوماسیون</p>
                </div>
              </div>

              <div className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                <Input label="نام و نام خانوادگی" value={form.full_name} onChange={(value) => setForm((current) => ({ ...current, full_name: value }))} required />
                <Input label="کد ملی (۱۰ رقم)" value={form.driver_national_code} onChange={(value) => setForm((current) => ({ ...current, driver_national_code: value }))} required />
                <Input label="شماره همراه" value={form.phone || ''} onChange={(value) => setForm((current) => ({ ...current, phone: value }))} />
                <Input label="شماره گواهینامه" value={form.license_number || ''} onChange={(value) => setForm((current) => ({ ...current, license_number: value }))} />
                <Input label="نام کاربری UTCMS" value={form.utcms_username} onChange={(value) => setForm((current) => ({ ...current, utcms_username: value }))} required />
                <Input label="رمز عبور UTCMS" type="password" value={form.utcms_password} onChange={(value) => setForm((current) => ({ ...current, utcms_password: value }))} required />
              </div>

              <div className="mt-10 flex justify-end">
                <button type="submit" disabled={saving} className="min-w-[200px] rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 px-8 py-4 text-sm font-black text-slate-950 shadow-xl shadow-cyan-500/20 transition hover:scale-105 active:scale-95 disabled:opacity-60">
                  {saving ? 'در حال ذخیره...' : 'افزودن به لیست'}
                </button>
              </div>
              {error && (
                <div className="mt-6 animate-in fade-in slide-in-from-top-2 rounded-2xl bg-rose-500/10 p-4 text-sm font-bold text-rose-200 ring-1 ring-rose-500/20">
                  {error}
                </div>
              )}
            </div>
          </form>

          <div className="relative overflow-hidden rounded-[2rem] lg:rounded-[3rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 md:p-8 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/5 pb-6">
              <div>
                <h2 className="text-xl font-bold text-white">رانندگان ناوگان</h2>
                <p className="mt-1 text-sm text-slate-400">لیست تمامی رانندگان احراز هویت شده و وضعیت فعالیت آن‌ها</p>
              </div>
              <button type="button" onClick={() => void loadDrivers()} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950 px-5 py-2.5 text-xs font-bold text-slate-300 transition hover:bg-slate-900 hover:scale-105 active:scale-95 shadow-sm">
                بروزرسانی لیست
              </button>
            </div>

            {loading ? (
              <div className="mt-8 space-y-4">
                {[1, 2, 3].map((item) => <div key={item} className="h-32 skeleton" />)}
              </div>
            ) : drivers.length === 0 ? (
              <div className="mt-12 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 py-20">
                <p className="text-sm font-medium text-slate-500">هنوز راننده‌ای در سامانه ثبت نشده است.</p>
              </div>
            ) : (
              <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-1">
                {drivers.map((driver) => (
                  <article key={driver.id} className="group relative rounded-2xl border border-white/5 bg-slate-950/40 p-6 transition-all hover:border-cyan-500/20 hover:bg-slate-950/60 hover:shadow-lg hover:shadow-cyan-500/5">
                    <div className="flex flex-wrap items-start justify-between gap-6">
                      <div className="flex items-center gap-5">
                        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-950 border border-white/5 text-slate-500 shadow-sm transition-colors group-hover:text-cyan-400 group-hover:border-cyan-500/30">
                          <UserCircleIcon className="h-8 w-8" />
                        </div>
                        <div>
                          <h3 className="text-lg font-black text-white group-hover:text-cyan-400">{driver.full_name}</h3>
                          <div className="mt-1 flex items-center gap-3 text-xs font-bold text-slate-400">
                            <span>{driver.driver_national_code}</span>
                            <span className="h-1 w-1 rounded-full bg-slate-700"></span>
                            <span>{driver.phone || 'فاقد شماره همراه'}</span>
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex flex-wrap items-center gap-3">
                        <span className={['inline-flex items-center rounded-xl px-4 py-2 text-xs font-bold shadow-sm', statusTone(driver.status)].join(' ')}>
                          {statusLabel(driver.status)}
                        </span>
                        {driver.runtime_status && (
                          <span className={['inline-flex items-center rounded-xl px-4 py-2 text-xs font-bold shadow-sm', statusTone(driver.runtime_status)].join(' ')}>
                            {statusLabel(driver.runtime_status)}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="mt-8 grid gap-4 sm:grid-cols-3">
                      <div className="rounded-2xl bg-slate-950/60 p-4 border border-white/5">
                        <p className="text-[10px] font-black uppercase text-slate-400">شناسه UTCMS</p>
                        <p className="mt-1 text-sm font-bold text-slate-300">{driver.utcms_username}</p>
                      </div>
                      <div className="rounded-2xl bg-slate-950/60 p-4 border border-white/5">
                        <p className="text-[10px] font-black uppercase text-slate-400">آخرین فعالیت</p>
                        <p className="mt-1 text-sm font-bold text-slate-300">{formatDateTime(driver.last_auth_at) || 'ثبت نشده'}</p>
                      </div>
                      <div className="rounded-2xl bg-slate-950/60 p-4 border border-white/5">
                        <p className="text-[10px] font-black uppercase text-slate-400">اعتبار نشست</p>
                        <p className="mt-1 text-sm font-bold text-slate-300">{formatDateTime(driver.last_session_expires_at) || 'نامشخص'}</p>
                      </div>
                    </div>

                    {driver.last_error_code && (
                      <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs font-bold text-rose-400">
                        آخرین خطا: {driver.last_error_code}
                      </div>
                    )}

                    <div className="mt-8 flex justify-end gap-3 border-t border-white/5 pt-6">
                      <button
                        type="button"
                        onClick={() =>
                          setEditDriver({
                            id: driver.id,
                            payload: {
                              full_name: driver.full_name,
                              phone: driver.phone || '',
                              license_number: driver.license_number || '',
                              utcms_username: driver.utcms_username,
                              status: driver.status,
                            },
                          })
                        }
                        className="rounded-xl border border-white/10 bg-slate-950 px-5 py-2.5 text-xs font-bold text-slate-300 transition hover:bg-slate-900 hover:scale-105"
                      >
                        ویرایش اطلاعات
                      </button>
                      <button 
                        type="button" 
                        onClick={() => void handleDriverDelete(driver.id)} 
                        className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-5 py-2.5 text-xs font-bold text-rose-400 transition hover:bg-rose-600 hover:text-white hover:border-rose-600"
                      >
                        حذف راننده
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>


          {editDriver && (
            <form onSubmit={handleDriverUpdate} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white animate-in fade-in duration-300">
              <h2 className="text-xl font-bold text-white">ویرایش راننده</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-3">
                <Input label="نام" value={editDriver.payload.full_name || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, full_name: value } } : current)} required />
                <Input label="تلفن" value={editDriver.payload.phone || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, phone: value } } : current)} />
                <Input label="گواهینامه" value={editDriver.payload.license_number || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, license_number: value } } : current)} />
                <Input label="کاربر UTCMS" value={editDriver.payload.utcms_username || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, utcms_username: value } } : current)} required />
                <Input label="رمز جدید (اختیاری)" type="password" value={editDriver.payload.utcms_password || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, utcms_password: value } } : current)} />
                <Input label="وضعیت" value={editDriver.payload.status || 'active'} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, status: value } } : current)} />
              </div>
              <div className="mt-6 flex gap-3">
                <button type="submit" className="rounded-xl bg-cyan-500 hover:bg-cyan-400 px-5 py-2.5 text-sm font-bold text-slate-950 transition hover:scale-105">ذخیره</button>
                <button type="button" onClick={() => setEditDriver(null)} className="rounded-xl border border-white/10 bg-slate-950 px-5 py-2.5 text-sm font-bold text-slate-300 hover:bg-slate-900 transition hover:scale-105">انصراف</button>
              </div>
            </form>
          )}

          <section className="grid gap-6 xl:grid-cols-2">
            <form onSubmit={handleCreatePlate} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
              <h2 className="text-xl font-bold text-white">مدیریت پلاک</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-medium text-slate-200">
                  <span className="mb-2 block">راننده</span>
                  <select value={plateForm.driver_id} onChange={(event) => setPlateForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white outline-none focus:border-cyan-400">
                    <option value={0} className="bg-slate-950">انتخاب راننده</option>
                    {drivers.map((driver) => <option key={driver.id} value={driver.id} className="bg-slate-950">{driver.full_name}</option>)}
                  </select>
                </label>
                <label className="text-sm font-medium text-slate-200">
                  <span className="mb-2 block">پلاک <span className="mr-1 text-rose-500">*</span></span>
                  <PlateInput value={plateForm.plate_number} onChange={(value) => setPlateForm((current) => ({ ...current, plate_number: value }))} />
                </label>
                <Input label="نوع خودرو" value={plateForm.vehicle_type || ''} onChange={(value) => setPlateForm((current) => ({ ...current, vehicle_type: value }))} />
                <Input label="یادداشت" value={plateForm.notes || ''} onChange={(value) => setPlateForm((current) => ({ ...current, notes: value }))} />
              </div>
              <button type="submit" disabled={saving} className="mt-6 rounded-xl bg-cyan-500 hover:bg-cyan-400 px-5 py-2.5 text-sm font-bold text-slate-950 transition hover:scale-105 active:scale-95 shadow-lg shadow-cyan-500/20">ثبت پلاک</button>
              <div className="mt-6 space-y-2">
                {plates.map((plate) => (
                  <div key={plate.id} className="rounded-2xl bg-slate-950/60 border border-white/5 px-4 py-3 text-sm text-slate-300">
                    {plate.plate_number} - راننده #{plate.driver_id} - {statusLabel(plate.status)}
                  </div>
                ))}
              </div>
            </form>

            <form onSubmit={handleScheduleCreate} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
              <h2 className="text-xl font-bold text-white">زمان‌بندی خودکار بارنامه</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-medium text-slate-200">
                  <span className="mb-2 block">راننده</span>
                  <select value={scheduleForm.driver_id} onChange={(event) => setScheduleForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white outline-none focus:border-cyan-400">
                    <option value={0} className="bg-slate-950">انتخاب راننده</option>
                    {drivers.map((driver) => <option key={driver.id} value={driver.id} className="bg-slate-950">{driver.full_name}</option>)}
                  </select>
                </label>
                <Input label="عنوان برنامه" value={scheduleForm.title} onChange={(value) => setScheduleForm((current) => ({ ...current, title: value }))} required />
                <Input label="ساعت اجرا (HH:MM)" value={scheduleForm.run_time} onChange={(value) => setScheduleForm((current) => ({ ...current, run_time: value }))} required />
                <Input
                  label="ساعت‌های اجرا (با کاما)"
                  value={(scheduleForm.run_times || []).join(',')}
                  onChange={(value) =>
                    setScheduleForm((current) => ({
                      ...current,
                      run_times: value
                        .split(',')
                        .map((item) => item.trim())
                        .filter(Boolean),
                    }))
                  }
                />
                <Input
                  label="تاریخ‌های مشخص (YYYY-MM-DD, comma)"
                  value={(scheduleForm.specific_dates || []).join(',')}
                  onChange={(value) =>
                    setScheduleForm((current) => ({
                      ...current,
                      specific_dates: value
                        .split(',')
                        .map((item) => item.trim())
                        .filter(Boolean),
                    }))
                  }
                />
                <Input label="از تاریخ (YYYY-MM-DD)" value={scheduleForm.start_date || ''} onChange={(value) => setScheduleForm((current) => ({ ...current, start_date: value }))} />
                <Input label="تا تاریخ (YYYY-MM-DD)" value={scheduleForm.end_date || ''} onChange={(value) => setScheduleForm((current) => ({ ...current, end_date: value }))} />
                <label className="text-sm font-medium text-slate-200">
                  <span className="mb-2 block">تناوب</span>
                  <select value={scheduleForm.frequency} onChange={(event) => setScheduleForm((current) => ({ ...current, frequency: event.target.value as 'daily' | 'weekly' }))} className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white outline-none focus:border-cyan-400">
                    <option value="daily" className="bg-slate-950">روزانه</option>
                    <option value="weekly" className="bg-slate-950">هفتگی</option>
                  </select>
                </label>
              </div>
              <div className="mt-6 flex flex-wrap gap-3">
                <button type="submit" disabled={saving} className="rounded-xl bg-cyan-500 hover:bg-cyan-400 px-5 py-2.5 text-sm font-bold text-slate-950 transition hover:scale-105 active:scale-95 shadow-lg shadow-cyan-500/20">ثبت زمان‌بندی</button>
                <button type="button" onClick={() => void runSchedulesNow()} disabled={saving} className="rounded-xl border border-white/10 bg-slate-950 px-5 py-2.5 text-sm font-bold text-slate-300 hover:bg-slate-900 transition hover:scale-105">
                  اجرای زمان‌بندی‌های سررسیدشده
                </button>
              </div>
              <div className="mt-6 space-y-2">
                {schedules.map((schedule) => (
                  <div key={schedule.id} className="rounded-2xl bg-slate-950/60 border border-white/5 px-4 py-3 text-sm text-slate-300">
                    {schedule.title} - راننده #{schedule.driver_id} - {schedule.frequency} - {(schedule.run_times?.length ? schedule.run_times.join(', ') : schedule.run_time)}
                  </div>
                ))}
              </div>
            </form>
          </section>
        </section>
      </AuthGuard>
    </AppShell>
  );
}

function Input({ label, onChange, required, type = 'text', value }: { label: string; onChange: (value: string) => void; required?: boolean; type?: string; value: string }) {
  return (
    <label className="text-sm font-medium text-slate-200">
      <span className="mb-2 block">{label}</span>
      <input type={type} required={required} value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-400" />
    </label>
  );
}


