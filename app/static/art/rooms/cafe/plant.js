/* Растение в горшке.
   cafePlantSvg(x, y): терракотовый горшок и семь листьев (PAL-зелень), x/y — угол клетки в зале. */

function cafePlantSvg(x, y) {
  const [sx, sy] = iso(x + 0.2, y + 0.2, 14);
  const leaf = (dx, dy, rx, ry, rot, fill) => `<ellipse cx="${dx}" cy="${dy}" rx="${rx}" ry="${ry}" fill="${fill}" transform="rotate(${rot} ${dx} ${dy})"/><path d="M${dx} ${dy + ry * 0.8} L${dx} ${dy - ry * 0.7}" stroke="${lighten(fill, 0.3)}" stroke-width="0.6" stroke-opacity="0.6" transform="rotate(${rot} ${dx} ${dy})"/>`;
  return box(x, y, 0.4, 0.4, 14, "#e0795a", "#c65f43", "#9e4731")
    + box(x - 0.035, y - 0.035, 0.47, 0.47, 2.2, "#ee8a69", "#e0795a", "#b55239", 12.4)
    + `<polygon points="${[[x + 0.04, y + 0.04, 14.6], [x + 0.36, y + 0.04, 14.6], [x + 0.36, y + 0.36, 14.6], [x + 0.04, y + 0.36, 14.6]].map(pt).join(" ")}" fill="#7a4a36"/>`
    + `<g transform="translate(${sx.toFixed(1)} ${sy.toFixed(1)})">`
    + leaf(-10, -10, 3.8, 11, -50, "#2f9a55") + leaf(10, -10, 3.8, 11, 50, "#35a85d")
    + leaf(-6, -16, 4, 12, -28, "#35a85d") + leaf(6, -16, 4, 12, 28, "#3fb264")
    + leaf(-3, -21, 4, 12, -10, "#3fb264") + leaf(3, -21, 4, 12, 12, "#52c477")
    + leaf(0, -25, 3.8, 12, 0, "#78dc94")
    + "</g>";
}
