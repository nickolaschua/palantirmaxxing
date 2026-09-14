/** WGS84. Degrees for lon/lat, metres for height. This never changes. */
export interface GeoPoint {
  lon: number;
  lat: number;
  height?: number;
}

/** WGS84 degrees. */
export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** Degrees. Negative pitch looks down. */
export interface CameraOrientation {
  heading?: number;
  pitch?: number;
  roll?: number;
}

export interface CameraPose extends GeoPoint, CameraOrientation {}

export type BasemapKind = "photorealistic" | "extruded";
export type LightingPreset = "midday" | "blue-hour";
export type BoundsEdge = "west" | "south" | "east" | "north" | "ceiling" | "floor";

/**
 * Singapore mainland plus the southern islands, with roughly 5 km of margin.
 * The camera cannot leave this box unless `bounds: null` is passed.
 */
export const SINGAPORE_BOUNDS: Bounds = {
  west: 103.56,
  south: 1.13,
  east: 104.14,
  north: 1.52,
};

export interface CanvasOptions {
  ionToken?: string;
  googleApiKey?: string;
  basemap?: BasemapKind;
  lighting?: LightingPreset;
  /** Hard camera cage. `null` unlocks it and lets the camera roam the globe. */
  bounds?: Bounds | null;
  /** Metres above the ellipsoid. Caps how far out you can zoom. */
  maxHeight?: number;
  /** Metres above the ellipsoid. Stops the camera burrowing through the mesh. */
  minHeight?: number;
}

export type CanvasEvents = {
  cameraChange: CameraPose;
  tileLoadProgress: { pending: number };
  boundsHit: { edge: BoundsEdge };
};

/** Rejection reason when a flight is interrupted by another camera command. */
export class FlightCancelled extends Error {
  constructor() {
    super("Camera flight was cancelled");
    this.name = "FlightCancelled";
  }
}
