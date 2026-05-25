function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;
  const isHidden = sidebar.classList.contains("translate-x-full");
  setSidebarOpen(isHidden);
}

const output = document.getElementById("response-output");
const historyList = document.getElementById("request-history");
const toast = document.getElementById("toast");

const AUTH_STORAGE_KEY = "utcms_auth_state";
const THEME_STORAGE_KEY = "utcms_theme";
const ACTIVE_TAB_STORAGE_KEY = "utcms_active_tab";

let lastResponseData = { message: "Ready." };
const REQUEST_TIMEOUT_MS = 25000;
const STATUS_AUTO_REFRESH_INTERVAL_MS = 20000;
const CAPTCHA_MONITOR_POLL_INTERVAL_MS = 8000;
let captchaMonitorAuto = true;
let captchaMonitorTimerId = null;
let captchaMonitorInFlight = false;
let statusAutoRefreshTimerId = null;
let statusRefreshInFlight = null;
const MAP_COORDINATE_PRECISION = 6;
const DEFAULT_MAP_CENTER = { lat: 32.4279, lng: 53.688 };
const DEFAULT_MAP_ZOOM = 5;
const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

// Map state with click tracking
const mapState = {
  instance: null,
  originMarker: null,
  destinationMarker: null,
  routeLine: null,
  activeTarget: "origin",
  isReady: false,
  loadPromise: null,
  clickCount: { origin: 0, destination: 0 },
  lastClickTime: { origin: null, destination: null },
};

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 1119px)").matches;
}

function setSidebarOpen(open) {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("mobile-overlay");
  if (!sidebar || !overlay) return;

  if (open) {
    sidebar.classList.remove("translate-x-full");
    overlay.classList.remove("hidden");
  } else {
    sidebar.classList.add("translate-x-full");
    overlay.classList.add("hidden");
  }
}

function addHistory(method, path, status, durationMs = null) {
  const item = document.createElement("li");
  const now = new Date().toLocaleTimeString("fa-IR");
  const durationPart = typeof durationMs === "number" ? ` | ${durationMs.toFixed(0)}ms` : "";
  item.textContent = `${now} | ${method} ${path} | ${status}${durationPart}`;
  historyList.prepend(item);
  while (historyList.children.length > 12) {
    historyList.removeChild(historyList.lastChild);
  }
}

function normalizeError(err) {
  const status = err?.status;
  const detail = err?.data?.detail;

  if (status === 401) {
    return {
      status,
      detail: "عدم دسترسی: API Key/JWT نامعتبر است یا ارسال نشده.",
      raw: err?.data || err,
    };
  }

  if (status === 503 && typeof detail === "string" && detail.includes("API_KEY")) {
    return {
      status,
      detail: "تنظیمات امنیتی سرور کامل نیست (API_KEY روی سرور تنظیم نشده).",
      action: "در .env سرور API_KEY را تنظیم کنید یا در محیط تست API_AUTH_MODE=off قرار دهید.",
      raw: err?.data || err,
    };
  }

  return err;
}

function showOutput(title, data, isError = false) {
  lastResponseData = { title, data };
  output.className = isError ? "error" : "ok";
  output.textContent = `${title}\n\n${JSON.stringify(data, null, 2)}`;
}

function setMutedMessage(container, message) {
  if (!container) return;
  const paragraph = document.createElement("p");
  paragraph.className = "muted";
  paragraph.textContent = message;
  container.replaceChildren(paragraph);
}

function renderResultCard(container, { wrapperClass, title, message }) {
  if (!container) return;
  const wrapper = document.createElement("div");
  wrapper.className = wrapperClass;

  const heading = document.createElement("h4");
  heading.textContent = title;
  wrapper.appendChild(heading);

  if (message !== undefined && message !== null && String(message).trim()) {
    const text = document.createElement("p");
    text.textContent = String(message);
    wrapper.appendChild(text);
  }

  container.replaceChildren(wrapper);
}

function formatPercent(value) {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return "-";
  return `${(numeric * 100).toFixed(1)}%`;
}

function updateWaybillTaskSummary(payload) {
  const stateEl = document.getElementById("waybill-task-state");
  const celeryEl = document.getElementById("waybill-task-celery");
  const updatedEl = document.getElementById("waybill-task-updated");
  if (!stateEl || !celeryEl || !updatedEl) return;

  stateEl.textContent = payload?.status || payload?.state || "-";
  celeryEl.textContent = payload?.celery_task_id || payload?.worker_task_id || "-";
  const stamp = payload?.updated_at || payload?.submitted_at || payload?.created_at;
  updatedEl.textContent = stamp ? String(stamp) : "-";

  stateEl.classList.remove("ok", "error");
  const normalized = String(stateEl.textContent || "").toLowerCase();
  if (["succeeded", "submitted", "processing", "queued", "dispatched", "retrying"].includes(normalized)) {
    stateEl.classList.add("ok");
  }
  if (["failed", "dead_letter", "error", "rejected"].includes(normalized)) {
    stateEl.classList.add("error");
  }
}

function setLoading(button, loading) {
  if (!button) return;
  if (loading) {
    button.dataset.originalText = button.textContent;
    button.textContent = button.dataset.loadingText || "Loading...";
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function getAuthHeaders() {
  const apiKeyHeader = document.getElementById("api-key-header").value.trim() || "X-API-Key";
  const apiKeyValue = document.getElementById("api-key-value").value.trim();
  const jwtToken = document.getElementById("jwt-token").value.trim();
  const headers = { "Content-Type": "application/json" };

  if (apiKeyValue) {
    headers[apiKeyHeader] = apiKeyValue;
  }
  if (jwtToken) {
    headers.Authorization = `Bearer ${jwtToken}`;
  }
  return headers;
}

async function request(path, options = {}, withAuth = false) {
  const method = options.method || "GET";
  const controller = new AbortController();
  const startedAt = performance.now();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: withAuth ? { ...(options.headers || {}), ...getAuthHeaders() } : options.headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") {
      throw {
        status: 408,
        data: { detail: "درخواست به‌علت timeout متوقف شد. دوباره تلاش کنید." },
      };
    }
    throw {
      status: 0,
      data: { detail: "خطای شبکه یا عدم دسترسی به سرور رخ داد." },
    };
  } finally {
    clearTimeout(timeoutId);
  }

  let data;
  try {
    data = await response.json();
  } catch (_err) {
    data = { detail: "Invalid JSON response" };
  }

  const elapsedMs = performance.now() - startedAt;
  addHistory(method, path, response.status, elapsedMs);

  if (!response.ok) {
    throw { status: response.status, data };
  }
  return data;
}

