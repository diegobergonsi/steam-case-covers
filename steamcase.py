#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
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
import argparse, completion, filecmp, functools, json, os, re, shutil, socket, ssl, struct, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    from PIL.PngImagePlugin import PngInfo
except ImportError:
    Image = ImageChops = ImageDraw = ImageFilter = PngInfo = None

try:
    import certifi                      # a bundled set of trusted certificates (the packaged app's own Python may not find the system's)
except ImportError:
    certifi = None

for _s in (sys.stdout, sys.stderr):          # game names may hold non-ASCII; never crash a legacy console
    if _s is not None and hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))   # _MEIPASS: inside a PyInstaller bundle
FRAME = os.path.join(HERE, "assets", "frame.png")
DEFAULT_ART = os.path.join(HERE, "assets", "default_art.png")     # original artwork, only used for the colour preview
FAMILY_CORNER = os.path.join(HERE, "assets", "family_corner.png")    # green triangle and icon, laid over the frame for games from the Steam Family library
COMPLETION_OVERLAY = os.path.join(HERE, "assets", "completion_overlay.png")    # rosette and "100% Complete" ribbon, laid over the covers of games with every achievement
CASES = ("ribbon", "gold-case", "gold-border")           # the case of a 100% cover: the marks only, the marks on a gold case, the marks inside a gold border
MARKS = ("full", "rosette")                              # the marks: the rosette and the ribbon, or the rosette alone
TREATMENTS = ("ribbon", "gold-case", "gold-border", "rosette", "gold-case-rosette", "gold-border-rosette")    # how a 100% cover looks: a case and its marks (see compose_treatment)
ROSETTE_ROWS = 450                                       # the rosette-only marks are the overlay above this row; the ribbon sits below it
GOLD_HUE = 176                              # the gold of the colour swatches (#c89817), used whole for the "gold-case" treatment
BORDER = 14                                 # width of the "gold-border" treatment's border, in cover pixels
DONE_CHUNK = "steamcase-done"               # PNG note naming a cover's treatment; plain covers have none
HUE_SWATCHES = (0, 42, 84, 134, 176, 276)           # ready-made case colours, as degrees of hue turned from the original blue (violet, magenta, red, orange, green)
NEUTRAL_SWATCHES = (("Black", 0, 14), ("Graphite", 0, 34), ("Silver", 0, 78))    # ready-made greys: (name, colourfulness, brightness), hue does not matter
FAMILY_COLOR = (46, 125, 50)                # #2e7d32: the white icon on it has a contrast of 5.1:1
FAMILY_ICON_CONTRAST = 4.5                  # WCAG AA for normal text; the icon must never fall below it
WINDOW = (14, 96, 586, 872)                 # art window inside frame.png (x0, y0, x1, y1)
SIZE = (600, 900)
STEAMID64_BASE = 76561197960265728
CDN = "https://shared.fastly.steamstatic.com/store_item_assets/"
OLD_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/library_600x900_2x.jpg"
STORE_API = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1?"
LIBRARY_JSON_URL = "https://store.steampowered.com/dynamicstore/userdata/"
# The data page returns an EMPTY list (not an error) when you are logged out, and Steam lets the browser keep that
# answer for an hour (Cache-Control: max-age=3600). So the button opens Steam's login page with a redirect to the
# data page, using a NEW address every time (?cb=...): logged in already -> straight to the data; logged out -> log in,
# then fresh data, never the cached empty copy.
def library_login_url():
    return "https://store.steampowered.com/login/?redir=dynamicstore%2Fuserdata%2F%3Fcb%3D" + uuid.uuid4().hex[:10] + "&redir_ssl=1"
MAX_DOWNLOAD = 25 * 1024 * 1024          # a cover portrait is ~1 MB; anything bigger is not one
MAX_LIBRARY_FILE = 20 * 1024 * 1024      # a real library list is a few KB
MAX_APPS = 100_000                       # a real library has at most a few thousand apps
MAX_PIXELS = 30_000_000                  # portraits are ~1 MP; refuses decompression bombs
MAX_PACKAGEINFO = 16 * 1024 * 1024       # Steam's own package list is a few hundred KB
_PACKAGEINFO_MAGICS = (0x06565527, 0x06565528)
TOOL_NAMES = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|Steam Controller Configs)", re.I)
BACKUP_PREFIX = "grid_backup_"

