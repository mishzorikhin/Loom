/* Стены, карниз и плита кофейни.
   cafeWallsSvg(): плита-основание (терракота), пол, задняя и левая стены (кремовые), мятная обшивка до пояса, рейка, карниз.
   Цвета: PAL.mint, PAL.terra, PAL.cream. */

function cafeWallsSvg() {
  const back = box(-0.28, -0.28, ROOM_W + 0.28, 0.28, WALL, "#fff4e0", "#fbeed8", "#e8d3b8");
  const left = box(-0.28, 0, 0.28, ROOM_D, WALL, "#fbeed8", "#f4e1c4", "#ead5b8");
  const bz = (a0, a1, z0, z1, yy = 0.02) => [[a0, yy, z0], [a1, yy, z0], [a1, yy, z1], [a0, yy, z1]];
  const lz = (a0, a1, z0, z1, xx = 0.02) => [[xx, a0, z0], [xx, a1, z0], [xx, a1, z1], [xx, a0, z1]];
  const wall = [`<defs>${vertical("wallLight", [[0, "#fff", 0.3], [1, "#fff", 0]])}${vertical("wallDark", [[0, PAL.tint, 0.05], [1, PAL.tint, 0.16]])}</defs>`];
  wall.push(ov(bz(0, ROOM_W, 0, WALL), "url(#wallLight)"), ov(lz(0, ROOM_D, 0, WALL), "url(#wallDark)"));
  // мятная обшивка до пояса, светлая рейка, плинтус
  wall.push(face(bz(0, ROOM_W, 0, 34, 0.02), PAL.mint.mid), face(bz(0, ROOM_W, 34, 38, 0.03), "#fff6e4"));
  wall.push(face(lz(0, ROOM_D, 0, 34), cool(PAL.mint.mid, 0.2)), face(lz(0, ROOM_D, 34, 38, 0.03), "#f1e3c8"));
  for (let x = 0.2; x < ROOM_W - 0.5; x += 1.6) wall.push(ov(bz(x + 0.06, x + 1.34, 6.2, 28.8), PAL.mint.light, 0.45));
  for (let y = 0.2; y < ROOM_D - 0.5; y += 1.6) wall.push(ov(lz(y + 0.06, y + 1.34, 6.2, 28.8), PAL.mint.light, 0.3));
  wall.push(face(bz(0, ROOM_W, 0, 4.2, 0.02), "#fff6e4"), face(lz(0, ROOM_D, 0, 4.2), "#f1e3c8"));
  // карниз
  wall.push(face(bz(-0.28, ROOM_W, WALL - 5, WALL, 0.03), "#fffaf0"), face(lz(0, ROOM_D, WALL - 5, WALL, 0.03), "#f8ecd6"));
  wall.push(seg([0, 0.03, WALL - 5], [ROOM_W, 0.03, WALL - 5], "#e8d3b8", 1.2), seg([0.03, 0, WALL - 5], [0.03, ROOM_D, WALL - 5], "#e0c9ab", 1.2));
  wall.push(seg([0, 0.02, 0], [0, 0.02, WALL], "#e0c9ab", 1.4));
  const slab = [
    face([[0, ROOM_D, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [0, ROOM_D, 0]], PAL.terra.mid),
    face([[ROOM_W, 0, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0]], PAL.terra.dark),
    seg([0, ROOM_D, 0], [ROOM_W, ROOM_D, 0], PAL.terra.light, 1.6),
    seg([ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0], PAL.terra.mid, 1.6),
  ];
  return slab.join("") + cafeFloorSvg() + back + left + wall.join("");
}
