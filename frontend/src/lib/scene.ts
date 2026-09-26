import {
  Cartesian3,
  Cesium3DTileset,
  Color,
  DirectionalLight,
  EllipsoidTerrainProvider,
  JulianDate,
  Matrix4,
  PostProcessStage,
  SunLight,
  Transforms,
  Viewer,
  createGooglePhotorealistic3DTileset,
  createWorldTerrainAsync,
} from "cesium";
import { addGround, singaporeClip, SEA_GREY } from "./coastline.js";
import type { Ground } from "./coastline.js";
import type { BasemapKind, LightingPreset } from "./types.js";

/** Cesium ion asset id for Cesium OSM Buildings. */
const OSM_BUILDINGS_ASSET = 96188;

/**
 * The ground layer is drawn in flat colours that Cesium does not light, so a sun
 * change alone barely touches the grey canvas. This grades the finished frame
 * instead, which moves ground, buildings and Google tiles together.
 */
const GRADE_SHADER = `
uniform sampler2D colorTexture;
uniform vec3 tint;
uniform float brightness;
in vec2 v_textureCoordinates;
void main() {
  vec4 color = texture(colorTexture, v_textureCoordinates);
  out_FragColor = vec4(color.rgb * tint * brightness, color.a);
}`;

export interface SceneModule {
  setBasemap(kind: BasemapKind): Promise<void>;
  setLighting(preset: LightingPreset): void;
  readonly basemap: BasemapKind;
}

export interface SceneInternals {
  module: SceneModule;
  /** The active city tileset, or null. Layers needs this for clip regions. */
  tileset(): Cesium3DTileset | null;
  /** Calls `listener` now with the current city tileset, and again whenever it is swapped. */
  onTileset(listener: (tileset: Cesium3DTileset | null) => void): () => void;
  requireGlobe(required: boolean): void;
  destroy(): void;
}

/** Camera height below which roads draw (see coastline.ts), and with them full building detail. */
const DETAIL_BELOW_M = 20_000;
/** Cesium3DTileset's own default. */
const DEFAULT_SSE = 16;