# Shown next to the "skip blurry auto-art" option (GUI tooltip, CLI --help).
AUTO_ART_HELP = (
    "Some games, mostly older or small ones, have no real portrait on Steam. "
    "Steam builds a stand-in from the wide header image: the title banner sits in the "
    "middle of a blurred, stretched copy of itself, with lots of empty space. "
    "Tick this to skip those games and keep Steam's default art for them."
)
FAMILY_HELP = (
    "Games shared with you through Steam Family Sharing are in your library, but they are not on your own game list and are often not installed. "
    "With this switch on, only games installed on this computer get covers, so shared games that are not installed are left out. "
    "To include them, turn this off and load your game list: the app then finds the shared games in Steam's own files "
    "and marks their covers with a green corner."
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
_ssl_ctx = None


def _ssl_context():
    """TLS settings: the system's trusted certificates plus certifi's. Without certifi, the packaged Linux app
    looked in /usr/lib/ssl (a Debian path), found nothing on SteamOS and failed every HTTPS request."""
    global _ssl_ctx
    if _ssl_ctx is None:
        ctx = ssl.create_default_context()
        if certifi is not None:
            try:
                ctx.load_verify_locations(cafile=certifi.where())
            except Exception:
                pass
        _ssl_ctx = ctx
    return _ssl_ctx


def explain_error(exc):
    """A short human reason for a failed request."""
    text = str(exc)
    inner = getattr(exc, "reason", exc)
    if isinstance(inner, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        return "its security certificate could not be verified. Check that your computer's date and time are right and that your network isn't intercepting secure connections"
    if isinstance(exc, urllib.error.HTTPError):
        return "it answered with an error (HTTP %d)" % exc.code
    if isinstance(inner, socket.gaierror) or "Name or service not known" in text or "getaddrinfo" in text:
        return "no internet, or a DNS problem (the address could not be found)"
    if isinstance(inner, (socket.timeout, TimeoutError)) or "timed out" in text:
        return "the connection timed out"
    return (text or type(exc).__name__)[:120]


def check_network():
    """One tiny real request to Steam's store API. Returns (ok, message). Used by 'gui.py --check-network'."""
    try:
        q = json.dumps({"ids": [{"appid": 220}], "context": {"language": "english", "country_code": "US"}, "data_request": {}})
        json.loads(http_get(STORE_API + urllib.parse.urlencode({"input_json": q}), tries=1))
        return True, "Steam's servers answered."
    except Exception as e:
        return False, explain_error(e)


ALLOW_LOCAL_HTTP = False         # only the tests switch this on (they talk to a throw-away local server)
_opener = None


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _require_https(url):
    """Every address the app opens must be https (no file:// and no unencrypted http://)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https":
        return
    if ALLOW_LOCAL_HTTP and parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost"):
        return
    raise SteamcaseError("Refusing to open an address that is not https: %s" % url[:80])


def _get_opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(_HttpsOnlyRedirects, urllib.request.HTTPSHandler(context=_ssl_context()))
    return _opener


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
            _require_https(url)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 steamcase"})
            with _get_opener().open(req, timeout=30) as r:
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


REPO = "diegobergonsi/steam-case-covers"
_TAG = re.compile(r"^v([0-9]{1,4})\.([0-9]{1,4})\.([0-9]{1,4})$")


def _read_version():
    """The release tag stamped into this build (assets/version.txt, written by the release workflow); "dev" for source runs."""
    try:
        with open(os.path.join(HERE, "assets", "version.txt"), encoding="ascii") as fh:
            v = fh.read(40).strip()
        return v if _TAG.match(v) else "dev"
    except Exception:
        return "dev"


APP_VERSION = _read_version()


def version_tuple(tag):
    m = _TAG.match(tag) if isinstance(tag, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def check_for_update(current=None):
    """Ask GitHub for the newest published release (pre-releases count). Returns
    {"current", "latest", "newer", "url"}; "newer" is None when this build carries no version number (run from source).
    The page address is built here from a tag that matched a strict pattern, never taken from the server's answer.
    Nothing is downloaded or installed. Raises SteamcaseError when GitHub cannot be reached or answers nonsense."""
    current = APP_VERSION if current is None else current
    try:
        data = json.loads(http_get("https://api.github.com/repos/%s/releases?per_page=30" % REPO, tries=2).decode("utf-8", "replace"))
    except SteamcaseError:
        raise
    except (ValueError, RecursionError, MemoryError, UnicodeError):
        raise SteamcaseError("GitHub's answer was not understood. Try again later.")
    except Exception as e:
        raise SteamcaseError("Could not reach GitHub: %s" % explain_error(e))
    best = None
    for r in data if isinstance(data, list) else []:
        tag = r.get("tag_name") if isinstance(r, dict) and not r.get("draft") else None
        v = version_tuple(tag)
        if v and (best is None or v > best[0]):
            best = (v, tag)
    if not best:
        raise SteamcaseError("No releases found on GitHub.")
    mine = version_tuple(current)
    return {"current": current, "latest": best[1], "newer": None if mine is None else best[0] > mine,
            "url": "https://github.com/%s/releases/tag/%s" % (REPO, best[1])}


def _replace(src, dst, tries=6):
    """os.replace, retried a few times. On Windows it fails for a moment when something else (antivirus, a second copy of this app)
    has the destination open; waiting a little almost always clears it."""
    for n in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if n == tries - 1:
                raise
            time.sleep(0.05 * (n + 1))


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


def _load_library_json(json_path):
    path = os.path.expanduser(json_path)
    try:
        if os.path.getsize(path) > MAX_LIBRARY_FILE:
            raise SteamcaseError("That file is far too big to be your game list (over %d MB)." % (MAX_LIBRARY_FILE >> 20))
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except SteamcaseError:
        raise
    except (OSError, ValueError, RecursionError, MemoryError, UnicodeError) as e:
        raise SteamcaseError("Could not read %s as a game list (%s)." % (os.path.basename(path), type(e).__name__))


def owned_ids(json_path):
    d = _load_library_json(json_path)
    ids = d.get("rgOwnedApps") if isinstance(d, dict) else None
    if isinstance(ids, list) and not ids and "rgOwnedPackages" in d:
        raise SteamcaseError("That file has no games in it. This usually means you were not logged in to Steam in your browser when you saved it. "
                             "Click “Download your userdata.json” again, log in when Steam asks, then save the page. "
                             "If the page you see shows no games even though you are logged in, refresh it (F5, or Cmd+R on a Mac) before saving.")
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


def owned_packages(json_path):
    """Package ids from the library file ('rgOwnedPackages'). Free, bundled and old games belong to a package without being in 'rgOwnedApps'.
    [] when the file has none."""
    d = _load_library_json(json_path)
    ids = d.get("rgOwnedPackages") if isinstance(d, dict) else None
    if not isinstance(ids, list):
        return []
    return [i for i in ids if type(i) is int and 0 <= i < 2 ** 32][:MAX_APPS]


def _read_binary_kv(data, pos, depth=0):
    """One Valve binary key-value tree starting at data[pos]: (dict, position after it). Raises on anything it does not understand."""
    if depth > 8:
        raise ValueError("tree too deep")
    out = {}
    while True:
        kind = data[pos]
        pos += 1
        if kind == 8:
            return out, pos
        end = data.index(b"\0", pos)
        key = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        if kind == 0:
            out[key], pos = _read_binary_kv(data, pos, depth + 1)
        elif kind == 1:
            end = data.index(b"\0", pos)
            out[key] = data[pos:end].decode("utf-8", "replace")
            pos = end + 1
        elif kind in (2, 4, 5):
            out[key] = struct.unpack_from("<i", data, pos)[0]
            pos += 4
        elif kind in (3, 6):
            out[key] = struct.unpack_from("<I" if kind == 6 else "<f", data, pos)[0]
            pos += 4
        elif kind in (7, 10):
            out[key] = struct.unpack_from("<Q", data, pos)[0]
            pos += 8
        else:
            raise ValueError("unknown value type %d" % kind)


def package_apps(steam, package_ids):
    """Every app id inside the given packages, read from Steam's own appcache/packageinfo.vdf.
    None when that file is missing, not in a layout we know, or not about these packages (fewer than 90% of them are in it, as when Steam is
    logged into another account): callers then treat ownership as unknown."""
    path = os.path.join(steam, "appcache", "packageinfo.vdf")
    wanted = set(package_ids)
    try:
        if os.path.getsize(path) > MAX_PACKAGEINFO:
            return None
        with open(path, "rb") as f:
            data = f.read()
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic not in _PACKAGEINFO_MAGICS:
            return None
        pos, apps, seen = 8, set(), 0              # magic and universe come first, then one entry per package
        while True:
            pid = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            if pid == 0xFFFFFFFF:
                return apps if seen >= 0.9 * len(wanted) else None
            pos += 24 + (8 if magic == 0x06565528 else 0)        # hash (20), change number (4), and a token (8) in the newer header
            tree, pos = _read_binary_kv(data, pos)
            entry = tree.get(str(pid))
            if pid in wanted and isinstance(entry, dict):
                seen += 1
                ids = entry.get("appids")
                if isinstance(ids, dict):
                    apps.update(v for v in ids.values() if type(v) is int and 0 < v < 2 ** 32)
    except (OSError, ValueError, struct.error, IndexError, RecursionError, MemoryError):
        return None


def find_family(steam, owned, package_ids):
    """App ids that are in your Steam library through Family Sharing: Steam keeps art for them (appcache/librarycache) or they are installed,
    but they are neither in your owned apps nor inside one of your owned packages (free, bundled and old games are, so they are yours).
    Empty when ownership cannot be told (no package data): then nothing is guessed."""
    if not package_ids:
        return set()
    mine = package_apps(steam, package_ids)
    if mine is None:
        return set()
    found = set(installed_games(steam))
    cache = os.path.join(steam, "appcache", "librarycache")
    try:
        for n in os.listdir(cache):
            p = os.path.join(cache, n)
            if re.fullmatch(r"[0-9]{1,10}", n) and os.path.isdir(p) and not os.path.islink(p):
                found.add(int(n))
    except OSError:
        pass
    return set(sorted(i for i in found - mine - set(owned) if 0 < i < 2 ** 32)[:MAX_APPS])


def load_library(steam, library_json=None):
    """(games, family): games is {appid: name or None} for installed games, every owned app when library_json is given, and your family games;
    family is the set of those that came from the Steam Family library (always empty without library_json: ownership is unknown then)."""
    games = installed_games(steam)
    family = set()
    if library_json:
        owned = owned_ids(library_json)
        for i in owned:
            games.setdefault(i, None)
        family = find_family(steam, owned, owned_packages(library_json))
        for i in family:
            games.setdefault(i, None)
    return games, family


def load_games(steam, library_json=None):
    """{appid: name or None}: installed games, plus every owned app (and family game) when library_json is given."""
    return load_library(steam, library_json)[0]


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


def list_accounts(steam):
    """[(folder id, display name)] for every Steam account that has a userdata folder, the one pick_account() would choose first."""
    base = os.path.join(steam, "userdata")
    accs = [d for d in os.listdir(base) if re.fullmatch(r"[0-9]+", d) and d != "0"] if os.path.isdir(base) else []
    first = pick_account(steam) if accs else None
    accs.sort(key=lambda a: (a != first, a))
    return [(a, account_label(steam, a)) for a in accs]


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
# On Windows a windowed app has no console, so every console program it starts (tasklist) would flash a black window and take the focus.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)         # 0 on Linux and macOS, where the attribute does not exist


def steam_running():
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run([_tool("tasklist")], capture_output=True, text=True, creationflags=_NO_WINDOW).stdout.lower()
            return "steam.exe" in out
        out = subprocess.run([_tool("ps"), "-A", "-o", "comm="], capture_output=True, text=True).stdout.lower()
        # Linux prints just the name ("steam"); macOS prints the whole path (".../Steam.app/Contents/MacOS/steam_osx")
        return any(os.path.basename(l.strip()) in ("steam", "steam_osx", "steamwebhelper") for l in out.splitlines())
    except Exception:
        return False


def _mac_steam_binary():
    for base in ("/Applications", os.path.expanduser("~/Applications")):
        p = os.path.join(base, "Steam.app", "Contents", "MacOS", "steam_osx")
        if os.path.exists(p):
            return p
    return None


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
            exe = _mac_steam_binary()
            if exe:                                                  # Steam's own "-shutdown" (works without any permission prompt)
                subprocess.Popen([exe, "-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
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
def store_items(appids, log=None, cancelled=None, errors=None):
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
            if errors is not None:
                errors.append(e)
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
def hue_shift(hue):
    """How far `hue` degrees turns Pillow's hue band (0..255). Neighbouring whole degrees can share a step (1 and 2 do): the covers are then identical."""
    return round((hue % 360) * 256 / 360) % 256


def tone_key(hue, sat=100, val=100):
    """What decides how a case looks: (hue step, sat, val), tone clamped to 0..100. Without colour or without light the hue shows nothing, so it counts as 0."""
    sat, val = min(max(sat, 0), 100), min(max(val, 0), 100)
    return (0 if sat == 0 or val == 0 else hue_shift(hue), sat, val)


def same_colour(a, b):
    """True if two case colours, (hue, sat, val) or None when unknown, look the same."""
    return a is not None and b is not None and tone_key(*a) == tone_key(*b)


def recolor_frame(frame, hue, sat=100, val=100):
    """The frame with its hue turned by `hue` degrees, then its colourfulness and brightness scaled to `sat` and `val` (0 to 100, 100 = as drawn).
    Brightness only changes the coloured parts (weighted by their own saturation), so the white logo and text and the transparency stay; at 0 degrees,
    100 and 100 the frame itself comes back (the original blue, byte for byte). Colourfulness 0 gives greys: dark ones are black, light ones silver."""
    shift = hue_shift(hue)
    sat, val = min(max(sat, 0), 100), min(max(val, 0), 100)
    if not shift and sat == 100 and val == 100:
        return frame
    r, g, b, a = frame.split()
    h, s, v = Image.merge("RGB", (r, g, b)).convert("HSV").split()
    if shift:
        h = h.point(lambda x: (x + shift) % 256)
    weight = [min(1.0, x / 255 / 0.02) for x in range(256)]            # 0 on the pure white parts, 1 on anything with a trace of colour
    new_s = s.point([round(x * sat / 100) for x in range(256)])               # white parts have none to lose
    factor = s.point([round(255 * (1 - w * (1 - val / 100))) for w in weight])
    v = ImageChops.multiply(v, factor)
    return Image.merge("RGBA", (*Image.merge("HSV", (h, new_s, v)).convert("RGB").split(), a))


def load_frame(hue=0, family=False, *, sat=100, val=100):
    """The case frame in the wanted colour and tone; with family=True the green corner of the Steam Family library is laid over it (never recoloured)."""
    frame = recolor_frame(Image.open(FRAME).convert("RGBA"), hue, sat, val)
    if family:
        frame = Image.alpha_composite(frame, Image.open(FAMILY_CORNER).convert("RGBA"))
    return frame


def case_color(hue, sat=100, val=100):
    """'#rrggbb' of the case's middle colour (the original is #1636c8) turned by `hue` degrees and toned by `sat` and `val`: for painting swatches and the colour sliders."""
    sat, val = min(max(sat, 0), 100), min(max(val, 0), 100)
    return _case_color(0 if sat == 0 or val == 0 else hue % 360, sat, val)           # the hue shows nothing without colour or light: one entry for all


@functools.lru_cache(maxsize=8192)                                  # the sliders ask for a few hundred colours per repaint
def _case_color(hue, sat, val):
    return "#%02x%02x%02x" % recolor_frame(Image.new("RGBA", (1, 1), (0x16, 0x36, 0xc8, 255)), hue, sat, val).getpixel((0, 0))[:3]


HUE_CHUNK = "steamcase-hue"
TONE_CHUNK = "steamcase-tone"                 # "<sat> <val>"; covers without it are in full tone


def _compose(art, frame):
    """A portrait scaled to cover the frame's art window (centre-cropped), with the frame on top. Real covers and the window's preview both use this."""
    x0, y0, x1, y1 = WINDOW
    ww, wh = x1 - x0, y1 - y0
    s = max(ww / art.width, wh / art.height)                      # scale to cover, then center-crop
    art = art.resize((max(ww, round(art.width * s)), max(wh, round(art.height * s))), Image.LANCZOS)
    cx, cy = (art.width - ww) // 2, (art.height - wh) // 2
    art = art.crop((cx, cy, cx + ww, cy + wh))
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.paste(art, (x0, y0))
    return Image.alpha_composite(canvas, frame)


def preview_cover(hue=0, family=False, *, sat=100, val=100, treatment=None):
    """What a cover looks like in this case colour and tone, made from the default art that ships with the app (the window shows it before any game's art exists).
    With a `treatment` (one of TREATMENTS) it shows the cover of a game with every achievement unlocked."""
    hue, sat, val = treatment_colour(treatment, (hue, sat, val))
    with Image.open(DEFAULT_ART) as im:
        return finish_treatment(_compose(im.convert("RGBA"), load_frame(hue, family, sat=sat, val=val)), treatment)


def compose_treatment(case, marks):
    """The treatment (one of TREATMENTS) for a `case` (one of CASES) and its `marks` (one of MARKS). Full marks keep the plain name of the case."""
    if case not in CASES or marks not in MARKS:
        raise ValueError("unknown case or marks: %r, %r" % (case, marks))
    if marks == "full":
        return case
    return "rosette" if case == "ribbon" else case + "-rosette"


def split_treatment(treatment):
    """(case, marks) of a treatment, the inverse of compose_treatment. ValueError for anything that is not one of TREATMENTS."""
    for case in CASES:
        for marks in MARKS:
            if treatment == compose_treatment(case, marks):
                return case, marks
    raise ValueError("unknown treatment: %r" % (treatment,))


def is_gold_case(treatment):
    """True for the treatments whose case is the gold one (always False for None or an unreadable note)."""
    return treatment in TREATMENTS and split_treatment(treatment)[0] == "gold-case"


def treatment_colour(treatment, colour):
    """The case colour (hue, sat, val) a cover is built in: gold for the "gold-case" treatments, the user's `colour` otherwise."""
    return (GOLD_HUE, 100, 100) if is_gold_case(treatment) else colour


@functools.lru_cache(maxsize=1)
def _completion_overlay():
    with Image.open(COMPLETION_OVERLAY) as im:
        return im.convert("RGBA")


@functools.lru_cache(maxsize=1)
def _rosette_overlay():
    """The overlay without the ribbon: everything from ROSETTE_ROWS down is cleared, which leaves the rosette on the platform badges."""
    marks = _completion_overlay().copy()
    marks.paste((0, 0, 0, 0), (0, ROSETTE_ROWS, marks.width, marks.height))
    return marks


@functools.lru_cache(maxsize=1)
def _gold_border():
    """The rounded gold plate of the "gold-border" treatment: a vertical gradient, its corners rounded to follow the case's (drawn at 3x for smooth edges)."""
    w, h, k = SIZE[0], SIZE[1], 3
    top, bottom = (0xff, 0xe2, 0x78), (0xc4, 0x88, 0x16)
    column = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        column.putpixel((0, y), tuple(round(top[i] * (1 - t) + bottom[i] * t) for i in range(3)))
    plate = column.resize(SIZE).convert("RGBA")
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w * k - 1, h * k - 1], radius=(24 + BORDER) * k, fill=255)
    plate.putalpha(mask.resize(SIZE, Image.LANCZOS))
    return plate


