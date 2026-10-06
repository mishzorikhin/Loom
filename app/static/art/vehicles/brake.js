/* Стоп-сигналы.
   carBrakeSvg(car) — яркие красные огни кормы поверх обычных фонарей (те же места, что в cars.js); Phaser показывает их,
   когда машина тормозит (флаг кадра города) и корма видна. */

function carBrakeSvg(car) {
  const k = CAR_KINDS[car.kind], hw = k.W / 2, B = k.body;
  const P = (u, v, z) => car.axis === "x" ? [u * car.dir, v, z] : [v, u * car.dir, z];
  const u = -k.L / 2 - 0.006;
  return `<g transform="translate(0 ${-G})">${[[0.3, hw - 0.08], [-hw + 0.08, -0.3]].map(([v0, v1]) => {
    const [gx, gy] = iso(...P(u, (v0 + v1) / 2, B - 3.4));
    return face([P(u, v0, B - 5.2), P(u, v1, B - 5.2), P(u, v1, B - 1.6), P(u, v0, B - 1.6)], "#ff2a1a")
      + `<ellipse cx="${gx.toFixed(1)}" cy="${gy.toFixed(1)}" rx="7" ry="4.5" fill="#ff4a3a" fill-opacity="0.35"/>`;
  }).join("")}</g>`;
}