export async function createScene(
  viewer: Viewer,
  initial: BasemapKind,
  lighting: LightingPreset,
  setSunInstant: (instant: JulianDate) => void,
  maximumScreenSpaceError?: number,
): Promise<SceneInternals> {
  let current: BasemapKind = initial;
  let tileset: Cesium3DTileset | null = null;
  let ground: Ground | null = null;
  let globeRequired = false;
  const tilesetListeners = new Set<(tileset: Cesium3DTileset | null) => void>();

  const grade = viewer.scene.postProcessStages.add(new PostProcessStage({
    name: "singapore-canvas-grade",
    fragmentShader: GRADE_SHADER,
    uniforms: { tint: new Cartesian3(1, 1, 1), brightness: 1 },
  })) as PostProcessStage;

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
      // No building outlines. Cesium 1.145 generates them by rewriting each
      // tile's index array in place, and that array is a view onto bytes the
      // module-level ResourceCache shares between scenes. With two canvases
      // loading the same tile, the second sees already-rewritten indices and
      // draws stretched triangles over its whole view (CesiumGS/cesium#11484).
      // Tile cache capped at 256 + 128 MB (Cesium's default is 512 + 512).
      next = await Cesium3DTileset.fromIonAssetId(OSM_BUILDINGS_ASSET, {
        enableShowOutline: false, cacheBytes: 256 * 1024 * 1024, maximumCacheOverflowBytes: 128 * 1024 * 1024,
      });
    } else {
      terrain = new EllipsoidTerrainProvider();
    }
    if (next) {
      next.clippingPolygons = singaporeClip();
      // Cesium 1.145 queues environment-map compute commands in one module-level
      // queue shared by every Scene, so with two canvases on a page one context
      // runs the other's commands: WebGL cross-context errors and corrupted
      // ground. Off, tilesets use Cesium's fallback diffuse lighting.
      next.environmentMapManager.enabled = false;
    }
    clearTileset();
    tileset = next;
    if (next) viewer.scene.primitives.add(next);
    applyDetail();
    for (const listener of tilesetListeners) listener(tileset);
    viewer.terrainProvider = terrain;
    viewer.scene.globe.baseColor = SEA_GREY;
    current = kind;
    viewer.scene.highDynamicRange = kind === "photorealistic"; // see setLighting
    viewer.scene.globe.show = kind !== "photorealistic" || globeRequired;
    ground?.setVisible(kind !== "photorealistic" && !globeRequired);
    viewer.scene.requestRender();
  }

  /**
   * Two looks for the same city. Singapore is UTC+8, so the sun instants below
   * are 12:30 and 19:20 local. Every value is set in both branches, so switching
   * back and forth always lands in the same place.
   *
   * Tilesets read `scene.light` for their direct light. Cesium's dynamic
   * environment map, which would otherwise add sky bounce, is off — see `load`.
   */
  function setLighting(preset: LightingPreset): void {
    const { scene, scene: { globe, skyAtmosphere, fog } } = viewer;
    globe.enableLighting = true;
    globe.dynamicAtmosphereLighting = true;
    globe.dynamicAtmosphereLightingFromSun = true;
    globe.showGroundAtmosphere = true;
    globe.translucency.enabled = false;
    if (skyAtmosphere) skyAtmosphere.show = true;
    // HDR for Google's tiles only. On the painted basemaps it would gamma-brighten the globe's base
    // colour (the sea: used as linear) but not the painted tiles (decoded from sRGB), then tone-map
    // everything darker, so the palette would not render as coded.
    scene.highDynamicRange = current === "photorealistic";
    fog.enabled = true;

    if (preset === "midday") {
      setSunInstant(JulianDate.fromIso8601("2026-03-15T04:30:00Z"));
      scene.light = new SunLight({ intensity: 2.4 });
      globe.lambertDiffuseMultiplier = 1;
      globe.atmosphereBrightnessShift = 0;
      globe.atmosphereSaturationShift = -0.1;
      globe.atmosphereLightIntensity = 10;
      if (skyAtmosphere) {
        skyAtmosphere.brightnessShift = 0;
        skyAtmosphere.saturationShift = -0.1;
        skyAtmosphere.hueShift = 0;
        skyAtmosphere.atmosphereLightIntensity = 50;
      }
      // Thin haze only: the city should read crisp from 6 km up.
      fog.density = 0.0002;
      fog.minimumBrightness = 0.12;
      grade.enabled = false;
    } else {
      setSunInstant(JulianDate.fromIso8601("2026-03-15T11:20:00Z"));
      // The sun is at the horizon, so a low cool key light keeps the city legible
      // instead of letting it fall to silhouette.
      const frame = Transforms.eastNorthUpToFixedFrame(Cartesian3.fromDegrees(103.82, 1.35));
      const direction = Matrix4.multiplyByPointAsVector(frame, new Cartesian3(0.72, 0.28, -0.63), new Cartesian3());
      scene.light = new DirectionalLight({
        direction: Cartesian3.normalize(direction, direction),
        color: Color.fromCssColorString("#b9ccff"),
        intensity: 1.6,
      });
      globe.lambertDiffuseMultiplier = 1.4;
      globe.atmosphereBrightnessShift = -0.22;
      globe.atmosphereSaturationShift = 0.18;
      globe.atmosphereLightIntensity = 6;
      if (skyAtmosphere) {
        skyAtmosphere.brightnessShift = -0.18;
        skyAtmosphere.saturationShift = 0.25;
        skyAtmosphere.hueShift = 0.02;
        skyAtmosphere.atmosphereLightIntensity = 28;
      }
      fog.density = 0.0006;
      fog.minimumBrightness = 0.03;
      grade.uniforms.tint = new Cartesian3(0.68, 0.79, 1.05);
      grade.uniforms.brightness = 0.52;
      grade.enabled = true;
    }
    scene.requestRender();
  }

  ground = addGround(viewer);
  // The finer building detail applies only once the camera is low enough for roads
  // to draw; above that Cesium's default keeps the zoomed-out view light.
  function applyDetail(): void {
    if (!tileset || maximumScreenSpaceError === undefined) return;
    const near = viewer.camera.positionCartographic.height < DETAIL_BELOW_M;
    const sse = near ? maximumScreenSpaceError : DEFAULT_SSE;
    if (tileset.maximumScreenSpaceError === sse) return;
    tileset.maximumScreenSpaceError = sse;
    viewer.scene.requestRender();
  }
  const offCameraDetail = [viewer.camera.changed, viewer.camera.moveEnd].map((e) => e.addEventListener(applyDetail));
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
    onTileset(listener) {
      tilesetListeners.add(listener);
      listener(tileset);
      return () => { tilesetListeners.delete(listener); };
    },
    requireGlobe(required) {
      globeRequired = required;
      ground?.setVisible(current !== "photorealistic" && !required);
      viewer.scene.globe.show = current !== "photorealistic" || required;
      viewer.scene.requestRender();
    },
    destroy(): void {
      for (const off of offCameraDetail) off();
      clearTileset();
      viewer.scene.postProcessStages.remove(grade);
      ground?.destroy();
      ground = null;
    },
  };
}
