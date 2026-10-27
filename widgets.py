# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Small custom tkinter widgets for the steamcase window: rounded, dark, keyboard friendly.

Everything here is drawn on a Canvas because the built-in widgets cannot be rounded.
All of them take Tab focus, show a white focus ring, and react to Space / Enter.
"""
import base64
import io
import tkinter as tk
import tkinter.font as tkfont

try:
    from PIL import Image, ImageDraw
except ImportError:                       # the app still works without Pillow, with rougher corners
    Image = ImageDraw = None

BG, CARD, CARD2 = "#11151c", "#182433", "#22344a"
LINE, FG, MUTED, FAINT = "#2c4259", "#e6edf3", "#93a7bb", "#7d92a8"      # FAINT: 4.5:1 on CARD, it carries real text (locked steps, hints)
EDGE = "#5d7a96"           # outline of controls and off switches: 3:1 against CARD, so the control is visible without its label
ACCENT, ACCENT_H, ACCENT_D, DARK = "#66c0f4", "#8fd3ff", "#45a5dc", "#0b141d"
GREEN, RED, AMBER = "#5ba32b", "#ff7b72", "#f0b429"
RING = "#ffffff"           # keyboard focus ring and the on-state knob
RAISED_H = "#2b405a"       # hover fill of an outlined button
OFF_FILL, OFF_EDGE = "#26384b", "#223244"            # disabled controls: present, but clearly unavailable (exempt from the 3:1 rule)
OFF_TRACK_ON, OFF_KNOB = "#2a5a78", "#8a9bab"        # disabled switch, on and off knob
INSET, INSET_EDGE = "#0c1219", "#1f2e3f"             # progress track
TIP_BG = "#0b1017"

_scale = 1.0
_dragging = False       # True while a finger/mouse drag is scrolling the page: controls under it must not fire a click
REF_LINE = 21.0        # line height of the 11 pt default font on a 96 dpi screen


def set_scale(root):
    """Call once after creating the root window: sizes follow the screen's DPI."""
    global _scale
    # Also follow the real text size: a desktop can scale fonts (e.g. 225 % zoom) without telling Tk its DPI, which clipped every label.
    text = tkfont.Font(root=root, font="TkDefaultFont").metrics("linespace") / REF_LINE
    _scale = max(1.0, root.winfo_fpixels("1i") / 96.0, text)


def px(n):
    return int(round(n * _scale))


def _rgb(color):
    return None if not color else tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


_png_cache = {}


def _shape_png(w, h, r, fill, outline, width):
    """Anti-aliased rounded rectangle as base64 PNG: drawn at 2x to 4x size, then scaled down. Tk's canvas does not smooth its own shapes."""
    key = (w, h, r, fill, outline, width)
    data = _png_cache.get(key)
    if data is None:
        k = 4 if w * h < 90000 else 2
        im = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=r * k, fill=_rgb(fill),
                                             outline=_rgb(outline) if outline else None, width=max(1, width * k))
        buf = io.BytesIO()
        im.resize((w, h), Image.LANCZOS).save(buf, "PNG")
        data = base64.b64encode(buf.getvalue())
        if len(_png_cache) > 400:
            _png_cache.clear()
        _png_cache[key] = data
    return data


def round_rect(c, x1, y1, x2, y2, r, fill="", outline="", width=1, tags=()):
    """Draw a rounded rectangle (a pill when r is half the height). Smooth when Pillow is available."""
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    w, h = int(x2 - x1), int(y2 - y1)
    if Image is None or w < 2 or h < 2:
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
               x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return c.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=width, tags=tags)
    img = tk.PhotoImage(master=c, data=_shape_png(w, h, r, fill, outline, width))
    keep = c.__dict__.setdefault("_shape_imgs", [])
    keep.append(img)                                  # Tk drops an image nobody references
    if len(keep) > 60:
        del keep[:30]
    return c.create_image(int(x1), int(y1), image=img, anchor="nw", tags=tags)


class _Stateful(tk.Canvas):
    """Canvas that understands configure(state=...) / cget('state') and redraws itself."""

    def _init_state(self, state):
        self._state = state

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            kw["cursor"] = "hand2" if self._state == "normal" else "arrow"
            kw["takefocus"] = self._state == "normal"          # Tab skips disabled controls
            self.draw()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure

    def cget(self, key):
        return self._state if key == "state" else super().cget(key)

    @property
    def enabled(self):
        return self._state == "normal"


