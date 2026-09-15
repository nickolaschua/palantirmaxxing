import { GoogleMaps, Ion, Viewer } from "cesium";
import { createCamera } from "./camera.js";
import { createScene } from "./scene.js";
import { Emitter } from "./events.js";
import { addPolygonLayer } from "./polygons.js";
import type { PolygonLayer, PolygonCallbacks } from "./polygons.js";
export type { PolygonLayer, PolygonStyle } from "./polygons.js";
import { SINGAPORE_BOUNDS } from "./types.js";
import type { CameraModule } from "./camera.js";
import type { SceneModule } from "./scene.js";
import type { CanvasEvents, CanvasOptions } from "./types.js";

export type {
  Bounds,
  BasemapKind,
  CameraOrientation,
  CameraPose,
  CanvasEvents,
  CanvasOptions,
  GeoPoint,
  LightingPreset,
} from "./types.js";
export { FlightCancelled, SINGAPORE_BOUNDS } from "./types.js";
export type { CameraPreset } from "./presets.js";
export { PRESETS } from "./presets.js";

export interface SingaporeCanvas {
  readonly camera: CameraModule;
  readonly scene: SceneModule;
  addPolygonLayer(data: object, callbacks: PolygonCallbacks): Promise<PolygonLayer>;
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
  const sceneParts = await createScene(viewer, basemap, options.lighting ?? "midday").catch((error: unknown) => {
    if (!viewer.isDestroyed()) viewer.destroy();
    throw error;
  });
  const polygonLayers = new Set<PolygonLayer>();
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
    async addPolygonLayer(data, callbacks) {
      const token = {};
      const layer = await addPolygonLayer(viewer, data, callbacks, (visible) => {
        if (visible) visibleLayers.add(token); else visibleLayers.delete(token);
        sceneParts.requireGlobe(visibleLayers.size > 0);
      });
      polygonLayers.add(layer);
      return layer;
    },
    on: (event, handler) => emit.on(event, handler),
    destroy(): void {
      viewer.scene.globe.tileLoadProgressEvent.removeEventListener(tileProgress);
      for (const layer of polygonLayers) layer.destroy();
      polygonLayers.clear();
      cameraParts.destroy();
      sceneParts.destroy();
      emit.clear();
      if (!viewer.isDestroyed()) viewer.destroy();
    },
  };
}
