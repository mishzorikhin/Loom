/* Светофор.
   makeTrafficSignal(spec) — Phaser-контейнер из графики: столб, корпус и три лампы с ореолами. spec: {axis, x, y}.
   Возвращает {...spec, el, lamps}; drawAmbient (phaser-world.js) зажигает лампу по Traffic.signal. Цвета ламп — в объекте colors. */

function makeTrafficSignal(spec) {
  const el = phaserScene.add.container(...iso(spec.x, spec.y, G));
  const body = phaserScene.add.graphics();
  // тень, основание, столб с бликом, корпус с козырьками над линзами
  body.fillStyle(0x3d5a9a, 0.22).fillEllipse(6, 2, 20, 7);
  body.fillStyle(0x7b88a0).fillEllipse(0, 1.5, 13, 5);
  body.fillStyle(0x7b88a0).fillRect(-1.8, -43, 3.6, 44);
  body.fillStyle(0xaab6cc).fillRect(-1.8, -43, 1.2, 44);
  body.fillStyle(0x59667d).fillRoundedRect(-3.2, -9, 6.4, 8, 1.5);
  body.fillStyle(0x34405a).fillRoundedRect(-8, -72, 16, 36, 3.5);
  body.fillStyle(0x4a5873).fillRoundedRect(-8, -72, 6, 36, 3.5);
  body.lineStyle(1, 0x7b88a0).strokeRoundedRect(-8, -72, 16, 36, 3.5);
  const colors = { red: 0xff5a4d, yellow: 0xffc93f, green: 0x4fdc98 };
  const lamps = Object.entries(colors).map(([name, color], i) => {
    const cy = -64 + i * 10;
    body.fillStyle(0x222b3d).fillCircle(0, cy, 4.7);
    body.fillStyle(0x59667d).fillRoundedRect(-5.6, cy - 6.4, 11.2, 2.4, 1);
    return { name, color, dot: phaserScene.add.circle(0, cy, 3.5, color), shine: phaserScene.add.circle(-1, cy - 1.1, 1, 0xffffff, 0.55), halo: glowImage(0, cy, 34, 34, color, 0) };
  });
  el.add([body, ...lamps.flatMap((l) => [l.halo, l.dot, l.shine])]);
  return { ...spec, el, lamps };
}
