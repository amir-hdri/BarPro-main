import { useMemo } from "react";
import { WaybillFormData } from "../contexts/WaybillContext";

interface ValidationError {
  field: string;
  message: string;
}

interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
}

export function useFormValidation(formData: WaybillFormData): ValidationResult {
  return useMemo(() => {
    const errors: ValidationError[] = [];

    if (!formData.senderName.trim()) {
      errors.push({ field: "senderName", message: "نام فرستنده الزامی است" });
    }
    if (formData.senderPhone && !/^09\d{9}$/.test(formData.senderPhone)) {
      errors.push({ field: "senderPhone", message: "شماره تلفن نامعتبر است" });
    }
    if (formData.senderNationalCode && !/^\d{10}$/.test(formData.senderNationalCode)) {
      errors.push({ field: "senderNationalCode", message: "کد ملی باید 10 رقم باشد" });
    }

    if (!formData.receiverName.trim()) {
      errors.push({ field: "receiverName", message: "نام گیرنده الزامی است" });
    }
    if (formData.receiverPhone && !/^09\d{9}$/.test(formData.receiverPhone)) {
      errors.push({ field: "receiverPhone", message: "شماره تلفن نامعتبر است" });
    }

    if (!formData.originProvince.trim()) {
      errors.push({ field: "originProvince", message: "استان مبدا الزامی است" });
    }
    if (!formData.originCity.trim()) {
      errors.push({ field: "originCity", message: "شهر مبدا الزامی است" });
    }

    if (!formData.destinationProvince.trim()) {
      errors.push({ field: "destinationProvince", message: "استان مقصد الزامی است" });
    }
    if (!formData.destinationCity.trim()) {
      errors.push({ field: "destinationCity", message: "شهر مقصد الزامی است" });
    }

    if (!formData.cargoType.trim()) {
      errors.push({ field: "cargoType", message: "نوع بار الزامی است" });
    }

    if (!formData.driverNationalCode.trim()) {
      errors.push({ field: "driverNationalCode", message: "کد ملی راننده الزامی است" });
    } else if (!/^\d{10}$/.test(formData.driverNationalCode)) {
      errors.push({ field: "driverNationalCode", message: "کد ملی باید 10 رقم باشد" });
    }

    if (!formData.vehiclePlate.trim()) {
      errors.push({ field: "vehiclePlate", message: "پلاک خودرو الزامی است" });
    }

    return {
      isValid: errors.length === 0,
      errors,
    };
  }, [formData]);
}
