/* Скамейка.
   benchSvg(axis): деревянные рейки PAL.wood на графитовых опорах; axis "x"|"y" — длинная сторона. */

/* Скамейка: тёплые деревянные рейки на графитовых опорах. Ось задаёт длинную сторону. */
function benchSvg(axis) {
  const long = axis === "x";
  const L = 1.8;
  const T = 0.6;
  const w = long ? L : T;
  const d = long ? T : L;
  const W = PAL.wood;
  const parts = [`<defs>${radial("bch", [[0, PAL.shadow, 0.26], [1, PAL.shadow, 0]])}</defs><ellipse cx="6" cy="2" rx="${long ? 34 : 19}" ry="9" fill="url(#bch)"/>`];
  const leg = (x0, y0) => box(x0, y0, 0.07, 0.07, 6.5, PAL.metal[2], PAL.metal[0], PAL.metal[1], 0);
  [[-w / 2, -d / 2], [w / 2 - 0.07, -d / 2], [-w / 2, d / 2 - 0.07], [w / 2 - 0.07, d / 2 - 0.07]].forEach(([a, b]) => parts.push(leg(a, b)));
  const slats = 3;
  for (let i = 0; i < slats; i += 1) {
    if (long) parts.push(box(-w / 2, -d / 2 + 0.05 + i * 0.17, w, 0.13, 1.4, W.light, W.mid, W.dark, 6.5));
    else parts.push(box(-w / 2 + 0.05 + i * 0.17, -d / 2, 0.13, d, 1.4, W.light, W.mid, W.dark, 6.5));
  }
  [0, 1].forEach((i) => {
    if (long) parts.push(box(-w / 2, -d / 2, w, 0.07, 2.4, W.light, W.mid, W.dark, 10.5 + i * 3.6));
    else parts.push(box(-w / 2, -d / 2, 0.07, d, 2.4, W.light, W.mid, W.dark, 10.5 + i * 3.6));
  });
  [-w / 2, w / 2 - 0.07].forEach((a) => {
    if (long) parts.push(box(a, -d / 2, 0.07, 0.07, 10, PAL.metal[2], PAL.metal[0], PAL.metal[1], 6.5));
  });
  return parts.join("");
}
