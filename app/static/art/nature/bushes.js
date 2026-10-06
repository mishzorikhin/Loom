/* Куст.
   bushSvg(s, v): три пятна листвы через foliage(); v=1 — с цветами PAL.bloom. */

function bushSvg(s = 1, v = 0) {
  const flowers = v === 1
    ? Array.from({ length: 9 }, (_, i) => `<circle cx="${(Math.cos(i * 2.1) * 9).toFixed(1)}" cy="${(-8 + Math.sin(i * 2.7) * 5).toFixed(1)}" r="1.8" fill="${PAL.bloom[i % 5]}"/>`).join("")
    : "";
  return `<defs>${radial("bsh", [[0, PAL.shadow, 0.3], [1, PAL.shadow, 0]])}</defs>
    <ellipse cx="6" cy="2" rx="17" ry="5.5" fill="url(#bsh)"/>
    ${foliage([[-5.5, -5, 8, 6.5], [6, -5.5, 8, 7], [0, -9, 9, 7.5]], PAL.leaf.light, PAL.leaf.mid, PAL.leaf.dark, 3)}${flowers}`;
}
