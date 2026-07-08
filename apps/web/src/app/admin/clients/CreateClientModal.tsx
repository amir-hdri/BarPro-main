"use client";

import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X, Loader2, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import type { ClientEditData } from "@/lib/types";

const schema = z.object({
  client_code: z.string().trim().min(1, "کد مشتری الزامی است"),
  name: z.string().trim().min(1, "نام الزامی است"),
  email: z.string().trim().email("ایمیل نامعتبر است"),
  phone: z.string().trim().optional().or(z.literal("")),
  password: z.string().optional().or(z.literal("")),
  max_drivers: z.coerce.number().int().min(1, "حداقل ۱ راننده"),
  max_plates: z.coerce.number().int().min(1, "حداقل ۱ پلاک"),
  max_concurrent_tasks: z.coerce.number().int().min(1, "حداقل ۱ تسک همزمان"),
  max_daily_tasks: z.coerce.number().int().min(1, "حداقل ۱ تسک روزانه"),
  status: z.enum(["active", "inactive"]),
  access_level: z.enum(["standard", "premium", "enterprise"]),
  subscription_start_date: z.string().optional().or(z.literal("")),
  subscription_end_date: z.string().optional().or(z.literal("")),
});

type FormValues = z.infer<typeof schema>;

interface CreateClientModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editingClient?: ClientEditData | null;
}

