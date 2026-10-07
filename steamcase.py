#!/usr/bin/env python3
"""steamcase: give every game in your Steam library a "physical case" portrait cover.

  python steamcase.py list                       show the games it found
  python steamcase.py make                       build covers into ./covers
  python steamcase.py apply                      copy covers into Steam's grid folder
  python steamcase.py run                        make + apply
  python steamcase.py restore                    undo the last apply

Needs Python 3.8+ and Pillow (pip install pillow). No Steam API key, no account login.
Covers are built on your machine from the artwork Steam itself serves for your games.

The functions below are the engine. The CLI at the bottom and gui.py both use them.
"""
import argparse, filecmp, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid

try:
    from PIL import Image
except ImportError:
    Image = None

for _s in (sys.stdout, sys.stderr):          # game names may hold non-ASCII; never crash a legacy console
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))   # _MEIPASS: inside a PyInstaller bundle
FRAME = os.path.join(HERE, "assets", "frame.png")
WINDOW = (14, 96, 586, 872)                 # art window inside frame.png (x0, y0, x1, y1)
SIZE = (600, 900)
STEAMID64_BASE = 76561197960265728
CDN = "https://shared.fastly.steamstatic.com/store_item_assets/"
OLD_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_600x900_2x.jpg"
STORE_API = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?"
LIBRARY_JSON_URL = "https://store.steampowered.com/dynamicstore/userdata/"
MAX_DOWNLOAD = 25 * 1024 * 1024          # a cover portrait is ~1 MB; anything bigger is not one
MAX_LIBRARY_FILE = 20 * 1024 * 1024      # a real library list is a few KB
MAX_APPS = 100_000                       # a real library has at most a few thousand apps
MAX_PIXELS = 30_000_000                  # portraits are ~1 MP; refuses decompression bombs
TOOL_NAMES = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|Steam Controller Configs)", re.I)
BACKUP_PREFIX = "grid_backup_"

# Shown next to the "skip blurry auto-art" option (GUI tooltip, CLI --help).
AUTO_ART_HELP = (
    "Some games, mostly older or small ones, have no real portrait on Steam. "
    "Steam builds a stand-in from the wide header image: the title banner sits in the "
    "middle of a blurred, stretched copy of itself, with lots of empty space. "
    "Tick this to skip those games and keep Steam's default art for them."
)


