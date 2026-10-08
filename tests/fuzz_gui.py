#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""A "clumsy robot user" for the window. It needs a display (on a server: `xvfb-run -a python tests/fuzz_gui.py`).

It builds a fake Steam folder and fake Steam servers, then performs random actions (clicks, key presses, toggles, cancelling at a
random moment, deleting folders mid-run, flipping the network and Steam's state, picking junk files, resizing...). After every
action it checks that nothing crashed, nothing is stuck, the buttons match the state, and the folders only hold what they should.

    python tests/fuzz_gui.py [--seeds N] [--steps N] [--sandbox]

Exit code 0 = every run was clean."""
import argparse, io, json, os, random, re, shutil, sys, tempfile, threading, time, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gui, widgets, steamcase as sc
from PIL import Image

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
    gui.messagebox.showerror = lambda t, m: notes.append("popup:" + m[:60])
    gui.messagebox.showinfo = lambda t, m: None
    gui.pick_file = lambda title, initialdir: picks["file"]

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
            if not app.running and not app.busy:
                return True
            time.sleep(0.02)
        return False

    def all_widgets():
        out = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (widgets.RoundedButton, widgets.Switch, widgets.InfoBadge)):
                    out.append(c)
                walk(c)
        walk(app)
        return out

    def act():
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
            app.sw_installed.event_generate("<Button-1>"); return "toggle installed"
        if r < .13:
            app.sw_skip.event_generate("<Button-1>"); return "toggle skip"
        if r < .16:
            app.chk_restart.event_generate("<Button-1>"); return "toggle restart"
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
        if r < .97:
            app.copy_link(); return "copy link"
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

    log, failure = [], None
    for n in range(steps):
        try:
            what = act()
        except Exception as e:
            errors.append(("act", "%s: %s" % (type(e).__name__, e)))
            what = "ACT-EXCEPTION"
        log.append(what)
        bad = invariants()
        if bad or errors:
            failure = "seed %d step %d after '%s' (last 6: %s)\n" % (seed, n, what, log[-6:]) + "".join("   INVARIANT: %s\n" % b for b in bad) + "".join("   ERROR: %s %s\n" % (e[0], e[1][-300:]) for e in errors[-3:])
            break
    try:
        app.destroy()
    except Exception:
        pass
    shutil.rmtree(base, ignore_errors=True)
    return failure, len(log), len(set(notes))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--steps", type=int, default=120)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--sandbox", action="store_true", help="pretend to run inside a Flatpak sandbox for every seed (default: every other seed)")
    a = ap.parse_args()
    bad = 0
    for seed in range(a.first_seed, a.first_seed + a.seeds):
        sandbox = (a.sandbox or seed % 2 == 0) and hasattr(sc, "IN_SANDBOX")
        failure, n, popups = run_one(seed, a.steps, sandbox)
        if failure:
            bad += 1
            print("FAIL (sandbox=%s) %s" % (sandbox, failure))
        else:
            print("ok   seed %d, %d random actions, sandbox=%s, %d kinds of error popup shown" % (seed, n, sandbox, popups))
    print("%d of %d runs failed" % (bad, a.seeds))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
