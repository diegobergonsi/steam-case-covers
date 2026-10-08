#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""steamcase GUI: three steps, no terminal.  Run:  python gui.py"""
import os, queue, re, shutil, subprocess, sys, threading, time, webbrowser
import tkinter as tk
from tkinter import filedialog
import tkinter.font as tkfont

import steamcase as sc
from widgets import (BG, CARD, FG, MUTED, FAINT, ACCENT, RED, Card, StepBadge, RoundedButton, Switch, Bar, InfoBadge, ScrollFrame, Messages, px, set_scale)


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


SAVE_KEY = "Cmd+S" if sys.platform == "darwin" else "Ctrl+S"
messagebox = Messages()                      # themed dialogs; App sets the parent window


def pick_file(title, initialdir):
    """File chooser. On Linux the plain Tk dialog looks very dated, so use the desktop's own (KDE or GNOME) when present."""
    start = (initialdir if initialdir and os.path.isdir(initialdir) else os.path.expanduser("~")).rstrip("/") + "/"
    if sys.platform.startswith("linux"):
        if shutil.which("kdialog"):
            cmds = [["kdialog", "--title", title, "--getopenfilename", start, "*.json|JSON files (*.json)\n*|All files"]]
        elif shutil.which("zenity"):
            cmds = [["zenity", "--file-selection", "--title=" + title, "--filename=" + start, "--file-filter=JSON files | *.json", "--file-filter=All files | *"]]
        else:
            cmds = []
        for cmd in cmds:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
            except OSError:
                break
            if r.returncode == 0:
                return r.stdout.strip()
            if r.returncode == 1:                    # the user pressed Cancel
                return ""
    return filedialog.askopenfilename(title=title, initialdir=start, filetypes=[("userdata.json", "*.json"), ("All files", "*.*")])


