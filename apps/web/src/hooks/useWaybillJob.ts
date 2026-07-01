import { useEffect, useState, useRef, useCallback } from "react";
import type { WebSocketEvent } from "@/lib/types";

function logError(...args: unknown[]) {
  if (process.env.NODE_ENV !== "production") {
    console.error(...args);
  }
}

// Determine the WebSocket URL based on the current environment and API_URL
function getWebSocketUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
  try {
    // اگر API URL ست شده و localhost نباشد، از آن استفاده کن
    if (apiUrl && !apiUrl.includes("localhost") && !apiUrl.includes("127.0.0.1")) {
      const url = new URL(apiUrl);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      return `${url.origin}/ws/waybill`;
    }
    // در browser: از origin فعلی استفاده می‌کنیم
    if (typeof window !== "undefined") {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      return `${protocol}//${window.location.host}/ws/waybill`;
    }
    return "ws://localhost:8000/ws/waybill";
  } catch {
    return "ws://localhost:8000/ws/waybill";
  }
}

interface UseWaybillJobOptions {
  taskId?: string;
  batchId?: string;
  correlationId?: string;
}

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

const MAX_WS_EVENTS = 100;

export function useWaybillJob(options: UseWaybillJobOptions = {}) {
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const [events, setEvents] = useState<WebSocketEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const { taskId, batchId, correlationId } = options;

  const connect = useCallback(() => {
    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    try {
      setStatus("connecting");

      const wsUrl = new URL(getWebSocketUrl());
      if (taskId) wsUrl.searchParams.append("task_id", taskId);
      if (batchId) wsUrl.searchParams.append("batch_id", batchId);
      if (correlationId) wsUrl.searchParams.append("correlation_id", correlationId);

      const ws = new WebSocket(wsUrl.toString());
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
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
        setStatus("disconnected");
      };

      ws.onerror = (error) => {
        logError("WebSocket error:", error);
        setStatus("error");
      };
    } catch (error) {
      logError("Failed to initialize WebSocket:", error);
      setStatus("error");
    }
  }, [taskId, batchId, correlationId]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
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
