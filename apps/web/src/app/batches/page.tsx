'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CubeIcon, TruckIcon, PlayIcon, CheckCircleIcon, ExclamationCircleIcon, MapPinIcon } from '@heroicons/react/24/outline';
import { Route as RouteIcon } from 'lucide-react';
import { toast } from 'react-hot-toast';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProgressBar } from '@/components/ProgressBar';
import { api, createBatch, generateIdempotencyKey } from '@/lib/api';
import { formatDateTime, toPersianDigits } from '@/lib/format';
import { useSession } from '@/hooks/useSession';
import type { BatchProgressResponse, Driver, WaybillRouteTemplate } from '@/lib/types';

const REPEAT_MODES: Array<{ value: 'round_robin' | 'random' | 'sequential'; label: string }> = [
  { value: 'round_robin', label: 'چرخشی (Round-robin)' },
  { value: 'sequential', label: 'ترتیبی (Sequential)' },
  { value: 'random', label: 'تصادفی (Random)' },
];

interface RecentBatch {
  id: number;
  name: string | null;
  created_at: string;
}

const RECENT_KEY = 'barpro_recent_batches';

function loadRecent(): RecentBatch[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as RecentBatch[]) : [];
  } catch {
    return [];
  }
}

function saveRecent(batches: RecentBatch[]) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(batches.slice(0, 20)));
  } catch {
    // ignore
  }
}

