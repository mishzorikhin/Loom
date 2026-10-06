/* Фигура человека: figureSvg(look, pose, staff, accent, carry). Заменяет `figureSvg` из app.js (art подключается позже).
   Параметры: look {shirt, hair, skin, pants, style} (из looksOf в app.js), pose "sit" | иначе стоя, staff — бариста (фартук),
   accent — цвет платка, carry — чашка в руке. Контракт страницы: классы .ring, .leg-l/.leg-r, .arm-l/.arm-r, .upper, .body;
   конечности вырезаются в отдельные текстуры, поэтому внутри .leg и .arm только плоские цвета. Части: legs.js, hair.js,
   clothes.js, face.js. Менять: пропорции торса и головы здесь; одежду, причёски и лица — в соседних файлах. */
function figureSvg(look, pose, staff, accent, carry) {
  const { shirt, hair, skin, pants, style } = look;
  const seated = pose === "sit";
  const up = seated ? 13 : 0;
  const h = hashOf(`${shirt}${hair}${pants}`);
  const kind = staff ? 3 : h % 6;
  const shoe = ["#3b3a52", "#4a3b44", "#fbf7ee", "#b0603f", "#35476a"][(h >> 2) % 5];
  const glasses = !staff && (h >> 3) % 7 === 0;
  const skinS = shade(skin, 0.13);
  const legs = personLegs(pants, shoe, seated);
  const hairs = personHair(hair, style);
  const detail = personTorso(kind, shirt, skinS);
  const apron = staff ? personApron(accent) : "";
  const face = personFaceSvg(glasses);
  return `<defs>${radial("fs", [[0, PAL.shadow, 0.32], [0.6, PAL.shadow, 0.16], [1, PAL.shadow, 0]])}</defs>
    <ellipse cx="0" cy="${seated ? 7 : 1.4}" rx="12" ry="4.2" fill="url(#fs)"/>
    <ellipse class="ring" cx="0" cy="${seated ? 6 : 1.5}" rx="13" ry="5.2" fill="none" stroke="#f0a73a" stroke-width="2"/>
    <g class="body">
      ${legs}
      <g class="upper" transform="translate(0 ${up})">
        ${hairs.back}
        <g class="arm arm-l"><rect x="-9.6" y="-34" width="3.8" height="17.5" rx="1.9" fill="${shade(shirt, 0.08)}"/><rect x="-9.6" y="-19.4" width="3.8" height="1.4" fill="${shade(shirt, 0.2)}"/><circle cx="-7.7" cy="-16" r="2" fill="${skin}"/></g>
        <g class="arm arm-r"><rect x="5.8" y="-34" width="3.8" height="17.5" rx="1.9" fill="${shade(shirt, 0.22)}"/><rect x="5.8" y="-19.4" width="3.8" height="1.4" fill="${shade(shirt, 0.34)}"/><circle cx="7.7" cy="-16" r="2" fill="${shade(skin, 0.1)}"/>${carry ? CUP_IN_HAND : ""}</g>
        <path d="M -6.4 -31 Q -6.4 -35.4 -2.4 -35.4 L 2.4 -35.4 Q 6.4 -35.4 6.4 -31 L 6.4 -16 Q 6.4 -13.6 4 -13.6 L -4 -13.6 Q -6.4 -13.6 -6.4 -16 Z" fill="${shirt}"/>
        <path d="M 0.6 -35.4 L 2.4 -35.4 Q 6.4 -35.4 6.4 -31 L 6.4 -16 Q 6.4 -13.6 4 -13.6 L 0.6 -13.6 Z" fill="#5d62ae" fill-opacity="0.16"/>
        <path d="M-5.6 -33 Q-4.6 -34.8 -2.6 -35" fill="none" stroke="${lighten(shirt, 0.35)}" stroke-width="0.9" stroke-linecap="round" stroke-opacity="0.7"/>
        <rect x="-6.4" y="-15.2" width="12.8" height="1.6" fill="${shade(pants, 0.35)}"/>
        ${detail}
        ${apron}
        <rect x="-1.9" y="-39" width="3.8" height="5" rx="1.4" fill="${skinS}"/>
        <circle cx="-6" cy="-43.6" r="1.4" fill="${shade(skin, 0.08)}"/><circle cx="6" cy="-43.6" r="1.4" fill="${shade(skin, 0.08)}"/>
        <ellipse cx="0" cy="-44" rx="6.2" ry="6.8" fill="${skin}"/>
        <path d="M3.4 -50 Q8 -45.6 5.4 -39.4 Q4.4 -38 3 -37.4 Q5.6 -44 3.4 -50 Z" fill="#5d62ae" fill-opacity="0.12"/>
        ${hairs.front}${hairs.sheen}
        ${face}
      </g>
    </g>
    <rect x="-12" y="-58" width="24" height="64" fill="transparent"/>`;
}
