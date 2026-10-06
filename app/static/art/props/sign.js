/* Табличка улицы.
   signSvg(): столб с синей табличкой. */

/* Столб с табличкой названия улицы. */
function signSvg() {
  return `${SHADOW_DOT("sgsh", 7, 2.4, 0.24)}
    <rect x="-1.1" y="-42" width="2.2" height="43" rx="1" fill="${PAL.metal[2]}"/><rect x="0.2" y="-42" width="0.9" height="43" fill="${PAL.metal[0]}"/>
    <path d="M-13 -42 L9 -45.6 L9 -39 L-13 -35.4 Z" fill="#3d9be0"/><path d="M-13 -42 L9 -45.6 L9 -44.6 L-13 -41 Z" fill="#fff" fill-opacity="0.7"/>
    <path d="M-10 -39 L4 -41.3" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>`;
}
