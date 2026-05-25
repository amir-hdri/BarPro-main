"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import axios, { isAxiosError } from "axios";
import {
  AlertCircle,
  BarChart,
  CheckCircle,
  Edit,
  FileText,
  MapPin,
  Menu,
  Moon,
  Package,
  RefreshCw,
  Settings,
  Sun,
  UploadCloud,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEFAULT_API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";
const API_KEY_STORAGE = "utcms_sensitive_api_key";

type NavTab =
  | "waybill-form"
  | "manual-entry"
  | "excel-upload"
  | "map-tools"
  | "reports-tools"
  | "management-tools";

type RequestState = "idle" | "loading" | "success" | "error";

type JsonRecord = Record<string, unknown>;

interface WaybillFormData {
  senderName: string;
  senderPhone: string;
  senderAddress: string;
  senderNationalCode: string;
  receiverName: string;
  receiverPhone: string;
  receiverAddress: string;
  receiverNationalCode: string;
  originProvince: string;
  originCity: string;
  originDistrict: string;
  originAddress: string;
  destinationProvince: string;
  destinationCity: string;
  destinationDistrict: string;
  destinationAddress: string;
  cargoType: string;
  cargoWeight: string;
  cargoCount: string;
  cargoDescription: string;
  vehiclePlate: string;
  vehicleType: string;
  driverNationalCode: string;
  driverPhone: string;
  financialCost: string;
  paymentMethod: string;
  operationMode: "safe" | "full";
  twoWay: boolean;
  timeLimit: string;
  notes: string;
}

const initialWaybillForm: WaybillFormData = {
  senderName: "",
  senderPhone: "",
  senderAddress: "",
  senderNationalCode: "",
  receiverName: "",
  receiverPhone: "",
  receiverAddress: "",
  receiverNationalCode: "",
  originProvince: "",
  originCity: "",
  originDistrict: "",
  originAddress: "",
  destinationProvince: "",
  destinationCity: "",
  destinationDistrict: "",
  destinationAddress: "",
  cargoType: "",
  cargoWeight: "",
  cargoCount: "1",
  cargoDescription: "",
  vehiclePlate: "",
  vehicleType: "",
  driverNationalCode: "",
  driverPhone: "",
  financialCost: "",
  paymentMethod: "",
  operationMode: "safe",
  twoWay: false,
  timeLimit: "",
  notes: "",
};

function getStoredApiKey(): string {
  if (typeof window === "undefined") {
    return DEFAULT_API_KEY;
  }
  return window.localStorage.getItem(API_KEY_STORAGE) || DEFAULT_API_KEY;
}

function extractErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: string }).message;
      if (typeof message === "string") {
        return message;
      }
    }
    const message = error.response?.data?.message;
    if (typeof message === "string") {
      return message;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "خطا در ارتباط با سرور";
}

