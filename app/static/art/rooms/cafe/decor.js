/* Декор стен кофейни.
   cafeDecorSvg(): полка с посудой, рамки, доска меню, часы; основа wallDecorSvg() из app.js плюс блики и тени под рамками. */

/* Рамки, доска меню, полка. Старый рисунок плюс блики на стекле, тени под рамками и часы. */
function cafeDecorSvg() {
  const parts = [wallDecorSvg()];
  const bq = (a0, a1, z0, z1) => [[a0, 0.045, z0], [a1, 0.045, z0], [a1, 0.045, z1], [a0, 0.045, z1]];
  const lq = (a0, a1, z0, z1) => [[0.045, a0, z0], [0.045, a1, z0], [0.045, a1, z1], [0.045, a0, z1]];
  parts.push(ov([[6.3, 0.05, 74], [6.62, 0.05, 74], [6.86, 0.05, 56], [6.5, 0.05, 56]], "#fff", 0.14));
  parts.push(ov([[0.047, 1.32, 72], [0.047, 1.7, 72], [0.047, 2.0, 52], [0.047, 1.62, 52]], "#fff", 0.14));
  // тень под рамкой и доской
  parts.push(ov(bq(6.2, 7.1, 47, 50), "#000", 0.06), ov(lq(1.2, 2.6, 43, 46), "#000", 0.06), ov(lq(3.3, 4.3, 49, 52), "#000", 0.08));
  // часы над дверью в левой стене
  const [cx, cy] = iso(0.05, 6.0, 84);
  parts.push(`<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="8" fill="#d89a5b"/><circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="6.6" fill="#fbf1df"/><circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="6.6" fill="none" stroke="#e2d2b3" stroke-width="0.6"/>
    <path d="M${cx.toFixed(1)} ${cy.toFixed(1)} L${(cx + 1.6).toFixed(1)} ${(cy - 3.6).toFixed(1)} M${cx.toFixed(1)} ${cy.toFixed(1)} L${(cx - 3).toFixed(1)} ${(cy - 2.2).toFixed(1)}" stroke="#2b1d14" stroke-width="1" stroke-linecap="round"/><circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="0.9" fill="#e8704f"/>`);
  return parts.join("");
}