def finish_treatment(cover, treatment):
    """`cover` (the finished 600 x 900 composition) with the marks of a 100% game: the rosette over the platform badges and, unless the
    treatment is a rosette-only one, the ribbon at the bottom, kept inside the case's own outline. For "gold-border" the whole cover is then shrunk by BORDER pixels
    on each side and set inside a gold border, so the marks stay on the art. No treatment: `cover` itself."""
    if treatment is None:
        return cover
    case, kind = split_treatment(treatment)
    marks = (_rosette_overlay() if kind == "rosette" else _completion_overlay()).copy()
    marks.putalpha(ImageChops.multiply(marks.getchannel("A"), cover.getchannel("A")))     # nothing reaches past the rounded case
    done = Image.alpha_composite(cover, marks)
    if case == "gold-border":
        plate = _gold_border().copy()
        plate.alpha_composite(done.resize((SIZE[0] - 2 * BORDER, SIZE[1] - 2 * BORDER), Image.LANCZOS), (BORDER, BORDER))
        done = plate
    return done


def cover_colour(path):
    """The case colour (hue, sat, val) a cover was made in, read from its PNG header without decoding the picture.
    Covers made before colours existed have no hue note and count as 0; those without a tone note count as full tone (100, 100).
    None if this is not a readable PNG, or if a note is not what we write (the hue a whole number from 0 to 359, the tone two whole
    numbers from 0 to 100 split by a space): the cover is then rebuilt rather than taken for blue."""
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_DOWNLOAD:
            return None
        with Image.open(path, formats=["PNG"]) as im:
            return _noted_colour(im.info)
    except Exception:
        return None