function buildHeaders(apiKey: string): Record<string, string> {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

function buildWaybillPayload(form: WaybillFormData): JsonRecord {
  return {
    operation_mode: form.operationMode,
    priority: 5,
    sender: {
      name: form.senderName,
      phone: form.senderPhone,
      address: form.senderAddress,
      national_code: form.senderNationalCode,
    },
    receiver: {
      name: form.receiverName,
      phone: form.receiverPhone,
      address: form.receiverAddress,
      national_code: form.receiverNationalCode || undefined,
    },
    origin: {
      province: form.originProvince,
      city: form.originCity,
      district: form.originDistrict || undefined,
      address: form.originAddress,
    },
    destination: {
      province: form.destinationProvince,
      city: form.destinationCity,
      district: form.destinationDistrict || undefined,
      address: form.destinationAddress,
    },
    cargo: {
      type: form.cargoType || undefined,
      weight: form.cargoWeight,
      count: form.cargoCount || "1",
      description: form.cargoDescription || undefined,
    },
    vehicle: {
      driver_national_code: form.driverNationalCode || undefined,
      driver_phone: form.driverPhone || undefined,
      plate: form.vehiclePlate || undefined,
      type: form.vehicleType || undefined,
    },
    financial: {
      cost: form.financialCost || undefined,
      payment_method: form.paymentMethod || undefined,
    },
    shipping_options: {
      two_way: form.twoWay,
      time_limit: form.timeLimit ? Number(form.timeLimit) : undefined,
    },
    notes: form.notes || undefined,
  };
}

export default function Home() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<NavTab>("waybill-form");
  const [isDark, setIsDark] = useState(true);
  const [apiKey, setApiKey] = useState(getStoredApiKey);
  const [healthStatus, setHealthStatus] = useState("در حال بررسی...");
  const [readyStatus, setReadyStatus] = useState("در حال بررسی...");
  const [queueStatus, setQueueStatus] = useState("0");
  const [activeStatus, setActiveStatus] = useState("0");
  const [authMode, setAuthMode] = useState("در حال بررسی...");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.classList.toggle("light", !isDark);
  }, [isDark]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(API_KEY_STORAGE, apiKey);
    }
  }, [apiKey]);

  const checkStatus = useCallback(async () => {
    try {
      setStatusMessage(null);
      setHealthStatus("بررسی...");
      setReadyStatus("بررسی...");

      const [healthRes, readyRes, authRes] = await Promise.all([
        axios.get(`${API_URL}/healthz`),
        axios.get(`${API_URL}/readyz`),
        axios.get(`${API_URL}/auth-config`),
      ]);

      setHealthStatus(healthRes.data.status === "ok" ? "سالم" : "خطا");
      setReadyStatus(readyRes.data.status === "ok" ? "آماده" : "خطا");
      setAuthMode(String(authRes.data.mode || "نامشخص"));

      if (apiKey) {
        const trafficRes = await axios.get(`${API_URL}/waybill/traffic-status`, {
          headers: buildHeaders(apiKey),
        });
        setQueueStatus(String(trafficRes.data.queued_requests ?? 0));
        setActiveStatus(String(trafficRes.data.active_requests ?? 0));
      } else {
        setQueueStatus("-");
        setActiveStatus("-");
        setStatusMessage("برای دیدن آمار صف و استفاده از endpointهای حساس، API Key را وارد کنید.");
      }
    } catch (error) {
      setHealthStatus("خطا در ارتباط");
      setReadyStatus("خطا در ارتباط");
      setQueueStatus("-");
      setActiveStatus("-");
      setStatusMessage(extractErrorMessage(error));
    }
  }, [apiKey]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void checkStatus();
    }, 0);
    const interval = window.setInterval(() => {
      void checkStatus();
    }, 30000);
    return () => {
      window.clearTimeout(timeoutId);
      window.clearInterval(interval);
    };
  }, [checkStatus]);

  const navItems: Array<{ id: NavTab; label: string; icon: typeof FileText }> = [
    { id: "waybill-form", label: "ثبت در صف", icon: FileText },
    { id: "manual-entry", label: "ثبت مستقیم", icon: Edit },
    { id: "excel-upload", label: "آپلود اکسل", icon: UploadCloud },
    { id: "map-tools", label: "نقشه و مسیر", icon: MapPin },
    { id: "reports-tools", label: "گزارش‌ها", icon: BarChart },
    { id: "management-tools", label: "مدیریت حرفه‌ای", icon: Settings },
  ];

  const statusCards = useMemo(
    () => [
      {
        title: "سلامت سیستم",
        value: healthStatus,
        color: healthStatus === "سالم" ? "text-emerald-400" : "text-red-400",
      },
      {
        title: "آمادگی سرویس",
        value: readyStatus,
        color: readyStatus === "آماده" ? "text-sky-400" : "text-orange-400",
      },
      {
        title: "عملیات فعال",
        value: activeStatus,
        color: "text-violet-400",
      },
      {
        title: "صف انتظار",
        value: queueStatus,
        color: "text-amber-400",
      },
    ],
    [activeStatus, healthStatus, queueStatus, readyStatus],
  );

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <AnimatePresence>
        {isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      <aside
        className={`fixed inset-y-0 right-0 z-50 flex h-full w-80 transform flex-col border-l border-white/10 glass-panel transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          isSidebarOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex-1 overflow-y-auto p-6 no-scrollbar">
          <div className="mb-8 flex items-center justify-between border-b border-white/10 pb-6">
            <div className="flex items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-amber-400 shadow-lg shadow-cyan-500/20">
                <Package className="h-6 w-6 text-slate-950" />
              </div>
              <div>
                <h2 className="bg-gradient-to-r from-cyan-300 to-amber-300 bg-clip-text text-xl font-bold text-transparent">
                  UTCMS Console
                </h2>
                <p className="text-xs text-slate-400">پنل عملیات واقعی بارنامه</p>
              </div>
            </div>
            <button className="text-slate-400 hover:text-white lg:hidden" onClick={() => setIsSidebarOpen(false)}>
              <X size={24} />
            </button>
          </div>

          <div className="mb-6 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">
            <label className="mb-2 block text-xs font-medium text-slate-300">API Key حساس</label>
            <input
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              dir="ltr"
              placeholder="X-API-Key برای endpointهای حساس"
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400"
            />
            <p className="mt-2 text-xs leading-5 text-slate-400">وضعیت auth backend: <span className="font-semibold text-slate-200">{authMode}</span></p>
          </div>

          <nav className="flex flex-col gap-2">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  if (window.innerWidth < 1024) {
                    setIsSidebarOpen(false);
                  }
                }}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3.5 text-sm transition-all duration-200 ${
                  activeTab === item.id
                    ? "bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950 shadow-lg shadow-cyan-500/20 font-semibold"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`}
              >
                <item.icon size={20} className={activeTab === item.id ? "text-slate-950" : "text-slate-400"} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="glass-panel z-10 mx-4 mt-4 flex shrink-0 flex-col items-center justify-between gap-4 rounded-2xl p-4 lg:mx-6 lg:mt-6 sm:flex-row">
          <div className="flex w-full items-center gap-4 sm:w-auto">
            <button
              className="rounded-xl border border-white/10 bg-white/5 p-2 text-slate-300 transition-colors hover:bg-white/10 lg:hidden"
              onClick={() => setIsSidebarOpen(true)}
            >
              <Menu size={24} />
            </button>
            <div>
              <h1 className="text-xl font-bold text-slate-100">داشبورد کنترل UTCMS</h1>
              <p className="hidden text-xs text-slate-400 sm:block">از این صفحه می‌توانید endpointهای اصلی سیستم را بدون placeholder اجرا و بررسی کنید.</p>
            </div>
          </div>
          <div className="flex w-full items-center justify-end gap-2 sm:w-auto sm:gap-3">
            <button
              onClick={() => setIsDark((current) => !current)}
              className="rounded-xl border border-white/10 bg-slate-800/50 p-2.5 text-slate-300 transition-all hover:bg-white/5"
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              onClick={() => void checkStatus()}
              className="flex items-center gap-2 rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-3 py-2.5 text-sm text-cyan-300 transition-all hover:bg-cyan-500/20 sm:px-4"
            >
              <RefreshCw size={18} />
              <span className="hidden sm:inline">بروزرسانی</span>
            </button>
            <button className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-3 py-2.5 text-sm text-emerald-300 transition-all hover:bg-emerald-500/20 sm:px-4">
              <CheckCircle size={18} />
              <span className="hidden sm:inline">اتصال</span>
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 pb-24 lg:p-6 no-scrollbar">
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {statusCards.map((card) => (
              <StatusCard key={card.title} title={card.title} value={card.value} color={card.color} />
            ))}
          </div>

          {statusMessage && (
            <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-amber-300">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <p className="text-sm leading-6">{statusMessage}</p>
            </div>
          )}

          <div className="glass-panel min-h-[560px] overflow-hidden rounded-2xl p-6 sm:p-8">
            {activeTab === "waybill-form" && <WaybillActionView apiKey={apiKey} mode="queue" />}
            {activeTab === "manual-entry" && <WaybillActionView apiKey={apiKey} mode="direct" />}
            {activeTab === "excel-upload" && <ExcelUploadView apiKey={apiKey} />}
            {activeTab === "map-tools" && <MapToolsView />}
            {activeTab === "reports-tools" && <ReportsView apiKey={apiKey} />}
            {activeTab === "management-tools" && <ManagementView apiKey={apiKey} />}
          </div>
        </div>
      </main>
    </div>
  );
}

