'use client';

import { useEffect, useState } from 'react';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { api } from '@/lib/api';
import { formatDateTime, statusLabel, toPersianDigits } from '@/lib/format';
import type { ClientProfile } from '@/lib/types';
import { useSession } from "@/hooks/useSession";

export default function SettingsPage() {
  const { role } = useSession();
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProfile() {
      if (role !== "client") return;

      const response = await api.get<ClientProfile>('/api/v1/auth/me');
      if (!response.success || !response.data) {
        setError(response.error || 'پروفایل مشتری بارگذاری نشد');
        return;
      }
      setProfile(response.data);
    }

    loadProfile();
  }, [role]);

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[32px] border border-white/20 bg-slate-950 p-6 text-white shadow-2xl shadow-slate-900/20">
            <h1 className="text-3xl font-semibold">حساب مشتری</h1>
            <p className="mt-3 text-sm leading-7 text-slate-300">این بخش اکنون به `auth/me` متصل است و اطلاعات اشتراک و ظرفیت عملیاتی را از بک‌اند واقعی می‌خواند.</p>
            <div className="mt-8 space-y-3 text-sm text-slate-300">
              <p>وضعیت حساب: <span className="font-semibold text-white">{profile ? statusLabel(profile.status) : '-'}</span></p>
              <p>آخرین ورود: <span className="font-semibold text-white">{profile ? formatDateTime(profile.last_login_at) : '-'}</span></p>
              <p>تاریخ ساخت: <span className="font-semibold text-white">{profile ? formatDateTime(profile.created_at) : '-'}</span></p>
            </div>
          </div>

          <div className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 shadow-2xl text-white">
            <h2 className="text-2xl font-semibold text-white">جزئیات اشتراک و ظرفیت</h2>
            {profile ? (
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <InfoCard label="نام مجموعه" value={profile.name} />
                <InfoCard label="کد مشتری" value={profile.client_code} />
                <InfoCard label="ایمیل" value={profile.email} />
                <InfoCard label="تلفن" value={profile.phone || '-'} />
                <InfoCard label="حداکثر راننده" value={toPersianDigits(profile.max_drivers)} />
                <InfoCard label="پردازش همزمان" value={toPersianDigits(profile.max_concurrent_tasks)} />
                <InfoCard label="سقف روزانه" value={toPersianDigits(profile.max_daily_tasks)} />
                <InfoCard label="وضعیت" value={statusLabel(profile.status)} />
              </div>
            ) : (
              <div className="mt-6 rounded-[2rem] border border-dashed border-white/10 px-5 py-8 text-sm text-slate-555 text-slate-500">در حال بارگذاری مشخصات مشتری...</div>
            )}
            {error && <p className="mt-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 px-4 py-3 text-sm text-rose-400">{error}</p>}
          </div>
        </section>
      </AuthGuard>
    </AppShell>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded-3xl bg-slate-950/60 border border-white/5 p-5 text-white">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-3 text-base font-semibold text-white">{value}</p>
    </article>
  );
}
