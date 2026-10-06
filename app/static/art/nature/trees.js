/* Деревья четырёх видов.
   treeSvg(s, delay, v): v=0 лиственное, 1 ель, 2 светлая крона, 3 цветущее. Крона лежит в группе class="sway" — Phaser качает её отдельно.
   foliage(blobs, light, mid, dark, seed, extra) — три плоских прохода по пятнам [cx, cy, rx, ry]; trunkSvg(h, цвет, тень) — ствол.
   Цвета: PAL.leaf, PAL.pine, PAL.trunk. Вид по месту выбирает treeKind (layout.js). */

/* ---------- деревья, кусты, камни ---------- */

const TREE_SHADOW = `<defs>${radial("ts", [[0, PAL.shadow, 0.34], [0.65, PAL.shadow, 0.18], [1, PAL.shadow, 0]])}</defs>`;

/* Листва: три плоских прохода по одним и тем же пятнам. Тёмный даёт силуэт, средний сдвинут к свету, светлый
   лежит на верхнем левом краю. Рисуется в группе .sway. */
function foliage(blobs, light, mid, dark, seed, extra = "") {
  const parts = [];
  const sorted = blobs.slice().sort((a, b) => b[1] - a[1]);
  sorted.forEach(([cx, cy, rx, ry]) => parts.push(`<ellipse cx="${cx + 0.8}" cy="${cy + 1.4}" rx="${rx + 0.6}" ry="${ry + 0.6}" fill="${dark}"/>`));
  sorted.forEach(([cx, cy, rx, ry]) => parts.push(`<ellipse cx="${cx - 1.2}" cy="${cy - 1.8}" rx="${rx * 0.93}" ry="${ry * 0.9}" fill="${mid}"/>`));
  sorted.forEach(([cx, cy, rx, ry]) => parts.push(`<ellipse cx="${(cx - rx * 0.28).toFixed(1)}" cy="${(cy - ry * 0.38).toFixed(1)}" rx="${(rx * 0.52).toFixed(1)}" ry="${(ry * 0.44).toFixed(1)}" fill="${light}"/>`));
  parts.push(extra);
  return parts.join("");
}

function trunkSvg(h, col = PAL.trunk[0], dark = PAL.trunk[1]) {
  return `<path d="M-3.2 2 Q-1.6 -2 -2 -${h * 0.4} L-1.7 -${h} L1.8 -${h} L2.2 -${h * 0.4} Q2.2 -2 4 2 Z" fill="${col}"/>
    <path d="M0.4 -${h} L1.8 -${h} L2.2 -${h * 0.4} Q2.2 -2 4 2 L0.8 2 Q1.4 -${h * 0.4} 0.4 -${h} Z" fill="${dark}"/>`;
}

function treeSvg(s = 1, delay = 0, v = 0) {
  const sh = `<ellipse cx="9" cy="5" rx="25" ry="8" fill="url(#ts)"/>`;
  const L = PAL.leaf;
  if (v === 1) {
    // ель: ярусы хвои, левая половина светлее
    const tiers = [[0, -20, 15, 15], [0, -32, 12.5, 14], [0, -43, 9.5, 13], [0, -53, 6, 11]];
    const base = (cx, cy, rw, hh) => `${cx - rw} ${cy + hh * 0.45} Q${cx} ${cy + hh * 0.7} ${cx + rw} ${cy + hh * 0.45}`;
    const full = (cx, cy, rw, hh, fill) => `<path d="M${base(cx, cy, rw, hh)} L${cx} ${cy - hh} Z" fill="${fill}"/>`;
    const half = (cx, cy, rw, hh, fill) => `<path d="M${cx - rw} ${cy + hh * 0.45} Q${cx - rw / 2} ${cy + hh * 0.62} ${cx} ${cy + hh * 0.62} L${cx} ${cy - hh} Z" fill="${fill}"/>`;
    return `${TREE_SHADOW}${sh}${trunkSvg(14)}
      <g class="sway" style="animation-delay:-${delay.toFixed(1)}s">
      ${tiers.map(([cx, cy, rw, hh]) => full(cx, cy, rw, hh, PAL.pine.dark)).join("")}
      ${tiers.map(([cx, cy, rw, hh]) => half(cx, cy, rw, hh, PAL.pine.light)).join("")}</g>`;
  }
  if (v === 2) {
    // светлая крона с жёлто-зелёным тоном
    return `${TREE_SHADOW}${sh}${trunkSvg(26, "#f4efe4", "#d7cfbf")}
      <g class="sway" style="animation-delay:-${delay.toFixed(1)}s">${foliage([[-6, -36, 10, 12], [7, -38, 9, 11], [0, -46, 9, 10], [-2, -29, 11, 8], [8, -28, 7, 7]], "#e4f7a8", "#a9e070", "#5fbd5c", 41)}</g>`;
  }
  if (v === 3) {
    // цветущее дерево: зелёная крона с розовыми лепестками
    const petals = Array.from({ length: 22 }, (_, i) => {
      const a = i * 2.4;
      const rr = 6 + (i * 7 % 13);
      return `<circle cx="${(Math.cos(a) * rr * 1.2).toFixed(1)}" cy="${(-33 + Math.sin(a) * rr * 0.95).toFixed(1)}" r="${(1.8 + (i % 3) * 0.5).toFixed(1)}" fill="${i % 3 ? "#ff9db0" : "#ffd3dc"}"/>`;
    }).join("");
    return `${TREE_SHADOW}${sh}${trunkSvg(20)}
      <g class="sway" style="animation-delay:-${delay.toFixed(1)}s">${foliage([[-8, -30, 11, 11], [8, -31, 11, 11], [0, -39, 12, 11], [0, -25, 14, 8]], "#b5ec92", "#66c36f", "#36985a", 53, petals)}</g>`;
  }
  return `${TREE_SHADOW}${sh}${trunkSvg(19)}
    <g class="sway" style="animation-delay:-${delay.toFixed(1)}s">${foliage([[-7, -33, 12, 12], [8, -30, 11, 11], [0, -42, 13, 12], [-1, -26, 15, 9]], L.light, L.mid, L.dark, 17)}</g>`;
}
