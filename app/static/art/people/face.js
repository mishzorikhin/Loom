/* Лицо человека (имя personFaceSvg, чтобы не пересекаться с faceSvg(mood) из app.js).
   personFaceSvg(glasses) — глаза с бликами, улыбка, при glasses=true очки. Оттенок кожи и голова лежат в figure.js.
   Менять: размер и положение глаз (cx ±2.3, cy -43.4), улыбку. */
function personFaceSvg(glasses) {
  return `<circle cx="-2.3" cy="-43.4" r="1.25" fill="#fffdf6"/><circle cx="2.3" cy="-43.4" r="1.25" fill="#fffdf6"/>
        <circle cx="-2.3" cy="-43.3" r="0.8" fill="#2b1d14"/><circle cx="2.3" cy="-43.3" r="0.8" fill="#2b1d14"/>
        <circle cx="-2.05" cy="-43.6" r="0.28" fill="#fff"/><circle cx="2.55" cy="-43.6" r="0.28" fill="#fff"/>
        <path d="M -1.7 -39.6 Q 0 -38.4 1.7 -39.6" fill="none" stroke="#a8503f" stroke-width="0.85" stroke-linecap="round"/>
        ${glasses ? `<circle cx="-2.3" cy="-43.4" r="1.9" fill="none" stroke="#2b1d14" stroke-width="0.6"/><circle cx="2.3" cy="-43.4" r="1.9" fill="none" stroke="#2b1d14" stroke-width="0.6"/><path d="M-0.4 -43.5 L0.4 -43.5" stroke="#2b1d14" stroke-width="0.6"/>` : ""}`;
}
