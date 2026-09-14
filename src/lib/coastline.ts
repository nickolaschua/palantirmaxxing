import {
  Cartesian3,
  ClassificationType,
  ClippingPolygon,
  ClippingPolygonCollection,
  Color,
  ColorGeometryInstanceAttribute,
  GeometryInstance,
  GroundPolylineGeometry,
  GroundPolylinePrimitive,
  GroundPrimitive,
  PolygonGeometry,
  PolygonHierarchy,
  PolylineColorAppearance,
  Viewer,
} from "cesium";
import landRings from "./coastline.json";
import waterRings from "./water.json";
import roadLines from "./roads.json";
import pathLines from "./paths.json";

/**
 * The ground: Singapore's landmass, its coastline, and its inland water.
 *
 * This lives with the scene, not with layers. It is part of what Singapore
 * looks like, not data a host application supplied, so a host never adds or
 * removes it and it does not belong in the id-addressed layer registry.
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
 */

/** Open sea. This is the globe's base colour, so it covers everything unpainted. */
export const SEA_BLUE = Color.fromCssColorString("#1d4e6b");
/** Reservoirs and lakes — a shade up from the sea so inland water separates. */
export const WATER_BLUE = Color.fromCssColorString("#2a6788");
/** Land. Matches the tone the buildings sit on. */
export const LAND_GREY = Color.fromCssColorString("#8f9194");
/** Coast edge, lighter than land so the boundary stays crisp. */
export const COAST_GREY = Color.fromCssColorString("#c2c6cb");
/** Carriageways — darker than land so they read as cut lines. */
export const ROAD_GREY = Color.fromCssColorString("#5f6469");
/** Pavements and park connectors — between land and road, and thinner. */
export const PAVEMENT_GREY = Color.fromCssColorString("#7c8188");

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
function dedupe(flat: readonly number[]): number[] {
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
const waterPositions = (waterRings as number[][]).map((r) =>
  Cartesian3.fromDegreesArray(dedupe(r)),
);
/**
 * Roads ship delta-encoded: each coordinate is an integer of degrees * 1e5, and
 * every point after the first is stored as an offset from the previous one.
 * Small integers instead of repeated "103.84217" strings takes the full
 * drivable network from 2.87 MB to 1.85 MB.
 */
function decodeLine(enc: readonly number[]): number[] {
  const out: number[] = [];
  let x = enc[0] as number;
  let y = enc[1] as number;
  out.push(x / 1e5, y / 1e5);
  for (let i = 2; i < enc.length; i += 2) {
    x += enc[i] as number;
    y += enc[i + 1] as number;
    out.push(x / 1e5, y / 1e5);
  }
  return out;
}

function toPositions(lines: number[][]): Cartesian3[][] {
  return lines
    .map((r) => dedupe(decodeLine(r)))
    .filter((r) => r.length >= 4)
    .map((r) => Cartesian3.fromDegreesArray(r));
}

const roadPositions = toPositions(roadLines as number[][]);
const pathPositions = toPositions(pathLines as number[][]);

function lineLayer(lines: Cartesian3[][], color: Color, width: number): GroundPolylinePrimitive {
  return new GroundPolylinePrimitive({
    classificationType: ClassificationType.TERRAIN,
    appearance: new PolylineColorAppearance(),
    geometryInstances: lines.map(
      (line) =>
        new GeometryInstance({
          geometry: new GroundPolylineGeometry({ positions: line, width }),
          attributes: { color: ColorGeometryInstanceAttribute.fromColor(color) },
        }),
    ),
  });
}

function fill(rings: Cartesian3[][], color: Color): GroundPrimitive {
  return new GroundPrimitive({
    // TERRAIN only. BOTH would drape the fill over the buildings as well and
    // flatten the city into a coloured slab.
    classificationType: ClassificationType.TERRAIN,
    geometryInstances: rings.map(
      (ring) =>
        new GeometryInstance({
          geometry: new PolygonGeometry({ polygonHierarchy: new PolygonHierarchy(ring) }),
          attributes: { color: ColorGeometryInstanceAttribute.fromColor(color) },
        }),
    ),
  });
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

export function addGround(viewer: Viewer): Ground {
  const scene = viewer.scene;

  const land = fill(landPositions, LAND_GREY);
  const water = fill(waterPositions, WATER_BLUE);

  const coast = new GroundPolylinePrimitive({
    classificationType: ClassificationType.TERRAIN,
    appearance: new PolylineColorAppearance(),
    geometryInstances: landPositions.map(
      (ring) =>
        new GeometryInstance({
          geometry: new GroundPolylineGeometry({ positions: ring, width: 2, loop: true }),
          attributes: { color: ColorGeometryInstanceAttribute.fromColor(COAST_GREY) },
        }),
    ),
  });

  const roads = lineLayer(roadPositions, ROAD_GREY, 2.5);
  const paths = lineLayer(pathPositions, PAVEMENT_GREY, 1);

  // Order matters: land, then water, then pavements under roads so junctions
  // read correctly, then the coast edge on top.
  scene.primitives.add(land);
  scene.primitives.add(water);
  scene.primitives.add(paths);
  scene.primitives.add(roads);
  scene.primitives.add(coast);

  return {
    setVisible(visible: boolean): void {
      land.show = visible;
      water.show = visible;
      roads.show = visible;
      paths.show = visible;
      coast.show = visible;
    },
    destroy(): void {
      scene.primitives.remove(land);
      scene.primitives.remove(water);
      scene.primitives.remove(roads);
      scene.primitives.remove(paths);
      scene.primitives.remove(coast);
    },
  };
}
