/* ---------- мир вокруг кофейни: земля, дома, улица, камера ---------- */
/* Использует iso, face, box, seg, shade, figureSvg, looksOf, liveMinutes из app.js; подключается после него. */

const G = -15; // земля лежит на уровне низа плиты зала
const GRASS = "#cfe0a6";
const PAVE = "#e3dcc8";
const KERB = "#c7ba98";
const ROAD = "#a7aaa1";
const ROAD_X0 = 11.5;
const ROAD_X1 = 15.5;

const HOUSES = [
  // слева за стеной
  { x: -13, y: 0, w: 6.5, d: 5, h: 46, wall: "#f1e2c6", roof: "#c9553d", ridge: "y" },
  { x: -13, y: 6.5, w: 6.5, d: 4.2, h: 34, wall: "#e7d3b0", roof: "#6f8f93", ridge: "x" },
  { x: -13, y: -7, w: 6.5, d: 4.5, h: 52, wall: "#efe0c4", roof: "#8a8a4a", ridge: "x", chimney: true },
  // сзади
  { x: -2, y: -12, w: 5, d: 5.5, h: 50, wall: "#f0dcc0", roof: "#8a8a4a", ridge: "x", chimney: true },
  { x: 4.5, y: -11, w: 5.5, d: 4.5, h: 38, wall: "#ead6b6", roof: "#c9553d", ridge: "y" },
  { x: -10, y: -13.5, w: 5, d: 5, h: 44, wall: "#e9d7bb", roof: "#6f8f93", ridge: "y" },
  // справа за поперечной улицей
  { x: 18, y: -12, w: 5.5, d: 5, h: 40, wall: "#f0e0c2", roof: "#c9553d", ridge: "x" },
  { x: 18.5, y: -5, w: 5.5, d: 5, h: 46, wall: "#e8d4b2", roof: "#6f8f93", ridge: "y", chimney: true },
  { x: 18.5, y: 2, w: 5.5, d: 4.5, h: 36, wall: "#f1e2c6", roof: "#8a8a4a", ridge: "x" },
  { x: 18.5, y: 8, w: 5, d: 3.2, h: 42, wall: "#ecdab8", roof: "#c9553d", ridge: "y" },
  // через главную улицу спереди
  { x: 18.5, y: 18.5, w: 6, d: 5, h: 48, wall: "#ead8b6", roof: "#6f8f93", ridge: "y" },
  { x: 18.5, y: 25.5, w: 5.5, d: 4.5, h: 38, wall: "#f0dfc0", roof: "#c9553d", ridge: "x" },
];

const PROPS_FIXED = [
  { kind: "tree", x: -2.1, y: 3.2, s: 1.0 },
  { kind: "tree", x: -2.1, y: 8.4, s: 0.9 },
  { kind: "tree", x: 10.3, y: 2.6, s: 1.05 },
  { kind: "tree", x: 10.3, y: 7.6, s: 0.95 },
  { kind: "lamp", x: 10.9, y: -1.5 },
  { kind: "lamp", x: 10.9, y: 5 },
  { kind: "lamp", x: 10.9, y: 10.9 },
  { kind: "lamp", x: -2.6, y: 10.9 },
  { kind: "lamp", x: 16.6, y: 16.6 },
  { kind: "bench", x: 2.6, y: 10, axis: "x" },
  { kind: "bench", x: 6.6, y: 10, axis: "x" },
  { kind: "bush", x: 9.7, y: 9.7 },
  { kind: "bush", x: -1.6, y: 9.9 },
];

function rng(seed) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gface(x0, y0, x1, y1, fill, alpha, dz = 0) {
  const z = G + dz;
  return face([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], fill, alpha);
}

