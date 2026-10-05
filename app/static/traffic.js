/* Детерминированная кинематика улицы: клетки и минуты симуляции, фиксированный шаг.
   Не влияет на кофейню и LLM. Считается от 00:00 суток и восстанавливается заново при новом дне. */
const Traffic = (() => {
  const STEP = 0.05, LENGTH = 68, START = -30, END = 38;
  const MAX_SPEED = 5.2, ACCEL = 1.8, BRAKE = 3.6, GAP = 0.8;
  const CYCLE = 36; // 12 зелёный, 3 жёлтый, 3 освобождение — по каждой оси.
  function signal(minute, axis) {
    const t = (((minute - 480) % CYCLE) + CYCLE) % CYCLE;
    const phase = axis === 'x' ? t : (t + 18) % CYCLE;
    return phase < 12 ? 'green' : phase < 15 ? 'yellow' : 'red';
  }
  function layout(car) {
    const dir = car.dir;
    const stop = dir > 0 ? ROAD_X0 - 2.4 - car.length / 2 : ROAD_X1 + 2.4 + car.length / 2;
    return { stop: dir > 0 ? stop - START : END - stop,
      entry: dir > 0 ? ROAD_X0 - START : END - ROAD_X1,
      exit: dir > 0 ? ROAD_X1 - START : END - ROAD_X0 };
  }
  class World {
    constructor(specs) {
      this.specs = specs;
      this.reset();
    }
    reset(day = 0) {
      this.day = day; this.tick = 0;
      this.cars = this.specs.map((spec, id) => ({ ...spec, id, s: spec.off, v: 3.4, brake: false, committed: false }));
    }
    step() {
      const time = this.tick * STEP;
      const old = this.cars.map((car) => ({ ...car }));
      this.cars.forEach((car, i) => {
        const before = old[i], lane = layout(car);
        let gap = Infinity, leaderSpeed = 0;
        old.forEach((other, j) => {
          if (i === j || car.axis !== other.axis || car.dir !== other.dir) return;
          const dist = (other.s - before.s + LENGTH) % LENGTH;
          const free = dist - (car.length + other.length) / 2;
          if (free < gap) { gap = free; leaderSpeed = other.v; }
        });
        let limit = Infinity;
        const distance = lane.stop - before.s;
        const color = signal(time, car.axis);
        // На жёлтый останавливается тот, кто может затормозить до линии.
        if (color === 'yellow' && distance >= 0 && distance <= before.v * before.v / (2 * BRAKE) + before.v * STEP + 0.15) car.committed = true;
        if (!car.committed && distance >= -0.01 && color !== 'green') limit = Math.max(0, distance);
        // Даже на зелёный не въезжаем, пока поперечный поток не освободил перекрёсток.
        const occupied = old.some((other) => {
          if (other.axis === car.axis) return false;
          const cross = layout(other);
          return other.s + other.length / 2 > cross.entry && other.s - other.length / 2 < cross.exit;
        });
        if (distance >= -0.01 && occupied) limit = Math.min(limit, Math.max(0, distance));
        const effectiveGap = Math.min(gap, limit + GAP);
        const aheadSpeed = limit + GAP < gap ? 0 : leaderSpeed;
        const closing = Math.max(0, before.v * (before.v - aheadSpeed) / (2 * Math.sqrt(ACCEL * BRAKE)));
        const desiredGap = GAP + before.v * 0.65 + closing;
        let acceleration = ACCEL * (1 - (before.v / (car.maxSpeed || MAX_SPEED)) ** 4 - (desiredGap / Math.max(0.01, effectiveGap)) ** 2);
        acceleration = Math.max(-BRAKE, Math.min(ACCEL, acceleration));
        let velocity = Math.max(0, before.v + acceleration * STEP);
        if (velocity < 0.03 && effectiveGap < GAP + 0.05) velocity = 0;
        let travel = (before.v + velocity) / 2 * STEP;
        const maxTravel = Math.max(0, Math.min(limit, gap - GAP));
        if (travel >= maxTravel) { travel = maxTravel; velocity = 0; }
        car.s = (before.s + travel) % LENGTH;
        if (car.s < before.s || car.s > lane.entry) car.committed = false;
        car.v = velocity;
        car.brake = acceleration < -0.3 || velocity < 0.08;
      });
      this.tick += 1;
    }
    at(minute, day = 0) {
      const ticks = Math.max(0, minute / STEP);
      const target = Math.floor(ticks + 1e-8);
      if (day !== this.day || target < this.tick) this.reset(day);
      while (this.tick < target) this.step();
      const fraction = Math.max(0, Math.min(1, ticks - target));
      // Между шагами только показ: следующий шаг не меняет сохранённое состояние.
      const saved = this.cars.map((c) => ({ ...c }));
      this.step();
      const next = this.cars;
      this.cars = saved; this.tick = target;
      return saved.map((car, i) => {
        const ds = (next[i].s - car.s + LENGTH) % LENGTH;
        const s = (car.s + ds * fraction) % LENGTH;
        return { ...car, s, u: car.dir > 0 ? START + s : END - s, v: car.v + (next[i].v - car.v) * fraction };
      });
    }
  }
  return { World, signal, layout, STEP, LENGTH, GAP, BRAKE, MAX_SPEED };
})();
if (typeof module !== 'undefined') module.exports = Traffic;
