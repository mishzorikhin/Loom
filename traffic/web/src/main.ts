// Точка входа: сокет, сборка сцены по сети, кадры, выбор объектов, управление.
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./style.css";
import * as THREE from "three";
import type { FrameMsg, HelloMsg, NetMsg, SimEvent } from "./types";
import { Stage } from "./world/stage";
import { buildRoads } from "./world/roads";
import { Terrain } from "./world/terrain";
import { City } from "./world/city";
import { Signals } from "./world/signals";
import { Actors } from "./world/actors";
import { Overlays } from "./world/overlays";
import { $, carCard, esc, drawSpark, junctionCard, pedCard, renderEvents, renderStats } from "./hud";

const stage = new Stage($("world"));
let world: THREE.Group | null = null;
let signals: Signals | null = null;
let actors: Actors | null = null;
let overlays: Overlays | null = null;
let net: NetMsg["net"] | null = null;
let hello: HelloMsg | null = null;
let last: FrameMsg | null = null;
let events: SimEvent[] = [];
let pick: THREE.Object3D[] = [];
let selected: { kind: "car" | "ped" | "junction"; id: number | string } | null = null;
let follow = true;
let hourSync = true;
let manualHour = 12;
const layers = { strips: true, conflicts: false, heat: false, mini: false, hq: true };
try {
  if (localStorage.getItem("quality") === "low") layers.hq = false;
} catch {
  /* без хранилища — высокое качество */
}

// ---------------------------------------------------------------- сокет

let ws: WebSocket | null = null;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => $("conn").classList.add("ok");
  ws.onclose = () => {
    $("conn").classList.remove("ok");
    setTimeout(connect, 1500);
  };
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.type === "hello") onHello(msg);
    else if (msg.type === "net") onNet(msg);
    else if (msg.type === "frame") onFrame(msg);
    else if (msg.type === "error") toast(msg.message);
  };
}

function send(cmd: Record<string, unknown>) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(cmd));
}

function toast(text: string) {
  const t = $("toast");
  t.textContent = text;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 6000);
}

// ---------------------------------------------------------------- сообщения

function onHello(h: HelloMsg) {
  hello = h;
  const s = h.settings;
  const sel = $("worlds") as HTMLSelectElement;
  sel.innerHTML = h.worlds.map((w) => `<option value="${esc(w.id)}">${esc(w.title)}</option>`).join("");
  sel.value = s.world;
  $("speeds").innerHTML = h.speeds.map((v) => `<button data-speed="${v}">×${String(v).replace(".", ",")}</button>`).join("");
  $("controllers").innerHTML = h.controllers.map((c) => `<button data-ctl="${esc(c.id)}" class="${c.id === s.controller ? "on" : ""}">${esc(c.title)}</button>`).join("");
  const hints: Record<string, string> = {
    fixed: "Фазы идут по кругу с длительностью зелёного от состава фазы.",
    max_pressure: "Каждые 2 с выбирается фаза с наибольшим давлением: очередь на входе минус загрузка выхода.",
    manual: "Фазу переключаете вы: выберите перекрёсток на карте и нажмите «включить».",
    external: "Решения приходят от внешнего агента (среда обучения). Сам контроллер ничего не делает.",
  };
  $("ctl-hint").textContent = hints[s.controller] ?? "";
  setSlider("demand", s.demand, (v) => `${Math.round(v * 100)}%`);
  setSlider("peds", s.peds, (v) => `${Math.round(v * 100)}%`);
  setSlider("timing", s.timing, (v) => `${Math.round(v * 100)}%`);
  $("timing").parentElement!.classList.toggle("low", s.timing < 0.999);
  ($("block-box") as HTMLInputElement).checked = s.block_box;
  ($("seed") as HTMLInputElement).value = String(s.seed);
}

function setSlider(id: string, v: number, label: (v: number) => string) {
  const el = $(id) as HTMLInputElement;
  if (document.activeElement !== el) el.value = String(v);
  $(`${id}-v`).textContent = label(v);
}

function disposeTree(root: THREE.Object3D) {
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    mesh.geometry?.dispose();
    const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : [];
    for (const mat of mats) {
      for (const v of Object.values(mat)) if (v instanceof THREE.Texture) v.dispose();
      mat.dispose();
    }
    (o as THREE.InstancedMesh).dispose?.();
  });
}

