// Машины и пешеходы: инстансы, позиции по пути и сглаживание между кадрами.
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { CarRow, NetJ, PedRow } from "../types";
import { FLAG } from "../types";
import { lerpAngle, Path } from "../geom";
import { radialTexture } from "./city";
import type { Daylight } from "./stage";

export const CAR_COLORS = ["#f2f2ef", "#b9bec6", "#5b626d", "#22262d", "#2d5fa8", "#c8352f", "#1f8a8a", "#d8c7a0",
  "#5e7a3a", "#7a2236", "#7fb6e0", "#e07a2e"];
const TAXI = "#f2c230";
const CLOTHES = ["#e4572e", "#29335c", "#f3a712", "#669bbc", "#a8c686", "#2e2e2e", "#d3d0cb", "#8e44ad", "#e98a9b", "#3a7d44"];
const SKIN = ["#f1c7a5", "#d9a47c", "#a5714c", "#6f4a32", "#e8b896"];

interface Spec {
  L: number;
  W: number;
  H: number;
  cab: [number, number, number, number]; // начало, длина (доли L), высота низа, высота кабины
  bus?: boolean;
}

const SPECS: Spec[] = [
  { L: 4.4, W: 1.8, H: 1.42, cab: [-0.36, 0.56, 0.86, 0.5] },   // седан
  { L: 3.9, W: 1.75, H: 1.48, cab: [-0.44, 0.62, 0.86, 0.55] },  // хэтчбек
  { L: 4.9, W: 1.95, H: 1.72, cab: [-0.42, 0.66, 1.0, 0.62] },   // кроссовер
  { L: 4.5, W: 1.8, H: 1.45, cab: [-0.36, 0.56, 0.86, 0.5] },    // такси
  { L: 5.6, W: 2.0, H: 2.25, cab: [-0.46, 0.8, 1.0, 1.1] },      // фургон
  { L: 11.5, W: 2.5, H: 3.1, cab: [-0.48, 0.95, 1.1, 1.6], bus: true }, // автобус
];

interface KindMeshes {
  body: THREE.InstancedMesh;
  glass: THREE.InstancedMesh;
  head: THREE.InstancedMesh;
  tail: THREE.InstancedMesh;
  blink: THREE.InstancedMesh;
  n: number;
}

interface Frame {
  t: number;
  cars: Map<number, Pose>;
  peds: Map<number, Pose>;
}

interface Pose {
  x: number;
  y: number;
  h: number;
  link: number;
  s: number;
  lat: number;
}

const CAP = 1600;

function flat(gs: THREE.BufferGeometry[]) {
  return mergeGeometries(gs.map((g) => (g.index ? g.toNonIndexed() : g)));
}

function carParts(sp: Spec) {
  const { L, W, cab } = sp;
  const body: THREE.BufferGeometry[] = [];
  const low = new RoundedBoxGeometry(L, cab[2] - 0.22, W, 2, 0.16);
  low.translate(0, 0.22 + (cab[2] - 0.22) / 2, 0);
  body.push(low);
  // крыша — цвет кузова
  const roofL = L * cab[1] * (sp.bus ? 1 : 0.86);
  const roof = new RoundedBoxGeometry(roofL, 0.09, W * 0.86, 1, 0.04);
  roof.translate(L * (cab[0] + cab[1] / 2), cab[2] + cab[3] + 0.03, 0);
  body.push(roof);
  if (sp.bus) {
    const belt = new THREE.BoxGeometry(L * 0.98, 0.25, W * 1.005);
    belt.translate(0, cab[2] + cab[3] * 0.62, 0);
    body.push(belt);
  }
  // стёкла
  const glass = new THREE.BoxGeometry(L * cab[1], cab[3], W * 0.84);
  glass.translate(L * (cab[0] + cab[1] / 2), cab[2] + cab[3] / 2, 0);
  // колёса и днище тёмной полосой
  const under = new THREE.BoxGeometry(L * 0.92, 0.32, W * 0.94);
  under.translate(0, 0.2, 0);
  const lights = (front: boolean) => {
    const g: THREE.BufferGeometry[] = [];
    for (const side of [-1, 1]) {
      const b = new THREE.BoxGeometry(0.06, sp.bus ? 0.28 : 0.13, sp.bus ? 0.32 : 0.36);
      b.translate((front ? 1 : -1) * (L / 2 + 0.01), sp.bus ? 0.65 : cab[2] - 0.12, side * (W / 2 - 0.26));
      g.push(b);
    }
    return flat(g);
  };
  const blink: THREE.BufferGeometry[] = [];
  for (const fx of [-1, 1]) {
    const b = new THREE.BoxGeometry(0.08, 0.09, 0.14);
    b.translate(fx * (L / 2 + 0.02), (sp.bus ? 0.65 : cab[2] - 0.12) + 0.1, W / 2 - 0.08);
    blink.push(b);
  }
  return { body: flat(body), glass, under, head: lights(true), tail: lights(false), blink: flat(blink) };
}

