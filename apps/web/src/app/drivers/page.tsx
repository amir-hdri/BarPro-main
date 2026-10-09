'use client';

import Link from 'next/link';
import { normalizePersianText } from '@/lib/plate';
import { tehranDateKey } from '@/lib/record-filters';
import { sessionQueryKey } from '@/lib/session-query';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ClipboardDocumentCheckIcon,
  ClipboardDocumentIcon,
  DevicePhoneMobileIcon,
  PlusIcon,
  SignalIcon,
  TruckIcon,
  UserCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { DriverTrackingPanel } from '@/components/DriverTrackingPanel';
import { PlateInput } from '@/components/PlateInput';
import { toast } from 'react-hot-toast';
import { api } from '@/lib/api';
import { copyText } from '@/lib/clipboard';
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
  vehicle_type: 'کامیون',
};

const VEHICLE_TYPE_PRESETS = [
  "کامیون",
  "تریلی کشنده",
  "کامیونت (خاور)",
  "وانت بار",
  "تک (۱۰ تن)",
  "جفت (۱۵ تن)",
  "تریلی کفی",
  "تریلی لبه‌دار",
  "تریلی کمپرسی",
  "تریلی ترانزیت",
  "بونکر",
  "تانکر",
];

interface ForwarderConfig {
  driver_id: number;
  driver_phone: string;
  webhook_path: string;
  token_configured: boolean;
  storage_ready: boolean;
  intake_ready: boolean;
  required_header_name: string;
  authentication_instructions: string;
  forwarder_connection_verified: boolean;
  setup_recorded: boolean;
  provisioned?: boolean;
  permissions_complete?: boolean;
  permissions_revoked?: boolean;
  status_available: boolean;
  permissions_observed_at?: number | null;
  last_sms_at?: number | null;
  last_seen?: number | null;
  permissions?: Record<string, boolean>;
  primary_sms_gateway_phone?: string;
}