function onNet(m: NetMsg) {
  net = m.net;
  if (world) {
    stage.scene.remove(world);
    disposeTree(world);
  }
  world = new THREE.Group();
  const roads = buildRoads(net.render, m.scenery.ground);
  world.add(new Terrain(net.render.bbox, roads.rays).group);
  pick = roads.pick;
  world.add(roads.group);
  const city = new City(m.scenery);
  world.add(city.group);
  world.userData.city = city;
  signals = new Signals(net);
  world.add(signals.group, signals.strips);
  actors = new Actors(net);
  world.add(actors.group);
  overlays = new Overlays(net);
  world.add(overlays.group);
  stage.scene.add(world);
  stage.frame(net.render.bbox, false);
  events = [];
  selected = null;
  closeInspect();
  applyLayers();
  setTimeout(() => $("boot").classList.add("gone"), 300);
}

function onFrame(f: FrameMsg) {
  const now = performance.now() / 1000;
  if (f.full) {
    actors?.reset();
    overlays?.clear();
    events = [];
  }
  last = f;
  actors?.push(f.cars, f.peds, now);
  const freshIds = new Set<number>();
  if (f.events.length) {
    const known = new Set(events.map((e) => e.id));
    const fresh = f.events.filter((e) => !known.has(e.id));
    fresh.forEach((e) => freshIds.add(e.id));
    events.push(...fresh);
    if (events.length > 400) events = events.slice(-400);
    overlays?.add(fresh, now, !f.full);
    if (fresh.length) renderEvents(events, freshIds);
  }
  if (f.full) renderEvents(events, freshIds);
  if (f.series) drawSpark($("spark") as HTMLCanvasElement, f.series);
  renderStats(f);
  $("clock").textContent = f.clock;
  const r = f.run;
  $("play").innerHTML = r.running
    ? `<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.5" height="12" rx="1"/><rect x="9.5" y="2" width="3.5" height="12" rx="1"/></svg>`
    : `<svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z"/></svg>`;
  $("eff").textContent = r.running ? `×${r.effective.toFixed(1).replace(".", ",")}` : "пауза";
  document.querySelectorAll<HTMLButtonElement>("#speeds button").forEach((b) => b.classList.toggle("on", Number(b.dataset.speed) === r.speed));
  $("sim-time").textContent = `день 1 · ${Math.floor(f.t / 60)} мин`;
  if (selected) renderInspect();
}

// ---------------------------------------------------------------- осмотр

function queues() {
  const q = new Map<number, number>();
  if (!last || !net) return q;
  for (const c of last.cars) {
    const l = net.links[c[1]];
    if (l.kind === "lane" && c[4] < 1.5 && l.len - c[2] < 80) q.set(c[1], (q.get(c[1]) ?? 0) + 1);
  }
  return q;
}

function showTab(tab: "control" | "inspect") {
  document.querySelectorAll<HTMLButtonElement>("#left-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll<HTMLElement>("#left [data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== tab));
}

function renderInspect() {
  if (!selected || !last || !net) return;
  const box = $("inspect");
  $("inspect-dot").classList.remove("hidden");
  // не перерисовывать, пока человек вводит длительности
  if (box.contains(document.activeElement) && document.activeElement?.tagName === "INPUT") return;
  if (selected.kind === "junction") {
    const j = net.junctions.find((x) => x.id === selected!.id);
    if (j) box.innerHTML = junctionCard(j, last, net, queues());
  } else if (selected.kind === "car") box.innerHTML = carCard(selected.id as number, last, net);
  else box.innerHTML = pedCard(selected.id as number, last);
}

function closeInspect() {
  const was = selected !== null;
  selected = null;
  $("inspect").innerHTML = `<p class="muted empty">Щёлкните по перекрёстку, машине или пешеходу на карте.</p>`;
  $("inspect-dot").classList.add("hidden");
  if (was) showTab("control");
  overlays?.hideSelect();
}

$("inspect").addEventListener("click", (e) => {
  const t = e.target as HTMLElement;
  if (t.dataset.close !== undefined) closeInspect();
  if (t.dataset.phase !== undefined && selected?.kind === "junction") {
    const num = (id: string) => {
      const v = ($(id) as HTMLInputElement | null)?.value;
      return v === undefined || v === "" ? null : Number(v);
    };
    send({ cmd: "phase", junction: selected.id, phase: Number(t.dataset.phase), yellow: num("d-yellow"), all_red: num("d-allred"), ped_flash: num("d-flash") });
  }
});

// ---------------------------------------------------------------- выбор мышью

const ray = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let downAt = { x: 0, y: 0 };
stage.renderer.domElement.addEventListener("pointerdown", (e) => (downAt = { x: e.clientX, y: e.clientY }));
stage.renderer.domElement.addEventListener("pointerup", (e) => {
  if (Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 5 || !actors) return;
  const rect = stage.renderer.domElement.getBoundingClientRect();
  mouse.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
  ray.setFromCamera(mouse, stage.camera);
  let best: { d: number; sel: typeof selected } | null = null;
  for (const p of actors.pickCars) {
    for (const h of ray.intersectObject(p.mesh)) {
      if (h.instanceId !== undefined && p.ids[h.instanceId] !== undefined && (!best || h.distance < best.d)) {
        best = { d: h.distance, sel: { kind: "car", id: p.ids[h.instanceId] } };
      }
    }
  }
  for (const h of ray.intersectObject(actors.pickPeds.mesh)) {
    if (h.instanceId !== undefined && (!best || h.distance < best.d)) best = { d: h.distance, sel: { kind: "ped", id: actors.pickPeds.ids[h.instanceId] } };
  }
  if (!best) {
    const hits = ray.intersectObjects(pick);
    if (hits.length) best = { d: hits[0].distance, sel: { kind: "junction", id: hits[0].object.userData.id } };
  }
  if (!best) {
    // переход посреди квартала: ближайший к точке на земле
    const g = new THREE.Vector3();
    ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), g);
    const mb = net?.junctions.find((j) => j.kind === "midblock" && Math.hypot(j.pos[0] - g.x, j.pos[1] + g.z) < 9);
    if (mb) best = { d: 0, sel: { kind: "junction", id: mb.id } };
  }
  if (best?.sel) {
    selected = best.sel;
    follow = selected.kind !== "junction";
    if (selected.kind === "junction") {
      const j = net!.junctions.find((x) => x.id === selected!.id)!;
      stage.focus(j.pos[0], j.pos[1], 95);
    }
    showTab("inspect");
    openRail("left");
    renderInspect();
  } else closeInspect();
});