def _noted_colour(info):
    """The case colour (hue, sat, val) the notes in a PNG's `info` give (see cover_colour), or None if a note is garbled."""
    hue, tone = info.get(HUE_CHUNK), info.get(TONE_CHUNK)
    if hue is None:
        hue = 0
    elif isinstance(hue, str) and re.fullmatch(r"0|[1-9][0-9]{0,2}", hue) and int(hue) < 360:
        hue = int(hue)
    else:
        return None
    if tone is None:
        return (hue, 100, 100)
    m = re.fullmatch(r"(0|[1-9][0-9]?|100) (0|[1-9][0-9]?|100)", tone) if isinstance(tone, str) else None
    return (hue, int(m.group(1)), int(m.group(2))) if m else None


def cover_hue(path):
    """The case hue of a cover (see cover_colour), or None when unknown."""
    colour = cover_colour(path)
    return colour[0] if colour else None


def cover_treatment(path):
    """The treatment (one of TREATMENTS) a cover was made with, read from its PNG header without decoding the picture; None for a plain cover.
    False if this is not a readable PNG or the note is not exactly one we write: the cover is then rebuilt."""
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_DOWNLOAD:
            return False
        with Image.open(path, formats=["PNG"]) as im:
            done = im.info.get(DONE_CHUNK)
    except Exception:
        return False
    return done if done is None or done in TREATMENTS else False


def build_cover(portrait_path, out_path, frame, hue=0, *, sat=100, val=100, treatment=None):
    """Write the cover of one portrait into `out_path`, with its colour notes and, for a 100% game, its `treatment` and treatment note.
    `frame` is already in the colour the cover is made in (for "gold-case": the gold frame, with hue, sat, val saying gold)."""
    if Image is None:
        raise SteamcaseError("Pillow is missing. Install it with:  python -m pip install pillow")
    with Image.open(portrait_path, formats=["PNG", "JPEG", "WEBP"]) as im:        # never let Pillow guess (EPS, TIFF, ... have a worse track record)
        if im.width * im.height > MAX_PIXELS:                  # header check only; nothing is decoded yet
            raise SteamcaseError("Image is too large to be a game portrait (%dx%d)." % im.size)
        art = im.convert("RGBA")
    cover = finish_treatment(_compose(art, frame), treatment)
    part = _tmp(out_path, "part")                  # write aside, then rename: a crash never leaves a half-written cover
    note = PngInfo()
    note.add_text(HUE_CHUNK, str(hue % 360))                   # lets make_covers tell what colour an existing cover is without decoding it
    note.add_text(TONE_CHUNK, "%d %d" % (min(max(sat, 0), 100), min(max(val, 0), 100)))
    if treatment is not None:
        note.add_text(DONE_CHUNK, treatment)                   # plain covers carry no note, as before treatments existed
    cover.save(part, format="PNG", optimize=True, pnginfo=note)
    _replace(part, out_path)


# ---------- make ----------
def _wanted_look(appid, path, colour, completed, treatment):
    """(treatment, case colour) the cover of `appid` at `path` should have (see make_covers). Without a page (`completed` None)
    a cover keeps the treatment it was made with; a garbled note counts as none, so the cover is rebuilt plain."""
    if completed is not None:
        target = treatment if appid in completed else None
    else:
        target = cover_treatment(path) or None
    return target, treatment_colour(target, colour)


