// Статичная сеть из скомпилированной разметки: асфальт, тротуары, разметка.
import * as THREE from "three";
import type { P2, RenderJ } from "../types";
import { offsetLine, Path } from "../geom";

const Y_ASPHALT = 0.0;
const Y_MARK = 0.025;
const Y_WALK = 0.16;
const Y_MEDIAN = 0.2;

/** Сборщик треугольников в мировых координатах (x, y) → сцена (x, h, -y). */
export class Builder {
  pos: number[] = [];
  nor: number[] = [];
  uv: number[] = [];
  idx: number[] = [];

  vert(x: number, y: number, h: number, nx = 0, ny = 1, nz = 0) {
    this.pos.push(x, h, -y);
    this.nor.push(nx, ny, nz);
    this.uv.push(x / 6, y / 6);
    return this.pos.length / 3 - 1;
  }

  /** Плоская лента вдоль ломаной. */
  ribbon(pts: P2[], width: number, h: number) {
    if (pts.length < 2) return;
    const l = offsetLine(pts, width / 2);
    const r = offsetLine(pts, -width / 2);
    this.strip(l, r, h);
  }

  strip(l: P2[], r: P2[], h: number) {
    const base = this.pos.length / 3;
    for (let i = 0; i < l.length; i++) {
      this.vert(l[i][0], l[i][1], h);
      this.vert(r[i][0], r[i][1], h);
    }
    for (let i = 0; i < l.length - 1; i++) {
      const a = base + i * 2;
      // против часовой при взгляде сверху
      this.idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
  }

  /** Вертикальная стенка вдоль ломаной (бордюр). */
  wall(pts: P2[], h0: number, h1: number, outward: number) {
    const base = this.pos.length / 3;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[Math.max(0, i - 1)];
      const b = pts[Math.min(pts.length - 1, i + 1)];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const l = Math.hypot(dx, dy) || 1;
      // нормаль влево от направления, outward = +1 / -1
      const nx = (-dy / l) * outward;
      const ny = (dx / l) * outward;
      this.vert(pts[i][0], pts[i][1], h0, nx, 0, -ny);
      this.vert(pts[i][0], pts[i][1], h1, nx, 0, -ny);
    }
    for (let i = 0; i < pts.length - 1; i++) {
      const a = base + i * 2;
      if (outward > 0) this.idx.push(a, a + 1, a + 2, a + 2, a + 1, a + 3);
      else this.idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  }

  polygon(pts: P2[], h: number) {
    if (pts.length < 3) return;
    const contour = pts.map((p) => new THREE.Vector2(p[0], p[1]));
    if (THREE.ShapeUtils.isClockWise(contour)) contour.reverse();
    const tris = THREE.ShapeUtils.triangulateShape(contour, []);
    const base = this.pos.length / 3;
    for (const v of contour) this.vert(v.x, v.y, h);
    for (const t of tris) this.idx.push(base + t[0], base + t[1], base + t[2]);
  }

  tri(a: P2, b: P2, c: P2, h: number) {
    const base = this.pos.length / 3;
    this.vert(a[0], a[1], h);
    this.vert(b[0], b[1], h);
    this.vert(c[0], c[1], h);
    // ориентация вверх
    const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    if (cross > 0) this.idx.push(base, base + 1, base + 2);
    else this.idx.push(base, base + 2, base + 1);
  }

  quad(a: P2, b: P2, c: P2, d: P2, h: number) {
    this.tri(a, b, c, h);
    this.tri(a, c, d, h);
  }

  geometry() {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(this.nor, 3));
    g.setAttribute("uv", new THREE.Float32BufferAttribute(this.uv, 2));
    g.setIndex(this.idx);
    g.computeBoundingSphere();
    return g;
  }
}

function noiseTexture(base: string, amp: number, size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  const img = ctx.getImageData(0, 0, size, size);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (rnd() - 0.5) * amp;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n;
  }
  ctx.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

/** Расстояние от точки внутри рамки до её края по направлению. */
function rayBox(p: P2, d: P2, box: [number, number, number, number]) {
  let t = 1e9;
  if (d[0] > 1e-6) t = Math.min(t, (box[2] - p[0]) / d[0]);
  if (d[0] < -1e-6) t = Math.min(t, (box[0] - p[0]) / d[0]);
  if (d[1] > 1e-6) t = Math.min(t, (box[3] - p[1]) / d[1]);
  if (d[1] < -1e-6) t = Math.min(t, (box[1] - p[1]) / d[1]);
  return Math.max(0, t);
}

