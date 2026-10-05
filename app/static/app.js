/* Ошибки страницы уходят в журнал сервера (`client.*`): консоль браузера агенту недоступна. */
const clientLog = (() => {
  let windowStart = 0;
  let sent = 0;
  return (kind, data) => {
    const now = Date.now();
    if (now - windowStart > 60000) {
      windowStart = now;
      sent = 0;
    }
    sent += 1;
    if (sent > 10) return;
    try {
      fetch("/api/clientlog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, ...data }),
        keepalive: true,
      }).catch(() => {});
    } catch (err) { /* журнал не должен ломать страницу */ }
  };
})();

window.addEventListener("error", (event) => {
  clientLog("error", {
    message: String(event.message || "").slice(0, 600), source: String(event.filename || "").slice(-200),
    line: event.lineno || null, col: event.colno || null, stack: String((event.error && event.error.stack) || "").slice(0, 1500),
  });
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason || {};
  clientLog("rejection", { message: String(reason.message || reason).slice(0, 600), stack: String(reason.stack || "").slice(0, 1500) });
});

const STATUS = {
  idle: "стоит",
  running: "идёт",
  paused: "пауза",
  error: "ошибка модели",
};
const AGENT = { client: "гость", staff: "бариста", manager: "управляющий", verdict: "вердикт гостя", critic: "критик", queue: "очередь", narrator: "рассказчик", director: "режиссёр" };

const openCalls = new Set();
const openWeeks = new Set();
const visitCache = new Map();
const callCache = new Map();
const loadingVisits = new Set();
let selectedGuest = null;
let focusVisit = null;
let showReviews = false;
let pinnedCall = null;
const seen = new Map();
let seenDay = null;
let firstLoad = true;
let weekSeen = false;
let lastWeekId = 0;
let flashItems = new Set();
let flashUntil = 0;
let dismissedDay = null;
let snap = null;
let snapAt = 0;
let loading = false;

const rub = (n) => new Intl.NumberFormat("ru-RU").format(n || 0) + " ₽";
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[ch]));

let queued = false;

let applying = false;
let pending = null;

/* Снимок приходит по сокету при каждом изменении. Если новый пришёл, пока рисуется прошлый, рисуется только последний. */
async function applySnapshot(data) {
  pending = data;
  if (applying) return;
  applying = true;
  try {
    while (pending) {
      snap = pending;
      pending = null;
      snapAt = performance.now();
      if (selectedGuest && !snap.clients.some((client) => client.id === selectedGuest)) {
        selectedGuest = null;
      }
      if (snap.current_visit) visitCache.set(snap.current_visit.id, snap.current_visit);
      await refreshOpen();
      render();
      detectEvents();
    }
  } catch (err) {
    clientLog("render", { message: String(err && err.message ? err.message : err).slice(0, 300), stack: String((err && err.stack) || "").slice(0, 1200) });
  } finally {
    applying = false;
  }
}

/* Запасной путь: снимок обычным запросом, пока сокет не поднялся. */
async function load() {
  try {
    const res = await fetch("/api/snapshot");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await applySnapshot(await res.json());
  } catch (err) {
    clientLog("fetch", { message: String(err && err.message ? err.message : err).slice(0, 300) });
  }
}

let socket = null;
let retries = 0;
let rpcId = 0;
const waiting = new Map();

function connect() {
  socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  socket.onopen = () => {
    retries = 0;
    setLink(true);
  };
  socket.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (err) {
      return;
    }
    if (msg.type === "snapshot") {
      applySnapshot(msg.data);
    } else if (msg.type === "reply" && waiting.has(msg.id)) {
      const done = waiting.get(msg.id);
      waiting.delete(msg.id);
      done(msg);
    }
  };
  socket.onclose = () => {
    setLink(false);
    waiting.forEach((done) => done({ ok: false, error: "Нет связи" }));
    waiting.clear();
    retries += 1;
    setTimeout(connect, Math.min(5000, 400 * 2 ** retries));
  };
  socket.onerror = () => {
    try {
      socket.close();
    } catch (err) { /* уже закрыт */ }
  };
}

/* Команда по сокету: ответ приходит с тем же id. Без связи сразу «Нет связи». */
function rpc(cmd, payload = {}) {
  return new Promise((resolve) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      resolve({ ok: false, error: "Нет связи" });
      return;
    }
    rpcId += 1;
    const id = rpcId;
    waiting.set(id, resolve);
    socket.send(JSON.stringify({ id, cmd, ...payload }));
    setTimeout(() => {
      if (waiting.delete(id)) resolve({ ok: false, error: "Нет ответа" });
    }, 90000);
  });
}

setInterval(() => {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ cmd: "ping" }));
}, 20000);

function setLink(ok) {
  const banner = document.getElementById("link");
  if (banner) banner.hidden = ok;
}

async function refreshOpen() {
  await Promise.all([...openCalls].map(async (id) => {
    const res = await fetch(`/api/llm/${id}`);
    if (res.ok) callCache.set(id, await res.json());
  }));
}

function formatClock(mins) {
  const total = Math.max(0, Math.floor(mins * 60));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function liveMinutes() {
  let mins = Number(snap.run.clock_min) || 0;
  if (snap.run.status === "running") {
    const speed = Number(snap.run.speed || 1);
    mins += ((performance.now() - snapAt) / 1000) * (snap.run.thinking ? Math.min(speed, 1) : speed);
  }
  return mins;
}

function render() {
  const began = performance.now();
  renderAll();
  const took = performance.now() - began;
  if (took > 150) clientLog("slow", { message: "render", ms: Math.round(took) });
}

function renderAll() {
  const run = snap.run;
  document.getElementById("place").textContent = snap.venue.name;
  document.getElementById("viewers-n").textContent = snap.viewers || 1;
  document.getElementById("viewers").title = `Сколько вкладок смотрят эту симуляцию: ${snap.viewers || 1}`;
  const day = document.getElementById("daylabel");
  const clock = document.getElementById("clockline");
  if (!run.day) {
    day.textContent = "Смена закрыта";
    clock.textContent = "08:00:00";
  } else {
    day.textContent = `День ${run.day}`;
    clock.textContent = formatClock(liveMinutes());
  }
  const seconds = 60 / Number(run.speed || 1);
  document.getElementById("pace").textContent = seconds === 60 ? "час за минуту" : `час за ${seconds} с`;
  paintDay();
  const status = document.getElementById("status");
  status.textContent = STATUS[run.status] || run.status;
  status.className = `status ${run.status}`;
  const banner = document.getElementById("banner");
  if (run.message) {
    banner.hidden = false;
    banner.textContent = run.message;
  } else {
    banner.hidden = true;
  }
  const busy = run.status === "running";
  document.getElementById("step").disabled = busy;
  document.getElementById("day").disabled = busy;
  document.getElementById("auto").disabled = busy;
  document.getElementById("pause").disabled = !busy;
  const speed = Number(run.speed || 1);
  document.querySelectorAll("#speed [data-speed]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(Number(btn.dataset.speed) === speed));
  });
  document.querySelector("#speed p span").textContent = speed === 1 ? "час за минуту" : `час за ${60 / speed} с`;
  const box = document.getElementById("monitor-box");
  if (run.status === "error") box.open = true;
  const till = document.getElementById("till");
  const today = snap.summary && snap.summary.today;
  till.textContent = rub(today ? today.revenue : 0);
  fillSettings();
  const health = snap.llm_health || {};
  document.getElementById("llm-dot").className = `dot ${health.ok ? "ok" : "bad"}`;
  document.getElementById("llm-brief").textContent = `${snap.llm.model} · ${health.ok ? "на связи" : "недоступна"}`;
  renderWorld();
  renderEventbar();
  renderReviews();
  renderRibbon();
  renderDots();
  renderDayCard();
  renderChats();
  renderManager();
  renderMonitor();
}

function paintDay() {
  const span = snap.run.close_min - snap.run.open_min;
  const done = snap.run.day ? (liveMinutes() - snap.run.open_min) / span : 0;
  document.getElementById("dayfill").style.width = `${Math.min(100, Math.max(0, done * 100)).toFixed(1)}%`;
}

function fillSettings() {
  const map = {
    "llm-url": snap.llm.base_url,
    "llm-model": snap.llm.model,
    "llm-timeout": snap.llm.timeout,
    "critic-url": snap.llm.critic_base_url,
    "critic-model": snap.llm.critic_model,
  };
  document.getElementById("llm-key").placeholder = snap.llm.has_key ? "задан, пусто — не менять" : "не задан";
  for (const [id, value] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (document.activeElement !== el) el.value = value;
  }
}

function healthLine() {
  const health = snap.llm_health || {};
  const mark = health.ok ? "модель на связи" : "модель недоступна";
  return `${mark}: ${health.detail || ""}. Запросы идут на ${snap.llm.base_url}, модель ${snap.llm.model}.`;
}

function itemName(visit) {
  if (visit.item_name) return visit.item_name;
  const id = visit.served_item_id || visit.requested_item_id;
  const item = (snap.menu || []).find((row) => row.id === id);
  return item ? item.name : "";
}

function bill(visit) {
  if (visit.status === "served") {
    const name = itemName(visit);
    return name ? `${name}, ${rub(visit.price)}` : rub(visit.price);
  }
  if (visit.status === "refused") return "Ушёл без заказа";
  if (visit.status === "left") return "Не дождался очереди";
  if (visit.status === "failed") return visit.outcome_note || "Разговор оборвался";
  return "";
}

function bubbles(visit) {
  const full = visit.lines ? visit : visitCache.get(visit.id);
  if (!full || !full.lines) return `<p class="pending">Открываю разговор…</p>`;
  if (!full.lines.length) return `<p class="pending">Пока молчат.</p>`;
  const guestName = full.client_name || visit.client_name;
  const staffName = full.staff_name || visit.staff_name;
  return full.lines.map((line) => {
    const guest = line.role === "client";
    const who = guest ? guestName : staffName;
    const think = line.action === "verdict";
    const tag = think ? `${who} про себя` : line.action === "queue" ? `${who} в очереди` : line.action === "left" ? `${who} уходит` : who;
    return `<div class="bubble ${guest ? "from-guest" : "from-staff"}${think ? " think" : ""}"><span class="speaker">${esc(tag)}</span><p>${esc(line.text)}</p></div>`;
  }).join("");
}

function verdictLine(v) {
  if (!v || !v.liked) return "";
  const back = { yes: "вернётся", maybe: "может вернуться", no: "не вернётся" }[v.intent] || "";
  const when = v.intent !== "no" && v.return_days ? `, через ${v.return_days} дн.` : "";
  const friends = v.recommend ? " · посоветует знакомым" : "";
  return `<p class="verdict">Вердикт гостя: ${v.liked}/5 · ${back}${when}${friends}</p>`;
}

function moodLine(v) {
  if (!v || !v.mood) return "";
  const guestWas = `${faceIcon(v.mood)}${esc(v.mood)}`;
  const guestNow = v.mood_after && v.mood_after !== v.mood ? ` → ${faceIcon(v.mood_after)}${esc(v.mood_after)}` : "";
  const staff = v.staff_mood ? ` · ${esc(v.staff_name || "бариста")}: ${faceIcon(v.staff_mood)}${esc(v.staff_mood)}` : "";
  const waited = v.wait_min >= 5 ? ` · ждал ${Math.round(v.wait_min)} мин` : "";
  return `<p class="moods">${esc(v.client_name || "Гость")}: ${guestWas}${guestNow}${staff}${waited}</p>`;
}

const ISSUE = {
  echo: "пересказ", price_named: "названа цена", second_item: "вторая позиция", mood_named: "настроение вслух",
  contradiction: "реплика против действия", nonsense: "бессмыслица", off_menu: "нет в меню", wrong_name: "чужое имя",
};

function criticLine(v) {
  if (!v || !v.critic_score) return "";
  let issues = [];
  try {
    issues = JSON.parse(v.critic_json || "[]");
  } catch (err) {
    issues = [];
  }
  const chips = issues.map((row) => `<span class="chip ${row.severity === "high" ? "high" : ""}" title="${esc(row.note || "")}">${esc(ISSUE[row.code] || row.code)}${row.line ? ` · реплика ${row.line}` : ""}</span>`).join("");
  return `<p class="critic">Критик: ${v.critic_score}/5 ${chips || "<span class=\"chip ok\">замечаний нет</span>"}</p>`;
}