function onGrass(x, y, margin = 0) {
  if (x > -3.5 - margin && x < ROAD_X1 + 2.5 && y > -3.5 - margin && y < 11.6 + margin) return false;
  if (y > ROAD_X0 - 0.5 - margin && y < 17.7 + margin) return false;
  if (x > ROAD_X0 - 0.5 - margin && x < 17.7 + margin) return false;
  if (x > -9.8 - margin && x < 6.2 + margin && y > 17.0 - margin && y < 32.5 + margin) return false;
  if (x > 7.6 - margin && x < 11.2 + margin && y > 17.5 - margin && y < 32.0 + margin) return false;
  if (x > -5.2 - margin && x < -2.8 + margin) return false;
  if (y > -5.2 - margin && y < -2.8 + margin) return false;
  return !HOUSES.some((h) => x > h.x - 1.8 - margin && x < h.x + h.w + 1.8 + margin && y > h.y - 1.8 - margin && y < h.y + h.d + 1.8 + margin);
}

function worldProps() {
  const props = [...PROPS_FIXED];
  const rand = rng(7);
  for (let i = 0; i < 90 && props.length < PROPS_FIXED.length + 44; i += 1) {
    const x = -26 + rand() * 58;
    const y = -26 + rand() * 62;
    const kind = rand() < 0.78 ? "tree" : rand() < 0.5 ? "bush" : "rock";
    if (onGrass(x, y, 0.8)) props.push({ kind, x, y, s: 0.8 + rand() * 0.55 });
  }
  return props;
}

/* ---------- земля ---------- */

