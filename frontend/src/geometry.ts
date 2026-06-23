// 轻量多边形几何：重叠检测 + 包围盒，用于交互画布的实时反馈。

export type Pt = [number, number];

export function bbox(pts: Pt[]): { minx: number; miny: number; maxx: number; maxy: number } {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const [x, y] of pts) {
    if (x < minx) minx = x;
    if (y < miny) miny = y;
    if (x > maxx) maxx = x;
    if (y > maxy) maxy = y;
  }
  return { minx, miny, maxx, maxy };
}

function segIntersect(a: Pt, b: Pt, c: Pt, d: Pt): boolean {
  const d1 = cross(c, d, a);
  const d2 = cross(c, d, b);
  const d3 = cross(a, b, c);
  const d4 = cross(a, b, d);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) &&
      ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
  return false;
}

function cross(o: Pt, a: Pt, b: Pt): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}

function pointInPoly(p: Pt, poly: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if (((yi > p[1]) !== (yj > p[1])) &&
        p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// 两多边形是否重叠（含包含）。先包围盒快速排除。
export function polysOverlap(a: Pt[], b: Pt[]): boolean {
  const ba = bbox(a), bb = bbox(b);
  if (ba.maxx < bb.minx || bb.maxx < ba.minx || ba.maxy < bb.miny || bb.maxy < ba.miny)
    return false;
  for (let i = 0; i < a.length - 1; i++)
    for (let j = 0; j < b.length - 1; j++)
      if (segIntersect(a[i], a[i + 1], b[j], b[j + 1])) return true;
  // 边不相交时检查包含关系
  return pointInPoly(a[0], b) || pointInPoly(b[0], a);
}
