// Сцена: рендер, камера, управление, свет суток, постобработка.
import * as THREE from "three";
import { MapControls } from "three/addons/controls/MapControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { HorizontalTiltShiftShader } from "three/addons/shaders/HorizontalTiltShiftShader.js";
import { VerticalTiltShiftShader } from "three/addons/shaders/VerticalTiltShiftShader.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { Sky } from "three/addons/objects/Sky.js";
import { clamp, smooth } from "../geom";

/** Мировые координаты (x на восток, y на север) → сцена (x, 0, -y). */
export function w2s(x: number, y: number, h = 0) {
  return new THREE.Vector3(x, h, -y);
}

interface Key {
  h: number;
  top: string;
  hor: string;
  sun: string;
  sunI: number;
  hemiI: number;
  fog: string;
}

// ключевые точки суток: небо, горизонт, солнце, рассеянный свет
const KEYS: Key[] = [
  { h: 0, top: "#03060f", hor: "#0b1530", sun: "#8fa6ff", sunI: 0.22, hemiI: 0.32, fog: "#0a1226" },
  { h: 5.2, top: "#0a1230", hor: "#2c2a52", sun: "#9aa8ff", sunI: 0.2, hemiI: 0.35, fog: "#1b1d3a" },
  { h: 6.3, top: "#3c5a9a", hor: "#ff9e6e", sun: "#ffa66a", sunI: 1.8, hemiI: 0.75, fog: "#c98d78" },
  { h: 7.4, top: "#5b93dd", hor: "#ffd9b0", sun: "#ffd8ac", sunI: 3.0, hemiI: 1.05, fog: "#e8d3bf" },
  { h: 10, top: "#4f8fe0", hor: "#d6e9fb", sun: "#fff6ea", sunI: 3.1, hemiI: 1.0, fog: "#d3e2f0" },
  { h: 15, top: "#4a88da", hor: "#d9e8f6", sun: "#fff3e0", sunI: 3.0, hemiI: 1.0, fog: "#d6e2ec" },
  { h: 18.2, top: "#5577c0", hor: "#ffc79a", sun: "#ffb27a", sunI: 2.1, hemiI: 0.8, fog: "#e6c3a6" },
  { h: 19.6, top: "#2a3a78", hor: "#ff8a5c", sun: "#ff7a48", sunI: 0.9, hemiI: 0.55, fog: "#a8687a" },
  { h: 20.6, top: "#0d1638", hor: "#3d2f5e", sun: "#8f9cff", sunI: 0.25, hemiI: 0.38, fog: "#251f44" },
  { h: 24, top: "#03060f", hor: "#0b1530", sun: "#8fa6ff", sunI: 0.22, hemiI: 0.32, fog: "#0a1226" },
];

export interface Daylight {
  hour: number;
  night: number;   // 0 — день, 1 — ночь: фонари, окна, фары
  sunDir: THREE.Vector3;
}

export class Stage {
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly controls: MapControls;
  readonly composer: EffectComposer;
  readonly bloom: UnrealBloomPass;
  readonly sun: THREE.DirectionalLight;
  readonly hemi: THREE.HemisphereLight;
  readonly sky: THREE.Mesh;
  private skyMat: THREE.ShaderMaterial;
  private tiltH: ShaderPass;
  /** Физическое небо (рассеяние в атмосфере, облака) — фон днём и источник освещения сцены. */
  private skyPhys: Sky;
  private envSky: Sky;
  private envScene = new THREE.Scene();
  private pmrem: THREE.PMREMGenerator;
  private envRT: THREE.WebGLRenderTarget | null = null;
  private envHour = -100;
  private gtao: GTAOPass;
  private grade: ShaderPass;
  private time = 0;
  quality: "high" | "low" = "high";
  private tiltV: ShaderPass;
  readonly day: Daylight = { hour: 12, night: 0, sunDir: new THREE.Vector3(1, 1, 1) };
  private center = new THREE.Vector3();
  private radius = 200;
  private fly: { from: THREE.Vector3; to: THREE.Vector3; tFrom: THREE.Vector3; tTo: THREE.Vector3; t: number; dur: number } | null = null;
  miniature = false;
  /** Свободная область экрана между колонками интерфейса: её центр — центр кадра. */
  private area = { x: 0, y: 0, w: 0, h: 0 };

