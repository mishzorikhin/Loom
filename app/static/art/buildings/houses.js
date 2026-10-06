/* Дом: houseSvg(o) и его тени.
   houseSvg({x, y, w, d, h, wall, roof, ridge, chimney}) — SVG-строка: стены в три тона, окна со ставнями и цветочными ящиками, дверь,
   двускатная кровля (ridge), дымоход с дымом. Окна оборачиваются в <polygon style="opacity:calc(var(--night,0)*..)">: Phaser вырезает
   их в светящийся слой ночью. houseShadows(houses) — размытая цветная тень по SUN. glow/smokeSvg — свет окна и клубы дыма.
   Менять: цвета ставен/дверей (SHUTTERS, DOORS), число окон (w / 1.7), высота кровли r, число линий кровли rows. */

function houseShadow(h) {
  const foot = [[h.x, h.y], [h.x + h.w, h.y], [h.x + h.w, h.y + h.d], [h.x, h.y + h.d]];
  const len = (h.h + Math.min(h.w, h.d) * 5) / 42;
  const moved = foot.map(([x, y]) => [x + SUN[0] * len, y + SUN[1] * len]);
  const pad = 0.3;
  const base = [[h.x - pad, h.y - pad], [h.x + h.w + pad, h.y - pad], [h.x + h.w + pad, h.y + h.d + pad], [h.x - pad, h.y + h.d + pad]];
  return ov(hull([...foot, ...moved]).map(([x, y]) => [x, y, G + 0.15]), PAL.shadow, 0.2)
    + ov(base.map(([x, y]) => [x, y, G + 0.2]), PAL.shadow, 0.1);
}

function houseShadows(houses) {
  return `<defs>${BLUR("hb", 2.2)}</defs><g filter="url(#hb)">${houses.map(houseShadow).join("")}</g>`;
}

function glow(points) {
  return `<polygon points="${points.map(pt).join(" ")}" fill="#ffd98a" style="opacity:calc(var(--night, 0) * 0.95)"/>`;
}

function smokeSvg(x, y, z) {
  const [sx, sy] = iso(x, y, z);
  return `<g transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)})">${[0, 1.3, 2.6].map((d) => `<circle class="puff" r="3.2" fill="#ffffff" style="animation-delay:-${d}s"/>`).join("")}</g>`;
}

const SHUTTERS = ["#5fc9b3", "#ee8a69", "#9bd36f", "#7aa8ee"];
const DOORS = ["#e0875f", "#4fbba6", "#6c90e3", "#a881d8"];

