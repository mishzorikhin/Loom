/* Тема кофейни: что стоит в зале.
   CAFE_THEME = {apron, base(), furniture(put, cups)}. base() склеивает слои зала по порядку (стены, окно, декор, ковёр, тени), furniture() ставит
   мебель через put(глубина, svg, коробка) для общей сортировки. STEAM_AT — точка носика кофемашины для пара. Подключается в rooms.js (THEMES). */

/* Пар над кофемашиной: параметры для сцены (мировая точка носика, зал кофейни). */
const STEAM_AT = [4.05, 1.2, 52];

const CAFE_THEME = {
  apron: true,
  base: () => cafeWallsSvg() + cafeWindowSvg() + cafeDecorSvg() + cafeRugSvg() + cafeShadowsSvg(),
  furniture(put, cups) {
    put(1.2, cafePlantSvg(0.4, 0.4), BOX_AT(0.4, 0.4, 0.4, 0.4));
    put(14.8, cafePlantSvg(7.3, 7.1), BOX_AT(7.3, 7.1, 0.4, 0.4));
    put(5.24, cafeCounterSvg(), BOX_AT(2.05, 0.78, 3.9, 0.92));
    put(2.475, cafeDeskSvg(), BOX_AT(0.35, 1.0, 0.75, 1.5));
    TABLES.forEach((table) => {
      const d = table.x + table.y + 1.1;
      put(d, cafeTableSvg(table.x, table.y), BOX_AT(table.x, table.y, 1.1, 1.1));
      cups.push(put(d + 0.01, box(table.x + 0.4, table.y + 0.42, 0.2, 0.2, 5, "#6b4426", "#fffaf0", "#d8cdb8", TABLE_TOP), BOX_AT(table.x, table.y, 1.1, 1.1)).setVisible(false));
    });
    SEATS.forEach((seat) => put(seat.at[0] + seat.at[1] - 0.05, cafeChairSvg(seat.at[0], seat.at[1], seat.face), BOX_AT(seat.at[0] - 0.25, seat.at[1] - 0.25, 0.5, 0.5)));
  },
};
