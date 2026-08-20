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
  if (!category) return '-';
  const cleanKey = category.trim().toLowerCase();

  const map: Record<string, string> = {
    submission_unconfirmed: 'در انتظار تطبیق و استخراج کد رهگیری (غیرقطعی)',
    submission_unknown: 'ثبت غیرقطعی (نیاز به تطبیق)',
    driver_submission_in_progress: 'ارسال همزمان بارنامه برای این راننده در جریان است',
    invalid_driver_info: 'اطلاعات راننده یا نام کاربری سامانه نامعتبر است',
    incomplete_waybill_info: 'اطلاعات فرم بارنامه ناقص است',
    system_or_network_error: 'اختلال در شبکه یا ارتباط با پرتال ملی',
    utcms_login_error: 'عدم موفقیت در ورود به پرتال ملی بارنامه',
    auth_expired: 'نشست راننده منقضی شده است',
    daily_limit_reached: 'رسیدن به سقف مجاز روزانه',
    daily_success_limit_reached: 'رسیدن به سقف موفقیت روزانه',
    daily_attempt_limit_reached: 'رسیدن به سقف تلاش روزانه',
    rate_limited: 'محدودیت نرخ ارسال درخواست',
    invalid_credentials: 'نام کاربری یا رمز عبور اشتباه است',
    duplicate: 'بارنامه تکراری',
    validation_error: 'خطای اعتبارسنجی داده‌ها',
    payload_validation_failed: 'خطای اعتبارسنجی فرم بارنامه',
    transient_failure: 'خطای موقت و گذرا',
    destination_service_limit: 'محدودیت سرویس مقصد',
    unknown_error: 'خطای نامشخص',
    unknown_automation_error: 'خطای ناشناخته اتوماسیون',
    captcha_solve_failed: 'خطا در حل کپچا و پردازش هوشمند تصویر',
    captcha_exhaustion: 'اتمام سقف تلاش‌های حل کپچا',
    captcha_failed: 'خطا در حل کپچا',
    waf_blocked: 'مسدودسازی موقت توسط دیوار آتش پرتال (WAF)',
    bot_detected: 'شناسایی و توقف ربات توسط پرتال ملی',
    session_timeout: 'انقضای نشست کاری و نیاز به ورود مجدد',
    concurrent_lock_held: 'قفل تراکنش همزمان برای راننده',
    otp_backoff: 'انتظار برای پنجره زمانی بدون رمز یکبارمصرف',
    otp_required: 'نیازمند تایید رمز یکبارمصرف پیامکی (OTP)',
    ip_circuit_open: 'قطع‌کننده مدار پروکسی و تعویض آی‌پی',
    user_data_error: 'اطلاعات ورودی نامعتبر است',
    auth_failure: 'عدم موفقیت در احراز هویت راننده',
    login_failed: 'ورود ناموفق به سامانه',
    target_site_timeout: 'عدم پاسخگویی سامانه مقصد (تایم‌اوت)',
    selector_changed: 'تغییر ساختار عناصر صفحه سامانه مقصد',
    transient_infra_error: 'خطای موقت زیرساختی و ارتباطی',
    worker_resource_error: 'محدودیت منابع یا حافظه پردازشگر',
    worker_drained: 'توقف و تخلیه موقت پردازشگر',
    system_error: 'خطای سیستمی در پردازش',
    circuit_breaker_open: 'فعال بودن مدار محافظتی',
  };

  return map[cleanKey] || category;
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