function slicePath(p: Path, s0: number, s1: number): P2[] {
  const o = { x: 0, y: 0, h: 0 };
  const out: P2[] = [];
  p.at(s0, o);
  out.push([o.x, o.y]);
  for (let i = 1; i < p.pts.length - 1; i++) if (p.cum[i] > s0 && p.cum[i] < s1) out.push(p.pts[i]);
  p.at(s1, o);
  out.push([o.x, o.y]);
  return out;
}

function dashes(pts: P2[], dash: number, gap: number): P2[][] {
  const path = new Path(pts);
  const out: P2[][] = [];
  const o = { x: 0, y: 0, h: 0 };
  for (let s = gap * 0.5; s < path.length; s += dash + gap) {
    const e = Math.min(path.length, s + dash);
    if (e - s < 0.5) continue;
    const seg: P2[] = [];
    const n = Math.max(1, Math.ceil((e - s) / 1.0));
    for (let i = 0; i <= n; i++) {
      path.at(s + ((e - s) * i) / n, o);
      seg.push([o.x, o.y]);
    }
    out.push(seg);
  }
  return out;
}

// стрелки разметки в местных координатах: x — вперёд по полосе, y — влево
const ARROW: Record<string, P2[]> = {
  straight: [[-2.8, 0], [1.2, 0]],
  left: [[-2.8, 0], [-0.2, 0], [0.55, 0.35], [0.95, 1.15]],
  right: [[-2.8, 0], [-0.2, 0], [0.55, -0.35], [0.95, -1.15]],
  uturn: [[-2.8, 0], [0.6, 0], [1.05, 0.45], [0.75, 1.05], [-0.1, 1.05]],
};

function arrowShape(b: Builder, pos: P2, dir: number, turns: string[], h: number) {
  const c = Math.cos(dir);
  const s = Math.sin(dir);
  const k = 1.25;
  const tr = (p: P2): P2 => [pos[0] + (p[0] * c - p[1] * s) * k, pos[1] + (p[0] * s + p[1] * c) * k];
  for (const t of turns) {
    const line = ARROW[t];
    if (!line) continue;
    const pts = line.map(tr);
    // наконечник
    const a = line[line.length - 2];
    const e = line[line.length - 1];
    const dx = e[0] - a[0];
    const dy = e[1] - a[1];
    const l = Math.hypot(dx, dy);
    const ux = dx / l;
    const uy = dy / l;
    const shaftEnd: P2 = [e[0] - ux * 0.1, e[1] - uy * 0.1];
    b.ribbon(pts.slice(0, -1).concat([tr(shaftEnd)]), 0.17 * k, h);
    const tip: P2 = [e[0] + ux * 1.2, e[1] + uy * 1.2];
    const l1: P2 = [e[0] - uy * 0.42, e[1] + ux * 0.42];
    const r1: P2 = [e[0] + uy * 0.42, e[1] - ux * 0.42];
    b.tri(tr(tip), tr(l1), tr(r1), h);
  }
}

export interface RoadMeshes {
  group: THREE.Group;
  pick: THREE.Mesh[];
}

