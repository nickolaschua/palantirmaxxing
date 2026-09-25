import {
  Cartesian3, Color, HeightReference, HorizontalOrigin, LabelCollection, LabelStyle, VerticalOrigin, Viewer,
} from "cesium";
import type { GeoPoint } from "./types.js";

export interface LabelLayer {
  setVisible(visible: boolean): void;
  destroy(): void;
}

/** The one label look, shared with marker labels. */
export const LABEL_LOOK = {
  font: "600 12px 'Alliance No.2', 'Alliance No.1', Inter, sans-serif", // matches the UI font in style.css
  style: LabelStyle.FILL_AND_OUTLINE,
  fillColor: Color.WHITE,
  outlineColor: Color.fromCssColorString("#1b1f24"),
  outlineWidth: 2,
  // Never hidden behind terrain or buildings.
  disableDepthTestDistance: Number.POSITIVE_INFINITY,
} as const;

/** Screen-aligned text at geographic points. Points without a height sit on the ground. Not pickable by callers. */
export function addLabels(
  viewer: Viewer, labels: readonly { position: GeoPoint; text: string }[], style: { font?: string } = {},
): LabelLayer {
  const collection = new LabelCollection({ scene: viewer.scene });
  for (const { position: p, text } of labels) {
    if (![p.lon, p.lat, p.height ?? 0].every(Number.isFinite)) throw new Error(`Label "${text}" has a non-finite position`);
    collection.add({
      position: Cartesian3.fromDegrees(p.lon, p.lat, p.height ?? 0),
      heightReference: p.height === undefined ? HeightReference.CLAMP_TO_GROUND : HeightReference.NONE,
      text,
      ...LABEL_LOOK,
      ...(style.font && { font: style.font }),
      horizontalOrigin: HorizontalOrigin.CENTER,
      verticalOrigin: VerticalOrigin.CENTER,
    });
  }
  viewer.scene.primitives.add(collection);
  let destroyed = false;
  return {
    setVisible(visible) {
      collection.show = visible;
      viewer.scene.requestRender();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      // remove() destroys the collection.
      viewer.scene.primitives.remove(collection);
      viewer.scene.requestRender();
    },
  };
}
