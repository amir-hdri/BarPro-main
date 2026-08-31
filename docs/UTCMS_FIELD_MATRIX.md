# ماتریس فیلدها و سلکتورهای سامانه بارنامه شهری (UTCMS Field Matrix)

**مرجع:** استخراج مستقیم از پورتال `barname.utcms.ir/barname/Document/HagigiHogugi` (فاز ۱)  
**نسخه:** 2.0.0  
**تاریخ بازبینی:** اوت ۲۰۲۶  

---

## ۱. ساختار فرم‌های ۱۴ مرحله‌ای ویزارد صدور بارنامه

ویزارد صدور بارنامه در پورتال UTCMS متشکل از ۱۴ فرم است که اطلاعات طرفین، خودرو، راننده، کالا، مسیر (مبدأ و مقصد)، مالی و تأیید نهایی را دریافت می‌کنند.

| ایندکس | شناسه فرم (Form ID) | عنوان بخش | وضعیت کاربرد |
|---|---|---|---|
| 0 | `frmSender` | فرستنده (حقیقی / حقوقی) | اجباری |
| 1 | `frmReciver` | گیرنده (حقیقی / حقوقی) | اجباری |
| 2 | `frmpelakFavorit` | پلاک‌های نشان‌شده (Favorite) | اختیاری |
| 3 | `frmpelaqTajmi` | پلاک تجمیعی / ناوگان | مشروط (حالت تجمیعی) |
| 4 | `frmDriverTajmi` | راننده تجمیعی | مشروط (حالت تجمیعی) |
| 5 | `pelakbox` | پلاک عادی و مناطق آزاد | اجباری (در صورت غیرتجمیعی) |
| 6 | `frmDriverFavorit` | راننده نشان‌شده | اختیاری |
| 7 | `frmBar` | برآورد ارزش بار | اجباری |
| 8 | `frmmabda` | مبدأ (استان، شهر، آدرس متنی) | اجباری |
| 9 | `formmagsad` | مقصد (استان، شهر، آدرس متنی) | اجباری |
| 10 | `frmkeraye` | کرایه، زمان‌بندی و پیامک | اجباری |
| 11 | `frmcommodityInsert` | درج کالا، وزن و نوع بسته‌بندی | اجباری |
| 12 | `frmPrint` | صدور و چاپ سند بارنامه | گام ارسال نهایی |
| 13 | `GetOptCodeModal` | مودال تأیید پیامکی OTP (شناسهٔ واقعی؛ `FormSendOtpCode` نادرست بود) | مشروط به `obj.isOtpNeeded == true` در پاسخ ذخیره |

---

## ۲. ماتریس تفصیلی فیلدها (Field Matrix Specification)

