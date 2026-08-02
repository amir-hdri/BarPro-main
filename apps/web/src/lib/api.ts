import axios, { AxiosInstance } from 'axios';

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000')
).replace(/\/+$/, '').replace(/\/api$/, '');

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

  const directMessage =
    normalizeToString(record.message) ||
    normalizeToString(record.detail) ||
    normalizeToString(record.msg);
  if (directMessage) return directMessage;

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

// ─── Backwards-compatible default export ──────────────────────────────────────

export const api = { get, post, put, patch, delete: del };
