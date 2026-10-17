# Phase 5: Recurring Waybill Cycling & Intelligent Scheduling — Context

## Locked decisions

1. **Smart Inversion Symmetry**: For recurring round-trip cycles ($A \to B \to A$), the return leg must swap origin $\leftrightarrow$ destination (including coordinates, city codes, and postal codes) and sender $\leftrightarrow$ receiver. Return sender postal code must match the return origin postal code to prevent UTCMS address-postal discrepancy rejections.
2. **Geographic Fleet Scope Pre-Dispatch Gate**: Fleet scope validation enforces the 31-province adjacency matrix (`IRAN_ADJACENT_PROVINCES`) before dispatch, immediately preventing UTCMS Rule 4028 (origin outside driver licensed city) and Rule 4045 (destination outside licensed or adjacent province) without wasting login or CAPTCHA budget.
3. **Realistic Road Speed & Rest Timing**: Transit duration calculations must use realistic heavy vehicle speeds (intercity 60 km/h, urban 28 km/h) combined with user-configurable safety/rest buffers (minimum 45 minutes) to satisfy UTCMS Rule 4013 (minimum required transit duration).
4. **Fail-Safe Chain Halt**: If any preceding leg in a multi-route cycling batch fails or enters `NEEDS_REVIEW`, the scheduler must halt subsequent legs automatically to protect driver portal accounts from cascading suspensions.

## Approaches considered

### A — Stateless Interval Cron Scheduling
Generates subsequent waybills purely via fixed periodic cron triggers without stateful origin/destination swapping or route geometry.
- What it buys: Minimal state overhead and simpler database models.
- What it costs: High failure rate on return legs due to postal-address mismatches, Rule 4028/4045 geographic boundary violations, and risk of overlapping active trips on the same license plate (violating Rule 4008).

### B — State-Machine Multi-Route Cycling with Smart Payload Inversion & Dynamic Road-Speed Profiles
Full-lifecycle multi-route engine that supports `standard`, `round_trip_cycling`, and `one_way_repeated` operational modes with symmetric payload inversion, road snapping, and chain-halt safety gates.
- What it buys: 100% compliance with UTCMS constraints, zero-rejection return legs, and deterministic trip sequencing.
- What it costs: Requires multi-tenant schema extensions, pre-dispatch fleet scope adjacency calculations, and custom schedule preview UI.

chosen: B — because UTCMS enforces strict geographic licensing (Rule 4028) and province adjacency (Rule 4045), making symmetric payload inversion and intelligent transit intervals mandatory for zero-rejection multi-leg cycles.
