// Окружение: дома с окнами из шейдера, деревья, фонари с пятнами света.
import * as THREE from "three";
import type { SceneryJ } from "../types";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
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
          attribute float aSeed; varying vec3 vLocal; varying vec3 vObjN; varying float vSeed; varying vec3 vSc;`)
        .replace("#include <begin_vertex>", `#include <begin_vertex>
          vec3 sc = vec3(length(instanceMatrix[0].xyz), length(instanceMatrix[1].xyz), length(instanceMatrix[2].xyz));
          vLocal = position * sc; vObjN = normal; vSeed = aSeed; vSc = sc;`);
      sh.fragmentShader = sh.fragmentShader
        .replace("#include <common>", `#include <common>
          uniform float uNight; uniform float uLit;
          varying vec3 vLocal; varying vec3 vObjN; varying float vSeed; varying vec3 vSc;
          float h21(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
          // ступенька со сглаживанием по размеру пикселя: без ряби вдали
          float aa(float e, float x){ float w = fwidth(x) * 0.75; return smoothstep(e - w, e + w, x); }
          float box2(vec2 f, vec2 lo, vec2 hi){ return aa(lo.x, f.x) * (1.0 - aa(hi.x, f.x)) * aa(lo.y, f.y) * (1.0 - aa(hi.y, f.y)); }`)
        .replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
          float typ = fract(vSeed * 3.17);
          float isBrick = step(typ, 0.34);
          float isPanel = step(0.72, typ);
          if (abs(vObjN.y) < 0.5) {
            float u = abs(vObjN.x) > 0.5 ? vLocal.z : vLocal.x;
            float v = vLocal.y;
            float H = vSc.y;
            vec3 base = diffuseColor.rgb;
            if (isBrick > 0.5) {
              // кирпич 25 × 7,5 см, перевязка со сдвигом рядов
              vec3 bc = mix(vec3(0.50, 0.24, 0.18), vec3(0.60, 0.40, 0.28), fract(vSeed * 7.31));
              vec2 bp = vec2(u / 0.25, v / 0.075);
              bp.x += 0.5 * mod(floor(bp.y), 2.0);
              vec2 bf = fract(bp);
              float fade = clamp(1.0 - max(fwidth(bp.x), fwidth(bp.y)) * 1.5, 0.0, 1.0);
              float mortar = (1.0 - aa(0.06, bf.x) * aa(0.14, bf.y)) * fade;
              float j = h21(floor(bp));
              base = mix(bc * (0.86 + 0.28 * j * fade), vec3(0.72, 0.69, 0.63), mortar * 0.75);
            } else if (isPanel > 0.5) {
              // бетонные панели 3 × 3,2 м со швами
              vec2 pf = vec2(fract(u / 3.0 + 0.5), fract(v / 3.2));
              float seam = 1.0 - box2(pf, vec2(0.012), vec2(0.988));
              base *= 1.0 - seam * 0.22;
              base *= 0.94 + 0.08 * h21(floor(vec2(u / 3.0, v / 3.2)));
            } else {
              // штукатурка: лёгкая неровность и карниз на каждом этаже
              float fy = fract(v / 3.2);
              base *= 0.96 + 0.06 * h21(floor(vec2(u, v) * 3.0));
              base *= 1.0 - 0.12 * (1.0 - aa(0.04, fy)) - 0.06 * (aa(0.97, fy));
            }
            // окна
            float cw = isBrick > 0.5 ? 2.2 : isPanel > 0.5 ? 3.0 : 2.6;
            float fl = floor(v / 3.2);
            float col = floor(u / cw + 50.0);
            vec2 f = vec2(fract(u / cw + 50.0), fract(v / 3.2));
            float win = isPanel > 0.5 ? box2(f, vec2(0.12, 0.3), vec2(0.88, 0.86)) : box2(f, vec2(0.24, 0.3), vec2(0.76, 0.88));
            float frame = (isPanel > 0.5 ? box2(f, vec2(0.1, 0.27), vec2(0.9, 0.89)) : box2(f, vec2(0.21, 0.27), vec2(0.79, 0.91))) - win;
            // первый этаж: витрины у части домов
            float shop = step(7.0, H) * step(fract(vSeed * 5.13), 0.6) * (1.0 - aa(3.6, v));
            float shopWin = box2(vec2(f.x, v / 3.6), vec2(0.06, 0.1), vec2(0.94, 0.8));
            win = mix(win, shopWin, shop);
            float awning = shop * aa(3.0, v) * (1.0 - aa(3.45, v));
            win *= 1.0 - aa(H - 0.9, v);
            float face = floor(vObjN.x * 1.5 + 2.0) * 3.0 + floor(vObjN.z * 1.5 + 2.0);
            float r = h21(vec2(col + face * 7.0, fl + floor(vSeed * 997.0) * 0.37));
            float lit = step(1.0 - uLit, r) * win;
            vec3 glass = mix(vec3(0.10, 0.14, 0.19), vec3(0.24, 0.32, 0.40), f.y);
            base = mix(base, vec3(0.86, 0.85, 0.82), frame * 0.85);
            base = mix(base, glass, win);
            vec3 awnCol = mix(vec3(0.62, 0.16, 0.14), vec3(0.14, 0.38, 0.32), step(0.5, fract(vSeed * 11.7)));
            base = mix(base, awnCol, awning);
            // парапет и тёмный цоколь
            base *= 1.0 - 0.1 * aa(H - 0.6, v);
            base *= mix(0.7, 1.0, smoothstep(0.0, 0.6, v));
            diffuseColor.rgb = base;
            // стекло отражает небо
            roughnessFactor = mix(roughnessFactor, 0.06, win);
            metalnessFactor = mix(metalnessFactor, 0.55, win);
            vec3 warm = mix(vec3(1.0, 0.78, 0.48), vec3(0.75, 0.85, 1.0), step(0.82, fract(r * 7.13)));
            totalEmissiveRadiance += warm * lit * uNight * 0.75;
          } else if (vObjN.y > 0.5) {
            // плоская крыша: гравий, светлый парапет по краю
            float k = floor(fract(vSeed * 2.3) * 4.0);
            vec3 roof = k < 1.0 ? vec3(0.36, 0.37, 0.39) : k < 2.0 ? vec3(0.46, 0.44, 0.40) : k < 3.0 ? vec3(0.30, 0.32, 0.35) : vec3(0.52, 0.50, 0.47);
            roof *= 0.9 + 0.2 * h21(floor(vLocal.xz * 4.0));
            vec2 e = vec2(vSc.x * 0.5 - abs(vLocal.x), vSc.z * 0.5 - abs(vLocal.z));
            float edge = 1.0 - aa(0.45, min(e.x, e.y));
            diffuseColor.rgb = mix(roof, vec3(0.78, 0.76, 0.72), edge);
          }`);
    };
    bm.customProgramCacheKey = () => "buildings-v2";
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

    // двускатные крыши малоэтажных домов и блоки на плоских крышах
    const gable = gableGeometry();
    const pitched = sc.buildings.filter((b) => b.h <= 10.5 && b.roof !== 2);
    const flatRoof = sc.buildings.filter((b) => !(b.h <= 10.5 && b.roof !== 2));
    const roofMesh = new THREE.InstancedMesh(gable, new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.75, flatShading: true }), Math.max(1, pitched.length));
    const ROOFS = ["#5b5f66", "#8e4a36", "#6d4b3c", "#4c5a63", "#7a6a5a"];
    pitched.forEach((b, i) => {
      const along = b.w >= b.d;
      const span = along ? b.d : b.w;
      dummy.position.set(b.pos[0], b.h, -b.pos[1]);
      dummy.rotation.set(0, b.a + (along ? 0 : Math.PI / 2), 0);
      dummy.scale.set((along ? b.w : b.d) * 1.04, span * 0.38, span * 1.08);
      dummy.updateMatrix();
      roofMesh.setMatrixAt(i, dummy.matrix);
      roofMesh.setColorAt(i, color.set(ROOFS[(i * 3 + b.style) % ROOFS.length]));
    });
    roofMesh.count = pitched.length;
    const unitGeo = new THREE.BoxGeometry(1, 1, 1);
    unitGeo.translate(0, 0.5, 0);
    const units: THREE.Matrix4[] = [];
    const q = new THREE.Quaternion();
    flatRoof.forEach((b) => {
      const n = 1 + Math.floor(rnd() * 3);
      for (let k = 0; k < n; k++) {
        const lx = (rnd() - 0.5) * (b.w - 3);
        const lz = (rnd() - 0.5) * (b.d - 3);
        const c = Math.cos(b.a);
        const s = Math.sin(b.a);
        const wx = b.pos[0] + lx * c + lz * s;
        const wz = -b.pos[1] - lx * s + lz * c;
        const sz = k === 0 && b.h > 14 ? [3, 2.6, 3.4] : [1 + rnd() * 1.8, 0.8 + rnd() * 1.2, 1 + rnd() * 1.6];
        q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), b.a);
        units.push(new THREE.Matrix4().compose(new THREE.Vector3(wx, b.h, wz), q, new THREE.Vector3(sz[0], sz[1], sz[2])));
      }
    });
    const unitMesh = new THREE.InstancedMesh(unitGeo, new THREE.MeshStandardMaterial({ color: "#a9aaa8", roughness: 0.7, metalness: 0.2 }), Math.max(1, units.length));
    units.forEach((m, i) => unitMesh.setMatrixAt(i, m));
    unitMesh.count = units.length;
    for (const m of [roofMesh, unitMesh]) {
      m.castShadow = true;
      m.receiveShadow = true;
      this.group.add(m);
    }

    // деревья: ствол и крона двух видов
    const trees = sc.trees;
    const trunkGeo = new THREE.CylinderGeometry(0.12, 0.2, 1, 6);
    trunkGeo.translate(0, 0.5, 0);
    const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshStandardMaterial({ color: "#6b5444", roughness: 1 }), trees.length);
    // лиственная крона — три шара разного размера; ель — два яруса
    const blob = (r: number, x: number, y: number, z: number) => {
      const g = new THREE.IcosahedronGeometry(r, 1);
      g.translate(x, y, z);
      return g;
    };
    const roundGeo = mergeGeometries([blob(1, 0, 0, 0), blob(0.72, 0.62, 0.28, 0.2), blob(0.66, -0.5, 0.36, -0.32), blob(0.55, 0.05, 0.72, 0.1)]);
    const c1 = new THREE.ConeGeometry(1, 1.8, 8);
    c1.translate(0, 0.9, 0);
    const c2 = new THREE.ConeGeometry(0.74, 1.5, 8);
    c2.translate(0, 1.85, 0);
    const coneGeo = mergeGeometries([c1, c2]);
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
      dummy.rotation.set(0, rnd() * 6.28, 0);
      dummy.scale.set(t.r * 0.82, t.r * 0.78, t.r * 0.82);
      dummy.updateMatrix();
      roundMesh.setMatrixAt(i, dummy.matrix);
      color.set(LEAVES[(i * 7 + t.kind) % (LEAVES.length - (rnd() < 0.85 ? 1 : 0))]);
      roundMesh.setColorAt(i, color);
    });
    cones.forEach((t, i) => {
      dummy.position.set(t.pos[0], t.r * 0.55, -t.pos[1]);
      dummy.rotation.set(0, rnd() * 3, 0);
      dummy.scale.set(t.r * 0.85, t.r * 1.15, t.r * 0.85);
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

/** Двускатная крыша: основание 1 × 1 на высоте 0, конёк вдоль x на высоте 1. */
function gableGeometry() {
  const p = [
    // скаты
    -0.5, 0, 0.5, 0.5, 0, 0.5, 0.5, 1, 0, -0.5, 1, 0,
    0.5, 0, -0.5, -0.5, 0, -0.5, -0.5, 1, 0, 0.5, 1, 0,
    // фронтоны
    -0.5, 0, -0.5, -0.5, 0, 0.5, -0.5, 1, 0,
    0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 1, 0,
  ];
  const idx = [0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 8, 9, 10, 11, 12, 13];
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g.toNonIndexed();
}