def default_covers_dir():
    """Per-user folder for the app (GUI) to keep covers in."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "steamcase", "covers")


class SteamcaseError(Exception):
    """A problem the user can understand (no Steam found, bad file...). The message is meant to be shown."""


# ---------- helpers ----------
def _read_capped(resp):
    size = resp.headers.get("Content-Length")
    if size and size.isdigit() and int(size) > MAX_DOWNLOAD:
        raise SteamcaseError("A download was unexpectedly large (%s bytes); refusing it." % size)
    data = resp.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise SteamcaseError("A download was unexpectedly large; refusing it.")
    return data


def http_get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 steamcase"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return _read_capped(r)
        except SteamcaseError:
            raise
        except urllib.error.HTTPError as e:
            if i == tries - 1 or (400 <= e.code < 500 and e.code != 429):      # a real "not found": retrying will not help
                raise
            time.sleep(1.5 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def _tmp(path, tag="tmp"):
    """A temp file name next to `path` that no other run can share."""
    return "%s.%d.%s.%s" % (path, os.getpid(), uuid.uuid4().hex[:8], tag)


def slug(name):
    return re.sub(r"[^\w]+", "_", name)[:60].strip("_") or "game"      # short enough for any filesystem (255 bytes)


def read_text(path):
    return open(path, encoding="utf-8-sig", errors="replace").read()


def vdf_values(text, key):
    return re.findall(r'"%s"\s+"((?:[^"\\]|\\.)*)"' % re.escape(key), text, re.I)


def _tool(name):
    """Full path of a system tool, so a look-alike file next to the app (or in the current folder) can never be run instead."""
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", name + ".exe")
    for d in ("/usr/bin", "/bin"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return name


def appid_of(filename):
    m = re.search(r"_([0-9]{1,10})\.png$", filename)
    return m.group(1) if m and 0 < int(m.group(1)) < 2 ** 32 else None


# ---------- finding Steam ----------
def steam_dir(override=None):
    if override:
        path = os.path.expanduser(override)
        if not os.path.isdir(path):
            raise SteamcaseError("Steam folder not found: %s" % path)
        return path
    home = os.path.expanduser("~")
    cands = []
    if sys.platform.startswith("win"):
        try:
            import winreg
            for hive, sub, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        cands.append(winreg.QueryValueEx(k, val)[0])
                except OSError:
                    pass
        except ImportError:
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
    raise SteamcaseError("Could not find Steam. Is it installed? (CLI: pass its folder with --steam-dir.)")


def library_paths(steam):
    paths = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        for p in vdf_values(read_text(vdf), "path"):
            p = p.replace("\\\\", "\\")
            if os.path.isdir(p) and os.path.realpath(p) not in [os.path.realpath(x) for x in paths]:
                paths.append(p)
    return paths


def installed_games(steam):
    games = {}
    for lib in library_paths(steam):
        apps = os.path.join(lib, "steamapps")
        if not os.path.isdir(apps):
            continue
        for fn in os.listdir(apps):
            if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
                continue
            t = read_text(os.path.join(apps, fn))
            i, n = vdf_values(t, "appid"), vdf_values(t, "name")
            if i and n and not TOOL_NAMES.match(n[0]):
                games[int(i[0])] = n[0]
    return games


def owned_ids(json_path):
    path = os.path.expanduser(json_path)
    try:
        if os.path.getsize(path) > MAX_LIBRARY_FILE:
            raise SteamcaseError("That file is far too big to be your game list (over %d MB)." % (MAX_LIBRARY_FILE >> 20))
        d = json.load(open(path, encoding="utf-8-sig"))
    except SteamcaseError:
        raise
    except (OSError, ValueError, RecursionError, MemoryError, UnicodeError) as e:
        raise SteamcaseError("Could not read %s as a game list (%s)." % (os.path.basename(path), type(e).__name__))
    ids = d.get("rgOwnedApps") if isinstance(d, dict) else None
    if not ids or not isinstance(ids, list):
        raise SteamcaseError("That file has no game list ('rgOwnedApps'). Save %s while logged in to Steam." % LIBRARY_JSON_URL)
    if len(ids) > MAX_APPS:
        raise SteamcaseError("That game list has %d entries; a real library has far fewer. Refusing it." % len(ids))
    try:
        out = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise SteamcaseError("The game list in that file is damaged. Save %s again." % LIBRARY_JSON_URL)
    out = [i for i in out if 0 < i < 2 ** 32]                    # real Steam app IDs only
    if not out:
        raise SteamcaseError("The game list in that file is empty. Save %s while logged in to Steam." % LIBRARY_JSON_URL)
    return out


def load_games(steam, library_json=None):
    """{appid: name or None}: installed games, plus every owned app when library_json is given."""
    games = installed_games(steam)
    if library_json:
        for i in owned_ids(library_json):
            games.setdefault(i, None)
    return games


def pick_account(steam, forced=None):
    base = os.path.join(steam, "userdata")
    accs = [d for d in os.listdir(base) if re.fullmatch(r"[0-9]+", d) and d != "0"] if os.path.isdir(base) else []
    if forced:
        if not re.fullmatch(r"[0-9]+", str(forced)):
            raise SteamcaseError("The account must be the numeric folder name inside userdata/, e.g. 12345678")
        return str(forced)
    if not accs:
        raise SteamcaseError("No account folders in %s. Log in to Steam once, then retry." % base)
    if len(accs) == 1:
        return accs[0]
    recent = None
    lu = os.path.join(steam, "config", "loginusers.vdf")
    if os.path.exists(lu):
        for m in re.finditer(r'"([0-9]{17})"\s*\{(.*?)\}', read_text(lu), re.S):
            if re.search(r'"MostRecent"\s+"1"', m.group(2)):
                recent = str(int(m.group(1)) - STEAMID64_BASE)
    if recent in accs:
        return recent
    return max(accs, key=lambda a: os.path.getmtime(os.path.join(base, a)))


def account_label(steam, acc):
    """Human name for a userdata folder id: Steam display name, else login name, else the number."""
    lu = os.path.join(steam, "config", "loginusers.vdf")
    if os.path.exists(lu):
        for m in re.finditer(r'"([0-9]{17})"\s*\{(.*?)\}', read_text(lu), re.S):
            if str(int(m.group(1)) - STEAMID64_BASE) == str(acc):
                names = vdf_values(m.group(2), "PersonaName") + vdf_values(m.group(2), "AccountName")
                for n in names:
                    if n.strip():
                        return n.strip()
    return str(acc)


def grid_dir(steam, user=None):
    return os.path.join(steam, "userdata", pick_account(steam, user), "config", "grid")


# ---------- Steam process ----------
def steam_running():
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run([_tool("tasklist")], capture_output=True, text=True).stdout.lower()
            return "steam.exe" in out
        out = subprocess.run([_tool("ps"), "-A", "-o", "comm="], capture_output=True, text=True).stdout.lower()
        return any(l.strip() in ("steam", "steam_osx", "steamwebhelper") for l in out.splitlines())
    except Exception:
        return False


def _steam_launcher(steam):
    """Command list that runs Steam, or None if unknown."""
    if sys.platform.startswith("win"):
        exe = os.path.join(steam, "steam.exe")
        return [exe] if os.path.exists(exe) else None
    if sys.platform == "darwin":
        return [_tool("open"), "-a", "Steam", "--args"]
    if "com.valvesoftware.Steam" in steam and shutil.which("flatpak"):
        return ["flatpak", "run", "com.valvesoftware.Steam"]
    found = shutil.which("steam")
    if found:
        return [found]
    for rel in ("steam.sh", "ubuntu12_32/steam"):
        p = os.path.join(steam, rel)
        if os.path.exists(p):
            return [p]
    return None


def close_steam(steam, timeout=60):
    """Ask Steam to exit and wait for it. Returns True when it is gone. Never kills the process."""
    if not steam_running():
        return True
    cmd = _steam_launcher(steam)
    try:
        if sys.platform == "darwin":
            subprocess.Popen([_tool("osascript"), "-e", 'quit app "Steam"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif cmd:
            subprocess.Popen(cmd + ["-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            raise SteamcaseError("Could not work out how to close Steam. Please close it yourself.")
    except OSError as e:
        raise SteamcaseError("Could not close Steam: %s" % e)
    end = time.time() + timeout
    while time.time() < end:
        if not steam_running():
            time.sleep(2)                       # let it finish writing its files
            return True
        time.sleep(1)
    return False


def start_steam(steam):
    cmd = _steam_launcher(steam)
    if not cmd:
        raise SteamcaseError("Could not work out how to start Steam. Please start it yourself.")
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=not sys.platform.startswith("win"))
    except OSError as e:
        raise SteamcaseError("Could not start Steam: %s" % e)


# ---------- store data ----------
def store_items(appids, log=None, cancelled=None):
    out = {}
    for n in range(0, len(appids), 100):
        if cancelled and cancelled():
            break
        chunk = appids[n:n + 100]
        q = json.dumps({"ids": [{"appid": i} for i in chunk], "context": {"language": "english", "country_code": "US"},
                        "data_request": {"include_assets": True}})
        try:
            items = json.loads(http_get(STORE_API + urllib.parse.urlencode({"input_json": q})))["response"].get("store_items", [])
        except Exception as e:
            if log:
                log("store lookup failed for a chunk: %s" % e)
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


def list_games(games, log=None):
    """[(appid, name)] of real games only (no DLC, tools or unnamed leftovers)."""
    info = store_items(sorted(games), log)
    out = []
    for appid in sorted(games):
        it = info.get(appid, {})
        name = games[appid] or it.get("name")
        if it.get("type", 0) not in (0, None) or not name or TOOL_NAMES.match(name):
            continue
        out.append((appid, name))
    return out


# ---------- drawing ----------
def build_cover(portrait_path, out_path, frame):
    if Image is None:
        raise SteamcaseError("Pillow is missing. Install it with:  python -m pip install pillow")
    with Image.open(portrait_path, formats=["PNG", "JPEG", "WEBP"]) as im:        # never let Pillow guess (EPS, TIFF, ... have a worse track record)
        if im.width * im.height > MAX_PIXELS:                  # header check only; nothing is decoded yet
            raise SteamcaseError("Image is too large to be a game portrait (%dx%d)." % im.size)
        art = im.convert("RGBA")
    x0, y0, x1, y1 = WINDOW
    ww, wh = x1 - x0, y1 - y0
    s = max(ww / art.width, wh / art.height)                      # scale to cover, then center-crop
    art = art.resize((max(ww, round(art.width * s)), max(wh, round(art.height * s))), Image.LANCZOS)
    cx, cy = (art.width - ww) // 2, (art.height - wh) // 2
    art = art.crop((cx, cy, cx + ww, cy + wh))
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.paste(art, (x0, y0))
    part = _tmp(out_path, "part")                  # write aside, then rename: a crash never leaves a half-written cover
    Image.alpha_composite(canvas, frame).save(part, format="PNG", optimize=True)
    os.replace(part, out_path)


# ---------- make ----------
def make_covers(games, out, only=None, force=False, skip_auto_art=False, progress=None, cancelled=None, log=None):
    """Build a cover per game into `out`.

    progress(done, total, appid, name, status)  status: ok | exists | skipped | noart | failed
    cancelled() -> True stops early.
    Returns {"ok", "skipped", "missing": [(appid, name)] (Steam has no art), "failed": [(appid, name)] (download problem),
    "cancelled", "files": [cover paths of this run]}.
    """
    if Image is None:
        raise SteamcaseError("Pillow is missing. Install it with:  python -m pip install pillow")
    os.makedirs(out, exist_ok=True)
    frame = Image.open(FRAME).convert("RGBA")
    ids = sorted(games)
    if only:
        ids = [i for i in ids if i in set(only)]
    if log:
        log("Looking up %d apps on Steam's store..." % len(ids))
    info = store_items(ids, log, cancelled)
    if ids and not info and not (cancelled and cancelled()):
        raise SteamcaseError("Could not reach Steam's servers. Check your internet connection and try again.")
    res = {"ok": 0, "skipped": 0, "missing": [], "failed": [], "cancelled": False, "files": []}
    total = len(ids)

    def report(done, appid, name, status):
        if progress:
            progress(done, total, appid, name, status)

    for n, appid in enumerate(ids, 1):
        if cancelled and cancelled():
            res["cancelled"] = True
            break
        it = info.get(appid) or {}
        name = games[appid] or it.get("name") or str(appid)
        if it.get("type", 0) not in (0, None) or TOOL_NAMES.match(name):
            res["skipped"] += 1
            report(n, appid, name, "skipped")
            continue
        dest = os.path.join(out, "%s_%d.png" % (slug(name), appid))
        urls, auto = portrait_candidates(appid, it)
        if auto and skip_auto_art:                 # checked first: also drops covers built by an earlier run without this option
            res["skipped"] += 1
            report(n, appid, name, "skipped")
            continue
        if os.path.exists(dest) and not force:
            res["ok"] += 1
            res["files"].append(dest)
            report(n, appid, name, "exists")
            continue
        tmp = os.path.join(out, ".tmp_%d_%s" % (appid, uuid.uuid4().hex[:8]))
        got = neterr = False
        for u in urls:
            try:
                b = http_get(u)
            except urllib.error.HTTPError as e:
                neterr = neterr or not (400 <= e.code < 500 and e.code != 429)      # 404/403 = no such art; the rest = trouble
                continue
            except Exception:
                neterr = True
                continue
            if b[:2] == b"\xff\xd8" or b[:4] == b"\x89PNG" or b[8:12] == b"WEBP":
                with open(tmp, "wb") as f:
                    f.write(b)
                got = True
                break
            neterr = True                                    # answered, but not with an image: a login page or proxy in the way
        if not got:
            res["failed" if neterr else "missing"].append((appid, name))        # failed = connection problem, worth a retry
            report(n, appid, name, "failed" if neterr else "noart")
            continue
        try:
            build_cover(tmp, dest, frame)
            res["ok"] += 1
            res["files"].append(dest)
            report(n, appid, name, "ok")
        except Exception as e:
            res["failed"].append((appid, name))
            if log:
                log("FAIL %s %s: %s" % (appid, name, e))
            report(n, appid, name, "failed")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return res


# ---------- apply / backup / restore ----------
def _safe_copy(src, dst):
    """Copy src to dst atomically. If dst is a symlink, the link itself is replaced, never the file it points to."""
    tmp = _tmp(dst)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def find_covers(covers_dir):
    cdir = os.path.abspath(covers_dir)
    if not os.path.isdir(cdir):
        return []
    return [os.path.join(cdir, f) for f in sorted(os.listdir(cdir)) if appid_of(f)]


def apply_covers(steam, covers_dir, user=None, files=None):
    """Copy covers into Steam's grid folder as <appid>p.png. Always makes a backup first.

    `files`: apply only these cover files (default: every cover in covers_dir).
    Only files that differ are written (and backed up); if nothing differs there is no backup and "backup" is None.
    Returns {"account", "account_name", "grid", "applied", "unchanged", "replaced", "backup"}.
    The caller closes Steam beforehand (see close_steam)."""
    grid = grid_dir(steam, user)
    covers = list(files) if files else find_covers(covers_dir)
    if not covers:
        raise SteamcaseError("No covers found in %s. Make them first." % covers_dir)
    gone = [f for f in covers if not os.path.exists(f)]
    if gone:
        raise SteamcaseError("%d cover files are missing (deleted since they were made). Click “Make covers” again. Nothing was changed." % len(gone))
    os.makedirs(grid, exist_ok=True)
    with _Lock(os.path.dirname(grid)):
        acc = os.path.basename(os.path.dirname(os.path.dirname(grid)))
        info = {"account": acc, "account_name": account_label(steam, acc), "grid": grid}
        work, added, replaced = [], [], []
        for f in covers:
            n = "%sp.png" % appid_of(f)
            dest = os.path.join(grid, n)
            if os.path.exists(dest):
                if filecmp.cmp(f, dest, shallow=False):
                    continue                                     # identical already: no need to touch or back it up
                replaced.append(n)
            else:
                added.append(n)
            work.append((f, n))
        if not work:
            return dict(info, applied=0, unchanged=len(covers), replaced=0, backup=None)
        base = os.path.join(os.path.dirname(grid), BACKUP_PREFIX + time.strftime("%Y%m%d_%H%M%S"))
        backup, k = base, 1
        while True:
            try:
                os.makedirs(backup)
                break
            except FileExistsError:                                  # two applies in the same second
                k += 1
                backup = "%s-%d" % (base, k)
        try:
            for n in replaced:
                shutil.copy2(os.path.join(grid, n), os.path.join(backup, n))
            with open(os.path.join(backup, "manifest.json"), "w") as fh:     # written before copying, so a rollback always works
                json.dump({"added": added, "replaced": replaced}, fh)
            for f, n in work:
                _safe_copy(f, os.path.join(grid, n))
        except OSError as e:
            try:
                _undo(grid, backup, {"added": added, "replaced": replaced})     # leave Steam's art exactly as it was (we already hold the lock)
            except Exception:
                pass
            shutil.rmtree(backup, ignore_errors=True)                           # a failed run must not leave a backup behind
            raise SteamcaseError("Could not write to Steam's artwork folder (%s). Nothing was changed." % e)
        return dict(info, applied=len(work), unchanged=len(covers) - len(work), replaced=len(replaced), backup=backup)


class _Lock:
    """One Apply/Restore at a time per Steam account (two open windows, or a script and a window)."""

    def __init__(self, cfg):
        self.path = os.path.join(cfg, ".steamcase.lock")

    def __enter__(self):
        for _ in range(3):
            try:
                os.mkdir(self.path)                                  # atomic: only one run can create it
                return self
            except FileExistsError:
                try:
                    stale = time.time() - os.path.getmtime(self.path) > 600       # left behind by a crashed run
                except OSError:
                    continue
                if stale:
                    shutil.rmtree(self.path, ignore_errors=True)
                    continue
                raise SteamcaseError("Another steamcase window is changing Steam's artwork right now. Wait for it to finish, then try again.")
        raise SteamcaseError("Could not get exclusive access to Steam's artwork folder. Please try again.")

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)


def list_backups(steam, user=None):
    """Backup folders for this account, newest first."""
    cfg = os.path.dirname(grid_dir(steam, user))
    if not os.path.isdir(cfg):
        return []
    return [os.path.join(cfg, d) for d in sorted(os.listdir(cfg), reverse=True) if d.startswith(BACKUP_PREFIX)]


def _undo(grid, backup_dir, m):
    """Put the replaced files back from backup_dir and remove the added ones. Caller holds the lock. Returns files touched."""
    n = 0
    for name in m.get("replaced", []):
        src = os.path.join(backup_dir, name)
        if os.path.exists(src) and not os.path.islink(src):          # a symlink here could smuggle another file into Steam's folder
            _safe_copy(src, os.path.join(grid, name))
            n += 1
    for name in m.get("added", []):
        p = os.path.join(grid, name)
        if os.path.lexists(p):
            os.remove(p)                                             # removes a symlink itself, never what it points to
            n += 1
    return n


_COVER_NAME = re.compile(r"^[0-9]{1,10}p\.png$")


def restore_backup(steam, backup_dir, user=None, keep=False):
    """Undo one apply: put replaced files back and remove the ones that were added. Returns files touched.
    The backup is deleted afterwards (so the next restore goes one step further back) unless keep=True.
    Only real steamcase backups inside this account's config folder are accepted, and only files named <appid>p.png are touched."""
    grid = grid_dir(steam, user)
    cfg = os.path.realpath(os.path.dirname(grid))
    real = os.path.realpath(backup_dir)
    if os.path.dirname(real) != cfg or not os.path.basename(real).startswith(BACKUP_PREFIX):
        raise SteamcaseError("That is not a steamcase backup of this Steam account.")
    mf = os.path.join(real, "manifest.json")
    if not os.path.exists(mf):
        raise SteamcaseError("That folder is not a steamcase backup: %s" % backup_dir)
    try:
        m = json.load(open(mf))
        names = [str(x) for x in m.get("replaced", []) + m.get("added", [])]
    except (OSError, ValueError, AttributeError, TypeError, RecursionError, MemoryError, UnicodeError):
        raise SteamcaseError("The backup's manifest is damaged.")
    if not all(_COVER_NAME.match(n) for n in names):
        raise SteamcaseError("The backup's manifest lists unexpected files; refusing to use it.")
    with _Lock(cfg):
        n = _undo(grid, real, m)
        if not keep:
            shutil.rmtree(real, ignore_errors=True)
    return n