  constructor(readonly host: HTMLElement) {
    const r = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
    r.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    r.setSize(host.clientWidth, host.clientHeight);
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.0;
    r.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(r.domElement);
    this.renderer = r;

    this.camera = new THREE.PerspectiveCamera(32, host.clientWidth / host.clientHeight, 1, 6000);
    this.camera.position.set(260, 320, 380);

    const c = new MapControls(this.camera, r.domElement);
    c.enableDamping = true;
    c.dampingFactor = 0.08;
    c.screenSpacePanning = false;
    c.maxPolarAngle = Math.PI * 0.44;
    c.minDistance = 12;
    c.maxDistance = 2200;
    c.zoomSpeed = 1.2;
    this.controls = c;

    // небо — купол с градиентом и солнечным ореолом
    this.skyMat = new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      fog: false,
      uniforms: {
        top: { value: new THREE.Color("#4f8fe0") },
        hor: { value: new THREE.Color("#d6e9fb") },
        sunCol: { value: new THREE.Color("#fff") },
        sunDir: { value: new THREE.Vector3(0, 1, 0) },
        stars: { value: 0 },
      },
      vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `
        uniform vec3 top; uniform vec3 hor; uniform vec3 sunCol; uniform vec3 sunDir; uniform float stars;
        varying vec3 vDir;
        float hash(vec3 p){ p = fract(p*0.3183099+.1); p *= 17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
        void main(){
          float h = clamp(vDir.y, -0.2, 1.0);
          vec3 col = mix(hor, top, pow(max(h,0.0), 0.55));
          col = mix(col, hor*0.8, smoothstep(0.0,-0.2,h));
          float d = max(dot(normalize(vDir), normalize(sunDir)), 0.0);
          col += sunCol * (pow(d, 600.0)*3.0 + pow(d, 12.0)*0.25);
          vec3 q = floor(vDir*420.0);
          float s = step(0.9975, hash(q)) * smoothstep(0.05, 0.4, h) * stars;
          col += vec3(s);
          gl_FragColor = vec4(col, 1.0);
        }`,
    });
    this.skyMat.transparent = true;
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(2800, 32, 16), this.skyMat);
    this.sky.renderOrder = -10;
    this.skyPhys = new Sky();
    this.skyPhys.scale.setScalar(5000);
    this.skyPhys.renderOrder = -11;
    this.envSky = new Sky();
    this.envSky.scale.setScalar(1000);
    this.envScene.add(this.envSky);
    for (const s of [this.skyPhys, this.envSky]) {
      const u = s.material.uniforms;
      u.turbidity.value = 5;
      u.rayleigh.value = 1.4;
      u.mieCoefficient.value = 0.004;
      u.mieDirectionalG.value = 0.82;
      if (u.cloudCoverage) u.cloudCoverage.value = 0.32;
      if (u.cloudDensity) u.cloudDensity.value = 0.35;
    }
    // в карте окружения без диска солнца: иначе его яркость отражается в фасадах и зажигает свечение
    this.envSky.material.uniforms.showSunDisc.value = 0;
    this.scene.add(this.skyPhys, this.sky);
    // воздушная перспектива: даль уходит в цвет горизонта
    this.scene.fog = new THREE.FogExp2("#d6e2ec", 0.00045);

    this.pmrem = new THREE.PMREMGenerator(r);
    this.hemi = new THREE.HemisphereLight("#cfe4ff", "#5d6a4f", 1.0);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight("#ffffff", 3);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(4096, 4096);
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.6;
    this.sun.shadow.radius = 3;
    this.scene.add(this.sun, this.sun.target);

    const size = new THREE.Vector2(host.clientWidth, host.clientHeight);
    const rt = new THREE.WebGLRenderTarget(size.x, size.y, { type: THREE.HalfFloatType, samples: 4 });
    this.composer = new EffectComposer(r, rt);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    // мягкое затенение в углах, под машинами, у стен и деревьев
    this.gtao = new GTAOPass(this.scene, this.camera, size.x, size.y);
    this.gtao.updateGtaoMaterial({ radius: 3.5, distanceExponent: 1.2, thickness: 3, scale: 1.1, samples: 12, distanceFallOff: 1 });
    this.gtao.blendIntensity = 0.85;
    this.composer.addPass(this.gtao);
    this.bloom = new UnrealBloomPass(size, 0.5, 0.55, 0.9);
    this.composer.addPass(this.bloom);
    this.tiltH = new ShaderPass(HorizontalTiltShiftShader);
    this.tiltV = new ShaderPass(VerticalTiltShiftShader);
    this.tiltH.enabled = this.tiltV.enabled = false;
    this.composer.addPass(this.tiltH);
    this.composer.addPass(this.tiltV);
    this.composer.addPass(new OutputPass());
    this.grade = new ShaderPass(GradeShader);
    this.composer.addPass(this.grade);

    window.addEventListener("resize", () => this.resize());
  }

  resize() {
    const w = this.host.clientWidth;
    const h = this.host.clientHeight;
    this.renderer.setSize(w, h);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.applyArea();
    const pr = this.renderer.getPixelRatio();
    this.tiltH.uniforms.h.value = 1.6 / (w * pr);
    this.tiltV.uniforms.v.value = 1.6 / (h * pr);
  }

  setFocusArea(x: number, y: number, w: number, h: number) {
    this.area = { x, y, w, h };
    this.applyArea();
  }

  private applyArea() {
    const W = this.host.clientWidth;
    const H = this.host.clientHeight;
    const a = this.area;
    if (a.w > 0 && a.h > 0) {
      // сдвиг главной точки проекции в центр свободной области; выбор мышью это учитывает сам
      this.camera.setViewOffset(W, H, W / 2 - (a.x + a.w / 2), H / 2 - (a.y + a.h / 2), W, H);
    } else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
  }

  /** Во сколько раз отодвинуть камеру, чтобы сеть влезла в свободную область. */
  private areaFit() {
    const W = this.host.clientWidth;
    const H = this.host.clientHeight;
    const a = this.area;
    if (!(a.w > 0 && a.h > 0)) return 1;
    return Math.min(1.8, Math.max(1, Math.min(W / a.w, H / a.h) * 0.92));
  }

  /** Высокое качество: затенение GTAO и плотность пикселей до 2; низкое — без них. */
  setQuality(q: "high" | "low") {
    this.quality = q;
    this.gtao.enabled = q === "high";
    this.renderer.setPixelRatio(q === "high" ? Math.min(window.devicePixelRatio, 2) : 1);
    this.sun.shadow.mapSize.set(q === "high" ? 4096 : 2048, q === "high" ? 4096 : 2048);
    this.sun.shadow.map?.dispose();
    this.sun.shadow.map = null;
    this.resize();
  }

  setMiniature(on: boolean) {
    this.miniature = on;
    this.tiltH.enabled = this.tiltV.enabled = on;
    this.resize();
  }

  /** Рамка сети: центр и радиус для камеры и тени. */
  frame(bbox: [number, number, number, number], animate = false) {
    const [x0, y0, x1, y1] = bbox;
    this.center.copy(w2s((x0 + x1) / 2, (y0 + y1) / 2));
    this.radius = Math.max(x1 - x0, y1 - y0) / 2 + 20;
    const s = this.sun.shadow.camera as THREE.OrthographicCamera;
    s.left = -this.radius * 1.3;
    s.right = this.radius * 1.3;
    s.top = this.radius * 1.3;
    s.bottom = -this.radius * 1.3;
    s.near = 1;
    s.far = this.radius * 6;
    s.updateProjectionMatrix();
    this.view("3d", animate);
  }

  view(kind: "3d" | "top" | "low", animate = true) {
    const d = this.radius * (kind === "low" ? 0.8 : 1.45) * this.areaFit();
    let pos: THREE.Vector3;
    if (kind === "top") pos = this.center.clone().add(new THREE.Vector3(0, d * 1.05, 0.01));
    else if (kind === "low") pos = this.center.clone().add(new THREE.Vector3(d * 0.55, d * 0.32, d * 0.75));
    else pos = this.center.clone().add(new THREE.Vector3(d * 0.42, d * 0.78, d * 0.62));
    this.flyTo(pos, this.center.clone(), animate ? 1.4 : 0);
  }

  focus(x: number, y: number, dist = 70) {
    const target = w2s(x, y);
    const dir = this.camera.position.clone().sub(this.controls.target).normalize();
    if (dir.y < 0.35) dir.y = 0.35;
    dir.normalize();
    this.flyTo(target.clone().add(dir.multiplyScalar(dist)), target, 1.1);
  }

  flyTo(pos: THREE.Vector3, target: THREE.Vector3, dur: number) {
    if (dur <= 0) {
      this.camera.position.copy(pos);
      this.controls.target.copy(target);
      this.controls.update();
      return;
    }
    this.fly = { from: this.camera.position.clone(), to: pos, tFrom: this.controls.target.clone(), tTo: target, t: 0, dur };
  }

  follow(x: number, y: number) {
    const t = w2s(x, y);
    const delta = t.clone().sub(this.controls.target);
    this.controls.target.add(delta);
    this.camera.position.add(delta);
  }

  /** Свет суток по часам симуляции. */
  setHour(hour: number) {
    this.day.hour = hour;
    let a = KEYS[0];
    let b = KEYS[KEYS.length - 1];
    for (let i = 0; i < KEYS.length - 1; i++) {
      if (hour >= KEYS[i].h && hour <= KEYS[i + 1].h) {
        a = KEYS[i];
        b = KEYS[i + 1];
        break;
      }
    }
    const t = smooth((hour - a.h) / Math.max(b.h - a.h, 1e-6));
    const mix = (x: string, y: string) => new THREE.Color(x).lerp(new THREE.Color(y), t);
    const top = mix(a.top, b.top);
    const hor = mix(a.hor, b.hor);
    const sunCol = mix(a.sun, b.sun);
    this.skyMat.uniforms.top.value.copy(top);
    this.skyMat.uniforms.hor.value.copy(hor);
    this.skyMat.uniforms.sunCol.value.copy(sunCol);
    const fogCol = mix(a.fog, b.fog);
    (this.scene.fog as THREE.FogExp2).color.copy(fogCol);

    // солнце по дуге с востока на запад, ночью — луна с юго-запада
    const ang = ((hour - 6) / 14) * Math.PI;
    const el = Math.sin(ang);
    const night = 1 - smooth((el + 0.05) / 0.3);
    let dir: THREE.Vector3;
    if (el > -0.02) dir = new THREE.Vector3(Math.cos(ang), Math.max(el, 0.04) * 1.1, -0.35).normalize();
    else dir = new THREE.Vector3(-0.4, 0.75, 0.5).normalize();
    this.day.sunDir.copy(dir);
    this.day.night = night;
    this.skyMat.uniforms.sunDir.value.copy(el > -0.02 ? dir : new THREE.Vector3(0, -1, 0));
    this.skyMat.uniforms.stars.value = night;
    // днём фон — физическое небо, к ночи поверх него проявляется ночной купол со звёздами
    this.skyMat.opacity = smooth((night - 0.15) / 0.6);
    this.sky.visible = this.skyMat.opacity > 0.01;
    const sunPos = new THREE.Vector3(Math.cos(ang), el, -0.35).normalize();
    this.skyPhys.material.uniforms.sunPosition.value.copy(sunPos);
    this.skyPhys.visible = night < 0.98;
    // освещение от неба: пересчёт при заметном сдвиге часов
    if (Math.abs(hour - this.envHour) > 0.2) {
      this.envHour = hour;
      this.envSky.material.uniforms.sunPosition.value.copy(sunPos);
      const rt = this.pmrem.fromScene(this.envScene, 0, 1, 2000);
      this.envRT?.dispose();
      this.envRT = rt;
      this.scene.environment = rt.texture;
    }
    this.scene.environmentIntensity = 0.28 * (1 - night) + 0.03;
    (this.scene.fog as THREE.FogExp2).density = 0.00035 + night * 0.0002;

    this.sun.color.copy(sunCol);
    this.sun.intensity = (a.sunI + (b.sunI - a.sunI) * t) * 0.78;
    this.sun.position.copy(this.center).add(dir.clone().multiplyScalar(this.radius * 3));
    this.sun.target.position.copy(this.center);
    // небо уже светит через окружение, полусфера — только подсветка теней
    this.hemi.intensity = (a.hemiI + (b.hemiI - a.hemiI) * t) * 0.45;
    this.hemi.color.copy(top).lerp(new THREE.Color("#ffffff"), 0.55);
    this.hemi.groundColor.set(night > 0.5 ? "#1a2030" : "#6b6f5c");

    // днём светятся только лампы и фары (яркость выше обычных поверхностей), ночью порог ниже
    this.bloom.strength = 0.32 + night * 0.25;
    this.bloom.threshold = 2.2 - night * 1.4;
    this.bloom.radius = 0.45;
    this.renderer.toneMappingExposure = 0.86 + night * 0.16;
    this.grade.uniforms.warmth.value = (1 - night) * 0.05 + (hour > 16 && hour < 20 ? 0.04 : 0);
  }

  render(dt: number) {
    if (this.fly) {
      this.fly.t += dt;
      const k = smooth(clamp(this.fly.t / this.fly.dur, 0, 1));
      this.camera.position.lerpVectors(this.fly.from, this.fly.to, k);
      this.controls.target.lerpVectors(this.fly.tFrom, this.fly.tTo, k);
      if (k >= 1) this.fly = null;
    }
    this.controls.update();
    this.sky.position.copy(this.camera.position);
    this.skyPhys.position.copy(this.camera.position);
    this.time += dt;
    this.skyPhys.material.uniforms.time.value = this.time;
    this.grade.uniforms.time.value = this.time;
    if (this.miniature) {
      // линия резкости — центр экрана
      this.tiltH.uniforms.r.value = 0.5;
      this.tiltV.uniforms.r.value = 0.5;
    }
    this.composer.render(dt);
  }
}

