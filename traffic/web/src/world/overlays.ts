// Слои поверх мира: ДТП, сближения, тепловая карта, точки конфликтов, выбор.
import * as THREE from "three";
import type { NetJ, SimEvent } from "../types";
import { Path } from "../geom";
import { radialTexture } from "./city";

const CRASH_LIFE = 150; // секунд симуляции, как CRASH_CLEAR в sim.py

interface Flash {
  mesh: THREE.Mesh;
  born: number;
  life: number;
  size: number;
}

export class Overlays {
  readonly group = new THREE.Group();
  readonly conflicts = new THREE.Group();
  readonly heat = new THREE.Group();
  private beacons = new Map<number, { g: THREE.Group; ev: SimEvent; ring: THREE.Mesh; beam: THREE.Mesh }>();
  private flashes: Flash[] = [];
  private heatMesh: THREE.InstancedMesh;
  private heatN = 0;
  private ringGeo = new THREE.RingGeometry(0.82, 1, 48);
  private beamGeo: THREE.CylinderGeometry;
  private beamMat: THREE.MeshBasicMaterial;
  private iconMat: THREE.SpriteMaterial;
  readonly select: THREE.Mesh;

  constructor(net: NetJ) {
    this.ringGeo.rotateX(-Math.PI / 2);
    this.beamGeo = new THREE.CylinderGeometry(0.9, 2.4, 40, 24, 1, true);
    this.beamGeo.translate(0, 20, 0);
    this.beamMat = new THREE.MeshBasicMaterial({
      map: beamTex(), color: "#ff2a2a", transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
    });
    this.iconMat = new THREE.SpriteMaterial({ map: iconTex(), depthTest: false, sizeAttenuation: false, toneMapped: false });

    // тепловая карта
    const hg = new THREE.PlaneGeometry(1, 1);
    hg.rotateX(-Math.PI / 2);
    this.heatMesh = new THREE.InstancedMesh(
      hg,
      new THREE.MeshBasicMaterial({ map: radialTexture("rgba(255,255,255,0.55)"), transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, toneMapped: false }),
      4000,
    );
    this.heatMesh.count = 0;
    this.heatMesh.frustumCulled = false;
    this.heatMesh.setColorAt(0, new THREE.Color());
    this.heatMesh.renderOrder = 4;
    this.heat.add(this.heatMesh);
    this.heat.visible = false;

    // точки конфликтов
    const pts: { x: number; y: number; c: string }[] = [];
    const o = { x: 0, y: 0, h: 0 };
    const seen = new Set<string>();
    net.links.forEach((l) => {
      const p = new Path(l.pts);
      for (const [other, , s, kind, rule] of l.conflicts) {
        p.at(s, o);
        const key = `${Math.round(o.x * 2)},${Math.round(o.y * 2)},${kind}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const c = rule === "yield" ? "#4cff9a" : kind === "merge" ? "#3fd0ff" : kind === "ped" || other === "cw" ? "#ffd23f" : "#ff4fd8";
        pts.push({ x: o.x, y: o.y, c });
      }
    });
    const dg = new THREE.CircleGeometry(0.42, 12);
    dg.rotateX(-Math.PI / 2);
    const dots = new THREE.InstancedMesh(dg, new THREE.MeshBasicMaterial({ toneMapped: false, depthWrite: false, transparent: true }), Math.max(1, pts.length));
    const m = new THREE.Matrix4();
    pts.forEach((p, i) => {
      m.makeTranslation(p.x, 0.07, -p.y);
      dots.setMatrixAt(i, m);
      dots.setColorAt(i, new THREE.Color(p.c));
    });
    dots.count = pts.length;
    dots.renderOrder = 5;
    this.conflicts.add(dots);
    this.conflicts.visible = false;

    const thin = new THREE.RingGeometry(0.93, 1, 64);
    thin.rotateX(-Math.PI / 2);
    this.select = new THREE.Mesh(
      thin,
      new THREE.MeshBasicMaterial({ color: "#7cf7ff", transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false }),
    );
    this.select.visible = false;
    this.select.renderOrder = 6;
    this.group.add(this.conflicts, this.heat, this.select);
  }

  clear() {
    for (const b of this.beacons.values()) this.group.remove(b.g);
    this.beacons.clear();
    for (const f of this.flashes) this.group.remove(f.mesh);
    this.flashes = [];
    this.heatN = 0;
    this.heatMesh.count = 0;
  }

  /** Новые события из кадра. */
  add(events: SimEvent[], now: number, fresh: boolean) {
    for (const ev of events) {
      if (ev.kind === "crash") {
        this.addHeat(ev.pos[0], ev.pos[1], 16, "#ff3030", 1);
        if (!this.beacons.has(ev.id)) this.beacon(ev);
        if (fresh) this.flash(ev.pos[0], ev.pos[1], "#ff4040", 18, 1.6, now);
      } else if (ev.kind === "near_miss") {
        this.addHeat(ev.pos[0], ev.pos[1], 10, ev.sub === "pedestrian" ? "#ff8a1e" : "#ffc21e", 0.5);
        if (fresh) this.flash(ev.pos[0], ev.pos[1], ev.sub === "pedestrian" ? "#ff9a2e" : "#ffd23f", 7, 1.2, now);
      } else if (ev.kind === "red_run" && fresh) {
        this.flash(ev.pos[0], ev.pos[1], "#ff3df2", 6, 1.0, now);
      } else if (ev.kind === "jaywalk" && fresh) {
        this.flash(ev.pos[0], ev.pos[1], "#ff9a2e", 4, 1.0, now);
      }
    }
  }

  private addHeat(x: number, y: number, size: number, color: string, w: number) {
    const i = this.heatN % 4000;
    this.heatN++;
    const m = new THREE.Matrix4().compose(new THREE.Vector3(x, 0.09, -y), new THREE.Quaternion(), new THREE.Vector3(size, 1, size));
    this.heatMesh.setMatrixAt(i, m);
    this.heatMesh.setColorAt(i, new THREE.Color(color).multiplyScalar(w));
    this.heatMesh.count = Math.min(this.heatN, 4000);
    this.heatMesh.instanceMatrix.needsUpdate = true;
    if (this.heatMesh.instanceColor) this.heatMesh.instanceColor.needsUpdate = true;
  }

  private beacon(ev: SimEvent) {
    const g = new THREE.Group();
    g.position.set(ev.pos[0], 0, -ev.pos[1]);
    const beam = new THREE.Mesh(this.beamGeo, this.beamMat);
    const ring = new THREE.Mesh(
      this.ringGeo,
      new THREE.MeshBasicMaterial({ color: "#ff2a2a", transparent: true, depthWrite: false, toneMapped: false }),
    );
    ring.position.y = 0.12;
    const icon = new THREE.Sprite(this.iconMat);
    icon.position.y = 11;
    icon.scale.set(0.034, 0.034, 1);
    icon.renderOrder = 10;
    g.add(beam, ring, icon);
    this.group.add(g);
    this.beacons.set(ev.id, { g, ev, ring, beam });
  }

  private flash(x: number, y: number, color: string, size: number, life: number, now: number) {
    const mesh = new THREE.Mesh(
      this.ringGeo,
      new THREE.MeshBasicMaterial({ color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }),
    );
    mesh.position.set(x, 0.14, -y);
    mesh.renderOrder = 6;
    this.group.add(mesh);
    this.flashes.push({ mesh, born: now, life, size });
  }

  update(now: number, simT: number) {
    for (const [id, b] of this.beacons) {
      const age = simT - b.ev.t;
      if (age > CRASH_LIFE || age < -1) {
        this.group.remove(b.g);
        (b.ring.material as THREE.Material).dispose();
        this.beacons.delete(id);
        continue;
      }
      const k = (now * 1.4 + id * 0.3) % 1;
      b.ring.scale.setScalar(3 + k * 9);
      (b.ring.material as THREE.MeshBasicMaterial).opacity = (1 - k) * 0.9;
      const fade = 1 - Math.max(0, age - CRASH_LIFE + 20) / 20;
      b.beam.scale.set(1, 0.85 + 0.15 * Math.sin(now * 3 + id), 1);
      b.beam.visible = fade > 0.02;
      this.beamMat.opacity = 0.85;
    }
    this.flashes = this.flashes.filter((f) => {
      const t = (now - f.born) / f.life;
      if (t >= 1) {
        this.group.remove(f.mesh);
        (f.mesh.material as THREE.Material).dispose();
        return false;
      }
      f.mesh.scale.setScalar(1 + t * f.size);
      (f.mesh.material as THREE.MeshBasicMaterial).opacity = (1 - t) ** 1.5;
      return true;
    });
    if (this.select.visible) {
      const k = (now * 1.2) % 1;
      (this.select.material as THREE.MeshBasicMaterial).opacity = 0.55 + 0.4 * Math.sin(k * Math.PI * 2) ** 2;
    }
  }

  crashes() {
    return [...this.beacons.values()].map((b) => b.ev);
  }

  setSelect(x: number, y: number, r: number) {
    this.select.visible = true;
    this.select.position.set(x, 0.15, -y);
    this.select.scale.setScalar(r);
  }

  hideSelect() {
    this.select.visible = false;
  }
}

function iconTex() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const ctx = c.getContext("2d")!;
  ctx.beginPath();
  ctx.arc(64, 64, 54, 0, Math.PI * 2);
  ctx.fillStyle = "#ff2f3d";
  ctx.shadowColor = "rgba(255,40,60,0.9)";
  ctx.shadowBlur = 14;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.lineWidth = 7;
  ctx.strokeStyle = "#ffffff";
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(56, 28, 16, 46);
  ctx.beginPath();
  ctx.arc(64, 92, 9, 0, Math.PI * 2);
  ctx.fill();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function beamTex() {
  const c = document.createElement("canvas");
  c.width = 4;
  c.height = 128;
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 0, 128);
  g.addColorStop(0, "rgba(255,255,255,0)");
  g.addColorStop(0.6, "rgba(255,255,255,0.25)");
  g.addColorStop(1, "rgba(255,255,255,0.8)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 4, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
