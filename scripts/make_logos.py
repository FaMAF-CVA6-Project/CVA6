#!/usr/bin/env python3
"""Draw this project's mark and the viewers', and put them in the pages.

Every mark is an instruction row that starts as raw input, trace text on the
gem5 side and a waveform on the CVA6 side, and turns into stage cells. The
viewers staircase their rows one cycle later down the tile, MinorFlow with the
four MinorCPU stages and the amber forwarding arrow and CVA6Flow with the six
stages it draws and its violet one. The project's own mark aligns a trace row
and a waveform row cell for cell instead, since the alignment is what this
repository is for, and the accent bar is the calibration that ties them.

Writes assets/FaMAF_CVA6_header.svg, assets/FaMAF_CVA6_logo.svg and
assets/FaMAF_CVA6_favicon.svg, and docs/<Viewer>_logo.svg,
docs/<Viewer>_favicon.svg and docs/<Viewer>_header.svg in each viewer. With
--patch it also puts the marks into the pages: the favicon, the top bar
heading and the drop zone of each viewer, the favicon of each viewer's
index.html, and the favicon, heading and empty state of FlowCompare, whose
mark pairs the two viewers' rows, and the favicon of the repository's own
index.html, which leads to FlowCompare. A second run replaces what the first
put there. The brand CSS is the shared css-brand block, kept by hand.

    python3 scripts/make_logos.py
    python3 scripts/make_logos.py --patch

Needs fontTools, for the wordmark outlines in the headers, and the IBM Plex
Mono files in assets/fonts/ (OFL, see assets/fonts/OFL.txt).
"""
import argparse
import math
import os
import re
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
VIEWERS = os.path.join(REPO, "viewers")
ASSETS = os.path.join(REPO, "assets")
FONTS = os.path.join(ASSETS, "fonts")

# The viewers' css-tokens.
BG = "#18181a"
TEXT = "#e4e2dc"
TEXT2 = "#a0a09a"
ACCENT = "#3ecf9a"
HAIR = "rgba(255,255,255,0.12)"

# Stage fills, the viewers' COL colours lifted to hold up at icon size.
FE1 = "#6cbbe4"
FE2 = "#2f7fb5"
FE_OUT = "#23828f"
DEC = "#7b4fc4"
EX = "#2a9a66"

IN_HEAD = "#7a8aa6"  # the tick that starts a trace line
IN_TEXT = "#62625d"  # the rest of the line
WAVE = "#7a8aa6"

VIEWER = {
    "MinorFlow": {
        "prefix": "Minor",
        "stages": [FE1, FE2, DEC, ACCENT],
        "tags": ["fe1", "fe2", "dec", "ex"],
        "arrow": "#ffc864",  # COL.fwd
        "arrow_kind": "diagonal",
        "input": "text",
        "tagline": "gem5 RISC-V pipeline viewer",
    },
    "CVA6Flow": {
        "prefix": "CVA6",
        "stages": [FE1, FE2, FE_OUT, DEC, EX, ACCENT],
        "tags": ["fe1", "fe2", "fe out", "dec/is", "ex", "co"],
        "arrow": "#cc72dc",  # COL.fwdSb, lifted
        "arrow_kind": "vertical",
        "input": "wave",
        "tagline": "Verilator RISC-V pipeline viewer",
    },
}