function parseCoordinateValue(rawValue) {
  const value = String(rawValue ?? "").trim();
  if (!value) {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : Number.NaN;
}

function formatCoordinateValue(value) {
  return Number(value).toFixed(MAP_COORDINATE_PRECISION);
}

function validateCoordinate(lat, lng) {
  if (lat === null || lng === null) return { valid: false, error: "مختصات کامل نیست" };
  if (Number.isNaN(lat) || Number.isNaN(lng)) return { valid: false, error: "مقدار نامعتبر" };
  if (lat < -90 || lat > 90) return { valid: false, error: "عرض جغرافیایی باید بین -90 تا 90 باشد" };
  if (lng < -180 || lng > 180) return { valid: false, error: "طول جغرافیایی باید بین -180 تا 180 باشد" };
  if (lat === 0 && lng === 0) return { valid: false, error: "مختصات (0,0) نامعتبر است" };
  return { valid: true, error: null };
}

function toCoordinate(latId, lngId) {
  const latValue = parseCoordinateValue(document.getElementById(latId).value);
  const lngValue = parseCoordinateValue(document.getElementById(lngId).value);
  if (latValue === null && lngValue === null) {
    return null;
  }
  if (latValue === null || lngValue === null || Number.isNaN(latValue) || Number.isNaN(lngValue)) {
    throw new Error("مختصات مبدا/مقصد باید با latitude و longitude معتبر تکمیل شوند.");
  }
  const validation = validateCoordinate(latValue, lngValue);
  if (!validation.valid) {
    throw new Error(`مختصات نامعتبر: ${validation.error}`);
  }
  return { lat: latValue, lng: lngValue };
}

function buildWaybillPayload() {
  const utcmsUsername = document.getElementById("utcms-username").value.trim();
  const utcmsPassword = document.getElementById("utcms-password").value.trim();
  const utcmsLoginUrl =
    document.getElementById("utcms-login-url").value.trim() ||
    "https://barname.utcms.ir/Barname/Account/Login";

  if ((utcmsUsername && !utcmsPassword) || (!utcmsUsername && utcmsPassword)) {
    throw new Error("برای ورود UTCMS باید هم نام کاربری و هم رمز عبور را وارد کنید.");
  }

  // Get coordinates with validation
  const originCoords = toCoordinate("origin-lat", "origin-lng");
  const destCoords = toCoordinate("destination-lat", "destination-lng");

  if (!originCoords) {
    throw new Error("لطفاً نقطه مبدا را روی نقشه کلیک کنید یا مختصات را وارد نمایید.");
  }
  if (!destCoords) {
    throw new Error("لطفاً نقطه مقصد را روی نقشه کلیک کنید یا مختصات را وارد نمایید.");
  }

  // Validate coordinates are reasonable for Iran
  const originValidation = validateCoordinate(originCoords.lat, originCoords.lng);
  if (!originValidation.valid) {
    throw new Error(`مختصات مبدا نامعتبر: ${originValidation.error}`);
  }
  
  const destValidation = validateCoordinate(destCoords.lat, destCoords.lng);
  if (!destValidation.valid) {
    throw new Error(`مختصات مقصد نامعتبر: ${destValidation.error}`);
  }

  const payload = {
    session_id: document.getElementById("session-id").value.trim() || null,
    operation_mode: document.getElementById("operation-mode").value,
    sender: {
      name: document.getElementById("sender-name").value.trim(),
      phone: document.getElementById("sender-phone").value.trim(),
      address: document.getElementById("sender-address").value.trim(),
      national_code: document.getElementById("sender-national-code").value.trim(),
    },
    receiver: {
      name: document.getElementById("receiver-name").value.trim(),
      phone: document.getElementById("receiver-phone").value.trim(),
      address: document.getElementById("receiver-address").value.trim(),
    },
    origin: {
      province: document.getElementById("origin-province").value.trim(),
      city: document.getElementById("origin-city").value.trim(),
      district: document.getElementById("origin-district").value.trim() || null,
      address: document.getElementById("origin-address").value.trim(),
      coordinates: originCoords,
    },
    destination: {
      province: document.getElementById("destination-province").value.trim(),
      city: document.getElementById("destination-city").value.trim(),
      district: document.getElementById("destination-district").value.trim() || null,
      address: document.getElementById("destination-address").value.trim(),
      coordinates: destCoords,
    },
    cargo: {
      type: document.getElementById("cargo-type").value.trim() || null,
      weight: document.getElementById("cargo-weight").value.trim(),
      count: document.getElementById("cargo-count").value.trim(),
      description: document.getElementById("cargo-description").value.trim() || null,
    },
    vehicle: {
      driver_national_code: document.getElementById("vehicle-driver-national-code").value.trim() || null,
      driver_phone: document.getElementById("vehicle-driver-phone").value.trim() || null,
      plate: document.getElementById("vehicle-plate").value.trim() || null,
      type: document.getElementById("vehicle-type").value.trim() || null,
    },
    financial: {
      cost: document.getElementById("financial-cost").value.trim() || null,
      payment_method: document.getElementById("financial-payment-method").value.trim() || null,
    },
  };

  if (utcmsUsername && utcmsPassword) {
    payload.utcms_auth = {
      username: utcmsUsername,
      password: utcmsPassword,
      login_url: utcmsLoginUrl,
    };
  }

  return payload;
}

function buildSampleITMBPayload() {
  const now = Math.floor(Date.now() / 1000);
  return {
    InsertTime: now,
    InsertPosition: {
      Latitude: 35.6892,
      Longitude: 51.389,
      Altitude: 1200,
      Bearing: 90,
      NumberOfSatellite: 8,
      PDOP: 2,
      GPSSpeed: 0,
      GPSMaxSpeed: 0,
      GPSTotalTraveledDistance: 0,
    },
    bol: {
      PlaqueID: "1234567",
      PlaqueSN: 12,
      PlaqueType: "IRI",
      DriverNationalCode: "1234567890",
      OWNERNATIONALID: "12345678901",
      SenderType: 2,
      SenderName: "شرکت فرستنده نمونه",
      SenderAddress: "تهران، پایانه غرب",
      SenderCityCode: "1001",
      RecieverType: 2,
      RecieverName: "شرکت گیرنده نمونه",
      RecieverAddress: "اصفهان، پایانه صفه",
      RecieverCityCode: "1002",
      Freightage: 1000,
      PreFreightage: 200,
      FreightageTax: 100,
      CompanyCommission: 50,
      ITServiceCost: 30,
      InfoServiceCost: 20,
      InsuranceCosts: 10,
      TotalAmountPayment: 1410,
      SerialNo: now,
      IssuerNaCode: "0987654321",
      IssueDate: now,
      LoadingPlaceAddress: "مبدأ نمونه",
      OffLoadingPlaceAddress: "مقصد نمونه",
      Goods: [
        {
          GoodID: 10,
          WeightKg: 1500.5,
          Value: 2,
          PackingTypeID: 3,
          GoodtypeID: 1,
          Description: "کالای نمونه",
        },
      ],
    },
  };
}



function getCoordinateFieldGroup(target) {
  if (target === "destination") {
    return ["destination-lat", "route-destination-lat", "destination-lng", "route-destination-lng"];
  }
  return ["origin-lat", "route-origin-lat", "origin-lng", "route-origin-lng"];
}

function getCoordinatePair(target) {
  const [primaryLatId, routeLatId, primaryLngId, routeLngId] = getCoordinateFieldGroup(target);
  const latCandidates = [
    parseCoordinateValue(document.getElementById(routeLatId)?.value),
    parseCoordinateValue(document.getElementById(primaryLatId)?.value),
  ];
  const lngCandidates = [
    parseCoordinateValue(document.getElementById(routeLngId)?.value),
    parseCoordinateValue(document.getElementById(primaryLngId)?.value),
  ];
  const lat = latCandidates.find((value) => value !== null && !Number.isNaN(value));
  const lng = lngCandidates.find((value) => value !== null && !Number.isNaN(value));
  if (lat === undefined || lng === undefined) {
    return null;
  }
  return { lat, lng };
}

function syncCoordinateFields(target, lat, lng) {
  const [primaryLatId, routeLatId, primaryLngId, routeLngId] = getCoordinateFieldGroup(target);
  const formattedLat = formatCoordinateValue(lat);
  const formattedLng = formatCoordinateValue(lng);
  document.getElementById(primaryLatId).value = formattedLat;
  document.getElementById(routeLatId).value = formattedLat;
  document.getElementById(primaryLngId).value = formattedLng;
  document.getElementById(routeLngId).value = formattedLng;
}

function clearCoordinateFields(target) {
  const fieldIds = getCoordinateFieldGroup(target);
  fieldIds.forEach((fieldId) => {
    const element = document.getElementById(fieldId);
    if (element) {
      element.value = "";
    }
  });
}

function setMapStatus(message, isError = false) {
  const element = document.getElementById("map-click-status");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function setMapFallback(message = "", isError = false) {
  const element = document.getElementById("map-fallback-notice");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function updateMapSelectionIndicators() {
  const activeTarget = mapState.activeTarget === "origin" ? "مبدا" : "مقصد";
  document.getElementById("map-active-target").textContent = activeTarget;
  document.getElementById("map-origin-status").textContent = getCoordinatePair("origin") ? "ثبت شد" : "ثبت نشده";
  document.getElementById("map-destination-status").textContent = getCoordinatePair("destination") ? "ثبت شد" : "ثبت نشده";

  const originButton = document.getElementById("btn-map-target-origin");
  const destinationButton = document.getElementById("btn-map-target-destination");
  originButton.classList.toggle("is-active", mapState.activeTarget === "origin");
  destinationButton.classList.toggle("is-active", mapState.activeTarget === "destination");
  originButton.classList.toggle("btn-secondary", mapState.activeTarget === "origin");
  originButton.classList.toggle("btn-ghost", mapState.activeTarget !== "origin");
  destinationButton.classList.toggle("btn-secondary", mapState.activeTarget === "destination");
  destinationButton.classList.toggle("btn-ghost", mapState.activeTarget !== "destination");
}

function setActiveMapTarget(target) {
  mapState.activeTarget = target === "destination" ? "destination" : "origin";
  updateMapSelectionIndicators();
}

function computeClientRoute(origin, destination) {
  const earthRadiusKm = 6371;
  const lat1 = (origin.lat * Math.PI) / 180;
  const lat2 = (destination.lat * Math.PI) / 180;
  const dLat = ((destination.lat - origin.lat) * Math.PI) / 180;
  const dLng = ((destination.lng - origin.lng) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const distanceKm = earthRadiusKm * c;
  const durationMin = Math.round(distanceKm);

  return {
    distanceKm: Number(distanceKm.toFixed(2)),
    durationMin,
  };
}

function updateRoutePreviewFromPoints() {
  const origin = getCoordinatePair("origin");
  const destination = getCoordinatePair("destination");
  if (!origin || !destination) {
    document.getElementById("route-distance").textContent = "-";
    document.getElementById("route-duration").textContent = "-";
    document.getElementById("route-method").textContent = "-";
    return;
  }

  const preview = computeClientRoute(origin, destination);
  document.getElementById("route-distance").textContent = `${preview.distanceKm} km`;
  document.getElementById("route-duration").textContent = `${preview.durationMin} min`;
  document.getElementById("route-method").textContent = "click-preview";
}

function removeMapLayer(layerKey) {
  if (!mapState.instance || !mapState[layerKey]) return;
  mapState.instance.removeLayer(mapState[layerKey]);
  mapState[layerKey] = null;
}

function ensurePointMarker(target, coordinates) {
  if (!mapState.instance || !window.L || !coordinates) return;
  const layerKey = target === "destination" ? "destinationMarker" : "originMarker";
  const color = target === "destination" ? "#ef4444" : "#22c55e";
  const label = target === "destination" ? "مقصد" : "مبدا";

  if (!mapState[layerKey]) {
    mapState[layerKey] = window.L.circleMarker([coordinates.lat, coordinates.lng], {
      radius: 9,
      color,
      weight: 3,
      fillColor: color,
      fillOpacity: 0.32,
    }).addTo(mapState.instance);
  } else {
    mapState[layerKey].setLatLng([coordinates.lat, coordinates.lng]);
  }

  mapState[layerKey].bindPopup(
    `${label}<br>Lat: ${formatCoordinateValue(coordinates.lat)}<br>Lng: ${formatCoordinateValue(coordinates.lng)}`
  );
}

function refreshMapLayers(fitBounds = false) {
  const origin = getCoordinatePair("origin");
  const destination = getCoordinatePair("destination");

  updateMapSelectionIndicators();
  updateRoutePreviewFromPoints();

  if (!mapState.instance || !window.L) {
    return;
  }

  if (origin) ensurePointMarker("origin", origin);
  else removeMapLayer("originMarker");

  if (destination) ensurePointMarker("destination", destination);
  else removeMapLayer("destinationMarker");

  if (origin && destination) {
    const latLngs = [
      [origin.lat, origin.lng],
      [destination.lat, destination.lng],
    ];
    if (!mapState.routeLine) {
      mapState.routeLine = window.L.polyline(latLngs, {
        color: "#3b82f6",
        weight: 4,
        opacity: 0.8,
      }).addTo(mapState.instance);
    } else {
      mapState.routeLine.setLatLngs(latLngs);
    }

    if (fitBounds) {
      mapState.instance.fitBounds(latLngs, { padding: [30, 30] });
    }
    return;
  }

  removeMapLayer("routeLine");

  if (fitBounds && origin) {
    mapState.instance.setView([origin.lat, origin.lng], 13);
  } else if (fitBounds && destination) {
    mapState.instance.setView([destination.lat, destination.lng], 13);
  }
}

function setMapPoint(target, coordinates, { fitBounds = true } = {}) {
  const validation = validateCoordinate(coordinates.lat, coordinates.lng);
  if (!validation.valid) {
    setMapStatus(`خطا: ${validation.error}`, true);
    return false;
  }
  
  syncCoordinateFields(target, coordinates.lat, coordinates.lng);
  refreshMapLayers(fitBounds);
  
  // Track click
  mapState.clickCount[target] = (mapState.clickCount[target] || 0) + 1;
  mapState.lastClickTime[target] = Date.now();
  
  return true;
}

function handleMapClick(latlng) {
  if (!latlng || !Number.isFinite(latlng.lat) || !Number.isFinite(latlng.lng)) {
    setMapStatus("مختصات کلیک نامعتبر بود؛ دوباره روی نقشه کلیک کنید.", true);
    return;
  }

  // Validate coordinates are within Iran bounds (rough check)
  const iranBounds = {
    minLat: 25.0,
    maxLat: 40.0,
    minLng: 44.0,
    maxLng: 64.0,
  };
  
  const isOutsideIran = (
    latlng.lat < iranBounds.minLat || 
    latlng.lat > iranBounds.maxLat ||
    latlng.lng < iranBounds.minLng || 
    latlng.lng > iranBounds.maxLng
  );

  const target = mapState.activeTarget;
  const success = setMapPoint(target, latlng, { fitBounds: true });
  
  if (!success) {
    return;
  }

  // Reverse geocode to auto-fill province/city
  reverseGeocodeAndFill(latlng.lat, latlng.lng, target);

  if (isOutsideIran) {
    setMapStatus(
      `هشدار: نقطه انتخابی خارج از محدوده ایران است. ${target === "origin" ? "مبدا" : "مقصد"} ثبت شد اما ممکن است در سامانه بارنامه پذیرفته نشود.`,
      true
    );
  } else if (target === "origin") {
    setMapStatus("✓ مبدا با موفقیت ثبت شد. حالا مقصد را روی نقشه انتخاب کنید.");
    if (!getCoordinatePair("destination")) {
      setActiveMapTarget("destination");
    }
  } else {
    setMapStatus("✓ مقصد با موفقیت ثبت شد. می‌توانید بارنامه را ارسال کنید.");
  }
}

async function reverseGeocodeAndFill(lat, lng, target) {
  try {
    const response = await fetch(
      `/waybill/reverse-geocode?lat=${lat}&lng=${lng}`
    );
    
    if (!response.ok) return;
    
    const data = await response.json();
    if (!data.success || !data.province && !data.city) return;

    const prefix = target === "origin" ? "origin" : "destination";
    const manualPrefix = target === "origin" ? "manual-origin" : "manual-destination";
    
    // Fill main form fields
    if (data.province) {
      const provinceEl = document.getElementById(`${prefix}-province`);
      if (provinceEl && !provinceEl.value) provinceEl.value = data.province;
      
      const manualProvinceEl = document.getElementById(`${manualPrefix}-province`);
      if (manualProvinceEl && !manualProvinceEl.value) manualProvinceEl.value = data.province;
    }
    
    if (data.city) {
      const cityEl = document.getElementById(`${prefix}-city`);
      if (cityEl && !cityEl.value) cityEl.value = data.city;
      
      const manualCityEl = document.getElementById(`${manualPrefix}-city`);
      if (manualCityEl && !manualCityEl.value) manualCityEl.value = data.city;
    }
    
    if (data.district) {
      const districtEl = document.getElementById(`${prefix}-district`);
      if (districtEl && !districtEl.value) districtEl.value = data.district;
      
      const manualDistrictEl = document.getElementById(`${manualPrefix}-district`);
      if (manualDistrictEl && !manualDistrictEl.value) manualDistrictEl.value = data.district;
    }

    setMapStatus(
      `✓ ${target === "origin" ? "مبدا" : "مقصد"} ثبت شد | ${data.province || ""}، ${data.city || ""}`,
      false
    );
  } catch (err) {
    // Silent fail for reverse geocoding
    console.warn("Reverse geocoding failed:", err);
  }
}

function mirrorCoordinateInputs() {
  const groups = [
    ["origin-lat", "route-origin-lat"],
    ["origin-lng", "route-origin-lng"],
    ["destination-lat", "route-destination-lat"],
    ["destination-lng", "route-destination-lng"],
  ];

  groups.forEach((group) => {
    group.forEach((fieldId) => {
      const element = document.getElementById(fieldId);
      if (!element) return;
      element.addEventListener("input", (event) => {
        const value = event.currentTarget.value;
        group.forEach((targetId) => {
          if (targetId !== fieldId) {
            document.getElementById(targetId).value = value;
          }
        });
        refreshMapLayers(false);
      });
      element.addEventListener("change", () => refreshMapLayers(false));
    });
  });
}

function clearMapSelections() {
  clearCoordinateFields("origin");
  clearCoordinateFields("destination");
  removeMapLayer("originMarker");
  removeMapLayer("destinationMarker");
  removeMapLayer("routeLine");
  if (mapState.instance) {
    mapState.instance.setView([DEFAULT_MAP_CENTER.lat, DEFAULT_MAP_CENTER.lng], DEFAULT_MAP_ZOOM);
  }
  setActiveMapTarget("origin");
  setMapStatus("نقاط پاک شدند. دوباره از روی نقشه مبدا و مقصد را ثبت کنید.");
  refreshMapLayers(false);
}

function loadStylesheetOnce(url) {
  const existing = document.querySelector(`link[data-dynamic-style="${url}"]`);
  if (existing) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    link.dataset.dynamicStyle = url;
    link.onload = () => resolve();
    link.onerror = () => reject(new Error(`stylesheet_load_failed: ${url}`));
    document.head.appendChild(link);
  });
}

function loadScriptOnce(url) {
  const existing = document.querySelector(`script[data-dynamic-script="${url}"]`);
  if (existing && existing.dataset.loaded === "true") {
    return Promise.resolve();
  }
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`script_load_failed: ${url}`)), { once: true });
    });
  }

  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.dataset.dynamicScript = url;
    script.addEventListener("load", () => {
      script.dataset.loaded = "true";
      resolve();
    }, { once: true });
    script.addEventListener("error", () => reject(new Error(`script_load_failed: ${url}`)), { once: true });
    document.body.appendChild(script);
  });
}