// ---------------------------------------------------------------- управление

document.addEventListener("click", (e) => {
  const t = (e.target as HTMLElement).closest("button") as HTMLButtonElement | null;
  if (!t) return;
  if (t.dataset.tab) showTab(t.dataset.tab as "control" | "inspect");
  if (t.dataset.speed) send({ cmd: "speed", value: Number(t.dataset.speed) });
  if (t.dataset.ctl) send({ cmd: "controller", value: t.dataset.ctl });
  if (t.dataset.view) stage.view(t.dataset.view as "3d" | "top" | "low");
  if (t.dataset.layer) {
    const k = t.dataset.layer as keyof typeof layers;
    layers[k] = !layers[k];
    applyLayers();
  }
});
$("play").addEventListener("click", () => send({ cmd: last?.run.running ? "pause" : "play" }));
for (const id of ["demand", "peds", "timing"]) {
  $(id).addEventListener("input", (e) => {
    const v = Number((e.target as HTMLInputElement).value);
    $(`${id}-v`).textContent = `${Math.round(v * 100)}%`;
    if (id === "timing") $("timing").parentElement!.classList.toggle("low", v < 0.999);
  });
  $(id).addEventListener("change", (e) => send({ cmd: id, value: Number((e.target as HTMLInputElement).value) }));
}
$("worlds").addEventListener("change", (e) => send({ cmd: "load", world: (e.target as HTMLSelectElement).value }));

// колонки: на широком экране сворачиваются (и это запоминается), на узком — выдвижные шторки
const narrow = window.matchMedia("(max-width: 860px)");
function railShown(side: "left" | "right") {
  return narrow.matches ? document.body.classList.contains(`open-${side}`) : !document.body.classList.contains(`no-${side}`);
}
function setRail(side: "left" | "right", show: boolean) {
  if (narrow.matches) {
    document.body.classList.toggle(`open-${side}`, show);
    if (show) document.body.classList.remove(`open-${side === "left" ? "right" : "left"}`);
  } else {
    document.body.classList.toggle(`no-${side}`, !show);
    try {
      localStorage.setItem(`rail-${side}`, show ? "1" : "0");
    } catch {
      /* хранилище недоступно — не запоминаем */
    }
  }
  $(`toggle-${side}`).classList.toggle("off", !railShown(side));
  layoutChanged();
}
function openRail(side: "left" | "right") {
  if (!railShown(side)) setRail(side, true);
}
for (const side of ["left", "right"] as const) {
  try {
    if (localStorage.getItem(`rail-${side}`) === "0") document.body.classList.add(`no-${side}`);
  } catch {
    /* без хранилища — колонки открыты */
  }
  $(`toggle-${side}`).addEventListener("click", () => setRail(side, !railShown(side)));
  $(`toggle-${side}`).classList.toggle("off", !railShown(side));
}
narrow.addEventListener("change", () => {
  document.body.classList.remove("open-left", "open-right");
  layoutChanged();
});

