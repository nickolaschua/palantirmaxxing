import {
  BillboardCollection, Cartesian3, ClassificationType, Color, EllipseGeometry, EllipsoidGeometry,
  EllipsoidSurfaceAppearance, GeometryInstance, GroundPrimitive, Material, MaterialAppearance, Matrix4, Primitive,
  Transforms,
} from "cesium";
import type { Viewer } from "cesium";
import type { GeoPoint } from "./types.js";

export interface BurstLayer {
  /** Restarts the effect from zero. */
  play(): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}

/** 0 before `a`, 1 after `b`, linear between. */
const ramp = (p: number, a: number, b: number): number => Math.min(1, Math.max(0, (p - a) / (b - a)));
const easeOut = (t: number): number => 1 - (1 - t) ** 3;

/** With reduced motion the effect is one still frame this far in, held this long. */
const STILL_AT = 0.3;
const STILL_MS = 350;

/** Radial sprite, white at the centre through `color` to clear. Baked once; the billboard tints and fades it. */
function glowSprite(color: Color): HTMLCanvasElement {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas is unavailable");
  const half = size / 2;
  const g = ctx.createRadialGradient(half, half, 0, half, half, half);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.3, color.withAlpha(0.9).toCssColorString());
  g.addColorStop(1, color.withAlpha(0).toCssColorString());
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return canvas;
}

// Fabric sources. Uniforms are declared by Cesium from the `uniforms` map; `m.` fields are left alone.
// Both are flat-shaded so the look does not depend on scene lighting.

/** Hollow shell: dense at the silhouette, thin where it faces the eye. */
const SHELL_SOURCE = `
czm_material czm_getMaterial(czm_materialInput materialInput)
{
    czm_material m;
    m.specular = 0.0;
    m.shininess = 1.0;
    m.normal = materialInput.normalEC;
    m.emission = vec3(0.0);
    float facing = abs(dot(normalize(materialInput.normalEC), normalize(materialInput.positionToEyeEC)));
    float rim = pow(1.0 - facing, 2.0);
    m.diffuse = mix(tint.rgb, vec3(1.0), 0.5 * rim);
    m.alpha = fade * (0.15 + 0.85 * rim);
    return m;
}`;

/** Ground wave: a ring at `front` (0 centre, 1 rim) with a sharp leading edge and a longer trail, plus an inner glow. */
const GROUND_SOURCE = `
czm_material czm_getMaterial(czm_materialInput materialInput)
{
    czm_material m;
    m.specular = 0.0;
    m.shininess = 1.0;
    m.normal = vec3(0.0);
    m.emission = vec3(0.0);
    // st spans the disc's bounding square, so radius is 0 at the centre and 1 at the rim.
    float r = length(materialInput.st - 0.5) * 2.0;
    float d = r - front;
    float ring = d > 0.0 ? 1.0 - smoothstep(0.0, band * 0.3, d) : 1.0 - smoothstep(0.0, band, -d);
    float fill = (1.0 - smoothstep(front * 0.3, max(front, 0.001), r)) * fillFade;
    m.diffuse = mix(tint.rgb, vec3(1.0), 0.6 * ring * ringFade);
    m.alpha = clamp(ring * ringFade + fill, 0.0, 1.0);
    return m;
}`;

/**
 * A short release of energy at a point: a bright core that flares and dies, a
 * hollow shell that grows and thins, and a wave racing outward across the
 * ground. Created paused; `play()` starts it. Everything is gone by
 * `durationS` and hidden so it costs nothing until the next `play()`.
 */
