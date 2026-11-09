"""SVG building blocks for Plasma/Aurorae frame graphics.

Plasma and Aurorae draw resizable surfaces from "9-slice" frames: nine named
elements (corners, edges, centre) whose bounding boxes define how the frame is
cut up. The renderer is QtSvg, so everything emitted here sticks to a safe
subset: plain paths/rects, gradients and opacity — no filters, clip paths,
masks or CSS — and absolute coordinates only, so each named element's bounding
box is exactly the slice it is meant to be.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

Color = tuple[str, float]  # (#rrggbb, alpha)


def fmt(x: float) -> str:
    """Compact number formatting for SVG attributes."""
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def paint(color: Color, attr: str = "fill") -> str:
    hex_color, alpha = color
    if alpha >= 1:
        return f'{attr}="{hex_color}"'
    return f'{attr}="{hex_color}" {attr}-opacity="{fmt(alpha)}"'


class Xf:
    """Axis-aligned mirror + translate, applied in Python instead of via SVG
    transform attributes so emitted geometry is always in absolute coordinates."""

    def __init__(self, tx: float = 0, ty: float = 0, sx: int = 1, sy: int = 1):
        self.tx, self.ty, self.sx, self.sy = tx, ty, sx, sy

    @property
    def flips(self) -> bool:
        return self.sx * self.sy < 0

    def pt(self, x: float, y: float) -> tuple[float, float]:
        return self.tx + self.sx * x, self.ty + self.sy * y

    def rect(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        ax, ay = self.pt(x, y)
        bx, by = self.pt(x + w, y + h)
        return min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay)


class PathD:
    """Minimal path builder that bakes an Xf into the coordinates."""

    def __init__(self, xf: Xf | None = None):
        self.xf = xf or Xf()
        self.parts: list[str] = []

    def M(self, x: float, y: float) -> "PathD":
        ax, ay = self.xf.pt(x, y)
        self.parts.append(f"M{fmt(ax)},{fmt(ay)}")
        return self

    def L(self, x: float, y: float) -> "PathD":
        ax, ay = self.xf.pt(x, y)
        self.parts.append(f"L{fmt(ax)},{fmt(ay)}")
        return self

    def A(self, r: float, x: float, y: float, sweep: int = 1, large: int = 0) -> "PathD":
        ax, ay = self.xf.pt(x, y)
        if self.xf.flips:
            sweep = 1 - sweep
        self.parts.append(f"A{fmt(r)},{fmt(r)} 0 {large} {sweep} {fmt(ax)},{fmt(ay)}")
        return self

    def Z(self) -> "PathD":
        self.parts.append("Z")
        return self

    def d(self) -> str:
        return " ".join(self.parts)


def rect_el(xf: Xf, x: float, y: float, w: float, h: float, attrs: str) -> str:
    ax, ay, aw, ah = xf.rect(x, y, w, h)
    return f'<rect x="{fmt(ax)}" y="{fmt(ay)}" width="{fmt(aw)}" height="{fmt(ah)}" {attrs}/>'


# A geometrically present but invisible rect: pins a slice's bounding box when
# its visible artwork does not reach all four sides.
PIN = 'fill="#000000" opacity="0.002"'


def stops(color: str, alphas: list[tuple[float, float]]) -> str:
    return "".join(
        f'<stop offset="{fmt(off)}" stop-color="{color}" stop-opacity="{fmt(a)}"/>' for off, a in alphas
    )


def two_stop(c0: Color, c1: Color) -> str:
    return (
        f'<stop offset="0" stop-color="{c0[0]}" stop-opacity="{fmt(c0[1])}"/>'
        f'<stop offset="1" stop-color="{c1[0]}" stop-opacity="{fmt(c1[1])}"/>'
    )


@dataclass
class FrameStyle:
    """Appearance of one 9-slice frame.

    The visible shape is a rectangle inset by `inset` from the slice bounds,
    with corners rounded to radius `r` (or clipped diagonally by `r` when `cut`
    is set), filled with a vertical gradient (fill_top -> fill_bot) and
    outlined by a `bw`-wide line that fades from border_top to border_bot.
    """

    fill_top: Color
    fill_bot: Color
    c: int = 12  # corner slice size == edge slice thickness
    m: int = 32  # size of the stretchable middle
    r: float = 10  # corner radius of the visible shape
    inset: float = 0
    border_top: Color | None = None
    border_bot: Color | None = None
    bw: float = 1
    sheen: Color | None = None  # 1px highlight just inside the top border
    accent: Color | None = None  # ornament arcs hugging each corner
    accent_w: float = 1.5
    # Solid indicator bar along one inner edge: (edge, colour, thickness)
    line: tuple[str, Color, float] | None = None
    square: set = field(default_factory=set)  # corner names drawn without rounding
    cut: bool = False  # clip corners with a 45° line instead of an arc

    @property
    def size(self) -> int:
        return 2 * self.c + self.m


CORNERS = {
    # name: (sx, sy, column, row)
    "topleft": (1, 1, 0, 0),
    "topright": (-1, 1, 2, 0),
    "bottomleft": (1, -1, 0, 2),
    "bottomright": (-1, -1, 2, 2),
}


def _pid(prefix: str, name: str) -> str:
    return f"{prefix}-{name}" if prefix else name


def frame_pieces(prefix: str, ox: float, oy: float, st: FrameStyle, uid: str) -> tuple[list[str], list[str]]:
    """Emit the nine slices of a frame with its top-left at (ox, oy).

    Returns (defs, body). `uid` namespaces gradient ids within the document.
    """
    c, m, r, i, bw = st.c, st.m, st.r, st.inset, st.bw
    if r + i > c:
        raise ValueError(f"frame {prefix!r}: radius {r} + inset {i} exceeds corner slice {c}")
    defs: list[str] = []
    body: list[str] = []
    gid = f"g{uid}"

    # Shared vertical gradients for the middle row (stretched vertically).
    defs.append(
        f'<linearGradient id="{gid}-fill" x1="0" y1="0" x2="0" y2="1">{two_stop(st.fill_top, st.fill_bot)}</linearGradient>'
    )
    if st.border_top and st.border_bot:
        defs.append(
            f'<linearGradient id="{gid}-edge" x1="0" y1="0" x2="0" y2="1">{two_stop(st.border_top, st.border_bot)}</linearGradient>'
        )

    line_edge = st.line[0] if st.line else None

    # ---- corners ----
    for name, (sx, sy, col, row) in CORNERS.items():
        is_top = row == 0
        fill = st.fill_top if is_top else st.fill_bot
        border = st.border_top if is_top else st.border_bot
        x0 = ox + (0 if col == 0 else c + m)
        y0 = oy + (0 if row == 0 else c + m)
        xf = Xf(x0 + (c if sx < 0 else 0), y0 + (c if sy < 0 else 0), sx, sy)
        rr = 0 if name in st.square else r
        parts = []
        if i > 0 or rr > 0:
            parts.append(rect_el(xf, 0, 0, c, c, PIN))
        # A line parallel to a 45° cut, d further in, meets the edges this much later.
        slip = 0.4142
        # fill
        p = PathD(xf).M(i, c).L(i, i + rr)
        if rr > 0:
            p.L(i + rr, i) if st.cut else p.A(rr, i + rr, i)
        p.L(c, i).L(c, c).Z()
        parts.append(f'<path d="{p.d()}" {paint(fill)}/>')
        # border ring
        if border:
            p = PathD(xf).M(i, c).L(i, i + rr)
            if rr > 0:
                p.L(i + rr, i) if st.cut else p.A(rr, i + rr, i)
            p.L(c, i).L(c, i + bw)
            if st.cut and rr > 0:
                p.L(i + rr + slip * bw, i + bw).L(i + bw, i + rr + slip * bw)
            elif rr > bw:
                p.L(i + rr, i + bw).A(rr - bw, i + bw, i + rr, sweep=0)
            else:
                p.L(i + bw, i + bw)
            p.L(i + bw, c).Z()
            parts.append(f'<path d="{p.d()}" {paint(border)}/>')
        # sheen on the straight part of the top edge
        if st.sheen and is_top and c - i - rr > 0:
            parts.append(rect_el(xf, i + max(rr, bw), i + bw, c - i - max(rr, bw), 1, paint(st.sheen)))
        # indicator line segment that falls inside this corner
        if st.line:
            edge, lcolor, lw = st.line
            if edge in ("top", "bottom") and ((edge == "top") == is_top) and c - i - rr > 0:
                parts.append(rect_el(xf, i + rr, i, c - i - rr, lw, paint(lcolor)))
            if edge in ("left", "right") and ((edge == "left") == (col == 0)) and c - i - rr > 0:
                parts.append(rect_el(xf, i, i + rr, lw, c - i - rr, paint(lcolor)))
        # ornament arc with fading tails
        if st.accent and rr > 0:
            aw = st.accent_w
            ext = c - i - rr
            if st.cut:
                p = PathD(xf).M(i, i + rr).L(i + rr, i).L(i + rr + slip * aw, i + aw).L(i + aw, i + rr + slip * aw).Z()
            else:
                p = (
                    PathD(xf)
                    .M(i, i + rr)
                    .A(rr, i + rr, i)
                    .L(i + rr, i + aw)
                    .A(rr - aw, i + aw, i + rr, sweep=0)
                    .Z()
                )
            parts.append(f'<path d="{p.d()}" {paint(st.accent)}/>')
            if ext > 0:
                hx0, hy0 = xf.pt(i + rr, 0)
                hx1, hy1 = xf.pt(i + rr + ext, 0)
                vx0, vy0 = xf.pt(0, i + rr)
                vx1, vy1 = xf.pt(0, i + rr + ext)
                fade = stops(st.accent[0], [(0, st.accent[1]), (1, 0)])
                defs.append(
                    f'<linearGradient id="{gid}-{name}-h" gradientUnits="userSpaceOnUse" x1="{fmt(hx0)}" y1="{fmt(hy0)}" x2="{fmt(hx1)}" y2="{fmt(hy1)}">{fade}</linearGradient>'
                )
                defs.append(
                    f'<linearGradient id="{gid}-{name}-v" gradientUnits="userSpaceOnUse" x1="{fmt(vx0)}" y1="{fmt(vy0)}" x2="{fmt(vx1)}" y2="{fmt(vy1)}">{fade}</linearGradient>'
                )
                parts.append(rect_el(xf, i + rr, i, ext, aw, f'fill="url(#{gid}-{name}-h)"'))
                parts.append(rect_el(xf, i, i + rr, aw, ext, f'fill="url(#{gid}-{name}-v)"'))
        body.append(f'<g id="{_pid(prefix, name)}">{"".join(parts)}</g>')

    # ---- horizontal edges ----
    for name, row in (("top", 0), ("bottom", 2)):
        is_top = row == 0
        fill = st.fill_top if is_top else st.fill_bot
        border = st.border_top if is_top else st.border_bot
        xf = Xf(ox + c, oy + (0 if is_top else 2 * c + m), 1, 1 if is_top else -1)
        parts = []
        if i > 0:
            parts.append(rect_el(xf, 0, 0, m, c, PIN))
        parts.append(rect_el(xf, 0, i, m, c - i, paint(fill)))
        if border:
            parts.append(rect_el(xf, 0, i, m, bw, paint(border)))
        if st.sheen and is_top:
            parts.append(rect_el(xf, 0, i + bw, m, 1, paint(st.sheen)))
        if line_edge == name:
            parts.append(rect_el(xf, 0, i, m, st.line[2], paint(st.line[1])))
        body.append(f'<g id="{_pid(prefix, name)}">{"".join(parts)}</g>')

    # ---- vertical edges ----
    for name, col in (("left", 0), ("right", 2)):
        is_left = col == 0
        xf = Xf(ox + (0 if is_left else 2 * c + m), oy + c, 1 if is_left else -1, 1)
        parts = []
        if i > 0:
            parts.append(rect_el(xf, 0, 0, c, m, PIN))
        parts.append(rect_el(xf, i, 0, c - i, m, f'fill="url(#{gid}-fill)"'))
        if st.border_top and st.border_bot:
            parts.append(rect_el(xf, i, 0, bw, m, f'fill="url(#{gid}-edge)"'))
        if line_edge == name:
            parts.append(rect_el(xf, i, 0, st.line[2], m, paint(st.line[1])))
        body.append(f'<g id="{_pid(prefix, name)}">{"".join(parts)}</g>')

    # ---- centre ----
    xf = Xf(ox + c, oy + c)
    body.append(
        f'<g id="{_pid(prefix, "center")}">{rect_el(xf, 0, 0, m, m, f"""fill="url(#{gid}-fill)" """)}</g>'
    )
    return defs, body


# Falloff of shadow opacity with distance from the frame edge (u = 0 at the
# edge, 1 at the shadow's outer limit); roughly a gaussian tail.
_FALLOFF = [(0.0, 1.0), (0.12, 0.72), (0.28, 0.44), (0.48, 0.2), (0.72, 0.06), (1.0, 0.0)]


def shadow_pieces(
    prefix: str, ox: float, oy: float, spread: int, r: int, color: str, alpha: float, uid: str, m: int = 32
) -> tuple[list[str], list[str], int]:
    """Emit the eight shadow slices (+ invisible centre) around a frame of radius r.

    Each slice extends `r` px underneath the frame so the shadow follows the
    rounded corner; that hidden part is left transparent because the frame
    itself may be translucent. Returns (defs, body, slice_size).
    """
    s = spread
    k = s + r  # slice thickness
    gid = f"s{uid}"
    defs: list[str] = []
    body: list[str] = []

    # Linear: offset 0 = outer limit, 1 = frame edge.
    lin = [(1 - u, alpha * a) for u, a in reversed(_FALLOFF)]
    # Radial: centre = corner arc centre; frame edge sits at r/k of the radius.
    t0 = r / k
    rad = [(0, 0.0), (max(t0 - 0.0001, 0), 0.0)] + [(t0 + (1 - t0) * u, alpha * a) for u, a in _FALLOFF]

    for name, (sx, sy, col, row) in CORNERS.items():
        x0 = ox + (0 if col == 0 else k + m)
        y0 = oy + (0 if row == 0 else k + m)
        xf = Xf(x0 + (k if sx < 0 else 0), y0 + (k if sy < 0 else 0), sx, sy)
        cx, cy = xf.pt(k, k)
        defs.append(
            f'<radialGradient id="{gid}-{name}" gradientUnits="userSpaceOnUse" cx="{fmt(cx)}" cy="{fmt(cy)}" fx="{fmt(cx)}" fy="{fmt(cy)}" r="{fmt(k)}">{stops(color, rad)}</radialGradient>'
        )
        body.append(
            f'<g id="{_pid(prefix, name)}">{rect_el(xf, 0, 0, k, k, f"""fill="url(#{gid}-{name})" """)}</g>'
        )

    for name, row in (("top", 0), ("bottom", 2)):
        is_top = row == 0
        xf = Xf(ox + k, oy + (0 if is_top else 2 * k + m), 1, 1 if is_top else -1)
        _, gy0 = xf.pt(0, 0)
        _, gy1 = xf.pt(0, s)
        defs.append(
            f'<linearGradient id="{gid}-{name}" gradientUnits="userSpaceOnUse" x1="0" y1="{fmt(gy0)}" x2="0" y2="{fmt(gy1)}">{stops(color, lin)}</linearGradient>'
        )
        body.append(
            f'<g id="{_pid(prefix, name)}">{rect_el(xf, 0, s, m, r, PIN)}{rect_el(xf, 0, 0, m, s, f"""fill="url(#{gid}-{name})" """)}</g>'
        )

    for name, col in (("left", 0), ("right", 2)):
        is_left = col == 0
        xf = Xf(ox + (0 if is_left else 2 * k + m), oy + k, 1 if is_left else -1, 1)
        gx0, _ = xf.pt(0, 0)
        gx1, _ = xf.pt(s, 0)
        defs.append(
            f'<linearGradient id="{gid}-{name}" gradientUnits="userSpaceOnUse" x1="{fmt(gx0)}" y1="0" x2="{fmt(gx1)}" y2="0">{stops(color, lin)}</linearGradient>'
        )
        body.append(
            f'<g id="{_pid(prefix, name)}">{rect_el(xf, s, 0, r, m, PIN)}{rect_el(xf, 0, 0, s, m, f"""fill="url(#{gid}-{name})" """)}</g>'
        )

    xf = Xf(ox + k, oy + k)
    body.append(f'<g id="{_pid(prefix, "center")}">{rect_el(xf, 0, 0, m, m, PIN)}</g>')
    return defs, body, k


def margin_hints(prefix: str, ox: float, oy: float, top: float, bottom: float, left: float, right: float) -> list[str]:
    """Hint rects whose thickness tells Plasma the content margins of a frame."""
    p = f"{prefix}-" if prefix else ""
    h = 'fill="#ff00ff" opacity="0.002"'
    return [
        f'<rect id="{p}hint-top-margin" x="{fmt(ox)}" y="{fmt(oy)}" width="4" height="{fmt(top)}" {h}/>',
        f'<rect id="{p}hint-bottom-margin" x="{fmt(ox + 6)}" y="{fmt(oy)}" width="4" height="{fmt(bottom)}" {h}/>',
        f'<rect id="{p}hint-left-margin" x="{fmt(ox + 12)}" y="{fmt(oy + 40)}" width="{fmt(left)}" height="4" {h}/>',
        f'<rect id="{p}hint-right-margin" x="{fmt(ox + 12)}" y="{fmt(oy + 46)}" width="{fmt(right)}" height="4" {h}/>',
    ]


def document(width: float, height: float, defs: list[str], body: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{fmt(width)}" height="{fmt(height)}" viewBox="0 0 {fmt(width)} {fmt(height)}">\n'
        f'<defs>{"".join(defs)}</defs>\n' + "\n".join(body) + "\n</svg>\n"
    )


def write_svgz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps rebuilds byte-identical.
    with open(path, "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
            gz.write(text.encode("utf-8"))


def fill_template(template: str, values: dict[str, object]) -> str:
    """Replace @@NAME@@ placeholders; QML and shell text are full of braces and
    percent signs, so neither str.format nor % formatting is safe for them."""
    out = template
    for key, value in values.items():
        out = out.replace(f"@@{key}@@", str(value))
    if "@@" in out:
        start = out.index("@@")
        raise ValueError(f"unfilled placeholder near: {out[start:start + 40]!r}")
    return out


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