# ---------- command line ----------
def _collect(args):
    steam = steam_dir(args.steam_dir)
    return steam, load_games(steam, args.library)


def cmd_list(args):
    steam, games = _collect(args)
    print("Steam folder:", steam)
    rows = list_games(games, print)
    for appid, name in rows:
        print(appid, name)
    print("\n%d games%s" % (len(rows), "" if args.library else "  (installed only; add --library userdata.json for your whole library)"))


def cmd_make(args):
    steam, games = _collect(args)

    def progress(done, total, appid, name, status):
        if status == "ok":
            print("ok  ", appid, name)

    res = make_covers(games, os.path.abspath(args.out), args.only, args.force, args.skip_auto_art, progress, log=print)
    print("\n%d covers in %s | %d skipped (DLC/tools/non-games) | %d without portrait art" % (res["ok"], os.path.abspath(args.out), res["skipped"], len(res["missing"])))
    for appid, name in res["missing"]:
        print("  no art:", appid, name)
    for appid, name in res["failed"]:
        print("  failed (connection problem? run again to retry):", appid, name)


def cmd_apply(args):
    steam = steam_dir(args.steam_dir)
    if steam_running() and not args.yes:
        if args.close_steam:
            print("Closing Steam...")
            if not close_steam(steam):
                raise SteamcaseError("Steam did not close. Close it yourself and retry.")
        else:
            print("Steam seems to be running. Close it first (Steam > Exit), or pass --close-steam.")
            if input("Copy anyway? [y/N] ").strip().lower() != "y":
                raise SteamcaseError("Cancelled.")
    r = apply_covers(steam, args.covers, args.user)
    print("Steam account:", r["account_name"], "(folder %s)" % r["account"], "\nGrid folder:", r["grid"])
    if r["applied"]:
        print("Applied %d covers (%d replaced older files, %d already up to date). Backup: %s" % (r["applied"], r["replaced"], r["unchanged"], r["backup"]))
    else:
        print("Nothing to change: all %d covers were already in Steam." % r["unchanged"])
    print("Start Steam to see them. A custom artwork set by hand in Steam may override these.")
    print("To undo: python steamcase.py restore")


