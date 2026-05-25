(function () {
  const managementTab = document.querySelector('.nav-item[data-tab="management-tools"]');
  if (!managementTab) {
    return;
  }

  const managementState = {
    hasLoaded: false,
    queueItems: [],
    accountItems: [],
    routeItems: [],
  };

  function managementRequest(path, options = {}) {
    return request(path, options, true);
  }

  async function managementUploadRequest(path, formData) {
    const headers = { ...getAuthHeaders() };
    delete headers["Content-Type"];
    const response = await fetch(path, {
      method: "POST",
      headers,
      body: formData,
    });
    let data;
    try {
      data = await response.json();
    } catch (_err) {
      data = { detail: "Invalid JSON response" };
    }
    addHistory("POST", path, response.status);
    if (!response.ok) {
      throw { status: response.status, data };
    }
    return data;
  }

  function textValue(id) {
    return document.getElementById(id)?.value?.trim() || "";
  }

  function optionalTextValue(id) {
    const value = textValue(id);
    return value || null;
  }

  function optionalNumberValue(id) {
    const value = textValue(id);
    if (!value) return null;
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
      throw new Error(`مقدار ${id} باید عدد معتبر باشد.`);
    }
    return numeric;
  }

  function checkboxValue(id) {
    return !!document.getElementById(id)?.checked;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function hashString(value) {
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
      hash = (hash << 5) - hash + value.charCodeAt(index);
      hash |= 0;
    }
    return Math.abs(hash).toString(36);
  }

  function generateRouteKey() {
    const seed = [
      textValue("management-route-name"),
      textValue("management-route-origin-province"),
      textValue("management-route-origin-city"),
      textValue("management-route-destination-province"),
      textValue("management-route-destination-city"),
      textValue("management-route-origin-lat"),
      textValue("management-route-origin-lng"),
      textValue("management-route-destination-lat"),
      textValue("management-route-destination-lng"),
    ]
      .filter(Boolean)
      .join("|");
    return `route-${hashString(seed || String(Date.now()))}`;
  }

  function summarizeArray(values) {
    if (!Array.isArray(values) || !values.length) return "-";
    return values.join("، ");
  }

  function badgeHtml(label, tone = "") {
    const className = ["badge", tone].filter(Boolean).join(" ");
    return `<span class="${className}">${escapeHtml(label)}</span>`;
  }

  function sessionBadge(row) {
    return row?.session_ready ? badgeHtml("ready", "ok") : badgeHtml("missing", "warn");
  }

  function otpBadge(row) {
    return row?.otp_needed ? badgeHtml("pending", "warn") : badgeHtml("clear", "ok");
  }

  function queueStatusBadge(status) {
    const normalized = String(status || "").toLowerCase();
    if (["submitted", "dispatched", "queued"].includes(normalized)) {
      return badgeHtml(normalized || "-", "ok");
    }
    if (["blocked", "retrying"].includes(normalized)) {
      return badgeHtml(normalized || "-", "warn");
    }
    if (["failed", "error"].includes(normalized)) {
      return badgeHtml(normalized || "-", "error");
    }
    return badgeHtml(normalized || "-");
  }

  function renderSummary(summary) {
    document.getElementById("management-summary-customers").textContent = summary.customers_count ?? 0;
    document.getElementById("management-summary-routes").textContent = summary.routes_count ?? 0;
    document.getElementById("management-summary-accounts").textContent = summary.accounts_count ?? 0;
    document.getElementById("management-summary-queue").textContent = summary.queue_count ?? 0;
    document.getElementById("management-summary-active-accounts").textContent = summary.active_accounts_count ?? 0;
    document.getElementById("management-summary-otp-accounts").textContent = summary.otp_accounts_count ?? 0;
    document.getElementById("management-summary-session-ready").textContent = summary.session_ready_accounts_count ?? 0;
    document.getElementById("management-summary-local-queue").textContent = summary.queued_local_items_count ?? 0;
    document.getElementById("management-summary-imported-queue").textContent = summary.imported_queue_items_count ?? summary.external_synced_items_count ?? 0;
  }

  function renderTable(containerId, columns, rows, emptyMessage) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!Array.isArray(rows) || !rows.length) {
      container.innerHTML = `<div class="management-empty">${escapeHtml(emptyMessage)}</div>`;
      return;
    }

    const header = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
    const body = rows
      .map((row) => {
        const cells = columns
          .map((column) => {
            if (typeof column.html === "function") {
              return `<td>${column.html(row)}</td>`;
            }
            const rawValue = typeof column.value === "function" ? column.value(row) : row?.[column.key];
            return `<td>${escapeHtml(rawValue ?? "-")}</td>`;
          })
          .join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");

    container.innerHTML = `<table class="management-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderCustomers(rows) {
    renderTable(
      "management-customers-list",
      [
        { label: "شناسه", key: "external_key" },
        { label: "نام", key: "full_name" },
        { label: "کیف پول", key: "wallet" },
        { label: "سقف راننده", key: "driver_limit" },
        { label: "فعال", value: (row) => (row.bot_running ? "بله" : "خیر") },
      ],
      rows.slice(0, 12),
      "هنوز مشتری مدیریتی ثبت نشده است."
    );
  }

  function renderRoutes(rows) {
    managementState.routeItems = rows;
    renderTable(
      "management-routes-list",
      [
        { label: "کلید", key: "route_key" },
        { label: "نام", key: "name" },
        { label: "مبدا", value: (row) => [row.origin_province, row.origin_city].filter(Boolean).join(" / ") || "-" },
        { label: "مقصد", value: (row) => [row.destination_province, row.destination_city].filter(Boolean).join(" / ") || "-" },
        { label: "فاصله", value: (row) => (row.distance_km != null ? `${row.distance_km} km` : "-") },
        {
          label: "عملیات",
          html: (row) =>
            `<button type="button" class="btn btn-ghost" data-management-action="select-route" data-route-key="${escapeHtml(row.route_key)}">انتخاب</button>`,
        },
      ],
      rows.slice(0, 12),
      "هنوز مسیری ثبت نشده است."
    );
  }

  function renderAccounts(rows) {
    managementState.accountItems = rows;
    renderTable(
      "management-accounts-list",
      [
        { label: "اکانت", key: "external_name" },
        { label: "مالک", key: "bot_owner" },
        { label: "مسیر", key: "route_key" },
        { label: "وضعیت", key: "status" },
        { label: "OTP", html: (row) => otpBadge(row) },
        { label: "Session", html: (row) => sessionBadge(row) },
        { label: "فعال", value: (row) => (row.start_shipping ? "بله" : "خیر") },
        {
          label: "عملیات",
          html: (row) =>
            [
              `<button type="button" class="btn btn-ghost" data-management-action="select-account" data-account-name="${escapeHtml(row.external_name)}">انتخاب</button>`,
              `<button type="button" class="btn btn-ghost" data-management-action="warm-account-session" data-account-name="${escapeHtml(row.external_name)}">Warm</button>`,
            ].join(" "),
        },
      ],
      rows.slice(0, 12),
      "هنوز اکانت عملیاتی ثبت نشده است."
    );
  }

  function renderQueue(rows) {
    managementState.queueItems = rows;
    renderTable(
      "management-queue-list",
      [
        { label: "Queue ID", key: "queue_item_id" },
        { label: "اکانت", key: "account_external_name" },
        { label: "مسیر", key: "route_key" },
        { label: "وضعیت", html: (row) => queueStatusBadge(row.status) },
        { label: "Payload", value: (row) => (row.payload ? "دارد" : "ندارد") },
        { label: "خطا/Block", value: (row) => row.last_error || "-" },
        {
          label: "عملیات",
          html: (row) =>
            `<button type="button" class="btn btn-ghost" data-management-action="dispatch-queue" data-queue-id="${escapeHtml(row.queue_item_id)}">Smart Dispatch</button>`,
        },
      ],
      rows.slice(0, 12),
      "صف محلی هنوز خالی است."
    );
  }

  function renderLogs(rows) {
    renderTable(
      "management-logs-list",
      [
        { label: "منبع", key: "source_system" },
        { label: "نوع", key: "sync_type" },
        { label: "وضعیت", key: "status" },
        { label: "خلاصه", value: (row) => JSON.stringify(row.summary || {}) },
      ],
      rows.slice(0, 8),
      "هنوز لاگی برای این بخش ثبت نشده است."
    );
  }

  function renderDiagnostics(payload) {
    const container = document.getElementById("management-diagnostics-list");
    if (!container) return;

    const readiness = payload?.readiness || {};
    const issues = payload?.issues || {};
    const summary = payload?.summary || {};
    const orderedIssues = Object.entries(issues).sort((left, right) => (right[1]?.count || 0) - (left[1]?.count || 0));

    const readinessHtml = `
      <div class="management-pill-list">
        <span class="management-pill">اکانت آماده: ${escapeHtml(readiness.accounts_ready_for_dispatch ?? 0)}</span>
        <span class="management-pill">مسیر آماده: ${escapeHtml(readiness.routes_ready ?? 0)}</span>
        <span class="management-pill">صف با Payload: ${escapeHtml(readiness.queued_with_payload ?? 0)}</span>
        <span class="management-pill">Session Ready: ${escapeHtml(summary.session_ready_accounts_count ?? 0)}</span>
        <span class="management-pill">OTP Pending: ${escapeHtml(summary.otp_accounts_count ?? 0)}</span>
      </div>
    `;

    if (!orderedIssues.length) {
      container.innerHTML = `${readinessHtml}<div class="management-empty">هنوز ایراد ساختاری شناسایی نشده است.</div>`;
      return;
    }

    const rows = orderedIssues
      .map(([key, value]) => {
        const label = key.replaceAll("_", " ");
        return `
          <tr>
            <td>${escapeHtml(label)}</td>
            <td>${escapeHtml(value?.count ?? 0)}</td>
            <td>${escapeHtml(summarizeArray(value?.samples || []))}</td>
          </tr>
        `;
      })
      .join("");

    container.innerHTML = `
      ${readinessHtml}
      <table class="management-table">
        <thead>
          <tr><th>شاخص عیب</th><th>تعداد</th><th>نمونه‌ها</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function renderImportResults(payload) {
    const container = document.getElementById("management-import-results");
    if (!container) return;

    const summary = payload?.summary || {};
    const imported = Array.isArray(payload?.imported) ? payload.imported : [];
    const errors = Array.isArray(payload?.errors) ? payload.errors : [];

    const rows = imported
      .slice(0, 10)
      .map(
        (item) => `
          <tr>
            <td>${escapeHtml(item.row_index)}</td>
            <td>${escapeHtml(item.account_external_name)}</td>
            <td>${escapeHtml(item.route_key)}</td>
            <td>${escapeHtml(item.queue_created ? "بله" : "خیر")}</td>
          </tr>
        `
      )
      .join("");

    const errorHtml = errors.length
      ? `<div class="management-empty">خطاها: ${escapeHtml(errors.slice(0, 5).map((item) => `ردیف ${item.row_index}: ${item.detail}`).join(" | "))}</div>`
      : `<div class="management-empty">خطای Import ثبت نشد.</div>`;

    container.innerHTML = `
      <div class="management-pill-list">
        <span class="management-pill">کل ردیف: ${escapeHtml(summary.rows_total ?? 0)}</span>
        <span class="management-pill">وارد شده: ${escapeHtml(summary.rows_imported ?? 0)}</span>
        <span class="management-pill">ناموفق: ${escapeHtml(summary.rows_failed ?? 0)}</span>
        <span class="management-pill">صف ساخته شده: ${escapeHtml(summary.queue_created ?? 0)}</span>
      </div>
      ${
        rows
          ? `<table class="management-table"><thead><tr><th>ردیف</th><th>اکانت</th><th>مسیر</th><th>صف</th></tr></thead><tbody>${rows}</tbody></table>`
          : `<div class="management-empty">هیچ ردیفی وارد نشده است.</div>`
      }
      ${errorHtml}
    `;
  }

  function buildCustomerPayload() {
    return {
      source_system: "local",
      external_key: textValue("management-customer-key"),
      full_name: textValue("management-customer-name"),
      wallet: optionalTextValue("management-customer-wallet"),
      driver_limit: optionalNumberValue("management-customer-driver-limit"),
      bot_running: checkboxValue("management-customer-bot-running"),
      bot_running_barname: checkboxValue("management-customer-barname-running"),
      auto_stop: checkboxValue("management-customer-auto-stop"),
      two_way: checkboxValue("management-customer-two-way"),
      raw: { source: "management-dashboard" },
    };
  }

  function buildRoutePayload() {
    const routeKey = textValue("management-route-key") || generateRouteKey();
    document.getElementById("management-route-key").value = routeKey;
    return {
      source_system: "local",
      route_key: routeKey,
      name: optionalTextValue("management-route-name"),
      origin_province: optionalTextValue("management-route-origin-province"),
      origin_city: optionalTextValue("management-route-origin-city"),
      origin_lat: optionalNumberValue("management-route-origin-lat"),
      origin_lng: optionalNumberValue("management-route-origin-lng"),
      destination_province: optionalTextValue("management-route-destination-province"),
      destination_city: optionalTextValue("management-route-destination-city"),
      destination_lat: optionalNumberValue("management-route-destination-lat"),
      destination_lng: optionalNumberValue("management-route-destination-lng"),
      distance_km: optionalNumberValue("management-route-distance"),
      duration_minutes: optionalNumberValue("management-route-duration"),
      enabled: checkboxValue("management-route-enabled"),
      recommended: checkboxValue("management-route-recommended"),
      raw: { source: "management-dashboard" },
    };
  }

  function buildAccountPayload() {
    return {
      source_system: "local",
      external_name: textValue("management-account-name"),
      bot_owner: optionalTextValue("management-account-owner"),
      title: optionalTextValue("management-account-title"),
      phone_number: optionalTextValue("management-account-phone"),
      national_code: optionalTextValue("management-account-national-code"),
      platform: optionalTextValue("management-account-platform"),
      status: optionalTextValue("management-account-status"),
      route_key: optionalTextValue("management-account-route-key"),
      otp_needed: checkboxValue("management-account-otp-needed"),
      has_account_is_enabled: true,
      has_driver_data: checkboxValue("management-account-driver-data"),
      has_truck_data: checkboxValue("management-account-truck-data"),
      has_valid_location: checkboxValue("management-account-valid-location"),
      start_shipping: checkboxValue("management-account-start-shipping"),
      two_way: checkboxValue("management-account-two-way"),
      custom_current_submit: optionalNumberValue("management-account-current-submit"),
      custom_target_submit: optionalNumberValue("management-account-target-submit"),
      time_interval: optionalNumberValue("management-account-time-interval"),
      last_success: optionalTextValue("management-account-last-success"),
      flags: { source: "management-dashboard" },
      raw: { source: "management-dashboard" },
    };
  }

  function buildQueuePayload(includeWaybillPayload) {
    const payload = {
      source_system: "local",
      account_external_name: optionalTextValue("management-queue-account-name"),
      route_key: optionalTextValue("management-queue-route-key"),
      bot_owner: optionalTextValue("management-queue-owner"),
      operation_mode: textValue("management-queue-operation-mode") || "safe",
      priority: optionalNumberValue("management-queue-priority") ?? 100,
      metadata: { source: "management-dashboard" },
    };
    if (includeWaybillPayload) {
      payload.waybill_payload = buildWaybillPayload();
    }
    return payload;
  }

  function buildBootstrapPayload() {
    const waybillPayload = buildWaybillPayload();
    const accountFallback =
      textValue("management-bootstrap-account-name") ||
      textValue("management-account-name") ||
      textValue("utcms-username") ||
      textValue("vehicle-driver-national-code") ||
      textValue("vehicle-plate");

    return {
      source_system: "local",
      customer_external_key:
        optionalTextValue("management-bootstrap-customer-key") ||
        optionalTextValue("management-customer-key") ||
        optionalTextValue("management-bootstrap-owner") ||
        "local-operations",
      customer_name:
        optionalTextValue("management-bootstrap-customer-name") ||
        optionalTextValue("management-customer-name") ||
        optionalTextValue("management-bootstrap-owner") ||
        "Local Operations",
      bot_owner:
        optionalTextValue("management-bootstrap-owner") ||
        optionalTextValue("management-account-owner") ||
        null,
      account_external_name: accountFallback || null,
      account_title:
        optionalTextValue("management-bootstrap-account-title") ||
        optionalTextValue("management-account-title") ||
        null,
      time_interval:
        optionalNumberValue("management-bootstrap-time-interval") ??
        optionalNumberValue("management-account-time-interval"),
      priority: optionalNumberValue("management-bootstrap-priority") ?? 100,
      create_queue: checkboxValue("management-bootstrap-create-queue"),
      waybill_payload: waybillPayload,
    };
  }

  function copyRouteFromWaybillForm() {
    document.getElementById("management-route-origin-province").value = textValue("origin-province");
    document.getElementById("management-route-origin-city").value = textValue("origin-city");
    document.getElementById("management-route-destination-province").value = textValue("destination-province");
    document.getElementById("management-route-destination-city").value = textValue("destination-city");
    document.getElementById("management-route-origin-lat").value = textValue("origin-lat");
    document.getElementById("management-route-origin-lng").value = textValue("origin-lng");
    document.getElementById("management-route-destination-lat").value = textValue("destination-lat");
    document.getElementById("management-route-destination-lng").value = textValue("destination-lng");
    document.getElementById("management-route-name").value =
      `${textValue("origin-city") || "مبدا"} ← ${textValue("destination-city") || "مقصد"}`;

    const originLat = Number(textValue("origin-lat"));
    const originLng = Number(textValue("origin-lng"));
    const destinationLat = Number(textValue("destination-lat"));
    const destinationLng = Number(textValue("destination-lng"));
    if ([originLat, originLng, destinationLat, destinationLng].every((value) => Number.isFinite(value))) {
      const preview = computeClientRoute(
        { lat: originLat, lng: originLng },
        { lat: destinationLat, lng: destinationLng }
      );
      document.getElementById("management-route-distance").value = preview.distanceKm;
      document.getElementById("management-route-duration").value = preview.durationMin;
    }
    notify("اطلاعات مسیر از فرم بارنامه کپی شد");
  }

  async function loadSummary(showInOutput = false) {
    const summary = await managementRequest("/management/summary");
    renderSummary(summary);
    if (showInOutput) {
      showOutput("خلاصه مدیریت حرفه‌ای", summary);
    }
    return summary;
  }

  async function loadCustomers(showInOutput = false) {
    const rows = await managementRequest("/management/customers");
    renderCustomers(rows);
    if (showInOutput) showOutput("لیست مشتری‌ها", rows);
    return rows;
  }

  async function loadRoutes(showInOutput = false) {
    const rows = await managementRequest("/management/routes");
    renderRoutes(rows);
    if (showInOutput) showOutput("لیست مسیرها", rows);
    return rows;
  }

  async function loadAccounts(showInOutput = false) {
    const rows = await managementRequest("/management/accounts");
    renderAccounts(rows);
    if (showInOutput) showOutput("لیست اکانت‌ها", rows);
    return rows;
  }

  async function warmAccountSession(accountName, button = null) {
    if (!accountName) {
      showOutput("خطا در Warm Session", { detail: "ابتدا اکانت را انتخاب کنید." }, true);
      return;
    }
    if (button) setLoading(button, true);
    try {
      const response = await managementRequest(`/management/accounts/${encodeURIComponent(accountName)}/warm-session`, {
        method: "POST",
      });
      showOutput("Warm Session اکانت", response);
      await Promise.all([loadSummary(false), loadAccounts(false), loadDiagnostics(false)]);
      notify(`Session برای اکانت ${accountName} آماده شد`);
    } catch (err) {
      showOutput("خطا در Warm Session", normalizeError(err), true);
    } finally {
      if (button) setLoading(button, false);
    }
  }

  async function loadQueue(showInOutput = false) {
    const rows = await managementRequest("/management/queue");
    renderQueue(rows);
    if (showInOutput) showOutput("صف مدیریت", rows);
    return rows;
  }

  async function loadLogs(showInOutput = false) {
    const rows = await managementRequest("/management/sync/logs");
    renderLogs(rows);
    if (showInOutput) showOutput("لاگ‌های مدیریت", rows);
    return rows;
  }

  async function loadDiagnostics(showInOutput = false) {
    const payload = await managementRequest("/management/diagnostics");
    renderDiagnostics(payload);
    if (showInOutput) showOutput("عیب‌یابی نهایی", payload, false);
    return payload;
  }

  async function refreshManagementDashboard(button = null, showInOutput = false) {
    if (button) setLoading(button, true);
    try {
      const [summary, diagnostics, customers, routes, accounts, queue, logs] = await Promise.all([
        loadSummary(false),
        loadDiagnostics(false),
        loadCustomers(false),
        loadRoutes(false),
        loadAccounts(false),
        loadQueue(false),
        loadLogs(false),
      ]);
      managementState.hasLoaded = true;
      if (showInOutput) {
        showOutput("داشبورد مدیریت حرفه‌ای", {
          summary,
          diagnostics,
          customers: customers.slice(0, 5),
          routes: routes.slice(0, 5),
          accounts: accounts.slice(0, 5),
          queue: queue.slice(0, 5),
          logs: logs.slice(0, 5),
        });
      }
      notify("داشبورد مدیریت بروزرسانی شد");
    } catch (err) {
      showOutput("خطا در داشبورد مدیریت", normalizeError(err), true);
    } finally {
      if (button) setLoading(button, false);
    }
  }

  async function saveCustomer(button) {
    setLoading(button, true);
    try {
      const payload = buildCustomerPayload();
      const response = await managementRequest("/management/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showOutput("ذخیره مشتری", response);
      await Promise.all([loadSummary(false), loadCustomers(false), loadDiagnostics(false)]);
      notify("مشتری ذخیره شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در ذخیره مشتری", { detail: err.message }, true);
      } else {
        showOutput("خطا در ذخیره مشتری", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function saveRoute(button) {
    setLoading(button, true);
    try {
      const payload = buildRoutePayload();
      const response = await managementRequest("/management/routes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      document.getElementById("management-account-route-key").value = response.route_key || payload.route_key;
      document.getElementById("management-queue-route-key").value = response.route_key || payload.route_key;
      showOutput("ذخیره مسیر", response);
      await Promise.all([loadSummary(false), loadRoutes(false), loadDiagnostics(false)]);
      notify("مسیر ذخیره شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در ذخیره مسیر", { detail: err.message }, true);
      } else {
        showOutput("خطا در ذخیره مسیر", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function saveAccount(button) {
    setLoading(button, true);
    try {
      const payload = buildAccountPayload();
      const response = await managementRequest("/management/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      document.getElementById("management-queue-account-name").value = response.external_name || payload.external_name;
      if (response.route_key) {
        document.getElementById("management-queue-route-key").value = response.route_key;
      }
      if (response.bot_owner) {
        document.getElementById("management-queue-owner").value = response.bot_owner;
      }
      showOutput("ذخیره اکانت", response);
      await Promise.all([loadSummary(false), loadAccounts(false), loadDiagnostics(false)]);
      notify("اکانت ذخیره شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در ذخیره اکانت", { detail: err.message }, true);
      } else {
        showOutput("خطا در ذخیره اکانت", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function createQueue(button, includeWaybillPayload = false) {
    setLoading(button, true);
    try {
      const payload = buildQueuePayload(includeWaybillPayload);
      const response = await managementRequest("/management/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      document.getElementById("management-dispatch-queue-id").value = response.queue_item_id || "";
      showOutput(includeWaybillPayload ? "ایجاد صف از فرم بارنامه" : "ایجاد آیتم صف", response);
      await Promise.all([loadSummary(false), loadQueue(false), loadDiagnostics(false)]);
      notify("آیتم صف ایجاد شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در ایجاد آیتم صف", { detail: err.message }, true);
      } else {
        showOutput("خطا در ایجاد آیتم صف", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function bootstrapCurrent(button) {
    setLoading(button, true);
    try {
      const payload = buildBootstrapPayload();
      const response = await managementRequest("/management/bootstrap/local", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showOutput("Bootstrap سناریوی کامل", response);
      if (response?.customer?.external_key) {
        document.getElementById("management-customer-key").value = response.customer.external_key;
      }
      if (response?.customer?.full_name) {
        document.getElementById("management-customer-name").value = response.customer.full_name;
      }
      if (response?.account?.external_name) {
        document.getElementById("management-account-name").value = response.account.external_name;
        document.getElementById("management-queue-account-name").value = response.account.external_name;
      }
      if (response?.route?.route_key) {
        document.getElementById("management-account-route-key").value = response.route.route_key;
        document.getElementById("management-queue-route-key").value = response.route.route_key;
        document.getElementById("management-route-key").value = response.route.route_key;
      }
      if (response?.queue_item?.queue_item_id) {
        document.getElementById("management-dispatch-queue-id").value = response.queue_item.queue_item_id;
      }
      await refreshManagementDashboard(null, false);
      notify("سناریوی کامل مدیریت ساخته شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در Bootstrap سناریو", { detail: err.message }, true);
      } else {
        showOutput("خطا در Bootstrap سناریو", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function importExcel(button) {
    setLoading(button, true);
    try {
      const fileInput = document.getElementById("management-excel-file");
      const file = fileInput?.files?.[0];
      if (!file) {
        throw new Error("ابتدا فایل اکسل را انتخاب کنید.");
      }

      const formData = new FormData();
      formData.append("file", file);
      formData.append("source_system", "local");
      formData.append("customer_external_key", textValue("management-excel-customer-key") || "excel-import");
      formData.append("customer_name", textValue("management-excel-customer-name") || "Excel Import");
      formData.append("bot_owner", textValue("management-excel-owner"));
      formData.append("default_province", textValue("management-excel-default-province") || "تهران");
      formData.append("default_city", textValue("management-excel-default-city") || "تهران");
      formData.append("operation_mode", textValue("management-excel-operation-mode") || "safe");
      formData.append("priority", String(optionalNumberValue("management-excel-priority") ?? 100));
      formData.append("include_auth", checkboxValue("management-excel-include-auth") ? "true" : "false");
      formData.append("create_queue", checkboxValue("management-excel-create-queue") ? "true" : "false");
      formData.append("reverse_geo_enabled", checkboxValue("management-excel-reverse-geo") ? "true" : "false");

      const response = await managementUploadRequest("/management/import/excel", formData);
      renderImportResults(response);
      showOutput("نتیجه Import اکسل", response);
      await refreshManagementDashboard(null, false);
      notify("Import اکسل با موفقیت انجام شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در Import اکسل", { detail: err.message }, true);
      } else {
        showOutput("خطا در Import اکسل", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  }

  async function dispatchQueue(queueId, button) {
    setLoading(button, true);
    try {
      const response = await managementRequest(`/management/queue/${encodeURIComponent(queueId)}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          warm_session_first: checkboxValue("management-dispatch-warm-session"),
          allow_otp_pending: checkboxValue("management-dispatch-allow-otp"),
        }),
      });
      showOutput("Dispatch صف", response);
      await Promise.all([loadSummary(false), loadQueue(false), loadDiagnostics(false)]);
      notify(response.status === "blocked" ? "Dispatch به‌علت OTP متوقف شد" : "آیتم صف Dispatch شد");
    } catch (err) {
      showOutput("خطا در Dispatch صف", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  }

  function fillQueueFromSelectedAccount() {
    document.getElementById("management-queue-account-name").value = textValue("management-account-name");
    document.getElementById("management-queue-route-key").value = textValue("management-account-route-key");
    document.getElementById("management-queue-owner").value = textValue("management-account-owner");
    notify("مشخصات صف از فرم اکانت کپی شد");
  }

  function selectRoute(routeKey) {
    const route = managementState.routeItems.find((item) => item.route_key === routeKey);
    if (!route) return;
    document.getElementById("management-route-key").value = route.route_key || "";
    document.getElementById("management-route-name").value = route.name || "";
    document.getElementById("management-route-origin-province").value = route.origin_province || "";
    document.getElementById("management-route-origin-city").value = route.origin_city || "";
    document.getElementById("management-route-destination-province").value = route.destination_province || "";
    document.getElementById("management-route-destination-city").value = route.destination_city || "";
    document.getElementById("management-route-origin-lat").value = route.origin_lat ?? "";
    document.getElementById("management-route-origin-lng").value = route.origin_lng ?? "";
    document.getElementById("management-route-destination-lat").value = route.destination_lat ?? "";
    document.getElementById("management-route-destination-lng").value = route.destination_lng ?? "";
    document.getElementById("management-route-distance").value = route.distance_km ?? "";
    document.getElementById("management-route-duration").value = route.duration_minutes ?? "";
    document.getElementById("management-route-enabled").checked = route.enabled !== false;
    document.getElementById("management-route-recommended").checked = !!route.recommended;
    document.getElementById("management-account-route-key").value = route.route_key || "";
    document.getElementById("management-queue-route-key").value = route.route_key || "";
    notify("مسیر برای ویرایش انتخاب شد");
  }

  function selectAccount(accountName) {
    const account = managementState.accountItems.find((item) => item.external_name === accountName);
    if (!account) return;
    document.getElementById("management-account-name").value = account.external_name || "";
    document.getElementById("management-account-owner").value = account.bot_owner || "";
    document.getElementById("management-account-title").value = account.title || "";
    document.getElementById("management-account-phone").value = account.phone_number || "";
    document.getElementById("management-account-national-code").value = account.national_code || "";
    document.getElementById("management-account-route-key").value = account.route_key || "";
    document.getElementById("management-account-status").value = account.status || "";
    document.getElementById("management-account-platform").value = account.platform || "Barname";
    document.getElementById("management-account-current-submit").value = account.custom_current_submit ?? "";
    document.getElementById("management-account-target-submit").value = account.custom_target_submit ?? "";
    document.getElementById("management-account-time-interval").value = account.time_interval ?? "";
    document.getElementById("management-account-last-success").value = account.last_success || "";
    document.getElementById("management-account-start-shipping").checked = !!account.start_shipping;
    document.getElementById("management-account-otp-needed").checked = !!account.otp_needed;
    document.getElementById("management-account-driver-data").checked = account.has_driver_data !== false;
    document.getElementById("management-account-truck-data").checked = account.has_truck_data !== false;
    document.getElementById("management-account-valid-location").checked = account.has_valid_location !== false;
    document.getElementById("management-account-two-way").checked = !!account.two_way;
    document.getElementById("management-queue-account-name").value = account.external_name || "";
    document.getElementById("management-queue-route-key").value = account.route_key || "";
    document.getElementById("management-queue-owner").value = account.bot_owner || "";
    notify("اکانت برای ویرایش انتخاب شد");
  }

  function bindManagementDelegation() {
    document.getElementById("management-tools").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-management-action]");
      if (!button) return;

      const action = button.dataset.managementAction;
      if (action === "select-route") {
        selectRoute(button.dataset.routeKey);
      }
      if (action === "select-account") {
        selectAccount(button.dataset.accountName);
      }
      if (action === "warm-account-session") {
        await warmAccountSession(button.dataset.accountName, button);
      }
      if (action === "dispatch-queue") {
        const queueId = button.dataset.queueId;
        document.getElementById("management-dispatch-queue-id").value = queueId || "";
        await dispatchQueue(queueId, button);
      }
    });
  }

  function bindManagementEvents() {
    document.getElementById("btn-management-refresh-summary").addEventListener("click", (event) => refreshManagementDashboard(event.currentTarget, true));
    document.getElementById("btn-management-diagnostics").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadDiagnostics(true);
        notify("عیب‌یابی نهایی انجام شد");
      } catch (err) {
        showOutput("خطا در عیب‌یابی نهایی", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });
    document.getElementById("btn-management-bootstrap-current").addEventListener("click", (event) => bootstrapCurrent(event.currentTarget));
    document.getElementById("btn-management-queue-current").addEventListener("click", (event) => createQueue(event.currentTarget, true));
    document.getElementById("btn-management-import-excel").addEventListener("click", (event) => importExcel(event.currentTarget));

    document.getElementById("btn-management-save-customer").addEventListener("click", (event) => saveCustomer(event.currentTarget));
    document.getElementById("btn-management-save-route").addEventListener("click", (event) => saveRoute(event.currentTarget));
    document.getElementById("btn-management-save-account").addEventListener("click", (event) => saveAccount(event.currentTarget));
    document.getElementById("btn-management-warm-session").addEventListener("click", (event) => {
      const accountName = textValue("management-account-name");
      warmAccountSession(accountName, event.currentTarget);
    });
    document.getElementById("btn-management-create-queue").addEventListener("click", (event) => createQueue(event.currentTarget, false));

    document.getElementById("btn-management-dispatch-queue").addEventListener("click", async (event) => {
      const queueId = textValue("management-dispatch-queue-id");
      if (!queueId) {
        showOutput("خطا در Dispatch صف", { detail: "ابتدا Queue Item ID را وارد کنید." }, true);
        return;
      }
      await dispatchQueue(queueId, event.currentTarget);
    });

    document.getElementById("btn-management-list-customers").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadCustomers(true);
      } catch (err) {
        showOutput("خطا در لیست مشتری‌ها", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });

    document.getElementById("btn-management-list-routes").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadRoutes(true);
      } catch (err) {
        showOutput("خطا در لیست مسیرها", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });

    document.getElementById("btn-management-list-accounts").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadAccounts(true);
      } catch (err) {
        showOutput("خطا در لیست اکانت‌ها", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });

    document.getElementById("btn-management-list-queue").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadQueue(true);
      } catch (err) {
        showOutput("خطا در لیست صف", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });

    document.getElementById("btn-management-list-logs").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      setLoading(button, true);
      try {
        await loadLogs(true);
      } catch (err) {
        showOutput("خطا در لاگ مدیریت", normalizeError(err), true);
      } finally {
        setLoading(button, false);
      }
    });

    document.getElementById("btn-management-copy-route-from-map").addEventListener("click", copyRouteFromWaybillForm);
    document.getElementById("btn-management-fill-queue-from-account").addEventListener("click", fillQueueFromSelectedAccount);

    managementTab.addEventListener("click", () => {
      if (!managementState.hasLoaded) {
        refreshManagementDashboard(null, false);
      }
    });
  }

  bindManagementEvents();
  bindManagementDelegation();
})();
