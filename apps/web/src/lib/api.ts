import axios, { AxiosInstance } from 'axios';

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000')
).replace(/\/+$/, '').replace(/\/api$/, '');

function clearAllAuthTokens() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('utcms_auth_token');
    localStorage.removeItem('utcms_auth_client');
    localStorage.removeItem('utcms_token');
    localStorage.removeItem('access_token');
    localStorage.removeItem('token');
  } catch (e) {
    console.error('Failed to clear auth tokens:', e);
  }
}

// ─── URL helpers ─────────────────────────────────────────────────────────────

function normalizeBaseUrl(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, '');
  return trimmed.endsWith('/api') ? trimmed.slice(0, -4) : trimmed;
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

  // Common patterns
  const directMessage =
    normalizeToString(record.message) ||
    normalizeToString(record.detail) ||
    normalizeToString(record.msg);
  if (directMessage) return directMessage;

  // FastAPI/Pydantic validation errors often appear as:
  // { detail: [ { msg, loc, ... } ] } or { errors: [...] }
  const detail = record.detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return normalizeToString(item);
        const obj = item as Record<string, unknown>;
        return (
          normalizeToString(obj.msg) ||
          normalizeToString(obj.message) ||
          normalizeToString(obj.detail)
        );
      })
      .filter(Boolean) as string[];

    if (parts.length) return parts.join('، ');
  }

  const errors = record.errors;
  if (Array.isArray(errors)) {
    const parts = errors
      .map((item) => {
        if (!item || typeof item !== 'object') return normalizeToString(item);
        const obj = item as Record<string, unknown>;
        return (
          normalizeToString(obj.msg) ||
          normalizeToString(obj.message) ||
          normalizeToString(obj.detail)
        );
      })
      .filter(Boolean) as string[];

    if (parts.length) return parts.join('، ');
  }

  // Some validators return { loc, msg, ... } at top-level
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
  });

  inst.interceptors.request.use((config) => {
    return config;
  });

  inst.interceptors.response.use(
    (res) => res,
    (err) => {
      const status = err?.response?.status;
      // Only clear session on 401 (Unauthorized) — not 403 (Forbidden)
      // 403 means authenticated but lacking permission, redirect without logout
      if (status === 401) {
        clearAllAuthTokens();
        if (typeof window !== 'undefined') {
          try {
            // Prevent redirect loop if already on /auth
            if (!window.location.pathname.startsWith('/auth')) {
              window.location.href = '/auth';
            }
          } catch {
            // ignore
          }
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

// ─── CRUD wrappers ────────────────────────────────────────────────────────────

export async function get<T = unknown>(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>
): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.get<T>(path, { params });
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function post<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.post<T>(path, body);
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function put<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.put<T>(path, body);
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function patch<T = unknown>(path: string, body?: unknown): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.patch<T>(path, body);
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

export async function del<T = unknown>(path: string): Promise<ApiResponse<T>> {
  try {
    const res = await axiosClient.delete<T>(path);
    return { data: res.data, success: true };
  } catch (e: unknown) {
    const axiosError = e as { response?: { data?: unknown } };
    const payload = axiosError?.response?.data ?? e;
    return { error: extractErrorMessage(payload), success: false };
  }
}

// ─── Backwards-compatible default export ──────────────────────────────────────

export const api = { get, post, put, patch, delete: del };
