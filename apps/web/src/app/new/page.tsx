"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckIcon,
  TruckIcon,
  MapPinIcon,
  CubeIcon,
  UserIcon,
  BanknotesIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  SparklesIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from "@heroicons/react/24/outline";
import { CheckCircleIcon } from "@heroicons/react/24/solid";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { PlateInput } from "@/components/PlateInput";
import { api } from "@/lib/api";
import { canonicalizePlate, normalizeDigits } from "@/lib/plate";
import { toPersianDigits } from "@/lib/format";
import type { Driver, WaybillJob } from "@/lib/types";
import { waybillSchema, type WaybillFormValues } from "@/schemas/waybillSchema";
import { useSession } from "@/hooks/useSession";

const initialForm: WaybillFormValues = {
  driver_national_code: "",
  origin: "",
  origin_province: "",
  origin_address: "",
  origin_district: "",
  destination: "",
  destination_province: "",
  destination_address: "",
  destination_district: "",
  plate_number: "",
  waybill_number: "",
  cargo_type: "",
  cargo_weight: "",
  cargo_count: "1",
  cargo_description: "",
  cargo_value: "",
  vehicle_type: "",
  driver_phone: "",
  sender_name: "",
  sender_phone: "",
  sender_national_code: "",
  sender_address: "",
  receiver_name: "",
  receiver_phone: "",
  receiver_national_code: "",
  receiver_address: "",
  financial_cost: "",
  financial_payment_method: "",
  shipping_two_way: false,
  shipping_time_limit: "",
  shipping_end_shipping: "",
  shipping_otp: "",
  notes: "",
};

// ─── Step definitions ────────────────────────────────────────────────────────
const STEPS = [
  { id: 1, label: "راننده و خودرو", icon: TruckIcon, fields: ["driver_national_code", "plate_number", "vehicle_type", "driver_phone"] },
  { id: 2, label: "مبدا", icon: MapPinIcon, fields: ["origin_province", "origin", "origin_address", "origin_district"] },
  { id: 3, label: "مقصد", icon: MapPinIcon, fields: ["destination_province", "destination", "destination_address", "destination_district"] },
  { id: 4, label: "بار", icon: CubeIcon, fields: ["cargo_type", "cargo_weight", "cargo_count", "cargo_value", "cargo_description"] },
  { id: 5, label: "فرستنده و گیرنده", icon: UserIcon, fields: ["sender_name", "sender_phone", "sender_national_code", "sender_address", "receiver_name", "receiver_phone", "receiver_national_code", "receiver_address"] },
  { id: 6, label: "مالی و تکمیلی", icon: BanknotesIcon, fields: ["financial_cost", "financial_payment_method", "shipping_time_limit", "shipping_two_way"] },
];

// ─── Field component ──────────────────────────────────────────────────────────
function Field({
  children,
  error,
  hint,
  label,
  required,
}: {
  children: React.ReactNode;
  error?: string;
  hint?: string;
  label: string;
  required?: boolean;
}) {
  return (
    <label className="block text-sm font-semibold text-slate-200">
      <span className="mb-2 flex items-center gap-1">
        {label}
        {required && <span className="text-rose-500 text-xs">*</span>}
      </span>
      {children}
      {hint && !error && (
        <span className="mt-1.5 flex items-center gap-1 text-xs text-slate-400 font-normal">
          <InformationCircleIcon className="h-3 w-3" />
          {hint}
        </span>
      )}
      {error && (
        <span className="mt-1.5 flex items-center gap-1 text-xs text-rose-600 font-medium">
          <ExclamationTriangleIcon className="h-3 w-3" />
          {error}
        </span>
      )}
    </label>
  );
}