class Tooltip:
    """Help bubble: hover, or Tab to the widget. Escape closes it."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip, self._job = widget, text, None, None
        for ev, fn in (("<Enter>", self.schedule), ("<Leave>", self.hide), ("<FocusIn>", self.schedule),
                       ("<FocusOut>", self.hide), ("<Escape>", self.hide)):
            widget.bind(ev, fn, add="+")

    def schedule(self, _e=None):
        # Short delay, cancelled by hide(): stops a popup that steals focus from flickering on and off forever.
        if self._job is None and not self.tip:
            self._job = self.widget.after(120, self.show)

    def show(self, _e=None):
        self._job = None
        if self.tip:
            return
        x, y = self.widget.winfo_rootx() + px(24), self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        frame = tk.Frame(self.tip, bg=ACCENT, padx=1, pady=1)
        frame.pack()
        tk.Label(frame, text=self.text, justify="left", wraplength=px(360), bg=TIP_BG, fg=FG, padx=px(12), pady=px(10)).pack()

    def hide(self, _e=None):
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


class InfoBadge(tk.Canvas):
    """Round "i" badge with a Tooltip."""

    def __init__(self, parent, text, bg=CARD):
        s = px(48)             # touch target: the visible disc stays small, the hit area does not
        super().__init__(parent, width=s, height=s, bg=bg, highlightthickness=0, takefocus=True, cursor="hand2")
        self._paint(ACCENT)
        self.create_text(s // 2, s // 2, text="i", fill=DARK, font=("TkDefaultFont", 11, "bold"))
        self.ring = None
        self.bind("<Enter>", lambda e: self._paint(ACCENT_H), add="+")
        self.bind("<Leave>", lambda e: self._paint(ACCENT), add="+")
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self.bind("<Button-1>", lambda e: self.focus_set())
        Tooltip(self, text)

    def _paint(self, fill):
        s = px(48)
        self.delete("disc")
        round_rect(self, px(14), px(14), s - px(14), s - px(14), s, fill=fill, tags="disc")
        self.tag_lower("disc")

    def _focus_in(self, _e):
        s = px(48)
        self.ring = round_rect(self, px(11), px(11), s - px(11), s - px(11), s, outline=RING, width=2)

    def _focus_out(self, _e):
        if self.ring:
            self.delete(self.ring)
            self.ring = None


class RoundedButton(_Stateful):
    """Pill button. primary=True is the filled accent button; otherwise an outline button."""

    def __init__(self, parent, text, command=None, primary=False, state="normal", bg=CARD, quiet=False):
        """quiet=True: no outline, muted text; for rare or secondary actions that must not compete with the main one."""
        self._font = tkfont.Font(font="TkDefaultFont")
        self._font.configure(weight="bold")
        self.quiet, self._bg = quiet, bg
        super().__init__(parent, width=self._font.measure(text) + px(46), height=max(px(46), self._font.metrics("linespace") + px(18)), bg=bg,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self._init_state(state)
        self.text, self.command, self.primary = text, command, primary
        self._hover = self._down = self._focus = False
        for ev, fn in (("<Enter>", self._enter), ("<Leave>", self._leave), ("<ButtonPress-1>", self._press),
                       ("<ButtonRelease-1>", self._release), ("<FocusIn>", self._focus_in), ("<FocusOut>", self._focus_out),
                       ("<space>", self._key), ("<Return>", self._key)):
            self.bind(ev, fn)
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = int(super().cget("width")), int(super().cget("height"))
        on = self.enabled
        if self.primary:
            fill = (ACCENT_D if self._down else ACCENT_H if self._hover else ACCENT) if on else OFF_FILL
            outline, fg = fill, DARK if on else FAINT
        elif self.quiet:
            fill = (LINE if self._down else CARD2 if self._hover else self._bg) if on else self._bg
            outline, fg = fill, (FG if self._hover else MUTED) if on else FAINT
        else:
            fill = (LINE if self._down else RAISED_H if self._hover else CARD2) if on else CARD
            outline, fg = (EDGE if on else OFF_EDGE), FG if on else FAINT
        if self._focus and on:
            round_rect(self, 1, 1, w - 1, h - 1, h // 2, outline=RING, width=2, fill="")
        round_rect(self, 4, 4, w - 4, h - 4, h // 2, fill=fill, outline=outline, width=1)
        self.create_text(w // 2, h // 2, text=self.text, font=self._font, fill=fg)

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def _enter(self, _e): self._hover = True; self.draw()
    def _leave(self, _e): self._hover = self._down = False; self.draw()
    def _press(self, _e): self._down = True; self.focus_set(); self.draw()
    def _focus_in(self, _e): self._focus = True; self.draw()
    def _focus_out(self, _e): self._focus = False; self.draw()

    def _release(self, e):
        was = self._down and not _dragging
        self._down = False
        self.draw()
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    def _key(self, _e):
        self.invoke()
        return "break"


class Switch(_Stateful):
    """On/off switch with a label. Bound to a tk.BooleanVar."""

    def __init__(self, parent, text, variable, command=None, state="normal", bg=CARD):
        self._font = tkfont.Font(font="TkDefaultFont")
        super().__init__(parent, width=px(58) + self._font.measure(text) + px(6), height=max(px(48), self._font.metrics("linespace") + px(8)), bg=bg,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self._init_state(state)
        self.text, self.variable, self.command = text, variable, command
        self._focus = False
        variable.trace_add("write", lambda *a: self.draw())
        self._armed = False
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", self._key)
        self.bind("<Return>", self._key)
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self.draw()

    def _set_focus(self, v):
        self._focus = v
        self.draw()

    def draw(self):
        self.delete("all")
        h = int(super().cget("height"))
        tw, th = px(44), px(24)
        x, y = px(3), (h - th) // 2
        on, val = self.enabled, bool(self.variable.get())
        track = (ACCENT if val else EDGE) if on else (OFF_TRACK_ON if val else OFF_FILL)
        if self._focus and on:
            round_rect(self, x - 3, y - 3, x + tw + 3, y + th + 3, th // 2 + 3, outline=RING, width=2, fill="")
        round_rect(self, x, y, x + tw, y + th, th // 2, fill=track, outline=track)
        k = th - px(6)
        kx = x + tw - k - px(3) if val else x + px(3)
        round_rect(self, kx, y + px(3), kx + k, y + px(3) + k, k, fill=RING if on else OFF_KNOB)
        self.create_text(px(58), h // 2, text=self.text, anchor="w", font=self._font, fill=FG if on else FAINT)

    def toggle(self):
        if self.enabled:
            self.variable.set(not self.variable.get())
            if self.command:
                self.command()

    def _click(self, _e):
        self.focus_set()
        self._armed = True

    def _release(self, e):
        armed, self._armed = self._armed, False
        if armed and not _dragging and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.toggle()

    def _key(self, _e):
        self.toggle()
        return "break"


def value_from_x(x, width, margin, top):
    """Value (0..top) for a pixel position on a slider track `width` wide whose ends are `margin` px inside the edges. Clamped."""
    span = width - 2 * margin
    if span <= 0:
        return 0
    return max(0, min(top, round((x - margin) * top / span)))


def hue_from_x(x, width, margin):
    """Hue (0..359 degrees) for a pixel position on a slider track; see value_from_x."""
    return value_from_x(x, width, margin, 359)


def drag_mode(dx, dy, threshold):
    """What a pointer drag means once it has moved (dx, dy) pixels from where it started: None while it is still a tap, "horizontal" to slide the
    thumb, "vertical" to scroll the page. A tie goes to the slider, so a sideways slide is never taken for a swipe."""
    if max(abs(dx), abs(dy)) < threshold:
        return None
    return "horizontal" if abs(dx) >= abs(dy) else "vertical"


def step_value(value, key, top, big=10, wrap=False):
    """The value (0..top) after a key press on a slider: arrows move 1, PageUp/PageDown `big`, Home is 0, End is `top`. Arrows stop at the ends,
    or wrap around when `wrap` is set."""
    if key == "Home":
        return 0
    if key == "End":
        return top
    delta = {"Left": -1, "Down": -1, "Right": 1, "Up": 1, "Prior": big, "Next": -big}.get(key)
    if delta is None:
        return value
    return (value + delta) % (top + 1) if wrap else max(0, min(top, value + delta))


def step_hue(hue, key, big=30):
    """The hue after a key press on the hue slider: like step_value over 0..359, and the arrows wrap around."""
    return step_value(hue, key, 359, big, wrap=True)


def step_choice(index, key, count):
    """The option index (0..count-1) after a key press on a choice group: Left/Up one back, Right/Down one forward, Home the first, End the last.
    It stops at the ends (no wrap)."""
    if key == "Home":
        return 0
    if key == "End":
        return count - 1
    delta = {"Left": -1, "Up": -1, "Right": 1, "Down": 1}.get(key)
    return index if delta is None else max(0, min(count - 1, index + delta))


def _dim(color, amount=0.6, toward=CARD):
    """A colour faded toward the card background: the look of a disabled control."""
    a, b = _rgb(color), _rgb(toward)
    return "#%02x%02x%02x" % tuple(round(x * (1 - amount) + y * amount) for x, y in zip(a[:3], b[:3]))


def _rainbow_png(w, h, colors):
    """A pill-shaped strip `w` x `h` whose column x is coloured colors[x], as base64 PNG (anti-aliased ends)."""
    k = 3
    strip = Image.new("RGB", (w, 1))
    strip.putdata([_rgb(c)[:3] for c in colors])
    big = strip.resize((w * k, h * k), Image.NEAREST).convert("RGBA")
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=h * k // 2, fill=255)
    big.putalpha(mask)
    buf = io.BytesIO()
    big.resize((w, h), Image.LANCZOS).save(buf, "PNG")
    return base64.b64encode(buf.getvalue())


class _Slider(_Stateful):
    """Base of the colour sliders: picks an integer 0..TOP into a tk.IntVar over a track painted by `color_for(value)` ('#rrggbb').
    A tap or a sideways drag sets the value; a mostly vertical swipe that starts on it scrolls the window instead (so a finger on its way to the
    button below does not recolour the covers). Arrows, PageUp/PageDown, Home and End work from the keyboard."""

    TOP, BIG, WRAP = 100, 10, False           # largest value, PageUp/PageDown step, whether the arrows wrap around

    def __init__(self, parent, variable, color_for, command=None, state="normal", bg=CARD, depends=()):
        super().__init__(parent, width=px(260), height=px(52), bg=bg, highlightthickness=0, takefocus=True, cursor="hand2")
        self._init_state(state)
        self.variable, self.color_for, self.command, self._bg = variable, color_for, command, bg
        self._focus = False
        self._start, self._mode = None, None                 # where the pointer went down, and what the drag turned out to be
        self._track, self._track_key = None, None
        self._repaint_job = None
        variable.trace_add("write", lambda *a: self.draw())
        for other in depends:                                # the track colours follow these variables
            other.trace_add("write", lambda *a: self._repaint())
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        for key in ("Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End"):
            self.bind("<%s>" % key, self._key)
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self.draw()

    def _geometry(self):
        w = self.winfo_width() if self.winfo_width() > 1 else int(super().cget("width"))
        return w, int(super().cget("height")), px(36), px(36) // 2 + px(8)           # width, height, thumb size, margin of the thumb's centre

    def _repaint(self):
        """Rebuild the track once per burst of changes (a swatch sets three variables), when the window is next idle."""
        if self._repaint_job is None:
            self._repaint_job = self.after_idle(self._repaint_now)

    def _repaint_now(self):
        self._repaint_job = None
        self._track_key = None
        try:
            self.draw()
        except tk.TclError:                                  # the window closed in between
            pass

    def _set_focus(self, v):
        self._focus = v
        self.draw()

    def draw(self):
        self.delete("all")
        w, h, thumb, margin = self._geometry()
        on = self.enabled
        track_h = px(48)
        key = (w, track_h, on)
        if self._track_key != key:
            colors = [self.color_for(value_from_x(x, w, margin, self.TOP)) for x in range(w)]
            if not on:
                colors = [_dim(c) for c in colors]
            self._track = tk.PhotoImage(master=self, data=_rainbow_png(w, track_h, colors)) if Image is not None else None
            self._track_key = key
        top = (h - track_h) // 2
        if self._track is not None:
            self.create_image(0, top, image=self._track, anchor="nw")
        value = max(0, min(self.TOP, int(self.variable.get())))
        cx = margin + value * (w - 2 * margin) / self.TOP
        cy = h // 2
        if self._focus and on:
            round_rect(self, cx - thumb // 2 - px(8), cy - thumb // 2 - px(8), cx + thumb // 2 + px(8), cy + thumb // 2 + px(8), thumb // 2 + px(8), outline=RING, width=2, fill="")
        round_rect(self, cx - thumb // 2 - px(4), cy - thumb // 2 - px(4), cx + thumb // 2 + px(4), cy + thumb // 2 + px(4), thumb // 2 + px(4), fill=self._bg, outline=self._bg)
        round_rect(self, cx - thumb // 2, cy - thumb // 2, cx + thumb // 2, cy + thumb // 2, thumb // 2, fill=RING if on else OFF_KNOB, outline=RING if on else OFF_KNOB)

    def _set(self, value):
        if self.enabled and int(self.variable.get()) != value:
            self.variable.set(value)
            if self.command:
                self.command()

    def _from_pointer(self, e):
        w, _, _, margin = self._geometry()
        self._set(value_from_x(e.x, w, margin, self.TOP))

    def _press(self, e):
        if self.enabled:
            self.focus_set()
            self._start, self._mode = (e.x_root, e.y_root), None

    def _motion(self, e):
        if not (self.enabled and self._start):
            return
        if self._mode is None:
            self._mode = drag_mode(e.x_root - self._start[0], e.y_root - self._start[1], px(6))
        if self._mode == "horizontal":
            self._from_pointer(e)

    def _release(self, e):
        tap = self.enabled and self._start and self._mode is None
        self._start, self._mode = None, None
        if tap:
            self._from_pointer(e)

    def claims_drag(self):
        """True while a sideways drag is sliding the thumb: ScrollFrame must not also scroll."""
        return self.enabled and self._mode == "horizontal"

    def _key(self, e):
        if self.enabled:
            self._set(step_value(int(self.variable.get()), e.keysym, self.TOP, self.BIG, self.WRAP))
        return "break"


class HueSlider(_Slider):
    """A rainbow slider that picks a hue, 0..359 degrees. `color_for(hue)` gives the '#rrggbb' to paint at that hue; the arrows wrap around."""

    TOP, BIG, WRAP = 359, 30, True


class ToneSlider(_Slider):
    """A slider that picks a tone strength, 0..100, with no wrap (colourfulness, brightness). `depends` lists the tk.IntVars the track colours
    depend on (the hue, say); the track repaints when one of them changes."""


class Swatch(_Stateful):
    """A round colour button. `selected()` says whether to draw it as the chosen one; call draw() again when that changes."""

    def __init__(self, parent, color, selected, command, state="normal", bg=CARD):
        super().__init__(parent, width=px(52), height=px(52), bg=bg, highlightthickness=0, takefocus=True, cursor="hand2")
        self._init_state(state)
        self.color, self.selected, self.command = color, selected, command
        self._focus = self._armed = False
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", self._key)
        self.bind("<Return>", self._key)
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self.draw()

    def _set_focus(self, v):
        self._focus = v
        self.draw()

    def draw(self):
        self.delete("all")
        w = int(super().cget("width"))
        c, d, on = w // 2, px(40), self.enabled
        if self._focus and on:
            round_rect(self, c - d // 2 - px(6), c - d // 2 - px(6), c + d // 2 + px(6), c + d // 2 + px(6), d // 2 + px(6), outline=RING, width=2, fill="")
        if self.selected() and on:
            round_rect(self, c - d // 2 - px(4), c - d // 2 - px(4), c + d // 2 + px(4), c + d // 2 + px(4), d // 2 + px(4), outline=ACCENT, width=3, fill="")
        color = self.color if on else _dim(self.color)
        round_rect(self, c - d // 2, c - d // 2, c + d // 2, c + d // 2, d // 2, fill=color, outline=EDGE if on else OFF_EDGE, width=1)

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def _click(self, _e):
        self.focus_set()
        self._armed = True

    def _release(self, e):
        armed, self._armed = self._armed, False
        if armed and not _dragging and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    def _key(self, _e):
        self.invoke()
        return "break"


class Bar(tk.Canvas):
    """Thin rounded progress bar. Use configure(value=..., maximum=...) like ttk.Progressbar."""

    def __init__(self, parent, bg=CARD):
        super().__init__(parent, height=px(10), bg=bg, highlightthickness=0)
        self._value, self._max = 0, 1
        self.bind("<Configure>", lambda e: self.draw())

    def configure(self, cnf=None, **kw):
        if "value" in kw:
            self._value = kw.pop("value")
        if "maximum" in kw:
            self._max = max(kw.pop("maximum"), 1)
        self.draw()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure

    def cget(self, key):
        return {"value": self._value, "maximum": self._max}.get(key) if key in ("value", "maximum") else super().cget(key)

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), int(super().cget("height"))
        if w < 4:
            return
        round_rect(self, 0, 0, w, h, h // 2, fill=INSET, outline=INSET_EDGE)
        if self._value > 0:
            fw = max(h, int(w * min(self._value / self._max, 1)))
            round_rect(self, 0, 0, fw, h, h // 2, fill=ACCENT, outline=ACCENT)


class StepBadge(tk.Canvas):
    """Numbered circle: locked (outline), active (filled), done (green check)."""

    def __init__(self, parent, number, bg=CARD):
        s = px(34)
        super().__init__(parent, width=s, height=s, bg=bg, highlightthickness=0)
        self.number, self.s = str(number), s
        self.set("locked")

    def set(self, status):
        self.delete("all")
        s = self.s
        if status == "done":
            round_rect(self, 2, 2, s - 2, s - 2, s, fill=GREEN, outline=GREEN)
            self.create_line(s * .30, s * .52, s * .45, s * .67, s * .72, s * .36, fill=RING, width=max(2, px(3)),
                             capstyle="round", joinstyle="round")
        elif status == "active":
            round_rect(self, 2, 2, s - 2, s - 2, s, fill=ACCENT, outline=ACCENT)
            self.create_text(s // 2, s // 2, text=self.number, fill=DARK, font=("TkDefaultFont", 13, "bold"))
        else:
            round_rect(self, 2, 2, s - 2, s - 2, s, fill=CARD, outline=LINE, width=2)
            self.create_text(s // 2, s // 2, text=self.number, fill=FAINT, font=("TkDefaultFont", 13, "bold"))


class Card(tk.Canvas):
    """Rounded panel. Put content in card.body; the card grows with it."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg, highlightthickness=0, width=px(700), height=px(120))
        self.body = tk.Frame(self, bg=CARD)
        self._win = self.create_window(px(22), px(18), window=self.body, anchor="nw")
        self.bind("<Configure>", self._relayout)
        self.body.bind("<Configure>", self._relayout)

    def _relayout(self, _e=None):
        w = self.winfo_width()
        if w < 10:
            return
        h = self.body.winfo_reqheight() + px(36)
        if int(super().cget("height")) != h:
            super().configure(height=h)
        self.itemconfigure(self._win, width=w - px(44))
        self.delete("bg")
        round_rect(self, 1, 1, w - 1, h - 1, px(18), fill=CARD, outline=LINE, tags="bg")
        self.tag_lower("bg")