export function addBurst(
  viewer: Viewer, center: GeoPoint,
  options: { color?: string; radiusM?: number; durationS?: number } = {},
): BurstLayer {
  const radiusM = options.radiusM ?? 500;
  const durationMs = (options.durationS ?? 2.2) * 1000;
  if (![center.lon, center.lat, center.height ?? 0].every(Number.isFinite)) throw new Error("Burst has a non-finite position");
  if (!(Number.isFinite(radiusM) && radiusM > 0)) throw new Error("Burst needs a positive, finite radius");
  if (!(Number.isFinite(durationMs) && durationMs > 0)) throw new Error("Burst needs a positive, finite duration");
  const scene = viewer.scene;
  const tint = Color.fromCssColorString(options.color ?? "#ff7043");
  const origin = Cartesian3.fromDegrees(center.lon, center.lat, center.height ?? 0);

  // Core: a sprite sized in metres so it stays in proportion from any height. Never occluded by buildings.
  const sprites = scene.primitives.add(new BillboardCollection()) as BillboardCollection;
  // Wider than half the radius: from several kilometres up a small core disappears.
  const coreM = radiusM * 1.2;
  const core = sprites.add({
    position: origin, image: glowSprite(tint), sizeInMeters: true, width: coreM, height: coreM,
    color: Color.WHITE.withAlpha(0), show: false, disableDepthTestDistance: Number.POSITIVE_INFINITY,
  });

  // Shell: a dome built once at full size in world coordinates (Cesium projects vertices to 2D at build time,
  // so it cannot live at the origin). Growth is a world-space scale about `origin` on the primitive's modelMatrix.
  const shellMaterial = new Material({ fabric: { uniforms: { tint, fade: 0 }, source: SHELL_SOURCE } });
  const shell = scene.primitives.add(new Primitive({
    geometryInstances: new GeometryInstance({
      geometry: new EllipsoidGeometry({
        radii: new Cartesian3(radiusM, radiusM, radiusM * 0.75), maximumCone: Math.PI / 2,
        stackPartitions: 24, slicePartitions: 48, vertexFormat: MaterialAppearance.MaterialSupport.BASIC.vertexFormat,
      }),
      modelMatrix: Transforms.eastNorthUpToFixedFrame(origin),
    }),
    appearance: new MaterialAppearance({
      material: shellMaterial, flat: true, translucent: true, closed: false,
      materialSupport: MaterialAppearance.MaterialSupport.BASIC,
    }),
    show: false, allowPicking: false,
  })) as Primitive;
  const shellMatrix = new Matrix4();
  const shellShift = new Cartesian3();
  const scaleShell = (s: number): void => {
    // Uniform scale about `origin`: S·p + (1 − s)·origin. Built in doubles here, so precision holds on the GPU.
    Matrix4.fromUniformScale(s, shellMatrix);
    Matrix4.setTranslation(shellMatrix, Cartesian3.multiplyByScalar(origin, 1 - s, shellShift), shellMatrix);
    shell.modelMatrix = shellMatrix;
  };

  // Ground: one draped disc; the wave is drawn by the material, so the slow ground-geometry build happens now,
  // not at play(). A hidden primitive still builds. The disc is wider than the reach so the wave's trail fits.
  const REACH = 1 / 1.12;
  const groundMaterial = new Material({
    fabric: { uniforms: { tint, front: 0, band: 0.2, ringFade: 0, fillFade: 0 }, source: GROUND_SOURCE },
  });
  const wave = groundMaterial.uniforms as { front: number; band: number; ringFade: number; fillFade: number };
  const ground = scene.primitives.add(new GroundPrimitive({
    geometryInstances: new GeometryInstance({
      geometry: new EllipseGeometry({
        center: Cartesian3.fromDegrees(center.lon, center.lat, 0),
        semiMajorAxis: radiusM / REACH, semiMinorAxis: radiusM / REACH,
      }),
    }),
    appearance: new EllipsoidSurfaceAppearance({ material: groundMaterial, flat: true }),
    classificationType: ClassificationType.BOTH,
    allowPicking: false,
    show: false,
  })) as GroundPrimitive;

  let visible = true;
  let active = false;
  const applyShow = (): void => {
    const on = visible && active;
    core.show = on;
    shell.show = on;
    ground.show = on;
    scene.requestRender();
  };

  const coreColor = new Color();
  /** The whole effect as a function of progress p in [0, 1). */
  const render = (p: number): void => {
    // Core: on within 5%, full until 15%, gone by 55%, swelling slightly as it dies.
    core.scale = 0.2 + easeOut(ramp(p, 0, 0.3)) + 0.3 * ramp(p, 0.3, 0.55);
    core.color = Color.fromAlpha(Color.WHITE, ramp(p, 0, 0.05) * (1 - ramp(p, 0.15, 0.55) ** 2), coreColor);
    // Shell: races out over 65%, drifts on as it thins, gone at 100%.
    scaleShell(Math.max(0.02, easeOut(ramp(p, 0, 0.65)) + 0.15 * ramp(p, 0.65, 1)));
    shellMaterial.uniforms.fade = 1.35 * ramp(p, 0, 0.06) * (1 - ramp(p, 0.2, 1) ** 2);
    // Ground: the wave leaves at 4%, reaches the edge at 78% and thins on the way; the inner glow dies first.
    const out = 1 - (1 - ramp(p, 0.04, 0.78)) ** 4;
    wave.front = out * REACH;
    wave.band = 0.22 - 0.17 * out;
    wave.ringFade = ramp(p, 0.04, 0.08) * (1 - ramp(p, 0.4, 1) ** 1.5);
    wave.fillFade = 0.5 * ramp(p, 0, 0.08) * (1 - ramp(p, 0.1, 0.6));
  };

  const reducedMotion = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let startMs = 0;
  let ticking = false;
  const stop = (): void => {
    if (ticking) scene.preRender.removeEventListener(tick);
    ticking = false;
    active = false;
    applyShow();
  };
  // Wall clock, not the Cesium clock: the host may freeze its clock at the moment this plays.
  const tick = (): void => {
    const elapsed = performance.now() - startMs;
    if (reducedMotion ? elapsed >= STILL_MS : elapsed >= durationMs) { stop(); return; }
    render(reducedMotion ? STILL_AT : elapsed / durationMs);
    scene.requestRender(); // wall clock: ask for the next frame until it finishes
  };

  let destroyed = false;
  return {
    play() {
      if (destroyed) return;
      startMs = performance.now();
      active = true;
      applyShow();
      tick(); // frame zero now, so nothing stale shows
      if (!ticking) scene.preRender.addEventListener(tick);
      ticking = true;
    },
    setVisible(value) {
      visible = value;
      applyShow();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      stop();
      scene.primitives.remove(sprites);
      scene.primitives.remove(shell);
      scene.primitives.remove(ground);
    },
  };
}