def cmd_run(args):
    args.covers = args.out
    cmd_make(args)
    cmd_apply(args)


def cmd_restore(args):
    steam = steam_dir(args.steam_dir)
    backups = list_backups(steam, args.user)
    if not backups:
        raise SteamcaseError("No backups found.")
    if args.backup and os.path.basename(args.backup) != args.backup:
        raise SteamcaseError("--backup takes just the folder name (like grid_backup_20260101_120000), not a path.")
    target = os.path.join(os.path.dirname(backups[0]), args.backup) if args.backup else backups[0]
    if steam_running() and not args.yes:
        print("Steam seems to be running. Close it first so it picks the files up on next start.")
        if input("Restore anyway? [y/N] ").strip().lower() != "y":
            raise SteamcaseError("Cancelled.")
    n = restore_backup(steam, target, args.user)
    left = len(list_backups(steam, args.user))
    print("Restored from %s (%d files). %d older backup%s left; run restore again to go one step further back." % (target, n, left, "" if left == 1 else "s"))


def main():
    ap = argparse.ArgumentParser(description="Steam 'physical case' covers for your library.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, make=False, apply_=False):
        p.add_argument("--steam-dir", help="Steam folder (auto-detected by default)")
        if make:
            p.add_argument("--library", metavar="JSON", help="whole-library list saved from " + LIBRARY_JSON_URL)
            p.add_argument("--out", default="covers", help="where covers are written (default: ./covers)")
        if apply_:
            p.add_argument("--covers", default="covers", help="folder with covers (default: ./covers)")
            p.add_argument("--user", help="Steam account folder id inside userdata/ (auto: most recent login)")
            p.add_argument("--yes", action="store_true", help="don't ask even if Steam is running")
            p.add_argument("--close-steam", action="store_true", help="close Steam automatically before copying")

    p = sub.add_parser("list", help="show detected games"); common(p, make=True); p.set_defaults(fn=cmd_list)
    for name, fn in (("make", cmd_make), ("run", cmd_run)):
        p = sub.add_parser(name, help=name + " covers" if name == "make" else "make + apply")
        common(p, make=True, apply_=(name == "run"))
        p.add_argument("--only", type=int, nargs="+", metavar="APPID", help="only these app IDs")
        p.add_argument("--force", action="store_true", help="rebuild covers that already exist")
        p.add_argument("--skip-auto-art", action="store_true", help=AUTO_ART_HELP)
        p.set_defaults(fn=fn)
    p = sub.add_parser("apply", help="copy covers into Steam"); common(p, apply_=True); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("restore", help="undo an apply (newest backup by default)")
    p.add_argument("--steam-dir"); p.add_argument("--user"); p.add_argument("--yes", action="store_true")
    p.add_argument("--backup", help="backup folder name (see userdata/<id>/config/)")
    p.set_defaults(fn=cmd_restore)
    args = ap.parse_args()
    try:
        args.fn(args)
    except SteamcaseError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