export class Actors {
  readonly group = new THREE.Group();
  private kinds: KindMeshes[] = [];
  private under: THREE.InstancedMesh[] = [];
  private beams: THREE.InstancedMesh;
  private beamMat: THREE.MeshBasicMaterial;
  private headMat: THREE.MeshBasicMaterial;
  private pedBody: THREE.InstancedMesh;
  private pedHead: THREE.InstancedMesh;
  private links: Path[];
  private edges: Path[];
  private next: number[][];
  /** Буфер последних кадров: отрисовка идёт с задержкой между двумя известными кадрами. */
  private frames: Frame[] = [];
  private rows = new Map<number, CarRow>();
  private pedRows = new Map<number, PedRow>();
  private born = new Map<number, number>();
  /** Задняя ось машины: тянется за передней точкой, отсюда плавный поворот кузова. */
  private rear = new Map<number, { x: number; y: number }>();
  private pedHeading = new Map<number, number>();
  private tLast = 0;
  private frameGap = 1 / 15;
  private lastRender = 0;
  /** Положения в последнем кадре отрисовки: для выбора и слежения. */
  readonly carPos = new Map<number, { x: number; y: number; h: number }>();
  readonly pedPos = new Map<number, { x: number; y: number }>();
  /** instanceId → id машины по видам и пешеходов. */
  readonly pickCars: { mesh: THREE.InstancedMesh; ids: number[] }[] = [];
  readonly pickPeds: { mesh: THREE.InstancedMesh; ids: number[] } = { mesh: null as unknown as THREE.InstancedMesh, ids: [] };

