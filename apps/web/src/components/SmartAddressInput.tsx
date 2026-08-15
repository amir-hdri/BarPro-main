"use client";

import { memo, useState } from "react";
import { SparklesIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import { api } from "@/lib/api";

interface ParsedAddressResult {
  province: string;
  city: string;
  district: string;
  address: string;
  coordinates?: { lat: number; lng: number } | null;
}

interface SmartAddressInputProps {
  onParsed: (result: ParsedAddressResult) => void;
}

export const SmartAddressInput = memo(function SmartAddressInput({ onParsed }: SmartAddressInputProps) {
  const [rawText, setRawText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const handleParse = async () => {
    if (!rawText.trim()) return;
    setParsing(true);
    setMessage(null);

    const res = await api.post<ParsedAddressResult | { data?: ParsedAddressResult }>("/api/v1/locations/parse-address", {
      address_text: rawText,
    });

    setParsing(false);

    if (res.success && res.data) {
      const data: ParsedAddressResult =
        "province" in res.data
          ? (res.data as ParsedAddressResult)
          : ((res.data as { data?: ParsedAddressResult }).data as ParsedAddressResult) || ({} as ParsedAddressResult);

      if (data && (data.province || data.city || data.address)) {
        onParsed(data);
        if (data.province || data.city) {
          setMessage(`✅ شناسایی شد: استان ${data.province || "—"} | شهر ${data.city || "—"}`);
        } else {
          setMessage("⚠️ استان/شهر در متن یافت نشد؛ لطفا به صورت دستی انتخاب کنید.");
        }
      } else {
        setMessage("⚠️ استان/شهر در متن یافت نشد؛ لطفا به صورت دستی انتخاب کنید.");
      }
    } else {
      setMessage("خطا در تفکیک هوشمند آدرس");
    }
  };

  return (
    <div className="rounded-2xl bg-gradient-to-r from-slate-900 via-slate-950 to-slate-900 p-4 border border-cyan-500/20 shadow-lg shadow-cyan-950/20 mb-5">
      <div className="flex items-center gap-2 text-xs font-bold text-cyan-400 mb-2">
        <SparklesIcon className="h-4 w-4" />
        <span>ورودی هوشمند آدرس (تفکیک خودکار)</span>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleParse();
            }
          }}
          placeholder="مثال: اصفهان، خمینی‌شهر، شهرک صنعتی، خیابان دهم پلاک ۱۲..."
          className="field flex-1 text-xs"
        />
        <button
          type="button"
          onClick={handleParse}
          disabled={parsing || !rawText.trim()}
          className="px-4 py-2.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-bold transition-all border border-cyan-500/30 flex items-center justify-center gap-1.5 shrink-0 disabled:opacity-50"
        >
          {parsing ? (
            <ArrowPathIcon className="h-4 w-4 animate-spin text-cyan-400" />
          ) : (
            <SparklesIcon className="h-4 w-4" />
          )}
          <span>تفکیک خودکار</span>
        </button>
      </div>
      {message && <div className="mt-2 text-[11px] font-medium text-slate-300">{message}</div>}
    </div>
  );
});
