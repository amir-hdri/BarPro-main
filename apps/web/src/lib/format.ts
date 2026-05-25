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
    active: 'bg-emerald-100 text-emerald-800',
    ready: 'bg-emerald-100 text-emerald-800',
    success: 'bg-emerald-100 text-emerald-800',
    submitting: 'bg-sky-100 text-sky-800',
    pending: 'bg-amber-100 text-amber-800',
    queued: 'bg-amber-100 text-amber-800',
    waiting_retry: 'bg-amber-100 text-amber-800',
    needs_review: 'bg-orange-100 text-orange-800',
    otp_backoff: 'bg-orange-100 text-orange-800',
    auth_in_progress: 'bg-violet-100 text-violet-800',
    rate_limit_cooldown: 'bg-violet-100 text-violet-800',
    in_progress: 'bg-sky-100 text-sky-800',
    retrying: 'bg-sky-100 text-sky-800',
    waiting_auth: 'bg-violet-100 text-violet-800',
    rate_limited: 'bg-violet-100 text-violet-800',
    failed: 'bg-rose-100 text-rose-800',
    dead_letter: 'bg-rose-100 text-rose-800',
    blocked: 'bg-rose-100 text-rose-800',
    invalid_credentials: 'bg-rose-100 text-rose-800',
    error_review: 'bg-rose-100 text-rose-800',
    inactive: 'bg-slate-200 text-slate-700',
    daily_limit_reached: 'bg-slate-200 text-slate-700',
    daily_success_limit_reached: 'bg-slate-200 text-slate-700',
    daily_attempt_limit_reached: 'bg-slate-200 text-slate-700',
    disabled: 'bg-slate-200 text-slate-700',
  };

  return map[status] || 'bg-slate-200 text-slate-700';
}