class Flow(tk.Frame):
    """Left-to-right row of widgets that wraps onto the next line when the window gets narrow.
    Children are created with this frame as parent and registered with add(widget, gap)."""

    def __init__(self, parent, bg=CARD):
        super().__init__(parent, bg=bg)
        self._items, self._placed = [], None
        self.bind("<Configure>", self._layout)

    def add(self, widget, gap=0):
        if all(w is not widget for w, _ in self._items):
            self._items.append((widget, gap))
        self._layout()

    def remove(self, widget):
        self._items = [(w, g) for w, g in self._items if w is not widget]
        widget.grid_forget()
        self._placed = None
        self._layout()

    def clear(self):
        for w, _ in self._items:
            w.grid_forget()
        self._items, self._placed = [], None

    def _layout(self, _e=None):
        width = self.winfo_width()
        if width < 2:
            width = 10 ** 6                      # not on screen yet: ask for a single line
        x = row = col = 0
        plan = []
        for w, gap in self._items:
            need = w.winfo_reqwidth() + (gap if col else 0)
            if col and x + need > width:
                row, col, x, need = row + 1, 0, 0, w.winfo_reqwidth()
            plan.append((w, row, col, gap if col else 0))
            x += need
            col += 1
        if plan == self._placed:
            return
        self._placed = plan
        for w, r, c, g in plan:
            w.grid(row=r, column=c, padx=(g, 0), pady=(0 if r == 0 else px(4), 0), sticky="w")


