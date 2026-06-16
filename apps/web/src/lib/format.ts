export function formatDateTime(value?: string | null): string {
  if (!value) {
    return '-';
  }

  return new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

export function formatRelativePercent(value: number): string {
  return `${Math.round(value)}%`;
}

export function toPersianDigits(value: number | string): string {
  return new Intl.NumberFormat('fa-IR').format(Number(value));
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    active: 'فعال',
    inactive: 'غیرفعال',
    blocked: 'مسدود',
    auth_required: 'نیازمند ورود',
    auth_in_progress: 'در حال احراز هویت',
    ready: 'آماده',
    submitting: 'در حال ثبت',
    waiting_retry: 'در انتظار تلاش مجدد',
    needs_review: 'نیازمند بررسی مجدد',
    rate_limited: 'محدود شده',
    rate_limit_cooldown: 'در cooldown محدودیت',
    invalid_credentials: 'اطلاعات نادرست',
    daily_limit_reached: 'سقف روزانه',
    daily_success_limit_reached: 'سقف موفقیت روزانه',
    daily_attempt_limit_reached: 'سقف تلاش روزانه',
    disabled: 'غیرفعال شده',
    error_review: 'نیازمند بررسی',
    pending: 'در انتظار',
    queued: 'در صف',
    in_progress: 'در حال پردازش',
    retrying: 'در حال تلاش مجدد',
    waiting_auth: 'در انتظار احراز هویت',
    otp_backoff: 'متوقف به دلیل OTP',
    success: 'موفق',
    failed: 'ناموفق',
    dead_letter: 'خارج از چرخه',
    transient_failure: 'خطای موقت',
    validation_error: 'خطای اعتبارسنجی',
    auth_expired: 'نشست منقضی شده',
    duplicate: 'تکراری',
    unknown_error: 'خطای نامشخص',
    utcms_login_error: 'خطای ورود به UTCMS',
    invalid_driver_info: 'نامعتبر بودن اطلاعات راننده',
    incomplete_waybill_info: 'ناقص بودن اطلاعات بارنامه',
    system_or_network_error: 'خطای سیستمی یا ارتباطی',
    destination_service_limit: 'محدودیت سرویس مقصد',
    manual: 'دستی',
    bulk_upload: 'اکسل',
    api: 'API',
  };

  return map[status] || status;
}

export function statusTone(status: string): string {
  const map: Record<string, string> = {
    active: 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400',
    ready: 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400',
    success: 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400',
    submitting: 'bg-sky-500/10 border border-sky-500/20 text-sky-400',
    pending: 'bg-amber-500/10 border border-amber-500/20 text-amber-400',
    queued: 'bg-amber-500/10 border border-amber-500/20 text-amber-400',
    waiting_retry: 'bg-amber-500/10 border border-amber-500/20 text-amber-400',
    needs_review: 'bg-orange-500/10 border border-orange-500/20 text-orange-400',
    otp_backoff: 'bg-orange-500/10 border border-orange-500/20 text-orange-400',
    auth_in_progress: 'bg-violet-500/10 border border-violet-500/20 text-violet-400',
    rate_limit_cooldown: 'bg-violet-500/10 border border-violet-500/20 text-violet-400',
    in_progress: 'bg-sky-500/10 border border-sky-500/20 text-sky-400',
    retrying: 'bg-sky-500/10 border border-sky-500/20 text-sky-400',
    waiting_auth: 'bg-violet-500/10 border border-violet-500/20 text-violet-400',
    rate_limited: 'bg-violet-500/10 border border-violet-500/20 text-violet-400',
    failed: 'bg-rose-500/10 border border-rose-500/20 text-rose-400',
    dead_letter: 'bg-rose-500/10 border border-rose-500/20 text-rose-400',
    blocked: 'bg-rose-500/10 border border-rose-500/20 text-rose-400',
    invalid_credentials: 'bg-rose-500/10 border border-rose-500/20 text-rose-400',
    error_review: 'bg-rose-500/10 border border-rose-500/20 text-rose-400',
    inactive: 'bg-slate-500/10 border border-white/5 text-slate-400',
    daily_limit_reached: 'bg-slate-500/10 border border-white/5 text-slate-400',
    daily_success_limit_reached: 'bg-slate-500/10 border border-white/5 text-slate-400',
    daily_attempt_limit_reached: 'bg-slate-500/10 border border-white/5 text-slate-400',
    disabled: 'bg-slate-500/10 border border-white/5 text-slate-400',
  };

  return map[status] || 'bg-slate-500/10 border border-white/5 text-slate-400';
}
