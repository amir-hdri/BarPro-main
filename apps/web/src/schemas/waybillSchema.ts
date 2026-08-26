import { z } from "zod";
import { canonicalizePlate, isValidIranPlate, normalizeDigits } from "@/lib/plate";

const optionalText = (max: number, message: string) =>
  z.string().trim().max(max, message).optional().or(z.literal(""));

const requiredText = (min: number, minMessage: string, max: number, maxMessage: string) =>
  z.string().trim().min(min, minMessage).max(max, maxMessage);

const digitsOnly = (value: string) => normalizeDigits(value).replace(/\D/g, "");
const requiredMobile = (label: string) =>
  z
    .string()
    .trim()
    .min(1, `موبایل ${label} الزامی است`)
    .transform((value) => digitsOnly(value))
    .refine(
      (value) => /^09\d{9}$/.test(value),
      `موبایل ${label} باید ۱۱ رقم و با ۰۹ شروع شود (مثال: ۰۹۱۲۳۴۵۶۷۸۹)`
    );
const numericText = (requiredMessage: string, invalidMessage: string, max: number, maxMessage: string) =>
  z
    .string()
    .trim()
    .min(1, requiredMessage)
    .max(max, maxMessage)
    .refine((value) => Number(normalizeDigits(value).replace(/,/g, "")) > 0, invalidMessage);

// Iranian national code checksum — mirrors the backend validator
// (WaybillPayload._validate_iran_national_code in app/schemas/multitenant.py)
// so users get immediate client-side feedback instead of a late 422.
const isValidIranNationalCode = (code: string): boolean => {
  if (!/^\d{10}$/.test(code)) return false;
  if (/^(\d)\1{9}$/.test(code)) return false;
  const checksum = code
    .slice(0, 9)
    .split("")
    .reduce((sum, digit, index) => sum + Number(digit) * (10 - index), 0);
  const remainder = checksum % 11;
  const control = Number(code[9]);
  return remainder < 2 ? control === remainder : control === 11 - remainder;
};

export const waybillSchema = z.object({
  driver_national_code: z
    .string()
    .min(1, "انتخاب راننده الزامی است")
    .transform((value) => digitsOnly(value))
    .refine((value) => /^\d{10}$/.test(value), "کد ملی باید دقیقاً ۱۰ رقم باشد")
    .refine((value) => isValidIranNationalCode(value), "کد ملی معتبر نیست (رقم کنترل نامعتبر است)"),
  origin: requiredText(2, "شهر مبدأ باید حداقل ۲ حرف باشد", 500, "مبدأ حداکثر ۵۰۰ حرف مجاز است"),
  origin_province: requiredText(2, "استان مبدأ الزامی است", 120, "استان مبدأ حداکثر ۱۲۰ حرف مجاز است"),
  origin_address: requiredText(5, "آدرس مبدأ الزامی است", 500, "آدرس مبدأ حداکثر ۵۰۰ حرف مجاز است"),
  origin_district: optionalText(120, "ناحیه مبدأ حداکثر ۱۲۰ حرف مجاز است"),
  destination: requiredText(2, "شهر مقصد باید حداقل ۲ حرف باشد", 500, "مقصد حداکثر ۵۰۰ حرف مجاز است"),
  destination_province: requiredText(2, "استان مقصد الزامی است", 120, "استان مقصد حداکثر ۱۲۰ حرف مجاز است"),
  destination_address: requiredText(5, "آدرس مقصد الزامی است", 500, "آدرس مقصد حداکثر ۵۰۰ حرف مجاز است"),
  destination_district: optionalText(120, "ناحیه مقصد حداکثر ۱۲۰ حرف مجاز است"),
  plate_number: z
    .string()
    .transform((value) => canonicalizePlate(value))
    .refine((value) => isValidIranPlate(value), "فرمت پلاک باید به صورت ۱۲ب۳۴۵ایران۶۷ باشد"),
  vehicle_type: requiredText(2, "نوع خودرو الزامی است", 100, "نوع خودرو حداکثر ۱۰۰ حرف مجاز است"),
  driver_phone: z
    .string()
    .trim()
    .optional()
    .or(z.literal(""))
    .refine(
      (value) => !value || /^09\d{9}$/.test(digitsOnly(value)),
      "شماره تلفن راننده باید ۱۱ رقم و با ۰۹ شروع شود (مثال: ۰۹۱۲۳۴۵۶۷۸۹)"
    ),
  cargo_type: requiredText(2, "نوع بار الزامی است", 100, "نوع بار حداکثر ۱۰۰ حرف مجاز است"),
  cargo_packaging: requiredText(1, "نوع بسته‌بندی الزامی است", 100, "نوع بسته‌بندی حداکثر ۱۰۰ حرف مجاز است"),
  cargo_weight: numericText("وزن بار الزامی است", "وزن بار باید عددی بزرگ‌تر از صفر باشد", 20, "وزن بار حداکثر ۲۰ کاراکتر مجاز است"),
  cargo_value: numericText("ارزش بار الزامی است", "ارزش بار باید عددی بزرگ‌تر از صفر باشد", 50, "ارزش بار حداکثر ۵۰ حرف مجاز است"),
  sender_name: requiredText(2, "نام فرستنده الزامی است", 255, "نام فرستنده حداکثر ۲۵۵ حرف مجاز است"),
  sender_phone: requiredMobile("فرستنده"),
  receiver_name: requiredText(2, "نام گیرنده الزامی است", 255, "نام گیرنده حداکثر ۲۵۵ حرف مجاز است"),
  receiver_phone: requiredMobile("گیرنده"),
});

export type WaybillFormValues = z.input<typeof waybillSchema>;
