/* Модель машины для carSvg: объёмное тело из «лофтов» — колец точек (u, v, z), соединённых гранями.
   u — вперёд по ходу, v — вбок (видимый борт v = +W/2), z — вверх в пикселях. Углы колец срезаны, поэтому у кузова и кабины
   есть фаски: они ловят свет и делают форму мягкой, но грани остаются плоскими и чёткими.
   Каждая грань красится по нормали (свет сверху-слева, тень холодная), стекло отдельно, с косым бликом. Весь силуэт обводится
   тёмной линией, внутренние рёбра — тоном своей грани.
   Зависит только от iso(), mix/shade/lighten и PAL.tint. Используется carSvg в cars.js. */

const CAR_SUN = (() => {
  const n = (a) => { const l = Math.hypot(...a); return a.map((x) => x / l); };
  return { sun: n([-0.45, 0.35, 0.82]), view: n([29, 29, 36]) };
})();

/* Восьмиугольник со срезанными углами: прямоугольник [u0, u1] × [−w, w] с фаской c. Обход против часовой при взгляде сверху. */
function carOct(u0, u1, w, c, z) {
  const zf = typeof z === "function" ? z : () => z;
  return [
    [u0 + c, -w], [u1 - c, -w], [u1, -w + c], [u1, w - c], [u1 - c, w], [u0 + c, w], [u0, w - c], [u0, -w + c],
  ].map(([u, v]) => [u, v, zf(u, v)]);
}

/* Тело из колец: rings[i] и rings[i + 1] соединяются боковыми гранями, верхнее кольцо закрывается крышкой.
   paint(face) → {fill, glass} решает цвет грани по её номеру и нормали. */
function carLoft(rings, paint, out, P) {
  const center = rings.flat().reduce((s, p) => [s[0] + p[0], s[1] + p[1], s[2] + p[2]], [0, 0, 0]).map((x) => x / rings.flat().length);
  const push = (pts, meta) => {
    const world = pts.map((p) => P(...p));
    const ph = world.map(([x, y, z]) => [x * 29, y * 29, z]);
    const c = ph.reduce((s, p) => [s[0] + p[0], s[1] + p[1], s[2] + p[2]], [0, 0, 0]).map((x) => x / ph.length);
    // нормаль по Ньюэллу: устойчива и для неплоских четырёхугольников
    let n = [0, 0, 0];
    for (let i = 0; i < ph.length; i += 1) {
      const a = ph[i], b = ph[(i + 1) % ph.length];
      n[0] += (a[1] - b[1]) * (a[2] + b[2]);
      n[1] += (a[2] - b[2]) * (a[0] + b[0]);
      n[2] += (a[0] - b[0]) * (a[1] + b[1]);
    }
    const len = Math.hypot(...n);
    if (len < 1e-6) return;
    n = n.map((x) => x / len);
    const cw = P(...center);
    const ref = [cw[0] * 29, cw[1] * 29, cw[2]];
    if (n[0] * (c[0] - ref[0]) + n[1] * (c[1] - ref[1]) + n[2] * (c[2] - ref[2]) < 0) n = n.map((x) => -x);
    const vis = n[0] * CAR_SUN.view[0] + n[1] * CAR_SUN.view[1] + n[2] * CAR_SUN.view[2];
    if (vis <= 0.01) return;
    const look = paint({ ...meta, n, pts });
    if (!look) return;
    out.push({ world, ...look, depth: (c[0] + c[1]) / 29 + c[2] / 40 });
  };
  for (let r = 0; r < rings.length - 1; r += 1) {
    const a = rings[r], b = rings[r + 1];
    for (let i = 0; i < a.length; i += 1) {
      const j = (i + 1) % a.length;
      push([a[i], a[j], b[j], b[i]], { band: r, edge: i });
    }
  }
  push(rings[rings.length - 1].slice().reverse(), { band: rings.length - 1, cap: true });
}

/* Цвет грани по нормали: свет сверху-слева, затенённые стороны уходят в холодный, а не в чёрный. */
function carTone(base, n, top = 0.32) {
  const d = n[0] * CAR_SUN.sun[0] + n[1] * CAR_SUN.sun[1] + n[2] * CAR_SUN.sun[2];
  if (n[2] > 0.8) return lighten(base, top);
  if (d > 0.35) return lighten(base, 0.08 + (d - 0.35) * 0.3);
  if (d > 0) return base;
  return mix(shade(base, 0.04), PAL.tint, Math.min(0.34, 0.16 - d * 0.25));
}

function carGlass(n) {
  if (n[2] > 0.5) return "#a9dcf4";
  const d = n[0] * CAR_SUN.sun[0] + n[1] * CAR_SUN.sun[1] + n[2] * CAR_SUN.sun[2];
  return d > 0 ? "#86c4e8" : "#5c93c2";
}