class _Pill(_Stateful):
    """One option of a Choice: a touch-sized pill, filled with the accent while it is the chosen one."""

    def __init__(self, parent, text, selected, select, move, bg=CARD):
        self._font = tkfont.Font(font="TkDefaultFont")
        self._font.configure(weight="bold")
        super().__init__(parent, width=self._font.measure(text) + px(40), height=max(px(46), self._font.metrics("linespace") + px(18)), bg=bg,
                         highlightthickness=0, takefocus=False, cursor="hand2")
        self._init_state("normal")
        self.text, self.selected, self.select, self.move = text, selected, select, move
        self._focus = self._armed = False
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", self._key)
        self.bind("<Return>", self._key)
        for key in ("Left", "Right", "Up", "Down", "Home", "End"):
            self.bind("<%s>" % key, lambda e: self._move(e.keysym))
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))

    def _set_focus(self, v):
        self._focus = v
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = int(super().cget("width")), int(super().cget("height"))
        on, chosen = self.enabled, self.selected()
        if on:
            fill, outline, fg = (ACCENT, ACCENT, DARK) if chosen else (CARD2, EDGE, FG)
        else:
            fill, outline, fg = (OFF_TRACK_ON, OFF_TRACK_ON, MUTED) if chosen else (CARD, OFF_EDGE, FAINT)
        if self._focus and on:
            round_rect(self, 1, 1, w - 1, h - 1, h // 2, outline=RING, width=2, fill="")
        round_rect(self, 4, 4, w - 4, h - 4, h // 2, fill=fill, outline=outline, width=1)
        self.create_text(w // 2, h // 2, text=self.text, font=self._font, fill=fg)

    def _click(self, _e):
        if self.enabled:
            self.focus_set()
            self._armed = True

    def _release(self, e):
        armed, self._armed = self._armed, False
        if armed and not _dragging and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.select()

    def _key(self, _e):
        if self.enabled:
            self.select()
        return "break"

    def _move(self, key):
        if self.enabled:
            self.move(key)
        return "break"


class Choice(tk.Frame):
    """A group of 2 to 4 pill options of which exactly one is chosen, kept in a tk.StringVar.
    `options` is a list of (value, label). The group is one Tab stop: Tab lands on the chosen pill, and the arrows, Home and End move AND choose
    (Space / Enter choose the focused pill). The pills wrap onto more rows when the window is narrow. command() runs once per change by the user."""

    def __init__(self, parent, variable, options, command=None, state="normal", bg=CARD):
        self._rows_h = None
        super().__init__(parent, bg=bg)
        self.bind("<Configure>", self._layout)
        self.variable, self.command, self._state = variable, command, state
        self._values = [value for value, _ in options]
        self._pills = []
        for i, (value, label) in enumerate(options):
            pill = _Pill(self, label, lambda v=value: self.variable.get() == v, lambda v=value: self._choose(v), self._move_from(i), bg=bg)
            self._pills.append(pill)
        self._layout()
        variable.trace_add("write", lambda *a: self._sync())
        self.configure(state=state)

    def _layout(self, _e=None):
        """Place the pills row by row with place(): a grid (as Flow uses) would give the pills of one column the width of the widest, which pushes them off a narrow window."""
        width = self.winfo_width()
        if width < 2:
            width = 10 ** 6                      # not on screen yet: ask for a single line
        gap, x, y, row_h = px(8), 0, 0, 0
        for pill in self._pills:
            pw, ph = pill.winfo_reqwidth(), pill.winfo_reqheight()
            if x and x + gap + pw > width:
                x, y, row_h = 0, y + row_h + px(4), 0
            x += gap if x else 0
            pill.place(x=x, y=y)
            x, row_h = x + pw, max(row_h, ph)
        if (y + row_h) != self._rows_h:
            self._rows_h = y + row_h
            tk.Frame.configure(self, height=self._rows_h, width=max([p.winfo_reqwidth() for p in self._pills] + [1]))

    def _move_from(self, i):
        return lambda key: self._choose_at(step_choice(i, key, len(self._pills)), focus=True)

    def _choose_at(self, index, focus=False):
        self._choose(self._values[index])
        if focus:
            self._pills[index].focus_set()

    def _choose(self, value):
        if self.enabled and self.variable.get() != value:
            self.variable.set(value)
            if self.command:
                self.command()

    def _sync(self):
        """Repaint the pills, and make the chosen one the group's only Tab stop (the first one while nothing is chosen)."""
        try:
            current = self.variable.get()
            stop = self._values.index(current) if current in self._values else 0
            for i, pill in enumerate(self._pills):
                pill.configure(takefocus=self.enabled and i == stop)
                pill.draw()
        except tk.TclError:                                  # the window closed in between
            pass

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self._state = kw.pop("state")
            for pill in self._pills:
                pill.configure(state=self._state)            # also redraws and sets the cursor
            self._sync()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure

    def cget(self, key):
        return self._state if key == "state" else super().cget(key)

    @property
    def enabled(self):
        return self._state == "normal"


class ScrollFrame(tk.Frame):
    """Vertical scroller for small screens (Steam Deck: 800 px high). Put content in .inner.
    The scrollbar only appears when the content does not fit. Mouse wheel and Tab both scroll."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=px(16), relief="flat", borderwidth=0,
                                highlightthickness=0, takefocus=0, troughcolor=BG, bg=LINE, activebackground=ACCENT)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda e: self._update())
        self.canvas.bind("<Configure>", self._on_canvas)
        top = self.winfo_toplevel()
        top.bind_all("<MouseWheel>", self._wheel, add="+")                       # Windows, macOS
        top.bind_all("<Button-4>", lambda e: self._scroll(-1), add="+")          # Linux
        top.bind_all("<Button-5>", lambda e: self._scroll(1), add="+")
        top.bind_all("<FocusIn>", self._focus, add="+")                          # Tab into something off-screen: scroll to it
        self._drag, self._drag_widget = None, None                               # touch: a finger drag arrives as mouse press, motion, release
        top.bind_all("<ButtonPress-1>", self._drag_start, add="+")
        top.bind_all("<B1-Motion>", self._drag_move, add="+")
        top.bind_all("<ButtonRelease-1>", self._drag_end, add="+")

    def _on_canvas(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._update()

    def _update(self):
        need = self.inner.winfo_reqheight() > self.canvas.winfo_height() > 1
        self.canvas.configure(scrollregion=(0, 0, 1, self.inner.winfo_reqheight()))
        if need and not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y")
        elif not need and self.bar.winfo_ismapped():
            self.bar.pack_forget()
            self.canvas.yview_moveto(0)

    def scrollable(self):
        return self.bar.winfo_ismapped()

    def _scroll(self, units):
        if self.scrollable():
            self.canvas.yview_scroll(units, "units")

    def _wheel(self, e):
        self._scroll(-1 if e.delta > 0 else 1)

    def _drag_start(self, e):
        self._drag = None
        if self.scrollable() and isinstance(e.widget, tk.Widget) and str(e.widget).startswith(str(self.inner)):
            self._drag = (e.y_root, self.canvas.canvasy(0), False)
            self._drag_widget = e.widget

    def _drag_move(self, e):
        global _dragging
        if not self._drag:
            return
        claim = getattr(self._drag_widget, "claims_drag", None)
        if claim and claim():                       # the widget is using this drag itself (the colour slider being slid sideways)
            self._drag = None
            return
        y0, view0, moving = self._drag
        if not moving and abs(e.y_root - y0) < px(10):
            return                                  # still a tap: leave the control under the finger alone
        _dragging = True
        self._drag = (y0, view0, True)
        total = self.inner.winfo_reqheight()
        self.canvas.yview_moveto(max(0, min(1, (view0 + y0 - e.y_root) / total)))

    def _drag_end(self, _e):
        global _dragging
        self._drag = None
        _dragging = False

    def _focus(self, e):
        w = e.widget
        if not self.scrollable() or not isinstance(w, tk.Widget):
            return
        try:
            if not str(w).startswith(str(self.inner)):
                return
            top = w.winfo_rooty() - self.inner.winfo_rooty()
            bottom = top + w.winfo_height()
            view_h, total = self.canvas.winfo_height(), self.inner.winfo_reqheight()
            y0 = self.canvas.canvasy(0)
            if top < y0 + px(10):
                self.canvas.yview_moveto(max(0, (top - px(24)) / total))
            elif bottom > y0 + view_h - px(10):
                self.canvas.yview_moveto(min(1, (bottom - view_h + px(24)) / total))
        except tk.TclError:
            pass


# ----- dialogs ---------------------------------------------------------------------------------------------


class _Glyph(tk.Canvas):
    """Round icon for dialogs: warning (!), question (?), info (i) or error (x)."""

    COLORS = {"warning": AMBER, "question": ACCENT, "info": ACCENT, "error": RED}

    def __init__(self, parent, kind):
        s = px(48)
        super().__init__(parent, width=s, height=s, bg=CARD, highlightthickness=0)
        color = self.COLORS.get(kind, ACCENT)
        round_rect(self, 2, 2, s - 2, s - 2, s, fill=color, outline=color)
        if kind == "error":
            a, b = s * .34, s * .66
            self.create_line(a, a, b, b, fill=DARK, width=max(3, px(4)), capstyle="round")
            self.create_line(a, b, b, a, fill=DARK, width=max(3, px(4)), capstyle="round")
        else:
            self.create_text(s // 2, s // 2, text={"warning": "!", "question": "?"}.get(kind, "i"), fill=DARK, font=("TkDefaultFont", 20, "bold"))


class Dialog(tk.Toplevel):
    """A modal message window in the app's own style (replaces the plain system message boxes).

    paragraphs: list of (text, style), style in "main", "muted", "note", "warn".
    buttons:    list of (label, value, primary); the primary one has the focus, so Enter confirms.
    Escape or closing the window returns `cancel_value`."""

    def __init__(self, parent, title, paragraphs, kind="info", buttons=(("OK", True, True),), cancel_value=None):
        super().__init__(parent)
        self.result = cancel_value
        self._cancel_value = cancel_value
        self.title(title)
        self.configure(bg=LINE)
        self.resizable(False, False)
        icon = getattr(parent, "_icon", None)
        if icon is not None:
            try:
                self.iconphoto(False, icon)
            except tk.TclError:
                pass
        self.transient(parent)
        frame = tk.Frame(self, bg=CARD, padx=px(28), pady=px(24))
        frame.pack(padx=1, pady=1)
        head = tk.Frame(frame, bg=CARD)
        head.pack(fill="x")
        _Glyph(head, kind).pack(side="left")
        tk.Label(head, text=title, bg=CARD, fg=FG, font=("TkDefaultFont", 15, "bold"), justify="left",
                 wraplength=px(400), anchor="w").pack(side="left", padx=px(16))
        body = tk.Frame(frame, bg=CARD)
        body.pack(fill="x", pady=(px(16), px(6)))
        for text, style in paragraphs:
            fg = {"main": FG, "muted": MUTED, "note": ACCENT}.get(style, AMBER)       # note: good news, in the accent color; anything else is a warning
            tk.Label(body, text=text, bg=CARD, fg=fg, font=("TkDefaultFont", 11, "bold") if style in ("warn", "note") else ("TkDefaultFont", 11),
                     justify="left", wraplength=px(470), anchor="w").pack(fill="x", pady=(0, px(10)))
        row = tk.Frame(frame, bg=CARD)
        row.pack(fill="x", pady=(px(8), 0))
        first_primary = None
        for label, value, primary in reversed(list(buttons)):                 # right to left: the primary action sits at the right edge
            b = RoundedButton(row, label, lambda v=value: self._finish(v), primary=primary)
            b.pack(side="right", padx=(px(10), 0))
            if primary and first_primary is None:
                first_primary = b
        self._default = first_primary or row
        self.bind("<Escape>", lambda e: self._finish(self._cancel_value))
        self.protocol("WM_DELETE_WINDOW", lambda: self._finish(self._cancel_value))
        self.update_idletasks()
        self._center(parent)

    def _center(self, parent):
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + max(px(40), (parent.winfo_height() - h) // 3)
        except tk.TclError:
            x, y = 200, 150
        self.geometry("+%d+%d" % (max(0, x), max(0, y)))

    def _finish(self, value):
        self.result = value
        self.destroy()

    def show(self):
        self.deiconify()
        self.lift()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self._default.focus_force()
        self.wait_window()
        return self.result


class Messages:
    """Drop-in for tkinter.messagebox using Dialog. Set .parent to the main window."""

    parent = None

    @staticmethod
    def _paragraphs(message):
        if not isinstance(message, str):
            return list(message)
        parts = [p.strip() for p in message.split("\n\n") if p.strip()]
        return [(p, "main" if i == 0 else "muted") for i, p in enumerate(parts)]

    def _run(self, title, message, kind, buttons, cancel_value):
        return Dialog(self.parent, title, self._paragraphs(message), kind, buttons, cancel_value).show()

    def askokcancel(self, title, message, icon="question", ok="OK", cancel="Cancel", **_):
        return bool(self._run(title, message, icon, ((cancel, False, False), (ok, True, True)), False))

    def choose(self, title, message, buttons, icon="question"):
        """One button per (label, value, primary); returns the chosen value, or None on Escape."""
        return self._run(title, message, icon, buttons, None)

    def showinfo(self, title, message, **_):
        self._run(title, message, "info", (("OK", True, True),), True)

    def showerror(self, title, message, **_):
        self._run(title, message, "error", (("OK", True, True),), True)
