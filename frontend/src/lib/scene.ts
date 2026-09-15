import {
  Cesium3DTileset,
  EllipsoidTerrainProvider,
  JulianDate,
  Viewer,
  createGooglePhotorealistic3DTileset,
  createWorldTerrainAsync,
} from "cesium";
import { addGround, singaporeClip, SEA_BLUE } from "./coastline.js";
import type { Ground } from "./coastline.js";
import type { BasemapKind, LightingPreset } from "./types.js";

/** Cesium ion asset id for Cesium OSM Buildings. */
const OSM_BUILDINGS_ASSET = 96188;

export interface SceneModule {
  setBasemap(kind: BasemapKind): Promise<void>;
  setLighting(preset: LightingPreset): void;
  readonly basemap: BasemapKind;
}

export interface SceneInternals {
  module: SceneModule;
  /** The active city tileset, or null. Layers needs this for clip regions. */
  tileset(): Cesium3DTileset | null;
  requireGlobe(required: boolean): void;
  destroy(): void;
}

export async function createScene(
  viewer: Viewer,
  initial: BasemapKind,
  lighting: LightingPreset,
): Promise<SceneInternals> {
  let current: BasemapKind = initial;
  let tileset: Cesium3DTileset | null = null;
  let ground: Ground | null = null;
  let globeRequired = false;

  function clearTileset(): void {
    if (!tileset) return;
    // primitives.remove destroys the primitive, which releases its tile cache.
    viewer.scene.primitives.remove(tileset);
    tileset = null;
  }

  async function load(kind: BasemapKind): Promise<void> {
    // Acquire before swapping so a failed remote request preserves the current map.
    let next: Cesium3DTileset | null = null;
    let terrain = viewer.terrainProvider;
    if (kind === "photorealistic") {
      next = await createGooglePhotorealistic3DTileset({ onlyUsingWithGoogleGeocoder: true });
    } else if (kind === "extruded") {
      terrain = await createWorldTerrainAsync();
      next = await Cesium3DTileset.fromIonAssetId(OSM_BUILDINGS_ASSET);
    } else {
      terrain = new EllipsoidTerrainProvider();
    }
    if (next) next.clippingPolygons = singaporeClip();
    clearTileset();
    tileset = next;
    if (next) viewer.scene.primitives.add(next);
    viewer.terrainProvider = terrain;
    viewer.imageryLayers.removeAll();
    viewer.scene.globe.baseColor = SEA_BLUE;
    current = kind;
    viewer.scene.globe.show = kind !== "photorealistic" || globeRequired;
    ground?.setVisible(kind !== "photorealistic" && !globeRequired);
  }

  function setLighting(preset: LightingPreset): void {
    const { scene, clock } = viewer;
    scene.globe.enableLighting = true;
    if (scene.skyAtmosphere) scene.skyAtmosphere.show = true;
    scene.highDynamicRange = true;

    // Singapore is UTC+8. Step 9 tunes these properly; for now they just differ.
    if (preset === "midday") {
      clock.currentTime = JulianDate.fromIso8601("2026-03-15T04:30:00Z");
      scene.fog.enabled = true;
      scene.globe.translucency.enabled = false;
    } else {
      clock.currentTime = JulianDate.fromIso8601("2026-03-15T11:20:00Z");
      scene.fog.enabled = true;
      scene.globe.translucency.enabled = false;
    }
  }

  ground = addGround(viewer);
  await load(initial);
  setLighting(lighting);

  return {
    module: {
      setBasemap: load,
      setLighting,
      get basemap() {
        return current;
      },
    },
    tileset: () => tileset,
    requireGlobe(required) {
      globeRequired = required;
      ground?.setVisible(current !== "photorealistic" && !required);
      viewer.scene.globe.show = current !== "photorealistic" || required;
    },
    destroy(): void {
      clearTileset();
      ground?.destroy();
      ground = null;
    },
  };
}