function StatusCard({ title, value, color }: { title: string; value: string; color: string }) {
  return (
    <div className="glass-panel rounded-2xl p-5 text-center transition-transform duration-300 hover:-translate-y-1">
      <h3 className="mb-2 text-sm text-slate-400">{title}</h3>
      <div className={`text-lg font-bold sm:text-2xl ${color}`}>{value}</div>
    </div>
  );
}

function WaybillActionView({ apiKey, mode }: { apiKey: string; mode: "queue" | "direct" }) {
  const [form, setForm] = useState<WaybillFormData>(initialWaybillForm);
  const [status, setStatus] = useState<RequestState>("idle");
  const [message, setMessage] = useState("");
  const [responseBody, setResponseBody] = useState<JsonRecord | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");
    setMessage("");
    setResponseBody(null);

    try {
      const endpoint = mode === "queue" ? "/waybill/queue/create-with-map" : "/waybill/submit-manual-waybill";
      const response = await axios.post(`${API_URL}${endpoint}`, buildWaybillPayload(form), {
        headers: buildHeaders(apiKey),
      });
      setStatus("success");
      setResponseBody(response.data as JsonRecord);
      setMessage(mode === "queue" ? "درخواست با موفقیت در صف ثبت شد." : "بارنامه با موفقیت به سرویس ثبت مستقیم ارسال شد.");
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error));
    }
  }

  return (
    <ViewShell
      title={mode === "queue" ? "ثبت بارنامه و ارسال به صف" : "ثبت مستقیم بارنامه"}
      description={
        mode === "queue"
          ? "این بخش endpoint واقعی `/waybill/queue/create-with-map` را صدا می‌زند و در صورت موفقیت `task_id` برمی‌گرداند."
          : "این بخش endpoint واقعی `/waybill/submit-manual-waybill` را صدا می‌زند و نتیجه ثبت را همان‌جا برمی‌گرداند."
      }
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <WaybillFields form={form} setForm={setForm} />
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <p className="text-sm leading-6 text-slate-400">برای این عملیات API Key لازم است؛ در صورت خالی بودن، backend پاسخ 401 می‌دهد.</p>
          <button
            type="submit"
            disabled={status === "loading"}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-5 py-3 font-medium text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:opacity-90 disabled:opacity-60"
          >
            {status === "loading" ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
            {mode === "queue" ? "ثبت در صف" : "ثبت مستقیم"}
          </button>
        </div>
      </form>

      <RequestFeedback status={status} message={message} />
      {responseBody && <JsonPreview data={responseBody} />}
    </ViewShell>
  );
}

