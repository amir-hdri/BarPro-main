import axios, { AxiosInstance } from 'axios';
import type { BatchCreateRequest, WaybillBatch } from './types';

// Cookie name must match the backend (AUTH_COOKIE_NAME in app/core/config.py).
// NEXT_PUBLIC_ prefix is required so Next.js inlines it into the client bundle;
// middleware.ts reads the same variable on the server side.
export const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_AUTH_COOKIE_NAME || 'utcms_auth_token';

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' ? window.location.origin.replace(/:\d+$/, ':8000') : 'http://localhost:8000')
).replace(/\/+$/, '').replace(/\/api$/, '');

// ─── URL helpers ─────────────────────────────────────────────────────────────

function normalizeBaseUrl(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, '');
  // Strip a trailing "/api" or "/api/v1" so callers can pass either the bare
  // origin, a proxy prefix ("/api"), or a full API root without producing
  // doubled segments like "/api/v1/api/v1/...".
  return trimmed.replace(/\/api(\/v1)?$/, '');
}

export function buildUrl(
  baseUrl: string,
  endpoint: string,
  query?: Record<string, string | number | boolean | undefined | null>
): string {
  const normalizedBase = normalizeBaseUrl(baseUrl);
  const cleanEndpoint = endpoint.replace(/^\/+/, '');
  const url = new URL(`${normalizedBase}/${cleanEndpoint}`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }

  return url.toString();
}

// ─── Error extraction ─────────────────────────────────────────────────────────

function normalizeToString(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

export function extractErrorMessage(payload: unknown): string {
  if (typeof payload === 'string') return payload;
  if (!payload || typeof payload !== 'object') return 'خطا در ارتباط با سرور';

  const record = payload as Record<string, unknown>;
  // FastAPI may put our structured contract inside `detail`, while Pydantic
  // validation errors arrive directly as `detail: []`. Normalize both shapes
  // so missing-field warnings remain visible instead of degrading to a generic
  // network error in the UI.
  const detailRecord = record.detail && typeof record.detail === 'object' && !Array.isArray(record.detail)
    ? (record.detail as Record<string, unknown>)
    : null;
  const details = record.details || record.errors || detailRecord?.errors || record.detail;
  if (Array.isArray(details) && details.length > 0) {
    const parts = details
      .map((item) => {
        if (!item || typeof item !== 'object') return normalizeToString(item);
        const obj = item as Record<string, unknown>;
        const loc = Array.isArray(obj.loc) ? obj.loc.filter((x) => x !== 'body').join('.') : '';
        const msg = normalizeToString(obj.msg) || normalizeToString(obj.message) || normalizeToString(obj.detail);
        if (loc && msg) return `${loc}: ${msg}`;
        return msg;
      })
      .filter(Boolean) as string[];

    if (parts.length) {
      const prefix =
        normalizeToString(record.message) ||
        normalizeToString(detailRecord?.message) ||
        'خطای اعتبارسنجی';
      return `${prefix}: ${parts.join('، ')}`;
    }
  }

  const directMessage =
    normalizeToString(record.message) ||
    normalizeToString(detailRecord?.message) ||
    normalizeToString(record.detail) ||
    normalizeToString(record.msg);
  if (directMessage) return directMessage;

  const topMsg = normalizeToString(record.msg) || normalizeToString(record.loc);
  if (topMsg) return topMsg;

  return 'خطا در ارتباط با سرور';
}

// ─── Axios client ─────────────────────────────────────────────────────────────

function createApiClient(): AxiosInstance {
  const inst = axios.create({
    baseURL: API_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    withCredentials: true,
    timeout: 15000,
  });

  inst.interceptors.response.use(
    (res) => res,
    (err) => {
      const status = err?.response?.status;
      if (status === 401 && typeof window !== 'undefined') {
        try {
          window.localStorage.removeItem('utcms_auth_client');
          // Clear the auth cookie
          document.cookie = `${AUTH_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
          if (!window.location.pathname.startsWith('/auth')) {
            window.location.href = '/auth';
          }
        } catch {
          // ignore
        }
      }
      return Promise.reject(err);
    }
  );

  return inst;
}

const axiosClient = createApiClient();

// ─── Public types ─────────────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  data?: T;
  error?: string;
  success?: boolean;
}

export interface RequestOptions {
  signal?: AbortSignal;
}

// ─── CRUD wrappers ────────────────────────────────────────────────────────────

export async function get<T = unknown>(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>,
  options?: RequestOptions
): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.get<T>(path, { params, signal: options?.signal });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function post<T = unknown>(
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.post<T>(path, body, { signal: options?.signal });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function put<T = unknown>(
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.put<T>(path, body, { signal: options?.signal });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function patch<T = unknown>(
  path: string,
  body?: unknown,
  options?: RequestOptions
): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.patch<T>(path, body, { signal: options?.signal });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function del<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.delete<T>(path, { signal: options?.signal });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

// ─── Multi-route batch helpers ───────────────────────────────────────────────

export function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Create a multi-route batch. Sends an `X-Idempotency-Key` header so retrying
 * the same logical request returns the already-created batch instead of duplicating.
 */
export async function createBatch(
  body: BatchCreateRequest,
  idempotencyKey?: string
): Promise<ApiResponse<WaybillBatch>> {
  const key = idempotencyKey || generateIdempotencyKey();
  try {
    const res = await axiosClient.post<WaybillBatch>('/api/v1/batches', body, {
      headers: { 'X-Idempotency-Key': key },
    });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

// ─── Backwards-compatible default export ──────────────────────────────────────

export const api = { get, post, put, patch, delete: del };
