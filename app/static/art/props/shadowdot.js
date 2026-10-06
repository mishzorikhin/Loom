/* Круглая цветная тень под предметом.
   SHADOW_DOT(id, rx, ry, alpha) — радиальная тень PAL.shadow; используется урной, гидрантом, столбом, фонарём. */

const SHADOW_DOT = (id, rx, ry, a = 0.28) => `<defs>${radial(id, [[0, PAL.shadow, a], [1, PAL.shadow, 0]])}</defs><ellipse cx="4" cy="1.5" rx="${rx}" ry="${ry}" fill="url(#${id})"/>`;