function chatCard(visit, scene) {
  const full = visitCache.get(visit.id) || visit;
  const guest = full.client_name || visit.client_name;
  const staff = full.staff_name || visit.staff_name;
  const live = snap.current_visit && snap.current_visit.id === visit.id && snap.run.phase;
  const typing = live ? `<p class="typing">${esc(snap.run.phase)}</p>` : "";
  const foot = bill(full.lines ? full : visit);
  const again = visit.is_return ? ", снова" : "";
  return `<article class="chat${scene ? " scene-chat" : ""}" id="chat-${visit.id}">
    <header class="chat-head">
      <strong>${esc(guest)}</strong>
      <span>День ${visit.day}, ${esc(visit.clock)}${esc(again)}</span>
      <strong>${esc(staff)}</strong>
    </header>
    ${moodLine(full)}
    <div class="thread">${bubbles(visit)}${typing}</div>
    ${foot ? `<p class="bill">${esc(foot)}</p>` : ""}
    ${verdictLine(full)}
    ${criticLine(full)}
  </article>`;
}

function otherChats() {
  if (!selectedGuest) return [];
  const client = snap.clients.find((row) => row.id === selectedGuest);
  if (!client) return [];
  return [...(client.history || [])].reverse().map((visit) => ({ ...visit, client_name: client.name }));
}

function wantLines(ids) {
  const need = ids.filter((id) => !visitCache.has(id) && !loadingVisits.has(id));
  if (!need.length) return;
  need.forEach((id) => loadingVisits.add(id));
  Promise.all(need.map(async (id) => {
    const res = await fetch(`/api/visits/${id}`);
    if (res.ok) visitCache.set(id, await res.json());
  })).finally(() => {
    need.forEach((id) => loadingVisits.delete(id));
    if (snap) render();
  });
}

const VB = { x: 0, y: 0, w: 700, h: 430 };
const TW = 36;
const TH = 18;
const ROOM_W = 8;
const ROOM_D = 8;
const WALL = 96;
const SKIN = ["#f3c9a8", "#e8b48c", "#d39a72", "#b97d56", "#8f5a3a"];
const SHIRTS = ["#e25b4a", "#3d8fd4", "#e39b12", "#7b5ea7", "#2f9e6b", "#d46aa6", "#d97b2a", "#4c6eb1"];
const PANTS = ["#34404f", "#4a4036", "#3b3a4a", "#53483a", "#2f4a45"];
const HAIR = ["#3a241c", "#6b3a22", "#1e1a17", "#8a5a32", "#4a3028", "#c9a15a"];
const STAFF_AT = { anya: [2.55, 0.45], mark: [5.3, 0.45] };
const STAFF_LOOK = {
  anya: { shirt: "#c4473a", hair: "#5c3318", accent: "#f0a73a", skin: SKIN[1], style: 1 },
  mark: { shirt: "#2f7d72", hair: "#241c18", accent: "#f6efe2", skin: SKIN[2], style: 0 },
};
const COUNTER_GUEST = [4.05, 2.5];
const MGR_AT = [1.5, 2.9];
const MGR_LOOK = { shirt: "#5b4b8a", hair: "#8d8d8d", skin: SKIN[0], pants: "#2f3a45", style: 0 };
const TABLES = [{ x: 1.3, y: 4.5 }, { x: 6.0, y: 4.9 }, { x: 3.4, y: 6.1 }];
const SEATS = [
  ...TABLES.map((t) => ({ at: [t.x + 0.55, t.y - 0.5], face: "n" })),
  ...TABLES.map((t) => ({ at: [t.x - 0.5, t.y + 0.55], face: "w" })),
];
const SEAT_Z = 10;
const SCALE = 1.3;

function iso(x, y, z = 0) {
  return [(x - y) * TW, (x + y) * TH - z];
}

function pt(p) {
  const [sx, sy] = iso(p[0], p[1], p[2] || 0);
  return `${sx.toFixed(1)},${sy.toFixed(1)}`;
}

function face(points, fill, alpha) {
  const op = alpha === undefined ? "" : ` fill-opacity="${alpha}"`;
  return `<polygon points="${points.map(pt).join(" ")}" fill="${fill}"${op} stroke="${fill}" stroke-opacity="${alpha === undefined ? 1 : alpha}" stroke-width="0.7" stroke-linejoin="round"/>`;
}

function seg(a, b, color, width = 1) {
  const [x1, y1] = iso(a[0], a[1], a[2] || 0);
  const [x2, y2] = iso(b[0], b[1], b[2] || 0);
  return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
}

function box(x, y, w, d, h, top, south, east, z0 = 0) {
  const x1 = x + w;
  const y1 = y + d;
  const z1 = z0 + h;
  return [
    face([[x, y1, z0], [x1, y1, z0], [x1, y1, z1], [x, y1, z1]], south),
    face([[x1, y, z0], [x1, y1, z0], [x1, y1, z1], [x1, y, z1]], east),
    face([[x, y, z1], [x1, y, z1], [x1, y1, z1], [x, y1, z1]], top),
  ].join("");
}

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `#${pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, "0")).join("")}`;
}
const shade = (c, t) => mix(c, "#000000", t);
const lighten = (c, t) => mix(c, "#ffffff", t);

function hashOf(name) {
  let n = 0;
  for (const ch of name) n = (n * 31 + ch.charCodeAt(0)) % 9973;
  return n;
}

function looksOf(name) {
  const h = hashOf(name);
  return {
    shirt: SHIRTS[h % SHIRTS.length],
    hair: HAIR[(h >> 2) % HAIR.length],
    skin: SKIN[(h >> 3) % SKIN.length],
    pants: PANTS[(h >> 1) % PANTS.length],
    style: h % 3,
  };
}

function frameRoom() {
  const pts = [
    [0, 0, 0], [ROOM_W, 0, 0], [0, ROOM_D, 0], [ROOM_W, ROOM_D, 0],
    [-0.28, -0.28, WALL], [ROOM_W, -0.28, WALL], [-0.28, ROOM_D, WALL],
    [0, ROOM_D, -16], [ROOM_W, ROOM_D, -16], [ROOM_W, 0, -16],
  ];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  pts.forEach(([x, y, z]) => {
    const [sx, sy] = iso(x, y, z);
    minX = Math.min(minX, sx);
    minY = Math.min(minY, sy);
    maxX = Math.max(maxX, sx);
    maxY = Math.max(maxY, sy);
  });
  VB.x = minX - 28;
  VB.y = minY - 14;
  VB.w = (maxX - minX) + 56;
  VB.h = (maxY - minY) + 14 + 22;
}

/* ---------- свет суток ---------- */

const LIGHT = [
  [480, "#cfe6ee", 0.35, 0.06, 1],
  [600, "#a8dcf4", 0.6, 0, 1],
  [780, "#8fd1f2", 0.75, 0, 1],
  [960, "#a9d4ec", 0.6, 0, 1],
  [1080, "#f6c58f", 0.5, 0.18, 0.97],
  [1140, "#f08f6a", 0.3, 0.3, 0.9],
  [1200, "#3a3f6e", 0, 0.2, 0.72],
];

function daylight(mins) {
  const m = Math.min(1200, Math.max(480, mins));
  let i = 0;
  while (i < LIGHT.length - 2 && m > LIGHT[i + 1][0]) i += 1;
  const a = LIGHT[i];
  const b = LIGHT[i + 1];
  const t = (m - a[0]) / (b[0] - a[0]);
  const lerp = (p, q) => p + (q - p) * t;
  return {
    sky: mix(a[1], b[1], t),
    sun: lerp(a[2], b[2]),
    filter: `sepia(${lerp(a[3], b[3]).toFixed(2)}) brightness(${lerp(a[4], b[4]).toFixed(2)})`,
  };
}

let lightKey = "";

function applyLight(force) {
  if (!snap) return;
  const mins = snap.run.day ? liveMinutes() : 540;
  const key = String(Math.round(mins / 4));
  if (!force && key === lightKey) return;
  lightKey = key;
  const light = daylight(mins);
  const room = document.getElementById("room");
  room.style.setProperty("--sky", light.sky);
  room.style.setProperty("--sun", light.sun.toFixed(2));
  const lit = document.getElementById("lit");
  if (lit) lit.style.filter = light.filter;
}

/* ---------- комната ---------- */

function floorSvg() {
  const out = [];
  const tones = ["#dba76b", "#d6a064", "#dcaa70", "#d39d62"];
  for (let y = 0; y < ROOM_D; y += 1) {
    const start = [0, 2.2, 1, 3.1][y % 4];
    const cuts = [0];
    for (let x = start; x < ROOM_W; x += 3.4) if (x > 0.4) cuts.push(x);
    cuts.push(ROOM_W);
    cuts.sort((a, b) => a - b);
    for (let i = 0; i < cuts.length - 1; i += 1) {
      const tone = tones[(y * 5 + i * 3 + (y % 2)) % tones.length];
      out.push(face([[cuts[i], y, 0], [cuts[i + 1], y, 0], [cuts[i + 1], y + 1, 0], [cuts[i], y + 1, 0]], tone));
      out.push(seg([cuts[i], y, 0], [cuts[i], y + 1, 0], "#b9854e", 0.8));
    }
    out.push(seg([0, y + 1, 0], [ROOM_W, y + 1, 0], "#b9854e", 0.8));
  }
  return out.join("");
}

function rugSvg() {
  const x0 = 2.4;
  const x1 = 5.9;
  const y0 = 1.95;
  const y1 = 3.2;
  return face([[x0, y0, 0.2], [x1, y0, 0.2], [x1, y1, 0.2], [x0, y1, 0.2]], "#2f6f62")
    + face([[x0 + 0.12, y0 + 0.12, 0.3], [x1 - 0.12, y0 + 0.12, 0.3], [x1 - 0.12, y1 - 0.12, 0.3], [x0 + 0.12, y1 - 0.12, 0.3]], "#e9d7b0")
    + face([[x0 + 0.28, y0 + 0.28, 0.4], [x1 - 0.28, y0 + 0.28, 0.4], [x1 - 0.28, y1 - 0.28, 0.4], [x0 + 0.28, y1 - 0.28, 0.4]], "#3e8374");
}

function sunSvg() {
  return `<g style="opacity:var(--sun)">${face([[2.6, 0.1, 0.5], [5.4, 0.1, 0.5], [6.6, 2.3, 0.5], [4.0, 2.3, 0.5]], "#fff6d2", 0.3)}</g>`;
}

function shadowSvg(poly) {
  return face(poly.map(([x, y]) => [x, y, 0.3]), "#3a1c08", 0.12);
}

