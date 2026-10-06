/* Стул кофейни.
   cafeChairSvg(x, y, side): деревянный стул с мятной подушкой; side "n" — спинка у северного края, иначе у западного. */

function cafeChairSvg(x, y, side) {
  const s = 0.5;
  const x0 = x - s / 2;
  const y0 = y - s / 2;
  const parts = [];
  [[0, 0], [s - 0.07, 0], [0, s - 0.07], [s - 0.07, s - 0.07]].forEach(([dx, dy]) => {
    parts.push(box(x0 + dx, y0 + dy, 0.07, 0.07, 7, "#ee8a69", "#a9703f", "#8a5a2d"));
  });
  parts.push(box(x0, y0, s, s, 2.4, "#f0bd82", "#d89a5b", "#b97f47", 7));
  parts.push(box(x0 + 0.04, y0 + 0.04, s - 0.08, s - 0.08, 1.4, "#7fd9bd", "#5fc4a6", "#46a68a", 9.4));
  const back = (a, b, c, d, z0, z1) => box(a, b, c, d, z1 - z0, "#ffb597", "#d89a5b", "#b97f47", z0);
  const slat = (cx, cy, horizontal, z0, z1) => horizontal
    ? box(cx - 0.05, cy - 0.04, 0.1, 0.08, z1 - z0, "#e0a96b", "#c98d55", "#a9703f", z0)
    : box(cx - 0.04, cy - 0.05, 0.08, 0.1, z1 - z0, "#e0a96b", "#c98d55", "#a9703f", z0);
  if (side === "n") {
    [0.08, 0.25, 0.42].forEach((a) => parts.push(slat(x0 + a, y0 - 0.02, true, 10, 27)));
    parts.push(back(x0, y0 - 0.02, s, 0.07, 27, 31));
  } else {
    [0.08, 0.25, 0.42].forEach((a) => parts.push(slat(x0 - 0.02, y0 + a, false, 10, 27)));
    parts.push(back(x0 - 0.02, y0, 0.07, s, 27, 31));
  }
  return parts.join("");
}
