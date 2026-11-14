#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""steamcase: give every game in your Steam library a "physical case" portrait cover.

  python -m engine list                       show the games it found
  python -m engine make                       build covers into ./covers
  python -m engine apply                      copy covers into Steam's grid folder
  python -m engine run                        make + apply
  python -m engine restore                    undo the last apply

Needs Python 3.10+ and Pillow (pip install pillow). No Steam API key, no account login.
Covers are built on your machine from the artwork Steam itself serves for your games.

The functions below are the engine. The CLI at the bottom and the window (qtui/) both use them.
"""
from engine import caseframe, completion, safefile, shortcuts
import argparse, filecmp, functools, hashlib, io, json, os, re, shutil, socket, ssl, stat, struct, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid
from typing import NamedTuple

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
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

HERE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # _MEIPASS: inside a PyInstaller bundle
FRAME = os.path.join(HERE, "assets", "frame.png")
DEFAULT_ART = os.path.join(HERE, "assets", "default_art.png")     # original artwork, only used for the colour preview
FAMILY_CORNER = os.path.join(HERE, "assets", "family_corner.png")    # green triangle and icon, laid over the frame for games from the Steam Family library
COMPLETION_OVERLAY = os.path.join(HERE, "assets", "completion_overlay.png")    # rosette and "100% Complete" ribbon, laid over the covers of games with every achievement
CHRISTMAS_OVERLAY = os.path.join(HERE, "assets", "christmas_overlay.png")    # a Santa hat, a tree and gifts, laid over the case for the Christmas theme
CASES = ("ribbon", "gold-case", "gold-border")           # the case of a 100% cover: the marks only, the marks on a gold case, the marks inside a gold border
MARKS = ("full", "rosette", "none")                      # the marks: the rosette and the ribbon, the rosette alone, or neither (only the gold case or border says it)
_PARTS = {"ribbon": ("ribbon", "full"), "rosette": ("ribbon", "rosette"),            # every treatment and the (case, marks) it is made of: how a 100% cover looks
          **{case + suffix: (case, marks) for case in CASES[1:] for suffix, marks in (("", "full"), ("-rosette", "rosette"), ("-plain", "none"))}}
_NAMES = {parts: name for name, parts in _PARTS.items()}
TREATMENTS = tuple(_PARTS)
ROSETTE_ROWS = 450                                       # the rosette-only marks are the overlay above this row; the ribbon sits below it
GOLD_HUE = 176                              # the gold of the colour swatches (#c89817), used whole for the "gold-case" treatment
BORDER = 14                                 # width of the "gold-border" treatment's border, in cover pixels
DONE_CHUNK = "steamcase-done"               # PNG note naming a cover's treatment; plain covers have none
THEMES = ("christmas",)                     # case themes: decorations drawn on the case, whatever its colour; the classic case has none
ART_CHUNK = "steamcase-art"                 # PNG note naming the source file of a cover built from the user's own art; covers from Steam's portrait carry none
THEME_CHUNK = "steamcase-theme"             # PNG note naming a cover's theme; classic covers carry none
PLATFORMS = ("ps3", "ps4", "ps5", "xbox360", "xboxone", "xboxseries", "switch", "switch2")      # the console cases (assets/cases); the Steam case is the one without a platform
PLATFORM_LABELS = {"ps3": "PlayStation 3", "ps4": "PlayStation 4", "ps5": "PlayStation 5", "xbox360": "Xbox 360", "xboxone": "Xbox One",
                   "xboxseries": "Xbox Series X|S", "switch": "Nintendo Switch", "switch2": "Nintendo Switch 2"}
GROUP_CHUNK = "steamcase-group"            # PNG note naming the group (groups.py) of a cover made by hand; a short id of lower-case letters and digits
GROUP_ID = re.compile(r"[a-z0-9]{1,12}")
LAYOUT_CHUNK = "steamcase-layout"           # PNG note naming how a cover was drawn (LAYOUT); covers made before v1.6.0 carry none
# How a cover was drawn. "2" (v1.6.0): the rosette at the top left, the family corner at the top right (v1.5.0 had them the other way round).
# "3": the whole art is stretched to the case window instead of cropped, on every cover (marks or not).
# "4": the window of an own glass case runs up to the sharp edge under its glow (caseframe._grow_window), so the art reaches the top as well.
LAYOUT = "4"
STRETCH_LIMIT = 1.25                        # an art whose shape is within this factor of the window's is stretched to fill it; a wider or narrower one is cropped
CASE_CHUNK = "steamcase-case"               # PNG note with the digest of the user's own case file, on covers whose platform note is "custom"
PLATFORM_CHUNK = "steamcase-platform"       # PNG note naming a cover's console case; Steam-case covers have none (and a console cover has no colour, tone or theme note)
CASES_DIR = os.path.join(HERE, "assets", "cases")    # one <platform>.png per case (transparent art window) and cases.json (the window of each)
KEEP = "keep"                             # in place of a theme: each existing cover keeps the theme it has
HUE_SWATCHES = (0, 42, 84, 134, 176, 276)           # ready-made case colours, as degrees of hue turned from the original blue (violet, magenta, red, orange, green)
NEUTRAL_SWATCHES = (("Black", 0, 14), ("Graphite", 0, 34), ("Silver", 0, 78))    # ready-made greys: (name, colourfulness, brightness), hue does not matter
FAMILY_COLOR = (46, 125, 50)                # #2e7d32: the white icon on it has a contrast of 5.1:1
FAMILY_ICON_CONTRAST = 4.5                  # WCAG AA for normal text; the icon must never fall below it
WINDOW = (14, 96, 586, 872)                 # art window inside frame.png (x0, y0, x1, y1)
SIZE = (600, 900)
STEAMID64_BASE = 76561197960265728
CDN = "https://shared.fastly.steamstatic.com/store_item_assets/"
OLD_CDN = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/"
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
MAX_STEAM_TEXT = 8 * 1024 * 1024         # Steam's own text files (libraryfolders, loginusers, appmanifest) are a few KB
MAX_APPS = 100_000                       # a real library has at most a few thousand apps
MAX_PIXELS = 30_000_000                  # portraits are ~1 MP; refuses decompression bombs
MAX_PACKAGEINFO = 16 * 1024 * 1024       # Steam's own package list is a few hundred KB
_PACKAGEINFO_MAGICS = (0x06565527, 0x06565528)
GAME_TYPES = (0, None, 12)           # 0 = game, 12 = playtest (same art as its game, and it sits in the library); other types are DLC, tools, demos
SOFTWARE_TYPE = 6                   # Lossless Scaling, Wallpaper Engine and Blender: type 6, with normal portrait art; made only when the user asks
TOOL_NAMES = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|Steam Controller Configs)", re.I)
BACKUP_PREFIX = "grid_backup_"

# Shown next to the "include software" option (GUI tooltip, CLI --help).
SOFTWARE_HELP = ("Also make covers for software you own on Steam, such as Wallpaper Engine or Lossless Scaling. "
                 "Steam's own tools, demos and DLC still get none.")
# Shown next to the "include non-Steam games" option (GUI tooltip, CLI --help).
NON_STEAM_HELP = ("Also make covers for the non-Steam games you added to Steam, when they already have a portrait in your Steam art folder. "
                  "Games without one are left alone.")
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


translate = lambda text: text           # the window puts its own tr() here, so the messages it shows are in its language; the command line stays English


def _t(text):
    """A message a person reads: translated when the window set `translate`. Mark with _t(...) only the text with its %s, never the finished sentence."""
    return translate(text)


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
    """One tiny real request to Steam's store API. Returns (ok, message). Used by 'python -m qtui --check-network'."""
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
    raise SteamcaseError(_t("Refusing to open an address that is not https: %s") % url[:80])


def _get_opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(_HttpsOnlyRedirects, urllib.request.HTTPSHandler(context=_ssl_context()))
    return _opener


def _read_capped(resp):
    size = resp.headers.get("Content-Length")
    if size and size.isdigit() and int(size) > MAX_DOWNLOAD:
        raise SteamcaseError(_t("A download was unexpectedly large (%s bytes); refusing it.") % size)
    data = resp.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise SteamcaseError(_t("A download was unexpectedly large; refusing it."))
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
KOFI_URL = "https://ko-fi.com/diegobergonsi"                # the author's Ko-fi page (the link the README uses); opened only when the button is clicked
DISCORD_URL = "https://discord.gg/JQMjAPWHCT"          # the project's Discord server (the invite the README uses); opened only when the button is clicked
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
        raise SteamcaseError(_t("GitHub's answer was not understood. Try again later."))
    except Exception as e:
        raise SteamcaseError(_t("Could not reach GitHub: %s") % explain_error(e))
    best = None
    for r in data if isinstance(data, list) else []:
        tag = r.get("tag_name") if isinstance(r, dict) and not r.get("draft") else None
        v = version_tuple(tag)
        if v and (best is None or v > best[0]):
            best = (v, tag)
    if not best:
        raise SteamcaseError(_t("No releases found on GitHub."))
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
    """A Steam text file (a regular file, links followed, of a sane size), closed again."""
    return safefile.read_small_file(path, MAX_STEAM_TEXT, follow_links=True).decode("utf-8-sig", errors="replace")


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
            raise SteamcaseError(_t("Steam folder not found: %s") % path)
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
    raise SteamcaseError(_t("Could not find Steam. Is it installed? (CLI: pass its folder with --steam-dir.)"))


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
            try:
                t = read_text(os.path.join(apps, fn))
            except OSError:                                        # one unreadable file must not hide the other games
                continue
            i, n = vdf_values(t, "appid"), vdf_values(t, "name")
            if i and n and i[0].isdigit() and not TOOL_NAMES.match(n[0]):
                games[int(i[0])] = n[0]
    return games


def _load_library_json(json_path):
    path = os.path.expanduser(json_path)
    name = os.path.basename(path)
    try:
        return json.loads(safefile.read_small_file(path, MAX_LIBRARY_FILE, follow_links=True).decode("utf-8-sig"))
    except safefile.FileTooBig:
        raise SteamcaseError(_t("That file is far too big to be your game list (over %d MB).") % (MAX_LIBRARY_FILE >> 20))
    except safefile.NotRegularFile:
        raise SteamcaseError(_t("Could not read %s as a game list (not a regular file).") % name)
    except (OSError, ValueError, RecursionError, MemoryError, UnicodeError) as e:
        raise SteamcaseError(_t("Could not read %s as a game list (%s).") % (name, type(e).__name__))


def owned_ids(json_path):
    d = _load_library_json(json_path)
    ids = d.get("rgOwnedApps") if isinstance(d, dict) else None
    if isinstance(ids, list) and not ids and "rgOwnedPackages" in d:
        raise SteamcaseError(_t("That file has no games in it. This usually means you were not logged in to Steam in your browser when you saved it. "
                             "Click “Download your userdata.json” again, log in when Steam asks, then save the page. "
                             "If the page you see shows no games even though you are logged in, refresh it (F5, or Cmd+R on a Mac) before saving."))
    if not isinstance(ids, list):
        raise SteamcaseError(_t("That file has no game list ('rgOwnedApps'). Save %s while logged in to Steam.") % LIBRARY_JSON_URL)
    if not ids:
        raise SteamcaseError(_t("The game list in that file is empty. Save %s while logged in to Steam.") % LIBRARY_JSON_URL)
    if len(ids) > MAX_APPS:
        raise SteamcaseError(_t("That game list has %d entries; a real library has far fewer. Refusing it.") % len(ids))
    try:
        if not all(type(i) is int or (isinstance(i, str) and i.isascii() and i.isdigit()) for i in ids):       # whole numbers only: no 1.9, true or Infinity
            raise ValueError("not a whole number")
        out = [int(i) for i in ids]
    except ValueError:                                                                                         # also a digit string too long for int()
        raise SteamcaseError(_t("The game list in that file is damaged. Save %s again.") % LIBRARY_JSON_URL)
    out = [i for i in out if 0 < i < 2 ** 32]                    # real Steam app IDs only
    if not out:
        raise SteamcaseError(_t("The game list in that file is empty. Save %s while logged in to Steam.") % LIBRARY_JSON_URL)
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
        with safefile.open_regular(path, MAX_PACKAGEINFO, follow_links=True) as f:     # too big, or not a plain file: an OSError, so None
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


