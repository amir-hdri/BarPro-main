'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PlusIcon, TruckIcon, UserCircleIcon } from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { PlateInput } from '@/components/PlateInput';
import { toast } from 'react-hot-toast';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, statusTone } from '@/lib/format';
import { canonicalizePlate, normalizeDigits } from '@/lib/plate';
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
  plate_number: '',
};

export default function DriversPage() {
  const { role } = useSession();
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
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'list' | 'add' | 'plates_schedules'>('list');

  const { data: drivers = [], isLoading: driversLoading, refetch: refetchDrivers } = useQuery({
    queryKey: ['drivers'],
    queryFn: async () => {
      const res = await api.get<Driver[]>('/api/v1/drivers?page_size=1000');
      if (!res.success || !res.data || !Array.isArray(res.data)) {
        return [];
      }
      return res.data;
    },
    staleTime: 120000,
    enabled: role === "client" || role === "master_admin",
  });

  const loadPlatesAndSchedules = useCallback(async () => {
    if (role !== "client" && role !== "master_admin") return;

    try {
      const [platesResponse, schedulesResponse] = await Promise.all([
        api.get<Plate[]>('/api/v1/plates?page_size=1000'),
        api.get<DriverSchedule[]>('/api/v1/driver-schedules?page_size=1000'),
      ]);

      setPlates(Array.isArray(platesResponse.data) ? platesResponse.data : []);
      setSchedules(Array.isArray(schedulesResponse.data) ? schedulesResponse.data : []);
      setError(null);
    } catch (err) {
      console.error("Failed to load plates and schedules:", err);
    }
  }, [role]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const natCode = normalizeDigits(form.driver_national_code.trim());
    if (!/^\d{10}$/.test(natCode)) {
      setError('کد ملی راننده باید دقیقاً ۱۰ رقم باشد.');
      toast.error('کد ملی راننده باید ۱۰ رقم معتبر باشد.');
      return;
    }
    const cleanUsername = form.utcms_username.trim();
    const cleanPassword = form.utcms_password.trim();
    if (!cleanUsername || cleanPassword.length < 4) {
      setError('نام کاربری و رمز UTCMS معتبر (حداقل ۴ کاراکتر) وارد کنید.');
      toast.error('نام کاربری و رمز عبور UTCMS را به درستی وارد کنید.');
      return;
    }
    const cleanPhone = form.phone ? normalizeDigits(form.phone.trim()) : undefined;
    const cleanLicense = form.license_number?.trim() || undefined;
    const cleanPlate = form.plate_number ? canonicalizePlate(form.plate_number.trim()) : '';
    if (!cleanPlate || cleanPlate.length < 2) {
      setError('ثبت پلاک خودرو برای هر راننده الزامی است.');
      toast.error('ثبت پلاک خودرو برای هر راننده الزامی است.');
      return;
    }
    setSaving(true);
    const response = await api.post<Driver>('/api/v1/drivers', {
      full_name: form.full_name.trim(),
      driver_national_code: natCode,
      phone: cleanPhone,
      license_number: cleanLicense,
      utcms_username: cleanUsername,
      utcms_password: cleanPassword,
      plate_number: cleanPlate,
    });
    setSaving(false);

    if (!response.success) {
      toast.error(response.error || 'ثبت راننده ناموفق بود');
      setError(response.error || 'ثبت راننده ناموفق بود');
      return;
    }

    toast.success('راننده جدید با موفقیت ثبت شد');
    setForm(initialDriver);
    setError(null);
    await Promise.all([refetchDrivers(), loadPlatesAndSchedules()]);
  }

  async function handleDriverUpdate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editDriver) {
      return;
    }
    setSaving(true);
    const payload = { ...editDriver.payload };
    if (payload.driver_national_code) {
      payload.driver_national_code = normalizeDigits(payload.driver_national_code.trim());
    }
    if (payload.phone) {
      payload.phone = normalizeDigits(payload.phone.trim());
    }
    if (payload.plate_number) {
      payload.plate_number = canonicalizePlate(payload.plate_number.trim());
    }
    if (!payload.utcms_password?.trim()) {
      delete payload.utcms_password;
    }
    const response = await api.put<Driver>(`/api/v1/drivers/${editDriver.id}`, payload);
    setSaving(false);
    if (!response.success) {
      toast.error(response.error || 'ویرایش راننده ناموفق بود');
      setError(response.error || 'ویرایش راننده ناموفق بود');
      return;
    }
    toast.success('اطلاعات راننده بروزرسانی شد');
    setEditDriver(null);
    await Promise.all([refetchDrivers(), loadPlatesAndSchedules()]);
  }

  async function handleDriverDelete(driverId: number) {
    setSaving(true);
    setDeleteConfirmId(null);
    const response = await api.delete<void>(`/api/v1/drivers/${driverId}`);
    setSaving(false);
    if (!response.success) {
      toast.error(response.error || 'حذف راننده ناموفق بود');
      setError(response.error || 'حذف راننده ناموفق بود');
      return;
    }
    toast.success('راننده با موفقیت حذف شد');
    await Promise.all([refetchDrivers(), loadPlatesAndSchedules()]);
  }

  async function handleDeletePlate(plateId: number) {
    setSaving(true);
    const response = await api.delete<void>(`/api/v1/plates/${plateId}`);
    setSaving(false);
    if (!response.success) {
      toast.error(response.error || 'حذف پلاک ناموفق بود');
      return;
    }
    toast.success('پلاک با موفقیت حذف شد');
    await loadPlatesAndSchedules();
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
      toast.error(response.error || 'ثبت پلاک ناموفق بود');
      setError(response.error || 'ثبت پلاک ناموفق بود');
      return;
    }
    toast.success('پلاک با موفقیت ثبت شد');
    setPlateForm({ driver_id: 0, plate_number: '', vehicle_type: '', notes: '' });
    await loadPlatesAndSchedules();
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
      toast.error(response.error || 'ثبت زمان‌بندی ناموفق بود');
      setError(response.error || 'ثبت زمان‌بندی ناموفق بود');
      return;
    }
    toast.success('زمان‌بندی جدید ثبت شد');
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
    await loadPlatesAndSchedules();
  }

  async function runSchedulesNow() {
    setSaving(true);
    const response = await api.post<{ created_count: number }>('/api/v1/driver-schedules/run-due', {});
    setSaving(false);
    if (!response.success) {
      setError(response.error || 'اجرای زمان‌بندی ناموفق بود');
      return;
    }
    toast.success(`تعداد ${response.data?.created_count || 0} زمان‌بندی سررسید شده اجرا شد`);
    await loadPlatesAndSchedules();
  }

  async function handleDeleteSchedule(scheduleId: number) {
    setSaving(true);
    const response = await api.delete(`/api/v1/driver-schedules/${scheduleId}`);
    setSaving(false);
    if (response.success) {
      toast.success('زمان‌بندی حذف شد');
      await loadPlatesAndSchedules();
    } else {
      setError(response.error || 'حذف زمان‌بندی ناموفق بود');
    }
  }

  async function handleToggleSchedule(schedule: DriverSchedule) {
    setSaving(true);
    const response = await api.put(`/api/v1/driver-schedules/${schedule.id}`, {
      is_active: !schedule.is_active,
    });
    setSaving(false);
    if (response.success) {
      toast.success(`زمان‌بندی ${!schedule.is_active ? 'فعال' : 'غیرفعال'} شد`);
      await loadPlatesAndSchedules();
    } else {
      setError(response.error || 'تغییر وضعیت زمان‌بندی ناموفق بود');
    }
  }

  useEffect(() => {
    void loadPlatesAndSchedules();
    void refetchDrivers();
  }, [role, loadPlatesAndSchedules, refetchDrivers]);

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <section className="flex flex-col gap-6 md:gap-10 xl:grid xl:grid-cols-[1fr_1.3fr] xl:grid-rows-[auto_auto] xl:items-start">
          
           <div className="flex xl:hidden rounded-2xl bg-slate-900/60 p-1 border border-white/5 mb-2 shadow-inner backdrop-blur-md overflow-x-auto scrollbar-none flex-nowrap shrink-0">
             <button
               type="button"
               onClick={() => setActiveTab('list')}
               className={`flex-1 min-w-[110px] shrink-0 rounded-xl py-4 text-xs font-black transition-all touch-target ${
                 activeTab === 'list' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="رانندگان ناوگان"
             >
               رانندگان ناوگان
             </button>
             <button
               type="button"
               onClick={() => setActiveTab('add')}
               className={`flex-1 min-w-[110px] shrink-0 rounded-xl py-4 text-xs font-black transition-all touch-target ${
                 activeTab === 'add' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="ثبت راننده"
             >
               ثبت راننده
             </button>
             <button
               type="button"
               onClick={() => setActiveTab('plates_schedules')}
               className={`flex-1 min-w-[130px] shrink-0 rounded-xl py-4 text-xs font-black transition-all touch-target ${
                 activeTab === 'plates_schedules' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="پلاک و زمان‌بندی"
             >
               پلاک و زمان‌بندی
             </button>
           </div>

          <div className={`${activeTab === 'add' ? 'block animate-in fade-in duration-300' : 'hidden xl:block'} xl:order-1 xl:col-start-1`}>
            <form onSubmit={handleSubmit} className="relative overflow-hidden rounded-[2.5rem] border border-white/10 bg-slate-950 px-8 py-10 text-white shadow-2xl shadow-slate-900/10">
              <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
              
              <div className="relative z-10">
                <div className="flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20">
                    <PlusIcon className="h-6 w-6" />
                  </div>
                  <div>
                    <h1 className="text-2xl font-black">ثبت راننده جدید</h1>
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

                <div className="mt-6 rounded-2xl border border-white/10 bg-slate-900/60 p-5">
                  <label className="block text-sm font-bold text-slate-200">
                    <span className="mb-2 flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <TruckIcon className="h-5 w-5 text-cyan-400" />
                        <span>پلاک خودرو راننده (جهت انتساب یکتای دائم)</span>
                      </span>
                      <span className="text-xs font-normal text-cyan-400">یکتا برای هر راننده</span>
                    </span>
                    <PlateInput
                      value={form.plate_number || ''}
                      onChange={(val) => setForm((current) => ({ ...current, plate_number: val }))}
                    />
                  </label>
                </div>

                 <div className="mt-10 flex justify-end">
                   <button type="submit" disabled={saving} className="min-w-[200px] min-h-[44px] rounded-2xl bg-cyan-400 px-8 py-4 text-sm font-black text-slate-950 shadow-xl shadow-cyan-400/20 transition hover:bg-cyan-300 active:scale-[0.98] disabled:opacity-60 touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">
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
          </div>

          <div className={`${activeTab === 'list' ? 'block animate-in fade-in duration-300' : 'hidden xl:block'} xl:order-3 xl:col-start-2 xl:row-span-2`}>
            <div className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl">
              <div className="flex items-center justify-between border-b border-white/5 pb-6">
                <div>
                  <h2 className="text-xl font-black text-white">رانندگان ناوگان</h2>
                  <p className="mt-1 text-sm text-slate-400">لیست تمامی رانندگان احراز هویت شده و وضعیت فعالیت آن‌ها</p>
                </div>
                 <button type="button" onClick={() => { void refetchDrivers(); void loadPlatesAndSchedules(); }} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950 px-5 py-3.5 text-xs font-bold text-slate-300 transition hover:bg-slate-900 hover:scale-105 active:scale-95 shadow-sm touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بروزرسانی لیست">
                   بروزرسانی لیست
                 </button>
              </div>

              {driversLoading ? (
                <div className="mt-8 space-y-4">
                  {[1, 2, 3].map((item) => <div key={item} className="h-32 skeleton rounded-3xl" />)}
                </div>
              ) : drivers.length === 0 ? (
                <div className="mt-12 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 bg-slate-950/20 py-20">
                  <p className="text-sm font-medium text-slate-400">هنوز راننده‌ای در سامانه ثبت نشده است.</p>
                </div>
              ) : (
                <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-1">
                  {drivers.map((driver) => (
                    <article key={driver.id} className="group relative rounded-[2rem] border border-white/5 bg-slate-950/30 p-6 transition-all hover:border-cyan-500/30 hover:bg-slate-950/60 hover:shadow-lg">
                      <div className="flex flex-wrap items-start justify-between gap-6">
                        <div className="flex items-center gap-5">
                          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-slate-400 shadow-sm transition-colors group-hover:text-cyan-400">
                            <UserCircleIcon className="h-8 w-8" />
                          </div>
                          <div>
                            <div className="flex items-center gap-3">
                              <h3 className="text-lg font-black text-white group-hover:text-cyan-400">{driver.full_name}</h3>
                              {driver.active_plate && (
                                <span className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/30 bg-cyan-950/60 px-2.5 py-0.5 text-xs font-black text-cyan-300">
                                  <TruckIcon className="h-3.5 w-3.5" />
                                  {driver.active_plate}
                                </span>
                              )}
                            </div>
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
                        <div className="rounded-2xl bg-slate-950/60 p-4 shadow-sm border border-white/5">
                          <p className="text-[10px] font-black uppercase text-slate-400">شناسه UTCMS</p>
                          <p className="mt-1 text-sm font-bold text-slate-200">{driver.utcms_username}</p>
                        </div>
                        <div className="rounded-2xl bg-slate-950/60 p-4 shadow-sm border border-white/5">
                          <p className="text-[10px] font-black uppercase text-slate-400">آخرین فعالیت</p>
                          <p className="mt-1 text-sm font-bold text-slate-200">{formatDateTime(driver.last_auth_at) || 'ثبت نشده'}</p>
                        </div>
                        <div className="rounded-2xl bg-slate-950/60 p-4 shadow-sm border border-white/5">
                          <p className="text-[10px] font-black uppercase text-slate-400">اعتبار نشست</p>
                          <p className="mt-1 text-sm font-bold text-slate-200">{formatDateTime(driver.last_session_expires_at) || 'نامشخص'}</p>
                        </div>
                      </div>

                      {driver.last_error_code && (
                        <div className="mt-6 rounded-2xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs font-bold text-rose-400 shadow-sm shadow-rose-950/20">
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
                                driver_national_code: driver.driver_national_code,
                                full_name: driver.full_name,
                                phone: driver.phone || '',
                                license_number: driver.license_number || '',
                                utcms_username: driver.utcms_username,
                                plate_number: driver.active_plate || '',
                                status: driver.status,
                              },
                            })
                          }
                          className="rounded-xl border border-white/10 bg-slate-950 px-5 py-3.5 text-xs font-bold text-slate-300 transition hover:bg-slate-900"
                        >
                          ویرایش اطلاعات
                        </button>
                        <button 
                          type="button" 
                          onClick={() => setDeleteConfirmId(driver.id)} 
                          className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-5 py-3.5 text-xs font-bold text-rose-400 transition hover:bg-rose-600 hover:text-white hover:border-rose-600"
                        >
                          حذف راننده
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className={`${activeTab === 'plates_schedules' ? 'block animate-in fade-in duration-300' : 'hidden xl:block'} xl:order-2 xl:col-start-1`}>
            <section className="grid gap-6 xl:grid-cols-1">
              <form onSubmit={handleCreatePlate} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
                <h2 className="text-xl font-black text-white">مدیریت پلاک</h2>
                <div className="mt-6 grid gap-4 md:grid-cols-2">
                  <label className="text-sm font-bold text-slate-200">
                    <span className="mb-2 block">راننده</span>
                    <select value={plateForm.driver_id} onChange={(event) => setPlateForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="field">
                      <option value={0}>انتخاب راننده</option>
                      {drivers.map((driver) => <option key={driver.id} value={driver.id} className="bg-slate-950">{driver.full_name}</option>)}
                    </select>
                  </label>
                  <label className="text-sm font-bold text-slate-200">
                    <span className="mb-2 block">پلاک <span className="mr-1 text-rose-500">*</span></span>
                    <PlateInput value={plateForm.plate_number} onChange={(value) => setPlateForm((current) => ({ ...current, plate_number: value }))} />
                  </label>
                  <Input label="نوع خودرو" value={plateForm.vehicle_type || ''} onChange={(value) => setPlateForm((current) => ({ ...current, vehicle_type: value }))} />
                  <Input label="یادداشت" value={plateForm.notes || ''} onChange={(value) => setPlateForm((current) => ({ ...current, notes: value }))} />
                </div>
                 <button type="submit" disabled={saving} className="mt-6 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-3.5 text-sm font-bold transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">ثبت پلاک</button>
                <div className="mt-6 space-y-2">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">لیست پلاک‌های ثبت‌شده</h3>
                  {plates.length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-2">هیچ پلاکی ثبت نشده است.</p>
                  ) : (
                    plates.map((plate) => {
                      const driver = drivers.find((d) => d.id === plate.driver_id);
                      return (
                        <div
                          key={plate.id}
                          className="flex items-center justify-between gap-3 rounded-2xl bg-slate-950/80 border border-white/5 px-4 py-3 text-sm text-slate-300 transition hover:border-cyan-500/20"
                        >
                          <div className="flex items-center gap-3">
                            <span className="font-bold text-cyan-400">{plate.plate_number}</span>
                            <span className="text-xs text-slate-400">
                              (راننده: {driver ? driver.full_name : `#${plate.driver_id}`})
                            </span>
                            {plate.vehicle_type && (
                              <span className="text-xs text-slate-500">| {plate.vehicle_type}</span>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => void handleDeletePlate(plate.id)}
                            disabled={saving}
                            className="rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-1 text-xs font-bold text-rose-400 hover:bg-rose-600 hover:text-white transition"
                          >
                            حذف
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              </form>


              <form onSubmit={handleScheduleCreate} className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
                <h2 className="text-xl font-black text-white">زمان‌بندی خودکار بارنامه</h2>
                <div className="mt-6 grid gap-4 md:grid-cols-2">
                  <label className="text-sm font-bold text-slate-200">
                    <span className="mb-2 block">راننده</span>
                    <select value={scheduleForm.driver_id} onChange={(event) => setScheduleForm((current) => ({ ...current, driver_id: Number(event.target.value) }))} className="field">
                      <option value={0}>انتخاب راننده</option>
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
                  <label className="text-sm font-bold text-slate-200">
                    <span className="mb-2 block">تناوب</span>
                    <select value={scheduleForm.frequency} onChange={(event) => setScheduleForm((current) => ({ ...current, frequency: event.target.value as 'daily' | 'weekly' | 'once' }))} className="field">
                      <option value="daily" className="bg-slate-950">روزانه</option>
                      <option value="weekly" className="bg-slate-950">هفتگی</option>
                      <option value="once" className="bg-slate-950">یکبار</option>
                    </select>
                  </label>
                </div>
                 <div className="mt-6 flex flex-wrap gap-2">
                   <button type="submit" disabled={saving} className="rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-5 py-3 text-sm font-bold transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">ثبت زمان‌بندی</button>
                   <button type="button" onClick={() => void runSchedulesNow()} disabled={saving} className="rounded-xl border border-white/10 bg-slate-950 hover:bg-slate-900 px-5 py-3 text-sm font-bold text-slate-300 transition touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500">
                     اجرای زمان‌بندی‌های سررسیدشده
                   </button>
                 </div>
                <div className="mt-6 space-y-3">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">لیست زمان‌بندی‌های فعال و تنظیم‌شده</h3>
                  {schedules.length === 0 ? (
                    <p className="text-xs text-slate-500 italic py-2">هیچ زمان‌بندی خودکاری ثبت نشده است.</p>
                  ) : (
                    schedules.map((schedule) => {
                      const driverName = drivers.find((d) => d.id === schedule.driver_id)?.full_name || `راننده #${schedule.driver_id}`;
                      const timesText = schedule.run_times?.length ? schedule.run_times.join(' , ') : schedule.run_time;
                      const freqLabel = schedule.frequency === 'daily' ? 'روزانه' : schedule.frequency === 'weekly' ? 'هفتگی' : 'یکبار';
                      return (
                        <div
                          key={schedule.id}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-950/80 border border-white/10 p-4 text-xs text-slate-200 transition hover:border-cyan-500/30"
                        >
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 font-bold text-slate-100">
                              <span className="text-cyan-400">{schedule.title}</span>
                              <span className="rounded-md bg-white/10 px-2 py-0.5 text-[10px] text-slate-300">
                                {freqLabel}
                              </span>
                              <span className="font-mono text-cyan-300 dir-ltr text-[11px]">
                                {timesText}
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-400">
                              راننده: <span className="text-slate-200 font-medium">{driverName}</span>
                              {schedule.start_date && ` | از: ${schedule.start_date}`}
                              {schedule.end_date && ` | تا: ${schedule.end_date}`}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void handleToggleSchedule(schedule)}
                              className={`rounded-lg px-3 py-1.5 text-[11px] font-bold border transition ${
                                schedule.is_active
                                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20'
                                  : 'bg-slate-800 text-slate-400 border-white/5 hover:bg-slate-700'
                              }`}
                            >
                              {schedule.is_active ? 'فعال' : 'غیرفعال'}
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDeleteSchedule(schedule.id)}
                              className="rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 px-3 py-1.5 text-[11px] font-bold hover:bg-rose-600 hover:text-white transition"
                            >
                              حذف
                            </button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </form>
            </section>
          </div>

        </section>
      </AppShell>

      {editDriver && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4 overflow-y-auto" role="dialog" aria-modal="true" aria-label="ویرایش اطلاعات راننده" onClick={() => setEditDriver(null)}>
          <div className="w-full max-w-xl rounded-3xl border border-white/10 bg-slate-900 p-6 sm:p-8 shadow-2xl text-white my-8 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <h3 className="text-lg font-black text-white flex items-center gap-2">
                <span>ویرایش اطلاعات راننده</span>
                <span className="text-xs text-cyan-400 font-mono">#{editDriver.id}</span>
              </h3>
              <button
                type="button"
                onClick={() => setEditDriver(null)}
                className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/5 transition"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleDriverUpdate} className="mt-6 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  label="نام و نام خانوادگی"
                  value={editDriver.payload.full_name || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, full_name: value } } : cur)}
                  required
                />
                <Input
                  label="کد ملی (۱۰ رقم)"
                  value={editDriver.payload.driver_national_code || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, driver_national_code: normalizeDigits(value) } } : cur)}
                  required
                />
                <Input
                  label="شماره تلفن همراه"
                  value={editDriver.payload.phone || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, phone: normalizeDigits(value) } } : cur)}
                />
                <Input
                  label="شماره گواهینامه"
                  value={editDriver.payload.license_number || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, license_number: value } } : cur)}
                />
                <Input
                  label="نام کاربری UTCMS"
                  value={editDriver.payload.utcms_username || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, utcms_username: value } } : cur)}
                  required
                />
                <Input
                  label="رمز عبور جدید UTCMS (اختیاری)"
                  type="password"
                  value={editDriver.payload.utcms_password || ''}
                  onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, utcms_password: value } } : cur)}
                />
                <div className="sm:col-span-2">
                  <PlateInput
                    value={editDriver.payload.plate_number || ''}
                    onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, plate_number: value } } : cur)}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="text-sm font-medium text-slate-200 block mb-2">وضعیت راننده</label>
                  <select
                    value={editDriver.payload.status || 'active'}
                    onChange={(e) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, status: e.target.value } } : cur)}
                    className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3.5 text-sm text-white outline-none transition focus:border-cyan-400"
                  >
                    <option value="active">فعال (Active)</option>
                    <option value="inactive">غیرفعال (Inactive)</option>
                    <option value="blocked">مسدود (Blocked)</option>
                  </select>
                </div>
              </div>

              <div className="mt-8 flex justify-end gap-3 border-t border-white/10 pt-6">
                <button
                  type="button"
                  onClick={() => setEditDriver(null)}
                  className="rounded-xl border border-white/10 bg-slate-950 px-5 py-3 text-sm font-bold text-slate-300 hover:bg-slate-800 transition touch-target focus:outline-none focus:ring-2 focus:ring-white"
                >
                  انصراف
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-3 text-sm font-bold transition disabled:opacity-50 touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                >
                  {saving ? 'در حال ذخیره...' : 'ذخیره تغییرات'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" role="dialog" aria-modal="true" aria-label="تأیید حذف راننده" onClick={() => setDeleteConfirmId(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl text-white" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-black">تأیید حذف</h3>
            <p className="mt-2 text-sm text-slate-400">آیا از حذف این راننده اطمینان دارید؟</p>
             <div className="mt-6 flex justify-end gap-3">
               <button onClick={() => setDeleteConfirmId(null)} className="rounded-xl border border-white/10 bg-slate-950 px-5 py-3 text-sm font-bold text-slate-300 hover:bg-slate-900 transition touch-target focus:outline-none focus:ring-2 focus:ring-white">
                 انصراف
               </button>
               <button onClick={() => void handleDriverDelete(deleteConfirmId)} className="rounded-xl bg-rose-500 px-5 py-3 text-sm font-bold text-white hover:bg-rose-600 transition touch-target focus:outline-none focus:ring-2 focus:ring-rose-500">
                 حذف شود
               </button>
             </div>
          </div>
        </div>
      )}
    </AuthGuard>
  );
}

const Input = memo(function Input({ label, onChange, required, type = 'text', value }: { label: string; onChange: (value: string) => void; required?: boolean; type?: string; value: string }) {
  return (
    <label className="text-sm font-medium text-slate-200">
      <span className="mb-2 block">{label}</span>
      <input type={type} required={required} value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-base md:text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-400 touch-target" />
    </label>
  );
});


