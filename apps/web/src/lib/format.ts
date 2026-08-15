export function formatDateTime(value?: string | null): string {
  if (!value) {
    return '-';
  }
  // Append 'Z' if no timezone info present so JS parses it as UTC (server stores UTC)
  const raw = value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z';
  return new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Tehran',
  }).format(new Date(raw));
}

export function formatDateTimeEn(value?: string | null): string {
  if (!value) {
    return '-';
  }
  const raw = value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z';
  return new Intl.DateTimeFormat('en-IR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Tehran',
  }).format(new Date(raw));
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
    rate_limit_cooldown: 'توقف موقت (سقف محدودیت)',
    invalid_credentials: 'اطلاعات ورود نامعتبر',
    daily_limit_reached: 'رسیدن به سقف روزانه',
    daily_success_limit_reached: 'سقف ثبت موفق روزانه',
    daily_attempt_limit_reached: 'سقف تلاش روزانه',
    disabled: 'غیرفعال شده',
    error_review: 'نیازمند بررسی',
    pending: 'در انتظار',
    queued: 'در صف پردازش',
    in_progress: 'در حال پردازش ربات',
    retrying: 'در حال تلاش مجدد خودکار',
    waiting_auth: 'در انتظار ورود به سامانه',
    waiting_submission_window: 'در انتظار بازه ثبت بدون OTP (پایش خودکار)',
    reconciling: 'در حال تطبیق با سامانه مرکزی',
    unknown: 'نیازمند استعلام وضعیت (نامشخص)',
    otp_backoff: 'توقف موقت (درخواست پیامک OTP)',
    success: 'ثبت موفق',
    failed: 'ناموفق',
    dead_letter: 'متوقف شده (نیازمند بازبینی)',
    transient_failure: 'خطای موقت شبکه',
    validation_error: 'خطای اعتبارسنجی اطلاعات',
    auth_expired: 'نشست کاربری منقضی شده',
    duplicate: 'درخواست تکراری',
    unknown_error: 'خطای غیرمنتظره',
    utcms_login_error: 'خطای ورود به پرتال ملی بارنامه',
    invalid_driver_info: 'اطلاعات نامعتبر راننده',
    incomplete_waybill_info: 'اطلاعات بارنامه کامل نیست',
    system_or_network_error: 'خطای سیستمی یا ارتباطی',
    destination_service_limit: 'محدودیت سرویس مقصد',
    manual: 'ثبت دستی',
    bulk_upload: 'فایل اکسل',
    api: 'درخواست وب‌سرویس',
    rpa_bot: 'ربات هوشمند اتوماسیون',
    scheduler: 'زمان‌بندی شده خودکار',
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
    waiting_submission_window: 'bg-amber-500/10 border border-amber-500/20 text-amber-400',
    reconciling: 'bg-sky-500/10 border border-sky-500/20 text-sky-400',
    unknown: 'bg-orange-500/10 border border-orange-500/20 text-orange-400',
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

export function errorCategoryLabel(category?: string | null): string {
  const map: Record<string, string> = {
    submission_unconfirmed: 'موفق (در انتظار استخراج کد رهگیری)',
    submission_unknown: 'خطای غیرمنتظره در ثبت',
    driver_submission_in_progress: 'ارسال همزمان بارنامه برای این راننده در جریان است',
    invalid_driver_info: 'اطلاعات راننده یا نام کاربری سامانه نامعتبر است',
    incomplete_waybill_info: 'اطلاعات فرم بارنامه ناقص است',
    system_or_network_error: 'اختلال در شبکه یا ارتباط با پرتال ملی',
    utcms_login_error: 'عدم موفقیت در ورود به پرتال ملی بارنامه',
    auth_expired: 'نشست راننده منقضی شده است',
    daily_limit_reached: 'سقف روزانه',
    daily_success_limit_reached: 'سقف موفقیت روزانه',
    daily_attempt_limit_reached: 'سقف تلاش روزانه',
    rate_limited: 'محدود شده',
    invalid_credentials: 'اطلاعات نادرست',
    duplicate: 'تکراری',
    validation_error: 'خطای اعتبارسنجی',
    transient_failure: 'خطای موقت',
    destination_service_limit: 'محدودیت سرویس مقصد',
    unknown_error: 'خطای نامشخص',
  };

  if (!category) return '-';
  return map[category] || category;
}

export function trackingCodeFromResult(result?: unknown): string | null {
  if (!result) return null;
  if (typeof result === 'string') {
    try {
      const parsed = JSON.parse(result);
      if (parsed && typeof parsed === 'object' && (parsed as Record<string, unknown>).tracking_code) {
        return String((parsed as Record<string, unknown>).tracking_code);
      }
    } catch {
      // ignore malformed json
    }
    return null;
  }
  if (typeof result === 'object' && (result as Record<string, unknown>).tracking_code) {
    return String((result as Record<string, unknown>).tracking_code);
  }
  return null;
}

export function downloadCSV(filename: string, headers: string[], rows: (string | number)[][]): void {
  const processRow = (row: (string | number)[]) =>
    row.map((val) => `"${String(val ?? '').replace(/"/g, '""')}"`).join(',');

  const csvContent = '\uFEFF' + [headers.join(','), ...rows.map(processRow)].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