### ۲.۱ فرم فرستنده (`frmSender`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی و Normalization | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| نوع فرستنده | `senderSelectType` | `senderSelectType` | select | بله | - | `1` (حقیقی)، `2` (حقوقی) | تبدیل به رشته عددی | `change`, `input` | `#senderSelectType` | `select[name="senderSelectType"]` | خواندن `value` و `selectedOptions[0].text` |
| نام شرکت/دفتر | `txtSenderOfficeName` | `txtSenderOfficeName` | text | مشروط (حقوقی) | 50 | نام فارسی معتبر | حذف فاصله‌های اضافی | `input`, `change`, `keyup` | `#txtSenderOfficeName` | `input[name="txtSenderOfficeName"]` | `element.value.trim()` |
| نام فرستنده | `txtSenderFirstName` | `txtSenderFirstName` | text | مشروط (حقیقی) | 20 | نام فارسی شخص | حذف کاراکترهای نامعتبر | `input`, `change`, `keyup` | `#txtSenderFirstName` | `input[name="txtSenderFirstName"]` | `element.value.trim()` |
| نام خانوادگی فرستنده | `txtSenderLastName` | `txtSenderLastName` | text | مشروط (حقیقی) | 50 | نام خانوادگی معتبر | تطبیق عدم تکرار نام | `input`, `change`, `keyup` | `#txtSenderLastName` | `input[name="txtSenderLastName"]` | `element.value.trim()` |
| موبایل فرستنده | `txtSenderMobile` | `txtSenderMobile` | text | خیر | 11 | 09xxxxxxxxx | تبدیل ارقام فارسی به انگلیسی | `input`, `change` | `#txtSenderMobile` | `input[name="txtSenderMobile"]` | `element.value.trim()` |
| کد ملی فرستنده | `txtSenderNationalCode` | `txtSenderNationalCode` | text | خیر | 11 | 10 یا 11 رقم | اعتبارسنجی الگوریتم کد ملی | `input`, `change` | `#txtSenderNationalCode` | `input[name="txtSenderNationalCode"]` | `element.value.trim()` |
| تلفن ثابت فرستنده | `txtSenderTell` | `txtSenderTell` | text | خیر | 11 | شماره ثابت با پیش‌شماره | تبدیل ارقام | `input`, `change` | `#txtSenderTell` | `input[name="txtSenderTell"]` | `element.value.trim()` |
| کد پستی فرستنده | `txtSenderPostalCode` | `txtSenderPostalCode` | text | خیر | 10 | 10 رقم عددی | تبدیل ارقام | `input`, `change` | `#txtSenderPostalCode` | `input[name="txtSenderPostalCode"]` | `element.value.trim()` |

---

### ۲.۲ فرم گیرنده (`frmReciver`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی و Normalization | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| نوع گیرنده | `receiverSelectType` | `receiverSelectType` | select | بله | - | `1` (حقیقی)، `2` (حقوقی) | تبدیل به رشته عددی | `change`, `input` | `#receiverSelectType` | `select[name="receiverSelectType"]` | خواندن `value` و `selectedOptions[0].text` |
| نام شرکت/دفتر گیرنده | `txtReceiverOfficeName` | `txtReceiverOfficeName` | text | مشروط (حقوقی) | 50 | نام معتبر شرکت | پاکسازی فضاها | `input`, `change`, `keyup` | `#txtReceiverOfficeName` | `input[name="txtReceiverOfficeName"]` | `element.value.trim()` |
| نام گیرنده | `txtReceiverFirstName` | `txtReceiverFirstName` | text | مشروط (حقیقی) | 50 | نام فارسی | پاکسازی فضاها | `input`, `change`, `keyup` | `#txtReceiverFirstName` | `input[name="txtReceiverFirstName"]` | `element.value.trim()` |
| نام خانوادگی گیرنده | `txtReceiverLastName` | `txtReceiverLastName` | text | مشروط (حقیقی) | 50 | نام خانوادگی فارسی | تطبیق عدم تکرار نام | `input`, `change`, `keyup` | `#txtReceiverLastName` | `input[name="txtReceiverLastName"]` | `element.value.trim()` |
| موبایل گیرنده | `txtReceiverMobile` | `txtReceiverMobile` | text | خیر | 11 | 09xxxxxxxxx | تبدیل ارقام فارسی | `input`, `change` | `#txtReceiverMobile` | `input[name="txtReceiverMobile"]` | `element.value.trim()` |
| کد ملی گیرنده | `txtReceiverNationalCode` | `txtReceiverNationalCode` | text | خیر | 11 | 10 یا 11 رقم | اعتبارسنجی کد ملی | `input`, `change` | `#txtReceiverNationalCode` | `input[name="txtReceiverNationalCode"]` | `element.value.trim()` |
| تلفن ثابت گیرنده | `txtReceiverTell` | `txtReceiverTell` | text | خیر | 11 | شماره ثابت | تبدیل ارقام | `input`, `change` | `#txtReceiverTell` | `input[name="txtReceiverTell"]` | `element.value.trim()` |
| کد پستی گیرنده | `txtReceiverPostalCode` | `txtReceiverPostalCode` | text | خیر | 10 | 10 رقم عددی | تبدیل ارقام | `input`, `change` | `#txtReceiverPostalCode` | `input[name="txtReceiverPostalCode"]` | `element.value.trim()` |