function ensureMapEngine() {
  if (window.L) {
    return Promise.resolve();
  }
  if (mapState.loadPromise) {
    return mapState.loadPromise;
  }

  setMapFallback("در حال بارگذاری موتور نقشه...", false);
  mapState.loadPromise = Promise.all([
    loadStylesheetOnce(LEAFLET_CSS_URL),
    loadScriptOnce(LEAFLET_JS_URL),
  ])
    .then(() => {
      setMapFallback("");
    })
    .catch((error) => {
      setMapFallback("Leaflet بارگذاری نشد؛ می‌توانید مختصات را دستی وارد کنید.", true);
      throw error;
    });
  return mapState.loadPromise;
}

function initInteractiveMap() {
  const container = document.getElementById("interactive-route-map");
  if (!container) return;
  if (mapState.instance) return;

  updateMapSelectionIndicators();

  if (!window.L) {
    container.classList.add("is-unavailable");
    container.textContent = "بارگذاری موتور نقشه انجام نشد. هنوز می‌توانید مختصات را دستی وارد کنید.";
    setMapFallback("Leaflet بارگذاری نشد؛ برای ثبت کلیکی باید دسترسی به CDN فعال باشد.", true);
    return;
  }

  mapState.instance = window.L.map(container, {
    center: [DEFAULT_MAP_CENTER.lat, DEFAULT_MAP_CENTER.lng],
    zoom: DEFAULT_MAP_ZOOM,
    zoomControl: true,
    preferCanvas: true,
  });

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(mapState.instance);

  mapState.instance.on("click", (event) => handleMapClick(event.latlng));
  mapState.instance.whenReady(() => {
    mapState.isReady = true;
    setMapFallback("");
    setMapStatus("نقشه آماده است. هر نقطه‌ای که کلیک کنید دقیقاً ثبت می‌شود.");
    refreshMapLayers(true);
  });

  setTimeout(() => {
    if (mapState.instance) {
      mapState.instance.invalidateSize();
      refreshMapLayers(false);
    }
  }, 250);
}

async function initInteractiveMapOnDemand() {
  const container = document.getElementById("interactive-route-map");
  if (!container || mapState.instance) {
    return;
  }
  container.classList.remove("is-unavailable");
  container.textContent = "";
  try {
    await ensureMapEngine();
    initInteractiveMap();
  } catch (_err) {
    container.classList.add("is-unavailable");
    container.textContent = "موتور نقشه در این شبکه بارگذاری نشد. مختصات را دستی وارد کنید.";
  }
}

