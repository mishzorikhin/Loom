/* ---------- залы заведений ----------
   Все заведения живут в одном каркасе: зал размера ROOM_W × ROOM_D с задней и левой стенами, дверью в левой стене,
   стойкой у задней стены, очередью, стульями. Тема задаёт только рисунки и людей за стойкой. Зал стоит в мире со
   сдвигом (ox, oy): рисунки строятся при включённом сдвиге `ISO_OFF`, поэтому остальной код считает в координатах зала.
   Использует iso, face, box, seg, shade, lighten, MOOD, figureSvg, svgObject и остальное из app.js; подключается после него. */

const ROOM_DEFS = [
  { id: "cafe", ox: 0, oy: 0, theme: "cafe", managerPhase: "Управляющий читает" },
  { id: "neuraldeep", ox: -4, oy: 19.5, theme: "dc", managerPhase: "Управляющий NeuralDeep" },
];

const ROOM_FIELDS = ["statics", "cups", "base", "sun", "door", "doorMask", "maskGraphics", "sky", "skyPoints", "sign", "signPoints"];
const ROOMS = new Map();
let ROOM = null;

function newRoom(def) {
  return { ...def, fields: {}, lives: [], actors: new Map(), stepSpeed: 1 };
}

function enterRoom(room) {
  ROOM = room;
  ISO_OFF[0] = room ? room.ox : 0;
  ISO_OFF[1] = room ? room.oy : 0;
  if (room) {
    ROOM_FIELDS.forEach((key) => { scene[key] = room.fields[key]; });
    lives = room.lives;
    actors = room.actors;
  }
}

/* Выполнить `fn` в координатах зала: сдвиг мира, его сцена, люди и жизни визитов. Возвращает результат `fn`. */
function withRoom(room, fn) {
  const before = ROOM;
  enterRoom(room);
  try {
    return fn();
  } finally {
    if (scene) ROOM_FIELDS.forEach((key) => { room.fields[key] = scene[key]; });
    room.lives = lives;
    room.actors = actors;
    if (before) enterRoom(before);
    else { ROOM = null; ISO_OFF[0] = 0; ISO_OFF[1] = 0; }
  }
}

function roomOf(placeId) {
  return ROOMS.get(placeId) || ROOMS.get("cafe");
}

/* ---------- тема ЦОДа ---------- */

const DC_WALL = "#4b5a66";
const DC_LED = ["#7fe3ef", "#8ff0a8", "#f0c35a", "#ff7a6a"];

function dcFloorSvg() {
  const out = [];
  for (let y = 0; y < ROOM_D; y += 1) {
    for (let x = 0; x < ROOM_W; x += 1) {
      out.push(face([[x, y, 0], [x + 1, y, 0], [x + 1, y + 1, 0], [x, y + 1, 0]], (x + y) % 2 ? "#aab7be" : "#b7c3c9"));
    }
  }
  for (let i = 0; i <= ROOM_W; i += 1) {
    out.push(seg([i, 0, 0], [i, ROOM_D, 0], "#8a98a1", 0.7));
    out.push(seg([0, i, 0], [ROOM_W, i, 0], "#8a98a1", 0.7));
  }
  return out.join("");
}

