import {
  Cartesian2, ClassificationType, Color, ColorMaterialProperty, ConstantProperty,
  Entity, GeoJsonDataSource, ScreenSpaceEventHandler, ScreenSpaceEventType, Viewer,
} from "cesium";

export interface PolygonStyle { color: string; visible: boolean; selected?: boolean }
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
  visibilityChanged: (visible: boolean) => void,
): Promise<PolygonLayer> {
  const collection = data as { type?: string; features?: { id?: unknown; geometry?: { type?: string } }[] };
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
      visibilityChanged(false);
    },
  };
}
