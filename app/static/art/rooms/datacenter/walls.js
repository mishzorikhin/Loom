/* Стены ЦОДа.
   dcWallsSvg(): графитовые стены с панелями и бирюзовыми неоновыми линиями, цоколь, плита-основание. Цвета PAL.graphite/teal. */

function dcWallsSvg() {
  const back = box(-0.28, -0.28, ROOM_W + 0.28, 0.28, WALL, "#6a7a94", "#51607a", "#3d4a63");
  const left = box(-0.28, 0, 0.28, ROOM_D, WALL, "#6a7a94", "#51607a", "#46546e");
  const panels = [];
  for (let x = 0.5; x < ROOM_W; x += 1.9) panels.push(face([[x, 0.03, 6], [x + 1.5, 0.03, 6], [x + 1.5, 0.03, 30], [x, 0.03, 30]], "#8394b0", 0.55));
  for (let y = 0.5; y < ROOM_D; y += 1.9) panels.push(face([[0.03, y, 6], [0.03, y + 1.5, 6], [0.03, y + 1.5, 30], [0.03, y, 30]], "#6c7c99", 0.55));
  panels.push(face([[0, 0.02, 0], [ROOM_W, 0.02, 0], [ROOM_W, 0.02, 3.5], [0, 0.02, 3.5]], "#2f3a4f"));
  panels.push(face([[0.02, 0, 0], [0.02, ROOM_D, 0], [0.02, ROOM_D, 3.5], [0.02, 0, 3.5]], "#2f3a4f"));
  panels.push(seg([0, 0.03, 31], [ROOM_W, 0.03, 31], PAL.teal, 1.2));
  panels.push(seg([0.03, 0, 31], [0.03, ROOM_D, 31], PAL.teal, 1.2));
  const slab = [
    face([[0, ROOM_D, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [0, ROOM_D, 0]], "#59667d"),
    face([[ROOM_W, 0, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0]], "#44506a"),
    seg([0, ROOM_D, 0], [ROOM_W, ROOM_D, 0], "#8d9ab3", 1.6),
    seg([ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0], "#6f7e9a", 1.6),
  ];
  return slab.join("") + dcFloorSvg() + back + left + panels.join("");
}