function wallsSvg() {
  const back = box(-0.28, -0.28, ROOM_W + 0.28, 0.28, WALL, "#e9d6b8", "#f3e4cb", "#dcc7a6");
  const left = box(-0.28, 0, 0.28, ROOM_D, WALL, "#ecd9bc", "#e4cfae", "#ecdbc0");
  const wain = [
    face([[0, 0.02, 0], [ROOM_W, 0.02, 0], [ROOM_W, 0.02, 34], [0, 0.02, 34]], "#3d7d6c"),
    face([[0, 0.03, 34], [ROOM_W, 0.03, 34], [ROOM_W, 0.03, 38], [0, 0.03, 38]], "#e6d2ae"),
    face([[0.02, 0, 0], [0.02, ROOM_D, 0], [0.02, ROOM_D, 34], [0.02, 0, 34]], "#33695a"),
    face([[0.03, 0, 34], [0.03, ROOM_D, 34], [0.03, ROOM_D, 38], [0.03, 0, 38]], "#d9c39d"),
  ];
  for (let x = 0.8; x < ROOM_W; x += 1.6) wain.push(seg([x, 0.03, 4], [x, 0.03, 31], "rgba(0,0,0,.14)", 1));
  for (let y = 0.8; y < ROOM_D; y += 1.6) wain.push(seg([0.03, y, 4], [0.03, y, 31], "rgba(0,0,0,.16)", 1));
  wain.push(seg([0, 0.02, 0.5], [ROOM_W, 0.02, 0.5], "#2b5c4e", 1.2));
  const slab = [
    face([[0, ROOM_D, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [0, ROOM_D, 0]], "#8c5b36"),
    face([[ROOM_W, 0, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0]], "#6d4527"),
    seg([0, ROOM_D, 0], [ROOM_W, ROOM_D, 0], "#c99560", 1.6),
    seg([ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0], "#a8744a", 1.6),
  ];
  return slab.join("") + floorSvg() + back + left + wain.join("");
}

function windowSvg() {
  const x0 = 2.25;
  const x1 = 5.75;
  const y = 0.03;
  const parts = [
    face([[x0 - 0.12, y, 28], [x1 + 0.12, y, 28], [x1 + 0.12, y, 80], [x0 - 0.12, y, 80]], "#f7efe0"),
    `<polygon points="${[[x0, y + 0.02, 33], [x1, y + 0.02, 33], [x1, y + 0.02, 76], [x0, y + 0.02, 76]].map(pt).join(" ")}" style="fill:var(--sky)"/>`,
    face([[x0 + 0.1, y + 0.025, 33], [x0 + 0.9, y + 0.025, 33], [x0 + 0.9, y + 0.025, 49], [x0 + 0.1, y + 0.025, 49]], "#a9c4b0", 0.85),
    face([[x0 + 0.9, y + 0.025, 33], [x0 + 1.9, y + 0.025, 33], [x0 + 1.9, y + 0.025, 43], [x0 + 0.9, y + 0.025, 43]], "#bcd1b6", 0.85),
    face([[x0 + 2.0, y + 0.025, 33], [x0 + 3.1, y + 0.025, 33], [x0 + 3.1, y + 0.025, 52], [x0 + 2.0, y + 0.025, 52]], "#b19a82", 0.8),
    face([[x0 + 2.0, y + 0.026, 52], [x0 + 3.1, y + 0.026, 52], [x0 + 2.55, y + 0.026, 58]], "#c9553d", 0.85),
    face([[x0 + 3.1, y + 0.025, 33], [x1, y + 0.025, 33], [x1, y + 0.025, 41], [x0 + 3.1, y + 0.025, 41]], "#8fb98f", 0.85),
    face([[x0, y + 0.03, 33], [x1, y + 0.03, 33], [x1, y + 0.03, 46], [x0, y + 0.03, 46]], "#ffffff", 0.22),
    face([[3.93, y + 0.04, 33], [4.07, y + 0.04, 33], [4.07, y + 0.04, 76], [3.93, y + 0.04, 76]], "#f7efe0"),
    face([[x0, y + 0.04, 53.5], [x1, y + 0.04, 53.5], [x1, y + 0.04, 55.5], [x0, y + 0.04, 55.5]], "#f7efe0"),
    box(x0 - 0.2, 0.02, x1 - x0 + 0.4, 0.2, 3, "#f9f2e4", "#d9c8a6", "#bfae8c", 25),
  ];
  const stripes = 9;
  const sw = (x1 - x0 + 0.4) / stripes;
  for (let i = 0; i < stripes; i += 1) {
    const a = x0 - 0.2 + i * sw;
    const b = a + sw;
    parts.push(face([[a, y + 0.05, 90], [b, y + 0.05, 90], [b, y + 0.05, 82], [(a + b) / 2, y + 0.05, 77.5], [a, y + 0.05, 82]], i % 2 ? "#f6e8d3" : "#c9553d"));
  }
  parts.push(seg([x0 - 0.2, y + 0.05, 90], [x1 + 0.2, y + 0.05, 90], "#8f3a28", 1.4));
  return parts.join("");
}

function wallDecorSvg() {
  const parts = [];
  // полка с посудой слева от окна
  parts.push(box(0.4, 0.02, 1.5, 0.3, 2.4, "#c98a4b", "#a96d36", "#8a5629", 56));
  [0.6, 0.95, 1.3].forEach((x, i) => {
    parts.push(box(x, 0.08, 0.2, 0.2, 7, "#fffaf0", i === 1 ? "#e8b25c" : "#efe6d4", "#cfc4ae", 58.4));
  });
  parts.push(box(1.62, 0.08, 0.24, 0.2, 11, "#8a5a33", "#6b4426", "#523319", 58.4));
  // рамки справа от окна
  parts.push(face([[6.2, 0.03, 50], [7.1, 0.03, 50], [7.1, 0.03, 80], [6.2, 0.03, 80]], "#7b4a2a"));
  parts.push(face([[6.28, 0.04, 54], [7.02, 0.04, 54], [7.02, 0.04, 76], [6.28, 0.04, 76]], "#f2dcae"));
  parts.push(face([[6.4, 0.05, 58], [6.9, 0.05, 58], [6.9, 0.05, 66], [6.4, 0.05, 66]], "#3f8f7a"));
  parts.push(face([[6.55, 0.05, 66], [6.75, 0.05, 66], [6.75, 0.05, 72], [6.55, 0.05, 72]], "#c9553d"));
  parts.push(face([[7.3, 0.03, 56], [7.8, 0.03, 56], [7.8, 0.03, 76], [7.3, 0.03, 76]], "#7b4a2a"));
  parts.push(face([[7.36, 0.04, 60], [7.74, 0.04, 60], [7.74, 0.04, 72], [7.36, 0.04, 72]], "#f0a73a"));
  // левая стена: дверь и две рамки
  parts.push(face([[0.03, 5.15, 0], [0.03, 6.65, 0], [0.03, 6.65, 74], [0.03, 5.15, 74]], "#6a3f22"));
  parts.push(face([[0.04, 5.25, 0], [0.04, 6.55, 0], [0.04, 6.55, 70], [0.04, 5.25, 70]], "#b3733f"));
  parts.push(face([[0.05, 5.4, 36], [0.05, 6.4, 36], [0.05, 6.4, 62], [0.05, 5.4, 62]], "#a8dcf4"));
  parts.push(face([[0.05, 5.4, 36], [0.05, 6.4, 36], [0.05, 6.4, 46], [0.05, 5.4, 46]], "#ffffff", 0.25));
  parts.push(face([[0.05, 5.4, 8], [0.05, 6.4, 8], [0.05, 6.4, 30], [0.05, 5.4, 30]], "#9a6234"));
  parts.push(face([[0.06, 5.66, 38], [0.06, 6.14, 38], [0.06, 6.14, 47], [0.06, 5.66, 47]], "#2b1d14"));
  parts.push(`<polygon points="${[[0.07, 5.7, 39.2], [0.07, 6.1, 39.2], [0.07, 6.1, 45.8], [0.07, 5.7, 45.8]].map(pt).join(" ")}" style="fill:var(--sign)"/>`);
  parts.push(face([[0.06, 5.36, 32], [0.06, 5.46, 32], [0.06, 5.46, 36], [0.06, 5.36, 36]], "#e8c27a"));
  parts.push(face([[0.03, 1.2, 46], [0.03, 2.6, 46], [0.03, 2.6, 78], [0.03, 1.2, 78]], "#7b4a2a"));
  parts.push(face([[0.04, 1.3, 50], [0.04, 2.5, 50], [0.04, 2.5, 74], [0.04, 1.3, 74]], "#f2dcae"));
  parts.push(face([[0.05, 1.45, 54], [0.05, 2.35, 54], [0.05, 2.35, 62], [0.05, 1.45, 62]], "#c9553d"));
  parts.push(face([[0.05, 1.45, 62], [0.05, 2.35, 62], [0.05, 2.35, 70], [0.05, 1.45, 70]], "#3f8f7a"));
  parts.push(face([[0.03, 3.3, 52], [0.03, 4.3, 52], [0.03, 4.3, 76], [0.03, 3.3, 76]], "#2b1d14"));
  parts.push(face([[0.04, 3.38, 56], [0.04, 4.22, 56], [0.04, 4.22, 72], [0.04, 3.38, 72]], "#26302c"));
  [60, 65, 69].forEach((z, i) => parts.push(seg([0.05, 3.5, z], [0.05, 3.9 + i * 0.08, z], "rgba(250,244,228,.7)", 1.2)));
  return parts.join("");
}

const DOOR_QUAD = [[0.06, 5.25, 0], [0.06, 6.55, 0], [0.06, 6.55, 70], [0.06, 5.25, 70]];

/* Распахнутая дверь: вместо створки видна улица. Показывается, пока кто-то проходит. */
function doorHoleSvg() {
  return face(DOOR_QUAD, "#b9d9a4")
    + face([[0.07, 5.25, 0], [0.07, 6.55, 0], [0.07, 6.55, 26], [0.07, 5.25, 26]], "#e3dcc8")
    + face([[0.07, 5.25, 44], [0.07, 6.55, 44], [0.07, 6.55, 70], [0.07, 5.25, 70]], "#a8d8f0")
    + face([[0.08, 5.2, 0], [0.08, 5.32, 0], [0.08, 5.32, 70], [0.08, 5.2, 70]], "#6a3f22");
}

function plantSvg(x, y) {
  const [sx, sy] = iso(x + 0.2, y + 0.2, 14);
  const leaf = (dx, dy, rx, ry, rot, fill) => `<ellipse cx="${dx}" cy="${dy}" rx="${rx}" ry="${ry}" fill="${fill}" transform="rotate(${rot} ${dx} ${dy})"/>`;
  return box(x, y, 0.4, 0.4, 14, "#b9694a", "#a15538", "#7f4129")
    + `<g transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)})">`
    + leaf(-9, -12, 4, 11, -35, "#2f7d42") + leaf(9, -12, 4, 11, 35, "#2f7d42")
    + leaf(-4, -18, 4, 12, -12, "#3e9a56") + leaf(4, -18, 4, 12, 12, "#57b56e")
    + leaf(0, -22, 4, 12, 0, "#3e9a56")
    + "</g>";
}

function deskSvg() {
  return box(0.35, 1.0, 0.75, 1.5, 17, "#e9cf9d", "#a8703f", "#8a582f")
    + box(0.5, 1.35, 0.4, 0.5, 1.2, "#d7dbde", "#3e474e", "#2f363c", 17)
    + box(0.46, 1.35, 0.04, 0.5, 11, "#2a3338", "#3e5a66", "#3e6b7a", 18)
    + box(0.8, 2.0, 0.22, 0.3, 1.4, "#c9553d", "#a03f2a", "#7e2f20", 17);
}

function counterSvg() {
  const x = 2.05;
  const y = 0.78;
  const w = 3.9;
  const d = 0.92;
  const h = 28;
  const parts = [box(x, y, w, d, h, "#f0dcb4", "#7c4b29", "#5f3a20")];
  for (let i = 1; i < 13; i += 1) parts.push(seg([x + (i * w) / 13, y + d, 4], [x + (i * w) / 13, y + d, h - 3], "rgba(0,0,0,.2)", 1));
  parts.push(seg([x, y + d, h], [x + w, y + d, h], "#fff3d6", 1.4));
  parts.push(face([[x, y + d + 0.01, 0], [x + w, y + d + 0.01, 0], [x + w, y + d + 0.01, 3], [x, y + d + 0.01, 3]], "#4c2f1a"));
  // кофемашина
  const mx = 3.68;
  const my = 0.92;
  parts.push(box(mx, my, 0.74, 0.58, 22, "#dfe3e4", "#56666e", "#3d4b53", h));
  parts.push(face([[mx + 0.06, my + 0.59, h + 14], [mx + 0.68, my + 0.59, h + 14], [mx + 0.68, my + 0.59, h + 19], [mx + 0.06, my + 0.59, h + 19]], "#c98a4b"));
  parts.push(box(mx + 0.2, my + 0.6, 0.34, 0.1, 3, "#2b2b2b", "#1d1d1d", "#151515", h + 9));
  parts.push(face([[mx + 0.12, my + 0.59, h + 3], [mx + 0.62, my + 0.59, h + 3], [mx + 0.62, my + 0.59, h + 6], [mx + 0.12, my + 0.59, h + 6]], "#2a3338"));
  parts.push(face([[mx + 0.48, my + 0.59, h + 8], [mx + 0.58, my + 0.59, h + 8], [mx + 0.58, my + 0.59, h + 11], [mx + 0.48, my + 0.59, h + 11]], "#f0a73a"));
  // кассовый аппарат, чашки, витрина с булочкой
  parts.push(box(5.42, 1.06, 0.42, 0.36, 7, "#59656b", "#3d484d", "#2f393d", h));
  parts.push(box(5.46, 1.1, 0.34, 0.06, 7, "#3a4a50", "#2a3438", "#202a2d", h + 7));
  parts.push(box(3.05, 1.12, 0.18, 0.18, 5, "#6b4426", "#fffaf0", "#d8cdb8", h));
  parts.push(box(3.32, 1.28, 0.18, 0.18, 5, "#6b4426", "#fffaf0", "#d8cdb8", h));
  parts.push(box(4.62, 1.14, 0.46, 0.4, 2, "#fffaf0", "#e8e0cf", "#cfc4ae", h));
  const [bx, by] = iso(4.85, 1.34, h + 2);
  parts.push(`<ellipse cx="${bx.toFixed(1)}" cy="${(by - 3).toFixed(1)}" rx="5.2" ry="3" fill="#c98a4b"/><ellipse cx="${(bx - 1.5).toFixed(1)}" cy="${(by - 4.2).toFixed(1)}" rx="2" ry="1" fill="#e8b878"/>`);
  parts.push(`<path d="M ${(bx - 9).toFixed(1)} ${by.toFixed(1)} A 9 11 0 0 1 ${(bx + 9).toFixed(1)} ${by.toFixed(1)} Z" fill="#d9f1fb" fill-opacity="0.45" stroke="#ffffff" stroke-opacity="0.6" stroke-width="0.8"/>`);
  return parts.join("");
}

function tableSvg(x, y, cups) {
  const parts = [
    box(x + 0.35, y + 0.35, 0.4, 0.4, 1.5, "#8a5a33", "#6b4426", "#523319"),
    box(x + 0.5, y + 0.5, 0.1, 0.1, 14, "#8a5a33", "#6b4426", "#523319", 1.5),
    box(x, y, 1.1, 1.1, 3, "#f3d9ae", "#c28a54", "#a06b3a", 14),
  ];
  if (cups) {
    parts.push(box(x + 0.4, y + 0.42, 0.2, 0.2, 5, "#6b4426", "#fffaf0", "#d8cdb8", 17));
  }
  return parts.join("");
}

function chairSvg(x, y, side) {
  const s = 0.5;
  const x0 = x - s / 2;
  const y0 = y - s / 2;
  const parts = [];
  [[0, 0], [s - 0.07, 0], [0, s - 0.07], [s - 0.07, s - 0.07]].forEach(([dx, dy]) => {
    parts.push(box(x0 + dx, y0 + dy, 0.07, 0.07, 7, "#9a6234", "#7a4a26", "#5f3a1c"));
  });
  parts.push(box(x0, y0, s, s, 3, "#d9a066", "#a8703f", "#8a582f", 7));
  if (side === "n") parts.push(box(x0, y0 - 0.02, s, 0.07, 16, "#c98d55", "#a8703f", "#8a582f", 10));
  else parts.push(box(x0 - 0.02, y0, 0.07, s, 16, "#c98d55", "#a8703f", "#8a582f", 10));
  return parts.join("");
}

/* ---------- люди: фигура ---------- */

const CUP_IN_HAND = `<rect x="6" y="-23" width="4.8" height="5.6" rx="1" fill="#fffaf0"/><rect x="6" y="-23" width="4.8" height="1.8" fill="#6b4426"/><path d="M10.8 -21 q2.2 0.6 0 2.8" fill="none" stroke="#fffaf0" stroke-width="1"/>`;

function figureSvg(look, pose, staff, accent, carry) {
  const { shirt, hair, skin, pants, style } = look;
  const seated = pose === "sit";
  const up = seated ? 13 : 0;
  const legs = seated
    ? `<rect x="-4.6" y="-5" width="4" height="7" rx="1.6" fill="${pants}"/><rect x="0.6" y="-5" width="4" height="7" rx="1.6" fill="${shade(pants, 0.2)}"/>
       <rect x="-4.4" y="1" width="3.6" height="8" rx="1.6" fill="${pants}"/><rect x="0.8" y="1" width="3.6" height="8" rx="1.6" fill="${shade(pants, 0.2)}"/>
       <ellipse cx="-2.6" cy="9.6" rx="3" ry="1.6" fill="#2a211c"/><ellipse cx="2.6" cy="9.6" rx="3" ry="1.6" fill="#2a211c"/>`
    : `<g class="leg leg-l"><rect x="-4.6" y="-15" width="4" height="14" rx="1.6" fill="${pants}"/><ellipse cx="-2.7" cy="-0.8" rx="3.2" ry="1.7" fill="#2a211c"/></g>
       <g class="leg leg-r"><rect x="0.6" y="-15" width="4" height="14" rx="1.6" fill="${shade(pants, 0.2)}"/><ellipse cx="2.7" cy="-0.8" rx="3.2" ry="1.7" fill="#2a211c"/></g>`;
  const fringe = "M -6.6 -44.2 Q -7.2 -51.8 0 -52 Q 7.2 -51.8 6.6 -44.2 Q 4.6 -48.4 0 -48.2 Q -4.6 -48 -6.6 -44.2 Z";
  const hairBack = style === 1 ? `<path d="M -7.8 -44 Q -8.6 -52 0 -52.4 Q 8.6 -52 7.8 -44 L 7.4 -30 L -7.4 -30 Z" fill="${hair}"/>` : "";
  const hairFront = style === 2
    ? `<circle cx="-4.8" cy="-49" r="4.1" fill="${hair}"/><circle cx="0" cy="-51.4" r="4.7" fill="${hair}"/><circle cx="4.8" cy="-49" r="4.1" fill="${hair}"/><path d="${fringe}" fill="${hair}"/>`
    : `<path d="${fringe}" fill="${hair}"/>`;
  const apron = staff
    ? `<path d="M -5 -33 L 5 -33 L 5.8 -9.5 L -5.8 -9.5 Z" fill="#f6efe2"/><path d="M 0.4 -33 L 5 -33 L 5.8 -9.5 L 0.4 -9.5 Z" fill="rgba(0,0,0,.08)"/>
       <rect x="-2.6" y="-22" width="5.2" height="4" rx="1" fill="none" stroke="#cdbf9f" stroke-width="0.7"/>
       <path d="M -3.6 -35.6 L 3.6 -35.6 L 0 -30.4 Z" fill="${accent}"/>`
    : "";
  return `<ellipse cx="0" cy="${seated ? 3 : 1}" rx="10" ry="3.4" fill="rgba(40,22,8,.22)"/>
    <ellipse class="ring" cx="0" cy="${seated ? 6 : 1.5}" rx="13" ry="5.2" fill="none" stroke="#f0a73a" stroke-width="2"/>
    <g class="body">
      ${legs}
      <g class="upper" transform="translate(0 ${up})">
        ${hairBack}
        <g class="arm arm-l"><rect x="-9.6" y="-34" width="3.8" height="17.5" rx="1.9" fill="${shade(shirt, 0.08)}"/><circle cx="-7.7" cy="-16" r="2" fill="${skin}"/></g>
        <g class="arm arm-r"><rect x="5.8" y="-34" width="3.8" height="17.5" rx="1.9" fill="${shade(shirt, 0.22)}"/><circle cx="7.7" cy="-16" r="2" fill="${shade(skin, 0.1)}"/>${carry ? CUP_IN_HAND : ""}</g>
        <path d="M -6.4 -31 Q -6.4 -35.4 -2.4 -35.4 L 2.4 -35.4 Q 6.4 -35.4 6.4 -31 L 6.4 -16 Q 6.4 -13.6 4 -13.6 L -4 -13.6 Q -6.4 -13.6 -6.4 -16 Z" fill="${shirt}"/>
        <path d="M 0.6 -35.4 L 2.4 -35.4 Q 6.4 -35.4 6.4 -31 L 6.4 -16 Q 6.4 -13.6 4 -13.6 L 0.6 -13.6 Z" fill="rgba(0,0,0,.14)"/>
        ${apron}
        <rect x="-1.9" y="-39" width="3.8" height="5" rx="1.4" fill="${shade(skin, 0.12)}"/>
        <circle cx="-6" cy="-43.6" r="1.4" fill="${shade(skin, 0.08)}"/><circle cx="6" cy="-43.6" r="1.4" fill="${shade(skin, 0.08)}"/>
        <ellipse cx="0" cy="-44" rx="6.2" ry="6.8" fill="${skin}"/>
        ${hairFront}
        <circle cx="-2.3" cy="-43.4" r="0.9" fill="#2b1d14"/><circle cx="2.3" cy="-43.4" r="0.9" fill="#2b1d14"/>
        <path d="M -1.7 -40.2 Q 0 -38.9 1.7 -40.2" fill="none" stroke="#8a4a3a" stroke-width="0.8" stroke-linecap="round"/>
      </g>
    </g>
    <rect x="-12" y="-58" width="24" height="64" fill="transparent"/>`;
}

function nodeOf(markup, tag = "g", attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  el.innerHTML = markup;
  return el;
}

const MOOD = {
  "радость": { v: 2, color: "#8fd19e" },
  "бодрость": { v: 1, color: "#c5dc7a" },
  "спокойствие": { v: 0, color: "#d8cdb8" },
  "усталость": { v: -1, color: "#9fb1cf" },
  "тревога": { v: -1, color: "#e8c25b" },
  "грусть": { v: -1, color: "#7aa0d8" },
  "раздражение": { v: -2, color: "#e0675a" },
};

const moodOf = (visit) => (visit && (visit.mood_after || visit.mood)) || "";

function faceSvg(mood) {
  const info = MOOD[mood];
  if (!info) return "";
  const mouth = {
    2: "M-2.4 1 Q0 4 2.4 1",
    1: "M-2 1.4 Q0 3.2 2 1.4",
    0: "M-1.8 2 L1.8 2",
    "-1": "M-2 3 Q0 1.2 2 3",
    "-2": "M-2 3.2 Q0 1.4 2 3.2",
  }[info.v];
  const brows = info.v <= -2 ? `<path d="M-3.4 -3.2 L-0.8 -1.9 M3.4 -3.2 L0.8 -1.9" stroke="#2b1d14" stroke-width="0.9" fill="none" stroke-linecap="round"/>` : "";
  return `<circle r="5.2" fill="${info.color}" stroke="#2b1d14" stroke-width="0.7"/>
    <circle cx="-1.8" cy="-1" r="0.8" fill="#2b1d14"/><circle cx="1.8" cy="-1" r="0.8" fill="#2b1d14"/>${brows}
    <path d="${mouth}" stroke="#2b1d14" stroke-width="0.9" fill="none" stroke-linecap="round"/>`;
}

function faceIcon(mood) {
  return MOOD[mood] ? `<svg class="face-icon" viewBox="-6 -6 12 12" aria-hidden="true">${faceSvg(mood)}</svg>` : "";
}

function tagNode(name, clientId, ret, mood) {
  const attrs = clientId ? { class: "tag", "data-client": clientId } : { class: "tag plain" };
  const el = nodeOf(
    `<title></title><rect class="nameplate" y="-9" height="17" rx="8.5"/>
     <g class="face"></g>
     <path class="heart" d="M0 3.4 C-5.2 -0.6 -3 -4.4 0 -1.8 C3 -4.4 5.2 -0.6 0 3.4 Z" fill="#e0675a"/>
     <text y="3.4" text-anchor="middle" font-size="11.5" font-family="Atkinson Hyperlegible, sans-serif" font-weight="700" fill="#2b1d14"></text>`,
    "g",
    attrs,
  );
  setTag(el, name, ret, mood);
  return el;
}

function setTag(el, text, heart, mood) {
  const key = `${text}|${heart ? 1 : 0}|${mood || ""}`;
  if (el.dataset.t === key) return;
  el.dataset.t = key;
  const face = Boolean(MOOD[mood]);
  const lead = (face ? 14 : 0) + (heart ? 12 : 0);
  const w = Math.max(40, [...text].length * 7.1 + 14 + lead);
  const rect = el.querySelector("rect");
  rect.setAttribute("x", (-w / 2).toFixed(1));
  rect.setAttribute("width", w.toFixed(1));
  const label = el.querySelector("text");
  label.textContent = text;
  label.setAttribute("x", lead / 2);
  const mark = el.querySelector(".heart");
  mark.style.display = heart ? "" : "none";
  mark.setAttribute("transform", `translate(${(-w / 2 + 11 + (face ? 13 : 0)).toFixed(1)} 0.4)`);
  const icon = el.querySelector(".face");
  icon.innerHTML = face ? faceSvg(mood) : "";
  icon.setAttribute("transform", `translate(${(-w / 2 + 11).toFixed(1)} 0)`);
  el.querySelector("title").textContent = mood ? `Настроение: ${mood}` : "";
}

/* ---------- маршруты и жизнь визита ---------- */

const DOOR = [0.35, 5.9];
const LANE = 3.5;
const WALK_SPEED = 2.8;
/* Вход с улицы: гость идёт по тротуару слева от зала (с юга или с севера), у двери в левой стене входит. */
const DOOR_OUT = [-0.7, 5.9];
const ALLEY_X = -3.6;
const STREET_FROM = [[ALLEY_X, 9.6], [ALLEY_X, 2.2]];
const streetIn = (side) => [STREET_FROM[side], [ALLEY_X, DOOR_OUT[1]], DOOR_OUT];
const streetOut = (side) => [DOOR_OUT, [ALLEY_X, DOOR_OUT[1]], STREET_FROM[side]];
const DEFAULT_STAY = 20;
const SEAT_ORDER = SEATS.map((_, index) => index);

function routeLen(pts) {
  let sum = 0;
  for (let i = 1; i < pts.length; i += 1) sum += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return sum;
}

function along(pts, p) {
  if (pts.length === 1) return pts[0];
  let left = routeLen(pts) * Math.min(1, Math.max(0, p));
  for (let i = 1; i < pts.length; i += 1) {
    const len = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (left <= len || i === pts.length - 1) {
      const k = len ? Math.min(1, left / len) : 1;
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k];
    }
    left -= len;
  }
  return pts[pts.length - 1];
}

