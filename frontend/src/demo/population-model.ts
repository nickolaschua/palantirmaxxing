/** Presentation selectors only. All population/area/density values are prepared offline. */
export type Metric = "population" | "density";
export interface ZoneProperties {
  zone_id: string; planning_area: string; subzone: string;
  population: number | null; population_status: string; population_raw: string | null;
  zone_area_m2: number | null; population_density_people_per_m2: number | null;
  geometry_status: string; pec_eligible: boolean; exclusion_reasons: string[];
  outside_viewer_bounds: boolean; dataset_version: string;
}
export interface Zone {
  type: "Feature"; id: string; properties: ZoneProperties;
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
}
export interface PopulationData {
  type: "FeatureCollection"; features: Zone[];
  metadata: {
    dataset_version: string; population_year: number; boundary_vintage: number; retrieved_at: string;
    retrieval_meaning: string;
    coverage: { status: string; counts: { eligible: number; excluded: number; unknown_population: number } };
  };
}
export const COLORS = ["#edf8fb", "#b3cde3", "#8c96c6", "#8856a7", "#810f7c"];
export const UNKNOWN_COLOR = "#909ba5";
export const BREAKS: Record<Metric, number[]> = {
  population: [1000, 10000, 20000, 40000], density: [1000, 5000, 10000, 20000],
};
export const units = (metric: Metric): string => metric === "population" ? "people" : "people/km²";
export const valueOf = (zone: Zone, metric: Metric): number | null => metric === "population"
  ? zone.properties.population
  : zone.properties.population_density_people_per_m2 === null ? null : zone.properties.population_density_people_per_m2 * 1_000_000;
export function colorOf(zone: Zone, metric: Metric): string {
  const value = valueOf(zone, metric);
  if (value === null) return UNKNOWN_COLOR;
  return COLORS[BREAKS[metric].filter(limit => value >= limit).length] ?? UNKNOWN_COLOR;
}
export function selectZones(data: PopulationData, search: string, planningArea: string): Zone[] {
  const query = search.trim().toLocaleLowerCase();
  return data.features.filter(({ properties: p }) => (!planningArea || p.planning_area === planningArea)
    && (!query || `${p.planning_area} ${p.subzone} ${p.zone_id}`.toLocaleLowerCase().includes(query)));
}
export function rankZones(zones: Zone[], metric: Metric): Zone[] {
  return zones.filter(z => valueOf(z, metric) !== null).sort((a, b) =>
    (valueOf(b, metric) ?? 0) - (valueOf(a, metric) ?? 0) || a.id.localeCompare(b.id));
}
export function parseDataset(value: unknown): PopulationData {
  const data = value as PopulationData;
  if (data?.type !== "FeatureCollection" || !Array.isArray(data.features)
    || data.metadata?.population_year !== 2020 || data.metadata.boundary_vintage !== 2019
    || !data.metadata.dataset_version || !data.metadata.coverage) throw new Error("Unexpected population dataset/version. Run the preparation command.");
  const ids = new Set<string>();
  for (const zone of data.features) {
    const p = zone.properties;
    if (!p || zone.id !== p.zone_id || ids.has(zone.id) || typeof p.planning_area !== "string" || typeof p.subzone !== "string"
      || !["Polygon", "MultiPolygon"].includes(zone.geometry?.type)
      || p.dataset_version !== data.metadata.dataset_version
      || [p.population, p.zone_area_m2, p.population_density_people_per_m2].some(n => n !== null && (typeof n !== "number" || !Number.isFinite(n) || n < 0))) {
      throw new Error("Invalid population payload. Inspect the preparation validation report.");
    }
    ids.add(zone.id);
  }
  return data;
}