---

### ۲.۳ فرم پلاک عادی و مناطق آزاد (`pelakbox`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی و Normalization | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ۲ رقم سمت راست (ایران) | `pelakIrNum` | `pelakIrNum` | text | بله (ملی) | 2 | دو رقم کد ایران (مثال: 11) | ارقام انگلیسی | `input`, `change`, `keyup` | `#pelakIrNum` | `input[name="pelakIrNum"]` | `element.value.trim()` |
| ۳ رقم وسط پلاک | `pelakCenter` | `pelakCenter` | text | بله (ملی) | 3 | سه رقم (مثال: 293) | ارقام انگلیسی | `input`, `change`, `keyup` | `#pelakCenter` | `input[name="pelakCenter"]` | `element.value.trim()` |
| حرف میانی پلاک | `pelakCombo` | `pelakCombo` | select | بله (ملی) | - | کد ۱ تا ۳۲ مطابق حروف الف-ی | تطبیق حرف فارسی با کدهای ۱..۳۲ | `change`, `input` | `#pelakCombo` | `select[name="pelakCombo"]` | خواندن `value` و تطبیق حرف با متن |
| ۲ رقم سمت چپ پلاک | `pelakFirst` | `pelakFirst` | text | بله (ملی) | 2 | دو رقم (مثال: 21) | ارقام انگلیسی | `input`, `change`, `keyup` | `#pelakFirst` | `input[name="pelakFirst"]` | `element.value.trim()` |
| نوع منطقه آزاد | `pelakTypeCombo` | `pelakTypeCombo` | select | مشروط (آزاد) | - | ۱: اروند، ۲: انزلی، ۳: چابهار، ۴: قشم، ۵: کیش، ۶: ماکو، ۷: ارس | تطبیق کد منطقه | `change`, `input` | `#pelakTypeCombo` | `select[name="pelakTypeCombo"]` | خواندن `value` و متن منطقه |
| ۵ رقم پلاک منطقه آزاد | `pelakAzadFarsiNumber` | `pelakAzadFarsiNumber` | text | مشروط (آزاد) | 5 | ۵ رقم عددی | تبدیل ارقام | `input`, `change` | `#pelakAzadFarsiNumber` | `input[name="pelakAzadFarsiNumber"]` | `element.value.trim()` |
| ۲ رقم پلاک منطقه آزاد | `pelakAzadFarsiNumber3` | `pelakAzadFarsiNumber3` | text | مشروط (آزاد) | 2 | ۲ رقم عددی | تبدیل ارقام | `input`, `change` | `#pelakAzadFarsiNumber3` | `input[name="pelakAzadFarsiNumber3"]` | `element.value.trim()` |

---

### ۲.۴ فرم ناوگان و راننده تجمیعی (`frmpelaqTajmi`, `frmDriverTajmi`)
| نام فارسی | id | name | نوع کنترل | Required | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|
| انتخاب پلاک تجمیعی | `PelakComboTajmi` | `PelakComboTajmi` | select | مشروط | گزینه‌های لودشده ناوگان | بررسی عدم مقدار خالی/صفر | `change` | `#PelakComboTajmi` | `select[name="PelakComboTajmi"]` | `value` و `selectedOptions[0].text` |
| انتخاب راننده تجمیعی | `DriverListTajmi` | `DriverListTajmi` | select | مشروط | گزینه‌های لودشده رانندگان | بررسی عدم مقدار 0 | `change` | `#DriverListTajmi` | `select[name="DriverListTajmi"]` | `value` و `selectedOptions[0].text` |
| موبایل راننده تجمیعی | `DriverMobileTajmi` | `DriverMobileTajmi` | text (پرشده توسط فرم) | فقط خواندنی در عمل | موبایل ثبت‌شده راننده | خود UTCMS از `data-attr3` گزینه انتخاب‌شده پر می‌کند | ندارد (نتیجه `change` روی `DriverListTajmi`) | `#DriverMobileTajmi` | `input[name="DriverMobileTajmi"]` | `element.value.trim()` |
| نام راننده تجمیعی | `DriverFullNameTajmi` | `DriverFullNameTajmi` | text (پرشده توسط فرم) | فقط خواندنی در عمل | نام راننده ناوگان | همراه موبایل توسط فرم پر می‌شود | ندارد | `#DriverFullNameTajmi` | `input[name="DriverFullNameTajmi"]` | `element.value.trim()` |