def make_covers(games, out, only=None, force=False, skip_auto_art=False, progress=None, cancelled=None, log=None, family=None, hue=0, sat=100, val=100,
                completed=None, treatment=None):
    """Build a cover per game into `out`.

    progress(done, total, appid, name, status)  status: ok | exists | skipped | noart | failed
    cancelled() -> True stops early.
    family: set of appids that come from the Steam Family library; those covers are drawn with the green-corner frame.
    hue, sat, val: the case colour: degrees to turn it from the original blue (0), then its colourfulness and brightness (0 to 100, 100 = as drawn).
    completed: set of appids with every achievement unlocked (from the saved games page), or None when no page is loaded.
    treatment: one of TREATMENTS (a case and its marks, see compose_treatment) for those games, or None ("No special case": they get plain covers).
    Without a page each existing cover keeps the treatment it was made with. A "gold-case" cover is made in gold whatever the colour asked.
    A cover that exists in another colour or with another treatment is rebuilt, one that already looks right is kept
    (the hue means nothing at 0 sat or 0 val). Apps in `completed` that are not in `games` are ignored.
    progress counts only items that can become a cover (DLC, soundtracks and tools are not counted).
    Returns {"ok", "skipped", "not_games" (DLC, tools...), "unlisted" (apps Steam no longer lists), "missing": [(appid, name)] (Steam has no art),
    "failed": [(appid, name)] (download problem), "cancelled", "files": [cover paths of this run],
    "family": how many covers were drawn with the family frame in this run (an existing plain cover is kept unless force is set),
    "completed": how many of "files" carry a treatment, kept ones included}.
    """
    if Image is None:
        raise SteamcaseError("Pillow is missing. Install it with:  python -m pip install pillow")
    if treatment is not None and treatment not in TREATMENTS:
        raise ValueError("unknown treatment: %r" % (treatment,))        # a note nobody can read back would have the cover rebuilt on every run
    os.makedirs(out, exist_ok=True)
    hue %= 360
    sat, val = min(max(sat, 0), 100), min(max(val, 0), 100)
    family = set(family or ())
    frames = {}                                 # (look of the colour, family?) -> frame: each one is made once per run

    def frame_for(colour, is_family):
        key = (tone_key(*colour), is_family)
        if key not in frames:
            frames[key] = load_frame(colour[0], is_family, sat=colour[1], val=colour[2])
        return frames[key]

    frame_for((hue, sat, val), False)           # a missing frame.png fails here, before any download
    if treatment is not None or completed is None:
        _completion_overlay()                   # so does a missing overlay: otherwise every 100% cover would count as a failed download

    ids = sorted(games)
    if only:
        ids = [i for i in ids if i in set(only)]
    if log:
        log("Looking up %d apps on Steam's store..." % len(ids))
    errs = []
    info = store_items(ids, log, cancelled, errs)
    if ids and not info and not (cancelled and cancelled()):
        why = explain_error(errs[-1]) if errs else "no answer, check your internet connection"
        raise SteamcaseError("Could not reach Steam's servers: %s." % why.rstrip("."))
    res = {"ok": 0, "skipped": 0, "not_games": 0, "unlisted": 0, "missing": [], "failed": [], "cancelled": False, "files": [], "family": 0, "completed": 0}
    todo = []                                   # only items that can become a cover count towards the progress
    for appid in ids:
        it = info.get(appid) or {}
        known = games[appid] or it.get("name")
        if it.get("type", 0) not in (0, None) or TOOL_NAMES.match(known or ""):
            res["skipped"] += 1
            res["not_games"] += 1               # DLC, soundtracks, tools, demos
        elif not known:
            res["skipped"] += 1
            res["unlisted"] += 1                # Steam no longer lists it (delisted or removed): no name, almost never any art
        else:
            todo.append(appid)
    ids = todo
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
        target, colour = _wanted_look(appid, dest, (hue, sat, val), completed, treatment)
        if os.path.exists(dest) and not force and same_colour(cover_colour(dest), colour) and cover_treatment(dest) == target:
            res["ok"] += 1
            res["completed"] += target is not None
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
            is_family = appid in family
            build_cover(tmp, dest, frame_for(colour, is_family), colour[0], sat=colour[1], val=colour[2], treatment=target)
            res["ok"] += 1
            res["family"] += is_family
            res["completed"] += target is not None
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
def covers_in_other_look(covers_dir, hue, sat=100, val=100, completed=None, treatment=None):
    """True if make_covers with this colour, `completed` and `treatment` would rebuild a cover already in the folder (stops at the first one):
    one in another case colour (a "gold-case" cover is compared as gold) or with another treatment. Covers whose colour notes are unreadable are not counted."""
    try:
        names = os.listdir(covers_dir)
    except OSError:
        return False
    for n in names:
        appid = appid_of(n)
        if n.lower().endswith(".png") and appid is not None:
            path = os.path.join(covers_dir, n)
            c = cover_colour(path)
            if c is None:
                continue
            target, colour = _wanted_look(int(appid), path, (hue, sat, val), completed, treatment)       # appid_of gives text; `completed` holds numbers
            if not same_colour(c, colour) or cover_treatment(path) != target:
                return True
    return False


def covers_in_other_colour(covers_dir, hue, sat=100, val=100):
    """True if the covers folder already holds a cover made in a different case colour than (`hue`, `sat`, `val`) (stops at the first one).
    No page loaded: each cover keeps its treatment, so a "gold-case" cover stays gold and is not counted (see covers_in_other_look)."""
    return covers_in_other_look(covers_dir, hue, sat, val)


def existing_cover_colour(covers_dir):
    """The case colour (hue, sat, val) of the covers already in the folder (that of the first one by name), or None when there are none.
    "gold-case" covers are skipped: their notes say gold, not the colour the user chose."""
    try:
        names = sorted(os.listdir(covers_dir))
    except OSError:
        return None
    for n in names:
        if n.lower().endswith(".png") and appid_of(n) is not None:
            path = os.path.join(covers_dir, n)
            c = cover_colour(path)
            if c is not None and not is_gold_case(cover_treatment(path)):
                return c
    return None


def mixed_cover_colours(covers_dir):
    """True if the covers folder holds covers in more than one case colour (what an interrupted colour change leaves behind).
    "gold-case" covers are skipped (they are always gold, see existing_cover_colour) and so are covers whose notes are unreadable."""
    try:
        names = os.listdir(covers_dir)
    except OSError:
        return False
    seen = set()
    for n in names:
        if n.lower().endswith(".png") and appid_of(n) is not None:
            path = os.path.join(covers_dir, n)
            c = cover_colour(path)
            if c is not None and not is_gold_case(cover_treatment(path)):
                seen.add(tone_key(*c))
                if len(seen) > 1:
                    return True
    return False


def _safe_copy(src, dst):
    """Copy src to dst atomically. If dst is a symlink, the link itself is replaced, never the file it points to."""
    tmp = _tmp(dst)
    try:
        shutil.copy2(src, tmp)
        _replace(tmp, dst)
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
    Steam shows <appid>p.jpg before <appid>p.png (tested), so a leftover .jpg (art set by hand in Steam) is moved into the backup too.
    Returns {"account", "account_name", "grid", "applied", "unchanged", "replaced", "jpg_moved", "backup"}.
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
        work, added, replaced, moved = [], [], [], []
        for f in covers:
            n = "%sp.png" % appid_of(f)
            dest = os.path.join(grid, n)
            js = ["%sp.%s" % (appid_of(f), e) for e in OTHER_EXT if _is_plain_file(os.path.join(grid, "%sp.%s" % (appid_of(f), e)))]
            moved += js                                          # they would hide our cover: Steam prefers them over .png
            same = os.path.exists(dest) and filecmp.cmp(f, dest, shallow=False)
            if same:
                if js:
                    work.append((None, n))                       # our cover is there, only the .jpg has to go
                continue                                         # identical already: no need to touch or back it up
            if os.path.exists(dest):
                replaced.append(n)
            else:
                added.append(n)
            work.append((f, n))
        if not work:
            return dict(info, applied=0, unchanged=len(covers), replaced=0, jpg_moved=0, backup=None)
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
                json.dump({"added": added, "replaced": replaced, "moved": moved}, fh)
            for j in moved:
                os.replace(os.path.join(grid, j), os.path.join(backup, j))   # a move: the user's own art is kept, not deleted
            for f, n in work:
                if f:
                    _safe_copy(f, os.path.join(grid, n))
        except OSError as e:
            try:
                _undo(grid, backup, {"added": added, "replaced": replaced, "moved": moved})     # leave Steam's art exactly as it was (we already hold the lock)
            except Exception:
                raise SteamcaseError("Could not write to Steam's artwork folder (%s), and the old artwork could not be put back. "
                                     "It is safe in the backup folder %s (use Restore, or copy the files back by hand)." % (e, backup))
            shutil.rmtree(backup, ignore_errors=True)                           # a failed run must not leave a backup behind
            raise SteamcaseError("Could not write to Steam's artwork folder (%s). Nothing was changed." % e)
        return dict(info, applied=len(work), unchanged=len(covers) - len(work), replaced=len(replaced), jpg_moved=len(moved), backup=backup)


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


