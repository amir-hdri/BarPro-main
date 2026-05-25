# Enterprise RPA Bot - Quick Reference Card

## 📦 New Modules Summary

| Module | Location | Size | Purpose |
|--------|----------|------|---------|
| **Advanced Stealth** | `app/automation/stealth_advanced.py` | 25KB | Anti-detection, WAF bypass, fingerprint spoofing |
| **Human Interaction** | `app/automation/human_interaction.py` | 18KB | Realistic typing, mouse movement, timing |
| **Resilience Engine** | `app/core/resilience.py` | 33KB | Exponential backoff, state tracking, graceful degradation |
| **Telemetry System** | `app/core/telemetry.py` | 33KB | Structured logging, evidence collection, client reports |
| **Resource Optimizer** | `app/automation/resource_optimizer.py` | 23KB | Memory management, lifecycle tracking, leak prevention |
| **Reporting Schema** | `app/schemas/enterprise_reporting.py` | 22KB | JSON schemas for all data structures |
| **Documentation** | `docs/enterprise_optimizations.md` | 28KB | Complete guide with examples |
| **Usage Examples** | `examples/enterprise_waybill_example.py` | 22KB | Production-ready code examples |

**Total: 8 files, 204KB of enterprise-grade code**

---

## 🚀 Quick Start

### 1. Apply Stealth Mode

```python
from app.automation.stealth_advanced import apply_enterprise_stealth

await apply_enterprise_stealth(page)
```

### 2. Human-Like Typing

```python
from app.automation.human_interaction import human_type, TypingProfile

await human_type(page, "#username", "admin", profile=TypingProfile.AVERAGE)
```

### 3. Resilient Retry

```python
from app.core.resilience import retry_with_backoff, RetryConfig

result = await retry_with_backoff(
    page.goto, 
    "https://portal.example",
    retry_config=RetryConfig(max_retries=3)
)
```

### 4. Track Workflow State

```python
from app.core.resilience import ResilientWorkflow

workflow = ResilientWorkflow(
    workflow_name="Login",
    workflow_id="login_001",
    page=page,
)

result = await workflow.execute(your_workflow_func)
```

### 5. Collect Evidence on Failure

```python
from app.core.telemetry import evidence_collector

evidence = await evidence_collector.capture_failure_evidence(
    page=page,
    workflow_id="wb_001",
    step_name="submit_waybill",
    error_code="SUBMISSION_FAILED",
    error_message="Portal returned 500",
)
```

### 6. Record Telemetry

```python
from app.core.telemetry import telemetry_collector

await telemetry_collector.record_step_start("login", workflow_id="wb_001")
await telemetry_collector.record_step_complete("login", duration_ms=1234.5, workflow_id="wb_001")
await telemetry_collector.record_step_failure("login", error_code="AUTH_TIMEOUT", error_message="...", workflow_id="wb_001")
```

### 7. Generate Client Report

```python
from app.core.telemetry import report_generator

report = report_generator.generate_client_report(
    workflow_state=workflow.state.to_dict(),
    evidence=evidence_list,
)
```

### 8. Manage Browser Resources

```python
from app.automation.resource_optimizer import (
    OptimizedBrowserPool,
    managed_browser_resource,
)

# Initialize pool
resource_pool = OptimizedBrowserPool(pool_size=8, enable_memory_tracking=True)
pool = await resource_pool.initialize_pool(browser)

# Use with automatic cleanup
async with managed_browser_resource(pool, workflow_id="wb_001") as (context, ctx_id):
    page = await context.new_page()
    # ... do work ...
```

---

## 🎯 Key Features Checklist

### ✅ Anti-Bot Evasion
- [x] Webdriver flag removal
- [x] Chrome runtime mocking
- [x] Playwright property deletion
- [x] WebGL fingerprint spoofing (Intel, NVIDIA, AMD)
- [x] Canvas fingerprint noise injection
- [x] AudioContext spoofing
- [x] Screen resolution randomization
- [x] User agent rotation
- [x] Cloudflare challenge handling
- [x] Imperva detection
- [x] Client hints spoofing
- [x] Language/plugin spoofing

### ✅ Human-Like Behavior
- [x] Variable typing delays (5 profiles)
- [x] Typo simulation & correction
- [x] Punctuation/capital pauses
- [x] Random hesitation
- [x] Bezier curve mouse movement
- [x] Hand tremor wobble
- [x] Hover-before-click
- [x] Human timing distributions
- [x] Reading simulation
- [x] Thinking pauses

### ✅ Error Handling
- [x] Exponential backoff retry
- [x] Jitter for thundering herd prevention
- [x] Explicit waits (no hard sleeps)
- [x] Element stability checking
- [x] Step-by-step state tracking
- [x] 20+ error categories
- [x] Graceful degradation
- [x] Automatic pausing on portal failure
- [x] Retryable vs non-retryable classification

