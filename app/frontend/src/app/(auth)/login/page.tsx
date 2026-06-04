"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { DashboardStats } from "@/lib/types";
import { Lock, Mail, AlertCircle, CheckCircle, Loader2 } from "lucide-react";

export default function LoginPage() {
  const [role, setRole] = useState<"client" | "admin">("client");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [adminUser, setAdminUser] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      if (role === "admin") {
        const res = await api.post("/api/v1/admin/login", {
          username: adminUser,
          password,
        });
        if (res.error) { setError(res.error); }
        else {
          setSuccess("ورود مدیر سیستم موفقیت‌آمیز بود");
          localStorage.setItem("utcms_role", "admin");
          window.location.href = "/admin/dashboard";
        }
      } else {
        const res = await api.post("/api/v1/auth/login", {
          email,
          password,
        });
        if (res.error) { setError(res.error); }
        else if (res.data) {
          if ((res.data as any).token) api.setToken((res.data as any).token);
          setSuccess("ورود موفقیت‌آمیز بود");
          localStorage.setItem("utcms_role", "client");
          window.location.href = "/client/dashboard";
        }
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
          <h1 className="mb-2 text-3xl font-bold text-slate-100">UTCMS Pro</h1>
          <p className="text-sm text-slate-400">سامانه هوشمند مدیریت بارنامه</p>
        </div>

        {/* Role toggle */}
        <div className="mb-6 flex rounded-xl border border-white/10 bg-slate-800/50 p-1">
          <button
            onClick={() => setRole("client")}
            className={`flex-1 rounded-lg py-2.5 text-sm font-medium transition-all ${
              role === "client"
                ? "bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950 shadow-lg"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            پنل کاربری
          </button>
          <button
            onClick={() => setRole("admin")}
            className={`flex-1 rounded-lg py-2.5 text-sm font-medium transition-all ${
              role === "admin"
                ? "bg-gradient-to-r from-cyan-500 to-amber-400 text-slate-950 shadow-lg"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            پنل مدیریت
          </button>
        </div>

        <form onSubmit={handleLogin} className="space-y-5">
          {role === "admin" ? (
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300">
                <Lock className="mr-1 inline h-4 w-4" />
                نام کاربری
              </label>
              <input
                type="text"
                value={adminUser}
                onChange={(e) => setAdminUser(e.target.value)}
                required
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500"
                placeholder="نام کاربری مدیر"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-300">
                  <Mail className="mr-1 inline h-4 w-4" />
                  ایمیل
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500"
                  placeholder="example@domain.com"
                />
              </div>
            </>
          )}

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300">
              <Lock className="mr-1 inline h-4 w-4" />
              رمز عبور
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400 placeholder:text-slate-500"
              placeholder="رمز عبور"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-gradient-to-r from-cyan-500 to-amber-400 py-3.5 text-sm font-semibold text-slate-950 transition-all hover:opacity-90 disabled:opacity-50"
          >
            {loading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : "ورود به سیستم"}
          </button>
        </form>

        {role === "client" && (
          <div className="mt-6 text-center text-sm text-slate-400">
            حساب کاربری ندارید؟{" "}
            <a href="/register" className="font-semibold text-cyan-400 hover:underline">
              ثبت نام کنید
            </a>
          </div>
        )}

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
