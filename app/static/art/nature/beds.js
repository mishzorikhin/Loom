/* Клумба.
   bedSvg(axis): терракотовый борт и россыпь цветов PAL.bloom; axis "x"|"y" задаёт длинную сторону (1.9 x 0.9 клетки). */

/* Клумба с цветами: невысокий терракотовый борт и россыпь соцветий. */
function bedSvg(axis = "x") {
  const long = axis === "x";
  const w = long ? 1.9 : 0.9;
  const d = long ? 0.9 : 1.9;
  const rand = rng(long ? 5 : 8);
  const parts = [box(-w / 2, -d / 2, w, d, 5, "#8a5f48", PAL.terra.mid, PAL.terra.dark, 0)];
  const pts = [];
  for (let i = 0; i < 24; i += 1) pts.push([(rand() - 0.5) * (w - 0.3), (rand() - 0.5) * (d - 0.3)]);
  pts.sort((a, b) => a[0] + a[1] - b[0] - b[1]);
  pts.forEach(([px, py], i) => {
    const [sx, sy] = iso(px, py, 5.5);
    parts.push(`<path d="M${sx.toFixed(1)} ${sy.toFixed(1)}l0 -3" stroke="#3fa65e" stroke-width="1" stroke-linecap="round"/><circle cx="${sx.toFixed(1)}" cy="${(sy - 4).toFixed(1)}" r="${(1.6 + (i % 3) * 0.4).toFixed(1)}" fill="${PAL.bloom[i % 5]}"/>`);
  });
  return parts.join("");
}
