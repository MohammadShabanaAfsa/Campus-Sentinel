import { create } from "zustand";

export type AlertSeverity = "low" | "medium" | "high" | "critical";
export type RiskLevel = "safe" | "low_risk" | "moderate" | "high_risk" | "critical";

export interface Alert {
  id: string;
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  camera_id?: string;
  threat_score: number;
  created_at: string;
  status: string;
  explanation?: Record<string, unknown>;
}

export interface Camera {
  last_error?: string | null;
  id: string;
  name: string;
  location_name: string;
  status: "online" | "offline" | "error" | "maintenance";
  zone_type: string;
  latitude?: number;
  longitude?: number;
  is_recording: boolean;
}

export interface CSIData {
  overall_score: number;
  risk_level: RiskLevel;
  crowd_score: number;
  loitering_score: number;
  access_score: number;
  anomaly_score: number;
  anomaly_count: number;
  active_alerts: number;
  updated_at: string;
}

export interface Prediction {
  threat_type: string;
  probability: number;
  threat_level: string;
  recommended_action?: string;
  camera_id?: string;
}

export interface ClassroomMetric {
  id: number;
  recorded_at: string;
  camera_id: string;
  present_count: number;
  expected_count: number;
  missing_count: number;
  sleeping_count: number;
  talking_count: number;
  attentive_count: number;
  faculty_present: boolean;
  faculty_engagement_score: number;
  attention_index: number;
  details: Record<string, unknown>;
}

interface AppState {
  alerts: Alert[];
  cameras: Camera[];
  csi: CSIData | null;
  csiError: boolean;
  predictions: Prediction[];
  activeCameraId: string | null;
  isConnected: boolean;
  backendConnected: boolean | null;
  authenticationRequired: boolean;
  camerasLoaded: boolean;
  cameraError: boolean;
  classroomMetrics: Record<string, ClassroomMetric>; // keyed by camera_id — latest snapshot

  addAlert: (alert: Alert) => void;
  setCameras: (cameras: Camera[]) => void;
  updateCSI: (csi: CSIData) => void;
  setCSIError: (value: boolean) => void;
  setPredictions: (predictions: Prediction[]) => void;
  setActiveCameraId: (id: string | null) => void;
  setConnected: (v: boolean) => void;
  setBackendConnected: (value: boolean) => void;
  setAuthenticationRequired: (value: boolean) => void;
  setCameraError: (value: boolean) => void;
  acknowledgeAlert: (id: string) => void;
  updateClassroomMetric: (cameraId: string, metric: ClassroomMetric) => void;
}

export const useAppStore = create<AppState>((set) => ({
  alerts: [],
  cameras: [],
  csi: null,
  csiError: false,
  predictions: [],
  activeCameraId: null,
  isConnected: false,
  backendConnected: null,
  authenticationRequired: false,
  camerasLoaded: false,
  cameraError: false,
  classroomMetrics: {},

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts.filter(existing => existing.id !== alert.id)].slice(0, 200),
    })),

  setCameras: (cameras) => set({ cameras, camerasLoaded: true, cameraError: false }),
  setCameraError: (cameraError) => set({ cameraError }),

  updateCSI: (csi) =>
    set((state) => {
      if (state.csi && Date.parse(csi.updated_at) < Date.parse(state.csi.updated_at)) return state;
      return { csi, csiError: false };
    }),
  setCSIError: (csiError) => set({ csiError }),

  setPredictions: (predictions) => set({ predictions }),

  updateClassroomMetric: (cameraId, metric) =>
    set((state) => ({
      classroomMetrics: { ...state.classroomMetrics, [cameraId]: metric },
    })),

  setActiveCameraId: (activeCameraId) => set({ activeCameraId }),

  setConnected: (isConnected) => set({ isConnected }),
  setBackendConnected: (backendConnected) => set({ backendConnected }),
  setAuthenticationRequired: (authenticationRequired) => set({ authenticationRequired }),

  acknowledgeAlert: (id) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id ? { ...a, status: "acknowledged" } : a
      ),
    })),
}));
