/* Тема ЦОДа: что стоит в зале.
   DC_THEME = {apron: false, base(), furniture(put)}; подключается в rooms.js (THEMES). Три серверные стойки заменяют столы. */

const DC_THEME = {
  apron: false,
  base: () => dcWallsSvg() + dcWindowSvg() + dcDecorSvg() + dcRugSvg() + dcShadows(),
  furniture(put) {
    put(1.2, dcCoolerSvg(0.4, 0.4), BOX_AT(0.4, 0.4, 0.5, 0.5));
    put(14.8, dcCoolerSvg(7.3, 7.1), BOX_AT(7.3, 7.1, 0.5, 0.5));
    put(5.24, dcCounterSvg(), BOX_AT(2.05, 0.78, 3.9, 0.92));
    put(2.475, dcDeskSvg(), BOX_AT(0.35, 1.0, 0.75, 1.5));
    TABLES.forEach((table) => put(table.x + table.y + 1.1, dcRackSvg(table.x, table.y), BOX_AT(table.x, table.y, 1.1, 1.1)));
  },
};