/** Цветокоррекция после тональной компрессии: контраст, насыщенность, тёплый тон, виньетка, лёгкое зерно. */
const GradeShader = {
  name: "GradeShader",
  uniforms: {
    tDiffuse: { value: null },
    time: { value: 0 },
    warmth: { value: 0.04 },
    contrast: { value: 1.06 },
    saturation: { value: 1.1 },
    vignette: { value: 0.22 },
    grain: { value: 0.018 },
  },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float time; uniform float warmth; uniform float contrast;
    uniform float saturation; uniform float vignette; uniform float grain;
    varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main(){
      vec4 c = texture2D(tDiffuse, vUv);
      vec3 col = c.rgb;
      col = (col - 0.5) * contrast + 0.5;
      float l = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = mix(vec3(l), col, saturation);
      // тёплые света, чуть холодные тени
      col += vec3(warmth, warmth * 0.45, -warmth * 0.6) * smoothstep(0.25, 1.0, l);
      col += vec3(-0.01, 0.0, 0.015) * (1.0 - smoothstep(0.0, 0.35, l));
      vec2 d = vUv - 0.5;
      col *= 1.0 - vignette * smoothstep(0.35, 0.85, length(d * vec2(1.0, 0.85)));
      col += (h(vUv * 1000.0 + time) - 0.5) * grain;
      gl_FragColor = vec4(clamp(col, 0.0, 1.0), c.a);
    }`,
};
