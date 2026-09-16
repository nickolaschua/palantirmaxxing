/**
 * Fetches the grey canvas's vegetation and bridge/tunnel geometry from OSM
 * through Overpass and writes src/lib/greens.json and src/lib/structures.json,
 * plus the demo's military areas (with names) to src/demo/military.json.
 *
 *   node scripts/fetch-ground-detail.mjs [forest|park|road|rail|military ...]
 *
 * With no arguments it fetches everything; named layers refresh only those and
 * keep the rest of the file as it is.
 *
 * Output matches the existing roads.json encoding: each ring or line is an
 * array of integers of degrees * 1e5, every point after the first stored as an
 * offset from the previous one (~1 m quantisation, much smaller files).
 *
 * Overpass is a free shared service, so this runs one request per band with a
 * pause between them. Re-run only when the data should change.
 */
import { writeFileSync, readFileSync } from "node:fs";

const ENDPOINT = "https://overpass-api.de/api/interpreter";
const HEADERS = {
  "Content-Type": "application/x-www-form-urlencoded",
  "User-Agent": "singapore-canvas/0.1 (hackathon prototype; https://github.com/nickolaschua/palantirmaxxing)",
  Accept: "application/json",
};
// Matches SINGAPORE_BOUNDS in src/lib/types.ts.
const BOUNDS = { west: 103.56, south: 1.13, east: 104.14, north: 1.52 };
const BANDS = 3;
const PAUSE_MS = 3000;
/** Same carriageway classes as roads.json. */
const ROAD_CLASSES = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link";
const RAIL_CLASSES = "subway|light_rail|monorail";
/** Degrees. ~11 m for areas, ~9 m for the shorter structure lines. */
const AREA_EPSILON = 0.0001;
const LINE_EPSILON = 0.00008;
/** Square metres. Drops slivers that cost bytes and never read on screen. */
const MIN_AREA_M2 = 3000;

const LAYERS = {
  forest: box => `way["natural"="wood"]${box};rel["natural"="wood"]${box};
    way["landuse"="forest"]${box};rel["landuse"="forest"]${box};
    way["leisure"="nature_reserve"]${box};rel["leisure"="nature_reserve"]${box};
    way["natural"="wetland"]["wetland"="mangrove"]${box};rel["natural"="wetland"]["wetland"="mangrove"]${box};`,
  park: box => `way["leisure"="park"]${box};rel["leisure"="park"]${box};
    way["landuse"="grass"]${box};rel["landuse"="grass"]${box};
    way["leisure"="golf_course"]${box};rel["leisure"="golf_course"]${box};`,
  // "tunnel" also tags a road passing under a building, which is not a tunnel here.
  road: box => `way["highway"~"^(${ROAD_CLASSES})$"]["bridge"]["bridge"!="no"]${box};
    way["highway"~"^(${ROAD_CLASSES})$"]["tunnel"]["tunnel"!~"^(no|building_passage|covered)$"]${box};`,
  rail: box => `way["railway"~"^(${RAIL_CLASSES})$"]["bridge"]["bridge"!="no"]${box};
    way["railway"~"^(${RAIL_CLASSES})$"]["tunnel"]["tunnel"!~"^(no|building_passage|covered)$"]${box};`,
  // Bases only: ranges, danger areas and training areas are not installations.
  military: box => `way["landuse"="military"]${box};rel["landuse"="military"]${box};
    way["military"~"^(base|barracks|airfield|naval_base)$"]${box};rel["military"~"^(base|barracks|airfield|naval_base)$"]${box};`,
};
const AREAS = new Set(["forest", "park", "military"]);
/** Layers whose features keep their OSM name. */
const NAMED = new Set(["military"]);

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function overpass(query) {
  for (let attempt = 1; ; attempt++) {
    const response = await fetch(ENDPOINT, { method: "POST", headers: HEADERS, body: `data=${encodeURIComponent(query)}` });
    if (response.ok) return response.json();
    if (attempt === 3 || ![429, 502, 503, 504].includes(response.status)) {
      throw new Error(`Overpass ${response.status}: ${(await response.text()).slice(0, 200)}`);
    }
    const wait = attempt * 20_000;
    console.warn(`  Overpass ${response.status}, retrying in ${wait / 1000}s`);
    await sleep(wait);
  }
}

/**
 * Joins a relation's outer member ways end to end into closed rings. A way that
 * closes nothing is kept as it is, which is what the old per-member output was.
 */
function assembleRings(ways) {
  const key = p => `${p.lon},${p.lat}`;
  const pool = ways.map(w => [...w]);
  const rings = [];
  while (pool.length) {
    let ring = pool.shift();
    while (key(ring[0]) !== key(ring.at(-1))) {
      const end = key(ring.at(-1));
      const i = pool.findIndex(w => key(w[0]) === end || key(w.at(-1)) === end);
      if (i < 0) break;
      const [w] = pool.splice(i, 1);
      ring = ring.concat((key(w[0]) === end ? w : [...w].reverse()).slice(1));
    }
    rings.push(ring);
  }
  return rings;
}

/** Ways carry geometry directly; relations carry it per member, outer rings only. */
function* geometries(elements) {
  for (const element of elements) {
    const name = element.tags?.name ?? null;
    if (element.type === "way" && element.geometry) yield { points: element.geometry, name };
    if (element.type === "relation") {
      const outers = (element.members ?? [])
        .filter(m => m.type === "way" && m.geometry && (m.role === "outer" || m.role === ""))
        .map(m => m.geometry);
      for (const points of assembleRings(outers)) yield { points, name };
    }
  }
}