> نکته‌ی تأییدشده روی نسخه‌ی زنده‌ی `hagigihogugitemplate.js` در ۱۴۰۵/۰۶/۰۶ (2026-08-28): گزینه‌های `DriverListTajmi` هویت راننده را در `data-attr3` (موبایل) حمل می‌کنند و هندلر `changeComboDriverClick` همان مقدار را در `DriverMobileTajmi` می‌نویسد. بنابراین موبایل راننده هرگز نباید تایپ شود؛ اگر فرم آن را پر کرده است، همان مقدار معتبر است.

---

### ۲.۴.۱ فرم راننده در حالت عادی (`frmDriver`)
| نام فارسی | id | name | نوع کنترل | Required | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|
| کد ملی راننده (جستجو) | `txtDriverSearch` | `txtDriverSearch` | text | بله | ۱۰ رقم کد ملی | ارقام انگلیسی | `input`, `change` | `#txtDriverSearch` | `input[name="txtDriverSearch"]` | `element.value.trim()` |
| دکمه مشاهده مشخصات راننده | `btnShowDetailsDriver` | - | button | بله | - | - | `click` | `#btnShowDetailsDriver` | `#driversearch` | فعال‌شدن فیلدهای زیر |
| نام راننده | `DriverFullName` | `DriverFullName` | text (پرشده توسط فرم) | فقط خواندنی در عمل | نام راننده بازگشتی از جستجو | - | ندارد | `#DriverFullName` | `input[name="DriverFullName"]` | `element.value.trim()` |
| موبایل راننده | `DriverMobile` | `DriverMobile` | text (پرشده توسط فرم) | فقط خواندنی در عمل | `result.obj.mobileNumber` پاسخ جستجو | - | ندارد | `#DriverMobile` | `input[name="DriverMobile"]` | `element.value.trim()` |
| شماره گواهی‌نامه | `DriverNumberDriverLicense` | `DriverNumberDriverLicense` | text (پرشده توسط فرم) | فقط خواندنی در عمل | `result.obj.driverLicenseId` | - | ندارد | `#DriverNumberDriverLicense` | `input[name="DriverNumberDriverLicense"]` | `element.value.trim()` |

> **هیچ فیلدی با شناسه `DriverPhone` در UTCMS وجود ندارد.** نام درست فیلد موبایل راننده `DriverMobile` (حالت عادی) و `DriverMobileTajmi` (حالت تجمیعی) است.
>
> **جستجوی مشخصات پلاک غیرفعال است:** در نسخه‌ی زنده‌ی `hagigihogugitemplate.js` کل فراخوانی `$.ajax` به `/Barname/Document/PlaqueSearch` کامنت شده است و تابع `PlaqueSearch` تنها ورودی‌های پلاک را اعتبارسنجی می‌کند. پس `TypeofLoader`، `CapacityFrom`، `CapacityTo`، `Activitylicense` و `ThirdPartyInsurance` طبق طراحیِ فعلیِ سامانه خالی می‌مانند و خالی‌بودن آن‌ها خطا نیست.

---

### ۲.۵ فرم ارزش بار (`frmBar`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ارزش تقریبی بار (ریال) | `txtLoadsValue` | `txtLoadsValue` | text | بله | 200 | عدد مثبت صحیح به ریال | ارقام بدون ویرگول | `input`, `change`, `keyup` | `#txtLoadsValue` | `input[name="txtLoadsValue"]` | `element.value.trim()` |

