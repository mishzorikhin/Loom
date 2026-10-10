// Окружение: дома с окнами из шейдера, деревья, фонари с пятнами света.
import * as THREE from "three";
import type { SceneryJ } from "../types";
import type { Daylight } from "./stage";

const FACADES = ["#e9e3d8", "#d8cdbf", "#c9d0d6", "#e6d6c4", "#bcc7cc", "#d9c7b5", "#cfd6c6", "#e3dcd0"];
const LEAVES = ["#5f8a46", "#6f9a4e", "#4f7c45", "#7fa457", "#8a9f4a", "#c58a3c"];

export function radialTexture(inner: string, outer = "rgba(0,0,0,0)", size = 128) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, inner);
  g.addColorStop(1, outer);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class City {
  readonly group = new THREE.Group();
  private windowUniforms = { uNight: { value: 0 }, uLit: { value: 0.5 } };
  private lampHeadMat: THREE.MeshStandardMaterial;
  private poolMat: THREE.MeshBasicMaterial;
  private glowMat: THREE.PointsMaterial;

  constructor(sc: SceneryJ) {
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    let seed = 11;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

    // дома
    const n = sc.buildings.length;
    const box = new THREE.BoxGeometry(1, 1, 1);
    box.translate(0, 0.5, 0);
    const seeds = new Float32Array(n);
    box.setAttribute("aSeed", new THREE.InstancedBufferAttribute(seeds, 1));
    const bm = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.82, metalness: 0.0 });
    const u = this.windowUniforms;
    bm.onBeforeCompile = (sh) => {
      sh.uniforms.uNight = u.uNight;
      sh.uniforms.uLit = u.uLit;
      sh.vertexShader = sh.vertexShader
        .replace("#include <common>", `#include <common>
          attribute float aSeed; varying vec3 vLocal; varying vec3 vObjN; varying float vSeed; varying float vH;`)
        .replace("#include <begin_vertex>", `#include <begin_vertex>
          vec3 sc = vec3(length(instanceMatrix[0].xyz), length(instanceMatrix[1].xyz), length(instanceMatrix[2].xyz));
          vLocal = position * sc; vObjN = normal; vSeed = aSeed; vH = sc.y;`);
      sh.fragmentShader = sh.fragmentShader
        .replace("#include <common>", `#include <common>
          uniform float uNight; uniform float uLit;
          varying vec3 vLocal; varying vec3 vObjN; varying float vSeed; varying float vH;
          float h21(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }`)
        .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
          float side = 1.0 - step(0.5, abs(vObjN.y));
          if (side > 0.5) {
            float u = abs(vObjN.x) > 0.5 ? vLocal.z : vLocal.x;
            float v = vLocal.y;
            float fl = floor(v / 3.2);
            float col = floor(u / 2.6 + 50.0);
            vec2 f = vec2(fract(u / 2.6 + 50.0), fract(v / 3.2));
            float ground = step(v, 3.6);
            float win = step(0.18, f.x) * step(f.x, 0.82) * step(0.32, f.y) * step(f.y, 0.86);
            win = mix(win, step(0.08, f.x) * step(f.x, 0.92) * step(0.12, f.y) * step(f.y, 0.8), ground);
            win *= step(v, vH - 0.9);
            float face = floor(vObjN.x * 1.5 + 2.0) * 3.0 + floor(vObjN.z * 1.5 + 2.0);
            float r = h21(vec2(col + face * 7.0, fl + floor(vSeed * 997.0) * 0.37));
            float lit = step(1.0 - uLit, r) * win;
            vec3 glass = mix(vec3(0.18, 0.24, 0.32), vec3(0.42, 0.55, 0.68), smoothstep(0.0, 1.0, f.y));
            diffuseColor.rgb = mix(diffuseColor.rgb, glass, win * 0.82);
            vec3 warm = mix(vec3(1.0, 0.78, 0.48), vec3(0.75, 0.85, 1.0), step(0.82, fract(r * 7.13)));
            totalEmissiveRadiance += warm * lit * uNight * 0.75;
            float band = smoothstep(0.0, 0.25, f.y) * (1.0 - smoothstep(0.92, 1.0, f.y));
            diffuseColor.rgb *= mix(0.92, 1.0, band);
            diffuseColor.rgb *= mix(0.72, 1.0, smoothstep(0.0, 2.2, v));
          } else if (vObjN.y > 0.5) {
            float k = floor(vSeed * 5.0);
            vec3 roof = k < 1.0 ? vec3(0.42, 0.44, 0.48) : k < 2.0 ? vec3(0.62, 0.36, 0.28) : k < 3.0 ? vec3(0.36, 0.47, 0.46) : k < 4.0 ? vec3(0.55, 0.55, 0.52) : vec3(0.3, 0.32, 0.36);
            diffuseColor.rgb = roof;
          }`);
    };
    const buildings = new THREE.InstancedMesh(box, bm, n);
    sc.buildings.forEach((b, i) => {
      dummy.position.set(b.pos[0], 0, -b.pos[1]);
      dummy.rotation.set(0, b.a, 0);
      dummy.scale.set(b.w, b.h, b.d);
      dummy.updateMatrix();
      buildings.setMatrixAt(i, dummy.matrix);
      color.set(FACADES[b.style % FACADES.length]);
      buildings.setColorAt(i, color);
      seeds[i] = (i * 0.618) % 1;
    });
    buildings.castShadow = true;
    buildings.receiveShadow = true;
    this.group.add(buildings);

    // деревья: ствол и крона двух видов
    const trees = sc.trees;
    const trunkGeo = new THREE.CylinderGeometry(0.12, 0.2, 1, 6);
    trunkGeo.translate(0, 0.5, 0);
    const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshStandardMaterial({ color: "#6b5444", roughness: 1 }), trees.length);
    const roundGeo = new THREE.IcosahedronGeometry(1, 1);
    const coneGeo = new THREE.ConeGeometry(1, 2.4, 7);
    coneGeo.translate(0, 1.2, 0);
    const leafMat = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.9, flatShading: true });
    const round = trees.filter((t) => t.kind !== 2);
    const cones = trees.filter((t) => t.kind === 2);
    const roundMesh = new THREE.InstancedMesh(roundGeo, leafMat, round.length);
    const coneMesh = new THREE.InstancedMesh(coneGeo, leafMat, cones.length);
    trees.forEach((t, i) => {
      const h = t.r * (t.kind === 2 ? 0.9 : 1.3);
      dummy.position.set(t.pos[0], 0, -t.pos[1]);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(t.r * 0.9, h, t.r * 0.9);
      dummy.updateMatrix();
      trunks.setMatrixAt(i, dummy.matrix);
    });
    round.forEach((t, i) => {
      dummy.position.set(t.pos[0], t.r * 1.3 + t.r * 0.75, -t.pos[1]);
      dummy.rotation.set(rnd() * 3, rnd() * 3, 0);
      dummy.scale.set(t.r, t.r * 0.9, t.r);
      dummy.updateMatrix();
      roundMesh.setMatrixAt(i, dummy.matrix);
      color.set(LEAVES[(i * 7 + t.kind) % (LEAVES.length - (rnd() < 0.85 ? 1 : 0))]);
      roundMesh.setColorAt(i, color);
    });
    cones.forEach((t, i) => {
      dummy.position.set(t.pos[0], t.r * 0.8, -t.pos[1]);
      dummy.rotation.set(0, rnd() * 3, 0);
      dummy.scale.set(t.r * 0.8, t.r * 1.1, t.r * 0.8);
      dummy.updateMatrix();
      coneMesh.setMatrixAt(i, dummy.matrix);
      color.set(i % 3 ? "#3f6b48" : "#4c7a52");
      coneMesh.setColorAt(i, color);
    });
    for (const m of [trunks, roundMesh, coneMesh]) {
      m.castShadow = true;
      m.receiveShadow = true;
      this.group.add(m);
    }

    // фонари: опора, плафон, ореол и пятно на земле
    const lamps = sc.lamps;
    const poleGeo = new THREE.CylinderGeometry(0.07, 0.1, 7.5, 6);
    poleGeo.translate(0, 3.75, 0);
    const armGeo = new THREE.BoxGeometry(1.8, 0.08, 0.08);
    armGeo.translate(0.9, 7.4, 0);
    const poleMat = new THREE.MeshStandardMaterial({ color: "#4a4f57", roughness: 0.6, metalness: 0.4 });
    const poles = new THREE.InstancedMesh(poleGeo, poleMat, lamps.length);
    const arms = new THREE.InstancedMesh(armGeo, poleMat, lamps.length);
    const headGeo = new THREE.BoxGeometry(0.7, 0.12, 0.3);
    headGeo.translate(1.75, 7.33, 0);
    this.lampHeadMat = new THREE.MeshStandardMaterial({ color: "#f3efe4", emissive: "#ffcf8a", emissiveIntensity: 0 });
    const heads = new THREE.InstancedMesh(headGeo, this.lampHeadMat, lamps.length);
    this.poolMat = new THREE.MeshBasicMaterial({
      map: radialTexture("rgba(255,205,140,0.9)"), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0,
    });
    const poolGeo = new THREE.PlaneGeometry(1, 1);
    poolGeo.rotateX(-Math.PI / 2);
    const pools = new THREE.InstancedMesh(poolGeo, this.poolMat, lamps.length);
    const glowPos: number[] = [];
    lamps.forEach((l, i) => {
      dummy.position.set(l.pos[0], 0, -l.pos[1]);
      dummy.rotation.set(0, l.a, 0);
      dummy.scale.set(1, 1, 1);
      dummy.updateMatrix();
      poles.setMatrixAt(i, dummy.matrix);
      arms.setMatrixAt(i, dummy.matrix);
      heads.setMatrixAt(i, dummy.matrix);
      const hx = l.pos[0] + Math.cos(l.a) * 1.75;
      const hy = l.pos[1] + Math.sin(l.a) * 1.75;
      dummy.position.set(hx, 0.05, -hy);
      dummy.rotation.set(0, 0, 0);
      dummy.scale.set(16, 1, 16);
      dummy.updateMatrix();
      pools.setMatrixAt(i, dummy.matrix);
      glowPos.push(hx, 7.2, -hy);
    });
    poles.castShadow = true;
    pools.renderOrder = 2;
    this.group.add(poles, arms, heads, pools);
    const glowGeo = new THREE.BufferGeometry();
    glowGeo.setAttribute("position", new THREE.Float32BufferAttribute(glowPos, 3));
    this.glowMat = new THREE.PointsMaterial({
      size: 5, map: radialTexture("rgba(255,220,170,1)"), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0,
    });
    this.group.add(new THREE.Points(glowGeo, this.glowMat));
  }

  update(day: Daylight) {
    const n = day.night;
    this.windowUniforms.uNight.value = n;
    this.windowUniforms.uLit.value = 0.18 + 0.22 * n;
    this.lampHeadMat.emissiveIntensity = n * 2.5;
    this.poolMat.opacity = n * 0.4;
    this.glowMat.opacity = n * 0.55;
  }
}
