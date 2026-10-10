// Ломаная с параметризацией по длине — та же, что в tsim/geom.py.
import type { P2 } from "./types";

export class Path {
  readonly pts: P2[];
  readonly cum: Float64Array;
  readonly length: number;

  constructor(pts: P2[]) {
    this.pts = pts;
    this.cum = new Float64Array(pts.length);
    for (let i = 1; i < pts.length; i++) {
      const dx = pts[i][0] - pts[i - 1][0];
      const dy = pts[i][1] - pts[i - 1][1];
      this.cum[i] = this.cum[i - 1] + Math.hypot(dx, dy);
    }
    this.length = this.cum[pts.length - 1];
  }

  /** Точка и угол направления на расстоянии s. */
  at(s: number, out: { x: number; y: number; h: number }) {
    const pts = this.pts;
    const cum = this.cum;
    if (s <= 0) s = 0;
    if (s >= this.length) s = this.length;
    let lo = 0;
    let hi = pts.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (cum[mid] <= s) lo = mid;
      else hi = mid;
    }
    const a = pts[lo];
    const b = pts[lo + 1] ?? pts[lo];
    const seg = cum[lo + 1] - cum[lo];
    const t = seg > 0 ? (s - cum[lo]) / seg : 0;
    out.x = a[0] + (b[0] - a[0]) * t;
    out.y = a[1] + (b[1] - a[1]) * t;
    out.h = Math.atan2(b[1] - a[1], b[0] - a[0]);
    return out;
  }
}

export function offsetLine(pts: P2[], d: number): P2[] {
  const out: P2[] = [];
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    let nx: number, ny: number;
    if (i === 0 || i === pts.length - 1) {
      const a = i === 0 ? pts[0] : pts[i - 1];
      const b = i === 0 ? pts[1] : pts[i];
      const l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      nx = -(b[1] - a[1]) / l;
      ny = (b[0] - a[0]) / l;
      out.push([p[0] + nx * d, p[1] + ny * d]);
    } else {
      const a = pts[i - 1];
      const b = pts[i + 1];
      const l1 = Math.hypot(p[0] - a[0], p[1] - a[1]) || 1;
      const l2 = Math.hypot(b[0] - p[0], b[1] - p[1]) || 1;
      const n1x = -(p[1] - a[1]) / l1;
      const n1y = (p[0] - a[0]) / l1;
      const n2x = -(b[1] - p[1]) / l2;
      const n2y = (b[0] - p[0]) / l2;
      let mx = n1x + n2x;
      let my = n1y + n2y;
      const ml = Math.hypot(mx, my) || 1;
      mx /= ml;
      my /= ml;
      const k = 1 / Math.max(0.3, mx * n1x + my * n1y);
      out.push([p[0] + mx * d * k, p[1] + my * d * k]);
    }
  }
  return out;
}

export function lerpAngle(a: number, b: number, t: number) {
  let d = b - a;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
}

export function clamp(x: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, x));
}

export function smooth(t: number) {
  t = clamp(t, 0, 1);
  return t * t * (3 - 2 * t);
}
