/* Phaser — только экран общего серверного мира, без собственных часов и физики. */
let phaserScene = null;
let phaserGame = null;
let cameraMoved = false;
const CAM = { cx: 0, cy: 0, z: 1, min: 0.42, max: 3.4 };
let HOME = { x: 0, y: 0, w: 960, h: 580 };
const view = { x: 0, y: 0, w: 960, h: 580, k: 1 };
let tagK = 1;
const textureAssets = new Map();
let textureSerial = 0;
const measureSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
measureSvg.setAttribute("aria-hidden", "true");
measureSvg.style.cssText = "position:fixed;left:-20000px;top:0;width:1px;height:1px;visibility:hidden;pointer-events:none";
document.body.appendChild(measureSvg);

function cleanMarkup(markup) {
  // Переменные цвета используются в исходных рисунках, а не в живом SVG-дереве.
  return markup.replace(/var\(--sky\)/g, "#a8dcf4").replace(/var\(--sign\)/g, "#6fcf8a")
    .replace(/var\(--sun\)/g, "1").replace(/var\(--night, 0\)/g, "0")
    .replace(/<ellipse class="ring"[^>]*\/>/g, "");
}

function assetFor(markup) {
  let asset = textureAssets.get(markup);
  if (asset) return asset;
  const clean = cleanMarkup(markup);
  measureSvg.innerHTML = `<g>${clean}</g>`;
  const bounds = measureSvg.firstChild.getBBox();
  // Размытые тени выходят за габариты фигур: даём запас, чтобы края не обрезались.
  const pad = clean.includes("<filter") ? 14 : 3;
  const x = Math.floor(bounds.x - pad), y = Math.floor(bounds.y - pad);
  const w = Math.max(1, Math.ceil(bounds.width + pad * 2)), h = Math.max(1, Math.ceil(bounds.height + pad * 2));
  const scale = Math.min(2, 4096 / w, 4096 / h);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${Math.ceil(w * scale)}" height="${Math.ceil(h * scale)}" viewBox="${x} ${y} ${w} ${h}">${clean}</svg>`;
  measureSvg.replaceChildren();
  asset = { key: `loom:${++textureSerial}`, x, y, w, h, refs: 0, ready: false };
  const img = new Image();
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  asset.promise = new Promise((resolve, reject) => {
    img.onload = () => {
      URL.revokeObjectURL(url);
      phaserScene.textures.addImage(asset.key, img);
      asset.ready = true;
      resolve(asset);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Не загрузилась текстура мира")); };
    img.src = url;
  });
  textureAssets.set(markup, asset);
  return asset;
}

function svgObject(markup) {
  const object = phaserScene.add.container(0, 0);
  const asset = assetFor(markup);
  asset.refs += 1;
  asset.promise.then(() => {
    if (!object.scene) return;
    const image = phaserScene.add.image(asset.x, asset.y, asset.key).setOrigin(0).setDisplaySize(asset.w, asset.h);
    // Рисунок приходит позже уже добавленных детей (свет окон, крона, колёса): он должен лежать под ними.
    object.add(image);
    object.sendToBack(image);
  }).catch((err) => clientLog("error", { message: err.message }));
  object.once("destroy", () => {
    asset.refs -= 1;
    // Не накапливаем внешности всех гостей за весь прогон.
    if (textureAssets.size > 256) {
      for (const [source, cached] of textureAssets) {
        if (cached.refs === 0 && cached.ready) {
          phaserScene.textures.remove(cached.key);
          textureAssets.delete(source);
          if (textureAssets.size <= 256) break;
        }
      }
    }
  });
  return object;
}

/* Земля — одна большая картинка, которая в один растр не помещается с нужной чёткостью. Режем её на плитки:
   в центре плитки резче, на краях карты грубее. Каждая плитка — тот же рисунок со своим окном viewBox. */
const LAND_TILE = 1024;
/* Три зоны: у перекрёстка и зала резко (1.4), в остальном квартале средне (0.95), на краях карты грубо. */
const LAND_ZONES = [
  { x0: -1100, x1: 1100, y0: -350, y1: 900, scale: 1.4 },
  { x0: -1900, x1: 1900, y0: -800, y1: 1250, scale: 0.95 },
];
const LAND_FAR = 0.5;

function landObject(markup) {
  const clean = cleanMarkup(markup);
  measureSvg.innerHTML = `<g>${clean}</g>`;
  const b = measureSvg.firstChild.getBBox();
  measureSvg.replaceChildren();
  const holder = phaserScene.add.container(0, 0);
  const inWorld = (sx, sy) => {
    // обратный iso: мир — квадрат вокруг карты, плитки вне него пусты
    const u = sx / TW, v = sy / TH;
    const wx = (u + v) / 2, wy = (v - u) / 2;
    return wx > -36 && wx < 44 && wy > -36 && wy < 44;
  };
  const tiles = [];
  for (let tx = Math.floor(b.x / LAND_TILE) * LAND_TILE; tx < b.x + b.width; tx += LAND_TILE) {
    for (let ty = Math.floor(b.y / LAND_TILE) * LAND_TILE; ty < b.y + b.height; ty += LAND_TILE) {
      let used = false;
      for (let i = 0; i <= 4 && !used; i += 1) for (let j = 0; j <= 4 && !used; j += 1) used = inWorld(tx + i * LAND_TILE / 4, ty + j * LAND_TILE / 4);
      if (!used) continue;
      const zone = LAND_ZONES.find((z) => tx + LAND_TILE > z.x0 && tx < z.x1 && ty + LAND_TILE > z.y0 && ty < z.y1);
      tiles.push({ tx, ty, scale: zone ? zone.scale : LAND_FAR });
    }
  }
  tiles.forEach((tile, index) => {
    const size = LAND_TILE + 2;
    const px = Math.ceil(size * tile.scale);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${px}" height="${px}" viewBox="${tile.tx - 1} ${tile.ty - 1} ${size} ${size}">${clean}</svg>`;
    const img = new Image();
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    const key = `loom:land:${++textureSerial}`;
    img.onload = () => {
      URL.revokeObjectURL(url);
      if (!holder.scene) return;
      phaserScene.textures.addImage(key, img);
      holder.add(phaserScene.add.image(tile.tx - 1, tile.ty - 1, key).setOrigin(0).setDisplaySize(size, size));
    };
    img.onerror = () => { URL.revokeObjectURL(url); clientLog("error", { message: "Не загрузилась плитка земли" }); };
    img.src = url;
  });
  return holder;
}

/* Радиальное свечение: одна канвас-текстура, из неё же фонари, окна, светофоры и пар. Цвет задаёт tint. */
function ensureSoftTextures() {
  if (!phaserScene.textures.exists("loomGlow")) {
    const tex = phaserScene.textures.createCanvas("loomGlow", 128, 128);
    const ctx = tex.getContext();
    const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.35, "rgba(255,255,255,0.45)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 128, 128);
    tex.refresh();
  }
}

function glowImage(x, y, w, h, tint, depth) {
  return phaserScene.add.image(x, y, "loomGlow").setDisplaySize(w, h).setTint(tint).setBlendMode(Phaser.BlendModes.ADD).setDepth(depth).setAlpha(0);
}

function worldBuild() {
  ensureSoftTextures();
  const terrain = landSvg();
  scene.land = landObject(terrain).setDepth(-1000);
  const items = [...HOUSES.map((h) => ({ kind: "house", ...h })), ...worldProps()];
  HOUSES.forEach((h) => svgObject(houseShadows([h])).setDepth(-900));
  // Тинт времени суток: умножение под светом фонарей и окон (глубина ниже 8000), днём белый и ничего не меняет.
  scene.tint = phaserScene.add.rectangle(0, 0, 10, 10, 0xffffff).setDepth(7900).setBlendMode(Phaser.BlendModes.MULTIPLY);
  const statics = [];
  scene.windowGlows = [];
  scene.smoke = [];
  scene.trees = [];
  items.forEach((p) => {
    const d = propDepth(p);
    let el;
    if (p.kind === "house") {
      const source = nodeOf(houseSvg(p));
      const glowNodes = [...source.querySelectorAll('polygon[style]')];
      const glowMarkup = glowNodes.map((node) => { node.removeAttribute("style"); const markup = node.outerHTML; node.remove(); return markup; }).join("");
      const chimney = source.querySelector(".puff");
      let smokeAt;
      if (chimney) {
        smokeAt = chimney.parentNode.getAttribute("transform").match(/-?[\d.]+/g).map(Number);
        chimney.parentNode.remove();
      }
      el = svgObject(source.innerHTML);
      // Окна светят поверх ночного тинта, поэтому лежат отдельно от дома.
      if (glowMarkup) { const glow = svgObject(glowMarkup).setAlpha(0).setDepth(8002); scene.windowGlows.push(glow); }
      if (smokeAt) for (let i = 0; i < 3; i += 1) {
        const puff = phaserScene.add.circle(0, 0, 3.2, 0xffffff); el.add(puff);
        scene.smoke.push({ puff, at: smokeAt, off: i * 1.3 });
      }
    }
    else {
      // Размер задаёт масштаб объекта, а не новый рисунок: текстур столько, сколько видов, а не деревьев.
      const markup = {
        tree: () => treeSvg(1, 0, p.v || 0), bush: () => bushSvg(1, p.v || 0), rock: () => rockSvg(1), lamp: lampSvg, bench: () => benchSvg(p.axis),
        bed: () => bedSvg(p.axis), bin: binSvg, hydrant: hydrantSvg, sign: signSvg,
      }[p.kind]();
      if (p.kind === "tree") {
        const source = nodeOf(markup), canopy = source.querySelector(".sway");
        const leaves = svgObject(canopy.outerHTML); canopy.remove();
        el = svgObject(source.innerHTML).setPosition(...iso(p.x, p.y, G));
        el.add(leaves); scene.trees.push({ leaves, off: p.x * 7 + p.y * 3 });
      } else el = svgObject(markup).setPosition(...iso(p.x, p.y, G));
      if (p.s) el.setScale(p.s);
    }
    const r = p.kind === "tree" ? 0.5 : p.kind === "bench" ? 0.9 : 0.3;
    let bounds = p.kind === "house" ? [p.x, p.x + p.w, p.y, p.y + p.d] : [p.x - r, p.x + r, p.y - r, p.y + r];
    if (p.kind === "bed") bounds = p.axis === "y" ? [p.x - 0.5, p.x + 0.5, p.y - 1, p.y + 1] : [p.x - 1, p.x + 1, p.y - 0.5, p.y + 0.5];
    statics.push({ el, d, box: bounds });
  });
  scene.signals = [
    { axis: "x", x: ROAD_X0 - 2.8, y: ROAD_X1 + 0.6 },
    { axis: "x", x: ROAD_X1 + 2.8, y: ROAD_X0 - 0.6 },
    { axis: "y", x: ROAD_X0 - 0.6, y: ROAD_X0 - 2.8 },
    { axis: "y", x: ROAD_X1 + 0.6, y: ROAD_X1 + 2.8 },
  ].map((spec) => {
    const signal = makeTrafficSignal(spec);
    statics.push({ el: signal.el, d: spec.x + spec.y, box: [spec.x - 0.2, spec.x + 0.2, spec.y - 0.2, spec.y + 0.2] });
    return signal;
  });
  const birds = Array.from({ length: 5 }, () => svgObject(birdSvg()).setDepth(9000));
  outer = { statics, birds };
  // Свет — самостоятельные объекты Phaser, меняется без перегенерации текстур.
  scene.glows = [];
  scene.halos = [];
  items.filter((p) => p.kind === "lamp").forEach((p) => {
    const [x, y] = iso(p.x, p.y, G);
    scene.glows.push(glowImage(x + 3, y + 2, 150, 62, 0xffdf92, 8000));
    scene.halos.push(glowImage(x + 2, y - 48, 54, 54, 0xffe7a8, 8001));
  });
}

/* ---------- город: люди и машины из кадров сервера ---------- */

const cityPeds = new Map();
const cityCars = new Map();
const cityEnts = { layer: null, key: "", labels: [] };
const LANE_META = [{ axis: "x", dir: 1 }, { axis: "x", dir: -1 }, { axis: "y", dir: 1 }, { axis: "y", dir: -1 }];
const CAR_KIND_NAMES = ["sedan", "hatch", "van"];
const PED_SCALE = [1.05, 0.98, 1.1, 0.82, 1.02];

function makeCityPed(id) {
  const meta = cityRoster.peds[id];
  const look = looksOf(meta ? meta.l : `прохожий${id}`);
  const root = phaserScene.add.container(0, 0);
  const body = svgObject(figureSvg(look, "walk", false, null, false));
  root.add(body);
  root.setInteractive(new Phaser.Geom.Rectangle(-14, -60, 28, 68), Phaser.Geom.Rectangle.Contains);
  root.on("pointerup", () => { if (!cameraMoved) inspectCity("ped", id); });
  const style = { fontFamily: "Atkinson Hyperlegible, sans-serif", fontSize: "11px", fontStyle: "bold", color: "#2b1d14", backgroundColor: "#fbf1df", padding: { x: 5, y: 2 } };
  const label = phaserScene.add.text(0, 0, "", style).setOrigin(0.5).setDepth(10000).setVisible(false);
  const say = phaserScene.add.text(0, 0, "", { ...style, fontStyle: "italic", backgroundColor: "#ffffff" }).setOrigin(0.5, 1).setDepth(10002).setVisible(false);
  return { root, body, label, say, scale: PED_SCALE[id % 5] };
}

function makeCityCar(id) {
  const meta = cityRoster.cars[id];
  if (!meta) return null;
  const lane = LANE_META[meta.lane];
  const kind = CAR_KIND_NAMES[meta.k];
  const car = { axis: lane.axis, dir: lane.dir, kind };
  const el = svgObject(carSvg(CAR_COLORS[meta.col], lane.axis, lane.dir, kind, meta.taxi));
  const brakes = svgObject(carBrakeSvg(car)).setVisible(false);
  const wheels = phaserScene.add.graphics();
  el.add([brakes, wheels]);
  el.setInteractive(new Phaser.Geom.Rectangle(-30, -30, 60, 40), Phaser.Geom.Rectangle.Contains);
  el.on("pointerup", () => { if (!cameraMoved) inspectCity("car", id); });
  return { el, brakes, wheels, car, kind };
}

function dropCity(map, id) {
  const item = map.get(id);
  if (!item) return;
  [item.root, item.el, item.label, item.say].forEach((obj) => obj && obj.destroy());
  if (item.wheels) item.wheels.destroy();
  map.delete(id);
}

function drawCityEntities(frame) {
  const key = JSON.stringify(frame.e);
  if (key === cityEnts.key) return;
  cityEnts.key = key;
  if (!cityEnts.layer) cityEnts.layer = phaserScene.add.graphics().setDepth(900);
  const g = cityEnts.layer;
  g.clear();
  cityEnts.labels.forEach((text) => text.destroy());
  cityEnts.labels = [];
  frame.e.forEach(([id, kind, x, y, r, blocks, hazard, glyph, label]) => {
    const [sx, sy] = iso(x, y, G);
    const color = Phaser.Display.Color.HexStringToColor(glyph.color || "#d9604c").color;
    const w = 2.83 * r * TW, h = 2.83 * r * TH;
    g.fillStyle(color, blocks ? 0.4 : 0.22).fillEllipse(sx, sy, w, h);
    g.lineStyle(2, hazard > 0 ? 0xd9304c : color, 0.8).strokeEllipse(sx, sy, w, h);
    const size = 12 * (glyph.size || 1);
    g.fillStyle(color, 0.95).lineStyle(2, 0x2b1d14, 0.9);
    if (glyph.shape === "square") g.fillRect(sx - size, sy - size * 0.7, size * 2, size * 1.4).strokeRect(sx - size, sy - size * 0.7, size * 2, size * 1.4);
    else if (glyph.shape === "ring") g.lineStyle(4, color, 0.95).strokeEllipse(sx, sy, size * 2.4, size * 1.2);
    else if (glyph.shape === "cloud") [[-0.7, 0.1], [0.1, -0.3], [0.8, 0.1]].forEach(([dx, dy]) => g.fillCircle(sx + dx * size, sy + dy * size, size * 0.8));
    else if (glyph.shape === "star") {
      const pts = Array.from({ length: 10 }, (_, i) => ({ x: sx + Math.cos(i * Math.PI / 5 - Math.PI / 2) * size * (i % 2 ? 0.45 : 1), y: sy + Math.sin(i * Math.PI / 5 - Math.PI / 2) * size * (i % 2 ? 0.45 : 1) * 0.7 }));
      g.fillPoints(pts, true);
    } else g.fillEllipse(sx, sy, size * 2, size * 1.1).strokeEllipse(sx, sy, size * 2, size * 1.1);
    const text = label || glyph.text || kind;
    if (text) {
      const t = phaserScene.add.text(sx, sy - size - 6, String(text), { fontFamily: "Atkinson Hyperlegible, sans-serif", fontSize: "11px", fontStyle: "bold", color: "#2b1d14", backgroundColor: "#fbf1df", padding: { x: 5, y: 2 } }).setOrigin(0.5).setDepth(10001);
      cityEnts.labels.push(t);
    }
  });
}

function drawCity(rows) {
  const frame = cityNow();
  if (!frame) return;
  drawCityEntities(frame);
  const mins = frame.t;
  const seen = new Set();
  frame.p.forEach(([id, x, y, st, h]) => {
    seen.add(id);
    let ped = cityPeds.get(id);
    if (!ped) { ped = makeCityPed(id); cityPeds.set(id, ped); }
    const meta = cityRoster.peds[id];
    const moving = st === 0 || st === 2 || st === 5;
    const [sx, sy] = iso(x, y, G);
    ped.root.setPosition(sx, sy + (moving ? Math.sin(mins * 13 + id) * 0.8 : 0)).setScale(ped.scale * h, ped.scale).setAngle(st === 6 ? 90 : 0);
    const shown = layers.life;
    ped.root.setVisible(shown);
    const named = shown && layers.names && CAM.z >= 0.62 && meta && meta.c;
    if (named && ped.label.text !== meta.n) ped.label.setText(meta.n);
    ped.label.setVisible(Boolean(named)).setPosition(sx, sy - 72 * ped.scale * tagK).setScale(tagK);
    const words = st === 3 ? "…" : (meta && meta.say) || "";
    if (ped.say.text !== words) ped.say.setText(words);
    ped.say.setVisible(shown && Boolean(words)).setPosition(sx, sy - 80 * ped.scale * tagK - (named ? 16 * tagK : 0)).setScale(tagK);
    if (shown) rows.push({ el: ped.root, d: x + y, box: [x - 0.25, x + 0.25, y - 0.25, y + 0.25] });
  });
  cityPeds.forEach((ped, id) => { if (!seen.has(id)) dropCity(cityPeds, id); });
  const seenCars = new Set();
  frame.c.forEach(([id, x, y, lane, flags, wheel]) => {
    let car = cityCars.get(id);
    if (!car) {
      car = makeCityCar(id);
      if (!car) return;
      cityCars.set(id, car);
    }
    seenCars.add(id);
    const [sx, sy] = iso(x, y);
    car.el.setPosition(sx, sy);
    car.brakes.setVisible(Boolean(flags & 1) && car.car.dir < 0);
    const shape = CAR_KINDS[car.kind];
    const P = (u, v, z) => car.car.axis === "x" ? iso(u * car.car.dir, v, G + z) : iso(v, u * car.car.dir, G + z);
    car.wheels.clear().lineStyle(0.8, 0x6b717c);
    [-shape.L / 2 + 0.5, shape.L / 2 - 0.5].forEach((u) => {
      // спицы на колпаке колеса (art/vehicles/cars.js: центр 5.8 px, колпак 0.62 радиуса 5.6 px)
      const [cx, cy] = P(u, shape.W / 2 + 0.06, 5.8);
      for (let i = 0; i < 3; i += 1) {
        const angle = wheel / 0.32 + i * Math.PI * 2 / 3;
        const [xw, yw] = P(u + Math.cos(angle) * 0.1, shape.W / 2 + 0.06, 5.8 + Math.sin(angle) * 3.2);
        car.wheels.lineBetween(cx, cy, xw, yw);
      }
    });
    const u = car.car.axis === "x" ? x : y;
    const alpha = Math.max(0, Math.min(1, (u + 30) / 2, (38 - u) / 2));
    car.el.setVisible(layers.life && alpha > 0.02).setAlpha(alpha);
    if (layers.life && alpha > 0.02) {
      const dx = (car.car.axis === "x" ? shape.L : shape.W) / 2, dy = (car.car.axis === "x" ? shape.W : shape.L) / 2;
      rows.push({ el: car.el, d: x + y, box: [x - dx, x + dx, y - dy, y + dy] });
    }
  });
  cityCars.forEach((car, id) => { if (!seenCars.has(id)) dropCity(cityCars, id); });
}

/* Пар над кофемашиной кофейни: несколько мягких клубов поднимаются и тают, пока заведение открыто. */
function drawSteam(mins) {
  const room = ROOMS.get("cafe");
  if (!room) return;
  if (!scene.steam) {
    const [sx, sy] = withRoom(room, () => iso(...STEAM_AT));
    scene.steam = { x: sx, y: sy, puffs: Array.from({ length: 5 }, () => glowImage(sx, sy, 20, 20, 0xffffff, 5000)) };
  }
  const place = placeOf("cafe");
  const open = layers.life && Boolean(place) && placeIsOpen(place);
  scene.steam.puffs.forEach((puff, i) => {
    const t = (((mins * 1.4 + i / 5) % 1) + 1) % 1;
    puff.setPosition(scene.steam.x + Math.sin(t * 5 + i) * 2.5 + t * 4, scene.steam.y - t * 34)
      .setDisplaySize(7 + t * 20, 7 + t * 20)
      .setAlpha(open ? Math.sin(t * Math.PI) * 0.34 : 0);
  });
}

/* Общий проход по глубине: объекты мира, залы заведений (`roomRows`), люди и машины сортируются вместе. */
function drawAmbient(mins, roomRows = []) {
  if (!outer) return;
  const rows = [...outer.statics, ...roomRows];
  scene.signals.forEach((signal) => {
    const color = Traffic.signal(mins, signal.axis);
    signal.lamps.forEach((lamp) => {
      const on = lamp.name === color;
      lamp.dot.setFillStyle(lamp.color, on ? 1 : 0.14);
      lamp.shine.setAlpha(on ? 0.6 : 0.08);
      lamp.halo.setAlpha(on ? 0.5 : 0);
    });
  });
  drawCity(rows);
  isoSort(rows);
  rows.forEach((row, index) => {
    row.el.setDepth(1000 + index);
    if (row.after) row.after.forEach((el, k) => el.setDepth(1000 + index + 0.1 * (k + 1)));
  });
  drawSteam(mins);
  scene.smoke.forEach(({ puff, at, off }) => {
    const t = ((mins + off) % 4 + 4) % 4 / 4;
    puff.setPosition(at[0] + t * 7, at[1] - t * 25).setScale(0.6 + t * 1.6).setAlpha((1 - t) * 0.5);
  });
  scene.trees.forEach(({ leaves, off }) => leaves.setX(Math.sin(mins * 1.5 + off) * 1.2));
  outer.birds.forEach((bird, i) => {
    bird.setPosition(-1300 + ((mins * 16 + i * 70 + i % 2 * 400) % 2600), -330 + i * 22 + Math.sin(mins * 0.9 + i) * 14)
      .setScale(1.2, 0.35 + 0.65 * Math.abs(Math.sin(mins * 38 + i * 1.7))).setVisible(layers.life);
  });
}

function updateSceneLight(light, mins) {
  const night = nightLevel(light, mins);
  if (scene.tint && light.tint) scene.tint.setFillStyle(Phaser.Display.Color.HexStringToColor(light.tint).color);
  scene.glows.forEach((glow) => glow.setAlpha(night * 0.55));
  scene.halos.forEach((halo) => halo.setAlpha(night * 0.8));
  scene.windowGlows.forEach((glow) => glow.setAlpha(night * 0.95));
  // Окно и табличка открытия каждого зала рисуются геометрией, их цвет зависит от снимка.
  ROOMS.forEach((room) => withRoom(room, () => {
    scene.sun.setAlpha(light.sun);
    const polygon = (points) => points.map((p) => { const [x, y] = iso(...p); return { x, y }; });
    if (!scene.sign) {
      scene.sky = phaserScene.add.graphics();
      scene.skyPoints = polygon([[2.25, 0.05, 55.6], [5.75, 0.05, 55.6], [5.75, 0.05, 76], [2.25, 0.05, 76]]);
      scene.sign = phaserScene.add.graphics();
      scene.signPoints = polygon([[0.07, 5.7, 39.2], [0.07, 6.1, 39.2], [0.07, 6.1, 45.8], [0.07, 5.7, 45.8]]);
      room.skyLayer = scene.sky;
      room.signLayer = scene.sign;
    }
    scene.sky.clear();
    if (room.theme === "cafe") scene.sky.fillStyle(Phaser.Display.Color.HexStringToColor(light.sky).color, 0.45).fillPoints(scene.skyPoints, true);
    const place = placeOf(room.id);
    const open = Boolean(place) && placeIsOpen(place);
    scene.sign.clear().fillStyle(open ? 0x6fcf8a : 0xd9604c).fillPoints(scene.signPoints, true);
  }));
}

function focusPlace(id) {
  const room = ROOMS.get(id);
  if (!room || !phaserScene) return;
  [CAM.cx, CAM.cy] = withRoom(room, () => iso(4, 4, 22));
  CAM.z = Math.max(CAM.z, 1.25);
  camApply();
}

function camReset() {
  HOME = { x: VB.x - 230, y: VB.y - 150, w: VB.w + 460, h: VB.h + 300 };
  CAM.cx = HOME.x + HOME.w / 2;
  CAM.cy = HOME.y + HOME.h / 2;
  CAM.z = 1;
  camApply();
}

function camApply() {
  if (!phaserScene) return;
  const room = document.getElementById("room");
  const w = room.clientWidth || 960, h = room.clientHeight || 580;
  CAM.z = Phaser.Math.Clamp(CAM.z, CAM.min, CAM.max);
  CAM.cx = Phaser.Math.Clamp(CAM.cx, -1500, 1500);
  CAM.cy = Phaser.Math.Clamp(CAM.cy, -500, 900);
  view.k = Math.min(w / HOME.w, h / HOME.h) * CAM.z;
  view.w = w / view.k;
  view.h = h / view.k;
  view.x = CAM.cx - view.w / 2;
  view.y = CAM.cy - view.h / 2;
  phaserScene.cameras.main.setSize(w, h).setZoom(view.k).centerOn(CAM.cx, CAM.cy);
  tagK = Phaser.Math.Clamp(CAM.z ** -0.6, 0.6, 1.45);
  if (scene && scene.tint) scene.tint.setPosition(CAM.cx, CAM.cy).setDisplaySize(view.w * 1.05, view.h * 1.05);
  document.getElementById("cam-home").disabled = Math.abs(CAM.z - 1) < 0.01 && Math.abs(CAM.cx - HOME.x - HOME.w / 2) < 2 && Math.abs(CAM.cy - HOME.y - HOME.h / 2) < 2;
  if (snap) { drawActors(); renderFloat(); }
}

function zoomAt(factor, px, py) {
  const room = document.getElementById("room");
  const x = px ?? room.clientWidth / 2, y = py ?? room.clientHeight / 2;
  const wx = view.x + x / view.k, wy = view.y + y / view.k;
  CAM.z = Phaser.Math.Clamp(CAM.z * factor, CAM.min, CAM.max);
  const k = Math.min(room.clientWidth / HOME.w, room.clientHeight / HOME.h) * CAM.z;
  CAM.cx = wx - x / k + room.clientWidth / k / 2;
  CAM.cy = wy - y / k + room.clientHeight / k / 2;
  camApply();
}

function setLayer(name, on) {
  layers[name] = on;
  try { localStorage.setItem(`layer.${name}`, on ? "1" : "0"); } catch (e) { /* хранилище необязательно */ }
  if (snap) drawActors();
}

function camInit() {
  const room = document.getElementById("room");
  const pointers = new Map();
  let drag = null, pinch = 0;
  ["names", "life"].forEach((name) => {
    try { const saved = localStorage.getItem(`layer.${name}`); if (saved !== null) layers[name] = saved === "1"; } catch (e) { /* хранилище необязательно */ }
    const box = document.getElementById(`lay-${name}`);
    box.checked = layers[name];
    box.addEventListener("change", () => setLayer(name, box.checked));
  });
  room.addEventListener("wheel", (event) => {
    event.preventDefault();
    const rect = room.getBoundingClientRect();
    zoomAt(Math.exp(-event.deltaY * (event.ctrlKey ? 0.01 : 0.0016)), event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  room.addEventListener("pointerdown", (event) => {
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      drag = { x: event.clientX, y: event.clientY, cx: CAM.cx, cy: CAM.cy };
      cameraMoved = false;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = Math.hypot(a.x - b.x, a.y - b.y);
      drag = null;
    }
  });
  room.addEventListener("pointermove", (event) => {
    const p = pointers.get(event.pointerId);
    if (!p) return;
    p.x = event.clientX; p.y = event.clientY;
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const rect = room.getBoundingClientRect();
      zoomAt(dist / pinch, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      pinch = dist; cameraMoved = true; return;
    }
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!cameraMoved && Math.hypot(dx, dy) < 5) return;
    if (!cameraMoved) room.setPointerCapture(event.pointerId);
    cameraMoved = true;
    room.classList.add("drag");
    CAM.cx = drag.cx - dx / view.k; CAM.cy = drag.cy - dy / view.k;
    camApply();
  });
  const up = (event) => {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinch = 0;
    if (!pointers.size) { drag = null; room.classList.remove("drag"); }
  };
  room.addEventListener("pointerup", up);
  room.addEventListener("pointercancel", up);
  room.addEventListener("lostpointercapture", up);
  room.addEventListener("dblclick", () => {
    if (phaserScene.input.hitTestPointer(phaserScene.input.activePointer).some((obj) => obj.getData("clientId"))) return;
    camReset();
  });
  document.getElementById("cam-in").addEventListener("click", () => zoomAt(1.35));
  document.getElementById("cam-out").addEventListener("click", () => zoomAt(1 / 1.35));
  document.getElementById("cam-home").addEventListener("click", () => camReset());
  document.getElementById("cam-traffic").addEventListener("click", () => {
    [CAM.cx, CAM.cy] = iso((ROAD_X0 + ROAD_X1) / 2, (ROAD_X0 + ROAD_X1) / 2, G);
    CAM.z = 1.45;
    camApply();
  });
  document.body.addEventListener("keydown", (event) => {
    if (event.target !== document.body || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "+" || event.key === "=") zoomAt(1.25);
    else if (event.key === "-" || event.key === "_") zoomAt(1 / 1.25);
    else if (event.key === "0") camReset();
  });
}

class LoomScene extends Phaser.Scene {
  constructor() { super("loom"); }
  create() {
    phaserScene = this;
    this.cameras.main.setBackgroundColor(GRASS);
    buildScene();
    camInit();
    this.scale.on("resize", () => camApply());
    if (snap) renderWorld();
  }
  update() {
    if (snap && scene) drawActors();
  }
}

phaserGame = new Phaser.Game({
  type: Phaser.AUTO,
  parent: "room",
  transparent: false,
  backgroundColor: GRASS,
  scale: { mode: Phaser.Scale.RESIZE, width: "100%", height: "100%" },
  render: { antialias: true, roundPixels: false },
  input: { activePointers: 3, keyboard: false, mouse: { preventDefaultWheel: false } },
  audio: { noAudio: true },
  fps: { target: 30 },
  scene: LoomScene,
});