export function CreateClientModal({
  isOpen,
  onClose,
  onSuccess,
  editingClient = null,
}: CreateClientModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isEdit = !!editingClient;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      status: "active",
      access_level: "standard",
      max_drivers: 10,
      max_plates: 10,
      max_concurrent_tasks: 5,
      max_daily_tasks: 100,
      password: "",
      subscription_start_date: "",
      subscription_end_date: "",
    },
  });

  useEffect(() => {
    if (isOpen) {
      setError(null);
      if (editingClient) {
        reset({
          client_code: editingClient.client_code || "",
          name: editingClient.name || "",
          email: editingClient.email || "",
          phone: editingClient.phone || "",
          password: "",
          max_drivers: editingClient.max_drivers ?? 10,
          max_plates: editingClient.max_plates ?? 10,
          max_concurrent_tasks: editingClient.max_concurrent_tasks ?? 5,
          max_daily_tasks: editingClient.max_daily_tasks ?? 100,
          status: editingClient.status === "active" ? "active" : "inactive",
          access_level: (editingClient.access_level as "standard" | "premium" | "enterprise") || "standard",
          subscription_start_date: editingClient.subscription_start_date ? editingClient.subscription_start_date.slice(0, 10) : "",
          subscription_end_date: editingClient.subscription_end_date ? editingClient.subscription_end_date.slice(0, 10) : "",
        });
      } else {
        reset({
          client_code: "",
          name: "",
          email: "",
          phone: "",
          password: "",
          max_drivers: 10,
          max_plates: 10,
          max_concurrent_tasks: 5,
          max_daily_tasks: 100,
          status: "active",
          access_level: "standard",
          subscription_start_date: "",
          subscription_end_date: "",
        });
      }
    }
  }, [isOpen, editingClient, reset]);

  if (!isOpen) return null;

  async function onSubmit(data: FormValues) {
    setLoading(true);
    setError(null);

    // Validate password for new users
    if (!isEdit && (!data.password || data.password.length < 8)) {
      setError("رمز عبور برای کاربر جدید الزامی است (حداقل ۸ کاراکتر)");
      setLoading(false);
      return;
    }

    const payload: Record<string, unknown> = {
      ...data,
      phone: data.phone?.trim() || undefined,
      client_code: data.client_code.trim(),
      name: data.name.trim(),
      email: data.email.trim(),
      subscription_start_date: data.subscription_start_date ? `${data.subscription_start_date}T00:00:00` : null,
      subscription_end_date: data.subscription_end_date ? `${data.subscription_end_date}T23:59:59` : null,
    };

    // Remove empty password when editing to avoid overwriting with empty
    if (isEdit && !data.password) {
      delete payload.password;
    }

    let res;
    if (isEdit) {
      res = await api.put(`/api/v1/admin/clients/${editingClient.id}`, payload);
    } else {
      res = await api.post("/api/v1/admin/clients", payload);
    }

    setLoading(false);
    if (!res.success) {
      setError(res.error || `خطا در ${isEdit ? "ویرایش" : "ایجاد"} کاربر`);
    } else {
      reset();
      onSuccess();
      onClose();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md animate-in fade-in overflow-y-auto">
      <div className="relative w-full max-w-xl rounded-[2rem] border border-white/10 bg-slate-900/90 p-[1px] shadow-2xl backdrop-blur-2xl my-auto">
        <div className="absolute inset-0 rounded-[2rem] bg-gradient-to-b from-white/10 to-transparent pointer-events-none" />
        
        <div className="relative bg-slate-950/90 rounded-[1.95rem] p-6 sm:p-8">
          <div className="mb-6 flex items-center justify-between border-b border-white/5 pb-4">
            <div>
              <h2 className="text-xl font-black text-slate-100">
                {isEdit ? "ویرایش حساب کاربر" : "افزودن کاربر جدید"}
              </h2>
              <p className="mt-1 text-xs text-slate-400">
                {isEdit ? "تنظیم مشخصات و سقف دسترسی‌های کاربر سیستم" : "ایجاد حساب کاربری جدید"}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-slate-100 transition"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {error && (
            <div className="mb-6 flex items-start gap-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 p-4 text-xs sm:text-sm text-rose-400">
              <ShieldAlert className="h-5 w-5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            
            {/* Row 1: Code and Name */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">کد مشتری</label>
                <input
                  {...register("client_code")}
                  disabled={isEdit}
                  placeholder="مثال: company_a"
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500 disabled:opacity-50"
                />
                {errors.client_code && (
                  <p className="text-[11px] text-rose-400">{errors.client_code.message}</p>
                )}
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">نام کامل</label>
                <input
                  {...register("name")}
                  placeholder="مثال: ترابری پتروشیمی آریا"
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
                />
                {errors.name && (
                  <p className="text-[11px] text-rose-400">{errors.name.message}</p>
                )}
              </div>
            </div>

            {/* Row 2: Email and Phone */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">ایمیل</label>
                <input
                  type="email"
                  {...register("email")}
                  placeholder="user@domain.com"
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
                />
                {errors.email && (
                  <p className="text-[11px] text-rose-400">{errors.email.message}</p>
                )}
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">تلفن تماس (اختیاری)</label>
                <input
                  {...register("phone")}
                  placeholder="۰۹۱۲۳۴۵۶۷۸۹"
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1">
              <label className="block text-xs font-bold text-slate-400">
                رمز عبور {isEdit && <span className="text-[10px] text-slate-500">(فقط در صورت نیاز به تغییر پر شود)</span>}
              </label>
              <input
                type="password"
                {...register("password")}
                placeholder={isEdit ? "••••••••" : "حداقل ۸ کاراکتر"}
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
              />
              {errors.password && (
                <p className="text-[11px] text-rose-400">{errors.password.message}</p>
              )}
            </div>

            {/* Row 3: Limits configuration */}
            <div className="border-t border-white/5 pt-4">
              <h3 className="text-xs font-black text-cyan-400 mb-3">پیکربندی سقف دسترسی و محدودیت‌ها</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="space-y-1">
                  <label className="block text-[10px] font-bold text-slate-400">حداکثر راننده</label>
                  <input
                    type="number"
                    {...register("max_drivers")}
                    className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500 text-center font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-[10px] font-bold text-slate-400">حداکثر پلاک</label>
                  <input
                    type="number"
                    {...register("max_plates")}
                    className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500 text-center font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-[10px] font-bold text-slate-400">کارهای همزمان</label>
                  <input
                    type="number"
                    {...register("max_concurrent_tasks")}
                    className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500 text-center font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-[10px] font-bold text-slate-400">کارهای روزانه</label>
                  <input
                    type="number"
                    {...register("max_daily_tasks")}
                    className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500 text-center font-mono"
                  />
                </div>
              </div>
            </div>

            {/* Row 4: Status and Level */}
            <div className="grid grid-cols-2 gap-4 border-t border-white/5 pt-4">
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">وضعیت حساب</label>
                <select
                  {...register("status")}
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
                >
                  <option value="active" className="bg-slate-950">فعال</option>
                  <option value="inactive" className="bg-slate-950">غیرفعال</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">سطح دسترسی</label>
                <select
                  {...register("access_level")}
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500"
                >
                  <option value="standard" className="bg-slate-950">استاندارد (Standard)</option>
                  <option value="premium" className="bg-slate-950">پریمیوم (Premium)</option>
                  <option value="enterprise" className="bg-slate-950">سازمانی (Enterprise)</option>
                </select>
              </div>
            </div>

            {/* Row 5: Subscription dates */}
            <div className="grid grid-cols-2 gap-4 border-t border-white/5 pt-4">
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">تاریخ شروع اشتراک</label>
                <input
                  type="date"
                  {...register("subscription_start_date")}
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500 font-mono"
                />
              </div>
              <div className="space-y-1">
                <label className="block text-xs font-bold text-slate-400">تاریخ پایان اشتراک</label>
                <input
                  type="date"
                  {...register("subscription_end_date")}
                  className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500 font-mono"
                />
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 flex justify-end gap-3 border-t border-white/5 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl px-5 py-3 text-sm font-bold text-slate-400 hover:bg-white/5 transition"
              >
                انصراف
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 px-6 py-3 text-sm font-bold text-slate-950 transition active:scale-[0.98] disabled:opacity-50"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                {isEdit ? "ثبت تغییرات" : "ایجاد حساب کاربری"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
