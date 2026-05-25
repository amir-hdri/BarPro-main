import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const schema = z.object({
  client_code: z.string().min(1, "کد مشتری الزامی است"),
  name: z.string().min(1, "نام الزامی است"),
  email: z.string().email("ایمیل نامعتبر است"),
  phone: z.string().optional(),
  password: z.string().min(6, "رمز عبور حداقل ۶ کاراکتر باشد"),
  max_drivers: z.coerce.number().min(0),
  max_plates: z.coerce.number().min(0),
  status: z.string(),
});

type FormValues = z.infer<typeof schema>;

export function CreateClientModal({
  isOpen,
  onClose,
  onSuccess,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      status: "active",
      max_drivers: 10,
      max_plates: 10,
    },
  });

  if (!isOpen) return null;

  async function onSubmit(data: FormValues) {
    setLoading(true);
    setError(null);
    const res = await api.post("/api/v1/admin/clients", data);
    setLoading(false);
    if (!res.success) {
      setError(res.error || "خطا در ایجاد کاربر");
    } else {
      reset();
      onSuccess();
      onClose();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-xl font-bold text-slate-100">افزودن کاربر جدید</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-slate-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-6 rounded-xl bg-red-500/10 p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm text-slate-300">کد مشتری</label>
              <input
                {...register("client_code")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
              {errors.client_code && (
                <p className="mt-1 text-xs text-red-400">{errors.client_code.message}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">نام</label>
              <input
                {...register("name")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
              {errors.name && (
                <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm text-slate-300">ایمیل</label>
              <input
                type="email"
                {...register("email")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">تلفن</label>
              <input
                {...register("phone")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">رمز عبور</label>
            <input
              type="password"
              {...register("password")}
              className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm text-slate-300">حداکثر راننده</label>
              <input
                type="number"
                {...register("max_drivers")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">حداکثر پلاک</label>
              <input
                type="number"
                {...register("max_plates")}
                className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">وضعیت</label>
            <select
              {...register("status")}
              className="w-full rounded-xl border border-white/10 bg-slate-950 px-4 py-2.5 text-slate-100 outline-none focus:border-cyan-500"
            >
              <option value="active">فعال</option>
              <option value="inactive">غیرفعال</option>
            </select>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl px-5 py-2.5 text-sm font-medium text-slate-300 hover:bg-white/5"
            >
              انصراف
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 rounded-xl bg-cyan-500 px-5 py-2.5 text-sm font-medium text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              ایجاد کاربر
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
