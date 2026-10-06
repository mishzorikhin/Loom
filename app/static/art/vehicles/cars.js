/* Машина: carSvg(color, axis, dir, kindName, taxi) — SVG-строка в мировых координатах, кэш carCache по всем параметрам.
   Смотреть и править удобно в песочнице art/sandbox/cars.html (все виды, четыре направления, масштаб).
   Ориентир — угловатый low-poly седан: прямой высокий кузов с острыми рёбрами, серые выступающие бамперы, порог и накладки арок,
   колёса утоплены в арки; кабина-трапеция, стёкла вставлены в рамки цвета кузова; крупная тёмная решётка, квадратные фары,
   номер на бампере, серый молдинг и ручки дверей. Без обводки: форму держат три тона граней.
   Геометрия видов — CAR_KINDS в kinds.js (в клетках по длине/ширине и пикселях по высоте). */

const CAR_GREY = "#7c8089";
const CAR_DARK = "#2c2f36";
const CAR_GLASS = "#8fd3f5";

const carCache = new Map();

function carSvg(color, axis, dir, kindName, taxi) {
  const cacheKey = `${color}|${axis}|${dir}|${kindName}|${taxi ? 1 : 0}`;
  if (carCache.has(cacheKey)) return carCache.get(cacheKey);
  const s = CAR_KINDS[kindName];
  const half = s.L / 2, hw = s.W / 2;
  const P = (u, v, z) => axis === "x" ? [u * dir, v, z] : [v, u * dir, z];
  const solids = [];
  const parts = [];
  const poly = (pts, fill, a) => parts.push(`<polygon points="${pts.map((p) => pt(P(...p))).join(" ")}" fill="${fill}"${a === undefined ? "" : ` fill-opacity="${a}"`} stroke="${fill}" stroke-width="0.5" stroke-linejoin="round"${a === undefined ? "" : ` stroke-opacity="${a}"`}/>`);
  const lerp = (p, q, t) => p.map((x, i) => x + (q[i] - x) * t);
  /* точка на грани-четырёхугольнике [a низ-1, b низ-2, c верх-2, d верх-1] по долям (t вдоль, h вверх) */
  const onQuad = ([a, b, c, d], t, h) => lerp(lerp(a, b, t), lerp(d, c, t), h);
  const pane = (q, t0, t1, h0, h1) => [onQuad(q, t0, h0), onQuad(q, t1, h0), onQuad(q, t1, h1), onQuad(q, t0, h1)];

  // тень
  const foot = carOct(-half - 0.06, half + 0.1, hw + 0.08, 0.3, 0).map(([u, v]) => { const w = P(u + 0.1, v + 0.12, 0); return [w[0], w[1], 0]; });
  parts.push(`<defs>${BLUR("carsh", 1.4)}</defs><polygon filter="url(#carsh)" points="${foot.map(pt).join(" ")}" fill="${PAL.shadow}" fill-opacity="0.32"/>`);

  const drawSolids = () => {
    solids.sort((a, b) => a.depth - b.depth).forEach((f) => parts.push(`<polygon points="${f.world.map(pt).join(" ")}" fill="${f.fill}" stroke="${f.fill}" stroke-width="0.6" stroke-linejoin="round"/>`));
    solids.length = 0;
  };
  const bumper = (u0, u1) => carLoft([carOct(u0, u1, hw + 0.03, 0.04, 3.4), carOct(u0, u1, hw + 0.03, 0.04, 7.2)], ({ n, cap }) => ({ fill: carTone(CAR_GREY, n, cap ? 0.18 : 0.1) }), solids, P);
  const near = dir > 0 ? [half - 0.02, half + 0.12] : [-half - 0.12, -half + 0.02];
  const far = dir > 0 ? [-half - 0.12, -half + 0.02] : [half - 0.02, half + 0.12];

  // дальний бампер, кузов, кабина
  bumper(...far); drawSolids();
  carLoft([
    carOct(-half, half, hw, 0.05, 4.4),
    carOct(-half, half, hw, 0.05, s.body - 0.7),
    carOct(-half + 0.04, half - 0.04, hw - 0.04, 0.06, s.body),
  ], ({ n, cap }) => ({ fill: carTone(color, n, cap ? 0.2 : 0.24) }), solids, P);
  drawSolids();
  const glassFaces = [];
  carLoft([
    carOct(s.cab[0], s.cab[1], hw - 0.06, 0.04, s.body),
    carOct(s.cab[2], s.cab[3], hw * 0.8, 0.04, s.roof - 0.5),
    carOct(s.cab[2] + 0.03, s.cab[3] - 0.03, hw * 0.8 - 0.03, 0.05, s.roof),
  ], ({ band, edge, cap, n, pts }) => {
    if (band === 0 && edge % 2 === 0) glassFaces.push({ edge, pts });
    return { fill: carTone(color, n, cap ? 0.26 : 0.22) };
  }, solids, P);
  drawSolids();

  // стёкла в рамках: вставки внутри граней кабины (рамка — цвет кузова вокруг)
  glassFaces.forEach(({ edge, pts }) => {
    const side = edge === 0 || edge === 4;
    const tint = edge === 4 ? CAR_GLASS : edge === 0 ? "#6fb8e0" : "#7cc6ec";
    if (side) s.panes.forEach(([t0, t1]) => poly(pane(pts, t0, t1, 0.14, 0.86), tint));
    else {
      poly(pane(pts, 0.1, 0.9, 0.14, 0.86), tint);
      poly(pane(pts, 0.22, 0.4, 0.2, 0.8), "#ffffff", 0.22);
    }
  });

  const hv = hw + 0.004;
  const sideQ = (u0, u1, z0, z1, fill, a) => poly([[u0, hv, z0], [u1, hv, z0], [u1, hv, z1], [u0, hv, z1]], fill, a);
  const greySide = carTone(CAR_GREY, [0, 1, 0]);
  // порог, молдинг, ручки
  sideQ(-half + 0.05, half - 0.05, 4.4, 5.8, greySide);
  const B = s.body;
  sideQ(-half + 0.12, half - 0.18, B - 5.6, B - 4.9, CAR_GREY);
  const doorU = (s.cab[0] + s.cab[1]) / 2;
  if (kindName !== "van") [s.cab[0] + 0.18, doorU + 0.18].forEach((u) => sideQ(u, u + 0.14, B - 3.4, B - 2.7, CAR_GREY));
  else sideQ(s.cab[1] - 0.3, s.cab[1] - 0.16, B - 3.4, B - 2.7, CAR_GREY);

  if (taxi) for (let i = 0; i < 8; i += 1) {
    const u0 = -half + 0.32 + i * 0.26;
    sideQ(u0, u0 + 0.13, B - 7.4, B - 6.2, i % 2 ? "#ffffff" : "#2a2c31", 0.95);
  }

  // видимый торец: решётка и фары впереди, фонари сзади
  const front = dir > 0;
  const eu = front ? half + 0.004 : -half - 0.004;
  const endQ = (v0, v1, z0, z1, fill, a, u = eu) => poly([[u, v0, z0], [u, v1, z0], [u, v1, z1], [u, v0, z1]], fill, a);
  if (front) {
    endQ(-0.26, 0.26, 8, B - 1.4, CAR_DARK);
    for (let i = 0; i < 6; i += 1) endQ(-0.24 + i * 0.09, -0.21 + i * 0.09, 8.4, B - 1.8, "#3d424c");
    [-1, 1].forEach((sd) => endQ(sd > 0 ? 0.32 : -hw + 0.08, sd > 0 ? hw - 0.08 : -0.32, B - 5.6, B - 1.4, "#ffd93a"));
  } else {
    [-1, 1].forEach((sd) => endQ(sd > 0 ? 0.3 : -hw + 0.08, sd > 0 ? hw - 0.08 : -0.3, B - 5.2, B - 1.6, "#ff4b3e"));
  }

  // колёса: тёмная ниша под серой накладкой арки, шина с толщиной, колпак со ступицей (спицы вращает Phaser)
  const R = 5.6, zc = 5.8, ru = R / 31;
  const ring = (u, v, k, from = 0, to = Math.PI * 2, n = 26) => Array.from({ length: n + 1 }, (_, i) => {
    const t = from + (to - from) * i / n;
    return [u + Math.cos(t) * ru * k, v, zc + Math.sin(t) * R * k];
  });
  [-half + 0.5, half - 0.5].forEach((u) => {
    const top = ring(u, hv + 0.003, 1.16, 0, Math.PI, 18);
    poly([...top, [u - ru * 1.16, hv + 0.003, 3.6], [u + ru * 1.16, hv + 0.003, 3.6]], "#23262c");
    poly([...ring(u, hv + 0.002, 1.42, 0, Math.PI, 18), ...ring(u, hv + 0.002, 1.16, Math.PI, 0, 18)], greySide);
    const back = ring(u, hw - 0.06, 1), face = ring(u, hw + 0.05, 1);
    const tread = hull([...back, ...face].map((p) => iso(...P(...p))));
    parts.push(`<polygon points="${tread.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}" fill="#1c1e23"/>`);
    poly(face, "#2a2c31");
    poly(ring(u, hw + 0.052, 0.62), "#a6abb4");
    poly(ring(u, hw + 0.054, 0.5), "#8d939d");
    poly(ring(u, hw + 0.056, 0.16), "#5d636d");
  });

  // ближний бампер и номер на нём
  bumper(...near); drawSolids();
  const bu = front ? half + 0.124 : -half - 0.124;
  endQ(-0.18, 0.18, 4.2, 6.4, "#fffbd0", undefined, bu);

  if (taxi) {
    const tu = (s.cab[2] + s.cab[3]) / 2;
    carLoft([carOct(tu - 0.2, tu + 0.2, 0.17, 0.02, s.roof), carOct(tu - 0.2, tu + 0.2, 0.17, 0.02, s.roof + 3.6)], ({ n, cap }) => ({ fill: cap ? "#fff0a8" : carTone("#ffcf3a", n) }), solids, P);
    drawSolids();
  }
  const out = `<g transform="translate(0 ${-G})">${parts.join("")}</g>`;
  carCache.set(cacheKey, out);
  return out;
}