export default function BatchesPage() {
  const { role } = useSession();

  // ── form state ──
  const [driverId, setDriverId] = useState<number | null>(null);
  const [selectedRoutes, setSelectedRoutes] = useState<number[]>([]);
  const [targetCount, setTargetCount] = useState(15);
  const [repeatMode, setRepeatMode] = useState<'round_robin' | 'random' | 'sequential'>('round_robin');
  const [intervalMinutes, setIntervalMinutes] = useState(40);
  const [senderName, setSenderName] = useState('');
  const [receiverName, setReceiverName] = useState('');
  const [cargoType, setCargoType] = useState('');
  const [cargoPackaging, setCargoPackaging] = useState('');
  const [cargoWeight, setCargoWeight] = useState('');
  const [cargoValue, setCargoValue] = useState('');
  const [batchName, setBatchName] = useState('');
  const [saving, setSaving] = useState(false);
  const pendingKeyRef = useRef<string | null>(null);

  // ── result/progress state ──
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [progress, setProgress] = useState<BatchProgressResponse | null>(null);
  const [recent, setRecent] = useState<RecentBatch[]>([]);

  useEffect(() => {
    setRecent(loadRecent());
  }, []);

  const { data: drivers = [] } = useQuery({
    queryKey: ['drivers'],
    queryFn: async () => {
      const res = await api.get<Driver[]>('/api/v1/drivers?page_size=1000');
      return res.success && Array.isArray(res.data) ? res.data : [];
    },
    staleTime: 120000,
    enabled: role === 'client' || role === 'master_admin',
  });

  const { data: templates = [] } = useQuery({
    queryKey: ['route-templates'],
    queryFn: async () => {
      const res = await api.get<WaybillRouteTemplate[]>('/api/v1/route-templates');
      return res.success && Array.isArray(res.data) ? res.data : [];
    },
    staleTime: 30000,
    enabled: role === 'client' || role === 'master_admin',
  });

  // Poll progress while a batch is active.
  useEffect(() => {
    if (!activeBatchId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function poll() {
      const res = await api.get<BatchProgressResponse>(`/api/v1/batches/${activeBatchId}/progress`);
      if (cancelled) return;
      if (res.success && res.data) {
        setProgress(res.data);
        // Stop polling once every job has settled (no further progress possible).
        if (res.data.target > 0 && res.data.completed + res.data.failed >= res.data.target && timer) {
          clearInterval(timer);
        }
      }
    }

    poll();
    timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [activeBatchId]);

  const selectedDriver = drivers.find((d) => d.id === driverId) || null;

  function toggleRoute(id: number) {
    setSelectedRoutes((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!selectedDriver) {
      toast.error('انتخاب راننده الزامی است');
      return;
    }
    if (selectedRoutes.length === 0) {
      toast.error('حداقل یک مسیر را انتخاب کنید');
      return;
    }
    if (senderName.trim().split(/\s+/).length < 2) {
      toast.error('نام و نام خانوادگی فرستنده (دو کلمه) الزامی است');
      return;
    }
    if (receiverName.trim().split(/\s+/).length < 2) {
      toast.error('نام و نام خانوادگی گیرنده (دو کلمه) الزامی است');
      return;
    }
    if (!cargoType.trim() || !cargoPackaging.trim() || !cargoValue.trim()) {
      toast.error('نوع، بسته‌بندی و ارزش کالا الزامی است');
      return;
    }
    const weight = Number(cargoWeight);
    if (!Number.isFinite(weight) || weight <= 0) {
      toast.error('وزن کالا باید عددی بزرگ‌تر از صفر باشد');
      return;
    }

    const basePayload: Record<string, unknown> = {
      sender: { name: senderName.trim() },
      receiver: { name: receiverName.trim() },
      cargo: {
        type: cargoType.trim(),
        packaging: cargoPackaging.trim(),
        weight,
        value: cargoValue.trim(),
      },
      vehicle: {
        driver_national_code: selectedDriver.driver_national_code,
        // plate/type intentionally omitted: the backend enriches them from the
        // authoritative DriverPlate record (status=='active') to avoid divergence
        // with the denormalized active_plate hint.
      },
    };

    setSaving(true);
    // Reuse the same idempotency key across retries of the same logical batch so a
    // network timeout + resubmit does not create a duplicate batch. Cleared on success.
    const idemKey = pendingKeyRef.current || generateIdempotencyKey();
    pendingKeyRef.current = idemKey;
    const res = await createBatch(
      {
        driver_id: selectedDriver.id,
        name: batchName.trim() || undefined,
        route_template_ids: selectedRoutes,
        base_payload_json: basePayload,
        target_count: targetCount,
        repeat_mode: repeatMode,
        interval_minutes: intervalMinutes,
        priority: 5,
      },
      idemKey
    );
    setSaving(false);

    if (!res.success || !res.data) {
      toast.error(res.error || 'ایجاد دسته ناموفق بود');
      return;
    }

    pendingKeyRef.current = null;
    setBatchName('');
    const batch = res.data;
    toast.success(`دستهٔ #${batch.id} با ${batch.target_count} بارنامه ایجاد شد`);
    setActiveBatchId(batch.id);
    const entry: RecentBatch = { id: batch.id, name: batch.name || null, created_at: batch.created_at };
    const next = [entry, ...recent.filter((r) => r.id !== batch.id)];
    setRecent(next);
    saveRecent(next);
  }

  const completedPercent = progress && progress.target > 0 ? progress.progress_percent : 0;

  return (
    <AuthGuard>
      <AppShell>
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
          <div className="mb-8">
            <h1 className="text-2xl font-black text-white">ثبت دسته‌ای بارنامه</h1>
            <p className="mt-1 text-sm text-slate-400">
              چند مسیر ذخیره‌شده را به تعداد دلخواه گسترش دهید؛ سیستم بارنامه‌ها را با فاصلهٔ زمانی مشخص ثبت می‌کند.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="mb-8 space-y-6 rounded-3xl bg-slate-950/60 border border-white/10 p-6 shadow-panel-lg backdrop-blur-xl">
            <div>
              <label className="mb-1.5 block text-xs font-bold text-slate-300">نام دسته (اختیاری)</label>
              <input className="field" placeholder="مثال: ارسال هفتگی تهران" value={batchName} onChange={(e) => setBatchName(e.target.value)} />
            </div>

            {/* driver */}
            <div>
              <label className="mb-1.5 flex items-center gap-2 text-xs font-bold text-slate-300">
                <TruckIcon className="h-4 w-4 text-cyan-400" /> راننده *
              </label>
              <select
                className="field"
                value={driverId ?? ''}
                onChange={(e) => setDriverId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— انتخاب راننده —</option>
                {drivers.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.full_name} — {d.driver_national_code}
                  </option>
                ))}
              </select>
              {selectedDriver && selectedDriver.active_plate && (
                <p className="mt-1 text-[11px] text-slate-400">پلاک متصل: {selectedDriver.active_plate}</p>
              )}
            </div>

            {/* routes */}
            <div>
              <label className="mb-2 flex items-center gap-2 text-xs font-bold text-slate-300">
                <RouteIcon className="h-4 w-4 text-cyan-400" /> مسیرها * (انتخاب چندگانه)
              </label>
              {templates.length === 0 ? (
                <p className="rounded-xl bg-slate-950/40 border border-dashed border-white/10 p-4 text-xs text-slate-400">
                  هنوز مسیری ذخیره نشده است. ابتدا از صفحهٔ «قالب‌های مسیر» مسیر بسازید.
                </p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {templates.map((t) => {
                    const checked = selectedRoutes.includes(t.id);
                    return (
                      <label
                        key={t.id}
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${
                          checked ? 'border-cyan-500/50 bg-cyan-500/10' : 'border-white/10 bg-white/5 hover:border-white/20'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleRoute(t.id)}
                          className="mt-0.5 h-4 w-4 accent-cyan-500"
                        />
                        <span className="min-w-0">
                          <span className="block truncate text-xs font-black text-slate-200">{t.name || 'بدون نام'}</span>
                          <span className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-400">
                            <MapPinIcon className="h-3 w-3" />
                            {t.origin_city || t.origin_province || '—'} → {t.dest_city || t.dest_province || '—'}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {/* base payload */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">نام و نام خانوادگی فرستنده *</label>
                <input className="field" placeholder="مثال: علی رضایی" value={senderName} onChange={(e) => setSenderName(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">نام و نام خانوادگی گیرنده *</label>
                <input className="field" placeholder="مثال: محمد احمدی" value={receiverName} onChange={(e) => setReceiverName(e.target.value)} />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">نوع کالا *</label>
                <input className="field" placeholder="مثال: سیمان" value={cargoType} onChange={(e) => setCargoType(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">نوع بسته‌بندی *</label>
                <input className="field" placeholder="مثال: کیسه" value={cargoPackaging} onChange={(e) => setCargoPackaging(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">وزن (تن) *</label>
                <input className="field" inputMode="decimal" placeholder="مثال: 20" value={cargoWeight} onChange={(e) => setCargoWeight(e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">ارزش بار (تومان) *</label>
                <input className="field" inputMode="numeric" placeholder="مثال: 50000000" value={cargoValue} onChange={(e) => setCargoValue(e.target.value)} />
              </div>
            </div>

            {/* batch options */}
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">تعداد بارنامه</label>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  className="field"
                  value={targetCount}
                  onChange={(e) => setTargetCount(Number(e.target.value) || 1)}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">الگوی توزیع مسیر</label>
                <select className="field" value={repeatMode} onChange={(e) => setRepeatMode(e.target.value as typeof repeatMode)}>
                  {REPEAT_MODES.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">فاصلهٔ زمانی (دقیقه)</label>
                <input
                  type="number"
                  min={0}
                  max={1440}
                  className="field"
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(Number(e.target.value) || 0)}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 px-6 py-3 text-sm font-black transition-all active:scale-95"
            >
              <PlayIcon className="h-4 w-4" />
              {saving ? 'در حال ایجاد…' : 'ایجاد دستهٔ بارنامه'}
            </button>
          </form>

          {/* progress panel */}
          {activeBatchId && (
            <div className="rounded-3xl bg-slate-950/60 border border-white/10 p-6 shadow-panel-lg backdrop-blur-xl">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-black text-white">
                  <CubeIcon className="h-5 w-5 text-cyan-400" />
                  پیشرفت دستهٔ #{activeBatchId}
                </h2>
                {progress && (
                  <span className="rounded-lg bg-cyan-500/10 border border-cyan-500/20 px-3 py-1 text-xs font-black text-cyan-300">
                    {toPersianDigits(progress.completed)} / {toPersianDigits(progress.target)}
                  </span>
                )}
              </div>

              <div className="mt-4 h-3 w-full overflow-hidden rounded-full bg-white/10">
                <ProgressBar
                  value={completedPercent}
                  max={100}
                  segments={40}
                  tone="cyan"
                  size="md"
                  label="پیشرفت دستهٔ بارنامه"
                  className="h-full border-0 bg-transparent p-0"
                />
              </div>

              {progress && (
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-xl bg-white/5 border border-white/10 p-3 text-center">
                    <p className="text-[10px] font-bold text-slate-400">موفق</p>
                    <p className="mt-1 flex items-center justify-center gap-1 text-sm font-black text-emerald-400">
                      <CheckCircleIcon className="h-4 w-4" /> {toPersianDigits(progress.completed)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-white/5 border border-white/10 p-3 text-center">
                    <p className="text-[10px] font-bold text-slate-400">ناموفق</p>
                    <p className="mt-1 flex items-center justify-center gap-1 text-sm font-black text-rose-400">
                      <ExclamationCircleIcon className="h-4 w-4" /> {toPersianDigits(progress.failed)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-white/5 border border-white/10 p-3 text-center">
                    <p className="text-[10px] font-bold text-slate-400">امروز</p>
                    <p className="mt-1 text-sm font-black text-slate-200">{toPersianDigits(progress.today)}</p>
                  </div>
                  <div className="rounded-xl bg-white/5 border border-white/10 p-3 text-center">
                    <p className="text-[10px] font-bold text-slate-400">درصد</p>
                    <p className="mt-1 text-sm font-black text-cyan-300">{toPersianDigits(progress.progress_percent)}٪</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* recent batches (local) */}
          {recent.length > 0 && (
            <div className="mt-6">
              <h3 className="mb-2 text-xs font-bold text-slate-400">دسته‌های اخیر (این مرورگر)</h3>
              <div className="flex flex-wrap gap-2">
                {recent.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => setActiveBatchId(b.id)}
                    className={`rounded-xl border px-4 py-2 text-xs font-bold transition ${
                      activeBatchId === b.id
                        ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300'
                        : 'border-white/10 bg-white/5 text-slate-300 hover:border-white/20'
                    }`}
                  >
                    #{b.id} {b.name ? `— ${b.name}` : ''}
                    <span className="mr-1 text-[10px] text-slate-500">{formatDateTime(b.created_at)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </AppShell>
    </AuthGuard>
  );
}
