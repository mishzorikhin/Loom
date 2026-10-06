/* Свет суток.
   TINT — таблица [минуты, цвет] умножаемого тинта: днём белый, вечером тёплый, ночью синий. daylight(mins) возвращает
   {sky, sun, tint, filter}. Менять TINT, чтобы сдвинуть вечер или ночь; filter — CSS-фильтр canvas (сейчас лёгкая насыщенность). */

/* Свет суток. Заменяет `daylight` из app.js (art/light.js подключается позже app.js): днём картинка не затемняется и не желтится,
   вечером мягкий тёплый тинт, ночью синий. Тинт ложится на мир умножением (phaser-world.js, scene.tint), поэтому светящиеся окна
   и фонари остаются яркими. Небо и солнце берутся из таблицы LIGHT в app.js. */
const TINT = [
  [0, "#6e7cc6"], [300, "#6e7cc6"], [390, "#a9aed8"], [480, "#fff3e6"], [570, "#ffffff"],
  [990, "#ffffff"], [1080, "#ffeedd"], [1140, "#ffc9aa"], [1200, "#9a9bd6"], [1290, "#6e7cc6"], [1440, "#6e7cc6"],
];

function daylight(mins) {
  const m = Math.min(1440, Math.max(0, mins));
  const span = (table, pick) => {
    let i = 0;
    while (i < table.length - 2 && m > table[i + 1][0]) i += 1;
    return [table[i], table[i + 1], (m - table[i][0]) / (table[i + 1][0] - table[i][0])];
  };
  const [a, b, t] = span(LIGHT);
  const [ta, tb, tt] = span(TINT);
  return {
    sky: mix(a[1], b[1], t),
    sun: a[2] + (b[2] - a[2]) * t,
    tint: mix(ta[1], tb[1], tt),
    filter: "saturate(1.1) contrast(1.03)",
  };
}
