/* Пол кофейни.
   cafeFloorSvg(): светлые доски разной длины (4 тона), тонкие швы, мягкая тень у стен. Размер зала ROOM_W x ROOM_D — в app.js. */

/* Пол: светлые доски разной длины, тонкие швы, без прожилок. */
function cafeFloorSvg() {
  const out = [];
  const tones = ["#f2c88f", "#edc084", "#f5d09b", "#eebf84"];
  const joints = [];
  for (let y = 0; y < ROOM_D; y += 1) {
    const start = [0, 2.2, 1, 3.1][y % 4];
    const cuts = [0];
    for (let x = start; x < ROOM_W; x += 3.4) if (x > 0.4) cuts.push(x);
    cuts.push(ROOM_W);
    cuts.sort((a, b) => a - b);
    for (let i = 0; i < cuts.length - 1; i += 1) {
      const tone = tones[(y * 5 + i * 3 + (y % 2)) % tones.length];
      out.push(face([[cuts[i], y, 0], [cuts[i + 1], y, 0], [cuts[i + 1], y + 1, 0], [cuts[i], y + 1, 0]], tone));
      joints.push([[cuts[i], y, 0], [cuts[i], y + 1, 0]]);
    }
  }
  const seams = [];
  for (let y = 0; y <= ROOM_D; y += 1) seams.push([[0, y, 0], [ROOM_W, y, 0]]);
  out.push(lines(seams, "#d9a46a", 0.7, 0.55), lines(joints, "#d9a46a", 0.7, 0.55));
  // мягкая тень от стен
  out.push(ov([[0, 0, 0.1], [ROOM_W, 0, 0.1], [ROOM_W, 0.6, 0.1], [0, 0.6, 0.1]], PAL.shadowWarm, 0.1));
  out.push(ov([[0, 0, 0.1], [0.6, 0, 0.1], [0.6, ROOM_D, 0.1], [0, ROOM_D, 0.1]], PAL.shadowWarm, 0.07));
  return out.join("");
}
