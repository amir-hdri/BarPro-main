'use client';

import { sessionQueryKey } from '@/lib/session-query';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  CubeIcon,
  TruckIcon,
  PlayIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  MapPinIcon,
  ArrowPathIcon,
  ArrowsRightLeftIcon,
  ClockIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import { Route as RouteIcon } from 'lucide-react';
import { toast } from 'react-hot-toast';

import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/layout/AuthGuard';
import { ProgressBar } from '@/components/ProgressBar';
import { api, createBatch, generateIdempotencyKey } from '@/lib/api';
import { formatDateTime, toPersianDigits } from '@/lib/format';
import { normalizeDigits } from '@/lib/plate';
import { isValidIranNationalCode } from '@/schemas/waybillSchema';
import { useSession } from '@/hooks/useSession';
import type { BatchProgressResponse, Driver, WaybillRouteTemplate } from '@/lib/types';

function estimateRouteDurationMinutes(route: WaybillRouteTemplate): number {
  const dur = Number(route.duration_min || 0);
  if (dur > 0) return dur;
  const dist = Number(route.distance_km || 0);
  if (dist <= 0) return 60;
  const isUrban = Boolean(route.origin_city && route.dest_city && route.origin_city.trim() === route.dest_city.trim());
  const speed = isUrban ? 28.0 : 60.0;
  return Math.max(1, Math.round((dist / speed) * 60));
}

function formatMinutes(min: number): string {
  if (min <= 0) return '0 دقیقه';
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (h === 0) return `${m} دقیقه`;
  if (m === 0) return `${h} ساعت`;
  return `${h} ساعت و ${m} دقیقه`;
}

function formatOffset(min: number): string {
  if (min === 0) return 'شروع اولیه (دقیقه 0)';
  return `+${Math.round(min)} دقیقه (${formatMinutes(min)})`;
}

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

function normalizeMobile(value: string): string {
  return normalizeDigits(value).replace(/\D/g, '').slice(0, 11);
}

function normalizeCode(value: string): string {
  return normalizeDigits(value).replace(/\D/g, '').slice(0, 10);
}