const routeIn = (side) => [...streetIn(side), DOOR, [DOOR[0], LANE], [COUNTER_GUEST[0], LANE], COUNTER_GUEST];
const routeToSeat = (seat) => [COUNTER_GUEST, [COUNTER_GUEST[0], LANE], [seat[0], LANE], seat];
const routeOut = (from, side) => [from, [from[0], LANE], [DOOR[0], LANE], DOOR, ...streetOut(side)];
const clockMinutes = (text) => {
  const [h, m] = String(text || "08:00").split(":").map(Number);
  return h * 60 + (m || 0);
};

const QUEUE_Y = 3.05;
const QUEUE = [[3.3, QUEUE_Y], [2.5, QUEUE_Y], [1.7, QUEUE_Y], [0.9, QUEUE_Y], [0.35, QUEUE_Y]];
const QUEUE_STEP = 0.6;
const routeToQueue = (side, spot) => [...streetIn(side), DOOR, [DOOR[0], QUEUE_Y], spot];
const routeQueueToCounter = (from) => [from, [from[0], 2.5], COUNTER_GUEST];

function queuePos(idx) {
  const last = QUEUE.length - 1;
  const i = Math.min(last, Math.floor(idx));
  const j = Math.min(last, i + 1);
  const f = Math.min(1, idx - i);
  return [QUEUE[i][0] + (QUEUE[j][0] - QUEUE[i][0]) * f, QUEUE[i][1] + (QUEUE[j][1] - QUEUE[i][1]) * f];
}

