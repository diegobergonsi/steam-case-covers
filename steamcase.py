#!/usr/bin/env python3
"""steamcase: give every game in your Steam library a "physical case" portrait cover.

  python steamcase.py list                       show the games it found
  python steamcase.py make                       build covers into ./covers
  python steamcase.py apply                      copy covers into Steam's grid folder
  python steamcase.py run                        make + apply

Needs Python 3.8+ and Pillow (pip install pillow). No Steam API key, no account login.
Covers are built on your machine from the artwork Steam itself serves for your games.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is missing. Install it with:  python -m pip install pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME = os.path.join(HERE, "assets", "frame.png")
WINDOW = (14, 96, 586, 872)                 # art window inside frame.png (x0, y0, x1, y1)
SIZE = (600, 900)
STEAMID64_BASE = 76561197960265728
CDN = "https://shared.fastly.steamstatic.com/store_item_assets/"
OLD_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_600x900_2x.jpg"
STORE_API = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?"
TOOL_NAMES = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|Steam Controller Configs)", re.I)


# ---------- helpers ----------
def http_get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 steamcase"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "game"


def vdf_values(text, key):
    return re.findall(r'"%s"\s+"((?:[^"\\]|\\.)*)"' % re.escape(key), text, re.I)


# ---------- finding Steam ----------
def steam_dir(override=None):
    if override:
        return os.path.expanduser(override)
    home = os.path.expanduser("~")
    cands = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                cands.append(winreg.QueryValueEx(k, "SteamPath")[0])
        except Exception:
            pass
        cands += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    elif sys.platform == "darwin":
        cands.append(os.path.join(home, "Library/Application Support/Steam"))
    else:
        cands += [os.path.join(home, ".local/share/Steam"), os.path.join(home, ".steam/steam"),
                  os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
                  os.path.join(home, "snap/steam/common/.local/share/Steam")]
    for c in cands:
        if os.path.isdir(os.path.join(c, "steamapps")) or os.path.isdir(os.path.join(c, "userdata")):
            return os.path.realpath(c)
    sys.exit("Could not find Steam. Pass its folder with --steam-dir.")


def library_paths(steam):
    paths = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        for p in vdf_values(open(vdf, errors="replace").read(), "path"):
            p = p.replace("\\\\", "\\")
            if os.path.isdir(p) and os.path.realpath(p) not in [os.path.realpath(x) for x in paths]:
                paths.append(p)
    return paths


def installed_games(steam):
    games = {}
    for lib in library_paths(steam):
        for f in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            t = open(f, errors="replace").read()
            i, n = vdf_values(t, "appid"), vdf_values(t, "name")
            if i and n and not TOOL_NAMES.match(n[0]):
                games[int(i[0])] = n[0]
    return games


def owned_ids(json_path):
    d = json.load(open(os.path.expanduser(json_path), encoding="utf-8"))
    ids = d.get("rgOwnedApps")
    if not ids:
        sys.exit("No 'rgOwnedApps' in that file. Save https://store.steampowered.com/dynamicstore/userdata/ while logged in.")
    return [int(i) for i in ids]


def pick_account(steam, forced=None):
    base = os.path.join(steam, "userdata")
    accs = [d for d in os.listdir(base) if d.isdigit() and d != "0"] if os.path.isdir(base) else []
    if forced:
        if not str(forced).isdigit():
            sys.exit("--user must be the numeric folder name inside userdata/, e.g. 12345678")
        return str(forced)
    if not accs:
        sys.exit("No account folders in %s. Log in to Steam once, then retry (or use --user)." % base)
    if len(accs) == 1:
        return accs[0]
    recent = None
    lu = os.path.join(steam, "config", "loginusers.vdf")
    if os.path.exists(lu):
        for m in re.finditer(r'"(\d{17})"\s*\{(.*?)\}', open(lu, errors="replace").read(), re.S):
            if re.search(r'"MostRecent"\s+"1"', m.group(2)):
                recent = str(int(m.group(1)) - STEAMID64_BASE)
    if recent in accs:
        return recent
    return max(accs, key=lambda a: os.path.getmtime(os.path.join(base, a)))


def steam_running():
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
            return "steam.exe" in out
        out = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True).stdout.lower()
        return any(l.strip() in ("steam", "steam_osx", "steamwebhelper") for l in out.splitlines())
    except Exception:
        return False


# ---------- store data ----------
def store_items(appids):
    out = {}
    for n in range(0, len(appids), 100):
        chunk = appids[n:n + 100]
        q = json.dumps({"ids": [{"appid": i} for i in chunk], "context": {"language": "english", "country_code": "US"},
                        "data_request": {"include_assets": True}})
        try:
            items = json.loads(http_get(STORE_API + urllib.parse.urlencode({"input_json": q})))["response"].get("store_items", [])
        except Exception as e:
            print("  store lookup failed for a chunk:", e)
            continue
        for appid, it in zip(chunk, items):
            out[appid] = it
    return out


def portrait_candidates(appid, item):
    a = (item or {}).get("assets") or {}
    fmt = a.get("asset_url_format")
    urls, auto = [], False
    for k in ("library_capsule_2x", "library_capsule"):
        if fmt and a.get(k):
            urls.append(CDN + fmt.replace("${FILENAME}", a[k]))
            auto = a[k].endswith("portrait.png")     # Steam-generated from the header: blurry
            break
    urls.append(OLD_CDN % appid)
    return urls, auto


# ---------- drawing ----------
def build_cover(portrait_path, out_path, frame):
    art = Image.open(portrait_path).convert("RGBA")
    x0, y0, x1, y1 = WINDOW
    ww, wh = x1 - x0, y1 - y0
    s = max(ww / art.width, wh / art.height)                      # scale to cover, then center-crop
    art = art.resize((max(ww, round(art.width * s)), max(wh, round(art.height * s))), Image.LANCZOS)
    cx, cy = (art.width - ww) // 2, (art.height - wh) // 2
    art = art.crop((cx, cy, cx + ww, cy + wh))
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.paste(art, (x0, y0))
    Image.alpha_composite(canvas, frame).save(out_path, optimize=True)


# ---------- commands ----------
def collect(args):
    steam = steam_dir(args.steam_dir)
    games = installed_games(steam)
    if args.library:
        for i in owned_ids(args.library):
            games.setdefault(i, None)
    return steam, games


def cmd_list(args):
    steam, games = collect(args)
    print("Steam folder:", steam)
    info = store_items(sorted(games))
    n = 0
    for appid in sorted(games):
        it = info.get(appid, {})
        if it.get("type", 0) not in (0, None) or not (games[appid] or it.get("name")):
            continue
        print(appid, games[appid] or it.get("name"))
        n += 1
    print("\n%d games%s" % (n, "" if args.library else "  (installed only; add --library userdata.json for your whole library)"))


def cmd_make(args):
    steam, games = collect(args)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    frame = Image.open(FRAME).convert("RGBA")
    ids = sorted(games)
    if args.only:
        ids = [i for i in ids if i in set(args.only)]
    print("Looking up %d apps on Steam's store..." % len(ids))
    info = store_items(ids)
    ok = skipped = 0
    missing = []
    for appid in ids:
        it = info.get(appid) or {}
        name = games[appid] or it.get("name") or str(appid)
        if it.get("type", 0) not in (0, None) or TOOL_NAMES.match(name):
            skipped += 1
            continue
        dest = os.path.join(out, "%s_%d.png" % (slug(name), appid))
        if os.path.exists(dest) and not args.force:
            ok += 1
            continue
        urls, auto = portrait_candidates(appid, it)
        if auto and args.skip_auto_art:
            skipped += 1
            continue
        tmp = os.path.join(out, ".tmp_%d" % appid)
        got = False
        for u in urls:
            try:
                b = http_get(u)
            except Exception:
                continue
            if b[:2] == b"\xff\xd8" or b[:4] == b"\x89PNG" or b[8:12] == b"WEBP":
                open(tmp, "wb").write(b)
                got = True
                break
        if not got:
            missing.append((appid, name))
            continue
        try:
            build_cover(tmp, dest, frame)
            ok += 1
            print("ok  ", appid, name)
        except Exception as e:
            missing.append((appid, name))
            print("FAIL", appid, name, e)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    print("\n%d covers in %s | %d skipped (DLC/tools/non-games) | %d without portrait art" % (ok, out, skipped, len(missing)))
    for appid, name in missing:
        print("  no art:", appid, name)


def cmd_apply(args):
    steam = steam_dir(args.steam_dir)
    acc = pick_account(steam, args.user)
    grid = os.path.join(steam, "userdata", acc, "config", "grid")
    covers = [f for f in glob.glob(os.path.join(os.path.abspath(args.covers), "*.png")) if re.search(r"_(\d+)\.png$", f)]
    if not covers:
        sys.exit("No covers found in %s. Run 'make' first." % args.covers)
    print("Steam account folder:", acc, "\nGrid folder:", grid, "\nCovers to apply:", len(covers))
    if steam_running() and not args.yes:
        print("\nSteam seems to be running. Close it first (Steam > Exit) so it picks the files up on next start.")
        if input("Copy anyway? [y/N] ").strip().lower() != "y":
            sys.exit("Cancelled.")
    os.makedirs(grid, exist_ok=True)
    backup = os.path.join(os.path.dirname(grid), "grid_backup_" + time.strftime("%Y%m%d_%H%M%S"))
    n = b = 0
    for f in covers:
        appid = re.search(r"_(\d+)\.png$", f).group(1)
        dest = os.path.join(grid, "%sp.png" % appid)
        if os.path.exists(dest):
            os.makedirs(backup, exist_ok=True)
            shutil.copy2(dest, os.path.join(backup, os.path.basename(dest)))
            b += 1
        shutil.copy2(f, dest)
        n += 1
    print("\nApplied %d covers. Backed up %d existing files%s." % (n, b, " to " + backup if b else ""))
    print("Restart Steam to see them. A custom artwork set by hand in Steam may override these.")


def cmd_run(args):
    args.covers = args.out
    cmd_make(args)
    cmd_apply(args)


def main():
    ap = argparse.ArgumentParser(description="Steam 'physical case' covers for your library.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, make=False, apply_=False):
        p.add_argument("--steam-dir", help="Steam folder (auto-detected by default)")
        if make:
            p.add_argument("--library", metavar="JSON", help="whole-library list saved from store.steampowered.com/dynamicstore/userdata/")
            p.add_argument("--out", default="covers", help="where covers are written (default: ./covers)")
        if apply_:
            p.add_argument("--covers", default="covers", help="folder with covers (default: ./covers)")
            p.add_argument("--user", help="Steam account folder id inside userdata/ (auto: most recent login)")
            p.add_argument("--yes", action="store_true", help="don't ask even if Steam is running")

    p = sub.add_parser("list", help="show detected games"); common(p, make=True); p.set_defaults(fn=cmd_list)
    for name, fn in (("make", cmd_make), ("run", cmd_run)):
        p = sub.add_parser(name, help=name + " covers" if name == "make" else "make + apply")
        common(p, make=True, apply_=(name == "run"))
        p.add_argument("--only", type=int, nargs="+", metavar="APPID", help="only these app IDs")
        p.add_argument("--force", action="store_true", help="rebuild covers that already exist")
        p.add_argument("--skip-auto-art", action="store_true", help="skip games whose Steam portrait is the blurry auto-generated one")
        p.set_defaults(fn=fn)
    p = sub.add_parser("apply", help="copy covers into Steam"); common(p, apply_=True); p.set_defaults(fn=cmd_apply)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
