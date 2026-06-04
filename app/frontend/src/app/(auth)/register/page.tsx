"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Lock, Mail, User, Phone, Tag, AlertCircle, CheckCircle, Loader2 } from "lucide-react";
import Link from "next/link";

export default function RegisterPage() {
  const [clientCode, setClientCode] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    // Validate client code regex
    if (!/^[a-zA-Z0-9_-]+$/.test(clientCode)) {
      setError("کد مشتری فقط می‌تواند شامل حروف انگلیسی، اعداد، خط تیره و زیرخط باشد.");
      setLoading(false);
      return;
    }

    try {
      const res = await api.post("/api/v1/auth/register", {
        client_code: clientCode,
        name,
        email,
        phone: phone || undefined,
        password,
      });

      if (res.error) {
        setError(res.error);
      } else {
        setSuccess("ثبت نام با موفقیت انجام شد! در حال انتقال به صفحه ورود...");
        setTimeout(() => {
          window.location.href = "/login";
        }, 2000);
      }
    } catch (e: any) {
      setError(e?.message || "خطا در ارتباط با سرور");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md">
      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-8 backdrop-blur-xl animate-fade-in">
        <div className="mb-8 text-center">
          <h1 className="mb-2 text-3xl font-bold text-slate-100">ثبت نام در UTCMS Pro</h1>
          <p className="text-sm text-slate-400">سامانه هوشمند مدیریت بارنامه (نسخه چند مستاجری)</p>
        </div>

        <form onSubmit={handleRegister} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              <Tag className="mr-1 inline h-4 w-4" />
              کد مستأجر / شناسه شرکت (انگلیسی)
            </label>
            <input
              type="text"
              value={clientCode}
              onChange={(e) => setClientCode(e.target.value)}
              required
              pattern="^[a-zA-Z0-9_-]+$"
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500 text-left"
              placeholder="e.g. smart_logistics"
              dir="ltr"
            />
            <p className="mt-1 text-xs text-slate-500 text-right">
              حروف، اعداد، خط تیره و خط زیر مجاز است. غیر قابل تغییر.
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              <User className="mr-1 inline h-4 w-4" />
              نام و نام خانوادگی / نام شرکت
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500 text-right"
              placeholder="نام شما یا نام سازمان شما"
              dir="rtl"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              <Mail className="mr-1 inline h-4 w-4" />
              ایمیل
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500 text-left"
              placeholder="example@domain.com"
              dir="ltr"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              <Phone className="mr-1 inline h-4 w-4" />
              شماره تلفن همراه (اختیاری)
            </label>
            <input
              type="text"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500 text-left"
              placeholder="09123456789"
              dir="ltr"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-300">
              <Lock className="mr-1 inline h-4 w-4" />
              رمز عبور (حداقل ۸ کاراکتر)
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500 text-left"
              placeholder="رمز عبور شما"
              dir="ltr"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 py-3.5 text-sm font-semibold text-slate-950 transition-all hover:opacity-90 disabled:opacity-50 mt-2"
          >
            {loading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : "ثبت نام حساب کاربری جدید"}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-slate-400">
          حساب کاربری دارید؟{" "}
          <Link href="/login" className="font-semibold text-cyan-400 hover:underline">
            وارد شوید
          </Link>
        </div>

        {error && (
          <div className="mt-5 flex items-center gap-3 rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-300">
            <AlertCircle className="shrink-0" />
            <p className="text-sm">{error}</p>
          </div>
        )}
        {success && (
          <div className="mt-5 flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-emerald-300">
            <CheckCircle className="shrink-0" />
            <p className="text-sm">{success}</p>
          </div>
        )}
      </div>
    </div>
  );
}
