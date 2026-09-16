import { test } from "node:test";
import assert from "node:assert/strict";
import { colorOf, labelPoint, parseDataset, planningAreaLabelPoints, rankZones, selectZones, UNKNOWN_COLOR, valueOf } from "../../frontend/src/demo/population-model.ts";
import type { PopulationData, Zone } from "../../frontend/src/demo/population-model.ts";

const zone = (id: string, area: string, population: number | null, density: number | null): Zone => ({
  type: "Feature", id, geometry: { type: "Polygon", coordinates: [] },
  properties: { zone_id: id, planning_area: area, subzone: id, population,
    population_density_people_per_m2: density, population_status: population === null ? "missing" : "known",
    population_raw: population === null ? null : String(population), zone_area_m2: 1_000_000,
    geometry_status: "valid", pec_eligible: population !== null, exclusion_reasons: [], outside_viewer_bounds: false, dataset_version: "test" },
});
const data = { type: "FeatureCollection", metadata: { dataset_version: "test", population_year: 2020, boundary_vintage: 2019, coverage: {} },
  features: [zone("A", "NORTH", 10000, .002), zone("B", "SOUTH", 0, 0), zone("C", "NORTH", null, null), zone("D", "NORTH", 5000, .005)] } as PopulationData;

test("filter and ranked chart use the same selection; unknown excluded, zero retained", () => {
  const selected = selectZones(data, "", "NORTH");
  assert.deepEqual(rankZones(selected,"population").map(z=>z.id),["A","D"]);
  assert.deepEqual(rankZones(selected,"density").map(z=>z.id),["D","A"]);
  assert.equal(rankZones(data.features,"population").at(-1)?.id,"B");
  assert.deepEqual(selectZones(data," c ","").map(z=>z.id),["C"]);
  assert.deepEqual(selectZones(data,"nothing",""),[]);
});
test("density conversion and stable colors", () => {
  assert.equal(valueOf(data.features[0]!,"density"),2000);
  assert.equal(colorOf(data.features[2]!,"population"),UNKNOWN_COLOR);
  const before=colorOf(data.features[0]!,"population");
  assert.equal(colorOf(selectZones(data,"A","")[0]!,"population"),before);
  assert.notEqual(colorOf(data.features[1]!,"population"),UNKNOWN_COLOR);
});
test("payload validation rejects wrong vintage, duplicate IDs and non-finite values", () => {
  assert.equal(parseDataset(data),data);
  assert.throws(()=>parseDataset({...data,metadata:{...data.metadata,population_year:2021}}));
  assert.throws(()=>parseDataset({...data,features:[data.features[0],data.features[0]]}));
  assert.throws(()=>parseDataset({...data,features:[zone("X","A",NaN,0)]}));
});
test("label anchors: largest part's centroid, planning areas weighted by zone area", () => {
  const square = (x: number, y: number, side: number) => [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]];
  const shaped = (id: string, area: string, geometry: Zone["geometry"]): Zone => ({ ...zone(id, area, 1, 1), geometry });
  const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);
  const single = labelPoint(shaped("S", "P", { type: "Polygon", coordinates: square(103.8, 1.3, 0.02) }));
  near(single.lon, 103.81); near(single.lat, 1.31); near(single.weight, 0.0004);
  const multi = labelPoint(shaped("M", "P", { type: "MultiPolygon", coordinates: [square(10, 10, 1), square(0, 0, 2)] }));
  near(multi.lon, 1); near(multi.lat, 1); near(multi.weight, 5);
  const [area] = planningAreaLabelPoints([
    shaped("A", "EAST", { type: "Polygon", coordinates: square(0, 0, 2) }),
    shaped("B", "EAST", { type: "Polygon", coordinates: square(4, 0, 2) }),
  ]);
  assert.equal(area?.name, "EAST"); near(area!.lon, 3); near(area!.lat, 1);
});