_frame_ref = None


def _shape(strip):
    """Saturation, brightness and transparency of a strip of a cover (for covers without a tone note). The hue is left out on purpose:
    a cover from before tones existed is in full tone, and turning only its hue still leaves it ours."""
    r, g, b, a = strip.split()
    _, s, v = Image.merge("RGB", (r, g, b)).convert("HSV").split()
    return s, v, a


def _frame_regions():
    """The parts of a cover that are pure frame (banner on top, lip at the bottom), from frame.png and from the family frame.
    Each reference is (shape, mask): mask is None, or marks the pixels worth comparing (the family corner's soft edge is left out: it
    blends the green with the banner, so its saturation depends on the colour the case was turned to). The mask comes last on its own."""
    global _frame_ref
    if _frame_ref is None:
        top, bot = (0, 0, SIZE[0], WINDOW[1]), (0, WINDOW[3], SIZE[0], SIZE[1])
        plain, family = load_frame(0), load_frame(0, True)          # the family frame differs from the plain one only in the corner triangle
        edge = Image.open(FAMILY_CORNER).convert("RGBA").getchannel("A").crop(top).point(lambda a: 255 if a in (0, 255) else 0)
        _frame_ref = (top, bot, ((_shape(plain.crop(top)), None), (_shape(family.crop(top)), edge)), (_shape(plain.crop(bot)), None), edge)
    return _frame_ref


def _same_shape(a, ref):
    """Same transparency exactly, and saturation and brightness within 2 levels (turning the hue moves them by at most 1). Hue is not
    compared, so this only holds for covers in full tone: a grey case has other saturation and brightness and never passes."""
    (s, v, alpha), mask = ref
    if a[2].tobytes() != alpha.tobytes():
        return False
    for x, y in ((a[0], s), (a[1], v)):
        diff = ImageChops.difference(x, y)
        if mask is not None:
            diff = ImageChops.darker(diff, mask)
        if diff.getextrema()[1] > 2:
            return False
    return True


@functools.lru_cache(maxsize=16)                                    # about 0.76 MB an entry, and the tone comes from a file's note
def _tone_strips(key):
    """_expected_strips for one tone_key: covers that look the same share one set of strips."""
    step, sat, val = key                                            # step * 360 / 256 degrees turns the hue by exactly `step` again
    top, bot, _, _, edge = _frame_regions()
    blank = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    plain, family = (Image.alpha_composite(blank, load_frame(step * 360 / 256, f, sat=sat, val=val)) for f in (False, True))   # as _compose lays it down
    return ((plain.crop(top), None), (family.crop(top), Image.merge("RGBA", (edge,) * 4))), (plain.crop(bot), None)


def _expected_strips(hue, sat, val):
    """The banner (plain, and family with the corner's soft-edge mask) and the bottom strip exactly as a cover in this colour and tone has them."""
    return _tone_strips(tone_key(hue, sat, val))


def _same_pixels(strip, ref):
    """Every RGBA channel within 2 levels of the reference strip, outside the masked-off pixels."""
    want, mask = ref
    diff = ImageChops.difference(strip, want)
    if mask is not None:
        diff = ImageChops.darker(diff, mask)
    return max(hi for _, hi in diff.getextrema()) <= 2


@functools.lru_cache(maxsize=16)                                    # about 2.7 MB an entry; a library uses one or two colours, each plain and family
def _treated_reference(key, family):
    """(expected, mask) for a treated cover: key is (tone_key, treatment). The cover is made twice, from flat black and from flat white
    art, through the same steps as build_cover; the mask is 255 where both agree within 2 on every channel (frame, rosette, ribbon,
    border: nothing the game's art reaches) and 0 elsewhere, then pulled back 3 pixels from the art: the gold border's shrink (Lanczos)
    lets detailed art ring that far past where flat art reaches. Expected is halfway between the two, so real art lands within 1 of it."""
    (step, sat, val), treatment = key                               # step * 360 / 256 degrees turns the hue by exactly `step` again
    frame = load_frame(step * 360 / 256, family, sat=sat, val=val)
    black, white = (finish_treatment(_compose(Image.new("RGBA", SIZE, (c, c, c, 255)), frame), treatment) for c in (0, 255))
    widest = functools.reduce(ImageChops.lighter, ImageChops.difference(black, white).split())
    return Image.blend(black, white, 0.5), widest.point(lambda d: 255 if d <= 2 else 0).filter(ImageFilter.MinFilter(7))


def _same_treated(im, key, family):
    """True if `im` matches the treated cover for `key` within 2 levels on every pixel the art does not reach (see _treated_reference).
    A mask that covers less than 15% of the canvas leaves too little to tell our covers from others: then never ours."""
    want, mask = _treated_reference(key, family)
    if mask.histogram()[255] < 0.15 * SIZE[0] * SIZE[1]:
        return False
    return _same_pixels(im, (want, Image.merge("RGBA", (mask,) * 4)))


def is_steamcase_cover(path):
    """True if this file is one of our covers: a 600x900 PNG whose banner and bottom edge are those of frame.png (or of the family frame).
    A cover with a treatment note (a 100% game) must name exactly one of TREATMENTS, have colour notes we write, and match the cover
    regenerated in that colour, tone and treatment on every pixel the game's art does not reach (frame, rosette, ribbon, border).
    Otherwise, a cover with a tone note must match, pixel for pixel, the frame regenerated in the colour and tone its notes give; one
    without (made before tones existed) must have the shape of the frame in full tone, whatever its hue (its notes are not read). Next to
    a tone or treatment note, a garbled note, or notes the pixels do not match, mean not ours. Art you set yourself never matches, so it
    is never mistaken for ours."""
    try:
        if Image is None or os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_DOWNLOAD:
            return False
        top, bot, ref_tops, ref_bot, _ = _frame_regions()
        with Image.open(path, formats=["PNG"]) as im:
            if im.size != SIZE:
                return False
            toned, colour, done = TONE_CHUNK in im.info, _noted_colour(im.info), im.info.get(DONE_CHUNK)
            im = im.convert("RGBA")
        if done is not None:
            if done not in TREATMENTS or colour is None:
                return False
            if is_gold_case(done) and tone_key(*colour) != tone_key(GOLD_HUE, 100, 100):
                return False                                    # we always write a gold case with gold notes (gold-case and the ribbon at hue 176 look the same, so those two notes swapped cannot be told; harmless)
            key = (tone_key(*treatment_colour(done, colour)), done)
            return any(_same_treated(im, key, family) for family in (False, True))
        if toned:
            if colour is None:
                return False
            tops, bottom = _expected_strips(*colour)
            banner = im.crop(top)
            return any(_same_pixels(banner, ref) for ref in tops) and _same_pixels(im.crop(bot), bottom)
        banner = _shape(im.crop(top))
        return any(_same_shape(banner, ref) for ref in ref_tops) and _same_shape(_shape(im.crop(bot)), ref_bot)
    except Exception:
        return False


