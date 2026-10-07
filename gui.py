#!/usr/bin/env python3
"""steamcase GUI: three steps, no terminal.  Run:  python gui.py"""
import os, queue, re, subprocess, sys, threading, time, webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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


def downloads_dir():
    """The user's Downloads folder (honours the Linux XDG setting)."""
    home = os.path.expanduser("~")
    cfg = os.path.join(home, ".config", "user-dirs.dirs")
    if os.path.exists(cfg):
        m = re.search(r'XDG_DOWNLOAD_DIR="([^"]+)"', open(cfg, errors="replace").read())
        if m:
            p = m.group(1).replace("$HOME", home)
            if os.path.isdir(p):
                return p
    return os.path.join(home, "Downloads")


class App(tk.Tk):
    def __init__(self, downloads=None, covers_dir=None):
        super().__init__()
        self.covers_dir = covers_dir or sc.default_covers_dir()
        self.cover_files = []             # covers built by the last run; step 3 applies exactly these
        self.running = False
        self.events = queue.Queue()
        self.cancel_flag = threading.Event()
        self.downloads = downloads or downloads_dir()
        self.started = time.time()
        self._seen = {}                   # path -> (size, mtime) from the last poll, to wait for a finished download
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
        self.refresh_step1()
        self.busy = False                 # step 3 (apply/restore) in progress
        self.refresh_step3()
        self._timers = [self.after(1500, self.watch_downloads), self.after(100, self.poll_events)]
        self.update_idletasks()                       # size the window to its content
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

    def destroy(self):
        self.cancel_flag.set()
        for t in getattr(self, "_timers", []):
            try:
                self.after_cancel(t)
            except tk.TclError:
                pass
        super().destroy()

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
        self.step1_status.configure(text="Page opened. Save it as userdata.json (Ctrl+S) and I'll pick it up…", fg=MUTED)

    def browse(self):
        path = filedialog.askopenfilename(title="Choose your userdata.json", initialdir=self.downloads if os.path.isdir(self.downloads) else None,
                                          filetypes=[("userdata.json", "*.json"), ("All files", "*.*")])
        if path:
            self.load_library(path, ask=True)

    def load_library(self, path, ask=False):
        """Check the file and use it. Returns True on success. With ask=True, errors pop up."""
        try:
            n = len(sc.owned_ids(path))
        except sc.SteamcaseError as e:
            if ask:
                messagebox.showerror("That file doesn't look right", str(e))
            return False
        self.library_path = path
        self.installed_only.set(False)
        self.step1_status.configure(text="Got it: %s (%d items in your library)." % (os.path.basename(path), n), fg=ACCENT)
        self.refresh_step1()
        return True

    def on_installed_only(self):
        self.refresh_step1()

    def refresh_step1(self):
        """Step 2 unlocks once we have a library file or the user chose installed games only."""
        ready = self.installed_only.get() or bool(self.library_path)
        if self.installed_only.get():
            self.step1_status.configure(text="Using installed games only.", fg=ACCENT)
        elif not self.library_path:
            self.step1_status.configure(text="Waiting for userdata.json…", fg=MUTED)
        self._set_state(self.step2, ready and not self.running)
        self.btn_cancel.configure(state="normal" if self.running else "disabled")

    def watch_downloads(self):
        """Every 1.5 s: look for a new, finished, valid userdata*.json in Downloads."""
        try:
            if not self.library_path and os.path.isdir(self.downloads):
                for fn in os.listdir(self.downloads):
                    if not (fn.lower().startswith("userdata") and fn.lower().endswith(".json")):
                        continue
                    p = os.path.join(self.downloads, fn)
                    st = os.stat(p)
                    if st.st_mtime < self.started:
                        continue
                    sig = (st.st_size, st.st_mtime)
                    if self._seen.get(p) == sig and self.load_library(p):      # unchanged since last poll = finished
                        break
                    self._seen[p] = sig
        except OSError:
            pass
        self._timers[0] = self.after(1500, self.watch_downloads)

    # ----- step 2 -----
    def _build_step2(self, body):
        self._note(body, "Downloads each game's artwork from Steam and builds the covers on your computer.")
        r = self._row(body)
        ttk.Checkbutton(r, text="Skip blurry auto-art", variable=self.skip_auto).pack(side="left")
        info = tk.Label(r, text="?", bg=ACCENT, fg="#0b141d", width=2, cursor="question_arrow", font=("TkDefaultFont", 10, "bold"))
        info.pack(side="left", padx=6)
        Tooltip(info, sc.AUTO_ART_HELP)
        r = self._row(body)
        self.btn_make = ttk.Button(r, text="Make covers", style="Accent.TButton", command=self.start_make)
        self.btn_make.pack(side="left")
        self.btn_cancel = ttk.Button(r, text="Cancel", command=self.cancel_make, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.btn_folder = ttk.Button(r, text="Open covers folder", command=self.open_covers_folder)
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.pack(fill="x", pady=(8, 2))
        self.step2_status = tk.Label(body, text="Not started.", bg=CARD, fg=MUTED, anchor="w")
        self.step2_status.pack(fill="x")

    def start_make(self):
        if self.running:
            return
        lib = None if self.installed_only.get() else self.library_path
        self.running = True
        self.cancel_flag.clear()
        self.cover_files = []
        self.progress.configure(value=0, maximum=1)
        self.step2_status.configure(text="Looking up your games on Steam…", fg=MUTED)
        self.btn_folder.pack_forget()
        self._set_state(self.step1, False)
        self.refresh_step1()
        self.refresh_step3()
        skip = self.skip_auto.get()
        threading.Thread(target=self._worker, args=(lib, skip), daemon=True).start()

    def _worker(self, lib, skip):
        """Runs off the UI thread; talks to the UI only through self.events."""
        try:
            steam = sc.steam_dir()
            games = sc.load_games(steam, lib)
            if not games:
                raise sc.SteamcaseError("No games found. Install a game first, or load your userdata.json.")
            res = sc.make_covers(games, self.covers_dir, skip_auto_art=skip,
                                 progress=lambda *a: self.events.put(("progress",) + a),
                                 cancelled=self.cancel_flag.is_set)
            self.events.put(("done", res))
        except sc.SteamcaseError as e:
            self.events.put(("error", str(e)))
        except Exception as e:                      # never leave the UI stuck in "running"
            self.events.put(("error", "Unexpected problem: %s" % e))

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    _, done, total, appid, name, status = ev
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.step2_status.configure(text="%d of %d · %s" % (done, total, name), fg=MUTED)
                elif ev[0] == "done":
                    self.finish_make(ev[1])
                elif ev[0] == "step3_status":
                    self.step3_status.configure(text=ev[1], fg=MUTED)
                elif ev[0] == "step3_done":
                    self.busy = False
                    self.step3_status.configure(text=ev[1], fg=ACCENT)
                    self.refresh_step3()
                elif ev[0] == "step3_error":
                    self.busy = False
                    self.step3_status.configure(text=ev[1], fg="#ff7b72")
                    self.refresh_step3()
                    messagebox.showerror("Could not finish", ev[1])
                elif ev[0] == "error":
                    self.running = False
                    self.step2_status.configure(text=ev[1], fg="#ff7b72")
                    self._set_state(self.step1, True)
                    self.refresh_step1()
                    messagebox.showerror("Could not make covers", ev[1])
        except queue.Empty:
            pass
        self._timers[1] = self.after(100, self.poll_events)

    def finish_make(self, res):
        self.running = False
        self.cover_files = res["files"]
        n, miss = res["ok"], len(res["missing"])
        text = "%s%d covers ready." % ("Stopped. " if res["cancelled"] else "Done. ", n)
        if miss:
            text += " %d %s no portrait on Steam." % (miss, "game has" if miss == 1 else "games have")
        self.step2_status.configure(text=text, fg=ACCENT if n else MUTED)
        self._set_state(self.step1, True)
        self.refresh_step1()
        if n:
            self.btn_folder.pack(side="left")
        self.refresh_step3()

    def cancel_make(self):
        self.cancel_flag.set()
        self.step2_status.configure(text="Stopping…", fg=MUTED)

    def open_covers_folder(self):
        os.makedirs(self.covers_dir, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.covers_dir)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.covers_dir])

    # ----- step 3 -----
    def _build_step3(self, body):
        self._note(body, "Warning: this step closes Steam automatically (any running game or download stops). "
                         "Your current artwork is backed up first, so you can undo it.")
        r = self._row(body)
        self.chk_restart = ttk.Checkbutton(r, text="Start Steam again when finished", variable=self.restart_steam)
        self.chk_restart.pack(side="left")
        r = self._row(body)
        self.btn_apply = ttk.Button(r, text="Apply to Steam", style="Accent.TButton", command=lambda: self.confirm_and_run("apply"))
        self.btn_apply.pack(side="left")
        self.btn_restore = ttk.Button(r, text="Restore previous artwork", command=lambda: self.confirm_and_run("restore"))
        self.btn_restore.pack(side="left", padx=8)
        self.step3_status = tk.Label(body, text="", bg=CARD, fg=MUTED, anchor="w", justify="left", wraplength=640)
        self.step3_status.pack(fill="x", pady=(6, 0))

    def has_backup(self):
        try:
            return bool(sc.list_backups(sc.steam_dir()))
        except sc.SteamcaseError:
            return False

    def refresh_step3(self):
        idle = not self.running and not self.busy
        can_apply = idle and bool(self.cover_files)
        self.btn_apply.configure(state="normal" if can_apply else "disabled")
        self.btn_restore.configure(state="normal" if idle and self.has_backup() else "disabled")
        self.chk_restart.configure(state="normal" if idle else "disabled")

    def confirm_and_run(self, mode):
        if self.busy or self.running:
            return
        steam_on = sc.steam_running()
        if mode == "apply":
            title, ok_text = "Add covers to Steam", "%d covers will be added to Steam." % len(self.cover_files)
            undo = "Your current artwork is backed up first, and you can undo this with “Restore previous artwork”."
        else:
            title, ok_text = "Restore previous artwork", "Your artwork from before the last Apply will be put back."
            undo = "The covers added by that Apply are removed."
        if steam_on:
            msg = ("%s\n\nSteam will be CLOSED automatically. Any running game stops and downloads pause. "
                   "Save your game first.\n\n%s\n\nContinue?") % (ok_text, undo)
        else:
            msg = "%s\n\n%s\n\nContinue?" % (ok_text, undo)
        if not messagebox.askokcancel(title, msg, icon="warning" if steam_on else "question"):
            return
        self.busy = True
        self.refresh_step3()
        self.step3_status.configure(text="Closing Steam…" if steam_on else "Working…", fg=MUTED)
        threading.Thread(target=self._step3_worker, args=(mode, self.restart_steam.get()), daemon=True).start()

    def _step3_worker(self, mode, restart):
        say = lambda t: self.events.put(("step3_status", t))
        try:
            steam = sc.steam_dir()
            if sc.steam_running():
                say("Closing Steam…")
                if not sc.close_steam(steam):
                    raise sc.SteamcaseError("Steam did not close in time. Close it yourself (Steam menu, then Exit) and press the button again.")
            if mode == "apply":
                say("Backing up and copying covers…")
                r = sc.apply_covers(steam, self.covers_dir, files=self.cover_files)
                text = "Done. %d covers added to account %s (%d replaced older art). Backup saved in: %s" % (
                    r["applied"], r["account"], r["replaced"], r["backup"])
            else:
                backups = sc.list_backups(steam)
                if not backups:
                    raise sc.SteamcaseError("No backup found.")
                n = sc.restore_backup(steam, backups[0])
                text = "Restored your previous artwork (%d files)." % n
            if restart:
                say("Starting Steam…")
                try:
                    sc.start_steam(steam)
                    text += " Steam is starting."
                except sc.SteamcaseError as e:
                    text += " Could not start Steam (%s). Please open it yourself." % e
            else:
                text += " Start Steam to see the change."
            self.events.put(("step3_done", text))
        except sc.SteamcaseError as e:
            self.events.put(("step3_error", str(e)))
        except Exception as e:
            self.events.put(("step3_error", "Unexpected problem: %s" % e))


if __name__ == "__main__":
    App().mainloop()
