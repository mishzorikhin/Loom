/* Ковёр кофейни.
   cafeRugSvg(): мятный ковёр с кремовой каймой, ромбами и бахромой; координаты x0..x1, y0..y1 задают размер. */

/* Ковёр: бирюзовый борт, кремовая кайма, ромбы и бахрома по коротким краям. */
function cafeRugSvg() {
  const x0 = 2.4;
  const x1 = 5.9;
  const y0 = 1.95;
  const y1 = 3.2;
  const f = (a, b, c, d, z, fill, al) => face([[a, b, z], [c, b, z], [c, d, z], [a, d, z]], fill, al);
  const out = [ov([[x0 - 0.05, y0 - 0.05, 0.15], [x1 + 0.1, y0 - 0.05, 0.15], [x1 + 0.1, y1 + 0.08, 0.15], [x0 - 0.05, y1 + 0.08, 0.15]], PAL.shadowWarm, 0.14),
    f(x0, y0, x1, y1, 0.2, "#4fb59c"), f(x0 + 0.12, y0 + 0.12, x1 - 0.12, y1 - 0.12, 0.3, "#fff1d2"), f(x0 + 0.28, y0 + 0.28, x1 - 0.28, y1 - 0.28, 0.4, "#6fcdb0")];
  const diamonds = [];
  for (let x = x0 + 0.55; x < x1 - 0.4; x += 0.5) {
    const yc = (y0 + y1) / 2;
    diamonds.push(ov([[x, yc - 0.1, 0.45], [x + 0.14, yc, 0.45], [x, yc + 0.1, 0.45], [x - 0.14, yc, 0.45]], "#fff1d2", 0.7));
    diamonds.push(ov([[x + 0.25, yc - 0.06, 0.45], [x + 0.33, yc, 0.45], [x + 0.25, yc + 0.06, 0.45], [x + 0.17, yc, 0.45]], "#4fb59c", 0.8));
  }
  out.push(diamonds.join(""));
  const tassels = [];
  for (let t = y0 + 0.08; t < y1; t += 0.12) tassels.push([[x0, t, 0.2], [x0 - 0.16, t, 0.2]], [[x1, t, 0.2], [x1 + 0.16, t, 0.2]]);
  out.push(lines(tassels, "#fff4d8", 0.8, 0.9));
  out.push(lines([[[x0 + 0.2, y0 + 0.2, 0.42], [x1 - 0.2, y0 + 0.2, 0.42]]], "#fff", 0.8, 0.2));
  return out.join("");
}