def find_our_covers(steam, user=None, progress=None, cancelled=None):
    """File names in Steam's grid folder (<appid>p.png) that are covers made by this app. Takes a few seconds for a big library."""
    grid = grid_dir(steam, user)
    names = sorted(n for n in os.listdir(grid) if _COVER_NAME.match(n)) if os.path.isdir(grid) else []
    out = []
    for i, n in enumerate(names, 1):
        if cancelled and cancelled():
            break
        if is_steamcase_cover(os.path.join(grid, n)):
            out.append(n)
        if progress and (i % 20 == 0 or i == len(names)):
            progress(i, len(names))
    return out


def find_other_art(steam, user=None, ours=()):
    """Custom portraits in the grid folder that this app did not make: art from SteamGridDB, from Steam's own menu, other formats.
    Returns (png names, jpg/jpeg/webp names)."""
    grid = grid_dir(steam, user)
    if not os.path.isdir(grid):
        return [], []
    files = [n for n in os.listdir(grid) if _is_plain_file(os.path.join(grid, n))]
    return sorted(n for n in files if _COVER_NAME.match(n) and n not in ours), sorted(n for n in files if _JPG_NAME.match(n))


def reset_to_default(steam, user=None, names=None, everything=False):
    """Remove our covers from Steam's grid folder so Steam shows its own default art again.
    Only files recognised as ours go; the files are moved into a normal backup, so restore_backup() undoes this.
    `names`: result of an earlier find_our_covers() (default: scan now).
    `everything`: also remove every other custom portrait (SteamGridDB, set by hand in Steam, any format), so no custom art is left.
    Returns {"removed", "backup", "account", "account_name"}."""
    grid = grid_dir(steam, user)
    acc = os.path.basename(os.path.dirname(os.path.dirname(grid)))
    info = {"account": acc, "account_name": account_label(steam, acc), "grid": grid}
    if names is None:
        names = find_our_covers(steam, user)
    names = [n for n in names if _COVER_NAME.match(n) and _is_plain_file(os.path.join(grid, n))]
    other = []
    if everything:
        extra_png, other = find_other_art(steam, user, names)
        names += extra_png
    if not names and not other:
        return dict(info, removed=0, backup=None)
    with _Lock(os.path.dirname(grid)):
        base = os.path.join(os.path.dirname(grid), BACKUP_PREFIX + time.strftime("%Y%m%d_%H%M%S"))
        backup, k = base, 1
        while True:
            try:
                os.makedirs(backup)
                break
            except FileExistsError:
                k += 1
                backup = "%s-%d" % (base, k)
        moved = []
        try:
            with open(os.path.join(backup, "manifest.json"), "w") as fh:
                json.dump({"added": [], "replaced": names, "moved": other}, fh)
            for n in names + other:
                os.replace(os.path.join(grid, n), os.path.join(backup, n))      # a move, not a copy: instant and no extra disk space
                moved.append(n)
        except OSError as e:
            for n in moved:
                try:
                    os.replace(os.path.join(backup, n), os.path.join(grid, n))
                except OSError:
                    pass
            shutil.rmtree(backup, ignore_errors=True)
            raise SteamcaseError("Could not remove the covers (%s). Nothing was changed." % e)
        return dict(info, removed=len(moved), backup=backup)


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
    for name in m.get("moved", []):
        src = os.path.join(backup_dir, name)
        if _JPG_NAME.match(name) and _is_plain_file(src):
            os.replace(src, os.path.join(grid, name))                # hand-made art goes back where it was
            n += 1
    return n


_COVER_NAME = re.compile(r"^[0-9]{1,10}p\.png$")
_JPG_NAME = re.compile(r"^[0-9]{1,10}p\.(jpg|jpeg|webp)$")      # art set from Steam's menu or by SteamGridDB; Steam shows these before our .png
OTHER_EXT = ("jpg", "jpeg", "webp")


def _is_plain_file(path):
    return os.path.isfile(path) and not os.path.islink(path)


def restore_backup(steam, backup_dir, user=None, keep=False):
    """Undo one apply: put replaced files back and remove the ones that were added. Returns files touched.
    The backup is deleted afterwards (so the next restore goes one step further back) unless keep=True.
    Only real steamcase backups inside this account's config folder are accepted, and only files named <appid>p.png (or <appid>p.jpg, put back from the backup) are touched."""
    grid = grid_dir(steam, user)
    cfg = os.path.realpath(os.path.dirname(grid))
    real = os.path.realpath(backup_dir)
    if os.path.dirname(real) != cfg or not os.path.basename(real).startswith(BACKUP_PREFIX):
        raise SteamcaseError("That is not a steamcase backup of this Steam account.")
    mf = os.path.join(real, "manifest.json")
    if not os.path.exists(mf):
        raise SteamcaseError("That folder is not a steamcase backup: %s" % backup_dir)
    try:
        with open(mf) as fh:
            m = json.load(fh)
        names = [str(x) for x in m.get("replaced", []) + m.get("added", [])]
        jpgs = [str(x) for x in m.get("moved", [])]
    except (OSError, ValueError, AttributeError, TypeError, RecursionError, MemoryError, UnicodeError):
        raise SteamcaseError("The backup's manifest is damaged.")
    if not all(_COVER_NAME.match(n) for n in names) or not all(_JPG_NAME.match(n) for n in jpgs):
        raise SteamcaseError("The backup's manifest lists unexpected files; refusing to use it.")
    with _Lock(cfg):
        n = _undo(grid, real, m)
        if not keep:
            shutil.rmtree(real, ignore_errors=True)
    return n


# ---------- command line ----------
def _collect(args):
    steam = steam_dir(args.steam_dir)
    games, family = load_library(steam, args.library)
    return steam, games, family


def cmd_list(args):
    steam, games, family = _collect(args)
    print("Steam folder:", steam)
    rows = list_games(games, print)
    for appid, name in rows:
        print("%d %s%s" % (appid, name, "  (family)" if appid in family else ""))
    print("\n%d games%s" % (len(rows), "" if args.library else "  (installed only; add --library userdata.json for your whole library)"))
    shared = sum(1 for appid, _ in rows if appid in family)
    if shared:
        print("%d from your Steam Family library" % shared)


def _hue_arg(text):
    if not re.fullmatch(r"[0-9]{1,3}", text) or int(text) > 359:
        raise argparse.ArgumentTypeError("%r is not a whole number from 0 to 359" % text)
    return int(text)


def _percent_arg(text):
    if not re.fullmatch(r"[0-9]{1,3}", text) or int(text) > 100:
        raise argparse.ArgumentTypeError("%r is not a whole number from 0 to 100" % text)
    return int(text)


