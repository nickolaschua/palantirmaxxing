/** WGS84. Degrees for lon/lat, metres for height. This never changes. */
export interface GeoPoint {
  lon: number;
  lat: number;
  height?: number;
}

/** A position at an instant. */
export interface TimedSample extends GeoPoint {
  time: Date;
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

export type BasemapKind = "photorealistic" | "extruded" | "plain";
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
  /** Read-only diagnostics for local acceptance runs; no rendering substitution. */
  acceptance?: boolean;
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
  /**
   * Cesium's tile detail threshold for the city tilesets; its default is 16.
   * Smaller loads finer tiles. Tile choice scales with canvas height, so a
   * small canvas needs a small value to show what a large one shows at the
   * same pose: a 300 px tall window wants about 2.
   */
  maximumScreenSpaceError?: number;
}

export type CanvasEvents = {
  renderError: { message: string };
  cameraChange: CameraPose;
  tileLoadProgress: { pending: number };
  boundsHit: { edge: BoundsEdge };
  /** Host time, whenever it changes — every frame while playing, once per seek. */
  clockTick: Date;
};

/** Rejection reason when a flight is interrupted by another camera command. */
export class FlightCancelled extends Error {
  constructor() {
    super("Camera flight was cancelled");
    this.name = "FlightCancelled";
  }
}
