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
  private prev = new Map<number, Pose>();
  private cur = new Map<number, Pose>();
  private rows = new Map<number, CarRow>();
  private pedPrev = new Map<number, Pose>();
  private pedCur = new Map<number, Pose>();
  private pedRows = new Map<number, PedRow>();
  private born = new Map<number, number>();
  private tCur = 0;
  private frameGap = 1 / 15;
  /** Положения в последнем кадре отрисовки: для выбора и слежения. */
  readonly carPos = new Map<number, { x: number; y: number; h: number }>();
  readonly pedPos = new Map<number, { x: number; y: number }>();
  /** instanceId → id машины по видам и пешеходов. */
  readonly pickCars: { mesh: THREE.InstancedMesh; ids: number[] }[] = [];
  readonly pickPeds: { mesh: THREE.InstancedMesh; ids: number[] } = { mesh: null as unknown as THREE.InstancedMesh, ids: [] };

  constructor(net: NetJ) {
    this.links = net.links.map((l) => new Path(l.pts));
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
    const gap = now - this.tCur;
    if (this.tCur > 0) this.frameGap = this.frameGap * 0.8 + Math.min(Math.max(gap, 0.02), 0.5) * 0.2;
    this.tCur = now;
    [this.prev, this.cur] = [this.cur, this.prev];
    this.cur.clear();
    this.rows.clear();
    for (const r of cars) {
      const id = r[0];
      this.cur.set(id, this.carPose(r, {} as Pose));
      this.rows.set(id, r);
      if (!this.born.has(id)) this.born.set(id, now);
    }
    [this.pedPrev, this.pedCur] = [this.pedCur, this.pedPrev];
    this.pedCur.clear();
    this.pedRows.clear();
    for (const r of peds) {
      this.pedCur.set(r[0], this.pedPose(r, {} as Pose));
      this.pedRows.set(r[0], r);
    }
    if (this.born.size > 6000) {
      for (const id of this.born.keys()) if (!this.cur.has(id)) this.born.delete(id);
    }
  }

  reset() {
    this.prev.clear();
    this.cur.clear();
    this.pedPrev.clear();
    this.pedCur.clear();
    this.born.clear();
  }

  update(now: number, day: Daylight) {
    const k = Math.min(1.25, Math.max(0, (now - this.tCur) / Math.max(this.frameGap, 1e-3)));
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
    for (const [id, c] of this.cur) {
      const r = this.rows.get(id)!;
      const p = this.prev.get(id);
      let x = c.x;
      let y = c.y;
      let h = c.h;
      let lat = c.lat;
      if (p) {
        const t = Math.min(k, 1);
        if (p.link === c.link) {
          this.links[c.link].at(p.s + (c.s - p.s) * t, q);
          x = q.x;
          y = q.y;
          h = q.h;
        } else {
          x = p.x + (c.x - p.x) * t;
          y = p.y + (c.y - p.y) * t;
          h = lerpAngle(p.h, c.h, t);
        }
        lat = p.lat + (c.lat - p.lat) * t;
      }
      const flags = r[5];
      const crashed = (flags & FLAG.CRASH) !== 0;
      if (crashed) h += ((id * 0.37) % 0.6) - 0.3;
      x += -Math.sin(h) * lat;
      y += Math.cos(h) * lat;
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
        dummy.position.set(x + Math.cos(h) * sp.L * 0.45, 0.06, -(y + Math.sin(h) * sp.L * 0.45));
        dummy.scale.set(16, 1, 7);
        dummy.updateMatrix();
        this.beams.setMatrixAt(nb++, dummy.matrix);
      }
    }
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
    for (const [id, c] of this.pedCur) {
      const r = this.pedRows.get(id)!;
      const p = this.pedPrev.get(id);
      let x = c.x;
      let y = c.y;
      let h = c.h;
      if (p && p.link === c.link) {
        const t = Math.min(k, 1);
        x = p.x + (c.x - p.x) * t;
        y = p.y + (c.y - p.y) * t;
        h = lerpAngle(p.h, c.h, t);
      }
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
