"""Real waybill creation test with full monitoring."""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


class WaybillMonitor:
    """Monitor waybill creation process."""

    def __init__(self):
        self.events = []
        self.start_time = time.time()
        self.current_step = 0
        self.total_steps = 8

    def log_event(self, event_type, data):
        """Log an event with timestamp."""
        elapsed = time.time() - self.start_time
        event = {
            "timestamp": datetime.now().isoformat(),
            "elapsed": f"{elapsed:.2f}s",
            "type": event_type,
            "data": data,
        }
        self.events.append(event)

        # Print to console
        icon = self._get_icon(event_type)
        print(f"{icon} [{elapsed:6.2f}s] {event_type}: {self._format_data(data)}")

    def _get_icon(self, event_type):
        icons = {
            "start": "🚀",
            "step": "📝",
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️",
            "pill_transition": "🔄",
            "selector_fill": "📋",
            "map_selection": "🗺️",
            "submit": "📤",
        }
        return icons.get(event_type, "•")

    def _format_data(self, data):
        if isinstance(data, dict):
            return ", ".join(f"{k}={v}" for k, v in data.items())
        return str(data)

    def progress(self):
        """Show progress bar."""
        filled = int((self.current_step / self.total_steps) * 40)
        bar = "█" * filled + "░" * (40 - filled)
        percent = (self.current_step / self.total_steps) * 100
        print(f"\n[{bar}] {percent:.0f}% ({self.current_step}/{self.total_steps})")

    def summary(self):
        """Print summary."""
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 80)
        print("📊 خلاصه اجرا")
        print("=" * 80)
        print(f"⏱️  زمان کل: {elapsed:.2f} ثانیه")
        print(f"📋 تعداد events: {len(self.events)}")
        print(f"✅ مراحل تکمیل شده: {self.current_step}/{self.total_steps}")

        # Save to file
        log_file = (
            Path(__file__).parent.parent / "logs" / f"waybill_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        log_file.parent.mkdir(exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)
        print(f"💾 Log saved to: {log_file}")


async def real_waybill_test():
    """Test real waybill creation with monitoring."""

    monitor = WaybillMonitor()

    print("=" * 80)
    print("🚀 ثبت واقعی بارنامه با پایش کامل")
    print("=" * 80)

    # Check credentials
    from app.core.config import utcms_config

    if not utcms_config.UTCMS_USERNAME or not utcms_config.UTCMS_PASSWORD:
        print("\n❌ خطا: اطلاعات ورود تنظیم نشده است")
        print("لطفاً در فایل .env تنظیم کنید:")
        print("  UTCMS_USERNAME=your_username")
        print("  UTCMS_PASSWORD=your_password")
        return {"success": False, "error": "Missing credentials"}

    monitor.log_event("info", {"message": "Credentials found"})

    # Sample data
    waybill_data = {
        "sender": {
            "name": "علی احمدی",
            "phone": "09121234567",
            "national_code": "0123456789",
        },
        "receiver": {
            "name": "محمد رضایی",
            "phone": "09351234567",
            "national_code": "9876543210",
        },
        "origin": {
            "province": "تهران",
            "city": "تهران",
            "address": "میدان آزادی",
            "coordinates": {"lat": 35.6892, "lng": 51.3890},
        },
        "destination": {
            "province": "اصفهان",
            "city": "اصفهان",
            "address": "میدان نقش جهان",
            "coordinates": {"lat": 32.6546, "lng": 51.6680},
        },
        "vehicle": {"plate": "12ب34567", "type": "کامیون"},
        "cargo": {"type": "کالای عمومی", "weight": 5000, "value": 10000000},
        "financial": {"cost": 5000000, "freight": 4500000},
    }

    monitor.log_event(
        "info",
        {
            "sender": waybill_data["sender"]["name"],
            "receiver": waybill_data["receiver"]["name"],
            "route": f"{waybill_data['origin']['city']} → {waybill_data['destination']['city']}",
        },
    )

    try:
        monitor.log_event("start", {"message": "Launching browser"})

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--start-maximized"])

            context = await browser.new_context(viewport={"width": 1920, "height": 1080}, locale="fa-IR")

            page = await context.new_page()
            monitor.log_event("success", {"message": "Browser ready"})

            # Import manager
            from app.automation.waybill_enhanced import EnhancedWaybillManager

            manager = EnhancedWaybillManager(page, context)
            monitor.log_event("success", {"message": "Manager initialized"})

            # Hook into manager to monitor events
            original_log_pill = manager._log_pill_transition

            async def monitored_log_pill(*args, **kwargs):
                monitor.current_step += 1
                monitor.progress()
                monitor.log_event(
                    "pill_transition",
                    {
                        "current": kwargs.get("current_step"),
                        "target": kwargs.get("target_step"),
                        "button": kwargs.get("button_text", "N/A"),
                    },
                )
                return await original_log_pill(*args, **kwargs)

            manager._log_pill_transition = monitored_log_pill

            # Start creation
            monitor.log_event("start", {"message": "Starting waybill creation"})

            result = await manager.create_waybill_with_map(waybill_data)

            if result.get("success"):
                monitor.log_event(
                    "success",
                    {
                        "tracking_code": result.get("tracking_code", "N/A"),
                        "document_id": result.get("document_id", "N/A"),
                    },
                )

                if result.get("route"):
                    route = result["route"]
                    monitor.log_event(
                        "info", {"distance": route.get("distance", "N/A"), "duration": route.get("duration", "N/A")}
                    )
            else:
                monitor.log_event("error", {"error": result.get("error", "Unknown error")})

            # Selector inventory
            if hasattr(manager, "_selector_inventory"):
                inventory = manager._selector_inventory
                filled = sum(1 for item in inventory.values() if item.get("status") == "filled")
                fallback = sum(1 for item in inventory.values() if item.get("status") == "fallback-only")
                failed = sum(1 for item in inventory.values() if item.get("status") in ("unsupported", "failed"))

                monitor.log_event(
                    "info", {"total_fields": len(inventory), "filled": filled, "fallback": fallback, "failed": failed}
                )

            monitor.log_event("info", {"message": "Waiting 5s to view result"})
            await asyncio.sleep(5)

            await browser.close()
            monitor.log_event("success", {"message": "Browser closed"})

            monitor.summary()

            return result

    except Exception as e:
        monitor.log_event("error", {"exception": type(e).__name__, "message": str(e)})
        monitor.summary()
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


def main():
    """Main entry point."""
    print("\n⚠️  این تست یک بارنامه واقعی ثبت می‌کند!")
    print("اطمینان حاصل کنید که:")
    print("  1. اطلاعات ورود در .env تنظیم شده است")
    print("  2. دسترسی به سیستم UTCMS دارید")
    print("  3. داده‌های تست صحیح هستند")
    print("\nآیا ادامه می‌دهید؟ (yes/no): ", end="")

    response = input().strip().lower()
    if response not in ["yes", "y"]:
        print("❌ لغو شد")
        return

    result = asyncio.run(real_waybill_test())

    if result.get("success"):
        print("\n✅ ثبت بارنامه موفق بود!")
        sys.exit(0)
    else:
        print("\n❌ ثبت بارنامه ناموفق بود")
        sys.exit(1)


if __name__ == "__main__":
    main()
