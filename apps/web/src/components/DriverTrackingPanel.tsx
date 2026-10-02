'use client';

import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';

import { api } from '@/lib/api';
import { toPersianDigits } from '@/lib/format';
import type {
  DriverTrackingItem,
  DriverTrackingResponse,
  PlateUpdateRequest,
} from '@/lib/types';

/** Days left until the period ends; backend sends naive UTC, so parse as UTC. */
function remainingDaysLabel(endAt: string): string | null {
  const end = new Date(endAt.endsWith('Z') ? endAt : `${endAt}Z`);
  const ms = end.getTime() - Date.now();
  if (!Number.isFinite(ms) || ms <= 0) return null;
  return `${toPersianDigits(Math.ceil(ms / 86400000))} روز مانده به پایان دوره`;
}

function Toggle({
  label,
  checked,
  onToggle,
  disabled,
  onLabel,
  offLabel,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
  disabled?: boolean;
  onLabel: string;
  offLabel: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={checked}
      className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold transition touch-target disabled:opacity-50 ${
        checked
          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
          : 'border-white/10 bg-slate-950 text-slate-400 hover:text-slate-200'
      }`}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${checked ? 'bg-emerald-400' : 'bg-slate-600'}`}
      />
      {label}: {checked ? onLabel : offLabel}
    </button>
  );
}

function TrackingCard({
  item,
  onUpdate,
  saving,
}: {
  item: DriverTrackingItem;
  onUpdate: (plateId: number, patch: PlateUpdateRequest) => Promise<void>;
  saving: boolean;
}) {
  const target = item.target_count ?? 0;
  const [targetDraft, setTargetDraft] = useState<string>(String(target));
  // Keep the draft in sync when the server-side target changes (save +
  // refetch); while typing, no refetch is in flight so the draft is safe.
  useEffect(() => {
    setTargetDraft(String(item.target_count ?? 0));
  }, [item.target_count]);
  const progress = target > 0 ? Math.min(100, Math.round((item.period_total / target) * 100)) : 0;

  const stats = [
    { label: 'ثبت امروز', value: item.today_count, tone: 'text-cyan-300' },
    { label: 'تعداد هدف ثبت', value: target, tone: 'text-amber-300' },
    { label: 'کل ثبت', value: item.period_total, tone: 'text-emerald-300' },
  ];

  return (
    <div className="rounded-2xl border border-white/5 bg-slate-950/80 p-4 sm:p-5 transition hover:border-cyan-500/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-base font-black text-cyan-400">{item.plate_number}</span>
          <span className="text-xs text-slate-400">
            راننده: {item.driver_name || `#${toPersianDigits(item.driver_id)}`}
          </span>
          {item.vehicle_type && <span className="text-xs text-slate-500">| {item.vehicle_type}</span>}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-xl border border-white/5 bg-slate-900/60 px-2 py-3 text-center"
          >
            <div className={`text-xl font-black ${stat.tone}`}>{toPersianDigits(stat.value)}</div>
            <div className="mt-1 text-[11px] font-bold text-slate-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {target > 0 && (
        <div className="mt-3">
          <div className="h-2 overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full rounded-full transition-all ${progress >= 100 ? 'bg-emerald-400' : 'bg-cyan-400'}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {toPersianDigits(progress)}٪ از هدف دوره
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/5 pt-4">
        <Toggle
          label="وضعیت"
          checked={item.status === 'active'}
          onToggle={() =>
            onUpdate(item.plate_id, { status: item.status === 'active' ? 'inactive' : 'active' })
          }
          disabled={saving}
          onLabel="فعال"
          offLabel="غیرفعال"
        />
        <Toggle
          label="رفت و برگشت"
          checked={item.round_trip}
          onToggle={() => onUpdate(item.plate_id, { round_trip: !item.round_trip })}
          disabled={saving}
          onLabel="روشن"
          offLabel="خاموش"
        />
        <Toggle
          label="حمل"
          checked={item.in_transport}
          onToggle={() => onUpdate(item.plate_id, { in_transport: !item.in_transport })}
          disabled={saving}
          onLabel="روشن"
          offLabel="خاموش"
        />
      </div>

      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = Number(targetDraft);
          if (!Number.isFinite(parsed) || parsed < 0) {
            toast.error('تعداد هدف باید عددی نامنفی باشد');
            return;
          }
          void onUpdate(item.plate_id, { target_count: Math.floor(parsed) });
        }}
      >
        <label className="text-xs font-bold text-slate-400">تعداد هدف ثبت (دوره):</label>
        <div className="w-24 shrink-0">
          <input
            type="number"
            min={0}
            value={targetDraft}
            onChange={(event) => setTargetDraft(event.target.value)}
            disabled={saving}
            className="field !py-2 text-center"
            dir="ltr"
            aria-label="تعداد هدف ثبت دوره"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-cyan-500/15 border border-cyan-500/25 px-3 py-2 text-xs font-bold text-cyan-300 hover:bg-cyan-500 hover:text-slate-950 transition disabled:opacity-50"
        >
          ذخیره هدف
        </button>
      </form>
    </div>
  );
}