/* Дом: стены в три тона (верх светлее, левая средняя, правая холоднее), плоская кровля, чёткие контуры. */
function houseSvg(o) {
  const { x, y, w, d, h, wall, roof, ridge } = o;
  const z0 = G;
  const zh = z0 + h;
  const south = wall;
  const east = cool(wall, 0.24);
  const e = 0.3;
  const r = Math.min(w, d) * 9 + 6;
  const rand = rng(Math.round(x * 31 + y * 17 + 100));
  const shutter = SHUTTERS[Math.floor(rand() * SHUTTERS.length)];
  const doorColor = DOORS[Math.floor(rand() * DOORS.length)];
  const yS = y + d;
  const xE = x + w;
  const edge = cool(wall, 0.5);
  const wallS = (a0, a1, b0, b1) => [[a0, yS, b0], [a1, yS, b0], [a1, yS, b1], [a0, yS, b1]];
  const wallE = (a0, a1, b0, b1) => [[xE, a0, b0], [xE, a1, b0], [xE, a1, b1], [xE, a0, b1]];
  const parts = [`<defs>
    ${vertical("glass", [[0, PAL.glass[0], 1], [0.55, PAL.glass[1], 1], [1, PAL.glass[2], 1]])}
    ${vertical("wl", [[0, "#fff", 0.2], [1, "#fff", 0]])}
    ${vertical("wr", [[0, "#fff", 0.1], [1, PAL.tint, 0.1]])}
    ${vertical("roofShade", [[0, "#fff", 0.22], [1, "#fff", 0]])}
  </defs>`];
  parts.push(box(x, y, w, d, h, roof, south, east, z0));
  parts.push(ov(wallS(x, xE, z0, zh), "url(#wl)"), ov(wallE(y, yS, z0, zh), "url(#wr)"));
  // цоколь
  parts.push(ov(wallS(x, xE, z0, z0 + 4), cool(wall, 0.12)), ov(wallE(y, yS, z0, z0 + 4), cool(wall, 0.34)));
  // контуры: углы и основание
  parts.push(seg([x, yS, z0], [x, yS, zh], lighten(wall, 0.5), 1.2), seg([xE, yS, z0], [xE, yS, zh], edge, 1.2));
  parts.push(seg([x, yS, z0], [xE, yS, z0], edge, 1), seg([xE, yS, z0], [xE, y, z0], edge, 1));
  // окна на южной и восточной стенах: рама, стекло с бликом, подоконник
  const frame = PAL.frame;
  const sill = (xa, xb, ya, yb, zz) => box(xa, ya, xb - xa, yb - ya, 1.8, "#fffdf6", "#f1e8d6", cool("#f1e8d6", 0.2), zz);
  const nx = Math.max(1, Math.floor(w / 1.7));
  const useShutters = rand() < 0.65;
  for (let i = 0; i < nx; i += 1) {
    const cx = x + ((i + 0.5) * w) / nx;
    const z1 = z0 + h * 0.56;
    const z2 = z0 + h * 0.82;
    if (useShutters) [[cx - 0.56, cx - 0.4], [cx + 0.4, cx + 0.56]].forEach(([a, b]) => parts.push(face(wallS(a, b, z1 - 1, z2 + 2), shutter)));
    parts.push(face(wallS(cx - 0.36, cx + 0.36, z1 - 2, z2 + 2), frame));
    parts.push(ov(wallS(cx - 0.28, cx + 0.28, z1, z2), "url(#glass)"));
    parts.push(ov([[cx - 0.28, yS, z1 + 2], [cx - 0.1, yS, z1 + 2], [cx + 0.1, yS, z2 - 1], [cx - 0.08, yS, z2 - 1]], "#fff", 0.55));
    parts.push(seg([cx, yS, z1], [cx, yS, z2], frame, 1.1), seg([cx - 0.28, yS, (z1 + z2) / 2], [cx + 0.28, yS, (z1 + z2) / 2], frame, 1));
    parts.push(sill(cx - 0.42, cx + 0.42, yS, yS + 0.13, z1 - 3.6));
    if (rand() < 0.3) {
      parts.push(box(cx - 0.38, yS + 0.02, 0.76, 0.16, 3.2, "#e0a96b", "#c98d55", "#a8703f", z1 - 7));
      for (let k = 0; k < 5; k += 1) {
        const [fx, fy] = iso(cx - 0.3 + k * 0.15, yS + 0.1, z1 - 2.6);
        parts.push(`<circle cx="${fx.toFixed(1)}" cy="${(fy - 1).toFixed(1)}" r="1.8" fill="${PAL.bloom[(i + k) % 5]}"/>`);
      }
    }
    parts.push(glow(wallS(cx - 0.28, cx + 0.28, z1, z2)));
  }
  const dx = x + w * 0.5;
  // дверь: наличник, цветное полотно, окошко, ручка, ступень и козырёк
  parts.push(face(wallS(dx - 0.47, dx + 0.47, z0, z0 + h * 0.45), frame));
  parts.push(face(wallS(dx - 0.38, dx + 0.38, z0, z0 + h * 0.42), doorColor));
  parts.push(ov(wallS(dx - 0.3, dx + 0.3, z0 + h * 0.24, z0 + h * 0.38), "url(#glass)", 0.95));
  parts.push(ov(wallS(dx - 0.3, dx + 0.3, z0 + 4, z0 + h * 0.2), cool(doorColor, 0.14)));
  parts.push(`<circle cx="${iso(dx + 0.28, yS, z0 + h * 0.2)[0].toFixed(1)}" cy="${iso(dx + 0.28, yS, z0 + h * 0.2)[1].toFixed(1)}" r="1.1" fill="#ffd45c"/>`);
  parts.push(box(dx - 0.55, yS, 1.1, 0.38, 2.4, "#f4ecdc", "#e4d9c4", cool("#e4d9c4", 0.22), z0));
  parts.push(box(dx - 0.62, yS, 1.24, 0.3, 2, roof, cool(roof, 0.1), cool(roof, 0.28), z0 + h * 0.47));
  // кровля
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  const ny = Math.max(1, Math.floor(d / 1.7));
  for (let i = 0; i < ny; i += 1) {
    const cy = y + ((i + 0.5) * d) / ny;
    const z1 = z0 + h * 0.56;
    const z2 = z0 + h * 0.82;
    parts.push(face(wallE(cy - 0.34, cy + 0.34, z1 - 2, z2 + 2), cool(frame, 0.12)));
    parts.push(ov(wallE(cy - 0.26, cy + 0.26, z1, z2), "url(#glass)"));
    parts.push(ov([[xE, cy - 0.2, z1 + 2], [xE, cy - 0.04, z1 + 2], [xE, cy + 0.12, z2 - 1], [xE, cy - 0.04, z2 - 1]], "#fff", 0.4));
    parts.push(seg([xE, cy, z1], [xE, cy, z2], cool(frame, 0.12), 1.1));
    parts.push(box(xE, cy - 0.38, 0.13, 0.76, 1.8, "#f1e8d6", "#e0d4bc", cool("#e0d4bc", 0.25), z1 - 3.6));
    parts.push(glow(wallE(cy - 0.26, cy + 0.26, z1, z2)));
  }
  const rows = 6;
  const brick = (bx, by, bz) => [
    box(bx, by, 0.5, 0.5, 14, "#f3a07e", "#e0805f", "#b9593f", bz),
    box(bx - 0.05, by - 0.05, 0.6, 0.6, 2.4, "#fdd3bf", "#d98a6c", "#a85840", bz + 14),
  ].join("");
  if (ridge === "x") {
    const ym = y + d / 2;
    const eaveA = [x - e, y + d + e, zh];
    const eaveB = [x + w + e, y + d + e, zh];
    const topA = [x - e, ym, zh + r];
    const topB = [x + w + e, ym, zh + r];
    parts.push(face([[xE, y, zh], [xE, y + d, zh], [xE, ym, zh + r]], east));
    parts.push(ov([[xE, y, zh], [xE, y + d, zh], [xE, ym, zh + r]], "url(#wr)"));
    // круглое чердачное окно в щипце
    const rw = Array.from({ length: 14 }, (_, k) => [xE, ym + Math.cos(k / 14 * Math.PI * 2) * 0.22, zh + r * 0.3 + Math.sin(k / 14 * Math.PI * 2) * 6]);
    parts.push(face(rw, cool(frame, 0.12)), ov(rw.map(([a, b, c]) => [a, ym + (b - ym) * 0.7, zh + r * 0.3 + (c - zh - r * 0.3) * 0.7]), PAL.glass[1]));
    parts.push(face([eaveA, eaveB, topB, topA], roof));
    parts.push(ov([eaveA, eaveB, topB, topA], "url(#roofShade)"));
    const rowLines = [];
    for (let k = 1; k < rows; k += 1) rowLines.push([lerp(eaveA, topA, k / rows), lerp(eaveB, topB, k / rows)]);
    parts.push(lines(rowLines, cool(roof, 0.35), 0.8, 0.3));
    parts.push(face([eaveA, eaveB, [eaveB[0], eaveB[1], zh - 2.2], [eaveA[0], eaveA[1], zh - 2.2]], cool(roof, 0.3)));
    parts.push(seg(eaveA, eaveB, lighten(roof, 0.4), 1));
    parts.push(seg(topA, topB, lighten(roof, 0.45), 2.2));
    parts.push(seg([xE, y, zh], [xE, ym, zh + r], lighten(frame, 0.2), 1.6), seg([xE, y + d, zh], [xE, ym, zh + r], cool(frame, 0.15), 1.6));
    if (o.chimney) {
      const cxp = x + w * 0.7;
      parts.push(brick(cxp, ym + 0.1, zh + r * 0.45));
      parts.push(smokeSvg(cxp + 0.25, ym + 0.35, zh + r * 0.45 + 16.4));
    }
  } else {
    const xm = x + w / 2;
    const eaveA = [xE + e, y - e, zh];
    const eaveB = [xE + e, y + d + e, zh];
    const topA = [xm, y - e, zh + r];
    const topB = [xm, y + d + e, zh + r];
    parts.push(face([[x, y + d, zh], [xE, y + d, zh], [xm, y + d, zh + r]], south));
    parts.push(ov([[x, y + d, zh], [xE, y + d, zh], [xm, y + d, zh + r]], "url(#wl)"));
    const rw = Array.from({ length: 14 }, (_, k) => [xm + Math.cos(k / 14 * Math.PI * 2) * 0.22, y + d, zh + r * 0.3 + Math.sin(k / 14 * Math.PI * 2) * 6]);
    parts.push(face(rw, frame), ov(rw.map(([a, b, c]) => [xm + (a - xm) * 0.7, b, zh + r * 0.3 + (c - zh - r * 0.3) * 0.7]), PAL.glass[1]));
    parts.push(face([eaveA, eaveB, topB, topA], cool(roof, 0.2)));
    parts.push(ov([eaveA, eaveB, topB, topA], "url(#roofShade)"));
    const rowLines = [];
    for (let k = 1; k < rows; k += 1) rowLines.push([lerp(eaveA, topA, k / rows), lerp(eaveB, topB, k / rows)]);
    parts.push(lines(rowLines, cool(roof, 0.5), 0.8, 0.3));
    parts.push(face([eaveA, eaveB, [eaveB[0], eaveB[1], zh - 2.2], [eaveA[0], eaveA[1], zh - 2.2]], cool(roof, 0.42)));
    parts.push(seg(eaveA, eaveB, lighten(roof, 0.3), 1));
    parts.push(seg(topA, topB, lighten(roof, 0.4), 2.2));
    parts.push(seg([x, yS, zh], [xm, yS, zh + r], lighten(frame, 0.2), 1.6), seg([xE, yS, zh], [xm, yS, zh + r], cool(frame, 0.15), 1.6));
    if (o.chimney) {
      parts.push(brick(xm + 0.1, y + d * 0.3, zh + r * 0.45));
      parts.push(smokeSvg(xm + 0.35, y + d * 0.3 + 0.25, zh + r * 0.45 + 16.4));
    }
  }
  return parts.join("");
}
