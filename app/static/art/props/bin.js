/* Урна.
   binSvg(): мятная урна с крышкой. */

function binSvg() {
  return `${SHADOW_DOT("bnsh", 9, 3)}
    <path d="M-5 -14 L5 -14 L4.2 0 L-4.2 0 Z" fill="#5fcbb5"/><path d="M1 -14 L5 -14 L4.2 0 L1 0 Z" fill="#3fa994"/>
    <path d="M-5.6 -14.4 Q0 -18.4 5.6 -14.4 L5.6 -13 L-5.6 -13 Z" fill="#8fe3cf"/>`;
}