/* Сколько человек в очереди впереди гостя в момент t. Дробное число: когда впереди кто-то уходит,
   очередь сдвигается плавно за QUEUE_STEP минуты. */
function queueIdx(life, t) {
  let idx = 0;
  for (const other of lives) {
    if (other === life || !other.q || !life.q) continue;
    const ahead = other.q.a < life.q.a || (other.q.a === life.q.a && other.visit.id < life.visit.id);
    if (!ahead || t < other.q.a) continue;
    const gone = t - other.q.b;
    idx += gone <= 0 ? 1 : Math.max(0, 1 - gone / QUEUE_STEP);
  }
  return idx;
}

function buildLives(visits) {
  const busy = SEATS.map(() => []);
  const sorted = [...visits].sort((a, b) => a.id - b.id);
  const built = sorted.map((v) => {
    const start = v.start_min ?? clockMinutes(v.clock);
    const side = v.id % 2;
    const walkQ = routeLen(routeToQueue(side, QUEUE[0])) / WALK_SPEED;
    const walkIn = routeLen(routeIn(side)) / WALK_SPEED;
    const waiting = v.status === "waiting";
    const left = v.status === "left";
    const serve = v.serve_min ?? null;
    const queued = waiting || left || (serve !== null && serve > start + walkQ + 0.5);
    const qEnd = waiting ? Infinity : left ? (v.end_min ?? start + walkQ + 1) : serve;
    return {
      key: `v${v.id}`, visit: v, clientId: v.client_id, name: v.client_name, ret: Boolean(v.is_return),
      look: looksOf(v.client_name), legs: [], side, exitSide: (v.id >> 1) % 2, start, walkQ, walkIn, queued, serve, qEnd,
      q: queued ? { a: start + walkQ, b: qEnd } : null,
    };
  });
  lives = built;
  built.forEach((life) => {
    const v = life.visit;
    const served = v.status === "served";
    const exitSpeed = served ? WALK_SPEED : WALK_SPEED * 1.6;
    const open = v.status === "open";
    const legs = life.legs;
    let atCounter;
    if (life.queued) {
      const spot = QUEUE[Math.min(QUEUE.length - 1, Math.round(queueIdx(life, life.q.a)))];
      legs.push({ a: life.start, b: life.q.a, route: routeToQueue(life.side, spot), pose: "walk", fade: "in", stage: "in" });
      legs.push({ a: life.q.a, b: life.qEnd, route: [spot], pose: "stand", stage: "queue", queue: true });
      if (v.status === "left") {
        const gone = life.qEnd;
        const from = queuePos(queueIdx(life, gone));
        const out = routeOut(from, life.exitSide);
        legs.push({ a: gone, b: gone + routeLen(out) / exitSpeed, route: out, pose: "walk", fade: "out", stage: "away" });
        return;
      }
      if (v.status === "waiting") return;
      const toCounter = routeQueueToCounter(QUEUE[0]);
      legs.push({ a: life.serve, b: life.serve + routeLen(toCounter) / WALK_SPEED, route: toCounter, pose: "walk", stage: "in" });
      atCounter = life.serve + routeLen(toCounter) / WALK_SPEED;
    } else {
      legs.push({ a: life.start, b: life.start + life.walkIn, route: routeIn(life.side), pose: "walk", fade: "in", stage: "in" });
      atCounter = Math.max(life.start + life.walkIn, life.serve ?? 0);
      if (atCounter > life.start + life.walkIn) {
        legs.push({ a: life.start + life.walkIn, b: atCounter, route: [COUNTER_GUEST], pose: "stand", stage: "in" });
      }
    }
    const end = v.end_min ?? (open ? null : life.start + 4);
    const leaves = end === null ? Infinity : Math.max(end, atCounter + 0.6);
    legs.push({ a: atCounter, b: leaves, route: [COUNTER_GUEST], pose: "stand", stage: "counter" });
    if (leaves !== Infinity) {
      const stay = v.stay_min ?? (v.status === "served" ? DEFAULT_STAY : 0);
      let taken = -1;
      let toSeat = null;
      let travel = 0;
      if (stay > 0) {
        for (const i of SEAT_ORDER) {
          const route = routeToSeat(SEATS[i].at);
          const dur = routeLen(route) / WALK_SPEED;
          const from = leaves;
          const to = leaves + dur + stay + routeLen(routeOut(SEATS[i].at, life.exitSide)) / WALK_SPEED;
          if (busy[i].every(([x, y]) => to <= x || from >= y)) {
            taken = i;
            toSeat = route;
            travel = dur;
            busy[i].push([from, to]);
            break;
          }
        }
      }
      if (taken >= 0) {
        const seat = SEATS[taken].at;
        const out = routeOut(seat, life.exitSide);
        const sitFrom = leaves + travel;
        const sitTo = sitFrom + stay;
        legs.push({ a: leaves, b: sitFrom, route: toSeat, pose: "walk", stage: "away", carry: served });
        legs.push({ a: sitFrom, b: sitTo, route: [seat], pose: "sit", seat: taken, stage: "away" });
        legs.push({ a: sitTo, b: sitTo + routeLen(out) / WALK_SPEED, route: out, pose: "walk", fade: "out", stage: "away" });
      } else {
        const out = routeOut(COUNTER_GUEST, life.exitSide);
        legs.push({ a: leaves, b: leaves + routeLen(out) / exitSpeed, route: out, pose: "walk", fade: "out", stage: "away", carry: served });
      }
    }
  });
  return built;
}

function stateAt(life, t) {
  const { legs } = life;
  if (!legs.length || t < legs[0].a) return null;
  const tail = legs[legs.length - 1];
  if (t >= tail.b) return null;
  const leg = legs.find((row) => t >= row.a && t < row.b);
  const p = Number.isFinite(leg.b) ? (t - leg.a) / (leg.b - leg.a) : 0;
  const [x, y] = leg.queue ? queuePos(queueIdx(life, t)) : along(leg.route, p);
  let alpha = 1;
  if (leg.fade === "in") alpha = Math.min(1, p * 6);
  if (leg.fade === "out") alpha = Math.min(1, (1 - p) * 6);
  return { x, y, pose: leg.pose, seat: leg.seat, alpha, stage: leg.stage, carry: Boolean(leg.carry) };
}

/* ---------- сцена ---------- */

let scene = null;
let lives = [];
let actors = new Map();
let orderKey = "";
let frameId = 0;

function buildScene() {
  frameRoom();
  const statics = [];
  const cups = [];
  const room = document.getElementById("room");
  const shadows = [
    shadowSvg([[2.05, 0.78], [6.45, 0.78], [6.45, 2.5], [2.05, 2.5]]),
    ...TABLES.map((t) => shadowSvg([[t.x + 0.1, t.y + 0.15], [t.x + 1.3, t.y + 0.15], [t.x + 1.3, t.y + 1.3], [t.x + 0.1, t.y + 1.3]])),
  ].join("");
  room.innerHTML = `<defs><clipPath id="doorclip"><polygon points="${DOOR_QUAD.map(pt).join(" ")}"/></clipPath></defs><g id="lit"><g id="land">${landSvg()}</g><g id="backs"></g><g id="behind"></g><g id="base">${wallsSvg()}${sunSvg()}${windowSvg()}${wallDecorSvg()}${rugSvg()}${shadows}</g><g id="doorway" clip-path="url(#doorclip)"><g id="doorhole">${doorHoleSvg()}</g></g><g id="actors"></g><g id="outer"></g><g id="tags"></g></g>`;
  worldBuild(room);
  camReset();
  const layer = document.getElementById("actors");
  const put = (d, markup) => {
    const el = nodeOf(markup);
    layer.appendChild(el);
    statics.push({ el, d });
    return el;
  };
  put(0.4 + 0.2 + 0.4 + 0.2, plantSvg(0.4, 0.4));
  put(7.3 + 0.2 + 7.1 + 0.2, plantSvg(7.3, 7.1));
  put(2.05 + 1.95 + 0.78 + 0.46, counterSvg());
  put(0.35 + 0.375 + 1.0 + 0.75, deskSvg());
  TABLES.forEach((table) => {
    const d = table.x + 0.55 + table.y + 0.55;
    put(d, tableSvg(table.x, table.y, false));
    const cup = put(d + 0.01, box(table.x + 0.4, table.y + 0.42, 0.2, 0.2, 5, "#6b4426", "#fffaf0", "#d8cdb8", 17));
    cup.style.display = "none";
    cups.push(cup);
  });
  SEATS.forEach((seat) => put(seat.at[0] + seat.at[1] - 0.05, chairSvg(seat.at[0], seat.at[1], seat.face)));
  scene = { statics, cups };
  actors = new Map();
  orderKey = "";
}

function turnInfo(stage) {
  const cur = snap.current_visit;
  if (!cur) return { guestTurn: false, staffId: null, visitId: null };
  const spoken = cur.lines ? cur : visitCache.get(cur.id);
  const last = spoken && spoken.lines && spoken.lines[spoken.lines.length - 1];
  const phase = snap.run.phase;
  const guestTurn = phase ? String(phase).includes("Гость") : Boolean(last && last.role === "client");
  const present = cur.status === "open" || stage === "counter" || stage === "in";
  const staffId = present && !guestTurn && (phase || last) ? cur.staff_id : null;
  return { guestTurn, staffId, visitId: cur.id };
}

