export const AUTH_TOKEN_KEY = 'utcms_auth_token';
export const AUTH_CLIENT_KEY = 'utcms_auth_client';
export const AUTH_SESSION_EVENT = 'utcms:session-change';

export type StoredRole = 'client' | 'master_admin';

export interface StoredClient {
  id: number | null;
  name: string;
  email: string;
  client_code: string;
  role: StoredRole;
}

export function getStoredToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredClient(): StoredClient | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const rawValue = window.localStorage.getItem(AUTH_CLIENT_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as StoredClient;
  } catch {
    return null;
  }
}

export function persistSession(token: string, client: StoredClient): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  window.localStorage.setItem(AUTH_CLIENT_KEY, JSON.stringify(client));
  window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
}

export function clearSession(): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_CLIENT_KEY);
  window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
}
