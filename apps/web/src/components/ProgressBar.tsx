export type ProgressTone = "amber" | "cyan" | "emerald" | "indigo" | "rose";

interface ProgressBarProps {
  value: number;
  max?: number;
  segments?: number;
  tone?: ProgressTone;
  size?: "sm" | "md";
  label?: string;
  className?: string;
}

const toneClasses: Record<ProgressTone, string> = {
  amber: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.45)]",
  cyan: "bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.45)]",
  emerald: "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.45)]",
  indigo: "bg-indigo-400 shadow-[0_0_8px_rgba(129,140,248,0.45)]",
  rose: "bg-rose-400 shadow-[0_0_8px_rgba(251,113,133,0.45)]",
};

const sizeClasses = {
  sm: "h-2",
  md: "h-2.5",
};

export function ProgressBar({
  value,
  max = 100,
  segments = 20,
  tone = "cyan",
  size = "sm",
  label = "میزان پیشرفت",
  className = "",
}: ProgressBarProps) {
  const safeMax = Math.max(max, 1);
  const safeSegments = Math.max(Math.round(segments), 1);
  const percent = Math.min(Math.max((value / safeMax) * 100, 0), 100);
  const filledSegments = percent >= 100 ? safeSegments : Math.floor((percent / 100) * safeSegments);

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={Math.min(Math.max(value, 0), safeMax)}
      className={`flex w-full gap-0.5 rounded-full border border-white/5 bg-slate-800/80 p-0.5 ${sizeClasses[size]} ${className}`}
    >
      {Array.from({ length: safeSegments }, (_, index) => (
        <span
          key={index}
          className={`h-full min-w-0 flex-1 rounded-full transition-colors duration-300 ${
            index < filledSegments ? toneClasses[tone] : "bg-transparent"
          }`}
        />
      ))}
    </div>
  );
}
