import {
  Cartesian3,
  ClassificationType,
  ClippingPolygon,
  ClippingPolygonCollection,
  Color,
  ColorGeometryInstanceAttribute,
  Event,
  GeographicTilingScheme,
  GeometryInstance,
  GroundPolylineGeometry,
  GroundPolylinePrimitive,
  Math as CesiumMath,
  PolylineColorAppearance,
  Rectangle,
  Viewer,
} from "cesium";
import type { ImageryProvider } from "cesium";
import landRings from "./coastline.json";
import waterRings from "./water.json";
import greenRings from "./greens.json";
import structureLines from "./structures.json";
import { packLines, query } from "./ground-model.js";
import type { Lines } from "./ground-model.js";

/**
 * The ground: Singapore's landmass, its coastline, and its inland water.
 *
 * This lives with the scene, not with layers. It is part of what Singapore
 * looks like, not data a host application supplied, so a host never adds or
 * removes it and it does not belong in the id-addressed layer registry.
 *
 * It is drawn as an imagery layer on the globe: each map tile Cesium asks for
 * is painted with Canvas 2D from the data below, so only what is on screen
 * costs memory. Being part of the globe surface, it sits under every
 * classification primitive (circles, outlines, tints) and drapes over terrain.
 *
 * Land geometry is OSM `place=island` relations 1769123 (Pulau Ujong) and
 * 9574725 (Sentosa), via Nominatim at a ~11 m simplification threshold. This is
 * the real coastline, NOT the political boundary: Singapore's admin boundary
 * runs out to Pedra Branca and follows maritime borders through the straits,
 * so it does not look like the island at all.
 *
 * Water is OSM `natural=water` / `landuse=reservoir` ways and relation outer
 * members via Overpass, filtered to bodies whose centroid falls inside the land
 * rings (which drops Johor), deduplicated by name, and Douglas-Peucker
 * simplified to ~9 m. 30 bodies, ~1.8k points.
 *
 * Roads are every OSM carriageway: motorway through residential, living_street
 * and service, including link roads. 162,905 ways / 344k points. Pavements are
 * footway, path, steps, pedestrian and cycleway — 80,523 ways / 183k points.
 * Both clipped to Singapore and simplified to ~13 m.
 *
 * Greens and structures come from `scripts/fetch-ground-detail.mjs`: forest,
 * nature reserves and mangrove; parks, grass and golf courses; road bridges and
 * tunnels; MRT/LRT viaducts and tunnels. Outer rings only — an enclosed
 * reservoir shows because water draws after the greens — and areas under
 * 3,000 m² are dropped.
 */

/** Open sea, near black. The globe's base colour, so it covers everything unpainted. */
export const SEA_GREY = Color.fromCssColorString("#191a1a");
/** Reservoirs and lakes, a dark blue-grey a shade up from the sea so inland water separates. */
export const WATER_BLUE = Color.fromCssColorString("#40494f");
/** Land, a dark warm grey: the canvas is dark, and its lines are lighter than the land. */
export const LAND_GREY = Color.fromCssColorString("#343332");
/** Coast edge, a faint step up from land; the land/sea contrast carries the boundary. */
export const COAST_GREY = Color.fromCssColorString("#454442");
/** Carriageways — lighter than land so they read as drawn lines. */
export const ROAD_GREY = Color.fromCssColorString("#61605e");
/** Pavements and park connectors — between land and road, and thinner. */
export const PAVEMENT_GREY = Color.fromCssColorString("#444341");
/** Forest, nature reserves and mangrove. A greyish green, so the canvas stays grey first. */
export const FOREST_GREEN = Color.fromCssColorString("#61695d");
/** Parks, grass and golf courses — a greyish green a step lighter than forest. */
export const PARK_GREEN = Color.fromCssColorString("#737b67");
/** Road bridges and tunnels — lighter than the carriageways around them. */
export const STRUCTURE_GREY = Color.fromCssColorString("#7d7c7a");
/** MRT and LRT viaducts and tunnels, the lightest line. */
export const RAIL_GREY = Color.fromCssColorString("#898886");

export interface Ground {
  setVisible(visible: boolean): void;
  destroy(): void;
}

/**
 * Strip consecutive duplicate vertices, including the closing point GeoJSON
 * rings repeat. A zero-length segment makes GroundPolylineGeometry normalize a
 * zero vector, which throws "normalized result is not a number" and halts the
 * whole render loop. Runs on the shared ring data rather than at each use site.
 */
export function dedupe(flat: readonly number[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < flat.length; i += 2) {
    const lon = flat[i] as number;
    const lat = flat[i + 1] as number;
    const n = out.length;
    if (n >= 2 && out[n - 2] === lon && out[n - 1] === lat) continue;
    out.push(lon, lat);
  }
  if (out.length >= 4 && out[0] === out[out.length - 2] && out[1] === out[out.length - 1]) {
    out.length -= 2;
  }
  return out;
}

