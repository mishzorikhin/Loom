/* Земля целиком.
   landSvg() собирает один большой рисунок земли в порядке слоёв: газон, кромки и плиты тротуаров, дороги, бордюры, разметка, тропинки.
   Phaser режет его на плитки разной чёткости (landObject в phaser-world.js). Отдельные части лежат в lawn.js, paving.js, roads.js, zebra.js. */

function landSvg() {
  const out = [lawnSvg()];
  out.push(pavementEdges(SIDEWALKS));
  out.push(pavingSvg(SIDEWALKS));
  out.push(roadSurfaceSvg());
  out.push(kerbSvg());
  out.push(laneMarkingsSvg());
  out.push(kerbHighlightSvg());
  // тропинки от тротуара к соседним домам: светлая плитка
  [[-6.5, 3.2, -3.5, 4.6], [-6.5, 9, -3.5, 10.2], [0.6, -6.5, 1.8, -3.5], [6.2, -6.5, 7.4, -3.5]].forEach(([x0, y0, x1, y1]) => {
    out.push(gface(x0, y0, x1, y1, "#f3e6c8", 1, 0.2));
  });
  return out.join("");
}
