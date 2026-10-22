// Campus anchor matches the existing General Entrance camera record, confirmed
// by the user as the correct green marker. Public env values can override it.
export const CAMPUS_NAME = "Sreyas Institute of Engineering and Technology";

function coordinate(raw: string | undefined, fallback: number, min: number, max: number) {
  const value = raw?.trim() ? Number(raw) : NaN;
  return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
}

export const CAMPUS_CENTER: [number, number] = [
  coordinate(process.env.NEXT_PUBLIC_CAMPUS_LAT, 17.3545464, -90, 90),
  coordinate(process.env.NEXT_PUBLIC_CAMPUS_LNG, 78.5934475, -180, 180),
];
export const CAMPUS_ZOOM = coordinate(process.env.NEXT_PUBLIC_CAMPUS_ZOOM, 18, 1, 19);

const warnedCameras = new Set<string>();
export function cameraPosition(camera: { id: string; name: string; latitude?: number | null; longitude?: number | null }): [number, number] | null {
  const { latitude, longitude } = camera;
  if (latitude == null || longitude == null || !Number.isFinite(latitude) || !Number.isFinite(longitude) ||
      latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
    if (!warnedCameras.has(camera.id)) {
      warnedCameras.add(camera.id);
      console.warn(`[Map] Hiding ${camera.name} marker: missing or invalid coordinates`);
    }
    return null;
  }
  return [latitude, longitude];
}