def num(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def luminance(colour):
    rgb = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
           for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def tag_ink(fill):
    """Near-black or white, whichever reads better on the cell."""
    lum = luminance(fill)
    dark = (lum + 0.05) / (luminance("#0f0f10") + 0.05)
    light = 1.05 / (lum + 0.05)
    return "#0f0f10" if dark >= light else "#ffffff"


# ------------------------------------------------------------------ drawing

def arrow(x1, y1, x2, y2, colour, width, head, halo):
    """A forwarding arrow with a halo in the ground colour, so it reads over
    any cell."""
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    bx, by = x2 - ux * head, y2 - uy * head
    px, py = -uy * head * 0.55, ux * head * 0.55
    points = (f"{num(x2)},{num(y2)} {num(bx + px)},{num(by + py)} "
              f"{num(bx - px)},{num(by - py)}")
    shaft = f'x1="{num(x1)}" y1="{num(y1)}" x2="{num(bx)}" y2="{num(by)}"'
    return [
        f'<line {shaft} stroke="{BG}" stroke-width="{num(width + halo)}" '
        f'stroke-linecap="round"/>',
        f'<polygon points="{points}" fill="{BG}" stroke="{BG}" '
        f'stroke-width="{num(halo)}" stroke-linejoin="round"/>',
        f'<line {shaft} stroke="{colour}" stroke-width="{num(width)}" '
        f'stroke-linecap="round"/>',
        f'<polygon points="{points}" fill="{colour}"/>',
    ]


def square_wave(edges, x0, end, cy, a):
    d, high = [f"M{num(x0)} {num(cy + a)}"], False
    for e in edges:
        if e >= end:
            break
        d.append(f"L{num(e)} {num(cy - a if high else cy + a)}")
        high = not high
        d.append(f"L{num(e)} {num(cy - a if high else cy + a)}")
    d.append(f"L{num(end)} {num(cy - a if high else cy + a)}")
    return " ".join(d)


def bus(bounds, cy, a, slope, width, colour=WAVE):
    out = []
    for xa, xb in zip(bounds, bounds[1:]):
        points = (f"{num(xa)},{num(cy)} {num(xa + slope)},{num(cy - a)} "
                  f"{num(xb - slope)},{num(cy - a)} {num(xb)},{num(cy)} "
                  f"{num(xb - slope)},{num(cy + a)} {num(xa + slope)},{num(cy + a)}")
        out.append(f'<polygon points="{points}" fill="none" stroke="{colour}" '
                   f'stroke-width="{num(width)}" stroke-linejoin="round"/>')
    return out


def wave(d, width, colour=WAVE):
    return (f'<path d="{d}" fill="none" stroke="{colour}" '
            f'stroke-width="{num(width)}" stroke-linejoin="round"/>')


TEXT_SEGMENTS = [[5, 7, 4, 9], [5, 8, 3, 6, 7], [5, 6, 9, 4, 5],
                 [5, 9, 4, 7, 3, 6]]


def mark(v, lod):
    """The mark's elements. lod "L" draws it on a 64 grid for 48 px and up,
    "S" on a 16 grid for 16 px, with three rows and the input as one line."""
    stages = v["stages"]
    count = len(stages)
    if lod == "S":
        x0, rows, h, ys = 1.5, 3, 2.0, (4.0, 7.0, 10.0)
        c = 1.5 if count == 4 else 1.25
        lead = 13.0 - (rows - 1 + count) * c
        out = [tile("S")]
        for i in range(rows):
            xs = x0 + lead + i * c
            end = xs - 0.5
            if v["input"] == "text":
                out.append(f'<rect x="{num(x0)}" y="{num(ys[i] + 0.5)}" '
                           f'width="{num(end - x0)}" height="1" fill="#6a6a66"/>')
            else:
                mid = x0 + (end - x0) / 2
                out.append(f'<path d="M{num(x0)} {num(ys[i] + 1.6)} H{num(mid)} '
                           f'V{num(ys[i] + 0.4)} H{num(end)}" fill="none" '
                           f'stroke="{WAVE}" stroke-width="0.7"/>')
            for j in range(count):
                out.append(f'<rect x="{num(xs + j * c)}" y="{num(ys[i])}" '
                           f'width="{num(c)}" height="{num(h)}" fill="{stages[j]}"/>')
        return out

    rows, h, g, y0, x0 = 4, 7.0, 3.0, 13.5, 8.0
    c = 5.0 if count == 4 else 4.0
    lead = 48.0 - (rows - 1 + count) * c

    def cell_x(i, j):
        return x0 + lead + (i + j) * c

    out = [tile("L")]
    for i in range(rows):
        y = y0 + i * (h + g)
        cy = y + h / 2
        end = cell_x(i, 0) - 1.6
        if v["input"] == "text":
            x = x0
            for k, length in enumerate(TEXT_SEGMENTS[i]):
                length = min(length, end - x)
                if length < 1.5:
                    break
                out.append(f'<rect x="{num(x)}" y="{num(cy - 1.2)}" '
                           f'width="{num(length)}" height="2.4" rx="1.2" '
                           f'fill="{IN_HEAD if k == 0 else IN_TEXT}"/>')
                x += length + 1.5
                if x >= end:
                    break
        elif i == 0:
            edges = [x0 + 2.6 * k for k in range(1, 20)]
            out.append(wave(square_wave(edges, x0, end, cy, 2.4), 1.1))
        elif i == 2:
            out.append(
                wave(square_wave([12.5, 19, 23.5], x0, end, cy, 2.4), 1.1))
        else:
            inner = [14] if i == 1 else [13, 21.5]
            out += bus([x0] + [b for b in inner if b < end - 3] + [end],
                       cy, 2.4, 1.2, 1.1)
        for j in range(count):
            out.append(f'<rect x="{num(cell_x(i, j) + 0.4)}" y="{num(y)}" '
                       f'width="{num(c - 0.8)}" height="{num(h)}" rx="1" '
                       f'fill="{stages[j]}"/>')
    if v["arrow_kind"] == "diagonal":
        xa, ya = cell_x(1, count - 1) + 0.3 * c, y0 + (h + g) + 1.5
        xb, yb = cell_x(2, count - 1) + 0.45 * c, y0 + 2 * (h + g) + 1.6
    else:
        xa = xb = cell_x(1, count - 2) + c / 2
        ya, yb = y0 + (h + g) + 1.3, y0 + 2 * (h + g) + 1.7
    return out + arrow(xa, ya, xb, yb, v["arrow"], 1.7, 4.2, 2.0)


# FlowCompare's own colours, one per JSON and one for the drift.
COMPARE_MINOR = "#8f7fd8"
COMPARE_MINOR_DIM = "#595182"
COMPARE_CVA6 = "#3ec0b0"
COMPARE_DRIFT = "#ebb450"


def tile(lod):
    if lod == "S":
        return (f'<rect x="0.25" y="0.25" width="15.5" height="15.5" rx="3.6" '
                f'fill="{BG}" stroke="{HAIR}" stroke-width="0.5"/>')
    return (f'<rect x="0.5" y="0.5" width="63" height="63" rx="14" '
            f'fill="{BG}" stroke="{HAIR}" stroke-width="0.75"/>')


def compare_mark(lod):
    """FlowCompare's mark: two instructions, each on both pipelines, the
    MinorFlow row over the CVA6Flow row. The input takes FlowCompare's colour
    for each JSON, and the amber arrow spans the drift between the commits."""
    minor = VIEWER["MinorFlow"]["stages"]
    cva6 = VIEWER["CVA6Flow"]["stages"]
    if lod == "S":
        # Each pair sits closer together than the two pairs do.
        x0, h, c, ys = 1.5, 2.0, 1.25, (2.0, 5.0, 9.0, 12.0)
        lead = 13.0 - 7 * c
        out = [tile("S")]
        for i in range(4):
            pair, on_cva6 = divmod(i, 2)
            xs = x0 + lead + pair * c
            end = xs - 0.5
            if on_cva6:
                mid = x0 + (end - x0) / 2
                out.append(f'<path d="M{num(x0)} {num(ys[i] + 1.6)} H{num(mid)} '
                           f'V{num(ys[i] + 0.4)} H{num(end)}" fill="none" '
                           f'stroke="{COMPARE_CVA6}" stroke-width="0.7"/>')
            else:
                out.append(f'<rect x="{num(x0)}" y="{num(ys[i] + 0.5)}" '
                           f'width="{num(end - x0)}" height="1" fill="{COMPARE_MINOR}"/>')
            for j, fill in enumerate(cva6 if on_cva6 else minor):
                out.append(f'<rect x="{num(xs + j * c)}" y="{num(ys[i])}" '
                           f'width="{num(c)}" height="{num(h)}" fill="{fill}"/>')
        start = x0 + lead + c
        out.append(f'<rect x="{num(start + 4 * c + 0.5)}" y="{num(ys[2] + 0.5)}" '
                   f'width="{num(2 * c - 0.5)}" height="1" fill="{COMPARE_DRIFT}"/>')
        return out

    h, x0, c, ys = 7.0, 8.0, 4.5, (13.5, 22.5, 34.5, 43.5)
    lead = 48.0 - 7 * c
    out = [tile("L")]
    for i in range(4):
        pair, on_cva6 = divmod(i, 2)
        y = ys[i]
        cy = y + h / 2
        xs = x0 + lead + pair * c
        end = xs - 1.6
        if on_cva6 and pair == 0:
            edges = [x0 + 2.6 * k for k in range(1, 20)]
            out.append(
                wave(square_wave(edges, x0, end, cy, 2.4), 1.1, COMPARE_CVA6))
        elif on_cva6:
            out += bus([x0, 14, 21, end], cy, 2.4, 1.2, 1.1, COMPARE_CVA6)
        else:
            x = x0
            for k, length in enumerate(TEXT_SEGMENTS[i]):
                length = min(length, end - x)
                if length < 1.5:
                    break
                out.append(f'<rect x="{num(x)}" y="{num(cy - 1.2)}" '
                           f'width="{num(length)}" height="2.4" rx="1.2" '
                           f'fill="{COMPARE_MINOR if k == 0 else COMPARE_MINOR_DIM}"/>')
                x += length + 1.5
                if x >= end:
                    break
        for j, fill in enumerate(cva6 if on_cva6 else minor):
            out.append(f'<rect x="{num(xs + j * c + 0.4)}" y="{num(y)}" '
                       f'width="{num(c - 0.8)}" height="{num(h)}" rx="1" fill="{fill}"/>')
    start = x0 + lead + c
    cy = ys[2] + h / 2
    return out + arrow(start + 4 * c + 1.2, cy, start + 6 * c - 0.6, cy,
                       COMPARE_DRIFT, 1.7, 4.2, 2.0)


# --------------------------------------------------------------- the fork

# The fork's mark: the accent spine is the calibration that ties the two
# sides, and both rows carry the same four stage cells at the same cycles,
# the trace above and the waveform below.
PROJECT_NAME = "FaMAF CVA6"
PROJECT_TAG = "a gem5 MinorCPU calibrated to the CVA6 RTL"
PROJECT_STAGES = (FE1, FE2, DEC, EX)


def project_mark(lod):
    """The mark's elements, on the 16 grid for "S" and the 64 grid for "L"."""
    if lod == "S":
        out = [tile("S")]
        spine, feed, x0, c, h = 1.5, 3.1, 8.0, 1.5, 2.6
        out.append(f'<rect x="{num(spine)}" y="4.4" width="0.8" height="7.2" '
                   f'rx="0.4" fill="{ACCENT}"/>')
        for i, y in enumerate((4.4, 9.0)):
            cy = y + h / 2
            end = x0 - 0.5
            if i == 0:
                out.append(f'<rect x="{num(feed)}" y="{num(cy - 0.5)}" '
                           f'width="{num(end - feed)}" height="1" '
                           f'fill="{IN_TEXT}"/>')
            else:
                mid = feed + (end - feed) / 2
                out.append(f'<path d="M{num(feed)} {num(cy + 0.6)} '
                           f'H{num(mid)} V{num(cy - 0.6)} H{num(end)}" '
                           f'fill="none" stroke="{WAVE}" '
                           f'stroke-width="0.7"/>')
            for j, fill in enumerate(PROJECT_STAGES):
                out.append(f'<rect x="{num(x0 + j * c)}" y="{num(y)}" '
                           f'width="{num(c)}" height="{num(h)}" '
                           f'fill="{fill}"/>')
        return out

    out = [tile("L")]
    spine, feed, x0, c, h = 6.0, 10.5, 25.0, 8.0, 11.0
    out.append(f'<rect x="{num(spine)}" y="18" width="2.6" height="28" '
               f'rx="1.3" fill="{ACCENT}"/>')
    for i, y in enumerate((18.0, 35.0)):
        cy = y + h / 2
        end = x0 - 2.0
        if i == 0:
            x = feed
            for k, length in enumerate((4.0, 6.5, 3.5)):
                length = min(length, end - x)
                if length < 1.5:
                    break
                out.append(f'<rect x="{num(x)}" y="{num(cy - 1.4)}" '
                           f'width="{num(length)}" height="2.8" rx="1.4" '
                           f'fill="{IN_HEAD if k == 0 else IN_TEXT}"/>')
                x += length + 1.6
        else:
            out.append(wave(square_wave([15.5, 19.5], feed, end, cy, 2.6),
                            1.1))
        for j, fill in enumerate(PROJECT_STAGES):
            out.append(f'<rect x="{num(x0 + j * c + 0.5)}" y="{num(y)}" '
                       f'width="{num(c - 1.0)}" height="{num(h)}" rx="1.5" '
                       f'fill="{fill}"/>')
    return out


def project_standalone(lod, px):
    grid = 64 if lod == "L" else 16
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" '
        f'height="{px}" viewBox="0 0 {grid} {grid}" role="img" '
        f'aria-label="{PROJECT_NAME} Project">',
        f"<title>{PROJECT_NAME} Project</title>",
        *(f"  {el}" for el in project_mark(lod)),
        "</svg>",
    ]) + "\n"


