import type { SingaporeCanvas } from "../lib/index.js";
import militaryJson from "./military.json";
import hospitalsJson from "./hospitals.json";

/** One named-area layer from OSM: what to draw, in which colour, and how the legend names it. */
export interface OsmAreaLayer {
  id: string;
  /** The tint, the outline and the legend swatch. */
  colour: string;
  legend: string;
  areas: readonly { name: string | null; ring: number[] }[];
}

export const MILITARY: OsmAreaLayer = {
  id: "military", colour: "#70a366", legend: "Military bases · OpenStreetMap landuse=military",
  areas: militaryJson.military as OsmAreaLayer["areas"],
};
export const HOSPITALS: OsmAreaLayer = {
  id: "hospital", colour: "#e5484d", legend: "Hospitals · OpenStreetMap amenity=hospital",
  areas: hospitalsJson.hospital as OsmAreaLayer["areas"],
};

/** Labels show below this camera height, so the island view is not a wall of names. */
const LABEL_BELOW_M = 20_000;

interface Point { lon: number; lat: number }

/** Integers of degrees × 1e5, delta-encoded after the first point: the library's ground-data encoding. */
function decode(enc: readonly number[]): Point[] {
  const out: Point[] = [];
  let x = enc[0] ?? 0;
  let y = enc[1] ?? 0;
  out.push({ lon: x / 1e5, lat: y / 1e5 });
  for (let i = 2; i < enc.length; i += 2) {
    x += enc[i] ?? 0;
    y += enc[i + 1] ?? 0;
    out.push({ lon: x / 1e5, lat: y / 1e5 });
  }
  return out;
}

const centroid = (ring: readonly Point[]): Point => ({
  lon: ring.reduce((s, p) => s + p.lon, 0) / ring.length,
  lat: ring.reduce((s, p) => s + p.lat, 0) / ring.length,
});

/** Shoelace, in square degrees; only used to rank rings that share a name. */
function area(ring: readonly Point[]): number {
  let twice = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[j] as Point, b = ring[i] as Point;
    twice += a.lon * b.lat - b.lon * a.lat;
  }
  return Math.abs(twice / 2);
}

export interface AreaLayer {
  setVisible(visible: boolean): void;
  destroy(): void;
}

/**
 * Named areas from OSM: buildings tinted in the layer's colour, boundaries
 * drawn and, on the main map, each name labelled once. Illustration from
 * public map data, not part of planning-result/1.
 */
export function mountOsmAreas(canvas: SingaporeCanvas, layer: OsmAreaLayer, options: { labels: boolean }): AreaLayer {
  const areas = layer.areas.map((a, i) => ({ id: `${layer.id}-${i}`, name: a.name, ring: decode(a.ring) }));
  const tint = canvas.addBuildingTint(areas, { color: layer.colour, outlineColor: layer.colour, outlineWidth: 2 });

  let visible = true;
  let labels: ReturnType<SingaporeCanvas["addLabels"]> | undefined;
  let offCamera: (() => void) | undefined;
  const labelsShow = (height: number | undefined): void => labels?.setVisible(visible && (height ?? Infinity) < LABEL_BELOW_M);
  if (options.labels) {
    // One label per name, on its largest ring.
    const largest = new Map<string, Point[]>();
    for (const a of areas) {
      if (a.name && area(a.ring) > area(largest.get(a.name) ?? [])) largest.set(a.name, a.ring);
    }
    labels = canvas.addLabels([...largest].map(([text, ring]) => ({ position: centroid(ring), text })));
    labelsShow(canvas.camera.pose.height);
    offCamera = canvas.on("cameraChange", pose => labelsShow(pose.height));
  }
  return {
    setVisible(value) {
      visible = value;
      tint.setVisible(value);
      labelsShow(canvas.camera.pose.height);
    },
    destroy() {
      offCamera?.();
      labels?.destroy();
      tint.destroy();
    },
  };
}