def pick_account(steam, forced=None):
    base = os.path.join(steam, "userdata")
    accs = [d for d in os.listdir(base) if re.fullmatch(r"[0-9]+", d) and d != "0"] if os.path.isdir(base) else []
    if forced:
        if not re.fullmatch(r"[0-9]+", str(forced)):
            raise SteamcaseError(_t("The account must be the numeric folder name inside userdata/, e.g. 12345678"))
        return str(forced)
    if not accs:
        raise SteamcaseError(_t("No account folders in %s. Log in to Steam once, then retry.") % base)
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
            raise SteamcaseError(_t("Could not work out how to close Steam. Please close it yourself."))
    except OSError as e:
        raise SteamcaseError(_t("Could not close Steam: %s") % e)
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
        raise SteamcaseError(_t("Could not work out how to start Steam. Please start it yourself."))
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=not sys.platform.startswith("win"))
    except OSError as e:
        raise SteamcaseError(_t("Could not start Steam: %s") % e)


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
    listed = [a[k] for k in ("library_capsule_2x", "library_capsule") if fmt and a.get(k)]     # both: Steam can list a 2x file it does not serve (ARK: Survival Evolved)
    urls = [CDN + fmt.replace("${FILENAME}", f) for f in listed]
    urls += [OLD_CDN % appid + f for f in ("library_600x900_2x.jpg", "library_600x900.jpg")]
    auto = bool(listed) and listed[0].endswith("portrait.png")     # the first listed file decides: Steam-generated from the header means blurry
    return urls, auto


def is_coverable(item, name, software=False):
    """True if a store item can get a cover by what it is: a game or playtest, or software when `software` is on, and not one of Steam's tools by name. DLC, demos and the rest never do. A missing `name` is the caller's business."""
    kind = item.get("type", 0)
    return not TOOL_NAMES.match(name or "") and (kind in GAME_TYPES or (software and kind == SOFTWARE_TYPE))


def list_games(games, log=None, errors=None, software=False):
    """[(appid, name)] of real games only (no DLC, tools or unnamed leftovers; software only with `software`). `errors`: a list that gets the exception of every store lookup that failed."""
    info = store_items(sorted(games), log, errors=errors)
    out = []
    for appid in sorted(games):
        it = info.get(appid, {})
        name = games[appid] or it.get("name")
        if not name or not is_coverable(it, name, software):
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


def family_corner(legacy=False):
    """The green corner of the Steam Family library, 600 x 900, at the top right (the logo of a case is on the left). `legacy` is where earlier versions put it, at the top left."""
    with Image.open(FAMILY_CORNER) as im:
        corner = im.convert("RGBA")
    return corner if legacy else ImageOps.mirror(corner)


def load_frame(hue=0, family=False, *, sat=100, val=100, legacy_corner=False):
    """The case frame in the wanted colour and tone; with family=True the green corner of the Steam Family library is laid over it (never recoloured).
    `legacy_corner` puts it at the top left, as covers made by earlier versions have it (only to recognise those)."""
    frame = recolor_frame(Image.open(FRAME).convert("RGBA"), hue, sat, val)
    if family:
        frame = Image.alpha_composite(frame, family_corner(legacy_corner))
    return frame


MARKS_GAP = 14                              # the 100% rosette is this far from the left edge of the art and from the banner (or tab) above it
RIBBON_WIDTH = 482                          # the "100% Complete" ribbon on a console case, tails included, centred in the art
RIBBON_GAP = 28                             # and this far above the bottom of the art
MIN_WINDOW = 400                            # the art window of a console case is at least this wide and tall


def _check_cases(data):
    """SteamcaseError (one sentence naming the platform and the problem) unless `data`, the parsed cases.json, describes every case sensibly:
    "window" four whole numbers inside the 600 x 900 picture and at least MIN_WINDOW each way; "overlay", if given, four whole numbers inside it."""
    def fail(where, what):
        raise SteamcaseError(_t("cases.json: %s: %s") % (where, what))

    def whole(value):
        return isinstance(value, int) and not isinstance(value, bool)

    def numbers(where, name, value, count):
        if not (isinstance(value, list) and len(value) == count and all(whole(v) for v in value)):
            fail(where, "%s must be %d whole numbers" % (name, count))
        return value
    if not isinstance(data, dict):
        fail("the file", "must hold one entry per case")
    for platform in PLATFORMS:
        info = data.get(platform)
        if not isinstance(info, dict):
            fail(platform, "this case is missing")
        if "window" not in info:
            fail(platform, "window is missing")
        x0, y0, x1, y1 = numbers(platform, "window", info["window"], 4)
        if not (0 <= x0 < x1 <= SIZE[0] and 0 <= y0 < y1 <= SIZE[1]):
            fail(platform, "window must lie inside the %d x %d picture, left before right and top before bottom" % SIZE)
        if x1 - x0 < MIN_WINDOW or y1 - y0 < MIN_WINDOW:
            fail(platform, "window must be at least %d x %d" % (MIN_WINDOW, MIN_WINDOW))
        if "overlay" in info:
            ox0, oy0, ox1, oy1 = numbers(platform, "overlay", info["overlay"], 4)
            if not (0 <= ox0 < ox1 <= SIZE[0] and 0 <= oy0 < oy1 <= SIZE[1]):
                fail(platform, "overlay must lie inside the picture, left before right and top before bottom")


