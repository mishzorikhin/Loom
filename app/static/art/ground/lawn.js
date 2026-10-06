/* Газон.
   lawnSvg() — базовая трава и крупные плитки трёх близких тонов PAL.grass (скошенная трава на макете) и редкие цветы PAL.bloom.
   Никакого зерна: менять тона в палитре, шаг клетки (4) и плотность цветов (0.16) здесь. */

function lawnSvg() {
  const out = [`<rect x="-6000" y="-4000" width="12000" height="9000" fill="${GRASS}"/>`];
  const rand = rng(21);
  for (let i = -8; i < 10; i += 1) {
    for (let j = -8; j < 10; j += 1) {
      const tone = PAL.grass[(i + j * 2 + 40) % 3];
      out.push(gface(i * 4, j * 4, i * 4 + 4, j * 4 + 4, tone));
    }
  }
  // редкие цветы на траве: чистые кружки без пятен
  const bloom = [];
  for (let i = 0; i < 700; i += 1) {
    const x = -31 + rand() * 70;
    const y = -31 + rand() * 72;
    if (!onGrass(x, y, 0.4) || rand() > 0.16) continue;
    const [sx, sy] = iso(x, y, G);
    bloom.push(`<circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="1.7" fill="${PAL.bloom[i % 5]}"/><circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="0.6" fill="#fff" fill-opacity="0.8"/>`);
  }
  out.push(bloom.join(""));
  return out.join("");
}
