/* Волосы человека.
   personHair(hair, style) -> {back, front, sheen}: задняя часть (длинные волосы, style 1), передняя (чёлка; пучки, style 2) и блик.
   Параметры: hair — цвет, style — 0 короткие, 1 длинные, 2 пучки. Менять: контуры чёлки (fringe) и форму пучков. */
function personHair(hair, style) {
  const fringe = "M -6.6 -44.2 Q -7.2 -51.8 0 -52 Q 7.2 -51.8 6.6 -44.2 Q 4.6 -48.4 0 -48.2 Q -4.6 -48 -6.6 -44.2 Z";
  const back = style === 1 ? `<path d="M -7.8 -44 Q -8.6 -52 0 -52.4 Q 8.6 -52 7.8 -44 L 7.6 -30.6 Q 0 -28.6 -7.6 -30.6 Z" fill="${hair}"/><path d="M4 -48 Q8 -44 7.4 -31 L 7.6 -30.6 Q8.4 -42 4 -48 Z" fill="#5d62ae" fill-opacity="0.2"/>` : "";
  const front = style === 2
    ? `<circle cx="-4.8" cy="-49" r="4.1" fill="${hair}"/><circle cx="0" cy="-51.4" r="4.7" fill="${hair}"/><circle cx="4.8" cy="-49" r="4.1" fill="${hair}"/><circle cx="3.2" cy="-51.6" r="2.4" fill="#5d62ae" fill-opacity="0.16"/><path d="${fringe}" fill="${hair}"/>`
    : `<path d="${fringe}" fill="${hair}"/>`;
  const sheen = `<path d="M-3.6 -50.2 Q0 -52.4 3.6 -50.2" fill="none" stroke="${lighten(hair, 0.35)}" stroke-width="1" stroke-linecap="round" stroke-opacity="0.65"/>`;
  return { back, front, sheen };
}
