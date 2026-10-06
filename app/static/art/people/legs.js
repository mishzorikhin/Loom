/* Ноги человека.
   personLegs(pants, shoe, seated) — SVG ног. Стоя: две группы .leg.leg-l / .leg.leg-r (страница вырезает их в отдельные
   текстуры для шага, поэтому внутри только плоские цвета). Сидя: бёдра вперёд, голени вниз, без групп.
   Параметры: pants — цвет брюк, shoe — цвет обуви, seated — сидит ли. Менять: пропорции (4 x 14), форму ботинка. */
function personLegs(pants, shoe, seated) {
  const sole = shade(shoe, 0.45);
  const leg = (x, fill, flip) => `<rect x="${x}" y="-15" width="4" height="14" rx="1.6" fill="${fill}"/>
      <rect x="${flip ? x + 2.6 : x + 0.4}" y="-14" width="1" height="11" rx="0.5" fill="#fff" fill-opacity="0.08"/>
      <rect x="${x}" y="-3.4" width="4" height="1.4" fill="${shade(fill, 0.18)}"/>
      <path d="M${x - 0.7} -1.6 Q${x - 0.4} -3.4 ${x + 1.6} -3 L${x + 4.9} -2.4 Q${x + 5.2} -0.2 ${x + 4.4} 0.4 L${x - 0.2} 0.5 Q${x - 0.9} -0.4 ${x - 0.7} -1.6 Z" fill="${shoe}"/>
      <path d="M${x - 0.3} 0.2 L${x + 4.5} 0.1" stroke="${sole}" stroke-width="0.9" stroke-linecap="round"/>`;
  // Сидя: человек в профиль к зрителю, лицом вправо (страница отражает фигуру по стороне стула). Бёдра лежат горизонтально
  // на подушке, колени вынесены вперёд, голени идут вниз, ботинки смотрят вперёд. Дальняя нога чуть выше и темнее.
  return seated
    ? `<rect x="3.4" y="4.4" width="4" height="9" rx="1.8" fill="${shade(pants, 0.32)}"/>
       <path d="M4.4 12.6 Q4.6 11.4 6.8 11.6 L10.8 12.4 Q11.3 14.4 10.2 14.8 L4.8 14.8 Q4 13.8 4.4 12.6 Z" fill="${shade(shoe, 0.2)}"/>
       <rect x="-3.6" y="-4.4" width="13.2" height="5.2" rx="2.5" fill="${shade(pants, 0.3)}"/>
       <rect x="-0.2" y="5" width="4.2" height="8.4" rx="1.8" fill="${pants}"/>
       <path d="M-0.4 12.6 Q-0.2 11.2 2.2 11.4 L6.4 12.2 Q7 14.4 5.8 14.8 L-0.2 14.8 Q-1 13.8 -0.4 12.6 Z" fill="${shoe}"/>
       <rect x="-4.2" y="-2" width="14" height="5.8" rx="2.7" fill="${pants}"/>
       <rect x="-2.6" y="-1.2" width="9" height="1.2" rx="0.6" fill="#fff" fill-opacity="0.12"/>`
    : `<g class="leg leg-l">${leg(-4.6, pants, false)}</g><g class="leg leg-r">${leg(0.6, shade(pants, 0.2), true)}</g>`;
}