async function refreshStatus(options = {}) {
  const { force = false, silent = false } = options;
  if (statusRefreshInFlight && !force) {
    return statusRefreshInFlight;
  }

  const run = async () => {
    try {
      const [health, ready, authConfig] = await Promise.all([
        request("/healthz"),
        request("/readyz"),
        request("/auth-config"),
      ]);
      document.getElementById("health-status").textContent = health.status || "-";
      document.getElementById("ready-status").textContent = ready.status || "-";
      renderAuthConfig(authConfig);
      renderCheckBadge("itmb-config-status", ready?.checks?.itmb_config);
      renderCheckBadge("itmb-cache-status", ready?.checks?.itmb_baseinfo_cache);
      renderCheckBadge("itmb-live-status", ready?.checks?.itmb_live_probe);
      renderCheckDetail("itmb-config-detail", ready?.details?.itmb_config?.message);
      renderCheckDetail("itmb-cache-detail", ready?.details?.itmb_baseinfo_cache?.message);
      renderCheckDetail("itmb-live-detail", ready?.details?.itmb_live_probe?.message);
      try {
        const baseInfoStatus = await request("/waybill/baseinfo/status", {}, true);
        const meta = baseInfoStatus?.meta || {};
        renderMetaField("itmb-meta-ttl", meta.cache_ttl_seconds ? `${meta.cache_ttl_seconds}s` : "-");
        renderMetaField("itmb-meta-validate", meta.validation_enabled ? "enabled" : "disabled");
        renderMetaField("itmb-meta-live", meta.live_probe_enabled ? "enabled" : "disabled");
      } catch (_err) {
        renderMetaField("itmb-meta-ttl", "auth");
        renderMetaField("itmb-meta-validate", "auth");
        renderMetaField("itmb-meta-live", "auth");
      }

      try {
        const traffic = await request("/waybill/traffic-status", {}, true);
        document.getElementById("queue-status").textContent = traffic.queued_requests ?? "-";
        document.getElementById("active-status").textContent = traffic.active_requests ?? "-";
      } catch (_err) {
        document.getElementById("queue-status").textContent = "auth";
        document.getElementById("active-status").textContent = "auth";
      }
    } catch (err) {
      renderCheckBadge("itmb-config-status", "error");
      renderCheckBadge("itmb-cache-status", "error");
      renderCheckBadge("itmb-live-status", "error");
      renderCheckDetail("itmb-config-detail", "status fetch failed");
      renderCheckDetail("itmb-cache-detail", "status fetch failed");
      renderCheckDetail("itmb-live-detail", "status fetch failed");
      renderMetaField("itmb-meta-ttl", "error");
      renderMetaField("itmb-meta-validate", "error");
      renderMetaField("itmb-meta-live", "error");
      if (!silent) {
        showOutput("خطا در بروزرسانی وضعیت", err, true);
      }
    }
  };

  statusRefreshInFlight = run();
  try {
    return await statusRefreshInFlight;
  } finally {
    statusRefreshInFlight = null;
  }
}

function renderCaptchaMonitor(payload) {
  const attemptsEl = document.getElementById("captcha-monitor-attempts");
  const successesEl = document.getElementById("captcha-monitor-successes");
  const failuresEl = document.getElementById("captcha-monitor-failures");
  const windowRateEl = document.getElementById("captcha-monitor-window-rate");
  const totalRateEl = document.getElementById("captcha-monitor-total-rate");
  const alertBadge = document.getElementById("captcha-monitor-alert");
  const historyElement = document.getElementById("captcha-monitor-history");
  if (!attemptsEl || !successesEl || !failuresEl || !windowRateEl || !totalRateEl || !alertBadge || !historyElement) {
    return;
  }

  const totals = payload?.totals || {};
  const windowData = payload?.window || {};
  const history = Array.isArray(payload?.recent_history) ? payload.recent_history : [];
  const alert = payload?.alert?.level || "-";

  attemptsEl.textContent = totals.attempts ?? 0;
  successesEl.textContent = totals.successes ?? 0;
  failuresEl.textContent = totals.failures ?? 0;
  windowRateEl.textContent = formatPercent(windowData.failure_rate);
  totalRateEl.textContent = formatPercent(totals.failure_rate);

  alertBadge.classList.remove("ok", "warn", "error");
  alertBadge.textContent = alert;
  if (alert === "high") alertBadge.classList.add("error");
  else if (alert === "normal") alertBadge.classList.add("ok");
  else if (alert === "low" || alert === "insufficient_data") alertBadge.classList.add("warn");

  historyElement.replaceChildren();
  if (!history.length) {
    const item = document.createElement("li");
    item.textContent = "هنوز داده‌ای برای مانیتور کپچا ثبت نشده است.";
    historyElement.appendChild(item);
    return;
  }

  history
    .slice()
    .reverse()
    .forEach((entry) => {
      const item = document.createElement("li");
      const timestamp = entry?.timestamp ? new Date(entry.timestamp * 1000).toLocaleTimeString("fa-IR") : "--:--";
      const left = document.createElement("span");
      left.textContent = `${timestamp} | ${entry?.strategy || entry?.reason || "-"}`;

      const right = document.createElement("strong");
      const failed = entry?.status === "failure";
      right.className = failed ? "error" : "ok";
      right.textContent = failed ? `FAIL ${entry?.reason || ""}` : "OK";

      item.appendChild(left);
      item.appendChild(right);
      historyElement.appendChild(item);
    });
}

async function refreshCaptchaMonitor(button = null) {
  if (captchaMonitorInFlight && !button) {
    return;
  }

  captchaMonitorInFlight = true;
  if (button) setLoading(button, true);
  try {
    const payload = await request("/captcha/monitor?window=50");
    renderCaptchaMonitor(payload);
  } catch (err) {
    if (button) {
      showOutput("خطا در مانیتور کپچا", normalizeError(err), true);
    }
  } finally {
    if (button) setLoading(button, false);
    captchaMonitorInFlight = false;
  }
}

function applyCaptchaMonitorAutoState() {
  const toggle = document.getElementById("btn-captcha-monitor-toggle");
  if (!toggle) return;
  toggle.textContent = `Auto: ${captchaMonitorAuto ? "ON" : "OFF"}`;
}

function startCaptchaMonitorPolling() {
  if (captchaMonitorTimerId) {
    clearTimeout(captchaMonitorTimerId);
    captchaMonitorTimerId = null;
  }
  if (!captchaMonitorAuto) {
    return;
  }

  const runLoop = async () => {
    if (!captchaMonitorAuto) {
      captchaMonitorTimerId = null;
      return;
    }
    await refreshCaptchaMonitor();
    captchaMonitorTimerId = setTimeout(runLoop, CAPTCHA_MONITOR_POLL_INTERVAL_MS);
  };

  captchaMonitorTimerId = setTimeout(runLoop, CAPTCHA_MONITOR_POLL_INTERVAL_MS);
}

function stopStatusAutoRefresh() {
  if (statusAutoRefreshTimerId) {
    clearInterval(statusAutoRefreshTimerId);
    statusAutoRefreshTimerId = null;
  }
}

function startStatusAutoRefresh() {
  stopStatusAutoRefresh();
  statusAutoRefreshTimerId = setInterval(() => {
    if (document.hidden) {
      return;
    }
    refreshStatus({ silent: true });
  }, STATUS_AUTO_REFRESH_INTERVAL_MS);
}

function setupStatusRefreshLifecycle() {
  startStatusAutoRefresh();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      return;
    }
    refreshStatus({ silent: true });
  });
  window.addEventListener("beforeunload", stopStatusAutoRefresh);
}

function renderAuthConfig(authConfig) {
  const badge = document.getElementById("auth-mode-badge");
  const hint = document.getElementById("map-auth-hint");
  const mode = authConfig?.mode || "unknown";
  const hasApiKey = !!authConfig?.api_key_configured;
  const hasJwt = !!authConfig?.jwt_configured;

  badge.classList.remove("ok", "warn", "error");
  badge.textContent = mode;

  if (mode === "off" || mode === "none" || mode === "disabled") {
    badge.classList.add("ok");
    hint.textContent = "حالت امنیتی غیرفعال است؛ ابزارهای نقشه بدون API Key/JWT قابل استفاده هستند.";
    return;
  }

  const needApi = mode.includes("api_key");
  const needJwt = mode.includes("jwt");
  const satisfied =
    (mode === "api_key" && hasApiKey) ||
    (mode === "jwt" && hasJwt) ||
    (mode === "api_key_and_jwt" && hasApiKey && hasJwt) ||
    (mode === "api_key_or_jwt" && (hasApiKey || hasJwt));

  if (satisfied) {
    badge.classList.add("ok");
    hint.textContent = "پیکربندی امنیتی معتبر است. برای endpoint حساس مقدار معتبر را در بالا وارد کنید.";
  } else {
    badge.classList.add("warn");
    hint.textContent = "پیکربندی امنیتی سرور ناقص است؛ برای اجرای کامل ابزارهای نقشه، API_KEY/JWT را روی سرور تنظیم کنید.";
  }

  if ((needApi && !hasApiKey) || (needJwt && !hasJwt)) {
    badge.classList.add("error");
  }

  const captchaConfidenceInput = document.getElementById("captcha-min-confidence");
  if (captchaConfidenceInput && authConfig?.captcha_math_min_confidence !== undefined) {
    captchaConfidenceInput.value = String(authConfig.captcha_math_min_confidence);
  }
}

function renderCheckBadge(elementId, value) {
  const element = document.getElementById(elementId);
  if (!element) return;
  const normalized = (value || "-").toString().toLowerCase();
  element.textContent = normalized;
  element.classList.remove("ok", "warn", "error");
  if (normalized === "ok") {
    element.classList.add("ok");
    return;
  }
  if (normalized === "skipped") {
    element.classList.add("warn");
    return;
  }
  if (normalized === "error") {
    element.classList.add("error");
  }
}

function renderCheckDetail(elementId, detailValue) {
  const element = document.getElementById(elementId);
  if (!element) return;
  if (typeof detailValue === "string" && detailValue.trim()) {
    element.textContent = detailValue.trim();
    return;
  }
  element.textContent = "-";
}

function renderMetaField(elementId, value) {
  const element = document.getElementById(elementId);
  if (!element) return;
  if (value === null || value === undefined || value === "") {
    element.textContent = "-";
    return;
  }
  element.textContent = String(value);
}

function saveAuthState() {
  const data = {
    apiKeyHeader: document.getElementById("api-key-header").value,
    apiKeyValue: document.getElementById("api-key-value").value,
    jwtToken: document.getElementById("jwt-token").value,
  };
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(data));
  notify("اطلاعات احراز هویت ذخیره شد");
}

function loadAuthState() {
  const raw = localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    document.getElementById("api-key-header").value = data.apiKeyHeader || "X-API-Key";
    document.getElementById("api-key-value").value = data.apiKeyValue || "";
    document.getElementById("jwt-token").value = data.jwtToken || "";
  } catch (_err) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  }
}

