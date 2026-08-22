'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PlusIcon, MapPinIcon, TrashIcon, PencilIcon, StarIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Route as RouteIcon } from 'lucide-react';
import { StarIcon as StarSolidIcon } from '@heroicons/react/24/solid';
import { toast } from 'react-hot-toast';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProvinceCitySelect } from '@/components/ProvinceCitySelect';
import { RouteDistanceBadge } from '@/components/RouteDistanceBadge';
import { api } from '@/lib/api';
import { formatDateTime, toPersianDigits } from '@/lib/format';
import { useSession } from '@/hooks/useSession';
import type { WaybillRouteTemplate } from '@/lib/types';

interface FormState {
  name: string;
  origin_province: string;
  origin_city: string;
  origin_address: string;
  origin_lat: string;
  origin_lng: string;
  dest_province: string;
  dest_city: string;
  dest_address: string;
  dest_lat: string;
  dest_lng: string;
  is_favorite: boolean;
}

const emptyForm: FormState = {
  name: '',
  origin_province: '',
  origin_city: '',
  origin_address: '',
  origin_lat: '',
  origin_lng: '',
  dest_province: '',
  dest_city: '',
  dest_address: '',
  dest_lat: '',
  dest_lng: '',
  is_favorite: true,
};

export default function RouteTemplatesPage() {
  const { role } = useSession();
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [originCoords, setOriginCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [destCoords, setDestCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const { data: templates = [], isLoading, refetch } = useQuery({
    queryKey: ['route-templates'],
    queryFn: async () => {
      const res = await api.get<WaybillRouteTemplate[]>('/api/v1/route-templates');
      if (!res.success || !Array.isArray(res.data)) return [];
      return res.data;
    },
    staleTime: 30000,
    enabled: role === 'client' || role === 'master_admin',
  });

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function resetForm() {
    setForm(emptyForm);
    setEditingId(null);
    setOriginCoords(null);
    setDestCoords(null);
  }

  function startEdit(t: WaybillRouteTemplate) {
    setEditingId(t.id);
    setForm({
      name: t.name || '',
      origin_province: t.origin_province || '',
      origin_city: t.origin_city || '',
      origin_address: t.origin_address || '',
      origin_lat: t.origin_lat != null ? String(t.origin_lat) : '',
      origin_lng: t.origin_lng != null ? String(t.origin_lng) : '',
      dest_province: t.dest_province || '',
      dest_city: t.dest_city || '',
      dest_address: t.dest_address || '',
      dest_lat: t.dest_lat != null ? String(t.dest_lat) : '',
      dest_lng: t.dest_lng != null ? String(t.dest_lng) : '',
      is_favorite: Boolean(t.is_favorite),
    });
    setOriginCoords(t.origin_lat != null && t.origin_lng != null ? { lat: t.origin_lat, lng: t.origin_lng } : null);
    setDestCoords(t.dest_lat != null && t.dest_lng != null ? { lat: t.dest_lat, lng: t.dest_lng } : null);
    setShowForm(true);
  }

  function parseCoord(v: string): number | undefined {
    const t = v.trim();
    if (!t) return undefined;
    const n = Number(t);
    return Number.isFinite(n) ? n : undefined;
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error('نام مسیر الزامی است');
      return;
    }
    if (!form.origin_province.trim() || !form.origin_city.trim()) {
      toast.error('استان و شهر مبدأ الزامی است');
      return;
    }
    if (!form.dest_province.trim() || !form.dest_city.trim()) {
      toast.error('استان و شهر مقصد الزامی است');
      return;
    }

    const body = {
      name: form.name.trim(),
      origin_province: form.origin_province.trim(),
      origin_city: form.origin_city.trim(),
      origin_address: form.origin_address.trim() || undefined,
      origin_lat: parseCoord(form.origin_lat),
      origin_lng: parseCoord(form.origin_lng),
      dest_province: form.dest_province.trim(),
      dest_city: form.dest_city.trim(),
      dest_address: form.dest_address.trim() || undefined,
      dest_lat: parseCoord(form.dest_lat),
      dest_lng: parseCoord(form.dest_lng),
      is_favorite: form.is_favorite,
    };

    setSaving(true);
    const res = editingId
      ? await api.put<WaybillRouteTemplate>(`/api/v1/route-templates/${editingId}`, body)
      : await api.post<WaybillRouteTemplate>('/api/v1/route-templates', body);
    setSaving(false);

    if (!res.success) {
      toast.error(res.error || 'ذخیرهٔ مسیر ناموفق بود');
      return;
    }

    toast.success(editingId ? 'مسیر به‌روزرسانی شد' : 'مسیر جدید ذخیره شد');
    resetForm();
    setShowForm(false);
    await refetch();
  }

  async function handleDelete(id: number) {
    setDeletingId(id);
    const res = await api.delete(`/api/v1/route-templates/${id}`);
    setDeletingId(null);
    if (!res.success) {
      toast.error(res.error || 'حذف مسیر ناموفق بود');
      return;
    }
    toast.success('مسیر حذف شد');
    await refetch();
  }

  async function handleFavorite(id: number) {
    const res = await api.post<WaybillRouteTemplate>(`/api/v1/route-templates/${id}/favorite`);
    if (!res.success) {
      toast.error(res.error || 'تغییر وضعیت علاقه‌مندی ناموفق بود');
      return;
    }
    await refetch();
  }

  return (
    <AuthGuard>
      <AppShell>
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-black text-white">قالب‌های مسیر</h1>
              <p className="mt-1 text-sm text-slate-400">
                مسیرهای پرتکرار (مبدأ → مقصد) را ذخیره کنید تا در ثبت دسته‌ای بارنامه از آن‌ها استفاده کنید.
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                resetForm();
                setShowForm((v) => !v);
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-5 py-2.5 text-sm font-black transition-all active:scale-95"
            >
              {showForm ? <XMarkIcon className="h-4 w-4" /> : <PlusIcon className="h-4 w-4" />}
              {showForm ? 'بستن فرم' : 'مسیر جدید'}
            </button>
          </div>

          {showForm && (
            <form onSubmit={handleSubmit} className="mb-8 rounded-3xl bg-slate-950/60 border border-white/10 p-6 shadow-panel-lg backdrop-blur-xl space-y-5">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">نام مسیر *</label>
                <input
                  className="field"
                  placeholder="مثال: تهران → اصفهان"
                  value={form.name}
                  onChange={(e) => setField('name', e.target.value)}
                />
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-2xl bg-white/5 border border-white/10 p-4 space-y-3">
                  <p className="text-sm font-black text-cyan-300">مبدأ</p>
                  <ProvinceCitySelect
                    provinceValue={form.origin_province}
                    cityValue={form.origin_city}
                    onProvinceChange={(p) => setField('origin_province', p)}
                    onCityChange={(c, coords) => {
                      setField('origin_city', c);
                      if (coords) {
                        setOriginCoords(coords);
                        setField('origin_lat', String(coords.lat));
                        setField('origin_lng', String(coords.lng));
                      }
                    }}
                  />
                  <input
                    className="field"
                    placeholder="آدرس مبدأ (اختیاری)"
                    value={form.origin_address}
                    onChange={(e) => setField('origin_address', e.target.value)}
                  />
                </div>

                <div className="rounded-2xl bg-white/5 border border-white/10 p-4 space-y-3">
                  <p className="text-sm font-black text-cyan-300">مقصد</p>
                  <ProvinceCitySelect
                    provinceValue={form.dest_province}
                    cityValue={form.dest_city}
                    onProvinceChange={(p) => setField('dest_province', p)}
                    onCityChange={(c, coords) => {
                      setField('dest_city', c);
                      if (coords) {
                        setDestCoords(coords);
                        setField('dest_lat', String(coords.lat));
                        setField('dest_lng', String(coords.lng));
                      }
                    }}
                  />
                  <input
                    className="field"
                    placeholder="آدرس مقصد (اختیاری)"
                    value={form.dest_address}
                    onChange={(e) => setField('dest_address', e.target.value)}
                  />
                </div>
              </div>

              <RouteDistanceBadge originCoords={originCoords} destinationCoords={destCoords} />

              <label className="flex items-center gap-3 text-sm font-bold text-slate-200">
                <input
                  type="checkbox"
                  checked={form.is_favorite}
                  onChange={(e) => setField('is_favorite', e.target.checked)}
                  className="h-4 w-4 accent-cyan-500"
                />
                علامت‌گذاری به‌عنوان مسیر موردعلاقه
              </label>

              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 px-6 py-3 text-sm font-black transition-all active:scale-95"
              >
                {saving ? 'در حال ذخیره…' : editingId ? 'به‌روزرسانی مسیر' : 'ذخیرهٔ مسیر'}
              </button>
            </form>
          )}

          {isLoading && <p className="py-10 text-center text-sm text-slate-400">در حال بارگذاری…</p>}

          {!isLoading && templates.length === 0 && (
            <div className="rounded-3xl bg-slate-950/40 border border-dashed border-cyan-500/30 p-10 text-center">
              <RouteIcon className="mx-auto h-10 w-10 text-slate-600" />
              <p className="mt-3 text-sm text-slate-300">هنوز مسیری ذخیره نشده است.</p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            {templates.map((t) => (
              <div key={t.id} className="rounded-2xl bg-slate-950/60 border border-white/10 p-5 backdrop-blur-xl shadow-panel">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-black text-white">{t.name || 'بدون نام'}</h3>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
                      <MapPinIcon className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                      <span className="truncate">
                        {t.origin_city || t.origin_province || '—'} → {t.dest_city || t.dest_province || '—'}
                      </span>
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleFavorite(t.id)}
                    className="shrink-0 rounded-lg p-1.5 text-amber-400 hover:bg-amber-400/10 transition"
                    title="موردعلاقه"
                  >
                    {t.is_favorite ? <StarSolidIcon className="h-5 w-5" /> : <StarIcon className="h-5 w-5" />}
                  </button>
                </div>

                {(t.distance_km != null || t.duration_min != null) && (
                  <p className="mt-2 text-[11px] font-bold text-slate-400">
                    {t.distance_km != null ? `${toPersianDigits(Number(t.distance_km).toFixed(1))} کیلومتر` : ''}
                    {t.distance_km != null && t.duration_min != null ? ' · ' : ''}
                    {t.duration_min != null ? `${toPersianDigits(Math.round(Number(t.duration_min)))} دقیقه` : ''}
                  </p>
                )}

                <p className="mt-1 text-[10px] text-slate-600">ایجاد: {formatDateTime(t.created_at)}</p>

                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => startEdit(t)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-xs font-bold text-slate-200 hover:bg-white/10 transition"
                  >
                    <PencilIcon className="h-3.5 w-3.5" />
                    ویرایش
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(t.id)}
                    disabled={deletingId === t.id}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 px-3 py-1.5 text-xs font-bold text-rose-300 hover:bg-rose-500/20 transition disabled:opacity-50"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                    حذف
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
