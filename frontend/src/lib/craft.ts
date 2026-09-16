import {
  BoundingSphere, BoxGeometry, Cartesian3, Color, ColorGeometryInstanceAttribute, CylinderGeometry, GeometryInstance,
  Matrix3, Matrix4, PerInstanceColorAppearance, Primitive, Transforms,
} from "cesium";
import type { Viewer } from "cesium";

export interface CraftMarker {
  /** Places the craft at `position`, nose pointing along `direction` (a world-space vector; may be zero-length). */
  setPose(position: Cartesian3, direction: Cartesian3): void;
  setVisible(visible: boolean): void;
  destroy(): void;
}

/**
 * The geometry is baked in world coordinates around this point instead of at
 * the origin. Unless the scene is `scene3DOnly` (ours is not), the primitive
 * pipeline projects every vertex to 2D at build time, and a point inside the
 * Earth has no cartographic position — "Could not project point". The model
 * matrix subtracts the anchor again each frame, so where it sits is irrelevant.
 */
const ANCHOR = Cartesian3.fromDegrees(0, 0);
const UNANCHOR = Cartesian3.negate(ANCHOR, new Cartesian3());

/**
 * A slender craft — tube body, tapered nose, four tail fins — pointing along
 * its direction of travel. One lit primitive: cheap to draw, and the round
 * body shows form. It grows with camera distance so it never drops below
 * `minimumPixelLength` on screen, and never shrinks below true size up close.
 *
 * Local frame: nose along +X, origin at mid-length, +Z away from the ellipsoid.
 * Only works in 3D scene mode — `Primitive.modelMatrix` throws elsewhere.
 */
export function addCraftMarker(
  viewer: Viewer,
  options: { color?: string; lengthM?: number; minimumPixelLength?: number } = {},
): CraftMarker {
  const scene = viewer.scene;
  const lengthM = options.lengthM ?? 60;
  const minimumPixelLength = options.minimumPixelLength ?? 34;
  const bodyColor = Color.fromCssColorString(options.color ?? "#f5f7fa");
  // Nose and fins a step darker so the silhouette reads against a grey map.
  const trimColor = bodyColor.darken(0.3, new Color());

  const vertexFormat = PerInstanceColorAppearance.VERTEX_FORMAT; // the lit shader needs normals
  const radius = lengthM / 24; // body 9x longer than wide
  const noseLength = lengthM / 4;
  const bodyLength = lengthM - noseLength;
  // CylinderGeometry runs along its own Z, centred on its origin; this turns Z into the nose axis.
  const alongX = Matrix3.fromRotationY(Math.PI / 2);
  const placed = (x: number, rotation: Matrix3): Matrix4 => Matrix4.multiplyByMatrix3(
    Matrix4.fromTranslation(new Cartesian3(ANCHOR.x + x, ANCHOR.y, ANCHOR.z)), rotation, new Matrix4(),
  );
  const part = (geometry: CylinderGeometry | BoxGeometry, modelMatrix: Matrix4, color: Color): GeometryInstance =>
    new GeometryInstance({ geometry, modelMatrix, attributes: { color: ColorGeometryInstanceAttribute.fromColor(color) } });
  // Fin root sits inside the body so there is no seam; the box is off-centre so rotating it about X fans the fins out.
  const fin = (): BoxGeometry => new BoxGeometry({
    minimum: new Cartesian3(-lengthM / 2, -lengthM * 0.005, radius * 0.5),
    maximum: new Cartesian3(-lengthM / 2 + lengthM * 0.14, lengthM * 0.005, radius * 2.4),
    vertexFormat,
  });
  const primitive = scene.primitives.add(new Primitive({
    geometryInstances: [
      part(new CylinderGeometry({ length: bodyLength, topRadius: radius, bottomRadius: radius, slices: 24, vertexFormat }),
        placed(-noseLength / 2, alongX), bodyColor),
      part(new CylinderGeometry({ length: noseLength, topRadius: 0, bottomRadius: radius, slices: 24, vertexFormat }),
        placed(bodyLength / 2, alongX), trimColor),
      ...[0, 1, 2, 3].map(k => part(fin(), placed(0, Matrix3.fromRotationX((k * Math.PI) / 2)), trimColor)),
    ],
    appearance: new PerInstanceColorAppearance({ translucent: false, closed: true }),
    allowPicking: false,
    asynchronous: false, // tiny geometry; building on the main thread means it is there on the first frame
  })) as Primitive;

  const rotation = new Matrix3(); // columns are the local axes in world space
  const pose = new Matrix4(); // rotation and position, unscaled
  const heading = new Cartesian3();
  const sphere = new BoundingSphere(); // zero radius at the craft: what the camera measures distance to
  let posed = false;
  let oriented = false;
  let shown = true;
  const applyShow = (): void => { primitive.show = shown && posed; };
  applyShow();

  const fit = (): void => {
    if (!posed) return;
    // ponytail: assumes the craft is seen side-on; nose-on it looks shorter than minimumPixelLength.
    const metresPerPixel = scene.camera.getPixelSize(sphere, scene.drawingBufferWidth, scene.drawingBufferHeight);
    const scale = Math.max(1, (minimumPixelLength * metresPerPixel) / lengthM);
    Matrix4.multiplyByUniformScale(pose, scale, primitive.modelMatrix);
    Matrix4.multiplyByTranslation(primitive.modelMatrix, UNANCHOR, primitive.modelMatrix);
  };
  scene.preRender.addEventListener(fit);

  let destroyed = false;
  return {
    setPose(position, direction) {
      if (![position.x, position.y, position.z].every(Number.isFinite)) throw new Error("Craft position is not finite");
      const m2 = Cartesian3.magnitudeSquared(direction);
      if (Number.isFinite(m2) && m2 > 0) {
        // Columns come out as heading, sideways, away from the ellipsoid — exactly local X, Y, Z.
        // It copies the velocity in verbatim, so it has to be unit length first.
        Cartesian3.normalize(direction, heading);
        Transforms.rotationMatrixFromPositionVelocity(position, heading, scene.ellipsoid, rotation);
        oriented = true;
      } else if (!oriented) {
        // Nothing to point along yet: level with the nose east, rather than an identity frame stuck in the ground.
        Matrix4.getMatrix3(Transforms.eastNorthUpToFixedFrame(position, scene.ellipsoid), rotation);
      }
      Cartesian3.clone(position, sphere.center);
      Matrix4.fromRotationTranslation(rotation, position, pose);
      posed = true;
      applyShow();
    },
    setVisible(visible) {
      shown = visible;
      applyShow();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      scene.preRender.removeEventListener(fit);
      scene.primitives.remove(primitive);
    },
  };
}