def project_header(faces):
    """The README lockup: the mark, the wordmark and the line under it."""
    width, height, pad = 1280, 260, 64
    side = height - 2 * pad
    scale = side / 64
    name, _ = faces["SemiBold"].path(PROJECT_NAME, 0, 0, 62, 0.02)
    tag, _ = faces["Regular"].path(PROJECT_TAG, 0, 0, 24, 0.01)
    text_x = pad + side + 44
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{PROJECT_NAME} Project">',
           f"<title>{PROJECT_NAME} Project</title>",
           f'  <rect width="{width}" height="{height}" rx="20" '
           f'fill="{BG}"/>',
           f'  <g transform="translate({pad} {pad}) scale({num(scale)})">']
    out += [f"    {el}" for el in project_mark("L")]
    out += ["  </g>",
            f'  <g transform="translate({text_x} 126)">',
            f'    <path d="{name}" fill="{TEXT}"/>',
            "  </g>",
            f'  <g transform="translate({text_x} 168)">',
            f'    <path d="{tag}" fill="{TEXT2}"/>',
            "  </g>",
            f'  <rect x="{text_x}" y="186" width="120" height="3" rx="1.5" '
            f'fill="{ACCENT}"/>',
            "</svg>"]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ type

class Face:
    """One IBM Plex Mono weight, drawn as outlines."""

    def __init__(self, weight):
        font = TTFont(os.path.join(FONTS, f"IBMPlexMono-{weight}.ttf"))
        self.glyphs = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm
        self.ascent = font["hhea"].ascent
        self.descent = -font["hhea"].descent

    def baseline(self, top, size, line_height):
        """Where CSS puts the baseline of a line box starting at top."""
        content = (self.ascent + self.descent) / self.upm
        lead = (line_height - content) / 2
        return top + (lead + self.ascent / self.upm) * size

    def path(self, text, x, baseline, size, tracking=0.0):
        """The outline of text as path data, and the pen's x after it."""
        pen = SVGPathPen(self.glyphs, ntos=num)
        scale = size / self.upm
        for ch in text:
            glyph = self.glyphs[self.cmap[ord(ch)]]
            glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
            x += glyph.width * scale + tracking * size
        return pen.getCommands(), x