export function buildRoads(R: RenderJ, groundBox: [number, number, number, number]): RoadMeshes {
  const group = new THREE.Group();
  const pick: THREE.Mesh[] = [];

  const asphaltTex = noiseTexture("#e8e8e8", 30);
  const asphalt = new THREE.MeshStandardMaterial({ color: "#7d838e", roughness: 0.92, metalness: 0, map: asphaltTex });
  const walkTex = noiseTexture("#f2f2f2", 16);
  const walk = new THREE.MeshStandardMaterial({ color: "#d9d4ca", roughness: 0.88, map: walkTex });
  const curb = new THREE.MeshStandardMaterial({ color: "#eeeae2", roughness: 0.75, side: THREE.DoubleSide });
  const grass = new THREE.MeshStandardMaterial({ color: "#7d9a5c", roughness: 0.95 });
  const paint = new THREE.MeshStandardMaterial({
    color: "#f4f3ee", roughness: 0.55, emissive: "#3a3a36", polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
  });

  // плита-диорама: газон сверху, срез грунта по краям
  const [gx0, gy0, gx1, gy1] = groundBox;
  const rad = 16;
  const shape = new THREE.Shape();
  shape.moveTo(gx0 + rad, gy0);
  shape.lineTo(gx1 - rad, gy0);
  shape.quadraticCurveTo(gx1, gy0, gx1, gy0 + rad);
  shape.lineTo(gx1, gy1 - rad);
  shape.quadraticCurveTo(gx1, gy1, gx1 - rad, gy1);
  shape.lineTo(gx0 + rad, gy1);
  shape.quadraticCurveTo(gx0, gy1, gx0, gy1 - rad);
  shape.lineTo(gx0, gy0 + rad);
  shape.quadraticCurveTo(gx0, gy0, gx0 + rad, gy0);
  const depth = 9;
  const slabGeo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: 0.8, bevelSize: 0.8, bevelSegments: 3, curveSegments: 10 });
  slabGeo.rotateX(-Math.PI / 2);
  slabGeo.translate(0, -depth - 0.8 - 0.06, 0);
  const groundTex = noiseTexture("#ececec", 22, 128);
  groundTex.repeat.set(0.05, 0.05);
  const slab = new THREE.Mesh(slabGeo, [
    new THREE.MeshStandardMaterial({ color: "#93ad6c", roughness: 1, map: groundTex }),
    new THREE.MeshStandardMaterial({ color: "#6a5646", roughness: 1 }),
  ]);
  slab.receiveShadow = true;
  group.add(slab);

  // асфальт: дороги, продолжения за край сети, перекрёстки
  const ab = new Builder();
  const ext: { l: P2[]; r: P2[] }[] = [];
  for (const r of R.roads) {
    ab.strip(r.left, r.right, Y_ASPHALT);
    r.boundary.forEach((isB, end) => {
      if (!isB) return;
      const L = end === 0 ? r.left : r.left.slice().reverse();
      const Rr = end === 0 ? r.right : r.right.slice().reverse();
      // от края наружу: точки 0 и 1 упорядочены от края
      const dx = L[0][0] - L[1][0];
      const dy = L[0][1] - L[1][1];
      const d = Math.hypot(dx, dy) || 1;
      const far = rayBox(L[0], [dx / d, dy / d], groundBox) + 0.6;
      const l: P2[] = [[L[0][0] + (dx / d) * far, L[0][1] + (dy / d) * far], L[0]];
      const rr: P2[] = [[Rr[0][0] + (dx / d) * far, Rr[0][1] + (dy / d) * far], Rr[0]];
      ext.push({ l, r: rr });
    });
  }
  for (const e of ext) ab.strip(e.l, e.r, Y_ASPHALT);
  for (const j of R.junctions) {
    ab.polygon(j.pts, Y_ASPHALT);
    const jb = new Builder();
    jb.polygon(j.pts, 0.3);
    const m = new THREE.Mesh(jb.geometry(), new THREE.MeshBasicMaterial({ visible: false }));
    m.userData = { pick: "junction", id: j.id };
    pick.push(m);
    group.add(m);
  }
  const asphaltMesh = new THREE.Mesh(ab.geometry(), asphalt);
  asphaltMesh.receiveShadow = true;
  group.add(asphaltMesh);

  // тротуары: верх, бордюр со стороны дороги и внешняя стенка
  const wb = new Builder();
  const cb = new Builder();
  for (const s of R.sidewalks) {
    wb.ribbon(s.pts, s.width, Y_WALK);
    cb.wall(offsetLine(s.pts, s.width / 2), -0.06, Y_WALK, 1);
    cb.wall(offsetLine(s.pts, -s.width / 2), -0.06, Y_WALK, -1);
  }
  const walkMesh = new THREE.Mesh(wb.geometry(), walk);
  walkMesh.receiveShadow = true;
  group.add(walkMesh);
  const curbMesh = new THREE.Mesh(cb.geometry(), curb);
  curbMesh.receiveShadow = true;
  group.add(curbMesh);

  // разделители с газоном
  const mb = new Builder();
  const mc = new Builder();
  for (const m of R.medians) {
    const pts = m.pts;
    const p = new Path(pts);
    if (p.length < 8) continue;
    mb.ribbon(pts, m.width, Y_MEDIAN);
    mc.wall(offsetLine(pts, m.width / 2), 0, Y_MEDIAN, 1);
    mc.wall(offsetLine(pts, -m.width / 2), 0, Y_MEDIAN, -1);
  }

  // разметка
  const pb = new Builder();
  for (const l of R.lines) {
    if (l.style === "dashed") for (const d of dashes(l.pts, 3, 6)) pb.ribbon(d, l.w, Y_MARK);
    else pb.ribbon(l.pts, l.w, Y_MARK);
  }
  for (const e of ext) {
    // осевая на продолжениях за краем
    const mid: P2[] = e.l.map((p, i) => [(p[0] + e.r[i][0]) / 2, (p[1] + e.r[i][1]) / 2]);
    for (const d of dashes(mid, 3, 6)) pb.ribbon(d, 0.15, Y_MARK);
  }
  for (const s of R.stops) pb.ribbon(s.pts, s.w, Y_MARK);
  for (const a of R.arrows) arrowShape(pb, a.pos, a.dir, a.turns, Y_MARK + 0.002);
  for (const z of R.zebras) {
    const p = new Path(z.pts);
    const o = { x: 0, y: 0, h: 0 };
    const trim = 1.9;
    for (let s = trim; s < p.length - trim; s += 1.0) {
      p.at(s, o);
      const ux = Math.cos(o.h);
      const uy = Math.sin(o.h);
      const vx = -uy;
      const vy = ux;
      const hw = 0.28;
      const hl = z.width / 2;
      pb.quad(
        [o.x - ux * hw - vx * hl, o.y - uy * hw - vy * hl],
        [o.x + ux * hw - vx * hl, o.y + uy * hw - vy * hl],
        [o.x + ux * hw + vx * hl, o.y + uy * hw + vy * hl],
        [o.x - ux * hw + vx * hl, o.y - uy * hw + vy * hl],
        Y_MARK,
      );
    }
  }
  // место кармана до его начала: газонный островок, перед карманом — штриховка отгона
  const islands: P2[][] = [];
  for (const hz of R.hatches) {
    const full = new Path(hz.pts);
    const taper = Math.min(25, full.length);
    const cut = full.length - taper;
    let hatchPts = hz.pts;
    if (cut > 6) {
      islands.push(slicePath(full, 0, cut - 1.5).map((p) => p));
      hatchPts = slicePath(full, cut, full.length);
      mb.ribbon(islands[islands.length - 1], hz.width - 0.5, Y_MEDIAN);
      mc.wall(offsetLine(islands[islands.length - 1], (hz.width - 0.5) / 2), 0, Y_MEDIAN, 1);
      mc.wall(offsetLine(islands[islands.length - 1], -(hz.width - 0.5) / 2), 0, Y_MEDIAN, -1);
    }
    const p = new Path(hatchPts);
    const o = { x: 0, y: 0, h: 0 };
    const o2 = { x: 0, y: 0, h: 0 };
    for (let s = 1.5; s < p.length - 1.5; s += 2.6) {
      p.at(s, o);
      p.at(Math.min(p.length, s + 1.6), o2);
      const nx = -Math.sin(o.h);
      const ny = Math.cos(o.h);
      const w = hz.width / 2 - 0.25;
      pb.ribbon([[o.x + nx * w, o.y + ny * w], [o2.x - nx * w, o2.y - ny * w]], 0.3, Y_MARK);
    }
    pb.ribbon(offsetLine(hatchPts, hz.width / 2 - 0.1), 0.15, Y_MARK);
    pb.ribbon(offsetLine(hatchPts, -hz.width / 2 + 0.1), 0.15, Y_MARK);
  }
  const islandMesh = new THREE.Mesh(mb.geometry(), grass);
  islandMesh.receiveShadow = true;
  group.add(islandMesh, new THREE.Mesh(mc.geometry(), curb));
  const paintMesh = new THREE.Mesh(pb.geometry(), paint);
  paintMesh.receiveShadow = true;
  group.add(paintMesh);

  return { group, pick };
}
