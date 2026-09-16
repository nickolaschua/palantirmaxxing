import { GoogleMaps, Ion, Viewer } from "cesium";
import { createCamera } from "./camera.js";
import { createScene } from "./scene.js";
import { createTime } from "./time.js";
import { Emitter } from "./events.js";
import { addPolygonLayer } from "./polygons.js";
import type { PolygonLayer, PolygonCallbacks, PolygonLayerOptions } from "./polygons.js";
export type { PolygonLayer, PolygonLayerOptions, PolygonStyle } from "./polygons.js";
import { addLabels } from "./labels.js";
import type { LabelLayer } from "./labels.js";
export type { LabelLayer } from "./labels.js";
import { addBurst } from "./burst.js";
import type { BurstLayer } from "./burst.js";
export type { BurstLayer } from "./burst.js";
import { addBuildingTint } from "./tint.js";
import type { TintArea, TintLayer, TintStyle } from "./tint.js";
export type { TintArea, TintLayer, TintStyle } from "./tint.js";
import { addGroundCircles, addMarkers, addPath } from "./overlays.js";
import type { CircleCallbacks, CircleLayer, MarkerLayer, PathLayer, PathStyle } from "./overlays.js";
export type { CircleCallbacks, CircleLayer, CircleStyle, MarkerLayer, MarkerStyle, PathLayer, PathStyle } from "./overlays.js";
import { SINGAPORE_BOUNDS } from "./types.js";
import type { CameraModule } from "./camera.js";
import type { SceneModule } from "./scene.js";
import type { TimeModule } from "./time.js";
export type { TimeModule } from "./time.js";
import type { CanvasEvents, CanvasOptions, GeoPoint, TimedSample } from "./types.js";

export type {
  Bounds,
  BasemapKind,
  CameraOrientation,
  CameraPose,
  CanvasEvents,
  CanvasOptions,
  GeoPoint,
  LightingPreset,
  TimedSample,
} from "./types.js";
export { FlightCancelled, SINGAPORE_BOUNDS } from "./types.js";
export type { CameraPreset } from "./presets.js";
export { PRESETS } from "./presets.js";

export interface SingaporeCanvas {
  readonly camera: CameraModule;
  readonly scene: SceneModule;
  readonly time: TimeModule;
  addPolygonLayer(data: object, callbacks: PolygonCallbacks, options?: PolygonLayerOptions): Promise<PolygonLayer>;
  addLabels(labels: readonly { position: GeoPoint; text: string }[], style?: { font?: string }): LabelLayer;
  addPath(samples: readonly TimedSample[], style?: PathStyle): PathLayer;
  addMarkers(markers: readonly { id: string; position: GeoPoint }[]): MarkerLayer;
  addGroundCircles(
    circles: readonly { id: string; center: GeoPoint; radiusM: number }[],
    callbacks?: CircleCallbacks,
  ): CircleLayer;
  /** A one-shot burst at a point. Build it early: its ground geometry takes a moment. */
  addBurst(center: GeoPoint, options?: { color?: string; radiusM?: number; durationS?: number }): BurstLayer;
  /** Colours the city's buildings inside `areas` and outlines the areas. Google's tiles get the outline only. */
  addBuildingTint(areas: readonly TintArea[], style: TintStyle): TintLayer;
  on<K extends keyof CanvasEvents>(
    event: K,
    handler: (payload: CanvasEvents[K]) => void,
  ): () => void;
  destroy(): void;
}

export async function createSingaporeCanvas(
  container: HTMLElement,
  options: CanvasOptions = {},
): Promise<SingaporeCanvas> {
  // Cesium keeps these as module-level statics, so they are the one thing that
  // genuinely cannot be per-instance: two canvases on one page share one ion
  // token. Everything else below is instance-scoped.
  if (options.ionToken) Ion.defaultAccessToken = options.ionToken;
  if (options.googleApiKey) GoogleMaps.defaultApiKey = options.googleApiKey;

  const basemap = options.basemap ?? (options.googleApiKey ? "photorealistic" : options.ionToken ? "extruded" : "plain");
  const bounds = options.bounds === undefined ? SINGAPORE_BOUNDS : options.bounds;
  const maxHeight = options.maxHeight ?? 80_000;
  const minHeight = options.minHeight ?? 60;

  const viewer = new Viewer(container, {
    // Strip the widgets we do not want. The credit container is NOT a widget and
    // stays: Google Map Tiles terms of service require visible attribution.
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    baseLayerPicker: false,
    navigationHelpButton: false,
    animation: false,
    timeline: false,
    fullscreenButton: false,
    baseLayer: false,
    infoBox: false,
    selectionIndicator: false,
  });

  const emit = new Emitter<CanvasEvents>();
  viewer.scene.renderError.addEventListener((_scene: unknown, error: Error) => {
    emit.emit("renderError", { message: error.message });
  });
  // Time first: lighting pins the sun through it.
  const timeParts = createTime(viewer, emit);
  const sceneParts = await createScene(
    viewer, basemap, options.lighting ?? "midday", timeParts.setSunInstant, options.maximumScreenSpaceError,
  ).catch((error: unknown) => {
    timeParts.destroy();
    if (!viewer.isDestroyed()) viewer.destroy();
    throw error;
  });
  const polygonLayers = new Set<PolygonLayer>();
  // Every other layer; none of them affects the globe rule.
  const layers = new Set<{ destroy(): void }>();
  const track = <T extends { destroy(): void }>(layer: T): T => {
    layers.add(layer);
    return layer;
  };
  const visibleLayers = new Set<object>();
  const cameraParts = createCamera(viewer, bounds, maxHeight, minHeight, emit);

  const tileProgress = (pending: number): void => {
    emit.emit("tileLoadProgress", { pending });
  };
  viewer.scene.globe.tileLoadProgressEvent.addEventListener(tileProgress);

  // Start inside the cage rather than wherever Cesium's default view lands.
  await cameraParts.module.flyToPreset("island", { duration: 0 });

  return {
    camera: cameraParts.module,
    scene: sceneParts.module,
    time: timeParts.module,
    async addPolygonLayer(data, callbacks, options) {
      const token = {};
      const layer = await addPolygonLayer(viewer, data, callbacks, (visible) => {
        if (visible) visibleLayers.add(token); else visibleLayers.delete(token);
        sceneParts.requireGlobe(visibleLayers.size > 0);
      }, options);
      polygonLayers.add(layer);
      return layer;
    },
    addLabels: (labels, style) => track(addLabels(viewer, labels, style)),
    addPath: (samples, style) => track(addPath(viewer, timeParts.now, samples, style)),
    addMarkers: (markers) => track(addMarkers(viewer, markers)),
    addGroundCircles: (circles, callbacks) => track(addGroundCircles(viewer, circles, callbacks)),
    addBurst: (center, options) => track(addBurst(viewer, center, options)),
    addBuildingTint: (areas, style) => track(addBuildingTint(viewer, sceneParts.onTileset, areas, style)),
    on: (event, handler) => emit.on(event, handler),
    destroy(): void {
      viewer.scene.globe.tileLoadProgressEvent.removeEventListener(tileProgress);
      for (const layer of polygonLayers) layer.destroy();
      polygonLayers.clear();
      for (const layer of layers) layer.destroy();
      layers.clear();
      cameraParts.destroy();
      timeParts.destroy();
      sceneParts.destroy();
      emit.clear();
      if (!viewer.isDestroyed()) viewer.destroy();
    },
  };
}