function makeActor(key, look, name, clientId, staff, accent, ret = false, mood = "") {
  const g = nodeOf("", "g", clientId ? { class: "person", "data-client": clientId, tabindex: 0, role: "button" } : { class: "person" });
  document.getElementById("actors").appendChild(g);
  const tag = tagNode(name, clientId, ret, mood);
  document.getElementById("tags").appendChild(tag);
  const actor = { key, g, tag, look, staff, accent, pose: "", clientId, name };
  actors.set(key, actor);
  orderKey = "";
  return actor;
}

function dropActor(actor) {
  actor.g.remove();
  actor.tag.remove();
  actors.delete(actor.key);
  orderKey = "";
}

function setPose(actor, pose, carry = false) {
  const key = `${pose}|${carry ? 1 : 0}`;
  if (actor.pose === key) return;
  const hadOn = actor.g.classList.contains("on");
  actor.pose = key;
  actor.g.innerHTML = figureSvg(actor.look, pose, actor.staff, actor.accent, carry);
  actor.g.classList.toggle("walk", pose === "walk");
  actor.g.classList.toggle("on", hadOn);
  actor.g.classList.toggle("mgr", actor.key === "mgr");
}

function drawActors() {
  if (!snap) return;
  if (!scene) buildScene();
  const running = snap.run.status === "running";
  document.getElementById("room").classList.toggle("still", !running);
  const t = snap.run.day ? liveMinutes() : -1;
  const curLife = snap.current_visit && lives.find((row) => row.visit.id === snap.current_visit.id);
  const curState = curLife && t >= 0 ? stateAt(curLife, t) : null;
  const turn = turnInfo(curState ? curState.stage : "away");
  const wanted = new Set();
  const seated = new Set();
  const dyn = [];
  const bob = running ? Math.sin(performance.now() / 420) * 0.8 : 0;

  (snap.staff || []).forEach((person) => {
    const key = `staff:${person.id}`;
    wanted.add(key);
    const at = STAFF_AT[person.id] || STAFF_AT.anya;
    const look = { ...(STAFF_LOOK[person.id] || STAFF_LOOK.anya), pants: "#2f3a45" };
    const actor = actors.get(key) || makeActor(key, look, person.name, null, true, look.accent);
    setPose(actor, "stand");
    const [sx, sy] = iso(at[0], at[1], 0);
    actor.g.setAttribute("transform", `translate(${sx.toFixed(1)} ${(sy + (person.id === "mark" ? -bob : bob)).toFixed(1)}) scale(${SCALE})`);
    setTag(actor.tag, person.served_today ? `${person.name} · ${person.served_today}` : person.name, false, person.mood);
    const [tx, ty] = iso(at[0], at[1], 40);
    const dx = person.id === "mark" ? 56 : -56;
    actor.tag.setAttribute("transform", `translate(${(tx + dx).toFixed(1)} ${ty.toFixed(1)}) scale(${tagK.toFixed(2)})`);
    actor.tag.style.display = turn.staffId === person.id ? "none" : "";
    dyn.push({ el: actor.g, d: at[0] + at[1] });
  });

  const mgrOn = String(snap.run.phase || "").startsWith("Управляющий");
  let mgr = actors.get("mgr");
  if (!mgr && mgrOn) {
    mgr = makeActor("mgr", MGR_LOOK, "Управляющий", null, false, null);
    mgr.g.style.opacity = 0;
  }
  if (mgr) {
    wanted.add("mgr");
    setPose(mgr, "stand");
    const [mx, my] = iso(MGR_AT[0], MGR_AT[1], 0);
    mgr.g.setAttribute("transform", `translate(${mx.toFixed(1)} ${my.toFixed(1)}) scale(${SCALE})`);
    mgr.g.style.opacity = mgrOn ? 1 : 0;
    const [gx, gy] = iso(MGR_AT[0], MGR_AT[1], 78);
    mgr.tag.setAttribute("transform", `translate(${gx.toFixed(1)} ${gy.toFixed(1)}) scale(${tagK.toFixed(2)})`);
    mgr.tag.style.display = "none";
    dyn.push({ el: mgr.g, d: MGR_AT[0] + MGR_AT[1] });
  }

  let followAt = null;
  let doorBusy = false;
  const stages = new Map();
  lives.forEach((life) => {
    const st = t >= 0 ? stateAt(life, t) : null;
    stages.set(life.visit.id, st ? st.stage : "away");
    let actor = actors.get(life.key);
    if (!st) {
      if (actor) dropActor(actor);
      return;
    }
    wanted.add(life.key);
    if (!actor) actor = makeActor(life.key, life.look, life.name, life.clientId, false, null, life.ret, moodOf(life.visit));
    setTag(actor.tag, life.name, life.ret, moodOf(life.visit));
    setPose(actor, st.pose, st.carry);
    const z = st.pose === "sit" ? SEAT_Z : 0;
    const [sx, sy] = iso(st.x, st.y, z);
    actor.g.setAttribute("transform", `translate(${sx.toFixed(1)} ${sy.toFixed(1)}) scale(${(facing(actor, sx) * SCALE).toFixed(2)} ${SCALE})`);
    actor.g.setAttribute("opacity", st.alpha.toFixed(2));
    const on = selectedGuest === life.clientId;
    actor.g.classList.toggle("on", on);
    actor.tag.querySelector(".nameplate").classList.toggle("on", on);
    const lift = st.stage === "queue" ? 78 + 20 * (Math.round(queueIdx(life, t)) % 2) : 78;
    const [tx, ty] = iso(st.x, st.y, st.pose === "sit" ? z + 62 : lift);
    actor.tag.setAttribute("transform", `translate(${tx.toFixed(1)} ${ty.toFixed(1)}) scale(${tagK.toFixed(2)})`);
    actor.tag.setAttribute("opacity", st.alpha.toFixed(2));
    const speaking = turn.visitId === life.visit.id;
    const zone = zoneOf(st.x, st.y);
    const hidden = zone === "door" || (st.x > -2.6 && st.x < 0.05);
    actor.tag.style.display = hidden || (speaking && turn.guestTurn) ? "none" : "";
    if (speaking) followAt = { x: st.x, y: st.y };
    if (st.pose === "sit") seated.add(st.seat % TABLES.length);
    if (Math.abs(st.y - DOOR[1]) < 0.9 && st.x > -1.6 && st.x < 1 && st.alpha > 0.1) doorBusy = true;
    if (zone === "in") {
      dyn.push({ el: actor.g, d: st.x + st.y });
    } else {
      const host = document.getElementById(zone === "door" ? "doorway" : "behind");
      if (actor.g.parentNode !== host) host.appendChild(actor.g);
    }
  });

  actors.forEach((actor, key) => {
    if (!wanted.has(key)) dropActor(actor);
  });
  drawAmbient(t >= 0 ? t : 540);
  scene.cups.forEach((cup, index) => { cup.style.display = seated.has(index) ? "" : "none"; });
  document.getElementById("doorhole").style.opacity = doorBusy ? 1 : 0;
  const spd = running && !snap.run.thinking ? Math.min(2, Number(snap.run.speed) || 1) : 1;
  if (spd !== stepSpeed) {
    stepSpeed = spd;
    document.getElementById("room").style.setProperty("--spd", String(spd));
  }

  const all = [...scene.statics, ...dyn].sort((a, b) => a.d - b.d);
  const key = all.map((row) => (row.el.dataset.k ||= String(++stamp))).join(",");
  if (key !== orderKey) {
    const layer = document.getElementById("actors");
    all.forEach((row) => layer.appendChild(row.el));
    orderKey = key;
  }
  followBubble(followAt);
  const cur = snap.current_visit;
  document.querySelectorAll("#float [data-visit]").forEach((el) => {
    const done = cur && cur.status !== "open" && cur.status !== "waiting";
    const here = stages.get(Number(el.dataset.visit));
    el.style.display = done && here !== "counter" && here !== "in" && here !== "queue" ? "none" : "";
  });
}

let stamp = 0;
let stepSpeed = 1;

function facing(actor, sx) {
  if (actor.sx !== undefined && Math.abs(sx - actor.sx) > 0.15) actor.dir = sx < actor.sx ? -1 : 1;
  actor.sx = sx;
  return actor.dir || 1;
}

/* Где человек относительно стены с дверью: внутри зала, в проёме двери, на улице за стеной. */
function zoneOf(x, y) {
  if (x >= 0.05) return "in";
  if (x > -1.1 && Math.abs(y - DOOR[1]) < 0.8) return "door";
  return "out";
}

function followBubble(at) {
  const bubble = document.querySelector("#float [data-follow]");
  if (!bubble) return;
  if (!at) {
    bubble.style.display = "none";
    return;
  }
  bubble.style.display = "";
  const pos = spot(at.x, at.y, 74);
  const room = document.getElementById("room");
  bubble.style.left = `${Math.min(room.clientWidth - 126, Math.max(126, pos.left)).toFixed(0)}px`;
  bubble.style.top = `${pos.top.toFixed(0)}px`;
}

function frame() {
  frameId = 0;
  drawActors();
  if (snap && snap.run.status === "running") frameId = requestAnimationFrame(frame);
}

function wake() {
  if (!frameId) frameId = requestAnimationFrame(frame);
}

function renderWorld() {
  if (!scene) buildScene();
  lives = snap.run.day ? buildLives(snap.day_visits || []) : [];
  const open = snap.run.day && !snap.run.day_closed;
  document.getElementById("room").style.setProperty("--sign", open ? "#6fcf8a" : "#d9604c");
  applyLight(true);
  renderBoard();
  renderFloat();
  drawActors();
  wake();
}

function renderBoard() {
  const week = snap.weeks[0];
  if (!weekSeen) {
    lastWeekId = week ? week.id : 0;
    weekSeen = true;
  }
  if (week && week.id !== lastWeekId) {
    lastWeekId = week.id;
    flashItems = new Set((week.changes || []).map((change) => change.item_id));
    flashUntil = performance.now() + 2600;
  }
  const flashing = performance.now() < flashUntil;
  const trend = new Map();
  if (week && snap.run.day <= week.through_day + 1) {
    (week.changes || []).forEach((change) => {
      if (change.op === "set_price") {
        trend.set(change.item_id, { dir: change.price_after > change.price_before ? "up" : "down", before: change.price_before });
      }
    });
  }
  const fresh = new Set(week ? (week.changes || []).filter((change) => change.op === "add_item").map((change) => change.item_id) : []);
  const menu = snap.menu.filter((item) => item.available).map((item) => {
    const klass = flashing && flashItems.has(item.id) ? "flash" : "";
    const moved = trend.get(item.id);
    const arrow = moved
      ? `<span class="was" title="Управляющий ${moved.dir === "up" ? "поднял" : "снизил"} цену">${rub(moved.before)}</span><i class="trend ${moved.dir}"></i>`
      : "";
    const badge = fresh.has(item.id) ? `<em class="new" title="Новинка этой недели">new</em>` : "";
    return `<li class="${klass}"><span>${esc(item.name)}${badge}</span><span>${arrow}${rub(item.price)}</span></li>`;
  }).join("");
  document.getElementById("board").innerHTML = `<h2>Меню</h2><ul class="menu">${menu}</ul>`;
}

function clip(text) {
  const value = String(text || "");
  return value.length > 110 ? `${value.slice(0, 107)}…` : value;
}

function spot(x, y, z = 0) {
  const [sx, sy] = iso(x, y, z);
  return { left: (sx - view.x) * view.k, top: (sy - view.y) * view.k, k: view.k };
}

function guestSpot(visit) {
  const life = lives.find((row) => row.visit.id === visit.id);
  const st = life && snap.run.day ? stateAt(life, liveMinutes()) : null;
  return { x: st ? st.x : COUNTER_GUEST[0], y: st ? st.y : COUNTER_GUEST[1], z: 74 };
}

function speakerSpot(visit, guestSpeaking) {
  if (guestSpeaking) return guestSpot(visit);
  const at = STAFF_AT[visit.staff_id] || STAFF_AT.anya;
  return { x: at[0], y: at[1], z: 74 };
}

function lastCall(visitId, agent) {
  return (snap.llm_calls || [])
    .filter((call) => call.visit_id === visitId && call.agent === agent)
    .sort((x, y) => y.id - x.id)[0];
}

