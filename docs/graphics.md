# Графика Loom

Как устроены рисунки мира и как их менять. Правила проекта — в `AGENTS.md`, поведение страницы — в `docs/mvp.md`. Здесь только графика: где что лежит, как рисуется и как проверить результат.

## Стиль

Чистый светлый «архитектурный макет / гуашь» (ориентиры: Townscaper, Monument Valley, Islanders).

- плоские насыщенные пастельные цвета, мягкий градиент на гранях, чёткие контуры там, где нужно;
- свет один, сверху-слева (из направления `-x`): верх грани самый светлый, левая (южная, `+y`) грань средняя, правая (восточная, `+x`) холодная и темнее; тени падают вправо-вниз;
- тени цветные (сине-фиолетовые `PAL.shadow`, `PAL.tint`), без серого и чёрного; на тёплом полу залов `PAL.shadowWarm`;
- на крупных поверхностях нет зерна, трещин, пятен и виньетки; днём картинка не затемняется;
- кофейня тёплая (терракота, дерево, мятные панели), ЦОД холодный (графит, бирюза, неоновые полоски).

## Карта папок

Все файлы в `app/static/art/`. Рисунок — функция, которая возвращает SVG-строку (в мировых координатах, см. «Координаты»). Файлы подключаются обычными тегами в `index.html` без сборщика; функции глобальные. Порядок тегов важен только для констант, вычисляемых при загрузке (`HOUSES`, `CAR_COLORS`, `TREE_SHADOW`, `DC_LED` используют `PAL` и помощники): сначала `palette.js`, `util.js`, потом остальное.

```
app/static/
  app.js            базовые iso/face/box/seg/mix/shade/lighten/pt, looksOf, снимок, окна
  art/
    palette.js      PAL — вся палитра; cool(цвет, доля) — холодная тень вместо чёрного
    util.js         rng, gface, ov, lines, radial, vertical, BLUR, SUN, hull, softShadow, softFloorShadows, BOX_AT
    layout.js       G, ROAD_X0/X1, SIDEWALKS, PROPS_FIXED, treeKind, onGrass, worldProps, propDepth
    light.js        TINT и daylight(mins): небо, солнце, тинт суток
    depth.js        isoSort(rows): порядок рисования объектов
    ground/
      lawn.js       lawnSvg: газон полосами трёх тонов, цветы
      paving.js     pavingSvg, pavementEdges: тротуары
      roads.js      roadSurfaceSvg, kerbSvg, kerbHighlightSvg, laneMarkingsSvg: асфальт, бордюры, разметка, стрелки, парковка
      zebra.js      zebraSvg: переходы и стоп-линии
      land.js       landSvg: порядок слоёв земли
    buildings/
      list.js       HOUSES: список домов
      houses.js     houseSvg, houseShadows, glow, smokeSvg
    nature/
      trees.js      treeSvg (4 вида), foliage, trunkSvg
      bushes.js  rocks.js  beds.js  birds.js
    props/
      lamp.js  bench.js  bin.js  hydrant.js  sign.js  shadowdot.js
      trafficlight.js   makeTrafficSignal(spec): светофор на графике Phaser
    people/
      figure.js     figureSvg: сборка человека
      legs.js  hair.js  face.js (personFaceSvg)  clothes.js (personTorso, personApron)
    vehicles/
      kinds.js      CAR_COLORS, CAR_KINDS (габарит, высота кузова и крыши, кабина, окна)
      model.js      carOct, carLoft, carTone, carGlass: лофты из колец со срезанными углами, тон грани по нормали
      cars.js       carSvg: угловатый low-poly седан/хэтчбек/универсал/такси (бамперы, порог, арки, стёкла в рамках, решётка, фары)
      brake.js      carBrakeSvg: яркие стоп-сигналы
      brake.js      carBrakeSvg: стоп-сигналы
    rooms/cafe/     floor walls window decor rug plant desk counter table chair shadows theme
    rooms/datacenter/  floor walls window decor rug counter rack desk cooler shadows theme
  rooms.js          каркас залов: ROOM_DEFS, withRoom, THEMES = {cafe, dc}, внешние заведения
  world.js          outer, layers, PED_PATHS, CARS, pedDensity (состояние и конфигурация, не рисунки)
  phaser-world.js   Phaser: текстуры, сцена, цикл, камера, свет окон и фонарей
```

## Что где править