function WaybillFields({ form, setForm }: { form: WaybillFormData; setForm: React.Dispatch<React.SetStateAction<WaybillFormData>> }) {
  function updateField<K extends keyof WaybillFormData>(key: K, value: WaybillFormData[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <InputGroup label="نام فرستنده" value={form.senderName} onChange={(value) => updateField("senderName", value)} />
        <InputGroup label="تلفن فرستنده" value={form.senderPhone} onChange={(value) => updateField("senderPhone", value)} dir="ltr" />
        <InputGroup label="کد ملی فرستنده" value={form.senderNationalCode} onChange={(value) => updateField("senderNationalCode", value)} dir="ltr" />
        <InputGroup label="آدرس فرستنده" value={form.senderAddress} onChange={(value) => updateField("senderAddress", value)} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <InputGroup label="نام گیرنده" value={form.receiverName} onChange={(value) => updateField("receiverName", value)} />
        <InputGroup label="تلفن گیرنده" value={form.receiverPhone} onChange={(value) => updateField("receiverPhone", value)} dir="ltr" />
        <InputGroup label="کد ملی گیرنده" value={form.receiverNationalCode} onChange={(value) => updateField("receiverNationalCode", value)} dir="ltr" required={false} />
        <InputGroup label="آدرس گیرنده" value={form.receiverAddress} onChange={(value) => updateField("receiverAddress", value)} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        <InputGroup label="استان مبدا" value={form.originProvince} onChange={(value) => updateField("originProvince", value)} />
        <InputGroup label="شهر مبدا" value={form.originCity} onChange={(value) => updateField("originCity", value)} />
        <InputGroup label="ناحیه مبدا" value={form.originDistrict} onChange={(value) => updateField("originDistrict", value)} required={false} />
        <InputGroup label="آدرس مبدا" value={form.originAddress} onChange={(value) => updateField("originAddress", value)} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        <InputGroup label="استان مقصد" value={form.destinationProvince} onChange={(value) => updateField("destinationProvince", value)} />
        <InputGroup label="شهر مقصد" value={form.destinationCity} onChange={(value) => updateField("destinationCity", value)} />
        <InputGroup label="ناحیه مقصد" value={form.destinationDistrict} onChange={(value) => updateField("destinationDistrict", value)} required={false} />
        <InputGroup label="آدرس مقصد" value={form.destinationAddress} onChange={(value) => updateField("destinationAddress", value)} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        <InputGroup label="نوع بار" value={form.cargoType} onChange={(value) => updateField("cargoType", value)} required={false} />
        <InputGroup label="وزن بار" value={form.cargoWeight} onChange={(value) => updateField("cargoWeight", value)} type="number" dir="ltr" />
        <InputGroup label="تعداد" value={form.cargoCount} onChange={(value) => updateField("cargoCount", value)} type="number" dir="ltr" />
        <InputGroup label="شرح بار" value={form.cargoDescription} onChange={(value) => updateField("cargoDescription", value)} required={false} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        <InputGroup label="پلاک خودرو" value={form.vehiclePlate} onChange={(value) => updateField("vehiclePlate", value)} required={false} />
        <InputGroup label="نوع خودرو" value={form.vehicleType} onChange={(value) => updateField("vehicleType", value)} required={false} />
        <InputGroup label="کد ملی راننده" value={form.driverNationalCode} onChange={(value) => updateField("driverNationalCode", value)} dir="ltr" required={false} />
        <InputGroup label="تلفن راننده" value={form.driverPhone} onChange={(value) => updateField("driverPhone", value)} dir="ltr" required={false} />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-4">
        <InputGroup label="هزینه حمل" value={form.financialCost} onChange={(value) => updateField("financialCost", value)} type="number" dir="ltr" required={false} />
        <InputGroup label="روش پرداخت" value={form.paymentMethod} onChange={(value) => updateField("paymentMethod", value)} required={false} />
        <InputGroup label="مهلت زمانی (دقیقه)" value={form.timeLimit} onChange={(value) => updateField("timeLimit", value)} type="number" dir="ltr" required={false} />
        <SelectGroup
          label="حالت عملیات"
          value={form.operationMode}
          onChange={(value) => updateField("operationMode", value as WaybillFormData["operationMode"])}
          options={[
            { label: "ایمن", value: "safe" },
            { label: "کامل", value: "full" },
          ]}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <label className="block text-sm font-medium text-slate-300">
          <span className="mb-1.5 block">یادداشت‌ها</span>
          <textarea
            value={form.notes}
            onChange={(event) => updateField("notes", event.target.value)}
            className="min-h-24 w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400"
          />
        </label>
        <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 px-4 py-3 text-sm text-slate-300">
          <input type="checkbox" checked={form.twoWay} onChange={(event) => updateField("twoWay", event.target.checked)} />
          ثبت رفت و برگشت
        </label>
      </div>
    </>
  );
}

function ExcelUploadView({ apiKey }: { apiKey: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"safe" | "full">("safe");
  const [skipInvalid, setSkipInvalid] = useState(true);
  const [status, setStatus] = useState<RequestState>("idle");
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<JsonRecord | null>(null);

  async function submit(endpoint: "/waybill/parse-excel" | "/waybill/submit-excel-waybills") {
    if (!file) {
      setStatus("error");
      setMessage("ابتدا فایل اکسل را انتخاب کنید.");
      return;
    }

    setStatus("loading");
    setMessage("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("operation_mode", mode);
      if (endpoint === "/waybill/submit-excel-waybills") {
        formData.append("skip_invalid", String(skipInvalid));
      }

      const response = await axios.post(`${API_URL}${endpoint}`, formData, {
        headers: {
          ...buildHeaders(apiKey),
          "Content-Type": "multipart/form-data",
        },
      });
      setStatus("success");
      setMessage(endpoint === "/waybill/parse-excel" ? "پیش‌نمایش فایل با موفقیت انجام شد." : "بارنامه‌های اکسل با موفقیت پردازش شدند.");
      setResult(response.data as JsonRecord);
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error));
    }
  }

  return (
    <ViewShell title="آپلود و پردازش اکسل" description="پیش‌نمایش و ثبت گروهی فایل اکسل از endpointهای واقعی `/waybill/parse-excel` و `/waybill/submit-excel-waybills`.">
      <div className="grid gap-5 lg:grid-cols-3">
        <label className="block text-sm font-medium text-slate-300 lg:col-span-2">
          <span className="mb-1.5 block">فایل اکسل</span>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="w-full rounded-xl border border-dashed border-white/20 bg-slate-900/40 px-4 py-4 text-sm text-slate-200"
          />
        </label>
        <SelectGroup
          label="حالت عملیات"
          value={mode}
          onChange={(value) => setMode(value as "safe" | "full")}
          options={[
            { label: "ایمن", value: "safe" },
            { label: "کامل", value: "full" },
          ]}
        />
      </div>

      <label className="mt-4 flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/30 px-4 py-3 text-sm text-slate-300">
        <input type="checkbox" checked={skipInvalid} onChange={(event) => setSkipInvalid(event.target.checked)} />
        ردیف‌های نامعتبر رد شوند
      </label>

      <div className="mt-6 flex flex-wrap gap-3">
        <button onClick={() => void submit("/waybill/parse-excel")} className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-300 transition hover:bg-cyan-500/20">
          پیش‌نمایش فایل
        </button>
        <button onClick={() => void submit("/waybill/submit-excel-waybills")} className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-3 text-sm font-medium text-slate-950 transition hover:opacity-90">
          پردازش و ثبت گروهی
        </button>
      </div>

      <RequestFeedback status={status} message={message} />
      {result && <JsonPreview data={result} />}
    </ViewShell>
  );
}

