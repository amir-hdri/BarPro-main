import { useEffect, useState, useRef, useCallback } from "react";

// Determine the WebSocket URL based on the current environment and API_URL
function getWebSocketUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const url = new URL(apiUrl);
    // Replace http:// with ws:// and https:// with wss://
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return `${url.origin}/ws/waybill`;
  } catch {
    // Fallback if URL parsing fails
    return "ws://localhost:8000/ws/waybill";
  }
}

interface UseWaybillJobOptions {
  taskId?: string;
  batchId?: string;
  correlationId?: string;
}

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export function useWaybillJob(options: UseWaybillJobOptions = {}) {
  const [status, setStatus] = useState<WebSocketStatus>("disconnected");
  const [lastEvent, setLastEvent] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
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
          setEvents((prev) => [...prev, data]);
        } catch (e) {
          console.error("Failed to parse WebSocket message", e);
        }
      };

      ws.onclose = () => {
        setStatus("disconnected");
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        setStatus("error");
      };
    } catch (error) {
      console.error("Failed to initialize WebSocket:", error);
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
