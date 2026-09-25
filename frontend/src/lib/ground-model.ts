/**
 * Pure logic for the ground imagery: line data packed into typed arrays with a
 * grid index, so a map tile visits only the lines that can touch it. No DOM,
 * no Cesium. Coordinates stay integers of degrees * 1e5 throughout.
 */

/** Grid cell edge, in degrees * 1e5: 0.01°, about 1.1 km. */
const CELL = 1000;

export interface Lines {
  /** x, y pairs of every line, back to back. */
  xy: Int32Array;
  /** Line i is points start[i] to start[i + 1] - 1. */
  start: Uint32Array;
  /** west, south, east, north of each line. */
  box: Int32Array;
  // Grid over the data's extent: cell c lists lines cellItems[cellStart[c] .. cellStart[c + 1]).
  x0: number;
  y0: number;
  cols: number;
  rows: number;
  cellStart: Uint32Array;
  cellItems: Uint32Array;
  /** Per-line stamp so a line spanning several cells is visited once per query. */
  seen: Uint32Array;
  stamp: number;
}

/**
 * Packs lines given either as degree arrays (`delta: false`) or as the ground
 * data's delta-encoded integers of degrees * 1e5 (`delta: true`): the first
 * point absolute, each later one an offset from the previous. Lines under two
 * points are dropped.
 */
export function packLines(lines: readonly (readonly number[])[], delta: boolean): Lines {
  const kept = lines.filter((l) => l.length >= 4);
  const n = kept.length;
  const start = new Uint32Array(n + 1);
  for (let i = 0; i < n; i++) start[i + 1] = start[i]! + kept[i]!.length / 2;
  const xy = new Int32Array(start[n]! * 2);
  const box = new Int32Array(n * 4);
  let o = 0;
  for (let i = 0; i < n; i++) {
    const l = kept[i]!;
    let x = 0, y = 0;
    let w = Infinity, s = Infinity, e = -Infinity, nn = -Infinity;
    for (let j = 0; j < l.length; j += 2) {
      if (delta) {
        x = j === 0 ? l[0]! : x + l[j]!;
        y = j === 0 ? l[1]! : y + l[j + 1]!;
      } else {
        x = Math.round(l[j]! * 1e5);
        y = Math.round(l[j + 1]! * 1e5);
      }
      xy[o++] = x;
      xy[o++] = y;
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > nn) nn = y;
    }
    box.set([w, s, e, nn], i * 4);
  }

  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < n; i++) {
    x0 = Math.min(x0, box[i * 4]!);
    y0 = Math.min(y0, box[i * 4 + 1]!);
    x1 = Math.max(x1, box[i * 4 + 2]!);
    y1 = Math.max(y1, box[i * 4 + 3]!);
  }
  if (n === 0) x0 = y0 = x1 = y1 = 0;
  const cols = Math.floor((x1 - x0) / CELL) + 1;
  const rows = Math.floor((y1 - y0) / CELL) + 1;
  // Two passes, count then fill: one flat array instead of a JS array per cell.
  const cellStart = new Uint32Array(cols * rows + 1);
  const eachCell = (i: number, visit: (c: number) => void): void => {
    const cx0 = Math.floor((box[i * 4]! - x0) / CELL), cx1 = Math.floor((box[i * 4 + 2]! - x0) / CELL);
    const cy0 = Math.floor((box[i * 4 + 1]! - y0) / CELL), cy1 = Math.floor((box[i * 4 + 3]! - y0) / CELL);
    for (let cy = cy0; cy <= cy1; cy++) for (let cx = cx0; cx <= cx1; cx++) visit(cy * cols + cx);
  };
  for (let i = 0; i < n; i++) eachCell(i, (c) => { cellStart[c + 1]!++; });
  for (let c = 0; c < cols * rows; c++) cellStart[c + 1]! += cellStart[c]!;
  const cellItems = new Uint32Array(cellStart[cols * rows]!);
  const fillAt = cellStart.slice(0, cols * rows);
  for (let i = 0; i < n; i++) eachCell(i, (c) => { cellItems[fillAt[c]!++] = i; });

  return { xy, start, box, x0, y0, cols, rows, cellStart, cellItems, seen: new Uint32Array(n), stamp: 0 };
}

/** Calls `visit` once for each line whose bounding box meets the box (degrees * 1e5, inclusive). */
export function query(
  lines: Lines, west: number, south: number, east: number, north: number, visit: (i: number) => void,
): void {
  const { box, x0, y0, cols, rows, cellStart, cellItems, seen } = lines;
  const cx0 = Math.max(0, Math.floor((west - x0) / CELL)), cx1 = Math.min(cols - 1, Math.floor((east - x0) / CELL));
  const cy0 = Math.max(0, Math.floor((south - y0) / CELL)), cy1 = Math.min(rows - 1, Math.floor((north - y0) / CELL));
  if (cx0 > cx1 || cy0 > cy1) return;
  const stamp = ++lines.stamp;
  for (let cy = cy0; cy <= cy1; cy++) {
    for (let cx = cx0; cx <= cx1; cx++) {
      const c = cy * cols + cx;
      for (let k = cellStart[c]!; k < cellStart[c + 1]!; k++) {
        const i = cellItems[k]!;
        if (seen[i] === stamp) continue;
        seen[i] = stamp;
        if (box[i * 4]! > east || box[i * 4 + 2]! < west || box[i * 4 + 1]! > north || box[i * 4 + 3]! < south) continue;
        visit(i);
      }
    }
  }
}
