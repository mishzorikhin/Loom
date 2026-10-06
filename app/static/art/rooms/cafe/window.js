/* Окно кофейни.
   cafeWindowSvg(): окно на задней стене с видом на квартал (цвет неба var(--sky) подставляет сцена), переплёт, подоконник с горшками, полосатый навес. */

/* Окно: за стеклом квартал (дома, крона дерева), блики, переплёт, подоконник с зеленью и полосатый навес. */
function cafeWindowSvg() {
  const x0 = 2.25;
  const x1 = 5.75;
  const y = 0.03;
  const q = (a0, a1, z0, z1, yy = y) => [[a0, yy, z0], [a1, yy, z0], [a1, yy, z1], [a0, yy, z1]];
  const parts = [
    face(q(x0 - 0.12, x1 + 0.12, 28, 80), "#fffaf0"),
    `<polygon points="${q(x0, x1, 33, 76, y + 0.02).map(pt).join(" ")}" style="fill:var(--sky)"/>`,
    ov(q(x0, x1, 33, 76, y + 0.021), "#fff", 0.1),
    // дальний план: дома и крона
    face(q(x0 + 0.1, x0 + 0.9, 33, 49, y + 0.025), "#cfeee0", 0.9),
    face([[x0 + 0.1, y + 0.026, 49], [x0 + 0.9, y + 0.026, 49], [x0 + 0.5, y + 0.026, 54]], "#a9dcc8", 0.9),
    face(q(x0 + 0.9, x0 + 1.9, 33, 43, y + 0.025), "#d9f2e6", 0.9),
    face(q(x0 + 2.0, x0 + 3.1, 33, 52, y + 0.025), "#f8d9c4", 0.85),
    face([[x0 + 2.0, y + 0.026, 52], [x0 + 3.1, y + 0.026, 52], [x0 + 2.55, y + 0.026, 58]], "#e8704f", 0.9),
    face(q(x0 + 3.1, x1, 33, 41, y + 0.025), "#b8ecb0", 0.9),
    `<ellipse cx="${iso(x0 + 3.4, y, 46)[0].toFixed(1)}" cy="${iso(x0 + 3.4, y, 46)[1].toFixed(1)}" rx="12" ry="9" fill="#54b85f" fill-opacity="0.9"/>`,
    `<ellipse cx="${iso(x0 + 1.4, y, 41)[0].toFixed(1)}" cy="${iso(x0 + 1.4, y, 41)[1].toFixed(1)}" rx="9" ry="7" fill="#7bd987" fill-opacity="0.85"/>`,
  ];
  // блики на стекле
  parts.push(ov([[x0 + 0.15, y + 0.03, 34], [x0 + 0.75, y + 0.03, 34], [x0 + 1.5, y + 0.03, 75], [x0 + 0.9, y + 0.03, 75]], "#fff", 0.2));
  parts.push(ov([[x0 + 1.0, y + 0.03, 34], [x0 + 1.3, y + 0.03, 34], [x0 + 2.05, y + 0.03, 75], [x0 + 1.75, y + 0.03, 75]], "#fff", 0.14));
  parts.push(ov(q(x0, x1, 33, 46, y + 0.03), "#fff", 0.16));
  // переплёт
  parts.push(face(q(3.93, 4.07, 33, 76, y + 0.04), "#fffaf0"), face(q(x0, x1, 53.5, 55.5, y + 0.04), "#fffaf0"));
  parts.push(seg([x0, y + 0.05, 76], [x1, y + 0.05, 76], "#fffaf0", 1.4), seg([x0, y + 0.05, 33], [x1, y + 0.05, 33], "#e8d8bc", 1.2));
  // подоконник и зелень на нём
  parts.push(box(x0 - 0.2, 0.02, x1 - x0 + 0.4, 0.2, 3, "#fffaf0", "#ecdcc0", "#d6c4a4", 25));
  [[2.6, "#3fb264"], [3.1, "#52c477"], [5.2, "#3fb264"]].forEach(([px, col]) => {
    parts.push(box(px, 0.04, 0.22, 0.16, 5, "#e0795a", "#c65f43", "#9e4731", 28));
    const [sx, sy] = iso(px + 0.11, 0.12, 33);
    parts.push(`<g transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)})"><ellipse cx="-2" cy="-5" rx="2" ry="5" fill="${col}" transform="rotate(-25 -2 -5)"/><ellipse cx="2" cy="-5" rx="2" ry="5" fill="${shade(col, 0.15)}" transform="rotate(25 2 -5)"/><ellipse cx="0" cy="-6.5" rx="2" ry="5.5" fill="${lighten(col, 0.12)}"/></g>`);
  });
  // навес
  const stripes = 9;
  const sw = (x1 - x0 + 0.4) / stripes;
  for (let i = 0; i < stripes; i += 1) {
    const a = x0 - 0.2 + i * sw;
    const b = a + sw;
    const col = i % 2 ? "#fff6e4" : "#e8704f";
    parts.push(face([[a, y + 0.05, 90], [b, y + 0.05, 90], [b, y + 0.05, 82], [(a + b) / 2, y + 0.05, 77.5], [a, y + 0.05, 82]], col));
    parts.push(ov([[(a + b) / 2, y + 0.05, 77.5], [b, y + 0.05, 82], [b, y + 0.05, 90], [(a + b) / 2, y + 0.05, 90]], "#000", 0.08));
  }
  parts.push(seg([x0 - 0.2, y + 0.05, 90], [x1 + 0.2, y + 0.05, 90], "#c65f43", 1.4));
  return parts.join("");
}
