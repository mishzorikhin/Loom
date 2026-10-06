/* Тени мебели на полу кофейни.
   cafeShadowsSvg(): мягкие цветные тени стойки, стола, столов, стульев и растений (размытая группа softFloorShadows). */

function cafeShadowsSvg() {
  const polys = [[[2.05, 0.78], [6.6, 0.78], [6.6, 2.7], [2.05, 2.7]], [[0.35, 1.0], [1.3, 1.0], [1.3, 2.7], [0.35, 2.7]]];
  TABLES.forEach((t) => {
    polys.push([[t.x + 0.15, t.y + 0.2], [t.x + 1.35, t.y + 0.2], [t.x + 1.35, t.y + 1.4], [t.x + 0.15, t.y + 1.4]]);
  });
  SEATS.forEach((seat) => polys.push([[seat.at[0] - 0.22, seat.at[1] - 0.22], [seat.at[0] + 0.32, seat.at[1] - 0.22], [seat.at[0] + 0.32, seat.at[1] + 0.32], [seat.at[0] - 0.22, seat.at[1] + 0.32]]));
  [[0.4, 0.4], [7.3, 7.1]].forEach(([x, y]) => polys.push([[x - 0.05, y], [x + 0.55, y], [x + 0.55, y + 0.6], [x - 0.05, y + 0.6]]));
  return softFloorShadows(polys, 0.18);
}
