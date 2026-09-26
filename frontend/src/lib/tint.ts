import {
  Cartesian3, ClassificationType, Color, ColorGeometryInstanceAttribute, GeometryInstance, GroundPolylineGeometry,
  GroundPolylinePrimitive, PolylineColorAppearance,
} from "cesium";
import type { Cesium3DTile, Cesium3DTileContent, Cesium3DTileset, Viewer } from "cesium";
import { dedupe } from "./coastline.js";
import type { GeoPoint } from "./types.js";

export interface TintArea { id: string; ring: readonly GeoPoint[] }
export interface TintStyle {
  /** Multiplied into every building whose footprint centre lies inside an area. */
  color: string;
  /** Draws each area's boundary on the ground when set. */
  outlineColor?: string;
  outlineWidth?: number;
}
export interface TintLayer {
  setVisible(visible: boolean): void;
  destroy(): void;
}

/** Cesium OSM Buildings stores each building's footprint centre as feature properties. */
const LON = "cesium#longitude";
const LAT = "cesium#latitude";

interface Area { minLon: number; maxLon: number; minLat: number; maxLat: number; flat: number[] }

/** Ray casting; `flat` is [lon, lat, …] without the closing repeat. */
function contains(a: Area, lon: number, lat: number): boolean {
  if (lon < a.minLon || lon > a.maxLon || lat < a.minLat || lat > a.maxLat) return false;
  const f = a.flat;
  let hit = false;
  for (let i = 0, j = f.length - 2; i < f.length; j = i, i += 2) {
    const xi = f[i] as number, yi = f[i + 1] as number, xj = f[j] as number, yj = f[j + 1] as number;
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

/**
 * Colours the city's buildings whose footprint centre lies inside any of
 * `areas`, and outlines the areas. Buildings are painted per tile as tiles come
 * into view, so the tint survives basemap switches. Google's tiles carry no
 * per-building features, so there only the outline draws.
 */
export function addBuildingTint(
  viewer: Viewer,
  onTileset: (listener: (tileset: Cesium3DTileset | null) => void) => () => void,
  areas: readonly TintArea[],
  style: TintStyle,
): TintLayer {
  const scene = viewer.scene;
  const ids = new Set<string>();
  const prepared = areas.map((a): Area => {
    if (ids.has(a.id)) throw new Error(`Duplicate area id "${a.id}"`);
    ids.add(a.id);
    const flat = dedupe(a.ring.flatMap(p => [p.lon, p.lat]));
    if (flat.length < 6 || !flat.every(Number.isFinite)) throw new Error(`Area "${a.id}" needs at least 3 finite points`);
    const lons = flat.filter((_, i) => i % 2 === 0);
    const lats = flat.filter((_, i) => i % 2 === 1);
    return { minLon: Math.min(...lons), maxLon: Math.max(...lons), minLat: Math.min(...lats), maxLat: Math.max(...lats), flat };
  });

  const tint = Color.fromCssColorString(style.color);
  let visible = true;
  let version = 1; // bumped whenever what a tile should look like changes
  const painted = new WeakMap<Cesium3DTileContent, number>();
  const paint = (tile: Cesium3DTile): void => {
    const content = tile.content as Cesium3DTileContent | undefined;
    if (!content || painted.get(content) === version) return;
    painted.set(content, version);
    for (let i = 0; i < content.featuresLength; i++) {
      const feature = content.getFeature(i);
      const lon: unknown = feature.getProperty(LON);
      const lat: unknown = feature.getProperty(LAT);
      if (typeof lon !== "number" || typeof lat !== "number") continue;
      feature.color = visible && prepared.some(a => contains(a, lon, lat)) ? tint : Color.WHITE;
    }
  };
  let current: Cesium3DTileset | null = null;
  const offTileset = onTileset(tileset => {
    // The previous tileset is already destroyed by the scene; its events never fire again.
    current = tileset;
    tileset?.tileVisible.addEventListener(paint);
  });

  let outline: GroundPolylinePrimitive | null = null;
  if (style.outlineColor) {
    const colour = ColorGeometryInstanceAttribute.fromColor(Color.fromCssColorString(style.outlineColor));
    outline = scene.primitives.add(new GroundPolylinePrimitive({
      classificationType: ClassificationType.BOTH, // draws on Google's tiles too, where the globe is hidden
      appearance: new PolylineColorAppearance(),
      allowPicking: false,
      geometryInstances: prepared.map(a => new GeometryInstance({
        geometry: new GroundPolylineGeometry({ positions: Cartesian3.fromDegreesArray(a.flat), width: style.outlineWidth ?? 2, loop: true }),
        attributes: { color: colour },
      })),
    })) as GroundPolylinePrimitive;
  }

  return {
    setVisible(value) {
      visible = value;
      version++;
      if (outline) outline.show = value;
      scene.requestRender();
    },
    destroy() {
      offTileset();
      if (current && !current.isDestroyed()) current.tileVisible.removeEventListener(paint);
      if (outline) scene.primitives.remove(outline);
      scene.requestRender();
      // ponytail: buildings already painted keep their colour until their tile reloads.
    },
  };
}