function clearAuthState() {
  document.getElementById("api-key-header").value = "X-API-Key";
  document.getElementById("api-key-value").value = "";
  document.getElementById("jwt-token").value = "";
  localStorage.removeItem(AUTH_STORAGE_KEY);
  notify("اطلاعات احراز هویت پاک شد");
}

function fillSampleData() {
  const sample = {
    "sender-name": "شرکت نمونه بار",
    "sender-phone": "09120000000",
    "sender-national-code": "1234567890",
    "sender-address": "تهران، خیابان نمونه، پلاک ۱۰",
    "receiver-name": "گیرنده تست",
    "receiver-phone": "09350000000",
    "receiver-address": "اصفهان، میدان نقش جهان",
    "origin-province": "تهران",
    "origin-city": "تهران",
    "origin-address": "پایانه غرب",
    "origin-lat": "35.7000",
    "origin-lng": "51.4000",
    "destination-province": "اصفهان",
    "destination-city": "اصفهان",
    "destination-address": "پایانه صفه",
    "destination-lat": "32.6500",
    "destination-lng": "51.6800",
    "cargo-type": "مواد غذایی",
    "cargo-weight": "1200",
    "cargo-count": "20",
    "cargo-description": "ارسال تستی",
    "financial-cost": "3500000",
    "financial-payment-method": "cash",
    "vehicle-driver-national-code": "0012345678",
    "vehicle-driver-phone": "09121111111",
    "vehicle-plate": "12الف34567",
    "vehicle-type": "truck",
    "utcms-login-url": "https://barname.utcms.ir/Barname/Account/Login",
  };

  Object.entries(sample).forEach(([id, value]) => {
    const element = document.getElementById(id);
    if (element) {
      element.value = value;
    }
  });

  document.getElementById("route-origin-lat").value = "35.7000";
  document.getElementById("route-origin-lng").value = "51.4000";
  document.getElementById("route-destination-lat").value = "32.6500";
  document.getElementById("route-destination-lng").value = "51.6800";

  refreshMapLayers(true);
  notify("نمونه داده وارد شد");
}

function setupTabs() {
  const tabs = document.querySelectorAll(".nav-item");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const selected = tab.dataset.tab;
      if (!selected) return;
      setTab(selected);
      localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, selected);
      if (isMobileViewport()) {
        setSidebarOpen(false);
      }
    });
  });

  const preferredTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
  if (preferredTab) {
    setTab(preferredTab);
  }
}

function setupTheme() {
  const html = document.documentElement;
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "dark";
  html.setAttribute("data-theme", storedTheme);

  document.getElementById("btn-theme-toggle").addEventListener("click", () => {
    const nextTheme = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", nextTheme);
    localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
    notify(`تم ${nextTheme === "dark" ? "تیره" : "روشن"} فعال شد`);
  });
}

function setTab(tabId) {
  if (!tabId) return;
  const hasTab = Array.from(document.querySelectorAll(".nav-item")).some((item) => item.dataset.tab === tabId);
  const effectiveTab = hasTab ? tabId : "waybill-form";

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.tab === effectiveTab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === effectiveTab);
  });
  localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, effectiveTab);

  if (effectiveTab === "map-tools") {
    initInteractiveMapOnDemand().finally(() => {
      if (mapState.instance) {
        setTimeout(() => mapState.instance.invalidateSize(), 120);
      }
    });
  }
}

function setupSidebarControls() {
  const toggleButton = document.getElementById("btn-sidebar-toggle");
  const closeButton = document.getElementById("btn-sidebar-close");
  const backdrop = document.getElementById("mobile-overlay");
  if (toggleButton) {
    toggleButton.addEventListener("click", () => {
      const sidebar = document.getElementById("sidebar");
      const isHidden = sidebar?.classList.contains("translate-x-full");
      setSidebarOpen(isHidden);
    });
  }
  if (closeButton) {
    closeButton.addEventListener("click", () => setSidebarOpen(false));
  }
  if (backdrop) {
    backdrop.addEventListener("click", () => setSidebarOpen(false));
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setSidebarOpen(false);
    }
  });
  window.addEventListener("resize", () => {
    if (!isMobileViewport()) {
      setSidebarOpen(false);
    }
  });
}

function setupShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (!event.altKey) return;
    if (event.key === "1") setTab("waybill-form");
    if (event.key === "2") setTab("map-tools");
    if (event.key === "3") setTab("reports-tools");
    if (event.key === "4") setTab("management-tools");
    if (event.key === "6") setTab("itmb-ws-tools");
    if (event.key.toLowerCase() === "r") refreshStatus({ force: true });
  });
}

function setupHeroChips() {
  document.getElementById("chip-health").addEventListener("click", () => request("/healthz").then((data) => showOutput("Health", data)).catch((err) => showOutput("Health Error", normalizeError(err), true)));
  document.getElementById("chip-ready").addEventListener("click", () => request("/readyz").then((data) => showOutput("Ready", data)).catch((err) => showOutput("Ready Error", normalizeError(err), true)));
  document.getElementById("chip-auth").addEventListener("click", () => request("/auth-config").then((data) => showOutput("Auth Config", data)).catch((err) => showOutput("Auth Error", normalizeError(err), true)));
}

