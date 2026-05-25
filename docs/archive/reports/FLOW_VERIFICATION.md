# بررسی Flow و ترتیب صحیح عملیات

## Flow اصلی ایجاد بارنامه

### 1. Entry Point
```python
EnhancedWaybillManager.create_waybill_with_map(data)
```

### 2. مراحل اصلی (به ترتیب)

#### مرحله 1: Navigation و Authentication
```
1. page.goto(WAYBILL_URL)
2. _handle_submit_captcha_if_present() - اگر نیاز باشد
3. _wait_for_page_ready()
```

#### مرحله 2: Pill Navigation (Bootstrap)
```
1. _detect_active_pane() - تشخیص pane فعلی
2. _navigate_to_pill(target_step) - رفتن به pill مورد نظر
3. _log_pill_transition() - ثبت transition در monitoring
   └─> monitoring_bridge.emit("waybill_pill_trace", ...)
```

#### مرحله 3: پر کردن اطلاعات فرستنده (Pill 1)
```
_fill_sender_info(sender):
  1. _select_dropdown_with_fallback("senderSelectType", "حقیقی")
  2. _fill_with_fallback(["#txtSenderFirstName", ...], sender_first, "نام فرستنده")
     └─> smart_locator.locate() - تلاش اول
     └─> interactor.safe_fill() - fallback
     └─> _set_value_with_js() - fallback نهایی
     └─> _record_selector_inventory() - ثبت نتیجه
  3. _fill_with_fallback(["#txtSenderLastName", ...], sender_last, "نام خانوادگی")
  4. _fill_verified_text_field(["#txtSenderMobile", ...], phone, "تلفن")
  5. _fill_verified_text_field(["#txtSenderNationalCode", ...], national_code, "کد ملی")
  6. interactor.safe_click("#btnGoLVL2") - رفتن به مرحله بعد
```

#### مرحله 4: پر کردن اطلاعات گیرنده (Pill 2)
```
_fill_receiver_info(receiver):
  1. _select_dropdown_with_fallback("receiverSelectType", "حقیقی")
  2. _fill_with_fallback(["#txtReceiverFirstName", ...], receiver_first, "نام گیرنده")
  3. _fill_with_fallback(["#txtReceiverLastName", ...], receiver_last, "نام خانوادگی")
  4. _fill_verified_text_field(["#txtReceiverMobile", ...], phone, "تلفن")
  5. _fill_verified_text_field(["#txtReceiverNationalCode", ...], national_code, "کد ملی")
  6. interactor.safe_click("#btnGoLVL3") - رفتن به مرحله بعد
```

#### مرحله 5: پر کردن اطلاعات وسیله نقلیه (Pill 3)
```
_fill_vehicle_info(vehicle):
  1. _fill_with_fallback(["#txtVehiclePlate", ...], plate, "پلاک")
  2. _select_dropdown_with_fallback(["#vehicleType", ...], vehicle_type, "نوع وسیله")
  3. interactor.safe_click("#btnGoLVL4") - رفتن به مرحله بعد
```

#### مرحله 6: پر کردن اطلاعات بار (Pill 4)
```
_fill_cargo_info(cargo):
  1. _fill_with_fallback(["#txtCargoWeight", ...], weight, "وزن بار")
  2. _select_dropdown_with_fallback(["#cargoType", ...], cargo_type, "نوع بار")
  3. _fill_with_fallback(["#txtCargoValue", ...], value, "ارزش بار")
  4. interactor.safe_click("#btnGoLVL5") - رفتن به مرحله بعد
```

#### مرحله 7: انتخاب مبدا و مقصد (Pills 5-6)
```
1. location_selector.select_location(origin, origin=True)
   └─> map_controller.open_map()
   └─> map_controller.set_marker(coordinates)
   └─> map_controller.confirm_selection()

2. location_selector.select_location(destination, origin=False)
   └─> map_controller.open_map()
   └─> map_controller.set_marker(coordinates)
   └─> map_controller.confirm_selection()

3. route_calculator.calculate_distance(origin, destination)
```

#### مرحله 8: اطلاعات مالی (Pill 8)
```
_fill_financial_info(financial):
  1. _fill_with_fallback(["#txtCost", ...], cost, "هزینه")
  2. _fill_with_fallback(["#txtFreight", ...], freight, "کرایه")
```

#### مرحله 9: ثبت نهایی
```
_submit_waybill(otp_value):
  1. _handle_submit_captcha_if_present() - اگر نیاز باشد
  2. interactor.safe_click("#btnSubmit")
  3. _wait_for_submission_result()
  4. _extract_tracking_code()
  5. _parse_register_submit_payload() - استخراج document_id
```

#### مرحله 10: Monitoring و Audit
```
1. _log_selector_inventory_audit()
   └─> monitoring_bridge.emit("waybill_selector_inventory_audit", ...)
   └─> event_hub.publish() - Real-time به UI
   └─> WAYBILL_SUCCESSES.labels(mode=mode).inc() - Prometheus

2. Return result:
   {
     "success": True,
     "tracking_code": "...",
     "route": {...},
     "document_id": "..."
   }
```

