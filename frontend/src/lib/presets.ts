import type { GeoPoint } from "./types.js";

/**
 * Camera presets. Plain data — edit this file to add, remove or retune, no code
 * change needed. The demo panel is generated from whatever is in here.
 *
 * A preset is a REAL WGS84 position plus a viewing offset. The target is the
 * actual location of the place and must not be nudged for framing; all framing
 * lives in heading/pitch/range. This is why the original spike's presets
 * drifted: it stored hand-tuned camera positions, and its Merlion preset ended
 * up ~250 m off, pointing at open water.
 *
 * Town coordinates are OSM/Nominatim centroids, not estimates.
 */
export interface CameraPreset {
  label: string;
  /** Real WGS84 position of the subject. Do not adjust for looks. */
  target: GeoPoint;
  /** Compass bearing of the camera relative to the target, degrees. */
  heading: number;
  /** Degrees below horizontal. Negative looks down. */
  pitch: number;
  /** Metres from the target. */
  range: number;
}

/** Oblique town-scale view: camera sits ~1.6 km up, ~2.3 km back. */
const TOWN = { heading: 30, pitch: -35, range: 2800 } as const;

export const PRESETS: Record<string, CameraPreset> = {
  island: {
    label: "Whole island",
    target: { lon: 103.8198, lat: 1.3521 },
    heading: 0,
    pitch: -60,
    range: 42000,
  },

  // --- West ---
  "jurong-west": { label: "Jurong West", target: { lon: 103.7049, lat: 1.3416 }, ...TOWN },
  "jurong-east": { label: "Jurong East", target: { lon: 103.7348, lat: 1.3204 }, ...TOWN },
  "bukit-batok": { label: "Bukit Batok", target: { lon: 103.7547, lat: 1.3557 }, ...TOWN },
  clementi: { label: "Clementi", target: { lon: 103.7608, lat: 1.3176 }, ...TOWN },
  queenstown: { label: "Queenstown", target: { lon: 103.7845, lat: 1.2892 }, ...TOWN },

  // --- Central ---
  "toa-payoh": { label: "Toa Payoh", target: { lon: 103.8481, lat: 1.3356 }, ...TOWN },
  bishan: { label: "Bishan", target: { lon: 103.849, lat: 1.3519 }, ...TOWN },
  "ang-mo-kio": { label: "Ang Mo Kio", target: { lon: 103.8421, lat: 1.3801 }, ...TOWN },

  // --- North-east ---
  serangoon: { label: "Serangoon", target: { lon: 103.8709, lat: 1.3517 }, ...TOWN },
  hougang: { label: "Hougang", target: { lon: 103.8898, lat: 1.3636 }, ...TOWN },
  sengkang: { label: "Sengkang", target: { lon: 103.8877, lat: 1.3913 }, ...TOWN },
  punggol: { label: "Punggol", target: { lon: 103.91, lat: 1.4054 }, ...TOWN },

  // --- North ---
  yishun: { label: "Yishun", target: { lon: 103.835, lat: 1.4294 }, ...TOWN },
  woodlands: { label: "Woodlands", target: { lon: 103.7862, lat: 1.4369 }, ...TOWN },

  // --- East ---
  tampines: { label: "Tampines", target: { lon: 103.9439, lat: 1.3541 }, ...TOWN },
  bedok: { label: "Bedok", target: { lon: 103.9284, lat: 1.3241 }, ...TOWN },
};
