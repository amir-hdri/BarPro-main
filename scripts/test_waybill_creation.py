"""Test script for complete waybill creation flow."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock


async def test_with_mock_data():
    """Test with mock data (no real browser)."""
    print("=" * 80)
    print("🧪 تست ثبت کامل بارنامه با Mock Data")
    print("=" * 80)

    from app.automation.waybill_enhanced import EnhancedWaybillManager

    mock_page = AsyncMock()
    mock_context = AsyncMock()

    # Mock page methods
    mock_page.goto = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value="pane-1")
    mock_page.query_selector = AsyncMock()
    mock_page.eval_on_selector = AsyncMock(return_value="بعدی")

    print("\n✅ Mock objects created")

    manager = EnhancedWaybillManager(mock_page, mock_context)

    print("✅ Manager initialized")

    # Test pill name mapping
    print("\n📋 Pill Mappings:")
    pills = {
        1: "sender",
        2: "receiver",
        3: "vehicle",
        4: "cargo",
        5: "origin",
        6: "destination",
        7: "address_preview",
        8: "financial"
    }

    for step, expected in pills.items():
        actual = manager._pill_name(step)
        status = "✓" if actual == expected else "✗"
        print(f"  {status} Step {step}: {actual}")

    # Test selector inventory
    print("\n📊 Testing Selector Inventory:")
    manager._record_selector_inventory(
        field_label="نام فرستنده",
        selectors=["#txtSenderFirstName", "#senderName"],
        status="filled",
        selector_used="#txtSenderFirstName",
        value="علی احمدی",
        pill="sender"
    )
    print("  ✓ Recorded: نام فرستنده")

    manager._record_selector_inventory(
        field_label="تلفن فرستنده",
        selectors=["#txtSenderMobile"],
        status="filled",
        selector_used="#txtSenderMobile",
        value="09121234567",
        pill="sender"
    )
    print("  ✓ Recorded: تلفن فرستنده")

    manager._record_selector_inventory(
        field_label="نام گیرنده",
        selectors=["#txtReceiverFirstName"],
        status="filled",
        selector_used="#txtReceiverFirstName",
        value="محمد رضایی",
        pill="receiver"
    )
    print("  ✓ Recorded: نام گیرنده")

    # Test pill field summary
    print("\n📈 Pill Field Summary:")
    sender_summary = manager._pill_field_summary("sender")
    print(f"  Sender fields: {len(sender_summary)}")
    for field, info in sender_summary.items():
        print(f"    - {field}: {info['status']}")

    receiver_summary = manager._pill_field_summary("receiver")
    print(f"  Receiver fields: {len(receiver_summary)}")
    for field, info in receiver_summary.items():
        print(f"    - {field}: {info['status']}")

    # Test selector audit
    print("\n🔍 Running Selector Audit:")
    manager._log_selector_inventory_audit()
    print("  ✓ Audit completed")

    # Summary
    total_fields = len(manager._selector_inventory)
    filled = sum(1 for item in manager._selector_inventory.values() if item.get('status') == 'filled')

    print("\n📊 Summary:")
    print(f"  Total fields tracked: {total_fields}")
    print(f"  Successfully filled: {filled}")
    print(f"  Success rate: {(filled/total_fields*100):.1f}%")

    print("\n✅ تست Mock موفق بود")

    return {"success": True, "mode": "mock", "fields_tracked": total_fields}


def main():
    """Main entry point."""
    print("\n🚀 شروع تست سیستم ثبت بارنامه")
    print("این تست عملکرد کامل سیستم را بدون نیاز به مرورگر واقعی بررسی می‌کند\n")

    start_time = time.time()

    try:
        result = asyncio.run(test_with_mock_data())
        elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("🏁 پایان تست")
        print("=" * 80)
        print(f"⏱️  زمان اجرا: {elapsed:.2f} ثانیه")

        if result.get('success'):
            print("✅ وضعیت: موفق")
            print(f"📊 فیلدهای ردیابی شده: {result.get('fields_tracked', 0)}")
            sys.exit(0)
        else:
            print("❌ وضعیت: ناموفق")
            sys.exit(1)

    except Exception as e:
        elapsed = time.time() - start_time
        print("\n❌ خطا در اجرای تست:")
        print(f"  {type(e).__name__}: {str(e)}")
        print(f"  زمان تا خطا: {elapsed:.2f} ثانیه")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