@functools.lru_cache(maxsize=1)
def _case_windows():
    try:
        with open(os.path.join(CASES_DIR, "cases.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise SteamcaseError(_t("cases.json: cannot be read (%s)") % e)
    _check_cases(data)
    return data


CUSTOM = "custom"                          # the key of the user's own case: accepted where a console platform key is, but not one of PLATFORMS (it has no frame in assets)
CUSTOM_FILE = "custom_case.png"            # the checked copy of that case, kept in the covers folder


class _CaseSlot(NamedTuple):
    """The user's own case as the process uses it: the picture, its measured window (and tab), and the digest of its file."""
    frame: object
    info: dict
    digest: str


_custom = None                             # shortcut: one _CaseSlot for the whole process, upgrade when several custom cases are wanted


class _CaseChanged(SteamcaseError):
    """The custom case was replaced while covers were being made with it."""


def _measure(path):
    """({"window", "overlay"?}, the case as RGBA, the bytes of the file) of a case file the user chose. SteamcaseError (one sentence) when it is not a usable case."""
    if Image is None:
        raise SteamcaseError(_t("Pillow is needed to read a case file."))
    try:
        data = caseframe.read(path)
        return caseframe.measure(data, SIZE, MIN_WINDOW) + (data,)
    except caseframe.CaseFileError as e:
        raise SteamcaseError(str(e))


def check_case_file(path):
    """{"window": [x0, y0, x1, y1]} and, if a tab of the case covers part of it, "overlay": [..] (as tools/measure_cases.py measures a console case) for a case the
    user made: a plain PNG, exactly SIZE, with a see-through art window of at least MIN_WINDOW each way and a visible frame. SteamcaseError (one sentence) for
    anything else."""
    return _measure(path)[0]


def save_custom_case(path, covers_dir):
    """Check the case file `path`, keep a re-encoded copy as CUSTOM_FILE in `covers_dir`, make it the active custom case and return its digest.
    SteamcaseError (one sentence) when the file is no good or the copy cannot be written; the kept copy and the active case stay as they were (the case
    only becomes the active one once its copy is on disk)."""
    global _custom
    info, frame, _ = _measure(path)
    buf = io.BytesIO()
    frame.save(buf, format="PNG")
    copy = buf.getvalue()
    dest = os.path.join(covers_dir, CUSTOM_FILE)
    tmp = _tmp(dest)
    try:
        os.makedirs(covers_dir, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(copy)
        _replace(tmp, dest)
    except OSError as e:
        raise SteamcaseError(_t("Your case could not be saved in %s (%s).") % (covers_dir, e.strerror or e))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    _custom = _CaseSlot(frame, info, hashlib.sha256(copy).hexdigest()[:16])
    return _custom.digest


def use_custom_case(covers_dir):
    """Make the case kept in `covers_dir` the active custom case: its digest, or None when there is none (and for covers_dir None, which clears the slot).
    SteamcaseError when the kept copy is no good."""
    global _custom
    path = os.path.join(covers_dir, CUSTOM_FILE) if covers_dir else None
    if path is None or not (os.path.isfile(path) or os.path.islink(path)):
        _custom = None
        return None
    try:
        info, frame, data = _measure(path)
    except SteamcaseError:
        _custom = None
        raise
    _custom = _CaseSlot(frame, info, hashlib.sha256(data).hexdigest()[:16])
    return _custom.digest


def custom_case_digest():
    """The digest of the active custom case, or None."""
    return _custom.digest if _custom else None


def _case_digest(platform):
    """What tells one custom case from another in a cover's notes and in caches: the digest of its file. None for a console case (and when no custom case is loaded)."""
    return custom_case_digest() if platform == CUSTOM else None


def _case_info(platform):
    """The measured window (and overlay) of a console case, or of the active custom case. ValueError for any other key."""
    if platform == CUSTOM and _custom:
        return _custom.info
    if platform not in PLATFORMS:
        raise ValueError("unknown platform: %r" % (platform,))
    return _case_windows()[platform]


def platform_window(platform):
    """The art window (x0, y0, x1, y1) inside the frame of a console case (or of the custom case). ValueError for a platform that is not one of PLATFORMS."""
    return tuple(_case_info(platform)["window"])


def platform_overlay(platform):
    """The part (x0, y0, x1, y1) of the art window that the frame itself covers (the Switch's red tab), or None."""
    box = _case_info(platform).get("overlay")
    return tuple(box) if box else None


@functools.lru_cache(maxsize=1)
def _rosette_box():
    """The box (x0, y0, x1, y1) of the rosette in the completion overlay."""
    return _rosette_overlay().getchannel("A").getbbox()


def _rosette_move(window, overlay):
    """(dy, dx): how far the rosette moves from where the overlay has it (top right) to the left of `window`, MARKS_GAP from its edge and from the banner or
    `overlay` (the tab the frame covers inside the window) above it."""
    x0, y0 = window[:2]
    return (max(y0, overlay[3] if overlay else y0) + MARKS_GAP - _rosette_box()[1], x0 + MARKS_GAP - _rosette_box()[0])


def platform_marks_dy(platform):
    """How far down the 100% rosette is moved on this console case: under the banner that holds the logo, or the tab."""
    return _rosette_move(platform_window(platform), platform_overlay(platform))[0]


def platform_marks_dx(platform):
    """How far left the 100% rosette is moved on this console case: to the left of the art, where the logo is not."""
    return _rosette_move(platform_window(platform), platform_overlay(platform))[1]


def platform_ribbon(platform):
    """(width, centre x, bottom y) of the ribbon on this console case: RIBBON_WIDTH wide, centred in the art, RIBBON_GAP above its bottom."""
    x0, _, x1, y1 = platform_window(platform)
    return RIBBON_WIDTH, (x0 + x1) // 2, y1 - RIBBON_GAP


def steam_marks():
    """(dy, dx, ribbon) for finish_treatment on the Steam case: the rosette and the ribbon in the same places and size as on a console case."""
    return _rosette_move(WINDOW, None) + ((RIBBON_WIDTH, (WINDOW[0] + WINDOW[2]) // 2, WINDOW[3] - RIBBON_GAP),)


def load_platform_frame(platform, family=False):
    """The frame of a console case (600 x 900, transparent where the art shows). With family=True the green corner of the Steam Family library is laid
    over it at the top right, where it covers only the end of the banner and never the logo, and kept inside the case's own outline. ValueError for a platform that
    is not one of PLATFORMS."""
    x0, y0, x1, y1 = platform_window(platform)
    frame = _custom.frame.copy() if platform == CUSTOM else Image.open(os.path.join(CASES_DIR, platform + ".png")).convert("RGBA")
    if family:
        outline = frame.getchannel("A").copy()
        outline.paste(255, (x0, y0, x1, y1))                      # the case's silhouette: its frame and the art window
        placed = family_corner()
        placed.putalpha(ImageChops.multiply(placed.getchannel("A"), outline))
        frame = Image.alpha_composite(frame, placed)
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


def _compose(art, frame, window=WINDOW):
    """A portrait stretched to fill the frame's art window, with the frame on top (an art far from the window's shape, see STRETCH_LIMIT, is scaled to cover it and
    centre-cropped instead). Real covers and the window's preview both use this. `window` is the frame's art window; the Steam case's unless the frame is a console case's (platform_window)."""
    x0, y0, x1, y1 = window
    ww, wh = x1 - x0, y1 - y0
    if 1 / STRETCH_LIMIT <= (art.width * wh) / (art.height * ww) <= STRETCH_LIMIT:
        art = art.resize((ww, wh), Image.LANCZOS)
    else:
        s = max(ww / art.width, wh / art.height)
        art = art.resize((max(ww, round(art.width * s)), max(wh, round(art.height * s))), Image.LANCZOS)
        cx, cy = (art.width - ww) // 2, (art.height - wh) // 2
        art = art.crop((cx, cy, cx + ww, cy + wh))
    canvas = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    canvas.paste(art, (x0, y0))
    return Image.alpha_composite(canvas, frame)


def _check_platform(platform, treatment, theme):
    """ValueError unless `platform` is one of PLATFORMS and goes with this `treatment` (none, "ribbon" or "rosette": no gold) and `theme` (none)."""
    if platform == CUSTOM and not _custom:
        raise SteamcaseError(_t("Your own case is missing. Pick the case file again."))
    if platform not in PLATFORMS and platform != CUSTOM:
        raise ValueError("unknown platform: %r" % (platform,))
    if theme is not None:
        raise ValueError("a console case has no theme: %r" % (theme,))
    if treatment not in (None, "ribbon", "rosette"):
        raise ValueError("a console case only goes with the marks (ribbon, rosette), not %r" % (treatment,))


def preview_cover(hue=0, family=False, *, sat=100, val=100, treatment=None, theme=None, platform=None):
    """What a cover looks like in this case colour and tone, made from the default art that ships with the app (the window shows it before any game's art exists).
    With a `treatment` (one of TREATMENTS) it shows the cover of a game with every achievement unlocked; with a `theme` (one of THEMES) the case also
    carries that theme's decorations. With a `platform` (one of PLATFORMS) it is that console's case: no colour, tone or theme, and only the "ribbon" or
    "rosette" marks."""
    if platform is not None:
        _check_platform(platform, treatment, theme)
        with Image.open(DEFAULT_ART) as im:
            return finish_treatment(_compose(im.convert("RGBA"), load_platform_frame(platform, family), platform_window(platform)), treatment,
                                    platform_marks_dy(platform), platform_marks_dx(platform), platform_ribbon(platform))
    hue, sat, val = treatment_colour(treatment, (hue, sat, val))
    with Image.open(DEFAULT_ART) as im:
        return finish_treatment(apply_theme(_compose(im.convert("RGBA"), load_frame(hue, family, sat=sat, val=val)), theme), treatment, *steam_marks())



def compose_treatment(case, marks):
    """The treatment (one of TREATMENTS) for a `case` (one of CASES) and its `marks` (one of MARKS). Full marks keep the plain name of the case. The normal case
    with no marks is no treatment at all: None, the same as "No special case"."""
    if case not in CASES or marks not in MARKS:
        raise ValueError("unknown case or marks: %r, %r" % (case, marks))
    return _NAMES.get((case, marks))


def split_treatment(treatment):
    """(case, marks) of a treatment, the inverse of compose_treatment. ValueError for anything that is not one of TREATMENTS."""
    if treatment not in _PARTS:
        raise ValueError("unknown treatment: %r" % (treatment,))
    return _PARTS[treatment]


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
def _christmas_overlay():
    with Image.open(CHRISTMAS_OVERLAY) as im:
        return im.convert("RGBA")


def apply_theme(cover, theme):
    """`cover` (the finished 600 x 900 composition, before the 100% marks) with the decorations of `theme` (one of THEMES) over it, kept inside
    the case's own outline. The case keeps its colour. No theme: `cover` itself."""
    if theme is None:
        return cover
    if theme not in THEMES:
        raise ValueError("unknown theme: %r" % (theme,))
    marks = _christmas_overlay().copy()
    marks.putalpha(ImageChops.multiply(marks.getchannel("A"), cover.getchannel("A")))     # nothing reaches past the rounded case
    return Image.alpha_composite(cover, marks)


def existing_cover_theme(covers_dir):
    """The theme of the covers already in the folder (that of the first readable one by name), or None when there are none or they are classic."""
    return next((notes.theme for _, _, notes in usual_covers(covers_dir) if notes.theme is not False), None)


def covers_in_other_theme(covers_dir, theme):
    """True if the covers folder holds a cover made with another theme than `theme` (None is the classic case); a garbled note counts as another."""
    return any(notes.theme != theme for _, _, notes in usual_covers(covers_dir))


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


def finish_treatment(cover, treatment, dy=0, dx=0, ribbon=None):
    """`cover` (the finished 600 x 900 composition) with the marks of a 100% game: the rosette over the platform badges and, unless the
    treatment is a rosette-only one, the ribbon at the bottom, kept inside the case's own outline. For "gold-border" the whole cover is then shrunk by BORDER pixels
    on each side and set inside a gold border, so the marks stay on the art. No treatment: `cover` itself.
    `dy` and `dx` move the rosette from the top right (where the cover as made by earlier versions has it); `ribbon` is (width, centre x, bottom y) for a ribbon of
    another width than the overlay's, set at the bottom."""
    if treatment is None:
        return cover
    case, kind = split_treatment(treatment)
    done = cover if kind == "none" else _with_marks(cover, kind, dy, dx, ribbon)
    if case == "gold-border":
        plate = _gold_border().copy()
        plate.alpha_composite(done.resize((SIZE[0] - 2 * BORDER, SIZE[1] - 2 * BORDER), Image.LANCZOS), (BORDER, BORDER))
        done = plate
    return done


def _with_marks(cover, kind, dy, dx, ribbon):
    """`cover` with the rosette (`kind` "rosette") or the rosette and the ribbon (`kind` "full") laid over it, moved and sized as finish_treatment says."""
    marks = (_rosette_overlay() if kind == "rosette" else _completion_overlay()).copy()
    if dy or dx or ribbon:                                              # the rosette moves to the left, below the banner; the ribbon stays at the bottom, in its width
        moved = Image.new("RGBA", marks.size, (0, 0, 0, 0))
        moved.paste(marks.crop((0, 0, marks.width, ROSETTE_ROWS)), (dx, dy))
        below = marks.crop((0, ROSETTE_ROWS, marks.width, marks.height))
        if ribbon and below.getchannel("A").getbbox():
            width, centre, bottom = ribbon
            tape = below.crop(below.getchannel("A").getbbox())
            tape = tape.resize((width, round(tape.height * width / tape.width)), Image.LANCZOS)
            moved.alpha_composite(tape, (centre - width // 2, bottom - tape.height))
        else:
            moved.paste(below, (0, ROSETTE_ROWS))
        marks = moved
    marks.putalpha(ImageChops.multiply(marks.getchannel("A"), cover.getchannel("A")))     # nothing reaches past the rounded case
    return Image.alpha_composite(cover, marks)


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


def _png_info(path):
    """The text notes of a PNG we may read (not a link, a plain file, not too big), or None. Reads the header only, never decodes the picture."""
    try:
        with safefile.open_regular(path, MAX_DOWNLOAD) as fh, Image.open(fh, formats=["PNG"]) as im:
            return dict(im.info)
    except Exception:
        return None


class CoverNotes(NamedTuple):
    """What a cover says about itself in its PNG header. A field is its value, None when the cover has no such note, and False (colour: None) when the note
    is not exactly one we write: the cover is then rebuilt rather than taken for what it might be."""
    colour: object          # (hue, sat, val): covers made before colours existed count as hue 0, those without a tone note as full tone; None when a colour note is garbled
    treatment: object       # one of TREATMENTS (a 100% game), or None
    theme: object           # one of THEMES, or None for the classic case
    platform: object        # one of PLATFORMS (a console case), or None for the Steam case
    group: object           # the id of the group a cover by hand was made in, or None
    art: object             # "custom <hash>" for a cover built from the user's own art (see art_note), or None for Steam's portrait
    layout: object = None   # LAYOUT for a cover drawn the way this version draws it, None for a cover of an earlier version (no note), False for another note
    case: object = None     # the digest of the user's own case file for a cover in CUSTOM, None for any other cover, False for a note we do not write


def _noted(value, valid):
    return value if value is None or valid(value) else False


def notes_of(info):
    """The CoverNotes of a PNG's `info`."""
    return CoverNotes(_noted_colour(info),
                      _noted(info.get(DONE_CHUNK), lambda v: v in TREATMENTS),
                      _noted(info.get(THEME_CHUNK), lambda v: v in THEMES),
                      _noted(info.get(PLATFORM_CHUNK), lambda v: v in PLATFORMS or v == CUSTOM),
                      _noted(info.get(GROUP_CHUNK), lambda v: bool(GROUP_ID.fullmatch(v))),
                      _noted(info.get(ART_CHUNK), lambda v: bool(re.fullmatch(r"custom [0-9a-f]{16}", v))),
                      _noted(info.get(LAYOUT_CHUNK), lambda v: v == LAYOUT),
                      _noted(info.get(CASE_CHUNK), lambda v: bool(re.fullmatch(r"[0-9a-f]{16}", v))))


def read_notes(path):
    """The CoverNotes of the file at `path`, or None if it is not a readable PNG. The one place a cover's notes are read."""
    info = _png_info(path)
    return None if info is None else notes_of(info)


def by_hand(notes):
    """True for a cover made by hand (a console case or a group's Steam case): the usual flow leaves it alone. None for a usual cover. False if the file is not a
    readable PNG or one of those notes is not one we write: the cover is then rebuilt."""
    if notes is None or notes.platform is False or notes.group is False or notes.case is False:
        return False
    return True if notes.platform or notes.group else None


def scan_covers(covers_dir):
    """[(appid, path)] of the cover files (<name>_<appid>.png) in the folder, by name; empty if it cannot be listed."""
    try:
        names = sorted(os.listdir(covers_dir))
    except OSError:
        return []
    return [(int(appid), os.path.join(covers_dir, n)) for n in names if n.lower().endswith(".png") for appid in [appid_of(n)] if appid is not None]


def usual_covers(covers_dir):
    """[(appid, path, notes)] of the covers the usual flow looks after: readable ones that are not made by hand."""
    found = []
    for appid, path in scan_covers(covers_dir):
        notes = read_notes(path)
        if by_hand(notes) is None:
            found.append((appid, path, notes))
    return found


class CoverSpec(NamedTuple):
    """What a cover must be to be kept as it is, field by field (see CoverNotes). A field left at KEEP is not compared."""
    colour: object = KEEP
    treatment: object = KEEP
    theme: object = KEEP
    art: object = KEEP
    platform: object = KEEP         # None: the Steam case
    group: object = KEEP
    layout: object = KEEP           # LAYOUT: a cover drawn the way this version draws it (older covers had marks elsewhere or the art cropped), so an older cover is not kept
    case: object = KEEP             # the digest of the active custom case, for a cover in CUSTOM


def matches(notes, spec):
    """True if a cover with these notes (None: missing or unreadable) is what `spec` asks for, so make_covers keeps it. The same question every "would it be rebuilt"
    check asks, so they cannot disagree with the run itself."""
    if notes is None or (spec.colour != KEEP and not same_colour(notes.colour, spec.colour)):
        return False
    return all(want == KEEP or have == want for have, want in ((notes.treatment, spec.treatment), (notes.theme, spec.theme), (notes.art, spec.art),
                                                                (notes.platform, spec.platform), (notes.group, spec.group), (notes.layout, spec.layout), (notes.case, spec.case)))


def _art_wanted(custom_art, appid):
    """The art note a cover of `appid` must carry when make_covers gets `custom_art` ({appid: path}): KEEP when it is KEEP (art is not compared), None for Steam's portrait."""
    return KEEP if custom_art == KEEP else (art_note(custom_art[appid]) if appid in custom_art else None)


def _spec_for(platform, colour, treatment, theme, art, group):
    """The CoverSpec of a game made in `platform` (None: the Steam case in `colour`). A console case has no colour or theme to compare, and an earlier gold
    look keeps only its marks there; its art is compared like any other (KEEP: not at all)."""
    if platform:
        return CoverSpec(treatment=_console_marks(treatment), art=art, platform=platform, group=group, layout=LAYOUT, case=_case_digest(platform))
    return CoverSpec(colour, treatment, theme, art, None, group, LAYOUT)



def cover_colour(path):
    """The case colour (hue, sat, val) a cover was made in (see CoverNotes), or None if the file is unreadable or a colour note is garbled."""
    notes = read_notes(path)
    return notes.colour if notes else None


def cover_theme(path):
    """The theme of a cover (None: classic; False: unreadable file or a note we do not write)."""
    notes = read_notes(path)
    return False if notes is None else notes.theme


def cover_treatment(path):
    """The treatment of a cover (None: a plain cover; False: unreadable file or a note we do not write)."""
    notes = read_notes(path)
    return False if notes is None else notes.treatment


def cover_platform(path):
    """The console case of a cover (None: the Steam case; False: unreadable file or a note we do not write)."""
    notes = read_notes(path)
    return False if notes is None else notes.platform


def cover_group(path):
    """The group id of a cover made by hand (None: no group; False: unreadable file or a note we do not write)."""
    notes = read_notes(path)
    return False if notes is None else notes.group


def cover_art(path):
    """The art note of a cover (None: made from Steam's portrait; False: unreadable file or a note we do not write)."""
    notes = read_notes(path)
    return False if notes is None else notes.art


def cover_by_hand(path):
    """by_hand() of the file at `path`."""
    return by_hand(read_notes(path))


def cover_hue(path):
    """The case hue of a cover (see cover_colour), or None when unknown."""
    colour = cover_colour(path)
    return colour[0] if colour else None


def forget_group(covers_dir, appids):
    """Take the group note off the covers in the folder of these games (a set of appids); the pictures and every other note stay. How many covers lost a note.
    A Steam-case cover is a usual cover again; a console cover still is by hand, its case is its own note. Damaged files, links and other covers are left alone."""
    count = 0
    for appid, path in scan_covers(covers_dir):
        if appid not in appids or not _is_plain_file(path) or not isinstance(cover_group(path), str):
            continue
        part = _tmp(path, "part")
        try:
            with Image.open(path, formats=["PNG"]) as im:
                note = PngInfo()
                for key, value in im.info.items():
                    if isinstance(value, str) and key != GROUP_CHUNK:
                        note.add_text(key, value)
                im.load()
                im.save(part, format="PNG", optimize=True, pnginfo=note)
            _replace(part, path)
            count += 1
        except Exception:
            pass
        finally:
            if os.path.exists(part):
                os.remove(part)
    return count


def _console_marks(treatment):
    """The marks a console cover keeps from a treatment (none, "ribbon" or "rosette"): a console case has no gold, so an earlier gold look keeps only its marks."""
    return compose_treatment("ribbon", split_treatment(treatment)[1]) if treatment else None


def art_note(path):
    """The note a cover built from the user's own art `path` carries: "custom " and the start of the file's SHA-256, so a changed file rebuilds it."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "custom " + h.hexdigest()[:16]


def build_cover(portrait_path, out_path, frame, hue=0, *, sat=100, val=100, treatment=None, theme=None, from_art=None, platform=None, group=None):
    """Write the cover of one portrait into `out_path`, with its colour notes, its `theme` and theme note (None: the classic case) and, for a 100% game,
    its `treatment` and treatment note, and `from_art` (an art_note) when the portrait is the user's own. `frame` is already in the colour the cover is made in (for "gold-case": the gold frame, with hue, sat, val saying gold).
    With a `platform` (one of PLATFORMS) `frame` is that console's (load_platform_frame): the cover gets the platform note and no colour, tone or theme note, and
    only no treatment or the "ribbon" and "rosette" marks go with it (ValueError otherwise, as for a theme).
    `group` (the id of a group, see groups.py) marks the cover as made by hand: it gets the group note and the usual flow leaves it alone."""
    if Image is None:
        raise SteamcaseError(_t("Pillow is missing. Install it with:  python -m pip install pillow"))
    if theme is not None and theme not in THEMES:
        raise ValueError("unknown theme: %r" % (theme,))
    if platform is not None:
        _check_platform(platform, treatment, theme)
    if group is not None and not (isinstance(group, str) and GROUP_ID.fullmatch(group)):
        raise ValueError("a group id is 1 to 12 lower-case letters and digits: %r" % (group,))
    with Image.open(portrait_path, formats=["PNG", "JPEG", "WEBP"]) as im:        # never let Pillow guess (EPS, TIFF, ... have a worse track record)
        if im.width * im.height > MAX_PIXELS:                  # header check only; nothing is decoded yet
            raise SteamcaseError(_t("Image is too large to be a game portrait (%dx%d).") % im.size)
        art = im.convert("RGBA")
    cover = finish_treatment(apply_theme(_compose(art, frame, platform_window(platform) if platform else WINDOW), theme), treatment,
                             *((platform_marks_dy(platform), platform_marks_dx(platform), platform_ribbon(platform)) if platform else steam_marks()))
    part = _tmp(out_path, "part")                  # write aside, then rename: a crash never leaves a half-written cover
    note = PngInfo()
    if platform is not None:
        note.add_text(PLATFORM_CHUNK, platform)                # a console cover has no colour, tone or theme: the case is fixed
        if platform == CUSTOM:
            note.add_text(CASE_CHUNK, custom_case_digest())     # a new case file rebuilds the covers made with the old one
    else:
        note.add_text(HUE_CHUNK, str(hue % 360))               # lets make_covers tell what colour an existing cover is without decoding it
        note.add_text(TONE_CHUNK, "%d %d" % (min(max(sat, 0), 100), min(max(val, 0), 100)))
    if treatment is not None:
        note.add_text(DONE_CHUNK, treatment)                   # plain covers carry no note, as before treatments existed
    if theme is not None:
        note.add_text(THEME_CHUNK, theme)                      # classic covers carry none, as before themes existed
    if from_art is not None:
        note.add_text(ART_CHUNK, from_art)                          # covers from Steam's portrait carry none
    if group is not None:
        note.add_text(GROUP_CHUNK, group)                           # covers made by hand carry it: the usual flow leaves them alone
    note.add_text(LAYOUT_CHUNK, LAYOUT)                             # how this cover is drawn: a later version that draws something elsewhere can tell it from this one
    cover.save(part, format="PNG", optimize=True, pnginfo=note)
    _replace(part, out_path)


# ---------- make ----------
def _wanted_look(appid, notes, colour, completed, treatment, theme=None):
    """(treatment, case colour) the cover of `appid`, whose notes are `notes` (None if it is missing or unreadable), should have (see make_covers). Without a page
    (`completed` None) a cover keeps the treatment it was made with; a garbled note counts as none, so the cover is rebuilt plain.
    With a theme (not None or KEEP) the marks are the rosette alone: a treatment kept from before with full marks, or with none, becomes its rosette-only twin."""
    if completed is not None:
        target = treatment if appid in completed else None
    else:
        target = (notes.treatment if notes else None) or None
    if theme not in (None, KEEP) and target is not None and split_treatment(target)[1] != "rosette":
        target = compose_treatment(split_treatment(target)[0], "rosette")
    return target, treatment_colour(target, colour)


def _check_hand(tones, groups, repaint, treatment, theme):
    """ValueError unless `tones` ({appid: (hue, sat, val)}), `groups` ({appid: group id}) and `repaint` (a set of appids) are what make_covers takes, and, for covers by hand
    (any tone or group), the `treatment` is none, "ribbon" or "rosette" and there is no `theme`: those covers have no gold and no theme."""
    def whole(a):
        return isinstance(a, int) and not isinstance(a, bool)
    for a, t in (tones or {}).items():
        if not (whole(a) and isinstance(t, (tuple, list)) and len(t) == 3 and all(whole(v) for v in t) and 0 <= t[0] < 360 and 0 <= t[1] <= 100 and 0 <= t[2] <= 100):
            raise ValueError("a colour is (hue 0-359, sat 0-100, val 0-100) for a game: %r" % ((a, t),))
    for a, g in (groups or {}).items():
        if not (whole(a) and isinstance(g, str) and GROUP_ID.fullmatch(g)):
            raise ValueError("a group is an id of 1 to 12 lower-case letters and digits for a game: %r" % ((a, g),))
    if repaint is not None and not (isinstance(repaint, (set, frozenset)) and all(whole(a) for a in repaint)):
        raise ValueError("repaint is a set of appids: %r" % (repaint,))
    if (tones or groups) and (theme is not None or treatment not in (None, "ribbon", "rosette")):
        raise ValueError("covers by hand only go with the marks (ribbon, rosette) and no theme")


def _drop_older_covers(covers_dir, dest, appid):
    """A game Steam renamed gets a cover under its new name: the file under the old name goes, or Apply could put the old one in Steam."""
    for name in os.listdir(covers_dir):
        path = os.path.join(covers_dir, name)
        if path != dest and appid_of(name) == str(appid) and _is_plain_file(path):
            os.remove(path)


def make_covers(games, out, only=None, force=False, skip_auto_art=False, progress=None, cancelled=None, log=None, family=None, hue=0, sat=100, val=100,
                completed=None, treatment=None, theme=None, custom_art=None, platforms=None, tones=None, groups=None, repaint=None, software=False):
    """Build a cover per game into `out`.

    progress(done, total, appid, name, status)  status: ok | exists | skipped | noart | failed
    cancelled() -> True stops early.
    family: set of appids that come from the Steam Family library; those covers are drawn with the green-corner frame.
    hue, sat, val: the case colour: degrees to turn it from the original blue (0), then its colourfulness and brightness (0 to 100, 100 = as drawn).
    completed: set of appids with every achievement unlocked (from the saved games page), or None when no page is loaded.
    treatment: one of TREATMENTS (a case and its marks, see compose_treatment) for those games, or None ("No special case": they get plain covers).
    theme: one of THEMES (decorations on every cover, the case keeps its colour) or None (the classic case). It only goes with the rosette-only
    marks: a `treatment` whose marks are "full" raises ValueError.
    custom_art: {appid: path} of the user's own portraits (see find_custom_art): those games get that picture in the case and nothing is downloaded
    for them (even a blurry auto-art, whatever `skip_auto_art` says); None: every cover is made from Steam's portrait, and a cover built from
    custom art before is rebuilt. Games in a console case (and in the user's own case) use it too.
    platforms: None (the natural flow): a game whose cover is already in a console case keeps it untouched, whatever `force` says, and is counted in "platforms".
    A dict {appid: one of PLATFORMS, or None for the Steam case}: only these games are made, each in its case (a console case has no colour, tone or theme,
    and only the "ribbon" and "rosette" `treatment` go with it: ValueError otherwise, before any lookup). A cover that already has the wanted case,
    marks and art is kept, any other is rebuilt. Apps in the dict that are not in `games` are ignored.
    Without a page each existing cover keeps the treatment it was made with. A "gold-case" cover is made in gold whatever the colour asked.
    A cover that exists in another colour, with another treatment or in another theme is rebuilt, one that already looks right is kept
    (the hue means nothing at 0 sat or 0 val). Apps in `completed` that are not in `games` are ignored.
    progress counts only items that can become a cover (DLC, soundtracks and tools are not counted).
    Returns {"ok", "skipped", "not_games" (DLC, tools...), "unlisted" (apps Steam no longer lists), "missing": [(appid, name)] (Steam has no art),
    "failed": [(appid, name)] (download problem), "cancelled", "files": [cover paths of this run],
    "family": how many covers were drawn with the family frame in this run (an existing plain cover is kept unless force is set),
    "completed": how many of "files" carry a treatment, kept ones included, "platforms": how many of "files" are in a console case}.
    tones: {appid: (hue, sat, val)}, with `platforms` a dict: the colour of a game in the Steam case (the run's own colour for a game not in it). groups: {appid: id of a
    group, see groups.py}: the cover gets the group note, and a cover is kept only if its group is the wanted one. Covers by hand only go with no `treatment` or the "ribbon"
    and "rosette" marks and no `theme` (ValueError otherwise, before any lookup). The natural flow (`platforms` None) leaves every cover by hand (a console case or a
    group note) alone, force or not, except those whose appid is in `repaint`: they are made again as normal covers.
    """
    if Image is None:
        raise SteamcaseError(_t("Pillow is missing. Install it with:  python -m pip install pillow"))
    _check_hand(tones, groups, repaint, treatment, theme)
    if treatment is not None and treatment not in TREATMENTS:
        raise ValueError("unknown treatment: %r" % (treatment,))        # a note nobody can read back would have the cover rebuilt on every run
    if theme is not None and theme not in THEMES:
        raise ValueError("unknown theme: %r" % (theme,))
    if theme is not None and treatment is not None and split_treatment(treatment)[1] != "rosette":
        raise ValueError("the %s theme only goes with the rosette-only marks, not %r" % (theme, treatment))      # the ribbon would hide the decorations
    tones, groups, repaint = tones or {}, groups or {}, repaint or set()
    wanted_platforms = set((platforms or {}).values()) - {None}
    if wanted_platforms - set(PLATFORMS) - {CUSTOM}:
        raise ValueError("unknown platform: %r" % (sorted(wanted_platforms - set(PLATFORMS) - {CUSTOM}, key=str)[0],))
    if wanted_platforms:
        _check_platform(sorted(wanted_platforms)[0], treatment, theme)
    if CUSTOM in wanted_platforms:
        _check_platform(CUSTOM, treatment, theme)           # the run stops here, before any download, when the case file is gone
    os.makedirs(out, exist_ok=True)
    hue %= 360
    sat, val = min(max(sat, 0), 100), min(max(val, 0), 100)
    family = set(family or ())
    custom_art = custom_art or {}
    slot = _custom if CUSTOM in wanted_platforms else None      # the case the run is made with: if it is replaced meanwhile the run stops, never a cover from two files
    frames = {}                                 # (look of the colour, family?) -> frame: each one is made once per run

    def frame_for(colour, is_family):
        key = (tone_key(*colour), is_family)
        if key not in frames:
            frames[key] = load_frame(colour[0], is_family, sat=colour[1], val=colour[2])
        return frames[key]

    def console_frame_for(platform, is_family):
        key = (platform, is_family)
        if key not in frames:
            frames[key] = load_platform_frame(platform, is_family)
        return frames[key]

    frame_for((hue, sat, val), False)           # a missing frame.png fails here, before any download
    for p in sorted(wanted_platforms):
        console_frame_for(p, False)             # so does a missing console case
    if treatment is not None or completed is None:
        _completion_overlay()                   # so does a missing overlay: otherwise every 100% cover would count as a failed download
    if theme is not None:
        _christmas_overlay()                    # and a missing theme overlay: otherwise every cover would

    ids = sorted(games)
    if platforms is not None:
        ids = [i for i in ids if i in platforms]
    if only:
        wanted = set(only)
        ids = [i for i in ids if i in wanted]
    if log:
        log("Looking up %d apps on Steam's store..." % len(ids))
    errs = []
    info = store_items(ids, log, cancelled, errs)
    if ids and not info and not (cancelled and cancelled()):
        why = explain_error(errs[-1]) if errs else "no answer, check your internet connection"
        raise SteamcaseError(_t("Could not reach Steam's servers: %s.") % why.rstrip("."))
    res = {"ok": 0, "skipped": 0, "not_games": 0, "unlisted": 0, "missing": [], "failed": [], "cancelled": False, "files": [], "family": 0, "completed": 0, "platforms": 0}
    todo = []                                   # only items that can become a cover count towards the progress
    for appid in ids:
        it = info.get(appid) or {}
        known = games[appid] or it.get("name")
        if not is_coverable(it, known, software):
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
        dest = os.path.join(out, "%s_%d.png" % (slug(name), appid))
        want_p = platforms.get(appid) if platforms is not None else None
        want_g = groups.get(appid) if platforms is not None else None
        notes = read_notes(dest)                        # None while there is no cover yet
        if platforms is None and appid not in repaint and by_hand(notes):      # the natural flow leaves a cover by hand alone
            res["ok"] += 1
            res["platforms"] += 1
            res["completed"] += bool(notes.treatment)
            res["files"].append(dest)
            report(n, appid, name, "exists")
            continue
        urls, auto = portrait_candidates(appid, it)
        try:
            wanted_art = art_note(custom_art[appid]) if appid in custom_art else None
        except OSError as e:                                              # the file went away since it was found
            res["failed"].append((appid, name))
            if log:
                log("FAIL %s %s: %s" % (appid, name, e))
            report(n, appid, name, "failed")
            continue
        if auto and skip_auto_art and wanted_art is None:                 # checked first: also drops covers built by an earlier run without this option
            res["skipped"] += 1
            report(n, appid, name, "skipped")
            continue
        target, colour = _wanted_look(appid, notes, tones.get(appid, (hue, sat, val)) if platforms is not None else (hue, sat, val), completed, treatment, theme)
        if want_p:
            target = _console_marks(target)             # an earlier gold look keeps only its marks: a console case has no gold
        spec = _spec_for(want_p, colour, target, theme, wanted_art, want_g)
        if not force and matches(notes, spec):
            res["ok"] += 1
            res["platforms"] += bool(want_p)
            res["completed"] += target is not None
            res["files"].append(dest)
            report(n, appid, name, "exists")
            continue
        tmp = os.path.join(out, ".tmp_%d_%s" % (appid, uuid.uuid4().hex[:8]))
        got, neterr = wanted_art is not None, False
        for u in [] if got else urls:
            try:
                b = http_get(u)
            except urllib.error.HTTPError as e:
                neterr = neterr or not (400 <= e.code < 500 and e.code != 429)      # 404/403 = no such art; the rest = trouble
                continue
            except Exception:
                neterr = True
                continue
            if b[:2] == b"\xff\xd8" or b[:4] == b"\x89PNG" or b[8:12] == b"WEBP":
                try:
                    with open(tmp, "wb") as f:
                        f.write(b)
                except OSError:                                  # a full disk is that game failing, not the end of the run
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    neterr = True
                    break
                got = True
                break
            neterr = True                                    # answered, but not with an image: a login page or proxy in the way
        if not got:
            res["failed" if neterr else "missing"].append((appid, name))        # failed = connection problem, worth a retry
            report(n, appid, name, "failed" if neterr else "noart")
            continue
        if want_p == CUSTOM and _custom is not slot:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise _CaseChanged(_t("Your own case changed while the covers were being made. Make them again."))
        try:
            is_family = appid in family
            build_cover(custom_art[appid] if got and wanted_art else tmp, dest, console_frame_for(want_p, is_family) if want_p else frame_for(colour, is_family), colour[0], sat=colour[1], val=colour[2],
                        treatment=target, theme=theme, from_art=wanted_art, platform=want_p, group=want_g)
            if want_p == CUSTOM and _custom is not slot:
                os.remove(dest)                                     # built while the case was being replaced: not trusted
                raise _CaseChanged(_t("Your own case changed while the covers were being made. Make them again."))
            _drop_older_covers(out, dest, appid)
            res["ok"] += 1
            res["platforms"] += bool(want_p)
            res["family"] += is_family
            res["completed"] += target is not None
            res["files"].append(dest)
            report(n, appid, name, "ok")
        except _CaseChanged:
            raise
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
def covers_in_other_look(covers_dir, hue, sat=100, val=100, completed=None, treatment=None, theme=KEEP, custom_art=KEEP, drawing=True):
    """True if make_covers with this colour, `completed`, `treatment` and `theme` would rebuild a cover already in the folder (stops at the first one):
    one in another case colour (a "gold-case" cover is compared as gold), with another treatment or, unless `theme` is KEEP, in another theme.
    Unless `custom_art` is KEEP, also one whose art differs: custom art newly on, off or changed ({appid: path}, as for make_covers).
    Unless `drawing` is False, also a cover with marks that an earlier version drew (see LAYOUT). Covers whose colour notes are unreadable are not counted."""
    for appid, path in scan_covers(covers_dir):
        notes = read_notes(path)
        state = by_hand(notes)
        if state is False:                                           # a damaged note of a cover by hand: the natural flow rebuilds the cover, so it must ask
            return True
        if state or notes.colour is None:                            # a cover by hand is left alone by the natural flow
            continue
        target, colour = _wanted_look(appid, notes, (hue, sat, val), completed, treatment, theme)
        art = _art_wanted(custom_art, appid)
        if not matches(notes, CoverSpec(colour=colour, treatment=target, theme=theme, art=art, layout=LAYOUT if drawing else KEEP)):
            return True
    return False


def covers_in_own_case(covers_dir):
    """{appid} of the covers in the folder made in the user's own case for all games (no group): the ones the usual flow leaves alone as made by hand, and
    that the Look step's "My own case" switch gives back to the Steam case when it is turned off."""
    return {appid for appid, path in scan_covers(covers_dir) for notes in [read_notes(path)] if notes and notes.platform == CUSTOM and not notes.group}


def covers_in_other_case(covers_dir, platforms, tone=(0, 100, 100), treatment=None, completed=None, tones=None, groups=None, custom_art=KEEP):
    """How many covers already in the folder `make_covers(platforms=platforms, ...)` would rebuild: of the games in `platforms` ({appid: platform or None for the
    Steam case}) those with a cover in another case (another console, or the Steam case instead), with other marks (`treatment` for the apps in `completed`, as in
    make_covers) or, for the Steam case, in another colour (`tone`: (hue, sat, val)) or theme. A garbled platform note counts as another case.
    `tones` ({appid: colour}) and `groups` ({appid: group id}) are those of make_covers: a cover in another colour of its own, or in another group (or in one when none
    is wanted), is counted. Unless `custom_art` is KEEP, a cover whose art differs ({appid: path}, as for make_covers) is counted too."""
    count = 0
    for appid, path in scan_covers(covers_dir):
        if appid not in platforms:
            continue
        notes = read_notes(path)
        target, colour = _wanted_look(appid, notes, (tones or {}).get(appid, tone), completed, treatment)
        art = _art_wanted(custom_art, appid)
        count += not matches(notes, _spec_for(platforms[appid], colour, target, None, art, (groups or {}).get(appid)))
    return count


def covers_with_other_art(covers_dir, custom_art, games=None):
    """True if make_covers with this `custom_art` ({appid: path}) would rebuild a cover already in the folder because of its art alone: a cover made
    from your art when `custom_art` has none for it (or another file), or a cover from Steam's portrait that now gets art of yours. Colour and look are not compared.
    `games`: only covers of these appids count (the run leaves the others alone); default: all."""
    return any(notes.colour is not None and notes.art != (art_note(custom_art[appid]) if appid in custom_art else None)
               for appid, _, notes in usual_covers(covers_dir) if games is None or appid in games)


def covers_with_art(covers_dir):
    """{appid} of the covers in the folder that were built from the user's own art."""
    return {appid for appid, _, notes in usual_covers(covers_dir) if notes.art}


def covers_in_other_colour(covers_dir, hue, sat=100, val=100):
    """True if the covers folder already holds a cover made in a different case colour than (`hue`, `sat`, `val`) (stops at the first one).
    No page loaded: each cover keeps its treatment, so a "gold-case" cover stays gold and is not counted (see covers_in_other_look)."""
    return covers_in_other_look(covers_dir, hue, sat, val, drawing=False)


def existing_cover_colour(covers_dir):
    """The case colour (hue, sat, val) of the covers already in the folder (that of the first one by name), or None when there are none.
    "gold-case" covers are skipped: their notes say gold, not the colour the user chose."""
    return next((notes.colour for _, _, notes in usual_covers(covers_dir) if notes.colour is not None and not is_gold_case(notes.treatment)), None)


def mixed_cover_colours(covers_dir):
    """True if the covers folder holds covers in more than one case colour (what an interrupted colour change leaves behind).
    "gold-case" covers are skipped (they are always gold, see existing_cover_colour) and so are covers whose notes are unreadable."""
    return len({tone_key(*notes.colour) for _, _, notes in usual_covers(covers_dir) if notes.colour is not None and not is_gold_case(notes.treatment)}) > 1


def covers_with_marks(covers_dir, marks):
    """True if the covers folder holds a 100% cover with these `marks` (one of MARKS): a theme turns "full" into the rosette alone and "none" into the rosette."""
    return any(notes.treatment and split_treatment(notes.treatment)[1] == marks for _, _, notes in usual_covers(covers_dir))


def mixed_cover_themes(covers_dir):
    """True if the covers folder holds covers in more than one case theme (what an interrupted theme change leaves behind). A garbled note counts as a theme of its own."""
    return len({notes.theme for _, _, notes in usual_covers(covers_dir)}) > 1


def _safe_copy(src, dst):
    """Copy src to dst atomically. If dst is a symlink, the link itself is replaced, never the file it points to."""
    tmp = _tmp(dst)
    try:
        shutil.copy2(src, tmp)
        _replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


_LEFTOVER = re.compile(r"^[0-9]{1,10}p\.(png|jpg)\.[0-9]+\.[0-9a-f]{8}\.(tmp)$")


def _remove_leftovers(grid):
    """Delete the half-copied files (<appid>p.png.<process>.<id>.tmp) a run that was killed in the middle of copying leaves in Steam's folder.
    Called while this run holds the lock, so no other run is writing one. Only regular files with exactly that name go."""
    try:
        names = os.listdir(grid)
    except OSError:
        return
    for n in names:
        p = os.path.join(grid, n)
        try:
            if _LEFTOVER.match(n) and stat.S_ISREG(os.lstat(p).st_mode):
                os.remove(p)
        except OSError:
            pass


def find_covers(covers_dir):
    return [path for _, path in scan_covers(os.path.abspath(covers_dir))]


def apply_covers(steam, covers_dir, user=None, files=None):
    """Copy covers into Steam's grid folder as <appid>p.png. Always makes a backup first.

    `files`: apply only these cover files (default: every cover in covers_dir).
    Only files that differ are written (and backed up); if nothing differs there is no backup and "backup" is None.
    Steam shows <appid>p.jpg before <appid>p.png (tested), so a leftover .jpg (art set by hand in Steam) is moved into the backup too.
    Returns {"account", "account_name", "grid", "applied", "unchanged", "replaced", "jpg_moved", "backup"}.
    The caller closes Steam beforehand (see close_steam)."""
    grid = grid_dir(steam, user)
    covers = list(files) if files is not None else find_covers(covers_dir)
    newest = {}
    for f in covers:                                         # a game renamed by Steam leaves two files for one app id: only the newest one is applied
        if not os.path.exists(f):
            continue
        a = appid_of(f)
        if a not in newest or os.path.getmtime(f) >= os.path.getmtime(newest[a]):
            newest[a] = f
    covers = [f for f in covers if not os.path.exists(f) or newest.get(appid_of(f)) == f]
    if not covers:
        raise SteamcaseError(_t("No covers found in %s. Make them first.") % covers_dir)
    gone = [f for f in covers if not os.path.exists(f)]
    if gone:
        raise SteamcaseError(_t("%d cover files are missing (deleted since they were made). Click “Make covers” again. Nothing was changed.") % len(gone))
    os.makedirs(grid, exist_ok=True)
    with _Lock(os.path.dirname(grid)):
        _remove_leftovers(grid)
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
        except OSError as e:                                                    # nothing in the grid was touched yet, and a half-copied backup must never go back into it
            shutil.rmtree(backup, ignore_errors=True)
            raise SteamcaseError(_t("Could not write to Steam's artwork folder (%s). Nothing was changed.") % e)
        try:
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
                raise SteamcaseError(_t("Could not write to Steam's artwork folder (%s), and the old artwork could not be put back. "
                                     "It is safe in the backup folder %s (use Restore, or copy the files back by hand).") % (e, backup))
            shutil.rmtree(backup, ignore_errors=True)                           # a failed run must not leave a backup behind
            raise SteamcaseError(_t("Could not write to Steam's artwork folder (%s). Nothing was changed.") % e)
        return dict(info, applied=len(work), unchanged=len(covers) - len(work), replaced=len(replaced), jpg_moved=len(moved), backup=backup)


def _pid_alive(pid):
    """False only when that process certainly does not exist (any doubt says True: a lock is then kept, as before)."""
    if pid == os.getpid():
        return True
    try:
        if sys.platform.startswith("win"):
            import ctypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = k.OpenProcess(0x1000, False, pid)                # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return ctypes.get_last_error() != 87                  # ERROR_INVALID_PARAMETER: no such process
            try:
                code = ctypes.c_ulong()
                return not k.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259     # STILL_ACTIVE
            finally:
                k.CloseHandle(handle)
        os.kill(pid, 0)                                               # signal 0 only asks whether the process exists
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


class _Lock:
    """One Apply/Restore at a time per Steam account (two open windows, or a script and a window).
    The lock is a folder holding the process number of its owner, so a lock left by a run that crashed is taken over at once;
    one whose owner may still be running is respected however long it takes, and one with no owner written is stale after ten minutes."""

    def __init__(self, cfg):
        self.path = os.path.join(cfg, ".steamcase.lock")

    def _owner(self):
        """The process number written in the lock, or None when there is none to read."""
        try:
            with open(os.path.join(self.path, "pid"), encoding="ascii") as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 0 else None

    def _stale(self):
        """Its owner is gone, or (when no owner can be read) it is older than ten minutes. A live owner keeps it however long it takes."""
        pid = self._owner()
        if pid is not None:
            return not _pid_alive(pid)
        return time.time() - os.path.getmtime(self.path) > 600

    def __enter__(self):
        for _ in range(3):
            try:
                os.mkdir(self.path)                                  # atomic: only one run can create it
                try:
                    with open(os.path.join(self.path, "pid"), "w", encoding="ascii") as f:
                        f.write(str(os.getpid()))
                except OSError:
                    pass                                              # the lock still works, only without the quick take-over
                return self
            except FileExistsError:
                try:
                    if not self._stale():
                        raise SteamcaseError(_t("Another steamcase window is changing Steam's artwork right now. Wait for it to finish, then try again."))
                    taken = _tmp(self.path, "stale")                  # left behind by a crashed run
                    os.rename(self.path, taken)                       # atomic: of two runs that both see it stale, only one takes it down
                except OSError:
                    continue
                shutil.rmtree(taken, ignore_errors=True)
        raise SteamcaseError(_t("Could not get exclusive access to Steam's artwork folder. Please try again."))

    def __exit__(self, *exc):
        if self._owner() in (None, os.getpid()):                     # a lock that another run took over meanwhile is theirs
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
        plain = load_frame(0)
        edges = tuple(family_corner(legacy).getchannel("A").crop(top).point(lambda a: 255 if a in (0, 255) else 0) for legacy in (False, True))
        families = tuple((_shape(load_frame(0, True, legacy_corner=legacy).crop(top)), edge) for legacy, edge in zip((False, True), edges))   # the family frame differs from the plain one only in the corner triangle; covers of earlier versions have it at the left
        _frame_ref = (top, bot, ((_shape(plain.crop(top)), None),) + families, (_shape(plain.crop(bot)), None), edges)
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
    top, bot, _, _, edges = _frame_regions()
    blank = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    frames = [Image.alpha_composite(blank, load_frame(step * 360 / 256, False, sat=sat, val=val))] + [      # as _compose lays it down
        Image.alpha_composite(blank, load_frame(step * 360 / 256, True, sat=sat, val=val, legacy_corner=legacy)) for legacy in (False, True)]
    return ((frames[0].crop(top), None),) + tuple((f.crop(top), Image.merge("RGBA", (edge,) * 4)) for f, edge in zip(frames[1:], edges)), (frames[0].crop(bot), None)


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
def _treated_reference(key, family, legacy=False):
    """(expected, mask) for a treated or themed cover: key is (tone_key, treatment, theme), the last two None for none. The cover is made twice, from flat black and from flat white
    art, through the same steps as build_cover; the mask is 255 where both agree within 2 on every channel (frame, rosette, ribbon,
    border, the theme's decorations: nothing the game's art reaches) and 0 elsewhere, then pulled back 3 pixels from the art: the gold border's shrink (Lanczos)
    lets detailed art ring that far past where flat art reaches. Expected is halfway between the two, so real art lands within 1 of it."""
    (step, sat, val), treatment, theme = key                        # step * 360 / 256 degrees turns the hue by exactly `step` again
    frame = load_frame(step * 360 / 256, family, sat=sat, val=val, legacy_corner=legacy)
    moved = () if legacy else steam_marks()                    # `legacy`: the cover as earlier versions made it, with the corner on the left and the rosette on the right
    black, white = (finish_treatment(apply_theme(_compose(Image.new("RGBA", SIZE, (c, c, c, 255)), frame), theme), treatment, *moved) for c in (0, 255))
    widest = functools.reduce(ImageChops.lighter, ImageChops.difference(black, white).split())
    return Image.blend(black, white, 0.5), widest.point(lambda d: 255 if d <= 2 else 0).filter(ImageFilter.MinFilter(7))


def _same_masked(im, want, mask, least):
    """True if `im` matches `want` within 2 levels on every pixel of `mask` (255 where the art does not reach), and the mask covers at least the
    fraction `least` of the canvas: a smaller one leaves too little to tell our covers from others."""
    if mask.histogram()[255] < least * SIZE[0] * SIZE[1]:
        return False
    return _same_pixels(im, (want, Image.merge("RGBA", (mask,) * 4)))


def _same_treated(im, key, family, legacy=False):
    """True if `im` matches the treated cover for `key` within 2 levels on every pixel the art does not reach (see _treated_reference).
    A mask that covers less than 15% of the canvas leaves too little to tell our covers from others: then never ours."""
    return _same_masked(im, *_treated_reference(key, family, legacy), 0.15)


@functools.lru_cache(maxsize=16)                                    # about 2.7 MB an entry
def _platform_reference(key, family, digest=None):
    """(expected, mask) for a console cover: key is (platform, treatment), the treatment None or "ribbon" or "rosette". Made like _treated_reference
    (from flat black and flat white art, through the same steps as build_cover); the art window is where the mask is 0.
    `digest` (of the custom case, for CUSTOM) is only part of the cache key: a new case file must not be compared with the old one's reference."""
    platform, treatment = key
    frame, window = load_platform_frame(platform, family), platform_window(platform)
    dy, dx, ribbon = platform_marks_dy(platform), platform_marks_dx(platform), platform_ribbon(platform)
    black, white = (finish_treatment(_compose(Image.new("RGBA", SIZE, (c, c, c, 255)), frame, window), treatment, dy, dx, ribbon) for c in (0, 255))
    widest = functools.reduce(ImageChops.lighter, ImageChops.difference(black, white).split())
    return Image.blend(black, white, 0.5), widest.point(lambda d: 255 if d <= 2 else 0).filter(ImageFilter.MinFilter(7))


def _same_platform(im, key, family):
    """True if `im` matches the console cover for `key` within 2 levels on every pixel the art does not reach. The PS3 and PS4 inserts are only a banner (about 8% of
    the canvas); the mask of every case must cover at least 6% (a test checks every case: over 30,000 pixels that must match), or too little is left to tell
    our covers from others."""
    digest = _case_digest(key[0])                                      # a custom cover's notes carry a digest as well, so a smaller mask is enough to tell it from art of someone else's
    return _same_masked(im, *_platform_reference(key, family, digest), 0.06 if digest is None else 0.002)


def is_steamcase_cover(path):
    """True if this file is one of our covers: a 600x900 PNG whose banner and bottom edge are those of frame.png (or of the family frame).
    A cover with a treatment note (a 100% game) or a theme note must name exactly one of TREATMENTS and one of THEMES (a theme never with full marks),
    have colour notes we write, and match the cover regenerated in that colour, tone, treatment and theme on every pixel the game's art does not reach
    (frame, rosette, ribbon, border, the theme's decorations).
    A cover by hand (a group note) must have a note we wrote and no theme, and otherwise match as a console or a Steam cover does.
    A console cover (a platform note) must name one of PLATFORMS, carry no colour, tone or theme note, have no treatment or "ribbon" or "rosette", and match that
    case on every pixel the art does not reach.
    Otherwise, a cover with a tone note must match, pixel for pixel, the frame regenerated in the colour and tone its notes give; one
    without (made before tones existed) must have the shape of the frame in full tone, whatever its hue (its notes are not read). Next to
    a tone, treatment or theme note, a garbled note, or notes the pixels do not match, mean not ours. Art you set yourself never matches, so it
    is never mistaken for ours."""
    try:
        if Image is None:
            return False
        top, bot, ref_tops, ref_bot, _ = _frame_regions()
        with safefile.open_regular(path, MAX_DOWNLOAD) as fh, Image.open(fh, formats=["PNG"]) as im:
            if im.size != SIZE:
                return False
            toned, colour, done, theme = TONE_CHUNK in im.info, _noted_colour(im.info), im.info.get(DONE_CHUNK), im.info.get(THEME_CHUNK)
            platform, strange = im.info.get(PLATFORM_CHUNK), any(k in im.info for k in (HUE_CHUNK, TONE_CHUNK, THEME_CHUNK))
            case = im.info.get(CASE_CHUNK)
            group = im.info.get(GROUP_CHUNK)
            im = im.convert("RGBA")
        if group is not None and (not GROUP_ID.fullmatch(group) or theme is not None):
            return False                                            # a cover by hand has a group note we wrote and no theme
        if platform is not None:                                    # a console cover: its case and marks decide, never a colour, tone, theme or art note
            if platform not in PLATFORMS and platform != CUSTOM or strange or done not in (None, "ribbon", "rosette"):
                return False
            if (platform == CUSTOM) != (case is not None) or (case is not None and not re.fullmatch(r"[0-9a-f]{16}", case)):
                return False                                        # a cover in the user's own case carries the digest of its file, and only such a cover does
            if case is not None and case != custom_case_digest():
                return True                                         # made with another case file than the one loaded now (a new pick, a new process): we cannot redraw it, but we wrote its notes
            return any(_same_platform(im, (platform, done), family) for family in (False, True))
        if done is not None or theme is not None:
            if (done is not None and done not in TREATMENTS) or (theme is not None and theme not in THEMES) or colour is None:
                return False
            if theme is not None and done is not None and split_treatment(done)[1] != "rosette":
                return False                                        # we never write a theme with full marks
            if is_gold_case(done) and tone_key(*colour) != tone_key(GOLD_HUE, 100, 100):
                return False                                    # we always write a gold case with gold notes (gold-case and the ribbon at hue 176 look the same, so those two notes swapped cannot be told; harmless)
            key = (tone_key(*treatment_colour(done, colour)), done, theme)
            return any(_same_treated(im, key, family, legacy) for family in (False, True) for legacy in (False, True))
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


def reset_to_default(steam, user=None, names=None, everything=False, keep=()):
    """Remove our covers from Steam's grid folder so Steam shows its own default art again.
    Only files recognised as ours go; the files are moved into a normal backup, so restore_backup() undoes this.
    `names`: result of an earlier find_our_covers() (default: scan now).
    `everything`: also remove every other custom portrait (SteamGridDB, set by hand in Steam, any format), so no custom art is left.
    `keep`: file names that stay whatever else is removed (the covers of groups the user did not tick): they are not "other art" either.
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
        names += [n for n in extra_png if n not in keep]
    if not names and not other:
        return dict(info, removed=0, backup=None)
    with _Lock(os.path.dirname(grid)):
        _remove_leftovers(grid)
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
            raise SteamcaseError(_t("Could not remove the covers (%s). Nothing was changed.") % e)
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


def _bring_back_art(grid, originals):
    """Copy the user's own art kept in `originals` back into the grid folder for every app that has no portrait there at all. Caller holds the lock. Returns files copied.
    The copy stays in `originals`."""
    try:
        kept = sorted(os.listdir(originals))
        held = {int(m.group(1)) for m in map(_ART_NAME.match, os.listdir(grid)) if m}
    except OSError:
        return 0
    n = 0
    for name in kept:
        m = _ORIGINAL_NAME.match(name)
        src = os.path.join(originals, name)
        if not m or int(m.group(1)) in held or not _usable_art(src):
            continue
        try:
            _safe_copy(src, os.path.join(grid, "%sp.%s" % (m.group(1), m.group(2))))
            n += 1
        except OSError:
            pass
    return n


_COVER_NAME = re.compile(r"^[0-9]{1,10}p\.png$")
_JPG_NAME = re.compile(r"^[0-9]{1,10}p\.(jpg|jpeg|webp)$")      # art set from Steam's menu or by SteamGridDB; Steam shows these before our .png
OTHER_EXT = ("jpg", "jpeg", "webp")


def _is_plain_file(path):
    return os.path.isfile(path) and not os.path.islink(path)


def restore_backup(steam, backup_dir, user=None, keep=False, originals=None):
    """Undo one apply: put replaced files back and remove the ones that were added. Returns files touched.
    The backup is deleted afterwards (so the next restore goes one step further back) unless keep=True.
    Only real steamcase backups inside this account's config folder are accepted, and only files named <appid>p.png (or <appid>p.jpg, put back from the backup) are touched.
    Art of your own that the app kept a copy of (find_custom_art) and that Steam's folder holds no portrait for any more (its backup is gone) is copied back too;
    `originals` is the folder of those copies (default: originals_dir())."""
    grid = grid_dir(steam, user)
    cfg = os.path.realpath(os.path.dirname(grid))
    real = os.path.realpath(backup_dir)
    if os.path.dirname(real) != cfg or not os.path.basename(real).startswith(BACKUP_PREFIX):
        raise SteamcaseError(_t("That is not a steamcase backup of this Steam account."))
    mf = os.path.join(real, "manifest.json")
    if not os.path.exists(mf):
        raise SteamcaseError(_t("That folder is not a steamcase backup: %s") % backup_dir)
    try:
        with open(mf) as fh:
            m = json.load(fh)
        names = [str(x) for x in m.get("replaced", []) + m.get("added", [])]
        jpgs = [str(x) for x in m.get("moved", [])]
    except (OSError, ValueError, AttributeError, TypeError, RecursionError, MemoryError, UnicodeError):
        raise SteamcaseError(_t("The backup's manifest is damaged."))
    if not all(_COVER_NAME.match(n) for n in names) or not all(_JPG_NAME.match(n) for n in jpgs):
        raise SteamcaseError(_t("The backup's manifest lists unexpected files; refusing to use it."))
    with _Lock(cfg):
        _remove_leftovers(grid)
        n = _undo(grid, real, m)
        n += _bring_back_art(grid, os.path.join(originals or originals_dir(), pick_account(steam, user)))
        if not keep:
            shutil.rmtree(real, ignore_errors=True)
    return n


# ---------- command line ----------
ART_EXT_ORDER = ("jpg", "jpeg", "webp", "png")          # which file Steam shows first when an app has several; ours follows it
_ART_NAME = re.compile(r"^([1-9][0-9]{0,9})p\.(jpg|jpeg|webp|png)$")          # no leading zeros: Steam looks for 100p.jpg, never 0100p.jpg
_ORIGINAL_NAME = re.compile(r"^([1-9][0-9]{0,9})\.(jpg|jpeg|webp|png)$")


def originals_dir():
    """Per-user folder where the app keeps a copy of the user's own art, so Apply moving the file out of Steam's grid folder loses nothing.
    Each Steam account has its own folder inside it (find_custom_art)."""
    return os.path.join(os.path.dirname(default_covers_dir()), "originals")


def _usable_art(path):
    """True for a plain image file this app can put in a case: not a link, not too big, a PNG, JPEG or WEBP that decodes."""
    try:
        if Image is None:
            return False
        with safefile.open_regular(path, MAX_DOWNLOAD) as fh, Image.open(fh, formats=["PNG", "JPEG", "WEBP"]) as im:
            if im.width * im.height > MAX_PIXELS:
                return False
        with safefile.open_regular(path, MAX_DOWNLOAD) as fh, Image.open(fh, formats=["PNG", "JPEG", "WEBP"]) as im:
            im.load()                       # a truncated or corrupt file fails here, not later in the middle of Make (verify() does nothing for JPEG and WEBP)
        return True
    except Exception:
        return False


def find_custom_art(steam, user=None, originals=None, problems=None):
    """{appid: path} of the user's own portraits (set by hand in Steam or from SteamGridDB), for `make_covers(custom_art=...)`.
    A plain image in the grid folder that is not one of our covers wins (`.jpg`, `.jpeg`, `.webp`, then `.png`, like Steam) and is copied into
    `originals` (default: `originals_dir()`, one folder per Steam account inside it); an app the grid folder holds only our cover for keeps the copy
    made earlier, and only while the grid still holds our cover: once it does not (Reset, or the art was cleared in Steam) the game goes back to
    Steam's portrait. A link, a file that is too big or does not decode is ignored. The app never deletes an original.
    One account's art never reaches another account's covers.
    `problems`: a list that gets one sentence for each file whose copy could not be kept (that file is then used where it is, but Apply will move it away)."""
    originals = os.path.join(originals or originals_dir(), pick_account(steam, user))
    grid = grid_dir(steam, user)
    found = {}
    try:
        names = sorted(os.listdir(grid))
    except OSError:
        names = []
    options = {}
    for n in names:
        m = _ART_NAME.match(n)
        if m:
            options.setdefault(int(m.group(1)), {})[m.group(2)] = os.path.join(grid, n)
    for appid, by_ext in options.items():
        for ext in ART_EXT_ORDER:
            path = by_ext.get(ext)
            if not path or not _usable_art(path) or (ext == "png" and is_steamcase_cover(path)):
                continue
            keep = os.path.join(originals, "%d.%s" % (appid, ext))
            try:
                os.makedirs(originals, exist_ok=True)
                if not (os.path.isfile(keep) and filecmp.cmp(path, keep, shallow=False)):
                    _safe_copy(path, keep)
                for other in ART_EXT_ORDER:                    # one original per app: a copy of another format is stale
                    stale = os.path.join(originals, "%d.%s" % (appid, other))
                    if other != ext and _is_plain_file(stale):
                        os.remove(stale)
                found[appid] = keep
            except OSError as e:
                found[appid] = path                            # cannot keep a copy: use the file where it is
                if problems is not None:
                    problems.append("Could not keep a copy of your art for game %d (%s)." % (appid, e.strerror or e))
            break
    try:
        stored = sorted(os.listdir(originals))
    except OSError:
        stored = []
    for n in stored:
        m = _ORIGINAL_NAME.match(n)
        path = os.path.join(originals, n)
        if m and int(m.group(1)) not in found and _usable_art(path) and not is_steamcase_cover(path):     # a copy that is one of our covers (an older version kept those) is no art
            ours = os.path.join(grid, "%sp.png" % m.group(1))
            if _is_plain_file(ours) and is_steamcase_cover(ours):
                found[int(m.group(1))] = path
    return found


def _collect(args):
    steam = steam_dir(args.steam_dir)
    games, family = load_library(steam, args.library)
    return steam, games, family


def cmd_list(args):
    steam, games, family = _collect(args)
    print("Steam folder:", steam)
    rows = list_games(games, print, software=args.include_software)
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


def _appid_arg(text):
    if not re.fullmatch(r"[0-9]{1,10}", text) or not 0 < int(text) < 2 ** 32:
        raise argparse.ArgumentTypeError("%r is not a Steam app id (a whole number from 1 to 4294967295)" % text)
    return int(text)


def _percent_arg(text):
    if not re.fullmatch(r"[0-9]{1,3}", text) or int(text) > 100:
        raise argparse.ArgumentTypeError("%r is not a whole number from 0 to 100" % text)
    return int(text)


def _chosen_colour(args):
    """The case colour (hue, sat, val) to build: each part is the option if given, else that of the covers already in the folder, else the original."""
    found = existing_cover_colour(os.path.abspath(args.out)) or (0, 100, 100)
    return tuple(found[i] if o is None else o for i, o in enumerate((args.hue, args.saturation, args.brightness)))


def _chosen_theme(args):
    """The case theme to build: --theme if given ("classic" is None), else that of the covers already in the folder, else None (the classic case)."""
    if args.theme is not None:
        return None if args.theme == "classic" else args.theme
    return existing_cover_theme(os.path.abspath(args.out))


def _completion_args(args, theme=None):
    """(completed, treatment) for make_covers from --games-page and --completed-style: (None, None) when neither is given (covers stay as they are).
    With a `theme` the marks default to the rosette alone, and asking for the full marks is refused (the ribbon would hide the decorations).
    A page alone means the ribbon (the plain case with the full marks); --completed-marks chooses the full marks, the rosette alone or no marks, and means nothing with "none"; "none" removes the treatments, with a page or without, and does not read the page. Exits with status 2 and the reason if the page cannot be used."""
    if args.games_page is None and args.completed_style is None and args.completed_marks is None:
        return None, None
    style = args.completed_style or "ribbon"
    if theme is not None and style in ("gold-case", "gold-border") and args.completed_marks == "none":
        raise SteamcaseError(_t("The %s theme only goes with the rosette-only marks (--completed-marks rosette), not with no marks: its decorations need the rosette. "
                             "To use no marks, make the classic case instead (--theme classic).") % theme.capitalize())
    if theme is not None and args.completed_marks == "full" and style != "none":
        raise SteamcaseError(_t("The %s theme only goes with the rosette-only marks (--completed-marks rosette): the ribbon would hide the decorations. "
                             "To use the full marks, make the classic case instead (--theme classic).") % theme.capitalize())
    treatment = None if style == "none" else compose_treatment(style, args.completed_marks or ("rosette" if theme else "full"))
    if args.games_page is None or treatment is None:        # "none" needs no page: a bad one must not stop you removing the highlights
        return set(), treatment
    try:
        completed = completion.completed_apps(completion.read_games_page(os.path.expanduser(args.games_page)))
    except completion.PageError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    return completed, treatment


def _refuse_with_case_file(args):
    """SteamcaseError (one sentence) for an option that means nothing next to --case-file: your own case has its own colours and no gold look."""
    for flag, given in (("--hue", args.hue is not None), ("--saturation", args.saturation is not None), ("--brightness", args.brightness is not None),
                        ("--theme", args.theme is not None), ("--completed-style gold-case or gold-border", args.completed_style in ("gold-case", "gold-border"))):
        if given:
            raise SteamcaseError(_t("--case-file cannot be used with %s: your own case keeps its own colours.") % flag)


def cmd_make(args):
    if args.case_file:
        _refuse_with_case_file(args)
        save_custom_case(args.case_file, os.path.abspath(args.out))     # first: a bad file fails before the library is loaded or anything is downloaded
    theme = _chosen_theme(args)
    completed, treatment = _completion_args(args, theme)    # first: a bad page fails before the library is loaded
    steam, games, family = _collect(args)
    hue, sat, val = _chosen_colour(args)
    out = os.path.abspath(args.out)
    problems = []
    custom_art = None
    own_art = args.use_custom_art or (args.use_custom_art is None and covers_with_art(out))
    if own_art or args.include_non_steam:
        found = find_custom_art(steam, args.user, problems=problems)
        custom_art = {}
        if own_art:
            have = None if args.use_custom_art else covers_with_art(out)         # not asked for: only the games whose covers already come from your art keep it
            custom_art = {a: p for a, p in found.items() if have is None or a in have}
        if args.include_non_steam:                          # the art of a shortcut is always used: it has no other portrait
            custom_art.update(shortcuts.add_non_steam(games, found, shortcuts.read_shortcuts(steam, args.user)))

    def progress(done, total, appid, name, status):
        if status == "ok":
            print("ok  ", appid, name)

    res = make_covers(games, os.path.abspath(args.out), args.only, args.force, args.skip_auto_art, progress, log=print, family=family, hue=hue, sat=sat, val=val, completed=completed, treatment=treatment, theme=theme, custom_art=custom_art,
                     platforms={appid: CUSTOM for appid in games} if args.case_file else None, software=args.include_software)
    own_art = sum(1 for f in res["files"] if cover_art(f))
    print("\n%d covers in %s | %d skipped (DLC/software/tools/non-games) | %d without portrait art" % (res["ok"], os.path.abspath(args.out), res["skipped"], len(res["missing"]))
          + (" | %d from your Steam Family library" % res["family"] if res["family"] else "")
          + (" | %d of them are 100%% complete" % res["completed"] if res["completed"] else "")
          + (" | in a custom colour" if hue or (sat, val) != (100, 100) else "")
          + (" | with the %s theme" % theme.capitalize() if theme else "")
          + (" | in your own case" if args.case_file else "")
          + (" | %d from your own art" % own_art if own_art else ""))
    for appid, name in res["missing"]:
        print("  no art:", appid, name)
    for appid, name in res["failed"]:
        print("  failed (connection problem? run again to retry):", appid, name)
    for text in problems:
        print("  " + text[0].lower() + text[1:])


def cmd_apply(args):
    if mixed_cover_colours(args.covers):                    # first: before Steam is closed
        raise SteamcaseError(_t("The covers in %s are in more than one colour (a colour change was probably interrupted). Nothing was changed. "
                             "Run make again with the colour you want (--hue, --saturation, --brightness) to finish it, then apply.") % args.covers)
    if mixed_cover_themes(args.covers):
        raise SteamcaseError(_t("The covers in %s are in more than one theme (a theme change was probably interrupted). Nothing was changed. "
                             "Run make again with the theme you want (--theme classic or --theme christmas) to finish it, then apply.") % args.covers)
    steam = steam_dir(args.steam_dir)
    if steam_running() and not args.yes:
        if args.close_steam:
            print("Closing Steam...")
            if not close_steam(steam):
                raise SteamcaseError(_t("Steam did not close. Close it yourself and retry."))
        else:
            print("Steam seems to be running. Close it first (Steam > Exit), or pass --close-steam.")
            if input("Copy anyway? [y/N] ").strip().lower() != "y":
                raise SteamcaseError(_t("Cancelled."))
    r = apply_covers(steam, args.covers, args.user)
    print("Steam account:", r["account_name"], "(folder %s)" % r["account"], "\nGrid folder:", r["grid"])
    if r["applied"]:
        print("Applied %d covers (%d replaced older files, %d already up to date). Backup: %s" % (r["applied"], r["replaced"], r["unchanged"], r["backup"]))
    else:
        print("Nothing to change: all %d covers were already in Steam." % r["unchanged"])
    if r["jpg_moved"]:
        print("Art you had set by hand in Steam (%d games) was moved into the backup; restore brings it back." % r["jpg_moved"])
    print("Start Steam to see them.")
    print("To undo: python -m engine restore")


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
                raise SteamcaseError(_t("Steam did not close. Close it yourself and retry."))
        else:
            print("Steam seems to be running. Close it first, or pass --close-steam.")
            if input("Continue anyway? [y/N] ").strip().lower() != "y":
                raise SteamcaseError(_t("Cancelled."))
    elif not args.yes and input("Remove them? [y/N] ").strip().lower() != "y":
        raise SteamcaseError(_t("Cancelled."))
    r = reset_to_default(steam, args.user, names, args.everything)
    print("Removed %d covers. Backup: %s\nTo bring them back: python -m engine restore" % (r["removed"], r["backup"]))


def cmd_restore(args):
    steam = steam_dir(args.steam_dir)
    backups = list_backups(steam, args.user)
    if not backups:
        raise SteamcaseError(_t("No backups found."))
    if args.backup and os.path.basename(args.backup) != args.backup:
        raise SteamcaseError(_t("--backup takes just the folder name (like grid_backup_20260101_120000), not a path."))
    target = os.path.join(os.path.dirname(backups[0]), args.backup) if args.backup else backups[0]
    if steam_running() and not args.yes:
        print("Steam seems to be running. Close it first so it picks the files up on next start.")
        if input("Restore anyway? [y/N] ").strip().lower() != "y":
            raise SteamcaseError(_t("Cancelled."))
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

    p = sub.add_parser("list", help="show detected games"); common(p, make=True); p.add_argument("--include-software", action="store_true", help=SOFTWARE_HELP); p.set_defaults(fn=cmd_list)
    for name, fn in (("make", cmd_make), ("run", cmd_run)):
        p = sub.add_parser(name, help=name + " covers" if name == "make" else "make + apply")
        common(p, make=True, apply_=(name == "run"))
        p.add_argument("--only", type=_appid_arg, nargs="+", metavar="APPID", help="only these app IDs")
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
        p.add_argument("--case-file", metavar="PNG", default=None,
                       help="put every game of this run in a case of your own: a 600 x 900 PNG that is see-through where the art goes (at least 400 x 400). A checked copy is kept "
                            "in --out. Covers made without it are not changed back by later runs without it; use another --out, or delete them")
        p.add_argument("--theme", choices=("classic", "christmas"), default=None,
                       help="the case theme: classic (the plain case) or christmas (a Santa hat at the top, a tree and gifts at the bottom; the case keeps its colour). "
                            "Without it the covers already in the folder keep their theme. Games at 100%% get the rosette alone with a theme (see --completed-marks)")
        p.add_argument("--completed-marks", choices=MARKS, default=None,
                       help="what 100%% games get on the cover: full (the rosette and the \"100%% Complete\" ribbon, the default; with a theme the default is rosette) rosette (the rosette alone) or none (no marks: the gold case or border alone; with the normal case it is the same as --completed-style none). "
                            "Works with every --completed-style except none (which has no marks) and needs --games-page, like it")
        p.add_argument("--skip-auto-art", action="store_true", help=AUTO_ART_HELP)
        p.add_argument("--include-software", action="store_true", help=SOFTWARE_HELP)
        p.add_argument("--include-non-steam", action="store_true", help=NON_STEAM_HELP)
        art = p.add_mutually_exclusive_group()
        art.add_argument("--use-custom-art", dest="use_custom_art", action="store_const", const=True, default=None,
                         help="put the art you set yourself (in Steam's menu or from SteamGridDB) inside the case, for the games that have it; a copy is kept in this app's own folder, "
                              "your files are not changed. Without this option or --no-custom-art, covers already made from your art keep it")
        art.add_argument("--no-custom-art", dest="use_custom_art", action="store_const", const=False,
                         help="use Steam's own portrait for every cover (covers made from your art are rebuilt)")
        if name == "make":
            p.add_argument("--user", help="Steam account folder id inside userdata/ whose custom art --use-custom-art reads (auto: most recent login)")
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