function normalizePositiveNumber(value: string): number {
  const normalized = normalizeDigits(value).replace(/[,٬]/g, '').trim();
  return Number(normalized);
}

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
  const { role, client } = useSession();

  // ── form state ──
  const [driverId, setDriverId] = useState<number | null>(null);
  const [selectedRoutes, setSelectedRoutes] = useState<number[]>([]);
  const [targetCount, setTargetCount] = useState(15);
  const [repeatMode, setRepeatMode] = useState<'round_robin' | 'random' | 'sequential'>('round_robin');
  const [batchMode, setBatchMode] = useState<'standard' | 'round_trip_cycling' | 'one_way_repeated'>('standard');
  const [cyclesCount, setCyclesCount] = useState<number>(5);
  const [repeatCount, setRepeatCount] = useState<number>(5);
  const [bufferMinutes, setBufferMinutes] = useState<number>(45);
  const [smartInversion, setSmartInversion] = useState<boolean>(true);
  const [routeChain, setRouteChain] = useState(true);
  const [intervalMinutes, setIntervalMinutes] = useState(40);

  const [senderName, setSenderName] = useState('');
  const [senderPhone, setSenderPhone] = useState('');
  const [receiverName, setReceiverName] = useState('');
  const [receiverPhone, setReceiverPhone] = useState('');
  const [senderNationalCode, setSenderNationalCode] = useState('');
  const [senderPostalCode, setSenderPostalCode] = useState('');
  const [receiverNationalCode, setReceiverNationalCode] = useState('');
  const [receiverPostalCode, setReceiverPostalCode] = useState('');
  const [originPostalCode, setOriginPostalCode] = useState('');
  const [destinationPostalCode, setDestinationPostalCode] = useState('');
  const [fare, setFare] = useState('');
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
    queryKey: sessionQueryKey(client, 'drivers'),
    queryFn: async ({ signal }) => {
      const res = await api.get<Driver[]>('/api/v1/drivers?page_size=1000', undefined, { signal });
      return res.success && Array.isArray(res.data) ? res.data : [];
    },
    staleTime: 120000,
    enabled: role === 'client' || role === 'master_admin',
  });

  const { data: templates = [] } = useQuery({
    queryKey: sessionQueryKey(client, 'route-templates'),
    queryFn: async ({ signal }) => {
      const res = await api.get<WaybillRouteTemplate[]>('/api/v1/route-templates', undefined, { signal });
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
    const controller = new AbortController();

    async function poll() {
      const res = await api.get<BatchProgressResponse>(`/api/v1/batches/${activeBatchId}/progress`, undefined, {
        signal: controller.signal,
      });
      if (cancelled || controller.signal.aborted) return;
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
      controller.abort();
      if (timer) clearInterval(timer);
    };
  }, [activeBatchId]);

  const selectedDriver = drivers.find((d) => d.id === driverId) || null;

  useEffect(() => {
    if (batchMode === 'standard' && routeChain && selectedRoutes.length > 0) {
      setTargetCount(selectedRoutes.length);
      setRepeatMode('sequential');
    }
  }, [batchMode, routeChain, selectedRoutes.length]);

  function toggleRoute(id: number) {
    setSelectedRoutes((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const selectedRouteTemplates = useMemo(() => {
    return selectedRoutes
      .map((id) => templates.find((t) => t.id === id))
      .filter((t): t is WaybillRouteTemplate => Boolean(t));
  }, [selectedRoutes, templates]);

  interface ScheduleLeg {
    index: number;
    legType: 'forward' | 'return' | 'standard';
    cycleLabel: string;
    origin: string;
    destination: string;
    distanceKm: number;
    durationMinutes: number;
    depMinutesFromStart: number;
    arrMinutesFromStart: number;
    bufferMinutes: number;
    smartInverted: boolean;
  }

  const schedulePreview = useMemo(() => {
    if (selectedRouteTemplates.length === 0) return [];

    const legs: ScheduleLeg[] = [];

    if (batchMode === 'round_trip_cycling') {
      const cycles = Math.max(1, cyclesCount || 1);
      const buffer = Math.max(0, bufferMinutes || 0);
      let currentMinutes = 0;
      let legCounter = 1;

      for (let c = 1; c <= cycles; c++) {
        for (const route of selectedRouteTemplates) {
          const dur = estimateRouteDurationMinutes(route);
          const dist = Number(route.distance_km || 0);

          // Forward leg
          legs.push({
            index: legCounter++,
            legType: 'forward',
            cycleLabel: `چرخه ${c} (رفت)`,
            origin: `${route.origin_city || route.origin_province || 'مبدأ'}`,
            destination: `${route.dest_city || route.dest_province || 'مقصد'}`,
            distanceKm: dist,
            durationMinutes: dur,
            depMinutesFromStart: currentMinutes,
            arrMinutesFromStart: currentMinutes + dur,
            bufferMinutes: buffer,
            smartInverted: false,
          });
          currentMinutes += dur + buffer;

          // Return leg
          legs.push({
            index: legCounter++,
            legType: 'return',
            cycleLabel: `چرخه ${c} (برگشت)`,
            origin: `${route.dest_city || route.dest_province || 'مقصد'}`,
            destination: `${route.origin_city || route.origin_province || 'مبدأ'}`,
            distanceKm: dist,
            durationMinutes: dur,
            depMinutesFromStart: currentMinutes,
            arrMinutesFromStart: currentMinutes + dur,
            bufferMinutes: buffer,
            smartInverted: smartInversion,
          });
          currentMinutes += dur + buffer;
        }
      }
    } else if (batchMode === 'one_way_repeated') {
      const repeats = Math.max(1, repeatCount || 1);
      const buffer = Math.max(0, bufferMinutes || 0);
      let currentMinutes = 0;
      let legCounter = 1;

      for (let r = 1; r <= repeats; r++) {
        for (const route of selectedRouteTemplates) {
          const dur = estimateRouteDurationMinutes(route);
          const dist = Number(route.distance_km || 0);

          legs.push({
            index: legCounter++,
            legType: 'forward',
            cycleLabel: `تکرار ${r}`,
            origin: `${route.origin_city || route.origin_province || 'مبدأ'}`,
            destination: `${route.dest_city || route.dest_province || 'مقصد'}`,
            distanceKm: dist,
            durationMinutes: dur,
            depMinutesFromStart: currentMinutes,
            arrMinutesFromStart: currentMinutes + dur,
            bufferMinutes: buffer,
            smartInverted: false,
          });
          // Spacing: forward dur + buffer + empty return dur + buffer
          currentMinutes += dur * 2 + buffer * 2;
        }
      }
    } else {
      const count = Math.max(1, targetCount || 1);
      const isChain = routeChain;
      let currentMinutes = 0;

      for (let i = 0; i < count; i++) {
        const route = selectedRouteTemplates[i % selectedRouteTemplates.length];
        const dur = estimateRouteDurationMinutes(route);
        const dist = Number(route.distance_km || 0);

        legs.push({
          index: i + 1,
          legType: 'standard',
          cycleLabel: `بارنامه ${i + 1}`,
          origin: `${route.origin_city || route.origin_province || 'مبدأ'}`,
          destination: `${route.dest_city || route.dest_province || 'مقصد'}`,
          distanceKm: dist,
          durationMinutes: dur,
          depMinutesFromStart: currentMinutes,
          arrMinutesFromStart: currentMinutes + dur,
          bufferMinutes: intervalMinutes,
          smartInverted: false,
        });

        if (isChain) {
          currentMinutes += dur + intervalMinutes;
        } else {
          currentMinutes += intervalMinutes;
        }
      }
    }

    return legs;
  }, [
    selectedRouteTemplates,
    batchMode,
    cyclesCount,
    repeatCount,
    bufferMinutes,
    smartInversion,
    targetCount,
    routeChain,
    intervalMinutes,
  ]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!selectedDriver) {
      toast.error('انتخاب راننده الزامی است');
      return;
    }
    if (selectedDriver.status && selectedDriver.status.toLowerCase() !== 'active') {
      toast.error('رانندهٔ انتخاب‌شده فعال نیست');
      return;
    }
    if (selectedRoutes.length === 0) {
      toast.error('حداقل یک مسیر را انتخاب کنید');
      return;
    }
    if (batchMode === 'round_trip_cycling' && (cyclesCount < 1 || cyclesCount > 100)) {
      toast.error('تعداد دور کامل (چرخه) باید عددی بین 1 تا 100 باشد');
      return;
    }
    if (batchMode === 'one_way_repeated' && (repeatCount < 1 || repeatCount > 100)) {
      toast.error('تعداد دفعات تکرار مسیر رفت باید عددی بین 1 تا 100 باشد');
      return;
    }
    if (batchMode === 'standard' && routeChain && targetCount !== selectedRoutes.length) {
      toast.error('در حالت زنجیره‌ای، تعداد بارنامه باید برابر تعداد مسیرها باشد');
      return;
    }
    if (batchMode !== 'standard' || routeChain) {
      const routesWithoutTiming = selectedRoutes
        .map((id) => templates.find((route) => route.id === id))
        .filter((route): route is WaybillRouteTemplate => Boolean(route))
        .filter((route) => !(Number(route.duration_min || 0) > 0 || Number(route.distance_km || 0) > 0));
      if (routesWithoutTiming.length > 0) {
        toast.error('برای هر مسیر در حالت زمان‌بندی هوشمند، فاصله یا زمان تخمینی معتبر لازم است');
        return;
      }
    }
    if (senderName.trim().split(/\s+/).length < 2) {
      toast.error('نام و نام خانوادگی فرستنده (دو کلمه) الزامی است');
      return;
    }
    if (receiverName.trim().split(/\s+/).length < 2) {
      toast.error('نام و نام خانوادگی گیرنده (دو کلمه) الزامی است');
      return;
    }
    const normalizedSenderPhone = normalizeMobile(senderPhone);
    const normalizedReceiverPhone = normalizeMobile(receiverPhone);
    if (!/^09\d{9}$/.test(normalizedSenderPhone)) {
      toast.error('موبایل فرستنده باید ۱۱ رقم و با ۰۹ شروع شود');
      return;
    }
    if (!/^09\d{9}$/.test(normalizedReceiverPhone)) {
      toast.error('موبایل گیرنده باید ۱۱ رقم و با ۰۹ شروع شود');
      return;
    }
    // Mobile-transport mandatory fields (parity with the single-waybill form):
    // the backend create_batch gate rejects the batch with 422 without these.
    const senderNat = normalizeCode(senderNationalCode);
    const receiverNat = normalizeCode(receiverNationalCode);
    if (!isValidIranNationalCode(senderNat)) {
      toast.error('کد ملی فرستنده باید ۱۰ رقم معتبر باشد');
      return;
    }
    if (!isValidIranNationalCode(receiverNat)) {
      toast.error('کد ملی گیرنده باید ۱۰ رقم معتبر باشد');
      return;
    }
    const senderPost = normalizeCode(senderPostalCode);
    const receiverPost = normalizeCode(receiverPostalCode);
    const originPost = normalizeCode(originPostalCode);
    const destinationPost = normalizeCode(destinationPostalCode);
    if (!/^\d{10}$/.test(senderPost)) {
      toast.error('کدپستی فرستنده باید دقیقاً ۱۰ رقم باشد');
      return;
    }
    if (!/^\d{10}$/.test(receiverPost)) {
      toast.error('کدپستی گیرنده باید دقیقاً ۱۰ رقم باشد');
      return;
    }
    if (!/^\d{10}$/.test(originPost)) {
      toast.error('کدپستی مبدا باید دقیقاً ۱۰ رقم باشد');
      return;
    }
    if (!/^\d{10}$/.test(destinationPost)) {
      toast.error('کدپستی مقصد باید دقیقاً ۱۰ رقم باشد');
      return;
    }
    const fareNumber = normalizePositiveNumber(fare);
    if (!Number.isFinite(fareNumber) || fareNumber <= 0) {
      toast.error('کرایه باید عددی بزرگ‌تر از صفر و به ریال باشد');
      return;
    }
    const normalizedDriverPhone = normalizeMobile(selectedDriver.phone || '');
    if (normalizedDriverPhone && (normalizedSenderPhone === normalizedDriverPhone || normalizedReceiverPhone === normalizedDriverPhone)) {
      toast.error('موبایل فرستنده و گیرنده نباید با موبایل راننده یکسان باشد');
      return;
    }
    if (cargoType.trim().length < 2 || !cargoPackaging.trim() || !cargoValue.trim()) {
      toast.error('نوع کالا، بسته‌بندی و ارزش کالا را کامل وارد کنید');
      return;
    }
    const weight = normalizePositiveNumber(cargoWeight);
    if (!Number.isFinite(weight) || weight <= 0) {
      toast.error('وزن کالا باید عددی بزرگ‌تر از صفر باشد');
      return;
    }
    const cargoValueNumber = normalizePositiveNumber(cargoValue);
    if (!Number.isFinite(cargoValueNumber) || cargoValueNumber <= 0) {
      toast.error('ارزش کالا باید عددی بزرگ‌تر از صفر و به ریال باشد');
      return;
    }

    const basePayload: Record<string, unknown> = {
      sender: {
        name: senderName.trim(),
        phone: normalizedSenderPhone,
        national_code: senderNat,
        postal_code: senderPost,
      },
      receiver: {
        name: receiverName.trim(),
        phone: normalizedReceiverPhone,
        national_code: receiverNat,
        postal_code: receiverPost,
      },
      origin: { postal_code: originPost },
      destination: { postal_code: destinationPost },
      financial: { cost: fareNumber },
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

    const calculatedTargetCount =
      batchMode === 'round_trip_cycling'
        ? (cyclesCount || 1) * 2 * selectedRoutes.length
        : batchMode === 'one_way_repeated'
          ? (repeatCount || 1) * selectedRoutes.length
          : targetCount;

    const res = await createBatch(
      {
        driver_id: selectedDriver.id,
        name: batchName.trim() || undefined,
        route_template_ids: selectedRoutes,
        base_payload_json: basePayload,
        target_count: calculatedTargetCount,
        repeat_mode: repeatMode,
        route_chain: batchMode !== 'standard' ? true : routeChain,
        interval_minutes: intervalMinutes,
        priority: 5,
        batch_mode: batchMode,
        cycles_count: batchMode === 'round_trip_cycling' ? cyclesCount : undefined,
        repeat_count: batchMode === 'one_way_repeated' ? repeatCount : undefined,
        buffer_minutes: bufferMinutes,
        smart_inversion: smartInversion,
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
              هر مسیر یک بارنامهٔ مستقل است؛ در حالت زنجیره‌ای، مسیر بعدی پس از موفقیت قبلی و زمان تخمینی آن ثبت می‌شود.
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
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">موبایل فرستنده *</label>
                <input
                  className="field"
                  inputMode="tel"
                  autoComplete="tel"
                  maxLength={11}
                  placeholder="مثال: 09123456789"
                  value={senderPhone}
                  onChange={(e) => setSenderPhone(normalizeMobile(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">موبایل گیرنده *</label>
                <input
                  className="field"
                  inputMode="tel"
                  autoComplete="tel"
                  maxLength={11}
                  placeholder="مثال: 09129876543"
                  value={receiverPhone}
                  onChange={(e) => setReceiverPhone(normalizeMobile(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کد ملی فرستنده *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={senderNationalCode}
                  onChange={(e) => setSenderNationalCode(normalizeCode(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کدپستی فرستنده *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={senderPostalCode}
                  onChange={(e) => setSenderPostalCode(normalizeCode(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کد ملی گیرنده *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={receiverNationalCode}
                  onChange={(e) => setReceiverNationalCode(normalizeCode(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کدپستی گیرنده *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={receiverPostalCode}
                  onChange={(e) => setReceiverPostalCode(normalizeCode(e.target.value))}
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کدپستی مبدا *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={originPostalCode}
                  onChange={(e) => setOriginPostalCode(normalizeCode(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کدپستی مقصد *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  maxLength={10}
                  placeholder="۱۰ رقم"
                  value={destinationPostalCode}
                  onChange={(e) => setDestinationPostalCode(normalizeCode(e.target.value))}
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-bold text-slate-300">کرایه (ریال) *</label>
                <input
                  className="field"
                  inputMode="numeric"
                  placeholder="مثال: 5000000"
                  value={fare}
                  onChange={(e) => setFare(e.target.value)}
                />
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
                <label className="mb-1.5 block text-xs font-bold text-slate-300">ارزش بار (ریال) *</label>
                <input className="field" inputMode="numeric" placeholder="مثال: 500000000" value={cargoValue} onChange={(e) => setCargoValue(e.target.value)} />
              </div>
            </div>

            {/* scenario strategy selector */}
            <div className="space-y-3">
              <label className="block text-xs font-bold text-slate-300">
                استراتژی و سناریوی ثبت بارنامه *
              </label>
              <div className="grid gap-3 sm:grid-cols-3">
                <button
                  type="button"
                  onClick={() => {
                    setBatchMode('standard');
                  }}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-right transition ${
                    batchMode === 'standard'
                      ? 'border-cyan-500 bg-cyan-500/10 shadow-lg shadow-cyan-500/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="text-xs font-black text-white">استاندارد دستی</span>
                    <RouteIcon className={`h-4 w-4 ${batchMode === 'standard' ? 'text-cyan-400' : 'text-slate-500'}`} />
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                    توزیع دلخواه بارنامه‌ها طبق الگوی انتخابی با فاصله زمانی ثابت یا زنجیره‌ای.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setBatchMode('round_trip_cycling');
                    setRouteChain(true);
                  }}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-right transition ${
                    batchMode === 'round_trip_cycling'
                      ? 'border-cyan-500 bg-cyan-500/10 shadow-lg shadow-cyan-500/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="text-xs font-black text-white">رفت و برگشت متوالی (چرخه‌ای)</span>
                    <ArrowsRightLeftIcon className={`h-4 w-4 ${batchMode === 'round_trip_cycling' ? 'text-cyan-400' : 'text-slate-500'}`} />
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                    چرخه‌های رفت و برگشت با وارون‌سازی خودکار فرستنده/گیرنده و بافر استراحت.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setBatchMode('one_way_repeated');
                    setRouteChain(true);
                  }}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-right transition ${
                    batchMode === 'one_way_repeated'
                      ? 'border-cyan-500 bg-cyan-500/10 shadow-lg shadow-cyan-500/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20'
                  }`}
                >
                  <div className="flex w-full items-center justify-between">
                    <span className="text-xs font-black text-white">فقط رفت (با بازگشت خالی)</span>
                    <ArrowPathIcon className={`h-4 w-4 ${batchMode === 'one_way_repeated' ? 'text-cyan-400' : 'text-slate-500'}`} />
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
                    تکرار ارسال‌های رفت با احتساب خودکار مدت‌زمان بازگشت ناوگان بدون بار به مبدأ.
                  </p>
                </button>
              </div>
            </div>

            {/* scenario specific options */}
            {batchMode === 'standard' ? (
              <>
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
                    <select
                      className="field disabled:cursor-not-allowed disabled:opacity-60"
                      value={repeatMode}
                      disabled={routeChain}
                      onChange={(e) => setRepeatMode(e.target.value as typeof repeatMode)}
                    >
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

                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3">
                  <input
                    type="checkbox"
                    checked={routeChain}
                    onChange={(e) => setRouteChain(e.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-cyan-500"
                  />
                  <span>
                    <span className="block text-xs font-black text-cyan-200">زنجیرهٔ مسیر برای همین راننده</span>
                    <span className="mt-1 block text-[11px] text-slate-400">
                      بارنامه‌ها هم‌زمان ارسال نمی‌شوند؛ هر leg بعد از موفقیت و زمان تقریبی leg قبل آزاد می‌شود و گیت ساعات مجاز UTCMS نیز اعمال می‌گردد.
                    </span>
                  </span>
                </label>
              </>
            ) : batchMode === 'round_trip_cycling' ? (
              <div className="space-y-4 rounded-2xl border border-cyan-500/30 bg-cyan-500/5 p-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-bold text-slate-300">
                      تعداد دور کامل (چرخه رفت و برگشت) *
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      className="field"
                      value={cyclesCount}
                      onChange={(e) => setCyclesCount(Math.max(1, Number(e.target.value) || 1))}
                    />
                    <p className="mt-1 text-[11px] text-cyan-300">
                      مجموع بارنامه‌ها: {cyclesCount * 2 * (selectedRoutes.length || 1)} فقره ({cyclesCount} رفت + {cyclesCount} برگشت)
                    </p>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-bold text-slate-300">
                      زمان بافر و استراحت راننده بین سفرها (دقیقه) *
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      className="field"
                      value={bufferMinutes}
                      onChange={(e) => setBufferMinutes(Math.max(0, Number(e.target.value) || 0))}
                    />
                    <p className="mt-1 text-[11px] text-slate-400">
                      شامل زمان استراحت طبق آیین‌نامه، تخلیه بار و بارگیری مجدد در مبدأ/مقصد.
                    </p>
                  </div>
                </div>

                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
                  <input
                    type="checkbox"
                    checked={smartInversion}
                    onChange={(e) => setSmartInversion(e.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-cyan-500"
                  />
                  <span>
                    <span className="block text-xs font-black text-slate-200">
                      وارون‌سازی هوشمند فرستنده و گیرنده (Smart Inversion)
                    </span>
                    <span className="mt-1 block text-[11px] text-slate-400">
                      در مسیر برگشت، موقعیت جغرافیایی و طرفین قرارداد جابجا می‌شوند تا کدپستی فرستنده برگشت با کدپستی مبدأ برگشت همخوانی دقیق داشته باشد و از خطای سامانه‌ای جلوگیری شود.
                    </span>
                  </span>
                </label>
              </div>
            ) : (
              <div className="space-y-4 rounded-2xl border border-cyan-500/30 bg-cyan-500/5 p-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-xs font-bold text-slate-300">
                      تعداد دفعات تکرار مسیر رفت *
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      className="field"
                      value={repeatCount}
                      onChange={(e) => setRepeatCount(Math.max(1, Number(e.target.value) || 1))}
                    />
                    <p className="mt-1 text-[11px] text-cyan-300">
                      مجموع بارنامه‌های صادره: {repeatCount * (selectedRoutes.length || 1)} فقره
                    </p>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-bold text-slate-300">
                      بافر استراحت و تخلیه در هر سفر (دقیقه) *
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      className="field"
                      value={bufferMinutes}
                      onChange={(e) => setBufferMinutes(Math.max(0, Number(e.target.value) || 0))}
                    />
                    <p className="mt-1 text-[11px] text-slate-400">
                      سیستم به طور خودکار مدت‌زمان بازگشت خالی ناوگان در جاده به اضافه ۲ بافر استراحت را قبل از صدور بارنامه بعدی لحاظ می‌کند.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* schedule preview timeline */}
            {schedulePreview.length > 0 && (
              <div className="space-y-3 rounded-2xl border border-white/10 bg-slate-950/80 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ClockIcon className="h-4 w-4 text-cyan-400" />
                    <span className="text-xs font-black text-white">
                      پیش‌نمایش جدول زمان‌بندی هوشمند ({schedulePreview.length} مرحله)
                    </span>
                  </div>
                  <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-bold text-emerald-400 border border-emerald-500/20">
                    <ShieldCheckIcon className="h-3.5 w-3.5" />
                    محافظت توقف زنجیره (Fail-Safe Chain Halt) فعال است
                  </span>
                </div>

                <div className="max-h-72 overflow-y-auto rounded-xl border border-white/5">
                  <table className="w-full text-right text-xs">
                    <thead className="sticky top-0 bg-slate-900 text-slate-400">
                      <tr className="border-b border-white/10">
                        <th className="py-2.5 px-3 font-bold">مرحله</th>
                        <th className="py-2.5 px-3 font-bold">نوع سفر</th>
                        <th className="py-2.5 px-3 font-bold">مسیر (مبدأ → مقصد)</th>
                        <th className="py-2.5 px-3 font-bold">مسافت و مدت</th>
                        <th className="py-2.5 px-3 font-bold">زمان شروع تخمینی</th>
                        <th className="py-2.5 px-3 font-bold">زمان رسیدن</th>
                        <th className="py-2.5 px-3 font-bold">بافر استراحت</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-slate-300">
                      {schedulePreview.map((leg) => (
                        <tr
                          key={leg.index}
                          className={`hover:bg-white/5 transition ${
                            leg.legType === 'return' ? 'bg-indigo-950/20' : ''
                          }`}
                        >
                          <td className="py-2.5 px-3 font-bold text-white">{leg.index}</td>
                          <td className="py-2.5 px-3">
                            {leg.legType === 'forward' ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-cyan-500/10 px-2 py-0.5 text-[11px] font-bold text-cyan-300 border border-cyan-500/20">
                                رفت
                              </span>
                            ) : leg.legType === 'return' ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-indigo-500/10 px-2 py-0.5 text-[11px] font-bold text-indigo-300 border border-indigo-500/20">
                                برگشت {leg.smartInverted ? '(وارون هوشمند)' : ''}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-md bg-slate-500/10 px-2 py-0.5 text-[11px] font-bold text-slate-300 border border-slate-500/20">
                                استاندارد
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 font-medium">
                            {leg.origin} → {leg.destination}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">
                            {leg.distanceKm > 0 ? `${leg.distanceKm} کیلومتر` : '—'} ({formatMinutes(leg.durationMinutes)})
                          </td>
                          <td className="py-2.5 px-3 font-bold text-cyan-300">
                            {formatOffset(leg.depMinutesFromStart)}
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">
                            +{Math.round(leg.arrMinutesFromStart)} دقیقه
                          </td>
                          <td className="py-2.5 px-3 text-slate-400">
                            {formatMinutes(leg.bufferMinutes)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

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
              {progress?.route_chain && (
                <div className="mt-4 rounded-xl border border-white/5 bg-white/5 p-3 text-xs">
                  {progress.blocked_by_sequence != null ? (
                    <div className="flex items-start gap-2 text-rose-300">
                      <ExclamationCircleIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
                      <div>
                        <span className="font-bold">توقف ایمن زنجیره (Fail-Safe Chain Halt):</span>
                        <p className="mt-0.5 text-[11px] text-slate-300">
                          عملیات ارسال در leg شماره {progress.blocked_by_sequence + 1} با خطا مواجه شد. جهت محافظت از سهمیه و جلوگیری از مسدودسازی راننده در پورتال کشوری، اجرای بارنامه‌های بعدی متوقف شده و نیاز به بررسی دستی دارد.
                        </p>
                      </div>
                    </div>
                  ) : progress.next_sequence != null ? (
                    <div className="flex items-center gap-2 text-cyan-300">
                      <ClockIcon className="h-4 w-4 shrink-0 text-cyan-400" />
                      <span>
                        آماده‌سازی leg بعدی: شماره {progress.next_sequence + 1} (پس از اتمام موفقیت‌آمیز leg قبل و سپری شدن زمان بافر استراحت آزاد خواهد شد)
                      </span>
                    </div>
                  ) : (
                    <p className="text-slate-400">تمام مراحل زنجیره با موفقیت آزاد و پردازش شده‌اند.</p>
                  )}
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
