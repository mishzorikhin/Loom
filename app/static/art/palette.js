/* Палитра мира: единственное место, где правятся цвета.
   Что даёт: объект PAL и помощник cool(цвет, доля) — подмешивает холодный тон тени вместо чёрного.
   Как менять: правь значения в PAL; формы рисунков не затрагиваются. Ключи: grass (три тона газона), pave/paveSeam/paveLip/paveLipE/paveHi
   (тротуар), kerb, road/roadX/roadEdge (асфальт), paint/yellow (разметка), shadow/shadowWarm/tint (цвета теней и холодного тона граней),
   walls/roofs (стены и кровли домов по кругу), glass/frame (окна), leaf/pine/trunk (деревья), bloom (цветы), metal (графит опор),
   wood/terra/mint/cream/graphite (материалы залов), teal/neon (подсветка ЦОДа), carColors (кузова машин).
   Свет: верх грани светлее, левая (южная) средняя, правая (восточная) холоднее; источник сверху-слева. */

const PAL = {
  grass: ["#9dd679", "#94d072", "#8cca6a"], // полосы газона: едва заметная разница тонов
  grassBase: "#94d072",
  pave: "#ece4d5", paveSeam: "#ddd3c1", paveLip: "#d4c8b4", paveLipE: "#c4b6a4", paveHi: "#fffdf8",
  kerb: "#f7f1e6",
  road: "#667386", roadX: "#6a778a", roadEdge: "#566274",
  paint: "#fdfcf7", yellow: "#f8c94b",
  shadow: "#3d5a9a", // тень на земле: холодный синий, прозрачный
  shadowWarm: "#6a3f45", // тень на тёплом полу залов
  tint: "#5d62ae", // подмешивается в правые (теневые) грани
  walls: ["#f9dccb", "#f8f3ea", "#cdeedf", "#d2e7f8", "#fbeec6"],
  roofs: ["#da6a4e", "#2fa7a2", "#4f82c8", "#e3ab3c"],
  glass: ["#f0fbff", "#b9e6f6", "#8accea"],
  frame: "#fffaf0",
  leaf: { light: "#a6e585", mid: "#54b85f", dark: "#2e9157" },
  pine: { light: "#46b872", dark: "#1f8656" },
  trunk: ["#b8814f", "#946239"],
  bloom: ["#ff8fa3", "#fff3c9", "#ffd45c", "#c9a5f2", "#ff9f5a"],
  metal: ["#59667d", "#44506a", "#7b88a0"],
  wood: { light: "#f0c58b", mid: "#e0a96b", dark: "#b97f47", leg: "#8a5a33" },
  terra: { light: "#ee8a69", mid: "#d96d4d", dark: "#ae4f37" },
  mint: { light: "#9fe0c9", mid: "#6fcdb0", dark: "#4aa98e" },
  cream: { light: "#fff6e4", mid: "#f8e8cc", dark: "#e3cfb0" },
  graphite: { light: "#5d6c84", mid: "#44526a", dark: "#2f3a4f", deep: "#222b3d" },
  teal: "#35d9d0", neon: ["#5ff2ea", "#8ff59a", "#ffd25a", "#ff8a7a"],
  carColors: ["#ff6a5c", "#4aa5f2", "#ffc93f", "#f6f3ea", "#4fc58a", "#9d7ee6", "#ff9a3d", "#38c9c4"],
};

/* Тень грани: подмешать холодный тон вместо чёрного. */
const cool = (c, t) => mix(c, PAL.tint, t);
