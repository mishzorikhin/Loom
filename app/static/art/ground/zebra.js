/* Пешеходные переходы и стоп-линии.
   zebraSvg() — по семь белых полос на каждом из четырёх заходов перекрёстка и четыре стоп-линии (раньше перехода по ходу движения).
   Положение связано с ROAD_X0/ROAD_X1 и с тем, где сервер считает переход (app/city.py); при сдвиге менять вместе. */

function zebraSvg() {
  const paint = [];
  const mid = (ROAD_X0 + ROAD_X1) / 2;
  [ROAD_X0 - 1.4, ROAD_X1 + 0.7].forEach((u) => {
    for (let i = 0; i < 7; i += 1) {
      const v = ROAD_X0 + 0.12 + i * 0.55;
      paint.push(gface(u, v, u + 0.7, v + 0.32, PAL.paint, 1, 0.4));
      paint.push(gface(v, u, v + 0.32, u + 0.7, PAL.paint, 1, 0.4));
    }
  });
  paint.push(lines([
    [[ROAD_X0 - 2.4, mid, G], [ROAD_X0 - 2.4, ROAD_X1 - 0.15, G]],
    [[ROAD_X1 + 2.4, ROAD_X0 + 0.15, G], [ROAD_X1 + 2.4, mid, G]],
    [[ROAD_X0 + 0.15, ROAD_X0 - 2.4, G], [mid, ROAD_X0 - 2.4, G]],
    [[mid, ROAD_X1 + 2.4, G], [ROAD_X1 - 0.15, ROAD_X1 + 2.4, G]],
  ], PAL.paint, 2.5));
  return paint.join("");
}
