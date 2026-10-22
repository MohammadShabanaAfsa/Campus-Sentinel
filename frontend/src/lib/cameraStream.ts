import { clearSession, getAccessToken, SESSION_EXPIRED_EVENT } from "@/lib/session";
import { diagnostic } from "@/lib/diagnostics";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function startCameraStream(cameraId: string, callbacks: {
  onConnected: (connected: boolean) => void;
  onMessage: (message: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onRetry?: (attempt: number) => void;
}) {
  let disposed = false;
  let socket: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempts = 0;

  const stop = () => {
    disposed = true;
    clearTimeout(timer);
    if (socket) {
      socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
      socket.close();
      socket = null;
    }
    window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  };
  const expired = () => {
    stop();
    callbacks.onConnected(false);
    callbacks.onError?.("Sign in required");
  };
  const connect = () => {
    if (disposed || (socket && socket.readyState < WebSocket.CLOSING)) return;
    const token = getAccessToken();
    if (!token) { expired(); return; }
    const ws = new WebSocket(`${WS_URL}/api/v1/ws/camera/${cameraId}/stream?token=${encodeURIComponent(token)}`);
    socket = ws;
    ws.onopen = () => {
      if (disposed || socket !== ws) return;
      attempts = 0;
      callbacks.onConnected(true);
      diagnostic("Cameras", `${cameraId} stream connected`);
    };
    ws.onmessage = (event) => {
      if (disposed || socket !== ws) return;
      try { callbacks.onMessage(JSON.parse(event.data)); } catch { /* Ignore malformed frames. */ }
    };
    ws.onerror = () => ws.close();
    ws.onclose = (event) => {
      if (disposed || socket !== ws) return;
      socket = null;
      callbacks.onConnected(false);
      if (event.code === 4001) { clearSession(token); expired(); return; }
      if (!getAccessToken()) { expired(); return; }
      if (attempts >= 5) {
        callbacks.onError?.("Connection failed after multiple attempts. Click retry to try again.");
        return;
      }
      attempts += 1;
      callbacks.onRetry?.(attempts);
      timer = setTimeout(connect, 3000);
    };
  };
  window.addEventListener(SESSION_EXPIRED_EVENT, expired);
  connect();
  return stop;
}
