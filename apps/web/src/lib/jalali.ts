/**
 * Self-contained Jalali (Persian/Shamsi) calendar utilities for frontend.
 * Pure TypeScript, zero external dependencies.
 * Follows Birashk/Kazemi algorithms consistent with app/core/jalali.py.
 */

export const JALALI_MONTH_NAMES = [
  'فروردین',
  'اردیبهشت',
  'خرداد',
  'تیر',
  'مرداد',
  'شهریور',
  'مهر',
  'آبان',
  'آذر',
  'دی',
  'بهمن',
  'اسفند',
] as const;

export const JALALI_WEEKDAY_NAMES = [
  'شنبه',
  'یکشنبه',
  'دوشنبه',
  'سه‌شنبه',
  'چهارشنبه',
  'پنج‌شنبه',
  'جمعه',
] as const;

export const JALALI_WEEKDAY_SHORT = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'] as const;

const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

export function toPersianDigits(value: number | string): string {
  return String(value).replace(/\d/g, (d) => PERSIAN_DIGITS[Number(d)] ?? d);
}

export function toEnglishDigits(value: string): string {
  return value.replace(/[۰-۹]/g, (d) => String(PERSIAN_DIGITS.indexOf(d)));
}

export function gregorianToJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    355666 +
    365 * gy +
    Math.floor((gy2 + 3) / 4) -
    Math.floor((gy2 + 99) / 100) +
    Math.floor((gy2 + 399) / 400) +
    gd +
    g_d_m[gm - 1];
  let jy = -1595 + 33 * Math.floor(days / 12053);
  days %= 12053;
  jy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    jy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  let jm: number;
  let jd: number;
  if (days < 186) {
    jm = 1 + Math.floor(days / 31);
    jd = 1 + (days % 31);
  } else {
    jm = 7 + Math.floor((days - 186) / 30);
    jd = 1 + ((days - 186) % 30);
  }
  return [jy, jm, jd];
}

export function jalaliToGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  jy += 1595;
  let days =
    -355668 +
    365 * jy +
    Math.floor(jy / 33) * 8 +
    Math.floor(((jy % 33) + 3) / 4) +
    jd;
  if (jm < 7) {
    days += (jm - 1) * 31;
  } else {
    days += (jm - 7) * 30 + 186;
  }
  let gy = 400 * Math.floor(days / 146097);
  days %= 146097;
  if (days > 36524) {
    gy += 100 * Math.floor((days - 1) / 36524);
    days = (days - 1) % 36524;
    if (days >= 365) {
      days += 1;
    }
  }
  gy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    gy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }
  let gd = days + 1;
  const leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
  const month_days = [0, 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gm = 0;
  while (gm < 13 && gd > month_days[gm]) {
    gd -= month_days[gm];
    gm += 1;
  }
  return [gy, gm, gd];
}

export function isJalaliLeapYear(jy: number): boolean {
  const [gy, gm, gd] = jalaliToGregorian(jy, 12, 30);
  const [checkJy, checkJm, checkJd] = gregorianToJalali(gy, gm, gd);
  return checkJy === jy && checkJm === 12 && checkJd === 30;
}

export function getJalaliMonthDays(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isJalaliLeapYear(jy) ? 30 : 29;
}

/**
 * Returns Persian weekday of 1st day of month (0 = شنبه, 1 = یکشنبه, ... 6 = جمعه).
 */
export function getJalaliFirstDayOfWeek(jy: number, jm: number): number {
  const [gy, gm, gd] = jalaliToGregorian(jy, jm, 1);
  const d = new Date(Date.UTC(gy, gm - 1, gd));
  return (d.getUTCDay() + 1) % 7;
}

/**
 * Convert Gregorian ISO date (e.g. "2026-10-11") to Jalali tuple { jy, jm, jd }.
 */
export function gregorianIsoToJalali(iso?: string | null): { jy: number; jm: number; jd: number } | null {
  if (!iso) return null;
  const clean = iso.trim().slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(clean);
  if (!match) return null;
  const gy = Number(match[1]);
  const gm = Number(match[2]);
  const gd = Number(match[3]);
  if (!gy || !gm || !gd) return null;
  const [jy, jm, jd] = gregorianToJalali(gy, gm, gd);
  return { jy, jm, jd };
}

/**
 * Convert Jalali { jy, jm, jd } to Gregorian ISO date "YYYY-MM-DD".
 */
export function jalaliToGregorianIso(jy: number, jm: number, jd: number): string {
  const [gy, gm, gd] = jalaliToGregorian(jy, jm, jd);
  const sm = String(gm).padStart(2, '0');
  const sd = String(gd).padStart(2, '0');
  return `${gy}-${sm}-${sd}`;
}

/**
 * Today's date in Jalali.
 */
export function getTodayJalali(): { jy: number; jm: number; jd: number } {
  const now = new Date();
  const [jy, jm, jd] = gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
  return { jy, jm, jd };
}

/**
 * Format Gregorian ISO string (or Date) to display Jalali string "۱۴۰۵/۰۷/۱۹".
 */
export function formatJalaliDisplay(iso?: string | null, withPersianDigits = true): string {
  if (!iso) return '-';
  const j = gregorianIsoToJalali(iso);
  if (!j) return iso;
  const str = `${j.jy}/${String(j.jm).padStart(2, '0')}/${String(j.jd).padStart(2, '0')}`;
  return withPersianDigits ? toPersianDigits(str) : str;
}
