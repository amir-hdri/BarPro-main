/**
 * Centralized API client with auth token handling.
 */

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  message?: string;
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("utcms_token") || null;
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("utcms_token", token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("utcms_token");
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return { ...h, ...extra };
  }

  async get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    try {
      const url = new URL(path, API_BASE);
      if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
      const res = await fetch(url.toString(), { headers: this.headers() });
      const data = await res.json();
      if (!res.ok) return { error: data?.detail || data?.message || "خطا در ارتباط با سرور" };
      return { data };
    } catch (e: any) {
      return { error: e?.message || "خطا در ارتباط با سرور" };
    }
  }

  async post<T>(path: string, body?: any): Promise<ApiResponse<T>> {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: this.headers(),
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) return { error: data?.detail || data?.message || "خطا در عملیات" };
      return { data };
    } catch (e: any) {
      return { error: e?.message || "خطا در ارتباط با سرور" };
    }
  }

  async put<T>(path: string, body?: any): Promise<ApiResponse<T>> {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "PUT",
        headers: this.headers(),
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) return { error: data?.detail || data?.message || "خطا در عملیات" };
      return { data };
    } catch (e: any) {
      return { error: e?.message || "خطا در ارتباط با سرور" };
    }
  }

  async del<T>(path: string): Promise<ApiResponse<T>> {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "DELETE",
        headers: this.headers(),
      });
      const data = await res.json();
      if (!res.ok) return { error: data?.detail || data?.message || "خطا در عملیات" };
      return { data };
    } catch (e: any) {
      return { error: e?.message || "خطا در ارتباط با سرور" };
    }
  }
}

export const api = new ApiClient();