function landSvg() {
  const out = [`<rect x="-6000" y="-4000" width="12000" height="9000" fill="${GRASS}"/>`];
  const rand = rng(21);
  for (let i = 0; i < 120; i += 1) {
    const x = -30 + rand() * 66;
    const y = -30 + rand() * 70;
    const [sx, sy] = iso(x, y, G);
    const tone = rand() < 0.5 ? "#bfd593" : "#d9e8b4";
    out.push(`<ellipse cx="${sx.toFixed(0)}" cy="${sy.toFixed(0)}" rx="${(30 + rand() * 90).toFixed(0)}" ry="${(12 + rand() * 30).toFixed(0)}" fill="${tone}" fill-opacity="0.55"/>`);
  }
  // тротуары
  out.push(gface(-3.5, -3.5, ROAD_X1 + 2.5, 11.6, PAVE));
  out.push(gface(-30, 15.5, 38, 17.7, PAVE));
  out.push(gface(15.5, -30, 17.7, 38, PAVE));
  out.push(gface(-5.2, -30, -2.8, 11.6, PAVE));
  out.push(gface(-30, -5.2, ROAD_X0, -2.8, PAVE));
  // участок NeuralDeep: тротуар вокруг зала и дорожка слева от его стены
  out.push(gface(-9.2, 17.7, 5.5, 31.5, PAVE));
  // парковка на пять мест слева от поперечной улицы, к югу от главной
  out.push(gface(8.0, 17.7, 11.2, 31.6, shade(ROAD, 0.05)));
  [0, 1, 2, 3, 4, 5].forEach((i) => {
    const y = 18.8 + i * 2.4;
    out.push(seg([8.5, y, G + 0.5], [10.0, y, G + 0.5], "#f4f1e8", 1.4));
  });
  // дороги
  out.push(gface(-30, ROAD_X0, 38, ROAD_X1, ROAD));
  out.push(gface(ROAD_X0, -30, ROAD_X1, 38, ROAD));
  out.push(gface(ROAD_X0, ROAD_X0, ROAD_X1, ROAD_X1, shade(ROAD, 0.03)));
  // бордюры
  [ROAD_X0, ROAD_X1].forEach((v) => {
    out.push(seg([-30, v, G + 0.4], [38, v, G + 0.4], KERB, 1.6));
    out.push(seg([v, -30, G + 0.4], [v, 38, G + 0.4], KERB, 1.6));
  });
  // разметка
  const mid = (ROAD_X0 + ROAD_X1) / 2;
  for (let v = -30; v < 38; v += 2.4) {
    if (v > ROAD_X0 - 1 && v < ROAD_X1 + 1) continue;
    out.push(seg([v, mid, G + 0.5], [v + 1.2, mid, G + 0.5], "#f4f1e8", 1.6));
    out.push(seg([mid, v, G + 0.5], [mid, v + 1.2, G + 0.5], "#f4f1e8", 1.6));
  }
  // Стрелки направления на правых полосах.
  [5, 23].forEach((u) => {
    ["x", "y"].forEach((axis) => [-1, 1].forEach((dir) => {
      const v = axis === "x" ? (dir > 0 ? 14.4 : 12.6) : (dir > 0 ? 12.6 : 14.4);
      const P = (a, b) => axis === "x" ? [u + a * dir, v + b, G + 0.5] : [v + b, u + a * dir, G + 0.5];
      out.push(face([P(-0.8, -0.08), P(0.25, -0.08), P(0.25, -0.25), P(0.85, 0), P(0.25, 0.25), P(0.25, 0.08), P(-0.8, 0.08)], "#f4f1e8", 0.85));
    }));
  });
  // Переходы — перед перекрёстком, стоп-линии раньше них по ходу движения.
  [ROAD_X0 - 1.4, ROAD_X1 + 0.7].forEach((u) => {
    for (let i = 0; i < 7; i += 1) {
      const v = ROAD_X0 + 0.12 + i * 0.55;
      out.push(gface(u, v, u + 0.7, v + 0.32, "#faf5e5", 0.9, 0.4));
      out.push(gface(v, u, v + 0.32, u + 0.7, "#faf5e5", 0.9, 0.4));
    }
  });
  const midLane = (ROAD_X0 + ROAD_X1) / 2;
  out.push(seg([ROAD_X0 - 2.4, midLane, G + 0.5], [ROAD_X0 - 2.4, ROAD_X1 - 0.15, G + 0.5], "#faf5e5", 2.5));
  out.push(seg([ROAD_X1 + 2.4, ROAD_X0 + 0.15, G + 0.5], [ROAD_X1 + 2.4, midLane, G + 0.5], "#faf5e5", 2.5));
  out.push(seg([ROAD_X0 + 0.15, ROAD_X0 - 2.4, G + 0.5], [midLane, ROAD_X0 - 2.4, G + 0.5], "#faf5e5", 2.5));
  out.push(seg([midLane, ROAD_X1 + 2.4, G + 0.5], [ROAD_X1 - 0.15, ROAD_X1 + 2.4, G + 0.5], "#faf5e5", 2.5));
  // песчаные тропинки от тротуара к соседним домам
  out.push(gface(-6.5, 3.2, -3.5, 4.6, "#e3d3ad", 0.9, 0.2));
  out.push(gface(-6.5, 9, -3.5, 10.2, "#e3d3ad", 0.9, 0.2));
  out.push(gface(0.6, -6.5, 1.8, -3.5, "#e3d3ad", 0.9, 0.2));
  out.push(gface(6.2, -6.5, 7.4, -3.5, "#e3d3ad", 0.9, 0.2));
  return out.join("");
}

/* ---------- дома, деревья, фонари ---------- */

/* Свет падает с севера (из окна кофейни): тени идут к югу, чуть к востоку. */
const SUN = [0.3, 1];

function hull(points) {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const build = (list) => {
    const out = [];
    list.forEach((p) => {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop();
      out.push(p);
    });
    out.pop();
    return out;
  };
  return [...build(pts), ...build([...pts].reverse())];
}

/* Тень предмета высотой height (пикселей): основание, протянутое по направлению света. */
function castShadow(foot, height, z, alpha = 0.17) {
  const len = height / 42;
  const moved = foot.map(([x, y]) => [x + SUN[0] * len, y + SUN[1] * len]);
  return face(hull([...foot, ...moved]).map(([x, y]) => [x, y, z]), "#3f5a28", alpha);
}

function houseShadow(h) {
  const foot = [[h.x, h.y], [h.x + h.w, h.y], [h.x + h.w, h.y + h.d], [h.x, h.y + h.d]];
  return castShadow(foot, h.h + Math.min(h.w, h.d) * 5, G + 0.15);
}

