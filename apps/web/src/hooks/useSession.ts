'use client';

import { useSyncExternalStore } from 'react';

import {
  AUTH_CLIENT_KEY,
  AUTH_SESSION_EVENT,
  AUTH_TOKEN_KEY,
  clearSession,
  type StoredClient,
} from '@/lib/auth';

interface SessionSnapshot {
  client: StoredClient | null;
  token: string | null;
}

let cachedClientRaw: string | null = null;
let cachedClientValue: StoredClient | null = null;
let cachedTokenValue: string | null = null;
let cachedSnapshot: SessionSnapshot = { client: null, token: null };

function readClientFromStorage(): StoredClient | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const rawValue = window.localStorage.getItem(AUTH_CLIENT_KEY);
  if (rawValue === cachedClientRaw) {
    return cachedClientValue;
  }

  cachedClientRaw = rawValue;
  if (!rawValue) {
    cachedClientValue = null;
    return cachedClientValue;
  }

  try {
    cachedClientValue = JSON.parse(rawValue) as StoredClient;
  } catch {
    cachedClientValue = null;
  }

  return cachedClientValue;
}

const SERVER_SNAPSHOT: SessionSnapshot = { client: null, token: null };

function getSnapshot(): SessionSnapshot {
  if (typeof window === 'undefined') {
    return SERVER_SNAPSHOT;
  }

  const client = readClientFromStorage();
  const token = window.localStorage.getItem(AUTH_TOKEN_KEY);

  // IMPORTANT:
  // During first hydration, storage reads can be temporarily inconsistent.
  // Never call clearSession() inside getSnapshot; instead, return a stable
  // "not ready/unauthenticated" snapshot and let the UI recover naturally.
  //
  // This prevents logout/redirect loops on refresh.
  if (client === cachedSnapshot.client && token === cachedTokenValue) {
    return cachedSnapshot;
  }

  cachedTokenValue = token;
  cachedSnapshot = { client, token };
  return cachedSnapshot;
}

function getServerSnapshot(): SessionSnapshot {
  return SERVER_SNAPSHOT;
}

function subscribe(callback: () => void) {
  if (typeof window === 'undefined') {
    return () => {};
  }

  const handler = () => callback();
  window.addEventListener('storage', handler);
  window.addEventListener(AUTH_SESSION_EVENT, handler);

  return () => {
    window.removeEventListener('storage', handler);
    window.removeEventListener(AUTH_SESSION_EVENT, handler);
  };
}

export function useSession() {
  const session = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const role = session.client?.role ?? null;

  return {
    client: session.client,
    isAuthenticated: Boolean(session.token),
    isAdmin: role === 'master_admin',
    isClient: role === 'client',
    isReady: typeof window !== 'undefined',
    logout: clearSession,
    role,
    token: session.token,
  };
}
