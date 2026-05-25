"""Simulated waybill test to demonstrate the full process."""
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


class WaybillSimulator:
    """Simulate waybill creation process."""
    
    def __init__(self):
        self.events = []
        self.start_time = time.time()
        
    def log_event(self, step: str, status: str, details: str = ""):
        """Log simulation event."""
        elapsed = time.time() - self.start_time
        event = {
            "step": step,
            "status": status,
            "details": details,
            "elapsed": f"{elapsed:.2f}s"
        }
        self.events.append(event)
        
        # نمایش زنده
        icon = "✅" if status == "success" else "⏳" if status == "progress" else "❌"
        print(f"{icon} [{elapsed:6.2f}s] {step}: {details}")
    
    async def simulate_login(self):
        """Simulate UTCMS login."""
        self.log_event("ورود به سیستم", "progress", "در حال اتصال به UTCMS...")
        await asyncio.sleep(1)
        
        self.log_event("ورود به سیستم", "progress", "در حال حل کپچا...")
        await asyncio.sleep(2)
        
        self.log_event("ورود به سیستم", "success", "ورود موفق - توکن دریافت شد")
    
    async def simulate_form_fill(self):
        """Simulate form filling."""
        fields = [
            ("اطلاعات فرستنده", "شرکت حمل و نقل تست - تهران"),
            ("اطلاعات گیرنده", "شرکت دریافت کننده - اصفهان"),
            ("اطلاعات راننده", "احمد محمدی - کد ملی: 1234567890"),
            ("اطلاعات بار", "10 تن - کالای عمومی"),
            ("مسیر حمل", "تهران به اصفهان - 450 کیلومتر"),
        ]
        
        for field_name, field_value in fields:
            self.log_event("پر کردن فرم", "progress", f"{field_name}: {field_value}")
            await asyncio.sleep(0.5)
        
        self.log_event("پر کردن فرم", "success", "تمام فیلدها پر شد")
    
    async def simulate_validation(self):
        """Simulate form validation."""
        self.log_event("اعتبارسنجی", "progress", "بررسی صحت اطلاعات...")
        await asyncio.sleep(1)
        
        checks = [
            "کد ملی راننده معتبر است",
            "شماره پلاک صحیح است",
            "وزن بار در محدوده مجاز است",
            "مسیر حمل تایید شد"
        ]
        
        for check in checks:
            self.log_event("اعتبارسنجی", "progress", f"✓ {check}")
            await asyncio.sleep(0.3)
        
        self.log_event("اعتبارسنجی", "success", "تمام بررسی‌ها موفق")
    
    async def simulate_submission(self):
        """Simulate form submission."""
        self.log_event("ثبت بارنامه", "progress", "ارسال اطلاعات به سرور...")
        await asyncio.sleep(2)
        
        self.log_event("ثبت بارنامه", "progress", "در حال پردازش...")
        await asyncio.sleep(1)
        
        # شماره بارنامه شبیه‌سازی شده
        waybill_number = f"WB-{datetime.now().strftime('%Y%m%d')}-{int(time.time()) % 10000:04d}"
        
        self.log_event("ثبت بارنامه", "success", f"شماره بارنامه: {waybill_number}")
        
        return waybill_number
    
    async def simulate_verification(self, waybill_number: str):
        """Simulate waybill verification."""
        self.log_event("تایید نهایی", "progress", f"بررسی بارنامه {waybill_number}...")
        await asyncio.sleep(1)
        
        self.log_event("تایید نهایی", "success", "بارنامه با موفقیت در سیستم ثبت شد")
    
    def print_summary(self, waybill_number: str):
        """Print execution summary."""
        total_time = time.time() - self.start_time
        
        print("\n" + "=" * 80)
        print("📊 خلاصه اجرا")
        print("=" * 80)
        print(f"✅ وضعیت: موفق")
        print(f"📝 شماره بارنامه: {waybill_number}")
        print(f"⏱️  زمان کل: {total_time:.2f} ثانیه")
        print(f"📈 تعداد مراحل: {len(self.events)}")
        print("=" * 80)
        
        print("\n📋 جزئیات مراحل:")
        print("-" * 80)
        for event in self.events:
            print(f"  [{event['elapsed']:>7}] {event['step']}: {event['details']}")
        print("-" * 80)


async def run_simulation():
    """Run complete waybill simulation."""
    print("\n" + "=" * 80)
    print("🚀 شبیه‌سازی ثبت بارنامه در UTCMS")
    print("=" * 80)
    print("⚠️  توجه: این یک شبیه‌سازی است و به سیستم واقعی متصل نمی‌شود")
    print("=" * 80 + "\n")
    
    simulator = WaybillSimulator()
    
    try:
        # مراحل شبیه‌سازی
        await simulator.simulate_login()
        await simulator.simulate_form_fill()
        await simulator.simulate_validation()
        waybill_number = await simulator.simulate_submission()
        await simulator.simulate_verification(waybill_number)
        
        # خلاصه
        simulator.print_summary(waybill_number)
        
        return {"success": True, "waybill_number": waybill_number}
        
    except Exception as e:
        simulator.log_event("خطا", "error", str(e))
        return {"success": False, "error": str(e)}


def main():
    """Main entry point."""
    result = asyncio.run(run_simulation())
    
    if result.get('success'):
        print("\n✅ شبیه‌سازی با موفقیت انجام شد!")
        print(f"📝 شماره بارنامه: {result['waybill_number']}")
        sys.exit(0)
    else:
        print(f"\n❌ شبیه‌سازی ناموفق: {result.get('error', 'خطای نامشخص')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
