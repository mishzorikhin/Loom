/* Состояние сцены мира и конфигурация движения. Все рисунки лежат в app/static/art/ (карта — docs/graphics.md).
   PED_PATHS — маршруты прохожих (запасной клиентский список, сервер ведёт людей сам); CARS — полосы и стартовые позиции машин,
   их читает traffic.js и проверка npm run test:traffic; outer — объекты мира для сортировки (заполняет phaser-world.js);
   layers — переключатели «Имена» и «Улица»; pedDensity(mins) — суточная плотность прохожих. */

const PED_PATHS = [
  { a: [-2.8, 10.3], b: [11, 10.3], n: 3 },
  { a: [10.4, -2.8], b: [10.4, 11], n: 2 },
  { a: [-4, -3], b: [-4, 11], n: 1 },
  { a: [-26, 16.6], b: [9.4, 16.6], n: 3 },
  { a: [18, 16.6], b: [34, 16.6], n: 2 },
  { a: [16.6, -26], b: [16.6, 9.4], n: 2 },
  { a: [16.6, 18], b: [16.6, 34], n: 2 },
  { a: [-4, -4], b: [11, -4], n: 1 },
];

const CARS = [
  // Правостороннее движение, по три машины на полосу. Сдвиги — начальные позиции.
  ...[0, 20, 43].map((off, i) => ({ axis: "x", fixed: 14.4, dir: 1, off, color: i, kind: i === 2 ? "van" : "sedan", taxi: i === 1 })),
  ...[6, 29, 52].map((off, i) => ({ axis: "x", fixed: 12.6, dir: -1, off, color: i + 3, kind: i === 0 ? "hatch" : "sedan" })),
  ...[3, 25, 48].map((off, i) => ({ axis: "y", fixed: 12.6, dir: 1, off, color: i + 4, kind: i === 1 ? "van" : "hatch" })),
  ...[10, 33, 56].map((off, i) => ({ axis: "y", fixed: 14.4, dir: -1, off, color: i + 1, kind: i === 2 ? "hatch" : "sedan" })),
];

let outer = null; // { statics: [{el, d}], ambient: [{el, kind, ...}], key }
const layers = { names: true, life: true };

function pedDensity(mins) {
  const peak = (m, c, s) => Math.exp(-(((m - c) / s) ** 2));
  const awake = Math.min(1, Math.max(0, (mins - 300) / 120), Math.max(0, (1440 - mins) / 120));
  return Math.min(1, 0.08 + awake * (0.27 + 0.65 * Math.max(peak(mins, 540, 70), peak(mins, 780, 90) * 0.8, peak(mins, 1050, 80))));
}