function glow(points) {
  return `<polygon points="${points.map(pt).join(" ")}" fill="#ffd98a" style="opacity:calc(var(--night, 0) * 0.95)"/>`;
}

function smokeSvg(x, y, z) {
  const [sx, sy] = iso(x, y, z);
  return `<g transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)})">${[0, 1.3, 2.6].map((d) => `<circle class="puff" r="3.2" fill="#f4f1ea" style="animation-delay:-${d}s"/>`).join("")}</g>`;
}

function houseSvg(o) {
  const { x, y, w, d, h, wall, roof, ridge } = o;
  const z0 = G;
  const zh = z0 + h;
  const south = wall;
  const east = shade(wall, 0.14);
  const e = 0.28;
  const r = Math.min(w, d) * 9 + 6;
  const parts = [box(x, y, w, d, h, roof, south, east, z0)];
  // окна и дверь на южной и восточной стенах
  const glass = "#a9d6e6";
  const frame = "#fff7e6";
  const nx = Math.max(1, Math.floor(w / 1.7));
  for (let i = 0; i < nx; i += 1) {
    const cx = x + ((i + 0.5) * w) / nx;
    parts.push(face([[cx - 0.36, y + d + 0.02, z0 + h * 0.52], [cx + 0.36, y + d + 0.02, z0 + h * 0.52], [cx + 0.36, y + d + 0.02, z0 + h * 0.86], [cx - 0.36, y + d + 0.02, z0 + h * 0.86]], frame));
    parts.push(face([[cx - 0.28, y + d + 0.03, z0 + h * 0.56], [cx + 0.28, y + d + 0.03, z0 + h * 0.56], [cx + 0.28, y + d + 0.03, z0 + h * 0.82], [cx - 0.28, y + d + 0.03, z0 + h * 0.82]], glass));
    parts.push(glow([[cx - 0.28, y + d + 0.04, z0 + h * 0.56], [cx + 0.28, y + d + 0.04, z0 + h * 0.56], [cx + 0.28, y + d + 0.04, z0 + h * 0.82], [cx - 0.28, y + d + 0.04, z0 + h * 0.82]]));
  }
  const dx = x + w * 0.5;
  parts.push(face([[dx - 0.4, y + d + 0.03, z0], [dx + 0.4, y + d + 0.03, z0], [dx + 0.4, y + d + 0.03, z0 + h * 0.42], [dx - 0.4, y + d + 0.03, z0 + h * 0.42]], "#8a5a33"));
  const ny = Math.max(1, Math.floor(d / 1.7));
  for (let i = 0; i < ny; i += 1) {
    const cy = y + ((i + 0.5) * d) / ny;
    parts.push(face([[x + w + 0.02, cy - 0.34, z0 + h * 0.52], [x + w + 0.02, cy + 0.34, z0 + h * 0.52], [x + w + 0.02, cy + 0.34, z0 + h * 0.86], [x + w + 0.02, cy - 0.34, z0 + h * 0.86]], shade(frame, 0.12)));
    parts.push(face([[x + w + 0.03, cy - 0.26, z0 + h * 0.56], [x + w + 0.03, cy + 0.26, z0 + h * 0.56], [x + w + 0.03, cy + 0.26, z0 + h * 0.82], [x + w + 0.03, cy - 0.26, z0 + h * 0.82]], shade(glass, 0.14)));
    parts.push(glow([[x + w + 0.04, cy - 0.26, z0 + h * 0.56], [x + w + 0.04, cy + 0.26, z0 + h * 0.56], [x + w + 0.04, cy + 0.26, z0 + h * 0.82], [x + w + 0.04, cy - 0.26, z0 + h * 0.82]]));
  }
  if (ridge === "x") {
    const ym = y + d / 2;
    parts.push(face([[x + w, y, zh], [x + w, y + d, zh], [x + w, ym, zh + r]], east));
    parts.push(face([[x - e, y + d + e, zh], [x + w + e, y + d + e, zh], [x + w + e, ym, zh + r], [x - e, ym, zh + r]], roof));
    parts.push(seg([x - e, ym, zh + r], [x + w + e, ym, zh + r], shade(roof, 0.25), 1.2));
    if (o.chimney) {
      parts.push(box(x + w * 0.7, ym + 0.1, 0.5, 0.5, 14, "#b9694a", "#a15538", "#7f4129", zh + r * 0.45));
      parts.push(smokeSvg(x + w * 0.7 + 0.25, ym + 0.35, zh + r * 0.45 + 14));
    }
  } else {
    const xm = x + w / 2;
    parts.push(face([[x, y + d, zh], [x + w, y + d, zh], [xm, y + d, zh + r]], south));
    parts.push(face([[x + w + e, y - e, zh], [x + w + e, y + d + e, zh], [xm, y + d + e, zh + r], [xm, y - e, zh + r]], shade(roof, 0.16)));
    parts.push(seg([xm, y - e, zh + r], [xm, y + d + e, zh + r], shade(roof, 0.3), 1.2));
    if (o.chimney) {
      parts.push(box(xm + 0.1, y + d * 0.3, 0.5, 0.5, 14, "#b9694a", "#a15538", "#7f4129", zh + r * 0.45));
      parts.push(smokeSvg(xm + 0.35, y + d * 0.3 + 0.25, zh + r * 0.45 + 14));
    }
  }
  return parts.join("");
}

