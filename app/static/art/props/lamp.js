/* Фонарь.
   lampSvg(): графитовая колонна и тёплая лампа; ночное свечение рисует Phaser (scene.glows/halos в phaser-world.js). */

/* Фонарь: графитовая колонна, изогнутый вынос и тёплая лампа. Свечение рисует сцена отдельными объектами. */
function lampSvg() {
  return `${SHADOW_DOT("lsh", 10, 3.2)}
    <path d="M-4 1 L-3 -5 L3 -5 L4 1 Z" fill="${PAL.metal[1]}"/><rect x="-3.4" y="-6.4" width="6.8" height="2" rx="1" fill="${PAL.metal[2]}"/>
    <path d="M-1.5 -6 L-1.1 -47 L1.1 -47 L1.5 -6 Z" fill="${PAL.metal[2]}"/><path d="M0.2 -6 L1.1 -47 L1.5 -6 Z" fill="${PAL.metal[0]}"/>
    <path d="M0 -47 Q0 -52 5 -52" fill="none" stroke="${PAL.metal[2]}" stroke-width="2" stroke-linecap="round"/>
    <path d="M-3 -52 L8 -52 L6.4 -49 L-1.4 -49 Z" fill="${PAL.metal[0]}"/>
    <rect x="-1.6" y="-49.2" width="7.2" height="4.6" rx="1.4" fill="#fff2bf"/><rect x="3" y="-49.2" width="2.6" height="4.6" rx="1.2" fill="#ffe08a"/>
    <path d="M-2.4 -45 L7.2 -45 L6 -43.6 L-1.2 -43.6 Z" fill="${PAL.metal[0]}"/>`;
}
