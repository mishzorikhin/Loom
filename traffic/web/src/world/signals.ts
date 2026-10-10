// Светофоры: опоры, секции, лампы и метки состояния на каждом движении.
import * as THREE from "three";
import type { NetJ, SignalSnap } from "../types";
import { Path } from "../geom";
import { radialTexture } from "./city";

const COL = {
  R: new THREE.Color("#ff3b3b"),
  Y: new THREE.Color("#ffb21e"),
  G: new THREE.Color("#2bff88"),
  W: new THREE.Color("#2bff88"),
  F: new THREE.Color("#2bff88"),
  D: new THREE.Color("#ff3b3b"),
};
const OFF = new THREE.Color("#1b1d22");

interface Lamp {
  mesh: THREE.Mesh;
  junction: string;
  gi: number;           // номер группы в состоянии перекрёстка
  on: string;           // при каком состоянии горит
  color: THREE.Color;
  glow: number;         // индекс в слое ореолов
}

export class Signals {
  readonly group = new THREE.Group();
  readonly strips = new THREE.Group();
  private lamps: Lamp[] = [];
  private glowGeo: THREE.BufferGeometry;
  private glowCol: Float32Array;
  private stripGeo: THREE.BufferGeometry;
  private stripCol: Float32Array;
  private stripOwner: { junction: string; gi: number; from: number; count: number }[] = [];
  private onMat = new Map<string, THREE.MeshStandardMaterial>();
  private offMat: THREE.MeshStandardMaterial;

