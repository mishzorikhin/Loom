/* Сортировка по глубине.
   isoSort(rows) — упорядочивает объекты сцены [{el, d, box:[x0, x1, y0, y1]}]: если коробки разделены по оси, дальняя рисуется раньше;
   иначе по d. Вызывается drawAmbient в phaser-world.js. Для нового объекта достаточно дать корректный box. */

/* Порядок рисования предметов-коробок в изометрии: если коробки разделены по одной из осей, дальняя рисуется раньше;
   по центру глубины сортировать нельзя, длинные машины на соседних полосах перекрывали бы друг друга неверно. */
function isoSort(rows) {
  const n = rows.length;
  const after = Array.from({ length: n }, () => []);
  const indeg = new Array(n).fill(0);
  const sep = (a0, a1, b0, b1) => (a1 <= b0 ? -1 : b1 <= a0 ? 1 : 0);
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const a = rows[i];
      const b = rows[j];
      const sx = sep(a.box[0], a.box[1], b.box[0], b.box[1]);
      const sy = sep(a.box[2], a.box[3], b.box[2], b.box[3]);
      let first;
      if ((sx && sy && sx !== sy) || (!sx && !sy)) first = a.d <= b.d ? -1 : 1;
      else first = sx || sy;
      if (first < 0) { after[i].push(j); indeg[j] += 1; } else { after[j].push(i); indeg[i] += 1; }
    }
  }
  const done = new Array(n).fill(false);
  const out = [];
  for (let step = 0; step < n; step += 1) {
    let pick = -1;
    for (let i = 0; i < n; i += 1) {
      if (!done[i] && indeg[i] === 0 && (pick < 0 || rows[i].d < rows[pick].d)) pick = i;
    }
    if (pick < 0) {
      for (let i = 0; i < n; i += 1) {
        if (!done[i] && (pick < 0 || rows[i].d < rows[pick].d)) pick = i;
      }
    }
    done[pick] = true;
    out.push(rows[pick]);
    after[pick].forEach((k) => { indeg[k] -= 1; });
  }
  rows.splice(0, n, ...out);
}
