/* Серверная стойка.
   dcRackSvg(x, y): корпус 1.1 x 1.1 x 46, девять юнитов со светодиодами DC_LED и мягким свечением, вентиляционные решётки.
   Стоит на месте стола (TABLES) в зале ЦОДа. */

function dcRackSvg(x, y) {
  const parts = [box(x, y, 1.1, 1.1, 46, "#44526a", "#34405a", "#2a3550")];
  const q = (a0, a1, z0, z1) => [[x + a0, y + 1.1, z0], [x + a1, y + 1.1, z0], [x + a1, y + 1.1, z1], [x + a0, y + 1.1, z1]];
  parts.push(ov(q(0, 1.1, 0, 46), "#4a5873", 0.35));
  parts.push(ov(q(0.06, 1.04, 2, 44), "#222b3d", 0.7));
  const glows = [];
  for (let k = 0; k < 9; k += 1) {
    const z = 4 + k * 4.6;
    parts.push(face(q(0.1, 1.0, z, z + 3.6), "#4a5873"));
    parts.push(lines([[[x + 0.12, y + 1.1, z + 0.4], [x + 0.98, y + 1.1, z + 0.4]]], "#8d9ab3", 0.6, 0.6));
    // решётка вентиляции справа
    parts.push(lines([0, 1, 2].map((v) => [[x + 0.62, y + 1.1, z + 0.9 + v * 0.8], [x + 0.95, y + 1.1, z + 0.9 + v * 0.8]]), "#34405a", 0.6, 0.8));
    for (let led = 0; led < 3; led += 1) {
      const c = DC_LED[(k + led * 2 + Math.round(x * 3)) % DC_LED.length];
      const a = x + 0.18 + led * 0.14;
      glows.push(ov([[a - 0.03, y + 1.1, z + 0.9], [a + 0.11, y + 1.1, z + 0.9], [a + 0.11, y + 1.1, z + 2.9], [a - 0.03, y + 1.1, z + 2.9]], c, 0.22));
      parts.push(face([[a, y + 1.13, z + 1.2], [a + 0.08, y + 1.13, z + 1.2], [a + 0.08, y + 1.13, z + 2.2], [a, y + 1.13, z + 2.2]], c));
    }
  }
  parts.push(`<defs>${BLUR("lb", 1.6)}</defs><g filter="url(#lb)">${glows.join("")}</g>`);
  parts.push(box(x + 0.02, y + 1.1, 0.06, 0.04, 40, "#9aa8c0", "#7d8aa3", "#667390", 3));
  parts.push(seg([x + 1.1, y + 0.2, 40], [x + 1.1, y + 1.0, 40], "#7ff5ee", 1));
  parts.push(box(x + 0.15, y + 0.3, 0.8, 0.5, 2, "#34405a", "#2a3550", "#222b3d", 46));
  return parts.join("");
}
