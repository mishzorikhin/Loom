/* Стол кофейни.
   TABLE_TOP — высота столешницы (24, привязана к поясу сидящего гостя). cafeTableSvg(x, y): крестовина, ножка, столешница 1.1 x 1.1, салфетница, вазочка. */

/* Высота столешницы. Люди в зале крупнее мебели, поэтому стол поднят до уровня пояса сидящего: иначе гость «стоит у стола». */
const TABLE_TOP = 24;

function cafeTableSvg(x, y) {
  const top = TABLE_TOP;
  const slab = 3.2;
  const parts = [
    box(x + 0.15, y + 0.46, 0.8, 0.09, 1.6, "#b97f47", "#9a6a3a", "#7d5530", 0),
    box(x + 0.46, y + 0.15, 0.09, 0.8, 1.6, "#b97f47", "#9a6a3a", "#7d5530", 0),
    box(x + 0.47, y + 0.47, 0.16, 0.16, top - slab - 1.6, "#c98d55", "#b97f47", "#9a6a3a", 1.6),
    box(x + 0.4, y + 0.4, 0.3, 0.3, 1.6, "#b97f47", "#9a6a3a", "#7d5530", top - slab - 1.6),
    box(x, y, 1.1, 1.1, slab, "#fbe6bf", "#e0a96b", "#bb7f47", top - slab),
    ov([[x + 0.08, y + 0.08, top], [x + 1.02, y + 0.08, top], [x + 1.02, y + 1.02, top], [x + 0.08, y + 1.02, top]], "#fff3d6", 0.35),
    seg([x, y + 1.1, top], [x + 1.1, y + 1.1, top], "#fff7e2", 1.2), seg([x + 1.1, y, top], [x + 1.1, y + 1.1, top], "#e8c791", 1.2),
    // салфетница, сахарница и вазочка
    box(x + 0.14, y + 0.78, 0.16, 0.1, 4, "#dbe2ec", "#9aa3a7", "#7f888c", top),
    box(x + 0.9, y + 0.72, 0.1, 0.1, 3, "#fffaf0", "#e8e0cf", "#cfc4ae", top),
  ];
  const [vx, vy] = iso(x + 0.9, y + 0.22, top);
  parts.push(`<path d="M${(vx - 1.8).toFixed(1)} ${vy.toFixed(1)} L${(vx - 1.3).toFixed(1)} ${(vy - 4.6).toFixed(1)} L${(vx + 1.3).toFixed(1)} ${(vy - 4.6).toFixed(1)} L${(vx + 1.8).toFixed(1)} ${vy.toFixed(1)} Z" fill="#a9d6e6" fill-opacity="0.85"/><path d="M${vx.toFixed(1)} ${(vy - 4).toFixed(1)} L${(vx - 0.4).toFixed(1)} ${(vy - 9).toFixed(1)}" stroke="#3f8a52" stroke-width="0.8"/><circle cx="${(vx - 0.4).toFixed(1)}" cy="${(vy - 10).toFixed(1)}" r="1.9" fill="#e87a6a"/><circle cx="${(vx + 1.1).toFixed(1)}" cy="${(vy - 8).toFixed(1)}" r="1.4" fill="#f6dc78"/>`);
  return parts.join("");
}