function treeSvg(s = 1, delay = 0) {
  return `<ellipse cx="${(-13 * s).toFixed(1)}" cy="${(6 * s).toFixed(1)}" rx="${(22 * s).toFixed(1)}" ry="${(7 * s).toFixed(1)}" fill="#3f5a28" fill-opacity="0.2"/>
    <rect x="${(-2.2 * s).toFixed(1)}" y="${(-16 * s).toFixed(1)}" width="${(4.4 * s).toFixed(1)}" height="${(17 * s).toFixed(1)}" rx="1.4" fill="#8a5a33"/>
    <g class="sway" style="animation-delay:-${delay.toFixed(1)}s"><ellipse cx="0" cy="${(-30 * s).toFixed(1)}" rx="${(17 * s).toFixed(1)}" ry="${(19 * s).toFixed(1)}" fill="#4f9a55"/>
    <ellipse cx="${(-5 * s).toFixed(1)}" cy="${(-35 * s).toFixed(1)}" rx="${(11 * s).toFixed(1)}" ry="${(12 * s).toFixed(1)}" fill="#68b567"/>
    <ellipse cx="${(7 * s).toFixed(1)}" cy="${(-24 * s).toFixed(1)}" rx="${(8 * s).toFixed(1)}" ry="${(9 * s).toFixed(1)}" fill="#3f8647" fill-opacity="0.85"/></g>`;
}

function bushSvg(s = 1) {
  return `<ellipse cx="2" cy="2" rx="${(13 * s).toFixed(1)}" ry="${(4.5 * s).toFixed(1)}" fill="#3f5a28" fill-opacity="0.18"/>
    <ellipse cx="0" cy="${(-7 * s).toFixed(1)}" rx="${(12 * s).toFixed(1)}" ry="${(9 * s).toFixed(1)}" fill="#59a860"/>
    <ellipse cx="${(-3 * s).toFixed(1)}" cy="${(-10 * s).toFixed(1)}" rx="${(7 * s).toFixed(1)}" ry="${(5.5 * s).toFixed(1)}" fill="#78c27a"/>`;
}

function rockSvg(s = 1) {
  return `<ellipse cx="1" cy="2" rx="${(12 * s).toFixed(1)}" ry="${(4 * s).toFixed(1)}" fill="#3f5a28" fill-opacity="0.18"/>
    <path d="M ${-10 * s} 0 Q ${-9 * s} ${-9 * s} ${-2 * s} ${-10 * s} Q ${8 * s} ${-10 * s} ${11 * s} 0 Z" fill="#b3b5ad"/>
    <path d="M ${-2 * s} ${-10 * s} Q ${8 * s} ${-10 * s} ${11 * s} 0 L ${3 * s} 0 Z" fill="#9a9c94"/>`;
}

