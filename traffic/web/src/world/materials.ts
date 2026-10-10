// Процедурные материалы: текстуры рисуются кодом на холсте, без скачанных файлов.
// Повтор плиток маскируется крупной вариацией цвета в мировых координатах (macroVariation).
import * as THREE from "three";

let seed = 1234567;
function rnd() {
  seed = (seed * 16807) % 2147483647;
  return seed / 2147483647;
}

function canvas(size: number) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  return [c, c.getContext("2d")!] as const;
}

function tex(c: HTMLCanvasElement, srgb = true) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.anisotropy = 8;
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** Мелкий шум поверх уже нарисованного холста. */
function grain(ctx: CanvasRenderingContext2D, size: number, amp: number) {
  const img = ctx.getImageData(0, 0, size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (rnd() - 0.5) * amp;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n;
  }
  ctx.putImageData(img, 0, 0);
}

/** Пятна мягкими кругами: заплатки, разводы, неровный тон. */
function blotches(ctx: CanvasRenderingContext2D, size: number, n: number, rMin: number, rMax: number, color: () => string) {
  for (let i = 0; i < n; i++) {
    const x = rnd() * size;
    const y = rnd() * size;
    const r = rMin + rnd() * (rMax - rMin);
    for (const [dx, dy] of [[0, 0], [size, 0], [-size, 0], [0, size], [0, -size]]) {
      const g = ctx.createRadialGradient(x + dx, y + dy, 0, x + dx, y + dy, r);
      g.addColorStop(0, color());
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(x + dx - r, y + dy - r, r * 2, r * 2);
    }
  }
}

/** Асфальт: зерно щебня, тёмные заплатки, трещины, следы колёс. Плитка 24 × 24 м. */
export function asphaltMaps() {
  const S = 1024;
  const [c, ctx] = canvas(S);
  ctx.fillStyle = "#808080";
  ctx.fillRect(0, 0, S, S);
  blotches(ctx, S, 26, 60, 220, () => (rnd() < 0.5 ? "rgba(40,40,44,0.22)" : "rgba(200,200,205,0.10)"));
  // заплатки ремонта
  for (let i = 0; i < 5; i++) {
    const w = 60 + rnd() * 180;
    const h = 40 + rnd() * 120;
    ctx.fillStyle = `rgba(40,40,44,${0.08 + rnd() * 0.1})`;
    ctx.fillRect(rnd() * S, rnd() * S, w, h);
  }
  // трещины
  ctx.strokeStyle = "rgba(20,20,22,0.55)";
  ctx.lineCap = "round";
  for (let i = 0; i < 14; i++) {
    let x = rnd() * S;
    let y = rnd() * S;
    let a = rnd() * Math.PI * 2;
    ctx.lineWidth = 0.8 + rnd() * 1.4;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let k = 0; k < 18; k++) {
      a += (rnd() - 0.5) * 1.1;
      x += Math.cos(a) * 9;
      y += Math.sin(a) * 9;
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  // щебень: светлые и тёмные точки
  for (let i = 0; i < 26000; i++) {
    const v = rnd() < 0.5 ? 40 + rnd() * 40 : 150 + rnd() * 70;
    ctx.fillStyle = `rgba(${v},${v},${v + 4},${0.35 + rnd() * 0.4})`;
    const s = rnd() < 0.9 ? 1 : 2;
    ctx.fillRect(rnd() * S, rnd() * S, s, s);
  }
  grain(ctx, S, 22);
  const map = tex(c);
  map.repeat.set(0.25, 0.25);
  // шероховатость: заплатки и колея глаже
  const [r, rc] = canvas(256);
  rc.fillStyle = "#e0e0e0";
  rc.fillRect(0, 0, 256, 256);
  blotches(rc, 256, 18, 10, 50, () => "rgba(120,120,120,0.35)");
  grain(rc, 256, 30);
  const rough = tex(r, false);
  rough.repeat.set(0.25, 0.25);
  return { map, rough };
}

/** Тротуарная плитка 40 × 40 см со швами и разбросом тона. Плитка текстуры 6 × 6 м. */
export function paversMap() {
  const S = 1024;
  const [c, ctx] = canvas(S);
  const n = 15;
  const step = S / n;
  ctx.fillStyle = "#6f6b66";
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const v = 196 + (rnd() - 0.5) * 26;
      ctx.fillStyle = `rgb(${v},${v - 4},${v - 10})`;
      ctx.fillRect(i * step + 2, j * step + 2, step - 4, step - 4);
    }
  }
  blotches(ctx, S, 30, 30, 140, () => (rnd() < 0.6 ? "rgba(90,85,78,0.14)" : "rgba(255,255,250,0.10)"));
  grain(ctx, S, 18);
  return tex(c);
}

/** Трава: оттенки зелёного, выгоревшие пятна, мелкие травинки. Плитка 20 × 20 м. */
export function grassMap() {
  const S = 512;
  const [c, ctx] = canvas(S);
  ctx.fillStyle = "#8aa06a";
  ctx.fillRect(0, 0, S, S);
  blotches(ctx, S, 40, 20, 110, () => {
    const k = rnd();
    return k < 0.4 ? "rgba(90,115,65,0.28)" : k < 0.7 ? "rgba(175,170,110,0.2)" : "rgba(120,145,85,0.25)";
  });
  for (let i = 0; i < 30000; i++) {
    const g = 90 + rnd() * 90;
    ctx.fillStyle = `rgba(${g * 0.6},${g},${g * 0.4},0.45)`;
    ctx.fillRect(rnd() * S, rnd() * S, 1, 1 + (rnd() < 0.3 ? 1 : 0));
  }
  grain(ctx, S, 16);
  return tex(c);
}

/** Краска разметки: белая со стёртыми местами. */
export function paintMap() {
  const S = 256;
  const [c, ctx] = canvas(S);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, S, S);
  blotches(ctx, S, 40, 4, 22, () => "rgba(120,120,120,0.45)");
  grain(ctx, S, 26);
  return tex(c);
}

/**
 * Крупная вариация тона в мировых координатах поверх текстуры:
 * убирает видимый повтор плиток (асфальт, трава, тротуар).
 */
export function macroVariation(mat: THREE.MeshStandardMaterial, scale: number, amount: number) {
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vMacroPos;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvMacroPos = (modelMatrix * vec4(transformed, 1.0)).xyz;");
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", `#include <common>
        varying vec3 vMacroPos;
        float mh(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
        float mnoise(vec2 p){ vec2 i = floor(p); vec2 f = fract(p); f = f*f*(3.0-2.0*f);
          return mix(mix(mh(i), mh(i+vec2(1,0)), f.x), mix(mh(i+vec2(0,1)), mh(i+vec2(1,1)), f.x), f.y); }`)
      .replace("#include <map_fragment>", `#include <map_fragment>
        float mv = mnoise(vMacroPos.xz / ${scale.toFixed(1)}) * 0.65 + mnoise(vMacroPos.xz / ${(scale * 0.31).toFixed(1)}) * 0.35;
        diffuseColor.rgb *= 1.0 + (mv - 0.5) * ${(amount * 2).toFixed(3)};`);
  };
  mat.customProgramCacheKey = () => `macro-${scale}-${amount}`;
  return mat;
}
