export default function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100">
      <div className="flex flex-col items-center gap-4">
        <div className="w-12 h-12 border-4 border-slate-800 border-t-emerald-500 rounded-full animate-spin" />
        <span className="text-sm font-medium text-slate-400">در حال بارگذاری اطلاعات...</span>
      </div>
    </div>
  );
}