# ------------------------------------------------------------------ files

WORDS = [22, 40, 16, 52, 28, 36, 18, 44, 24, 60, 20, 34, 30, 14, 48, 26]
TRACE_PATHS = [78, 78, 72, 80]
BUS_RUNS = [2, 1, 3, 2, 1, 1, 3, 2]
BIT_RUNS = [3, 1, 2, 4, 1, 2, 2, 3]


def header(name, v, faces):
    """The README header: the lockup where the viewer's label column is, and
    a schematic of the timeline beside it."""
    width, height, left = 1280, 320, 560
    pane = width - left - 1
    cw, ruler, pitch, ch, k0, rows = 40, 18, 36, 24, 3, 9
    stages, tags, count = v["stages"], v["tags"], len(v["stages"])
    ident = name.lower()

    def cell_x(i, j):
        return (k0 + i + j) * cw

    def cell_y(i):
        return ruler + i * pitch + (pitch - ch) / 2

    body = [f'<rect width="{pane}" height="{height}" fill="{BG}"/>']
    for i in range(rows):
        body.append(f'<rect y="{ruler + i * pitch}" width="{pane}" height="{pitch}" '
                    f'fill="{"#1c1c1e" if i % 2 == 0 else "#1a1a1c"}"/>')
    columns = pane // cw + 1
    for k in range(columns + 1):
        body.append(f'<line x1="{k * cw}" y1="{ruler}" x2="{k * cw}" y2="{height}" '
                    f'stroke="rgba(255,255,255,{0.07 if k % 5 == 0 else 0.03})"/>')
    body.append(f'<rect width="{pane}" height="{ruler}" fill="#1c1c1e"/>')
    for k in range(columns + 1):
        body.append(f'<line x1="{k * cw}" y1="0" x2="{k * cw}" y2="{ruler}" '
                    f'stroke="{"#383838" if k % 5 == 0 else "#252525"}"/>')
        d, _ = faces["Regular"].path(str(k + 1), k * cw + 4, 12.5, 9)
        body.append(f'<path d="{d}" fill="#909090"/>')
    body.append(f'<line y1="{ruler - 0.5}" x2="{pane}" y2="{ruler - 0.5}" '
                f'stroke="rgba(255,255,255,0.07)"/>')

    for i in range(rows):
        cy = cell_y(i) + ch / 2
        end = cell_x(i, 0) - 8
        if v["input"] == "text":
            lengths = ([30, TRACE_PATHS[i % 4]]
                       + [WORDS[(i * 3 + m) % len(WORDS)]
                          for m in range(len(WORDS))])
            x = 8
            for k, length in enumerate(lengths):
                length = min(length, end - x)
                if length < 12:
                    break
                body.append(f'<rect x="{num(x)}" y="{num(cy - 2.5)}" '
                            f'width="{num(length)}" height="5" rx="2.5" '
                            f'fill="{IN_HEAD if k == 0 else IN_TEXT}"/>')
                x += length + 7
        elif i % 4 == 0:
            edges = [m * cw / 2 for m in range(1, 2 * (k0 + i) + 1)]
            body.append(wave(square_wave(edges, 8, end, cy, 7), 1.4))
        elif i % 4 == 2:
            edges, x, m = [], 0, i
            while True:
                x += BIT_RUNS[m % len(BIT_RUNS)] * cw
                m += 1
                if x >= end:
                    break
                edges.append(x)
            body.append(wave(square_wave(edges, 8, end, cy, 7), 1.4))
        else:
            bounds, x, m = [8], 0, i
            while True:
                x += BUS_RUNS[m % len(BUS_RUNS)] * cw
                m += 1
                if x >= end - 12:
                    break
                bounds.append(x)
            body += bus(bounds + [end], cy, 7, 4, 1.4)
        for j in range(count):
            x, y = cell_x(i, j), cell_y(i)
            body.append(f'<rect x="{x + 1}" y="{num(y)}" width="{cw - 2}" '
                        f'height="{ch}" rx="2" fill="{stages[j]}"/>')
            body.append(f'<use href="#{ident}-tag-{j}" x="{x + 5}" '
                        f'y="{num(y + 15.5)}" fill="{tag_ink(stages[j])}"/>')
    for r in (2, 5):
        if v["arrow_kind"] == "diagonal":
            xa, ya = cell_x(r, count - 1) + 0.35 * cw, cell_y(r) + 7
            xb, yb = cell_x(r + 1, count - 1) + 0.5 * cw, cell_y(r + 1) + 5
        else:
            xa = xb = cell_x(r, count - 2) + cw / 2
            ya, yb = cell_y(r) + 6, cell_y(r + 1) + 6
        body += arrow(xa, ya, xb, yb, v["arrow"], 2.2, 8, 3)

    defs = [
        f'<clipPath id="{ident}-card"><rect width="{width}" height="{height}" rx="12"/></clipPath>']
    for j, tag in enumerate(tags):
        d, _ = faces["Medium"].path(tag, 0, 0, 9)
        defs.append(f'<path id="{ident}-tag-{j}" d="{d}"/>')

    # The lockup, laid out as the canvas does it in CSS.
    mark_px, text_x = 104, 64 + 104 + 26
    word, tag_size, between = 52, 16, 14
    column = word + between + tag_size * 1.3
    top = height / 2 - column / 2
    semi, medium = faces["SemiBold"], faces["Medium"]
    regular = faces["Regular"]
    base = semi.baseline(top, word, 1.0)
    prefix, x = semi.path(v["prefix"], text_x, base, word, -0.02)
    flow, _ = medium.path("Flow", x, base, word, -0.02)
    line, _ = regular.path(v["tagline"], text_x,
                           regular.baseline(
                               top + word + between, tag_size, 1.3),
                           tag_size)
    scale = mark_px / 64
    lockup = [f'<rect width="{left}" height="{height}" fill="{BG}"/>',
              f'<g transform="translate(64 {num(height / 2 - mark_px / 2)}) scale({num(scale)})">',
              *(f"  {el}" for el in mark(v, "L")),
              "</g>",
              f'<path d="{prefix}" fill="{TEXT}"/>',
              f'<path d="{flow}" fill="{ACCENT}"/>',
              f'<path d="{line}" fill="{TEXT2}"/>',
              f'<line x1="{left + 0.5}" x2="{left + 0.5}" y2="{height}" '
              f'stroke="rgba(255,255,255,0.07)"/>']

    title = f'{name}, a {v["tagline"]}'
    rows_out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="{ident}-title">',
        f'<title id="{ident}-title">{title}</title>',
        "<defs>", *(f"  {d}" for d in defs), "</defs>",
        f'<g clip-path="url(#{ident}-card)">',
        *(f"  {el}" for el in lockup),
        f'  <g transform="translate({left + 1} 0)">',
        *(f"    {el}" for el in body),
        "  </g>",
        "</g>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="11.5" '
        f'fill="none" stroke="rgba(255,255,255,0.08)"/>',
        "</svg>",
    ]
    return "\n".join(rows_out) + "\n"


