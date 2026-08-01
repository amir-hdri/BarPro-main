"use client";

import { useEffect, useState, useRef, useCallback } from "react";

export interface WebSocketMessage {
  data: any;
  type: string;
  timestamp: number;
}

export interface WebSocketOptions {
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

const WS_RECONNECT_INTERVAL_MS = 5000;
const WS_MAX_RECONNECT_ATTEMPTS = 10;

export function useWebSocket(
  url: string | (() => string) | null,
  options: WebSocketOptions = {}
): {
  ws: WebSocket | null;
  lastMessage: MessageEvent | null;
  readyState: number;
  sendMessage: (message: any) => void;
  reconnect: () => void;
} {
  const {
    reconnectInterval = WS_RECONNECT_INTERVAL_MS,
    maxReconnectAttempts = WS_MAX_RECONNECT_ATTEMPTS,
    onOpen,
    onClose,
    onError,
  } = options;

  const [ws, setWs] = useState<WebSocket | null>(null);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
  const [readyState, setReadyState] = useState<number>(WebSocket.CLOSED);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const messageQueueRef = useRef<any[]>([]);
  const reconnectCountRef = useRef(0);
  const activeRef = useRef(false);

  const resolveUrl = useCallback((): string | null => {
    if (typeof url === "function") return url();
    return url;
  }, [url]);

  const doReconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (!activeRef.current) return;
    if (reconnectCountRef.current >= maxReconnectAttempts) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("WebSocket max reconnect attempts reached");
      }
      return;
    }
    reconnectCountRef.current += 1;
    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectTimeoutRef.current = null;
      if (activeRef.current) {
        connectRef.current();
      }
    }, reconnectInterval);
  }, [reconnectInterval, maxReconnectAttempts]);

  const connectRef = useRef(() => {});

  const connect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    activeRef.current = true;

    // Close existing socket cleanly
    if (ws) {
      try { ws.close(); } catch (_) { /* ignore */ }
      setWs(null);
    }
    setReadyState(WebSocket.CONNECTING);

    const resolved = resolveUrl();
    if (!resolved) {
      setReadyState(WebSocket.CLOSED);
      doReconnect();
      return;
    }

    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(resolved);
      setWs(socket);

      socket.onopen = () => {
        setReadyState(WebSocket.OPEN);
        reconnectCountRef.current = 0;

        // Flush queued messages
        while (messageQueueRef.current.length > 0 && socket?.readyState === WebSocket.OPEN) {
          const message = messageQueueRef.current.shift();
          if (message !== undefined) {
            try { socket.send(JSON.stringify(message)); } catch (_) { messageQueueRef.current.unshift(message); break; }
          }
        }

        onOpen?.();
      };

      socket.onmessage = (event) => {
        setLastMessage(event);
      };

      socket.onclose = () => {
        setWs(null);
        setReadyState(WebSocket.CLOSED);
        onClose?.();
        if (activeRef.current) {
          doReconnect();
        }
      };

      socket.onerror = (error) => {
        setReadyState(WebSocket.CLOSING);
        onError?.(error);
      };
    } catch (error) {
      if (process.env.NODE_ENV !== "production") {
        console.error("WebSocket connection error:", error);
      }
      setWs(null);
      setReadyState(WebSocket.CLOSED);
      doReconnect();
    }
  }, [resolveUrl, doReconnect, onOpen, onClose, onError, ws]);

  connectRef.current = connect;

  const sendMessage = useCallback((message: any) => {
    if (ws && readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify(message));
      } catch (error) {
        if (process.env.NODE_ENV !== "production") {
          console.error("Failed to send WebSocket message:", error);
        }
        messageQueueRef.current.push(message);
      }
    } else {
      messageQueueRef.current.push(message);
    }
  }, [ws, readyState]);

  const reconnect = useCallback(() => {
    reconnectCountRef.current = 0;
    connect();
  }, [connect]);

  useEffect(() => {
    activeRef.current = true;
    reconnectCountRef.current = 0;
    connect();
    return () => {
      activeRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (ws) {
        try { ws.close(); } catch (_) { /* ignore */ }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  return {
    ws,
    lastMessage,
    readyState,
    sendMessage,
    reconnect,
  };
}