function downloadJson() {
  const blob = new Blob([JSON.stringify(lastResponseData, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "utcms-response.json";
  anchor.click();
  URL.revokeObjectURL(url);
}

async function smokeCheck(button) {
  setLoading(button, true);
  try {
    const [health, ready] = await Promise.all([request("/healthz"), request("/readyz")]);
    showOutput("Smoke Check", { health, ready });
    notify("Smoke check با موفقیت انجام شد");
  } catch (err) {
    showOutput("خطا در Smoke Check", err, true);
  } finally {
    setLoading(button, false);
  }
}

function bindEvents() {

  // Close sidebar when a navigation item is clicked on mobile
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      if (isMobileViewport()) {
        setSidebarOpen(false);
      }
    });
  });

  document.getElementById("btn-refresh-status").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      await refreshStatus({ force: true });
    } finally {
      setLoading(button, false);
    }
  });
  document.getElementById("btn-save-auth").addEventListener("click", saveAuthState);
  document.getElementById("btn-clear-auth").addEventListener("click", clearAuthState);
  document.getElementById("btn-fill-sample").addEventListener("click", fillSampleData);
  document.getElementById("btn-map-target-origin").addEventListener("click", () => {
    setActiveMapTarget("origin");
    setMapStatus("حالت انتخاب روی مبدا قرار گرفت. روی نقشه کلیک کنید.");
  });
  document.getElementById("btn-map-target-destination").addEventListener("click", () => {
    setActiveMapTarget("destination");
    setMapStatus("حالت انتخاب روی مقصد قرار گرفت. روی نقشه کلیک کنید.");
  });
  document.getElementById("btn-clear-map-points").addEventListener("click", clearMapSelections);

  document.getElementById("btn-copy-output").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(output.textContent);
      notify("خروجی کپی شد");
    } catch (_err) {
      notify("کپی خودکار ممکن نیست؛ متن را دستی کپی کنید");
    }
  });
  document.getElementById("btn-download-output").addEventListener("click", downloadJson);

  document.getElementById("btn-run-smoke").addEventListener("click", (event) => smokeCheck(event.currentTarget));

  document.getElementById("create-waybill-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = event.submitter;
    setLoading(submitButton, true);
    try {
      const payload = buildWaybillPayload();
      const queueRequested = submitButton?.id === "btn-submit-waybill-queue";
      const endpoint = queueRequested ? "/waybill/queue/create-with-map" : "/waybill/create-with-map";
      const data = await request(
        endpoint,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
        true
      );

      if (queueRequested) {
        showOutput("نتیجه صف‌بندی بارنامه", data);
        const taskId = data?.task_id || "";
        const taskInput = document.getElementById("queue-task-id");
        if (taskInput && taskId) {
          taskInput.value = taskId;
        }
        updateWaybillTaskSummary(data);
        notify(taskId ? `تسک صف ایجاد شد: ${taskId}` : "درخواست صف ثبت شد");
      } else {
        showOutput("نتیجه ثبت بارنامه", data);
        notify("درخواست بارنامه ارسال شد");
      }

      await refreshStatus();
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در ثبت بارنامه", { detail: err.message }, true);
        notify(err.message);
      } else {
        showOutput("خطا در ثبت بارنامه", normalizeError(err), true);
      }
    } finally {
      setLoading(submitButton, false);
    }
  });

  document.getElementById("btn-waybill-task-status").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const taskId = document.getElementById("queue-task-id").value.trim();
      if (!taskId) {
        throw new Error("ابتدا Task ID را وارد کنید.");
      }
      const data = await request(`/waybill/tasks/${encodeURIComponent(taskId)}`, {}, true);
      showOutput("وضعیت تسک صف", data);
      updateWaybillTaskSummary(data);
      notify("وضعیت تسک بروزرسانی شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در وضعیت تسک", { detail: err.message }, true);
      } else {
        showOutput("خطا در وضعیت تسک", normalizeError(err), true);
      }
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-waybill-queue-snapshot").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/waybill/queue/snapshot", {}, true);
      showOutput("Queue Snapshot", data);
      if (data?.queued !== undefined) {
        document.getElementById("queue-status").textContent = data.queued;
      }
      notify("اسنپ‌شات صف دریافت شد");
    } catch (err) {
      showOutput("خطا در Queue Snapshot", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-detect-map").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const sessionId = document.getElementById("session-id").value.trim();
      const path = sessionId ? `/waybill/detect-map?session_id=${encodeURIComponent(sessionId)}` : "/waybill/detect-map";
      const data = await request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, true);
      showOutput("نتیجه تشخیص نقشه", data);
      notify("بررسی نقشه انجام شد");
    } catch (err) {
      showOutput("خطا در تشخیص نقشه", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-traffic-status").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/waybill/traffic-status", {}, true);
      showOutput("وضعیت ترافیک", data);
      document.getElementById("queue-status").textContent = data.queued_requests ?? "-";
      document.getElementById("active-status").textContent = data.active_requests ?? "-";
    } catch (err) {
      showOutput("خطا در دریافت وضعیت ترافیک", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("route-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = event.submitter;
    setLoading(submitButton, true);
    try {
      const origin = toCoordinate("route-origin-lat", "route-origin-lng");
      const destination = toCoordinate("route-destination-lat", "route-destination-lng");
      if (!origin || !destination) {
        throw new Error("ابتدا مبدا و مقصد را از روی نقشه یا ورودی‌ها ثبت کنید.");
      }
      const payload = {
        origin,
        destination,
      };
      const data = await request(
        "/waybill/calculate-route",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
      );
      showOutput("نتیجه محاسبه مسیر", data);
      document.getElementById("route-distance").textContent = data.distance_km ? `${data.distance_km} km` : "-";
      document.getElementById("route-duration").textContent = data.duration_min ? `${data.duration_min} min` : "-";
      document.getElementById("route-method").textContent = data.method || "-";
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در محاسبه مسیر", { detail: err.message }, true);
      } else {
        showOutput("خطا در محاسبه مسیر", normalizeError(err), true);
      }
    } finally {
      setLoading(submitButton, false);
    }
  });

  document.getElementById("btn-report-summary").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/reports/summary", {}, true);
      showOutput("گزارش خلاصه", data);
    } catch (err) {
      showOutput("خطا در گزارش خلاصه", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-report-daily").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/reports/daily", {}, true);
      showOutput("گزارش روزانه", data);
    } catch (err) {
      showOutput("خطا در گزارش روزانه", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-report-operational").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/reports/operational", {}, true);
      showOutput("گزارش عملیاتی", data);
    } catch (err) {
      showOutput("خطا در گزارش عملیاتی", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-itmb-fill-sample").addEventListener("click", () => {
    document.getElementById("itmb-ws-payload").value = JSON.stringify(buildSampleITMBPayload(), null, 2);
    notify("نمونه WS01 وارد شد");
  });

  document.getElementById("btn-baseinfo-status").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const data = await request("/waybill/baseinfo/status", {}, true);
      showOutput("وضعیت کش BaseInfo", data);
    } catch (err) {
      showOutput("خطا در وضعیت BaseInfo", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("btn-baseinfo-refresh").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setLoading(button, true);
    try {
      const companyCode = document.getElementById("itmb-company-code").value.trim() || null;
      const servicePassword = document.getElementById("itmb-service-password").value.trim() || null;
      const payload = { CompanyCode: companyCode, ServicePassword: servicePassword };
      const data = await request(
        "/waybill/baseinfo/refresh",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
        true
      );
      showOutput("بروزرسانی BaseInfo", data);
      notify("کش BaseInfo بروزرسانی شد");
    } catch (err) {
      showOutput("خطا در بروزرسانی BaseInfo", normalizeError(err), true);
    } finally {
      setLoading(button, false);
    }
  });

  document.getElementById("itmb-ws-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = event.submitter;
    setLoading(submitButton, true);
    try {
      const rawPayload = document.getElementById("itmb-ws-payload").value.trim();
      if (!rawPayload) {
        throw new Error("Payload JSON را وارد کنید.");
      }
      const parsedPayload = JSON.parse(rawPayload);
      const companyCode = document.getElementById("itmb-company-code").value.trim();
      const servicePassword = document.getElementById("itmb-service-password").value.trim();
      if (companyCode) parsedPayload.CompanyCode = companyCode;
      if (servicePassword) parsedPayload.ServicePassword = servicePassword;

      const data = await request(
        "/waybill/ws01-insert-bol",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(parsedPayload) },
        true
      );
      showOutput("نتیجه WS01_InsertBOL", data);
      notify("درخواست WS01 با موفقیت ارسال شد");
    } catch (err) {
      if (err instanceof Error) {
        showOutput("خطا در WS01_InsertBOL", { detail: err.message }, true);
      } else {
        showOutput("خطا در WS01_InsertBOL", normalizeError(err), true);
      }
    } finally {
      setLoading(submitButton, false);
    }
  });

  const captchaSampleButton = document.getElementById("btn-captcha-fill-sample");
  const captchaDiagnoseForm = document.getElementById("captcha-diagnose-form");
  const captchaMonitorRefreshButton = document.getElementById("btn-captcha-monitor-refresh");
  const captchaMonitorToggleButton = document.getElementById("btn-captcha-monitor-toggle");

  if (captchaSampleButton) {
    captchaSampleButton.addEventListener("click", () => {
      document.getElementById("captcha-diagnose-input").value = "حاصل (3 + 5) * 2";
      notify("نمونه کپچا وارد شد");
    });
  }

  if (captchaDiagnoseForm) {
    captchaDiagnoseForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = event.submitter;
      setLoading(submitButton, true);
      try {
        const text = document.getElementById("captcha-diagnose-input").value.trim();
        if (!text) {
          throw new Error("ابتدا متن کپچا را وارد کنید.");
        }

        const minConfidenceRaw = document.getElementById("captcha-min-confidence").value.trim();
        const minConfidence = minConfidenceRaw === "" ? null : Number(minConfidenceRaw);
        if (minConfidence !== null && Number.isNaN(minConfidence)) {
          throw new Error("مقدار confidence باید عدد باشد.");
        }

        const payload = { text, min_confidence: minConfidence };
        const data = await request(
          "/captcha/diagnose",
          { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
        );

        showOutput("نتیجه تحلیل کپچا", data, !data.accepted);
        document.getElementById("captcha-solved-value").textContent = data.solved_value || "-";
        document.getElementById("captcha-confidence").textContent = data.confidence ?? "-";
        document.getElementById("captcha-status").textContent = data.status || "-";
        notify(data.accepted ? "کپچا با confidence مناسب حل شد" : "کپچا reject شد (confidence پایین)");
      } catch (err) {
        if (err instanceof Error) {
          showOutput("خطا در تحلیل کپچا", { detail: err.message }, true);
        } else {
          showOutput("خطا در تحلیل کپچا", normalizeError(err), true);
        }
      } finally {
        setLoading(submitButton, false);
      }
    });
  }

  if (captchaMonitorRefreshButton) {
    captchaMonitorRefreshButton.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      await refreshCaptchaMonitor(button);
    });
  }

  if (captchaMonitorToggleButton) {
    captchaMonitorToggleButton.addEventListener("click", () => {
      captchaMonitorAuto = !captchaMonitorAuto;
      applyCaptchaMonitorAutoState();
      startCaptchaMonitorPolling();
      notify(captchaMonitorAuto ? "پایش خودکار کپچا فعال شد" : "پایش خودکار کپچا غیرفعال شد");
    });
  }
}

setupTabs();
setupSidebarControls();
setupTheme();
setupShortcuts();
setupHeroChips();
loadAuthState();
bindEvents();
mirrorCoordinateInputs();
setupStatusRefreshLifecycle();
refreshStatus({ force: true });
if (document.getElementById("btn-captcha-monitor-toggle")) {
  applyCaptchaMonitorAutoState();
  refreshCaptchaMonitor();
  startCaptchaMonitorPolling();
}
document.getElementById("itmb-ws-payload").value = JSON.stringify(buildSampleITMBPayload(), null, 2);