export function confirmedTrackingCode(
  result: unknown,
  status?: string | null,
  mutationStatus?: string | null,
  reconciledAt?: string | null,
): string | null {
  if (status !== 'success' || mutationStatus !== 'confirmed' || !reconciledAt) return null;
  return trackingCodeFromResult(result);
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

export function toPersianDigitsPreserveZero(str?: string | number | null): string {
  if (str === undefined || str === null) return '';
  const map: Record<string, string> = {
    '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
    '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹',
  };
  return str.toString().replace(/[0-9]/g, (w) => map[w] || w);
}

export function formatFuelTrackingCode(inquiry: { id: number; year?: number | null; month?: number | null }): string {
  const yy = inquiry.year ? inquiry.year.toString().slice(-2) : '00';
  const mm = inquiry.month ? inquiry.month.toString().padStart(2, '0') : '00';
  const idStr = inquiry.id.toString().padStart(4, '0');
  return toPersianDigitsPreserveZero(`UTC-${yy}${mm}-${idStr}`);
}

export interface ParsedQuotaSummary {
  baseQuota: string | null;
  performanceQuota: string | null;
  cardNumber: string | null;
  keyValues: Array<{ key: string; value: string }>;
  tables: Array<{
    tableIndex?: number;
    headers: string[];
    rows: (string | number)[][];
  }>;
}

export function parseQuotaData(quotaData: unknown): ParsedQuotaSummary {
  const result: ParsedQuotaSummary = {
    baseQuota: null,
    performanceQuota: null,
    cardNumber: null,
    keyValues: [],
    tables: [],
  };

  if (!quotaData) return result;

  let data: Record<string, unknown> | null = null;
  if (typeof quotaData === 'string') {
    try {
      const parsed = JSON.parse(quotaData);
      if (parsed && typeof parsed === 'object') {
        data = parsed as Record<string, unknown>;
      }
    } catch {
      return result;
    }
  } else if (typeof quotaData === 'object') {
    data = quotaData as Record<string, unknown>;
  }

  if (!data) return result;

  // 1. Check summary object
  if (data.summary && typeof data.summary === 'object') {
    const sum = data.summary as Record<string, unknown>;
    if (sum.base_quota !== undefined && sum.base_quota !== null && String(sum.base_quota).trim() !== '') {
      result.baseQuota = String(sum.base_quota).trim();
    }
    if (sum.performance_quota !== undefined && sum.performance_quota !== null && String(sum.performance_quota).trim() !== '') {
      result.performanceQuota = String(sum.performance_quota).trim();
    }
    if (sum.card_number !== undefined && sum.card_number !== null && String(sum.card_number).trim() !== '') {
      result.cardNumber = String(sum.card_number).trim();
    }
  }

  // 2. Check key_values
  if (data.key_values && typeof data.key_values === 'object') {
    const kv = data.key_values as Record<string, unknown>;
    for (const [k, v] of Object.entries(kv)) {
      if (v === undefined || v === null) continue;
      const strVal = typeof v === 'object' ? '' : String(v).trim();
      if (!strVal) continue;

      if (!result.baseQuota && (k === 'سهمیه پایه' || k === 'base_quota')) {
        result.baseQuota = strVal;
      } else if (!result.performanceQuota && (k === 'سهمیه عملکردی' || k === 'performance_quota')) {
        result.performanceQuota = strVal;
      } else if (!result.cardNumber && (k === 'شماره کارت' || k === 'شماره کارت سوخت' || k === 'card_number')) {
        result.cardNumber = strVal;
      } else {
        result.keyValues.push({ key: k, value: strVal });
      }
    }
  }

  // 3. Check flat properties if summary or key_values did not match
  if (!result.baseQuota && data.base_quota !== undefined && data.base_quota !== null) {
    result.baseQuota = String(data.base_quota).trim();
  }
  if (!result.performanceQuota && data.performance_quota !== undefined && data.performance_quota !== null) {
    result.performanceQuota = String(data.performance_quota).trim();
  }
  if (!result.cardNumber && data.card_number !== undefined && data.card_number !== null) {
    result.cardNumber = String(data.card_number).trim();
  }

  // 4. Check tables
  if (Array.isArray(data.tables)) {
    for (const t of data.tables) {
      if (!t || typeof t !== 'object') continue;
      const tableObj = t as Record<string, unknown>;
      const headers = Array.isArray(tableObj.headers) ? tableObj.headers.map((h) => String(h ?? '')) : [];
      const rawRows = Array.isArray(tableObj.rows) ? tableObj.rows : [];
      const rows: (string | number)[][] = [];

      for (const r of rawRows) {
        if (Array.isArray(r)) {
          rows.push(r.map((cell) => (cell === null || cell === undefined ? '' : typeof cell === 'object' ? '' : String(cell))));
        } else if (r && typeof r === 'object') {
          rows.push(Object.values(r as Record<string, unknown>).map((cell) => (cell === null || cell === undefined ? '' : typeof cell === 'object' ? '' : String(cell))));
        }
      }

      if (headers.length > 0 || rows.length > 0) {
        result.tables.push({
          tableIndex: typeof tableObj.table_index === 'number' ? tableObj.table_index : undefined,
          headers,
          rows,
        });
      }
    }
  }

  return result;
}

export interface ParsedWaybillPayload {
  plateNumber?: string | null;
  originCity?: string | null;
  destinationCity?: string | null;
  cargoName?: string | null;
  cargoWeight?: string | number | null;
  cargoDescription?: string | null;
  vehicleType?: string | null;
  senderName?: string | null;
  receiverName?: string | null;
  driverPhone?: string | null;
  driverNationalCode?: string | null;
  notes?: string | null;
}

export function parseWaybillPayload(payloadJson: unknown): ParsedWaybillPayload {
  const result: ParsedWaybillPayload = {
    plateNumber: null,
    originCity: null,
    destinationCity: null,
    cargoName: null,
    cargoWeight: null,
    cargoDescription: null,
    vehicleType: null,
    senderName: null,
    receiverName: null,
    driverPhone: null,
    driverNationalCode: null,
    notes: null,
  };

  if (!payloadJson) return result;

  let payload: Record<string, unknown> | null = null;
  if (typeof payloadJson === 'string') {
    try {
      const parsed = JSON.parse(payloadJson);
      if (parsed && typeof parsed === 'object') {
        payload = parsed as Record<string, unknown>;
      }
    } catch {
      return result;
    }
  } else if (typeof payloadJson === 'object') {
    payload = payloadJson as Record<string, unknown>;
  }

  if (!payload) return result;

  // Vehicle & Plate
  if (payload.plate_number && typeof payload.plate_number === 'string') {
    result.plateNumber = payload.plate_number;
  } else if (payload.vehicle_plate && typeof payload.vehicle_plate === 'string') {
    result.plateNumber = payload.vehicle_plate;
  } else if (payload.vehicle && typeof payload.vehicle === 'object') {
    const v = payload.vehicle as Record<string, unknown>;
    if (v.plate_number && typeof v.plate_number === 'string') {
      result.plateNumber = v.plate_number;
    } else if (v.plate && typeof v.plate === 'object') {
      const pl = v.plate as Record<string, unknown>;
      if (pl.two_digits && pl.letter && pl.three_digits && pl.iran_code) {
        result.plateNumber = `${pl.two_digits}${pl.letter}${pl.three_digits}ایران${pl.iran_code}`;
      }
    }
    if (v.vehicle_type && typeof v.vehicle_type === 'string') {
      result.vehicleType = v.vehicle_type;
    }
  }
  if (!result.vehicleType && payload.vehicle_type && typeof payload.vehicle_type === 'string') {
    result.vehicleType = payload.vehicle_type;
  }

  // Origin & Destination
  if (typeof payload.origin === 'string') {
    result.originCity = payload.origin;
  } else if (payload.origin && typeof payload.origin === 'object') {
    const o = payload.origin as Record<string, unknown>;
    result.originCity = (o.city as string) || (o.province as string) || (o.address as string) || null;
  }

  if (typeof payload.destination === 'string') {
    result.destinationCity = payload.destination;
  } else if (payload.destination && typeof payload.destination === 'object') {
    const d = payload.destination as Record<string, unknown>;
    result.destinationCity = (d.city as string) || (d.province as string) || (d.address as string) || null;
  }

  // Cargo
  if (payload.cargo && typeof payload.cargo === 'object') {
    const c = payload.cargo as Record<string, unknown>;
    result.cargoName = (c.cargo_name as string) || (c.name as string) || (c.title as string) || null;
    result.cargoWeight = (c.weight as string | number) || null;
    result.cargoDescription = (c.description as string) || null;
  }
  if (!result.cargoName && typeof payload.cargo_type === 'string') {
    result.cargoName = payload.cargo_type;
  }
  if (!result.cargoWeight && (typeof payload.cargo_weight === 'number' || typeof payload.cargo_weight === 'string')) {
    result.cargoWeight = payload.cargo_weight;
  }
  if (!result.cargoDescription && typeof payload.cargo_description === 'string') {
    result.cargoDescription = payload.cargo_description;
  }

  // Sender & Receiver
  if (payload.sender && typeof payload.sender === 'object') {
    const s = payload.sender as Record<string, unknown>;
    result.senderName = (s.name as string) || (s.company_name as string) || null;
  } else if (typeof payload.sender_name === 'string') {
    result.senderName = payload.sender_name;
  }

  if (payload.receiver && typeof payload.receiver === 'object') {
    const r = payload.receiver as Record<string, unknown>;
    result.receiverName = (r.name as string) || (r.company_name as string) || null;
  } else if (typeof payload.receiver_name === 'string') {
    result.receiverName = payload.receiver_name;
  }

  // Driver details
  if (typeof payload.driver_phone === 'string') {
    result.driverPhone = payload.driver_phone;
  }
  if (typeof payload.driver_national_code === 'string') {
    result.driverNationalCode = payload.driver_national_code;
  }
  if (typeof payload.notes === 'string') {
    result.notes = payload.notes;
  }

  return result;
}