| Хочу изменить | Файл и функция | Параметры |
| --- | --- | --- |
| любой цвет мира | `art/palette.js`, `PAL` | ключи `grass`, `pave*`, `road*`, `paint`, `walls`, `roofs`, `leaf`, `wood`, `terra`, `mint`, `neon`, `carColors` |
| тон или шаг полос газона | `ground/lawn.js`, `lawnSvg` | `PAL.grass`, клетка 4, плотность цветов 0.16 |
| тротуар, швы, кромку | `ground/paving.js` | `PAL.pave*`, шаг швов 2.2 |
| асфальт, бордюр, цвет разметки | `ground/roads.js` | `PAL.road`, `PAL.paint`, `PAL.yellow` |
| переходы | `ground/zebra.js`, `zebraSvg` | число полос 7, шаг 0.55 |
| дом: окна, дверь, кровлю, дымоход | `buildings/houses.js`, `houseSvg` | `SHUTTERS`, `DOORS`, `rows`, высота кровли `r` |
| добавить или перекрасить дом | `buildings/list.js`, `HOUSES` | `{x, y, w, d, h, wall, roof, ridge, chimney}` |
| деревья | `nature/trees.js`, `treeSvg`/`foliage` | виды 0..3, цвета `PAL.leaf`, `PAL.pine` |
| фонари, скамейки, урны, гидранты | `props/*.js` | одна функция на предмет |
| где что стоит на улице | `layout.js`, `PROPS_FIXED`, `worldProps` | `{kind, x, y, s, v, axis}` |
| светофор | `props/trafficlight.js` | цвета в `colors`, размеры корпуса |
| людей: пропорции, ноги | `people/figure.js`, `people/legs.js` | `look`, `pose`, `staff` |
| причёски | `people/hair.js` | `style` 0 короткие, 1 длинные, 2 пучки |
| одежду, фартук | `people/clothes.js` | `kind` 0..5, добавить фасон — элемент `details` и `h % 6` в `figure.js` |
| лицо, очки | `people/face.js` | `glasses` |
| цвета одежды, кожи, волос | `SHIRTS`, `SKIN`, `HAIR`, `PANTS` в `app.js` | массивы |
| машины: цвет, размер, форму | `vehicles/kinds.js` | `CAR_COLORS`, `CAR_KINDS` |
| машины: детали, стекло, колёса | `vehicles/cars.js`, `carSvg` | `CAR_GREY`, `CAR_DARK`, `CAR_GLASS`, колёса (`R`, `zc`), бамперы, решётка, фары |
| машины: свет и тон граней | `vehicles/model.js` | `CAR_SUN`, `carTone`, `carGlass` |
| стоп-сигналы | `vehicles/brake.js` | положение огней |
| зал кофейни | `rooms/cafe/*.js` | по файлу на предмет; состав и порядок слоёв — `theme.js` |
| зал ЦОДа | `rooms/datacenter/*.js` | то же; неоновые цвета — `PAL.neon` (`DC_LED`) |
| вечер, ночь, небо | `light.js`, `TINT`; `LIGHT` в `app.js` для неба и солнца | `[минуты, цвет]` |
| свет окон, фонарей, пар | `phaser-world.js`: `updateSceneLight`, `scene.glows`, `drawSteam` | прозрачность `night` |
| направление теней | `util.js`, `SUN` | вектор `[x, y]`; у машин тон грани считает `carTone` по нормали (`model.js`) |

## Палитра

`PAL` (`art/palette.js`) — единственное место правки цветов. Группы:

- земля: `grass` (три тона газона), `pave`, `paveSeam`, `paveLip` (боковая грань южного края), `paveLipE` (восточного), `paveHi` (светлая кромка), `kerb`, `road`, `roadX` (перекрёсток), `roadEdge`, `paint` (белая разметка), `yellow` (осевая);
- тени: `shadow` (на земле), `shadowWarm` (на полу залов), `tint` (примешивается в правые грани через `cool(цвет, доля)`);
- дома: `walls` (персиковый, белый, мятный, голубой, сливочный), `roofs` (терракота, бирюза, синий, горчичный), `glass`, `frame`;
- природа: `leaf` {light, mid, dark}, `pine`, `trunk`, `bloom`;
- материалы: `metal`, `wood`, `terra`, `mint`, `cream`, `graphite`, `teal`, `neon`;
- `carColors` — кузова; индекс приходит от сервера (`meta.col`).

Правило тона: левая грань — цвет материала, правая — `cool(цвет, 0.2..0.3)`, верх — `lighten(цвет, 0.1..0.2)`. Чёрный и серый для теней не использовать.

## Координаты

