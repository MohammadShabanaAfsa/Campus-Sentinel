import type { CSIData, RiskLevel } from "@/store/useAppStore";

const levels = new Set<RiskLevel>(["safe", "low_risk", "moderate", "high_risk", "critical"]);

// API and realtime messages carry the same complete backend snapshot.
export function parseCSI(data: Record<string, unknown>): CSIData {
  const scoreKeys = ["overall_score", "crowd_score", "loitering_score", "access_score", "anomaly_score"];
  for (const key of scoreKeys) {
    const value = data[key];
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
      throw new Error(`Invalid backend CSI field: ${key}`);
    }
  }
  if (!levels.has(data.risk_level as RiskLevel) || typeof data.updated_at !== "string" || !Number.isFinite(Date.parse(data.updated_at))) {
    throw new Error("Invalid backend CSI level or timestamp");
  }
  for (const key of ["anomaly_count", "active_alerts"]) {
    if (typeof data[key] !== "number" || !Number.isInteger(data[key]) || (data[key] as number) < 0) {
      throw new Error(`Invalid backend CSI count: ${key}`);
    }
  }
  return data as unknown as CSIData;
}
