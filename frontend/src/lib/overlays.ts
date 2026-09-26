import {
  Cartesian2, Cartesian3, ClassificationType, Color, ColorGeometryInstanceAttribute, EllipseGeometry, Ellipsoid,
  ExtrapolationType, GeometryInstance, GroundPolylineGeometry, GroundPolylinePrimitive, GroundPrimitive, JulianDate,
  LabelCollection, Material, Matrix4, PointPrimitiveCollection, PolylineColorAppearance, PolylineCollection,
  SampledPositionProperty, ScreenSpaceEventHandler, ScreenSpaceEventType, ShowGeometryInstanceAttribute, Transforms,
  VerticalOrigin, Viewer,
} from "cesium";
import type { Label, PointPrimitive } from "cesium";
import { addCraftMarker } from "./craft.js";
import { LABEL_LOOK } from "./labels.js";
import type { GeoPoint, TimedSample } from "./types.js";

export interface PathLayer {
  setVisible(visible: boolean): void;
  /** Hides the moving marker while the route stays drawn. */
  setMarkerVisible(visible: boolean): void;
  destroy(): void;
}
export interface PathStyle {
  color?: string;
  width?: number;
  /** The stretch already flown. Defaults to a dim grey. */
  trailColor?: string;
  /** Marker diameter in pixels; 0 draws the line with no marker. */
  markerSize?: number;
  /** "craft" swaps the dot for a solid shape that points along the direction of travel. */
  markerShape?: "point" | "craft";
  /** The craft brightens to white and back on a ~1 s cycle, so it stays findable when the map is zoomed out. */
  markerPulse?: boolean;
  dashed?: boolean;
}

export interface MarkerStyle { color: string; size: number; visible: boolean; label?: string }
export interface MarkerLayer {
  /** Markers missing from the map are hidden. */
  setStyles(styles: ReadonlyMap<string, MarkerStyle>): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}

export interface CircleStyle { fill: string; outline: string; visible: boolean }
export interface CircleCallbacks { hover(id: string | null): void; click(id: string | null): void }
export interface CircleLayer {
  /**
   * Resolves once the circles are built and can draw and be picked. Building
   * runs on Cesium's shared web workers, so it can take seconds while other
   * geometry is queued. It happens even while the layer is hidden.
   */
  readonly ready: Promise<void>;
  /** Circles missing from the map are hidden. */
  setStyles(styles: ReadonlyMap<string, CircleStyle>): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}

/** Heights default to 0 m above the ellipsoid. Never nudged. */
function toCartesian(p: GeoPoint, what: string): Cartesian3 {
  if (![p.lon, p.lat, p.height ?? 0].every(Number.isFinite)) throw new Error(`${what} has a non-finite position`);
  return Cartesian3.fromDegrees(p.lon, p.lat, p.height ?? 0);
}

function uniqueIds(items: readonly { id: string }[]): void {
  const seen = new Set<string>();
  for (const { id } of items) {
    if (seen.has(id)) throw new Error(`Duplicate id "${id}"`);
    seen.add(id);
  }
}

/**
 * The route as a line at its true heights, plus a marker that moves with the
 * clock. The stretch still ahead of the marker draws in `color`; the stretch
 * already flown drops to `trailColor`. `markerSize: 0` draws the line alone,
 * with no marker and no split — for a route nothing travels along.
 */
