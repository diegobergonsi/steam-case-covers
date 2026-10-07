"""Small custom tkinter widgets for the steamcase window: rounded, dark, keyboard friendly.

Everything here is drawn on a Canvas because the built-in widgets cannot be rounded.
All of them take Tab focus, show a white focus ring, and react to Space / Enter.
"""
import tkinter as tk
import tkinter.font as tkfont

BG, CARD, CARD2 = "#11151c", "#182433", "#22344a"
LINE, FG, MUTED, FAINT = "#2c4259", "#e6edf3", "#93a7bb", "#5d7185"
ACCENT, ACCENT_H, ACCENT_D, DARK = "#66c0f4", "#8fd3ff", "#45a5dc", "#0b141d"
GREEN, RED = "#5ba32b", "#ff7b72"

_scale = 1.0


def set_scale(root):
    """Call once after creating the root window: sizes follow the screen's DPI."""
    global _scale
    _scale = max(1.0, root.winfo_fpixels("1i") / 96.0)


def px(n):
    return int(round(n * _scale))


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


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
        self.widget, self.text, self.tip = widget, text, None
        for ev, fn in (("<Enter>", self.show), ("<Leave>", self.hide), ("<FocusIn>", self.show),
                       ("<FocusOut>", self.hide), ("<Escape>", self.hide)):
            widget.bind(ev, fn, add="+")

    def show(self, _e=None):
        if self.tip:
            return
        x, y = self.widget.winfo_rootx() + px(24), self.widget.winfo_rooty() + self.widget.winfo_height() + px(6)
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        frame = tk.Frame(self.tip, bg=ACCENT, padx=1, pady=1)
        frame.pack()
        tk.Label(frame, text=self.text, justify="left", wraplength=px(360), bg="#0b1017", fg=FG, padx=px(12), pady=px(10)).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class InfoBadge(tk.Canvas):
    """Round "i" badge with a Tooltip."""

    def __init__(self, parent, text, bg=CARD):
        s = px(28)
        super().__init__(parent, width=s, height=s, bg=bg, highlightthickness=0, takefocus=True, cursor="hand2")
        self.disc = self.create_oval(px(4), px(4), s - px(4), s - px(4), fill=ACCENT, outline="")
        self.create_text(s // 2, s // 2, text="i", fill=DARK, font=("TkDefaultFont", 11, "bold"))
        self.ring = None
        self.bind("<Enter>", lambda e: self.itemconfigure(self.disc, fill=ACCENT_H), add="+")
        self.bind("<Leave>", lambda e: self.itemconfigure(self.disc, fill=ACCENT), add="+")
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")
        self.bind("<Button-1>", lambda e: self.focus_set())
        Tooltip(self, text)

    def _focus_in(self, _e):
        s = px(28)
        self.ring = self.create_oval(px(1), px(1), s - px(1), s - px(1), outline="#ffffff", width=2)

    def _focus_out(self, _e):
        if self.ring:
            self.delete(self.ring)
            self.ring = None


class RoundedButton(_Stateful):
    """Pill button. primary=True is the filled accent button; otherwise an outline button."""

    def __init__(self, parent, text, command=None, primary=False, state="normal", bg=CARD):
        self._font = tkfont.Font(font="TkDefaultFont")
        self._font.configure(weight="bold")
        super().__init__(parent, width=self._font.measure(text) + px(46), height=px(42), bg=bg,
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
            fill = (ACCENT_D if self._down else ACCENT_H if self._hover else ACCENT) if on else "#26384b"
            outline, fg = fill, DARK if on else FAINT
        else:
            fill = (LINE if self._down else "#2b405a" if self._hover else CARD2) if on else CARD
            outline, fg = (LINE if on else "#223244"), FG if on else FAINT
        if self._focus and on:
            round_rect(self, 1, 1, w - 1, h - 1, h // 2, outline="#ffffff", width=2, fill="")
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
        was = self._down
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
        super().__init__(parent, width=px(58) + self._font.measure(text) + px(6), height=px(32), bg=bg,
                         highlightthickness=0, takefocus=True, cursor="hand2")
        self._init_state(state)
        self.text, self.variable, self.command = text, variable, command
        self._focus = False
        variable.trace_add("write", lambda *a: self.draw())
        self.bind("<Button-1>", self._click)
        self.bind("<space>", self._key)
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
        track = (ACCENT if val else "#3a4f66") if on else ("#2a5a78" if val else "#26384b")
        if self._focus and on:
            round_rect(self, x - 3, y - 3, x + tw + 3, y + th + 3, th // 2 + 3, outline="#ffffff", width=2, fill="")
        round_rect(self, x, y, x + tw, y + th, th // 2, fill=track, outline=track)
        k = th - px(6)
        kx = x + tw - k - px(3) if val else x + px(3)
        self.create_oval(kx, y + px(3), kx + k, y + px(3) + k, fill="#ffffff" if on else "#8a9bab", outline="")
        self.create_text(px(58), h // 2, text=self.text, anchor="w", font=self._font, fill=FG if on else FAINT)

    def toggle(self):
        if self.enabled:
            self.variable.set(not self.variable.get())
            if self.command:
                self.command()

    def _click(self, _e):
        self.focus_set()
        self.toggle()

    def _key(self, _e):
        self.toggle()
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
        round_rect(self, 0, 0, w, h, h // 2, fill="#0c1219", outline="#1f2e3f")
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
            self.create_oval(2, 2, s - 2, s - 2, fill=GREEN, outline=GREEN)
            self.create_line(s * .30, s * .52, s * .45, s * .67, s * .72, s * .36, fill="#ffffff", width=max(2, px(3)),
                             capstyle="round", joinstyle="round")
        elif status == "active":
            self.create_oval(2, 2, s - 2, s - 2, fill=ACCENT, outline=ACCENT)
            self.create_text(s // 2, s // 2, text=self.number, fill=DARK, font=("TkDefaultFont", 13, "bold"))
        else:
            self.create_oval(2, 2, s - 2, s - 2, fill=CARD, outline=LINE, width=2)
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