export function DriverTrackingPanel({ role }: { role: string | null }) {
  const queryClient = useQueryClient();
  const [savingId, setSavingId] = useState<number | null>(null);

  const {
    data: tracking,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['driver-tracking'],
    queryFn: async () => {
      const res = await api.get<DriverTrackingResponse>('/api/v1/driver-tracking');
      if (!res.success || !res.data) {
        throw new Error(res.error || 'خطا در دریافت اطلاعات پیگیری');
      }
      return res.data;
    },
    staleTime: 60000,
    enabled: role === 'client' || role === 'master_admin',
  });

  const handleUpdate = async (plateId: number, patch: PlateUpdateRequest) => {
    setSavingId(plateId);
    try {
      const res = await api.put(`/api/v1/plates/${plateId}`, patch);
      if (!res.success) {
        throw new Error(res.error || 'خطا در ذخیره‌سازی');
      }
      toast.success('ذخیره شد');
      await queryClient.invalidateQueries({ queryKey: ['driver-tracking'] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'خطا در ذخیره‌سازی');
    } finally {
      setSavingId(null);
    }
  };

  return (
    <section className="relative overflow-hidden rounded-[2rem] border border-white/5 bg-slate-900/50 backdrop-blur-xl p-6 sm:p-8 shadow-2xl text-white">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-black text-white">پیگیری راننده‌ها</h2>
        <button
          type="button"
          onClick={() => void refetch()}
          className="rounded-xl border border-white/10 bg-slate-950 px-4 py-2 text-xs font-bold text-slate-300 hover:text-white transition"
        >
          به‌روزرسانی
        </button>
      </div>

      {isLoading ? (
        <div className="mt-4 grid gap-4" aria-label="در حال بارگذاری">
          {[1, 2].map((item) => (
            <div key={item} className="h-48 skeleton rounded-2xl" />
          ))}
        </div>
      ) : isError || !tracking ? (
        <p className="mt-6 text-sm text-rose-400">خطا در دریافت اطلاعات پیگیری. دوباره تلاش کنید.</p>
      ) : (
        <>
          <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-black text-cyan-300">{tracking.period.label}</div>
              {(() => {
                const remaining = remainingDaysLabel(tracking.period.end_at);
                return remaining ? (
                  <div className="text-xs font-bold text-slate-400">{remaining}</div>
                ) : null;
              })()}
            </div>
            <div className="mt-1 text-xs text-slate-400">
              کل ثبت در پایان هر دوره ۱۵ روزه به‌صورت خودکار صفر می‌شود.
            </div>
          </div>

          {tracking.items.length === 0 ? (
            <p className="mt-6 text-xs text-slate-500 italic py-2">هیچ پلاکی ثبت نشده است.</p>
          ) : (
            <div className="mt-4 grid gap-4">
              {tracking.items.map((item) => (
                <TrackingCard
                  key={item.plate_id}
                  item={item}
                  onUpdate={handleUpdate}
                  saving={savingId === item.plate_id}
                />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
