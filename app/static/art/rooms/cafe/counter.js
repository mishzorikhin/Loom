/* Стойка кофейни.
   cafeCounterSvg(): терракотовая стойка с филёнками, кофемашина, кассовый аппарат, чашки, банка для чаевых, витрина с булочкой. Размер 3.9 x 0.92 клетки, высота 28. */

function cafeCounterSvg() {
  const x = 2.05;
  const y = 0.78;
  const w = 3.9;
  const d = 0.92;
  const h = 28;
  const parts = [box(x, y, w, d, h, "#fbe9c8", "#e0795a", "#b85a40")];
  // фасад: филёнки с рамкой, цоколь, латунная подножка
  for (let i = 0; i < 6; i += 1) {
    const a = x + 0.1 + i * (w - 0.2) / 6;
    const b = a + (w - 0.2) / 6 - 0.1;
    parts.push(ov([[a, y + d, 6], [b, y + d, 6], [b, y + d, h - 4], [a, y + d, h - 4]], "#b85a40", 0.5));
    parts.push(ov([[a + 0.05, y + d, 7.2], [b - 0.05, y + d, 7.2], [b - 0.05, y + d, h - 5.2], [a + 0.05, y + d, h - 5.2]], "#ee8a69", 0.55));
    parts.push(lines([[[a, y + d, h - 4], [b, y + d, h - 4]], [[a, y + d, h - 4], [a, y + d, 6]]], "#ffb597", 0.8, 0.6));
  }
  parts.push(face([[x, y + d + 0.01, 0], [x + w, y + d + 0.01, 0], [x + w, y + d + 0.01, 3], [x, y + d + 0.01, 3]], "#9e4731"));
  parts.push(seg([x + 0.05, y + d + 0.1, 5], [x + w - 0.05, y + d + 0.1, 5], "#d9b04a", 1.6), seg([x + 0.05, y + d + 0.1, 5.8], [x + w - 0.05, y + d + 0.1, 5.8], "#fff0b8", 0.7));
  parts.push(seg([x, y + d, h], [x + w, y + d, h], "#fff3d6", 1.6));
  parts.push(ov([[x, y, h], [x + w, y, h], [x + w, y + 0.18, h], [x, y + 0.18, h]], "#fff", 0.28));
  // кофемашина
  const mx = 3.68;
  const my = 0.92;
  parts.push(box(mx, my, 0.74, 0.58, 22, "#f1f5fa", "#7d8aa3", "#59667d", h));
  parts.push(box(mx - 0.02, my - 0.02, 0.78, 0.62, 3, "#dbe2ec", "#59667d", "#44506a", h + 19));
  const sw = (a0, a1, z0, z1, c) => face([[mx + a0, my + 0.59, h + z0], [mx + a1, my + 0.59, h + z0], [mx + a1, my + 0.59, h + z1], [mx + a0, my + 0.59, h + z1]], c);
  parts.push(sw(0.06, 0.68, 14, 19, "#ee9a5b"));
  parts.push(sw(0.06, 0.68, 10, 13.4, "#3b475f"));
  parts.push(sw(0.12, 0.2, 7.4, 9.2, "#3b475f"), sw(0.54, 0.62, 7.4, 9.2, "#3b475f"));
  [0.2, 0.37, 0.54].forEach((a, i) => parts.push(box(mx + a - 0.02, my + 0.6, 0.12, 0.1, 2.4, "#3b475f", "#2f3a50", "#222b3d", h + 8.4)));
  parts.push(box(mx + 0.08, my + 0.6, 0.58, 0.14, 1.2, "#6b7891", "#3b475f", "#34405a", h + 2));
  parts.push(sw(0.1, 0.64, 3, 5, "#3b475f"));
  parts.push(lines(Array.from({ length: 7 }, (_, i) => [[mx + 0.12 + i * 0.075, my + 0.6, h + 3.4], [mx + 0.12 + i * 0.075, my + 0.6, h + 4.8]]), "#8d9ab3", 0.7, 0.9));
  parts.push(sw(0.5, 0.6, 15.4, 18, "#f0a73a"), sw(0.08, 0.18, 15.4, 18, "#7fe3a2"));
  // кофемолка рядом
  parts.push(box(mx + 0.82, my + 0.08, 0.3, 0.3, 11, "#59667d", "#44506a", "#34405a", h));
  parts.push(`<path d="${(() => { const [a, b] = iso(mx + 0.97, my + 0.23, h + 11); return `M${a - 7} ${b} L${a - 4} ${b - 8} L${a + 4} ${b - 8} L${a + 7} ${b} Z`; })()}" fill="#c9b89a" fill-opacity="0.9"/>`);
  // кассовый аппарат
  parts.push(box(5.42, 1.06, 0.42, 0.36, 7, "#7b88a0", "#59667d", "#44506a", h));
  parts.push(box(5.46, 1.1, 0.34, 0.06, 7, "#4a5873", "#34405a", "#34405a", h + 7));
  parts.push(face([[5.47, 1.17, h + 9], [5.79, 1.17, h + 9], [5.79, 1.17, h + 13], [5.47, 1.17, h + 13]], "#8fd7c8", 0.8));
  parts.push(lines([[[5.48, 1.45, h + 3], [5.78, 1.45, h + 3]], [[5.48, 1.45, h + 5], [5.78, 1.45, h + 5]]], "#e3e9f2", 0.8, 0.8));
  // чашки в ряд, стопка у кассы
  parts.push(box(3.05, 1.12, 0.18, 0.18, 5, "#b97f47", "#fffaf0", "#d8cdb8", h), box(3.32, 1.28, 0.18, 0.18, 5, "#b97f47", "#fffaf0", "#d8cdb8", h));
  parts.push(box(2.55, 1.28, 0.16, 0.16, 3, "#fffaf0", "#efe6d4", "#d8cdb8", h), box(2.55, 1.28, 0.16, 0.16, 3, "#fffaf0", "#efe6d4", "#d8cdb8", h + 3));
  // банка для чаевых
  const [jx, jy] = iso(5.2, 1.5, h + 1);
  parts.push(`<ellipse cx="${jx.toFixed(1)}" cy="${(jy - 3).toFixed(1)}" rx="2.6" ry="1.6" fill="#d9f1fb" fill-opacity="0.7"/><rect x="${(jx - 2.6).toFixed(1)}" y="${(jy - 6).toFixed(1)}" width="5.2" height="5" rx="1.4" fill="#d9f1fb" fill-opacity="0.55" stroke="#fff" stroke-opacity="0.7" stroke-width="0.6"/><ellipse cx="${jx.toFixed(1)}" cy="${(jy - 1.6).toFixed(1)}" rx="2" ry="1" fill="#f0c35a"/>`);
  // витрина с булочкой
  parts.push(box(4.62, 1.14, 0.46, 0.4, 2, "#fffaf0", "#e8e0cf", "#cfc4ae", h));
  const [bx, by] = iso(4.85, 1.34, h + 2);
  parts.push(`<ellipse cx="${bx.toFixed(1)}" cy="${(by - 3).toFixed(1)}" rx="5.2" ry="3" fill="#ee9a5b"/><ellipse cx="${(bx - 1.5).toFixed(1)}" cy="${(by - 4.2).toFixed(1)}" rx="2" ry="1" fill="#e8b878"/><circle cx="${(bx + 1.2).toFixed(1)}" cy="${(by - 4.4).toFixed(1)}" r="0.6" fill="#f6e2c0"/>`);
  parts.push(`<path d="M ${(bx - 9).toFixed(1)} ${by.toFixed(1)} A 9 11 0 0 1 ${(bx + 9).toFixed(1)} ${by.toFixed(1)} Z" fill="#d9f1fb" fill-opacity="0.45" stroke="#ffffff" stroke-opacity="0.65" stroke-width="0.8"/><path d="M ${(bx - 6).toFixed(1)} ${(by - 2).toFixed(1)} Q ${(bx - 5).toFixed(1)} ${(by - 8).toFixed(1)} ${(bx - 1).toFixed(1)} ${(by - 9.4).toFixed(1)}" fill="none" stroke="#fff" stroke-width="1.1" stroke-linecap="round" stroke-opacity="0.8"/>`);
  return parts.join("");
}