`iso(x, y, z)` из `app.js`: `sx = (x - y) * TW`, `sy = (x + y) * TH - z`, `TW = 36`, `TH = 18`, `z` в пикселях вверх. Мировые `x`, `y` — клетки.

- ось `x` уходит вправо-вниз, ось `y` влево-вниз; видимые грани: верх, южная (`+y`, слева), восточная (`+x`, справа);
- земля лежит на `G = -15` (низ плиты зала); дороги идут по `ROAD_X0 = 11.5 .. ROAD_X1 = 15.5` по обеим осям;
- зал — квадрат `ROOM_W × ROOM_D = 8 × 8` клеток, стены высотой `WALL = 96`, дверь в левой стене; рисунки зала считаются в его локальных координатах, а в мир зал ставит сдвиг `ISO_OFF` (`withRoom` в `rooms.js`: кофейня `(0, 0)`, ЦОД `(-4, 19.5)`);
- хелперы: `face(points, fill, alpha)` (многоугольник с обводкой того же цвета), `box(x, y, w, d, h, top, south, east, z0)`, `seg`, а из `util.js` — `ov` (без обводки), `lines`, `gface` (плоскость на земле).

Центр людей и предметов — ступни в точке `iso(x, y, G)`; фигура рисуется вверх от `(0, 0)`.

## Как рисунок становится картинкой на экране

1. `phaser-world.js`, `svgObject(markup)`: SVG-строка чистится (`cleanMarkup` подставляет `var(--sky)`, убирает `.ring`), её габариты меряет скрытый `<svg>` (`getBBox`, запас 14 пикселей, если есть `<filter>`), потом она растеризуется в текстуру Phaser (масштаб до 2, не больше 4096 пикселей). **Кэш по тексту разметки:** одинаковая строка даёт одну текстуру. Поэтому деревьев столько текстур, сколько видов, а не штук; размер объекта задаёт масштаб `p.s`. Больше 256 неиспользуемых текстур вычищаются.
2. Земля одна большая картинка, `landObject` режет её на плитки 1024 с тремя зонами чёткости (у перекрёстка 1.4, остальной квартал 0.95, края 0.5).
3. Дом, дерево, зал сохраняют структуру: `polygon[style]` у дома — окна, которые Phaser выносит в отдельный светящийся слой (глубина 8002, прозрачность `night`); `.puff` — дым (Phaser рисует круги сам); `.sway` у дерева — крона, качается отдельно; у человека `.leg`, `.arm`, `.upper`, `.body`, `.ring` — страница режет ноги и руки в отдельные текстуры. Эти имена менять нельзя.
4. Глубина: `drawAmbient` собирает объекты мира, залов, людей и машин в строки `{el, d, box}`, `isoSort` (`art/depth.js`) упорядочивает их (если коробки разделены по оси, дальняя первой; иначе по `d = x + y`), и объекты получают `depth = 1000 + индекс`. Вне сортировки: земля `-1000`, тени домов `-900`, тинт суток `7900` (умножение), свет фонарей `8000/8001`, окна `8002`, птицы `9000`, подписи `10000+`. Для нового предмета нужен корректный `box`.
5. Свет суток: `applyLight` (`app.js`) вызывает `daylight(mins)` из `art/light.js` (она перекрывает версию из `app.js`: файл подключён позже). `tint` ложится прямоугольником с умножением под светом окон и фонарей (`scene.tint`), `filter` ставится на canvas. День: белый тинт, картинка не меняется.

## Как добавить

- **Дом.** Строка в `buildings/list.js`: `{x, y, w, d, h, wall: PAL.walls[i], roof: PAL.roofs[j], ridge: "x"|"y"}`. Тень, сортировка и свет окон подхватятся сами. Проверь, что дом не лежит на улице (`onGrass`).
- **Дерево.** Новый вид: ветка `v === 4` в `treeSvg` (`nature/trees.js`), крону оберни в `<g class="sway">`; в `treeKind` (`layout.js`) допиши вероятность. Деревья на улице — в `PROPS_FIXED`.
- **Предмет улицы.** Файл `props/имя.js` с функцией `имяSvg()` (ступни в `(0, 0)`), тег в `index.html`, ключ в таблице `markup` внутри `worldBuild` (`phaser-world.js`), строки в `PROPS_FIXED`.
- **Машина.** Новый вид: ключ в `CAR_KINDS` (`vehicles/kinds.js`: `L`, `W`, `body`, `roof`, `cab`, `panes`), имя в `CAR_KIND_NAMES` (`phaser-world.js`), если сервер пришлёт новый индекс `k`; новый цвет — в `PAL.carColors`.
- **Вид человека.** Причёска: ветка `style` в `people/hair.js`; одежда: элемент `details` в `people/clothes.js` и модуль `h % 6` в `figure.js`; цвета — массивы в `app.js`.
- **Заведение (тема зала).** Создай `art/rooms/<имя>/` с файлами пола, стен, окна, декора, стойки и т. д. и `theme.js` с объектом `{apron, base(), furniture(put)}` по образцу `CAFE_THEME`; подключи теги в `index.html` до `rooms.js`, добавь тему в `THEMES` и строку в `ROOM_DEFS` (`rooms.js`). Размеры зала общие, мебель ставится через `put(глубина, svg, BOX_AT(...))`.