def standalone(name, lod, px):
    grid = 64 if lod == "L" else 16
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" '
        f'viewBox="0 0 {grid} {grid}" role="img" aria-label="{name}">',
        f"<title>{name}</title>",
        *(f"  {el}" for el in mark(VIEWER[name], lod)),
        "</svg>",
    ]) + "\n"


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(os.path.relpath(path, REPO))


def write_files(faces):
    os.makedirs(ASSETS, exist_ok=True)
    write(os.path.join(ASSETS, "FaMAF_CVA6_logo.svg"),
          project_standalone("L", 128))
    write(os.path.join(ASSETS, "FaMAF_CVA6_favicon.svg"),
          project_standalone("S", 16))
    write(os.path.join(ASSETS, "FaMAF_CVA6_header.svg"),
          project_header(faces))
    for name, v in VIEWER.items():
        docs = os.path.join(VIEWERS, name, "docs")
        write(os.path.join(docs, f"{name}_logo.svg"),
              standalone(name, "L", 128))
        write(os.path.join(docs, f"{name}_favicon.svg"),
              standalone(name, "S", 16))
        write(os.path.join(docs, f"{name}_header.svg"), header(name, v, faces))


# ------------------------------------------------------------------ pages

def inline(elements, grid, px, indent):
    return "\n".join(
        [f'{indent}<svg class="brand-mark" width="{px}" height="{px}" '
         f'viewBox="0 0 {grid} {grid}" aria-hidden="true">']
        + [f"{indent}  {el}" for el in elements]
        + [f"{indent}</svg>"])