---

### ۲.۶ فرم مبدأ متنی (`frmmabda`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| استان مبدأ | `ddStateSource` | `ddStateSource` | select | بله | - | شناسه ۱..۳۳ استان‌های کشور | تطابق با ۳۳ استان رسمی | `change`, `input` | `#ddStateSource` | `select[name="ddStateSource"]` | `value` و `selectedOptions[0].text` |
| شهر مبدأ | `ddCitySource` | `ddCitySource` | select | بله | - | کد شهر لودشده با AJAX | تطابق یکتای نام شهر | `change`, `input` | `#ddCitySource` | `select[name="ddCitySource"]` | `value` و `selectedOptions[0].text` |
| آدرس دقیق مبدأ | `txtAddressSource` | `txtAddressSource` | textarea | بله | 250 | رشته آدرس متنی | غیرخالی، حداقل ۵ کاراکتر | `input`, `change`, `keyup` | `#txtAddressSource` | `textarea[name="txtAddressSource"]` | `element.value.trim()` |
| کد پستی مبدأ | `sourcePostalCode` | `sourcePostalCode` | text | خیر | 10 | ۱۰ رقم | تبدیل ارقام | `input`, `change` | `#sourcePostalCode` | `input[name="sourcePostalCode"]` | `element.value.trim()` |

---

### ۲.۷ فرم مقصد متنی (`formmagsad`)
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|---|
| استان مقصد | `ddStateDest` | `ddStateDest` | select | بله | - | شناسه ۱..۳۳ استان‌ها | تطابق با ۳۳ استان رسمی | `change`, `input` | `#ddStateDest` | `select[name="ddStateDest"]` | `value` و `selectedOptions[0].text` |
| شهر مقصد | `ddCityDest` | `ddCityDest` | select | بله | - | کد شهر لودشده با AJAX | تطابق یکتای نام شهر | `change`, `input` | `#ddCityDest` | `select[name="ddCityDest"]` | `value` و `selectedOptions[0].text` |
| آدرس دقیق مقصد | `txtAddressDest` | `txtAddressDest` | textarea | بله | 250 | رشته آدرس متنی | غیرخالی، حداقل ۵ کاراکتر | `input`, `change`, `keyup` | `#txtAddressDest` | `textarea[name="txtAddressDest"]` | `element.value.trim()` |
| کد پستی مقصد | `destPostalCode` | `destPostalCode` | text | خیر | 10 | ۱۰ رقم | تبدیل ارقام | `input`, `change` | `#destPostalCode` | `input[name="destPostalCode"]` | `element.value.trim()` |

---

### ۲.۸ فرم کرایه و زمان‌بندی (`frmkeraye`)
| نام فارسی | id | name | نوع کنترل | Required | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|
| مبلغ کرایه | `txtkeraye` | `txtkeraye` | text | خیر | عدد به ریال | تبدیل ارقام | `input`, `change` | `#txtkeraye` | `input[name="txtkeraye"]` | `element.value.trim()` |
| پیش‌کرایه | `txtPishKeraye` | `txtPishKeraye` | text | خیر | عدد به ریال | تبدیل ارقام | `input`, `change` | `#txtPishKeraye` | `input[name="txtPishKeraye"]` | `element.value.trim()` |
| پس‌کرایه | `txtPasKeraye` | `txtPasKeraye` | text | خیر | عدد به ریال | تبدیل ارقام | `input`, `change` | `#txtPasKeraye` | `input[name="txtPasKeraye"]` | `element.value.trim()` |
| ساعت شروع حمل | `loadingTime` | `loadingTime` | text | بله | فرمت HH:MM (مثال 08:30) | اعتبارسنجی ساعت | `input`, `change` | `#loadingTime` | `input[name="loadingTime"]` | `element.value.trim()` |
| ارسال پیامک به فرستنده | `sendsmsvalue` | `sendsmsvalue` | checkbox | خیر | true / false | وضعیت تیک چک‌باکس | `change`, `click` | `#sendsmsvalue` | `input[name="sendsmsvalue"]` | `element.checked` |

