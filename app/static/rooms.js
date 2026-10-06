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
const DEFAULT_TABLES = TABLES;
const DEFAULT_SEATS = SEATS;
const ROOMS = new Map();
let ROOM = null;

function newRoom(def) {
  return { ...def, fields: {}, lives: [], actors: new Map(), stepSpeed: 1 };
}

function enterRoom(room) {
  ROOM = room;
  TABLES = room?.layout ? room.layout.objects.filter(o => o.kind === "table").map(o => ({x:o.x-0.55, y:o.y-0.55})) : DEFAULT_TABLES;
  SEATS = room?.layout ? room.layout.seats : DEFAULT_SEATS;
  SEAT_ORDER = SEATS.map((_, i) => i);
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
    else { enterRoom(null); }
  }
}

function roomOf(placeId) {
  return ROOMS.get(placeId) || ROOMS.get("cafe");
}

/* Темы залов (CAFE_THEME, DC_THEME) лежат в art/rooms/<заведение>/theme.js, рисунки зала — рядом. */


const THEMES = { cafe: CAFE_THEME, dc: DC_THEME };

/* Люди за стойкой: места по порядку в списке персонала, внешность по id. */
const STAFF_SLOTS = [[2.55, 0.45], [5.3, 0.45]];
const STAFF_LOOKS = {
  anya: { shirt: "#c4473a", hair: "#5c3318", accent: "#f0a73a", skin: SKIN[1], style: 1 },
  mark: { shirt: "#2f7d72", hair: "#241c18", accent: "#f6efe2", skin: SKIN[2], style: 0 },
  valera: { shirt: "#2d6f8f", hair: "#241c18", accent: "#7fe3ef", skin: SKIN[2], style: 0 },
  pasha: { shirt: "#5b4b8a", hair: "#8a5a32", accent: "#8ff0a8", skin: SKIN[1], style: 2 },
};


/* Проект агента становится залом без перезагрузки страницы. */
function syncExternalRooms() {
  const places = (snap.places || []).filter(p => p.type === "custom" && p.room);
  ROOMS.forEach((room, id) => {
    if (room.theme !== "custom" || places.some(p => p.id === id)) return;
    withRoom(room, () => {
      [...actors.values()].forEach(dropActor);
      scene.statics.forEach(s => s.el.destroy());
      ROOM_FIELDS.filter(k => !["statics", "cups", "doorMask", "skyPoints", "signPoints"].includes(k)).forEach(k => scene[k]?.destroy?.());
      scene.doorMask?.destroy();
    });
    ROOMS.delete(id);
  });
  places.forEach(place => {
    if (ROOMS.has(place.id)) return;
    const room = newRoom({id:place.id, ox:place.room.ox, oy:place.room.oy, theme:"custom", layout:place.room, managerPhase:`Управляющий ${place.name}`});
    ROOMS.set(place.id, room);
    buildRoom(room);
  });
}

THEMES.custom = {
  apron: true,
  base() {
    const layout = ROOM.layout;
    let svg = wallsSvg().replace(/#(?:e9d6b8|f3e4cb|dcc7a6|ecd9bc|e4cfae|ecdbc0|3d7d6c|33695a)/g, layout.wall_color)
      .replace(/#(?:dba76b|d6a064|dcaa70|d39d62)/g, layout.floor_color);
    svg += windowSvg();
    // Тротуар соединяет входы участка с существующей сетью улиц.
    const j = [layout.junction[0]-ROOM.ox, layout.junction[1]-ROOM.oy];
    const near = Math.abs(j[1]-9.6) < Math.abs(j[1]-2.2) ? 9.6 : 2.2;
    svg += face([[-3.85,2.2,-15],[-3.35,2.2,-15],[-3.35,9.6,-15],[-3.85,9.6,-15]], "#d4cbbb");
    svg += seg([-3.6,near,-15], [j[0],j[1],-15], "#d4cbbb", 12);
    return svg;
  },
  furniture(put) {
    const accent = ROOM.layout.accent_color;
    put(5.24, box(2.05,0.78,3.9,0.92,24,accent,shade(accent,0.15),shade(accent,0.3)), BOX_AT(2.05,0.78,3.9,0.92));
    ROOM.layout.objects.forEach(o => {
      const sizes = {table:[1.1,1.1,17],chair:[0.5,0.5,10],plant:[0.5,0.5,26],equipment:[0.8,0.8,35],shelf:[1.2,0.5,42],decor:[0.5,0.5,18]};
      const [w,d,h] = sizes[o.kind];
      const x=o.x-w/2, y=o.y-d/2;
      let svg;
      if (o.kind === "chair") svg = chairSvg(o.x,o.y,o.face).replace(/#(?:[0-9a-f]{6})/g, o.color);
      else if (o.kind === "plant") svg = plantSvg(x,y);
      else svg = box(x,y,w,d,h,o.color,shade(o.color,0.18),shade(o.color,0.3));
      put(o.x+o.y, svg, BOX_AT(x,y,w,d));
    });
  },
};
