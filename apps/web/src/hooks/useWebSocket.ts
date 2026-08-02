"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface WebSocketMessage {
  data: unknown;
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

export const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
} as const;

const WS_MAX_RECONNECT_ATTEMPTS = 10;
const WS_MAX_QUEUED_MESSAGES = 100;

export function useWebSocket(
  url: string | (() => string) | null,
  options: WebSocketOptions = {}
): {
  ws: WebSocket | null;
  lastMessage: MessageEvent | null;
  readyState: number;
  sendMessage: (message: unknown) => void;
  reconnect: () => void;
} {
  const {
    maxReconnectAttempts = WS_MAX_RECONNECT_ATTEMPTS,
    onOpen,
    onClose,
    onError,
  } = options;

  const [ws, setWs] = useState<WebSocket | null>(null);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);
  const [readyState, setReadyState] = useState<number>(WS_READY_STATE.CLOSED);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageQueueRef = useRef<unknown[]>([]);
  const reconnectCountRef = useRef(0);
  const activeRef = useRef(false);
  const callbacksRef = useRef({ onOpen, onClose, onError });

  useEffect(() => {
    callbacksRef.current = { onOpen, onClose, onError };
  }, [onOpen, onClose, onError]);

  const resolveUrl = useCallback((): string | null => {
    if (typeof url === "function") return url();
    return url;
  }, [url]);

  const enqueueMessage = useCallback((message: unknown) => {
    if (messageQueueRef.current.length >= WS_MAX_QUEUED_MESSAGES) {
      messageQueueRef.current.shift();
    }
    messageQueueRef.current.push(message);
  }, []);

  const connectRef = useRef<() => void>(() => undefined);

  const scheduleReconnect = useCallback(() => {
    if (!activeRef.current || reconnectTimeoutRef.current) return;
    if (reconnectCountRef.current >= maxReconnectAttempts) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("WebSocket max reconnect attempts reached");
      }
      return;
    }

    const attempt = reconnectCountRef.current;
    reconnectCountRef.current += 1;

    const baseDelay = Math.min(
      1000 * Math.pow(2, attempt),
      30000,
    );
    const jitter = baseDelay * 0.25 * (Math.random() * 2 - 1);
    const delay = Math.round(baseDelay + jitter);

    reconnectTimeoutRef.current = setTimeout(() => {
      reconnectTimeoutRef.current = null;
      if (activeRef.current) connectRef.current();
    }, delay);
  }, [maxReconnectAttempts]);

  const connect = useCallback(() => {
    if (!activeRef.current || typeof window === "undefined") return;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    const resolved = resolveUrl();
    if (!resolved) {
      setReadyState(WS_READY_STATE.CLOSED);
      return;
    }

    const currentSocket = socketRef.current;
    if (
      currentSocket &&
      (currentSocket.readyState === WS_READY_STATE.CONNECTING ||
        currentSocket.readyState === WS_READY_STATE.OPEN)
    ) {
      return;
    }

    setReadyState(WS_READY_STATE.CONNECTING);

    try {
      const socket = new window.WebSocket(resolved);
      socketRef.current = socket;
      setWs(socket);

      socket.onopen = () => {
        if (socketRef.current !== socket) return;
        setReadyState(WS_READY_STATE.OPEN);
        reconnectCountRef.current = 0;

        while (
          messageQueueRef.current.length > 0 &&
          socket.readyState === WS_READY_STATE.OPEN
        ) {
          const message = messageQueueRef.current.shift();
          try {
            socket.send(JSON.stringify(message));
          } catch {
            if (message !== undefined) messageQueueRef.current.unshift(message);
            break;
          }
        }

        callbacksRef.current.onOpen?.();
      };

      socket.onmessage = (event) => setLastMessage(event);

      socket.onclose = () => {
        if (socketRef.current !== socket) return;
        socketRef.current = null;
        setWs(null);
        setReadyState(WS_READY_STATE.CLOSED);
        callbacksRef.current.onClose?.();
        scheduleReconnect();
      };

      socket.onerror = (error) => {
        callbacksRef.current.onError?.(error);
      };
    } catch (error) {
      socketRef.current = null;
      setWs(null);
      setReadyState(WS_READY_STATE.CLOSED);
      if (process.env.NODE_ENV !== "production") {
        console.error("WebSocket connection error:", error);
      }
      scheduleReconnect();
    }
  }, [resolveUrl, scheduleReconnect]);

  connectRef.current = connect;

  const sendMessage = useCallback(
    (message: unknown) => {
      const socket = socketRef.current;
      if (socket?.readyState === WS_READY_STATE.OPEN) {
        try {
          socket.send(JSON.stringify(message));
          return;
        } catch (error) {
          if (process.env.NODE_ENV !== "production") {
            console.error("Failed to send WebSocket message:", error);
          }
        }
      }
      enqueueMessage(message);
    },
    [enqueueMessage]
  );

  const reconnect = useCallback(() => {
    reconnectCountRef.current = 0;
    const socket = socketRef.current;
    if (socket) {
      socketRef.current = null;
      socket.close();
    }
    connectRef.current();
  }, []);

  useEffect(() => {
    activeRef.current = true;
    reconnectCountRef.current = 0;
    connectRef.current();

    return () => {
      activeRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) socket.close();
    };
  }, [url]);

  return { ws, lastMessage, readyState, sendMessage, reconnect };
}
