#!/usr/bin/env python3
"""steamcase GUI: three steps, no terminal.  Run:  python gui.py"""
import os, sys, webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

import steamcase as sc

BG, CARD, FG, MUTED, ACCENT = "#171a21", "#1b2838", "#e6edf3", "#8fa3b8", "#66c0f4"


class Tooltip:
    """Small hover bubble."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _e=None):
        if self.tip:
            return
        x, y = self.widget.winfo_rootx() + 20, self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.tip, text=self.text, justify="left", wraplength=340, bg="#0e1218", fg=FG,
                 relief="solid", borderwidth=1, padx=10, pady=8).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Steam Case Covers")
        self.configure(bg=BG)
        self._style()

        self.library_path = None          # chosen userdata.json
        self.installed_only = tk.BooleanVar(value=False)
        self.skip_auto = tk.BooleanVar(value=False)
        self.restart_steam = tk.BooleanVar(value=True)

        tk.Label(self, text="Steam Case Covers", bg=BG, fg=FG, font=("TkDefaultFont", 20, "bold")).pack(anchor="w", padx=24, pady=(20, 0))
        tk.Label(self, text="Put every game in your library in a physical case.", bg=BG, fg=MUTED).pack(anchor="w", padx=24, pady=(0, 12))

        self.step1 = self._card("1", "Get your game list")
        self.step2 = self._card("2", "Make the covers")
        self.step3 = self._card("3", "Add them to Steam")
        self._build_step1(self.step1)
        self._build_step2(self.step2)
        self._build_step3(self.step3)
        self._set_state(self.step2, False)
        self._set_state(self.step3, False)
        self.update_idletasks()                       # size the window to its content
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

    # ----- look -----
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TButton", padding=(14, 8))
        s.configure("Accent.TButton", background=ACCENT, foreground="#0b141d", padding=(14, 8))
        s.map("Accent.TButton", background=[("active", "#8fd3ff"), ("disabled", "#3a4a5a")])
        s.configure("TCheckbutton", background=CARD, foreground=FG)
        s.map("TCheckbutton", background=[("active", CARD)])
        s.configure("Horizontal.TProgressbar", troughcolor="#0e1218", background=ACCENT, thickness=14)

    def _card(self, num, title):
        outer = tk.Frame(self, bg=CARD, padx=18, pady=14)
        outer.pack(fill="x", padx=24, pady=6)
        head = tk.Frame(outer, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=num, bg=ACCENT, fg="#0b141d", width=2, font=("TkDefaultFont", 12, "bold")).pack(side="left")
        tk.Label(head, text=title, bg=CARD, fg=FG, font=("TkDefaultFont", 13, "bold")).pack(side="left", padx=10)
        body = tk.Frame(outer, bg=CARD)
        body.pack(fill="x", pady=(10, 0))
        body.outer = outer
        return body

    def _row(self, parent):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=3)
        return r

    def _note(self, parent, text):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, justify="left", wraplength=640, anchor="w").pack(fill="x", pady=(0, 4))

    def _set_state(self, body, enabled):
        st = "normal" if enabled else "disabled"

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (ttk.Button, ttk.Checkbutton)):
                    c.configure(state=st)
                walk(c)
        walk(body)

    # ----- step 1 -----
    def _build_step1(self, body):
        self._note(body, "Steam keeps your full game list on a web page. Click the button, log in if asked, "
                         "then press Ctrl+S and save the page (keep the name userdata.json). "
                         "This app will notice the file by itself.")
        r = self._row(body)
        ttk.Button(r, text="Download your userdata.json", style="Accent.TButton", command=self.open_download_page).pack(side="left")
        ttk.Button(r, text="Browse…", command=self.browse).pack(side="left", padx=8)
        r = self._row(body)
        ttk.Checkbutton(r, text="Only my installed games (no file needed)", variable=self.installed_only, command=self.on_installed_only).pack(side="left")
        self.step1_status = tk.Label(body, text="Waiting for userdata.json…", bg=CARD, fg=MUTED, anchor="w")
        self.step1_status.pack(fill="x", pady=(6, 0))

    def open_download_page(self):
        webbrowser.open(sc.LIBRARY_JSON_URL)
        self.step1_status.configure(text="Page opened. Save it as userdata.json (Ctrl+S)…")

    def browse(self):
        self._todo("Browse for a file", 2)

    def on_installed_only(self):
        ok = self.installed_only.get()
        self.step1_status.configure(text="Using installed games only." if ok else "Waiting for userdata.json…", fg=ACCENT if ok else MUTED)
        self._set_state(self.step2, ok)
        self._set_state(self.step1, True)

    # ----- step 2 -----
    def _build_step2(self, body):
        self._note(body, "Downloads each game's artwork from Steam and builds the covers on your computer.")
        r = self._row(body)
        ttk.Checkbutton(r, text="Skip blurry auto-art", variable=self.skip_auto).pack(side="left")
        info = tk.Label(r, text="?", bg=ACCENT, fg="#0b141d", width=2, cursor="question_arrow", font=("TkDefaultFont", 10, "bold"))
        info.pack(side="left", padx=6)
        Tooltip(info, sc.AUTO_ART_HELP)
        r = self._row(body)
        ttk.Button(r, text="Make covers", style="Accent.TButton", command=lambda: self._todo("Make covers", 3)).pack(side="left")
        ttk.Button(r, text="Cancel", command=lambda: self._todo("Cancel", 3)).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.pack(fill="x", pady=(8, 2))
        self.step2_status = tk.Label(body, text="Not started.", bg=CARD, fg=MUTED, anchor="w")
        self.step2_status.pack(fill="x")

    # ----- step 3 -----
    def _build_step3(self, body):
        self._note(body, "Warning: this step closes Steam automatically (any running game or download stops). "
                         "Your current artwork is backed up first, so you can undo it.")
        r = self._row(body)
        ttk.Checkbutton(r, text="Start Steam again when finished", variable=self.restart_steam).pack(side="left")
        r = self._row(body)
        ttk.Button(r, text="Apply to Steam", style="Accent.TButton", command=lambda: self._todo("Apply to Steam", 4)).pack(side="left")
        ttk.Button(r, text="Restore previous artwork", command=lambda: self._todo("Restore backup", 4)).pack(side="left", padx=8)
        self.step3_status = tk.Label(body, text="", bg=CARD, fg=MUTED, anchor="w")
        self.step3_status.pack(fill="x", pady=(6, 0))

    # ----- stubs -----
    def _todo(self, what, milestone):
        messagebox.showinfo("Not built yet", "%s comes in milestone %d." % (what, milestone))


if __name__ == "__main__":
    App().mainloop()