---

### ۲.۹ فرم کالا و بسته‌بندی (`frmcommodityInsert`)
| نام فارسی | id | name | نوع کنترل | Required | مقدار قابل قبول | اعتبارسنجی | Eventهای لازم | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|
| نام کالا | `txtLoadName` | `txtLoadName` | text | بله | عنوان فارسی کالا | حداقل ۲ کاراکتر | `input`, `change` | `#txtLoadName` | `input[name="txtLoadName"]` | `element.value.trim()` |
| وزن کالا (تن) | `txtWeight` | `txtWeight` | text | بله | عدد مثبت اعشاری یا صحیح | اعتبارسنجی بزرگتر از صفر | `input`, `change` | `#txtWeight` | `input[name="txtWeight"]` | `element.value.trim()` |
| نوع بسته‌بندی | `ddBoxType` | `ddBoxType` | select | بله | ۱۲ نوع رسمی (کارتن، کیسه، فله، ...) | انتخاب از گزینه‌های معتبر | `change`, `input` | `#ddBoxType` | `select[name="ddBoxType"]` | `value` و `selectedOptions[0].text` |
| تعداد بسته‌ها | `txtBoxNum` | `txtBoxNum` | number | خیر | عدد صحیح مثبت | عدد صحیح | `input`, `change` | `#txtBoxNum` | `input[name="txtBoxNum"]` | `element.value.trim()` |
| شرح جزئیات بار | `txtLoadDetail` | `txtLoadDetail` | textarea | خیر | حداکثر ۱۰۰ کاراکتر | پاکسازی متن | `input`, `change` | `#txtLoadDetail` | `textarea[name="txtLoadDetail"]` | `element.value.trim()` |

---

### ۲.۱۰ فرم ارسال و تأیید OTP (`GetOptCodeModal`)

> مودال از لحظهٔ لود صفحه در DOM هست (`modal fade`, `aria-hidden="true"`, `#otp`
> با کلاس `visually-hidden`, تایمر `02:00`). حضورش هیچ چیزی را اثبات نمی‌کند —
> فقط کلاس `.show` معنی‌دار است. دکمهٔ ارسال مجدد `#sendVerificationCode` است.
| نام فارسی | id | name | نوع کنترل | Required | MaxLength | مقدار قابل قبول | اعتبارسنجی | سلکتور اصلی | سلکتور جایگزین | روش Read-Back |
|---|---|---|---|---|---|---|---|---|---|---|
| کد OTP تأیید | `otp` | `otp` | text / tel | بله (در صورت نمایش مودال) | 6 | دقیقاً ۶ رقم | ارقام انگلیسی ۶ عددی | `#otp` | `input[name="otp"]` | `element.value.trim()` |
| دکمه تأیید OTP | `submitOtp` | - | button | - | - | کلیک تأیید | - | `#submitOtp` | `button:has-text('تایید')` | بررسی ناپدید شدن مودال |

---

## ۳. قواعد تطبیق و Read-Back اجباری

1. **ارزیابی همزمان Value و Label:** در کلیه منوهای آبشاری (Select)، علاوه بر بررسی شناسه مقدار (`value`)، برچسب متنی انتخاب‌شده (`selectedOptions[0].text`) با مقدار ورودی کاربر مقایسه می‌شود.
2. **منع انتخاب پیش‌فرض تصادفی:** انتخاب اولین آیتم در Dropdownها به عنوان حدس، مطلقاً ممنوع است.
3. **شکست در عدم انطباق Read-Back:** اگر پس از اجرای متد درج (`fill`) یا انتخاب (`select_option`)، مقدار بازخوانی‌شده از DOM با مقدار درخواستی کاربر تطابق دقیق نداشته باشد، مرحله جاری فوراً Fail شده و کار متوقف می‌گردد.
