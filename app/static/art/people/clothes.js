/* Одежда: рисунок верха.
   personTorso(kind, shirt, skinS) — деталь футболки (kind 0 круглый ворот, 1 куртка на молнии, 2 полосы, 3 рубашка с воротником,
   4 худи, 5 рюкзак); personApron(accent) — фартук бариста с цветным платком. Цвета берутся из shirt (shade/lighten), яркость рубашки
   задаёт список SHIRTS в app.js. Чтобы добавить фасон: допиши элемент в details и увеличь `h % 6` в figure.js. */
function personTorso(kind, shirt, skinS) {
  const dark = shade(shirt, 0.3);
  const details = [
    // 0: футболка с круглым воротом
    `<path d="M-3 -35.4 Q0 -31.4 3 -35.4" fill="${skinS}"/><path d="M-3.4 -35.4 Q0 -30.6 3.4 -35.4" fill="none" stroke="${lighten(shirt, 0.3)}" stroke-width="0.9"/>`,
    // 1: куртка на молнии
    `<path d="M0 -35 L0 -13.8" stroke="${dark}" stroke-width="0.9"/><path d="M-3.2 -35.4 L0 -29 L3.2 -35.4" fill="none" stroke="${dark}" stroke-width="0.9"/><path d="M-5 -19 L-2 -19 M2 -19 L5 -19" stroke="${dark}" stroke-width="0.8" stroke-linecap="round"/>`,
    // 2: полосы
    [-30, -26, -22, -18].map((y) => `<path d="M-6.2 ${y} L6.2 ${y}" stroke="${lighten(shirt, 0.5)}" stroke-width="1.4" stroke-opacity="0.5"/>`).join("") + `<path d="M-3 -35.4 Q0 -32 3 -35.4" fill="${skinS}"/>`,
    // 3: рубашка с воротником и пуговицами
    `<path d="M-3.4 -35.6 L0 -31 L3.4 -35.6 L2.2 -36.4 L0 -34 L-2.2 -36.4 Z" fill="${lighten(shirt, 0.55)}"/><path d="M0 -31 L0 -14" stroke="${lighten(shirt, 0.25)}" stroke-width="0.7"/>${[-27, -23, -19].map((y) => `<circle cx="0.5" cy="${y}" r="0.6" fill="${lighten(shirt, 0.6)}"/>`).join("")}`,
    // 4: худи с капюшоном и карманом
    `<path d="M-5 -35.6 Q0 -30 5 -35.6 Q6.6 -37.6 0 -38 Q-6.6 -37.6 -5 -35.6 Z" fill="${shade(shirt, 0.18)}"/><path d="M-4.6 -21 L4.6 -21 L5.4 -14.4 L-5.4 -14.4 Z" fill="${shade(shirt, 0.1)}" fill-opacity="0.8"/><path d="M-1.4 -35 L-1.6 -28 M1.4 -35 L1.6 -28" stroke="${lighten(shirt, 0.4)}" stroke-width="0.7"/>`,
    // 5: лямки рюкзака
    `<path d="M-3 -35.4 Q0 -32 3 -35.4" fill="${skinS}"/><path d="M-3.8 -35 L-4.2 -15 M3.8 -35 L4.2 -15" stroke="#4a3a2c" stroke-width="1.6" stroke-linecap="round"/><rect x="-4.9" y="-26.6" width="1.6" height="1.2" fill="#c9b89a"/><rect x="3.3" y="-26.6" width="1.6" height="1.2" fill="#c9b89a"/>`,
  ];
  return details[kind];
}

function personApron(accent) {
  return `<path d="M -5 -33 L 5 -33 L 5.8 -9.5 L -5.8 -9.5 Z" fill="#f6efe2"/><path d="M0.4 -33 L5 -33 L5.8 -9.5 L0.4 -9.5 Z" fill="#5d62ae" fill-opacity="0.1"/>
       <path d="M-4.2 -33 L-2.8 -36.4 M4.2 -33 L2.8 -36.4" stroke="#e8dcc4" stroke-width="1"/>
       <rect x="-2.6" y="-22" width="5.2" height="4" rx="1" fill="none" stroke="#cdbf9f" stroke-width="0.7"/>
       <path d="M-5.6 -16.4 L5.6 -16.4" stroke="#d9cdb2" stroke-width="0.8"/>
       <path d="M -3.6 -35.6 L 3.6 -35.6 L 0 -30.4 Z" fill="${accent}"/>`;
}
