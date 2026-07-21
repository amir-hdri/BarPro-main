"""Automated waybill test without user confirmation."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.real_waybill_test import real_waybill_test


def main():
    """Run waybill test automatically."""
    print("\n🚀 شروع تست اتوماتیک ثبت بارنامه...")

    result = asyncio.run(real_waybill_test())

    if result.get("success"):
        print("\n✅ ثبت بارنامه موفق بود!")
        sys.exit(0)
    else:
        print(f"\n❌ ثبت بارنامه ناموفق بود: {result.get('error', 'خطای نامشخص')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