class App(tk.Tk):
    def __init__(self, downloads=None, covers_dir=None, screen_h=None):
        super().__init__()
        self.covers_dir = covers_dir or sc.default_covers_dir()
        self.cover_files = []             # covers built by the last run; step 3 applies exactly these
        self.running = False
        self.busy = False                 # step 3 (apply/restore) in progress
        self.applied = False              # covers were added to Steam in this session
        self.events = queue.Queue()
        self.cancel_flag = threading.Event()
        self.downloads = downloads or downloads_dir()
        self.started = time.time()
        self._reported = {}               # path -> signature of the files we already complained about
        self._last_error = ""
        self._seen = {}                   # path -> (size, mtime) from the last poll, to wait for a finished download
        self.title("Steam Case Covers")
        messagebox.parent = self
        try:                                           # window / taskbar icon
            self._icon = tk.PhotoImage(master=self, file=os.path.join(sc.HERE, "assets", "icon.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        self.configure(bg=BG)
        self._style()
        set_scale(self)

        self.library_path = None          # chosen userdata.json
        self.installed_only = tk.BooleanVar(value=False)
        self.skip_auto = tk.BooleanVar(value=False)
        self.restart_steam = tk.BooleanVar(value=True)

        self.scroller = ScrollFrame(self)
        self.scroller.pack(fill="both", expand=True)
        self.holder = self.scroller.inner
        head = tk.Frame(self.holder, bg=BG)
        head.pack(fill="x", padx=px(28), pady=(px(24), px(14)))
        if getattr(self, "_icon", None):
            self._icon_small = self._icon.subsample(4 if px(1) == 1 else 3)
            tk.Label(head, image=self._icon_small, bg=BG).pack(side="left", padx=(0, px(16)))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="Steam Case Covers", bg=BG, fg=FG, font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        tk.Label(titles, text="Put every game in your library in a physical case.", bg=BG, fg=MUTED).pack(anchor="w")
        self.btn_update = RoundedButton(head, "Check for updates", self.check_update, bg=BG)
        self.btn_update.pack(side="right")

        self.step1 = self._card("1", "Get your game list")
        self.step2 = self._card("2", "Make the covers")
        self.step3 = self._card("3", "Add them to Steam")
        self._build_step1(self.step1)
        self._build_step2(self.step2)
        self._build_step3(self.step3)
        self.refresh_step1()
        self.refresh_step3()
        self._timers = [self.after(1500, self.watch_downloads), self.after(100, self.poll_events)]
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_idletasks()                       # fit the content, but never taller than the screen (Steam Deck: 800 px)
        want_w, want_h = self.holder.winfo_reqwidth(), self.holder.winfo_reqheight()
        room = (screen_h or self.winfo_screenheight()) - px(110)               # title bar + taskbar
        self.geometry("%dx%d" % (want_w + px(14), min(want_h, max(room, px(420)))))
        self.minsize(want_w, px(380))

    def on_close(self):
        if self.busy:
            messagebox.showinfo("Please wait", "Steam's artwork is being changed. Closing now could leave it half-done. "
                                               "Wait a few seconds, then close the window.")
            return
        self.destroy()

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
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(size=11)          # a little larger than the 10 pt default

    def _card(self, num, title):
        card = Card(self.holder)
        card.pack(fill="x", padx=px(28), pady=px(7))
        head = tk.Frame(card.body, bg=CARD)
        head.pack(fill="x")
        badge = StepBadge(head, num)
        badge.pack(side="left")
        title_lbl = tk.Label(head, text=title, bg=CARD, fg=FG, font=("TkDefaultFont", 14, "bold"))
        title_lbl.pack(side="left", padx=px(12))
        body = tk.Frame(card.body, bg=CARD)
        body.pack(fill="x", pady=(px(12), 0))
        body.badge, body.title_lbl = badge, title_lbl
        return body

    def _row(self, parent, pady=px(4)):
        r = tk.Frame(parent, bg=CARD)
        r.pack(fill="x", pady=pady)
        return r

    def _note(self, parent, text):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, justify="left", wraplength=px(620), anchor="w").pack(fill="x", pady=(0, px(6)))

    def _set_state(self, body, enabled):
        st = "normal" if enabled else "disabled"

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (RoundedButton, Switch)):
                    c.configure(state=st)
                walk(c)
        walk(body)

    def update_steps(self):
        """Badges and titles show where you are: locked, active or done."""
        ready = self.installed_only.get() or bool(self.library_path)
        s1 = "done" if ready else "active"
        s2 = "locked" if not ready else "done" if self.cover_files else "active"
        s3 = "done" if self.cover_files and self.applied else "active" if (self.cover_files or self.has_backup()) else "locked"   # Restore alone also unlocks it
        for body, status in ((self.step1, s1), (self.step2, s2), (self.step3, s3)):
            body.badge.set(status)
            body.title_lbl.configure(fg=FAINT if status == "locked" else FG)

    # ----- step 1 -----
    def _build_step1(self, body):
        self._note(body, "Steam keeps your full game list on a web page. Click the button and log in to Steam if it asks. "
                         "You'll land on a page of plain text: press %s and save it (keep the name userdata.json). "
                         "This app will notice the file by itself." % SAVE_KEY)
        r = self._row(body)
        RoundedButton(r, "Download your userdata.json", self.open_download_page, primary=True).pack(side="left")
        RoundedButton(r, "Browse…", self.browse).pack(side="left", padx=px(10))
        RoundedButton(r, "Copy link", self.copy_link).pack(side="left")
        r = self._row(body)
        self.sw_installed = Switch(r, "Only my installed games (no file needed)", self.installed_only, self.on_installed_only)
        self.sw_installed.pack(side="left")
        self.step1_status = tk.Label(body, text="Waiting for userdata.json…", bg=CARD, fg=MUTED, anchor="w", justify="left", wraplength=px(620))
        self.step1_status.pack(fill="x", pady=(px(8), 0))

    def open_download_page(self):
        try:
            webbrowser.open(sc.library_login_url())
        except Exception:
            pass
        # webbrowser cannot tell us whether a browser really opened, so always show the way out
        self.step1_status.configure(text="Opening your browser… Log in to Steam if it asks. You'll then see a page of plain text: save it as userdata.json (%s) and I'll pick it up. "
                                         "Nothing opened? Click “Copy link” and paste it into your browser." % SAVE_KEY, fg=MUTED)

    def copy_link(self):
        self.clipboard_clear()
        self.clipboard_append(sc.library_login_url())
        self.update()                               # keeps the text on the clipboard on some systems
        self.step1_status.configure(text="Link copied. Paste it into your browser, log in if asked, then save the page as userdata.json (%s)." % SAVE_KEY, fg=ACCENT)

    def browse(self):
        path = pick_file("Choose your userdata.json", self.downloads)
        if path:
            self.load_library(path, ask=True)

    def load_library(self, path, ask=False):
        """Check the file and use it. Returns True on success. With ask=True, errors pop up."""
        try:
            n = len(sc.owned_ids(path))
        except sc.SteamcaseError as e:
            self._last_error = str(e)
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
        self.update_steps()

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
                    if self._seen.get(p) == sig:                                # unchanged since last poll = finished
                        if self.load_library(p):
                            break
                        if self._reported.get(p) != sig and self._last_error:      # say why, once (e.g. saved while logged out)
                            self._reported[p] = sig
                            self.step1_status.configure(text="%s: %s" % (fn, self._last_error), fg=RED)
                    self._seen[p] = sig
        except OSError:
            pass
        self._timers[0] = self.after(1500, self.watch_downloads)

    # ----- step 2 -----
    def _build_step2(self, body):
        self._note(body, "Downloads each game's artwork from Steam and builds the covers on your computer.")
        r = self._row(body)
        self.sw_skip = Switch(r, "Skip blurry auto-art", self.skip_auto)
        self.sw_skip.pack(side="left")
        InfoBadge(r, sc.AUTO_ART_HELP).pack(side="left", padx=px(6))
        r = self._row(body, pady=px(6))
        self.btn_make = RoundedButton(r, "Make covers", self.start_make, primary=True)
        self.btn_make.pack(side="left")
        self.btn_cancel = RoundedButton(r, "Cancel", self.cancel_make, state="disabled")
        self.btn_cancel.pack(side="left", padx=px(10))
        self.btn_folder = RoundedButton(r, "Open covers folder", self.open_covers_folder)
        self.progress = Bar(body)
        self.progress.pack(fill="x", pady=(px(10), px(6)))
        self.step2_status = tk.Label(body, text="Not started.", bg=CARD, fg=MUTED, anchor="w", justify="left", wraplength=px(620))
        self.step2_status.pack(fill="x")

    def start_make(self):
        if self.running:
            return
        lib = None if self.installed_only.get() else self.library_path
        self.running = True
        self.cancel_flag.clear()
        self.cover_files = []
        self.applied = False
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

    def check_update(self):
        """Asks GitHub whether a newer release exists. Only on click; nothing is downloaded or installed."""
        self.btn_update.configure(state="disabled")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        try:
            self.events.put(("update", sc.check_for_update()))
        except sc.SteamcaseError as e:
            self.events.put(("update_error", str(e)))
        except Exception as e:
            self.events.put(("update_error", "Unexpected problem: %s" % e))

    def show_update(self, r):
        self.btn_update.configure(state="normal")
        if r["newer"] is False:
            messagebox.showinfo("No update needed", "You have the latest version (%s)." % r["current"])
            return
        if r["newer"]:
            text = "A newer version is available: %s (you have %s).\n\nOpen the download page in your browser? Nothing is installed automatically." % (r["latest"], r["current"])
        else:
            text = "The latest version is %s. This copy has no version number (it was not installed from a release), so I cannot compare.\n\nOpen the download page?" % r["latest"]
        if messagebox.askokcancel("Update available", text, ok="Open page", cancel="Not now"):
            try:
                webbrowser.open(r["url"])
            except Exception:
                pass

    def poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    _, done, total, appid, name, status = ev
                    self.progress.configure(maximum=max(total, 1), value=done)
                    self.step2_status.configure(text="%d of %d · %s" % (done, total, name if len(name) <= 60 else name[:57] + "…"), fg=MUTED)
                elif ev[0] == "done":
                    self.finish_make(ev[1])
                elif ev[0] == "update":
                    self.show_update(ev[1])
                elif ev[0] == "update_error":
                    self.btn_update.configure(state="normal")
                    messagebox.showerror("Could not check for updates", ev[1])
                elif ev[0] == "reset_scan":
                    self.on_reset_scan(ev[1], ev[2])
                elif ev[0] == "step3_status":
                    self.say3(ev[1], MUTED)
                elif ev[0] == "step3_done":
                    self.busy = False
                    self.applied = ev[2] == "apply" if len(ev) > 2 else self.applied
                    self.say3(ev[1], ACCENT)
                    self.refresh_step3()
                elif ev[0] == "step3_error":
                    self.busy = False
                    self.say3(ev[1], RED)
                    self.refresh_step3()
                    messagebox.showerror("Could not finish", ev[1])
                elif ev[0] == "error":
                    self.running = False
                    self.step2_status.configure(text=ev[1], fg=RED)
                    self._set_state(self.step1, True)
                    self.refresh_step1()
                    messagebox.showerror("Could not make covers", ev[1])
        except queue.Empty:
            pass
        self._timers[1] = self.after(100, self.poll_events)

    def finish_make(self, res):
        self.running = False
        self.cover_files = res["files"]
        n, miss, bad = res["ok"], len(res["missing"]), len(res["failed"])
        text = "%s%d covers ready." % ("Stopped. " if res["cancelled"] else "Done. ", n)
        if miss:
            text += " %d %s no portrait on Steam." % (miss, "game has" if miss == 1 else "games have")
        skipped = res.get("not_games", 0) + res.get("unlisted", 0)
        if skipped:
            text += " Skipped %d items that aren't games you can play (DLC, soundtracks, tools, and apps Steam no longer lists)." % skipped
        if bad:
            text += " %d could not be downloaded (connection problem?): click “Make covers” again to retry only those." % bad
        self.step2_status.configure(text=text, fg=ACCENT if n and not bad else MUTED if not n else FG)
        self._set_state(self.step1, True)
        self.refresh_step1()
        if n:
            self.btn_folder.pack(side="left", padx=px(10))
        self.refresh_step3()

    def cancel_make(self):
        self.cancel_flag.set()
        self.step2_status.configure(text="Stopping…", fg=MUTED)

    def open_covers_folder(self):
        folder = os.path.abspath(self.covers_dir)
        os.makedirs(folder, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(folder)
        else:
            subprocess.Popen([sc._tool("open" if sys.platform == "darwin" else "xdg-open"), folder])

    # ----- step 3 -----
    def _build_step3(self, body):
        self._note(body, "Warning: this step closes Steam automatically (any running game or download stops). "
                         "Your current artwork is backed up first, so you can undo it.")
        r = self._row(body)
        self.chk_restart = Switch(r, "Start Steam again when finished", self.restart_steam)
        self.chk_restart.pack(side="left")
        r = self._row(body, pady=px(6))
        self.btn_apply = RoundedButton(r, "Apply to Steam", lambda: self.confirm_and_run("apply"), primary=True)
        self.btn_apply.pack(side="left")
        self.btn_restore = RoundedButton(r, "Restore previous artwork", lambda: self.confirm_and_run("restore"))
        self.btn_restore.pack(side="left", padx=px(10))
        r2 = self._row(body, pady=px(2))
        self.btn_reset = RoundedButton(r2, "Reset to Steam's default art", self.start_reset)
        self.btn_reset.pack(side="left")
        self.step3_status = tk.Label(body, text="", bg=CARD, fg=MUTED, anchor="w", justify="left", wraplength=px(620))

    def say3(self, text, fg=MUTED):
        """Step 3 message; the line only takes space while it has something to say."""
        self.step3_status.configure(text=text, fg=fg)
        if text and not self.step3_status.winfo_ismapped():
            self.step3_status.pack(fill="x", pady=(px(8), 0))
        elif not text:
            self.step3_status.pack_forget()

    def has_grid_art(self):
        """Cheap check (no image decoding): is there any <appid>p.png in Steam's grid folder?"""
        try:
            grid = sc.grid_dir(sc.steam_dir())
            return os.path.isdir(grid) and any(sc._COVER_NAME.match(n) for n in os.listdir(grid))
        except sc.SteamcaseError:
            return False

    def start_reset(self):
        """Step 1 of 2: look for our covers (a few seconds, in the background). Step 2 asks, then removes them."""
        if self.busy or self.running:
            return
        self.busy = True
        self.refresh_step3()
        self.say3("Looking for covers made by this app… (a few seconds)")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            steam = sc.steam_dir()
            names = sc.find_our_covers(steam, progress=lambda i, n: self.events.put(("step3_status", "Checking Steam's artwork… %d of %d" % (i, n))),
                                       cancelled=self.cancel_flag.is_set)
            who = sc.account_label(steam, sc.pick_account(steam))
            self.events.put(("reset_scan", names, who))
        except sc.SteamcaseError as e:
            self.events.put(("step3_error", str(e)))
        except Exception as e:
            self.events.put(("step3_error", "Unexpected problem: %s" % e))

    def on_reset_scan(self, names, who):
        if not names:
            self.busy = False
            self.say3("No covers made by this app were found in “%s”. Nothing to reset." % who)
            self.refresh_step3()
            return
        steam_on = sc.steam_running()
        paras = [("%d covers made by this app will be removed from the Steam account “%s”. Steam goes back to its own default art for them." % (len(names), who), "main"),
                 ("Art you set yourself is not touched. A backup is kept, so “Restore previous artwork” brings the covers back.", "muted")]
        if steam_on:
            paras.append(("Steam will be closed automatically. Any running game stops and downloads pause. Save your game first.", "warn"))
        if not messagebox.askokcancel("Reset to Steam's default art", paras, icon="warning" if steam_on else "question",
                                      ok="Close Steam and reset" if steam_on else "Reset"):
            self.busy = False
            self.say3("")
            self.refresh_step3()
            return
        self.say3("Closing Steam…" if steam_on else "Working…")
        threading.Thread(target=self._step3_worker, args=("reset", self.restart_steam.get(), names), daemon=True).start()

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
        backup = self.has_backup()
        self.btn_reset.configure(state="normal" if idle and self.has_grid_art() else "disabled")
        self.chk_restart.configure(state="normal" if idle and (can_apply or backup) else "disabled")
        # say why Restore is greyed out, and clear that note once it no longer applies
        hint = "Nothing to undo yet: “Restore previous artwork” works once you have used “Apply to Steam” in this app."
        if idle and not can_apply and not backup and not self.step3_status.cget("text"):
            self.say3(hint, FAINT)
        elif self.step3_status.cget("text") == hint and (can_apply or backup):
            self.say3("")
        self.update_steps()

    def confirm_and_run(self, mode):
        if self.busy or self.running:
            return
        steam_on = sc.steam_running()
        try:
            who = sc.account_label(sc.steam_dir(), sc.pick_account(sc.steam_dir()))
        except sc.SteamcaseError:
            who = "your Steam account"
        if mode == "apply":
            title = "Add covers to Steam"
            paras = [("%d covers will be added to the Steam account “%s”." % (len(self.cover_files), who), "main"),
                     ("Your current artwork is backed up first. You can undo this with “Restore previous artwork”.", "muted")]
            go = "Close Steam and add them" if steam_on else "Add them"
        else:
            title = "Restore previous artwork"
            paras = [("Your artwork from before the last Apply will be put back on the Steam account “%s”." % who, "main"),
                     ("The covers added by that Apply are removed.", "muted")]
            go = "Close Steam and restore" if steam_on else "Restore"
        if steam_on:
            paras.append(("Steam will be closed automatically. Any running game stops and downloads pause. Save your game first.", "warn"))
        if not messagebox.askokcancel(title, paras, icon="warning" if steam_on else "question", ok=go):
            return
        self.busy = True
        self.refresh_step3()
        self.say3("Closing Steam…" if steam_on else "Working…", MUTED)
        threading.Thread(target=self._step3_worker, args=(mode, self.restart_steam.get()), daemon=True).start()

    def _step3_worker(self, mode, restart, names=None):
        say = lambda t: self.events.put(("step3_status", t))
        try:
            steam = sc.steam_dir()
            if sc.steam_running():
                say("Closing Steam…")
                if not sc.close_steam(steam):
                    raise sc.SteamcaseError("Steam did not close in time. Close it yourself (Steam menu, then Exit) and press the button again."
                                            + (" If macOS asked for permission, allow it first and then press the button again." if sys.platform == "darwin" else ""))
            if mode == "apply":
                say("Backing up and copying covers…")
                r = sc.apply_covers(steam, self.covers_dir, files=self.cover_files)
                if r["applied"]:
                    text = "Done. %d covers added to the Steam account “%s” (%d replaced older art, %d already up to date). Backup saved in: %s" % (
                        r["applied"], r["account_name"], r["replaced"], r["unchanged"], r["backup"])
                    if r["jpg_moved"]:
                        text += " Art you had set by hand in Steam (%d games) was moved into the backup; Restore brings it back." % r["jpg_moved"]
                else:
                    text = "Nothing to change: all %d covers were already in the Steam account “%s”." % (r["unchanged"], r["account_name"])
            elif mode == "reset":
                say("Removing our covers…")
                r = sc.reset_to_default(steam, names=names)
                text = "Done. %d covers removed from the Steam account “%s”: Steam shows its own default art again. Press “Restore previous artwork” to bring them back." % (
                    r["removed"], r["account_name"])
            else:
                backups = sc.list_backups(steam)
                if not backups:
                    raise sc.SteamcaseError("No backup found.")
                n = sc.restore_backup(steam, backups[0])
                left = len(sc.list_backups(steam))
                text = "Restored your previous artwork (%d files)." % n
                if left:
                    text += " %d older backup%s left: press Restore again to go one step further back." % (left, "" if left == 1 else "s")
            if restart:
                say("Starting Steam…")
                try:
                    sc.start_steam(steam)
                    text += " Steam is starting."
                except sc.SteamcaseError as e:
                    text += " Could not start Steam (%s). Please open it yourself." % e
            else:
                text += " Start Steam to see the change."
            self.events.put(("step3_done", text, mode))
        except sc.SteamcaseError as e:
            self.events.put(("step3_error", str(e)))
        except Exception as e:
            self.events.put(("step3_error", "Unexpected problem: %s" % e))


def restore_child_env():
    """Packaged Linux app: PyInstaller points LD_LIBRARY_PATH at its bundled libraries (OpenSSL...).
    Programs we launch (xdg-open, kde-open, flatpak, Steam) would load those and crash, so undo it."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
        if orig is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = orig


def enable_dpi_awareness():
    """Windows: without this, tkinter windows look blurry on high-DPI screens."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def selftest():
    """Headless check used by the build: Pillow, tkinter and the bundled frame all work. Exit code 0 = fine."""
    import tempfile
    from PIL import Image
    try:
        assert os.path.exists(sc.FRAME), "frame image missing: %s" % sc.FRAME
        assert os.path.exists(os.path.join(sc.HERE, "assets", "icon.png")), "icon missing"
        restore_child_env()
        assert sc._ssl_context().cert_store_stats()["x509_ca"] > 0, "no trusted certificates loaded: secure connections to Steam would fail"
        if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
            assert getattr(sys, "_MEIPASS", "\0") not in os.environ.get("LD_LIBRARY_PATH", ""), "child programs would inherit the bundled libraries"
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "p.png"), os.path.join(d, "c.png")
            Image.new("RGB", (600, 900), (200, 60, 60)).save(src)
            sc.build_cover(src, out, Image.open(sc.FRAME).convert("RGBA"))
            im = Image.open(out)
            assert im.size == (600, 900), "bad size %s" % (im.size,)
            assert im.getpixel((300, 500))[:3] == (200, 60, 60), "art window not filled"
        print("selftest ok")
        return 0
    except Exception as e:
        print("selftest FAILED:", e)
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--version" in sys.argv:
        print("steam-case-covers %s" % sc.APP_VERSION)
        sys.exit(0)
    if "--check-network" in sys.argv:                     # for bug reports: does this computer reach Steam?
        ok, msg = sc.check_network()
        print(("network ok: " if ok else "network FAILED: ") + msg)
        sys.exit(0 if ok else 1)
    restore_child_env()
    enable_dpi_awareness()
    App().mainloop()