  constructor(net: NetJ) {
    this.links = net.links.map((l) => new Path(l.pts));
    this.next = net.links.map((l) => l.next ?? []);
    this.edges = net.sw_edges.map((e) => new Path(e.pts));
    const bodyMat = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.32, metalness: 0.25 });
    const glassMat = new THREE.MeshStandardMaterial({ color: "#5b7389", roughness: 0.18, metalness: 0.05 });
    const underMat = new THREE.MeshStandardMaterial({ color: "#15171b", roughness: 0.9 });
    this.headMat = new THREE.MeshBasicMaterial({ color: "#ffffff", toneMapped: false });
    const tailMat = new THREE.MeshBasicMaterial({ color: "#ffffff", toneMapped: false });
    const blinkMat = new THREE.MeshBasicMaterial({ color: "#ffa21a", toneMapped: false, side: THREE.DoubleSide });
    for (const sp of SPECS) {
      const g = carParts(sp);
      const mk = (geo: THREE.BufferGeometry, mat: THREE.Material, shadow = false) => {
        const m = new THREE.InstancedMesh(geo, mat, CAP);
        m.count = 0;
        m.castShadow = shadow;
        m.frustumCulled = false;
        m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        this.group.add(m);
        return m;
      };
      const k: KindMeshes = {
        body: mk(g.body, bodyMat, true),
        glass: mk(g.glass, glassMat, true),
        head: mk(g.head, this.headMat),
        tail: mk(g.tail, tailMat),
        blink: mk(g.blink, blinkMat),
        n: 0,
      };
      // цвета инстансов
      k.body.setColorAt(0, new THREE.Color());
      k.head.setColorAt(0, new THREE.Color());
      k.tail.setColorAt(0, new THREE.Color());
      this.under.push(mk(g.under, underMat));
      this.kinds.push(k);
      this.pickCars.push({ mesh: k.body, ids: [] });
    }
    // пятна фар на асфальте
    const beamGeo = new THREE.PlaneGeometry(1, 1);
    beamGeo.rotateX(-Math.PI / 2);
    beamGeo.translate(0.5, 0, 0);
    this.beamMat = new THREE.MeshBasicMaterial({
      map: beamTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0,
    });
    this.beams = new THREE.InstancedMesh(beamGeo, this.beamMat, CAP);
    this.beams.count = 0;
    this.beams.frustumCulled = false;
    this.beams.renderOrder = 2;
    this.group.add(this.beams);

    // пешеходы
    const bodyGeo = new THREE.CapsuleGeometry(0.21, 0.78, 3, 8);
    bodyGeo.translate(0, 0.21 + 0.39 + 0.05, 0);
    const headGeo = new THREE.SphereGeometry(0.15, 10, 8);
    headGeo.translate(0, 1.5, 0);
    this.pedBody = new THREE.InstancedMesh(bodyGeo, new THREE.MeshStandardMaterial({ color: "#fff", roughness: 0.8 }), CAP);
    this.pedHead = new THREE.InstancedMesh(headGeo, new THREE.MeshStandardMaterial({ color: "#fff", roughness: 0.7 }), CAP);
    for (const m of [this.pedBody, this.pedHead]) {
      m.count = 0;
      m.castShadow = true;
      m.frustumCulled = false;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.setColorAt(0, new THREE.Color());
      this.group.add(m);
    }
    this.pickPeds.mesh = this.pedBody;
  }

  private carPose(r: CarRow, o: Pose): Pose {
    const p = this.links[r[1]];
    const q = { x: 0, y: 0, h: 0 };
    p.at(r[2], q);
    o.x = q.x;
    o.y = q.y;
    o.h = q.h;
    o.link = r[1];
    o.s = r[2];
    o.lat = r[3];
    return o;
  }

  private pedPose(r: PedRow, o: Pose): Pose {
    const p = this.edges[r[1]];
    const q = { x: 0, y: 0, h: 0 };
    p.at(r[2], q);
    const nx = -Math.sin(q.h);
    const ny = Math.cos(q.h);
    o.x = q.x + nx * r[3];
    o.y = q.y + ny * r[3];
    o.h = r[7] > 0 ? q.h : q.h + Math.PI;
    o.link = r[1];
    o.s = r[2];
    o.lat = r[3];
    return o;
  }

  /** Новый кадр сервера. */
  push(cars: CarRow[], peds: PedRow[], now: number) {
    if (this.tLast > 0) {
      const gap = Math.min(Math.max(now - this.tLast, 0.02), 0.5);
      this.frameGap = this.frameGap * 0.85 + gap * 0.15;
    }
    this.tLast = now;
    // метка кадра сглаживает неровный приход по сети
    const prevT = this.frames.length ? this.frames[this.frames.length - 1].t : now - this.frameGap;
    const t = Math.max(prevT + this.frameGap * 0.5, Math.min(now, prevT + this.frameGap * 1.5));
    const f: Frame = { t, cars: new Map(), peds: new Map() };
    this.rows.clear();
    for (const r of cars) {
      f.cars.set(r[0], this.carPose(r, {} as Pose));
      this.rows.set(r[0], r);
      if (!this.born.has(r[0])) this.born.set(r[0], now);
    }
    this.pedRows.clear();
    for (const r of peds) {
      f.peds.set(r[0], this.pedPose(r, {} as Pose));
      this.pedRows.set(r[0], r);
    }
    this.frames.push(f);
    if (this.frames.length > 5) this.frames.shift();
    if (this.born.size > 6000) {
      for (const id of this.born.keys()) if (!f.cars.has(id)) this.born.delete(id);
    }
  }

  /** Два кадра вокруг момента отрисовки и доля между ними. */
  private bracket(rt: number): [Frame | undefined, Frame, number] {
    const fr = this.frames;
    const last = fr[fr.length - 1];
    if (rt >= last.t || fr.length < 2) {
      const a = fr[fr.length - 2];
      return [a, last, 1];
    }
    for (let i = fr.length - 1; i > 0; i--) {
      const a = fr[i - 1];
      const b = fr[i];
      if (rt >= a.t) return [a, b, Math.min(1, Math.max(0, (rt - a.t) / Math.max(b.t - a.t, 1e-3)))];
    }
    return [undefined, fr[0], 1];
  }

  /** Точка между двумя положениями машины вдоль её пути, в том числе через смену пути. */
  private along(a: Pose, b: Pose, t: number, out: { x: number; y: number; h: number }) {
    if (a.link === b.link) {
      this.links[b.link].at(a.s + (b.s - a.s) * t, out);
      return;
    }
    // цепочка путей от a к b (обычно полоса → коннектор → полоса)
    const chain = this.chain(a.link, b.link);
    if (chain) {
      const lens = chain.map((li) => this.links[li].length);
      let total = lens[0] - a.s + b.s;
      for (let i = 1; i < chain.length - 1; i++) total += lens[i];
      let d = Math.max(0, total) * t;
      const first = lens[0] - a.s;
      if (d <= first) {
        this.links[chain[0]].at(a.s + d, out);
        return;
      }
      d -= first;
      for (let i = 1; i < chain.length - 1; i++) {
        if (d <= lens[i]) {
          this.links[chain[i]].at(d, out);
          return;
        }
        d -= lens[i];
      }
      this.links[b.link].at(Math.min(d, b.s), out);
      return;
    }
    // перестроение или неизвестный переход: по прямой
    out.x = a.x + (b.x - a.x) * t;
    out.y = a.y + (b.y - a.y) * t;
    out.h = lerpAngle(a.h, b.h, t);
  }

  private chain(from: number, to: number): number[] | null {
    for (const n1 of this.next[from]) {
      if (n1 === to) return [from, to];
      for (const n2 of this.next[n1]) {
        if (n2 === to) return [from, n1, to];
        for (const n3 of this.next[n2]) if (n3 === to) return [from, n1, n2, to];
      }
    }
    return null;
  }

  reset() {
    this.frames = [];
    this.rear.clear();
    this.pedHeading.clear();
    this.born.clear();
  }

  update(now: number, day: Daylight) {
    if (!this.frames.length) return;
    const dtR = Math.min(0.1, Math.max(0, now - this.lastRender));
    this.lastRender = now;
    const [fa, fb, k] = this.bracket(now - this.frameGap * 1.6 - 0.02);
    const dummy = new THREE.Object3D();
    const col = new THREE.Color();
    const night = day.night;
    const blinkOn = Math.floor(now * 2.4) % 2 === 0;
    for (const kd of this.kinds) {
      kd.n = 0;
      kd.blink.count = 0;
    }
    for (const p of this.pickCars) p.ids.length = 0;
    const under = this.under.map(() => 0);
    let nb = 0;
    this.carPos.clear();
    const q = { x: 0, y: 0, h: 0 };
    const seen = new Set<number>();
    for (const [id, c] of fb.cars) {
      const r = this.rows.get(id);
      if (!r) continue;
      seen.add(id);
      const p = fa?.cars.get(id);
      let lat = c.lat;
      if (p) {
        this.along(p, c, k, q);
        lat = p.lat + (c.lat - p.lat) * k;
      } else {
        q.x = c.x;
        q.y = c.y;
        q.h = c.h;
      }
      const kind0 = Math.min(r[6], SPECS.length - 1);
      const L = SPECS[kind0].L;
      // передний край машины (сервер даёт s переднего края) со смещением перестроения
      const fx = q.x - Math.sin(q.h) * lat;
      const fy = q.y + Math.cos(q.h) * lat;
      // задняя ось тянется за передней точкой на расстоянии колёсной базы
      const wb = L * 0.62;
      let rr = this.rear.get(id);
      if (!rr || Math.hypot(fx - rr.x, fy - rr.y) > L * 3) {
        rr = { x: fx - Math.cos(q.h) * wb, y: fy - Math.sin(q.h) * wb };
        this.rear.set(id, rr);
      } else {
        const dx = fx - rr.x;
        const dy = fy - rr.y;
        const l = Math.hypot(dx, dy);
        if (l > 1e-4) {
          rr.x = fx - (dx / l) * wb;
          rr.y = fy - (dy / l) * wb;
        }
      }
      let h = Math.atan2(fy - rr.y, fx - rr.x);
      const flags = r[5];
      const crashed = (flags & FLAG.CRASH) !== 0;
      if (crashed) h += ((id * 0.37) % 0.6) - 0.3;
      const x = fx - Math.cos(h) * (L / 2);
      const y = fy - Math.sin(h) * (L / 2);
      this.carPos.set(id, { x, y, h });
      const kind = Math.min(r[6], SPECS.length - 1);
      const kd = this.kinds[kind];
      const i = kd.n++;
      if (i >= CAP) continue;
      const age = now - (this.born.get(id) ?? now);
      const grow = Math.min(1, 0.35 + age * 2.2);
      dummy.position.set(x, 0, -y);
      dummy.rotation.set(0, h, 0);
      dummy.scale.set(grow, grow, grow);
      dummy.updateMatrix();
      kd.body.setMatrixAt(i, dummy.matrix);
      kd.glass.setMatrixAt(i, dummy.matrix);
      kd.head.setMatrixAt(i, dummy.matrix);
      kd.tail.setMatrixAt(i, dummy.matrix);
      this.under[kind].setMatrixAt(under[kind]++, dummy.matrix);
      this.pickCars[kind].ids[i] = id;
      col.set(kind === 3 ? TAXI : kind === 5 ? (r[7] % 2 ? "#d8473b" : "#2f8f6a") : CAR_COLORS[r[7] % CAR_COLORS.length]);
      kd.body.setColorAt(i, col);
      const brake = (flags & FLAG.BRAKE) !== 0;
      const hl = 0.35 + night * 1.1;
      kd.head.setColorAt(i, col.setRGB(hl, hl * 0.96, hl * 0.86));
      const tl = brake ? 2.6 : 0.35 + night * 0.8;
      kd.tail.setColorAt(i, col.setRGB(tl, tl * 0.06, tl * 0.06));
      // поворотник: левая или правая сторона; аварийка — обе
      const left = (flags & FLAG.LEFT) !== 0;
      const right = (flags & FLAG.RIGHT) !== 0;
      if ((left || right || crashed) && blinkOn) {
        const sides = crashed ? [1, -1] : [left ? -1 : 1];
        for (const sd of sides) {
          const bi = kd.blink.count++;
          if (bi >= CAP) break;
          dummy.scale.set(grow, grow, sd * grow);
          dummy.updateMatrix();
          kd.blink.setMatrixAt(bi, dummy.matrix);
        }
        dummy.scale.set(grow, grow, grow);
      }
      if (night > 0.05 && nb < CAP) {
        const sp = SPECS[kind];
        dummy.position.set(x + Math.cos(h) * sp.L * 0.48, 0.06, -(y + Math.sin(h) * sp.L * 0.48));
        dummy.scale.set(16, 1, 7);
        dummy.updateMatrix();
        this.beams.setMatrixAt(nb++, dummy.matrix);
      }
    }
    if (this.rear.size > seen.size + 200) for (const id of this.rear.keys()) if (!seen.has(id)) this.rear.delete(id);
    if (this.pedHeading.size > fb.peds.size + 200) for (const id of this.pedHeading.keys()) if (!fb.peds.has(id)) this.pedHeading.delete(id);
    this.kinds.forEach((kd, kind) => {
      for (const m of [kd.body, kd.glass, kd.head, kd.tail]) {
        m.count = kd.n;
        m.instanceMatrix.needsUpdate = true;
        if (m.instanceColor) m.instanceColor.needsUpdate = true;
      }
      kd.blink.instanceMatrix.needsUpdate = true;
      this.under[kind].count = under[kind];
      this.under[kind].instanceMatrix.needsUpdate = true;
    });
    this.beams.count = nb;
    this.beams.instanceMatrix.needsUpdate = true;
    this.beamMat.opacity = night * 0.2;

    // пешеходы
    let np = 0;
    this.pickPeds.ids.length = 0;
    this.pedPos.clear();
    for (const [id, c] of fb.peds) {
      const r = this.pedRows.get(id);
      if (!r) continue;
      const p = fa?.peds.get(id);
      let x = c.x;
      let y = c.y;
      if (p && Math.hypot(c.x - p.x, c.y - p.y) < 8) {
        x = p.x + (c.x - p.x) * k;
        y = p.y + (c.y - p.y) * k;
      }
      // голова поворачивается плавно, а не рывком на углу тротуара
      const prevH = this.pedHeading.get(id) ?? c.h;
      const h = lerpAngle(prevH, c.h, 1 - Math.exp(-dtR * 8));
      this.pedHeading.set(id, h);
      this.pedPos.set(id, { x, y });
      const state = r[4];
      const i = np++;
      if (i >= CAP) break;
      const walking = state === 0 || state === 2;
      const bob = walking ? Math.abs(Math.sin(now * 8 + id)) * 0.06 : 0;
      dummy.position.set(x, 0.16 + bob, -y);
      if (state === 3) {
        dummy.rotation.set(0, h, Math.PI / 2);
        dummy.position.y = 0.36;
      } else dummy.rotation.set(0, h, walking ? Math.sin(now * 8 + id) * 0.05 : 0);
      const sc = r[5] === 1 ? 0.92 : 1;
      dummy.scale.set(sc, sc, sc);
      dummy.updateMatrix();
      this.pedBody.setMatrixAt(i, dummy.matrix);
      this.pedHead.setMatrixAt(i, dummy.matrix);
      this.pedBody.setColorAt(i, col.set(CLOTHES[r[6] % CLOTHES.length]));
      this.pedHead.setColorAt(i, col.set(SKIN[(id * 7) % SKIN.length]));
      this.pickPeds.ids[i] = id;
    }
    for (const m of [this.pedBody, this.pedHead]) {
      m.count = np;
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
  }

  row(id: number) {
    return this.rows.get(id);
  }

  pedRow(id: number) {
    return this.pedRows.get(id);
  }
}

function beamTexture() {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(0, 32, 0, 0, 32, 128);
  g.addColorStop(0, "rgba(255,240,210,0.9)");
  g.addColorStop(0.5, "rgba(255,230,190,0.35)");
  g.addColorStop(1, "rgba(255,230,190,0)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.moveTo(0, 26);
  ctx.lineTo(128, 0);
  ctx.lineTo(128, 64);
  ctx.lineTo(0, 38);
  ctx.closePath();
  ctx.fill();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export { radialTexture };
