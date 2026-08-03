import { useEffect, useState, useRef, useCallback } from "react";
import { z } from "zod";
import type { WebSocketEvent } from "@/lib/types";
import { buildWebSocketUrl } from "@/lib/ws";

const webSocketEventSchema = z.object({
  type: z.string(),
  job_id: z.string().optional(),
  status: z.string().optional(),
  message: z.string().optional(),
  data: z.record(z.unknown()).optional(),
  timestamp: z.string().optional(),
});

function logError(...args: unknown[]) {
  if (process.env.NODE_ENV !== "production") {
    console.error(...args);
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
  const { taskId, batchId, correlationId } = options;
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
      const wsUrl = buildWebSocketUrl("/ws/waybill", {
        task_id: taskId,
        batch_id: batchId,
        correlation_id: correlationId,
      });

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        attemptRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          const data = webSocketEventSchema.parse(parsed);
          setLastEvent(data);
          setEvents((prev) => {
            const next = [...prev, data];
            return next.length > MAX_WS_EVENTS ? next.slice(-MAX_WS_EVENTS) : next;
          });
        } catch (e) {
          logError("Failed to parse or validate WebSocket message", e);
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
