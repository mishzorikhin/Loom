/* Дороги, парковка, бордюры и дорожная разметка.
   roadSurfaceSvg() — clipPath "roadClip", полотно парковки и двух улиц, перекрёсток чуть светлее (PAL.road, PAL.roadX).
   kerbSvg() — светлый бордюр и тонкая кромка у дороги; kerbHighlightSvg() — светлая линия по верху бордюра (рисуется поверх разметки).
   laneMarkingsSvg() — жёлтая осевая, белые краевые линии, стрелки направления и парковочные места. Цвета PAL.paint/yellow.
   Положение улиц задают ROAD_X0/ROAD_X1 в layout.js. */

const ROAD_SPANS = [[-30, ROAD_X0], [ROAD_X1, 38]];

function roadSurfaceSvg() {
  const clip = `<defs><clipPath id="roadClip">${[
    [-30, ROAD_X0, 38, ROAD_X1], [ROAD_X0, -30, ROAD_X1, 38],
  ].map(([a, b, c, d]) => `<polygon points="${[[a, b], [c, b], [c, d], [a, d]].map((p) => pt([p[0], p[1], G])).join(" ")}"/>`).join("")}</clipPath></defs>`;
  return clip
    + gface(8.0, 17.7, 11.2, 31.6, ROAD) // парковка
    + gface(-30, ROAD_X0, 38, ROAD_X1, ROAD)
    + gface(ROAD_X0, -30, ROAD_X1, 38, ROAD)
    + gface(ROAD_X0, ROAD_X0, ROAD_X1, ROAD_X1, PAL.roadX);
}

function kerbSvg() {
  const out = [];
  const kerbEdge = [];
  [ROAD_X0, ROAD_X1].forEach((v) => ROAD_SPANS.forEach(([a, b]) => {
    const near = v === ROAD_X0 ? -0.22 : 0.22;
    out.push(gface(a, Math.min(v, v + near), b, Math.max(v, v + near), KERB, 1, 0.2));
    out.push(gface(Math.min(v, v + near), a, Math.max(v, v + near), b, KERB, 1, 0.2));
    kerbEdge.push([[a, v, G], [b, v, G]], [[v, a, G], [v, b, G]]);
  }));
  out.push(lines(kerbEdge, PAL.roadEdge, 1, 0.5));
  return out.join("");
}

function kerbHighlightSvg() {
  const kerbTop = [];
  [ROAD_X0, ROAD_X1].forEach((v) => ROAD_SPANS.forEach(([a, b]) => {
    const near = v === ROAD_X0 ? -0.22 : 0.22;
    kerbTop.push([[a, v + near, G], [b, v + near, G]], [[v + near, a, G], [v + near, b, G]]);
  }));
  return lines(kerbTop, PAL.paveHi, 0.9, 0.8);
}

/* Разметка. Первые две группы обрезаны полотном дороги, остальные лежат поверх без обрезки. */
function laneMarkingsSvg() {
  const mid = (ROAD_X0 + ROAD_X1) / 2;
  const dashes = [];
  for (let v = -30; v < 38; v += 2.4) {
    if (v > ROAD_X0 - 1 && v < ROAD_X1 + 1) continue;
    dashes.push([[v, mid, G], [v + 1.2, mid, G]], [[mid, v, G], [mid, v + 1.2, G]]);
  }
  const edgeLines = [];
  ROAD_SPANS.forEach(([a, b]) => [ROAD_X0 + 0.45, ROAD_X1 - 0.45].forEach((v) => edgeLines.push([[a, v, G], [b, v, G]], [[v, a, G], [v, b, G]])));
  const clipped = lines(dashes, PAL.yellow, 2) + lines(edgeLines, PAL.paint, 1, 0.8);
  const free = [];
  [5, 23].forEach((u) => {
    ["x", "y"].forEach((axis) => [-1, 1].forEach((dir) => {
      const v = axis === "x" ? (dir > 0 ? 14.4 : 12.6) : (dir > 0 ? 12.6 : 14.4);
      const Q = (a, b) => axis === "x" ? [u + a * dir, v + b, G + 0.5] : [v + b, u + a * dir, G + 0.5];
      free.push(ov([Q(-0.8, -0.08), Q(0.25, -0.08), Q(0.25, -0.25), Q(0.85, 0), Q(0.25, 0.25), Q(0.25, 0.08), Q(-0.8, 0.08)], PAL.paint, 0.9));
    }));
  });
  free.push(zebraSvg());
  const stalls = [];
  [0, 1, 2, 3, 4, 5].forEach((i) => stalls.push([[8.5, 18.8 + i * 2.4, G], [10.0, 18.8 + i * 2.4, G]]));
  free.push(lines(stalls, PAL.paint, 1.4));
  free.push(lines([[[10.6, 18.8, G], [10.6, 18.8 + 5 * 2.4, G]]], PAL.paint, 0.9, 0.6));
  return `<g clip-path="url(#roadClip)">${clipped}</g>` + free.join("");
}
