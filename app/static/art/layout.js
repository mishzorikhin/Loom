/* Раскладка мира: уровни, улицы, где что стоит.
   G — уровень земли (низ плиты зала); ROAD_X0/ROAD_X1 — границы улиц; SIDEWALKS — прямоугольники тротуаров [x0, y0, x1, y1];
   PROPS_FIXED — расставленные вручную деревья, фонари, скамейки и др.; worldProps() — они плюс случайные деревья, кусты и камни на траве;
   onGrass(x, y, margin) — свободна ли точка для травы; propDepth — ключ сортировки. Менять, чтобы переставить предметы или улицы;
   но координаты улиц связаны с сервером (app/city.py), двигать их нельзя. */

const G = -15; // земля лежит на уровне низа плиты зала
const GRASS = PAL.grassBase;
const PAVE = PAL.pave;
const KERB = PAL.kerb;
const ROAD = PAL.road;
const ROAD_X0 = 11.5;
const ROAD_X1 = 15.5;

/* ---------- земля ---------- */

const SIDEWALKS = [
  [-3.5, -3.5, ROAD_X1 + 2.5, 11.6],
  [-30, 15.5, 38, 17.7],
  [15.5, -30, 17.7, 38],
  [-5.2, -30, -2.8, 11.6],
  [-30, -5.2, ROAD_X0, -2.8],
  [-9.2, 17.7, 5.5, 31.5],
];

const PROPS_FIXED = [
  { kind: "tree", x: -2.1, y: 3.2, s: 1.0, v: 0 },
  { kind: "tree", x: -2.1, y: 8.4, s: 0.9, v: 3 },
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
  { kind: "bush", x: -1.6, y: 9.9, v: 1 },
  { kind: "bed", x: 4.6, y: 10.1, axis: "x" },
  { kind: "bed", x: -7.6, y: 23.2, axis: "y" },
  { kind: "bed", x: 1.2, y: 30.3, axis: "x" },
  { kind: "bin", x: 8.5, y: 10.7 },
  { kind: "bin", x: -0.7, y: 10.7 },
  { kind: "bin", x: -6.4, y: 18.2 },
  { kind: "hydrant", x: 10.9, y: 3.1 },
  { kind: "hydrant", x: 16.8, y: 21.5 },
  { kind: "sign", x: 16.9, y: 10.9 },
  { kind: "lamp", x: -6.2, y: 18.4 },
  { kind: "lamp", x: 4.9, y: 30.6 },
];

/* Вид дерева по месту: дуб, ель, берёза, цветущее. Детерминированно, без лишних вызовов генератора. */
function treeKind(x, y) {
  const m = Math.abs(Math.floor(x * 13 + y * 7)) % 10;
  return m < 5 ? 0 : m < 7 ? 1 : m < 9 ? 2 : 3;
}

function onGrass(x, y, margin = 0) {
  if ((snap?.building_plots || []).some(p => x > p.ox - 1 - margin && x < p.ox + 9 + margin && y > p.oy - 1 - margin && y < p.oy + 9 + margin)) return false;
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
  const props = PROPS_FIXED.map((p) => (p.kind === "tree" && p.v === undefined ? { ...p, v: treeKind(p.x, p.y) } : p));
  const rand = rng(7);
  for (let i = 0; i < 90 && props.length < PROPS_FIXED.length + 44; i += 1) {
    const x = -26 + rand() * 58;
    const y = -26 + rand() * 62;
    const kind = rand() < 0.78 ? "tree" : rand() < 0.5 ? "bush" : "rock";
    if (onGrass(x, y, 0.8)) props.push({ kind, x, y, s: 0.8 + rand() * 0.55, v: kind === "tree" ? treeKind(x, y) : Math.abs(Math.floor(x * 5 + y)) % 2 });
  }
  return props;
}

function propDepth(p) {
  return p.kind === "house" ? p.x + p.w + p.y + p.d : p.x + p.y;
}
