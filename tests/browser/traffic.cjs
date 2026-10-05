/* Проверка поведения потока, без браузера и LLM. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const context = vm.createContext({ module: { exports: {} } });
vm.runInContext(fs.readFileSync('app/static/world.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('app/static/traffic.js', 'utf8'), context);
const T = context.module.exports;
const specs = vm.runInContext('CARS.map(c => ({ ...c, length: CAR_KINDS[c.kind].L, maxSpeed: c.kind === "van" ? 4.4 : 5.2 }))', context);
const world = new T.World(specs);
let previous = null, stops = 0, starts = 0, laps = 0, maxDecel = 0;
for (let tick = 0; tick <= 14400; tick += 1) {
  const minute = tick * T.STEP;
  const cars = world.at(minute, 1);
  assert.ok(!(T.signal(minute, 'x') === 'green' && T.signal(minute, 'y') === 'green'));
  for (const car of cars) {
    assert.ok(car.v >= 0 && car.v <= car.maxSpeed + 1e-6);
    for (const other of cars) {
      if (car.id === other.id) continue;
      if (car.axis === other.axis && car.dir === other.dir) {
        const gap = (other.s - car.s + T.LENGTH) % T.LENGTH - (car.length + other.length) / 2;
        assert.ok(gap >= T.GAP - 1e-5, `Дистанция ${gap}, время ${minute}`);
      } else if (car.axis !== other.axis) {
        const a = T.layout(car), b = T.layout(other);
        const crossing = (c, lane) => c.s + c.length / 2 > lane.entry && c.s - c.length / 2 < lane.exit;
        assert.ok(!(crossing(car, a) && crossing(other, b)), `Конфликт потоков в ${minute}`);
      }
    }
    if (car.v === 0) stops += 1;
    if (!previous) continue;
    const before = previous[car.id];
    const decel = (before.v - car.v) / T.STEP;
    maxDecel = Math.max(maxDecel, decel);
    assert.ok((car.v - before.v) / T.STEP <= 1.8 + 1e-6, 'Рывок при разгоне');
    assert.ok(decel <= T.BRAKE + 0.6, 'Рывок при торможении');
    if (car.v > before.v + 0.01) starts += 1;
    if (car.s < before.s) { laps += 1; continue; }
    const line = T.layout(car).stop;
    if (before.s <= line && car.s > line) {
      assert.ok(T.signal(minute - T.STEP, car.axis) !== 'red' || before.committed, `Въезд на красный в ${minute}`);
    }
  }
  previous = cars;
}
assert.ok(stops > 100 && starts > 100 && laps > 100, 'Поток должен останавливаться и продолжать движение');
const minute = 750.123;
const rewound = world.at(minute, 1);
const fresh = new T.World(specs).at(minute, 1);
assert.equal(JSON.stringify(rewound), JSON.stringify(fresh), 'Перемотка и перезагрузка меняют мир');
assert.equal(JSON.stringify(world.at(minute, 1)), JSON.stringify(fresh), 'На паузе транспорт движется');
assert.equal(JSON.stringify(world.at(minute, 2)), JSON.stringify(fresh), 'Новый день не сбрасывает расчёт');
const sparse = new T.World(specs);
[480, 480.13, 510.47, 720.71, minute].forEach(t => sparse.at(t, 1));
assert.equal(JSON.stringify(sparse.at(minute, 1)), JSON.stringify(fresh), 'Частота кадров меняет движение');
assert.equal(T.signal(492, 'x'), 'yellow');
assert.equal(T.signal(495, 'x'), 'red');
assert.equal(T.signal(495, 'y'), 'red');
assert.equal(T.signal(498, 'y'), 'green');
console.log(`PASS: полные сутки, дистанция, сигналы, освобождение перекрёстка, разгон/торможение (max ${maxDecel.toFixed(2)}), пауза, перемотка, новый день и разная частота кадров.`);
