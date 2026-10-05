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
  { x: -12, y: 18.5, w: 6, d: 5, h: 40, wall: "#efdfc2", roof: "#6f8f93", ridge: "x" },
  { x: -4, y: 18.5, w: 6, d: 5, h: 56, wall: "#e9d4b0", roof: "#c9553d", ridge: "y", chimney: true },
  { x: 3, y: 18.5, w: 5, d: 4.5, h: 36, wall: "#f2e4c8", roof: "#8a8a4a", ridge: "x" },
  { x: 18.5, y: 18.5, w: 6, d: 5, h: 48, wall: "#ead8b6", roof: "#6f8f93", ridge: "y" },
  { x: 18.5, y: 25.5, w: 5.5, d: 4.5, h: 38, wall: "#f0dfc0", roof: "#c9553d", ridge: "x" },
  { x: -4, y: 25.5, w: 6, d: 4.5, h: 44, wall: "#e8d5b4", roof: "#8a8a4a", ridge: "y" },
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
  // зебры
  for (let i = 0; i < 7; i += 1) {
    out.push(gface(5 + i * 0.7, ROAD_X0 + 0.15, 5.4 + i * 0.7, ROAD_X1 - 0.15, "#f4f1e8", 0.85, 0.4));
    out.push(gface(ROAD_X0 + 0.15, 4 + i * 0.7, ROAD_X1 - 0.15, 4.4 + i * 0.7, "#f4f1e8", 0.85, 0.4));
  }
  // песчаные тропинки от тротуара к соседним домам
  out.push(gface(-6.5, 3.2, -3.5, 4.6, "#e3d3ad", 0.9, 0.2));
  out.push(gface(-6.5, 9, -3.5, 10.2, "#e3d3ad", 0.9, 0.2));
  out.push(gface(0.6, -6.5, 1.8, -3.5, "#e3d3ad", 0.9, 0.2));
  out.push(gface(6.2, -6.5, 7.4, -3.5, "#e3d3ad", 0.9, 0.2));
  return out.join("");
}

/* ---------- дома, деревья, фонари ---------- */

function shadowFlat(x, y, w, d, k = 1.1) {
  return face([[x + k, y + k, G + 0.15], [x + w + k, y + k, G + 0.15], [x + w + k, y + d + k, G + 0.15], [x + k, y + d + k, G + 0.15]], "#3f5a28", 0.14);
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
  }
  const dx = x + w * 0.5;
  parts.push(face([[dx - 0.4, y + d + 0.03, z0], [dx + 0.4, y + d + 0.03, z0], [dx + 0.4, y + d + 0.03, z0 + h * 0.42], [dx - 0.4, y + d + 0.03, z0 + h * 0.42]], "#8a5a33"));
  const ny = Math.max(1, Math.floor(d / 1.7));
  for (let i = 0; i < ny; i += 1) {
    const cy = y + ((i + 0.5) * d) / ny;
    parts.push(face([[x + w + 0.02, cy - 0.34, z0 + h * 0.52], [x + w + 0.02, cy + 0.34, z0 + h * 0.52], [x + w + 0.02, cy + 0.34, z0 + h * 0.86], [x + w + 0.02, cy - 0.34, z0 + h * 0.86]], shade(frame, 0.12)));
    parts.push(face([[x + w + 0.03, cy - 0.26, z0 + h * 0.56], [x + w + 0.03, cy + 0.26, z0 + h * 0.56], [x + w + 0.03, cy + 0.26, z0 + h * 0.82], [x + w + 0.03, cy - 0.26, z0 + h * 0.82]], shade(glass, 0.14)));
  }
  if (ridge === "x") {
    const ym = y + d / 2;
    parts.push(face([[x + w, y, zh], [x + w, y + d, zh], [x + w, ym, zh + r]], east));
    parts.push(face([[x - e, y + d + e, zh], [x + w + e, y + d + e, zh], [x + w + e, ym, zh + r], [x - e, ym, zh + r]], roof));
    parts.push(seg([x - e, ym, zh + r], [x + w + e, ym, zh + r], shade(roof, 0.25), 1.2));
    if (o.chimney) parts.push(box(x + w * 0.7, ym + 0.1, 0.5, 0.5, 14, "#b9694a", "#a15538", "#7f4129", zh + r * 0.45));
  } else {
    const xm = x + w / 2;
    parts.push(face([[x, y + d, zh], [x + w, y + d, zh], [xm, y + d, zh + r]], south));
    parts.push(face([[x + w + e, y - e, zh], [x + w + e, y + d + e, zh], [xm, y + d + e, zh + r], [xm, y - e, zh + r]], shade(roof, 0.16)));
    parts.push(seg([xm, y - e, zh + r], [xm, y + d + e, zh + r], shade(roof, 0.3), 1.2));
    if (o.chimney) parts.push(box(xm + 0.1, y + d * 0.3, 0.5, 0.5, 14, "#b9694a", "#a15538", "#7f4129", zh + r * 0.45));
  }
  return parts.join("");
}

