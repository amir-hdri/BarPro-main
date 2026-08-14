"use client";

import { memo, useEffect, useMemo, useState } from "react";
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
  PlusIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { CheckCircleIcon } from "@heroicons/react/24/solid";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "react-hot-toast";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { PlateInput } from "@/components/PlateInput";
import { ProvinceCitySelect } from "@/components/ProvinceCitySelect";
import { SmartAddressInput } from "@/components/SmartAddressInput";
import { LocationMapPicker } from "@/components/LocationMapPicker";
import { FavoriteLocationPicker } from "@/components/FavoriteLocationPicker";
import { ProgressBar } from "@/components/ProgressBar";
import { api } from "@/lib/api";
import { canonicalizePlate, normalizeDigits } from "@/lib/plate";
import { toPersianDigits } from "@/lib/format";
import type { Driver, Plate, WaybillJob } from "@/lib/types";
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
  cargo_type: "",
  cargo_packaging: "",
  cargo_weight: "",
  cargo_value: "",
  sender_name: "",
  receiver_name: "",
};

const STEPS = [
  { id: 1, label: "راننده و خودرو", icon: TruckIcon, fields: ["driver_national_code", "plate_number"] },
  { id: 2, label: "مبدا", icon: MapPinIcon, fields: ["origin_province", "origin", "origin_address", "origin_district"] },
  { id: 3, label: "مقصد", icon: MapPinIcon, fields: ["destination_province", "destination", "destination_address", "destination_district"] },
  { id: 4, label: "بار", icon: CubeIcon, fields: ["cargo_type", "cargo_packaging", "cargo_weight", "cargo_value"] },
  { id: 5, label: "فرستنده و گیرنده", icon: UserIcon, fields: ["sender_name", "receiver_name"] },
  { id: 6, label: "ثبت و زمان‌بندی", icon: BanknotesIcon, fields: [] },
];

