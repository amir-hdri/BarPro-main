'use client';

import { useEffect, useState } from 'react';
import { PlusIcon } from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
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

  async function loadDrivers() {
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
  }

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
  }, [role]);

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-6">
          <form onSubmit={handleSubmit} className="rounded-[32px] border border-white/20 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/20">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl bg-cyan-400/20 p-3 text-cyan-300">
                <PlusIcon className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold">افزودن راننده جدید</h1>
                <p className="mt-1 text-sm text-slate-300">اطلاعات هویتی و دسترسی UTCMS را کامل وارد کنید.</p>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <Input label="نام و نام خانوادگی" value={form.full_name} onChange={(value) => setForm((current) => ({ ...current, full_name: value }))} required />
              <Input label="کد ملی" value={form.driver_national_code} onChange={(value) => setForm((current) => ({ ...current, driver_national_code: value }))} required />
              <Input label="تلفن" value={form.phone || ''} onChange={(value) => setForm((current) => ({ ...current, phone: value }))} />
              <Input label="شماره گواهینامه" value={form.license_number || ''} onChange={(value) => setForm((current) => ({ ...current, license_number: value }))} />
              <Input label="نام کاربری UTCMS" value={form.utcms_username} onChange={(value) => setForm((current) => ({ ...current, utcms_username: value }))} required />
              <Input label="رمز UTCMS" type="password" value={form.utcms_password} onChange={(value) => setForm((current) => ({ ...current, utcms_password: value }))} required />
            </div>

            <button type="submit" disabled={saving} className="mt-6 w-full rounded-2xl bg-cyan-400 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-60">
              {saving ? 'در حال ذخیره...' : 'ثبت راننده'}
            </button>
            {error && <p className="mt-4 rounded-2xl bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>}
          </form>

          <section className="rounded-[32px] border border-white/20 bg-white/75 p-6 shadow-lg shadow-slate-900/5 backdrop-blur">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-slate-950">رانندگان ثبت‌شده</h2>
                <p className="mt-1 text-sm text-slate-500">وضعیت عملیاتی، زمان احراز هویت و خطاهای اخیر</p>
              </div>
              <button type="button" onClick={() => void loadDrivers()} className="rounded-2xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50">
                بروزرسانی
              </button>
            </div>

            {loading ? (
              <div className="mt-6 space-y-3">
                {[1, 2, 3].map((item) => <div key={item} className="h-24 animate-pulse rounded-3xl bg-slate-100" />)}
              </div>
            ) : drivers.length === 0 ? (
              <div className="mt-6 rounded-3xl border border-dashed border-slate-200 px-5 py-8 text-sm text-slate-500">برای این مشتری هنوز راننده‌ای ثبت نشده است.</div>
            ) : (
              <div className="mt-6 space-y-4">
                {drivers.map((driver) => (
                  <article key={driver.id} className="rounded-3xl border border-slate-100 bg-slate-50 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-950">{driver.full_name}</h3>
                        <p className="mt-1 text-sm text-slate-500">{driver.driver_national_code} - {driver.phone || 'بدون تلفن'}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className={['rounded-full px-3 py-1 text-xs font-semibold', statusTone(driver.status)].join(' ')}>{statusLabel(driver.status)}</span>
                        {driver.runtime_status && <span className={['rounded-full px-3 py-1 text-xs font-semibold', statusTone(driver.runtime_status)].join(' ')}>{statusLabel(driver.runtime_status)}</span>}
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <Detail label="نام کاربری UTCMS" value={driver.utcms_username} />
                      <Detail label="آخرین احراز هویت" value={formatDateTime(driver.last_auth_at)} />
                      <Detail label="انقضای نشست" value={formatDateTime(driver.last_session_expires_at)} />
                    </div>
                    {driver.last_error_code && <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">خطای اخیر: {driver.last_error_code}</p>}
                    <div className="mt-4 flex flex-wrap gap-2">
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
                        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700"
                      >
                        ویرایش
                      </button>
                      <button type="button" onClick={() => void handleDriverDelete(driver.id)} className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                        حذف
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          {editDriver && (
            <form onSubmit={handleDriverUpdate} className="rounded-[32px] border border-white/20 bg-white p-6 shadow-lg">
              <h2 className="text-xl font-semibold text-slate-950">ویرایش راننده</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-3">
                <Input label="نام" value={editDriver.payload.full_name || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, full_name: value } } : current)} required />
                <Input label="تلفن" value={editDriver.payload.phone || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, phone: value } } : current)} />
                <Input label="گواهینامه" value={editDriver.payload.license_number || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, license_number: value } } : current)} />
                <Input label="کاربر UTCMS" value={editDriver.payload.utcms_username || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, utcms_username: value } } : current)} required />
                <Input label="رمز جدید (اختیاری)" type="password" value={editDriver.payload.utcms_password || ''} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, utcms_password: value } } : current)} />
                <Input label="وضعیت" value={editDriver.payload.status || 'active'} onChange={(value) => setEditDriver((current) => current ? { ...current, payload: { ...current.payload, status: value } } : current)} />
              </div>
              <div className="mt-4 flex gap-2">
                <button type="submit" className="rounded-xl bg-slate-900 px-4 py-2 text-sm text-white">ذخیره</button>
                <button type="button" onClick={() => setEditDriver(null)} className="rounded-xl border px-4 py-2 text-sm">انصراف</button>
              </div>
            </form>
          )}

          <section className="grid gap-6 xl:grid-cols-2">
            <form onSubmit={handleCreatePlate} className="rounded-[32px] border border-white/20 bg-white p-6 shadow-lg">
              <h2 className="text-xl font-semibold text-slate-950">مدیریت پلاک</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-medium text-slate-700">
                  <span className="mb-2 block">راننده</span>
                  <select value={plateForm.driver_id} onChange={(event) => setPlateForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="w-full rounded-2xl border border-slate-200 px-4 py-3">
                    <option value={0}>انتخاب راننده</option>
                    {drivers.map((driver) => <option key={driver.id} value={driver.id}>{driver.full_name}</option>)}
                  </select>
                </label>
                <Input label="پلاک" value={plateForm.plate_number} onChange={(value) => setPlateForm((current) => ({ ...current, plate_number: value }))} required />
                <Input label="نوع خودرو" value={plateForm.vehicle_type || ''} onChange={(value) => setPlateForm((current) => ({ ...current, vehicle_type: value }))} />
                <Input label="یادداشت" value={plateForm.notes || ''} onChange={(value) => setPlateForm((current) => ({ ...current, notes: value }))} />
              </div>
              <button type="submit" disabled={saving} className="mt-4 rounded-xl bg-cyan-500 px-4 py-2 text-sm font-semibold text-white">ثبت پلاک</button>
              <div className="mt-4 space-y-2">
                {plates.map((plate) => (
                  <div key={plate.id} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    {plate.plate_number} - راننده #{plate.driver_id} - {statusLabel(plate.status)}
                  </div>
                ))}
              </div>
            </form>

            <form onSubmit={handleScheduleCreate} className="rounded-[32px] border border-white/20 bg-white p-6 shadow-lg">
              <h2 className="text-xl font-semibold text-slate-950">زمان‌بندی خودکار بارنامه</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-medium text-slate-700">
                  <span className="mb-2 block">راننده</span>
                  <select value={scheduleForm.driver_id} onChange={(event) => setScheduleForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="w-full rounded-2xl border border-slate-200 px-4 py-3">
                    <option value={0}>انتخاب راننده</option>
                    {drivers.map((driver) => <option key={driver.id} value={driver.id}>{driver.full_name}</option>)}
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
                <label className="text-sm font-medium text-slate-700">
                  <span className="mb-2 block">تناوب</span>
                  <select value={scheduleForm.frequency} onChange={(event) => setScheduleForm((current) => ({ ...current, frequency: event.target.value as 'daily' | 'weekly' }))} className="w-full rounded-2xl border border-slate-200 px-4 py-3">
                    <option value="daily">روزانه</option>
                    <option value="weekly">هفتگی</option>
                  </select>
                </label>
              </div>
              <button type="submit" disabled={saving} className="mt-4 rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">ثبت زمان‌بندی</button>
              <button type="button" onClick={() => void runSchedulesNow()} disabled={saving} className="mt-4 mr-2 rounded-xl border px-4 py-2 text-sm">
                اجرای زمان‌بندی‌های سررسیدشده
              </button>
              <div className="mt-4 space-y-2">
                {schedules.map((schedule) => (
                  <div key={schedule.id} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white px-4 py-3">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-2 text-sm font-medium text-slate-900">{value}</p>
    </div>
  );
}
