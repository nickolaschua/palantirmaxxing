import { test } from "node:test";
import assert from "node:assert/strict";
import { colorOf, parseDataset, rankZones, selectZones, UNKNOWN_COLOR, valueOf } from "../../frontend/src/demo/population-model.ts";
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