function lampSvg() {
  return `<ellipse cx="2" cy="1.5" rx="7" ry="2.4" fill="#3f5a28" fill-opacity="0.2"/>
    <rect x="-1.3" y="-46" width="2.6" height="47" rx="1" fill="#4b5560"/>
    <rect x="-4.5" y="-52" width="9" height="7" rx="2" fill="#4b5560"/>
    <ellipse cx="0" cy="1" rx="26" ry="9" fill="#ffe9a0" style="opacity:calc(var(--night, 0) * 0.35)"/>
    <ellipse cx="0" cy="-47" rx="14" ry="12" fill="#ffe9a0" style="opacity:calc(var(--night, 0) * 0.4)"/>
    <rect x="-3.3" y="-50.8" width="6.6" height="4.6" rx="1.4" fill="#fff0b8" style="filter:brightness(calc(0.85 + var(--night, 0) * 0.3))"/>`;
}

function benchSvg(axis) {
  const long = axis === "x";
  const w = long ? 1.7 : 0.55;
  const d = long ? 0.55 : 1.7;
  return box(-w / 2, -d / 2, w, d, 6, "#b3733f", "#8a5a33", "#6b4426", 0)
    + box(-w / 2, -d / 2, long ? w : 0.15, long ? 0.15 : d, 10, "#c98a4b", "#a96d36", "#8a5629", 6);
}

function propDepth(p) {
  return p.kind === "house" ? p.x + p.w + p.y + p.d : p.x + p.y;
}

/* ---------- улица: прохожие, машины ---------- */

const PED_PATHS = [
  { a: [-2.8, 10.3], b: [11, 10.3], n: 3 },
  { a: [10.4, -2.8], b: [10.4, 11], n: 2 },
  { a: [-4, -3], b: [-4, 11], n: 1 },
  { a: [-26, 16.6], b: [9.4, 16.6], n: 3 },
  { a: [18, 16.6], b: [34, 16.6], n: 2 },
  { a: [16.6, -26], b: [16.6, 9.4], n: 2 },
  { a: [16.6, 18], b: [16.6, 34], n: 2 },
  { a: [-4, -4], b: [11, -4], n: 1 },
];
const CAR_COLORS = ["#d9604c", "#3d8fd4", "#e3b13c", "#f1ede2", "#5aa56f", "#7b5ea7", "#4c5560", "#e08a3c"];
const CAR_KINDS = {
  sedan: { L: 2.8, W: 1.2, roof: 27, rear: -0.78, front: 0.55 },
  hatch: { L: 2.45, W: 1.2, roof: 29, rear: -1.02, front: 0.52 },
  van: { L: 3.2, W: 1.3, roof: 36, rear: -1.3, front: 0.65 },
};