const landPositions = (landRings as number[][]).map((r) =>
  Cartesian3.fromDegreesArray(dedupe(r)),
);

/*
 * Roads, greens and structures ship delta-encoded: each coordinate is an
 * integer of degrees * 1e5, and every point after the first is stored as an
 * offset from the previous one. Small integers instead of repeated "103.84217"
 * strings takes the full drivable network from 2.87 MB to 1.85 MB. Land and
 * water are plain degrees. All are packed once per page and shared by every canvas.
 */
const land = packLines(landRings as number[][], false);
const water = packLines(waterRings as number[][], false);
const forest = packLines(greenRings.forest as number[][], true);
const parks = packLines(greenRings.park as number[][], true);

/*
 * Level of detail by tile level. A 256 px geographic tile at level L is about
 * 78 km / 2^L per pixel, and Cesium picks a level whose pixels are near screen
 * pixels: on a ~1400 px wide map level 12 (~19 m) is roughly a 20 km camera
 * height, level 14 (~5 m) roughly 4 km. Above them, lines would be sub-pixel
 * grey blur. Level 20 (~7 cm) is the finest; Cesium stretches it for anything closer.
 */
const ROADS_FROM_LEVEL = 12;
const PATHS_FROM_LEVEL = 14;
const MAX_LEVEL = 20;
const TILE = 256;

/**
 * Roads and pavements are 6 MB of JSON and 243k lines: loaded as their own
 * chunks the first time a tile needs them. Once per page, shared by every canvas.
 */
let roads: Lines | null = null;
let paths: Lines | null = null;
let roadsLoad: Promise<void> | null = null;
let pathsLoad: Promise<void> | null = null;
const loadRoads = (): Promise<void> => roadsLoad ??= import("./roads.json")
  .then(({ default: lines }) => { roads = packLines(lines as number[][], true); });
const loadPaths = (): Promise<void> => pathsLoad ??= import("./paths.json")
  .then(({ default: lines }) => { paths = packLines(lines as number[][], true); });

const tilingScheme = new GeographicTilingScheme();
// Tiles are requested only over the land's box, 0.02° (~2 km) wider for bridges and piers.
const extent = Rectangle.fromDegrees(
  Math.min(...land.box.filter((_, i) => i % 4 === 0)) / 1e5 - 0.02,
  Math.min(...land.box.filter((_, i) => i % 4 === 1)) / 1e5 - 0.02,
  Math.max(...land.box.filter((_, i) => i % 4 === 2)) / 1e5 + 0.02,
  Math.max(...land.box.filter((_, i) => i % 4 === 3)) / 1e5 + 0.02,
);