function MapToolsView() {
  const [routeStatus, setRouteStatus] = useState<RequestState>("idle");
  const [geoStatus, setGeoStatus] = useState<RequestState>("idle");
  const [routeResult, setRouteResult] = useState<JsonRecord | null>(null);
  const [geoResult, setGeoResult] = useState<JsonRecord | null>(null);
  const [routeMessage, setRouteMessage] = useState("");
  const [geoMessage, setGeoMessage] = useState("");
  const [routeForm, setRouteForm] = useState({ originLat: "35.6892", originLng: "51.3890", destLat: "32.6546", destLng: "51.6680" });
  const [geoForm, setGeoForm] = useState({ lat: "35.6892", lng: "51.3890" });

  async function calculateRoute() {
    setRouteStatus("loading");
    setRouteMessage("");
    setRouteResult(null);
    try {
      const response = await axios.post(`${API_URL}/waybill/calculate-route`, {
        origin: { lat: Number(routeForm.originLat), lng: Number(routeForm.originLng) },
        destination: { lat: Number(routeForm.destLat), lng: Number(routeForm.destLng) },
      });
      setRouteStatus("success");
      setRouteResult(response.data as JsonRecord);
      setRouteMessage("مسیر با موفقیت محاسبه شد.");
    } catch (error) {
      setRouteStatus("error");
      setRouteMessage(extractErrorMessage(error));
    }
  }

  async function reverseGeocode() {
    setGeoStatus("loading");
    setGeoMessage("");
    setGeoResult(null);
    try {
      const response = await axios.get(`${API_URL}/waybill/reverse-geocode`, {
        params: { lat: Number(geoForm.lat), lng: Number(geoForm.lng) },
      });
      setGeoStatus("success");
      setGeoResult(response.data as JsonRecord);
      setGeoMessage("آدرس تقریبی مختصات دریافت شد.");
    } catch (error) {
      setGeoStatus("error");
      setGeoMessage(extractErrorMessage(error));
    }
  }

  return (
    <ViewShell title="ابزارهای نقشه و مسیر" description="این بخش placeholder نیست؛ محاسبه مسیر و reverse geocode را از endpointهای واقعی backend انجام می‌دهد.">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-white/10 bg-slate-900/30 p-5">
          <h3 className="mb-4 text-lg font-semibold text-slate-100">محاسبه فاصله و زمان</h3>
          <div className="grid grid-cols-2 gap-4">
            <InputGroup label="عرض مبدا" value={routeForm.originLat} onChange={(value) => setRouteForm((current) => ({ ...current, originLat: value }))} dir="ltr" />
            <InputGroup label="طول مبدا" value={routeForm.originLng} onChange={(value) => setRouteForm((current) => ({ ...current, originLng: value }))} dir="ltr" />
            <InputGroup label="عرض مقصد" value={routeForm.destLat} onChange={(value) => setRouteForm((current) => ({ ...current, destLat: value }))} dir="ltr" />
            <InputGroup label="طول مقصد" value={routeForm.destLng} onChange={(value) => setRouteForm((current) => ({ ...current, destLng: value }))} dir="ltr" />
          </div>
          <button onClick={() => void calculateRoute()} className="mt-4 rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-3 text-sm font-medium text-slate-950">
            محاسبه مسیر
          </button>
          <RequestFeedback status={routeStatus} message={routeMessage} />
          {routeResult && <JsonPreview data={routeResult} />}
        </section>

        <section className="rounded-2xl border border-white/10 bg-slate-900/30 p-5">
          <h3 className="mb-4 text-lg font-semibold text-slate-100">تبدیل مختصات به آدرس</h3>
          <div className="grid grid-cols-2 gap-4">
            <InputGroup label="عرض جغرافیایی" value={geoForm.lat} onChange={(value) => setGeoForm((current) => ({ ...current, lat: value }))} dir="ltr" />
            <InputGroup label="طول جغرافیایی" value={geoForm.lng} onChange={(value) => setGeoForm((current) => ({ ...current, lng: value }))} dir="ltr" />
          </div>
          <button onClick={() => void reverseGeocode()} className="mt-4 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-300">
            بازیابی آدرس
          </button>
          <RequestFeedback status={geoStatus} message={geoMessage} />
          {geoResult && <JsonPreview data={geoResult} />}
        </section>
      </div>
    </ViewShell>
  );
}

