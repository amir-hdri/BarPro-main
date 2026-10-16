---
issues: [97, 98]
---
# Phase 3: virtual-android-shipping-lifecycle-automation — Plan

## Tasks

- [ ] 97 — Resolve Start Shipping controller defects, ensure reliable ADB/FakeTraveler connection and implement unknown state reconciliation verify: pytest tests/test_android_bridge_controller.py tests/test_mobile_shipping_start_contract.py
- [ ] 98 — Resolve Finish Shipping defects, automate GPS waypoint simulation, and enforce Rule 4012 distance escalation verify: pytest tests/test_automated_shipping_lifecycle.py tests/test_shipping_worker.py tests/test_gps_shipping_batch_g.py