export function addPath(
  viewer: Viewer, now: () => JulianDate, samples: readonly TimedSample[], style: PathStyle = {},
): PathLayer {
  if (samples.length < 2) throw new Error("A path needs at least two samples");
  const scene = viewer.scene;
  const sampled = new SampledPositionProperty();
  // Hold at the first sample before the path starts and at the last after it ends.
  sampled.backwardExtrapolationType = ExtrapolationType.HOLD;
  sampled.forwardExtrapolationType = ExtrapolationType.HOLD;
  const positions: Cartesian3[] = [];
  let previous = -Infinity;
  for (const [i, s] of samples.entries()) {
    const t = s.time.getTime();
    if (!(t > previous)) throw new Error(`Path sample ${i} has an invalid or non-increasing time`);
    previous = t;
    const position = toCartesian(s, `Path sample ${i}`);
    positions.push(position);
    sampled.addSample(JulianDate.fromDate(s.time), position);
  }

  const color = Color.fromCssColorString(style.color ?? "#ff4d4d");
  const width = style.width ?? 3;
  const size = style.markerSize ?? 12;
  const material = (fill: Color): Material => style.dashed
    ? Material.fromType("PolylineDash", { color: fill, gapColor: Color.TRANSPARENT, dashLength: 14 })
    : Material.fromType("Color", { color: fill });
  const lines = scene.primitives.add(new PolylineCollection()) as PolylineCollection;
  // The whole route, dimmed, with the part still to fly drawn over it.
  lines.add({ positions, width, material: material(Color.fromCssColorString(style.trailColor ?? "#6e7681")) });
  const ahead = size > 0 ? lines.add({ positions, width, material: material(color) }) : undefined;
  const craft = size > 0 && style.markerShape === "craft"
    ? addCraftMarker(viewer, { color: style.color ?? "#f5f7fa", lengthM: size * 3.75, minimumPixelLength: size * 2.5, pulse: style.markerPulse })
    : undefined;
  const points = size > 0 && !craft ? scene.primitives.add(new PointPrimitiveCollection()) as PointPrimitiveCollection : undefined;
  const halo = points?.add({
    position: positions[0], pixelSize: size * 2.2, color: color.withAlpha(0.25),
    disableDepthTestDistance: Number.POSITIVE_INFINITY,
  });
  const dot = points?.add({
    position: positions[0], pixelSize: size, color, outlineColor: Color.WHITE, outlineWidth: 2,
    disableDepthTestDistance: Number.POSITIVE_INFINITY,
  });

  const times = samples.map(s => s.time.getTime());
  const scratch = new Cartesian3();
  const scratchAhead = new Cartesian3();
  const scratchTime = new JulianDate();
  const heading = new Cartesian3();
  const move = (): void => {
    const time = now();
    const p = sampled.getValue(time, scratch);
    if (!p || !ahead) return;
    if (craft) {
      // Point it where it is going: the position half a second on.
      const next = sampled.getValue(JulianDate.addSeconds(time, 0.5, scratchTime), scratchAhead);
      craft.setPose(p, next ? Cartesian3.subtract(next, p, heading) : heading);
    }
    if (dot && halo) {
      dot.position = p; // the setter copies
      halo.position = p;
    }
    // Everything from the marker to the last sample; hidden once there is no line left.
    const ms = JulianDate.toDate(time).getTime();
    const next = times.findIndex(t => t > ms);
    ahead.show = next >= 0;
    if (next >= 0) ahead.positions = [Cartesian3.clone(p), ...positions.slice(next)];
  };
  if (size > 0) scene.preRender.addEventListener(move);

  let destroyed = false;
  let layerVisible = true;
  let markerVisible = true;
  const applyVisibility = (): void => {
    lines.show = layerVisible;
    if (points) points.show = layerVisible && markerVisible;
    craft?.setVisible(layerVisible && markerVisible);
    scene.requestRender();
  };
  return {
    setVisible(visible) {
      layerVisible = visible;
      applyVisibility();
    },
    setMarkerVisible(visible) {
      markerVisible = visible;
      applyVisibility();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      scene.preRender.removeEventListener(move);
      scene.primitives.remove(lines);
      if (points) scene.primitives.remove(points);
      craft?.destroy();
      scene.requestRender();
    },
  };
}

/** Points with optional labels, styled by id. Not pickable. */
export function addMarkers(viewer: Viewer, markers: readonly { id: string; position: GeoPoint }[]): MarkerLayer {
  uniqueIds(markers);
  const scene = viewer.scene;
  const points = scene.primitives.add(new PointPrimitiveCollection()) as PointPrimitiveCollection;
  const labels = scene.primitives.add(new LabelCollection({ scene })) as LabelCollection;
  const byId = new Map<string, { point: PointPrimitive; label: Label }>();
  for (const { id, position: p } of markers) {
    const position = toCartesian(p, `Marker "${id}"`);
    byId.set(id, {
      point: points.add({ position, pixelSize: 8, color: Color.WHITE, disableDepthTestDistance: Number.POSITIVE_INFINITY }),
      label: labels.add({
        position, show: false, ...LABEL_LOOK,
        verticalOrigin: VerticalOrigin.BOTTOM, pixelOffset: new Cartesian2(0, -10),
      }),
    });
  }

  let destroyed = false;
  return {
    setStyles(styles) {
      for (const [id, { point, label }] of byId) {
        const style = styles.get(id);
        point.show = style?.visible ?? false;
        label.show = point.show && !!style?.label;
        if (!style) continue;
        point.color = Color.fromCssColorString(style.color);
        point.pixelSize = style.size;
        label.pixelOffset = new Cartesian2(0, -(style.size / 2 + 4));
        if (style.label) label.text = style.label;
      }
      scene.requestRender();
    },
    setVisible(visible) {
      points.show = visible;
      labels.show = visible;
      scene.requestRender();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      scene.primitives.remove(points);
      scene.primitives.remove(labels);
      scene.requestRender();
    },
  };
}

/** Ring of a geodesic-ish circle: tangent-plane offsets pushed back to the ellipsoid. Sub-metre at these radii. */
function circleRing(center: Cartesian3, radiusM: number, segments = 90): Cartesian3[] {
  const frame = Transforms.eastNorthUpToFixedFrame(center);
  return Array.from({ length: segments }, (_, i) => {
    const a = (2 * Math.PI * i) / segments;
    const p = Matrix4.multiplyByPoint(frame, new Cartesian3(radiusM * Math.cos(a), radiusM * Math.sin(a), 0), new Cartesian3());
    return Ellipsoid.WGS84.scaleToGeodeticSurface(p, p);
  });
}

