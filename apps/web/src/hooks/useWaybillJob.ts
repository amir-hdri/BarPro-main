import { useEffect, useState, useRef, useCallback } from "react";
import type { WebSocketEvent } from "@/lib/types";

function logError(...args: unknown[]) {
  if (process.env.NODE_ENV !== "production") {
    console.error(...args);
  }
}

function getWebSocketUrl(): string {
  try {
    if (typeof window !== "undefined") {
      if (window.location.port === "3000") {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.hostname}:8000/ws/waybill`;
      }
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${window.location.host}/ws/waybill`;
    }
    return "ws://127.0.0.1:8000/ws/waybill";
  } catch {
    return "ws://127.0.0.1:8000/ws/waybill";
  }
}

interface UseWaybillJobOptions {
  taskId?: string;
  batchId?: string;
  correlationId?: string;
}

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

const MAX_WS_EVENTS = 100;
const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30_000;
const BACKOFF_FACTOR = 2;
const MAX_RECONNECT_ATTEMPTS = 10;

export function useWaybillJob(options: UseWaybillJobOptions = {}) {
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const activeRef = useRef(true); // false when user explicitly disconnects

  const openSocketRef = useRef<() => void>(() => {});

  const scheduleReconnect = useCallback(() => {
    if (!activeRef.current) return;
    const attempt = attemptRef.current;
    if (attempt >= MAX_RECONNECT_ATTEMPTS) {
      setStatus("error");
      return;
    }

    const baseDelay = Math.min(
      INITIAL_RECONNECT_DELAY_MS * Math.pow(BACKOFF_FACTOR, attempt),
      MAX_RECONNECT_DELAY_MS,
    );
    const jitter = baseDelay * 0.25 * (Math.random() * 2 - 1);
    const delay = Math.round(baseDelay + jitter);

    attemptRef.current = attempt + 1;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      if (activeRef.current) {
        openSocketRef.current();
      }
    }, delay);
  }, []);

  const openSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus("connecting");

    try {
      const url = new URL(getWebSocketUrl());
      if (taskId) url.searchParams.append("task_id", taskId);
      if (batchId) url.searchParams.append("batch_id", batchId);
      if (correlationId) url.searchParams.append("correlation_id", correlationId);

      const ws = new WebSocket(url.toString());
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        attemptRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data: WebSocketEvent = JSON.parse(event.data);
          setLastEvent(data);
          setEvents((prev) => {
            const next = [...prev, data];
            return next.length > MAX_WS_EVENTS ? next.slice(-MAX_WS_EVENTS) : next;
          });
        } catch (e) {
          logError("Failed to parse WebSocket message", e);
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        setStatus("disconnected");
        scheduleReconnect();
      };

      ws.onerror = (error) => {
        logError("WebSocket error:", error);
        setStatus("error");
      };
    } catch (error) {
      logError("Failed to initialize WebSocket:", error);
      setStatus("error");
      scheduleReconnect();
    }
  }, [taskId, batchId, correlationId, scheduleReconnect]);

  useEffect(() => {
    openSocketRef.current = openSocket;
  }, [openSocket]);

  const connect = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    activeRef.current = true;
    attemptRef.current = 0;
    openSocket();
  }, [openSocket]);

  const disconnect = useCallback(() => {
    activeRef.current = false;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    attemptRef.current = 0;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEvent(null);
  }, []);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    status,
    lastEvent,
    events,
    reconnect: connect,
    disconnect,
    clearEvents,
  };
}
