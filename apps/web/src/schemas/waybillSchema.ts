import { z } from "zod";
import { canonicalizePlate, isValidIranPlate, normalizeDigits } from "@/lib/plate";

const optionalText = (max: number, message: string) =>
  z.string().max(max, message).optional().or(z.literal(""));

const requiredText = (min: number, minMessage: string, max: number, maxMessage: string) =>
  z.string().trim().min(min, minMessage).max(max, maxMessage);

const digitsOnly = (value: string) => normalizeDigits(value).replace(/\D/g, "");
const numericText = (requiredMessage: string, invalidMessage: string, max: number, maxMessage: string) =>
  z
    .string()
    .trim()
    .min(1, requiredMessage)
    .max(max, maxMessage)
    .refine((value) => Number(normalizeDigits(value).replace(/,/g, "")) > 0, invalidMessage);

export const waybillSchema = z.object({
  driver_national_code: z
    .string()
    .min(1, "انتخاب راننده الزامی است")
    .transform((value) => digitsOnly(value))
    .refine((value) => /^\d{10}$/.test(value), "کد ملی باید دقیقاً ۱۰ رقم باشد"),
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
  waybill_number: optionalText(100, "شماره بارنامه حداکثر ۱۰۰ حرف مجاز است"),
  cargo_type: requiredText(2, "نوع بار الزامی است", 100, "نوع بار حداکثر ۱۰۰ حرف مجاز است"),
  cargo_weight: numericText("وزن بار الزامی است", "وزن بار باید عددی بزرگ‌تر از صفر باشد", 20, "وزن بار حداکثر ۲۰ کاراکتر مجاز است"),
  cargo_count: numericText("تعداد کالا الزامی است", "تعداد کالا باید عددی بزرگ‌تر از صفر باشد", 20, "تعداد کالا حداکثر ۲۰ حرف مجاز است"),
  cargo_description: optionalText(1000, "شرح بار حداکثر ۱۰۰۰ حرف مجاز است"),
  cargo_value: numericText("ارزش بار الزامی است", "ارزش بار باید عددی بزرگ‌تر از صفر باشد", 50, "ارزش بار حداکثر ۵۰ حرف مجاز است"),
  vehicle_type: requiredText(2, "نوع وسیله الزامی است", 100, "نوع وسیله حداکثر ۱۰۰ حرف مجاز است"),
  driver_phone: z.string().transform((value) => digitsOnly(value)).refine((value) => /^09\d{9}$/.test(value), "تلفن راننده باید ۱۱ رقم باشد و با ۰۹ شروع شود (مثال: ۰۹۱۲۳۴۵۶۷۸۹)"),
  sender_name: requiredText(2, "نام فرستنده الزامی است", 255, "نام فرستنده حداکثر ۲۵۵ حرف مجاز است"),
  sender_phone: z.string().transform((value) => digitsOnly(value)).refine((value) => /^09\d{9}$/.test(value), "تلفن فرستنده باید ۱۱ رقم باشد و با ۰۹ شروع شود (مثال: ۰۹۱۲۳۴۵۶۷۸۹)"),
  sender_national_code: z.string().transform((value) => digitsOnly(value)).refine((value) => /^\d{10}$/.test(value), "کد ملی فرستنده باید دقیقاً ۱۰ رقم باشد"),
  sender_address: requiredText(5, "آدرس فرستنده الزامی است", 500, "آدرس فرستنده حداکثر ۵۰۰ حرف مجاز است"),
  receiver_name: requiredText(2, "نام گیرنده الزامی است", 255, "نام گیرنده حداکثر ۲۵۵ حرف مجاز است"),
  receiver_phone: z.string().transform((value) => digitsOnly(value)).refine((value) => /^09\d{9}$/.test(value), "تلفن گیرنده باید ۱۱ رقم باشد و با ۰۹ شروع شود (مثال: ۰۹۱۲۳۴۵۶۷۸۹)"),
  receiver_national_code: z.string().transform((value) => digitsOnly(value)).refine((value) => /^\d{10}$/.test(value), "کد ملی گیرنده باید دقیقاً ۱۰ رقم باشد"),
  receiver_address: requiredText(5, "آدرس گیرنده الزامی است", 500, "آدرس گیرنده حداکثر ۵۰۰ حرف مجاز است"),
  financial_cost: numericText("هزینه حمل الزامی است", "هزینه حمل باید عددی بزرگ‌تر از صفر باشد", 50, "هزینه حمل حداکثر ۵۰ حرف مجاز است"),
  financial_payment_method: optionalText(50, "روش پرداخت حداکثر ۵۰ حرف مجاز است"),
  shipping_two_way: z.boolean().default(false),
  shipping_time_limit: z.string().trim().min(1, "مهلت زمانی الزامی است").max(50, "مهلت زمانی حداکثر ۵۰ حرف مجاز است"),
  shipping_end_shipping: optionalText(100, "زمان پایان حمل حداکثر ۱۰۰ حرف مجاز است"),
  shipping_otp: optionalText(20, "OTP حداکثر ۲۰ حرف مجاز است"),
  notes: optionalText(500, "توضیحات حداکثر ۵۰۰ حرف مجاز است"),
});

export type WaybillFormValues = z.input<typeof waybillSchema>;
