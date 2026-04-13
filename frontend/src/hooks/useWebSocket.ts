import { useCallback, useEffect, useRef, useState } from "react";
import { WSConnectionState } from "../types";

interface UseWebSocketOptions {
  url: string;
  onMessage: (msg: { type: string; data: unknown }) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export function useWebSocket({
  url,
  onMessage,
  onConnect,
  onDisconnect,
}: UseWebSocketOptions) {
  const [state, setState] = useState<WSConnectionState>("disconnected");

  // Keep callbacks in refs so they never cause reconnects when they change
  const onMessageRef = useRef(onMessage);
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);
  useEffect(() => { onConnectRef.current = onConnect; }, [onConnect]);
  useEffect(() => { onDisconnectRef.current = onDisconnect; }, [onDisconnect]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Incremented on each intentional cleanup so stale onclose handlers ignore themselves
  const sessionRef = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const session = ++sessionRef.current;
    setState("connecting");

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (sessionRef.current !== session) return;
      setState("connected");
      onConnectRef.current?.();
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string);
        onMessageRef.current(msg);
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (sessionRef.current !== session) return; // stale — ignore
      setState("disconnected");
      onDisconnectRef.current?.();
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      setState("error");
      ws.close();
    };
  }, [url]); // url is the only real dep

  useEffect(() => {
    connect();
    return () => {
      // Invalidate current session so its onclose won't reconnect
      sessionRef.current++;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const reconnect = useCallback(() => {
    sessionRef.current++;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
    connect();
  }, [connect]);

  return { state, send, reconnect };
}
