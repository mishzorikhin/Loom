// Окружение за пределами сети: рельеф с холмами и горами, лес, долины вдоль уходящих дорог.
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { P2 } from "../types";
import { grassMap, macroVariation } from "./materials";

export interface Ray {
  p: P2;   // точка на краю сети
  d: P2;   // направление наружу, единичное
}

function hash(x: number, y: number) {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

function noise(x: number, y: number) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const u = fx * fx * (3 - 2 * fx);
  const v = fy * fy * (3 - 2 * fy);
  const a = hash(ix, iy);
  const b = hash(ix + 1, iy);
  const c = hash(ix, iy + 1);
  const d = hash(ix + 1, iy + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function fbm(x: number, y: number) {
  let s = 0;
  let a = 0.5;
  for (let i = 0; i < 5; i++) {
    s += a * noise(x, y);
    x = x * 2.03 + 17.1;
    y = y * 2.03 - 9.3;
    a *= 0.5;
  }
  return s;
}

function smooth(e0: number, e1: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
}

export class Terrain {
  readonly group = new THREE.Group();
  private box: [number, number, number, number];
  private rays: Ray[];

  constructor(box: [number, number, number, number], rays: Ray[]) {
    this.box = box;
    this.rays = rays;
    this.buildGround();
    this.buildForest();
  }

  /** Расстояние от точки до прямоугольника сети (0 внутри). */
  private outside(x: number, y: number) {
    const [x0, y0, x1, y1] = this.box;
    const dx = Math.max(x0 - x, 0, x - x1);
    const dy = Math.max(y0 - y, 0, y - y1);
    return Math.hypot(dx, dy);
  }

  /** Расстояние до ближайшей уходящей дороги (луча от края сети). */
  private toRoad(x: number, y: number) {
    let best = 1e9;
    for (const r of this.rays) {
      const vx = x - r.p[0];
      const vy = y - r.p[1];
      const t = vx * r.d[0] + vy * r.d[1];
      if (t < -20) continue;
      const px = vx - r.d[0] * t;
      const py = vy - r.d[1] * t;
      best = Math.min(best, Math.hypot(px, py));
    }
    return best;
  }

  /** Плотность леса: у края долины гуще, вдали реже, рощами по шуму. */
  forest(x: number, y: number) {
    const d = this.outside(x, y);
    if (d < 18 || this.toRoad(x, y) < 26) return 0;
    return (1 - smooth(300, 1700, d)) * smooth(0.36, 0.56, fbm(x / 220, y / 220));
  }

  height(x: number, y: number) {
    const d = this.outside(x, y);
    if (d < 40) return -0.06;
    const hills = smooth(60, 700, d) * (fbm(x / 380, y / 380) * 150 - 30);
    const mountains = smooth(1400, 2600, d) * Math.pow(fbm(x / 900 + 3.3, y / 900 - 1.7), 1.6) * 520;
    const valley = smooth(60, 260, this.toRoad(x, y));
    return Math.max(-0.25, (hills + mountains) * valley * smooth(40, 160, d) - 0.25 * (1 - valley));
  }

  private buildGround() {
    const [x0, y0, x1, y1] = this.box;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const size = 9000;
    const seg = 220;
    const geo = new THREE.PlaneGeometry(size, size, seg, seg);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const colors = new Float32Array(pos.count * 3);
    const uv = geo.attributes.uv as THREE.BufferAttribute;
    const grass = new THREE.Color("#ffffff");
    const forest = new THREE.Color("#6f8a63");
    const rock = new THREE.Color("#b8a58c");
    const snow = new THREE.Color("#f2f2f0");
    const c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) + cx;
      const y = -pos.getZ(i) + cy;
      const h = this.height(x, y);
      pos.setXYZ(i, x, h, -y);
      uv.setXY(i, x / 20, y / 20);
      const d = this.outside(x, y);
      c.copy(grass).lerp(forest, smooth(80, 500, d));
      // под лесом тёмная подложка: издали массив читается сплошным
      c.lerp(new THREE.Color("#4f6b45"), Math.min(1, this.forest(x, y) * 1.6));
      c.lerp(rock, smooth(90, 260, h));
      c.lerp(snow, smooth(380, 470, h));
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    const map = grassMap();
    const mat = macroVariation(new THREE.MeshStandardMaterial({ color: "#ffffff", vertexColors: true, roughness: 1, map }), 70, 0.16);
    const ground = new THREE.Mesh(geo, mat);
    ground.receiveShadow = true;
    this.group.add(ground);
  }

  /** Лес вокруг сети: плотно у края долины, реже дальше, не на дорогах и не на склонах гор. */
  private buildForest() {
    const [x0, y0, x1, y1] = this.box;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const R = 1600;
    const blob = (r: number, x: number, y: number, z: number) => {
      const g = new THREE.IcosahedronGeometry(r, 0);
      g.translate(x, y, z);
      return g;
    };
    const crown = mergeGeometries([blob(1, 0, 1.7, 0), blob(0.7, 0.55, 2.0, 0.2), blob(0.65, -0.45, 2.1, -0.3)]);
    const trunk = new THREE.CylinderGeometry(0.1, 0.16, 1.4, 5);
    trunk.translate(0, 0.7, 0);
    const deciduous = mergeGeometries([crown, trunk.clone()].map((g) => g.toNonIndexed()));
    const c1 = new THREE.ConeGeometry(1, 2, 7);
    c1.translate(0, 1.6, 0);
    const c2 = new THREE.ConeGeometry(0.72, 1.6, 7);
    c2.translate(0, 2.6, 0);
    const conifer = mergeGeometries([c1, c2, trunk.clone()].map((g) => g.toNonIndexed()));
    const mat = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.95, flatShading: true });
    const N = 22000;
    const dec = new THREE.InstancedMesh(deciduous, mat, N);
    const con = new THREE.InstancedMesh(conifer, mat, N);
    let nd = 0;
    let nc = 0;
    const dummy = new THREE.Object3D();
    const col = new THREE.Color();
    const GREENS = ["#4f7a3f", "#5d8746", "#44703c", "#6a8f4c", "#3f6638", "#7a9a52"];
    let s = 99;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    for (let k = 0; k < N * 6 && (nd < N || nc < N); k++) {
      const x = cx + (rnd() - 0.5) * 2 * R;
      const y = cy + (rnd() - 0.5) * 2 * R;
      const d = this.outside(x, y);
      const density = this.forest(x, y);
      if (rnd() > density) continue;
      const h = this.height(x, y);
      if (h > 230) continue;
      const pine = rnd() < 0.35 + smooth(60, 200, h) * 0.5;
      const sc = 4.2 + rnd() * 4 + smooth(100, 900, d) * 2.5;
      dummy.position.set(x, h - 0.2, -y);
      dummy.rotation.set(0, rnd() * 6.28, 0);
      dummy.scale.set(sc, sc * (0.9 + rnd() * 0.5), sc);
      dummy.updateMatrix();
      if (pine && nc < N) {
        con.setMatrixAt(nc, dummy.matrix);
        con.setColorAt(nc++, col.set(rnd() < 0.5 ? "#3d6440" : "#4a7350").multiplyScalar(0.85 + rnd() * 0.3));
      } else if (!pine && nd < N) {
        dec.setMatrixAt(nd, dummy.matrix);
        dec.setColorAt(nd++, col.set(GREENS[Math.floor(rnd() * GREENS.length)]).multiplyScalar(0.85 + rnd() * 0.3));
      }
    }
    dec.count = nd;
    con.count = nc;
    for (const m of [dec, con]) {
      m.castShadow = false;
      m.receiveShadow = true;
      this.group.add(m);
    }
  }
}
