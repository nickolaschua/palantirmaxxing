import type { MultiThreatComparisonResult, OutcomeMetric, RangeValue, ThreatComparison } from "./comparison-contract.js";

const metrics = (
  exposed: RangeValue,
  fatalities: RangeValue,
  service: RangeValue,
  recovery: RangeValue,
  delay: RangeValue,
): readonly OutcomeMetric[] => [
  { id: "exposed", label: "People potentially exposed", unit: "people", ...exposed },
  { id: "fatalities", label: "Estimated fatalities", unit: "people", ...fatalities },
  { id: "service", label: "Service disruption", unit: "person-hours", ...service },
  { id: "recovery", label: "Time to 90% function", unit: "days", ...recovery },
  { id: "delay", label: "Simulated response delay", unit: "minutes", ...delay },
];

/**
 * Fictional presentation fixture. Values demonstrate the UI contract only and
 * are not estimates for real Singapore locations, systems, or capabilities.
 */
export const SYNTHETIC_THREATS: readonly ThreatComparison[] = [
  {
    id: "synthetic-threat-01",
    displayId: "M-01",
    condition: "Weekday night - normal system state",
    samples: [
      { seconds: 0, lon: 103.67, lat: 1.39, height: 8500 },
      { seconds: 5, lon: 103.73, lat: 1.37, height: 7200 },
      { seconds: 10, lon: 103.79, lat: 1.35, height: 5600 },
      { seconds: 15, lon: 103.85, lat: 1.33, height: 3800 },
      { seconds: 20, lon: 103.91, lat: 1.31, height: 1800 },
    ],
    baseline: {
      policyLabel: "Baseline - earliest feasible",
      policyDetail: "Selects the first feasible candidate without using the consequence vector.",
      position: { lon: 103.79, lat: 1.35, height: 5600 },
      timeFromStartS: 10,
      successProbability: 0.94,
      metrics: metrics(
        { low: 8900, central: 10400, high: 12100 },
        { low: 21, central: 28, high: 35 },
        { low: 690000, central: 830000, high: 1010000 },
        { low: 12, central: 15, high: 19 },
        { low: 3, central: 5, high: 8 },
      ),
      vector: {
        H: { low: 72, central: 78, high: 84 }, E: { low: 57, central: 64, high: 72 },
        D: { low: 28, central: 35, high: 44 }, X: { low: 49, central: 58, high: 69 },
        R: { low: 64, central: 72, high: 80 }, A: { low: 32, central: 40, high: 49 },
      },
      categories: [
        { label: "Residential", contribution: 41, mechanism: "Night-time occupancy exposure" },
        { label: "Water and drainage", contribution: 24, mechanism: "Downstream service interruption" },
        { label: "Transport", contribution: 17, mechanism: "Network access disruption" },
      ],
      sourcedPercent: 82,
      assumedPercent: 18,
    },
    optimised: {
      policyLabel: "Optimised - consequence-aware v1",
      policyDetail: "Selects the feasible candidate with the lowest supplied consequence result.",
      position: { lon: 103.86, lat: 1.327, height: 3500 },
      timeFromStartS: 15.8,
      successProbability: 0.922,
      metrics: metrics(
        { low: 3200, central: 4000, high: 4900 },
        { low: 7, central: 10, high: 14 },
        { low: 180000, central: 240000, high: 330000 },
        { low: 3, central: 5, high: 7 },
        { low: 4, central: 7, high: 10 },
      ),
      vector: {
        H: { low: 36, central: 42, high: 50 }, E: { low: 25, central: 31, high: 39 },
        D: { low: 34, central: 41, high: 50 }, X: { low: 18, central: 24, high: 32 },
        R: { low: 29, central: 36, high: 44 }, A: { low: 13, central: 18, high: 25 },
      },
      categories: [
        { label: "Residential", contribution: 23, mechanism: "Lower estimated occupancy" },
        { label: "Transport", contribution: 15, mechanism: "Local route disruption" },
        { label: "Green and recreation", contribution: 9, mechanism: "Open-area exposure" },
      ],
      sourcedPercent: 82,
      assumedPercent: 18,
    },
    reasons: [
      "Reduces simulated population exposure by 6,400 people.",
      "Avoids the largest water-service dependency in this scenario.",
      "Lowers cascading consequence X from 58 to 24.",
    ],
    tradeoffs: [
      "Capability-continuity score D increases from 35 to 41.",
      "Intercept occurs 5.8 seconds later with 1.8 percentage points lower supplied success.",
    ],
    robustnessPercent: 89,
    simulationCount: 50000,
  },
  {
    id: "synthetic-threat-02",
    displayId: "M-02",
    condition: "Weekday morning peak - reduced transport capacity",
    samples: [
      { seconds: 0, lon: 104.02, lat: 1.46, height: 9000 },
      { seconds: 5, lon: 103.98, lat: 1.42, height: 7600 },
      { seconds: 10, lon: 103.94, lat: 1.38, height: 6100 },
      { seconds: 15, lon: 103.90, lat: 1.34, height: 4200 },
      { seconds: 20, lon: 103.86, lat: 1.30, height: 2100 },
    ],
    baseline: {
      policyLabel: "Baseline - earliest feasible",
      policyDetail: "Selects the first feasible candidate without using the consequence vector.",
      position: { lon: 103.94, lat: 1.38, height: 6100 }, timeFromStartS: 10, successProbability: 0.95,
      metrics: metrics(
        { low: 14800, central: 17200, high: 20600 }, { low: 30, central: 41, high: 55 },
        { low: 1200000, central: 1600000, high: 2300000 }, { low: 16, central: 24, high: 38 },
        { low: 8, central: 13, high: 21 },
      ),
      vector: {
        H: { low: 78, central: 84, high: 91 }, E: { low: 70, central: 79, high: 90 },
        D: { low: 61, central: 70, high: 82 }, X: { low: 67, central: 76, high: 88 },
        R: { low: 70, central: 81, high: 92 }, A: { low: 21, central: 29, high: 38 },
      },
      categories: [
        { label: "Aviation", contribution: 38, mechanism: "Operational continuity" },
        { label: "Transport", contribution: 31, mechanism: "Morning network demand" },
        { label: "Commercial and civic", contribution: 19, mechanism: "Workplace occupancy" },
      ], sourcedPercent: 76, assumedPercent: 24,
    },
    optimised: {
      policyLabel: "Optimised - consequence-aware v1",
      policyDetail: "Selects the feasible candidate with the lowest supplied consequence result.",
      position: { lon: 103.889, lat: 1.329, height: 3700 }, timeFromStartS: 16.4, successProbability: 0.918,
      metrics: metrics(
        { low: 5700, central: 6900, high: 8400 }, { low: 12, central: 17, high: 24 },
        { low: 410000, central: 560000, high: 790000 }, { low: 6, central: 9, high: 14 },
        { low: 3, central: 6, high: 9 },
      ),
      vector: {
        H: { low: 49, central: 56, high: 65 }, E: { low: 39, central: 47, high: 57 },
        D: { low: 30, central: 38, high: 48 }, X: { low: 34, central: 42, high: 52 },
        R: { low: 39, central: 48, high: 59 }, A: { low: 26, central: 34, high: 43 },
      },
      categories: [
        { label: "Transport", contribution: 26, mechanism: "Reduced alternative capacity" },
        { label: "Commercial and civic", contribution: 17, mechanism: "Workplace occupancy" },
        { label: "Industrial and logistics", contribution: 12, mechanism: "Supply interruption" },
      ], sourcedPercent: 76, assumedPercent: 24,
    },
    reasons: [
      "Reduces simulated exposure by 10,300 people.",
      "Preserves the scenario's aviation continuity threshold.",
      "Cuts essential-service and cascading scores by more than 30 points.",
    ],
    tradeoffs: [
      "Additional-hazard score A increases from 29 to 34.",
      "Intercept occurs 6.4 seconds later with 3.2 percentage points lower supplied success.",
    ],
    robustnessPercent: 86, simulationCount: 50000,
  },
  {
    id: "synthetic-threat-03",
    displayId: "M-03",
    condition: "Weekend afternoon - recreation event active",
    samples: [
      { seconds: 0, lon: 103.78, lat: 1.17, height: 8200 },
      { seconds: 5, lon: 103.80, lat: 1.22, height: 7000 },
      { seconds: 10, lon: 103.82, lat: 1.27, height: 5500 },
      { seconds: 15, lon: 103.84, lat: 1.32, height: 3600 },
      { seconds: 20, lon: 103.86, lat: 1.37, height: 1700 },
    ],
    baseline: {
      policyLabel: "Baseline - earliest feasible",
      policyDetail: "Selects the first feasible candidate without using the consequence vector.",
      position: { lon: 103.82, lat: 1.27, height: 5500 }, timeFromStartS: 10, successProbability: 0.945,
      metrics: metrics(
        { low: 6200, central: 7800, high: 9900 }, { low: 14, central: 20, high: 29 },
        { low: 330000, central: 480000, high: 710000 }, { low: 10, central: 17, high: 29 },
        { low: 2, central: 4, high: 7 },
      ),
      vector: {
        H: { low: 57, central: 65, high: 75 }, E: { low: 38, central: 47, high: 58 },
        D: { low: 20, central: 27, high: 36 }, X: { low: 43, central: 53, high: 65 },
        R: { low: 52, central: 63, high: 76 }, A: { low: 71, central: 82, high: 93 },
      },
      categories: [
        { label: "Industrial and logistics", contribution: 37, mechanism: "Hazard inventory band" },
        { label: "Port and maritime", contribution: 22, mechanism: "Logistics interruption" },
        { label: "Green and recreation", contribution: 18, mechanism: "Weekend event occupancy" },
      ], sourcedPercent: 69, assumedPercent: 31,
    },
    optimised: {
      policyLabel: "Optimised - consequence-aware v1",
      policyDetail: "Selects the feasible candidate with the lowest supplied consequence result.",
      position: { lon: 103.847, lat: 1.338, height: 3000 }, timeFromStartS: 16.8, successProbability: 0.911,
      metrics: metrics(
        { low: 2500, central: 3300, high: 4300 }, { low: 5, central: 8, high: 12 },
        { low: 160000, central: 230000, high: 350000 }, { low: 4, central: 7, high: 11 },
        { low: 3, central: 5, high: 8 },
      ),
      vector: {
        H: { low: 33, central: 40, high: 48 }, E: { low: 25, central: 32, high: 41 },
        D: { low: 22, central: 29, high: 38 }, X: { low: 23, central: 30, high: 39 },
        R: { low: 31, central: 39, high: 49 }, A: { low: 25, central: 33, high: 43 },
      },
      categories: [
        { label: "Green and recreation", contribution: 21, mechanism: "Event occupancy" },
        { label: "Transport", contribution: 14, mechanism: "Access disruption" },
        { label: "Commercial and civic", contribution: 10, mechanism: "Visitor displacement" },
      ], sourcedPercent: 69, assumedPercent: 31,
    },
    reasons: [
      "Moves away from the scenario's high additional-hazard band.",
      "Reduces estimated exposure by 4,500 people.",
      "Shortens central functional recovery from 17 to 7 days.",
    ],
    tradeoffs: [
      "Capability-continuity score D increases from 27 to 29.",
      "Intercept occurs 6.8 seconds later with 3.4 percentage points lower supplied success.",
    ],
    robustnessPercent: 91, simulationCount: 50000,
  },
];

export const DEMO_COMPARISON_RESULT: MultiThreatComparisonResult = {
  schemaVersion: "multi-threat-comparison/1",
  scenarioId: "synthetic-singapore-multi-threat-demo",
  generatedAt: "2026-09-25T12:00:00+08:00",
  dataMode: "fixture",
  start: "2026-09-25T06:00:00+08:00",
  scorePolicy: {
    id: "research-balanced-v1",
    version: "1",
    weights: { H: 0.30, E: 0.18, D: 0.20, X: 0.12, R: 0.10, A: 0.10 },
  },
  threats: SYNTHETIC_THREATS,
  provenance: {
    sourceIds: ["frontend-synthetic-fixture-v1"],
    limitations: [
      "All values are fictional and demonstrate the frontend contract only.",
      "Aggregate totals do not deduplicate overlapping people or service effects.",
    ],
  },
};
