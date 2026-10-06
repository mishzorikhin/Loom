/* Камень.
   rockSvg(s): пастельный валун в два тона с бликом и цветной тенью. */

function rockSvg(s = 1) {
  return `<defs>${radial("rsh", [[0, PAL.shadow, 0.28], [1, PAL.shadow, 0]])}</defs>
    <ellipse cx="4" cy="2" rx="15" ry="4.6" fill="url(#rsh)"/>
    <path d="M-10 0 Q-10 -8 -3 -10.5 Q6 -11 11 -2 Q11 1 8 1 L-8 1 Z" fill="#dde3f0"/>
    <path d="M-3 -10.5 Q6 -11 11 -2 Q11 1 8 1 L2 1 Q4 -6 -3 -10.5 Z" fill="#b4bdd8"/>
    <path d="M-7 -4 Q-5 -9 -1 -9.5" fill="none" stroke="#fff" stroke-width="1.2" stroke-linecap="round" stroke-opacity="0.8"/>`;
}
