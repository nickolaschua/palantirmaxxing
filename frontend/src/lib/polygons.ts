import {
  Cartesian2, Cartesian3, ClassificationType, Color, ColorGeometryInstanceAttribute, ColorMaterialProperty, ConstantProperty,
  Entity, GeoJsonDataSource, GeometryInstance, GroundPolylineGeometry, GroundPolylinePrimitive, PolylineColorAppearance,
  ScreenSpaceEventHandler, ScreenSpaceEventType, Viewer,
} from "cesium";
import { dedupe } from "./coastline.js";

export interface PolygonStyle { color: string; visible: boolean; selected?: boolean }
export interface PolygonLayerOptions {
  /** CSS colour for every ring's boundary line, draped on the ground. Omit for no boundaries. */
  outline?: string;
}
export interface PolygonLayer {
  setVisible(visible: boolean): void;
  setStyles(styles: ReadonlyMap<string, PolygonStyle>): void;
  destroy(): void;
}
export interface PolygonCallbacks {
  hover(id: string | null): void;
  click(id: string | null): void;
}

/** Domain-neutral GeoJSON polygons, including MultiPolygons, with feature-ID picking. */
export async function addPolygonLayer(
  viewer: Viewer, data: object, callbacks: PolygonCallbacks,
  visibilityChanged: (visible: boolean) => void, options: PolygonLayerOptions = {},
): Promise<PolygonLayer> {
  const collection = data as { type?: string; features?: { id?: unknown; geometry?: { type?: string; coordinates?: unknown } }[] };
  if (collection.type !== "FeatureCollection" || !Array.isArray(collection.features)) throw new Error("Expected polygon FeatureCollection");
  const ids = new Set<string>();
  const features = collection.features.map(feature => {
    if (typeof feature.id !== "string" || ids.has(feature.id) || !["Polygon", "MultiPolygon"].includes(feature.geometry?.type ?? "")) {
      throw new Error("Polygon features require unique string IDs and Polygon/MultiPolygon geometry");
    }
    ids.add(feature.id);
    // GeoJsonDataSource generates extra Entity IDs for MultiPolygon parts.
    // Internal tagging preserves the caller's stable ID for all parts.
    return { ...feature, properties: { __featureId: feature.id } };
  });
  const source = await GeoJsonDataSource.load({ type: "FeatureCollection", features }, { clampToGround: true, stroke: Color.WHITE, strokeWidth: 1, describe: () => "" });
  await viewer.dataSources.add(source);
  const outline = options.outline ? addOutline(viewer, features, Color.fromCssColorString(options.outline)) : undefined;
  const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
  let visible = true;
  let destroyed = false;
  let hoverId: string | null = null;
  function featureId(entity: Entity): string {
    return String(entity.properties?.getValue(viewer.clock.currentTime).__featureId ?? entity.id);
  }
  function pick(position: Cartesian2): string | null {
    if (!visible) return null;
    // drillPick finds ground polygons even where a building is also pickable.
    for (const hit of viewer.scene.drillPick(position, 12)) {
      // A string id is another id-addressed layer (ground circles) drawn on top; it wins the pick.
      if (typeof hit.id === "string") return null;
      if (hit.id instanceof Entity && source.entities.contains(hit.id) && hit.id.show) return featureId(hit.id);
    }
    return null;
  }
  handler.setInputAction((motion: { endPosition: Cartesian2 }) => {
    const id = pick(motion.endPosition);
    if (id !== hoverId) { hoverId = id; callbacks.hover(id); }
  }, ScreenSpaceEventType.MOUSE_MOVE);
  handler.setInputAction((motion: { position: Cartesian2 }) => callbacks.click(pick(motion.position)), ScreenSpaceEventType.LEFT_CLICK);
  const leave = (): void => { hoverId = null; callbacks.hover(null); };
  viewer.scene.canvas.addEventListener("mouseleave", leave);
  visibilityChanged(true);
  return {
    setVisible(value) {
      visible = value;
      source.show = value;
      if (outline) outline.show = value;
      if (!value) leave();
      visibilityChanged(value);
      viewer.scene.requestRender();
    },
    setStyles(styles) {
      source.entities.suspendEvents();
      try {
        for (const entity of source.entities.values) {
          const style = styles.get(featureId(entity));
          entity.show = style?.visible ?? false;
          if (style && entity.polygon) {
            const color = Color.fromCssColorString(style.color).withAlpha(style.selected ? 0.95 : 0.72);
            entity.polygon.material = new ColorMaterialProperty(color);
            entity.polygon.classificationType = new ConstantProperty(ClassificationType.BOTH);
            entity.polygon.zIndex = new ConstantProperty(style.selected ? 20 : 10);
          }
        }
      } finally { source.entities.resumeEvents(); }
      viewer.scene.requestRender();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      handler.destroy();
      viewer.scene.canvas.removeEventListener("mouseleave", leave);
      viewer.dataSources.remove(source, true);
      if (outline) viewer.scene.primitives.remove(outline);
      visibilityChanged(false);
    },
  };
}

/**
 * One ground-draped line per ring, outer and holes, in a single primitive.
 * ponytail: follows the layer's visibility only, not each feature's `visible` style;
 * per-instance show attributes if a caller ever hides individual features.
 */
function addOutline(viewer: Viewer, features: readonly { geometry?: { type?: string; coordinates?: unknown } }[], color: Color): GroundPolylinePrimitive {
  const instances: GeometryInstance[] = [];
  for (const { geometry } of features) {
    const polygons = (geometry?.type === "Polygon" ? [geometry.coordinates] : geometry?.coordinates) as number[][][][];
    for (const ring of polygons.flat()) {
      const flat = dedupe(ring.flatMap(([lon, lat]) => [lon!, lat!]));
      if (flat.length < 6) continue;
      instances.push(new GeometryInstance({
        geometry: new GroundPolylineGeometry({ positions: Cartesian3.fromDegreesArray(flat), width: 2, loop: true }),
        attributes: { color: ColorGeometryInstanceAttribute.fromColor(color) },
      }));
    }
  }
  return viewer.scene.primitives.add(new GroundPolylinePrimitive({
    classificationType: ClassificationType.BOTH,
    appearance: new PolylineColorAppearance(),
    allowPicking: false,
    geometryInstances: instances,
  }));
}