/** Paints one tile; `lod` is the level used for the road and pavement cut-offs. */
function drawTile(x: number, y: number, level: number, lod: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = TILE;
  const ctx = canvas.getContext("2d")!;
  ctx.lineJoin = ctx.lineCap = "round";
  const r = tilingScheme.tileXYToRectangle(x, y, level);
  const west = CesiumMath.toDegrees(r.west) * 1e5, east = CesiumMath.toDegrees(r.east) * 1e5;
  const south = CesiumMath.toDegrees(r.south) * 1e5, north = CesiumMath.toDegrees(r.north) * 1e5;
  const sx = TILE / (east - west), sy = TILE / (north - south);
  // A line whose box is just outside the tile can still reach in by half its width.
  const pad = 2 / sx;

  const paint = (lines: Lines | null, color: Color, width: number, closed: boolean): void => {
    if (!lines) return;
    const { xy, start } = lines;
    ctx.fillStyle = ctx.strokeStyle = color.toCssColorString();
    ctx.lineWidth = width;
    ctx.beginPath();
    query(lines, west - pad, south - pad, east + pad, north + pad, (i) => {
      for (let p = start[i]!; p < start[i + 1]!; p++) {
        const px = (xy[p * 2]! - west) * sx, py = (north - xy[p * 2 + 1]!) * sy;
        if (p === start[i]) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      if (closed) ctx.closePath();
      // Rings wind both ways, so one nonzero fill of them all would cancel where
      // opposite rings overlap. Filled one by one, overlaps union.
      if (width === 0) { ctx.fill(); ctx.beginPath(); }
    });
    if (width !== 0) ctx.stroke();
  };

  // Order matters: land, then vegetation, then water over both, then pavements
  // under roads so junctions read correctly, bridges and tunnels over the
  // carriageways they carry, and the coast edge on top. Widths are in tile
  // pixels, which Cesium shows at 1–2 screen pixels, so they are about half the
  // screen widths the lines used to have.
  paint(land, LAND_GREY, 0, true);
  paint(forest, FOREST_GREEN, 0, true);
  paint(parks, PARK_GREEN, 0, true);
  paint(water, WATER_BLUE, 0, true);
  if (lod >= PATHS_FROM_LEVEL) paint(paths, PAVEMENT_GREY, 1, false);
  if (lod >= ROADS_FROM_LEVEL) paint(roads, ROAD_GREY, 1.25, false);
  paint(land, COAST_GREY, 1, true);
  return canvas;
}

/**
 * Clips a 3D tileset to Singapore's landmass. `inverse: true` means "clip
 * everything OUTSIDE these polygons", which is what removes Johor's buildings —
 * Cesium OSM Buildings is a global tileset and happily renders Malaysia.
 */
export function singaporeClip(): ClippingPolygonCollection {
  return new ClippingPolygonCollection({
    inverse: true,
    polygons: landPositions.map((positions) => new ClippingPolygon({ positions })),
  });
}

/** Constant screen-width lines draped on the terrain, over the painted ground. Not pickable. */
function structureLayer(lines: number[][], color: Color, width: number): GroundPolylinePrimitive {
  const attributes = { color: ColorGeometryInstanceAttribute.fromColor(color) };
  return new GroundPolylinePrimitive({
    classificationType: ClassificationType.TERRAIN,
    allowPicking: false,
    appearance: new PolylineColorAppearance(),
    geometryInstances: lines.flatMap((enc) => {
      const flat = dedupe(decodeDegrees(enc));
      return flat.length >= 4 ? [new GeometryInstance({ geometry: new GroundPolylineGeometry({ positions: Cartesian3.fromDegreesArray(flat), width }), attributes })] : [];
    }),
  });
}

/** Delta-encoded integers of degrees * 1e5 (see roads.json) back to flat lon/lat degrees. */
function decodeDegrees(enc: readonly number[]): number[] {
  const out: number[] = [];
  let x = 0, y = 0;
  for (let i = 0; i + 1 < enc.length; i += 2) {
    x += enc[i]!; y += enc[i + 1]!;
    out.push(x / 1e5, y / 1e5);
  }
  return out;
}

export function addGround(viewer: Viewer): Ground {
  const scene = viewer.scene;
  const layers = viewer.imageryLayers;
  // The cut-offs assume a ~1400 px wide map; a narrower canvas (the side
  // window) picks tiles ~log2(ratio) levels coarser at the same height.
  const lod = (level: number): number =>
    level + Math.max(0, Math.round(Math.log2(1400 / (viewer.canvas.clientWidth || 1400))));

  // Cesium's ImageryProvider is an interface in practice; its typings declare a class.
  const provider = {
    tilingScheme,
    rectangle: extent,
    tileWidth: TILE,
    tileHeight: TILE,
    minimumLevel: 0,
    maximumLevel: MAX_LEVEL,
    tileDiscardPolicy: undefined,
    errorEvent: new Event(),
    credit: undefined,
    proxy: undefined,
    // Unpainted pixels are clear, so the globe's sea-blue base colour shows.
    hasAlphaChannel: true,
    getTileCredits: () => [],
    pickFeatures: () => undefined,
    requestImage(x: number, y: number, level: number): Promise<HTMLCanvasElement> {
      const detail = lod(level);
      // A tile that shows roads or pavements waits for them, so none is drawn
      // without; meanwhile Cesium stretches the coarser tile above it.
      return Promise.all([
        detail >= ROADS_FROM_LEVEL ? loadRoads() : undefined,
        detail >= PATHS_FROM_LEVEL ? loadPaths() : undefined,
      ]).catch(() => undefined) // chunk fetch failed: draw without
        // Each tile in its own task, so a burst of tiles does not stall one frame.
        .then(() => new Promise((resolve) => setTimeout(() => resolve(drawTile(x, y, level, detail)), 0)));
    },
  } as unknown as ImageryProvider;

  const layer = layers.addImageryProvider(provider);
  // Bridges, tunnels, viaducts and rail stay geometry: only ~4k lines, and they are
  // the network's skeleton from the island view, where tiles would blur them.
  const structures = [
    scene.primitives.add(structureLayer(structureLines.road as number[][], STRUCTURE_GREY, 2.5)),
    scene.primitives.add(structureLayer(structureLines.rail as number[][], RAIL_GREY, 3)),
  ] as GroundPolylinePrimitive[];

  return {
    setVisible(visible: boolean): void {
      layer.show = visible;
      for (const s of structures) s.show = visible;
      scene.requestRender();
    },
    destroy(): void {
      layers.remove(layer);
      for (const s of structures) scene.primitives.remove(s);
    },
  };
}
