import { useEffect, useRef, useState } from "react";

// Connects to app3's /realtime WebSocket and calls onEvent for each message.
// Auto-reconnects. Returns the live connection state.
export function useRealtime(onEvent: (msg: any) => void) {
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/realtime";
    let ws: WebSocket | null = null;
    let alive = true;
    let timer: any;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (alive) timer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (e) => {
        try {
          cb.current(JSON.parse(e.data));
        } catch {
          /* ignore */
        }
      };
    };
    connect();

    return () => {
      alive = false;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return connected;
}
