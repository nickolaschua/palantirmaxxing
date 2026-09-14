import {
  Cesium3DTileset,
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

  function clearTileset(): void {
    if (!tileset) return;
    // primitives.remove destroys the primitive, which releases its tile cache.
    viewer.scene.primitives.remove(tileset);
    tileset = null;
  }

  async function load(kind: BasemapKind): Promise<void> {
    clearTileset();

    if (kind === "photorealistic") {
      tileset = await createGooglePhotorealistic3DTileset({
        onlyUsingWithGoogleGeocoder: true,
      });
      tileset.clippingPolygons = singaporeClip();
      viewer.scene.primitives.add(tileset);
      // Google tiles carry their own ground surface; the ellipsoid underneath
      // z-fights with them.
      viewer.scene.globe.show = false;
    } else {
      viewer.terrainProvider = await createWorldTerrainAsync();
      viewer.scene.globe.show = true;
      // Drop satellite imagery: the ground should read as the same material as
      // the buildings, not as a photo underneath them.
      viewer.imageryLayers.removeAll();
      // The globe paints everything unpainted, so its base colour is the open
      // sea. Land and inland water are drawn back on top by the ground layer.
      viewer.scene.globe.baseColor = SEA_BLUE;
      tileset = await Cesium3DTileset.fromIonAssetId(OSM_BUILDINGS_ASSET);
      // Cesium OSM Buildings is global — without this, Johor Bahru renders
      // across the strait.
      tileset.clippingPolygons = singaporeClip();
      viewer.scene.primitives.add(tileset);
    }

    // The ground drapes onto the globe, so it is only meaningful when the globe
    // is showing. Photorealistic tiles carry their own coast and water.
    ground?.setVisible(kind === "extruded");

    current = kind;
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
    destroy(): void {
      clearTileset();
      ground?.destroy();
      ground = null;
    },
  };
}