def data_uri(elements):
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'>"
           + "".join(elements) + "</svg>").replace('"', "'")
    for raw, coded in (("%", "%25"), ("#", "%23"), ("<", "%3C"), (">", "%3E")):
        svg = svg.replace(raw, coded)
    return "data:image/svg+xml," + svg


def replace_one(pattern, make, text, what):
    """text with the one match of pattern replaced by make(match)."""
    text, done = re.subn(pattern, make, text, flags=re.S)
    assert done == 1, f"{what}: {done} matches"
    return text


def set_icon(text, elements):
    """The favicon link, right after the <title>, replacing an earlier one."""
    icon = f'  <link rel="icon" type="image/svg+xml" href="{data_uri(elements)}">\n'
    text = re.sub(r'  <link rel="icon"[^\n]*\n', "", text)
    return replace_one(r"(  <title>[^\n]*</title>\n)", lambda m: m.group(1) + icon,
                       text, "<title>")


def heading(elements, name):
    """The top bar heading: the 16 px mark and the wordmark, Flow in the
    accent, the name in one span so the flex gap stays out of it."""
    name = name.replace("Flow", '<span class="brand-flow">Flow</span>')
    return (f'    <h1 class="brand">\n{inline(elements, 16, 16, "      ")}\n'
            f"      <span>{name}</span>\n    </h1>")


