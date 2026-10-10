// Панели поверх сцены: сводка, график, события, осмотр.
import type { FrameMsg, JunctionJ, NetJ, SeriesPoint, SimEvent } from "./types";
import { FLAG } from "./types";

export const CAUSE: Record<string, [string, string]> = {
  signal_timing: ["Короткие переходные стадии", "#ff4d4d"],
  red_light: ["Проезд на красный", "#ff3df2"],
  failed_yield: ["Не уступил пешеходу", "#ff8a3d"],
  pedestrian: ["Пешеход на красный", "#ffbf3a"],
  distraction: ["Водитель отвлёкся", "#b98cff"],
  following: ["Малая дистанция", "#5ee6ff"],
  other: ["Прочее", "#8d97a8"],
};
export const NEAR: Record<string, string> = { ttc: "TTC < 1,5 с", pet: "PET < 1 с", pedestrian: "рядом с пешеходом" };
export const WHY = ["едет свободно", "держит дистанцию", "красный", "жёлтый — останавливается", "ждёт перестроения",
  "слияние потоков", "уступает пешеходу", "пешеход на пути", "пропускает машину на перекрёстке", "выезд занят",
  "за переходом нет места"];
const KIND = ["седан", "хэтчбек", "кроссовер", "такси", "фургон", "автобус"];
const MOVE: Record<string, string> = { left: "налево", straight: "прямо", right: "направо", uturn: "разворот" };
const STAGE: Record<string, string> = { green: "зелёный", change: "жёлтый и мигающий", all_red: "весь красный" };
const STATE_COL: Record<string, string> = { G: "#2bff88", Y: "#ffbf3a", R: "#ff4d4d", W: "#2bff88", F: "#9dffc8", D: "#ff4d4d" };

export function $(id: string) {
  return document.getElementById(id)!;
}

export function esc(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}

export function eventText(e: SimEvent): [string, string, string] {
  if (e.kind === "crash") {
    const what = e.sub === "pedestrian" ? "Наезд на пешехода" : e.sub === "rear_end" ? "Удар сзади" : "Боковое столкновение";
    return [what, CAUSE[e.cause ?? "other"]?.[0] ?? e.cause ?? "", "#ff4d4d"];
  }
  if (e.kind === "near_miss") {
    const v = e.value !== undefined ? ` · ${e.value.toFixed(2)} с` : "";
    return ["Опасное сближение", (NEAR[e.sub ?? ""] ?? e.sub ?? "") + v, "#ffbf3a"];
  }
  if (e.kind === "red_run") return ["Проезд на красный", e.junction ? `перекрёсток ${e.junction}` : "", "#ff3df2"];
  if (e.kind === "jaywalk") return ["Пешеход пошёл на красный", e.junction ? `переход у ${e.junction}` : "", "#ff9a2e"];
  return ["Машина застряла и убрана", "стояла больше 5 минут", "#8d97a8"];
}

