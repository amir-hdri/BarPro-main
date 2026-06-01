"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGuard } from "@/components/layout/AuthGuard";
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
            : {
                ...current,
                driver_national_code: driverList[0].driver_national_code,
              },
        );
      }
      setLoadingDrivers(false);
    }

    loadDrivers();
  }, [role]);

  const selectedDriver = useMemo(
    () =>
      drivers.find(
        (driver) => driver.driver_national_code === form.driver_national_code,
      ) || null,
    [drivers, form.driver_national_code],
  );

  const handleChange = (
    name: keyof WaybillFormValues,
    value: string | boolean,
  ) => {
    let nextValue = value;

    if (typeof nextValue === "string") {
      if (name === "plate_number") {
        nextValue = canonicalizePlate(nextValue);
      } else if (
        name === "driver_national_code" ||
        name === "driver_phone" ||
        name === "cargo_weight" ||
        name === "cargo_count" ||
        name === "cargo_value" ||
        name === "financial_cost" ||
        name === "sender_phone" ||
        name === "receiver_phone" ||
        name === "sender_national_code" ||
        name === "receiver_national_code"
      ) {
        nextValue = normalizeDigits(nextValue);
      }
    }

    setForm((current) => ({ ...current, [name]: nextValue }));
    setErrors((current) => {
      const next = { ...current };
      delete next[name];
      return next;
    });
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

    const cargoWeight = parsed.data.cargo_weight
      ? Number(parsed.data.cargo_weight)
      : undefined;
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
        sender: {
          name: parsed.data.sender_name,
          phone: parsed.data.sender_phone,
          national_code: parsed.data.sender_national_code,
          address: parsed.data.sender_address,
        },
        receiver: {
          name: parsed.data.receiver_name,
          phone: parsed.data.receiver_phone,
          national_code: parsed.data.receiver_national_code,
          address: parsed.data.receiver_address,
        },
        origin: {
          province: parsed.data.origin_province,
          city: parsed.data.origin,
          district: parsed.data.origin_district || undefined,
          address: parsed.data.origin_address,
        },
        destination: {
          province: parsed.data.destination_province,
          city: parsed.data.destination,
          district: parsed.data.destination_district || undefined,
          address: parsed.data.destination_address,
        },
        cargo: {
          type: parsed.data.cargo_type,
          weight: parsed.data.cargo_weight,
          count: parsed.data.cargo_count,
          description: parsed.data.cargo_description,
          value: parsed.data.cargo_value,
        },
        vehicle: {
          driver_national_code: parsed.data.driver_national_code,
          driver_phone: parsed.data.driver_phone,
          plate: parsed.data.plate_number,
          type: parsed.data.vehicle_type,
        },
        financial: {
          cost: parsed.data.financial_cost,
          payment_method: parsed.data.financial_payment_method,
          cargo_value: parsed.data.cargo_value,
        },
        shipping_options: {
          two_way: parsed.data.shipping_two_way,
          time_limit: parsed.data.shipping_time_limit,
          end_shipping: parsed.data.shipping_end_shipping || undefined,
          otp: parsed.data.shipping_otp || undefined,
          waybill_number: parsed.data.waybill_number,
        },
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

    setServerMessage(
      `کار با شناسه ${response.data.job_id} ساخته شد و به صف رفت.`,
    );
    setTimeout(() => {
      router.push("/history");
      router.refresh();
    }, 1200);
  };

  return (
    <AppShell>
      <AuthGuard requiredRole="client">
        <section className="grid gap-8 xl:grid-cols-[0.78fr_1.22fr]">
          <aside className="space-y-6">
            <div className="relative overflow-hidden rounded-[40px] border border-slate-200 bg-slate-950 p-8 text-white shadow-2xl shadow-slate-900/10">
              <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-cyan-500/10 blur-[80px]"></div>
              <div className="relative z-10">
                <h1 className="text-3xl font-black">ثبت ماموریت</h1>
                <p className="mt-4 text-base leading-relaxed text-slate-400">
                  درج اطلاعات دقیق ناوگان و محموله جهت پردازش هوشمند توسط ربات‌های اتوماسیون.
                </p>
              </div>
            </div>

            <div className="mt-6 rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300">
              <p className="font-medium text-white">راننده انتخاب‌شده</p>
              {loadingDrivers ? (
                <p className="mt-2">در حال بارگذاری...</p>
              ) : selectedDriver ? (
                <div className="mt-2 space-y-1">
                  <p>{selectedDriver.full_name}</p>
                  <p className="text-slate-400">
                    {selectedDriver.driver_national_code} -{" "}
                    {selectedDriver.utcms_username}
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-amber-200">ابتدا یک راننده ثبت کنید.</p>
              )}
            </div>

            <div className="rounded-[32px] border border-white/20 bg-white/80 p-6 shadow-lg shadow-slate-900/5 backdrop-blur">
              <h2 className="text-lg font-semibold text-slate-950">
                چک‌لیست قبل از ثبت
              </h2>
              <div className="mt-4 space-y-3 text-sm text-slate-600">
                <p>۱. راننده باید قبلا در بخش رانندگان ایجاد شده باشد.</p>
                <p>۲. مبدا و مقصد به صورت متنی و واضح ثبت شوند.</p>
                <p>
                  ۳. در صورت نیاز به OTP بعدی، وضعیت کار در تاریخچه قابل مشاهده است.
                </p>
              </div>
            </div>
          </aside>

          <form
            onSubmit={handleSubmit}
            className="rounded-[32px] border border-white/20 bg-white/80 p-6 shadow-lg shadow-slate-900/5 backdrop-blur"
          >
            <div className="grid gap-6 lg:grid-cols-2">
              <Field
                label="راننده"
                error={errors.driver_national_code}
                required
              >
                <select
                  value={form.driver_national_code}
                  onChange={(event) =>
                    handleChange("driver_national_code", event.target.value)
                  }
                  className="field"
                >
                  <option value="">انتخاب راننده</option>
                  {drivers.map((driver) => (
                    <option key={driver.id} value={driver.driver_national_code}>
                      {driver.full_name} - {driver.driver_national_code}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                label="پلاک خودرو"
                error={errors.plate_number}
                hint="فرمت: ۱۲ب۳۴۵ایران۶۷"
                required
              >
                <input
                  dir="ltr"
                  className="field"
                  placeholder="12ب345ایران67"
                  value={form.plate_number}
                  onChange={(event) =>
                    handleChange("plate_number", event.target.value)
                  }
                />
              </Field>

              <Field label="شهر مبدا" error={errors.origin} required>
                <input
                  className="field"
                  value={form.origin}
                  onChange={(event) =>
                    handleChange("origin", event.target.value)
                  }
                />
              </Field>

              <Field label="استان مبدا" error={errors.origin_province} required>
                <input
                  className="field"
                  value={form.origin_province}
                  onChange={(event) =>
                    handleChange("origin_province", event.target.value)
                  }
                />
              </Field>

              <Field label="آدرس مبدا" error={errors.origin_address} required>
                <input
                  className="field"
                  value={form.origin_address}
                  onChange={(event) =>
                    handleChange("origin_address", event.target.value)
                  }
                />
              </Field>

              <Field label="ناحیه مبدا" error={errors.origin_district}>
                <input
                  className="field"
                  value={form.origin_district}
                  onChange={(event) =>
                    handleChange("origin_district", event.target.value)
                  }
                />
              </Field>

              <Field label="شهر مقصد" error={errors.destination} required>
                <input
                  className="field"
                  value={form.destination}
                  onChange={(event) =>
                    handleChange("destination", event.target.value)
                  }
                />
              </Field>

              <Field
                label="استان مقصد"
                error={errors.destination_province}
                required
              >
                <input
                  className="field"
                  value={form.destination_province}
                  onChange={(event) =>
                    handleChange("destination_province", event.target.value)
                  }
                />
              </Field>

              <Field
                label="آدرس مقصد"
                error={errors.destination_address}
                required
              >
                <input
                  className="field"
                  value={form.destination_address}
                  onChange={(event) =>
                    handleChange("destination_address", event.target.value)
                  }
                />
              </Field>

              <Field label="ناحیه مقصد" error={errors.destination_district}>
                <input
                  className="field"
                  value={form.destination_district}
                  onChange={(event) =>
                    handleChange("destination_district", event.target.value)
                  }
                />
              </Field>

              <Field label="نام فرستنده" error={errors.sender_name} required>
                <input
                  className="field"
                  value={form.sender_name}
                  onChange={(event) =>
                    handleChange("sender_name", event.target.value)
                  }
                />
              </Field>

              <Field label="تلفن فرستنده" error={errors.sender_phone} required>
                <input
                  dir="ltr"
                  className="field"
                  placeholder="09120000000"
                  value={form.sender_phone}
                  onChange={(event) =>
                    handleChange("sender_phone", event.target.value)
                  }
                />
              </Field>

              <Field
                label="کد ملی فرستنده"
                error={errors.sender_national_code}
                required
              >
                <input
                  dir="ltr"
                  className="field"
                  value={form.sender_national_code}
                  onChange={(event) =>
                    handleChange("sender_national_code", event.target.value)
                  }
                />
              </Field>

              <Field
                label="آدرس فرستنده"
                error={errors.sender_address}
                required
              >
                <input
                  className="field"
                  value={form.sender_address}
                  onChange={(event) =>
                    handleChange("sender_address", event.target.value)
                  }
                />
              </Field>

              <Field label="نام گیرنده" error={errors.receiver_name} required>
                <input
                  className="field"
                  value={form.receiver_name}
                  onChange={(event) =>
                    handleChange("receiver_name", event.target.value)
                  }
                />
              </Field>

              <Field label="تلفن گیرنده" error={errors.receiver_phone} required>
                <input
                  dir="ltr"
                  className="field"
                  placeholder="09120000000"
                  value={form.receiver_phone}
                  onChange={(event) =>
                    handleChange("receiver_phone", event.target.value)
                  }
                />
              </Field>

              <Field
                label="کد ملی گیرنده"
                error={errors.receiver_national_code}
                required
              >
                <input
                  dir="ltr"
                  className="field"
                  value={form.receiver_national_code}
                  onChange={(event) =>
                    handleChange("receiver_national_code", event.target.value)
                  }
                />
              </Field>

              <Field
                label="آدرس گیرنده"
                error={errors.receiver_address}
                required
              >
                <input
                  className="field"
                  value={form.receiver_address}
                  onChange={(event) =>
                    handleChange("receiver_address", event.target.value)
                  }
                />
              </Field>

              <Field label="نوع بار" error={errors.cargo_type} required>
                <input
                  className="field"
                  value={form.cargo_type}
                  onChange={(event) =>
                    handleChange("cargo_type", event.target.value)
                  }
                />
              </Field>

              <Field
                label="وزن بار"
                error={errors.cargo_weight}
                hint="مثال: 3 یا 3.5"
                required
              >
                <input
                  dir="ltr"
                  className="field"
                  value={form.cargo_weight}
                  onChange={(event) =>
                    handleChange("cargo_weight", event.target.value)
                  }
                />
              </Field>

              <Field label="تعداد" error={errors.cargo_count} required>
                <input
                  dir="ltr"
                  className="field"
                  value={form.cargo_count}
                  onChange={(event) =>
                    handleChange("cargo_count", event.target.value)
                  }
                />
              </Field>

              <Field label="ارزش بار" error={errors.cargo_value} required>
                <input
                  dir="ltr"
                  className="field"
                  value={form.cargo_value}
                  onChange={(event) =>
                    handleChange("cargo_value", event.target.value)
                  }
                />
              </Field>

              <Field label="نوع خودرو" error={errors.vehicle_type} required>
                <input
                  className="field"
                  value={form.vehicle_type}
                  onChange={(event) =>
                    handleChange("vehicle_type", event.target.value)
                  }
                />
              </Field>

              <Field label="تلفن راننده" error={errors.driver_phone} required>
                <input
                  dir="ltr"
                  className="field"
                  placeholder="09333702137"
                  value={form.driver_phone}
                  onChange={(event) =>
                    handleChange("driver_phone", event.target.value)
                  }
                />
              </Field>

              <Field label="هزینه حمل" error={errors.financial_cost} required>
                <input
                  dir="ltr"
                  className="field"
                  value={form.financial_cost}
                  onChange={(event) =>
                    handleChange("financial_cost", event.target.value)
                  }
                />
              </Field>

              <Field
                label="روش پرداخت"
                error={errors.financial_payment_method}
                required
              >
                <input
                  className="field"
                  value={form.financial_payment_method}
                  onChange={(event) =>
                    handleChange("financial_payment_method", event.target.value)
                  }
                />
              </Field>

              <Field
                label="مهلت زمانی"
                error={errors.shipping_time_limit}
                hint="مثال: 120 دقیقه"
                required
              >
                <input
                  className="field"
                  value={form.shipping_time_limit}
                  onChange={(event) =>
                    handleChange("shipping_time_limit", event.target.value)
                  }
                />
              </Field>

              <Field
                label="شماره بارنامه"
                error={errors.waybill_number}
                required
              >
                <input
                  dir="ltr"
                  className="field"
                  value={form.waybill_number}
                  onChange={(event) =>
                    handleChange("waybill_number", event.target.value)
                  }
                />
              </Field>
            </div>

            <div className="mt-6 grid gap-6">
              <Field label="شرح بار" error={errors.cargo_description} required>
                <textarea
                  className="field min-h-28"
                  value={form.cargo_description}
                  onChange={(event) =>
                    handleChange("cargo_description", event.target.value)
                  }
                />
              </Field>

              <Field label="توضیحات" error={errors.notes} required>
                <textarea
                  className="field min-h-24"
                  value={form.notes}
                  onChange={(event) =>
                    handleChange("notes", event.target.value)
                  }
                />
              </Field>

              <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={form.shipping_two_way}
                  onChange={(event) =>
                    handleChange("shipping_two_way", event.target.checked)
                  }
                />
                ثبت حمل رفت و برگشت
              </label>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 pt-6">
              <p className="text-sm text-slate-500">
                پس از ثبت، کار در صف قرار می‌گیرد و از صفحه پیگیری می‌توانید
                وضعیت را مشاهده کنید.
              </p>

              <button
                type="submit"
                disabled={submitting || drivers.length === 0}
                className="rounded-2xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60"
              >
                {submitting
                  ? "در حال ایجاد کار..."
                  : `ثبت و ارسال به صف (${toPersianDigits(drivers.length)} راننده)`}
              </button>
            </div>

            {serverError && (
              <p className="mt-4 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {serverError}
              </p>
            )}

            {serverMessage && (
              <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {serverMessage}
              </p>
            )}
          </form>
        </section>
      </AuthGuard>
    </AppShell>
  );
}

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
    <label className="block text-sm font-medium text-slate-700">
      <span className="mb-2 block">
        {label}
        {required ? <span className="mr-1 text-rose-600">*</span> : null}
      </span>
      {children}
      {hint && !error && (
        <span className="mt-2 block text-xs text-slate-500">{hint}</span>
      )}
      {error && (
        <span className="mt-2 block text-xs text-rose-600">{error}</span>
      )}
    </label>
  );
}
