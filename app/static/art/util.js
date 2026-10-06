/* Общие помощники рисования.
   rng(seed) — детерминированный генератор; ov(points, fill, alpha) — многоугольник без обводки; lines(list, color, width, alpha) — много
   отрезков одним путём; gface(x0, y0, x1, y1, fill, alpha, dz) — плоскость на уровне земли; radial/vertical — градиенты (id, stops);
   BLUR(id, dev) — размытие; hull — выпуклая оболочка; softShadow(foot, height, z, alpha, dev, tint) — мягкая цветная тень по SUN;
   softFloorShadows(polys, alpha, dev) — тень на полу зала; BOX_AT(x, y, w, d) — коробка для сортировки по глубине.
   Базовые iso, face, box, seg, mix, shade, lighten, pt лежат в app.js. Менять здесь осторожно: этим пользуются все рисунки. */

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

/* ---------- общие приёмы рисования ---------- */

/* Многоугольник без обводки: накладки, швы, блики. */
function ov(points, fill, alpha) {
  const op = alpha === undefined || alpha >= 1 ? "" : ` fill-opacity="${alpha}"`;
  return `<polygon points="${points.map(pt).join(" ")}" fill="${fill}"${op}/>`;
}

/* Много отрезков одним путём: дешевле сотни <line>. Отрезки заданы в мировых координатах. */
function lines(list, color, width, alpha = 1) {
  const d = list.map(([a, b]) => {
    const [x1, y1] = iso(a[0], a[1], a[2] || 0);
    const [x2, y2] = iso(b[0], b[1], b[2] || 0);
    return `M${x1.toFixed(1)} ${y1.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}`;
  }).join("");
  return `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" stroke-opacity="${alpha}" stroke-linecap="round"/>`;
}

function radial(id, stops, cx = 0.5, cy = 0.5, r = 0.5) {
  return `<radialGradient id="${id}" cx="${cx}" cy="${cy}" r="${r}">${stops.map(([o, c, a]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join("")}</radialGradient>`;
}

function vertical(id, stops) {
  return `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">${stops.map(([o, c, a]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join("")}</linearGradient>`;
}

const BLUR = (id, dev) => `<filter id="${id}" x="-25%" y="-25%" width="150%" height="150%"><feGaussianBlur stdDeviation="${dev}"/></filter>`;

/* ---------- дома, деревья, фонари ---------- */

/* Свет сверху-слева, из -x: тени ложатся вправо-вниз по экрану (к +x). */
const SUN = [1, 0.22];

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

/* Мягкая цветная тень: та же форма, но размытая. */
function softShadow(foot, height, z, alpha = 0.2, dev = 2.4, tint = PAL.shadow) {
  const len = height / 42;
  const moved = foot.map(([x, y]) => [x + SUN[0] * len, y + SUN[1] * len]);
  const shape = hull([...foot, ...moved]).map(([x, y]) => [x, y, z]);
  const grow = foot.map(([x, y]) => [x, y, z]);
  return `<defs>${BLUR("sb", dev)}</defs><g filter="url(#sb)">${ov(shape, tint, alpha)}${ov(grow, tint, alpha * 0.8)}</g>`;
}

/* ---------- зал кофейни ---------- */

/* Мягкая цветная тень на полу под мебелью: одна размытая группа вместо ступенчатых многоугольников. */
function softFloorShadows(polys, alpha = 0.2, dev = 2.4) {
  return `<defs>${BLUR("fb", dev)}</defs><g filter="url(#fb)">${polys.map((poly) => ov(poly.map(([x, y]) => [x + 0.12, y + 0.04, 0.3]), PAL.shadowWarm, alpha)).join("")}</g>`;
}

const BOX_AT = (x, y, w, d) => [x - 0.05, x + w + 0.05, y - 0.05, y + d + 0.05];
