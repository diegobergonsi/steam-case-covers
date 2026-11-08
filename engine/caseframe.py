# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Reads a case the user made: one PNG with a see-through art window. Finds the window (and the tabs of the frame that cover part of it) from the picture itself.
Nothing here knows about covers or Steam; engine/steamcase.py keeps the chosen case and draws with it."""
import io, os

try:
    from PIL import Image, ImageDraw
except ImportError:                     # engine/steamcase.py says what is missing when a case is asked for
    Image = ImageDraw = None

_t = lambda text: text                  # the window replaces this with its own tr(), so a message is in its language; the command line stays English

MAX_FILE = 8 * 1024 * 1024              # a case is a 600 x 900 picture; anything bigger is not one
FRAME_ALPHA = 128                       # a frame pixel counts as visible from this opacity: glass cases are never fully opaque, a faint shadow is not a frame
CLEAR_ALPHA = 40                        # a pixel is part of the art window below this opacity: a soft glow along the frame's inner edge is not frame
MIN_FRAME = 0.02                        # a case shows at least this much visible frame (of the whole picture), or there is no case to speak of
CELL = 6                                # the see-through map of a case is read in cells of this many pixels: fast, then the edges are made exact
TAB_FILL = 0.5                          # a part of the frame inside the window is a tab (like the Switch's) only if it fills this much of its own box: rounded corners and shadows do not


class CaseFileError(Exception):
    """The file is not a usable case. The message is one sentence meant to be shown."""


def read(path):
    """The bytes of a case file the user chose. CaseFileError for a link, something that is not a plain file, or a file that is too big."""
    if os.path.islink(path):
        raise CaseFileError(_t("That file is a link, not a picture. Pick the picture itself."))
    if not os.path.isfile(path):
        raise CaseFileError(_t("That is not a PNG picture I can read."))
    if os.path.getsize(path) > MAX_FILE:
        raise CaseFileError(_t("That file is far too big to be a case (over %d MB).") % (MAX_FILE >> 20))
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        raise CaseFileError(_t("That is not a PNG picture I can read."))


def _cells(mask, full=False):
    """(columns, rows, set of the (x, y) cells of CELL pixels that hold a lit pixel of `mask` (an "L" picture of 0 and 255), or with `full` only the cells that
    are lit all over)."""
    small = mask.reduce(CELL)
    cols, rows = small.size
    return cols, rows, {(i % cols, i // cols) for i, v in enumerate(small.getdata()) if v == 255 or (v and not full)}


def _parts(cells):
    """The groups of `cells` that touch each other (up, down, left, right); `cells` is used up."""
    while cells:
        part, todo = set(), [next(iter(cells))]
        while todo:
            c = todo.pop()
            if c in cells:
                cells.discard(c)
                part.add(c)
                todo += [(c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)]
        yield part


def _find_window(alpha, min_window):
    """The box (x0, y0, x1, y1) of the see-through part joined to the middle of the picture: transparent corners and margins outside the case are not the window."""
    clear = alpha.point(lambda a: 255 if a < CLEAR_ALPHA else 0)
    cols, rows, empty = _cells(clear, full=True)
    if not empty:
        raise CaseFileError(_t("The art window is missing: the part where the cover goes must be fully see-through (a PNG with transparency)."))
    start = min(empty, key=lambda c: (c[0] - cols // 2) ** 2 + (c[1] - rows // 2) ** 2)
    ImageDraw.floodfill(clear, (start[0] * CELL + CELL // 2, start[1] * CELL + CELL // 2), 128)
    x0, y0, x1, y1 = clear.point(lambda v: 255 if v == 128 else 0).getbbox()
    if x1 - x0 < min_window or y1 - y0 < min_window:
        raise CaseFileError(_t("The art window is too small: it must be at least %d x %d pixels.") % (min_window, min_window))
    return x0, y0, x1, y1


def _find_tab(alpha, window):
    """The box of the tabs of the frame inside `window` (the Switch's red tab), or None. Only a part that fills TAB_FILL of its own box counts: the corners of a
    rounded window and a faint shadow along an edge do not."""
    covered = alpha.crop(window).point(lambda a: 255 if a >= CLEAR_ALPHA else 0)
    _, _, cells = _cells(covered)
    tabs = []
    for part in _parts(cells):
        xs, ys = [c[0] for c in part], [c[1] for c in part]
        box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        if len(part) >= 4 and len(part) >= TAB_FILL * (box[2] - box[0]) * (box[3] - box[1]):
            tabs.append(box)
    if not tabs:
        return None
    left, top = min(b[0] for b in tabs) * CELL, min(b[1] for b in tabs) * CELL
    tab = covered.crop((left, top, max(b[2] for b in tabs) * CELL, max(b[3] for b in tabs) * CELL)).getbbox()
    return None if tab is None else (tab[0] + left + window[0], tab[1] + top + window[1], tab[2] + left + window[0], tab[3] + top + window[1])


def measure(data, size, min_window):
    """({"window": [x0, y0, x1, y1], "overlay": [..]?}, the picture as RGBA) of the bytes of a case PNG of exactly `size` with a see-through window of at least
    `min_window` each way and a visible frame; "overlay" only when a tab covers part of the window (see _find_tab). CaseFileError for anything else."""
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as im:
            if im.size != tuple(size):
                raise CaseFileError(_t("A case must be a PNG of exactly %d x %d pixels; this one is %d x %d.") % (tuple(size) + im.size))
            if "A" not in im.getbands() and "transparency" not in im.info:
                raise CaseFileError(_t("The art window is missing: the part where the cover goes must be fully see-through (a PNG with transparency)."))
            frame = im.convert("RGBA")
    except CaseFileError:
        raise
    except Exception:
        raise CaseFileError(_t("That is not a PNG picture I can read."))
    alpha = frame.getchannel("A")
    if sum(alpha.histogram()[FRAME_ALPHA:]) < MIN_FRAME * size[0] * size[1]:
        raise CaseFileError(_t("The case is almost all see-through: it needs a visible frame around the art window."))
    window = _find_window(alpha, min_window)
    info = {"window": list(window)}
    tab = _find_tab(alpha, window)
    if tab:
        info["overlay"] = list(tab)
    return info, frame