/* Кузов с фасками, наклонными стёклами и колёсными арками. u — вперёд по ходу. */
function carSvg(color, axis, dir, kindName, taxi) {
  const k = CAR_KINDS[kindName], half = k.L / 2, hw = k.W / 2;
  const P = (u, v, z) => axis === "x" ? [u * dir, v, z] : [v, u * dir, z];
  const surfaces = [];
  const panel = (points, fill) => surfaces.push({ points: points.map((p) => P(...p)), fill });
  const chamfer = (z, inset = 0) => [
    [-half + 0.18, -hw + inset, z], [half - 0.23, -hw + inset, z],
    [half, -hw + 0.2 + inset, z], [half, hw - 0.2 - inset, z],
    [half - 0.23, hw - inset, z], [-half + 0.18, hw - inset, z],
    [-half, hw - 0.17 - inset, z], [-half, -hw + 0.17 + inset, z],
  ];
  const lower = chamfer(6), belt = chamfer(15);
  const foot = lower.map((p) => P(p[0], p[1], 0).slice(0, 2));
  const parts = [castShadow(foot, k.roof, 0.2, 0.2)];
  for (let i = 0; i < 8; i += 1) {
    const j = (i + 1) % 8;
    const points = [lower[i], lower[j], belt[j], belt[i]];
    const transformed = points.map((p) => P(...p));
    const cross = (transformed[1][0] - transformed[0][0]) - (transformed[1][1] - transformed[0][1]);
    panel(points, shade(color, cross > 0 ? 0.13 : 0.26));
  }
  panel(belt, lighten(color, 0.12));
  const v0 = -hw + 0.06, v1 = hw - 0.06, roofV = hw - 0.2;
  const rearTop = k.rear + (kindName === "van" ? 0.04 : 0.2);
  const frontTop = k.front - (kindName === "van" ? 0.32 : 0.42);
  const bottom = [[k.rear, v0, 15], [k.front, v0, 15], [k.front, v1, 15], [k.rear, v1, 15]];
  const top = [[rearTop, -roofV, k.roof], [frontTop, -roofV, k.roof], [frontTop, roofV, k.roof], [rearTop, roofV, k.roof]];
  const glass = "#527383";
  for (let i = 0; i < 4; i += 1) panel([bottom[i], bottom[(i + 1) % 4], top[(i + 1) % 4], top[i]], i === 1 ? "#79a0af" : glass);
  panel(top, lighten(color, 0.2));
  // Стойки и разделитель дверей на обеих сторонах кабины.
  [-1, 1].forEach((side) => {
    const u = (k.rear + k.front) / 2;
    panel([[u - 0.04, side * (hw - 0.045), 15], [u + 0.04, side * (hw - 0.045), 15], [u + 0.04, side * roofV, k.roof], [u - 0.04, side * roofV, k.roof]], shade(color, 0.05));
    panel([[k.rear, side * (hw - 0.04), 14], [k.front, side * (hw - 0.04), 14], [k.front, side * (hw - 0.04), 16], [k.rear, side * (hw - 0.04), 16]], color);
    panel([[u - 0.08, side * (hw + 0.01), 11.5], [u + 0.08, side * (hw + 0.01), 11.5], [u + 0.08, side * (hw + 0.01), 12.5], [u - 0.08, side * (hw + 0.01), 12.5]], "#d4dadd");
  });
  [-1, 1].forEach((end) => {
    const u = end * (half + 0.01);
    panel([[u, -hw + 0.15, 6], [u, hw - 0.15, 6], [u, hw - 0.15, 8], [u, -hw + 0.15, 8]], "#333c42");
    [-1, 1].forEach((side) => {
      const v = side * (hw - 0.28);
      panel([[u, v - 0.15, 10], [u, v + 0.15, 10], [u, v + 0.15, 13.5], [u, v - 0.15, 13.5]], end > 0 ? "#fff3cb" : "#9d302e");
    });
  });
  if (taxi) {
    panel([[-0.25, -0.2, k.roof + 0.3], [0.25, -0.2, k.roof + 0.3], [0.25, 0.2, k.roof + 0.3], [-0.25, 0.2, k.roof + 0.3]], "#ffc847");
    panel([[-0.25, 0.2, k.roof], [0.25, 0.2, k.roof], [0.25, 0.2, k.roof + 4], [-0.25, 0.2, k.roof + 4]], "#ffc847");
  }
  surfaces.sort((a, b) => {
    const depth = (p) => p.reduce((sum, q) => sum + q[0] + q[1], 0) / p.length;
    return depth(a.points) - depth(b.points);
  }).forEach((p) => parts.push(face(p.points, p.fill)));
  // Ближний борт одинаково виден у обеих осей; направление меняет только нос.
  [-half + 0.5, half - 0.5].forEach((u) => {
    const wheel = (r, rz, fill, v) => {
      const pts = Array.from({ length: 16 }, (_, i) => { const a = i / 16 * Math.PI * 2; return P(u + Math.cos(a) * r, v, 5 + Math.sin(a) * rz); });
      parts.push(face(pts, fill));
    };
    wheel(0.32, 6, "#1e252a", hw + 0.02);
    wheel(0.17, 3.2, "#c0c9cf", hw + 0.03);
    wheel(0.06, 1.1, "#65747c", hw + 0.04);
  });
  return `<g transform="translate(0 ${-G})">${parts.join("")}</g>`;
}

