"use client";

import { useEffect } from "react";
import { useAppStore } from "@/store/useAppStore";
import api, { alertsApi, csiApi } from "@/lib/api";
import { parseCSI } from "@/lib/csi";
import { clearSession, getAccessToken, SESSION_EXPIRED_EVENT } from "@/lib/session";
import { diagnostic } from "@/lib/diagnostics";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

// Exported for the same message path to be covered by frontend regression tests.
export function handleRealtimeMessage(msg: Record<string, unknown>) {
  const { addAlert, updateCSI, setPredictions, updateClassroomMetric } = useAppStore.getState();
  switch (msg.type) {
    case "new_alert":
      addAlert(msg.alert as Parameters<typeof addAlert>[0]);
      break;
    case "alert_deleted":
      if (typeof msg.alert_id === "string") {
        useAppStore.setState(state => ({ alerts: state.alerts.filter(alert => alert.id !== msg.alert_id) }));
      }
      break;
    case "csi_update":
      updateCSI(parseCSI(msg));
      break;
    case "predictions_update":
      setPredictions(msg.predictions as Parameters<typeof setPredictions>[0]);
      break;
    case "classroom_update":
      updateClassroomMetric(msg.camera_id as string, msg.metrics as Parameters<typeof updateClassroomMetric>[1]);
      break;
  }
}

export function startRealtimeEvents() {
    let mounted = true;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let fetching = false;
    const { updateCSI, setCSIError, setConnected, setBackendConnected, setAuthenticationRequired } = useAppStore.getState();
    let checkingHealth = false;
    const checkHealth = async () => {
      if (checkingHealth) return;
      checkingHealth = true;
      try {
        await api.get("/health");
        if (mounted) setBackendConnected(true);
        diagnostic("Dashboard", "API connected");
      } catch {
        if (mounted) setBackendConnected(false);
        diagnostic("Dashboard", "API health request failed");
      } finally { checkingHealth = false; }
    };

    const onSessionExpired = () => {
      setAuthenticationRequired(true);
      setConnected(false);
      setCSIError(true);
      clearTimeout(reconnectTimer);
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);

    const fetchCSI = async () => {
      if (fetching || !getAccessToken()) return;
      fetching = true;
      try {
        const response = await csiApi.campus();
        const data = parseCSI(response.data);
        if (mounted) updateCSI(data);
        diagnostic("CSI", `score updated: ${data.overall_score}`);
      } catch (error) {
        if (mounted) {
          setCSIError(true);
          diagnostic("CSI", `Refresh failed; retaining last valid score: ${error instanceof Error ? error.message : "request failed"}`);
        }
      } finally {
        fetching = false;
      }
    };

    const fetchMissedAlerts = async () => {
      try {
        const response = await alertsApi.list({ status: "active", limit: 50 });
        if (mounted && Array.isArray(response.data)) {
          response.data.forEach(alert => useAppStore.getState().addAlert(alert));
        }
      } catch { /* Retain existing alerts; retry on the next connection/resync. */ }
    };

    const connect = () => {
      if (!mounted) return;
      if (socket && socket.readyState < WebSocket.CLOSING) return;
      const token = getAccessToken();
      if (!token) { onSessionExpired(); return; }
      setAuthenticationRequired(false);
      clearTimeout(reconnectTimer);
      const ws = new WebSocket(`${WS_URL}/api/v1/ws/events?token=${encodeURIComponent(token)}`);
      socket = ws;
      ws.onopen = () => {
        if (!mounted || socket !== ws) { ws.close(); return; }
        setConnected(true);
        diagnostic("WebSocket", "connected");
        void fetchCSI();
        void fetchMissedAlerts();
      };
      ws.onmessage = (event) => {
        if (!mounted || socket !== ws || event.data === "pong") return;
        try {
          const message = JSON.parse(event.data);
          if (message.type === "realtime_resync") void fetchMissedAlerts();
          else handleRealtimeMessage(message);
        } catch (error) {
          console.error("[WS] Invalid event", error);
        }
      };
      ws.onclose = (event) => {
        if (!mounted || socket !== ws) return;
        socket = null;
        setConnected(false);
        diagnostic("WebSocket", "disconnected");
        if (event.code === 4001) { clearSession(token); return; }
        if (!getAccessToken()) return;
        diagnostic("WebSocket", "reconnecting in 3000ms");
        reconnectTimer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    void fetchCSI();
    void checkHealth();
    // Existing polling remains as a fallback and accounts for continuous time decay.
    const pollInterval = setInterval(fetchCSI, 5000);
    const healthInterval = setInterval(checkHealth, 10000);
    const pingInterval = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, 25000);

    return () => {
      mounted = false;
      clearInterval(pollInterval);
      clearInterval(healthInterval);
      clearInterval(pingInterval);
      clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
      window.removeEventListener(SESSION_EXPIRED_EVENT, onSessionExpired);
      setConnected(false);
    };
}

export function useRealtimeEvents() {
  useEffect(startRealtimeEvents, []);
}
