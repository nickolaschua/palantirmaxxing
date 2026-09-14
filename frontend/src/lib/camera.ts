import {
  BoundingSphere,
  CameraEventType,
  Cartesian3,
  EasingFunction,
  HeadingPitchRange,
  KeyboardEventModifier,
  Math as CesiumMath,
  Matrix4,
  Viewer,
} from "cesium";
import { PRESETS } from "./presets.js";
import { FlightCancelled } from "./types.js";
import type { Bounds, BoundsEdge, CameraPose, CanvasEvents } from "./types.js";
import type { Emitter } from "./events.js";

export interface OrbitOptions {
  centre: { lon: number; lat: number; height?: number };
  radius: number;
  pitch?: number;
  degreesPerSecond?: number;
}

export interface CameraModule {
  flyToPreset(name: string, opts?: { duration?: number }): Promise<void>;
  flyTo(pose: CameraPose, opts?: { duration?: number }): Promise<void>;
  orbit(opts: OrbitOptions): void;
  follow(pathId: string, opts?: { range?: number; pitch?: number }): void;
  stop(): void;
  readonly pose: CameraPose;
  readonly presets: readonly string[];
}

export interface CameraInternals {
  module: CameraModule;
  destroy(): void;
}

export function createCamera(
  viewer: Viewer,
  bounds: Bounds | null,
  maxHeight: number,
  minHeight: number,
  emit: Emitter<CanvasEvents>,
): CameraInternals {
  const scene = viewer.scene;
  const cam = viewer.camera;

  let orbitTick: (() => void) | null = null;
  let lastEdge: BoundsEdge | null = null;
  let cancelActive: (() => void) | null = null;
  // Library-driven motion is trusted; the cage only polices user input.
  let suspended = 0;

  // First line of defence. maximumZoomDistance is deliberately NOT set: the docs
  // describe it as a magnitude of the camera position, which may mean distance
  // from the ellipsoid centre rather than altitude, and getting that wrong puts
  // the camera underground. The per-frame clamp below owns the ceiling instead.
  scene.screenSpaceCameraController.minimumZoomDistance = minHeight;

  // Middle and right drag are swapped from Cesium's defaults. Stock CesiumJS is
  // right-drag = zoom, middle-drag = tilt; here middle zooms and right tilts.
  const ssc = scene.screenSpaceCameraController;
  ssc.zoomEventTypes = [CameraEventType.MIDDLE_DRAG, CameraEventType.WHEEL, CameraEventType.PINCH];
  ssc.tiltEventTypes = [
    CameraEventType.RIGHT_DRAG,
    CameraEventType.PINCH,
    { eventType: CameraEventType.LEFT_DRAG, modifier: KeyboardEventModifier.CTRL },
    { eventType: CameraEventType.MIDDLE_DRAG, modifier: KeyboardEventModifier.CTRL },
  ];

  // ---------------------------------------------------------------------------
  // The cage
  // ---------------------------------------------------------------------------
  function clamp(): void {
    if (suspended > 0) return;

    const c = cam.positionCartographic;
    let lon = CesiumMath.toDegrees(c.longitude);
    let lat = CesiumMath.toDegrees(c.latitude);
    let height = c.height;
    let edge: BoundsEdge | null = null;

    if (bounds) {
      if (lon < bounds.west) {
        lon = bounds.west;
        edge = "west";
      } else if (lon > bounds.east) {
        lon = bounds.east;
        edge = "east";
      }
      if (lat < bounds.south) {
        lat = bounds.south;
        edge = "south";
      } else if (lat > bounds.north) {
        lat = bounds.north;
        edge = "north";
      }
    }

    if (height > maxHeight) {
      height = maxHeight;
      edge = "ceiling";
    } else if (height < minHeight) {
      height = minHeight;
      edge = "floor";
    }

    if (edge === null) {
      lastEdge = null;
      return;
    }

    cam.setView({
      destination: Cartesian3.fromDegrees(lon, lat, height),
      orientation: { heading: cam.heading, pitch: cam.pitch, roll: cam.roll },
    });

    // Announce the transition only, not every frame spent against the wall.
    if (edge !== lastEdge) {
      lastEdge = edge;
      emit.emit("boundsHit", { edge });
    }
  }

  const cageTick = clamp;
  scene.preRender.addEventListener(cageTick);

  // ---------------------------------------------------------------------------
  // Flights
  // ---------------------------------------------------------------------------
  function flight(
    run: (cb: { complete: () => void; cancel: () => void }) => void,
  ): Promise<void> {
    stop();
    return new Promise<void>((resolve, reject) => {
      suspended += 1;
      let settled = false;
      const release = (): void => {
        if (settled) return;
        settled = true;
        suspended -= 1;
        cancelActive = null;
      };
      cancelActive = (): void => {
        release();
        reject(new FlightCancelled());
      };
      run({
        complete: (): void => {
          release();
          resolve();
        },
        cancel: (): void => {
          release();
          reject(new FlightCancelled());
        },
      });
    });
  }

  function flyToPreset(name: string, opts: { duration?: number } = {}): Promise<void> {
    const preset = PRESETS[name];
    if (!preset) return Promise.reject(new Error(`Unknown camera preset: ${name}`));

    const centre = Cartesian3.fromDegrees(
      preset.target.lon,
      preset.target.lat,
      preset.target.height ?? 0,
    );

    return flight(({ complete, cancel }) => {
      cam.flyToBoundingSphere(new BoundingSphere(centre, 1), {
        offset: new HeadingPitchRange(
          CesiumMath.toRadians(preset.heading),
          CesiumMath.toRadians(preset.pitch),
          preset.range,
        ),
        duration: opts.duration ?? 2.5,
        // Stops the flight arc bulging up through the ceiling.
        maximumHeight: maxHeight,
        easingFunction: EasingFunction.QUADRATIC_IN_OUT,
        complete,
        cancel,
      });
    });
  }

  function flyTo(pose_: CameraPose, opts: { duration?: number } = {}): Promise<void> {
    return flight(({ complete, cancel }) => {
      cam.flyTo({
        destination: Cartesian3.fromDegrees(pose_.lon, pose_.lat, pose_.height ?? 1000),
        orientation: {
          heading: CesiumMath.toRadians(pose_.heading ?? 0),
          pitch: CesiumMath.toRadians(pose_.pitch ?? -30),
          roll: CesiumMath.toRadians(pose_.roll ?? 0),
        },
        duration: opts.duration ?? 2.5,
        maximumHeight: maxHeight,
        easingFunction: EasingFunction.QUADRATIC_IN_OUT,
        complete,
        cancel,
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Orbit
  // ---------------------------------------------------------------------------
  function orbit(opts: OrbitOptions): void {
    stop();
    const target = Cartesian3.fromDegrees(
      opts.centre.lon,
      opts.centre.lat,
      opts.centre.height ?? 0,
    );
    const pitch = CesiumMath.toRadians(opts.pitch ?? -20);
    const rate = CesiumMath.toRadians(opts.degreesPerSecond ?? 6);

    // Own the angle rather than reading camera.heading back out of a transform
    // that is rewritten every frame. That readback is what made the spike drift.
    let heading = cam.heading;
    let last = performance.now();

    suspended += 1;
    orbitTick = (): void => {
      const now = performance.now();
      heading += rate * ((now - last) / 1000);
      last = now;
      cam.lookAt(target, new HeadingPitchRange(heading, pitch, opts.radius));
    };
    scene.preRender.addEventListener(orbitTick);
  }

  function follow(_pathId: string): void {
    throw new Error(
      "camera.follow() needs path layers, which arrive in step 6 (layers module).",
    );
  }

  function stop(): void {
    cancelActive?.();
    cam.cancelFlight();
    if (orbitTick) {
      scene.preRender.removeEventListener(orbitTick);
      orbitTick = null;
      cam.lookAtTransform(Matrix4.IDENTITY);
      suspended -= 1;
    }
  }

  function pose(): CameraPose {
    const c = cam.positionCartographic;
    return {
      lon: CesiumMath.toDegrees(c.longitude),
      lat: CesiumMath.toDegrees(c.latitude),
      height: c.height,
      heading: CesiumMath.toDegrees(cam.heading),
      pitch: CesiumMath.toDegrees(cam.pitch),
      roll: CesiumMath.toDegrees(cam.roll),
    };
  }

  const changeListener = (): void => emit.emit("cameraChange", pose());
  cam.percentageChanged = 0.1;
  cam.changed.addEventListener(changeListener);

  return {
    module: {
      flyToPreset,
      flyTo,
      orbit,
      follow,
      stop,
      get pose() {
        return pose();
      },
      presets: Object.keys(PRESETS),
    },
    destroy(): void {
      stop();
      cam.changed.removeEventListener(changeListener);
      scene.preRender.removeEventListener(cageTick);
    },
  };
}