export default function DriversPage() {
  const { role, client } = useSession();
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
  const [forwarderDriver, setForwarderDriver] = useState<Driver | null>(null);
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [driverSearch, setDriverSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'list' | 'add' | 'plates_schedules' | 'tracking'>('list');
  const dataLoadControllerRef = useRef<AbortController | null>(null);

  const { data: forwarderConfig, isPending: forwarderLoading, isError: forwarderFailed, refetch: refetchForwarderConfig } = useQuery({
    queryKey: sessionQueryKey(client, 'otp-forwarder-config', forwarderDriver?.id),
    enabled: Boolean(client && forwarderDriver),
    queryFn: async ({ signal }) => {
      const response = await api.get<ForwarderConfig>(
        `/api/v1/otp/forwarder-config/${forwarderDriver?.id}`, undefined, { signal },
      );
      if (!response.success || !response.data) throw new Error(response.error || 'تنظیمات دریافت نشد');
      return response.data;
    },
    staleTime: 0,
  });
  const forwarderUrl = forwarderConfig && typeof window !== 'undefined'
    ? new URL(forwarderConfig.webhook_path, window.location.origin).href
    : '';

  useEffect(() => { setCopiedWebhook(false); }, [forwarderDriver?.id]);

  const { data: drivers = [], isLoading: driversLoading, refetch: refetchDrivers } = useQuery({
    queryKey: sessionQueryKey(client, 'drivers'),
    queryFn: async ({ signal }) => {
      const res = await api.get<Driver[]>('/api/v1/drivers?page_size=1000', undefined, { signal });
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

    dataLoadControllerRef.current?.abort();
    const controller = new AbortController();
    dataLoadControllerRef.current = controller;
    try {
      const [platesResponse, schedulesResponse] = await Promise.all([
        api.get<Plate[]>('/api/v1/plates?page_size=1000', undefined, { signal: controller.signal }),
        api.get<DriverSchedule[]>('/api/v1/driver-schedules?page_size=1000', undefined, { signal: controller.signal }),
      ]);

      if (controller.signal.aborted) return;

      setPlates(Array.isArray(platesResponse.data) ? platesResponse.data : []);
      setSchedules(Array.isArray(schedulesResponse.data) ? schedulesResponse.data : []);
      setError(null);
    } catch (err) {
      if (!controller.signal.aborted) console.error("Failed to load plates and schedules:", err);
    }
    if (dataLoadControllerRef.current === controller) dataLoadControllerRef.current = null;
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
      vehicle_type: form.vehicle_type || 'کامیون',
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
    return () => dataLoadControllerRef.current?.abort();
  }, [role, loadPlatesAndSchedules, refetchDrivers]);

  const visibleDrivers = drivers.filter(driver => normalizePersianText(normalizeDigits(`${driver.full_name} ${driver.driver_national_code} ${driver.phone || ''}`)).includes(normalizePersianText(normalizeDigits(driverSearch.trim()))));

  return (
    <AuthGuard requiredRole="client">
      <AppShell>
        <section className="flex flex-col gap-6 md:gap-10 xl:grid xl:grid-cols-[1fr_1.3fr] xl:grid-rows-[auto_auto] xl:items-start">
          
           <div className="flex xl:hidden rounded-2xl bg-slate-900/60 p-1 border border-white/5 mb-2 shadow-inner backdrop-blur-md shrink-0">
             <button
               type="button"
               onClick={() => setActiveTab('list')}
               className={`flex-1 min-w-0 rounded-xl py-3.5 text-[11px] font-black transition-all touch-target whitespace-nowrap overflow-hidden ${
                 activeTab === 'list' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="رانندگان ناوگان"
             >
               رانندگان ناوگان
             </button>
             <button
               type="button"
               onClick={() => setActiveTab('add')}
               className={`flex-1 min-w-0 rounded-xl py-3.5 text-[11px] font-black transition-all touch-target whitespace-nowrap overflow-hidden ${
                 activeTab === 'add' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="ثبت راننده"
             >
               ثبت راننده
             </button>
             <button
               type="button"
               onClick={() => setActiveTab('plates_schedules')}
               className={`flex-1 min-w-0 rounded-xl py-3.5 text-[11px] font-black transition-all touch-target whitespace-nowrap overflow-hidden ${
                 activeTab === 'plates_schedules' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="پلاک و زمان‌بندی"
             >
               پلاک و زمان‌بندی
             </button>
             <button
               type="button"
               onClick={() => setActiveTab('tracking')}
               className={`flex-1 min-w-0 rounded-xl py-3.5 text-[11px] font-black transition-all touch-target whitespace-nowrap overflow-hidden ${
                 activeTab === 'tracking' ? 'bg-slate-950 border border-white/10 text-cyan-400 shadow-lg' : 'text-slate-400 hover:text-slate-200'
               }`}
               aria-label="پیگیری راننده‌ها"
             >
               پیگیری راننده‌ها
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

                <div className="mt-6 rounded-2xl border border-white/10 bg-slate-900/60 p-5 space-y-4">
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

                  <div className="pt-2 border-t border-white/5">
                    <label className="block text-sm font-bold text-slate-200 mb-2">
                      نوع خودرو / ناوگان
                    </label>
                    <input
                      type="text"
                      className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400"
                      placeholder="مثال: کامیون، تریلی کشنده، خاور..."
                      value={form.vehicle_type || ''}
                      onChange={(e) => setForm((current) => ({ ...current, vehicle_type: e.target.value }))}
                    />
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {VEHICLE_TYPE_PRESETS.map((type) => (
                        <button
                          key={type}
                          type="button"
                          onClick={() => setForm((current) => ({ ...current, vehicle_type: type }))}
                          className={`px-2.5 py-1 rounded-lg text-xs transition-all ${
                            form.vehicle_type === type
                              ? 'bg-cyan-500 text-slate-950 font-black shadow-sm shadow-cyan-500/30'
                              : 'bg-slate-950 text-slate-300 hover:bg-slate-800 hover:text-white border border-white/5 font-medium'
                          }`}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                  </div>
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
                  <p className="mt-1 text-sm text-slate-400">راننده را پیدا کنید و بارنامه‌های روز یا سابقه استعلام سوخت او را ببینید.</p>
                </div>
                 <button type="button" onClick={() => { void refetchDrivers(); void loadPlatesAndSchedules(); }} className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950 px-5 py-3.5 text-xs font-bold text-slate-300 transition hover:bg-slate-900 hover:scale-105 active:scale-95 shadow-sm touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500" aria-label="بروزرسانی لیست">
                   بروزرسانی لیست
                 </button>
              </div>

              <label htmlFor="driver-search" className="mt-5 mb-2 block text-xs font-bold text-slate-300">جستجوی راننده</label>
              <input id="driver-search" className="field touch-target" placeholder="نام، کد ملی یا شماره همراه" value={driverSearch} onChange={event => setDriverSearch(event.target.value)} />
              {driversLoading ? (
                <div className="mt-8 space-y-4">
                  {[1, 2, 3].map((item) => <div key={item} className="h-32 skeleton rounded-3xl" />)}
                </div>
              ) : drivers.length === 0 ? (
                <div className="mt-12 flex flex-col items-center justify-center rounded-[2rem] border-2 border-dashed border-white/5 bg-slate-950/20 py-20">
                  <p className="text-sm font-medium text-slate-400">هنوز راننده‌ای در سامانه ثبت نشده است.</p>
                </div>
              ) : visibleDrivers.length === 0 ? <p className="py-8 text-sm text-slate-400">راننده‌ای با این جستجو پیدا نشد.</p> : (
                <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-1">
                  {visibleDrivers.map((driver) => (
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
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className="inline-flex items-center gap-1 rounded-lg border border-cyan-500/30 bg-cyan-950/60 px-2.5 py-0.5 text-xs font-black text-cyan-300">
                                    <TruckIcon className="h-3.5 w-3.5" />
                                    {driver.active_plate}
                                  </span>
                                  {(() => {
                                    const p = plates.find((pl) => pl.driver_id === driver.id && pl.status === 'active') || plates.find((pl) => pl.driver_id === driver.id);
                                    return p?.vehicle_type ? (
                                      <span className="inline-flex items-center rounded-lg border border-white/10 bg-slate-900 px-2 py-0.5 text-[11px] font-bold text-slate-300">
                                        {p.vehicle_type}
                                      </span>
                                    ) : null;
                                  })()}
                                </div>
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

                      <div className="mt-6 grid gap-3 sm:grid-cols-2">
                        <Link href={`/history?driver_id=${driver.id}&day=${tehranDateKey()}`} className="touch-target flex items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-xs font-bold text-cyan-300">بارنامه‌های امروز</Link>
                        <Link href={`/fuel?driver_id=${driver.id}`} className="touch-target flex items-center justify-center rounded-xl border border-white/10 px-4 py-3 text-xs font-bold text-slate-200">سوابق استعلام سوخت</Link>
                      </div>
                      <div className="mt-8 flex flex-wrap justify-end gap-3 border-t border-white/5 pt-6">
                        <button
                          type="button"
                          onClick={() => setForwarderDriver(driver)}
                          className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3.5 text-xs font-bold text-cyan-300 transition hover:bg-cyan-500/20 hover:border-cyan-500/40 flex items-center gap-1.5 touch-target"
                          title="تنظیمات فورواردر پیامک راننده"
                        >
                          <DevicePhoneMobileIcon className="h-4 w-4 text-cyan-400" />
                          <span>فورواردر پیامک OTP</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const activePlateObj = plates.find((p) => p.driver_id === driver.id && p.status === 'active') || plates.find((p) => p.driver_id === driver.id);
                            setEditDriver({
                              id: driver.id,
                              payload: {
                                driver_national_code: driver.driver_national_code,
                                full_name: driver.full_name,
                                phone: driver.phone || '',
                                license_number: driver.license_number || '',
                                utcms_username: driver.utcms_username,
                                plate_number: driver.active_plate || '',
                                vehicle_type: activePlateObj?.vehicle_type || 'کامیون',
                                status: driver.status,
                              },
                            });
                          }}
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

          <div className={`${activeTab === 'tracking' ? 'block animate-in fade-in duration-300' : 'hidden xl:block'} xl:order-4 xl:col-start-1`}>
            <DriverTrackingPanel role={role} />
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
                aria-label="بستن پنجره"
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
                <div className="sm:col-span-2 space-y-4 rounded-2xl border border-white/10 bg-slate-900/40 p-4">
                  <label className="block text-sm font-bold text-slate-200">
                    پلاک خودرو راننده
                  </label>
                  <PlateInput
                    value={editDriver.payload.plate_number || ''}
                    onChange={(value) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, plate_number: value } } : cur)}
                  />

                  <div className="pt-2 border-t border-white/5">
                    <label className="block text-sm font-bold text-slate-200 mb-2">
                      نوع خودرو / ناوگان
                    </label>
                    <input
                      type="text"
                      className="w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-white outline-none transition focus:border-cyan-400"
                      placeholder="مثال: کامیون، تریلی کشنده، خاور..."
                      value={editDriver.payload.vehicle_type || ''}
                      onChange={(e) => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, vehicle_type: e.target.value } } : cur)}
                    />
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {VEHICLE_TYPE_PRESETS.map((type) => (
                        <button
                          key={type}
                          type="button"
                          onClick={() => setEditDriver((cur) => cur ? { ...cur, payload: { ...cur.payload, vehicle_type: type } } : cur)}
                          className={`px-2.5 py-1 rounded-lg text-xs transition-all ${
                            editDriver.payload.vehicle_type === type
                              ? 'bg-cyan-500 text-slate-950 font-black shadow-sm shadow-cyan-500/30'
                              : 'bg-slate-950 text-slate-300 hover:bg-slate-800 hover:text-white border border-white/5 font-medium'
                          }`}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                  </div>
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

      {forwarderDriver && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4 overflow-y-auto"
          role="dialog"
          aria-modal="true"
          aria-label="تنظیمات فورواردر پیامک راننده"
          onKeyDown={event => { if (event.key === 'Escape') setForwarderDriver(null); }}
          onClick={() => setForwarderDriver(null)}
        >
          <div
            className="w-full max-w-xl max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-3xl border border-cyan-500/30 bg-slate-900 p-6 sm:p-8 shadow-2xl relative my-auto text-white animate-in fade-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-500/20 text-cyan-400 ring-1 ring-cyan-500/30 shadow-inner">
                  <DevicePhoneMobileIcon className="h-6 w-6" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-white">تنظیمات فورواردر پیامک راننده (SMS Forwarder)</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    راننده: <span className="text-cyan-300 font-bold">{forwarderDriver.full_name}</span> ({forwarderDriver.phone || 'فاقد شماره همراه'})
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setForwarderDriver(null)}
                className="touch-target p-2 text-slate-400 hover:text-white rounded-xl hover:bg-white/5 transition"
                aria-label="بستن"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-5 text-xs leading-relaxed">
              {/* Webhook URL Box */}
              <div className="rounded-2xl bg-slate-950 border border-white/10 p-4">
                <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                  آدرس وب‌هوک اختصاصی این راننده (Webhook URL)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    dir="ltr"
                    value={forwarderUrl}
                    className="w-full rounded-xl bg-slate-900 border border-white/10 px-3.5 py-2.5 text-xs font-mono text-cyan-300 select-all outline-none"
                  />
                  <button
                    type="button"
                    disabled={!forwarderUrl}
                    onClick={async () => {
                      if (!await copyText(forwarderUrl)) {
                        toast.error('کپی خودکار ممکن نشد؛ آدرس را انتخاب و دستی کپی کنید.');
                        return;
                      }
                      setCopiedWebhook(true);
                      toast.success('آدرس وب‌هوک کپی شد');
                      setTimeout(() => setCopiedWebhook(false), 2000);
                    }}
                    className="shrink-0 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold px-4 py-2.5 text-xs transition flex items-center gap-1.5 shadow-md shadow-cyan-950 touch-target disabled:opacity-50"
                  >
                    {copiedWebhook ? (
                      <>
                        <ClipboardDocumentCheckIcon className="h-4 w-4" />
                        کپی شد
                      </>
                    ) : (
                      <>
                        <ClipboardDocumentIcon className="h-4 w-4" />
                        کپی آدرس
                      </>
                    )}
                  </button>
                </div>
                <p className="mt-2 text-[11px] text-slate-400">
                  این آدرس را در بخش URL برنامه فورواردر پیامک گوشی راننده قرار دهید تا پیامک‌های ارسالی بدون نیاز به تایپ دستی ثبت شوند.
                </p>
              </div>

              <div
                className={`rounded-2xl border p-4 text-xs transition-all ${
                  forwarderLoading
                    ? 'border-white/10 bg-slate-900/50 text-slate-300'
                    : forwarderFailed
                    ? 'border-rose-500/20 bg-rose-500/5 text-rose-300'
                    : forwarderConfig?.setup_recorded
                    ? forwarderConfig?.permissions_revoked
                      ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                      : forwarderConfig?.permissions_complete
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                      : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                    : forwarderConfig?.intake_ready
                    ? 'border-amber-500/20 bg-amber-500/5 text-amber-200'
                    : 'border-rose-500/20 bg-rose-500/5 text-rose-300'
                }`}
                role="status"
              >
                {forwarderLoading ? (
                  'در حال بررسی آمادگی سرور…'
                ) : forwarderFailed ? (
                  'آمادگی سرور و تنظیمات این راننده قابل بررسی نیست؛ اتصال فورواردر تأیید نشده است.'
                ) : forwarderConfig?.status_available === false ? (
                  'آخرین گزارش گوشی قابل بازیابی نیست؛ وضعیت فعلی نامشخص است.'
                ) : forwarderConfig?.setup_recorded ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 font-bold text-sm">
                        {forwarderConfig.permissions_revoked ? (
                          <>
                            <span className="inline-block w-2.5 h-2.5 rounded-full bg-rose-400"></span>
                            <span className="text-rose-300">راه‌اندازی‌شده، اما مجوزهای ضروری در آخرین گزارش غیرفعال بوده‌اند!</span>
                          </>
                        ) : forwarderConfig.permissions_complete ? (
                          <>
                            <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                            <span className="text-emerald-300">راه‌اندازی‌شده و مجوزها در آخرین گزارش کامل بوده است</span>
                          </>
                        ) : (
                          <>
                            <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                            <span className="text-amber-300">راه‌اندازی برنامه ثبت شده (اطلاعات مجوزها هنوز گزارش نشده است)</span>
                          </>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => void refetchForwarderConfig()}
                        className="min-h-11 min-w-11 touch-manipulation rounded-lg bg-slate-800/80 border border-white/20 px-2.5 py-1 text-[11px] font-bold text-slate-200 hover:bg-slate-700/80 transition"
                      >
                        بازخوانی آخرین گزارش
                      </button>
                    </div>
                    {forwarderConfig.last_seen ? (
                      <p className="text-[11px] text-slate-300">
                        آخرین ارتباط ثبت‌شده: {new Date(forwarderConfig.last_seen * 1000).toLocaleString('fa-IR')}
                      </p>
                    ) : null}
                    <p className="text-[11px] text-slate-300">
                      این سابقه وضعیت پایدار «راه‌اندازی‌شده» و آخرین گزارش ارتباط است، نه استعلام آنلاین لحظه‌ای. در نبود اینترنت گوشی، وضعیت راننده قطع نشان داده نمی‌شود؛ برای آزمون تازه، از گزینه «تست سلامت و اتصال» یا «ارسال پیامک تستی» در اپلیکیشن گوشی راننده استفاده کنید.
                    </p>
                    {!forwarderConfig.intake_ready && <p className="text-amber-300">دریافت پیامک روی سرور در حال حاضر آماده نیست.</p>}
                    <p className="text-[11px] text-slate-300">
                      زمان گزارش مجوزها: {forwarderConfig.permissions_observed_at
                        ? new Date(forwarderConfig.permissions_observed_at * 1000).toLocaleString('fa-IR')
                        : 'نامشخص؛ تست سلامت را روی گوشی اجرا کنید'}
                    </p>
                    {forwarderConfig.last_sms_at && <p className="text-[11px]">آخرین پیامک پذیرفته‌شده در درگاه: {new Date(forwarderConfig.last_sms_at * 1000).toLocaleString('fa-IR')}</p>}
                    {forwarderConfig.permissions && Object.keys(forwarderConfig.permissions).length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1 text-[10px]">
                        <span className={`rounded px-2 py-0.5 border ${
                          forwarderConfig.permissions.receive_sms === true
                            ? 'bg-emerald-950/80 border-emerald-500/20 text-emerald-300'
                            : 'bg-rose-950/80 border-rose-500/20 text-rose-300'
                        }`}>
                          دریافت پیامک: {forwarderConfig.permissions.receive_sms === true ? '✅ در آخرین گزارش' : forwarderConfig.permissions.receive_sms === false ? '❌ مجوز داده نشده' : 'نامشخص'}
                        </span>
                        <span className={`rounded px-2 py-0.5 border ${
                          forwarderConfig.permissions.send_sms === true
                            ? 'bg-emerald-950/80 border-emerald-500/20 text-emerald-300'
                            : 'bg-rose-950/80 border-rose-500/20 text-rose-300'
                        }`}>
                          ارسال پیامک رله: {forwarderConfig.permissions.send_sms === true ? '✅ در آخرین گزارش' : forwarderConfig.permissions.send_sms === false ? '❌ مجوز داده نشده' : 'نامشخص'}
                        </span>
                        <span className={`rounded px-2 py-0.5 border ${
                          forwarderConfig.permissions.battery_optimization_ignored === true
                            ? 'bg-emerald-950/80 border-emerald-500/20 text-emerald-300'
                            : 'bg-amber-950/80 border-amber-500/20 text-amber-300'
                        }`}>
                          باتری بدون توقف: {forwarderConfig.permissions.battery_optimization_ignored === true ? '✅ در آخرین گزارش' : forwarderConfig.permissions.battery_optimization_ignored === false ? '⚠️ نیاز به معافیت' : 'نامشخص'}
                        </span>
                      </div>
                    )}
                  </div>
                ) : forwarderConfig?.intake_ready ? (
                  <div className="flex items-center justify-between">
                    <span>سرور آماده دریافت پیامک است؛ اتصال برنامه گوشی راننده هنوز ثبت نشده است.</span>
                    <button
                      type="button"
                      onClick={() => void refetchForwarderConfig()}
                      className="min-h-11 min-w-11 touch-manipulation rounded-lg bg-amber-950/60 border border-amber-500/30 px-2.5 py-1 text-[11px] font-bold text-amber-300 hover:bg-amber-900/60 transition"
                    >
                      بازخوانی آخرین گزارش
                    </button>
                  </div>
                ) : (
                  'دریافت پیامک روی سرور آماده نیست؛ اپراتور باید تنظیمات و سرویس ذخیره‌سازی را بررسی کند.'
                )}
              </div>

              {/* The global webhook secret is never sent to the browser. */}
              <div className="rounded-2xl bg-cyan-950/20 border border-cyan-500/20 p-4 space-y-3">
                <h3 className="font-bold text-cyan-300 text-xs flex items-center gap-2">
                  <SignalIcon className="h-4 w-4 text-cyan-400" />
                  راهنمای راه‌اندازی روی گوشی اندروید راننده:
                </h3>
                <ol className="list-decimal list-inside space-y-2 text-slate-300 text-[11px] pe-1">
                  <li>
                    اپلیکیشن <span className="text-white font-bold">SecureSMS Forwarder</span> را روی گوشی راننده نصب کنید.
                  </li>
                  <li>
                    یک قانون (Rule) جدید اضافه کرده و فرستنده (Sender) را روی سرشماره‌های سامانه بارنامه کشوری (<code className="bg-slate-900 px-1 py-0.5 rounded text-cyan-300 font-mono">20007777</code> یا <code className="bg-slate-900 px-1 py-0.5 rounded text-cyan-300 font-mono">30001923</code>) قرار دهید.
                  </li>
                  <li>
                    نوع ارسال را روی <code className="bg-slate-900 px-1 py-0.5 rounded text-amber-300 font-mono">Webhook (POST)</code> قرار داده و آدرس وب‌هوک کپی‌شده در بالا را در آن قرار دهید.
                  </li>
                  <li>
                    بدنه را JSON و شامل متن پیامک (<code>text</code>)، فرستنده (<code>sender</code>) و زمان دریافت (<code>timestamp</code>) تنظیم کنید.
                  </li>
                  <li>
                    اپراتور مجاز باید هدر <code dir="ltr">{forwarderConfig?.required_header_name || 'X-OTP-Webhook-Token'}</code> را با اعتبارنامه مناسب در گوشی تنظیم کند. بدون این هدر پیامک پذیرفته نمی‌شود؛ مقدار محرمانه در این صفحه نمایش داده نمی‌شود.
                  </li>
                  <li>
                    پس از تنظیم هدر، یک درخواست آزمایشی با بدنه <code dir="ltr">{'{"event":"HEALTH_CHECK"}'}</code> ارسال و پاسخ <code>ready</code> را بررسی کنید. این تست فقط اتصال به سرور را می‌سنجد؛ دریافت SMS واقعی باید جداگانه بررسی شود.
                  </li>
                </ol>
              </div>

              <div className="rounded-2xl bg-slate-950/60 border border-white/5 p-4 text-[11px] text-slate-400">
                <span className="font-bold text-amber-400">نحوه عملکرد:</span> نیاز به OTP را پاسخ فعلی سامانه تعیین می‌کند. پس از دریافت پیامک معتبر، درخواست تکمیل سند در صف قرار می‌گیرد؛ نتیجه صدور و کد رهگیری را در صفحه پیگیری کارها بررسی کنید.
              </div>
            </div>

            <div className="mt-6 flex justify-end border-t border-white/5 pt-4">
              <button
                type="button"
                onClick={() => setForwarderDriver(null)}
                className="touch-target rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold px-6 py-2.5 text-xs transition"
              >
                بستن
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