// ─── Step indicator ───────────────────────────────────────────────────────────
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-2">
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1;
        const state = step < current ? "completed" : step === current ? "active" : "pending";
        return (
          <div key={step} className="flex items-center">
            <div className={`step-dot ${state}`}>
              {state === "completed" ? (
                <CheckIcon className="h-3.5 w-3.5" />
              ) : (
                <span>{step}</span>
              )}
            </div>
            {i < total - 1 && (
              <div className={`step-line ${state === "completed" ? "completed" : ""}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Section header ────────────────────────────────────────────────────────────
function SectionHeader({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle: string }) {
  return (
    <div className="flex items-start gap-4 mb-6 pb-5 border-b border-white/5">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-cyan-400 shadow-md shadow-slate-900/20">
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <h2 className="text-lg font-bold text-white">{title}</h2>
        <p className="text-sm text-slate-400 font-normal mt-0.5">{subtitle}</p>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function NewWaybillPage() {
  const { role } = useSession();
  const router = useRouter();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [form, setForm] = useState<WaybillFormValues>(initialForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [serverMessage, setServerMessage] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(1);

  useEffect(() => {
    async function loadDrivers() {
      if (role !== "client") { setLoadingDrivers(false); return; }
      setLoadingDrivers(true);
      const response = await api.get<Driver[]>("/api/v1/drivers");
      if (response.success && response.data) {
        const driverList = response.data;
        setDrivers(driverList);
        setForm((current) =>
          current.driver_national_code || !driverList[0]
            ? current
            : { ...current, driver_national_code: driverList[0].driver_national_code }
        );
      }
      setLoadingDrivers(false);
    }
    loadDrivers();
  }, [role]);

  const selectedDriver = useMemo(
    () => drivers.find((d) => d.driver_national_code === form.driver_national_code) || null,
    [drivers, form.driver_national_code]
  );

  const handleChange = (name: keyof WaybillFormValues, value: string | boolean) => {
    let nextValue = value;
    if (typeof nextValue === "string") {
      if (name === "plate_number") {
        nextValue = canonicalizePlate(nextValue);
      } else if (name === "cargo_value" || name === "financial_cost") {
        const cleanDigits = normalizeDigits(nextValue).replace(/\D/g, "");
        nextValue = cleanDigits ? Number(cleanDigits).toLocaleString("en-US") : "";
      } else if (
        ["driver_national_code", "driver_phone", "cargo_weight", "cargo_count",
          "sender_phone", "receiver_phone", "sender_national_code", "receiver_national_code"].includes(name)
      ) {
        nextValue = normalizeDigits(nextValue);
      }
    }
    setForm((current) => ({ ...current, [name]: nextValue }));
    setErrors((current) => { const next = { ...current }; delete next[name]; return next; });
  };

  // Validate only the fields of the current step
  const validateCurrentStep = (): boolean => {
    const stepFields = STEPS[currentStep - 1]?.fields ?? [];
    const parsed = waybillSchema.safeParse(form);
    if (!parsed.success) {
      const stepErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] || "form");
        if (stepFields.includes(key)) {
          stepErrors[key] = issue.message;
        }
      }
      if (Object.keys(stepErrors).length > 0) {
        setErrors(stepErrors);
        return false;
      }
    }
    return true;
  };

  const goNext = () => {
    if (!validateCurrentStep()) return;
    setCurrentStep((s) => Math.min(s + 1, STEPS.length));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const goPrev = () => {
    setCurrentStep((s) => Math.max(s - 1, 1));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setServerError(null);
    setServerMessage(null);

    const parsed = waybillSchema.safeParse(form);
    if (!parsed.success) {
      const nextErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] || "form");
        nextErrors[key] = issue.message;
      }
      setErrors(nextErrors);
      return;
    }

    const cargoWeight = parsed.data.cargo_weight ? Number(parsed.data.cargo_weight) : undefined;
    const payload = {
      driver_national_code: parsed.data.driver_national_code,
      origin: parsed.data.origin,
      destination: parsed.data.destination,
      waybill_number: parsed.data.waybill_number,
      cargo_type: parsed.data.cargo_type,
      cargo_weight: Number.isFinite(cargoWeight) ? cargoWeight : undefined,
      cargo_description: parsed.data.cargo_description,
      cargo_value: parsed.data.cargo_value,
      vehicle_type: parsed.data.vehicle_type,
      driver_phone: parsed.data.driver_phone,
      plate_number: parsed.data.plate_number,
      notes: parsed.data.notes,
      metadata_json: {
        origin_province: parsed.data.origin_province,
        origin_address: parsed.data.origin_address,
        origin_district: parsed.data.origin_district || undefined,
        destination_province: parsed.data.destination_province,
        destination_address: parsed.data.destination_address,
        destination_district: parsed.data.destination_district || undefined,
        cargo_count: parsed.data.cargo_count,
        cargo_value: parsed.data.cargo_value,
        driver_phone: parsed.data.driver_phone,
        sender_name: parsed.data.sender_name,
        sender_phone: parsed.data.sender_phone,
        sender_national_code: parsed.data.sender_national_code,
        sender_address: parsed.data.sender_address,
        receiver_name: parsed.data.receiver_name,
        receiver_phone: parsed.data.receiver_phone,
        receiver_national_code: parsed.data.receiver_national_code,
        receiver_address: parsed.data.receiver_address,
        financial_cost: parsed.data.financial_cost,
        payment_method: parsed.data.financial_payment_method,
        two_way: parsed.data.shipping_two_way,
        time_limit: parsed.data.shipping_time_limit,
        end_shipping: parsed.data.shipping_end_shipping || undefined,
        otp: parsed.data.shipping_otp || undefined,
        sender: { name: parsed.data.sender_name, phone: parsed.data.sender_phone, national_code: parsed.data.sender_national_code, address: parsed.data.sender_address },
        receiver: { name: parsed.data.receiver_name, phone: parsed.data.receiver_phone, national_code: parsed.data.receiver_national_code, address: parsed.data.receiver_address },
        origin: { province: parsed.data.origin_province, city: parsed.data.origin, district: parsed.data.origin_district || undefined, address: parsed.data.origin_address },
        destination: { province: parsed.data.destination_province, city: parsed.data.destination, district: parsed.data.destination_district || undefined, address: parsed.data.destination_address },
        cargo: { type: parsed.data.cargo_type, weight: parsed.data.cargo_weight, count: parsed.data.cargo_count, description: parsed.data.cargo_description, value: parsed.data.cargo_value },
        vehicle: { driver_national_code: parsed.data.driver_national_code, driver_phone: parsed.data.driver_phone, plate: parsed.data.plate_number, type: parsed.data.vehicle_type },
        financial: { cost: parsed.data.financial_cost, payment_method: parsed.data.financial_payment_method, cargo_value: parsed.data.cargo_value },
        shipping_options: { two_way: parsed.data.shipping_two_way, time_limit: parsed.data.shipping_time_limit, end_shipping: parsed.data.shipping_end_shipping || undefined, otp: parsed.data.shipping_otp || undefined, waybill_number: parsed.data.waybill_number },
      },
    };

    setSubmitting(true);
    const response = await api.post<WaybillJob>("/api/v1/waybill-jobs", {
      driver_national_code: parsed.data.driver_national_code,
      payload,
      max_retries: 3,
      priority: 5,
    });
    setSubmitting(false);

    if (!response.success || !response.data) {
      setServerError(response.error || "ثبت کار ناموفق بود");
      return;
    }

    setServerMessage(`✅ ماموریت #${response.data.job_id} با موفقیت ایجاد شد و در صف پردازش قرار گرفت.`);
    setTimeout(() => { router.push("/history"); router.refresh(); }, 1600);
  };

  const step = STEPS[currentStep - 1];
  const stepHasErrors = step?.fields.some((f) => errors[f]);
  const isLastStep = currentStep === STEPS.length;

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <div className="max-w-3xl mx-auto">

          {/* ── Hero header ──────────────────────────────────────── */}
          <div className="relative overflow-hidden rounded-[2rem] bg-slate-950 px-5 py-6 sm:px-8 sm:py-10 text-white shadow-2xl shadow-slate-900/20 mb-6 md:mb-8">
            <div className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-cyan-400/10 blur-[80px]" />
            <div className="absolute -left-16 -bottom-16 h-48 w-48 rounded-full bg-indigo-400/10 blur-[80px]" />
            <div className="relative z-10 flex items-center justify-between">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full bg-cyan-400/10 px-4 py-1.5 text-xs font-bold  text-cyan-400 uppercase mb-4">
                  <SparklesIcon className="h-3.5 w-3.5" />
                  ثبت ماموریت جدید
                </div>
                <h1 className="text-2xl sm:text-3xl font-black leading-tight">اتوماسیون هوشمند بارنامه</h1>
                <p className="mt-2 text-sm text-slate-400 leading-relaxed max-w-sm">
                  اطلاعات را در {toPersianDigits(STEPS.length)} مرحله وارد کنید. ربات به صورت خودکار فرم UTCMS را تکمیل می‌کند.
                </p>
              </div>
              {selectedDriver && (
                <div className="hidden lg:flex flex-col items-end gap-1 text-left shrink-0">
                  <span className="text-xs text-slate-500 font-medium">راننده انتخابی</span>
                  <span className="text-sm font-bold text-white">{selectedDriver.full_name}</span>
                  <span className="text-xs text-cyan-400 font-mono">{selectedDriver.utcms_username}</span>
                </div>
              )}
            </div>

            {/* Progress bar */}
            <div className="relative z-10 mt-6">
              <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                <span>مرحله {toPersianDigits(currentStep)} از {toPersianDigits(STEPS.length)}</span>
                <span className="text-cyan-400 font-bold">{step?.label}</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-cyan-400 transition-all duration-500 ease-out shadow-[0_0_8px_rgba(34,211,238,0.5)]"
                  style={{ width: `${(currentStep / STEPS.length) * 100}%` }}
                />
              </div>
            </div>
          </div>

          {/* ── Step dots ────────────────────────────────────────── */}
          <div className="section-card mb-6 py-4">
            <StepIndicator current={currentStep} total={STEPS.length} />
            <div className="hidden sm:flex justify-between mt-3 px-1">
              {STEPS.map((s) => (
                <span
                  key={s.id}
                  className={`text-[10px] font-bold text-center flex-1 transition-colors ${s.id === currentStep ? "text-cyan-400" : s.id < currentStep ? "text-cyan-600/80" : "text-slate-500"}`}
                >
                  {s.label}
                </span>
              ))}
            </div>
            <div className="sm:hidden text-center mt-3">
              <span className="text-xs font-black text-cyan-400">
                مرحله {toPersianDigits(currentStep)}: {step?.label}
              </span>
            </div>
          </div>

          {/* ── Form ─────────────────────────────────────────────── */}
          <form onSubmit={isLastStep ? handleSubmit : (e) => { e.preventDefault(); goNext(); }}>
            <div className="section-card space-y-5">

              {/* Step 1: راننده و خودرو */}
              {currentStep === 1 && (
                <>
                  <SectionHeader
                    icon={TruckIcon}
                    title="راننده و خودرو"
                    subtitle="انتخاب راننده و ثبت مشخصات وسیله نقلیه"
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="راننده" error={errors.driver_national_code} required>
                      {loadingDrivers ? (
                        <div className="skeleton h-12 w-full" />
                      ) : (
                        <select
                          value={form.driver_national_code}
                          onChange={(e) => handleChange("driver_national_code", e.target.value)}
                          className={`field ${errors.driver_national_code ? "error" : ""}`}
                        >
                          <option value="">انتخاب راننده...</option>
                          {drivers.map((d) => (
                            <option key={d.id} value={d.driver_national_code}>
                              {d.full_name} — {d.driver_national_code}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>

                    <Field label="پلاک خودرو" error={errors.plate_number} required>
                      <PlateInput
                        value={form.plate_number}
                        onChange={(val) => handleChange("plate_number", val)}
                      />
                    </Field>

                    <Field label="نوع خودرو" error={errors.vehicle_type} required>
                      <input
                        className={`field ${errors.vehicle_type ? "error" : ""}`}
                        placeholder="مثال: کامیون ۱۸ چرخ"
                        value={form.vehicle_type}
                        onChange={(e) => handleChange("vehicle_type", e.target.value)}
                      />
                    </Field>

                    <Field label="تلفن راننده" error={errors.driver_phone} required>
                      <input
                        dir="ltr"
                        className={`field ${errors.driver_phone ? "error" : ""}`}
                        placeholder="09123456789"
                        value={form.driver_phone}
                        onChange={(e) => handleChange("driver_phone", e.target.value)}
                      />
                    </Field>
                  </div>

                  {selectedDriver && (
                    <div className="mt-2 flex items-center gap-3 rounded-xl bg-slate-950/60 border border-white/5 px-4 py-3">
                      <div className="h-2 w-2 rounded-full bg-emerald-400 pulse-dot" />
                      <div className="text-sm">
                        <span className="font-semibold text-slate-200">{selectedDriver.full_name}</span>
                        <span className="mx-2 text-slate-700">|</span>
                        <span className="text-xs text-slate-400 font-mono">{selectedDriver.utcms_username}</span>
                        <span className={`mr-2 badge ${selectedDriver.status === "active" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-400 border border-amber-500/20"}`}>
                          {selectedDriver.status === "active" ? "فعال" : selectedDriver.status}
                        </span>
                      </div>
                    </div>
                  )}

                  {drivers.length === 0 && !loadingDrivers && (
                    <div className="status-bar info">
                      <InformationCircleIcon className="h-5 w-5 shrink-0" />
                      ابتدا در بخش رانندگان یک راننده ثبت کنید.
                    </div>
                  )}
                </>
              )}

              {/* Step 2: مبدا */}
              {currentStep === 2 && (
                <>
                  <SectionHeader
                    icon={MapPinIcon}
                    title="مبدا بارگیری"
                    subtitle="اطلاعات دقیق مکان مبدا — ربات این اطلاعات را در مرحله ۵ فرم UTCMS پر می‌کند"
                  />
                  <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/20 px-4 py-3 text-xs text-cyan-400 font-medium flex items-start gap-2">
                    <SparklesIcon className="h-4 w-4 shrink-0 mt-0.5 text-cyan-400" />
                    <span>
                      ربات ابتدا <strong>ddStateSource</strong> (استان) را انتخاب می‌کند، سپس <strong>ddCitySource</strong> (شهر) را بار می‌زند و در نهایت <strong>txtAddressSource</strong> را پر می‌کند.
                    </span>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="استان مبدا" error={errors.origin_province} required>
                      <input
                        className={`field ${errors.origin_province ? "error" : ""}`}
                        placeholder="مثال: تهران"
                        value={form.origin_province}
                        onChange={(e) => handleChange("origin_province", e.target.value)}
                      />
                    </Field>

                    <Field label="شهر مبدا" error={errors.origin} required>
                      <input
                        className={`field ${errors.origin ? "error" : ""}`}
                        placeholder="مثال: تهران"
                        value={form.origin}
                        onChange={(e) => handleChange("origin", e.target.value)}
                      />
                    </Field>

                    <Field label="آدرس مبدا" error={errors.origin_address} required>
                      <input
                        className={`field ${errors.origin_address ? "error" : ""}`}
                        placeholder="خیابان، کوچه، پلاک..."
                        value={form.origin_address}
                        onChange={(e) => handleChange("origin_address", e.target.value)}
                      />
                    </Field>

                    <Field label="ناحیه / منطقه مبدا" error={errors.origin_district} hint="اختیاری">
                      <input
                        className="field"
                        placeholder="مثال: منطقه ۱۵"
                        value={form.origin_district}
                        onChange={(e) => handleChange("origin_district", e.target.value)}
                      />
                    </Field>
                  </div>
                </>
              )}

              {/* Step 3: مقصد */}
              {currentStep === 3 && (
                <>
                  <SectionHeader
                    icon={MapPinIcon}
                    title="مقصد تحویل"
                    subtitle="اطلاعات دقیق مکان مقصد — ربات در مرحله ۶ فرم UTCMS این اطلاعات را تکمیل می‌کند"
                  />
                  <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/20 px-4 py-3 text-xs text-cyan-400 font-medium flex items-start gap-2">
                    <SparklesIcon className="h-4 w-4 shrink-0 mt-0.5 text-cyan-400" />
                    <span>
                      ربات <strong>ddStateDest</strong> (استان) و <strong>ddCityDest</strong> (شهر) را به ترتیب انتخاب کرده و <strong>txtAddressDest</strong> را پر می‌کند.
                    </span>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="استان مقصد" error={errors.destination_province} required>
                      <input
                        className={`field ${errors.destination_province ? "error" : ""}`}
                        placeholder="مثال: اصفهان"
                        value={form.destination_province}
                        onChange={(e) => handleChange("destination_province", e.target.value)}
                      />
                    </Field>

                    <Field label="شهر مقصد" error={errors.destination} required>
                      <input
                        className={`field ${errors.destination ? "error" : ""}`}
                        placeholder="مثال: اصفهان"
                        value={form.destination}
                        onChange={(e) => handleChange("destination", e.target.value)}
                      />
                    </Field>

                    <Field label="آدرس مقصد" error={errors.destination_address} required>
                      <input
                        className={`field ${errors.destination_address ? "error" : ""}`}
                        placeholder="خیابان، کوچه، پلاک..."
                        value={form.destination_address}
                        onChange={(e) => handleChange("destination_address", e.target.value)}
                      />
                    </Field>

                    <Field label="ناحیه / منطقه مقصد" error={errors.destination_district} hint="اختیاری">
                      <input
                        className="field"
                        placeholder="مثال: شهرک صنعتی"
                        value={form.destination_district}
                        onChange={(e) => handleChange("destination_district", e.target.value)}
                      />
                    </Field>
                  </div>
                </>
              )}

              {/* Step 4: بار */}
              {currentStep === 4 && (
                <>
                  <SectionHeader
                    icon={CubeIcon}
                    title="مشخصات محموله"
                    subtitle="جزئیات بار جهت ثبت در سامانه UTCMS"
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="نوع بار" error={errors.cargo_type} required>
                      <input
                        className={`field ${errors.cargo_type ? "error" : ""}`}
                        placeholder="مثال: مواد غذایی"
                        value={form.cargo_type}
                        onChange={(e) => handleChange("cargo_type", e.target.value)}
                      />
                    </Field>

                    <Field label="وزن بار (تن)" error={errors.cargo_weight} hint="عدد صحیح یا اعشاری" required>
                      <input
                        dir="ltr"
                        className={`field ${errors.cargo_weight ? "error" : ""}`}
                        placeholder="مثال: ۳.۵"
                        value={form.cargo_weight}
                        onChange={(e) => handleChange("cargo_weight", e.target.value)}
                      />
                    </Field>

                    <Field label="تعداد" error={errors.cargo_count} required>
                      <input
                        dir="ltr"
                        className={`field ${errors.cargo_count ? "error" : ""}`}
                        placeholder="۱"
                        value={form.cargo_count}
                        onChange={(e) => handleChange("cargo_count", e.target.value)}
                      />
                    </Field>

                    <Field label="ارزش بار (ریال)" error={errors.cargo_value} required>
                      <input
                        dir="ltr"
                        className={`field ${errors.cargo_value ? "error" : ""}`}
                        placeholder="۱۰,۰۰۰,۰۰۰"
                        value={form.cargo_value}
                        onChange={(e) => handleChange("cargo_value", e.target.value)}
                      />
                    </Field>

                    <div className="sm:col-span-2">
                      <Field label="شرح بار" error={errors.cargo_description} hint="اختیاری">
                        <textarea
                          className="field min-h-24 resize-none"
                          placeholder="توضیحات تکمیلی در مورد محموله..."
                          value={form.cargo_description}
                          onChange={(e) => handleChange("cargo_description", e.target.value)}
                        />
                      </Field>
                    </div>
                  </div>
                </>
              )}

              {/* Step 5: فرستنده و گیرنده */}
              {currentStep === 5 && (
                <>
                  <SectionHeader
                    icon={UserIcon}
                    title="اطلاعات فرستنده و گیرنده"
                    subtitle="مشخصات کامل طرفین قرارداد حمل"
                  />
                  <div>
                    <p className="text-xs font-black text-cyan-400 uppercase r mb-3">فرستنده</p>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="نام و نام خانوادگی" error={errors.sender_name} required>
                        <input className={`field ${errors.sender_name ? "error" : ""}`} value={form.sender_name} onChange={(e) => handleChange("sender_name", e.target.value)} />
                      </Field>
                      <Field label="تلفن" error={errors.sender_phone} required>
                        <input dir="ltr" className={`field ${errors.sender_phone ? "error" : ""}`} placeholder="09120000000" value={form.sender_phone} onChange={(e) => handleChange("sender_phone", e.target.value)} />
                      </Field>
                      <Field label="کد ملی" error={errors.sender_national_code} required>
                        <input dir="ltr" className={`field ${errors.sender_national_code ? "error" : ""}`} value={form.sender_national_code} onChange={(e) => handleChange("sender_national_code", e.target.value)} />
                      </Field>
                      <Field label="آدرس" error={errors.sender_address} required>
                        <input className={`field ${errors.sender_address ? "error" : ""}`} value={form.sender_address} onChange={(e) => handleChange("sender_address", e.target.value)} />
                      </Field>
                    </div>
                  </div>

                  <div className="border-t border-white/5 pt-5">
                    <p className="text-xs font-black text-cyan-400 uppercase r mb-3">گیرنده</p>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="نام و نام خانوادگی" error={errors.receiver_name} required>
                        <input className={`field ${errors.receiver_name ? "error" : ""}`} value={form.receiver_name} onChange={(e) => handleChange("receiver_name", e.target.value)} />
                      </Field>
                      <Field label="تلفن" error={errors.receiver_phone} required>
                        <input dir="ltr" className={`field ${errors.receiver_phone ? "error" : ""}`} placeholder="09120000000" value={form.receiver_phone} onChange={(e) => handleChange("receiver_phone", e.target.value)} />
                      </Field>
                      <Field label="کد ملی" error={errors.receiver_national_code} hint="اختیاری">
                        <input dir="ltr" className="field" value={form.receiver_national_code} onChange={(e) => handleChange("receiver_national_code", e.target.value)} />
                      </Field>
                      <Field label="آدرس" error={errors.receiver_address} required>
                        <input className={`field ${errors.receiver_address ? "error" : ""}`} value={form.receiver_address} onChange={(e) => handleChange("receiver_address", e.target.value)} />
                      </Field>
                    </div>
                  </div>
                </>
              )}

              {/* Step 6: مالی و تکمیلی */}
              {currentStep === 6 && (
                <>
                  <SectionHeader
                    icon={BanknotesIcon}
                    title="اطلاعات مالی و گزینه‌های حمل"
                    subtitle="هزینه حمل، روش پرداخت و تنظیمات نهایی"
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <Field label="هزینه حمل (ریال)" error={errors.financial_cost} required>
                      <input dir="ltr" className={`field ${errors.financial_cost ? "error" : ""}`} placeholder="۵,۰۰۰,۰۰۰" value={form.financial_cost} onChange={(e) => handleChange("financial_cost", e.target.value)} />
                    </Field>

                    <Field label="روش پرداخت" error={errors.financial_payment_method}>
                      <input className="field" placeholder="مثال: نقدی، چک" value={form.financial_payment_method} onChange={(e) => handleChange("financial_payment_method", e.target.value)} />
                    </Field>

                    <Field label="مهلت زمانی" error={errors.shipping_time_limit} hint="مثال: ۱۲۰ دقیقه" required>
                      <input className={`field ${errors.shipping_time_limit ? "error" : ""}`} value={form.shipping_time_limit} onChange={(e) => handleChange("shipping_time_limit", e.target.value)} />
                    </Field>

                    <Field label="شماره بارنامه" error={errors.waybill_number} hint="در صورت وجود">
                      <input dir="ltr" className="field" value={form.waybill_number} onChange={(e) => handleChange("waybill_number", e.target.value)} />
                    </Field>

                    <div className="sm:col-span-2">
                      <Field label="توضیحات" error={errors.notes} hint="اختیاری">
                        <textarea className="field min-h-24 resize-none" value={form.notes} onChange={(e) => handleChange("notes", e.target.value)} />
                      </Field>
                    </div>

                    <div className="sm:col-span-2">
                      <label className="flex items-center gap-3 rounded-xl border border-white/5 bg-slate-950/60 px-4 py-3.5 cursor-pointer hover:bg-slate-950/80 transition-colors">
                        <input
                          type="checkbox"
                          checked={form.shipping_two_way}
                          onChange={(e) => handleChange("shipping_two_way", e.target.checked)}
                          className="w-4 h-4 accent-cyan-500"
                        />
                        <span className="text-sm font-semibold text-slate-200">ثبت حمل رفت و برگشت</span>
                      </label>
                    </div>
                  </div>

                  {/* Summary before submit */}
                  <div className="rounded-2xl bg-slate-950 text-white p-5 mt-2">
                    <p className="text-xs font-bold text-slate-400 uppercase r mb-3">خلاصه ماموریت</p>
                    <div className="grid gap-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-400">راننده</span>
                        <span className="font-semibold">{selectedDriver?.full_name || "—"}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">مسیر</span>
                        <span className="font-semibold">{form.origin_province} ← {form.destination_province}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">بار</span>
                        <span className="font-semibold">{form.cargo_type} / {form.cargo_weight} تن</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">هزینه</span>
                        <span className="font-semibold text-cyan-400">{form.financial_cost} ریال</span>
                      </div>
                    </div>
                  </div>
                </>
              )}

              {/* ── Feedback messages ─────────────────────────── */}
              {serverError && (
                <div className="status-bar error">
                  <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
                  {serverError}
                </div>
              )}
              {serverMessage && (
                <div className="status-bar success">
                  <CheckCircleIcon className="h-5 w-5 shrink-0" />
                  {serverMessage}
                </div>
              )}
              {stepHasErrors && (
                <div className="status-bar error">
                  <ExclamationTriangleIcon className="h-5 w-5 shrink-0" />
                  لطفاً فیلدهای اجباری این مرحله را کامل کنید.
                </div>
              )}
            </div>

            {/* ── Navigation buttons ────────────────────────────── */}
            <div className="flex items-center justify-between mt-5 gap-4">
              <button
                type="button"
                onClick={goPrev}
                disabled={currentStep === 1}
                className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-950 px-6 py-3 text-sm font-semibold text-slate-300 transition hover:bg-slate-900 disabled:opacity-30 disabled:cursor-not-allowed shadow-sm"
              >
                <ChevronRightIcon className="h-4 w-4" />
                مرحله قبل
              </button>

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-medium">
                  {toPersianDigits(currentStep)}/{toPersianDigits(STEPS.length)}
                </span>
                {isLastStep ? (
                  <button
                    type="submit"
                    disabled={submitting || drivers.length === 0}
                    className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 px-8 py-3.5 text-sm font-black text-slate-950 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-cyan-500/20 active:scale-[0.98]"
                  >
                    {submitting ? (
                      <>
                        <div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                        در حال ارسال...
                      </>
                    ) : (
                      <>
                        <CheckIcon className="h-4 w-4" />
                        ثبت و ارسال به صف
                      </>
                    )}
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 px-7 py-3.5 text-sm font-black text-slate-950 transition-all shadow-lg shadow-cyan-500/20 active:scale-[0.98]"
                  >
                    مرحله بعد
                    <ChevronLeftIcon className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            {/* automation hint footer */}
            <div className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-400">
              <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 pulse-dot" />
              <span>ربات اتوماسیون پس از ثبت، فرم UTCMS را با روش <strong className="text-cyan-400">utcms_direct</strong> پر می‌کند</span>
            </div>
          </form>
        </div>
      </AuthGuard>
    </AppShell>
  );
}
