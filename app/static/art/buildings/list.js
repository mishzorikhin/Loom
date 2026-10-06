/* Список домов квартала.
   HOUSES — массив {x, y, w, d, h, wall, roof, ridge, chimney}: положение и размеры в клетках, высота стены h в пикселях, цвета стены/кровли
   (из PAL.walls/PAL.roofs), ridge "x"|"y" — направление конька. Чтобы добавить дом: допиши строку; сортировка и тени подхватятся сами,
   но проверь, что дом не лежит на улице (onGrass в layout.js). */

const HOUSES = [
  // слева за стеной
  { x: -13, y: 0, w: 6.5, d: 5, h: 46, wall: PAL.walls[0], roof: PAL.roofs[0], ridge: "y" },
  { x: -13, y: 6.5, w: 6.5, d: 4.2, h: 34, wall: PAL.walls[3], roof: PAL.roofs[1], ridge: "x" },
  { x: -13, y: -7, w: 6.5, d: 4.5, h: 52, wall: PAL.walls[4], roof: PAL.roofs[3], ridge: "x", chimney: true },
  // сзади
  { x: -2, y: -12, w: 5, d: 5.5, h: 50, wall: PAL.walls[1], roof: PAL.roofs[2], ridge: "x", chimney: true },
  { x: 4.5, y: -11, w: 5.5, d: 4.5, h: 38, wall: PAL.walls[2], roof: PAL.roofs[0], ridge: "y" },
  { x: -10, y: -13.5, w: 5, d: 5, h: 44, wall: PAL.walls[0], roof: PAL.roofs[1], ridge: "y" },
  // справа за поперечной улицей
  { x: 18, y: -12, w: 5.5, d: 5, h: 40, wall: PAL.walls[4], roof: PAL.roofs[0], ridge: "x" },
  { x: 18.5, y: -5, w: 5.5, d: 5, h: 46, wall: PAL.walls[3], roof: PAL.roofs[3], ridge: "y", chimney: true },
  { x: 18.5, y: 2, w: 5.5, d: 4.5, h: 36, wall: PAL.walls[1], roof: PAL.roofs[2], ridge: "x" },
  { x: 18.5, y: 8, w: 5, d: 3.2, h: 42, wall: PAL.walls[2], roof: PAL.roofs[1], ridge: "y" },
  // через главную улицу спереди
  { x: 18.5, y: 18.5, w: 6, d: 5, h: 48, wall: PAL.walls[0], roof: PAL.roofs[2], ridge: "y" },
  { x: 18.5, y: 25.5, w: 5.5, d: 4.5, h: 38, wall: PAL.walls[4], roof: PAL.roofs[0], ridge: "x" },
];