export function fmt(n: number, d = 0) {
  return n.toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function drawSpark(cv: HTMLCanvasElement, series: SeriesPoint[]) {
  const ctx = cv.getContext("2d")!;
  const W = cv.width;
  const H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const pts = series.slice(-90);
  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo(0, (H * i) / 4);
    ctx.lineTo(W, (H * i) / 4);
    ctx.stroke();
  }
  if (pts.length < 2) {
    ctx.fillStyle = "rgba(255,255,255,0.35)";
    ctx.font = "22px Inter Variable, sans-serif";
    ctx.fillText("график появится через пару минут симуляции", 12, H / 2 + 8);
    return;
  }
  const n = pts.length;
  const x = (i: number) => (i / (n - 1)) * (W - 8) + 4;
  const line = (vals: number[], color: string, fill: boolean) => {
    const max = Math.max(1, ...vals) * 1.15;
    const y = (v: number) => H - 6 - (v / max) * (H - 14);
    ctx.beginPath();
    vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.stroke();
    if (fill) {
      ctx.lineTo(x(n - 1), H);
      ctx.lineTo(x(0), H);
      ctx.closePath();
      const g = ctx.createLinearGradient(0, 0, 0, H);
      g.addColorStop(0, color + "55");
      g.addColorStop(1, color + "00");
      ctx.fillStyle = g;
      ctx.fill();
    }
  };
  line(pts.map((p) => p.done), "#5ee6ff", true);
  line(pts.map((p) => p.delay), "#ffbf3a", false);
  pts.forEach((p, i) => {
    if (!p.crashes) return;
    ctx.fillStyle = "#ff4d4d";
    for (let k = 0; k < p.crashes; k++) {
      ctx.beginPath();
      ctx.arc(x(i), 12 + k * 12, 5, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}

export function renderStats(f: FrameMsg) {
  const m = f.metrics;
  $("k-cars").textContent = fmt(m.cars);
  $("k-done").textContent = fmt(m.done);
  $("k-delay").textContent = fmt(m.delay);
  $("k-peds").textContent = fmt(m.peds);
  $("k-crash").textContent = fmt(m.crashes);
  const near = Object.values(m.near).reduce((a, b) => a + b, 0);
  $("k-near").textContent = fmt(near);
  const total = Math.max(1, m.crashes);
  const rows = Object.entries(m.causes).sort((a, b) => b[1] - a[1]);
  $("causes").innerHTML = rows.length
    ? rows.map(([k, v]) => {
        const [label, color] = CAUSE[k] ?? [k, "#8d97a8"];
        return `<div class="cause"><span>${esc(label)}</span><b>${v}</b><div class="bar"><i style="width:${(v / total) * 100}%;background:${color}"></i></div></div>`;
      }).join("")
    : `<div class="muted small">ДТП пока нет. Опустите «запас переходных стадий» ниже 100% и посмотрите, что будет.</div>`;
  $("violations").textContent = `проезд на красный: ${m.red_runs} · пешеходы на красный: ${m.jaywalks} · резкие торможения: ${m.hard_brakes} · застряли: ${m.stuck}`;
}

export function renderEvents(list: SimEvent[], fresh: Set<number>) {
  const ul = $("events");
  const items = list.slice(-80).reverse();
  ul.innerHTML = items
    .map((e) => {
      const [title, sub, color] = eventText(e);
      return `<li data-x="${e.pos[0]}" data-y="${e.pos[1]}" class="${fresh.has(e.id) && e.kind === "crash" ? "new" : ""}">
        <span class="dot" style="background:${color};box-shadow:0 0 8px ${color}"></span>
        <span class="what">${esc(title)}<small>${esc(sub)}</small></span><time>${e.clock}</time></li>`;
    })
    .join("");
}

export function junctionCard(j: JunctionJ, f: FrameMsg, net: NetJ, queues: Map<number, number>) {
  const snap = f.signals[j.id];
  if (!snap) return "";
  const gname = j.groups.map((g) => g.name);
  const pill = (name: string) => {
    const gi = gname.indexOf(name);
    const st = snap.state[gi] ?? "R";
    const g = j.groups[gi];
    const icon = g.kind === "ped" ? "пеш. " : "";
    return `<span class="pill"><i style="background:${STATE_COL[st]};box-shadow:0 0 6px ${STATE_COL[st]}"></i>${icon}${esc(name)}</span>`;
  };
  const dur = snap.stage === "green" ? snap.green_t : snap.t;
  const stageLen = snap.stage === "green" ? j.bounds.green[1] : snap.stage === "change" ? snap.dur.change || 1 : snap.dur.all_red || 1;
  const stageCol = snap.stage === "green" ? "#2bff88" : snap.stage === "change" ? "#ffbf3a" : "#ff4d4d";
  const phases = j.phases
    .map((p, i) => {
      const cls = i === snap.phase ? "cur" : i === snap.target ? "next" : "";
      return `<div class="phase ${cls}"><span class="pid">${i + 1}</span><span class="pills">${p.green.map(pill).join("")}</span>
        <button class="btn small" data-phase="${i}" ${i === snap.phase ? "disabled" : ""}>включить</button></div>`;
    })
    .join("");
  const qrows = j.approaches
    .map((li) => {
      const l = net.links[li];
      const q = queues.get(li) ?? 0;
      const label = l.id.replace(/\.(forward|backward)\./, (_, s) => (s === "forward" ? " → " : " ← ")) + (l.turns.length ? " · " + l.turns.map((t) => MOVE[t] ?? t).join(", ") : "");
      return `<div class="q"><span title="${esc(l.id)}">${esc(label.slice(0, 22))}</span><span class="bar"><i style="width:${Math.min(100, q * 7)}%"></i></span><b>${q}</b></div>`;
    })
    .join("");
  const b = j.bounds;
  return `<div class="insp-title"><b>${j.kind === "midblock" ? "Переход по вызову" : "Перекрёсток"} ${esc(j.id)}</b><button class="insp-close" data-close>×</button></div>
    <div class="stage">Стадия: <b style="color:${stageCol}">${STAGE[snap.stage]}</b> · ${dur.toFixed(1)} с
      <div class="stage-bar"><i style="width:${Math.min(100, (dur / stageLen) * 100)}%;background:${stageCol}"></i></div></div>
    <div class="muted small">Безопасно по геометрии: жёлтый ${j.safe.yellow} с · весь красный ${j.safe.all_red} с · мигающий ${j.safe.ped_flash} с</div>
    <div class="phases">${phases}</div>
    <div class="muted small">Переход вручную с длительностями (пределы: жёлтый ${b.yellow.join("–")}, весь красный ${b.all_red.join("–")}, мигающий ${b.ped_flash.join("–")} с)</div>
    <div class="durs">
      <label>жёлтый<input id="d-yellow" type="number" step="0.5" min="${b.yellow[0]}" max="${b.yellow[1]}" placeholder="авто"></label>
      <label>весь красный<input id="d-allred" type="number" step="0.5" min="${b.all_red[0]}" max="${b.all_red[1]}" placeholder="авто"></label>
      <label>мигающий<input id="d-flash" type="number" step="0.5" min="${b.ped_flash[0]}" max="${b.ped_flash[1]}" placeholder="авто"></label>
    </div>
    <h3 style="margin-top:14px">Очереди на подходах</h3><div class="queues">${qrows}</div>`;
}

export function carCard(id: number, f: FrameMsg, net: NetJ) {
  const r = f.cars.find((c) => c[0] === id);
  if (!r) return `<div class="insp-title"><b>Машина ${id}</b><button class="insp-close" data-close>×</button></div><p class="muted">Уехала из сети.</p>`;
  const l = net.links[r[1]];
  const flags = r[5];
  const where = l.kind === "conn" ? `на перекрёстке ${l.junction}: ${MOVE[l.movement] ?? l.movement}` : `полоса ${l.id}`;
  const notes: string[] = [];
  if (flags & FLAG.CRASH) notes.push("<b style='color:#ff4d4d'>попала в ДТП</b>");
  if (flags & FLAG.DISTRACT) notes.push("водитель отвлёкся");
  if (flags & FLAG.RED_RUN) notes.push("проехал на красный");
  return `<div class="insp-title"><b>${KIND[r[6]] ?? "машина"} №${id}</b><button class="insp-close" data-close>×</button></div>
    <div class="facts">
      <span>Скорость</span><b>${fmt(r[4] * 3.6)} км/ч</b>
      <span>Где</span><b>${esc(where)}</b>
      <span>Почему так едет</span><b>${WHY[r[8]] ?? "—"}</b>
      <span>В пути</span><b>${fmt(r[9])} с</b>
      <span>Ждёт</span><b>${fmt(r[10])} с</b>
      ${notes.length ? `<span>Отметки</span><b>${notes.join(", ")}</b>` : ""}
    </div>
    <p class="muted small" style="margin-top:10px">Камера следит за машиной. Щелчок по пустому месту снимает выбор.</p>`;
}

export function pedCard(id: number, f: FrameMsg) {
  const r = f.peds.find((p) => p[0] === id);
  if (!r) return `<div class="insp-title"><b>Пешеход ${id}</b><button class="insp-close" data-close>×</button></div><p class="muted">Дошёл.</p>`;
  const st = ["идёт по тротуару", "ждёт зелёного", "переходит дорогу", "сбит машиной"][r[4]];
  return `<div class="insp-title"><b>Пешеход №${id}</b><button class="insp-close" data-close>×</button></div>
    <div class="facts"><span>Состояние</span><b>${st}</b><span>Шаг</span><b>${r[5] === 1 ? "медленный" : "обычный"}</b></div>`;
}