### ✅ Telemetry & Reporting
- [x] JSON structured logging
- [x] Automatic screenshot capture
- [x] HTML DOM dump on failure
- [x] Console log capture
- [x] Page metadata collection
- [x] Evidence storage management
- [x] Client-friendly error messages
- [x] Severity levels
- [x] Recommended actions
- [x] Workflow progress tracking
- [x] Performance metrics (avg, p95, p99)

### ✅ Resource Optimization
- [x] Memory leak detection
- [x] Automatic garbage collection
- [x] Context lifecycle management
- [x] Stale context cleanup
- [x] Page cleanup before release
- [x] Memory usage monitoring
- [x] Configurable thresholds
- [x] Resource usage statistics
- [x] Concurrent processing support

---

## 📊 Error Code Reference

| Code | Category | User Message | Retryable |
|------|----------|--------------|-----------|
| `AUTH_INVALID_CREDENTIALS` | Auth | Invalid username or password | No |
| `AUTH_SESSION_EXPIRED` | Auth | Session expired, login again | Yes |
| `AUTH_CAPTCHA_FAILED` | Auth | CAPTCHA verification failed | Yes |
| `CAPTCHA_MAX_RETRY` | Auth | Too many CAPTCHA failures | No |
| `NET_TIMEOUT` | Network | Portal not responding | Yes |
| `NET_CONNECTION_REFUSED` | Network | Service unavailable | Yes |
| `BR_NAVIGATION_TIMEOUT` | Browser | Page loading too slow | Yes |
| `ELEMENT_NOT_FOUND` | Form | Portal interface changed | No |
| `WAYBILL_FORM_CHANGED` | Form | Form structure changed | No |
| `WAYBILL_SUBMISSION_FAILED` | Form | Submission failed | Yes |
| `MAP_LOADING_TIMEOUT` | Map | Map service unavailable | Yes |
| `PORTAL_DOWN` | Portal | Portal is down | No |
| `PORTAL_MAINTENANCE` | Portal | Under maintenance | No |
| `RATE_LIMITED` | Rate | Too many requests | Yes |

---

## 🔧 Configuration Reference

### Stealth Config

```python
StealthConfig(
    enable_core_stealth=True,        # Remove webdriver flags
    enable_webgl_spoof=True,         # Spoof GPU fingerprints
    enable_canvas_noise=True,        # Canvas fingerprint noise
    enable_audio_spoof=True,         # AudioContext spoofing
    enable_waf_bypass=True,          # WAF detection & bypass
    randomize_fingerprints=True,     # Randomize screen/locale
    enable_behavior_simulation=True, # Human behavior
)
```

### Retry Config

```python
RetryConfig(
    max_retries=3,                   # Max retry attempts
    base_delay=1.0,                  # Initial delay (seconds)
    max_delay=30.0,                  # Max delay cap
    exponential_base=2.0,            # Exponential multiplier
    jitter=True,                     # Add randomness
)
```

### Memory Tracker

```python
MemoryTracker(
    max_memory_mb=512.0,             # Hard limit
    warning_threshold_mb=384.0,      # Warning threshold
    check_interval_seconds=30.0,     # Check frequency
)
```

### Context Lifecycle

```python
ContextLifecycleManager(
    max_context_age_seconds=600.0,   # 10 min max age
    max_idle_seconds=300.0,          # 5 min idle timeout
    max_pages_per_context=10,        # Page limit
    max_operations_per_context=100,  # Operation limit
    success_rate_threshold=80.0,     # Min success rate
)
```

---

## 📖 Documentation Links

- **Full Guide**: `docs/enterprise_optimizations.md`
- **Code Examples**: `examples/enterprise_waybill_example.py`
- **JSON Schemas**: `app/schemas/enterprise_reporting.py`

---

## 🎓 Best Practices

### ✅ DO
- Use `apply_enterprise_stealth()` on every new page
- Use `human_type()` for all text input
- Use `retry_with_backoff()` for network operations
- Record telemetry for every step
- Use `managed_browser_resource()` for cleanup
- Capture evidence on failures
- Monitor memory usage

### ❌ DON'T
- Use `asyncio.sleep()` for synchronization
- Skip stealth configuration
- Use `page.fill()` for sensitive fields
- Ignore memory warnings
- Release contexts without cleanup
- Skip error categorization

---

## 🔍 Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot detected | Check stealth applied, verify WAF handling |
| Too slow | Reduce delays, check retry config |
| Memory leak | Run `memory_tracker.force_garbage_collection()` |
| Context stale | Check `lifecycle_manager.get_stale_contexts()` |
| Evidence missing | Verify `capture_evidence_on_failure=True` |
| Report unclear | Check `FRIENDLY_ERROR_MESSAGES` mapping |

---

## 📞 Support

When debugging:
1. Check `evidence/` directory for screenshots/HTML
2. Review telemetry: `telemetry_collector.get_workflow_telemetry(workflow_id)`
3. Check resource stats: `resource_pool.get_resource_stats()`
4. Review structured logs (JSON format)
5. Check memory: `memory_tracker.check_memory_usage()`