/**
 * Circles draped on whatever surface is showing — terrain, OSM buildings or
 * Google tiles. Centre heights are ignored. Pickable by id.
 */
export function addGroundCircles(
  viewer: Viewer, circles: readonly { id: string; center: GeoPoint; radiusM: number }[], callbacks?: CircleCallbacks,
): CircleLayer {
  uniqueIds(circles);
  const scene = viewer.scene;
  // Translucent from the start, so later translucent styles render the same way.
  const initial = Color.RED.withAlpha(0.35);
  const fillInstances: GeometryInstance[] = [];
  const outlineInstances: GeometryInstance[] = [];
  for (const { id, center: c, radiusM } of circles) {
    if (!(Number.isFinite(radiusM) && radiusM > 0)) throw new Error(`Circle "${id}" needs a positive, finite radius`);
    const center = toCartesian({ lon: c.lon, lat: c.lat }, `Circle "${id}"`);
    fillInstances.push(new GeometryInstance({
      id,
      geometry: new EllipseGeometry({ center, semiMajorAxis: radiusM, semiMinorAxis: radiusM }),
      attributes: { color: ColorGeometryInstanceAttribute.fromColor(initial), show: new ShowGeometryInstanceAttribute(true) },
    }));
    outlineInstances.push(new GeometryInstance({
      id,
      geometry: new GroundPolylineGeometry({ positions: circleRing(center, radiusM), width: 2, loop: true }),
      attributes: { color: ColorGeometryInstanceAttribute.fromColor(Color.RED), show: new ShowGeometryInstanceAttribute(true) },
    }));
  }
  const fills = scene.primitives.add(new GroundPrimitive({
    classificationType: ClassificationType.BOTH,
    geometryInstances: fillInstances,
  })) as GroundPrimitive;
  const outlines = scene.primitives.add(new GroundPolylinePrimitive({
    classificationType: ClassificationType.BOTH,
    appearance: new PolylineColorAppearance(),
    allowPicking: false,
    geometryInstances: outlineInstances,
  })) as GroundPolylinePrimitive;

  // Instance attributes exist only once both primitives are ready, so styles wait for that.
  let pending: ReadonlyMap<string, CircleStyle> | undefined;
  let markReady: () => void;
  const ready = new Promise<void>(resolve => { markReady = resolve; }); // never settles if destroyed first
  const applyPending = (): void => {
    // Readiness lands in an afterRender that asks for no frame, so keep frames coming until it does.
    // With no circles Cesium never builds them, so they never become ready: don't ask then.
    if (!fills.ready || !outlines.ready) { if (circles.length) scene.requestRender(); return; }
    markReady();
    if (!pending) return;
    for (const { id } of circles) {
      const style = pending.get(id);
      const show = ShowGeometryInstanceAttribute.toValue(style?.visible ?? false);
      const fill = fills.getGeometryInstanceAttributes(id);
      const outline = outlines.getGeometryInstanceAttributes(id);
      fill.show = show;
      outline.show = show;
      if (!style) continue;
      fill.color = ColorGeometryInstanceAttribute.toValue(Color.fromCssColorString(style.fill));
      outline.color = ColorGeometryInstanceAttribute.toValue(Color.fromCssColorString(style.outline));
    }
    pending = undefined;
  };
  scene.preRender.addEventListener(applyPending);

  let visible = true;
  let hoverId: string | null = null;
  const handler = new ScreenSpaceEventHandler(scene.canvas);
  const pick = (position: Cartesian2): string | null => {
    if (!visible) return null;
    for (const hit of scene.drillPick(position, 8)) {
      if (hit.primitive === fills && typeof hit.id === "string") return hit.id;
    }
    return null;
  };
  const leave = (): void => {
    if (hoverId !== null) { hoverId = null; callbacks?.hover(null); }
  };
  if (callbacks) {
    handler.setInputAction((motion: { endPosition: Cartesian2 }) => {
      const id = pick(motion.endPosition);
      if (id !== hoverId) { hoverId = id; callbacks.hover(id); }
    }, ScreenSpaceEventType.MOUSE_MOVE);
    handler.setInputAction((click: { position: Cartesian2 }) => callbacks.click(pick(click.position)), ScreenSpaceEventType.LEFT_CLICK);
    scene.canvas.addEventListener("mouseleave", leave);
  }

  let destroyed = false;
  return {
    ready,
    setStyles(styles) {
      pending = styles;
      applyPending();
      scene.requestRender(); // applies on the next frame if the geometry is still building
    },
    setVisible(value) {
      visible = value;
      fills.show = value;
      outlines.show = value;
      if (!value) leave();
      scene.requestRender();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      handler.destroy();
      scene.canvas.removeEventListener("mouseleave", leave);
      scene.preRender.removeEventListener(applyPending);
      scene.primitives.remove(fills);
      scene.primitives.remove(outlines);
      scene.requestRender();
    },
  };
}