def _chosen_colour(args):
    """The case colour (hue, sat, val) to build: each part is the option if given, else that of the covers already in the folder, else the original."""
    found = existing_cover_colour(os.path.abspath(args.out)) or (0, 100, 100)
    return tuple(found[i] if o is None else o for i, o in enumerate((args.hue, args.saturation, args.brightness)))


def _completion_args(args):
    """(completed, treatment) for make_covers from --games-page and --completed-style: (None, None) when neither is given (covers stay as they are).
    A page alone means the ribbon (the plain case with the full marks); --completed-marks chooses the full marks or the rosette alone, and means nothing with "none"; "none" removes the treatments, with a page or without, and does not read the page. Exits with status 2 and the reason if the page cannot be used."""
    if args.games_page is None and args.completed_style is None and args.completed_marks is None:
        return None, None
    style = args.completed_style or "ribbon"
    treatment = None if style == "none" else compose_treatment(style, args.completed_marks or "full")
    if args.games_page is None or treatment is None:        # "none" needs no page: a bad one must not stop you removing the highlights
        return set(), treatment
    try:
        completed = completion.completed_apps(completion.read_games_page(os.path.expanduser(args.games_page)))
    except completion.PageError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    return completed, treatment


def cmd_make(args):
    completed, treatment = _completion_args(args)           # first: a bad page fails before the library is loaded
    steam, games, family = _collect(args)
    hue, sat, val = _chosen_colour(args)

    def progress(done, total, appid, name, status):
        if status == "ok":
            print("ok  ", appid, name)

    res = make_covers(games, os.path.abspath(args.out), args.only, args.force, args.skip_auto_art, progress, log=print, family=family, hue=hue, sat=sat, val=val, completed=completed, treatment=treatment)
    print("\n%d covers in %s | %d skipped (DLC/tools/non-games) | %d without portrait art" % (res["ok"], os.path.abspath(args.out), res["skipped"], len(res["missing"]))
          + (" | %d from your Steam Family library" % res["family"] if res["family"] else "")
          + (" | %d of them are 100%% complete" % res["completed"] if res["completed"] else "")
          + (" | in a custom colour" if hue or (sat, val) != (100, 100) else ""))
    for appid, name in res["missing"]:
        print("  no art:", appid, name)
    for appid, name in res["failed"]:
        print("  failed (connection problem? run again to retry):", appid, name)


def cmd_apply(args):
    if mixed_cover_colours(args.covers):                    # first: before Steam is closed
        raise SteamcaseError("The covers in %s are in more than one colour (a colour change was probably interrupted). Nothing was changed. "
                             "Run make again with the colour you want (--hue, --saturation, --brightness) to finish it, then apply." % args.covers)
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
    if r["jpg_moved"]:
        print("Art you had set by hand in Steam (%d games) was moved into the backup; restore brings it back." % r["jpg_moved"])
    print("Start Steam to see them.")
    print("To undo: python steamcase.py restore")


def cmd_run(args):
    args.covers = args.out
    cmd_make(args)
    cmd_apply(args)


def cmd_reset(args):
    steam = steam_dir(args.steam_dir)
    print("Looking for covers made by this app (this can take a few seconds)...")
    names = find_our_covers(steam, args.user)
    if args.everything:
        extra, other = find_other_art(steam, args.user, names)
        print("%d covers made by this app and %d custom portraits from other sources (SteamGridDB, set by hand) will be removed; Steam goes back to its own default art." % (len(names), len(extra) + len(other)))
        names = names + extra
        if not names and not other:
            print("Nothing to reset.")
            return
    elif not names:
        print("None found. Nothing to reset.")
        return
    else:
        print("%d covers made by this app will be removed; Steam goes back to its own default art for them. Your own custom art is not touched. (--everything also removes art from other sources.)" % len(names))
    if steam_running() and not args.yes:
        if args.close_steam:
            print("Closing Steam...")
            if not close_steam(steam):
                raise SteamcaseError("Steam did not close. Close it yourself and retry.")
        else:
            print("Steam seems to be running. Close it first, or pass --close-steam.")
            if input("Continue anyway? [y/N] ").strip().lower() != "y":
                raise SteamcaseError("Cancelled.")
    elif not args.yes and input("Remove them? [y/N] ").strip().lower() != "y":
        raise SteamcaseError("Cancelled.")
    r = reset_to_default(steam, args.user, names, args.everything)
    print("Removed %d covers. Backup: %s\nTo bring them back: python steamcase.py restore" % (r["removed"], r["backup"]))


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
    ap.add_argument("--version", action="version", version="steam-case-covers %s" % APP_VERSION)
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
        p.add_argument("--hue", type=_hue_arg, default=None, metavar="DEGREES",
                       help="turn the case colour by this many degrees, 0 to 359 (0 is the original blue; covers in another colour are rebuilt). "
                            "Default: the colour of the covers already in the folder, else the original blue")
        p.add_argument("--saturation", type=_percent_arg, default=None, metavar="PERCENT",
                       help="how colourful the case is, 0 to 100 (100 is the original, 0 is grey; covers in another tone are rebuilt). "
                            "Default: that of the covers already in the folder, else 100")
        p.add_argument("--brightness", type=_percent_arg, default=None, metavar="PERCENT",
                       help="how light the case is, 0 to 100 (100 is the original, 0 is black; covers in another tone are rebuilt). "
                            "Default: that of the covers already in the folder, else 100")
        p.add_argument("--games-page", metavar="FILE",
                       help="your Steam games page saved from the browser as \"Webpage, Complete\" (HTML only will not do); games with every achievement unlocked get a special cover. "
                            "The saved page contains a temporary login token of yours: this app does not use or keep it, and you can delete the page afterwards")
        p.add_argument("--completed-style", choices=("ribbon", "gold-case", "gold-border", "none"), default=None,
                       help="how 100%% games look: ribbon (a rosette and a ribbon, the default with --games-page), gold-case, gold-border, or none (plain covers again). "
                            "gold-case is always gold and ignores --hue, --saturation and --brightness. "
                            "Needs --games-page, except none. Without either option the covers are left as they are")
        p.add_argument("--completed-marks", choices=MARKS, default=None,
                       help="what 100%% games get on the cover: full (the rosette and the \"100%% Complete\" ribbon, the default) or rosette (the rosette alone). "
                            "Works with every --completed-style and needs --games-page, like it")
        p.add_argument("--skip-auto-art", action="store_true", help=AUTO_ART_HELP)
        p.set_defaults(fn=fn)
    p = sub.add_parser("apply", help="copy covers into Steam"); common(p, apply_=True); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("reset", help="remove our covers from Steam so it shows its default art again"); common(p, apply_=True)
    p.add_argument("--everything", action="store_true", help="also remove custom portraits from other sources (SteamGridDB, set by hand)"); p.set_defaults(fn=cmd_reset)
    p = sub.add_parser("restore", help="undo an apply (newest backup by default)")
    p.add_argument("--steam-dir"); p.add_argument("--user"); p.add_argument("--yes", action="store_true")
    p.add_argument("--backup", help="backup folder name (see userdata/<id>/config/)")
    p.set_defaults(fn=cmd_restore)
    args = ap.parse_args()
    if args.cmd in ("make", "run") and args.games_page is None:
        if args.completed_style not in (None, "none"):
            ap.error("--completed-style needs --games-page")
        if args.completed_style is None and args.completed_marks is not None:
            ap.error("--completed-marks needs --games-page")
    try:
        args.fn(args)
    except SteamcaseError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