function ReportsView({ apiKey }: { apiKey: string }) {
  const [status, setStatus] = useState<RequestState>("idle");
  const [message, setMessage] = useState("");
  const [reports, setReports] = useState<Array<{ title: string; data: JsonRecord }>>([]);

  async function loadReports() {
    setStatus("loading");
    setMessage("");
    try {
      const headers = buildHeaders(apiKey);
      const endpoints = [
        ["خلاصه", "/reports/summary"],
        ["روزانه", "/reports/daily"],
        ["عملیاتی", "/reports/operational"],
        ["خطاها", "/reports/errors"],
        ["عملکرد", "/reports/performance"],
      ] as const;

      const responses = await Promise.all(
        endpoints.map(async ([title, endpoint]) => {
          const response = await axios.get(`${API_URL}${endpoint}`, { headers });
          return { title, data: response.data as JsonRecord };
        }),
      );

      setReports(responses);
      setStatus("success");
      setMessage("گزارش‌ها با موفقیت بارگذاری شدند.");
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error));
    }
  }

  return (
    <ViewShell title="گزارش‌ها و آمار" description="این تب تمام endpointهای مهم بخش reports را می‌خواند و پاسخ واقعی آن‌ها را نمایش می‌دهد.">
      <button onClick={() => void loadReports()} className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-3 text-sm font-medium text-slate-950">
        بارگذاری گزارش‌ها
      </button>
      <RequestFeedback status={status} message={message} />
      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        {reports.map((report) => (
          <section key={report.title} className="rounded-2xl border border-white/10 bg-slate-900/30 p-5">
            <h3 className="mb-3 text-lg font-semibold text-slate-100">{report.title}</h3>
            <JsonPreview data={report.data} />
          </section>
        ))}
      </div>
    </ViewShell>
  );
}