## Flow Monitoring Events

### Event Types و ترتیب ارسال

1. **waybill_create_started**
   - زمان: شروع create_waybill_with_map
   - Destination: Prometheus metrics

2. **waybill_pill_trace** (چندین بار)
   - زمان: هر transition بین pills
   - Destination: Timeline API + Logs
   - Payload: pill name, button clicked, success status

3. **waybill_selector_inventory_audit**
   - زمان: پایان فرآیند
   - Destination: Timeline API + Logs
   - Payload: تمام selectors استفاده شده و نتایج

4. **waybill_create_success** یا **waybill_create_failed**
   - زمان: پایان فرآیند
   - Destination: Prometheus metrics + Timeline API

## Flow Selector Fallback

### ترتیب تلاش برای پر کردن فیلد

```
_fill_with_fallback(selectors, value, field_label):
  
  1. Smart Locator (اولویت اول)
     ├─> smart_locator.locate(page, selectors)
     ├─> locator.fill(value)
     └─> SUCCESS → _record_selector_inventory(status="filled")
  
  2. Safe Fill Loop (fallback)
     ├─> for selector in selectors:
     │   ├─> interactor.safe_fill(selector, value)
     │   └─> SUCCESS → _record_selector_inventory(status="fallback-only")
     │
     └─> for selector in selectors:
         ├─> _set_value_with_js(selector, value)
         └─> SUCCESS → _record_selector_inventory(status="fallback-only")
  
  3. Final State
     ├─> All failed + required=True → raise WaybillError
     └─> All failed + required=False → _record_selector_inventory(status="unsupported")
```

## Database Query Flow

### Worker Processing (Celery)

```
1. Queue Query (با index جدید)
   SELECT * FROM waybilltask 
   WHERE status IN ('queued', 'pending')
   ORDER BY created_at
   LIMIT 1
   -- Uses: idx_waybilltask_status_created

2. Worker Assignment
   UPDATE waybilltask 
   SET status='in_progress', worker_id='worker-1'
   WHERE task_id='...'
   -- Uses: idx_waybilltask_worker_status

3. Retry Logic
   SELECT * FROM waybilltask
   WHERE retryable=true AND attempt_count < max_retries
   -- Uses: idx_waybilltask_retryable_attempt

4. Event Logging
   INSERT INTO domainevent (client_id, event_type, timestamp, ...)
   -- Uses: idx_domainevent_client_timestamp, idx_domainevent_event_type
```

### Multitenant Queries

```
1. Client-specific Jobs
   SELECT * FROM waybilljob
   WHERE client_id='...' AND status IN ('pending', 'queued')
   -- Uses: idx_waybilljob_client_status (partial index)

2. Driver Assignment
   SELECT * FROM waybilljob
   WHERE driver_id='...' AND status='in_progress'
   -- Uses: idx_waybilljob_driver_status

3. Monitoring Dashboard
   SELECT * FROM waybilljob
   WHERE created_at > NOW() - INTERVAL '1 day'
   ORDER BY created_at DESC
   -- Uses: idx_waybilljob_created_status
```

## Connection Pool Flow

```
Request → FastAPI Handler
  ↓
async_session_factory() → Get connection from pool
  ↓
Pool Check:
  ├─> Available connection? → Reuse (با pool_pre_ping health check)
  ├─> Pool full? → Create new (تا max_overflow=10)
  └─> All busy? → Wait (تا pool_timeout=30s)
  ↓
Execute Query
  ↓
Return connection to pool
  ↓
Auto-recycle after pool_recycle=3600s
```

## Test Flow

### Fast Unit Tests
```
TestWaybillEnhancedFast:
  setUp() → Create minimal mocks
    ↓
  test_*() → Test pure logic
    ↓
  tearDown() → Clean patches

Total: 16 tests in ~2.6s
```

### Integration Tests (قدیمی)
```
TestEnhancedWaybillManager:
  asyncSetUp() → Heavy mock setup
    ↓
  test_create_waybill_success() → Full flow simulation
    ↓
  asyncTearDown() → Cleanup

Total: 14 tests in ~30s (کند)
```

## بررسی صحت Flow

✅ **Navigation Flow**: صحیح - از login تا submit
✅ **Pill Transitions**: صحیح - با monitoring
✅ **Selector Fallback**: صحیح - 3 سطح fallback
✅ **Monitoring Events**: صحیح - به metrics و timeline
✅ **Database Queries**: بهینه - با indexes جدید
✅ **Connection Pool**: بهینه - با health checks
✅ **Test Coverage**: بهبود یافته - fast + integration

## نکات مهم

1. **Async Context**: همه operations async هستند
2. **Error Handling**: هر مرحله exception handling دارد
3. **Monitoring**: هر event به چند destination می‌رود
4. **Selector Inventory**: تمام تلاش‌ها ثبت می‌شوند
5. **Database Indexes**: queries بهینه شده‌اند
6. **Connection Pool**: concurrent requests را handle می‌کند