const M_PER_DEG_LAT = 110_574;
const mPerDegLon = lat => 111_320 * Math.cos((lat * Math.PI) / 180);

/** Shoelace area in square metres, treating the ring as flat. Good enough to drop slivers. */
function areaM2(points) {
  let twice = 0;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const a = points[j], b = points[i];
    twice += (a.lon * b.lat - b.lon * a.lat);
  }
  const mid = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
  return Math.abs(twice / 2) * M_PER_DEG_LAT * mPerDegLon(mid);
}

function centroid(points) {
  const lon = points.reduce((sum, p) => sum + p.lon, 0) / points.length;
  const lat = points.reduce((sum, p) => sum + p.lat, 0) / points.length;
  return { lon, lat };
}

/** Ray casting against the flat [lon, lat, …] rings in coastline.json. */
function inside(point, rings) {
  for (const ring of rings) {
    let hit = false;
    for (let i = 0, j = ring.length - 2; i < ring.length; j = i, i += 2) {
      const xi = ring[i], yi = ring[i + 1], xj = ring[j], yj = ring[j + 1];
      if ((yi > point.lat) !== (yj > point.lat) && point.lon < ((xj - xi) * (point.lat - yi)) / (yj - yi) + xi) hit = !hit;
    }
    if (hit) return true;
  }
  return false;
}

/** Douglas-Peucker in degrees. */
function simplify(points, epsilon) {
  if (points.length < 3) return points;
  let index = 0;
  let farthest = 0;
  const [first] = points;
  const last = points[points.length - 1];
  const dx = last.lon - first.lon;
  const dy = last.lat - first.lat;
  const length = Math.hypot(dx, dy);
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i];
    const distance = length === 0
      ? Math.hypot(p.lon - first.lon, p.lat - first.lat)
      : Math.abs(dy * p.lon - dx * p.lat + last.lon * first.lat - last.lat * first.lon) / length;
    if (distance > farthest) { farthest = distance; index = i; }
  }
  if (farthest <= epsilon) return [first, last];
  return [...simplify(points.slice(0, index + 1), epsilon).slice(0, -1), ...simplify(points.slice(index), epsilon)];
}

/** Integers of degrees * 1e5, delta-encoded after the first point. */
function encode(points) {
  const out = [];
  let px = 0;
  let py = 0;
  for (const [i, p] of points.entries()) {
    const x = Math.round(p.lon * 1e5);
    const y = Math.round(p.lat * 1e5);
    if (i === 0) out.push(x, y);
    else if (x !== px || y !== py) out.push(x - px, y - py);
    px = x;
    py = y;
  }
  return out;
}

const land = JSON.parse(readFileSync(new URL("../src/lib/coastline.json", import.meta.url), "utf8"));

async function collect(name) {
  const isArea = AREAS.has(name);
  const seen = new Set();
  const out = [];
  let dropped = 0;
  for (let band = 0; band < BANDS; band++) {
    const south = BOUNDS.south + ((BOUNDS.north - BOUNDS.south) * band) / BANDS;
    const north = BOUNDS.south + ((BOUNDS.north - BOUNDS.south) * (band + 1)) / BANDS;
    const box = `(${south},${BOUNDS.west},${north},${BOUNDS.east})`;
    const data = await overpass(`[out:json][timeout:180];(${LAYERS[name](box)});out geom;`);
    for (const { points: geometry, name: featureName } of geometries(data.elements)) {
      const points = geometry.filter(p => Number.isFinite(p.lon) && Number.isFinite(p.lat));
      if (points.length < (isArea ? 4 : 2)) continue;
      const key = `${points[0].lon},${points[0].lat},${points.length},${points.at(-1).lon}`;
      if (seen.has(key)) continue; // bands overlap at their edges
      seen.add(key);
      if (isArea && areaM2(points) < MIN_AREA_M2) { dropped++; continue; }
      if (!inside(centroid(points), land)) { dropped++; continue; } // keeps Johor and Batam out
      const simplified = simplify(points, isArea ? AREA_EPSILON : LINE_EPSILON);
      if (simplified.length < (isArea ? 4 : 2)) continue;
      out.push(NAMED.has(name) ? { name: featureName, ring: encode(simplified) } : encode(simplified));
    }
    console.log(`  ${name} band ${band + 1}/${BANDS}: ${data.elements.length} elements, ${out.length} kept`);
    if (band < BANDS - 1) await sleep(PAUSE_MS);
  }
  console.log(`${name}: ${out.length} features, ${dropped} dropped (small or outside Singapore)`);
  return out;
}

const wanted = new Set(process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(LAYERS));
for (const name of wanted) if (!LAYERS[name]) throw new Error(`Unknown layer "${name}"`);

/** Refreshes only the named layers; the rest keeps whatever the file already holds. */
async function build(file, names, dir = "lib") {
  const url = new URL(`../src/${dir}/${file}`, import.meta.url);
  let current = {};
  try { current = JSON.parse(readFileSync(url, "utf8")); } catch { /* first run */ }
  const out = { ...current };
  for (const name of names) if (wanted.has(name)) out[name] = await collect(name);
  writeFileSync(url, JSON.stringify(out));
  return out;
}

const greens = await build("greens.json", ["forest", "park"]);
const structures = await build("structures.json", ["road", "rail"]);
const military = await build("military.json", ["military"], "demo");

for (const [file, data] of [["greens.json", greens], ["structures.json", structures], ["military.json", military]]) {
  const points = Object.values(data).flat().reduce((sum, line) => sum + (line.ring ?? line).length / 2, 0);
  console.log(`${file}: ${points.toLocaleString("en-SG")} points`);
}