// ==========================================
// Manual Waybill Entry
// ==========================================
function setupManualEntry() {
  const validateBtn = document.getElementById("btn-validate-manual");
  const submitBtn = document.getElementById("btn-submit-manual-waybill");
  const sampleBtn = document.getElementById("btn-fill-sample-manual");
  const validationResult = document.getElementById("manual-validation-result");
  const submitResult = document.getElementById("manual-submit-result");

  if (!validateBtn || !submitBtn) return;

  function buildManualWaybillPayload() {
    const getValue = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : "";
    };

    const originLat = parseFloat(getValue("manual-origin-lat")) || null;
    const originLng = parseFloat(getValue("manual-origin-lng")) || null;
    const destLat = parseFloat(getValue("manual-destination-lat")) || null;
    const destLng = parseFloat(getValue("manual-destination-lng")) || null;

    const payload = {
      operation_mode: document.getElementById("manual-operation-mode")?.value || "safe",
      sender: {
        name: getValue("manual-sender-name"),
        national_code: getValue("manual-sender-national-code"),
        phone: getValue("manual-sender-phone"),
        address: getValue("manual-sender-address"),
      },
      receiver: {
        name: getValue("manual-receiver-name"),
        national_code: getValue("manual-receiver-national-code") || null,
        phone: getValue("manual-receiver-phone"),
        address: getValue("manual-receiver-address"),
      },
      origin: {
        province: getValue("manual-origin-province"),
        city: getValue("manual-origin-city"),
        district: getValue("manual-origin-district") || null,
        address: getValue("manual-origin-address"),
        coordinates: (originLat && originLng) ? { lat: originLat, lng: originLng } : null,
      },
      destination: {
        province: getValue("manual-destination-province"),
        city: getValue("manual-destination-city"),
        district: getValue("manual-destination-district") || null,
        address: getValue("manual-destination-address"),
        coordinates: (destLat && destLng) ? { lat: destLat, lng: destLng } : null,
      },
      cargo: {
        type: getValue("manual-cargo-type") || null,
        weight: parseFloat(getValue("manual-cargo-weight")) || 1,
        count: parseInt(getValue("manual-cargo-count")) || 1,
        description: getValue("manual-cargo-description") || null,
      },
      vehicle: {
        driver_national_code: getValue("manual-vehicle-driver-national-code") || null,
        driver_phone: getValue("manual-vehicle-driver-phone") || null,
        plate: getValue("manual-vehicle-plate") || null,
        type: getValue("manual-vehicle-type") || null,
      },
      financial: {
        cost: getValue("manual-financial-cost") ? parseFloat(getValue("manual-financial-cost")) : null,
        payment_method: getValue("manual-financial-payment-method") || null,
      },
    };

    const username = getValue("manual-utcms-username");
    const password = getValue("manual-utcms-password");
    if (username && password) {
      payload.utcms_auth = {
        username,
        password,
        login_url: "https://barname.utcms.ir/Barname/Account/Login",
      };
    }

    return payload;
  }

  validateBtn.addEventListener("click", async () => {
    const payload = buildManualWaybillPayload();
    
    setLoading(validateBtn, true);
    setMutedMessage(validationResult, "در حال اعتبارسنجی...");

    try {
      const data = await request("/waybill/validate-manual-entry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const isValid = Boolean(data.valid);
      const wrapper = document.createElement("div");
      wrapper.className = `validation-summary ${isValid ? "valid" : "invalid"}`;

      const heading = document.createElement("h4");
      heading.textContent = isValid ? "✓ اعتبارسنجی موفق" : "✗ خطاهای اعتبارسنجی";
      wrapper.appendChild(heading);

      const stats = document.createElement("div");
      stats.className = "validation-stats";
      const statsLine = document.createElement("div");
      statsLine.append("تکمیل فیلدها: ");
      const statsStrong = document.createElement("strong");
      statsStrong.textContent = `${data.completed_fields}/${data.field_count}`;
      statsLine.append(statsStrong, ` (${data.completion_percent}%)`);
      stats.appendChild(statsLine);
      wrapper.appendChild(stats);

      if (Array.isArray(data.errors) && data.errors.length > 0) {
        const errorsWrap = document.createElement("div");
        errorsWrap.className = "validation-errors";
        const errorsTitle = document.createElement("h5");
        errorsTitle.textContent = "خطاها:";
        const errorsList = document.createElement("ul");
        data.errors.forEach((err) => {
          const li = document.createElement("li");
          li.className = "error";
          li.textContent = String(err);
          errorsList.appendChild(li);
        });
        errorsWrap.append(errorsTitle, errorsList);
        wrapper.appendChild(errorsWrap);
      }

      if (Array.isArray(data.warnings) && data.warnings.length > 0) {
        const warningsWrap = document.createElement("div");
        warningsWrap.className = "validation-warnings";
        const warningsTitle = document.createElement("h5");
        warningsTitle.textContent = "هشدارها:";
        const warningsList = document.createElement("ul");
        data.warnings.forEach((warn) => {
          const li = document.createElement("li");
          li.className = "warning";
          li.textContent = String(warn);
          warningsList.appendChild(li);
        });
        warningsWrap.append(warningsTitle, warningsList);
        wrapper.appendChild(warningsWrap);
      }

      validationResult.replaceChildren(wrapper);
      
      if (isValid) {
        notify("اعتبارسنجی موفق ✓");
      } else {
        notify("اعتبارسنجی ناموفق ✗");
      }
    } catch (err) {
      renderResultCard(validationResult, {
        wrapperClass: "validation-summary invalid",
        title: "خطا در اعتبارسنجی",
        message: err?.message || JSON.stringify(err),
      });
      notify("خطا در اعتبارسنجی");
    } finally {
      setLoading(validateBtn, false);
    }
  });

  submitBtn.addEventListener("click", async () => {
    const payload = buildManualWaybillPayload();
    
    setLoading(submitBtn, true);
    setMutedMessage(submitResult, "در حال ارسال...");

    try {
      const data = await request("/waybill/submit-manual-waybill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const wrapper = document.createElement("div");
      wrapper.className = "submit-summary success";
      const heading = document.createElement("h4");
      heading.textContent = `✓ ${data.message || "بارنامه با موفقیت ثبت شد"}`;
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(data.result, null, 2);
      wrapper.append(heading, pre);
      submitResult.replaceChildren(wrapper);
      notify("بارنامه با موفقیت ارسال شد ✓");
    } catch (err) {
      const errorData = err.data?.detail || err.message || JSON.stringify(err);
      renderResultCard(submitResult, {
        wrapperClass: "submit-summary error",
        title: "✗ خطا در ارسال",
        message: typeof errorData === "string" ? errorData : JSON.stringify(errorData),
      });
      notify("خطا در ارسال بارنامه");
    } finally {
      setLoading(submitBtn, false);
    }
  });

  sampleBtn?.addEventListener("click", () => {
    document.getElementById("manual-sender-name").value = "علی احمدی";
    document.getElementById("manual-sender-national-code").value = "1234567890";
    document.getElementById("manual-sender-phone").value = "09121234567";
    document.getElementById("manual-sender-address").value = "تهران، خیابان ولیعصر";
    
    document.getElementById("manual-receiver-name").value = "مرضا رضایی";
    document.getElementById("manual-receiver-national-code").value = "0987654321";
    document.getElementById("manual-receiver-phone").value = "09139876543";
    document.getElementById("manual-receiver-address").value = "اصفهان، خیابان چهارباغ";
    
    document.getElementById("manual-origin-province").value = "تهران";
    document.getElementById("manual-origin-city").value = "تهران";
    document.getElementById("manual-origin-address").value = "تهران، میدان آزادی";
    document.getElementById("manual-origin-lat").value = "35.6892";
    document.getElementById("manual-origin-lng").value = "51.3890";
    
    document.getElementById("manual-destination-province").value = "اصفهان";
    document.getElementById("manual-destination-city").value = "اصفهان";
    document.getElementById("manual-destination-address").value = "اصفهان، خیابان آمادگاه";
    document.getElementById("manual-destination-lat").value = "32.6546";
    document.getElementById("manual-destination-lng").value = "51.6780";
    
    document.getElementById("manual-cargo-type").value = "مواد غذایی";
    document.getElementById("manual-cargo-weight").value = "10.5";
    document.getElementById("manual-cargo-count").value = "5";
    
    notify("داده‌های نمونه وارد شد");
  });
}

// ==========================================
// Excel Upload
// ==========================================
function setupExcelUpload() {
  const fileInput = document.getElementById("excel-file-input");
  const selectBtn = document.getElementById("btn-select-excel");
  const parseBtn = document.getElementById("btn-parse-excel");
  const submitBtn = document.getElementById("btn-submit-excel-waybills");
  const queueBtn = document.getElementById("btn-queue-excel-waybills");
  const templateBtn = document.getElementById("btn-download-template");
  const fileInfo = document.getElementById("excel-file-info");
  const parseResult = document.getElementById("excel-parse-result");
  const previewDiv = document.getElementById("excel-waybills-preview");
  const clearBtn = document.getElementById("btn-clear-excel-results");

  if (!fileInput || !selectBtn) return;

  let selectedFile = null;

  selectBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    selectedFile = file;
    fileInfo.style.display = "block";
    fileInfo.querySelector(".file-name").textContent = file.name;
    fileInfo.querySelector(".file-size").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
    
    parseBtn.disabled = false;
    submitBtn.disabled = false;
    queueBtn.disabled = false;
    
    notify("فایل اکسل انتخاب شد");
  });

  // Drag and drop
  const uploadArea = document.querySelector(".excel-upload-area");
  if (uploadArea) {
    uploadArea.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadArea.classList.add("dragover");
    });

    uploadArea.addEventListener("dragleave", () => {
      uploadArea.classList.remove("dragover");
    });

    uploadArea.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadArea.classList.remove("dragover");
      
      const file = e.dataTransfer.files[0];
      if (file && (file.name.endsWith(".xlsx") || file.name.endsWith(".xls"))) {
        fileInput.files = e.dataTransfer.files;
        fileInput.dispatchEvent(new Event("change"));
      } else {
        notify("لطفاً فایل اکسل معتبر انتخاب کنید");
      }
    });
  }

  parseBtn?.addEventListener("click", async () => {
    if (!selectedFile) {
      notify("لطفاً ابتدا فایل اکسل را انتخاب کنید");
      return;
    }

    setLoading(parseBtn, true);
    setMutedMessage(parseResult, "در حال پردازش...");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("operation_mode", document.getElementById("excel-operation-mode")?.value || "safe");

      const response = await fetch("/waybill/parse-excel", {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || "خطا در پردازش فایل");
      }

      const data = await response.json();
      
      const summary = document.createElement("div");
      summary.className = "excel-summary";
      const heading = document.createElement("h4");
      heading.textContent = "✓ فایل با موفقیت پردازش شد";
      const stats = document.createElement("div");
      stats.className = "excel-stats";

      const buildStat = (label, value, valueClass = "") => {
        const row = document.createElement("div");
        row.textContent = `${label}: `;
        const strong = document.createElement("strong");
        if (valueClass) strong.className = valueClass;
        strong.textContent = String(value);
        row.appendChild(strong);
        return row;
      };

      stats.append(
        buildStat("نام فایل", data.file_name),
        buildStat("تعداد ردیف", data.total_rows),
        buildStat("بارنامه‌های معتبر", data.valid_waybills, "success"),
        buildStat("خطاها", data.errors, data.errors > 0 ? "error" : ""),
      );

      summary.append(heading, stats);
      parseResult.replaceChildren(summary);

      // Show preview
      if (data.waybills_preview && data.waybills_preview.length > 0) {
        const table = document.createElement("table");
        table.className = "waybills-table";
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        ["ردیف", "فرستنده", "گیرنده", "مبدأ", "مقصد", "وزن", "وضعیت"].forEach((text) => {
          const th = document.createElement("th");
          th.textContent = text;
          headRow.appendChild(th);
        });
        thead.appendChild(headRow);

        const tbody = document.createElement("tbody");
        data.waybills_preview.forEach((item) => {
          const isValid = item.validation?.valid;
          const tr = document.createElement("tr");
          [item.row, item.sender, item.receiver, item.origin, item.destination, item.cargo_weight].forEach((value) => {
            const td = document.createElement("td");
            td.textContent = String(value ?? "");
            tr.appendChild(td);
          });
          const statusTd = document.createElement("td");
          statusTd.className = isValid ? "success" : "error";
          statusTd.textContent = isValid ? "✓" : "✗";
          tr.appendChild(statusTd);
          tbody.appendChild(tr);
        });

        table.append(thead, tbody);
        previewDiv.replaceChildren(table);
      }

      notify("فایل اکسل با موفقیت پردازش شد");
    } catch (err) {
      renderResultCard(parseResult, {
        wrapperClass: "excel-summary error",
        title: "✗ خطا در پردازش",
        message: err?.message || JSON.stringify(err),
      });
      notify("خطا در پردازش فایل اکسل");
    } finally {
      setLoading(parseBtn, false);
    }
  });

  submitBtn?.addEventListener("click", async () => {
    if (!selectedFile) {
      notify("لطفاً ابتدا فایل اکسل را انتخاب کنید");
      return;
    }

    setLoading(submitBtn, true);
    setMutedMessage(parseResult, "در حال پردازش و ارسال...");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("operation_mode", document.getElementById("excel-operation-mode")?.value || "safe");
      formData.append("skip_invalid", document.getElementById("excel-skip-invalid")?.checked !== false);

      const response = await fetch("/waybill/submit-excel-waybills", {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || "خطا در ارسال");
      }

      const data = await response.json();
      
      const summary = document.createElement("div");
      summary.className = "excel-summary success";
      const heading = document.createElement("h4");
      heading.textContent = `✓ ${data.message}`;
      const stats = document.createElement("div");
      stats.className = "excel-stats";

      const totalRow = document.createElement("div");
      totalRow.textContent = "کل پردازش: ";
      const totalStrong = document.createElement("strong");
      totalStrong.textContent = String(data.total_processed);
      totalRow.appendChild(totalStrong);

      const successRow = document.createElement("div");
      successRow.textContent = "موفق: ";
      const successStrong = document.createElement("strong");
      successStrong.className = "success";
      successStrong.textContent = String(data.success_count);
      successRow.appendChild(successStrong);

      const errorRow = document.createElement("div");
      errorRow.textContent = "ناموفق: ";
      const errorStrong = document.createElement("strong");
      if (data.error_count > 0) errorStrong.className = "error";
      errorStrong.textContent = String(data.error_count);
      errorRow.appendChild(errorStrong);

      stats.append(totalRow, successRow, errorRow);
      summary.append(heading, stats);
      parseResult.replaceChildren(summary);
      notify("پردازش و ارسال بارنامه‌ها انجام شد");
    } catch (err) {
      renderResultCard(parseResult, {
        wrapperClass: "excel-summary error",
        title: "✗ خطا در ارسال",
        message: err?.message || JSON.stringify(err),
      });
      notify("خطا در ارسال بارنامه‌ها");
    } finally {
      setLoading(submitBtn, false);
    }
  });

  queueBtn?.addEventListener("click", async () => {
    if (!selectedFile) {
      notify("لطفاً ابتدا فایل اکسل را انتخاب کنید");
      return;
    }

    setLoading(queueBtn, true);
    setMutedMessage(parseResult, "در حال افزودن به صف...");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("operation_mode", document.getElementById("excel-operation-mode")?.value || "safe");
      formData.append("skip_invalid", document.getElementById("excel-skip-invalid")?.checked !== false);

      const response = await fetch("/waybill/queue-excel-waybills", {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.message || "خطا در افزودن به صف");
      }

      const data = await response.json();
      
      const summary = document.createElement("div");
      summary.className = "excel-summary success";
      const heading = document.createElement("h4");
      heading.textContent = `✓ ${data.message}`;
      const stats = document.createElement("div");
      stats.className = "excel-stats";

      const parsedRow = document.createElement("div");
      parsedRow.textContent = "کل parsed: ";
      const parsedStrong = document.createElement("strong");
      parsedStrong.textContent = String(data.total_parsed);
      parsedRow.appendChild(parsedStrong);

      const queuedRow = document.createElement("div");
      queuedRow.textContent = "افزوده شده به صف: ";
      const queuedStrong = document.createElement("strong");
      queuedStrong.className = "success";
      queuedStrong.textContent = String(data.queued_count);
      queuedRow.appendChild(queuedStrong);

      const errorRow = document.createElement("div");
      errorRow.textContent = "خطاها: ";
      const errorStrong = document.createElement("strong");
      if (data.error_count > 0) errorStrong.className = "error";
      errorStrong.textContent = String(data.error_count);
      errorRow.appendChild(errorStrong);

      stats.append(parsedRow, queuedRow, errorRow);
      summary.append(heading, stats);
      parseResult.replaceChildren(summary);
      notify("بارنامه‌ها به صف اضافه شدند");
    } catch (err) {
      renderResultCard(parseResult, {
        wrapperClass: "excel-summary error",
        title: "✗ خطا",
        message: err?.message || JSON.stringify(err),
      });
      notify("خطا در افزودن به صف");
    } finally {
      setLoading(queueBtn, false);
    }
  });

  templateBtn?.addEventListener("click", async () => {
    try {
      const response = await fetch("/waybill/excel-template");
      if (!response.ok) throw new Error("خطا در دانلود قالب");
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "waybill_template.xlsx";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      notify("قالب اکسل دانلود شد");
    } catch (err) {
      notify("خطا در دانلود قالب");
    }
  });

  clearBtn?.addEventListener("click", () => {
    setMutedMessage(parseResult, "هنوز فایلی پرداز نشده است");
    setMutedMessage(previewDiv, "پس از پردازش فایل اکسل، پیش‌نمایش اینجا نمایش داده می‌شود");
    fileInfo.style.display = "none";
    fileInput.value = "";
    selectedFile = null;
    parseBtn.disabled = true;
    submitBtn.disabled = true;
    queueBtn.disabled = true;
  });
}