function carBrakeSvg(car) {
  const k = CAR_KINDS[car.kind], hw = k.W / 2;
  const P = (u, v, z) => car.axis === "x" ? [u * car.dir, v, z] : [v, u * car.dir, z];
  return `<g transform="translate(0 ${-G})">${[-1, 1].map((side) => {
    const u = -k.L / 2 - 0.035, v = side * (hw - 0.28);
    return face([P(u, v - 0.16, 10), P(u, v + 0.16, 10), P(u, v + 0.16, 13.5), P(u, v - 0.16, 13.5)], "#ff5443");
  }).join("")}</g>`;
}

const CARS = [
  // Правостороннее движение, по три машины на полосу. Сдвиги — начальные позиции.
  ...[0, 20, 43].map((off, i) => ({ axis: "x", fixed: 14.4, dir: 1, off, color: i, kind: i === 2 ? "van" : "sedan", taxi: i === 1 })),
  ...[6, 29, 52].map((off, i) => ({ axis: "x", fixed: 12.6, dir: -1, off, color: i + 3, kind: i === 0 ? "hatch" : "sedan" })),
  ...[3, 25, 48].map((off, i) => ({ axis: "y", fixed: 12.6, dir: 1, off, color: i + 4, kind: i === 1 ? "van" : "hatch" })),
  ...[10, 33, 56].map((off, i) => ({ axis: "y", fixed: 14.4, dir: -1, off, color: i + 1, kind: i === 2 ? "hatch" : "sedan" })),
];

let outer = null; // { statics: [{el, d}], ambient: [{el, kind, ...}], key }
const layers = { names: true, life: true };

function pedDensity(mins) {
  const peak = (m, c, s) => Math.exp(-(((m - c) / s) ** 2));
  const awake = Math.min(1, Math.max(0, (mins - 300) / 120), Math.max(0, (1440 - mins) / 120));
  return Math.min(1, 0.08 + awake * (0.27 + 0.65 * Math.max(peak(mins, 540, 70), peak(mins, 780, 90) * 0.8, peak(mins, 1050, 80))));
}

/* Порядок рисования предметов-коробок в изометрии: если коробки разделены по одной из осей, дальняя рисуется раньше;
   по центру глубины сортировать нельзя, длинные машины на соседних полосах перекрывали бы друг друга неверно. */
function isoSort(rows) {
  const n = rows.length;
  const after = Array.from({ length: n }, () => []);
  const indeg = new Array(n).fill(0);
  const sep = (a0, a1, b0, b1) => (a1 <= b0 ? -1 : b1 <= a0 ? 1 : 0);
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const a = rows[i];
      const b = rows[j];
      const sx = sep(a.box[0], a.box[1], b.box[0], b.box[1]);
      const sy = sep(a.box[2], a.box[3], b.box[2], b.box[3]);
      let first;
      if ((sx && sy && sx !== sy) || (!sx && !sy)) first = a.d <= b.d ? -1 : 1;
      else first = sx || sy;
      if (first < 0) { after[i].push(j); indeg[j] += 1; } else { after[j].push(i); indeg[i] += 1; }
    }
  }
  const done = new Array(n).fill(false);
  const out = [];
  for (let step = 0; step < n; step += 1) {
    let pick = -1;
    for (let i = 0; i < n; i += 1) {
      if (!done[i] && indeg[i] === 0 && (pick < 0 || rows[i].d < rows[pick].d)) pick = i;
    }
    if (pick < 0) {
      for (let i = 0; i < n; i += 1) {
        if (!done[i] && (pick < 0 || rows[i].d < rows[pick].d)) pick = i;
      }
    }
    done[pick] = true;
    out.push(rows[pick]);
    after[pick].forEach((k) => { indeg[k] -= 1; });
  }
  rows.splice(0, n, ...out);
}
