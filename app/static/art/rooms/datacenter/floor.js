/* Пол ЦОДа.
   dcFloorSvg(): светлая плитка в шахматку, сетка швов, бирюзовая полоса холодного коридора, мягкая тень у стен. */

const DC_LED = PAL.neon;

function dcFloorSvg() {
  const out = [];
  for (let y = 0; y < ROOM_D; y += 1) {
    for (let x = 0; x < ROOM_W; x += 1) {
      out.push(face([[x, y, 0], [x + 1, y, 0], [x + 1, y + 1, 0], [x, y + 1, 0]], (x + y) % 2 ? "#d3dcea" : "#dde5f0"));
    }
  }
  const grid = [];
  for (let i = 0; i <= ROOM_W; i += 1) grid.push([[i, 0, 0], [i, ROOM_D, 0]], [[0, i, 0], [ROOM_W, i, 0]]);
  out.push(lines(grid, "#b4c2d6", 0.7, 0.7));
  // холодный коридор между стойками: светящаяся полоса под рядом
  out.push(ov([[1.55, 3.55, 0.1], [7.6, 3.55, 0.1], [7.6, 4.15, 0.1], [1.55, 4.15, 0.1]], PAL.teal, 0.16));
  out.push(ov([[0, 0, 0.1], [ROOM_W, 0, 0.1], [ROOM_W, 0.6, 0.1], [0, 0.6, 0.1]], PAL.shadow, 0.1));
  out.push(ov([[0, 0, 0.1], [0.6, 0, 0.1], [0.6, ROOM_D, 0.1], [0, ROOM_D, 0.1]], PAL.shadow, 0.08));
  return out.join("");
}