const Field = memo(function Field({
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
});

const StepIndicator = memo(function StepIndicator({ current, total }: { current: number; total: number }) {
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
});

const SectionHeader = memo(function SectionHeader({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle: string }) {
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
});

export default function NewWaybillPage() {
  const { role } = useSession();
  const router = useRouter();
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [plates, setPlates] = useState<Plate[]>([]);
  const [form, setForm] = useState<WaybillFormValues>(initialForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [serverMessage, setServerMessage] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [direction, setDirection] = useState<'next' | 'back'>('next');

  // Quick Add Driver Modal states
  const [showQuickAddDriver, setShowQuickAddDriver] = useState(false);
  const [quickDriverForm, setQuickDriverForm] = useState({
    full_name: "",
    driver_national_code: "",
    utcms_username: "",
    utcms_password: "",
    plate_number: "",
  });
  const [quickAddLoading, setQuickAddLoading] = useState(false);
  const [quickAddError, setQuickAddError] = useState<string | null>(null);

  // Map & Location states
  const [originCoords, setOriginCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [destinationCoords, setDestinationCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [showOriginMap, setShowOriginMap] = useState(false);
  const [showDestinationMap, setShowDestinationMap] = useState(false);

  // Scheduling state
  const [isScheduled, setIsScheduled] = useState(false);
  const [scheduleTitle, setScheduleTitle] = useState("");
  const [scheduleFrequency, setScheduleFrequency] = useState("daily");
  const [scheduleRunTime, setScheduleRunTime] = useState("08:00");
  const [scheduleRunTimes, setScheduleRunTimes] = useState("08:00");
  const [scheduleSpecificDates, setScheduleSpecificDates] = useState("");
  const [scheduleStartDate, setScheduleStartDate] = useState("");
  const [scheduleEndDate, setScheduleEndDate] = useState("");

  const loadDriversAndPlates = async () => {
    if (role !== "client" && role !== "master_admin") {
      setLoadingDrivers(false);
      return;
    }
    setLoadingDrivers(true);
    const [driversRes, platesRes] = await Promise.all([
      api.get<Driver[]>("/api/v1/drivers"),
      api.get<Plate[]>("/api/v1/plates"),
    ]);

    const driverList = driversRes.success && driversRes.data ? driversRes.data : [];
    const plateList = platesRes.success && platesRes.data ? platesRes.data : [];
    setDrivers(driverList);
    setPlates(plateList);

    if (driverList.length > 0) {
      setForm((current) => {
        const selectedD = driverList.find((d) => d.driver_national_code === current.driver_national_code) || driverList[0];
        const matchingPlate = plateList.find((p) => p.driver_id === selectedD.id)?.plate_number;
        return {
          ...current,
          driver_national_code: current.driver_national_code || selectedD.driver_national_code,
          plate_number: current.plate_number || matchingPlate || "",
        };
      });
    }
    setLoadingDrivers(false);
  };

  useEffect(() => {
    void loadDriversAndPlates();
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
      } else if (name === "cargo_value") {
        const cleanDigits = normalizeDigits(nextValue).replace(/\D/g, "");
        nextValue = cleanDigits ? Number(cleanDigits).toLocaleString("en-US") : "";
      } else if (
        ["driver_national_code", "cargo_weight"].includes(name)
      ) {
        nextValue = normalizeDigits(nextValue);
      }
    }
    setForm((current) => ({ ...current, [name]: nextValue }));
    setErrors((current) => { const next = { ...current }; delete next[name]; return next; });
  };

  const handleDriverSelection = (driverNationalCode: string) => {
    handleChange("driver_national_code", driverNationalCode);
    const foundDriver = drivers.find((d) => d.driver_national_code === driverNationalCode);
    if (foundDriver) {
      const matchingPlate = plates.find((p) => p.driver_id === foundDriver.id)?.plate_number;
      if (matchingPlate) {
        handleChange("plate_number", matchingPlate);
      }
    }
  };

  const handleQuickAddDriver = async (e: React.FormEvent) => {
    e.preventDefault();
    setQuickAddError(null);
    if (!quickDriverForm.full_name.trim() || !quickDriverForm.driver_national_code.trim()) {
      setQuickAddError("نام و کد ملی راننده الزامی است.");
      return;
    }
    if (!/^\d{10}$/.test(quickDriverForm.driver_national_code)) {
      setQuickAddError("کد ملی راننده باید ۱۰ رقم باشد.");
      return;
    }
    if (!quickDriverForm.utcms_username.trim() || quickDriverForm.utcms_password.length < 4) {
      setQuickAddError("نام کاربری و رمز عبور UTCMS (حداقل ۴ کاراکتر) الزامی است.");
      return;
    }

    setQuickAddLoading(true);
    const driverRes = await api.post<Driver>("/api/v1/drivers", {
      full_name: quickDriverForm.full_name,
      driver_national_code: quickDriverForm.driver_national_code,
      utcms_username: quickDriverForm.utcms_username,
      utcms_password: quickDriverForm.utcms_password,
    });

    if (!driverRes.success || !driverRes.data) {
      setQuickAddLoading(false);
      setQuickAddError(driverRes.error || "خطا در ثبت راننده");
      return;
    }

    const newDriver = driverRes.data;

    // If plate provided, register it as well
    if (quickDriverForm.plate_number.trim()) {
      await api.post<Plate>("/api/v1/plates", {
        driver_id: newDriver.id,
        plate_number: quickDriverForm.plate_number,
      });
    }

    toast.success("راننده با موفقیت افزوده شد");
    setShowQuickAddDriver(false);
    setQuickDriverForm({ full_name: "", driver_national_code: "", utcms_username: "", utcms_password: "", plate_number: "" });
    setQuickAddLoading(false);

    // Reload and select
    await loadDriversAndPlates();
    handleChange("driver_national_code", newDriver.driver_national_code);
    if (quickDriverForm.plate_number.trim()) {
      handleChange("plate_number", quickDriverForm.plate_number);
    }
  };


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
    setDirection('next');
    setCurrentStep((s) => Math.min(s + 1, STEPS.length));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const goPrev = () => {
    setDirection('back');
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
      cargo_type: parsed.data.cargo_type,
      cargo_packaging: parsed.data.cargo_packaging,
      cargo_weight: Number.isFinite(cargoWeight) ? cargoWeight : undefined,
      cargo_value: parsed.data.cargo_value,
      plate_number: parsed.data.plate_number,
      metadata_json: {
        origin_province: parsed.data.origin_province,
        origin_address: parsed.data.origin_address,
        origin_district: parsed.data.origin_district || undefined,
        destination_province: parsed.data.destination_province,
        destination_address: parsed.data.destination_address,
        destination_district: parsed.data.destination_district || undefined,
        cargo_packaging: parsed.data.cargo_packaging,
        cargo_value: parsed.data.cargo_value,
        sender_name: parsed.data.sender_name,
        receiver_name: parsed.data.receiver_name,
        sender: { name: parsed.data.sender_name },
        receiver: { name: parsed.data.receiver_name },
        origin: { province: parsed.data.origin_province, city: parsed.data.origin, district: parsed.data.origin_district || undefined, address: parsed.data.origin_address, coordinates: originCoords || undefined },
        destination: { province: parsed.data.destination_province, city: parsed.data.destination, district: parsed.data.destination_district || undefined, address: parsed.data.destination_address, coordinates: destinationCoords || undefined },
        cargo: { type: parsed.data.cargo_type, packaging: parsed.data.cargo_packaging, weight: parsed.data.cargo_weight, value: parsed.data.cargo_value },
        vehicle: { driver_national_code: parsed.data.driver_national_code, plate: parsed.data.plate_number },
      },
    };

    if (isScheduled) {
      if (!selectedDriver) {
        setServerError("انتخاب راننده برای زمان‌بندی الزامی است");
        return;
      }
      if (!scheduleTitle.trim()) {
        setServerError("عنوان زمان‌بندی الزامی است");
        return;
      }
      if (!/^\d{2}:\d{2}$/.test(scheduleRunTime)) {
        setServerError("فرمت ساعت اجرا باید HH:MM باشد");
        return;
      }

      setSubmitting(true);
      const schedulePayload = {
        driver_id: selectedDriver.id,
        title: scheduleTitle,
        frequency: scheduleFrequency,
        run_time: scheduleRunTime,
        run_times: scheduleRunTimes ? scheduleRunTimes.split(',').map((s: string) => s.trim()).filter(Boolean) : [scheduleRunTime],
        specific_dates: scheduleSpecificDates ? scheduleSpecificDates.split(',').map((s: string) => s.trim()).filter(Boolean) : [],
        start_date: scheduleStartDate || undefined,
        end_date: scheduleEndDate || undefined,
        payload_template: payload,
        is_active: true
      };

      const response = await api.post("/api/v1/driver-schedules", schedulePayload);
      setSubmitting(false);

      if (!response.success) {
        setServerError(response.error || "ثبت زمان‌بندی ناموفق بود");
        return;
      }

      setServerMessage("✅ زمان‌بندی خودکار بارنامه با موفقیت ایجاد شد.");
      setTimeout(() => { router.push("/drivers"); router.refresh(); }, 1600);
      return;
    }

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
    <AuthGuard requiredRole="client">
      <AppShell>
        <div className="max-w-4xl mx-auto">

          <div className="relative overflow-hidden rounded-[2.5rem] bg-slate-950 px-6 py-8 sm:px-10 sm:py-12 text-white shadow-2xl shadow-slate-900/40 mb-8 md:mb-10">
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
              <ProgressBar
                value={currentStep}
                max={STEPS.length}
                segments={STEPS.length}
                tone="indigo"
                label="پیشرفت مراحل ثبت بارنامه"
              />
            </div>
          </div>

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

          <form onSubmit={isLastStep ? handleSubmit : (e) => { e.preventDefault(); goNext(); }} className="pb-24 sm:pb-0">
            <AnimatePresence mode="wait" custom={direction}>
              <motion.div
                key={currentStep}
                custom={direction}
                variants={{
                  enter: (dir: 'next' | 'back') => ({
                    x: dir === 'next' ? -20 : 20,
                    opacity: 0,
                  }),
                  center: {
                    x: 0,
                    opacity: 1,
                  },
                  exit: (dir: 'next' | 'back') => ({
                    x: dir === 'next' ? 20 : -20,
                    opacity: 0,
                  }),
                }}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.2, ease: "easeInOut" }}
                className="section-card space-y-5"
              >

              {currentStep === 1 && (
                <>
                  <SectionHeader
                    icon={TruckIcon}
                    title="راننده و خودرو"
                    subtitle="انتخاب راننده و ثبت مشخصات وسیله نقلیه"
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <label className="text-sm font-semibold text-slate-200">
                          راننده <span className="text-rose-500 text-xs">*</span>
                        </label>
                        <button
                          type="button"
                          onClick={() => setShowQuickAddDriver(true)}
                          className="inline-flex items-center gap-1 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition"
                        >
                          <PlusIcon className="h-3.5 w-3.5" />
                          + ثبت سریع راننده جدید
                        </button>
                      </div>
                      {loadingDrivers ? (
                        <div className="skeleton h-12 w-full" />
                      ) : (
                        <select
                          value={form.driver_national_code}
                          onChange={(e) => handleDriverSelection(e.target.value)}
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
                      {errors.driver_national_code && (
                        <span className="mt-1.5 flex items-center gap-1 text-xs text-rose-600 font-medium">
                          <ExclamationTriangleIcon className="h-3 w-3" />
                          {errors.driver_national_code}
                        </span>
                      )}
                    </div>

                    <Field label="پلاک خودرو" error={errors.plate_number} required>
                      <PlateInput
                        value={form.plate_number}
                        onChange={(val) => handleChange("plate_number", val)}
                        error={errors.plate_number}
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
                    <div className="flex flex-col items-center justify-center p-6 rounded-2xl bg-slate-950/40 border border-dashed border-cyan-500/30 text-center gap-3">
                      <p className="text-sm text-slate-300">هنوز راننده‌ای در سامانه ثبت نشده است.</p>
                      <button
                        type="button"
                        onClick={() => setShowQuickAddDriver(true)}
                        className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-5 py-2.5 text-xs font-black transition"
                      >
                        <PlusIcon className="h-4 w-4" />
                        ثبت سریع راننده جدید
                      </button>
                    </div>
                  )}
                </>
              )}


              {currentStep === 2 && (
                <>
                  <SectionHeader
                    icon={MapPinIcon}
                    title="مبدا بارگیری"
                    subtitle="اطلاعات دقیق مکان مبدا — ربات این اطلاعات را در مرحله ۵ فرم UTCMS پر می‌کند"
                  />

                  {/* ورودی هوشمند آدرس سرهم */}
                  <SmartAddressInput
                    onParsed={(parsed) => {
                      if (parsed.province) handleChange("origin_province", parsed.province);
                      if (parsed.city) handleChange("origin", parsed.city);
                      if (parsed.district) handleChange("origin_district", parsed.district);
                      if (parsed.address) handleChange("origin_address", parsed.address);
                      if (parsed.coordinates) setOriginCoords(parsed.coordinates);
                    }}
                  />

                  {/* انتخاب از آدرس‌های محبوب */}
                  <FavoriteLocationPicker
                    mode="origin"
                    currentProvince={form.origin_province}
                    currentCity={form.origin}
                    currentDistrict={form.origin_district}
                    currentAddress={form.origin_address}
                    currentLat={originCoords?.lat}
                    currentLng={originCoords?.lng}
                    onSelectFavorite={(fav) => {
                      handleChange("origin_province", fav.province);
                      handleChange("origin", fav.city);
                      if (fav.district) handleChange("origin_district", fav.district);
                      handleChange("origin_address", fav.address);
                      if (fav.latitude && fav.longitude) {
                        setOriginCoords({ lat: fav.latitude, lng: fav.longitude });
                      }
                    }}
                  />

                  {/* دکمه نمایش / مخفی‌سازی نقشه تعاملی */}
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold text-slate-300">انتخاب استان و شهر:</span>
                    <button
                      type="button"
                      onClick={() => setShowOriginMap(!showOriginMap)}
                      className="px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 text-xs font-bold transition-all border border-cyan-500/30 flex items-center gap-1.5"
                    >
                      <MapPinIcon className="h-4 w-4" />
                      <span>{showOriginMap ? "بستن نقشه" : "انتخاب پین روی نقشه تعاملی"}</span>
                    </button>
                  </div>

                  {/* نقشه تعاملی Leaflet */}
                  {showOriginMap && (
                    <LocationMapPicker
                      label="مبدا"
                      initialLat={originCoords?.lat || 35.6892}
                      initialLng={originCoords?.lng || 51.3890}
                      onLocationSelected={(loc) => {
                        if (loc.province) handleChange("origin_province", loc.province);
                        if (loc.city) handleChange("origin", loc.city);
                        if (loc.district) handleChange("origin_district", loc.district);
                        if (loc.address) handleChange("origin_address", loc.address);
                        setOriginCoords({ lat: loc.lat, lng: loc.lng });
                      }}
                      onClose={() => setShowOriginMap(false)}
                    />
                  )}

                  {/* انتخابگر کشویی استان و شهر */}
                  <ProvinceCitySelect
                    provinceValue={form.origin_province}
                    cityValue={form.origin}
                    onProvinceChange={(prov) => handleChange("origin_province", prov)}
                    onCityChange={(city, coords) => {
                      handleChange("origin", city);
                      if (coords) setOriginCoords(coords);
                    }}
                    provinceError={errors.origin_province}
                    cityError={errors.origin}
                  />

                  <div className="grid gap-5 sm:grid-cols-2 mt-5">
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
                        placeholder="مثال: منطقه ۱۵ یا شهرک صنعتی"
                        value={form.origin_district}
                        onChange={(e) => handleChange("origin_district", e.target.value)}
                      />
                    </Field>
                  </div>
                </>
              )}

              {currentStep === 3 && (
                <>
                  <SectionHeader
                    icon={MapPinIcon}
                    title="مقصد تحویل"
                    subtitle="اطلاعات دقیق مکان مقصد — ربات در مرحله ۶ فرم UTCMS این اطلاعات را تکمیل می‌کند"
                  />

                  {/* ورودی هوشمند آدرس سرهم */}
                  <SmartAddressInput
                    onParsed={(parsed) => {
                      if (parsed.province) handleChange("destination_province", parsed.province);
                      if (parsed.city) handleChange("destination", parsed.city);
                      if (parsed.district) handleChange("destination_district", parsed.district);
                      if (parsed.address) handleChange("destination_address", parsed.address);
                      if (parsed.coordinates) setDestinationCoords(parsed.coordinates);
                    }}
                  />

                  {/* انتخاب از آدرس‌های محبوب */}
                  <FavoriteLocationPicker
                    mode="destination"
                    currentProvince={form.destination_province}
                    currentCity={form.destination}
                    currentDistrict={form.destination_district}
                    currentAddress={form.destination_address}
                    currentLat={destinationCoords?.lat}
                    currentLng={destinationCoords?.lng}
                    onSelectFavorite={(fav) => {
                      handleChange("destination_province", fav.province);
                      handleChange("destination", fav.city);
                      if (fav.district) handleChange("destination_district", fav.district);
                      handleChange("destination_address", fav.address);
                      if (fav.latitude && fav.longitude) {
                        setDestinationCoords({ lat: fav.latitude, lng: fav.longitude });
                      }
                    }}
                  />

                  {/* دکمه نمایش / مخفی‌سازی نقشه تعاملی */}
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold text-slate-300">انتخاب استان و شهر:</span>
                    <button
                      type="button"
                      onClick={() => setShowDestinationMap(!showDestinationMap)}
                      className="px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 text-xs font-bold transition-all border border-cyan-500/30 flex items-center gap-1.5"
                    >
                      <MapPinIcon className="h-4 w-4" />
                      <span>{showDestinationMap ? "بستن نقشه" : "انتخاب پین روی نقشه تعاملی"}</span>
                    </button>
                  </div>

                  {/* نقشه تعاملی Leaflet */}
                  {showDestinationMap && (
                    <LocationMapPicker
                      label="مقصد"
                      initialLat={destinationCoords?.lat || 32.6546}
                      initialLng={destinationCoords?.lng || 51.6680}
                      onLocationSelected={(loc) => {
                        if (loc.province) handleChange("destination_province", loc.province);
                        if (loc.city) handleChange("destination", loc.city);
                        if (loc.district) handleChange("destination_district", loc.district);
                        if (loc.address) handleChange("destination_address", loc.address);
                        setDestinationCoords({ lat: loc.lat, lng: loc.lng });
                      }}
                      onClose={() => setShowDestinationMap(false)}
                    />
                  )}

                  {/* انتخابگر کشویی استان و شهر */}
                  <ProvinceCitySelect
                    provinceValue={form.destination_province}
                    cityValue={form.destination}
                    onProvinceChange={(prov) => handleChange("destination_province", prov)}
                    onCityChange={(city, coords) => {
                      handleChange("destination", city);
                      if (coords) setDestinationCoords(coords);
                    }}
                    provinceError={errors.destination_province}
                    cityError={errors.destination}
                  />

                  <div className="grid gap-5 sm:grid-cols-2 mt-5">
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
                        aria-label="وزن بار"
                        className={`field ${errors.cargo_weight ? "error" : ""}`}
                        placeholder="مثال: ۳.۵"
                        value={form.cargo_weight}
                        onChange={(e) => handleChange("cargo_weight", e.target.value)}
                      />
                    </Field>

                    <Field label="نوع بسته‌بندی" error={errors.cargo_packaging} required>
                      <input
                        className={`field ${errors.cargo_packaging ? "error" : ""}`}
                        placeholder="مثال: فله، کیسه، پالت"
                        value={form.cargo_packaging}
                        onChange={(e) => handleChange("cargo_packaging", e.target.value)}
                      />
                    </Field>

                    <Field label="ارزش بار (ریال)" error={errors.cargo_value} required>
                      <input
                        dir="ltr"
                        aria-label="ارزش بار"
                        className={`field ${errors.cargo_value ? "error" : ""}`}
                        placeholder="۱۰,۰۰۰,۰۰۰"
                        value={form.cargo_value}
                        onChange={(e) => handleChange("cargo_value", e.target.value)}
                      />
                    </Field>

                  </div>
                </>
              )}

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
                    </div>
                  </div>

                  <div className="border-t border-white/5 pt-5">
                    <p className="text-xs font-black text-cyan-400 uppercase r mb-3">گیرنده</p>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="نام و نام خانوادگی" error={errors.receiver_name} required>
                        <input className={`field ${errors.receiver_name ? "error" : ""}`} value={form.receiver_name} onChange={(e) => handleChange("receiver_name", e.target.value)} />
                      </Field>
                    </div>
                  </div>
                </>
              )}

              {currentStep === 6 && (
                <>
                  <SectionHeader
                    icon={BanknotesIcon}
                    title="ثبت و زمان‌بندی"
                    subtitle="مرور اطلاعات ضروری و در صورت نیاز ساخت برنامه تکرار"
                  />
                  <div className="grid gap-5 sm:grid-cols-2">
                    <div className="sm:col-span-2 border-t border-white/5 pt-5 mt-2">
                      <label className="flex items-center gap-3 rounded-xl border border-white/5 bg-slate-950/60 px-4 py-3.5 cursor-pointer hover:bg-slate-950/80 transition-colors">
                        <input
                          type="checkbox"
                          checked={isScheduled}
                          onChange={(e) => setIsScheduled(e.target.checked)}
                          className="w-4 h-4 accent-cyan-500"
                        />
                        <span className="text-sm font-semibold text-slate-200">زمان‌بندی و تکرار خودکار این بارنامه</span>
                      </label>
                    </div>

                    {isScheduled && (
                      <div className="sm:col-span-2 grid gap-5 sm:grid-cols-2 bg-slate-950/40 p-5 rounded-2xl border border-white/5 animate-in fade-in duration-200">
                        <div className="sm:col-span-2">
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">عنوان برنامه زمان‌بندی</span>
                            <input
                              className="field"
                              placeholder="مثال: برنامه روزانه بار آجر"
                              value={scheduleTitle}
                              onChange={(e) => setScheduleTitle(e.target.value)}
                              required
                            />
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">تناوب</span>
                            <select
                              value={scheduleFrequency}
                              onChange={(e) => setScheduleFrequency(e.target.value)}
                              className="field"
                            >
                              <option value="daily" className="bg-slate-950">روزانه</option>
                              <option value="weekly" className="bg-slate-950">هفتگی</option>
                              <option value="once" className="bg-slate-950">یکبار</option>
                            </select>
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">ساعت اجرا (HH:MM)</span>
                            <input
                              className="field"
                              placeholder="08:00"
                              value={scheduleRunTime}
                              onChange={(e) => setScheduleRunTime(e.target.value)}
                              required
                            />
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">ساعت‌های اجرای بیشتر (جدا شده با کاما)</span>
                            <input
                              className="field"
                              placeholder="08:00, 14:00"
                              value={scheduleRunTimes}
                              onChange={(e) => setScheduleRunTimes(e.target.value)}
                            />
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">تاریخ‌های مشخص (Solar Hijri YYYY-MM-DD, comma)</span>
                            <input
                              className="field"
                              placeholder="1405-04-15, 1405-04-16"
                              value={scheduleSpecificDates}
                              onChange={(e) => setScheduleSpecificDates(e.target.value)}
                            />
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">از تاریخ (YYYY-MM-DD)</span>
                            <input
                              className="field"
                              placeholder="1405-04-01"
                              value={scheduleStartDate}
                              onChange={(e) => setScheduleStartDate(e.target.value)}
                            />
                          </label>
                        </div>

                        <div>
                          <label className="block text-sm font-semibold text-slate-200">
                            <span className="mb-2 block">تا تاریخ (YYYY-MM-DD)</span>
                            <input
                              className="field"
                              placeholder="1405-04-30"
                              value={scheduleEndDate}
                              onChange={(e) => setScheduleEndDate(e.target.value)}
                            />
                          </label>
                        </div>
                      </div>
                    )}
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
                    </div>
                  </div>
                </>
              )}

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
            </motion.div>
          </AnimatePresence>

          <div className="flex items-center justify-between mt-5 gap-3 sm:relative sm:bottom-auto sm:left-auto sm:right-auto sm:p-0 sm:border-t-0 sm:bg-transparent fixed bottom-0 left-0 right-0 z-40 bg-slate-950/80 backdrop-blur-md p-4 border-t border-white/10 safe-bottom">
              <button
                type="button"
                onClick={goPrev}
                disabled={currentStep === 1}
                className="flex items-center gap-1.5 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3.5 sm:px-6 sm:py-3 text-xs sm:text-sm font-semibold text-slate-300 transition hover:bg-slate-900 disabled:opacity-30 disabled:cursor-not-allowed shadow-sm touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                aria-label="مرحله قبل"
              >
                <ChevronRightIcon className="h-4 w-4" />
                مرحله قبل
              </button>

              <div className="flex items-center gap-2">
                <span className="text-[11px] sm:text-xs text-slate-400 font-medium whitespace-nowrap">
                  {toPersianDigits(currentStep)}/{toPersianDigits(STEPS.length)}
                </span>
                 {isLastStep ? (
                   <button
                     type="submit"
                     disabled={submitting || drivers.length === 0}
                     className="flex items-center gap-1.5 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 px-4 py-3 sm:px-8 sm:py-3.5 text-xs sm:text-sm font-black text-slate-950 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-cyan-500/20 active:scale-[0.98] min-h-[44px] touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                     aria-label={isScheduled ? "ایجاد زمان‌بندی" : "ثبت و ارسال"}
                   >
                     {submitting ? (
                       <>
                         <div className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                         در حال ارسال...
                       </>
                     ) : (
                       <>
                         <CheckIcon className="h-4 w-4" />
                         {isScheduled ? "ایجاد زمان‌بندی" : "ثبت و ارسال"}
                       </>
                     )}
                   </button>
                 ) : (
                   <button
                     type="submit"
                     className="flex items-center gap-1.5 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-400 hover:to-blue-400 px-4 py-3 sm:px-7 sm:py-3.5 text-xs sm:text-sm font-black text-slate-950 transition-all shadow-lg shadow-cyan-500/20 active:scale-[0.98] touch-target focus:outline-none focus:ring-2 focus:ring-cyan-500"
                     aria-label="مرحله بعد"
                   >
                     مرحله بعد
                     <ChevronLeftIcon className="h-4 w-4" />
                   </button>
                 )}
              </div>
            </div>

            <div className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-400">
              <div className="h-1.5 w-1.5 rounded-full bg-cyan-400 pulse-dot" />
              <span>ربات اتوماسیون پس از ثبت، فرم UTCMS را با روش <strong className="text-cyan-400">utcms_direct</strong> پر می‌کند</span>
            </div>
          </form>
        </div>

        {showQuickAddDriver && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200"
            role="dialog"
            aria-modal="true"
            aria-label="ثبت سریع راننده جدید"
            onClick={() => setShowQuickAddDriver(false)}
          >
            <div
              className="w-full max-w-lg rounded-[2rem] border border-white/10 bg-slate-900 p-6 sm:p-8 shadow-2xl text-white relative overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-400">
                    <PlusIcon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-black">ثبت سریع راننده</h3>
                    <p className="text-xs text-slate-400">افزودن مستقیم راننده و اتصال به فرم بارنامه</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowQuickAddDriver(false)}
                  className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white transition"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              <form onSubmit={handleQuickAddDriver} className="mt-6 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="text-xs font-semibold text-slate-200">
                    <span className="mb-1.5 block">نام و نام خانوادگی <span className="text-rose-500">*</span></span>
                    <input
                      type="text"
                      required
                      placeholder="مثال: رضا احمدی"
                      value={quickDriverForm.full_name}
                      onChange={(e) => setQuickDriverForm((c) => ({ ...c, full_name: e.target.value }))}
                      className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-cyan-400 transition"
                    />
                  </label>

                  <label className="text-xs font-semibold text-slate-200">
                    <span className="mb-1.5 block">کد ملی (۱۰ رقم) <span className="text-rose-500">*</span></span>
                    <input
                      type="text"
                      required
                      maxLength={10}
                      placeholder="۱۰ رقم کد ملی"
                      value={quickDriverForm.driver_national_code}
                      onChange={(e) => setQuickDriverForm((c) => ({ ...c, driver_national_code: normalizeDigits(e.target.value) }))}
                      className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-cyan-400 transition dir-ltr text-right"
                    />
                  </label>

                  <label className="text-xs font-semibold text-slate-200">
                    <span className="mb-1.5 block">نام کاربری UTCMS <span className="text-rose-500">*</span></span>
                    <input
                      type="text"
                      required
                      placeholder="نام کاربری سامانه"
                      value={quickDriverForm.utcms_username}
                      onChange={(e) => setQuickDriverForm((c) => ({ ...c, utcms_username: e.target.value }))}
                      className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-cyan-400 transition dir-ltr text-right"
                    />
                  </label>

                  <label className="text-xs font-semibold text-slate-200">
                    <span className="mb-1.5 block">رمز عبور UTCMS <span className="text-rose-500">*</span></span>
                    <input
                      type="password"
                      required
                      placeholder="رمز ورود سامانه"
                      value={quickDriverForm.utcms_password}
                      onChange={(e) => setQuickDriverForm((c) => ({ ...c, utcms_password: e.target.value }))}
                      className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2.5 text-sm text-white outline-none focus:border-cyan-400 transition"
                    />
                  </label>
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-200">
                    <span className="mb-1.5 block">پلاک پیش‌فرض خودرو (اختیاری)</span>
                    <PlateInput
                      value={quickDriverForm.plate_number}
                      onChange={(val) => setQuickDriverForm((c) => ({ ...c, plate_number: val }))}
                    />
                  </label>
                </div>

                {quickAddError && (
                  <div className="rounded-xl bg-rose-500/10 border border-rose-500/20 p-3 text-xs font-bold text-rose-300">
                    {quickAddError}
                  </div>
                )}

                <div className="mt-6 flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowQuickAddDriver(false)}
                    className="rounded-xl border border-white/10 bg-slate-950 px-5 py-2.5 text-xs font-bold text-slate-300 hover:bg-slate-800 transition"
                  >
                    انصراف
                  </button>
                  <button
                    type="submit"
                    disabled={quickAddLoading}
                    className="rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-2.5 text-xs font-black transition disabled:opacity-50"
                  >
                    {quickAddLoading ? "در حال ثبت..." : "ثبت و انتخاب راننده"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </AppShell>
    </AuthGuard>
  );
}