function dcWallsSvg() {
  const back = box(-0.28, -0.28, ROOM_W + 0.28, 0.28, WALL, "#566672", "#6b7b87", "#5a6a76");
  const left = box(-0.28, 0, 0.28, ROOM_D, WALL, "#586874", "#52626e", "#586874");
  const panels = [];
  for (let x = 0.5; x < ROOM_W; x += 1.9) panels.push(face([[x, 0.03, 6], [x + 1.5, 0.03, 6], [x + 1.5, 0.03, 30], [x, 0.03, 30]], "#7a8b97", 0.55));
  for (let y = 0.5; y < ROOM_D; y += 1.9) panels.push(face([[0.03, y, 6], [0.03, y + 1.5, 6], [0.03, y + 1.5, 30], [0.03, y, 30]], "#6e7f8b", 0.55));
  panels.push(face([[0, 0.02, 0], [ROOM_W, 0.02, 0], [ROOM_W, 0.02, 3.5], [0, 0.02, 3.5]], "#2f3b44"));
  panels.push(face([[0.02, 0, 0], [0.02, ROOM_D, 0], [0.02, ROOM_D, 3.5], [0.02, 0, 3.5]], "#2f3b44"));
  panels.push(seg([0, 0.03, 31], [ROOM_W, 0.03, 31], "#35e0f0", 1.2));
  panels.push(seg([0.03, 0, 31], [0.03, ROOM_D, 31], "#35e0f0", 1.2));
  const slab = [
    face([[0, ROOM_D, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [0, ROOM_D, 0]], "#6c7a84"),
    face([[ROOM_W, 0, -15], [ROOM_W, ROOM_D, -15], [ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0]], "#55626b"),
    seg([0, ROOM_D, 0], [ROOM_W, ROOM_D, 0], "#9fb0ba", 1.6),
    seg([ROOM_W, ROOM_D, 0], [ROOM_W, 0, 0], "#8396a1", 1.6),
  ];
  return slab.join("") + dcFloorSvg() + back + left + panels.join("");
}

/* Окно на задней стене: за стеклом ряды стоек. Небо через окно не видно, только машинный зал. */
function dcWindowSvg() {
  const x0 = 2.25;
  const x1 = 5.75;
  const y = 0.03;
  const parts = [
    face([[x0 - 0.12, y, 28], [x1 + 0.12, y, 28], [x1 + 0.12, y, 80], [x0 - 0.12, y, 80]], "#2b3640"),
    face([[x0, y + 0.02, 33], [x1, y + 0.02, 33], [x1, y + 0.02, 76], [x0, y + 0.02, 76]], "#17222a"),
  ];
  for (let i = 0; i < 6; i += 1) {
    const a = x0 + 0.12 + i * 0.57;
    parts.push(face([[a, y + 0.03, 34], [a + 0.42, y + 0.03, 34], [a + 0.42, y + 0.03, 70], [a, y + 0.03, 70]], "#26343e"));
    for (let k = 0; k < 7; k += 1) {
      parts.push(face([[a + 0.06, y + 0.04, 37 + k * 4.6], [a + 0.36, y + 0.04, 37 + k * 4.6], [a + 0.36, y + 0.04, 39 + k * 4.6], [a + 0.06, y + 0.04, 39 + k * 4.6]],
        DC_LED[(i + k * 3) % DC_LED.length], 0.9));
    }
  }
  parts.push(face([[x0, y + 0.05, 33], [x1, y + 0.05, 33], [x1, y + 0.05, 46], [x0, y + 0.05, 46]], "#ffffff", 0.1));
  parts.push(box(x0 - 0.2, 0.02, x1 - x0 + 0.4, 0.2, 3, "#aab7be", "#8b99a2", "#74818a", 25));
  return parts.join("");
}

function dcTextOnBack(text, x, z, size, color) {
  const [sx, sy] = iso(x, 0.05, z);
  return `<text transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)}) skewY(26.57)" font-family="Unbounded, Arial, sans-serif" font-weight="700" font-size="${size}" fill="${color}" letter-spacing="1">${text}</text>`;
}

function dcDecorSvg() {
  const parts = [];
  // вывеска над стойкой и мониторы с графиками нагрузки справа от окна
  parts.push(face([[0.5, 0.03, 56], [1.95, 0.03, 56], [1.95, 0.03, 80], [0.5, 0.03, 80]], "#1d2830"));
  parts.push(face([[0.58, 0.04, 60], [1.87, 0.04, 60], [1.87, 0.04, 76], [0.58, 0.04, 76]], "#0f1a20"));
  [[0.66, 62, 0.5, 4], [0.66, 68, 1.1, 3.4], [0.66, 72, 0.8, 2.2]].forEach(([x, z, w, h], i) => {
    parts.push(face([[x, 0.05, z], [x + w, 0.05, z], [x + w, 0.05, z + h], [x, 0.05, z + h]], DC_LED[i]));
  });
  parts.push(face([[6.2, 0.03, 44], [7.9, 0.03, 44], [7.9, 0.03, 80], [6.2, 0.03, 80]], "#1d2830"));
  parts.push(face([[6.3, 0.04, 48], [7.8, 0.04, 48], [7.8, 0.04, 76], [6.3, 0.04, 76]], "#0f1a20"));
  for (let k = 0; k < 6; k += 1) {
    const h = 3 + ((k * 7) % 11);
    parts.push(face([[6.45 + k * 0.23, 0.05, 52], [6.62 + k * 0.23, 0.05, 52], [6.62 + k * 0.23, 0.05, 52 + h], [6.45 + k * 0.23, 0.05, 52 + h]], DC_LED[k % 4]));
  }
  parts.push(seg([6.4, 0.05, 66], [7.7, 0.05, 66], "rgba(130,255,255,.5)", 1));
  parts.push(dcTextOnBack("NEURALDEEP", 2.45, 83.5, 9, "#8ff0ff"));
  // левая стена: дверь, табличка и плакат
  parts.push(face([[0.03, 5.15, 0], [0.03, 6.65, 0], [0.03, 6.65, 74], [0.03, 5.15, 74]], "#27323a"));
  parts.push(face([[0.04, 5.25, 0], [0.04, 6.55, 0], [0.04, 6.55, 70], [0.04, 5.25, 70]], "#3b4954"));
  parts.push(face([[0.05, 5.4, 34], [0.05, 6.4, 34], [0.05, 6.4, 62], [0.05, 5.4, 62]], "#9fdcec"));
  parts.push(face([[0.05, 5.4, 34], [0.05, 6.4, 34], [0.05, 6.4, 44], [0.05, 5.4, 44]], "#ffffff", 0.25));
  parts.push(face([[0.06, 5.66, 38], [0.06, 6.14, 38], [0.06, 6.14, 47], [0.06, 5.66, 47]], "#0f1a20"));
  parts.push(`<polygon points="${[[0.07, 5.7, 39.2], [0.07, 6.1, 39.2], [0.07, 6.1, 45.8], [0.07, 5.7, 45.8]].map(pt).join(" ")}" style="fill:var(--sign)"/>`);
  parts.push(face([[0.03, 1.2, 46], [0.03, 3.4, 46], [0.03, 3.4, 78], [0.03, 1.2, 78]], "#1d2830"));
  parts.push(face([[0.04, 1.3, 50], [0.04, 3.3, 50], [0.04, 3.3, 74], [0.04, 1.3, 74]], "#0f1a20"));
  for (let k = 0; k < 5; k += 1) parts.push(seg([0.05, 1.5 + k * 0.38, 54], [0.05, 1.5 + k * 0.38, 54 + 6 + ((k * 5) % 13)], DC_LED[k % 4], 2));
  parts.push(face([[0.03, 3.8, 52], [0.03, 4.7, 52], [0.03, 4.7, 70], [0.03, 3.8, 70]], "#d9e6ee"));
  parts.push(seg([0.05, 4.0, 66], [0.05, 4.5, 66], "#35525f", 1.2));
  parts.push(seg([0.05, 4.0, 62], [0.05, 4.5, 62], "#35525f", 1.2));
  parts.push(seg([0.05, 4.0, 58], [0.05, 4.3, 58], "#35525f", 1.2));
  return parts.join("");
}

/* Жёлто-чёрная разметка у стойки поддержки и антистатический коврик. */
function dcRugSvg() {
  const x0 = 2.4, x1 = 5.9, y0 = 1.95, y1 = 3.2;
  const parts = [
    face([[x0, y0, 0.2], [x1, y0, 0.2], [x1, y1, 0.2], [x0, y1, 0.2]], "#273640"),
    face([[x0 + 0.15, y0 + 0.15, 0.3], [x1 - 0.15, y0 + 0.15, 0.3], [x1 - 0.15, y1 - 0.15, 0.3], [x0 + 0.15, y1 - 0.15, 0.3]], "#33454f"),
  ];
  for (let i = 0; i < 14; i += 1) {
    const a = x0 + i * ((x1 - x0) / 14);
    const b = a + (x1 - x0) / 28;
    parts.push(face([[a, y1 - 0.12, 0.4], [b, y1 - 0.12, 0.4], [b + 0.1, y1, 0.4], [a + 0.1, y1, 0.4]], i % 2 ? "#f0c35a" : "#222c33"));
  }
  return parts.join("");
}

function dcCounterSvg() {
  const x = 2.05, y = 0.78, w = 3.9, d = 0.92, h = 28;
  const parts = [box(x, y, w, d, h, "#d7dde1", "#33424c", "#27343c")];
  for (let i = 1; i < 10; i += 1) parts.push(seg([x + (i * w) / 10, y + d, 4], [x + (i * w) / 10, y + d, h - 3], "rgba(0,0,0,.25)", 1));
  parts.push(seg([x, y + d, h], [x + w, y + d, h], "#8ff0ff", 1.4));
  parts.push(face([[x, y + d + 0.01, 0], [x + w, y + d + 0.01, 0], [x + w, y + d + 0.01, 3], [x, y + d + 0.01, 3]], "#1d2830"));
  // два монитора с терминалами и клавиатуры
  [[2.55, "#0f1a20"], [4.3, "#0f1a20"]].forEach(([mx, tone]) => {
    parts.push(box(mx, 0.95, 0.9, 0.08, 15, "#2a353d", "#1d262c", "#161d22", h + 3));
    parts.push(face([[mx + 0.06, 1.04, h + 6], [mx + 0.84, 1.04, h + 6], [mx + 0.84, 1.04, h + 16], [mx + 0.06, 1.04, h + 16]], tone));
    for (let k = 0; k < 4; k += 1) parts.push(seg([mx + 0.12, 1.05, h + 8 + k * 2.2], [mx + 0.3 + (k * 0.17) % 0.5, 1.05, h + 8 + k * 2.2], k % 2 ? "#8ff0a8" : "#7fe3ef", 1));
    parts.push(box(mx + 0.18, 1.2, 0.55, 0.22, 1.2, "#9aa7ae", "#2a353d", "#222c33", h));
  });
  // роутер с антеннами и стойка с «ключами»
  parts.push(box(5.3, 1.08, 0.5, 0.36, 3, "#222c33", "#161d22", "#11171b", h));
  parts.push(seg([5.38, 1.12, h + 3], [5.33, 1.12, h + 14], "#222c33", 1.2));
  parts.push(seg([5.7, 1.12, h + 3], [5.75, 1.12, h + 14], "#222c33", 1.2));
  parts.push(face([[5.36, 1.45, h + 1], [5.46, 1.45, h + 1], [5.46, 1.45, h + 2.4], [5.36, 1.45, h + 2.4]], "#8ff0a8"));
  parts.push(box(3.55, 1.35, 0.3, 0.2, 7, "#fff7d6", "#e8d8a4", "#c9b985", h));
  return parts.join("");
}

function dcRackSvg(x, y) {
  const parts = [box(x, y, 1.1, 1.1, 46, "#2c3943", "#1f2a32", "#182026")];
  for (let k = 0; k < 9; k += 1) {
    const z = 4 + k * 4.6;
    parts.push(face([[x + 0.1, y + 1.12, z], [x + 1.0, y + 1.12, z], [x + 1.0, y + 1.12, z + 3.6], [x + 0.1, y + 1.12, z + 3.6]], "#3b4954"));
    for (let led = 0; led < 3; led += 1) {
      parts.push(face([[x + 0.18 + led * 0.14, y + 1.13, z + 1.2], [x + 0.26 + led * 0.14, y + 1.13, z + 1.2], [x + 0.26 + led * 0.14, y + 1.13, z + 2.2], [x + 0.18 + led * 0.14, y + 1.13, z + 2.2]],
        DC_LED[(k + led * 2 + Math.round(x * 3)) % DC_LED.length]));
    }
  }
  parts.push(seg([x + 1.1, y + 0.2, 40], [x + 1.1, y + 1.0, 40], "#8ff0ff", 1));
  return parts.join("");
}

function dcDeskSvg() {
  return box(0.35, 1.0, 0.75, 1.5, 17, "#c5d0d6", "#33424c", "#27343c")
    + box(0.46, 1.05, 0.05, 0.6, 12, "#11181d", "#2a353d", "#1f2a31", 18)
    + box(0.46, 1.7, 0.05, 0.6, 12, "#11181d", "#2a353d", "#1f2a31", 18)
    + box(0.8, 1.35, 0.22, 0.3, 1.4, "#f0c35a", "#c79a30", "#9e7a24", 17);
}

function dcCoolerSvg(x, y) {
  return box(x, y, 0.5, 0.5, 26, "#d7dde1", "#8f9ca4", "#74818a")
    + face([[x + 0.08, y + 0.51, 6], [x + 0.42, y + 0.51, 6], [x + 0.42, y + 0.51, 22], [x + 0.08, y + 0.51, 22]], "#33424c")
    + [0, 1, 2, 3].map((i) => seg([x + 0.1, y + 0.52, 8 + i * 4], [x + 0.4, y + 0.52, 8 + i * 4], "#aebbc3", 0.9)).join("");
}

function dcShadows() {
  return [
    shadowSvg([[2.05, 0.78], [6.45, 0.78], [6.45, 2.5], [2.05, 2.5]]),
    ...TABLES.map((t) => shadowSvg([[t.x + 0.1, t.y + 0.15], [t.x + 1.3, t.y + 0.15], [t.x + 1.3, t.y + 1.3], [t.x + 0.1, t.y + 1.3]])),
  ].join("");
}

const BOX_AT = (x, y, w, d) => [x - 0.05, x + w + 0.05, y - 0.05, y + d + 0.05];

/* Темы залов. `furniture(put)` ставит мебель со своими коробками для сортировки по глубине. */
const THEMES = {
  cafe: {
    apron: true,
    base: () => wallsSvg() + windowSvg() + wallDecorSvg() + rugSvg() + shadowsSvg(),
    furniture(put, cups) {
      put(1.2, plantSvg(0.4, 0.4), BOX_AT(0.4, 0.4, 0.4, 0.4));
      put(14.8, plantSvg(7.3, 7.1), BOX_AT(7.3, 7.1, 0.4, 0.4));
      put(5.24, counterSvg(), BOX_AT(2.05, 0.78, 3.9, 0.92));
      put(2.475, deskSvg(), BOX_AT(0.35, 1.0, 0.75, 1.5));
      TABLES.forEach((table) => {
        const d = table.x + table.y + 1.1;
        put(d, tableSvg(table.x, table.y, false), BOX_AT(table.x, table.y, 1.1, 1.1));
        cups.push(put(d + 0.01, box(table.x + 0.4, table.y + 0.42, 0.2, 0.2, 5, "#6b4426", "#fffaf0", "#d8cdb8", 17), BOX_AT(table.x, table.y, 1.1, 1.1)).setVisible(false));
      });
      SEATS.forEach((seat) => put(seat.at[0] + seat.at[1] - 0.05, chairSvg(seat.at[0], seat.at[1], seat.face), BOX_AT(seat.at[0] - 0.25, seat.at[1] - 0.25, 0.5, 0.5)));
    },
  },
  dc: {
    apron: false,
    base: () => dcWallsSvg() + dcWindowSvg() + dcDecorSvg() + dcRugSvg() + dcShadows(),
    furniture(put) {
      put(1.2, dcCoolerSvg(0.4, 0.4), BOX_AT(0.4, 0.4, 0.5, 0.5));
      put(14.8, dcCoolerSvg(7.3, 7.1), BOX_AT(7.3, 7.1, 0.5, 0.5));
      put(5.24, dcCounterSvg(), BOX_AT(2.05, 0.78, 3.9, 0.92));
      put(2.475, dcDeskSvg(), BOX_AT(0.35, 1.0, 0.75, 1.5));
      TABLES.forEach((table) => put(table.x + table.y + 1.1, dcRackSvg(table.x, table.y), BOX_AT(table.x, table.y, 1.1, 1.1)));
    },
  },
};

function shadowsSvg() {
  return [
    shadowSvg([[2.05, 0.78], [6.45, 0.78], [6.45, 2.5], [2.05, 2.5]]),
    ...TABLES.map((t) => shadowSvg([[t.x + 0.1, t.y + 0.15], [t.x + 1.3, t.y + 0.15], [t.x + 1.3, t.y + 1.3], [t.x + 0.1, t.y + 1.3]])),
  ].join("");
}

/* Люди за стойкой: места по порядку в списке персонала, внешность по id. */
const STAFF_SLOTS = [[2.55, 0.45], [5.3, 0.45]];
const STAFF_LOOKS = {
  anya: { shirt: "#c4473a", hair: "#5c3318", accent: "#f0a73a", skin: SKIN[1], style: 1 },
  mark: { shirt: "#2f7d72", hair: "#241c18", accent: "#f6efe2", skin: SKIN[2], style: 0 },
  valera: { shirt: "#2d6f8f", hair: "#241c18", accent: "#7fe3ef", skin: SKIN[2], style: 0 },
  pasha: { shirt: "#5b4b8a", hair: "#8a5a32", accent: "#8ff0a8", skin: SKIN[1], style: 2 },
};