function bubbleAt(at, who, body, o = {}) {
  const pos = spot(at.x, at.y, at.z);
  const room = document.getElementById("room");
  const left = Math.min(room.clientWidth - 126, Math.max(126, pos.left));
  const attrs = [
    o.follow ? "data-follow" : "",
    o.visitId ? `data-visit="${o.visitId}"` : "",
    o.agent ? `data-agent="${o.agent}" title="Открыть этот ход в мониторе модели"` : "",
  ].join(" ");
  return `<div class="speech${o.cls ? ` ${o.cls}` : ""}" ${attrs} style="left:${left.toFixed(0)}px;top:${pos.top.toFixed(0)}px"><b>${esc(who)}</b>${body}${o.note || ""}</div>`;
}

function speechBubbles(visit) {
  if (/^(Рассказчик|Режиссёр)/.test(String(snap.run.phase || ""))) return "";
  if (String(snap.run.phase || "").startsWith("Управляющий")) {
    return bubbleAt({ x: MGR_AT[0], y: MGR_AT[1], z: 82 }, "Управляющий", `<span class="dots"><i></i><i></i><i></i></span>`);
  }
  if (!visit) return "";
  const thinking = snap.run.phase && snap.current_visit && snap.current_visit.id === visit.id;
  if (thinking) {
    const guestTurn = String(snap.run.phase).includes("Гость");
    const verdict = snap.run.active_agent === "verdict";
    return bubbleAt(speakerSpot(visit, guestTurn), snap.run.phase, `<span class="dots"><i></i><i></i><i></i></span>`, {
      follow: guestTurn, visitId: verdict ? null : visit.id, agent: verdict ? "verdict" : guestTurn ? "client" : "staff",
      cls: verdict ? "think" : "",
    });
  }
  const full = visit.lines ? visit : visitCache.get(visit.id);
  const lines = (full && full.lines) || [];
  const line = lines[lines.length - 1];
  if (!line) return "";
  const guest = line.role === "client";
  const inner = line.action === "verdict";
  const agent = inner ? "verdict" : line.action === "queue" || line.action === "left" ? "queue" : guest ? "client" : "staff";
  const call = lastCall(visit.id, agent);
  const note = call && call.latency_ms ? `<small class="lat">модель думала ${(call.latency_ms / 1000).toFixed(1).replace(".", ",")} с</small>` : "";
  return bubbleAt(speakerSpot(visit, guest), guest ? `${visit.client_name}${inner ? " · про себя" : ""}` : visit.staff_name, `<p>${esc(clip(line.text))}</p>`, {
    follow: guest, visitId: inner ? null : visit.id, agent, note,
    cls: inner ? "think" : visit.status === "refused" || visit.status === "failed" || visit.status === "left" ? "refused" : "",
  });
}

function renderFloat() {
  const closed = snap.run.day
    ? ""
    : `<div class="speech closed" style="left:50%;top:46%"><b>Смена закрыта</b><p>Пустить время — и гости придут сами.</p></div>`;
  document.getElementById("float").innerHTML = closed + speechBubbles(snap.current_visit);
}

function renderChats() {
  const root = document.getElementById("chats");
  const list = otherChats();
  if (!selectedGuest) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  root.hidden = false;
  wantLines(list.map((visit) => visit.id));
  const who = snap.clients.find((row) => row.id === selectedGuest);
  const heading = `<div class="drawer-head"><h2>Разговоры <span>${esc(who ? who.name : "")}</span></h2><button type="button" id="close-chats">Весь зал</button></div>`;
  const body = list.length
    ? list.map((visit) => chatCard(visit, false)).join("")
    : `<p class="quiet-note">Разговоров ещё нет.</p>`;
  root.innerHTML = heading + body;
  if (focusVisit) {
    const card = document.getElementById(`chat-${focusVisit}`);
    if (card) {
      card.scrollIntoView({ block: "nearest" });
      card.classList.add("flash");
      focusVisit = null;
    }
  }
}

const openNotes = new Set();
let showNotes = false;

function noteSeen() {
  try {
    return Number(localStorage.getItem("loom-note-seen") || 0);
  } catch (err) {
    return 0;
  }
}

function markNotesSeen() {
  try {
    if (snap.weeks.length) localStorage.setItem("loom-note-seen", String(snap.weeks[0].id));
  } catch (err) { /* без хранилища точка «новая» просто не запоминается */ }
}

