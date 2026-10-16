# Phase 3: virtual-android-shipping-lifecycle-automation — Context

## Locked decisions

1. Direct UTCMS Mobile API transport (`UtcmsMobileClient`) remains the authoritative wire protocol for `/Document/RegisterStartOfShipping` and `/Document/RegisterEndOfShipping`.
2. Virtual Android Bridge (`AndroidShippingController` + `FakeTraveler`) provides mock location injection and ADB readback verification when enabled (`ANDROID_BRIDGE_ENABLED=true`); when disabled, the system falls back safely to verified `operator_anchor`.
3. An ambiguous "unknown" shipping state must not permanently brick waybills; a read-only reconciliation path against UTCMS portal history must decide whether the trip was accepted or can be safely retried.
4. Finish Shipping must strictly enforce Rule 4012 (minimum distance/travel time) and chronological waypoint simulation before wire submission.
5. FakeTraveler mock location provider must be torn down on all exit paths to avoid cross-job coordinate leakage.

## Approaches considered

### A — Direct UTCMS Mobile API with FakeTraveler ADB anchor injection
Combine direct HTTPS transport for UTCMS mobile endpoints with optional ADB-level FakeTraveler location injection and readback proof on Redroid.
What it buys: Full testability, headless operation on server, zero dependency on buggy UI automation of official app, strict two-witness proof.
What it costs: Requires maintaining ADB connection to Redroid and handling device locks across concurrent jobs.

### B — Complete UI automation of official APK inside Redroid
Launch and automate `com.baarnameshahri` via UI layout dumps and input taps for starting and ending shipping.
What it buys: Mimics human phone interaction.
What it costs: Fails in headless/emulator environments due to native anti-emulator/root checks (`SecurityNativeModule.detectMockLocationApps`); APK has no exported intents; fragile across UI updates.

chosen: A — because direct mobile transport is deterministic, resilient, and eliminates reverse-engineering/UI-automation brittleness while FakeTraveler supplies verified GPS anchors.