def rewrite(path, change):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    text = change(text)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(os.path.relpath(path, REPO))


def patch_viewer(name):
    small, large = mark(VIEWER[name], "S"), mark(VIEWER[name], "L")

    def page(text):
        text = set_icon(text, small)
        text = replace_one(r"    <h1[ >].*?</h1>", lambda _: heading(small, name),
                           text, "top bar heading")
        drop = inline(large, 64, 64, "    ") + "\n"
        return replace_one(
            r'(  <div id="drop-zone">\n)(    <svg class="brand-mark".*?</svg>\n)?(    <h2>)',
            lambda m: m.group(1) + drop + m.group(3), text, "drop zone")

    rewrite(os.path.join(VIEWERS, name, f"{name}.html"), page)
    rewrite(os.path.join(VIEWERS, name, "index.html"),
            lambda t: set_icon(t, small))


def patch_compare():
    small, large = compare_mark("S"), compare_mark("L")

    def page(text):
        text = set_icon(text, small)
        text = replace_one(
            r'    (?:<span class="app-name">FlowCompare</span>|<h1[ >].*?</h1>)',
            lambda _: heading(small, "FlowCompare"), text, "top bar heading")
        empty = inline(large, 64, 64, "        ") + "\n"
        return replace_one(
            r'(      <div id="empty">\n)(        <svg class="brand-mark".*?</svg>\n)?(        <h2>)',
            lambda m: m.group(1) + empty + m.group(3), text, "empty state")

    rewrite(os.path.join(VIEWERS, "FlowCompare.html"), page)
    # The repository's index.html, the GitHub Pages entry, leads to it.
    rewrite(os.path.join(REPO, "index.html"), lambda t: set_icon(t, small))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--patch", action="store_true",
                        help="Also put the marks into the pages.")
    args = parser.parse_args()
    faces = {w: Face(w) for w in ("Regular", "Medium", "SemiBold")}
    write_files(faces)
    if args.patch:
        for name in VIEWER:
            patch_viewer(name)
        patch_compare()
    return 0


if __name__ == "__main__":
    sys.exit(main())
