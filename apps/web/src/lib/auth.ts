import { post } from './api';

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
  return null;
}

export function getStoredClient(): StoredClient | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(AUTH_CLIENT_KEY);
    if (!rawValue) {
      return null;
    }
    return JSON.parse(rawValue) as StoredClient;
  } catch (e) {
    console.error('Failed to get stored client:', e);
    return null;
  }
}

export function persistSession(token: string, client: StoredClient): void {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    // Token is stored in httpOnly cookie, not in localStorage to prevent XSS
    window.localStorage.setItem(AUTH_CLIENT_KEY, JSON.stringify(client));
    window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
  } catch (e) {
    console.error('Failed to persist session:', e);
  }
}

export function clearSession(): void {
  if (typeof window === 'undefined') {
    return;
  }

  // Clear cookie in backend
  post('/api/v1/auth/logout').catch(() => {});

  try {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    window.localStorage.removeItem(AUTH_CLIENT_KEY);
    window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
  } catch (e) {
    console.error('Failed to clear session:', e);
  }
}