/* Записки управляющего: кнопка в шапке и окно слева. На сцене их нет. */
function renderManager() {
  const button = document.getElementById("notes-btn");
  const root = document.getElementById("manager");
  if (!snap.weeks.length) {
    button.hidden = true;
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  button.hidden = false;
  document.getElementById("notes-n").textContent = String(snap.weeks.length);
  button.setAttribute("aria-expanded", String(showNotes));
  button.querySelector(".pin").hidden = showNotes || snap.weeks[0].id <= noteSeen();
  if (!showNotes) {
    root.hidden = true;
    return;
  }
  markNotesSeen();
  root.hidden = false;
  const list = snap.weeks.map((week, index) => {
    const changes = (week.changes || []).map((change) => {
      if (change.op === "add_item") return `${change.name}: добавил в меню, ${rub(change.price)}`;
      if (change.op === "set_price") return `${change.name}: ${rub(change.price_before)} → ${rub(change.price_after)}`;
      return `${change.name}: ${change.available_after ? "вернул в меню" : "убрал из меню"}`;
    }).join(". ") || "Меню не трогал.";
    const notes = (week.notes || []).join(" ");
    const open = openNotes.has(week.id) || (index === 0 && !openNotes.has(-week.id));
    return `<details class="slip" data-note="${week.id}"${open ? " open" : ""}>
      <summary>После дня ${week.through_day}</summary>
      <p class="say">${esc(week.say || "Без слов.")}</p>
      <p class="did">${esc(changes)} ${esc(notes)}</p>
      <details data-week="${week.id}"${openWeeks.has(week.id) ? " open" : ""}>
        <summary>Что он читал</summary>
        <pre>${esc(JSON.stringify(week.summary, null, 2))}</pre>
      </details>
    </details>`;
  }).join("");
  root.innerHTML = `<div class="drawer-head"><h2>Записки <span>управляющего</span></h2><button type="button" id="close-notes">Закрыть</button></div>${list}`;
}

function renderMonitor() {
  const agent = document.getElementById("agent-filter").value;
  const errors = document.getElementById("err-only").checked;
  const calls = snap.llm_calls.filter((call) => {
    if (agent && call.agent !== agent) return false;
    if (errors && !call.error) return false;
    return true;
  });
  const root = document.getElementById("monitor");
  const health = `<p class="meta">${esc(healthLine())}</p>`;
  if (!calls.length) {
    root.innerHTML = `${health}<p class="quiet-note">Запросов к модели ещё нет.</p>`;
    return;
  }
  root.innerHTML = health + calls.map((call) => {
    const where = call.visit_id ? `визит ${call.visit_id}` : `неделя, день ${call.week_day || ""}`;
    const mark = call.error ? `<span class="err">${esc(call.error)}</span>` : "разобран";
    const retry = call.attempt > 1 ? ", повтор" : "";
    const open = openCalls.has(call.id) ? renderCallDetail(callCache.get(call.id)) : "";
    return `<article class="call${pinnedCall === call.id ? " pinned" : ""}">
      <button type="button" data-call="${call.id}">${esc(call.created_at)} · ${esc(AGENT[call.agent] || call.agent)} · ${esc(where)} · ${call.latency_ms ?? "—"} мс · ${mark}${retry}</button>
      ${open}
    </article>`;
  }).join("");
}

function renderCallDetail(call) {
  if (!call) return `<div class="detail">Открываю запрос…</div>`;
  return `<div class="detail">
    <p class="meta">${esc(call.model)}, попытка ${call.attempt}</p>
    <h3>Системное описание</h3><pre>${esc(call.system_prompt)}</pre>
    <h3>Промпт хода</h3><pre>${esc(call.user_prompt)}</pre>
    <h3>Сырой ответ</h3><pre>${esc(call.raw_content || "пусто")}</pre>
    <h3>Разбор</h3><pre>${esc(call.parsed_json || "не разобран")}</pre>
    ${call.error ? `<p class="err">${esc(call.error)}</p>` : ""}
  </div>`;
}

function pick(visitId, clientId) {
  selectedGuest = clientId;
  focusVisit = visitId;
  if (snap) render();
}

async function openCallFor(visitId, agent) {
  const call = lastCall(visitId, agent);
  if (!call) return;
  document.getElementById("monitor-box").open = true;
  document.getElementById("agent-filter").value = "";
  document.getElementById("err-only").checked = false;
  openCalls.add(call.id);
  pinnedCall = call.id;
  await refreshOpen();
  render();
  const btn = document.querySelector(`[data-call="${call.id}"]`);
  if (btn) btn.scrollIntoView({ block: "center" });
}

const OUTCOME = { served: "ok", refused: "no", failed: "bad", open: "live", waiting: "wait", left: "left" };

function outcomeText(v) {
  if (v.status === "served") return `${v.item_name || "заказ"} · ${rub(v.price)}`;
  if (v.status === "refused") return "ушёл без заказа";
  if (v.status === "failed") return "разговор оборвался";
  if (v.status === "left") return "не дождался очереди";
  if (v.status === "waiting") return "в очереди";
  return "у прилавка…";
}

function renderEventbar() {
  const root = document.getElementById("eventbar");
  const events = snap.events || [];
  const phase = String(snap.run.phase || "");
  const thinking = /^(Рассказчик|Режиссёр)/.test(phase);
  if (!events.length && !thinking) {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  root.hidden = false;
  const voice = snap.district;
  const district = voice
    ? `<article class="ev district" title="${esc(voice.why || "")}"><b>Район</b><div class="fxs"><span class="fx">спрос ×${voice.traffic}</span><span class="fx">новых ${Math.round(voice.newcomers * 100)}%</span></div>${voice.buzz ? `<p>«${esc(voice.buzz)}»</p>` : ""}</article>`
    : "";
  const shown = [...events].reverse().slice(0, 3);
  const hidden = events.length - shown.length;
  const rows = shown.map((e) => {
    const chips = e.effects.map((label) => `<span class="fx">${esc(label)}</span>`).join("");
    const meta = [e.source === "director" ? "режиссёр" : "", e.until_day > snap.run.day ? `до дня ${e.until_day}` : ""].filter(Boolean).join(" · ");
    return `<article class="ev from-${e.source}" title="${esc(e.input ? `Вброс: ${e.input}. ` : "")}${esc(e.story || "")}"><header><b>${esc(e.headline)}</b>${meta ? `<span class="meta">${esc(meta)}</span>` : ""}<button type="button" class="end" data-end="${e.id}" title="Завершить событие сейчас" aria-label="Завершить событие">×</button></header>${chips ? `<div class="fxs">${chips}</div>` : ""}${e.story ? `<p>${esc(e.story)}</p>` : ""}</article>`;
  }).join("") + (hidden > 0 ? `<p class="more" title="${esc(events.slice(0, hidden).map((e) => e.headline).join("; "))}">ещё событий: ${hidden}</p>` : "");
  const wait = thinking ? `<article class="ev wait"><b>${esc(phase)}</b><span class="dots"><i></i><i></i><i></i></span></article>` : "";
  root.innerHTML = district + rows + wait;
}

function stars(n) {
  return "★".repeat(Math.max(0, Math.min(5, n))) + "☆".repeat(5 - Math.max(0, Math.min(5, n)));
}

function renderReviews() {
  const stats = snap.reviews || { avg: null, count: 0, latest: [] };
  document.getElementById("rating-val").textContent = stats.avg === null ? "—" : stats.avg.toFixed(1).replace(".", ",");
  document.getElementById("rating-n").textContent = stats.count ? ` · ${stats.count}` : "";
  const button = document.getElementById("rating");
  button.setAttribute("aria-expanded", String(showReviews));
  const root = document.getElementById("reviews");
  if (!showReviews) {
    root.hidden = true;
    return;
  }
  root.hidden = false;
  const list = stats.latest.length
    ? stats.latest.map((row) => `<article class="review" data-pick="${row.id}" data-who="${row.client_id}" tabindex="0" role="button" title="Открыть разговор">
        <header><b>${esc(row.client_name)}</b><span class="stars">${stars(row.liked)}</span></header>
        <p>${esc(row.review)}</p><small>День ${row.day}, ${esc(row.clock)}</small></article>`).join("")
    : `<p class="quiet-note">Отзывов пока нет.</p>`;
  root.innerHTML = `<div class="drawer-head"><h2>Отзывы <span>${stats.avg === null ? "" : `★ ${stats.avg.toFixed(1).replace(".", ",")}`}</span></h2><button type="button" id="close-reviews">Закрыть</button></div>${list}`;
}

function renderRibbon() {
  const list = document.getElementById("ribbon-list");
  const visits = [...(snap.day_visits || [])].reverse();
  if (!visits.length) {
    list.innerHTML = `<li class="quiet-note">${snap.run.day ? "Гостей ещё не было." : "Смена не начата."}</li>`;
    return;
  }
  const top = list.scrollTop;
  list.innerHTML = visits.map((v) => {
    const heart = v.is_return ? `<svg class="heart" viewBox="-5 -5 10 10" aria-label="вернулся"><path d="M0 3.4 C-5.2 -0.6 -3 -4.4 0 -1.8 C3 -4.4 5.2 -0.6 0 3.4 Z" fill="#e0675a"/></svg>` : "";
    const on = selectedGuest === v.client_id ? " on" : "";
    return `<li><button type="button" class="row ${OUTCOME[v.status] || "ok"}${on}" data-pick="${v.id}" data-who="${v.client_id}" title="Открыть разговор"><time>${esc(v.clock)}</time><b>${esc(v.client_name)}${heart}</b><span>${esc(outcomeText(v))}</span></button></li>`;
  }).join("");
  list.scrollTop = top;
}

function renderDots() {
  const root = document.getElementById("dots");
  if (!snap.run.day) {
    root.innerHTML = "";
    return;
  }
  const span = snap.run.close_min - snap.run.open_min;
  root.innerHTML = (snap.day_visits || []).map((v) => {
    const at = v.start_min ?? clockMinutes(v.clock);
    const left = (((at - snap.run.open_min) / span) * 100).toFixed(2);
    const title = `${v.clock} ${v.client_name}: ${outcomeText(v)}`;
    return `<button type="button" class="dot-mark ${OUTCOME[v.status] || "ok"}" style="left:${left}%" title="${esc(title)}" data-pick="${v.id}" data-who="${v.client_id}"></button>`;
  }).join("");
}

function daysChart(today) {
  const days = (snap.days || []).slice(-10);
  if (days.length < 2) return "";
  const top = Math.max(1, ...days.map((row) => row.visits));
  const bars = days.map((row) => `<div class="bar${row.day === today ? " now" : ""}" title="День ${row.day}: ${row.visits} гостей, ${esc(rub(row.revenue))}"><b>${row.visits}</b><i style="height:${Math.max(6, Math.round((row.visits / top) * 100))}%"></i><span>${row.day}</span></div>`).join("");
  return `<div class="bars-title">Гостей по дням</div><div class="bars">${bars}</div>`;
}

function renderDayCard() {
  const root = document.getElementById("daycard");
  const run = snap.run;
  if (!run.day || !run.day_closed || run.status === "running" || dismissedDay === run.day) {
    root.hidden = true;
    return;
  }
  const s = (snap.summary && snap.summary.today) || {};
  const refused = (s.refused || 0) + (s.failed || 0) + (s.left || 0);
  root.hidden = false;
  root.innerHTML = `<button type="button" class="x" id="close-card" aria-label="Закрыть итог дня">×</button>
    <h2>День ${run.day} закрыт</h2>
    <dl>
      <div><dt>Гостей</dt><dd>${s.visits || 0}</dd></div>
      <div><dt>Выручка</dt><dd>${rub(s.revenue)}</dd></div>
      <div><dt>Средний чек</dt><dd>${rub(s.avg_check)}</dd></div>
      <div><dt>${refused ? "Без заказа" : "Знакомых"}</dt><dd>${refused || s.returned || 0}</dd></div>
    </dl>
    ${daysChart(run.day)}
    <p>«Пустить время» или «До закрытия» откроют следующий день.</p>`;
}

/* ---------- события: деньги над кассой и звук ---------- */

function pop(text, kind, at) {
  const pos = spot(at.x, at.y, at.z);
  const el = document.createElement("div");
  el.className = `pop ${kind}`;
  el.textContent = text;
  el.style.left = `${pos.left.toFixed(0)}px`;
  el.style.top = `${pos.top.toFixed(0)}px`;
  document.getElementById("pops").appendChild(el);
  setTimeout(() => el.remove(), 2200);
}

function detectEvents() {
  if (seenDay !== snap.run.day) {
    seen.clear();
    seenDay = snap.run.day;
  }
  (snap.day_visits || []).forEach((v) => {
    const prev = seen.get(v.id);
    if (!firstLoad) {
      if (prev === undefined) sfx.play("bell");
      if ((prev === undefined || prev === "open" || prev === "waiting") && v.status !== "open" && v.status !== "waiting") {
        if (v.status === "left") {
          pop("не дождался", "dim", { x: QUEUE[0][0], y: QUEUE[0][1], z: 70 });
          sfx.play("nope");
        } else if (v.status === "served") {
          pop(`+${rub(v.price)}`, "good", { x: 5.6, y: 1.25, z: 44 });
          sfx.play("cash");
        } else if (v.status === "refused") {
          pop("отказ", "bad", { x: COUNTER_GUEST[0], y: COUNTER_GUEST[1], z: 70 });
          sfx.play("nope");
        } else {
          pop("обрыв", "dim", { x: COUNTER_GUEST[0], y: COUNTER_GUEST[1], z: 70 });
          sfx.play("nope");
        }
      }
    }
    seen.set(v.id, v.status);
  });
  firstLoad = false;
}

const sfx = (() => {
  let ctx = null;
  let on = false;
  try {
    on = localStorage.getItem("loom-sound") === "1";
  } catch (err) {
    on = false;
  }
  const audio = () => {
    if (!ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) ctx = new Ctx();
    }
    if (ctx && ctx.state === "suspended") ctx.resume();
    return ctx;
  };
  const tone = (c, freq, at, len, type, level) => {
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(level, at + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + len);
    osc.connect(gain).connect(c.destination);
    osc.start(at);
    osc.stop(at + len + 0.05);
  };
  return {
    get on() { return on; },
    set(value) {
      on = value;
      try {
        localStorage.setItem("loom-sound", value ? "1" : "0");
      } catch (err) { /* без хранилища звук просто не запоминается */ }
      if (value) this.play("bell");
    },
    play(name) {
      if (!on) return;
      const c = audio();
      if (!c) return;
      const t = c.currentTime;
      if (name === "bell") {
        tone(c, 1318, t, 0.4, "sine", 0.09);
        tone(c, 1760, t + 0.12, 0.55, "sine", 0.07);
      } else if (name === "cash") {
        tone(c, 880, t, 0.09, "square", 0.04);
        tone(c, 1320, t + 0.1, 0.28, "square", 0.04);
      } else if (name === "nope") {
        tone(c, 220, t, 0.26, "sawtooth", 0.05);
        tone(c, 165, t + 0.15, 0.32, "sawtooth", 0.05);
      }
    },
  };
})();

function paintSound() {
  document.getElementById("sound").setAttribute("aria-pressed", String(sfx.on));
}

async function control(action, extra = {}) {
  await rpc("control", { action, ...extra });
}

document.getElementById("rating").onclick = () => {
  showReviews = !showReviews;
  if (showReviews) showNotes = false;
  if (snap) {
    renderReviews();
    renderManager();
  }
};
document.getElementById("notes-btn").onclick = () => {
  showNotes = !showNotes;
  if (showNotes) showReviews = false;
  if (snap) {
    renderManager();
    renderReviews();
  }
};
document.getElementById("sound").onclick = () => {
  sfx.set(!sfx.on);
  paintSound();
};
paintSound();
document.getElementById("director").onsubmit = async (event) => {
  event.preventDefault();
  const input = document.getElementById("director-text");
  const button = document.getElementById("director-go");
  const note = document.getElementById("director-note");
  const text = input.value.trim();
  if (text.length < 2) return;
  button.disabled = true;
  button.textContent = "Думает…";
  note.hidden = true;
  const result = await rpc("director", { text });
  if (result.ok) {
    input.value = "";
  } else {
    note.textContent = result.error || "Не получилось";
    note.hidden = false;
  }
  button.disabled = false;
  button.textContent = "Вбросить";
};
document.getElementById("step").onclick = () => control("step");
document.getElementById("day").onclick = () => control("day");
document.getElementById("auto").onclick = () => control("auto");
document.getElementById("pause").onclick = () => control("pause");
document.getElementById("reset").onclick = () => {
  if (confirm("Начать прогон заново? Разговоры этой смены сотрутся.")) control("reset");
};
document.getElementById("speed").onclick = (event) => {
  const btn = event.target.closest("[data-speed]");
  if (btn) control("speed", { speed: Number(btn.dataset.speed) });
};
document.getElementById("agent-filter").onchange = () => { if (snap) render(); };
document.getElementById("err-only").onchange = () => { if (snap) render(); };
document.getElementById("settings").onsubmit = async (event) => {
  event.preventDefault();
  const body = {
    base_url: document.getElementById("llm-url").value.trim(),
    model: document.getElementById("llm-model").value.trim(),
    timeout: Number(document.getElementById("llm-timeout").value),
    critic_base_url: document.getElementById("critic-url").value.trim(),
    critic_model: document.getElementById("critic-model").value.trim(),
    api_key: document.getElementById("llm-key").value.trim(),
  };
  await rpc("settings", body);
  document.getElementById("llm-key").value = "";
};

document.body.addEventListener("toggle", (event) => {
  const note = event.target.dataset && event.target.dataset.note;
  if (note) {
    const id = Number(note);
    if (event.target.open) {
      openNotes.add(id);
      openNotes.delete(-id);
    } else {
      openNotes.delete(id);
      openNotes.add(-id);
    }
    return;
  }
  const week = event.target.dataset && event.target.dataset.week;
  if (!week) return;
  if (event.target.open) openWeeks.add(Number(week));
  else openWeeks.delete(Number(week));
}, true);

document.body.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const guestBtn = event.target.closest("[data-client]");
  if (!guestBtn) return;
  event.preventDefault();
  guestBtn.click();
});

document.body.addEventListener("keydown", (event) => {
  if (event.target !== document.body || event.ctrlKey || event.metaKey || event.altKey || !snap) return;
  if (event.key === " ") {
    event.preventDefault();
    control(snap.run.status === "running" ? "pause" : "auto");
  } else if ("1234".includes(event.key) && event.key.length === 1) {
    control("speed", { speed: [1, 2, 4, 8][Number(event.key) - 1] });
  }
});

document.body.addEventListener("click", (event) => {
  if (event.target.closest("#close-chats")) {
    selectedGuest = null;
    if (snap) render();
    return;
  }
  const endBtn = event.target.closest("[data-end]");
  if (endBtn) {
    endBtn.disabled = true;
    rpc("end_event", { event_id: Number(endBtn.dataset.end) });
    return;
  }
  if (event.target.closest("#close-notes")) {
    showNotes = false;
    renderManager();
    return;
  }
  if (event.target.closest("#close-reviews")) {
    showReviews = false;
    renderReviews();
    return;
  }
  if (event.target.closest("#close-card")) {
    dismissedDay = snap.run.day;
    renderDayCard();
    return;
  }
  const bubble = event.target.closest(".speech[data-agent]");
  if (bubble) {
    openCallFor(Number(bubble.dataset.visit), bubble.dataset.agent);
    return;
  }
  const pickBtn = event.target.closest("[data-pick]");
  if (pickBtn) {
    pick(Number(pickBtn.dataset.pick), Number(pickBtn.dataset.who));
    return;
  }
  const guestBtn = event.target.closest("[data-client]");
  if (guestBtn) {
    const id = Number(guestBtn.dataset.client);
    selectedGuest = selectedGuest === id ? null : id;
    render();
    return;
  }
  const callBtn = event.target.closest("[data-call]");
  if (!callBtn) return;
  const id = Number(callBtn.dataset.call);
  if (openCalls.has(id)) openCalls.delete(id);
  else openCalls.add(id);
  refreshOpen().then(() => { if (snap) render(); });
});

window.addEventListener("resize", () => { if (snap) renderFloat(); });

connect();
load();
setInterval(() => {
  if (!snap || snap.run.status !== "running") return;
  const line = document.getElementById("clockline");
  if (line && snap.run.day) line.textContent = formatClock(liveMinutes());
  paintDay();
  applyLight(false);
}, 200);