// Initialize new features
setupManualEntry();
setupExcelUpload();


// ==========================================
// AUTOMATED SCHEDULES LOGIC
// ==========================================

async function loadDriversForSchedule() {
  const select = document.getElementById("schedule-driver-select");
  if (!select) return;
  try {
    const data = await request("/api/v1/drivers");
    if (Array.isArray(data)) {
      select.innerHTML = '<option value="">انتخاب راننده...</option>';
      data.forEach(d => {
         const isReady = d.status === 'ready' || d.status === 'active';
         const statusIcon = isReady ? '✅' : '❌';
         select.innerHTML += `<option value="${d.id}">${statusIcon} ${d.full_name} (${d.driver_national_code})</option>`;
      });
    }
  } catch (error) {
    select.innerHTML = '<option value="">خطا در بارگذاری رانندگان</option>';
  }
}

async function loadSchedules() {
  const list = document.getElementById("schedules-list");
  if (!list) return;
  try {
    list.innerHTML = '<div class="text-center opacity-50 py-4 text-sm">در حال بارگذاری...</div>';
    const data = await request("/api/v1/driver-schedules");
    if (!Array.isArray(data) || data.length === 0) {
      list.innerHTML = '<div class="text-center opacity-50 py-4 text-sm">زمان‌بندی فعالی یافت نشد.</div>';
      return;
    }

    list.innerHTML = '';
    data.forEach(s => {
      const freq = s.frequency === 'daily' ? 'روزانه' : (s.frequency === 'weekly' ? 'هفتگی' : s.frequency);
      list.innerHTML += `
        <div class="bg-slate-800 border border-white/10 rounded-xl p-4 flex justify-between items-start gap-4">
          <div>
             <h4 class="font-bold text-sm text-blue-400 mb-1">${s.title}</h4>
             <div class="text-xs opacity-80 grid grid-cols-2 gap-x-4 gap-y-1">
                <div>تناوب: <span class="font-bold">${freq}</span></div>
                <div>ساعت: <span class="font-bold">${s.run_times ? s.run_times.join(', ') : s.run_time}</span></div>
                ${s.start_date ? `<div>شروع: <span>${s.start_date}</span></div>` : ''}
                ${s.end_date ? `<div>پایان: <span>${s.end_date}</span></div>` : ''}
             </div>
             <div class="text-xs mt-2 opacity-60">تعداد دفعات اجرا: ${s.last_run_at ? new Date(s.last_run_at).toLocaleString('fa-IR') : 'هنوز اجرا نشده'}</div>
          </div>
          <div>
             <button onclick="deleteSchedule(${s.id})" class="text-red-400 hover:text-red-300 p-2 bg-red-500/10 hover:bg-red-500/20 rounded-lg transition-colors" title="حذف" aria-label="حذف زمان‌بندی">🗑️</button>
          </div>
        </div>
      `;
    });
  } catch (error) {
    list.innerHTML = '<div class="text-center text-red-400 py-4 text-sm">خطا در بارگذاری زمان‌بندی‌ها</div>';
    console.error("Load schedules error:", error);
  }
}

async function handleScheduleSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);
  const submitBtn = form.querySelector('button[type="submit"]');

  try {
    let payload_template = {};
    const rawPayload = formData.get("payload_template").trim();
    if (rawPayload) {
      try {
        payload_template = JSON.parse(rawPayload);
      } catch (err) {
         notify("قالب JSON نامعتبر است");
         return;
      }
    }

    const reqBody = {
      driver_id: parseInt(formData.get("driver_id")),
      title: formData.get("title"),
      frequency: formData.get("frequency"),
      run_time: formData.get("run_time"),
      run_times: [formData.get("run_time")],
      start_date: formData.get("start_date") || null,
      end_date: formData.get("end_date") || null,
      payload_template: payload_template,
      is_active: true
    };

    submitBtn.disabled = true;
    submitBtn.innerHTML = 'در حال ذخیره...';

    await request("/api/v1/driver-schedules", {
      method: "POST",
      body: JSON.stringify(reqBody)
    });

    notify("زمان‌بندی با موفقیت ایجاد شد");
    form.reset();
    await loadSchedules();
  } catch (error) {
    notify("خطا در ذخیره زمان‌بندی");
    showOutput("Schedule Error", normalizeError(error), true);
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'ذخیره زمان‌بندی';
  }
}

async function deleteSchedule(id) {
  if (!confirm("آیا از حذف این زمان‌بندی اطمینان دارید؟")) return;

  try {
    await request(`/api/v1/driver-schedules/${id}`, { method: "DELETE" });
    notify("زمان‌بندی حذف شد");
    await loadSchedules();
  } catch (error) {
    notify("خطا در حذف زمان‌بندی");
  }
}

// Attach Schedule initialization
document.addEventListener("DOMContentLoaded", () => {
   const schedForm = document.getElementById("schedule-form");
   if (schedForm) {
      schedForm.addEventListener("submit", handleScheduleSubmit);
   }
});