function treeSvg(s = 1) {
  return `<ellipse cx="3" cy="2" rx="${(20 * s).toFixed(1)}" ry="${(7 * s).toFixed(1)}" fill="#3f5a28" fill-opacity="0.2"/>
    <rect x="${(-2.2 * s).toFixed(1)}" y="${(-16 * s).toFixed(1)}" width="${(4.4 * s).toFixed(1)}" height="${(17 * s).toFixed(1)}" rx="1.4" fill="#8a5a33"/>
    <ellipse cx="0" cy="${(-30 * s).toFixed(1)}" rx="${(17 * s).toFixed(1)}" ry="${(19 * s).toFixed(1)}" fill="#4f9a55"/>
    <ellipse cx="${(-5 * s).toFixed(1)}" cy="${(-35 * s).toFixed(1)}" rx="${(11 * s).toFixed(1)}" ry="${(12 * s).toFixed(1)}" fill="#68b567"/>
    <ellipse cx="${(7 * s).toFixed(1)}" cy="${(-24 * s).toFixed(1)}" rx="${(8 * s).toFixed(1)}" ry="${(9 * s).toFixed(1)}" fill="#3f8647" fill-opacity="0.85"/>`;
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
    <rect x="-3.3" y="-50.8" width="6.6" height="4.6" rx="1.4" class="lamp-glow" fill="#fff0b8"/>`;
}

function benchSvg(axis) {
  const long = axis === "x";
  const w = long ? 1.7 : 0.55;
  const d = long ? 0.55 : 1.7;
  return box(-w / 2, -d / 2, w, d, 6, "#b3733f", "#8a5a33", "#6b4426", 0)
    + box(-w / 2, -d / 2, long ? w : 0.15, long ? 0.15 : d, 10, "#c98a4b", "#a96d36", "#8a5629", 6);
}

function propNode(p) {
  const [sx, sy] = iso(p.x, p.y, G);
  const at = `translate(${sx.toFixed(1)} ${sy.toFixed(1)})`;
  if (p.kind === "house") return nodeOf(houseSvg(p));
  const markup = { tree: () => treeSvg(p.s), bush: () => bushSvg(p.s), rock: () => rockSvg(p.s), lamp: lampSvg, bench: () => benchSvg(p.axis) }[p.kind]();
  return nodeOf(markup, "g", { transform: at });
}

function propDepth(p) {
  return p.kind === "house" ? p.x + p.w + p.y + p.d : p.x + p.y;
}

/* ---------- улица: прохожие, машины ---------- */

const PED_PATHS = [
  { a: [-2.8, 10.3], b: [11, 10.3], n: 3 },
  { a: [10.4, -2.8], b: [10.4, 11], n: 2 },
  { a: [-4, -3], b: [-4, 11], n: 1 },
  { a: [-26, 16.6], b: [34, 16.6], n: 5 },
  { a: [16.6, -26], b: [16.6, 34], n: 4 },
  { a: [-4, -4], b: [11, -4], n: 1 },
];
const CAR_COLORS = ["#d9604c", "#3d8fd4", "#e3b13c", "#f1ede2", "#5aa56f", "#7b5ea7", "#4c5560"];

function carSvg(color, axis) {
  const top = lighten(color, 0.12);
  const side = shade(color, 0.12);
  const wheel = (x0, x1, plane) => (axis === "x"
    ? face([[x0, 0.46, 0], [x1, 0.46, 0], [x1, 0.46, 3], [x0, 0.46, 3]], "#2a2622")
    : face([[0.46, x0, 0], [0.46, x1, 0], [0.46, x1, 3], [0.46, x0, 3]], plane || "#2a2622"));
  const body = axis === "x"
    ? box(-1, -0.45, 2, 0.9, 6, top, color, side, 0.5) + box(-0.55, -0.4, 1.05, 0.8, 5, "#cfe6ef", shade("#cfe6ef", 0.05), shade("#cfe6ef", 0.18), 6.5)
    : box(-0.45, -1, 0.9, 2, 6, top, color, side, 0.5) + box(-0.4, -0.55, 0.8, 1.05, 5, "#cfe6ef", shade("#cfe6ef", 0.05), shade("#cfe6ef", 0.18), 6.5);
  const shadow = face(axis === "x" ? [[-1.1, -0.5, 0.2], [1.1, -0.5, 0.2], [1.1, 0.7, 0.2], [-1.1, 0.7, 0.2]] : [[-0.5, -1.1, 0.2], [0.7, -1.1, 0.2], [0.7, 1.1, 0.2], [-0.5, 1.1, 0.2]], "#3b3f36", 0.2);
  return `<g transform="translate(${iso(0, 0, G)[0]} ${iso(0, 0, G)[1]})">${shadow}${body}${wheel(-0.7, -0.3)}${wheel(0.3, 0.7)}</g>`;
}

const CARS = [
  { axis: "x", fixed: 12.6, dir: 1, from: -26, to: 34, speed: 4.2, off: 0, color: 0 },
  { axis: "x", fixed: 14.4, dir: -1, from: -26, to: 34, speed: 3.6, off: 31, color: 1 },
  { axis: "x", fixed: 12.6, dir: 1, from: -26, to: 34, speed: 3.9, off: 40, color: 4 },
  { axis: "y", fixed: 12.6, dir: 1, from: -26, to: 34, speed: 3.8, off: 12, color: 2 },
  { axis: "y", fixed: 14.4, dir: -1, from: -26, to: 34, speed: 4.4, off: 22, color: 3 },
  { axis: "y", fixed: 14.4, dir: -1, from: -26, to: 34, speed: 4.1, off: 48, color: 5 },
];

let outer = null; // { statics: [{el, d}], ambient: [{el, kind, ...}], key }
const layers = { names: true, life: true };

function worldBuild(room) {
  const backs = room.querySelector("#backs");
  const outerG = room.querySelector("#outer");
  const items = [...HOUSES.map((h) => ({ kind: "house", ...h })), ...worldProps()];
  const shadows = [];
  const back = [];
  const statics = [];
  items.forEach((p) => {
    if (p.kind === "house") shadows.push(shadowFlat(p.x, p.y, p.w, p.d));
    const d = propDepth(p);
    const el = propNode(p);
    if (d < 8) back.push({ el, d });
    else statics.push({ el, d });
  });
  room.querySelector("#land").insertAdjacentHTML("beforeend", shadows.join(""));
  back.sort((a, b) => a.d - b.d).forEach((row) => backs.appendChild(row.el));
  const ambient = [];
  PED_PATHS.forEach((path, pi) => {
    const len = Math.hypot(path.b[0] - path.a[0], path.b[1] - path.a[1]);
    for (let i = 0; i < path.n; i += 1) {
      const id = pi * 10 + i;
      const look = looksOf(`прохожий${id}`);
      const el = nodeOf(figureSvg(look, "walk", false, null, false), "g", { class: "person walk ped" });
      ambient.push({
        el, kind: "ped", path, len, speed: 1.1 + ((id * 7) % 5) * 0.12, off: (i / path.n) * len * 2 + pi * 3.7, rank: ((id * 37) % 100) / 100, dir: i % 2 ? -1 : 1,
      });
    }
  });
  CARS.forEach((car) => {
    const el = nodeOf(carSvg(CAR_COLORS[car.color], car.axis), "g", { class: "car" });
    ambient.push({ el, kind: "car", car, rank: car.off % 7 / 7 });
  });
  statics.forEach((row) => outerG.appendChild(row.el));
  outer = { statics, ambient, key: "" };
  ambient.forEach((row) => outerG.appendChild(row.el));
}

function pedDensity(mins) {
  const peak = (m, c, s) => Math.exp(-(((m - c) / s) ** 2));
  return Math.min(1, 0.35 + 0.65 * Math.max(peak(mins, 540, 70), peak(mins, 780, 90) * 0.8, peak(mins, 1050, 80)));
}

function drawAmbient(mins) {
  if (!outer) return;
  const alive = layers.life;
  const dens = pedDensity(mins);
  const rows = [...outer.statics];
  outer.ambient.forEach((row) => {
    let x;
    let y;
    let alpha = 1;
    if (row.kind === "ped") {
      const { path, len } = row;
      const loop = len + 3;
      let s = (mins * row.speed + row.off) % loop;
      if (s < 0) s += loop;
      const u = row.dir > 0 ? s : len - s;
      const f = Math.min(1, s / 1.2, (loop - s) / 1.2);
      alpha = Math.max(0, f) * (row.rank < dens ? 1 : 0);
      const t = Math.min(1, Math.max(0, u / len));
      x = path.a[0] + (path.b[0] - path.a[0]) * t;
      y = path.a[1] + (path.b[1] - path.a[1]) * t;
      const [sx, sy] = iso(x, y, G);
      const flip = (path.b[0] - path.a[0] - (path.b[1] - path.a[1])) * row.dir < 0 ? -1 : 1;
      row.el.setAttribute("transform", `translate(${sx.toFixed(1)} ${sy.toFixed(1)}) scale(${1.05 * flip} 1.05)`);
    } else {
      const { car } = row;
      const span = car.to - car.from;
      let s = (mins * car.speed + car.off) % span;
      if (s < 0) s += span;
      const u = car.dir > 0 ? car.from + s : car.to - s;
      x = car.axis === "x" ? u : car.fixed;
      y = car.axis === "x" ? car.fixed : u;
      const [sx, sy] = iso(x, y, 0);
      row.el.setAttribute("transform", `translate(${sx.toFixed(1)} ${sy.toFixed(1)})`);
    }
    const shown = alive && alpha > 0.02;
    row.el.style.display = shown ? "" : "none";
    if (!shown) return;
    row.el.setAttribute("opacity", alpha.toFixed(2));
    rows.push({ el: row.el, d: x + y + (row.kind === "car" ? 0.5 : 0) });
  });
  rows.sort((a, b) => a.d - b.d);
  const key = rows.map((row) => (row.el.dataset.k ||= String(++stamp))).join(",");
  if (key !== outer.key) {
    const layer = document.getElementById("outer");
    rows.forEach((row) => layer.appendChild(row.el));
    outer.key = key;
  }
}

/* ---------- камера ---------- */

const CAM = { cx: 0, cy: 0, z: 1, min: 0.42, max: 3.4 };
let HOME = { x: 0, y: 0, w: 960, h: 580 };
const view = { x: 0, y: 0, w: 960, h: 580, k: 1 };
let tagK = 1;
let camFrame = 0;

function camReset(instant) {
  HOME = { x: VB.x - 230, y: VB.y - 150, w: VB.w + 460, h: VB.h + 300 };
  CAM.cx = HOME.x + HOME.w / 2;
  CAM.cy = HOME.y + HOME.h / 2;
  CAM.z = 1;
  camApply(instant);
}

function camApply() {
  const room = document.getElementById("room");
  const w = room.clientWidth || 960;
  const h = room.clientHeight || 580;
  CAM.z = Math.min(CAM.max, Math.max(CAM.min, CAM.z));
  const k = Math.min(w / HOME.w, h / HOME.h) * CAM.z;
  view.k = k;
  view.w = w / k;
  view.h = h / k;
  CAM.cx = Math.min(1500, Math.max(-1500, CAM.cx));
  CAM.cy = Math.min(900, Math.max(-500, CAM.cy));
  view.x = CAM.cx - view.w / 2;
  view.y = CAM.cy - view.h / 2;
  room.setAttribute("viewBox", `${view.x.toFixed(1)} ${view.y.toFixed(1)} ${view.w.toFixed(1)} ${view.h.toFixed(1)}`);
  tagK = Math.min(1.45, Math.max(0.6, CAM.z ** -0.6));
  room.classList.toggle("far", CAM.z < 0.62);
  const home = document.getElementById("cam-home");
  if (home) home.disabled = Math.abs(CAM.z - 1) < 0.01 && Math.abs(CAM.cx - (HOME.x + HOME.w / 2)) < 2 && Math.abs(CAM.cy - (HOME.y + HOME.h / 2)) < 2;
  if (!snap || camFrame) return;
  camFrame = requestAnimationFrame(() => {
    camFrame = 0;
    drawActors();
    renderFloat();
  });
}

function zoomAt(factor, px, py) {
  const room = document.getElementById("room");
  const x = px === undefined ? room.clientWidth / 2 : px;
  const y = py === undefined ? room.clientHeight / 2 : py;
  const wx = view.x + x / view.k;
  const wy = view.y + y / view.k;
  CAM.z = Math.min(CAM.max, Math.max(CAM.min, CAM.z * factor));
  const k = Math.min(room.clientWidth / HOME.w, room.clientHeight / HOME.h) * CAM.z;
  CAM.cx = wx - x / k + room.clientWidth / k / 2;
  CAM.cy = wy - y / k + room.clientHeight / k / 2;
  camApply();
}

function setLayer(name, on) {
  layers[name] = on;
  try { localStorage.setItem(`layer.${name}`, on ? "1" : "0"); } catch (e) { /* без хранилища работает и так */ }
  const room = document.getElementById("room");
  room.classList.toggle("nonames", !layers.names);
  if (snap) drawActors();
}

function camInit() {
  const room = document.getElementById("room");
  const pointers = new Map();
  let drag = null;
  let pinch = 0;
  let moved = false;

  try {
    ["names", "life"].forEach((name) => {
      const saved = localStorage.getItem(`layer.${name}`);
      if (saved !== null) layers[name] = saved === "1";
    });
  } catch (e) { /* без хранилища работает и так */ }
  ["names", "life"].forEach((name) => {
    const box = document.getElementById(`lay-${name}`);
    if (!box) return;
    box.checked = layers[name];
    box.addEventListener("change", () => setLayer(name, box.checked));
  });
  room.classList.toggle("nonames", !layers.names);

  room.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = room.getBoundingClientRect();
    zoomAt(Math.exp(-event.deltaY * (event.ctrlKey ? 0.01 : 0.0016)), event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });

  room.addEventListener("pointerdown", (event) => {
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      drag = { x: event.clientX, y: event.clientY, cx: CAM.cx, cy: CAM.cy, on: false };
      moved = false;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = Math.hypot(a.x - b.x, a.y - b.y);
      drag = null;
    }
  });
  room.addEventListener("pointermove", (event) => {
    const p = pointers.get(event.pointerId);
    if (!p) return;
    p.x = event.clientX;
    p.y = event.clientY;
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const rect = room.getBoundingClientRect();
      zoomAt(dist / pinch, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      pinch = dist;
      moved = true;
      return;
    }
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.on && Math.hypot(dx, dy) < 5) return;
    if (!drag.on) {
      drag.on = true;
      room.setPointerCapture(event.pointerId);
      room.classList.add("drag");
    }
    moved = true;
    CAM.cx = drag.cx - dx / view.k;
    CAM.cy = drag.cy - dy / view.k;
    camApply();
  });
  const up = (event) => {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinch = 0;
    if (!pointers.size) {
      drag = null;
      room.classList.remove("drag");
    }
  };
  room.addEventListener("pointerup", up);
  room.addEventListener("pointercancel", up);
  // перетаскивание не должно открывать разговор того, над кем закончилось
  document.getElementById("world").addEventListener("click", (event) => {
    if (!moved) return;
    moved = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);
  room.addEventListener("dblclick", (event) => {
    if (event.target.closest("[data-client]")) return;
    camReset();
  });

  document.getElementById("cam-in").addEventListener("click", () => zoomAt(1.35));
  document.getElementById("cam-out").addEventListener("click", () => zoomAt(1 / 1.35));
  document.getElementById("cam-home").addEventListener("click", () => camReset());
  document.body.addEventListener("keydown", (event) => {
    if (event.target !== document.body || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "+" || event.key === "=") zoomAt(1.25);
    else if (event.key === "-" || event.key === "_") zoomAt(1 / 1.25);
    else if (event.key === "0") camReset();
  });
  window.addEventListener("resize", () => camApply());
}

camInit();
