import axios from "axios";
import { clearSession, getAccessToken } from "@/lib/session";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  timeout: 15000,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const isLogin = /\/auth\/(login|register)$/.test(config.url || "");
    if (isLogin || config.url === "/health") return config;
    const token = getAccessToken();
    if (!token) return Promise.reject(new Error("Sign in required"));
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      const isLogin = /\/auth\/(login|register)$/.test(error.config?.url || "");
      if (!isLogin) {
        const authorization = error.config?.headers?.Authorization;
        if (typeof authorization === "string" && authorization.startsWith("Bearer ")) {
          clearSession(authorization.slice(7));
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ─── Typed API helpers ────────────────────────────────────────────────────────

export const camerasApi = {
  list: () => api.get("/api/v1/cameras/"),
  get: (id: string) => api.get(`/api/v1/cameras/${id}`),
  create: (data: unknown) => api.post("/api/v1/cameras/", data),
  update: (id: string, data: unknown) => api.patch(`/api/v1/cameras/${id}`, data),
  delete: (id: string) => api.delete(`/api/v1/cameras/${id}`),
  createZone: (id: string, data: unknown) => api.post(`/api/v1/cameras/${id}/zones`, data),
};

export const alertsApi = {
  list: (params?: Record<string, unknown>) => api.get("/api/v1/alerts/", { params }),
  stats: () => api.get("/api/v1/alerts/stats"),
  get: (id: string) => api.get(`/api/v1/alerts/${id}`),
  acknowledge: (id: string) => api.patch(`/api/v1/alerts/${id}`, { status: "acknowledged" }),
  resolve: (id: string) => api.patch(`/api/v1/alerts/${id}`, { status: "resolved" }),
};

export const csiApi = {
  campus: () => api.get("/api/v1/csi/campus"),
  latest: () => api.get("/api/v1/csi/latest"),
  history: (params?: Record<string, unknown>) => api.get("/api/v1/csi/history", { params }),
};

export const predictionsApi = {
  list: (params?: Record<string, unknown>) => api.get("/api/v1/predictions/", { params }),
};

export const analyticsApi = {
  summary: (hours?: number) => api.get("/api/v1/analytics/summary", { params: { hours } }),
  detectionsByHour: (hours?: number) => api.get("/api/v1/analytics/detections/by-hour", { params: { hours } }),
  behaviorDistribution: (hours?: number) => api.get("/api/v1/analytics/behavior/distribution", { params: { hours } }),
};

export const heatmapApi = {
  detections: (params?: Record<string, unknown>) => api.get("/api/v1/heatmap/detections", { params }),
  behavior: (params?: Record<string, unknown>) => api.get("/api/v1/heatmap/behavior", { params }),
};

export const settingsApi = {
  get: () => api.get("/api/v1/settings/"),
  update: (data: Record<string, unknown>) => api.put("/api/v1/settings/", data),
  reset: () => api.post("/api/v1/settings/reset"),
};

export const incidentsApi = {
  list: (params?: Record<string, unknown>) => api.get("/api/v1/incidents/", { params }),
  create: (data: unknown) => api.post("/api/v1/incidents/", data),
  resolve: (id: string) => api.patch(`/api/v1/incidents/${id}/resolve`),
};

export const adminApi = {
  trainABD: () => api.post("/api/v1/admin/train-abd"),
  computeCSI: () => api.post("/api/v1/admin/compute-csi"),
  seedData: (days?: number) => api.post("/api/v1/admin/seed-data", null, { params: { days } }),
  sendDigest: () => api.post("/api/v1/admin/send-digest"),
};

export const authApi = {
  login: (email: string, password: string) => {
    const form = new FormData();
    form.append("username", email);
    form.append("password", password);
    return api.post("/api/v1/auth/login", form);
  },
  me: () => api.get("/api/v1/auth/me"),
};

export const classroomApi = {
  list: () => api.get("/api/v1/classroom/"),
  getConfig: (cameraId: string) => api.get(`/api/v1/classroom/${cameraId}/config`),
  updateConfig: (cameraId: string, data: object) =>
    api.put(`/api/v1/classroom/${cameraId}/config`, data),
  latestMetric: (cameraId: string) => api.get(`/api/v1/classroom/${cameraId}/metrics/latest`),
  metricHistory: (cameraId: string, hours?: number) =>
    api.get(`/api/v1/classroom/${cameraId}/metrics/history`, { params: { hours } }),
};