  constructor(net: NetJ) {
    const groupIndex = new Map<string, Map<string, number>>();
    for (const j of net.junctions) groupIndex.set(j.id, new Map(j.groups.map((g, i) => [g.name, i])));

    const poleMat = new THREE.MeshStandardMaterial({ color: "#3d434c", roughness: 0.5, metalness: 0.5 });
    const boxMat = new THREE.MeshStandardMaterial({ color: "#16181c", roughness: 0.6 });
    this.offMat = new THREE.MeshStandardMaterial({ color: OFF, roughness: 0.3 });
    for (const [k, c] of Object.entries(COL)) {
      this.onMat.set(k, new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: 9, toneMapped: false }));
    }
    const lampGeo = new THREE.CircleGeometry(0.13, 16);
    const glowPos: number[] = [];

    const poleDone = new Set<string>();
    for (const h of net.render.heads) {
      const gi = groupIndex.get(h.junction)?.get(h.group);
      if (gi === undefined) continue;
      const isCar = h.kind === "car";
      const facing = isCar ? h.facing : h.facing + Math.PI;
      const height = isCar ? 5.6 : 2.7;
      const pk = `${h.pole[0]},${h.pole[1]}`;
      if (!poleDone.has(pk)) {
        poleDone.add(pk);
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.12, height + 0.4, 8), poleMat);
        pole.position.set(h.pole[0], (height + 0.4) / 2, -h.pole[1]);
        pole.castShadow = true;
        this.group.add(pole);
      }
      const dx = h.pos[0] - h.pole[0];
      const dy = h.pos[1] - h.pole[1];
      const reach = Math.hypot(dx, dy);
      if (reach > 0.6) {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(reach, 0.1, 0.1), poleMat);
        arm.position.set((h.pos[0] + h.pole[0]) / 2, height + 0.75, -(h.pos[1] + h.pole[1]) / 2);
        arm.rotation.y = Math.atan2(dy, dx);
        arm.castShadow = true;
        this.group.add(arm);
      }
      const head = new THREE.Group();
      head.position.set(h.pos[0], height, -h.pos[1]);
      head.rotation.y = facing;
      const nl = isCar ? 3 : 2;
      const box = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.36 * nl + 0.1, 0.42), boxMat);
      box.position.y = 0;
      box.castShadow = true;
      head.add(box);
      if (reach > 0.6) {
        const hanger = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.75 - (0.36 * nl + 0.1) / 2 + 0.05, 0.05), poleMat);
        hanger.position.y = (0.36 * nl + 0.1) / 2 + (0.75 - (0.36 * nl + 0.1) / 2) / 2;
        head.add(hanger);
      }
      const order = isCar ? ["R", "Y", "G"] : ["D", "W"];
      order.forEach((on, k) => {
        const lamp = new THREE.Mesh(lampGeo, this.offMat);
        lamp.position.set(0.172, ((nl - 1) / 2 - k) * 0.36, 0);
        lamp.rotation.y = Math.PI / 2;
        head.add(lamp);
        head.updateMatrixWorld(true);
        const wp = new THREE.Vector3();
        lamp.getWorldPosition(wp);
        // ореол чуть впереди лампы
        const fx = Math.cos(facing) * 0.25;
        const fz = -Math.sin(facing) * 0.25;
        glowPos.push(wp.x + fx, wp.y, wp.z + fz);
        this.lamps.push({ mesh: lamp, junction: h.junction, gi, on, color: COL[on as keyof typeof COL], glow: glowPos.length / 3 - 1 });
      });
      this.group.add(head);
    }
    this.glowGeo = new THREE.BufferGeometry();
    this.glowGeo.setAttribute("position", new THREE.Float32BufferAttribute(glowPos, 3));
    this.glowCol = new Float32Array(glowPos.length);
    this.glowGeo.setAttribute("color", new THREE.BufferAttribute(this.glowCol, 3));
    const glow = new THREE.Points(
      this.glowGeo,
      new THREE.PointsMaterial({
        size: 2.6, map: radialTexture("rgba(255,255,255,1)"), vertexColors: true, transparent: true,
        depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
      }),
    );
    this.group.add(glow);

    // метки на движениях: начало каждого коннектора окрашено состоянием его группы
    const pos: number[] = [];
    const idx: number[] = [];
    const o = { x: 0, y: 0, h: 0 };
    for (const j of net.junctions) {
      if (j.kind !== "signal") continue;
      for (const li of j.approaches) {
        const lane = net.links[li];
        const groups = [...new Set(lane.next.map((ci) => net.links[ci].group).filter(Boolean))];
        if (!groups.length) continue;
        const p = new Path(lane.pts);
        const len = Math.min(5, p.length * 0.5);
        const band = (lane.w * 0.7) / groups.length;
        groups.forEach((g, k) => {
          const gi = groupIndex.get(j.id)?.get(g);
          if (gi === undefined) return;
          const from = pos.length / 3;
          const n = 4;
          // полоса делится поперёк по группам: слева направо в порядке групп
          const off = -lane.w * 0.35 + band * (k + 0.5);
          for (let i = 0; i <= n; i++) {
            p.at(p.length - 0.9 - len + (len * i) / n, o);
            const nx = -Math.sin(o.h);
            const ny = Math.cos(o.h);
            const cx = o.x + nx * off;
            const cy = o.y + ny * off;
            const hw = band * 0.42;
            pos.push(cx + nx * hw, 0.05, -(cy + ny * hw), cx - nx * hw, 0.05, -(cy - ny * hw));
            if (i < n) {
              const a = from + i * 2;
              idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
            }
          }
          this.stripOwner.push({ junction: j.id, gi, from, count: (n + 1) * 2 });
        });
      }
    }
    // метки на стоп-линиях переходов посреди квартала
    for (const j of net.junctions) {
      if (j.kind !== "midblock") continue;
      const gi = groupIndex.get(j.id)!.get("veh")!;
      for (const li of j.groups.find((g) => g.name === "veh")!.links) {
        const l = net.links[li];
        const p = new Path(l.pts);
        const from = pos.length / 3;
        const s0 = Math.max(3, Math.min(p.length, closestS(p, j.pos) - 3.6));
        for (let i = 0; i <= 3; i++) {
          p.at(s0 - 3 + i, o);
          const nx = -Math.sin(o.h) * 0.32;
          const ny = Math.cos(o.h) * 0.32;
          pos.push(o.x + nx, 0.05, -(o.y + ny), o.x - nx, 0.05, -(o.y - ny));
          if (i < 3) {
            const a = from + i * 2;
            idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
          }
        }
        this.stripOwner.push({ junction: j.id, gi, from, count: 8 });
      }
    }
    this.stripGeo = new THREE.BufferGeometry();
    this.stripGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    this.stripCol = new Float32Array(pos.length);
    this.stripGeo.setAttribute("color", new THREE.BufferAttribute(this.stripCol, 3));
    this.stripGeo.setIndex(idx);
    const stripMesh = new THREE.Mesh(
      this.stripGeo,
      new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false, transparent: true, opacity: 0.8, depthWrite: false,
        polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 }),
    );
    stripMesh.renderOrder = 3;
    this.strips.add(stripMesh);
  }

  update(signals: Record<string, SignalSnap>, time: number) {
    const blink = Math.floor(time * 2.2) % 2 === 0;
    for (const l of this.lamps) {
      const st = signals[l.junction]?.state[l.gi] ?? "R";
      let lit = st === l.on;
      if (l.on === "W" && st === "F") lit = blink;
      const mat = lit ? this.onMat.get(l.on)! : this.offMat;
      if (l.mesh.material !== mat) l.mesh.material = mat;
      const c = lit ? l.color : OFF;
      const k = lit ? 1 : 0;
      this.glowCol[l.glow * 3] = c.r * k;
      this.glowCol[l.glow * 3 + 1] = c.g * k;
      this.glowCol[l.glow * 3 + 2] = c.b * k;
    }
    this.glowGeo.attributes.color.needsUpdate = true;
    for (const s of this.stripOwner) {
      const st = signals[s.junction]?.state[s.gi] ?? "R";
      const c = COL[st as keyof typeof COL] ?? COL.R;
      for (let i = 0; i < s.count; i++) {
        const k = (s.from + i) * 3;
        this.stripCol[k] = c.r;
        this.stripCol[k + 1] = c.g;
        this.stripCol[k + 2] = c.b;
      }
    }
    this.stripGeo.attributes.color.needsUpdate = true;
  }
}

function closestS(p: Path, q: [number, number]) {
  let best = 0;
  let bd = Infinity;
  const o = { x: 0, y: 0, h: 0 };
  for (let s = 0; s <= p.length; s += 0.5) {
    p.at(s, o);
    const d = Math.hypot(o.x - q[0], o.y - q[1]);
    if (d < bd) {
      bd = d;
      best = s;
    }
  }
  return best;
}