## Проверка

1. Статика отдаётся сервером с диска: `SIM_DB=/путь/sim.db SIM_IDLE_PAUSE=0 python3 -m uvicorn app.main:app --port 8431`; прогон на модели не нужен.
2. Снимок: `node scripts/art-shot.mjs out.png 1600 900 "js" http://localhost:8431` (`CHROME_BIN` или puppeteer chrome-headless-shell; печатает ошибки консоли).
3. Время суток: `"snap.run.clock_min=780;snap.run.day_end=1440;applyLight(true)"` (780 день, 1130 вечер, 1320 ночь).
4. Камера: `"[CAM.cx,CAM.cy]=iso(4,2,30);CAM.z=3.4;camApply()"`; зумы от 0.42 до 3.4, проверяй 0.5, 1, 1.7, 3.4.
5. Машины отдельно: песочница `http://localhost:8431/static/art/sandbox/cars.html` — все виды в четырёх направлениях, ползунок масштаба, флажок стоп-сигналов; правки в `art/vehicles/` видны после перезагрузки.
6. Улица с людьми и машинами: подставь `scripts/art-testframe.js` в тот же `js` (на копии базы и при прогоне на паузе).
6. Рефакторинг без смены вида: сделай снимки до и после и сравни попиксельно (PIL `ImageChops.difference`), разница должна быть нулевой. Так проверено разделение на `art/`.
7. `npm run test:traffic` загружает `art/*` и `world.js` в vm по тегам из `index.html`; `PYTHONPATH=. python3 -m unittest discover -s tests` — Python.

## Известные ограничения

- Заведения «внешних агентов» (`THEMES.custom` в `rooms.js`) строятся из `wallsSvg`, `windowSvg`, `chairSvg`, `plantSvg` из `app.js` с подменой цветов регулярками: их стиль старый, пока эти функции не перенесены в `art/`.
- `wallDecorSvg`, `sunSvg`, `shadowSvg` из `app.js` (декор стен кофейни и пятно света) остались со старыми цветами; в `art/rooms/cafe/decor.js` лежит лишь обёртка.
- Спицы колёс машин (центр колеса 5,8 px и колпак согласованы с `cars.js` вручную), маркеры событий города и пузыри рисует `phaser-world.js` графикой Phaser, их цвета не из `PAL`.
- Ночной тинт умножает и ореолы светофоров (они внутри объектов сцены), поэтому ночью красный сигнал тусклее фонарей.
- Окно кофейни показывает небо через `var(--sky)`, цвет подставляет Phaser (`light.sky`), вид за стеклом нарисован и не соответствует реальным домам.
- Рисунок ЦОДа и кофейни по планировке один (стойка у задней стены, три объекта на месте столов): новые темы повторяют каркас.

## Сидящие гости

Поза `sit` рисуется в профиль: `personLegs(pants, shoe, true)` (`art/people/legs.js`) кладёт бёдра горизонтально вправо, колени вынесены вперёд, голени идут вниз. Страница отражает фигуру по стороне стула (`app.js`, `drawActors`): у стула `n` человек смотрит влево-вниз, у `w` вправо-вниз, то есть всегда на стол. Высота посадки: `SEAT_Z = 10` (подушка стула, `art/rooms/cafe/chair.js`) и смещение `up = 13` в `art/people/figure.js`; если менять высоту стула или стола (`TABLE_TOP`), эти числа нужно менять вместе. Столешница перекрывает колени за счёт сортировки глубины (`art/depth.js`): сидящий стоит на 0,5 клетки дальше от зрителя, чем край стола. Проверка: `clock_min` около середины `stay_min` визита, камера на стол (`focusPlace('cafe')`, `CAM.z = 4–7`).