function ManagementView({ apiKey }: { apiKey: string }) {
  const [status, setStatus] = useState<RequestState>("idle");
  const [message, setMessage] = useState("");
  const [blocks, setBlocks] = useState<Array<{ title: string; data: JsonRecord }>>([]);

  async function loadManagement() {
    setStatus("loading");
    setMessage("");
    try {
      const headers = buildHeaders(apiKey);
      const endpoints = [
        ["خلاصه مدیریت", "/management/summary"],
        ["تشخیص سیستم", "/management/diagnostics"],
        ["داشبورد اپراتور", "/management/operator/dashboard"],
        ["تسک‌های اپراتور", "/management/operator/tasks"],
        ["پیکربندی احراز هویت", "/auth-config"],
        ["وضعیت Workerها", "/workers/heartbeats"],
      ] as const;

      const responses = await Promise.all(
        endpoints.map(async ([title, endpoint]) => {
          const response = await axios.get(`${API_URL}${endpoint}`, { headers });
          return { title, data: response.data as JsonRecord };
        }),
      );

      setBlocks(responses);
      setStatus("success");
      setMessage("اطلاعات مدیریتی دریافت شد.");
    } catch (error) {
      setStatus("error");
      setMessage(extractErrorMessage(error));
    }
  }

  return (
    <ViewShell title="مدیریت حرفه‌ای" description="این بخش اکنون endpointهای مدیریتی، تشخیصی و heartbeat را بارگذاری می‌کند.">
      <button onClick={() => void loadManagement()} className="rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 px-4 py-3 text-sm font-medium text-slate-950">
        بارگذاری ابزارهای مدیریت
      </button>
      <RequestFeedback status={status} message={message} />
      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        {blocks.map((block) => (
          <section key={block.title} className="rounded-2xl border border-white/10 bg-slate-900/30 p-5">
            <h3 className="mb-3 text-lg font-semibold text-slate-100">{block.title}</h3>
            <JsonPreview data={block.data} />
          </section>
        ))}
      </div>
    </ViewShell>
  );
}

