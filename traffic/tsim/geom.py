"""Ломаные с параметризацией по длине, смещение, пересечения, кривые Безье."""

from __future__ import annotations

import bisect
import math

Pt = tuple[float, float]


def sub(a: Pt, b: Pt) -> Pt:
    return (a[0] - b[0], a[1] - b[1])


def add(a: Pt, b: Pt) -> Pt:
    return (a[0] + b[0], a[1] + b[1])


def mul(a: Pt, k: float) -> Pt:
    return (a[0] * k, a[1] * k)


def norm(a: Pt) -> float:
    return math.hypot(a[0], a[1])


def unit(a: Pt) -> Pt:
    n = norm(a)
    return (a[0] / n, a[1] / n) if n > 1e-9 else (1.0, 0.0)


def left(a: Pt) -> Pt:
    """Перпендикуляр влево (против часовой)."""
    return (-a[1], a[0])


def cross(a: Pt, b: Pt) -> float:
    return a[0] * b[1] - a[1] * b[0]


def angle(a: Pt) -> float:
    return math.atan2(a[1], a[0])


def wrap(a: float) -> float:
    """Угол в (-pi, pi]."""
    while a <= -math.pi:
        a += 2 * math.pi
    while a > math.pi:
        a -= 2 * math.pi
    return a


class Polyline:
    """Ломаная с накопленной длиной: точка и направление по s."""

    __slots__ = ("pts", "cum", "length")

    def __init__(self, pts: list[Pt]):
        clean: list[Pt] = []
        for p in pts:
            p = (float(p[0]), float(p[1]))
            if not clean or norm(sub(p, clean[-1])) > 1e-6:
                clean.append(p)
        if len(clean) < 2:
            raise ValueError("ломаная короче двух точек")
        self.pts = clean
        self.cum = [0.0]
        for a, b in zip(clean, clean[1:]):
            self.cum.append(self.cum[-1] + norm(sub(b, a)))
        self.length = self.cum[-1]

    def _seg(self, s: float) -> int:
        i = bisect.bisect_right(self.cum, s) - 1
        return max(0, min(i, len(self.pts) - 2))

    def at(self, s: float) -> tuple[Pt, Pt]:
        """Точка и единичное направление на расстоянии s от начала."""
        i = self._seg(s)
        a, b = self.pts[i], self.pts[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        t = (s - self.cum[i]) / seg if seg > 0 else 0.0
        d = unit(sub(b, a))
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), d

    def point(self, s: float) -> Pt:
        return self.at(s)[0]

    def dir(self, s: float) -> Pt:
        return self.at(s)[1]

    def slice(self, s0: float, s1: float) -> "Polyline":
        s0 = max(0.0, s0)
        s1 = min(self.length, s1)
        if s1 - s0 < 1e-6:
            raise ValueError("пустой отрезок ломаной")
        pts = [self.point(s0)]
        for p, c in zip(self.pts, self.cum):
            if s0 < c < s1:
                pts.append(p)
        pts.append(self.point(s1))
        return Polyline(pts)

    def reversed(self) -> "Polyline":
        return Polyline(list(reversed(self.pts)))

    def offset(self, d: float) -> "Polyline":
        """Смещение влево на d (вправо при d < 0) со стыками по биссектрисе."""
        pts = self.pts
        out: list[Pt] = []
        for i, p in enumerate(pts):
            if i == 0:
                n = left(unit(sub(pts[1], pts[0])))
                out.append(add(p, mul(n, d)))
            elif i == len(pts) - 1:
                n = left(unit(sub(pts[-1], pts[-2])))
                out.append(add(p, mul(n, d)))
            else:
                n1 = left(unit(sub(p, pts[i - 1])))
                n2 = left(unit(sub(pts[i + 1], p)))
                m = unit(add(n1, n2))
                k = 1.0 / max(0.3, m[0] * n1[0] + m[1] * n1[1])
                out.append(add(p, mul(m, d * k)))
        return Polyline(out)

    def resample(self, step: float) -> "Polyline":
        n = max(1, int(math.ceil(self.length / step)))
        return Polyline([self.point(self.length * i / n) for i in range(n + 1)])

    def project(self, p: Pt) -> tuple[float, float]:
        """Ближайшая точка: (s, расстояние)."""
        best = (0.0, float("inf"))
        for i, (a, b) in enumerate(zip(self.pts, self.pts[1:])):
            ab = sub(b, a)
            l2 = ab[0] ** 2 + ab[1] ** 2
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
            q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
            dist = norm(sub(p, q))
            if dist < best[1]:
                best = (self.cum[i] + t * math.sqrt(l2), dist)
        return best

    def intersections(self, other: "Polyline") -> list[tuple[float, float, Pt]]:
        """Пересечения: (s на себе, s на другой, точка)."""
        res = []
        for i, (a, b) in enumerate(zip(self.pts, self.pts[1:])):
            for j, (c, d) in enumerate(zip(other.pts, other.pts[1:])):
                r = sub(b, a)
                q = sub(d, c)
                den = cross(r, q)
                if abs(den) < 1e-12:
                    continue
                t = cross(sub(c, a), q) / den
                u = cross(sub(c, a), r) / den
                if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                    p = add(a, mul(r, t))
                    res.append((self.cum[i] + t * norm(r), other.cum[j] + u * norm(q), p))
        res.sort()
        merged: list[tuple[float, float, Pt]] = []
        for x in res:
            if not merged or abs(x[0] - merged[-1][0]) > 0.5:
                merged.append(x)
        return merged

    def to_list(self, nd: int = 2) -> list[list[float]]:
        return [[round(p[0], nd), round(p[1], nd)] for p in self.pts]


def bezier(p0: Pt, d0: Pt, p3: Pt, d3: Pt, n: int = 16) -> Polyline:
    """Кубическая кривая из p0 по направлению d0 в p3 с направлением d3."""
    dist = norm(sub(p3, p0))
    turn = abs(wrap(angle(d3) - angle(d0)))
    k = dist * (0.36 if turn > 2.5 else 0.42)
    if turn > 2.5:
        k = max(k, 6.0)
    p1 = add(p0, mul(d0, k))
    p2 = sub(p3, mul(d3, k))
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((
            u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
        ))
    return Polyline(pts)


def quad(p0: Pt, c: Pt, p2: Pt, n: int = 10) -> Polyline:
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p2[1]))
    return Polyline(pts)


def line_meet(p: Pt, d: Pt, q: Pt, e: Pt) -> Pt | None:
    """Пересечение прямых p + t d и q + u e."""
    den = cross(d, e)
    if abs(den) < 1e-9:
        return None
    t = cross(sub(q, p), e) / den
    return add(p, mul(d, t))


def hull(points: list[Pt]) -> list[Pt]:
    """Выпуклая оболочка против часовой стрелки."""
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out: list[Pt] = []
        for p in seq:
            while len(out) >= 2 and cross(sub(out[-1], out[-2]), sub(p, out[-2])) <= 0:
                out.pop()
            out.append(p)
        return out

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]