/** Центр кадра — середина свободной области между колонками, а не всего окна. */
function layoutChanged() {
  const r = $("center").getBoundingClientRect();
  stage.setFocusArea(r.left, r.top, r.width, r.height);
}
new ResizeObserver(layoutChanged).observe($("center"));
$("block-box").addEventListener("change", (e) => send({ cmd: "block_box", value: (e.target as HTMLInputElement).checked }));
$("reset").addEventListener("click", () => send({ cmd: "reset", seed: Number(($("seed") as HTMLInputElement).value) || 1 }));
$("events").addEventListener("click", (e) => {
  const li = (e.target as HTMLElement).closest("li");
  if (li) {
    selected = null;
    follow = false;
    stage.focus(Number(li.dataset.x), Number(li.dataset.y), 60);
  }
});
$("hour").addEventListener("input", (e) => {
  hourSync = false;
  manualHour = Number((e.target as HTMLInputElement).value);
  $("hour-sync").classList.remove("on");
});
$("hour-sync").addEventListener("click", () => {
  hourSync = true;
  $("hour-sync").classList.add("on");
});
window.addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).tagName === "INPUT") return;
  if (e.code === "Space") {
    e.preventDefault();
    send({ cmd: last?.run.running ? "pause" : "play" });
  }
  const views: Record<string, "3d" | "top" | "low"> = { Digit1: "3d", Digit2: "top", Digit3: "low" };
  if (views[e.code]) stage.view(views[e.code]);
  const lk: Record<string, keyof typeof layers> = { KeyS: "strips", KeyC: "conflicts", KeyH: "heat", KeyM: "mini", KeyQ: "hq" };
  if (lk[e.code]) {
    layers[lk[e.code]] = !layers[lk[e.code]];
    applyLayers();
  }
  if (e.code === "Escape") closeInspect();
  if (e.code === "BracketLeft") setRail("left", !railShown("left"));
  if (e.code === "BracketRight") setRail("right", !railShown("right"));
  if (e.code === "KeyP") {
    const show = !(railShown("left") || railShown("right"));
    setRail("left", show);
    setRail("right", show);
  }
});

function applyLayers() {
  document.querySelectorAll<HTMLButtonElement>("#layers button").forEach((b) => b.classList.toggle("on", layers[b.dataset.layer as keyof typeof layers]));
  if (signals) signals.strips.visible = layers.strips;
  if (overlays) {
    overlays.conflicts.visible = layers.conflicts;
    overlays.heat.visible = layers.heat;
  }
  stage.setMiniature(layers.mini);
  if (stage.quality !== (layers.hq ? "high" : "low")) {
    stage.setQuality(layers.hq ? "high" : "low");
    try {
      localStorage.setItem("quality", layers.hq ? "high" : "low");
    } catch {
      /* не запоминаем */
    }
  }
}

// ---------------------------------------------------------------- цикл отрисовки

let prevT = performance.now() / 1000;
function tick() {
  requestAnimationFrame(tick);
  const now = performance.now() / 1000;
  const dt = Math.min(0.1, now - prevT);
  prevT = now;
  const hour = hourSync && last ? last.hour : manualHour;
  if (hourSync && last) ($("hour") as HTMLInputElement).value = String(last.hour);
  stage.setHour(hour);
  const sunEl = $("sun");
  const n = stage.day.night;
  sunEl.style.background = n > 0.5 ? "#c9d4ff" : "#ffd27a";
  sunEl.style.boxShadow = n > 0.5 ? "0 0 10px #9fb0ff" : "0 0 12px #ffcf6a";
  if (world) (world.userData.city as City).update(stage.day);
  if (actors && last) {
    actors.update(now, stage.day);
    signals?.update(last.signals, now);
    overlays?.update(now, last.t);
    if (selected && selected.kind !== "junction") {
      const p = selected.kind === "car" ? actors.carPos.get(selected.id as number) : actors.pedPos.get(selected.id as number);
      if (p) {
        overlays?.setSelect(p.x, p.y, selected.kind === "car" ? 3.6 : 1.2);
        if (follow) stage.follow(p.x, p.y);
      }
    } else if (selected?.kind === "junction" && net) {
      const j = net.junctions.find((x) => x.id === selected!.id);
      if (j) overlays?.setSelect(j.pos[0], j.pos[1], j.kind === "midblock" ? 8 : 26);
    }
  }
  stage.render(dt);
}

stage.resize();
connect();
tick();
void hello;

// для проверок скриншотами и отладки из консоли
(window as unknown as { __tsim: unknown }).__tsim = { stage, send, layers, applyLayers, actors: () => actors };