function ViewShell({ children, description, title }: { children: React.ReactNode; description: string; title: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="h-full">
      <div className="mb-6">
        <h2 className="mb-2 flex items-center gap-2 text-2xl font-bold text-slate-100">
          <FileText className="text-cyan-300" />
          {title}
        </h2>
        <p className="text-sm leading-6 text-slate-400">{description}</p>
      </div>
      {children}
    </motion.div>
  );
}

function RequestFeedback({ status, message }: { status: RequestState; message: string }) {
  if (status === "idle" || !message) {
    return null;
  }

  const isSuccess = status === "success";
  const isLoading = status === "loading";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`mt-6 flex items-center gap-3 rounded-xl border p-4 ${
        isSuccess
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
          : isLoading
            ? "border-cyan-500/20 bg-cyan-500/10 text-cyan-300"
            : "border-red-500/20 bg-red-500/10 text-red-300"
      }`}
    >
      {isSuccess ? <CheckCircle className="shrink-0" /> : isLoading ? <RefreshCw className="shrink-0 animate-spin" /> : <AlertCircle className="shrink-0" />}
      <p className="text-sm leading-6">{message}</p>
    </motion.div>
  );
}

function InputGroup({
  label,
  value,
  onChange,
  type = "text",
  dir = "rtl",
  required = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  dir?: string;
  required?: boolean;
}) {
  return (
    <label className="block text-sm font-medium text-slate-300">
      <span className="mb-1.5 block">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        dir={dir}
        className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500"
      />
    </label>
  );
}

function SelectGroup({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ label: string; value: string }>;
}) {
  return (
    <label className="block text-sm font-medium text-slate-300">
      <span className="mb-1.5 block">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function JsonPreview({ data }: { data: JsonRecord }) {
  return (
    <pre className="mt-4 overflow-x-auto rounded-xl border border-white/10 bg-slate-950/60 p-4 text-left text-xs leading-6 text-slate-200" dir="ltr">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
