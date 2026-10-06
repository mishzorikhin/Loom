/* Тротуары: плиты и края.
   pavingSvg(rects) — плоская заливка PAL.pave и крупные швы; pavementEdges(rects) — светлая кромка с севера/запада и боковая грань
   с юга/востока там, где тротуар граничит с травой. Параметры: список прямоугольников SIDEWALKS. Цвета: PAL.pave*. */

/* Плиты тротуара: чистый тон и редкие тонкие швы крупной сеткой. */
function pavingSvg(rects) {
  const out = [];
  rects.forEach(([x0, y0, x1, y1]) => {
    out.push(gface(x0, y0, x1, y1, PAVE));
    const seams = [];
    const step = 2.2;
    for (let x = Math.ceil(x0 / step) * step; x < x1; x += step) seams.push([[x, y0, G], [x, y1, G]]);
    for (let y = Math.ceil(y0 / step) * step; y < y1; y += step) seams.push([[x0, y, G], [x1, y, G]]);
    out.push(lines(seams, PAL.paveSeam, 0.8, 0.7));
  });
  return out.join("");
}

/* Края тротуара, выходящие на траву: светлая кромка с севера и запада, видимая боковая грань с юга и востока. */
function pavementEdges(rects) {
  const out = [];
  const lip = (a, b, dir) => {
    const z = 4;
    out.push(ov([[a[0], a[1], G], [b[0], b[1], G], [b[0], b[1], G - z], [a[0], a[1], G - z]], dir === "s" ? PAL.paveLip : PAL.paveLipE));
  };
  const light = [];
  rects.forEach(([x0, y0, x1, y1]) => {
    for (let x = Math.max(x0, -30); x < Math.min(x1, 38); x += 1) {
      const xb = Math.min(x + 1, x1);
      if (onGrass((x + xb) / 2, y1 + 0.4)) lip([x, y1], [xb, y1], "s");
      if (onGrass((x + xb) / 2, y0 - 0.4)) light.push([[x, y0, G], [xb, y0, G]]);
    }
    for (let y = Math.max(y0, -30); y < Math.min(y1, 38); y += 1) {
      const yb = Math.min(y + 1, y1);
      if (onGrass(x1 + 0.4, (y + yb) / 2)) lip([x1, y], [x1, yb], "e");
      if (onGrass(x0 - 0.4, (y + yb) / 2)) light.push([[x0, y, G], [x0, yb, G]]);
    }
  });
  out.push(lines(light, PAL.paveHi, 1.2, 0.9));
  return out.join("");
}
