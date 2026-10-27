#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""A "clumsy robot user" for the window. It needs a display (on a server: `xvfb-run -a python tests/fuzz_gui.py`).

It builds a fake Steam folder and fake Steam servers, then performs random actions (clicks, key presses, toggles, cancelling at a
random moment, deleting folders mid-run, flipping the network and Steam's state, picking junk files, resizing...). After every
action it checks that nothing crashed, nothing is stuck, the buttons match the state, and the folders only hold what they should.

    python tests/fuzz_gui.py [--seeds N] [--steps N] [--sandbox]

Exit code 0 = every run was clean."""
import argparse, faulthandler, io, json, os, random, re, shutil, sys, tempfile, threading, time, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui, widgets, completion, steamcase as sc
from PIL import Image

LAUNCHED = []                        # programs the window tried to start; a fuzz run never starts any (no file manager, no browser)


class _NoProcess:
    """Stands in for subprocess.Popen: records the command and pretends it finished at once."""
    returncode = 0

    def __init__(self, args, *a, **k):
        LAUNCHED.append(args)
        self.args = args

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def communicate(self, *a, **k):
        return None, None

    def poll(self):
        return 0

    def wait(self, *a, **k):
        return 0

    def kill(self):
        pass


gui.App.open_covers_folder = lambda self: LAUNCHED.append(("open covers folder", self.covers_dir))
gui.webbrowser.open = lambda url, *a, **k: LAUNCHED.append(("browser", url)) or True
gui.subprocess.Popen = _NoProcess        # global for the whole run: it is the same subprocess module, so subprocess.run starts this stand-in too


def games_page(rows):
    """A saved games page in the structure of tests/fixtures/games_page.html: rows is [(appid, unlocked, total or None)]."""
    out = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>Games</title></head><body><div class="list">']
    for appid, done, total in rows:
        out.append('<div class="row"><a href="https://store.steampowered.com/app/%d" class="name">G%d</a>' % (appid, appid))
        if total is not None:
            out.append('<a class="ach" href="https://steamcommunity.com/id/playerone/achievements/%d">ACHIEVEMENTS</a><span class="cnt">%d/%d</span>'
                       % (appid, done, total))
        out.append("</div>")
    return "\n".join(out + ["</div></body></html>"])

NAMES = {101: "Plain Game", 102: "Gäme 🎮 ✓", 103: "نص عربي ‮ RTL", 104: "X" * 300, 105: "../../etc/passwd",
         106: "Tom's \"Quoted\" & <Tagged>", 107: "日本語のゲーム"}


def run_one(seed, steps, sandbox):
    rnd = random.Random(seed)
    base = tempfile.mkdtemp(prefix="fuzz_gui_")
    errors, notes = [], []
    threading.excepthook = lambda a: errors.append(("thread", "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))[-400:]))
    steam = os.path.join(base, "steam")
    grid = os.path.join(steam, "userdata", "111", "config", "grid")
    cfg = os.path.dirname(grid)

    def build_steam():
        shutil.rmtree(steam, ignore_errors=True)
        os.makedirs(os.path.join(steam, "steamapps"))
        os.makedirs(grid)
        os.makedirs(os.path.join(steam, "config"))
        for i, n in NAMES.items():
            with open(os.path.join(steam, "steamapps", "appmanifest_%d.acf" % i), "w", encoding="utf-8") as f:
                f.write('"AppState"\n{\n\t"appid"\t\t"%d"\n\t"name"\t\t"%s"\n}\n' % (i, n.replace('"', "'")))
        with open(os.path.join(grid, "101p.png"), "wb") as f:
            f.write(b"USER'S OWN ART")
    build_steam()

    buf = io.BytesIO()
    Image.linear_gradient("L").resize((600, 900)).convert("RGB").save(buf, "PNG")
    art = buf.getvalue()
    net = {"mode": "ok"}

    def fake_get(url, tries=3):
        if net["mode"] == "fail":
            raise OSError("network down")
        if net["mode"] == "html":
            return b"<html>login to wifi</html>"
        if net["mode"] == "slow":
            time.sleep(0.05)
        return art

    def fake_store(ids, log=None, cancelled=None, errors=None):
        if net["mode"] == "fail":
            return {}
        return {i: {"type": 0, "name": NAMES.get(i, "G%d" % i), "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}} for i in ids}

    state = {"running": False, "closes": True}
    answers = {"ok": True}
    picks = {"file": ""}
    sandbox = sandbox and hasattr(sc, "IN_SANDBOX")      # sandbox mode only exists in builds that have it
    if sandbox:
        sc.IN_SANDBOX = True
    sc.http_get, sc.store_items, sc.steam_dir = fake_get, fake_store, (lambda *a: steam)
    sc.steam_running = lambda: state["running"] and not sandbox

    def fake_close(s, timeout=60):
        if state["closes"]:
            state["running"] = False
        return state["closes"]
    sc.close_steam, sc.start_steam = fake_close, (lambda s: None)
    gui.messagebox.askokcancel = lambda t, m, **k: answers["ok"]
    gui.messagebox.choose = lambda t, m, buttons, icon="question": rnd.choice([b[1] for b in buttons]) if answers["ok"] else None
    gui.messagebox.showerror = lambda t, m: notes.append("popup:" + m[:60])
    gui.messagebox.showinfo = lambda t, m: None
    gui.pick_file = lambda title, initialdir, *a, **k: picks["file"]

    junk = os.path.join(base, "junk")
    os.makedirs(junk)
    open(os.path.join(junk, "empty.json"), "w").close()
    open(os.path.join(junk, "photo.json"), "wb").write(art)
    open(os.path.join(junk, "text.json"), "w").write("hello")
    json.dump({"rgOwnedApps": [101, 102, 103, 999999]}, open(os.path.join(junk, "lib.json"), "w"))
    json.dump({"rgOwnedApps": [], "rgOwnedPackages": []}, open(os.path.join(junk, "loggedout.json"), "w"))
    os.makedirs(os.path.join(junk, "folder.json"))
    open(os.path.join(junk, "nested.json"), "w").write("[" * 50000)
    choices = [os.path.join(junk, f) for f in os.listdir(junk)] + [os.path.join(junk, "nope.json"), ""]
    pages = os.path.join(base, "pages")
    os.makedirs(os.path.join(pages, "games_files"))           # the folder a browser saves next to the page
    ids = sorted(NAMES)
    for name, text in (("games.html", games_page([(i, rnd.choice([0, 3, 5]), 5) for i in ids])),
                       ("all100.html", games_page([(i, 7, 7) for i in ids])),
                       ("none100.html", games_page([(i, 1, 9) for i in ids] + [(999999, 2, 2)])),
                       ("noprogress.html", games_page([(i, 0, None) for i in ids])),
                       ("htmlonly.html", "<html><script>var rgRecentlyPlayedGames = [];</script></html>"),
                       ("empty.html", "")):
        with open(os.path.join(pages, name), "w", encoding="utf-8") as f:
            f.write(text)
    page_files = sorted(os.path.join(pages, f) for f in os.listdir(pages) if os.path.isfile(os.path.join(pages, f)))      # sorted: the same actions per seed on any filesystem
    page_choices = page_files + [os.path.join(pages, "games_files"), os.path.join(junk, "photo.json"), os.path.join(pages, "nope.html"), ""]

    covers = os.path.join(base, "cv")
    app = gui.App(downloads=os.path.join(base, "dl"), covers_dir=covers, screen_h=rnd.choice([700, 800, 1080]))
    os.makedirs(os.path.join(base, "dl"), exist_ok=True)
    app.update()
    app.report_callback_exception = lambda *e: errors.append(("tk", "".join(traceback.format_exception(*e))[-500:]))
    base_threads = threading.active_count()

    def settle(limit=25):
        t0 = time.time()
        while time.time() - t0 < limit:
            app.update()
            if not app.running and not app.busy and not app.page_pending:
                return True
            time.sleep(0.02)
        return False

    def all_widgets():
        out = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (widgets.RoundedButton, widgets.Switch, widgets.InfoBadge, widgets.HueSlider, widgets.ToneSlider, widgets.Swatch, widgets._Pill)):
                    out.append(c)
                walk(c)
        walk(app)
        return out

    def act_page():
        """The optional 100% block: pick a page (good, junk or none), drop one in Downloads, or change the style."""
        r = rnd.random()
        if r < .35:
            picks["file"] = rnd.choice(page_choices); app.browse_games_page(); return "browse page " + os.path.basename(picks["file"])
        if r < .75:
            app.completion_style.set(rnd.choice(["ribbon", "gold-case", "gold-border", "none"])); return "set 100% style " + app.completion_style.get()
        if r < .9:
            name = rnd.choice(["games.html", "games (1).htm", "Games.HTML"])
            if rnd.random() < .15:                    # a folder with a page's name: it must be skipped, never read
                shutil.copytree(os.path.join(pages, "games_files"), os.path.join(base, "dl", name), dirs_exist_ok=True)
                return "drop a folder named %s in Downloads" % name
            src = rnd.choice(page_files)
            dst = os.path.join(base, "dl", name)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copy(src, dst)
            return "drop a games page in Downloads: " + os.path.basename(src)
        rnd.choice([app.open_games_page, app.copy_page_link])(); return "open or copy the games page link"

    def act():
        if rnd.random() < .12:
            return act_page()
        r = rnd.random()
        if r < .05:
            net["mode"] = "slow"
            app.btn_make.invoke()
            end = time.time() + rnd.random() * .25
            while time.time() < end:
                app.update()
                time.sleep(.005)
            app.btn_cancel.invoke()
            if rnd.random() < .5:
                app.btn_make.invoke()
            return "make + cancel at a random instant"
        if r < .10:
            app.sw_installed.event_generate("<ButtonPress-1>"); app.sw_installed.event_generate("<ButtonRelease-1>", x=5, y=5); return "toggle installed"
        if r < .13:
            app.sw_skip.event_generate("<ButtonPress-1>"); app.sw_skip.event_generate("<ButtonRelease-1>", x=5, y=5); return "toggle skip"
        if r < .16:
            app.chk_restart.event_generate("<ButtonPress-1>"); app.chk_restart.event_generate("<ButtonRelease-1>", x=5, y=5); return "toggle restart"
        if r < .26:
            app.btn_make.event_generate("<ButtonPress-1>"); app.btn_make.event_generate("<ButtonRelease-1>", x=5, y=5); return "click make"
        if r < .30:
            app.btn_cancel.invoke(); return "cancel"
        if r < .36:
            answers["ok"] = rnd.random() < .8; app.btn_apply.invoke(); return "apply"
        if r < .40:
            answers["ok"] = rnd.random() < .8; app.btn_reset.invoke(); return "reset to default art"
        if r < .43:
            answers["ok"] = rnd.random() < .8; app.btn_restore.invoke(); return "restore"
        if r < .50:
            end = time.time() + rnd.random() * .3
            while time.time() < end:
                app.update()
                time.sleep(.01)
            return "wait"
        if r < .56:
            picks["file"] = rnd.choice(choices); app.browse(); return "browse " + os.path.basename(picks["file"])
        if r < .59:
            shutil.rmtree(covers, ignore_errors=True); return "delete covers dir"
        if r < .62:
            files = [f for f in app.cover_files if os.path.exists(f)]
            if files:
                f = rnd.choice(files)
                if rnd.random() < .5:
                    open(f, "wb").write(b"garbage")
                else:
                    os.remove(f)
            return "mangle a cover"
        if r < .64:
            build_steam() if rnd.random() < .5 else shutil.rmtree(cfg, ignore_errors=True); return "reset/destroy steam folder"
        if r < .68:
            state["running"] = rnd.random() < .5; state["closes"] = rnd.random() < .7; return "steam state"
        if r < .73:
            net["mode"] = rnd.choice(["ok", "ok", "fail", "html", "slow"]); return "network " + net["mode"]
        if r < .76:
            app.on_close() if app.busy else None; return "try close"
        if r < .79:
            app.geometry("%dx%d" % (rnd.randint(300, 1800), rnd.randint(300, 1200))); return "resize"
        if r < .87:
            w = rnd.choice(all_widgets()); w.focus_force(); w.event_generate(rnd.choice(["<space>", "<Return>", "<Escape>"])); return "key on " + type(w).__name__
        if r < .91:
            f = app.focus_get()
            if f:
                f.tk_focusNext().focus_force()
            return "tab"
        if r < .95:
            app.scroller.canvas.yview_moveto(rnd.random()); app.scroller._scroll(rnd.choice([-3, 3])); return "scroll"
        if r < .965:
            app.copy_link(); return "copy link"
        if r < .98:
            app.hue.set(rnd.randint(0, 359)); app.sat.set(rnd.randint(0, 100)); app.val.set(rnd.randint(0, 100)); return "set colour"
        if r < .99:
            w = rnd.choice([app.slider, app.sat_slider, app.val_slider] + app.swatches); w.focus_force()
            w.event_generate(rnd.choice(["<Right>", "<Left>", "<Prior>", "<Next>", "<Home>", "<End>", "<space>"])); return "key on a colour control"
        if r < .995:
            rnd.choice(app.swatches).invoke(); return "click a swatch"
        with open(os.path.join(base, "dl", "userdata%s.json" % rnd.choice(["", " (1)"])), "w") as f:
            f.write(rnd.choice(['{"rgOwnedApps":[101,102]}', '{"rgOwnedApps":', "[", "\x00\x01"]))
        return "drop a file in Downloads"

    def invariants():
        bad = []
        if not settle():
            return ["STUCK: running=%s busy=%s" % (app.running, app.busy)]
        st = lambda w: str(w.cget("state"))
        ready = app.installed_only.get() or bool(app.library_path)
        if st(app.btn_cancel) != "disabled":
            bad.append("cancel enabled while idle")
        if (st(app.btn_make) == "normal") != ready:
            bad.append("make enabled=%s but ready=%s" % (st(app.btn_make), ready))
        if (st(app.btn_apply) == "normal") != bool(app.cover_files):
            bad.append("apply enabled=%s but cover_files=%d" % (st(app.btn_apply), len(app.cover_files)))
        colour = [app.slider, app.sat_slider, app.val_slider] + app.swatches
        if {st(w) for w in colour} != {st(app.sw_skip)}:
            bad.append("colour controls are %s but the other step 2 controls are %s" % ({st(w) for w in colour}, st(app.sw_skip)))
        page_buttons = [app.btn_page_open, app.btn_page_browse, app.btn_page_copy]
        if {st(w) for w in page_buttons} != {st(app.sw_skip)}:
            bad.append("games page buttons are %s but the other step 2 controls are %s" % ({st(w) for w in page_buttons}, st(app.sw_skip)))
        want = "normal" if st(app.sw_skip) == "normal" and app.games_page else "disabled"
        if st(app.style_choice) != want or {st(p) for p in app.style_choice._pills} != {want}:
            bad.append("100%% choice is %s but should be %s (page loaded: %s)" % (st(app.style_choice), want, bool(app.games_page)))
        if app.completion_style.get() not in ("ribbon", "gold-case", "gold-border", "none"):
            bad.append("100%% style out of range: %r" % app.completion_style.get())
        if not (app.completed is None or (isinstance(app.completed, set) and all(type(a) is int for a in app.completed))):
            bad.append("completed is not None or a set of app ids: %r" % (app.completed,))
        if (app.completed is None) != (app.games_page is None):
            bad.append("games_page=%r but completed=%r" % (app.games_page, app.completed))
        if not 0 <= app.hue.get() < 360:
            bad.append("hue out of range: %s" % app.hue.get())
        if not (0 <= app.sat.get() <= 100 and 0 <= app.val.get() <= 100):
            bad.append("tone out of range: %s %s" % (app.sat.get(), app.val.get()))
        if threading.active_count() > base_threads + 1:
            bad.append("leaked threads: %d" % (threading.active_count() - base_threads))
        if os.path.isdir(grid):
            for f in os.listdir(grid):
                if not re.fullmatch(r"[0-9]+p\.png", f):
                    bad.append("junk file in grid: " + f)
        if os.path.isdir(cfg):
            for d in os.listdir(cfg):
                if d.startswith("grid_backup_") and not os.path.exists(os.path.join(cfg, d, "manifest.json")):
                    bad.append("backup without manifest: " + d)
        if os.path.isdir(covers):
            for f in os.listdir(covers):
                if f.endswith(".part") or ".tmp_" in f or f.endswith(".tmp"):
                    bad.append("temp file left: " + f)
        return bad

    def act_load_page():
        """Load one of the pages: every seed does this once early, so the 100% block is always exercised."""
        picks["file"] = rnd.choice(page_files); app.browse_games_page(); return "browse page (forced) " + os.path.basename(picks["file"])

    forced = rnd.randrange(min(10, steps)) if steps else -1       # one of the first 10 steps
    log, failure, loaded = [], None, set()
    for n in range(steps):
        try:
            what = act_load_page() if n == forced else act()
        except Exception as e:
            errors.append(("act", "%s: %s" % (type(e).__name__, e)))
            what = "ACT-EXCEPTION"
        log.append(what)
        bad = invariants()
        if app.games_page:
            loaded.add((os.path.basename(app.games_page), app.completion_style.get()))
        if bad or errors:
            failure = "seed %d step %d after '%s' (last 6: %s)\n" % (seed, n, what, log[-6:]) + "".join("   INVARIANT: %s\n" % b for b in bad) + "".join("   ERROR: %s %s\n" % (e[0], e[1][-300:]) for e in errors[-3:])
            break
    try:
        app.destroy()
    except Exception:
        pass
    shutil.rmtree(base, ignore_errors=True)
    return failure, len(log), len(set(notes)), len(loaded)


def main():
    faulthandler.dump_traceback_later(420, exit=True)  # a hang prints where it stuck instead of running forever
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--sandbox", action="store_true", help="pretend to run inside a Flatpak sandbox for every seed (default: every other seed)")
    a = ap.parse_args()
    bad = 0
    for seed in range(a.first_seed, a.first_seed + a.seeds):
        sandbox = (a.sandbox or seed % 2 == 0) and hasattr(sc, "IN_SANDBOX")
        failure, n, popups, looks = run_one(seed, a.steps, sandbox)
        if failure:
            bad += 1
            print("FAIL (sandbox=%s) %s" % (sandbox, failure))
        else:
            print("ok   seed %d, %d random actions, sandbox=%s, %d kinds of error popup shown, %d (page, 100%% style) pairs used" % (seed, n, sandbox, popups, looks))
    print("%d of %d runs failed; %d attempts to open a program or folder were blocked" % (bad, a.seeds, len(LAUNCHED)))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
