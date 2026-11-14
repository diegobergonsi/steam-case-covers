# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Regression tests: normal use, plus the attacks the app must refuse. No network, no real Steam.
Run:  python -m unittest discover -s tests -v"""
import http.server, json, os, re, shutil, socketserver, struct, sys, tempfile, threading, time, unittest, zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_tokens import THEME, contrast
from engine import steamcase as sc
from engine import completion as cp


def make_png(path, w, h):
    """A tiny file that claims to be huge (compresses ~1000:1): a decompression bomb."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    z, body, row = zlib.compressobj(9), b"", b"\x00" + b"\x00" * (w * 3)
    for _ in range(h):
        body += z.compress(row)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", body + z.flush()) + chunk(b"IEND", b""))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patch = mock.patch.object(sc, "originals_dir", return_value=os.path.join(self.tmp, "app-originals"))     # never the real app folder
        patch.start()
        self.addCleanup(patch.stop)
        self.steam = os.path.join(self.tmp, "steam")
        self.cfg = os.path.join(self.steam, "userdata", "111", "config")
        self.grid = os.path.join(self.cfg, "grid")
        os.makedirs(self.grid)
        os.makedirs(os.path.join(self.steam, "config"))
        self.covers = os.path.join(self.tmp, "covers")
        os.makedirs(self.covers)

    def cover(self, appid, data=b"COVER"):
        p = os.path.join(self.covers, "Game_%d.png" % appid)
        with open(p, "wb") as f:
            f.write(data + str(appid).encode())
        return p

    def read(self, *parts):
        with open(os.path.join(*parts), "rb") as f:
            return f.read()

    def resave(self, path, **notes):
        """The same pixels with other notes (None drops a note)."""
        with sc.Image.open(path) as im:
            im.load()
            info = sc.PngInfo()
            for k, v in {**im.info, **notes}.items():
                if v is not None and isinstance(v, str):
                    info.add_text(k, v)
            out = path + ".resaved.png"
            im.save(out, format="PNG", pnginfo=info)
        return out


class ApplyRestore(Base):
    def test_apply_then_restore_returns_original(self):
        with open(os.path.join(self.grid, "1p.png"), "wb") as f:
            f.write(b"ORIGINAL")
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1), self.cover(2)])
        self.assertEqual((r["applied"], r["replaced"]), (2, 1))
        sc.restore_backup(self.steam, r["backup"])
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png"])
        self.assertEqual(self.read(self.grid, "1p.png"), b"ORIGINAL")

    def test_identical_covers_make_no_backup(self):
        fs = [self.cover(1), self.cover(2)]
        sc.apply_covers(self.steam, self.covers, files=fs)
        r = sc.apply_covers(self.steam, self.covers, files=fs)
        self.assertEqual((r["applied"], r["unchanged"], r["backup"]), (0, 2, None))
        self.assertEqual(len(sc.list_backups(self.steam)), 1)

    def test_restore_walks_back_one_step_at_a_time(self):
        with open(os.path.join(self.grid, "1p.png"), "wb") as f:
            f.write(b"ORIGINAL")
        sc.apply_covers(self.steam, self.covers, files=[self.cover(1, b"V1")])
        sc.apply_covers(self.steam, self.covers, files=[self.cover(1, b"V2")])
        sc.restore_backup(self.steam, sc.list_backups(self.steam)[0])
        self.assertTrue(self.read(self.grid, "1p.png").startswith(b"V1"))
        sc.restore_backup(self.steam, sc.list_backups(self.steam)[0])
        self.assertEqual(self.read(self.grid, "1p.png"), b"ORIGINAL")

    def test_failed_apply_rolls_back_and_leaves_no_backup(self):
        with open(os.path.join(self.grid, "1p.png"), "wb") as f:
            f.write(b"ORIG1")
        fs = [self.cover(1), self.cover(2), self.cover(3)]
        real, calls = shutil.copy2, {"n": 0}

        def flaky(src, dst, **k):
            if os.path.dirname(dst) == self.grid:
                calls["n"] += 1
                if calls["n"] == 2:
                    raise PermissionError("read-only")
            return real(src, dst, **k)
        shutil.copy2 = flaky
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.apply_covers(self.steam, self.covers, files=fs)
        finally:
            shutil.copy2 = real
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png"])
        self.assertEqual(self.read(self.grid, "1p.png"), b"ORIG1")
        self.assertEqual(sc.list_backups(self.steam), [])

    def test_missing_cover_files_change_nothing(self):
        fs = [self.cover(1), self.cover(2)]
        os.remove(fs[0])
        with self.assertRaises(sc.SteamcaseError):
            sc.apply_covers(self.steam, self.covers, files=fs)
        self.assertEqual(os.listdir(self.grid), [])
        self.assertEqual(sc.list_backups(self.steam), [])

    def test_rollback_still_works_while_holding_the_lock(self):
        with open(os.path.join(self.grid, "1p.png"), "wb") as f:
            f.write(b"ORIG1")
        fs = [self.cover(1), self.cover(2)]
        real, calls = shutil.copy2, {"n": 0}

        def flaky(src, dst, **k):
            if os.path.dirname(dst) == self.grid:
                calls["n"] += 1
                if calls["n"] == 2:
                    raise PermissionError("disk full")
            return real(src, dst, **k)
        shutil.copy2 = flaky
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.apply_covers(self.steam, self.covers, files=fs)
        finally:
            shutil.copy2 = real
        self.assertEqual(self.read(self.grid, "1p.png"), b"ORIG1")
        self.assertFalse(os.path.exists(os.path.join(self.cfg, ".steamcase.lock")))

    def test_two_applies_in_the_same_second(self):
        for data in (b"A", b"B", b"C"):
            sc.apply_covers(self.steam, self.covers, files=[self.cover(1, data)])
        self.assertEqual(len(sc.list_backups(self.steam)), 3)


    def put(self, name, data=b"HAND-MADE"):
        with open(os.path.join(self.grid, name), "wb") as f:
            f.write(data)

    def test_a_hand_made_jpg_is_moved_to_the_backup_and_comes_back_on_restore(self):
        self.put("1p.jpg")
        self.put("2p.jpg")                                          # a game we do not cover: must stay
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        self.assertEqual(r["jpg_moved"], 1)
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.jpg"])
        sc.restore_backup(self.steam, r["backup"])
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.jpg", "2p.jpg"])
        self.assertEqual(self.read(self.grid, "1p.jpg"), b"HAND-MADE")

    def test_webp_and_jpeg_art_is_moved_too(self):
        self.put("1p.webp")
        self.put("2p.jpeg")
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1), self.cover(2)])
        self.assertEqual(r["jpg_moved"], 2)
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.png"])
        sc.restore_backup(self.steam, r["backup"])
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.webp", "2p.jpeg"])

    def test_reset_everything_removes_other_art_and_restore_brings_it_back(self):
        self.put("1p.png", b"SGDB")                                 # not ours: no frame
        self.put("2p.webp")
        self.put("3p.jpg")
        self.put("3_hero.jpg")                                      # other art kinds are never touched
        r = sc.reset_to_default(self.steam, names=[], everything=True)
        self.assertEqual(r["removed"], 3)
        self.assertEqual(os.listdir(self.grid), ["3_hero.jpg"])
        sc.restore_backup(self.steam, r["backup"])
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.webp", "3_hero.jpg", "3p.jpg"])
        self.assertEqual(self.read(self.grid, "1p.png"), b"SGDB")

    def test_plain_reset_leaves_other_art(self):
        self.put("2p.webp")
        r = sc.reset_to_default(self.steam, names=[])
        self.assertEqual(r["removed"], 0)
        self.assertEqual(os.listdir(self.grid), ["2p.webp"])

    def test_list_accounts_puts_the_chosen_one_first(self):
        os.makedirs(os.path.join(self.steam, "userdata", "5"))
        os.makedirs(os.path.join(self.steam, "userdata", "0"))     # Steam's placeholder folder is not an account
        self.assertEqual(sorted(a for a, _ in sc.list_accounts(self.steam)), ["111", "5"])
        self.assertEqual(sc.list_accounts(self.steam)[0][0], sc.pick_account(self.steam))

    def test_a_jpg_added_after_our_cover_is_still_moved(self):
        fs = [self.cover(1)]
        sc.apply_covers(self.steam, self.covers, files=fs)
        self.put("1p.jpg")                                          # the png is identical, the jpg alone hides it
        r = sc.apply_covers(self.steam, self.covers, files=fs)
        self.assertEqual((r["jpg_moved"], r["replaced"]), (1, 0))
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png"])
        self.assertTrue(r["backup"])

    def test_a_symlinked_jpg_is_left_alone(self):
        target = os.path.join(self.tmp, "elsewhere.jpg")
        with open(target, "wb") as f:
            f.write(b"X")
        os.symlink(target, os.path.join(self.grid, "1p.jpg"))
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        self.assertEqual(r["jpg_moved"], 0)
        self.assertTrue(os.path.islink(os.path.join(self.grid, "1p.jpg")))

    def test_failed_apply_puts_the_jpg_back(self):
        self.put("1p.jpg")
        fs = [self.cover(1), self.cover(2)]
        real = shutil.copy2

        def flaky(src, dst, **k):
            if os.path.dirname(dst) == self.grid:
                raise PermissionError("read-only")
            return real(src, dst, **k)
        shutil.copy2 = flaky
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.apply_covers(self.steam, self.covers, files=fs)
        finally:
            shutil.copy2 = real
        self.assertEqual(os.listdir(self.grid), ["1p.jpg"])
        self.assertEqual(self.read(self.grid, "1p.jpg"), b"HAND-MADE")
        self.assertEqual(sc.list_backups(self.steam), [])

    def test_if_the_rollback_itself_fails_the_backup_is_kept(self):
        self.put("1p.jpg")
        real_copy, real_undo = shutil.copy2, sc._undo

        def broken(src, dst, **k):
            if os.path.dirname(dst) == self.grid:
                raise PermissionError("read-only")
            return real_copy(src, dst, **k)

        def undo_fails(*a, **k):
            raise PermissionError("cannot put it back")
        shutil.copy2, sc._undo = broken, undo_fails
        try:
            with self.assertRaises(sc.SteamcaseError) as ctx:
                sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        finally:
            shutil.copy2, sc._undo = real_copy, real_undo
        backups = sc.list_backups(self.steam)
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.read(backups[0], "1p.jpg"), b"HAND-MADE")      # the user's art survived
        self.assertIn("safe in the backup", str(ctx.exception))

    def test_restore_refuses_a_manifest_that_moves_odd_names(self):
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        mf = os.path.join(r["backup"], "manifest.json")
        with open(mf, "w") as f:
            json.dump({"added": [], "replaced": [], "moved": ["../../evil.jpg"]}, f)
        with self.assertRaises(sc.SteamcaseError):
            sc.restore_backup(self.steam, r["backup"])


class UpdateCheck(unittest.TestCase):
    def releases(self, *rows):
        real = sc.http_get
        sc.http_get = lambda url, tries=3: json.dumps(list(rows)).encode()
        self.addCleanup(setattr, sc, "http_get", real)

    def test_newer_release_is_found_and_the_link_is_built_by_us(self):
        self.releases({"tag_name": "v0.9.10", "html_url": "https://evil.example/x"}, {"tag_name": "v0.9.9"})
        r = sc.check_for_update("v0.9.9")
        self.assertEqual((r["latest"], r["newer"]), ("v0.9.10", True))
        self.assertEqual(r["url"], "https://github.com/diegobergonsi/steam-case-covers/releases/tag/v0.9.10")

    def test_versions_compare_as_numbers_not_text(self):
        self.releases({"tag_name": "v0.9.10"}, {"tag_name": "v0.9.9"})
        self.assertFalse(sc.check_for_update("v0.9.10")["newer"])
        self.assertTrue(sc.check_for_update("v0.9.9")["newer"])
        self.assertFalse(sc.check_for_update("v1.0.0")["newer"])

    def test_drafts_and_odd_tags_are_ignored(self):
        self.releases({"tag_name": "v9.9.9", "draft": True}, {"tag_name": "v1.0.0/../x"}, {"tag_name": "nightly"},
                      {"tag_name": 7}, "junk", None, {"tag_name": "v0.9.8"})
        self.assertEqual(sc.check_for_update("v0.9.8")["latest"], "v0.9.8")

    def test_a_source_run_has_no_version_to_compare(self):
        self.releases({"tag_name": "v0.9.10"})
        r = sc.check_for_update("dev")
        self.assertEqual((r["latest"], r["newer"]), ("v0.9.10", None))

    def test_bad_answers_and_network_errors_become_a_clear_error(self):
        for body in (b"not json", b"{}", b"[]", b"[" * 100000):
            real = sc.http_get
            sc.http_get = lambda url, tries=3, b=body: b
            try:
                with self.assertRaises(sc.SteamcaseError):
                    sc.check_for_update("v0.9.9")
            finally:
                sc.http_get = real

        def down(url, tries=3):
            raise OSError("no route")
        real, sc.http_get = sc.http_get, down
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.check_for_update("v0.9.9")
        finally:
            sc.http_get = real

    def test_a_stamped_version_must_look_like_a_tag(self):
        self.assertEqual(sc.version_tuple("v0.9.10"), (0, 9, 10))
        for bad in ("dev", "0.9.10", "v1.0", "v1.0.0-rc1", "v1.0.0\nx", "", None, 5):
            self.assertIsNone(sc.version_tuple(bad))


class Reset(Base):
    """Removing our covers so Steam shows its own art again, without touching art the user set themselves."""

    def real_cover(self, appid, color=(200, 60, 60)):
        """A genuine steamcase cover, built by the app itself."""
        if sc.Image is None:
            self.skipTest("Pillow missing")
        src = os.path.join(self.tmp, "portrait_%d.png" % appid)
        sc.Image.new("RGB", (600, 900), color).save(src)
        out = os.path.join(self.grid, "%dp.png" % appid)
        sc.build_cover(src, out, sc.Image.open(sc.FRAME).convert("RGBA"))
        return out

    def users_own_art(self, appid):
        p = os.path.join(self.grid, "%dp.png" % appid)
        sc.Image.new("RGBA", (600, 900), (30, 60, 90, 255)).save(p)         # same size, but not our frame
        return p

    def test_recognises_only_our_covers(self):
        ours = self.real_cover(1)
        mine = self.users_own_art(2)
        jpg = os.path.join(self.grid, "3p.png")
        sc.Image.new("RGB", (600, 900)).save(jpg, "JPEG")                  # a JPEG wearing a .png name
        tampered = self.real_cover(4)
        im = sc.Image.open(tampered).convert("RGBA")
        im.putpixel((300, 40), (255, 0, 0, 255))
        im.save(tampered)
        self.assertEqual([sc.is_steamcase_cover(p) for p in (ours, mine, jpg, tampered)], [True, False, False, False])

    def test_reset_removes_ours_keeps_the_users_art_and_can_be_undone(self):
        for i in (1, 2, 3):
            self.real_cover(i)
        mine = self.users_own_art(9)
        before = self.read(mine)
        os.makedirs(os.path.join(self.tmp, "elsewhere"))
        r = sc.reset_to_default(self.steam)
        self.assertEqual(r["removed"], 3)
        self.assertEqual(os.listdir(self.grid), ["9p.png"])
        self.assertEqual(self.read(mine), before)
        sc.restore_backup(self.steam, r["backup"])                          # undo
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.png", "3p.png", "9p.png"])
        self.assertTrue(all(sc.is_steamcase_cover(os.path.join(self.grid, "%dp.png" % i)) for i in (1, 2, 3)))

    def test_reset_keeps_the_covers_it_is_told_to_keep_even_when_it_removes_other_art(self):
        for i in (1, 2, 3):
            self.real_cover(i)
        sc.Image.new("RGBA", (50, 50), (1, 2, 3, 255)).save(os.path.join(self.grid, "8p.png"))       # not ours: a custom picture
        names = sc.find_our_covers(self.steam)
        r = sc.reset_to_default(self.steam, names=[n for n in names if n != "2p.png"], everything=True, keep=["2p.png"])
        self.assertEqual(r["removed"], 3)                                  # 1p, 3p and the custom 8p
        self.assertEqual(sorted(os.listdir(self.grid)), ["2p.png"])
        sc.restore_backup(self.steam, r["backup"])
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.png", "3p.png", "8p.png"])

    def test_reset_without_keep_removes_everything_as_before(self):
        for i in (1, 2):
            self.real_cover(i)
        sc.reset_to_default(self.steam, names=sc.find_our_covers(self.steam), everything=True)
        self.assertEqual(os.listdir(self.grid), [])

    def test_reset_with_nothing_to_remove_makes_no_backup(self):
        self.users_own_art(9)
        r = sc.reset_to_default(self.steam)
        self.assertEqual((r["removed"], r["backup"]), (0, None))
        self.assertEqual(sc.list_backups(self.steam), [])

    def test_reset_never_touches_symlinks_or_odd_names(self):
        self.real_cover(5)
        self.real_cover(6)
        shutil.copy(os.path.join(self.grid, "6p.png"), os.path.join(self.grid, "6_hero.png"))      # not an <appid>p.png name
        try:
            os.symlink(os.path.join(self.grid, "5p.png"), os.path.join(self.grid, "7p.png"))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed here")
        r = sc.reset_to_default(self.steam)
        self.assertEqual(r["removed"], 2)                                  # 5p.png and 6p.png only
        self.assertEqual(sorted(os.listdir(self.grid)), ["6_hero.png", "7p.png"])
        self.assertTrue(os.path.islink(os.path.join(self.grid, "7p.png")))

    def test_reset_failure_puts_everything_back(self):
        for i in (1, 2, 3):
            self.real_cover(i)
        real, calls = os.replace, {"n": 0}

        def flaky(src, dst):
            if os.path.dirname(src) == self.grid:
                calls["n"] += 1
                if calls["n"] == 2:
                    raise PermissionError("locked")
            return real(src, dst)
        os.replace = flaky
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.reset_to_default(self.steam)
        finally:
            os.replace = real
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.png", "3p.png"])
        self.assertEqual(sc.list_backups(self.steam), [])

    def test_cli_reset(self):
        self.real_cover(1)
        self.users_own_art(2)
        argv, sys.argv = sys.argv, ["steamcase", "reset", "--steam-dir", self.steam, "--yes"]
        try:
            sc.main()
        finally:
            sys.argv = argv
        self.assertEqual(os.listdir(self.grid), ["2p.png"])


class ReplaceRetry(Base):
    def test_replace_waits_out_a_brief_lock_but_not_a_permanent_one(self):
        src, dst = os.path.join(self.tmp, "a"), os.path.join(self.tmp, "b")
        open(src, "w").write("x")
        real, calls = os.replace, []

        def flaky(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("locked")
            return real(a, b)
        os.replace = flaky
        try:
            sc._replace(src, dst)
            self.assertEqual((len(calls), os.path.exists(dst)), (3, True))
            os.replace = lambda a, b: (_ for _ in ()).throw(PermissionError("locked"))
            with self.assertRaises(PermissionError):
                sc._replace(dst, src, tries=2)
        finally:
            os.replace = real


class SteamProcess(Base):
    def _ps(self, output):
        real = sc.subprocess.run
        sc.subprocess.run = lambda *a, **k: type("R", (), {"stdout": output})()
        try:
            return sc.steam_running()
        finally:
            sc.subprocess.run = real

    def test_tasklist_runs_without_a_console_window_on_windows(self):
        """A black console window used to flash every 3 seconds (and take the focus) because tasklist was started with a console."""
        seen = {}
        real_run, real_platform, real_flag = sc.subprocess.run, sc.sys.platform, sc._NO_WINDOW
        sc.subprocess.run = lambda *a, **k: seen.update(k) or type("R", (), {"stdout": "steam.exe"})()
        sc.sys.platform, sc._NO_WINDOW = "win32", 0x08000000
        try:
            self.assertTrue(sc.steam_running())
        finally:
            sc.subprocess.run, sc.sys.platform, sc._NO_WINDOW = real_run, real_platform, real_flag
        self.assertEqual(seen.get("creationflags"), 0x08000000)

    @unittest.skipIf(sys.platform.startswith("win"), "uses ps output")
    def test_steam_is_found_by_short_name_on_linux(self):
        self.assertTrue(self._ps("systemd\nsteam\nbash\n"))
        self.assertFalse(self._ps("systemd\nbash\nsteamos-manager\n"))

    @unittest.skipIf(sys.platform.startswith("win"), "uses ps output")
    def test_steam_is_found_by_full_path_on_macos(self):
        self.assertTrue(self._ps("/sbin/launchd\n/Applications/Steam.app/Contents/MacOS/steam_osx\n"))
        self.assertTrue(self._ps("/usr/bin/foo\n/Users/me/Library/Application Support/Steam/Steam.AppBundle/Steam/Contents/MacOS/steamwebhelper\n"))
        self.assertFalse(self._ps("/sbin/launchd\n/Applications/Safari.app/Contents/MacOS/Safari\n/usr/bin/steamer\n"))


class Network(Base):
    def test_trusted_certificates_are_loaded(self):
        self.assertGreater(sc._ssl_context().cert_store_stats()["x509_ca"], 0)

    def test_errors_are_explained_in_plain_words(self):
        import ssl
        import urllib.error
        cert = urllib.error.URLError(ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"))
        self.assertIn("security certificate", sc.explain_error(cert))
        self.assertIn("DNS", sc.explain_error(urllib.error.URLError(OSError(-2, "Name or service not known"))))
        self.assertIn("timed out", sc.explain_error(TimeoutError("timed out")))
        self.assertIn("404", sc.explain_error(urllib.error.HTTPError("u", 404, "nf", {}, None)))

    def test_the_real_reason_reaches_the_user(self):
        import ssl
        import urllib.error
        real_get = sc.http_get
        sc.http_get = lambda url, tries=3: (_ for _ in ()).throw(urllib.error.URLError(ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED")))
        try:
            with self.assertRaises(sc.SteamcaseError) as cm:
                sc.make_covers({1: "G"}, os.path.join(self.tmp, "cv"))
        finally:
            sc.http_get = real_get
        self.assertIn("security certificate", str(cm.exception))
        self.assertNotIn("Check your internet connection and try again", str(cm.exception))


class Progress(Base):
    def test_progress_counts_only_items_that_can_become_covers(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), (10, 80, 160)).save(buf, "PNG")
        kinds = {1: 0, 2: 0, 3: 4, 4: 4, 5: 4, 6: 0, 7: None, 8: None}        # 0 = game, 4 = DLC, None = Steam no longer lists it
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": kinds[i], "name": "Item %d" % i, "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}} for i in ids if kinds[i] is not None}
        sc.http_get = lambda url, tries=3: buf.getvalue()
        seen = []
        try:
            r = sc.make_covers({i: None for i in kinds}, os.path.join(self.tmp, "cv"), progress=lambda d, t, a, n, s: seen.append((d, t)))
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        self.assertEqual((r["ok"], r["not_games"], r["unlisted"]), (3, 3, 2))
        self.assertEqual(seen[-1], (3, 3))                              # "3 of 3", not "6 of 6"
        self.assertTrue(all(t == 3 for _, t in seen))


class Playtests(Base):
    def test_a_playtest_gets_a_cover_like_a_game(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), (10, 80, 160)).save(buf, "PNG")
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 12, "name": "G Playtest", "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}} for i in ids}      # 12 = Steam's type for a playtest
        sc.http_get = lambda url, tries=3: buf.getvalue()
        try:
            self.assertEqual(sc.list_games({1: None}), [(1, "G Playtest")])
            r = sc.make_covers({1: None}, os.path.join(self.tmp, "cv"))
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        self.assertEqual((r["ok"], r["not_games"]), (1, 0))


class Software(Base):
    def make(self, items, **kw):
        """(list_games result, make_covers result) with Steam answering `items` ({appid: store item}, an id missing from it is one Steam no longer lists)."""
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), (10, 80, 160)).save(buf, "PNG")
        art = {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}
        full = {i: dict(it, assets=art) for i, it in items.items()}
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: full[i] for i in ids if i in full}
        sc.http_get = lambda url, tries=3: buf.getvalue()
        try:
            games = {i: None for i in items}
            return sc.list_games(games, **kw), sc.make_covers(games, os.path.join(self.tmp, "cv"), **kw)
        finally:
            sc.store_items, sc.http_get = real_store, real_get

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_software_is_skipped_by_default(self):
        listed, r = self.make({1: {"type": 6, "name": "Lossless Scaling"}})
        self.assertEqual(listed, [])
        self.assertEqual((r["ok"], r["not_games"]), (0, 1))

    def test_software_gets_a_cover_with_the_switch(self):
        listed, r = self.make({1: {"type": 6, "name": "Lossless Scaling"}}, software=True)
        self.assertEqual(listed, [(1, "Lossless Scaling")])
        self.assertEqual((r["ok"], r["not_games"]), (1, 0))

    def test_tools_and_other_types_stay_skipped_with_the_switch(self):
        listed, r = self.make({1: {"type": 6, "name": "Proton 9.0"}, 2: {"type": 1, "name": "A Demo"}, 3: {"type": 4, "name": "Some DLC"}}, software=True)
        self.assertEqual(listed, [])
        self.assertEqual((r["ok"], r["not_games"]), (0, 3))

    def test_software_without_a_name_stays_unlisted_with_the_switch(self):
        listed, r = self.make({1: {"type": 0, "name": "Game"}, 2: {"type": 6}}, software=True)
        self.assertEqual(listed, [(1, "Game")])
        self.assertEqual((r["ok"], r["unlisted"], r["not_games"]), (1, 1, 0))


class NonSteam(Base):
    def test_a_shortcut_with_art_gets_a_cover_and_is_counted(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), (10, 80, 160)).save(buf, "PNG")
        art = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), (160, 30, 30)).save(art, format="JPEG")
        shortcut = 3998375076                                           # an id as big as Steam gives to games added by hand
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {1: {"type": 0, "name": "Game", "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}}}      # Steam knows nothing of the shortcut
        sc.http_get = lambda url, tries=3: buf.getvalue()
        out = os.path.join(self.tmp, "cv")
        try:
            r = sc.make_covers({1: None, shortcut: "My Shortcut"}, out, custom_art={shortcut: art})
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        cover = os.path.join(out, "My_Shortcut_%d.png" % shortcut)
        self.assertTrue(os.path.isfile(cover))
        self.assertIsNotNone(sc.cover_art(cover))
        self.assertEqual((r["ok"], r["unlisted"], r["not_games"], r["failed"], r["missing"]), (2, 0, 0, [], []))


class Concurrency(Base):
    def test_simultaneous_applies_never_lose_covers(self):
        files = [self.cover(i) for i in range(1, 41)]
        results = []

        def go():
            try:
                results.append(sc.apply_covers(self.steam, self.covers, files=files)["applied"])
            except sc.SteamcaseError as e:
                results.append(str(e))
        threads = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertIn(40, results)                                       # one run did the work
        self.assertEqual(len(os.listdir(self.grid)), 40)                 # and nobody removed anything
        self.assertEqual([f for f in os.listdir(self.grid) if not f.endswith("p.png")], [])
        self.assertFalse(os.path.exists(os.path.join(self.cfg, ".steamcase.lock")))

    def test_stale_lock_from_a_crashed_run_is_ignored(self):
        lock = os.path.join(self.cfg, ".steamcase.lock")
        os.makedirs(lock)
        old = time.time() - 3600
        os.utime(lock, (old, old))
        self.assertEqual(sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])["applied"], 1)

    def dead_pid(self):
        import subprocess
        p = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
        return int(p.stdout)                                           # that process has ended and been collected

    def test_the_lock_records_who_holds_it(self):
        with sc._Lock(self.cfg):
            with open(os.path.join(self.cfg, ".steamcase.lock", "pid")) as f:
                self.assertEqual(f.read().strip(), str(os.getpid()))
        self.assertFalse(os.path.exists(os.path.join(self.cfg, ".steamcase.lock")))

    def test_a_lock_left_by_a_run_that_is_gone_is_taken_over_at_once(self):
        lock = os.path.join(self.cfg, ".steamcase.lock")
        os.makedirs(lock)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(str(self.dead_pid()))                              # fresh lock, but its owner crashed
        self.assertEqual(sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])["applied"], 1)

    def test_a_lock_held_by_a_live_run_is_respected(self):
        lock = os.path.join(self.cfg, ".steamcase.lock")
        os.makedirs(lock)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(str(os.getpid()))                                  # this process is alive
        with self.assertRaises(sc.SteamcaseError) as cm:
            sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        self.assertIn("Another steamcase window", str(cm.exception))

    def test_an_old_lock_of_a_live_run_is_still_respected(self):
        lock = os.path.join(self.cfg, ".steamcase.lock")
        os.makedirs(lock)
        with open(os.path.join(lock, "pid"), "w") as f:
            f.write(str(os.getpid()))                                  # alive, and a long Apply on a slow card can take more than ten minutes
        os.utime(lock, (1, 1))
        with self.assertRaises(sc.SteamcaseError):
            sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])

    def test_leaving_never_removes_a_lock_that_another_run_now_holds(self):
        lock = os.path.join(self.cfg, ".steamcase.lock")
        with sc._Lock(self.cfg):
            with open(os.path.join(lock, "pid"), "w") as f:
                f.write(str(os.getpid() + 1))                          # taken over by someone else meanwhile
        self.assertTrue(os.path.isdir(lock))

    def test_a_fresh_lock_with_no_owner_written_yet_is_respected(self):
        os.makedirs(os.path.join(self.cfg, ".steamcase.lock"))
        with self.assertRaises(sc.SteamcaseError):
            sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])

    def test_a_half_copied_file_left_by_a_crashed_run_is_removed_by_apply_restore_and_reset(self):
        junk = os.path.join(self.grid, "10p.png.730352.488da39e.tmp")
        mine = os.path.join(self.grid, "notes.tmp")                     # not ours: must stay
        os.makedirs(self.grid, exist_ok=True)
        for p in (junk, mine):
            with open(p, "wb") as f:
                f.write(b"x" * 100)
        r = sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        self.assertFalse(os.path.exists(junk))
        self.assertTrue(os.path.exists(mine))
        with open(junk, "wb") as f:
            f.write(b"x")
        sc.restore_backup(self.steam, r["backup"])
        self.assertFalse(os.path.exists(junk))
        with open(junk, "wb") as f:
            f.write(b"x")
        sc.apply_covers(self.steam, self.covers, files=[self.cover(1)])
        with open(junk, "wb") as f:
            f.write(b"x")
        sc.reset_to_default(self.steam, names=["1p.png"])               # something to remove, so Reset does its work
        self.assertFalse(os.path.exists(junk))
        self.assertTrue(os.path.exists(mine))

    def test_simultaneous_makes_do_not_trip_over_each_other(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), (10, 80, 160)).save(buf, "PNG")
        games = {i: "Game %d" % i for i in range(1, 31)}
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 0, "name": games[i], "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}} for i in ids}
        sc.http_get = lambda url, tries=3: buf.getvalue()
        out = []
        try:
            threads = [threading.Thread(target=lambda: out.append(sc.make_covers(games, os.path.join(self.tmp, "cv")))) for _ in range(3)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        self.assertTrue(all(len(r["failed"]) == 0 for r in out), [len(r["failed"]) for r in out])
        left = os.listdir(os.path.join(self.tmp, "cv"))
        self.assertEqual(len([f for f in left if f.endswith(".png")]), 30)
        self.assertEqual([f for f in left if not f.endswith(".png")], [])


class Attacks(Base):
    def test_two_cover_files_for_one_game_apply_only_the_newest(self):
        old, new = self.cover(5, b"OLD"), os.path.join(self.covers, "Renamed_5.png")
        with open(new, "wb") as f:
            f.write(b"NEW5")
        os.utime(old, (1, 1))                                                    # the older file, as a game renamed by Steam leaves it
        info = sc.apply_covers(self.steam, self.covers)
        self.assertEqual(self.read(self.grid, "5p.png"), b"NEW5")
        self.assertEqual(info["applied"], 1)
        manifest = json.loads(self.read(info["backup"], "manifest.json")) if info["backup"] else {"added": ["5p.png"]}
        self.assertEqual(manifest["added"], ["5p.png"])

    def test_an_empty_pick_applies_nothing_instead_of_everything(self):
        self.cover(6)
        with self.assertRaises(sc.SteamcaseError):
            sc.apply_covers(self.steam, self.covers, files=[])
        self.assertFalse(os.path.exists(os.path.join(self.grid, "6p.png")))

    def test_a_full_disk_while_backing_up_leaves_the_grid_as_it_was_and_no_half_backup(self):
        with open(os.path.join(self.grid, "7p.png"), "wb") as f:
            f.write(b"STEAMS")
        self.cover(7, b"NEW")
        real = shutil.copy2

        def full(src, dst, **kw):
            if sc.BACKUP_PREFIX not in dst:
                return real(src, dst, **kw)                                       # only the copy into the backup runs out of room
            with open(dst, "wb") as f:
                f.write(b"PART")                                                  # the disk filled up halfway through the copy
            raise OSError(28, "No space left on device")
        with mock.patch.object(shutil, "copy2", full), self.assertRaises(sc.SteamcaseError) as cm:
            sc.apply_covers(self.steam, self.covers)
        self.assertEqual(self.read(self.grid, "7p.png"), b"STEAMS")
        self.assertEqual([d for d in os.listdir(self.cfg) if d.startswith(sc.BACKUP_PREFIX)], [])      # no folder that Restore would refuse
        self.assertNotIn("Restore", str(cm.exception))

    def test_manifest_with_path_traversal_is_refused(self):
        victim = os.path.join(self.tmp, "victim.txt")
        open(victim, "w").write("DATA")
        bk = os.path.join(self.cfg, "grid_backup_20260101_000000")
        os.makedirs(bk)
        json.dump({"added": ["../../../../../victim.txt"], "replaced": []}, open(os.path.join(bk, "manifest.json"), "w"))
        with self.assertRaises(sc.SteamcaseError):
            sc.restore_backup(self.steam, bk, keep=True)
        self.assertTrue(os.path.exists(victim))

    def test_restore_refuses_folders_that_are_not_backups(self):
        doc = os.path.join(self.tmp, "Documents")
        os.makedirs(doc)
        open(os.path.join(doc, "thesis.docx"), "w").write("WORK")
        json.dump({"added": [], "replaced": []}, open(os.path.join(doc, "manifest.json"), "w"))
        with self.assertRaises(sc.SteamcaseError):
            sc.restore_backup(self.steam, doc)
        self.assertTrue(os.path.exists(os.path.join(doc, "thesis.docx")))

    def test_cli_backup_option_takes_a_name_not_a_path(self):
        doc = os.path.join(self.tmp, "Documents")
        os.makedirs(doc)
        json.dump({"added": [], "replaced": []}, open(os.path.join(doc, "manifest.json"), "w"))
        os.makedirs(os.path.join(self.cfg, "grid_backup_20260101_000000"))
        json.dump({"added": [], "replaced": []}, open(os.path.join(self.cfg, "grid_backup_20260101_000000", "manifest.json"), "w"))
        argv, sys.argv = sys.argv, ["steamcase", "restore", "--steam-dir", self.steam, "--backup", doc, "--yes"]
        try:
            with self.assertRaises(SystemExit):
                sc.main()
        finally:
            sys.argv = argv
        self.assertTrue(os.path.isdir(doc))

    def test_symlink_in_grid_is_replaced_not_followed(self):
        target = os.path.join(self.tmp, "target.txt")
        open(target, "w").write("PRECIOUS")
        try:
            os.symlink(target, os.path.join(self.grid, "7p.png"))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed here (Windows without developer mode)")
        sc.apply_covers(self.steam, self.covers, files=[self.cover(7)])
        self.assertEqual(open(target).read(), "PRECIOUS")
        self.assertFalse(os.path.islink(os.path.join(self.grid, "7p.png")))

    def test_deeply_nested_library_file(self):
        p = os.path.join(self.tmp, "deep.json")
        open(p, "w").write("[" * 200000 + "]" * 200000)
        with self.assertRaises(sc.SteamcaseError):
            sc.owned_ids(p)

    def test_library_file_with_absurd_size_or_count(self):
        p = os.path.join(self.tmp, "huge.json")
        json.dump({"rgOwnedApps": list(range(1, sc.MAX_APPS + 2))}, open(p, "w"))
        with self.assertRaises(sc.SteamcaseError):
            sc.owned_ids(p)

    def test_an_empty_game_list_is_called_empty_not_missing(self):
        p = os.path.join(self.tmp, "empty.json")
        json.dump({"rgOwnedApps": []}, open(p, "w"))
        with self.assertRaises(sc.SteamcaseError) as cm:
            sc.owned_ids(p)
        self.assertIn("is empty", str(cm.exception))
        self.assertNotIn("has no game list", str(cm.exception))
        json.dump({"rgOwnedApps": "x"}, open(p, "w"))
        with self.assertRaises(sc.SteamcaseError) as cm:
            sc.owned_ids(p)
        self.assertIn("has no game list", str(cm.exception))                    # the control: a file without a list still says so

    def test_only_takes_real_app_ids(self):
        import subprocess
        for bad in ("-1", "0", "99999999999"):
            r = subprocess.run([sys.executable, "-m", "engine", "make", "--only", bad], capture_output=True, text=True, cwd=sc.HERE)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("--only", r.stderr, bad)

    def test_a_library_saved_while_logged_out_gets_a_clear_message(self):
        p = os.path.join(self.tmp, "loggedout.json")
        json.dump({"rgWishlist": [], "rgOwnedPackages": [], "rgOwnedApps": [], "rgFollowedApps": []}, open(p, "w"))
        with self.assertRaises(sc.SteamcaseError) as cm:
            sc.owned_ids(p)
        self.assertIn("not logged in", str(cm.exception))

    def test_download_button_opens_the_login_page_with_a_fresh_address_each_time(self):
        a, b = sc.library_login_url(), sc.library_login_url()
        self.assertNotEqual(a, b)                                          # never the browser's cached (logged-out) copy
        for u in (a, b):
            self.assertTrue(u.startswith("https://store.steampowered.com/login/?redir=dynamicstore%2Fuserdata%2F%3Fcb%3D"))
            self.assertTrue(u.endswith("&redir_ssl=1"))

    def test_invalid_app_ids_are_dropped(self):
        p = os.path.join(self.tmp, "ids.json")
        json.dump({"rgOwnedApps": [-5, 0, 10 ** 30, 413150]}, open(p, "w"))
        self.assertEqual(sc.owned_ids(p), [413150])

    def test_a_game_list_with_numbers_that_are_not_whole_ids_is_called_damaged(self):
        p = os.path.join(self.tmp, "odd.json")
        for text in ('{"rgOwnedApps":[Infinity]}', '{"rgOwnedApps":[1.9, 5]}', '{"rgOwnedApps":[true]}', '{"rgOwnedApps":["abc"]}'):
            with open(p, "w") as f:
                f.write(text)
            with self.assertRaises(sc.SteamcaseError, msg=text) as cm:
                sc.owned_ids(p)
            self.assertIn("damaged", str(cm.exception), text)

    def test_oversized_download_is_refused(self):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(sc.MAX_DOWNLOAD + 1))
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = socketserver.TCPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sc.ALLOW_LOCAL_HTTP = True
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.http_get("http://127.0.0.1:%d/x" % srv.server_address[1], tries=1)
        finally:
            sc.ALLOW_LOCAL_HTTP = False
            srv.shutdown()
            srv.server_close()

    def test_only_https_addresses_are_ever_opened(self):
        for bad in ("file:///etc/passwd", "http://store.steampowered.com/x", "ftp://example.com/a", "http://127.0.0.1:1/x", "//example.com/x", "javascript:alert(1)"):
            with self.assertRaises(sc.SteamcaseError, msg=bad):
                sc.http_get(bad, tries=1)

    def test_a_redirect_to_a_plain_http_page_is_refused(self):
        class R(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "http://example.invalid/downgraded")
                self.end_headers()

            def log_message(self, *a):
                pass
        srv = socketserver.TCPServer(("127.0.0.1", 0), R)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sc.ALLOW_LOCAL_HTTP = True
        try:
            with self.assertRaises(sc.SteamcaseError) as cm:
                sc.http_get("http://127.0.0.1:%d/x" % srv.server_address[1], tries=1)
        finally:
            sc.ALLOW_LOCAL_HTTP = False
            srv.shutdown()
            srv.server_close()
        self.assertIn("not https", str(cm.exception))

    def test_decompression_bomb_image_is_refused(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        bomb = os.path.join(self.tmp, "bomb.png")
        make_png(bomb, 6000, 6000)                       # 36 MP from a few KB
        with self.assertRaises(sc.SteamcaseError):
            sc.build_cover(bomb, os.path.join(self.tmp, "o.png"), sc.Image.open(sc.FRAME).convert("RGBA"))

    def test_lookalike_digits_are_refused(self):
        self.assertIsNone(sc._COVER_NAME.match("\u0661\u0662\u0663p.png"))
        self.assertIsNone(sc.appid_of("Game_\u0661\u0662\u0663.png"))
        os.makedirs(os.path.join(self.steam, "userdata", "\u00b2"))
        self.assertEqual(sc.pick_account(self.steam), "111")
        with self.assertRaises(sc.SteamcaseError):
            sc.pick_account(self.steam, "\u00b2")

    def test_symlinked_file_inside_a_backup_is_not_copied(self):
        secret = os.path.join(self.tmp, "secret.txt")
        open(secret, "w").write("TOP SECRET")
        bk = os.path.join(self.cfg, "grid_backup_20260101_000000")
        os.makedirs(bk)
        try:
            os.symlink(secret, os.path.join(bk, "5p.png"))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed here")
        json.dump({"added": [], "replaced": ["5p.png"]}, open(os.path.join(bk, "manifest.json"), "w"))
        sc.restore_backup(self.steam, bk, keep=True)
        self.assertFalse(os.path.exists(os.path.join(self.grid, "5p.png")))

    def test_nested_manifest_is_a_clean_error(self):
        bk = os.path.join(self.cfg, "grid_backup_20260101_000000")
        os.makedirs(bk)
        open(os.path.join(bk, "manifest.json"), "w").write("[" * 100000)
        with self.assertRaises(sc.SteamcaseError):
            sc.restore_backup(self.steam, bk, keep=True)

    def test_only_png_jpeg_webp_images_are_decoded(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        frame = sc.Image.open(sc.FRAME).convert("RGBA")
        for ext in ("tif", "gif", "bmp"):
            p = os.path.join(self.tmp, "x." + ext)
            sc.Image.new("RGB", (10, 10)).save(p)
            with self.assertRaises(Exception):
                sc.build_cover(p, os.path.join(self.tmp, "o.png"), frame)

    def test_a_login_page_instead_of_art_counts_as_a_connection_problem(self):
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {1: {"type": 0, "name": "G", "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/c.jpg"}}}
        sc.http_get = lambda url, tries=3: b"<html>Please log in to the WiFi</html>"
        try:
            r = sc.make_covers({1: "G"}, os.path.join(self.tmp, "cv"))
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        self.assertEqual((len(r["failed"]), len(r["missing"])), (1, 0))

    def test_a_missing_2x_image_falls_back_to_the_1x_one(self):
        # ARK: Survival Evolved lists a 2x portrait that Steam answers 404 for, while the 1x one exists
        assets = {"asset_url_format": "steam/apps/1/${FILENAME}", "library_capsule_2x": "library_600x900_2x.jpg", "library_capsule": "library_600x900.jpg"}
        urls, _ = sc.portrait_candidates(1, {"assets": assets})
        self.assertTrue(any(u.split("?")[0].endswith("/library_600x900.jpg") for u in urls))
        self.assertTrue(urls[-1].endswith("/steam/apps/1/library_600x900.jpg"))

    def test_a_real_2x_portrait_is_not_called_blurry_because_of_the_1x_one(self):
        assets = {"asset_url_format": "steam/apps/1/${FILENAME}", "library_capsule_2x": "library_600x900_2x.jpg", "library_capsule": "portrait.png"}
        self.assertFalse(sc.portrait_candidates(1, {"assets": assets})[1])

    def test_a_cover_is_made_from_the_1x_image_when_the_2x_one_is_a_404(self):
        import io, urllib.error
        buf = io.BytesIO()
        sc.Image.new("RGB", (600, 900), "red").save(buf, "PNG")
        real_store, real_get = sc.store_items, sc.http_get
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {1: {"type": 0, "name": "G", "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "p_2x.jpg", "library_capsule": "p.jpg"}}}
        def get(url, tries=3):
            if "_2x" in url:
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            return buf.getvalue()
        sc.http_get = get
        try:
            r = sc.make_covers({1: "G"}, os.path.join(self.tmp, "cv"))
        finally:
            sc.store_items, sc.http_get = real_store, real_get
        self.assertEqual((r["ok"], r["missing"], r["failed"]), (1, [], []))

    def test_hostile_api_data_cannot_change_the_download_host(self):
        import urllib.parse
        for key in ("../../../x", "@evil.example/p.jpg", "p.jpg\r\nHost: evil.example"):
            urls, _ = sc.portrait_candidates(1, {"assets": {"asset_url_format": "steam/apps/1/${FILENAME}", "library_capsule_2x": key}})
            self.assertEqual(urllib.parse.urlparse(urls[0]).hostname, "shared.fastly.steamstatic.com")

    def test_file_names_are_safe(self):
        self.assertEqual(sc.slug("../../etc/passwd"), "etc_passwd")
        self.assertLessEqual(len(sc.slug("X" * 500).encode()), 60)
        self.assertIsNone(sc.appid_of("Game_99999999999.png"))
        self.assertIsNone(sc.appid_of("Game_0.png"))


def write_packageinfo(path, packages, magic=0x06565528):
    """A packageinfo.vdf in Steam's real layout: header, then one binary key-value tree per package, then 0xFFFFFFFF."""
    def kv(d):
        out = b""
        for k, v in d.items():
            key = k.encode() + b"\0"
            out += (b"\x00" + key + kv(v)) if isinstance(v, dict) else (b"\x02" + key + struct.pack("<i", v))
        return out + b"\x08"
    body = struct.pack("<II", magic, 1)
    for pid, apps in packages.items():
        body += struct.pack("<I", pid) + b"\0" * 20 + struct.pack("<I", 7)
        if magic >= 0x06565528:
            body += b"\0" * 8
        body += kv({str(pid): {"packageid": pid, "appids": {str(i): a for i, a in enumerate(apps)}}})
    with open(path, "wb") as f:
        f.write(body + struct.pack("<I", 0xFFFFFFFF))


class FamilyOwnership(Base):
    """Which apps are yours, through packages as well as through the owned-apps list."""

    def packageinfo(self, packages, **kw):
        os.makedirs(os.path.join(self.steam, "appcache"), exist_ok=True)
        path = os.path.join(self.steam, "appcache", "packageinfo.vdf")
        write_packageinfo(path, packages, **kw)
        return path

    def test_package_apps_reads_the_apps_of_the_listed_packages(self):
        self.packageinfo({0: [570, 340], 7: [100], 8: [200]})
        self.assertEqual(sc.package_apps(self.steam, [0, 7]), {570, 340, 100})

    def test_package_apps_also_reads_the_older_header_without_a_token(self):
        self.packageinfo({0: [570], 7: [100]}, magic=0x06565527)
        self.assertEqual(sc.package_apps(self.steam, [0, 7]), {570, 100})

    def test_package_apps_is_none_when_the_file_is_missing_truncated_garbage_or_huge(self):
        self.assertIsNone(sc.package_apps(self.steam, [0]))                       # no file
        path = self.packageinfo({0: [570], 7: [100]})
        good = self.read(path)
        for bad in (good[:len(good) // 2], os.urandom(4096), struct.pack("<II", 0x12345678, 1) + good[8:]):
            with open(path, "wb") as f:
                f.write(bad)
            self.assertIsNone(sc.package_apps(self.steam, [0, 7]))
        with open(path, "wb") as f:
            f.write(good)
        real = sc.MAX_PACKAGEINFO
        sc.MAX_PACKAGEINFO = 10
        self.addCleanup(setattr, sc, "MAX_PACKAGEINFO", real)
        self.assertIsNone(sc.package_apps(self.steam, [0, 7]))                    # over the size cap

    def test_package_apps_is_none_when_the_file_lacks_most_of_your_packages(self):
        # e.g. Steam is logged into another account, or its appcache was just cleared: the file parses but is not about you
        self.packageinfo({})
        self.assertIsNone(sc.package_apps(self.steam, [0, 5]))
        self.packageinfo({i: [100 + i] for i in range(8)})
        self.assertIsNone(sc.package_apps(self.steam, list(range(10))))             # 8 of 10 found
        self.packageinfo({i: [100 + i] for i in range(10)})
        self.assertEqual(sc.package_apps(self.steam, list(range(10))), {100 + i for i in range(10)})

    def test_package_apps_refuses_a_file_over_16_mb(self):
        # a real packageinfo.vdf is a few hundred KB; a huge one could only make us use a lot of memory
        path = self.packageinfo({0: [570]})
        self.assertEqual(sc.package_apps(self.steam, [0]), {570})
        with open(path, "ab") as f:
            f.write(b"\0" * (17 * 1024 * 1024))                                      # padding after the end marker, which the parser would ignore
        self.assertIsNone(sc.package_apps(self.steam, [0]))

    def test_package_apps_survives_a_tree_of_an_odd_shape(self):
        path = self.packageinfo({})
        tree = b"\x01" + b"7\0" + b"x\0" + b"\x08"                                   # {"7": "x"}: a string where a section belongs
        with open(path, "wb") as f:
            f.write(struct.pack("<II", 0x06565528, 1) + struct.pack("<I", 7) + b"\0" * 32 + tree + struct.pack("<I", 0xFFFFFFFF))
        self.assertIsNone(sc.package_apps(self.steam, [7]))                         # no AttributeError, and nothing found for package 7

    def test_owned_packages_reads_the_list_and_tolerates_a_missing_key(self):
        lib = os.path.join(self.tmp, "userdata.json")
        with open(lib, "w") as f:
            json.dump({"rgOwnedApps": [1], "rgOwnedPackages": [0, 5, "x", -1, 2 ** 40]}, f)
        self.assertEqual(sc.owned_packages(lib), [0, 5])
        with open(lib, "w") as f:
            json.dump({"rgOwnedApps": [1]}, f)
        self.assertEqual(sc.owned_packages(lib), [])

    # ---- finding the family games ----
    def cache(self, *names):
        for n in names:
            os.makedirs(os.path.join(self.steam, "appcache", "librarycache", str(n)))

    def manifest(self, appid, name):
        apps = os.path.join(self.steam, "steamapps")
        os.makedirs(apps, exist_ok=True)
        with open(os.path.join(apps, "appmanifest_%d.acf" % appid), "w") as f:
            f.write('"AppState"\n{\n\t"appid"\t\t"%d"\n\t"name"\t\t"%s"\n}\n' % (appid, name))

    def library(self, apps, packages=None):
        path = os.path.join(self.tmp, "userdata.json")
        d = {"rgOwnedApps": apps}
        if packages is not None:
            d["rgOwnedPackages"] = packages
        with open(path, "w") as f:
            json.dump(d, f)
        return path

    def test_one_damaged_install_file_does_not_stop_the_library_from_loading(self):
        self.manifest(10, "Good Game")
        apps = os.path.join(self.steam, "steamapps")
        with open(os.path.join(apps, "appmanifest_11.acf"), "w") as f:
            f.write('"AppState"\n{\n\t"appid"\t\t""\n\t"name"\t\t"Broken"\n}\n')
        os.makedirs(os.path.join(apps, "appmanifest_12.acf"))                      # a folder where a file should be
        self.assertEqual(sc.installed_games(self.steam), {10: "Good Game"})

    def test_a_cached_app_you_do_not_own_is_family(self):
        self.packageinfo({0: [1]})
        self.cache(1, 2)
        self.assertEqual(sc.find_family(self.steam, [1], [0]), {2})

    def test_an_owned_app_is_never_family_even_if_cached(self):
        self.packageinfo({0: []})
        self.cache(1)
        self.assertEqual(sc.find_family(self.steam, [1], [0]), set())

    def test_apps_inside_owned_packages_are_yours_not_family(self):
        self.packageinfo({0: [570]})
        self.cache(570, 3981100)
        self.assertEqual(sc.find_family(self.steam, [], [0]), {3981100})

    def test_an_installed_app_you_do_not_own_is_family(self):
        self.packageinfo({0: []})
        self.manifest(674750, "Zombie")
        self.assertEqual(sc.find_family(self.steam, [], [0]), {674750})

    def test_without_readable_package_data_nothing_is_family(self):
        self.cache(2)
        self.assertEqual(sc.find_family(self.steam, [1], [0]), set())              # no packageinfo.vdf
        self.packageinfo({0: [1]})
        self.assertEqual(sc.find_family(self.steam, [1], []), set())               # library file without rgOwnedPackages

    def test_odd_cache_folders_are_ignored(self):
        self.packageinfo({0: []})
        self.cache("abc", "٣", "0", "99999999999")
        target = os.path.join(self.tmp, "elsewhere")
        os.makedirs(target)
        try:
            os.symlink(target, os.path.join(self.steam, "appcache", "librarycache", "5"))
        except (OSError, NotImplementedError):
            pass                                                                    # no symlinks here (Windows without privilege): the rest still counts
        self.assertEqual(sc.find_family(self.steam, [], [0]), set())

    def test_load_library_adds_family_games_and_installed_only_mode_adds_none(self):
        self.packageinfo({0: [1]})
        self.cache(1, 2)
        lib = self.library([1], [0])
        games, family = sc.load_library(self.steam, lib)
        self.assertEqual(family, {2})
        self.assertEqual(games, {1: None, 2: None})
        games, family = sc.load_library(self.steam, None)
        self.assertEqual(family, set())
        self.assertNotIn(2, games)


class FamilyFrame(unittest.TestCase):
    """The frame for family games: the normal frame plus a green corner triangle with the family icon."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.plain = sc.Image.open(sc.FRAME).convert("RGBA")
        self.family = sc.load_frame(0, True)

    def test_family_frame_equals_the_plain_frame_outside_the_corner(self):
        self.assertEqual(self.family.size, sc.SIZE)
        for box in ((0, 0, 380, 900), (380, 220, 600, 900)):                 # all but the top right corner
            self.assertEqual(self.family.crop(box).tobytes(), self.plain.crop(box).tobytes())

    def test_the_corner_is_green_and_follows_the_case_shape(self):
        r, g, b, a = self.family.getpixel((591, 8))
        self.assertEqual(a, 255)
        self.assertTrue(all(abs(x - y) <= 8 for x, y in zip((r, g, b), sc.FAMILY_COLOR)), (r, g, b))
        self.assertEqual(self.family.getpixel((599, 0))[3], 0)                # the case's rounded corner stays transparent
        self.assertEqual(self.family.getpixel((449, 150)), self.plain.getpixel((449, 150)))     # past the diagonal the art window is untouched (it keeps the faint gloss)

    def test_the_icon_is_white_and_readable_on_the_triangle(self):
        self.assertGreaterEqual(contrast((255, 255, 255), sc.FAMILY_COLOR), sc.FAMILY_ICON_CONTRAST)
        self.assertEqual(self.family.getpixel((559, 35))[:3], (255, 255, 255))   # centre of the head of the person nearest the corner's tip


class StoreMocks(Base):
    """A fake store and a fake download (a small red JPEG), for tests that make covers."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        buf = io.BytesIO()
        sc.Image.new("RGB", (100, 150), (200, 60, 60)).save(buf, format="JPEG")
        jpeg = buf.getvalue()
        real = (sc.store_items, sc.http_get)
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 0, "name": "Game %d" % i} for i in ids}
        sc.http_get = lambda url, tries=3: jpeg
        self.addCleanup(lambda: setattr(sc, "store_items", real[0]) or setattr(sc, "http_get", real[1]))

    def corner(self, path):
        return sc.Image.open(path).convert("RGBA").getpixel((591, 8))[:3]            # the corner is at the top right

    def is_green(self, rgb):
        return all(abs(x - y) <= 8 for x, y in zip(rgb, sc.FAMILY_COLOR))

    # ---- command line ----
    def fake_library(self, with_family):
        """Steam with one owned game (1) and, if asked, one game that is only in the cache (2); returns the library file."""
        os.makedirs(os.path.join(self.steam, "appcache", "librarycache", "2" if with_family else "1"), exist_ok=True)
        write_packageinfo(os.path.join(self.steam, "appcache", "packageinfo.vdf"), {0: [1]})
        path = os.path.join(self.tmp, "userdata.json")
        with open(path, "w") as f:
            json.dump({"rgOwnedApps": [1], "rgOwnedPackages": [0]}, f)
        return path

    def run_cli(self, *args):
        import contextlib, io
        out, argv = io.StringIO(), sys.argv
        sys.argv = ["steamcase"] + list(args)
        try:
            with contextlib.redirect_stdout(out):
                sc.main()
        finally:
            sys.argv = argv
        return out.getvalue()


class SoftwareCli(StoreMocks):
    def make_kwargs(self, *extra):
        """The keywords the command line gave make_covers."""
        seen = {}
        real = sc.make_covers
        empty = real({}, os.path.join(self.tmp, "none"))
        sc.make_covers = lambda *a, **kw: seen.update(kw) or empty
        try:
            self.run_cli("make", "--steam-dir", self.steam, "--library", self.fake_library(True), "--out", os.path.join(self.tmp, "out"), *extra)
        finally:
            sc.make_covers = real
        return seen

    def test_flag_gives_make_covers_software(self):
        self.assertIs(self.make_kwargs("--include-software")["software"], True)

    def test_list_shows_software_with_the_flag(self):
        seen = []
        real = sc.list_games
        sc.list_games = lambda games, log=None, errors=None, software=False: seen.append(software) or []
        try:
            for extra in ((), ("--include-software",)):
                self.run_cli("list", "--steam-dir", self.steam, "--library", self.fake_library(True), *extra)
        finally:
            sc.list_games = real
        self.assertEqual(seen, [False, True])

    def test_without_the_flag_software_is_off(self):
        self.assertIs(self.make_kwargs()["software"], False)


class FamilyCovers(StoreMocks):
    """Family games are drawn with the family frame, and Reset recognises both kinds of cover."""

    def test_family_games_get_the_family_frame_and_others_the_plain_one(self):
        res = sc.make_covers({1: None, 2: None}, self.covers, family={2})
        self.assertTrue(self.is_green(self.corner(os.path.join(self.covers, "Game_2_2.png"))))
        self.assertFalse(self.is_green(self.corner(os.path.join(self.covers, "Game_1_1.png"))))
        self.assertEqual(res["family"], 1)

    def test_an_existing_plain_cover_is_kept_for_a_game_that_is_now_family(self):
        sc.make_covers({2: None}, self.covers)
        path = os.path.join(self.covers, "Game_2_2.png")
        before = self.read(path)
        res = sc.make_covers({2: None}, self.covers, family={2})
        self.assertEqual(self.read(path), before)
        self.assertEqual(res["family"], 0)                                   # nothing was drawn with the family frame this time
        res = sc.make_covers({2: None}, self.covers, family={2}, force=True)
        self.assertTrue(self.is_green(self.corner(path)))
        self.assertEqual(res["family"], 1)

    def test_reset_recognises_plain_covers_family_covers_and_not_look_alikes(self):
        sc.make_covers({1: None, 2: None}, self.covers, family={2})
        plain, family = os.path.join(self.covers, "Game_1_1.png"), os.path.join(self.covers, "Game_2_2.png")
        self.assertTrue(sc.is_steamcase_cover(plain))
        self.assertTrue(sc.is_steamcase_cover(family))
        look_alike = os.path.join(self.tmp, "lookalike.png")
        img = sc.Image.new("RGBA", sc.SIZE, (30, 60, 90, 255))
        img.paste(sc.FAMILY_COLOR + (255,), (0, 0, 100, 100))                # a green corner on someone else's art
        img.save(look_alike)
        self.assertFalse(sc.is_steamcase_cover(look_alike))
        tampered = os.path.join(self.tmp, "tampered.png")
        img = sc.Image.open(family).convert("RGBA")
        img.putpixel((400, 10), (1, 2, 3, 255))                              # one banner pixel outside the corner
        img.save(tampered)
        self.assertFalse(sc.is_steamcase_cover(tampered))

    def test_list_marks_family_games(self):
        lib = self.fake_library(True)
        text = self.run_cli("list", "--steam-dir", self.steam, "--library", lib)
        lines = text.splitlines()
        self.assertIn("2 Game 2  (family)", lines)
        self.assertIn("1 Game 1", lines)
        self.assertIn("1 from your Steam Family library", text)

    def test_make_summary_mentions_family_only_when_there_are_some(self):
        lib = self.fake_library(True)
        out = os.path.join(self.tmp, "out")
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out)
        self.assertIn("1 from your Steam Family library", text)
        self.assertTrue(self.is_green(self.corner(os.path.join(out, "Game_2_2.png"))))
        os.remove(os.path.join(self.steam, "appcache", "packageinfo.vdf"))            # ownership unknown: nothing is family
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", os.path.join(self.tmp, "out2"))
        self.assertNotIn("Family library", text)


class CoverColour(unittest.TestCase):
    """Rotating the hue of the case: shape, white parts and transparency stay, the family corner stays green."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.plain = sc.Image.open(sc.FRAME).convert("RGBA")

    def test_hue_zero_is_the_untouched_frame(self):
        for hue in (0, 360, -360):
            self.assertEqual(sc.load_frame(hue).tobytes(), self.plain.tobytes())

    def test_a_rotated_frame_keeps_shape_white_and_alpha(self):
        turned = sc.load_frame(134)
        self.assertEqual(turned.getchannel("A").tobytes(), self.plain.getchannel("A").tobytes())
        white = (255, 255, 255, 255)
        self.assertEqual(list(turned.crop((0, 0, 600, 96)).getdata()).count(white), list(self.plain.crop((0, 0, 600, 96)).getdata()).count(white))
        h0, s0, v0 = self.plain.convert("RGB").convert("HSV").getpixel((7, 450))
        h1, s1, v1 = turned.convert("RGB").convert("HSV").getpixel((7, 450))
        want = round(134 * 256 / 360)
        self.assertLessEqual(min((h1 - h0 - want) % 256, (h0 + want - h1) % 256), 2)
        self.assertLessEqual(abs(s1 - s0), 1)
        self.assertLessEqual(abs(v1 - v0), 1)

    def test_the_family_corner_stays_green_at_every_hue(self):
        for hue in sc.HUE_SWATCHES:
            r, g, b, a = sc.load_frame(hue, True).getpixel((591, 8))
            self.assertTrue(all(abs(x - y) <= 8 for x, y in zip((r, g, b), sc.FAMILY_COLOR)), (hue, (r, g, b)))
            self.assertEqual(sc.load_frame(hue, True).getpixel((7, 450)), sc.load_frame(hue).getpixel((7, 450)))

    def test_case_color_matches_the_rotated_frame(self):
        import re
        self.assertEqual(sc.case_color(0), "#1636c8")
        for hue in sc.HUE_SWATCHES:
            self.assertRegex(sc.case_color(hue), r"^#[0-9a-f]{6}$")


class CoverClamping(unittest.TestCase):
    """Out-of-range tones are clamped, hue 360 is hue 0, and the case_color cache shares what looks the same."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_tones_are_clamped_and_360_is_0(self):
        self.assertEqual(sc.load_frame(0, sat=150, val=-5).tobytes(), sc.load_frame(0, sat=100, val=0).tobytes())
        frame = sc.Image.open(sc.FRAME).convert("RGBA")
        self.assertEqual(sc.recolor_frame(frame, 0, 150, -5).tobytes(), sc.recolor_frame(frame, 0, 100, 0).tobytes())
        self.assertEqual(sc.case_color(360), sc.case_color(0))
        self.assertEqual(sc.case_color(0, 150, -5), sc.case_color(0, 100, 0))

    def test_case_color_ignores_a_hue_that_shows_nothing(self):
        self.assertEqual(sc.case_color(10, 0, 50), sc.case_color(200, 0, 50))
        self.assertEqual(sc.case_color(10, 80, 0), sc.case_color(300, 80, 0))
        self.assertEqual(sc.case_color(0), "#1636c8")
        self.assertNotEqual(sc.case_color(10, 80, 50), sc.case_color(200, 80, 50))


class CoverTone(unittest.TestCase):
    """Colourfulness and brightness of the case: a case can become black, grey or silver; white parts, alpha and the family corner stay."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.plain = sc.Image.open(sc.FRAME).convert("RGBA")

    def assertClose(self, a, b, tol=1):
        self.assertEqual(len(a), len(b))
        self.assertLessEqual(max(abs(x - y) for x, y in zip(a, b)), tol)

    def test_full_tone_is_the_untouched_frame(self):
        self.assertEqual(sc.load_frame(0, sat=100, val=100).tobytes(), self.plain.tobytes())

    def test_tone_keeps_alpha_and_white_parts(self):
        white = (255, 255, 255, 255)
        want = list(self.plain.crop((0, 0, 600, 96)).getdata()).count(white)
        for sat, val in ((0, 0), (0, 14), (0, 78), (40, 50)):
            toned = sc.load_frame(0, sat=sat, val=val)
            self.assertEqual(toned.getchannel("A").tobytes(), self.plain.getchannel("A").tobytes(), (sat, val))
            self.assertEqual(list(toned.crop((0, 0, 600, 96)).getdata()).count(white), want, (sat, val))

    def test_black_is_dark_and_grey_has_no_colour(self):
        r, g, b, _ = sc.load_frame(0, sat=0, val=14).getpixel((7, 450))
        self.assertLessEqual(max(r, g, b), 60)
        self.assertLessEqual(max(r, g, b) - min(r, g, b), 4)
        r, g, b, _ = sc.load_frame(0, sat=0, val=78).getpixel((7, 450))
        self.assertLessEqual(max(r, g, b) - min(r, g, b), 4)
        self.assertGreaterEqual(max(r, g, b), 150)
        r, g, b, _ = sc.load_frame(0, sat=100, val=50).getpixel((7, 450))
        self.assertGreater(b, r + 40)
        self.assertLess(max(r, g, b), max(self.plain.getpixel((7, 450))[:3]))

    def test_less_saturation_or_brightness_never_brightens(self):
        _, s0, v0 = self.plain.convert("RGB").convert("HSV").getpixel((7, 450))
        _, s1, v1 = sc.load_frame(0, sat=60, val=60).convert("RGB").convert("HSV").getpixel((7, 450))
        self.assertLessEqual(s1, s0)
        self.assertLessEqual(v1, v0)

    def test_hue_does_not_matter_at_zero_saturation_or_zero_brightness(self):
        for sat, val in ((0, 60), (80, 0)):
            a = sc.load_frame(134, sat=sat, val=val).tobytes()
            b = sc.load_frame(0, sat=sat, val=val).tobytes()
            self.assertEqual(len(a), len(b))
            self.assertLessEqual(max(abs(x - y) for x, y in zip(a, b)), 1, (sat, val))

    def test_the_family_corner_stays_green_on_black_and_silver(self):
        for sat, val in ((0, 14), (0, 78)):
            r, g, b, _ = sc.load_frame(0, True, sat=sat, val=val).getpixel((591, 8))
            self.assertClose((r, g, b), sc.FAMILY_COLOR, 8)

    def test_case_color_follows_the_tone(self):
        self.assertEqual(sc.case_color(0), "#1636c8")
        grey = sc.case_color(0, 0, 14)
        self.assertRegex(grey, r"^#[0-9a-f]{6}$")
        r, g, b = (int(grey[i:i + 2], 16) for i in (1, 3, 5))
        self.assertLessEqual(max(r, g, b) - min(r, g, b), 4)
        self.assertLess(max(r, g, b), 70)

    def test_neutral_swatches_are_plain_tuples(self):
        self.assertEqual([n for n, _, _ in sc.NEUTRAL_SWATCHES], ["Black", "Graphite", "Silver"])
        for name, sat, val in sc.NEUTRAL_SWATCHES:
            self.assertIsInstance(name, str)
            self.assertEqual(sat, 0)
            self.assertTrue(0 <= val <= 100)


class CoverColourFiles(Base):
    """What is written into a cover file, and recognising covers of every colour."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.src = os.path.join(self.tmp, "portrait.png")
        sc.Image.new("RGB", (600, 900), (200, 60, 60)).save(self.src)

    def make(self, name, hue=0, family=False, sat=100, val=100, treatment=None, src=None, theme=None):
        """A cover built the way make_covers builds it; with a `treatment`, in the colour that treatment uses."""
        out = os.path.join(self.tmp, name)
        hue, sat, val = sc.treatment_colour(treatment, (hue, sat, val))
        sc.build_cover(src or self.src, out, sc.load_frame(hue, family, sat=sat, val=val), hue, sat=sat, val=val, treatment=treatment, theme=theme)
        return out

    def note_cover(self, **notes):
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        for key, value in notes.items():
            info.add_text("steamcase-" + key, value)
        path = os.path.join(self.tmp, "n.png")
        sc.Image.new("RGBA", sc.SIZE).save(path, pnginfo=info)
        return path

    def test_tone_is_recorded_and_old_covers_count_as_full_tone(self):
        self.assertEqual(sc.cover_colour(self.make("a.png", 0, sat=0, val=14)), (0, 0, 14))
        self.assertEqual(sc.cover_colour(self.make("b.png", 134)), (134, 100, 100))
        self.assertEqual(sc.cover_colour(self.note_cover(hue="77")), (77, 100, 100))      # built the old way: only the hue note
        old = os.path.join(self.tmp, "old.png")
        sc.Image.new("RGBA", sc.SIZE).save(old)
        self.assertEqual(sc.cover_colour(old), (0, 100, 100))
        self.assertIsNone(sc.cover_colour(os.path.join(self.tmp, "missing.png")))

    def test_a_garbled_tone_note_is_unknown(self):
        for value in ("abc", "101 5", "-1 5", "5", "5 5 5", " 5 5", "5 5 ", "05 5", "5  5", ""):
            self.assertIsNone(sc.cover_colour(self.note_cover(tone=value)), repr(value))
        self.assertEqual(sc.cover_colour(self.note_cover(tone="100 0")), (0, 100, 0))

    def test_same_colour_ignores_hue_at_zero_saturation_or_brightness(self):
        self.assertTrue(sc.same_colour((10, 0, 50), (200, 0, 50)))
        self.assertFalse(sc.same_colour((10, 0, 50), (10, 0, 51)))
        self.assertFalse(sc.same_colour((10, 100, 50), (200, 100, 50)))
        self.assertTrue(sc.same_colour((10, 80, 0), (300, 80, 0)))
        self.assertFalse(sc.same_colour(None, (0, 100, 100)))
        self.assertFalse(sc.same_colour((0, 100, 100), None))
        self.assertTrue(sc.same_colour((1, 100, 100), (2, 100, 100)))                 # neighbouring degrees on the same step
        self.assertEqual(sc.tone_key(5, 150, -3), (0, 100, 0))

    def test_cover_hue_reads_the_recorded_hue_and_treats_old_covers_as_zero(self):
        self.assertEqual(sc.cover_hue(self.make("a.png", 134)), 134)
        self.assertEqual(sc.cover_hue(self.make("b.png", 360 + 5)), 5)                 # recorded already wrapped
        old = os.path.join(self.tmp, "old.png")
        sc.Image.new("RGBA", sc.SIZE).save(old)                                         # made before this feature: no hue chunk
        self.assertEqual(sc.cover_hue(old), 0)
        self.assertIsNone(sc.cover_hue(os.path.join(self.tmp, "missing.png")))
        jpeg = os.path.join(self.tmp, "j.png")
        sc.Image.new("RGB", (10, 10)).save(jpeg, format="JPEG")
        self.assertIsNone(sc.cover_hue(jpeg))
        link = os.path.join(self.tmp, "link.png")
        try:
            os.symlink(old, link)
        except (OSError, NotImplementedError):
            return                                                                      # no symlinks here (Windows without privilege)
        self.assertIsNone(sc.cover_hue(link))

    def test_an_unreadable_hue_note_is_not_taken_for_blue(self):
        from PIL.PngImagePlugin import PngInfo
        for value, want in (("0", 0), ("5", 5), ("359", 359), ("360", None), ("999", None), ("-5", None), ("12345", None), ("abc", None), ("", None), ("007", None), ("\u0663", None)):
            note = PngInfo()
            note.add_text("steamcase-hue", value)
            path = os.path.join(self.tmp, "n.png")
            sc.Image.new("RGBA", sc.SIZE).save(path, pnginfo=note)
            self.assertEqual(sc.cover_hue(path), want, repr(value))

    def test_covers_of_every_colour_are_recognised_and_look_alikes_are_not(self):
        for hue in sc.HUE_SWATCHES:
            for family in (False, True):
                self.assertTrue(sc.is_steamcase_cover(self.make("c.png", hue, family)), (hue, family))
        flat = os.path.join(self.tmp, "flat.png")
        sc.Image.new("RGBA", sc.SIZE, (30, 60, 90, 255)).save(flat)
        self.assertFalse(sc.is_steamcase_cover(flat))
        for hue in (0, 134):
            real = self.make("r.png", hue)
            grey = os.path.join(self.tmp, "grey.png")
            sc.Image.open(real).convert("L").convert("RGBA").save(grey)
            self.assertFalse(sc.is_steamcase_cover(grey), hue)
            img = sc.Image.open(real).convert("RGBA")
            img.putpixel((400, 10), (1, 2, 3, 255))
            tampered = os.path.join(self.tmp, "t.png")
            img.save(tampered)
            self.assertFalse(sc.is_steamcase_cover(tampered), hue)

    def renote(self, path, **notes):
        """The same pixels saved again with only these notes (none: a cover from before notes existed)."""
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        for key, value in notes.items():
            info.add_text("steamcase-" + key, value)
        out = os.path.join(self.tmp, "renoted.png")
        sc.Image.open(path).convert("RGBA").save(out, pnginfo=info)
        return out

    def test_covers_of_every_tone_are_recognised(self):
        tones = [(hue, 100, 100) for hue in sc.HUE_SWATCHES] + [(0, s, v) for _, s, v in sc.NEUTRAL_SWATCHES] + [(0, 100, 45), (134, 60, 30), (0, 0, 0)]
        for hue, sat, val in tones:
            for family in (False, True):
                self.assertTrue(sc.is_steamcase_cover(self.make("c.png", hue, family, sat, val)), (hue, sat, val, family))

    def test_old_covers_without_a_tone_note_are_still_recognised(self):
        self.assertTrue(sc.is_steamcase_cover(self.renote(self.make("a.png", 0), hue="0")))
        self.assertTrue(sc.is_steamcase_cover(self.renote(self.make("b.png", 134), hue="134")))
        self.assertTrue(sc.is_steamcase_cover(self.renote(self.make("c.png", 0))))

    def test_a_note_that_does_not_match_the_pixels_is_not_recognised(self):
        self.assertFalse(sc.is_steamcase_cover(self.renote(self.make("a.png", 0), hue="0", tone="0 14")))
        black = self.make("b.png", 0, sat=0, val=14)
        self.assertFalse(sc.is_steamcase_cover(self.renote(black, hue="0")))           # the documented limit: the legacy rule sees other S and V
        self.assertFalse(sc.is_steamcase_cover(self.renote(black, hue="0", tone="100 100")))
        self.assertFalse(sc.is_steamcase_cover(self.renote(black, hue="0", tone="0 15x")))   # a garbled tone note is not ours

    def test_look_alikes_are_still_refused_at_every_tone(self):
        from PIL.PngImagePlugin import PngInfo
        for hue, sat, val in ((0, 100, 100), (134, 100, 100), (0, 0, 14), (0, 0, 78)):
            real = self.make("r.png", hue, False, sat, val)
            note = PngInfo()
            note.add_text("steamcase-hue", str(hue))
            note.add_text("steamcase-tone", "%d %d" % (sat, val))
            flat = os.path.join(self.tmp, "flat.png")
            sc.Image.new("RGBA", sc.SIZE, (30, 60, 90, 255)).save(flat, pnginfo=note)
            self.assertFalse(sc.is_steamcase_cover(flat), (hue, sat, val))
            grey = os.path.join(self.tmp, "grey.png")
            sc.Image.open(real).convert("L").convert("RGBA").save(grey)
            self.assertFalse(sc.is_steamcase_cover(grey), (hue, sat, val))
            img = sc.Image.open(real).convert("RGBA")
            img.putpixel((400, 10), (1, 2, 3, 255))
            tampered = os.path.join(self.tmp, "t.png")
            img.save(tampered, pnginfo=note)                                            # notes kept: the toned check must catch it
            self.assertFalse(sc.is_steamcase_cover(tampered), (hue, sat, val))
            jpeg = os.path.join(self.tmp, "j.png")
            sc.Image.open(real).convert("RGB").save(jpeg, format="JPEG", quality=100)
            self.assertFalse(sc.is_steamcase_cover(jpeg), (hue, sat, val))

    def test_a_look_alike_is_refused_at_zero_brightness(self):
        cover = self.make("k.png", 0, False, 0, 0)
        img = sc.Image.open(cover).convert("RGBA")
        r, g, b, a = img.getpixel((400, 10))
        img.putpixel((400, 10), (r + 3, g + 3, b + 3, a))                  # +2 is within the tolerance and may pass; +3 may not
        from PIL.PngImagePlugin import PngInfo
        note = PngInfo()
        note.add_text("steamcase-hue", "0")
        note.add_text("steamcase-tone", "0 0")
        path = os.path.join(self.tmp, "near.png")
        img.save(path, pnginfo=note)
        self.assertFalse(sc.is_steamcase_cover(path))

    def test_a_black_cover_survives_zero_brightness(self):
        cover = self.make("k.png", 0, False, 0, 0)
        self.assertTrue(sc.is_steamcase_cover(cover))
        top = (0, 0, sc.SIZE[0], sc.WINDOW[1])
        self.assertEqual(sc.load_frame(0, sat=0, val=0).getchannel("A").tobytes(), sc.load_frame(0).getchannel("A").tobytes())
        self.assertEqual(sc.Image.open(cover).convert("RGBA").crop(top).getchannel("A").tobytes(), sc.load_frame(0).crop(top).getchannel("A").tobytes())


class RecogniseTreated(Base):
    """Reset finds covers with a 100% treatment by their treatment note, and still refuses look-alikes."""
    COLOURS = ((0, 100, 100), (134, 100, 100), (0, 0, 14), (200, 60, 40))
    make, renote = CoverColourFiles.make, CoverColourFiles.renote

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.src = os.path.join(self.tmp, "portrait.png")
        sc.Image.new("RGB", (600, 900), (200, 60, 60)).save(self.src)

    def notes_of(self, path, **change):
        """The steamcase notes of a cover, as renote takes them, with some changed or (None) dropped."""
        with sc.Image.open(path) as im:
            notes = {k[len("steamcase-"):]: v for k, v in im.info.items() if k.startswith("steamcase-")}
        notes.update(change)
        return {k: v for k, v in notes.items() if v is not None}

    def save_with_notes(self, img, like, name="t.png"):
        """`img` saved with the notes of the cover `like`."""
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        for key, value in self.notes_of(like).items():
            info.add_text("steamcase-" + key, value)
        out = os.path.join(self.tmp, name)
        img.save(out, pnginfo=info)
        return out

    def noise(self, name, seed):
        """A portrait full of fine detail: the worst case for art that bleeds into the frame."""
        path = os.path.join(self.tmp, name)
        bands = [sc.Image.effect_noise((600, 900), 120 + 10 * (seed + i)) for i in range(3)]
        sc.Image.merge("RGB", bands).save(path)
        return path

    def test_every_treatment_in_every_kind_is_recognised(self):
        for t in sc.TREATMENTS:
            for family in (False, True):
                for hue, sat, val in self.COLOURS:
                    self.assertTrue(sc.is_steamcase_cover(self.make("c.png", hue, family, sat, val, treatment=t)), (t, family, hue, sat, val))

    def test_a_treatment_note_on_plain_pixels_is_not_ours(self):
        plain = self.make("p.png")
        self.assertTrue(sc.is_steamcase_cover(plain))
        self.assertFalse(sc.is_steamcase_cover(self.renote(plain, **self.notes_of(plain, done="ribbon"))))

    def test_a_note_over_another_treatments_pixels_is_not_ours(self):
        border = self.make("b.png", treatment="gold-border")
        self.assertFalse(sc.is_steamcase_cover(self.renote(border, **self.notes_of(border, done="ribbon"))))
        ribbon = self.make("r.png", treatment="ribbon")
        self.assertFalse(sc.is_steamcase_cover(self.renote(ribbon, **self.notes_of(ribbon, done="gold-case"))))

    def test_a_gold_case_whose_colour_notes_are_not_gold_is_not_ours(self):
        gold = self.make("g.png", treatment="gold-case")
        self.assertTrue(sc.is_steamcase_cover(gold))
        for change in ({"hue": "10"}, {"tone": "50 100"}, {"tone": "100 60"}):
            self.assertFalse(sc.is_steamcase_cover(self.renote(gold, **self.notes_of(gold, **change))), change)

    def test_a_garbled_treatment_note_is_not_ours(self):
        ribbon = self.make("r.png", treatment="ribbon")
        for value in ("sparkly", "", "ribbon ", "RIBBON"):
            self.assertFalse(sc.is_steamcase_cover(self.renote(ribbon, **self.notes_of(ribbon, done=value))), repr(value))
        self.assertFalse(sc.is_steamcase_cover(self.renote(ribbon, **self.notes_of(ribbon, tone="0 15x"))))   # a garbled colour note too

    def deep_pixel(self, box, alpha=255, reach=4):
        """The first pixel of the Christmas overlay inside `box` that is at least `alpha` opaque and whose whole neighbourhood (`reach` pixels each way)
        is too: a pixel of the decorations well inside them, which the game's art cannot reach (the check pulls its mask back from the art's edge)."""
        with sc.Image.open(sc.CHRISTMAS_OVERLAY) as im:
            ov = im.convert("RGBA")
        x0, y0, x1, y1 = box
        for y in range(y0, y1):
            for x in range(x0, x1):
                if all(ov.getpixel((x + dx, y + dy))[3] >= alpha for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1)):
                    return x, y
        self.fail("no such pixel in %r" % (box,))

    def test_themed_covers_are_recognised_on_every_tone_and_look(self):
        for hue, sat, val in ((0, 100, 100), (0, 0, 14), (200, 60, 40), (0, 0, 78)):
            for family in (False, True):
                for treatment in (None, "rosette", "gold-case-rosette", "gold-border-rosette"):
                    path = self.make("t.png", hue, family, sat, val, treatment=treatment, theme="christmas")
                    self.assertTrue(sc.is_steamcase_cover(path), (hue, sat, val, family, treatment))
                    self.assertEqual(sc.cover_theme(path), "christmas")

    def test_themed_look_alikes_are_refused(self):
        real = self.make("r.png", 134, treatment="rosette", theme="christmas")
        self.assertTrue(sc.is_steamcase_cover(real))
        for what, xy in (("the gifts", self.deep_pixel((455, 790, 590, 890))), ("the tree", self.deep_pixel((30, 760, 140, 860))),
                         ("the hat", self.deep_pixel((260, 20, 360, 60))), ("the trunk", self.deep_pixel((76, 862, 94, 888), 255, 3))):
            img = sc.Image.open(real).convert("RGBA")
            img.putpixel(xy, (1, 2, 3, 255))
            self.assertFalse(sc.is_steamcase_cover(self.save_with_notes(img, real)), what)
        classic = self.make("c.png", 134, treatment="rosette")
        forged = self.renote(classic, **self.notes_of(classic, theme="christmas"))
        self.assertFalse(sc.is_steamcase_cover(forged))                                  # a theme note on a cover without the decorations
        bare = self.renote(real, **self.notes_of(real, theme=None))
        self.assertFalse(sc.is_steamcase_cover(bare))                                    # decorations without their note
        for bad in ("Christmas", "christmas2", "", "spooky"):
            garbled = self.renote(real, **self.notes_of(real, theme=bad))
            self.assertFalse(sc.is_steamcase_cover(garbled), bad)
            self.assertIs(sc.cover_theme(garbled), False if bad else False)

    def test_a_themed_plain_cover_keeps_enough_frame_to_be_told_apart(self):
        for treatment in (None, "rosette", "gold-border-rosette"):
            for tone in ((0, 100, 100), (0, 0, 14), (0, 0, 78)):
                mask = sc._treated_reference((sc.tone_key(*tone), treatment, "christmas"), False)[1]
                self.assertGreaterEqual(mask.histogram()[255], 0.15 * sc.SIZE[0] * sc.SIZE[1], (treatment, tone))

    def test_look_alikes_are_still_refused_at_every_treatment(self):
        for t in sc.TREATMENTS:
            real = self.make("r.png", 134, treatment=t)
            self.assertTrue(sc.is_steamcase_cover(real), t)
            flat = self.save_with_notes(sc.Image.new("RGBA", sc.SIZE, (30, 60, 90, 255)), real, "flat.png")
            self.assertFalse(sc.is_steamcase_cover(flat), t)
            grey = self.save_with_notes(sc.Image.open(real).convert("L").convert("RGBA"), real, "grey.png")
            self.assertFalse(sc.is_steamcase_cover(grey), t)
            probes = ((400, 10), (526, 66)) + (((300, 800),) if sc.split_treatment(t)[1] == "full" else ())    # the banner, the rosette, and the ribbon below the art (rosette-only covers have none)
            for xy in probes:
                img = sc.Image.open(real).convert("RGBA")
                img.putpixel(xy, (1, 2, 3, 255))
                self.assertFalse(sc.is_steamcase_cover(self.save_with_notes(img, real)), (t, xy))
            jpeg = os.path.join(self.tmp, "j.png")
            sc.Image.open(real).convert("RGB").save(jpeg, format="JPEG", quality=100)
            self.assertFalse(sc.is_steamcase_cover(jpeg), t)

    def test_art_changes_do_not_matter(self):
        for t in sc.TREATMENTS:
            for family in (False, True):
                a = self.make("a.png", 0, family, treatment=t, src=self.noise("n1.png", 0))
                b = self.make("b.png", 0, family, treatment=t, src=self.noise("n2.png", 3))
                self.assertTrue(sc.is_steamcase_cover(a), (t, family))
                self.assertTrue(sc.is_steamcase_cover(b), (t, family))
                key = (sc.tone_key(*sc.treatment_colour(t, (0, 100, 100))), t, None)
                self.assertIs(sc._treated_reference(key, family), sc._treated_reference(key, family))

    def test_the_mask_ignores_the_art_and_includes_the_marks(self):
        for t in sc.TREATMENTS:
            _, mask = sc._treated_reference((sc.tone_key(*sc.treatment_colour(t, (0, 100, 100))), t, None), False)
            self.assertEqual(mask.getpixel((300, 400)), 0, t)
        _, mask = sc._treated_reference((sc.tone_key(0), "ribbon", None), False)
        dy, dx, _ = sc.steam_marks()
        self.assertEqual(mask.getpixel((526 + dx, 66 + dy)), 255)
        _, mask = sc._treated_reference((sc.tone_key(0), "gold-border", None), False)
        self.assertEqual(mask.getpixel((5, 450)), 255)

    def test_covers_from_earlier_versions_are_unchanged(self):
        self.assertTrue(sc.is_steamcase_cover(self.make("blue.png")))
        self.assertTrue(sc.is_steamcase_cover(self.renote(self.make("h.png", 134), hue="134")))      # hue note only
        self.assertTrue(sc.is_steamcase_cover(self.make("t.png", 134, sat=60, val=30)))
        self.assertTrue(sc.is_steamcase_cover(self.make("f.png", 84, True)))
        gold = self.make("g.png", treatment="gold-case")

    def test_a_forged_oversized_or_symlinked_treated_file_is_refused(self):
        real = self.make("r.png", treatment="ribbon")
        big = os.path.join(self.tmp, "big.png")
        shutil.copy(real, big)
        with open(big, "ab") as f:
            f.truncate(sc.MAX_DOWNLOAD + 1)                                              # trailing bytes after IEND
        self.assertFalse(sc.is_steamcase_cover(big))
        narrow = self.save_with_notes(sc.Image.open(real).convert("RGBA").crop((0, 0, 599, 900)), real, "narrow.png")
        self.assertFalse(sc.is_steamcase_cover(narrow))
        link = os.path.join(self.tmp, "link.png")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            return                                                                      # no symlinks here (Windows without privilege)
        self.assertFalse(sc.is_steamcase_cover(link))


    def test_every_treatment_is_recognised_and_a_garbled_one_is_not(self):
        for hue, sat, val in ((0, 100, 100), (0, 0, 14)):
            for t in sc.TREATMENTS:
                colour = sc.treatment_colour(t, (hue, sat, val))
                out = os.path.join(self.tmp, "%s_%d.png" % (t, val))
                sc.build_cover(self.src, out, sc.load_frame(colour[0], sat=colour[1], val=colour[2]), colour[0], sat=colour[1], val=colour[2], treatment=t)
                self.assertTrue(sc.is_steamcase_cover(out), (t, val))
                self.assertEqual(sc.cover_treatment(out), t)
        good = os.path.join(self.tmp, "rosette_100.png")
        for bad in ("ribbon-rosette", "rosette-rosette", "gold"):
            garbled = self.renote(good, **self.notes_of(good, done=bad))
            self.assertFalse(sc.is_steamcase_cover(garbled), bad)
            self.assertIs(sc.cover_treatment(garbled), False)


class MakeInColour(StoreMocks):
    """make_covers in a chosen case colour."""

    def cover(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def test_covers_are_made_in_the_chosen_hue(self):
        sc.make_covers({1: None}, self.covers, hue=134)
        self.assertEqual(sc.cover_hue(self.cover(1)), 134)
        self.assertEqual(sc.Image.open(self.cover(1)).convert("RGBA").getpixel((7, 450)), sc.load_frame(134).getpixel((7, 450)))

    def test_covers_are_made_in_the_chosen_tone(self):
        sc.make_covers({1: None}, self.covers, hue=0, sat=0, val=14)
        self.assertEqual(sc.cover_colour(self.cover(1)), (0, 0, 14))
        self.assertEqual(sc.Image.open(self.cover(1)).convert("RGBA").getpixel((7, 450)), sc.load_frame(0, sat=0, val=14).getpixel((7, 450)))

    def test_changing_only_the_tone_rebuilds_and_changing_only_the_hue_at_black_does_not(self):
        sc.make_covers({1: None}, self.covers, hue=0)
        blue = self.read(self.cover(1))
        sc.make_covers({1: None}, self.covers, hue=0, sat=0, val=14)
        black = self.read(self.cover(1))
        self.assertNotEqual(black, blue)
        self.assertEqual(sc.cover_colour(self.cover(1)), (0, 0, 14))
        statuses = []
        sc.make_covers({1: None}, self.covers, hue=200, sat=0, val=14, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual((self.read(self.cover(1)), statuses), (black, ["exists"]))

    def test_covers_in_other_colour_sees_the_tone(self):
        sc.make_covers({1: None}, self.covers)
        self.assertTrue(sc.covers_in_other_colour(self.covers, 0, 0, 14))
        os.remove(self.cover(1))
        sc.make_covers({1: None}, self.covers, sat=0, val=14)
        self.assertFalse(sc.covers_in_other_colour(self.covers, 200, 0, 14))
        self.assertTrue(sc.covers_in_other_colour(self.covers, 0))

    def test_existing_cover_colour_reads_the_folder(self):
        self.assertIsNone(sc.existing_cover_colour(self.covers))
        sc.make_covers({1: None}, self.covers, sat=0, val=14)
        self.assertEqual(sc.existing_cover_colour(self.covers), (0, 0, 14))

    def test_an_existing_cover_in_another_colour_is_rebuilt_and_one_in_the_same_colour_is_kept(self):
        sc.make_covers({1: None}, self.covers)
        before = self.read(self.cover(1))
        res = sc.make_covers({1: None}, self.covers, hue=134)
        self.assertNotEqual(self.read(self.cover(1)), before)
        self.assertEqual((sc.cover_hue(self.cover(1)), res["ok"]), (134, 1))
        again = self.read(self.cover(1))
        statuses = []
        sc.make_covers({1: None}, self.covers, hue=134, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual(self.read(self.cover(1)), again)
        self.assertEqual(statuses, ["exists"])

    def test_a_mixed_folder_is_fixed_by_the_next_run(self):
        sc.make_covers({1: None, 2: None}, self.covers)
        sc.make_covers({1: None, 2: None}, self.covers, only=[1], hue=134)            # a run that stopped halfway through a colour change
        self.assertEqual((sc.cover_hue(self.cover(1)), sc.cover_hue(self.cover(2))), (134, 0))
        sc.make_covers({1: None, 2: None}, self.covers, hue=134)
        self.assertEqual((sc.cover_hue(self.cover(1)), sc.cover_hue(self.cover(2))), (134, 134))

    def test_family_covers_keep_a_green_corner_in_a_custom_colour(self):
        sc.make_covers({1: None, 2: None}, self.covers, family={2}, hue=134)
        self.assertTrue(self.is_green(self.corner(self.cover(2))))
        self.assertFalse(self.is_green(self.corner(self.cover(1))))

    def test_hues_that_look_the_same_are_not_rebuilt(self):
        # 1 and 2 degrees turn Pillow's 0..255 hue scale by the same step: the covers would come out identical
        self.assertEqual(sc.hue_shift(1), sc.hue_shift(2))
        self.assertNotEqual(sc.hue_shift(1), sc.hue_shift(3))
        self.assertEqual(sc.hue_shift(0), sc.hue_shift(360))
        sc.make_covers({1: None}, self.covers, hue=1)
        before = self.read(self.cover(1))
        statuses = []
        sc.make_covers({1: None}, self.covers, hue=2, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual((self.read(self.cover(1)), statuses), (before, ["exists"]))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 2))
        self.assertTrue(sc.covers_in_other_colour(self.covers, 3))                      # a real step: rebuilt
        sc.make_covers({1: None}, self.covers, hue=3)
        self.assertEqual(sc.cover_hue(self.cover(1)), 3)

    def test_existing_cover_colour_reads_the_colour_of_the_folder(self):
        self.assertIsNone(sc.existing_cover_colour(os.path.join(self.tmp, "nowhere")))
        self.assertIsNone(sc.existing_cover_colour(self.covers))                            # empty folder
        sc.Image.new("RGBA", sc.SIZE).save(os.path.join(self.covers, "notes.png"))      # not named like one of our covers: ignored
        self.assertIsNone(sc.existing_cover_colour(self.covers))
        sc.make_covers({1: None}, self.covers, hue=134)
        self.assertEqual(sc.existing_cover_colour(self.covers), (134, 100, 100))
        old = os.path.join(self.covers, "Old_2.png")                                     # made before colours existed: blue
        sc.Image.new("RGBA", sc.SIZE).save(old)
        self.assertEqual(sc.existing_cover_colour(self.covers), (134, 100, 100))                        # the first cover by name decides: Game_1_1.png

    def test_covers_in_other_colour(self):
        self.assertFalse(sc.covers_in_other_colour(os.path.join(self.tmp, "nowhere"), 134))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 134))                    # empty folder
        sc.make_covers({1: None}, self.covers)
        self.assertFalse(sc.covers_in_other_colour(self.covers, 0))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 360))
        self.assertTrue(sc.covers_in_other_colour(self.covers, 134))
        sc.Image.new("RGBA", sc.SIZE).save(os.path.join(self.covers, "notes.png"))      # not named like one of our covers: ignored
        os.remove(self.cover(1))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 134))


class PreviewCover(Base):
    """The preview in the window is built exactly like a real cover, from the default art that ships with the app."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_the_default_art_ships_and_is_a_portrait(self):
        with sc.Image.open(sc.DEFAULT_ART) as im:
            self.assertEqual(im.size, (600, 900))

    def test_preview_cover_is_exactly_what_a_real_cover_would_be(self):
        for hue, family in ((134, False), (0, True), (276, True)):
            out = os.path.join(self.tmp, "real.png")
            sc.build_cover(sc.DEFAULT_ART, out, sc.load_frame(hue, family), hue)
            real, preview = sc.Image.open(out).convert("RGBA"), sc.preview_cover(hue, family)
            self.assertEqual(real.size, preview.size)
            self.assertIsNone(sc.ImageChops.difference(real, preview).getbbox(), (hue, family))


class ReplaceReason(StoreMocks):
    """The sentence of the Replace question (qtui.reasons.replace_reason) for every kind of change, over covers made by the app's own functions."""

    def setUp(self):
        super().setUp()
        from qtui import reasons
        self.reasons = reasons
        self.games = {1: None, 2: None}

    def made(self, hue=0, completed=None, treatment=None, theme=None, custom_art=None):
        sc.make_covers(self.games, self.covers, hue=hue, completed=completed, treatment=treatment, theme=theme, custom_art=custom_art)

    def mine(self, colour=(10, 160, 30)):
        path = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), colour).save(path, format="JPEG")
        return path

    def reason(self, tone, completed, treatment, theme=None):
        got = self.reasons.replace_reason(self.covers, tone, completed, treatment, theme)
        self.assertIsNotNone(got)
        title, sentence = got
        self.assertTrue(title.strip() and sentence.strip() and "%" not in title.replace("100%", "") and "%" not in sentence.replace("100%", ""), got)
        return got

    def test_turning_custom_art_on_asks_before_replacing_existing_covers(self):
        self.made()
        got = self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None, {1: self.mine()})
        self.assertIsNotNone(got)
        self.assertIn("your own art", got[1])

    def test_turning_custom_art_off_asks_too(self):
        self.made(custom_art={1: self.mine()})
        got = self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None, {})
        self.assertIsNotNone(got)
        self.assertIn("Steam's own art", got[1])

    def test_no_custom_art_question_when_nothing_changes(self):
        mine = self.mine()
        self.made(custom_art={1: mine})
        self.assertIsNone(self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None, {1: mine}))
        self.assertIsNone(self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None))     # not asked about: covers keep their art

    def test_covers_of_games_outside_the_run_are_not_mentioned(self):
        self.made(custom_art={1: self.mine()})
        self.assertIsNotNone(self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None, {}, {1, 2}))
        self.assertIsNone(self.reasons.replace_reason(self.covers, (0, 100, 100), None, None, None, {}, {2, 3}))

    def test_a_colour_change_with_custom_art_says_both(self):
        self.made()
        got = self.reasons.replace_reason(self.covers, (90, 100, 100), None, None, None, {1: self.mine()})
        self.assertIn("colour", got[1])
        self.assertIn("your own art", got[1])

    def test_a_colour_change_does_not_claim_an_art_change(self):
        self.made()                                                         # never made from custom art
        got = self.reasons.replace_reason(self.covers, (90, 100, 100), None, None, None, {})
        self.assertIn("colour", got[1])
        self.assertNotIn("art", got[1])
        mine = self.mine()
        shutil.rmtree(self.covers)
        os.makedirs(self.covers)
        self.made(custom_art={1: mine})
        got = self.reasons.replace_reason(self.covers, (90, 100, 100), None, None, None, {1: mine})
        self.assertNotIn("art", got[1])                                     # same art: only the colour changes

    def test_nothing_to_rebuild_gives_no_prompt(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIsNone(self.reasons.replace_reason(self.covers, (0, 100, 100), {1}, "ribbon"))

    def test_no_page_only_a_colour_change(self):
        self.made()
        self.assertIn("colour", self.reason((90, 100, 100), None, None)[1])

    def test_no_special_case(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIn("No special case", self.reason((0, 100, 100), set(), None)[1])

    def test_a_page_with_no_game_at_100_says_the_highlight_is_lost(self):
        for treatment in ("ribbon", "gold-case"):
            shutil.rmtree(self.covers, ignore_errors=True)
            self.made(completed={1}, treatment=treatment)
            self.assertIn("lose it", self.reason((0, 100, 100), set(), "ribbon")[1])

    def test_a_first_highlight_over_plain_covers(self):
        for treatment in sc.TREATMENTS:
            shutil.rmtree(self.covers, ignore_errors=True)
            self.made()
            self.assertIn("highlighted", self.reason((0, 100, 100), {1}, treatment)[1])

    def test_a_change_of_marks_alone_says_which_marks_come(self):
        self.made(completed={1}, treatment="rosette")
        text = self.reason((0, 100, 100), {1}, "ribbon")[1]
        self.assertIn("rosette and ribbon", text)
        self.made(completed={1}, treatment="ribbon")
        self.assertIn("rosette only", self.reason((0, 100, 100), {1}, "rosette")[1])

    def test_a_theme_change_alone_says_the_new_covers_get_the_theme(self):
        self.made()
        title, text = self.reason((0, 100, 100), None, None, "christmas")
        self.assertIn("theme", title.lower())
        self.assertIn("new ones in the Christmas theme", text)
        self.made(theme="christmas")
        self.assertIn("new ones in the Classic case", self.reason((0, 100, 100), None, None, None)[1])

    def test_a_theme_without_a_page_says_the_100_covers_lose_their_ribbon(self):
        self.made(completed={1}, treatment="ribbon")
        text = self.reason((0, 100, 100), None, None, "christmas")[1]
        self.assertIn("lose their ribbon", text)
        self.assertIn("Rosette and ribbon", text)                                  # and how to get it back
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made(completed={1}, treatment="rosette")
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "christmas")[1])        # nothing to lose
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made()
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "christmas")[1])

    def test_covers_with_marks_are_found(self):
        self.assertFalse(sc.covers_with_marks(os.path.join(self.tmp, "nowhere"), "full"))
        self.made()
        self.assertFalse(sc.covers_with_marks(self.covers, "full"))
        self.made(completed={1}, treatment="gold-border-rosette")
        self.assertFalse(sc.covers_with_marks(self.covers, "full"))
        self.made(completed={1}, treatment="gold-border")
        self.assertTrue(sc.covers_with_marks(self.covers, "full"))

    def test_a_theme_with_a_colour_or_a_look_change_stays_readable(self):
        self.made()
        text = self.reason((134, 100, 100), None, None, "christmas")[1]
        self.assertIn("another colour or theme", text)
        self.assertNotIn(", and with", text)
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made(completed={1}, treatment="ribbon")
        text = self.reason((0, 100, 100), {1}, "rosette", "christmas")[1]
        self.assertIn("100%", text)
        self.assertIn("All your covers are also made in the Christmas theme", text)

    def test_another_style_for_the_100_games(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIn("another look", self.reason((0, 100, 100), {1}, "gold-border")[1])

    def test_the_set_of_100_games_changes(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIn("match your games page", self.reason((0, 100, 100), {2}, "ribbon")[1])

    def test_a_colour_and_a_style_change_name_both(self):
        self.made(completed={1}, treatment="ribbon")
        for completed, treatment, part in (({1}, "gold-border", "another look"), (set(), "ribbon", "lose it"), (set(), None, "normal covers"), ({2}, "ribbon", "match your games page")):
            sentence = self.reason((90, 100, 100), completed, treatment)[1]
            self.assertIn("colour", sentence)
            self.assertIn(part, sentence)


class CompletionCli(StoreMocks):
    """--games-page and --completed-style on the command line."""

    def page(self, progress, name="games.html"):
        """A saved games page like tests/fixtures/games_page.html, with a row per app id in `progress` {appid: (unlocked, total) or None}."""
        rows = []
        for appid, counts in progress.items():
            store = '<a href="https://store.steampowered.com/app/%d"' % appid
            row = '<div class="row">\n  %s class="img"></a>\n  %s class="name">Game</a>\n' % (store, store)
            if counts:
                row += '  <a class="ach" href="https://steamcommunity.com/id/playerone/achievements/%d">ACHIEVEMENTS</a><span class="cnt">%d/%d</span>\n' % ((appid,) + counts)
            rows.append(row + "</div>\n")
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE html>\n<html><body><div class="list">\n' + "".join(rows) + "</div></body></html>\n")
        return path

    def make(self, out, *extra):
        lib = self.fake_library(True)
        return self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, *extra)

    def treatment(self, out, appid):
        return sc.cover_treatment(os.path.join(out, "Game_%d_%d.png" % (appid, appid)))

    def test_make_with_a_page_highlights_the_completed_games(self):
        out = os.path.join(self.tmp, "out")
        text = self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}))
        self.assertEqual(self.treatment(out, 1), "ribbon")
        self.assertIsNone(self.treatment(out, 2))
        self.assertIn("1 of them are 100% complete", text)

    def test_each_style_is_accepted(self):
        page = self.page({1: (10, 10), 2: (1, 9)})
        for style in sc.CASES:                                       # the marks have their own option, see test_marks_*
            out = os.path.join(self.tmp, "out_" + style)
            text = self.make(out, "--games-page", page, "--completed-style", style)
            self.assertEqual(self.treatment(out, 1), style)
            self.assertIsNone(self.treatment(out, 2))
            self.assertIn("1 of them are 100% complete", text)

    def test_completed_marks_none_gives_gold_without_marks(self):
        page = self.page({1: (10, 10), 2: (1, 9)})
        for style in ("gold-case", "gold-border"):
            with self.subTest(style):
                out = os.path.join(self.tmp, "out_plain_" + style)
                self.make(out, "--games-page", page, "--completed-style", style, "--completed-marks", "none")
                self.assertEqual(self.treatment(out, 1), style + "-plain")
                self.assertIsNone(self.treatment(out, 2))

    def test_the_normal_case_without_marks_is_no_special_case(self):
        out = os.path.join(self.tmp, "out_normal_none")
        self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}), "--completed-style", "ribbon", "--completed-marks", "none")
        self.assertEqual((self.treatment(out, 1), self.treatment(out, 2)), (None, None))

    def test_no_marks_with_a_theme_is_refused_in_one_sentence(self):
        out = os.path.join(self.tmp, "out_theme_none")
        with self.assertRaises(SystemExit) as ctx:
            self.make(out, "--theme", "christmas", "--games-page", self.page({1: (10, 10)}), "--completed-style", "gold-case", "--completed-marks", "none")
        self.assertIn("rosette", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(out, "Game_1_1.png")))

    def theme(self, out, appid):
        return sc.cover_theme(os.path.join(out, "Game_%d_%d.png" % (appid, appid)))

    def test_theme_makes_christmas_covers_and_keeps_the_colour_options(self):
        out = os.path.join(self.tmp, "out")
        text = self.make(out, "--theme", "christmas", "--hue", "134")
        self.assertEqual(self.theme(out, 1), "christmas")
        self.assertEqual(sc.cover_hue(os.path.join(out, "Game_1_1.png")), 134)
        self.assertIn("Christmas theme", text)

    def test_the_theme_of_the_covers_already_there_is_kept_unless_asked_otherwise(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--theme", "christmas")
        path = os.path.join(out, "Game_1_1.png")
        before = self.read(path)
        text = self.make(out)                                                           # no --theme: Christmas covers stay Christmas
        self.assertEqual(self.read(path), before)
        self.assertIn("Christmas theme", text)
        self.make(out, "--theme", "classic")
        self.assertIsNone(self.theme(out, 1))
        self.assertNotIn("Christmas theme", self.make(out, "--theme", "classic"))

    def test_a_theme_gives_100_percent_games_the_rosette_only(self):
        page = self.page({1: (10, 10), 2: (1, 9)})
        out = os.path.join(self.tmp, "out")
        self.make(out, "--theme", "christmas", "--games-page", page)
        self.assertEqual(self.treatment(out, 1), "rosette")
        self.assertIsNone(self.treatment(out, 2))
        out2 = os.path.join(self.tmp, "out2")
        self.make(out2, "--theme", "christmas", "--games-page", page, "--completed-style", "gold-border", "--completed-marks", "rosette")
        self.assertEqual(self.treatment(out2, 1), "gold-border-rosette")
        self.make(out2, "--games-page", page)                                           # the folder is themed already: the default marks are rosette
        self.assertEqual(self.treatment(out2, 1), "rosette")

    def test_a_theme_and_full_marks_are_refused(self):
        page = self.page({1: (10, 10)})
        out = os.path.join(self.tmp, "out")
        with self.assertRaises(SystemExit) as caught:
            self.make(out, "--theme", "christmas", "--games-page", page, "--completed-marks", "full")
        self.assertIn("Christmas", str(caught.exception))
        self.assertIn("rosette", str(caught.exception))
        self.assertIn("--theme classic", str(caught.exception))                         # the way out, also when the theme comes from the folder
        self.assertFalse(os.path.exists(out))
        import contextlib, io
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["steamcase", "make", "-h"]), contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            sc.main()
        self.assertIn("with a theme the default is rosette", " ".join(out.getvalue().split()))      # the help says so too

    def test_a_bad_theme_is_refused(self):
        import contextlib, io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.make(os.path.join(self.tmp, "out"), "--theme", "bogus")
        self.assertIn("invalid choice", err.getvalue())

    def test_a_style_without_a_page_is_refused(self):
        import contextlib, io
        out = os.path.join(self.tmp, "out")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            self.make(out, "--completed-style", "gold-case")
        self.assertNotEqual(caught.exception.code, 0)
        self.assertIn("error: --completed-style needs --games-page", err.getvalue())
        self.assertFalse(os.path.exists(out))

    def test_marks_rosette_with_a_page_means_the_plain_case_with_the_rosette(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}), "--completed-marks", "rosette")
        self.assertEqual(self.treatment(out, 1), "rosette")
        self.assertIsNone(self.treatment(out, 2))

    def test_marks_combine_with_the_style(self):
        page = self.page({1: (10, 10)})
        for style, marks, want in (("gold-border", "rosette", "gold-border-rosette"), ("gold-case", "rosette", "gold-case-rosette"),
                                   ("gold-case", "full", "gold-case"), ("ribbon", "full", "ribbon")):
            out = os.path.join(self.tmp, "out_%s_%s" % (style, marks))
            self.make(out, "--games-page", page, "--completed-style", style, "--completed-marks", marks)
            self.assertEqual(self.treatment(out, 1), want)

    def test_marks_with_none_remove_the_highlights_and_need_no_page(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--games-page", self.page({1: (10, 10)}), "--completed-marks", "rosette")
        self.assertEqual(self.treatment(out, 1), "rosette")
        self.make(out, "--completed-style", "none", "--completed-marks", "rosette")
        self.assertIsNone(self.treatment(out, 1))

    def test_marks_without_a_page_or_with_a_bad_value_are_refused(self):
        import contextlib, io
        for args, message in ((("--completed-marks", "rosette"), "error: --completed-marks needs --games-page"),
                              (("--completed-style", "gold-case", "--completed-marks", "rosette"), "error: --completed-style needs --games-page"),
                              (("--completed-marks", "bogus"), "invalid choice")):
            out = os.path.join(self.tmp, "out")
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                self.make(out, *args)
            self.assertNotEqual(caught.exception.code, 0)
            self.assertIn(message, err.getvalue())
            self.assertFalse(os.path.exists(out))

    def test_none_removes_treatments(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}))
        self.assertEqual(self.treatment(out, 1), "ribbon")
        text = self.make(out, "--completed-style", "none")
        self.assertIsNone(self.treatment(out, 1))
        self.assertNotIn("100% complete", text)
        self.make(out, "--games-page", self.page({1: (10, 10)}), "--completed-style", "ribbon")
        self.assertEqual(self.treatment(out, 1), "ribbon")
        self.make(out, "--games-page", self.page({1: (10, 10)}), "--completed-style", "none")
        self.assertIsNone(self.treatment(out, 1))

    def test_without_the_new_options_treated_covers_stay_treated(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}))
        path = os.path.join(out, "Game_1_1.png")
        before = self.read(path)
        self.make(out)
        self.assertEqual(self.read(path), before)
        self.assertEqual(self.treatment(out, 1), "ribbon")

    def test_none_does_not_read_the_page_so_a_bad_one_cannot_stop_it(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--games-page", self.page({1: (10, 10), 2: (1, 9)}))
        self.assertEqual(self.treatment(out, 1), "ribbon")
        bad = os.path.join(self.tmp, "plain.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html><body>nothing here</body></html>")
        for page in (bad, os.path.join(self.tmp, "missing.html")):
            self.make(out, "--games-page", page, "--completed-style", "none")
            self.assertIsNone(self.treatment(out, 1))
            self.make(out, "--games-page", self.page({1: (10, 10)}))

    def test_none_with_a_good_page_works(self):
        out = os.path.join(self.tmp, "out")
        page = self.page({1: (10, 10), 2: (1, 9)})
        self.make(out, "--games-page", page)
        self.make(out, "--games-page", page, "--completed-style", "none")
        self.assertIsNone(self.treatment(out, 1))

    def test_the_page_is_checked_before_the_library_is_loaded(self):
        import contextlib, io
        with mock.patch.object(sc, "_collect", side_effect=AssertionError("loaded the library")), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            sc.cmd_make(sc.argparse.Namespace(games_page=os.path.join(self.tmp, "missing.html"), completed_style=None, completed_marks=None, theme="classic", case_file=None))
        self.assertEqual(caught.exception.code, 2)

    def test_a_tilde_in_the_page_path_is_expanded(self):
        page = self.page({1: (10, 10)}, "tilde.html")
        with mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp}):
            got = sc._completion_args(sc.argparse.Namespace(games_page=os.path.join("~", "tilde.html"), completed_style=None, completed_marks=None))
        self.assertEqual(got, ({1}, "ribbon"))

    def test_a_missing_page_names_only_its_file_name(self):
        import contextlib, io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            self.make(os.path.join(self.tmp, "out"), "--games-page", os.path.join(self.tmp, "gone.html"))
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(err.getvalue().strip(), "That file could not be opened. (gone.html)")

    def test_run_with_a_bad_page_exits_2_and_does_not_apply(self):
        import contextlib, io
        bad = os.path.join(self.tmp, "plain.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html><body>nothing here</body></html>")
        with mock.patch.object(sc, "cmd_apply") as apply_, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.run_cli("run", "--steam-dir", self.steam, "--library", self.fake_library(True), "--out", os.path.join(self.tmp, "out"), "--games-page", bad)
        self.assertEqual(caught.exception.code, 2)
        apply_.assert_not_called()

    def test_run_with_none_and_a_good_page_applies(self):
        with mock.patch.object(sc, "cmd_apply") as apply_:
            out = os.path.join(self.tmp, "out")
            self.run_cli("run", "--steam-dir", self.steam, "--library", self.fake_library(True), "--out", out,
                         "--games-page", self.page({1: (10, 10)}), "--completed-style", "none")
        apply_.assert_called_once()
        self.assertIsNone(self.treatment(out, 1))

    def test_a_bad_page_prints_the_reason_and_exits_2(self):
        import contextlib, io
        bad = os.path.join(self.tmp, "plain.html")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("<html><body>nothing here</body></html>")
        out = os.path.join(self.tmp, "out")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            self.make(out, "--games-page", bad)
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("Webpage, Complete", err.getvalue())
        self.assertFalse(os.path.exists(out))

    def test_run_shares_the_options(self):
        import contextlib, io
        out, argv = io.StringIO(), sys.argv
        sys.argv = ["steamcase", "run", "-h"]
        try:
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                sc.main()
        finally:
            sys.argv = argv
        self.assertIn("--games-page", out.getvalue())
        self.assertIn("--completed-style", out.getvalue())


class ColourCli(StoreMocks):
    """--hue, --saturation and --brightness on the command line."""

    def test_make_accepts_a_hue(self):
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", "134")
        self.assertIn("in a custom colour", text)
        self.assertEqual(sc.cover_hue(os.path.join(out, "Game_1_1.png")), 134)
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", os.path.join(self.tmp, "out0"))
        self.assertNotIn("custom colour", text)

    def test_make_without_hue_keeps_the_colour_of_the_covers_already_there(self):
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", "134")
        path = os.path.join(out, "Game_1_1.png")
        before = self.read(path)
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out)          # no --hue: do not turn red covers blue
        self.assertEqual(self.read(path), before)
        self.assertIn("in a custom colour", text)
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", "0")    # asking for blue explicitly does
        self.assertEqual(sc.cover_hue(path), 0)

    def test_make_accepts_saturation_and_brightness(self):
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--saturation", "0", "--brightness", "14")
        self.assertIn("in a custom colour", text)
        self.assertEqual(sc.cover_colour(os.path.join(out, "Game_1_1.png")), (0, 0, 14))

    def test_make_without_tone_options_keeps_the_tone_of_the_covers_already_there(self):
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        path = os.path.join(out, "Game_1_1.png")
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--saturation", "0", "--brightness", "14")
        before = self.read(path)
        text = self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out)          # no options: black stays black
        self.assertEqual(sc.cover_colour(path), (0, 0, 14))
        self.assertEqual(self.read(path), before)
        self.assertIn("in a custom colour", text)
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--saturation", "100", "--brightness", "100", "--hue", "0")
        self.assertEqual(sc.cover_colour(path), (0, 100, 100))                                            # asking for the original does rebuild

    def test_apply_refuses_a_folder_with_covers_in_two_themes(self):
        """A cancelled theme change leaves classic and Christmas covers side by side; apply must not copy that mix into Steam."""
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out)
        self.assertFalse(sc.mixed_cover_themes(out))
        sc.make_covers({2: None}, out, theme="christmas")                           # a cover from the interrupted run, in the other theme
        self.assertTrue(sc.mixed_cover_themes(out))
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("apply", "--steam-dir", self.steam, "--covers", out, "--yes")
        self.assertIn("more than one theme", str(caught.exception))
        self.assertEqual(os.listdir(self.grid), [])                                  # nothing was copied
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--theme", "christmas")
        self.assertFalse(sc.mixed_cover_themes(out))
        self.run_cli("apply", "--steam-dir", self.steam, "--covers", out, "--yes")   # one theme again: applies
        self.assertEqual(len(os.listdir(self.grid)), 2)

    def test_apply_refuses_a_folder_with_covers_in_two_colours(self):
        """An interrupted colour change leaves old and new covers side by side; apply must not copy that mix into Steam."""
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", "134")
        sc.make_covers({2: None}, out, hue=0)                                      # a cover from the interrupted run, in the other colour
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("apply", "--steam-dir", self.steam, "--covers", out, "--yes")
        self.assertIn("more than one colour", str(caught.exception))
        self.assertEqual(os.listdir(self.grid), [])                                  # nothing was copied
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", "134")
        sc.make_covers({2: None}, out, hue=134)
        self.run_cli("apply", "--steam-dir", self.steam, "--covers", out, "--yes")   # one colour again: applies
        self.assertEqual(len(os.listdir(self.grid)), 2)

    def test_apply_ignores_gold_case_covers_when_checking_the_colour(self):
        out = os.path.join(self.tmp, "out")
        sc.make_covers({1: None}, out, hue=134)
        sc.make_covers({2: None}, out, hue=134, completed={2}, treatment="gold-case")
        self.assertFalse(sc.mixed_cover_colours(out))

    def test_a_bad_percentage_is_refused_with_a_clear_message(self):
        import contextlib, io
        lib = self.fake_library(False)
        for option in ("--saturation", "--brightness"):
            for bad in ("101", "-1", "abc", "1.5", ""):
                out = os.path.join(self.tmp, "out_" + option.strip("-") + (bad or "empty"))
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                    self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, option, bad)
                self.assertIn("whole number from 0 to 100", err.getvalue(), option + bad)
                self.assertIn(repr(bad), err.getvalue(), option + bad)
                self.assertFalse(os.path.exists(out), option + bad)

    def test_percentages_are_plain_ascii_digits(self):
        import contextlib, io
        lib = self.fake_library(False)
        for bad in ("\u0663", " 5", "+5"):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", os.path.join(self.tmp, "out_bad"), "--saturation", bad)
            self.assertIn(repr(bad), err.getvalue(), bad)
        for good, want in (("05", 5), ("0", 0), ("100", 100)):
            self.assertEqual(sc._percent_arg(good), want)

    def test_a_bad_hue_is_refused_with_a_clear_message(self):
        import contextlib, io
        lib = self.fake_library(False)
        for bad in ("400", "-1", "abc", "1.5", ""):
            out = os.path.join(self.tmp, "out_" + (bad or "empty"))
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--hue", bad)
            self.assertIn("0 to 359", err.getvalue(), bad)
            self.assertFalse(os.path.exists(out), bad)                                   # nothing was built


class GamesPage(unittest.TestCase):
    """Reading the saved Steam games page: only ints may come out of it, whatever the file holds."""
    FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "games_page.html")
    WANT = {1001: (10, 10), 1002: (4, 50), 1003: (0, 12), 1004: (7, 7)}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with open(self.FIXTURE, encoding="utf-8") as f:
            self.html = f.read()

    def page(self, text, name="page.html"):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(text if isinstance(text, bytes) else text.encode("utf-8"))
        return p

    def test_reads_progress_for_every_row_that_shows_it(self):
        self.assertEqual(cp.read_games_page(self.FIXTURE), self.WANT)

    def test_completed_apps_needs_unlocked_equal_total_above_zero(self):
        self.assertEqual(cp.completed_apps({1: (10, 10), 2: (4, 50), 3: (0, 0), 4: (5, 3), 5: (7, 7)}), {1, 5})

    def test_the_label_language_does_not_matter(self):
        self.assertEqual(cp.completed_apps(cp.read_games_page(self.FIXTURE)), {1001, 1004})
        swapped = re.sub(r"(/achievements/\d+\">)[^<]*(</a><span)", "\\1日本語\\2", self.html)
        self.assertIn("日本語", swapped)
        self.assertNotIn("CONQUISTAS", swapped)
        self.assertEqual(cp.read_games_page(self.page(swapped)), self.WANT)

    def test_a_profiles_address_works_like_an_id_address(self):
        other = self.html.replace("/id/playerone/", "/profiles/76561190000000000/")
        self.assertNotIn("/id/", other)
        self.assertEqual(cp.read_games_page(self.page(other)), self.WANT)

    def test_a_page_saved_as_html_only_is_refused_with_advice(self):
        p = self.page('<html><script>var x = {"rgRecentlyPlayedGames":[1,2]};</script></html>')
        with self.assertRaises(cp.PageError) as cm:
            cp.read_games_page(p)
        self.assertIn("Webpage, Complete", str(cm.exception))

    def test_rows_without_any_progress_are_refused(self):
        bare = re.sub(r"<span class=\"cnt\">[^<]*</span>", "", self.html)
        with self.assertRaises(cp.PageError) as cm:
            cp.read_games_page(self.page(bare))
        self.assertIn("no game shows achievement progress", str(cm.exception).lower())

    def test_a_file_that_is_not_a_steam_page_is_refused(self):
        for name, data in (("a.txt", b"just some words\n"), ("b.html", b""), ("c.html", b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8)):
            with self.assertRaises(cp.PageError) as cm:
                cp.read_games_page(self.page(data, name))
            self.assertIn("does not look like your Steam games page", str(cm.exception))

    def test_too_big_files_and_links_are_refused(self):
        big = os.path.join(self.tmp, "big.html")
        with open(big, "wb") as f:
            f.truncate(cp.MAX_GAMES_PAGE + 1)                                   # sparse: costs no disk
        with self.assertRaises(cp.PageError):
            cp.read_games_page(big)
        link = os.path.join(self.tmp, "link.html")
        try:
            os.symlink(self.FIXTURE, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available here")
        with self.assertRaises(cp.PageError):
            cp.read_games_page(link)

    def test_a_link_swapped_in_after_the_first_check_is_still_refused(self):
        if not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("no O_NOFOLLOW here")
        link = os.path.join(self.tmp, "link.html")
        os.symlink(self.FIXTURE, link)
        with mock.patch.object(cp.os, "lstat", os.stat):                       # as if the path was a plain file when it was checked
            with self.assertRaises(cp.PageError) as cm:
                cp.read_games_page(link)
        self.assertIn("not a plain file", str(cm.exception))

    def test_a_missing_file_names_only_its_base_name(self):
        with self.assertRaises(cp.PageError) as cm:
            cp.read_games_page(os.path.join(self.tmp, "gone.html"))
        self.assertEqual(str(cm.exception), "That file could not be opened. (gone.html)")

    def test_junk_is_parsed_in_linear_time(self):
        junk = b'<a href="https://store.steampowered.com/app/' * (5 * 1024 * 1024 // 44) + os.urandom(5 * 1024 * 1024)
        # the progress pattern too: link starts that never end, and achievements links with nothing after them
        junk += (b'<a href="https://steamcommunity.com/id/' + b"a" * 200) * 2000 + b'/achievements/' * 20000
        p = self.page(self.html.encode("utf-8") + junk)
        t0 = time.monotonic()
        got = cp.read_games_page(p)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual(got, self.WANT)
        for k, v in got.items():
            self.assertIs(type(k), int)
            self.assertTrue(all(type(n) is int for n in v))

    def test_nothing_from_a_script_is_returned(self):
        text = self.html.replace("</body>", '<script>{"strWebAPIToken":"SECRET-TOKEN"}</script></body>')
        self.assertNotIn("SECRET-TOKEN", repr(cp.read_games_page(self.page(text))))
        only = self.page('<script>{"strWebAPIToken":"SECRET-TOKEN","rgRecentlyPlayedGames":[]}</script>', "s.html")
        with self.assertRaises(cp.PageError) as cm:
            cp.read_games_page(only)
        self.assertNotIn("SECRET-TOKEN", str(cm.exception))

    def test_odd_numbers_are_ignored_or_kept_but_never_complete(self):
        text = self.html.replace("10/10", "5/3").replace("4/50", "0/0").replace("0/12", "x/y")
        got = cp.read_games_page(self.page(text))
        self.assertEqual(got, {1001: (5, 3), 1002: (0, 0), 1004: (7, 7)})
        self.assertEqual(cp.completed_apps(got), {1004})


class FamilyHelp(unittest.TestCase):
    """The hover text next to "Only my installed games": it must say what the switch leaves out and how to get those games."""

    def test_the_help_explains_family_games_and_the_game_list(self):
        text = sc.FAMILY_HELP.lower()
        for must in ("family", "game list", "installed", "green corner"):
            self.assertIn(must, text)
        self.assertLess(len(sc.FAMILY_HELP), 700)                                 # a tooltip, not a manual


def near(px, ref, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(px, ref))


def pixels(im):
    return getattr(im, "get_flattened_data", im.getdata)()          # getdata is deprecated from Pillow 12; the floor (10.3) only has getdata


def BORDER_AT(v, axis):
    """Where a point of the full cover lands once the "gold-border" treatment has shrunk it into the border."""
    return sc.BORDER + v * (sc.SIZE[axis] - 2 * sc.BORDER) / sc.SIZE[axis]


class DrawingVersion(unittest.TestCase):
    """Covers made by an earlier drawing (v1.5.0: the rosette at the top right, the family corner at the top left) must not be kept as if they were current:
    the notes in their PNG (colour, treatment, theme...) can match while the picture does not."""
    IDS = (11, 12, 13)

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        import io
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        def art(appid):
            b = io.BytesIO(); sc.Image.new("RGB", (600, 900), (appid * 7, 90, 150)).save(b, "PNG"); return b.getvalue()
        real = (sc.store_items, sc.http_get)
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: {"type": 0, "name": "Game %d" % i, "assets": {"asset_url_format": "s/${FILENAME}", "library_capsule_2x": "h/%d.jpg" % i}} for i in ids}
        sc.http_get = lambda url, tries=3: art(int(re.search(r"h/([0-9]+)\.jpg", url).group(1)))
        self.addCleanup(lambda: setattr(sc, "store_items", real[0]) or setattr(sc, "http_get", real[1]))
        self.out = os.path.join(self.tmp, "covers")

    def make(self, **kw):
        return sc.make_covers({i: "Game %d" % i for i in self.IDS}, self.out, log=lambda *a: None, **kw)

    def path(self, appid):
        return dict(sc.scan_covers(self.out))[appid]

    def read(self, appid):
        with open(self.path(appid), "rb") as f:
            return f.read()

    def make_old(self, appid):
        """Turn a cover into what v1.5.0 left: the same picture and notes, but no note about the drawing."""
        path = self.path(appid)
        with sc.Image.open(path) as im:
            im.load()
            info = {k: v for k, v in im.info.items() if k != sc.LAYOUT_CHUNK}
            note = sc.PngInfo()
            for k, v in info.items():
                if isinstance(v, str):
                    note.add_text(k, v)
            im.save(path, format="PNG", pnginfo=note)

    def test_every_new_cover_says_which_drawing_it_has(self):
        self.make(completed={11}, treatment="ribbon")
        for appid in self.IDS:
            self.assertEqual(sc.read_notes(self.path(appid)).layout, sc.LAYOUT)

    def test_a_100_percent_cover_of_the_old_drawing_is_drawn_again_with_the_same_choices(self):
        self.make(completed={11}, treatment="ribbon")
        self.make_old(11)
        self.assertIsNone(sc.read_notes(self.path(11)).layout)
        self.make(completed={11}, treatment="ribbon")                        # the very same choices
        self.assertEqual(sc.read_notes(self.path(11)).layout, sc.LAYOUT)

    def test_a_plain_cover_of_the_old_drawing_is_drawn_again(self):           # its art was cropped; now the whole art is stretched to the case
        self.make(completed={11}, treatment="ribbon")
        self.make_old(12)
        self.assertTrue(sc.covers_in_other_look(self.out, 0, 100, 100, completed={11}, treatment="ribbon"))
        self.make(completed={11}, treatment="ribbon")
        self.assertEqual(sc.read_notes(self.path(12)).layout, sc.LAYOUT)

    def test_a_family_cover_of_the_old_drawing_is_drawn_again(self):         # the green corner moved from the top left to the top right
        self.make(family={13})
        self.make_old(13)
        self.make(family={13})
        self.assertEqual(sc.read_notes(self.path(13)).layout, sc.LAYOUT)

    def test_without_options_an_old_gold_cover_is_drawn_again_in_the_same_look(self):
        self.make(completed={11}, treatment="gold-case")
        self.make_old(11)
        self.make()                                                         # no options: every cover keeps its look
        notes = sc.read_notes(self.path(11))
        self.assertEqual((notes.treatment, notes.layout), ("gold-case", sc.LAYOUT))

    def test_the_question_before_making_counts_the_old_100_percent_covers(self):
        self.make(completed={11}, treatment="ribbon")
        self.assertFalse(sc.covers_in_other_look(self.out, 0, 100, 100, completed={11}, treatment="ribbon"))
        self.make_old(11)
        self.assertTrue(sc.covers_in_other_look(self.out, 0, 100, 100, completed={11}, treatment="ribbon"))

    def test_the_window_asks_with_words_that_say_why(self):
        from qtui import reasons
        self.make(completed={11}, treatment="ribbon")
        self.assertIsNone(reasons.replace_reason(self.out, (0, 100, 100), {11}, "ribbon"))      # nothing to ask when the covers are current
        self.make_old(11)
        title, text = reasons.replace_reason(self.out, (0, 100, 100), {11}, "ribbon")
        self.assertIn("again", title)
        self.assertIn("earlier version", text)
        self.assertIn("whole art", text)
        self.make(completed={11}, treatment="ribbon")
        self.assertIsNone(reasons.replace_reason(self.out, (0, 100, 100), {11}, "ribbon"))

    def test_the_question_for_plain_covers_of_the_old_drawing_says_why(self):
        from qtui import reasons
        self.make()
        self.assertIsNone(reasons.replace_reason(self.out, (0, 100, 100), None, None))
        self.make_old(12)
        title, text = reasons.replace_reason(self.out, (0, 100, 100), None, None)
        self.assertEqual(title, "Draw your covers again?")
        self.assertIn("whole art", text)

    def test_a_console_cover_of_the_old_drawing_is_drawn_again_when_the_game_is_picked_again(self):
        self.make(platforms={11: "ps5"})
        self.assertEqual(sc.covers_in_other_case(self.out, {11: "ps5"}), 0)
        self.make_old(11)
        self.assertEqual(sc.covers_in_other_case(self.out, {11: "ps5"}), 1)
        self.make(platforms={11: "ps5"})
        self.assertEqual(sc.read_notes(self.path(11)).layout, sc.LAYOUT)

    def test_a_garbled_drawing_note_counts_as_an_old_one(self):
        self.make(completed={11}, treatment="ribbon")
        self.assertIs(sc.notes_of({sc.LAYOUT_CHUNK: "x"}).layout, False)
        self.assertFalse(sc.matches(sc.notes_of({sc.DONE_CHUNK: "ribbon", sc.HUE_CHUNK: "0", sc.LAYOUT_CHUNK: "x"}), sc.CoverSpec(treatment="ribbon", layout=sc.LAYOUT)))


class Treatments(unittest.TestCase):
    """The marks of a 100% game: the rosette over the badges, the cut ribbon at the bottom, and the three case treatments."""
    DISC, BAND = (255, 207, 10), (26, 159, 255)

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_the_overlay_asset_exists_and_is_a_full_size_rgba(self):
        with sc.Image.open(sc.COMPLETION_OVERLAY) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.size, (600, 900))

    def test_the_overlay_has_the_approved_marks(self):
        with sc.Image.open(sc.COMPLETION_OVERLAY) as im:
            ov = im.convert("RGBA")
        self.assertTrue(near(ov.getpixel((526, 66))[:3], self.DISC), ov.getpixel((526, 66)))     # the rosette's gold disc
        text = ov.crop((150, 800, 450, 840))
        white = sum(1 for p in pixels(text) if p[3] == 255 and min(p[:3]) >= 240)
        self.assertGreaterEqual(white, 200)                                                    # "100% Complete"
        self.assertTrue(near(ov.getpixel((80, 800))[:3], self.BAND), ov.getpixel((80, 800)))    # the band
        self.assertEqual(ov.getpixel((300, 400))[3], 0)                                         # the middle of the art stays clear

    def test_no_treatment_returns_the_cover_untouched(self):
        c = sc.preview_cover()
        self.assertIs(sc.finish_treatment(c, None), c)

    def test_a_ribbon_cover_changes_only_the_rosette_and_the_ribbon(self):
        done, plain = sc.preview_cover(treatment="ribbon"), sc.preview_cover()
        dy, dx, _ = sc.steam_marks()
        self.assertEqual(done.getpixel((300, 400)), plain.getpixel((300, 400)))
        self.assertNotEqual(done.getpixel((526 + dx, 66 + dy)), plain.getpixel((526 + dx, 66 + dy)))              # the rosette, at the left under the banner
        self.assertNotEqual(done.getpixel((300, 820)), plain.getpixel((300, 820)))
        self.assertEqual(done.getpixel((0, 0))[3], 0)                                           # nothing leaves the rounded case

    def test_gold_case_changes_the_case_colour_to_gold(self):
        self.assertEqual(sc.preview_cover(20, treatment="gold-case").getpixel((7, 450)),
                         sc.preview_cover(sc.GOLD_HUE).getpixel((7, 450)))                      # the user's hue 20 is ignored

    def test_other_treatments_keep_the_users_colour(self):
        self.assertEqual(sc.preview_cover(134, treatment="ribbon").getpixel((7, 450)), sc.preview_cover(134).getpixel((7, 450)))
        self.assertEqual(sc.preview_cover(134, sat=0, val=14, treatment="ribbon").getpixel((7, 450)),
                         sc.preview_cover(134, sat=0, val=14).getpixel((7, 450)))

    def test_gold_border_shrinks_the_case_and_stays_600_by_900(self):
        im = sc.preview_cover(treatment="gold-border")
        self.assertEqual(im.size, (600, 900))
        r, g, b, a = im.getpixel((5, 450))
        self.assertTrue(r > 180 and b < 90, (r, g, b))                                         # the gold border
        r, g, b, a = im.getpixel((20, 450))
        self.assertGreater(b, r)                                                               # the user's blue case, a little inside
        self.assertNotEqual(im.getpixel((300, 450)), im.getpixel((5, 450)))                     # the art still shows
        self.assertEqual(im.getpixel((300, 450))[3], 255)
        for corner in ((0, 0), (599, 0), (0, 899), (599, 899)):
            self.assertEqual(im.getpixel(corner)[3], 0, corner)

    def test_gold_border_keeps_the_rosette_and_ribbon_on_the_art(self):
        im = sc.preview_cover(treatment="gold-border")
        dy, dx, _ = sc.steam_marks()
        x, y = 526 + dx, 66 + dy                                                               # the disc's centre before the case shrinks
        self.assertTrue(any(near(p[:3], self.DISC) for p in pixels(im.crop((x - 46, y - 36, x + 34, y + 34)))))
        box = im.crop((x - 66, y - 46, x + 54, y + 74))                                        # the whole disc, to find its centre
        disc = [(i % 120 + x - 66, i // 120 + y - 46) for i, p in enumerate(pixels(box)) if near(p[:3], self.DISC)]
        cx, cy = sum(px for px, _ in disc) / len(disc), sum(py for _, py in disc) / len(disc)
        want = (BORDER_AT(x, 0), BORDER_AT(y, 1))                                              # the disc shrank with the case: its centre moved
        self.assertTrue(abs(cx - want[0]) <= 2 and abs(cy - want[1]) <= 2, ((cx, cy), want))
        self.assertGreater(abs(cx - x) + abs(cy - y), 10)
        strip = pixels(im.crop((0, 0, 14, 900)))
        self.assertFalse(any(p[3] and near(p[:3], self.BAND) for p in strip))

    def test_family_corner_and_the_rosette_do_not_overlap(self):
        im = sc.preview_cover(0, True, treatment="ribbon")
        dy, dx, _ = sc.steam_marks()
        self.assertTrue(near(im.getpixel((591, 8))[:3], sc.FAMILY_COLOR, 8), im.getpixel((591, 8)))
        self.assertTrue(near(im.getpixel((526 + dx, 66 + dy))[:3], self.DISC), im.getpixel((526 + dx, 66 + dy)))

    def test_treatment_colour(self):
        self.assertEqual(sc.treatment_colour("gold-case", (20, 40, 50)), (176, 100, 100))
        self.assertEqual(sc.treatment_colour("ribbon", (20, 40, 50)), (20, 40, 50))
        c = (20, 40, 50)
        self.assertEqual(sc.treatment_colour(None, c), c)


    def test_compose_and_split_round_trip(self):
        for style in sc.CASES:
            for marks in sc.MARKS:
                if (style, marks) != ("ribbon", "none"):                             # the normal case with no marks is no treatment: see PlainGold
                    self.assertEqual(sc.split_treatment(sc.compose_treatment(style, marks)), (style, marks))
        self.assertEqual(sc.compose_treatment("ribbon", "full"), "ribbon")
        self.assertEqual(sc.compose_treatment("ribbon", "rosette"), "rosette")
        self.assertEqual(sc.compose_treatment("gold-case", "rosette"), "gold-case-rosette")
        self.assertEqual(sc.compose_treatment("gold-border", "full"), "gold-border")
        self.assertEqual(len(sc.TREATMENTS), 8)
        for bad in ("ribbon-rosette", "rosette-rosette", "", None, False, "RIBBON"):
            with self.assertRaises(ValueError):
                sc.split_treatment(bad)
        with self.assertRaises(ValueError):
            sc.compose_treatment("ribbon", "banner")
        with self.assertRaises(ValueError):
            sc.compose_treatment("sparkly", "full")

    def test_rosette_only_has_no_bottom_ribbon(self):
        only, full, plain = sc.preview_cover(treatment="rosette"), sc.preview_cover(treatment="ribbon"), sc.preview_cover()
        self.assertEqual(list(pixels(only.crop((0, 450, 600, 900)))), list(pixels(plain.crop((0, 450, 600, 900)))))
        left = (0, 96, 200, 300)                                                                # where the rosette is
        self.assertNotEqual(list(pixels(only.crop(left))), list(pixels(plain.crop(left))))
        self.assertEqual(list(pixels(only.crop(left))), list(pixels(full.crop(left))))             # the same rosette
        self.assertNotEqual(list(pixels(full.crop((0, 800, 600, 870)))), list(pixels(plain.crop((0, 800, 600, 870)))))

    def test_every_treatment_is_gold_or_not(self):
        for t in sc.TREATMENTS:
            want = (sc.GOLD_HUE, 100, 100) if t.startswith("gold-case") else (50, 60, 70)
            self.assertEqual(sc.treatment_colour(t, (50, 60, 70)), want, t)
            self.assertEqual(sc.is_gold_case(t), t.startswith("gold-case"), t)
        for none in (None, False):
            self.assertFalse(sc.is_gold_case(none))

    def test_gold_border_rosette_has_the_border_and_no_ribbon(self):
        only, full = sc.preview_cover(treatment="gold-border-rosette"), sc.preview_cover(treatment="gold-border")
        r, g, b, a = only.getpixel((5, 450))
        self.assertTrue(r > 180 and b < 90, (r, g, b))
        self.assertEqual(only.getpixel((5, 450)), full.getpixel((5, 450)))
        self.assertNotEqual(list(pixels(only.crop((0, 800, 600, 870)))), list(pixels(full.crop((0, 800, 600, 870)))))
        self.assertFalse(any(p[3] and near(p[:3], self.BAND) for p in pixels(only.crop((20, 780, 580, 870)))))

    def test_gold_case_rosette_is_a_gold_case(self):
        self.assertEqual(sc.preview_cover(20, treatment="gold-case-rosette").getpixel((7, 450)),
                         sc.preview_cover(sc.GOLD_HUE).getpixel((7, 450)))

    def test_covers_and_mixed_colours_ignore_gold_case_rosette_covers(self):
        d = os.path.join(tempfile.mkdtemp(), "covers")
        self.addCleanup(shutil.rmtree, os.path.dirname(d), True)
        os.makedirs(d)
        src = os.path.join(os.path.dirname(d), "p.png")
        sc.Image.new("RGB", (600, 900), (200, 60, 60)).save(src)
        sc.build_cover(src, os.path.join(d, "A_1_1.png"), sc.load_frame(134), 134)
        gold = (sc.GOLD_HUE, 100, 100)
        sc.build_cover(src, os.path.join(d, "B_2_2.png"), sc.load_frame(*gold[:1], sat=gold[1], val=gold[2]), gold[0], sat=gold[1], val=gold[2],
                       treatment="gold-case-rosette")
        self.assertEqual(sc.existing_cover_colour(d), (134, 100, 100))
        self.assertFalse(sc.mixed_cover_colours(d))


class MakeTreated(StoreMocks):
    """make_covers with the games that are 100% and a treatment: which covers get it, which are kept and which are rebuilt."""

    def setUp(self):
        super().setUp()
        self.games = {1: None, 2: None}

    def cover(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def test_a_renamed_game_keeps_one_cover_file(self):
        sc.make_covers(self.games, self.covers)
        self.assertTrue(os.path.exists(self.cover(1)))
        self.games[1] = "Renamed"
        sc.make_covers(self.games, self.covers)
        self.assertEqual(sorted(f for f in os.listdir(self.covers) if f.endswith("_1.png")), ["Renamed_1.png"])

    def test_an_unknown_treatment_is_refused_before_anything_is_made(self):
        for bad in ("sparkly", "", "RIBBON", False):
            with self.assertRaises(ValueError):
                sc.make_covers(self.games, self.covers, completed={1}, treatment=bad)
        self.assertEqual(os.listdir(self.covers), [])

    def test_a_missing_frame_fails_before_any_lookup_or_download(self):
        with mock.patch.object(sc, "FRAME", os.path.join(self.tmp, "no-frame.png")), \
                mock.patch.object(sc, "store_items") as store, mock.patch.object(sc, "http_get") as get:
            with self.assertRaises(OSError):
                sc.make_covers(self.games, self.covers, completed={1}, treatment="gold-case")
        store.assert_not_called()
        get.assert_not_called()

    def test_a_missing_overlay_fails_before_any_cover_is_made(self):
        with mock.patch.object(sc, "COMPLETION_OVERLAY", os.path.join(self.tmp, "no-overlay.png")):
            sc._completion_overlay.cache_clear()
            self.addCleanup(sc._completion_overlay.cache_clear)
            with self.assertRaises(OSError):
                sc.make_covers(self.games, self.covers, completed={1}, treatment="ribbon")
        self.assertEqual(os.listdir(self.covers), [])

    def test_changing_only_the_marks_rebuilds_the_cover(self):
        sc.make_covers(self.games, self.covers, completed={1}, treatment="gold-case")
        self.assertEqual(sc.cover_treatment(self.cover(1)), "gold-case")
        statuses = []
        sc.make_covers(self.games, self.covers, completed={1}, treatment="gold-case-rosette", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "ok"), statuses)
        self.assertEqual(sc.cover_treatment(self.cover(1)), "gold-case-rosette")
        statuses = []
        sc.make_covers(self.games, self.covers, completed={1}, treatment="gold-case-rosette", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "exists"), statuses)
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, completed={1}, treatment="gold-case"))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, completed={1}, treatment="gold-case-rosette"))

    def test_changing_only_the_theme_rebuilds_the_cover(self):
        sc.make_covers(self.games, self.covers)
        self.assertIsNone(sc.cover_theme(self.cover(1)))
        statuses = []
        sc.make_covers(self.games, self.covers, theme="christmas", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "ok"), statuses)
        self.assertEqual(sc.cover_theme(self.cover(1)), "christmas")
        statuses = []
        sc.make_covers(self.games, self.covers, theme="christmas", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "exists"), statuses)
        sc.make_covers(self.games, self.covers, theme="christmas", force=True, progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "ok"), statuses[2:])
        sc.make_covers(self.games, self.covers)                                           # no theme: back to classic
        self.assertIsNone(sc.cover_theme(self.cover(1)))
        self.assertNotIn(sc.THEME_CHUNK, sc.Image.open(self.cover(1)).info)

    def test_the_rebuild_checks_see_the_theme_and_keep_ignores_it(self):
        sc.make_covers(self.games, self.covers, theme="christmas")
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme=sc.KEEP))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="christmas"))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, theme=None))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 0, 100, 100))              # a themed folder in its own colour is not "another colour"
        self.assertTrue(sc.covers_in_other_theme(self.covers, None))
        self.assertFalse(sc.covers_in_other_theme(self.covers, "christmas"))

    def test_a_theme_and_full_marks_are_refused_before_anything_is_made(self):
        for bad in ("ribbon", "gold-case", "gold-border"):
            with self.assertRaises(ValueError):
                sc.make_covers(self.games, self.covers, completed={1}, treatment=bad, theme="christmas")
        with self.assertRaises(ValueError):
            sc.make_covers(self.games, self.covers, theme="spooky")
        self.assertEqual(os.listdir(self.covers), [])
        for fine in (None, "rosette", "gold-border-rosette"):
            sc.make_covers(self.games, self.covers, completed={1}, treatment=fine, theme="christmas")
            self.assertEqual(sc.cover_theme(self.cover(1)), "christmas")

    def test_a_theme_over_existing_full_marks_covers_turns_them_into_rosette_only(self):
        for old, want in (("ribbon", "rosette"), ("gold-case", "gold-case-rosette"), ("gold-border", "gold-border-rosette")):
            shutil.rmtree(self.covers, ignore_errors=True)
            sc.make_covers(self.games, self.covers, completed={1}, treatment=old)
            self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="christmas"))
            sc.make_covers(self.games, self.covers, theme="christmas")                    # no page: each cover keeps its look, with the marks the theme allows
            self.assertEqual(sc.cover_treatment(self.cover(1)), want)
            self.assertEqual(sc.cover_theme(self.cover(1)), "christmas")
            self.assertIsNone(sc.cover_treatment(self.cover(2)))
            self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="christmas"))

    def test_a_missing_christmas_overlay_fails_before_any_cover_is_made(self):
        with mock.patch.object(sc, "CHRISTMAS_OVERLAY", os.path.join(self.tmp, "no-overlay.png")):
            sc._christmas_overlay.cache_clear()
            self.addCleanup(sc._christmas_overlay.cache_clear)
            with self.assertRaises(OSError):
                sc.make_covers(self.games, self.covers, theme="christmas")
        self.assertEqual(os.listdir(self.covers), [])

    def test_a_completed_game_gets_the_treatment_and_the_others_do_not(self):
        res = sc.make_covers(self.games, self.covers, completed={1}, treatment="ribbon")
        self.assertEqual(sc.cover_treatment(self.cover(1)), "ribbon")
        self.assertIsNone(sc.cover_treatment(self.cover(2)))
        self.assertEqual(res["completed"], 1)

    def test_each_treatment_is_recorded(self):
        for t in sc.TREATMENTS:
            with self.subTest(t):
                shutil.rmtree(self.covers)
                sc.make_covers({1: None}, self.covers, hue=90, completed={1}, treatment=t)
                self.assertEqual(sc.cover_treatment(self.cover(1)), t)
                self.assertEqual(sc.cover_colour(self.cover(1)), (176, 100, 100) if sc.is_gold_case(t) else (90, 100, 100))
                with sc.Image.open(self.cover(1)) as im:
                    self.assertEqual(im.size, sc.SIZE)

    def test_the_gold_case_ignores_the_users_colour_and_is_not_rebuilt_when_it_changes(self):
        sc.make_covers(self.games, self.covers, hue=0, completed={1}, treatment="gold-case")
        gold, plain = self.read(self.cover(1)), self.read(self.cover(2))
        self.assertTrue(sc.covers_in_other_look(self.covers, 134, 100, 100, completed={1}, treatment="gold-case"))
        aside = os.path.join(self.tmp, "aside.png")
        shutil.move(self.cover(2), aside)
        self.assertFalse(sc.covers_in_other_look(self.covers, 134, 100, 100, completed={1}, treatment="gold-case"))    # only game 2 counted
        self.assertFalse(sc.covers_in_other_colour(self.covers, 134))                     # no page: the gold case keeps its gold
        shutil.move(aside, self.cover(2))
        res = sc.make_covers(self.games, self.covers, hue=134, completed={1}, treatment="gold-case")
        self.assertEqual(self.read(self.cover(1)), gold)
        self.assertNotEqual(self.read(self.cover(2)), plain)
        self.assertEqual(sc.cover_colour(self.cover(2)), (134, 100, 100))
        self.assertEqual(res["completed"], 1)                                               # the kept one counts too

    def test_a_changed_style_rebuilds_only_the_completed_games(self):
        sc.make_covers(self.games, self.covers, completed={1}, treatment="ribbon")
        ribbon, plain = self.read(self.cover(1)), self.read(self.cover(2))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, completed={1}, treatment="gold-border"))
        sc.make_covers(self.games, self.covers, completed={1}, treatment="gold-border")
        self.assertNotEqual(self.read(self.cover(1)), ribbon)
        self.assertEqual(sc.cover_treatment(self.cover(1)), "gold-border")
        self.assertEqual(self.read(self.cover(2)), plain)

    def test_no_special_case_rebuilds_treated_covers_as_plain(self):
        sc.make_covers(self.games, self.covers, hue=134, completed={1}, treatment="gold-case")
        self.assertTrue(sc.covers_in_other_look(self.covers, 134, 100, 100, completed=set(), treatment=None))
        res = sc.make_covers(self.games, self.covers, hue=134, completed=set(), treatment=None)
        self.assertIsNone(sc.cover_treatment(self.cover(1)))
        self.assertEqual(sc.cover_colour(self.cover(1)), (134, 100, 100))
        self.assertEqual(res["completed"], 0)

    def test_without_a_page_treated_covers_keep_their_treatment(self):
        sc.make_covers(self.games, self.covers, completed={1}, treatment="ribbon")
        ribbon, plain = self.read(self.cover(1)), self.read(self.cover(2))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100))
        res = sc.make_covers(self.games, self.covers, completed=None, treatment=None)
        self.assertEqual((self.read(self.cover(1)), self.read(self.cover(2))), (ribbon, plain))
        self.assertEqual(res["completed"], 1)
        sc.make_covers(self.games, self.covers, hue=134)
        self.assertNotEqual(self.read(self.cover(1)), ribbon)
        self.assertEqual(sc.cover_colour(self.cover(1)), (134, 100, 100))
        self.assertEqual((sc.cover_treatment(self.cover(1)), sc.cover_treatment(self.cover(2))), ("ribbon", None))

    def test_a_game_that_stops_being_complete_loses_the_treatment(self):
        sc.make_covers(self.games, self.covers, completed={1}, treatment="ribbon")
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, completed=set(), treatment="ribbon"))
        sc.make_covers(self.games, self.covers, completed=set(), treatment="ribbon")
        self.assertIsNone(sc.cover_treatment(self.cover(1)))

    def test_family_games_can_be_completed(self):
        for t in ("ribbon", "gold-case"):
            with self.subTest(t):
                shutil.rmtree(self.covers)
                sc.make_covers({1: None}, self.covers, family={1}, completed={1}, treatment=t)
                self.assertTrue(self.is_green(self.corner(self.cover(1))))
                self.assertEqual(sc.cover_treatment(self.cover(1)), t)
        shutil.rmtree(self.covers)
        sc.make_covers({1: None}, self.covers, family={1}, completed={1}, treatment="gold-border")
        box = sc.Image.open(self.cover(1)).convert("RGBA").crop((540, 14, 586, 60))
        self.assertTrue(any(p[3] == 255 and self.is_green(p[:3]) for p in pixels(box)))
        self.assertEqual(sc.cover_treatment(self.cover(1)), "gold-border")

    def test_a_garbled_treatment_note_means_rebuild(self):
        from PIL.PngImagePlugin import PngInfo
        sc.make_covers({1: None}, self.covers)
        note = PngInfo()
        note.add_text(sc.HUE_CHUNK, "0")
        note.add_text(sc.TONE_CHUNK, "100 100")
        note.add_text(sc.DONE_CHUNK, "sparkly")
        sc.Image.open(self.cover(1)).save(self.cover(1), pnginfo=note)
        garbled = self.read(self.cover(1))
        self.assertIs(sc.cover_treatment(self.cover(1)), False)
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100))
        statuses = []
        sc.make_covers({1: None}, self.covers, completed=None, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual(statuses, ["ok"])
        self.assertNotEqual(self.read(self.cover(1)), garbled)
        self.assertIsNone(sc.cover_treatment(self.cover(1)))

    def test_cover_treatment_of_files_that_are_not_covers(self):
        self.assertIs(sc.cover_treatment(os.path.join(self.tmp, "nowhere.png")), False)
        junk = os.path.join(self.tmp, "junk.png")
        with open(junk, "wb") as f:
            f.write(b"not a png")
        self.assertIs(sc.cover_treatment(junk), False)
        sc.make_covers({1: None}, self.covers)
        self.assertIsNone(sc.cover_treatment(self.cover(1)))

    def test_existing_cover_colour_ignores_gold_case_covers(self):
        sc.make_covers({1: None}, self.covers, hue=134, completed={1}, treatment="gold-case")
        self.assertIsNone(sc.existing_cover_colour(self.covers))
        sc.make_covers({2: None}, self.covers, hue=134, completed={1}, treatment="gold-case")
        self.assertEqual(sc.existing_cover_colour(self.covers), (134, 100, 100))

    def test_a_completed_game_that_is_not_in_the_library_is_ignored(self):
        res = sc.make_covers({1: None}, self.covers, completed={1, 99}, treatment="ribbon")
        self.assertEqual(sorted(os.listdir(self.covers)), ["Game_1_1.png"])
        self.assertEqual((res["files"], res["completed"]), ([self.cover(1)], 1))

    def test_make_covers_keeps_its_old_behaviour_without_the_new_arguments(self):
        res = sc.make_covers(self.games, self.covers, hue=134)
        self.assertEqual(res["completed"], 0)
        for appid in self.games:
            self.assertIsNone(sc.cover_treatment(self.cover(appid)))
            with sc.Image.open(self.cover(appid)) as im:
                self.assertNotIn(sc.DONE_CHUNK, im.info)



class ReadmeLanguages(unittest.TestCase):
    """README.md (English, the default) and README.pt-BR.md say the same things; each has the two flags that lead to the other."""
    def read(self, name):
        with open(os.path.join(sc.HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_each_readme_has_both_flags_and_they_lead_to_the_two_files(self):
        for name in ("README.md", "README.pt-BR.md"):
            text = self.read(name)
            self.assertRegex(text, r'<a href="README\.md"><img src="assets/flag_us\.png"')
            self.assertRegex(text, r'<a href="README\.pt-BR\.md"><img src="assets/flag_br\.png"')
        for flag in ("flag_us.png", "flag_br.png"):
            self.assertTrue(os.path.isfile(os.path.join(sc.HERE, "assets", flag)))

    def test_every_image_and_file_link_in_both_exists(self):
        for name in ("README.md", "README.pt-BR.md"):
            text = self.read(name)
            for target in re.findall(r'(?:src|srcset|href)="((?:assets|docs)/[^"#]+)', text) + re.findall(r"\]\(((?:assets|docs)/[^)#]+)\)", text):
                self.assertTrue(os.path.exists(os.path.join(sc.HERE, target)), "%s links to a missing file: %s" % (name, target))

    def test_the_portuguese_one_has_the_same_sections_anchors_and_code(self):
        en, pt = self.read("README.md"), self.read("README.pt-BR.md")
        for pattern in (r'<a id="([a-z-]+)"', r'<details( id="[a-z-]+")?>', r"^## ", r"^### ", r"^```", r"^> \[!"):
            self.assertEqual(len(re.findall(pattern, en, re.M)), len(re.findall(pattern, pt, re.M)), pattern)
        self.assertEqual(re.findall(r'<a id="([a-z-]+)"', en), re.findall(r'<a id="([a-z-]+)"', pt))
        self.assertEqual(re.findall(r"^python -m engine [^#\n]*", en, re.M), re.findall(r"^python -m engine [^#\n]*", pt, re.M))   # the commands are the same

    def test_the_portuguese_one_shows_the_program_in_portuguese(self):
        en, pt = self.read("README.md"), self.read("README.pt-BR.md")
        for name in ("home", "look", "100", "cases"):
            self.assertIn("assets/screenshot-%s.png" % name, en)
            self.assertIn("assets/screenshot-%s-pt.png" % name, pt)
            self.assertNotIn("assets/screenshot-%s.png" % name, pt)
            self.assertTrue(os.path.isfile(os.path.join(sc.HERE, "assets", "screenshot-%s-pt.png" % name)))
            self.assertTrue(os.path.isfile(os.path.join(sc.HERE, "assets", "screenshot-%s.png" % name)))

    def test_the_four_screenshots_sit_in_one_grid_of_two_rows_of_two_with_the_same_size(self):
        from PIL import Image
        for name, suffix in (("README.md", ""), ("README.pt-BR.md", "-pt")):
            text = self.read(name)
            grid = re.search(r"<table.*?</table>", text, re.S).group(0)
            self.assertEqual(len(re.findall(r"<tr>", grid)), 2, name)
            self.assertEqual(len(re.findall(r"<td", grid)), 4, name)
            widths = set(re.findall(r'<img src="assets/screenshot-[a-z0-9]+%s\.png" width="(\d+)"' % suffix, grid))
            self.assertEqual(len(widths), 1, name)                                          # one width for all four
            for row in re.findall(r"<tr>.*?</tr>", grid, re.S):                              # the two pictures of a row have the same height
                sizes = {Image.open(os.path.join(sc.HERE, "assets", f)).size for f in re.findall(r'assets/(screenshot-[a-z0-9]+%s\.png)"' % suffix, row)}
                self.assertEqual(len(sizes), 1, "%s: %s" % (name, sizes))

    def test_the_words_the_project_keeps_out_of_public_files_are_in_neither(self):
        for name in ("README.md", "README.pt-BR.md"):
            self.assertNotRegex(self.read(name), r"(?i)flatpak|flathub|\baur\b")

    def test_the_buttons_the_portuguese_readme_names_are_the_ones_the_program_shows(self):
        pt = self.read("README.pt-BR.md")
        try:
            from qtui.i18n_pt_br import PT_BR
        except ImportError:
            self.skipTest("PySide6 missing")
        for english in ("Open the page in my browser", "Copy link", "Make covers", "Apply to Steam", "Restore previous artwork", "Reset to Steam's default art",
                        "Remove all", "Pick games, choose their cases", "Open my games page", "Browse…", "Use my own custom art where I have it", "Skip blurry covers",
                        "Open covers folder", "Rosette and ribbon", "Rosette only", "Gold case", "Gold border", "Normal case", "No special case",
                        "Mark family games with a green corner", "Remove only ours"):
            self.assertIn("**%s**" % PT_BR[english].rstrip("."), pt, english)


class DiscordButton(unittest.TestCase):
    """The Discord icon in the window's navigation: one link, one bundled image, credited."""
    PNG = os.path.join(sc.HERE, "assets", "discord.png")

    def test_the_invite_link_is_the_one_the_readme_uses(self):
        self.assertEqual(sc.DISCORD_URL, "https://discord.gg/JQMjAPWHCT")
        with open(os.path.join(sc.HERE, "README.md"), encoding="utf-8") as f:
            links = set(re.findall(r"https://discord\.gg/[A-Za-z0-9]+", f.read()))
        self.assertEqual(links, {sc.DISCORD_URL})

    def test_the_image_is_a_square_blurple_mark_on_transparency(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        with sc.Image.open(self.PNG) as im:
            im = im.convert("RGBA")
        self.assertEqual(im.size, (96, 96))
        solid = [p for p in pixels(im) if p[3] == 255]
        self.assertGreater(len(solid), 1500)
        self.assertTrue(all(p[:3] == (0x58, 0x65, 0xF2) for p in solid))                  # Discord's blurple, nothing else
        self.assertEqual(im.getpixel((0, 0))[3], 0)

    def test_the_mark_is_readable_on_the_navigation_background(self):
        def lum(rgb):
            c = [x / 255 for x in rgb]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        with open(os.path.join(sc.HERE, "qtui", "qml", "Theme.qml"), encoding="utf-8") as f:
            window = re.search(r'readonly property color bg: "#([0-9a-fA-F]{6})"', f.read()).group(1)
        bg = tuple(int(int(window[i:i + 2], 16) / 1.3) for i in (0, 2, 4))                 # the navigation panel: the window colour, darkened by 1.3 (Qt.darker)
        mark = (0x58, 0x65, 0xF2)                                                         # the blurple
        self.assertGreaterEqual((lum(mark) + .05) / (lum(bg) + .05), 3.0)                  # WCAG for graphics

    def test_the_packaged_app_bundles_the_image_and_credits_the_source(self):
        with open(os.path.join(sc.HERE, "steamcase-qt.spec"), encoding="utf-8") as f:
            self.assertIn("discord.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read()
        for must in ("Simple Icons", "CC0", "Discord", "trademark"):
            self.assertIn(must, text)


class KofiButton(unittest.TestCase):
    """The Ko-fi icon in the window's navigation, under Discord: one link, one bundled image, credited."""
    PNG = os.path.join(sc.HERE, "assets", "kofi.png")

    def test_the_link_is_the_one_the_readme_uses(self):
        self.assertEqual(sc.KOFI_URL, "https://ko-fi.com/diegobergonsi")
        with open(os.path.join(sc.HERE, "README.md"), encoding="utf-8") as f:
            links = set(re.findall(r"https://ko-fi\.com/[A-Za-z0-9]+", f.read()))
        self.assertEqual(links, {sc.KOFI_URL})

    def test_the_image_is_a_square_coral_mark_on_transparency(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        with sc.Image.open(self.PNG) as im:
            im = im.convert("RGBA")
        self.assertEqual(im.size, (96, 96))
        solid = [p for p in pixels(im) if p[3] == 255]
        self.assertGreater(len(solid), 1500)
        self.assertTrue(all(p[:3] == (0xFF, 0x5E, 0x5B) for p in solid))                  # Ko-fi's coral, nothing else
        self.assertEqual(im.getpixel((0, 0))[3], 0)

    def test_the_mark_is_readable_on_the_navigation_background(self):
        def lum(rgb):
            c = [x / 255 for x in rgb]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        with open(os.path.join(sc.HERE, "qtui", "qml", "Theme.qml"), encoding="utf-8") as f:
            window = re.search(r'readonly property color bg: "#([0-9a-fA-F]{6})"', f.read()).group(1)
        bg = tuple(int(int(window[i:i + 2], 16) / 1.3) for i in (0, 2, 4))
        self.assertGreaterEqual((lum((0xFF, 0x5E, 0x5B)) + .05) / (lum(bg) + .05), 3.0)

    def test_the_packaged_app_bundles_the_image_and_credits_the_source(self):
        with open(os.path.join(sc.HERE, "steamcase-qt.spec"), encoding="utf-8") as f:
            self.assertIn("kofi.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read()
        for must in ("Ko-fi", "kofi.svg", "trademark"):
            self.assertIn(must, text)


class CoverNotesAndSpec(unittest.TestCase):
    """read_notes, by_hand, matches, scan_covers and usual_covers: the one place a cover's notes are read and compared."""
    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def png(self, name, **notes):
        from PIL.PngImagePlugin import PngInfo
        info = PngInfo()
        for key, value in notes.items():
            info.add_text(key, value)
        path = os.path.join(self.tmp, name)
        sc.Image.new("RGBA", (8, 8)).save(path, pnginfo=info)
        return path

    def test_an_unreadable_file_has_no_notes(self):
        self.assertIsNone(sc.read_notes(os.path.join(self.tmp, "missing_1.png")))
        bad = os.path.join(self.tmp, "bad_1.png")
        with open(bad, "w") as f:
            f.write("not a picture")
        self.assertIsNone(sc.read_notes(bad))
        link = os.path.join(self.tmp, "link_2.png")
        try:
            os.symlink(self.png("real_3.png"), link)
        except (OSError, NotImplementedError):
            return
        self.assertIsNone(sc.read_notes(link))

    def test_each_note_is_its_value_none_when_absent_and_false_when_it_is_not_one_we_write(self):
        plain = sc.read_notes(self.png("plain_1.png"))
        self.assertEqual(plain, sc.CoverNotes((0, 100, 100), None, None, None, None, None))
        full = sc.read_notes(self.png("full_2.png", **{sc.HUE_CHUNK: "120", sc.TONE_CHUNK: "40 70", sc.DONE_CHUNK: "ribbon", sc.THEME_CHUNK: "christmas",
                                                       sc.ART_CHUNK: "custom 0123456789abcdef"}))
        self.assertEqual(full, sc.CoverNotes((120, 40, 70), "ribbon", "christmas", None, None, "custom 0123456789abcdef"))
        console = sc.read_notes(self.png("ps5_3.png", **{sc.PLATFORM_CHUNK: "ps5", sc.GROUP_CHUNK: "gabc12345"}))
        self.assertEqual((console.platform, console.group), ("ps5", "gabc12345"))
        garbled = sc.read_notes(self.png("bad_4.png", **{sc.HUE_CHUNK: "400", sc.DONE_CHUNK: "gold-sparkle", sc.THEME_CHUNK: "xmas", sc.PLATFORM_CHUNK: "atari",
                                                         sc.GROUP_CHUNK: "Not valid!", sc.ART_CHUNK: "custom xyz"}))
        self.assertEqual(garbled, sc.CoverNotes(None, False, False, False, False, False))

    def test_by_hand(self):
        notes = lambda **k: sc.read_notes(self.png("n_%d.png" % len(os.listdir(self.tmp)), **k))
        self.assertIsNone(sc.by_hand(notes()))                                           # a usual cover
        self.assertTrue(sc.by_hand(notes(**{sc.PLATFORM_CHUNK: "ps5"})))
        self.assertTrue(sc.by_hand(notes(**{sc.GROUP_CHUNK: "gabc12345"})))
        self.assertIs(sc.by_hand(notes(**{sc.PLATFORM_CHUNK: "atari"})), False)           # a damaged note: the cover is rebuilt
        self.assertIs(sc.by_hand(notes(**{sc.GROUP_CHUNK: "Not valid!"})), False)
        self.assertIs(sc.by_hand(None), False)                                           # unreadable
        self.assertIs(sc.cover_by_hand(os.path.join(self.tmp, "missing_9.png")), False)

    def test_the_old_readers_answer_as_before(self):
        path = self.png("x_1.png", **{sc.DONE_CHUNK: "ribbon", sc.PLATFORM_CHUNK: "xboxone"})
        self.assertEqual((sc.cover_treatment(path), sc.cover_platform(path), sc.cover_theme(path), sc.cover_group(path), sc.cover_art(path)), ("ribbon", "xboxone", None, None, None))
        missing = os.path.join(self.tmp, "missing_2.png")
        self.assertEqual((sc.cover_treatment(missing), sc.cover_platform(missing), sc.cover_theme(missing), sc.cover_group(missing), sc.cover_art(missing)), (False,) * 5)
        self.assertIsNone(sc.cover_colour(missing))
        self.assertEqual(sc.cover_hue(self.png("h_3.png", **{sc.HUE_CHUNK: "200"})), 200)

    def test_matches_compares_only_the_fields_the_spec_names(self):
        notes = sc.read_notes(self.png("m_1.png", **{sc.HUE_CHUNK: "90", sc.DONE_CHUNK: "ribbon"}))
        spec = sc.CoverSpec
        self.assertTrue(sc.matches(notes, spec()))                                       # nothing asked: anything matches
        self.assertTrue(sc.matches(notes, spec(colour=(90, 100, 100), treatment="ribbon", theme=None, art=None, platform=None, group=None)))
        self.assertFalse(sc.matches(notes, spec(colour=(91, 100, 100))))
        self.assertFalse(sc.matches(notes, spec(treatment=None)))                        # None is a wish too: no marks
        self.assertFalse(sc.matches(notes, spec(theme="christmas")))
        self.assertFalse(sc.matches(notes, spec(platform="ps5")))
        self.assertFalse(sc.matches(notes, spec(group="gabc12345")))
        self.assertFalse(sc.matches(None, spec()))                                       # missing or unreadable: make it
        garbled = sc.read_notes(self.png("g_2.png", **{sc.DONE_CHUNK: "gold-sparkle"}))
        self.assertFalse(sc.matches(garbled, spec(treatment=None)))                      # a note we do not write never equals anything

    def test_the_same_look_at_zero_colourfulness_is_the_same_colour(self):
        notes = sc.read_notes(self.png("z_1.png", **{sc.HUE_CHUNK: "10", sc.TONE_CHUNK: "0 50"}))
        self.assertTrue(sc.matches(notes, sc.CoverSpec(colour=(200, 0, 50))))            # the hue means nothing at 0 sat

    def test_a_console_spec_ignores_the_colour_and_the_theme(self):
        notes = sc.read_notes(self.png("c_1.png", **{sc.PLATFORM_CHUNK: "ps4", sc.DONE_CHUNK: "ribbon", sc.LAYOUT_CHUNK: sc.LAYOUT}))
        self.assertTrue(sc.matches(notes, sc._spec_for("ps4", (0, 100, 100), "gold-case-rosette", "christmas", None, None)) is False)
        self.assertTrue(sc.matches(notes, sc._spec_for("ps4", (0, 100, 100), "ribbon", "christmas", None, None)))

    def test_scan_covers_lists_only_cover_files_by_name(self):
        self.png("B_Game_20.png"), self.png("A_Game_3.png"), self.png("notes.png"), self.png("C_Game_4.PNG")
        open(os.path.join(self.tmp, "D_Game_5.txt"), "w").close()
        self.assertEqual([a for a, _ in sc.scan_covers(self.tmp)], [3, 20])
        self.assertEqual(sc.scan_covers(os.path.join(self.tmp, "nowhere")), [])

    def test_usual_covers_leaves_out_covers_by_hand_and_unreadable_files(self):
        self.png("U_Game_1.png"), self.png("H_Game_2.png", **{sc.GROUP_CHUNK: "gabc12345"}), self.png("P_Game_3.png", **{sc.PLATFORM_CHUNK: "ps5"})
        with open(os.path.join(self.tmp, "X_Game_4.png"), "w") as f:
            f.write("not a picture")
        found = sc.usual_covers(self.tmp)
        self.assertEqual([a for a, _, _ in found], [1])
        self.assertIsInstance(found[0][2], sc.CoverNotes)


class UpdateIcon(unittest.TestCase):
    """The refresh icon of "Check for updates" in the navigation: the project's own drawing, one bundled image."""
    PNG = os.path.join(sc.HERE, "assets", "update.png")

    def test_the_image_is_a_square_mark_in_the_muted_text_colour_on_transparency(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        with sc.Image.open(self.PNG) as im:
            im = im.convert("RGBA")
        self.assertEqual(im.size, (96, 96))
        solid = [p for p in pixels(im) if p[3] == 255]
        self.assertGreater(len(solid), 500)
        muted = tuple(int(THEME["muted"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(all(p[:3] == muted for p in solid))                  # Theme.muted, the colour of the link's words
        self.assertEqual(im.getpixel((0, 0))[3], 0)

    def test_the_packaged_app_bundles_the_image_and_says_the_drawing_is_ours(self):
        with open(os.path.join(sc.HERE, "steamcase-qt.spec"), encoding="utf-8") as f:
            self.assertIn("update.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"`tools/src/update\.svg`[^\n]*own")


class ChristmasOverlay(unittest.TestCase):
    """The artwork of the Christmas case theme: a transparent overlay with a Santa hat, a tree and gifts."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        with sc.Image.open(sc.CHRISTMAS_OVERLAY) as im:
            self.mode, self.ov = im.mode, im.convert("RGBA")

    def ink(self, box):
        """How many pixels of the overlay in `box` are not fully transparent."""
        return sum(1 for p in pixels(self.ov.crop(box)) if p[3] > 0)

    def test_it_is_a_full_size_rgba_png(self):
        self.assertEqual((self.mode, self.ov.size), ("RGBA", (600, 900)))

    def test_the_three_decorations_are_where_they_should_be(self):
        self.assertGreaterEqual(self.ink((0, 700, 200, 900)), 400)                    # the tree, bottom-left
        self.assertGreaterEqual(self.ink((440, 760, 600, 900)), 400)                  # the gifts, bottom-right
        self.assertGreaterEqual(self.ink((230, 0, 400, 135)), 400)                    # the Santa hat, top centre

    def test_the_rest_of_the_cover_stays_clear(self):
        self.assertEqual(self.ink((140, 300, 460, 760)), 0)                           # the middle of the art
        self.assertEqual(self.ink((14, 96, 60, 140)), 0)                              # under the family corner
        self.assertEqual(self.ink((440, 20, 586, 80)), 0)                             # the platform badges, where the rosette goes

    def test_the_decorations_that_matter_are_opaque(self):
        solid = sum(1 for p in pixels(self.ov.crop((440, 760, 600, 900))) if p[3] == 255)
        self.assertGreater(solid, 3000)                                               # gifts and a tree, not a faint sketch

    def test_the_packaged_app_bundles_it_and_the_licence_file_credits_it(self):
        with open(os.path.join(sc.HERE, "steamcase-qt.spec"), encoding="utf-8") as f:
            self.assertIn("christmas_overlay.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read().lower()
        for must in ("christmas", "original artwork"):
            self.assertIn(must, text)


class ThemeCovers(unittest.TestCase):
    """The Christmas theme on a cover: the decorations, the note that records it, and reading it back."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = os.path.join(self.tmp, "portrait.png")
        sc.Image.new("RGB", (600, 900), (200, 60, 60)).save(self.src)

    def built(self, name, theme=None, hue=0):
        out = os.path.join(self.tmp, name)
        sc.build_cover(self.src, out, sc.load_frame(hue), hue, theme=theme)
        return out

    def test_apply_theme_adds_the_decorations_and_nothing_else(self):
        c = sc.preview_cover()
        self.assertIs(sc.apply_theme(c, None), c)
        themed, plain = sc.preview_cover(134, theme="christmas"), sc.preview_cover(134)
        self.assertNotEqual(themed.getpixel((520, 842)), plain.getpixel((520, 842)))             # the gifts
        self.assertEqual(themed.getpixel((300, 400)), plain.getpixel((300, 400)))                # the art
        self.assertEqual(themed.getpixel((7, 450)), plain.getpixel((7, 450)))                    # the case keeps its colour
        self.assertEqual(themed.getpixel((0, 0))[3], 0)                                          # nothing reaches past the rounded case

    def test_the_theme_is_noted_and_read_back(self):
        themed, plain = self.built("t.png", "christmas"), self.built("p.png")
        self.assertEqual(sc.cover_theme(themed), "christmas")
        self.assertIsNone(sc.cover_theme(plain))
        self.assertNotIn(sc.THEME_CHUNK, sc.Image.open(plain).info)                              # classic covers carry no note, as before themes existed
        from PIL.PngImagePlugin import PngInfo
        for bad in ("Christmas", "christmas2", ""):
            info = PngInfo()
            info.add_text(sc.THEME_CHUNK, bad)
            garbled = os.path.join(self.tmp, "g.png")
            sc.Image.new("RGBA", sc.SIZE).save(garbled, pnginfo=info)
            self.assertIs(sc.cover_theme(garbled), False, bad)
        self.assertIs(sc.cover_theme(os.path.join(self.tmp, "missing.png")), False)

    def test_the_folder_helpers_read_the_first_cover(self):
        d = os.path.join(self.tmp, "covers")
        os.makedirs(d)
        self.assertIsNone(sc.existing_cover_theme(d))
        self.assertIsNone(sc.existing_cover_theme(os.path.join(self.tmp, "nowhere")))
        self.assertFalse(sc.covers_in_other_theme(d, "christmas"))
        sc.build_cover(self.src, os.path.join(d, "A_1_1.png"), sc.load_frame(0), 0)
        sc.build_cover(self.src, os.path.join(d, "B_2_2.png"), sc.load_frame(0), 0, theme="christmas")
        self.assertIsNone(sc.existing_cover_theme(d))                                           # the first by name decides
        self.assertTrue(sc.covers_in_other_theme(d, "christmas"))
        self.assertTrue(sc.covers_in_other_theme(d, None))
        os.remove(os.path.join(d, "A_1_1.png"))
        self.assertEqual(sc.existing_cover_theme(d), "christmas")
        self.assertFalse(sc.covers_in_other_theme(d, "christmas"))

    def test_a_cover_from_the_removed_halloween_theme_counts_as_another_theme(self):
        from PIL.PngImagePlugin import PngInfo
        d = os.path.join(self.tmp, "covers")
        os.makedirs(d)
        old = os.path.join(d, "A_1_1.png")
        sc.build_cover(self.src, old, sc.load_frame(0), 0, theme="christmas")
        info = PngInfo()
        with sc.Image.open(old) as im:
            for key, value in im.text.items():
                info.add_text(key, "halloween" if key == sc.THEME_CHUNK else value)
            im.copy().save(old, pnginfo=info)
        self.assertIs(sc.cover_theme(old), False)
        self.assertTrue(sc.covers_in_other_theme(d, "christmas"))                               # so the make-again message shows

    def test_build_cover_refuses_an_unknown_theme(self):
        with self.assertRaises(ValueError):
            self.built("x.png", "spooky")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x.png")))


class ReleaseMessage(unittest.TestCase):
    """tools/release_message.py: the release page text and the Discord announcement, both taken from docs/CHANGELOG.md."""
    SAMPLE = ("# Changelog\n\nIntro.\n\n## [Unreleased]\n- Not out yet.\n\n## [1.5.0] - 2026-10-29\n- New: a thing.\n- Fix: another `thing`.\n\n"
              "## [1.4.0] - 2026-10-27\n- Old: before.\n")

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("release_message", os.path.join(sc.HERE, "tools", "release_message.py"))
        cls.rm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.rm)

    def test_section_returns_only_that_versions_bullets(self):
        for name in ("1.5.0", "v1.5.0"):
            self.assertEqual(self.rm.section(self.SAMPLE, name), "- New: a thing.\n- Fix: another `thing`.")
        self.assertEqual(self.rm.section(self.SAMPLE, "v1.4.0"), "- Old: before.")

    def test_section_refuses_a_missing_or_empty_version(self):
        for bad in ("v9.9.9", "Unreleased", "", "v1.5"):
            with self.assertRaises(ValueError, msg=bad):
                self.rm.section(self.SAMPLE, bad)
        with self.assertRaises(ValueError):
            self.rm.section("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n- x\n", "v1.0.0")          # a header with nothing under it

    def test_the_real_changelog_has_this_release(self):
        with open(os.path.join(sc.HERE, "docs", "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Halloween", self.rm.section(text, "v1.5.0"))

    def test_the_changelog_has_the_1_6_0_notes(self):
        with open(os.path.join(sc.HERE, "docs", "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        notes = self.rm.section(text, "v1.6.0")
        for word in ("Qt", "Ko-fi", "console", "Groups", "custom art", "Good to know", "Steam Deck", "named pipe"):
            self.assertIn(word, notes)
        self.assertRegex(text, r"## \[1\.6\.0\] - 2026-11-03")
        for word in ("bottom of the list on the left", "README", "Qt window tests"):
            self.assertIn(word, notes)
        description = self.rm.announcement(text, "v1.6.0", "https://example.test/r")["embeds"][0]["description"]
        self.assertNotIn("Documentation", description)
        self.assertLess(len(description), 1700)

    def test_the_changelog_has_the_1_6_1_notes_and_nothing_waits_under_unreleased(self):
        with open(os.path.join(sc.HERE, "docs", "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        notes = self.rm.section(text, "v1.6.1")
        for word in ("100%", "Fixed", "Portuguese", "case", "asks first"):
            self.assertIn(word, notes)
        self.assertRegex(text, r"## \[1\.6\.1\] - 2026-11-03")
        self.assertNotRegex(text, r"## \[Unreleased\]\n+- ")                   # everything that was waiting is in 1.6.1
        description = self.rm.announcement(text, "v1.6.1", "https://example.test/r")["embeds"][0]["description"]
        self.assertNotIn("Documentation", description)
        self.assertLess(len(description), 1700)
        self.assertTrue(description.startswith("- Covers of your 100% games"))     # the fix comes first: it is what people must know

    def test_the_changelog_has_the_1_7_0_notes(self):
        with open(os.path.join(sc.HERE, "docs", "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        notes = self.rm.section(text, "v1.7.0")
        for word in ("My own case", "Christmas", "Manage", "collections", "Start over", "No marks", "All Games", "python -m engine", "Tab", "Portuguese"):
            self.assertIn(word, notes)
        self.assertRegex(text, r"## \[1\.7\.0\] - 2026-11-09")
        self.assertNotRegex(text, r"## \[Unreleased\]\n+- ")                   # nothing waits under Unreleased
        announcement = self.rm.announcement(text, "v1.7.0", "https://example.test/r")["embeds"][0]["description"]
        self.assertNotIn("Documentation", announcement)
        self.assertLess(len(announcement), self.rm.LIMIT)
        self.assertTrue(announcement.startswith("- Use a case you made yourself."))      # what the person can do first

    def test_the_release_page_body_is_the_section_plus_how_to_check_the_files(self):
        body = self.rm.release_body(self.SAMPLE, "v1.5.0")
        self.assertTrue(body.startswith("- New: a thing."))
        self.assertNotIn("Old: before", body)
        self.assertIn("SHA256SUMS", body)
        self.assertIn("gh attestation verify", body)

    def test_the_announcement_is_one_embed_with_the_changelog_and_the_link(self):
        url = "https://github.com/diegobergonsi/steam-case-covers/releases/tag/v1.5.0"
        payload = self.rm.announcement(self.SAMPLE, "v1.5.0", url)
        json.dumps(payload)                                                           # it must be plain JSON
        (embed,) = payload["embeds"]
        self.assertIn("v1.5.0", embed["title"])
        self.assertEqual(embed["url"], url)
        self.assertIn("a thing", embed["description"])
        self.assertNotIn("Old: before", embed["description"])
        self.assertIn("(%s)" % url, embed["description"])                              # the way to the full notes is always there
        self.assertEqual(payload["allowed_mentions"], {"parse": []})                  # words in the changelog can never ping anyone

    def test_the_announcement_keeps_the_first_sentence_of_each_bullet_and_drops_documentation(self):
        text = ("## [2.0.0] - 2026-11-01\n- New: a big feature. It has many details. And more details.\n"
                "- Fix: a bug in `apply` (see the notes). Nothing else.\n- Documentation: the README changed. Lots of words.\n")
        lines = self.rm.announcement(text, "v2.0.0", "https://example.test/r")["embeds"][0]["description"].split("\n")
        self.assertEqual(lines[:2], ["- New: a big feature.", "- Fix: a bug in `apply` (see the notes)."])
        joined = "\n".join(lines)
        for gone in ("many details", "Nothing else", "Documentation", "README"):
            self.assertNotIn(gone, joined)
        self.assertIn("Full notes", joined)

    def test_a_documentation_only_release_still_has_a_message(self):
        text = "## [2.0.1] - 2026-11-02\n- Documentation: the README changed. Lots of words.\n"
        description = self.rm.announcement(text, "v2.0.1", "https://example.test/r")["embeds"][0]["description"]
        self.assertIn("- Documentation: the README changed.", description)
        self.assertNotIn("Lots of words", description)

    def test_a_very_long_sentence_is_cut_at_a_word(self):
        text = "## [2.0.2] - 2026-11-03\n- New: " + "word " * 200 + "end.\n"
        line = self.rm.announcement(text, "v2.0.2", "https://example.test/r")["embeds"][0]["description"].split("\n")[0]
        self.assertLessEqual(len(line), 240)
        self.assertTrue(line.endswith("…"))
        self.assertTrue(line[:-1].endswith("word"))

    def test_the_real_release_message_is_short(self):
        with open(os.path.join(sc.HERE, "docs", "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        description = self.rm.announcement(text, "v1.5.0", "https://example.test/r")["embeds"][0]["description"]
        self.assertIn("Halloween", description)
        self.assertNotIn("Documentation", description)
        self.assertLess(len(description), 1200)

    def test_a_long_changelog_is_cut_at_a_line_and_points_to_the_release_page(self):
        long = "## [1.5.0] - 2026-10-29\n" + "".join("- Line number %d of a very long list of changes.\n" % i for i in range(400))
        url = "https://example.test/release"
        embed = self.rm.announcement(long, "v1.5.0", url)["embeds"][0]
        self.assertLessEqual(len(embed["description"]), 4096)
        self.assertIn(url, embed["description"])
        self.assertIn("Line number 0 ", embed["description"])
        self.assertNotIn("Line number 399", embed["description"])
        self.assertFalse(embed["description"].split("\n")[0].endswith("…"))           # cut between lines, not in the middle of one

    def test_the_command_line_prints_the_body_and_the_json(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "CHANGELOG.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE)
            for args, check in ((["body", "v1.5.0", "--changelog", path], lambda t: "New: a thing" in t),
                                (["announce", "v1.5.0", "--changelog", path, "--repo", "o/r"], lambda t: json.loads(t)["embeds"][0]["url"] == "https://github.com/o/r/releases/tag/v1.5.0")):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(self.rm.main(args), 0)
                self.assertTrue(check(out.getvalue()), args)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.rm.main(["body", "v9.9.9", "--changelog", path]), 1)       # a missing version fails the release step loudly

    def test_the_workflows_use_it_without_putting_the_secret_in_a_script(self):
        wf = os.path.join(sc.HERE, ".github", "workflows")
        with open(os.path.join(wf, "release.yml"), encoding="utf-8") as f:
            release = f.read()
        with open(os.path.join(wf, "announce-release.yml"), encoding="utf-8") as f:
            announce = f.read()
        self.assertIn("body_path", release)
        self.assertNotIn("generate_release_notes: true", release)
        self.assertIn("tools/release_message.py", release)
        self.assertIn("workflow_dispatch", announce)
        self.assertIn("tools/release_message.py", announce)
        self.assertIn("continue-on-error: true", release)                             # a Discord problem never marks a published release as failed
        self.assertNotIn("continue-on-error", announce)                               # but a manual run must fail loudly (a mistyped tag once showed a green job)
        for text in (release, announce):
            self.assertIn("DISCORD_WEBHOOK_URL", text)
            for line in text.splitlines():
                self.assertFalse("curl" in line and "secrets." in line, line)           # the secret goes through the environment, never into the command line text


class CustomArt(Base):
    """The user's own portraits in Steam's grid folder: found, and kept in the app's own folder."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.originals = os.path.join(self.tmp, "originals")

    def kept(self, appid, ext="jpg", account="111"):
        return os.path.join(self.originals, account, "%d.%s" % (appid, ext))

    def applied(self, appid, grid=None):
        """What Apply leaves in the grid folder: our cover as <appid>p.png."""
        plain = self.art("applied.jpg", folder=self.tmp)
        sc.build_cover(plain, os.path.join(grid or self.grid, "%dp.png" % appid), sc.load_frame(0))

    def art(self, name, colour=(10, 120, 30), fmt="JPEG", folder=None):
        path = os.path.join(folder or self.grid, name)
        sc.Image.new("RGB", (100, 150), colour).save(path, format=fmt)
        return path

    def test_a_custom_jpg_is_found_and_copied_to_originals(self):
        src = self.art("100p.jpg")
        found = sc.find_custom_art(self.steam, originals=self.originals)
        self.assertEqual(found, {100: self.kept(100)})
        self.assertEqual(self.read(found[100]), self.read(src))

    def test_our_own_cover_is_not_custom_art(self):
        plain = self.art("x.jpg", folder=self.tmp)
        sc.build_cover(plain, os.path.join(self.grid, "101p.png"), sc.load_frame(0))
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_the_original_survives_apply_moving_the_jpg(self):
        src = self.art("100p.jpg")
        sc.find_custom_art(self.steam, originals=self.originals)
        os.remove(src)                                  # Apply moved it into the backup and put our cover in its place
        self.applied(100)
        found = sc.find_custom_art(self.steam, originals=self.originals)
        self.assertEqual(found, {100: self.kept(100)})

    def test_jpg_wins_over_png(self):
        self.art("102p.jpg", (200, 0, 0))
        self.art("102p.png", (0, 0, 200), fmt="PNG")
        found = sc.find_custom_art(self.steam, originals=self.originals)
        self.assertEqual(found, {102: self.kept(102)})
        self.assertFalse(os.path.exists(self.kept(102, "png")))

    def test_new_art_replaces_the_old_original(self):
        self.art("100p.jpg", (10, 10, 10))
        sc.find_custom_art(self.steam, originals=self.originals)
        src = self.art("100p.jpg", (250, 250, 250))
        found = sc.find_custom_art(self.steam, originals=self.originals)
        self.assertEqual(self.read(found[100]), self.read(src))

    def test_a_truncated_jpeg_is_ignored(self):
        noisy = sc.Image.frombytes("RGB", (200, 300), os.urandom(200 * 300 * 3))
        whole = os.path.join(self.tmp, "whole.jpg")
        noisy.save(whole, format="JPEG")
        with open(whole, "rb") as f:
            data = f.read()
        with open(os.path.join(self.grid, "106p.jpg"), "wb") as f:
            f.write(data[: len(data) // 2])
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})
        self.assertFalse(os.path.exists(self.kept(106)))

    def cover_from_art(self, dest, **kw):
        """A cover of the user's own art, as Make writes it: with the art note."""
        src = self.art("src.jpg", folder=self.tmp)
        sc.build_cover(src, dest, kw.pop("frame"), from_art=sc.art_note(src), **kw)

    def test_our_covers_made_from_own_art_in_a_console_case_or_by_hand_are_still_ours(self):
        for name, kw in (("console", dict(frame=sc.load_platform_frame("ps5"), platform="ps5")), ("group", dict(frame=sc.load_frame(0), group="abc")),
                         ("console group", dict(frame=sc.load_platform_frame("ps5"), platform="ps5", group="abc"))):
            with self.subTest(name):
                dest = os.path.join(self.grid, "100p.png")
                self.cover_from_art(dest, **kw)
                self.assertTrue(sc.is_steamcase_cover(dest))
                self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})       # and never taken as the user's art

    def test_a_stored_original_that_is_one_of_our_covers_is_never_used_as_art(self):
        self.applied(100)                                           # Steam holds our cover ...
        kept = self.kept(100, "png")
        os.makedirs(os.path.dirname(kept))
        self.cover_from_art(kept, frame=sc.load_platform_frame("ps5"), platform="ps5")          # ... and the copy kept as the "original" is a cover too (an older version did that)
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_an_original_is_not_used_once_steam_no_longer_holds_our_cover(self):
        src = self.art("100p.jpg")
        sc.find_custom_art(self.steam, originals=self.originals)
        os.remove(src)                                  # nothing in the grid now: reset --everything, or the user cleared the art
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_originals_are_kept_per_account(self):
        grid2 = os.path.join(self.steam, "userdata", "222", "config", "grid")
        os.makedirs(grid2)
        mine = self.art("100p.jpg", (200, 0, 0))
        sc.find_custom_art(self.steam, "111", originals=self.originals)
        os.remove(mine)
        self.applied(100)
        self.art("100p.jpg", (0, 0, 200), folder=grid2)                     # another account has its own art for the same game
        sc.find_custom_art(self.steam, "222", originals=self.originals)
        self.assertEqual(sc.find_custom_art(self.steam, "111", originals=self.originals), {100: self.kept(100)})
        self.assertNotEqual(self.read(self.kept(100)), self.read(self.kept(100, account="222")))
        self.assertEqual(sc.find_custom_art(self.steam, "222", originals=self.originals), {100: self.kept(100, account="222")})

    def test_one_account_does_not_see_the_art_of_another(self):
        grid2 = os.path.join(self.steam, "userdata", "222", "config", "grid")
        os.makedirs(grid2)
        self.art("100p.jpg")
        sc.find_custom_art(self.steam, "111", originals=self.originals)
        self.applied(100, grid2)
        self.assertEqual(sc.find_custom_art(self.steam, "222", originals=self.originals), {})

    def test_a_file_that_is_not_an_image_is_ignored(self):
        with open(os.path.join(self.grid, "103p.jpg"), "w") as f:
            f.write("not an image")
        self.art("107p.jpg")
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {107: self.kept(107)})

    def test_a_link_is_ignored(self):
        os.symlink(self.art("real.jpg", folder=self.tmp), os.path.join(self.grid, "104p.jpg"))
        self.art("107p.jpg")
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {107: self.kept(107)})

    def test_a_file_over_the_size_limit_is_ignored(self):
        self.art("105p.jpg")
        with mock.patch.object(sc, "MAX_DOWNLOAD", 50):
            self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_a_picture_over_the_pixel_limit_is_ignored(self):
        self.art("105p.jpg")
        with mock.patch.object(sc, "MAX_PIXELS", 100 * 150 - 1):
            self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {105: self.kept(105)})

    def test_names_with_leading_zeros_are_not_art(self):
        self.art("0100p.jpg")                           # Steam looks for 100p.jpg, not this
        self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_an_unreadable_grid_folder_gives_nothing(self):
        real = os.listdir

        def deny(path="."):
            if os.path.abspath(path) == os.path.abspath(self.grid):
                raise PermissionError(13, "denied")
            return real(path)
        with mock.patch.object(os, "listdir", deny):
            self.assertEqual(sc.find_custom_art(self.steam, originals=self.originals), {})

    def test_a_copy_that_fails_is_reported_and_the_file_is_used_where_it_is(self):
        src = self.art("100p.jpg")
        problems = []
        with mock.patch.object(sc, "_safe_copy", side_effect=OSError(28, "No space left on device")):
            found = sc.find_custom_art(self.steam, originals=self.originals, problems=problems)
        self.assertEqual(found, {100: src})
        self.assertEqual(len(problems), 1)
        self.assertIn("100", problems[0])

    def restore_point(self):
        """A backup to restore: Apply put one cover (game 2) in the grid."""
        return sc.apply_covers(self.steam, self.covers, "111", files=[self.cover(2)])["backup"]

    def test_restore_brings_back_art_the_grid_no_longer_holds(self):
        src = self.art("100p.jpg")
        sc.find_custom_art(self.steam, originals=self.originals)
        backup = self.restore_point()
        os.remove(src)                                  # the backup that held it is gone, and so is the file in Steam's folder
        sc.restore_backup(self.steam, backup, originals=self.originals)
        self.assertEqual(self.read(self.grid, "100p.jpg"), self.read(self.kept(100)))
        self.assertTrue(os.path.exists(self.kept(100)))                 # the copy stays

    def test_restore_leaves_art_the_grid_already_has(self):
        self.art("100p.jpg", (10, 10, 10))
        sc.find_custom_art(self.steam, originals=self.originals)
        backup = self.restore_point()
        newer = self.art("100p.jpg", (250, 250, 250))
        sc.restore_backup(self.steam, backup, originals=self.originals)
        self.assertEqual(self.read(newer), self.read(self.grid, "100p.jpg"))
        self.assertNotEqual(self.read(self.kept(100)), self.read(self.grid, "100p.jpg"))
        self.assertEqual(sorted(n for n in os.listdir(self.grid) if n.startswith("100")), ["100p.jpg"])

    def test_restore_does_not_bring_back_a_cover_we_hold_for_that_game(self):
        src = self.art("100p.jpg")
        sc.find_custom_art(self.steam, originals=self.originals)
        os.remove(src)
        self.applied(100)
        backup = self.restore_point()
        sc.restore_backup(self.steam, backup, originals=self.originals)
        self.assertFalse(os.path.exists(os.path.join(self.grid, "100p.jpg")))

    def test_restore_does_not_bring_back_another_accounts_art(self):
        grid2 = os.path.join(self.steam, "userdata", "222", "config", "grid")
        os.makedirs(grid2)
        self.art("100p.jpg", folder=grid2)
        sc.find_custom_art(self.steam, "222", originals=self.originals)
        os.remove(os.path.join(grid2, "100p.jpg"))
        backup = self.restore_point()
        sc.restore_backup(self.steam, backup, "111", originals=self.originals)
        self.assertFalse(os.path.exists(os.path.join(self.grid, "100p.jpg")))


class MakeFromCustomArt(StoreMocks):
    """make_covers with the user's own art inside the case."""

    def setUp(self):
        super().setUp()
        self.downloads = []
        plain = sc.http_get
        sc.http_get = lambda url, tries=3: self.downloads.append(url) or plain(url, tries)       # StoreMocks restores the real one afterwards

    def cover(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def art(self, name="mine.jpg", colour=(10, 160, 30), size=(100, 150)):
        path = os.path.join(self.tmp, name)
        sc.Image.new("RGB", size, colour).save(path, format="JPEG")
        return path

    def centre(self, appid):
        return sc.Image.open(self.cover(appid)).convert("RGB").getpixel((300, 480))

    def test_a_game_with_custom_art_uses_it_and_downloads_nothing(self):
        mine = self.art()
        sc.make_covers({1: None}, self.covers, custom_art={1: mine})
        r, g, b = self.centre(1)
        self.assertTrue(g > r + 60 and g > b + 60, (r, g, b))
        self.assertEqual(sc.cover_art(self.cover(1)), sc.art_note(mine))
        self.assertEqual(self.downloads, [])

    def test_a_game_in_a_console_case_uses_custom_art_too(self):
        mine = self.art()
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"}, custom_art={1: mine})
        self.assertEqual(sc.cover_art(self.cover(1)), sc.art_note(mine))
        self.assertEqual(self.downloads, [])
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"}, custom_art={})        # the option off: Steam's portrait comes back
        self.assertIsNone(sc.cover_art(self.cover(1)))

    def test_other_games_keep_steams_portrait(self):
        sc.make_covers({1: None, 2: None}, self.covers, custom_art={1: self.art()})
        r, g, b = self.centre(2)
        self.assertTrue(r > g + 60 and r > b + 60, (r, g, b))
        self.assertIsNone(sc.cover_art(self.cover(2)))
        self.assertEqual(len(self.downloads), 1)

    def test_the_cover_is_still_recognised_as_ours(self):
        mine = self.art()
        for name, look in (("plain", {}), ("a 100% game", {"completed": {1}, "treatment": "ribbon"}),
                           ("a theme", {"completed": {1}, "treatment": "rosette", "theme": "christmas"})):
            with self.subTest(name):
                sc.make_covers({1: None}, self.covers, custom_art={1: mine}, force=True, **look)
                self.assertTrue(sc.is_steamcase_cover(self.cover(1)))

    def test_same_source_keeps_the_cover_and_a_changed_source_rebuilds_it(self):
        mine = self.art()
        sc.make_covers({1: None}, self.covers, custom_art={1: mine})
        statuses = []
        sc.make_covers({1: None}, self.covers, custom_art={1: mine}, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual(statuses, ["exists"])
        before = sc.cover_art(self.cover(1))
        mine = self.art(colour=(200, 20, 200))
        sc.make_covers({1: None}, self.covers, custom_art={1: mine}, progress=lambda *a: statuses.append(a[4]))
        self.assertEqual(statuses[-1], "ok")
        self.assertNotEqual(sc.cover_art(self.cover(1)), before)

    def test_switching_off_rebuilds_with_steams_portrait(self):
        sc.make_covers({1: None}, self.covers, custom_art={1: self.art()})
        sc.make_covers({1: None}, self.covers)
        self.assertIsNone(sc.cover_art(self.cover(1)))
        r, g, b = self.centre(1)
        self.assertTrue(r > g + 60 and r > b + 60, (r, g, b))

    def test_custom_art_ignores_skip_auto_art(self):
        blurry = {"type": 0, "name": "Game 1", "assets": {"asset_url_format": "${FILENAME}", "library_capsule_2x": "portrait.png"}}
        sc.store_items = lambda ids, log=None, cancelled=None, errors=None: {i: blurry for i in ids}
        res = sc.make_covers({1: None}, self.covers, skip_auto_art=True)
        self.assertEqual((res["skipped"], os.path.exists(self.cover(1))), (1, False))            # without custom art the blurry portrait is skipped
        res = sc.make_covers({1: None}, self.covers, skip_auto_art=True, custom_art={1: self.art()})
        self.assertEqual((res["ok"], os.path.exists(self.cover(1))), (1, True))

    def test_covers_in_other_look_sees_the_art_change(self):
        mine = self.art()
        sc.make_covers({1: None}, self.covers)
        self.assertFalse(sc.covers_in_other_look(self.covers, 0))                                # custom art not asked about: nothing to say
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, custom_art={1: mine}))           # switching on
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, custom_art={}))
        sc.make_covers({1: None}, self.covers, custom_art={1: mine})
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, custom_art={1: mine}))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, custom_art={}))                  # switching off
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, custom_art={1: self.art(colour=(1, 2, 3))}))   # changed source

    def test_covers_with_other_art_looks_at_the_art_only(self):
        mine = self.art()
        sc.make_covers({1: None}, self.covers, hue=90)
        self.assertFalse(sc.covers_with_other_art(self.covers, {}))                  # the colour is not its business
        self.assertTrue(sc.covers_with_other_art(self.covers, {1: mine}))
        sc.make_covers({1: None}, self.covers, hue=90, custom_art={1: mine})
        self.assertFalse(sc.covers_with_other_art(self.covers, {1: mine}))
        self.assertTrue(sc.covers_with_other_art(self.covers, {}))
        self.assertTrue(sc.covers_with_other_art(self.covers, {1: self.art(colour=(1, 2, 3))}))

    def test_art_that_vanished_fails_that_game_only(self):
        res = sc.make_covers({1: None, 2: None}, self.covers, custom_art={1: os.path.join(self.tmp, "gone.jpg")})
        self.assertEqual(([a for a, _ in res["failed"]], res["ok"]), ([1], 1))
        self.assertTrue(os.path.exists(self.cover(2)))

    def test_covers_with_other_art_counts_only_the_games_asked_about(self):
        mine = self.art()
        sc.make_covers({1: None, 2: None}, self.covers, custom_art={1: mine, 2: mine})
        self.assertTrue(sc.covers_with_other_art(self.covers, {}))
        self.assertTrue(sc.covers_with_other_art(self.covers, {}, games={1}))
        self.assertFalse(sc.covers_with_other_art(self.covers, {}, games={3}))                   # games the run will not touch do not count
        self.assertFalse(sc.covers_with_other_art(self.covers, {1: mine, 2: mine}, games={1, 2}))

    def test_covers_with_art_lists_the_games_built_from_art(self):
        sc.make_covers({1: None, 2: None}, self.covers, custom_art={1: self.art()})
        self.assertEqual(sc.covers_with_art(self.covers), {1})

    def test_wide_custom_art_is_cropped_to_the_window(self):
        sc.make_covers({1: None}, self.covers, custom_art={1: self.art(size=(1000, 500))})
        self.assertEqual(sc.Image.open(self.cover(1)).size, sc.SIZE)
        self.assertTrue(sc.is_steamcase_cover(self.cover(1)))


class CustomArtBase(StoreMocks):
    """A fake Steam account with a grid folder, and make on the command line."""

    def setUp(self):
        super().setUp()
        self.originals = os.path.join(self.tmp, "originals")
        patch = mock.patch.object(sc, "originals_dir", return_value=self.originals)         # never the real app folder
        patch.start()
        self.addCleanup(patch.stop)

    def mine(self, appid, colour=(10, 160, 30)):
        sc.Image.new("RGB", (100, 150), colour).save(os.path.join(self.grid, "%dp.jpg" % appid), format="JPEG")

    def make(self, out, *extra):
        lib = self.fake_library(True)
        return self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, *extra)

    def cover(self, out, appid):
        return os.path.join(out, "Game_%d_%d.png" % (appid, appid))



class CustomArtCli(CustomArtBase):
    """--use-custom-art on the command line."""

    def test_use_custom_art_builds_from_the_grid_file(self):
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--use-custom-art")
        self.assertIsNotNone(sc.cover_art(self.cover(out, 1)))
        self.assertIsNone(sc.cover_art(self.cover(out, 2)))                       # game 2 has no art of its own

    def test_without_the_flag_steams_portrait_is_used(self):
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out)
        self.assertIsNone(sc.cover_art(self.cover(out, 1)))

    def test_leaving_the_flag_out_keeps_covers_made_from_your_art(self):
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--use-custom-art")
        text = self.make(out, "--hue", "90")                                      # a colour change rebuilds it, still from your art
        self.assertIsNotNone(sc.cover_art(self.cover(out, 1)))
        self.assertIn("1 from your own art", text)

    def test_no_custom_art_goes_back_to_steams_portrait(self):
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--use-custom-art")
        self.make(out, "--no-custom-art")
        self.assertIsNone(sc.cover_art(self.cover(out, 1)))

    def test_leaving_the_flag_out_does_not_add_art_to_other_covers(self):
        out = os.path.join(self.tmp, "out")
        self.make(out)
        self.mine(1)
        self.make(out)
        self.assertIsNone(sc.cover_art(self.cover(out, 1)))

    def test_the_flag_and_its_opposite_cannot_be_combined(self):
        with self.assertRaises(SystemExit):
            self.make(os.path.join(self.tmp, "out"), "--use-custom-art", "--no-custom-art")

    def test_a_copy_that_fails_is_printed(self):
        self.mine(1)
        with mock.patch.object(sc, "_safe_copy", side_effect=OSError(28, "No space left on device")):
            text = self.make(os.path.join(self.tmp, "out"), "--use-custom-art")
        self.assertIn("could not keep a copy", text.lower())

    def test_the_summary_counts_custom_covers(self):
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.assertIn("1 from your own art", self.make(out, "--use-custom-art"))
        self.assertNotIn("from your own art", self.make(os.path.join(self.tmp, "out2")))

    def test_custom_art_for_a_game_outside_the_library_is_ignored(self):
        self.mine(9)
        out = os.path.join(self.tmp, "out")
        text = self.make(out, "--use-custom-art")
        self.assertFalse(os.path.exists(self.cover(out, 9)))
        self.assertNotIn("from your own art", text)


class NonSteamCli(CustomArtBase):
    """--include-non-steam on the command line."""
    SHORTCUT = 4000000000

    def setUp(self):
        super().setUp()
        from tests.test_shortcuts import vdf
        with open(os.path.join(self.cfg, "shortcuts.vdf"), "wb") as f:
            f.write(vdf([(self.SHORTCUT - 2 ** 32, "Cod Game")]))        # Steam stores the id as a signed number

    def shortcut_cover(self, out):
        return os.path.join(out, "Cod_Game_%d.png" % self.SHORTCUT)

    def test_the_flag_gives_a_shortcut_with_art_its_cover(self):
        self.mine(self.SHORTCUT)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--include-non-steam")
        self.assertIsNotNone(sc.cover_art(self.shortcut_cover(out)))

    def test_without_the_flag_the_shortcut_is_ignored(self):
        self.mine(self.SHORTCUT)
        out = os.path.join(self.tmp, "out")
        self.make(out)
        self.assertFalse(os.path.exists(self.shortcut_cover(out)))

    def test_a_shortcut_without_art_is_ignored_with_the_flag(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--include-non-steam")
        self.assertFalse(os.path.exists(self.shortcut_cover(out)))

    def test_the_flag_alone_does_not_use_the_art_of_steam_games(self):
        self.mine(self.SHORTCUT)
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--include-non-steam")
        self.assertIsNotNone(sc.cover_art(self.shortcut_cover(out)))
        self.assertIsNone(sc.cover_art(self.cover(out, 1)))

    def test_the_flag_with_use_custom_art_uses_both(self):
        self.mine(self.SHORTCUT)
        self.mine(1)
        out = os.path.join(self.tmp, "out")
        self.make(out, "--include-non-steam", "--use-custom-art")
        self.assertIsNotNone(sc.cover_art(self.shortcut_cover(out)))
        self.assertIsNotNone(sc.cover_art(self.cover(out, 1)))


class PlatformCases(Base):
    """The console cases: a frame and an art window per platform (assets/cases)."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")

    def test_every_platform_has_a_frame_and_window(self):
        for p in sc.PLATFORMS:
            with self.subTest(platform=p):
                frame = sc.load_platform_frame(p)
                self.assertEqual((frame.size, frame.mode), (sc.SIZE, "RGBA"))
                x0, y0, x1, y1 = sc.platform_window(p)
                self.assertTrue(0 <= x0 < x1 <= sc.SIZE[0] and 0 <= y0 < y1 <= sc.SIZE[1])
                self.assertTrue(x1 - x0 >= 400 and y1 - y0 >= 400)
                alpha = frame.getchannel("A").crop((x0, y0, x1, y1))
                tab = sc.platform_overlay(p)                                                       # a part of the window the frame itself covers (the Switch's red tab)
                if tab is None:
                    self.assertEqual(alpha.getextrema(), (0, 0))                                   # the art shows through
                else:
                    covered = alpha.copy()
                    covered.paste(0, (tab[0] - x0, tab[1] - y0, tab[2] - x0, tab[3] - y0))
                    self.assertEqual(covered.getextrema(), (0, 0))                                 # the art shows through everywhere else
                    inside = alpha.crop((tab[0] - x0, tab[1] - y0, tab[2] - x0, tab[3] - y0))                # the tab may be slanted: most of its box is opaque
                    self.assertGreater(sum(inside.getdata()) / (inside.width * inside.height), 150)

    def test_cases_json_says_what_the_frames_show(self):
        """The window is the box of the see-through pixels of the frame, the overlay the box of what the frame still covers inside it (the Switch's tab)."""
        for p in sc.PLATFORMS:
            with self.subTest(platform=p):
                alpha = sc.load_platform_frame(p).getchannel("A")
                window = alpha.point(lambda a: 255 if a == 0 else 0).getbbox()
                self.assertEqual(sc.platform_window(p), window)
                tab = alpha.crop(window).point(lambda a: 255 if a else 0).getbbox()
                self.assertEqual(sc.platform_overlay(p), None if tab is None else (tab[0] + window[0], tab[1] + window[1], tab[2] + window[0], tab[3] + window[1]))

    def test_labels_cover_every_platform(self):
        self.assertEqual(set(sc.PLATFORM_LABELS), set(sc.PLATFORMS))
        self.assertEqual(len(sc.PLATFORMS), 8)

    def test_unknown_platform_is_refused(self):
        for call in (sc.platform_window, sc.load_platform_frame):
            with self.assertRaises(ValueError):
                call("ps9")

    def test_family_corner_goes_top_right_over_the_end_of_the_banner(self):
        """The corner sits on the right so it never covers the logo on the left; it stays inside the case's own outline."""
        for p in sc.PLATFORMS:
            with self.subTest(platform=p):
                plain, family = sc.load_platform_frame(p), sc.load_platform_frame(p, True)
                self.assertNotEqual(plain.tobytes(), family.tobytes())
                x0, y0, x1, y1 = sc.platform_window(p)
                diff = sc.ImageChops.difference(plain, family).convert("RGB").convert("L").point(lambda v: 255 if v else 0)
                box = diff.getbbox()
                self.assertTrue(box[0] >= sc.SIZE[0] - 207 and box[2] <= sc.SIZE[0] and box[1] <= y0 and box[3] <= 207, (p, box))    # the top right corner, reaching into the banner
                outside = sc.Image.new("L", sc.SIZE, 255)
                outside.paste(0, (x0, y0, x1, y1))                                                                           # the window is see-through in the plain frame: the corner may fill it
                alpha = sc.ImageChops.multiply(sc.ImageChops.subtract(family.getchannel("A"), plain.getchannel("A")), outside)
                self.assertIsNone(alpha.getbbox())                                                                           # and adds nothing outside the case

    def test_the_playstation_cases_have_a_banner_on_top_and_the_art_below_it(self):
        """From her frames: a banner of about 100 rows holds the logo, the art starts under it."""
        for p in ("ps3", "ps4", "ps5"):
            with self.subTest(platform=p):
                x0, y0, x1, y1 = sc.platform_window(p)
                self.assertTrue(100 <= y0 <= 130, y0)
                frame = sc.load_platform_frame(p)
                self.assertGreater(frame.getpixel((300, y0 // 2))[3], 250)                               # the banner is opaque
                self.assertEqual(frame.getpixel((300, y0 + 40))[3], 0)                                   # the art shows below it

    def test_the_series_x_case_is_a_thin_shell_with_a_slanted_tab_and_art_to_the_top(self):
        """From photographs: the art reaches the top edge on the right of the tab."""
        frame = sc.load_platform_frame("xboxseries")
        x0, y0, x1, y1 = sc.platform_window("xboxseries")
        tab = sc.platform_overlay("xboxseries")
        self.assertTrue(tab[0] <= x0 + 1 and tab[1] <= y0 + 1 and 200 <= tab[2] - tab[0] <= 360 and 90 <= tab[3] - tab[1] <= 130, tab)
        self.assertEqual(frame.getpixel((x1 - 60, y0 + 20))[3], 0)                                     # art shows at the top right
        self.assertGreater(frame.getpixel((tab[0] + 20, tab[1] + 20))[3], 200)                         # the tab holds the sphere

    def test_the_100_marks_sit_left_below_the_banner_and_the_ribbon_has_her_width(self):
        """The rosette must never hide the logo of the case: it is on the left, MARKS_GAP from the art's edge and from the banner or tab above. The ribbon is
        RIBBON_WIDTH wide, centred in the window, RIBBON_GAP above its bottom."""
        art = os.path.join(self.tmp, "a.png")
        sc.Image.new("RGB", (120, 180), (30, 30, 30)).save(art)
        for p in sc.PLATFORMS:
            for treatment in ("ribbon", "rosette"):
                with self.subTest(platform=p, treatment=treatment):
                    plain, marked = os.path.join(self.tmp, "p.png"), os.path.join(self.tmp, "m.png")
                    sc.build_cover(art, plain, sc.load_platform_frame(p), platform=p)
                    sc.build_cover(art, marked, sc.load_platform_frame(p), platform=p, treatment=treatment)
                    (x0, y0, x1, y1), tab = sc.platform_window(p), sc.platform_overlay(p)
                    below = max(y0, tab[3] if tab else y0)
                    with sc.Image.open(plain) as a, sc.Image.open(marked) as b:
                        diff = sc.ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).convert("RGB").convert("L").point(lambda v: 255 if v else 0)
                        rosette = diff.crop((0, 0, sc.SIZE[0], 450)).getbbox()
                        self.assertIsNotNone(rosette)
                        self.assertAlmostEqual(rosette[0], x0 + sc.MARKS_GAP, delta=1)                                      # on the left
                        self.assertAlmostEqual(rosette[1], below + sc.MARKS_GAP, delta=1)                                   # below the banner, or the tab
                        self.assertTrue(rosette[2] <= x1 and rosette[3] <= y1, (rosette, (x0, y0, x1, y1)))               # inside the art window
                        if treatment == "ribbon":
                            ribbon = diff.crop((0, 450, sc.SIZE[0], sc.SIZE[1])).getbbox()
                            self.assertAlmostEqual(ribbon[2] - ribbon[0], sc.RIBBON_WIDTH, delta=2)
                            self.assertAlmostEqual((ribbon[0] + ribbon[2]) / 2, (x0 + x1) / 2, delta=2)
                            self.assertAlmostEqual(ribbon[3] + 450, y1 - sc.RIBBON_GAP, delta=2)
                        else:
                            self.assertIsNone(diff.crop((0, 450, sc.SIZE[0], sc.SIZE[1])).getbbox())                        # the rosette alone has no ribbon

    def circle_art(self, size):
        """A flat art with a white disc in the middle and a white line near the top."""
        art = sc.Image.new("RGBA", size, (20, 20, 80, 255))
        d = sc.ImageDraw.Draw(art)
        r = min(size) // 4
        d.ellipse((size[0] // 2 - r, size[1] // 2 - r, size[0] // 2 + r, size[1] // 2 + r), fill=(255, 255, 255, 255))
        d.rectangle((0, 30, size[0], 33), fill=(255, 0, 0, 255))
        return art

    def white_box(self, im, window):
        x0, y0, x1, y1 = window
        r, g, b = im.crop(window).convert("RGB").split()
        return sc.ImageChops.darker(sc.ImageChops.darker(r, g), b).point(lambda v: 255 if v > 240 else 0).getbbox()

    def test_a_portrait_close_to_the_window_is_stretched_to_fill_it_and_nothing_is_cut(self):
        """A 2:3 art is a little narrower than the case's window: it is stretched to the window's shape, so its top line and its disc are all there."""
        frame = sc.Image.new("RGBA", sc.SIZE, (0, 0, 0, 0))
        window = (14, 96, 586, 872)
        got = sc._compose(self.circle_art((600, 900)), frame, window)
        box = self.white_box(got, window)
        self.assertAlmostEqual((box[2] - box[0]) / (box[3] - box[1]), (572 / 600) / (776 / 900), delta=0.02)     # the disc is stretched by the same 10% as the whole art
        r, g, _ = got.crop(window).convert("RGB").split()
        line = sc.ImageChops.darker(r.point(lambda v: 255 if v > 200 else 0), g.point(lambda v: 255 if v < 80 else 0)).getbbox()
        self.assertAlmostEqual(line[1], round(30 * 776 / 900), delta=2)                      # no row is cropped at the top

    def test_an_art_far_from_the_windows_shape_is_cropped_not_stretched(self):
        frame = sc.Image.new("RGBA", sc.SIZE, (0, 0, 0, 0))
        window = (14, 96, 586, 872)
        box = self.white_box(sc._compose(self.circle_art((800, 800)), frame, window), window)        # a square art: 1.36 times wider than the window
        self.assertAlmostEqual((box[2] - box[0]) / (box[3] - box[1]), 1.0, delta=0.03)

    def test_a_wide_art_is_only_cropped(self):
        frame = sc.Image.new("RGBA", sc.SIZE, (0, 0, 0, 0))
        window = (14, 96, 586, 872)
        got = sc._compose(self.circle_art((900, 600)), frame, window)
        box = self.white_box(got, window)
        self.assertAlmostEqual((box[2] - box[0]) / (box[3] - box[1]), 1.0, delta=0.03)       # the disc stays round

    def test_compose_default_window_is_unchanged(self):
        art = sc.Image.new("RGBA", (300, 450), (200, 60, 60, 255))
        frame = sc.load_frame()
        self.assertEqual(sc._compose(art, frame).tobytes(), sc._compose(art, frame, sc.WINDOW).tobytes())
        x0, y0, _, _ = sc.WINDOW
        r, g, b = sc._compose(art, frame).getpixel((x0 + 40, y0 + 40))[:3]
        self.assertTrue(r > g + 80 and r > b + 80)                    # the art shows (the frame's gloss tints it a little)

    # ---- building a console cover ----
    def portrait(self, colour=(30, 220, 30)):
        path = os.path.join(self.tmp, "portrait.jpg")
        sc.Image.new("RGB", (300, 450), colour).save(path, format="JPEG", quality=100)
        return path

    def build(self, platform, name="c.png", family=False, **kw):
        out = os.path.join(self.tmp, name)
        sc.build_cover(self.portrait(), out, sc.load_platform_frame(platform, family), platform=platform, **kw)
        return out

    def test_build_writes_only_the_platform_note(self):
        out = self.build("ps5")
        self.assertEqual(sc.cover_platform(out), "ps5")
        with sc.Image.open(out) as im:
            self.assertEqual(im.size, sc.SIZE)
            for chunk in (sc.HUE_CHUNK, sc.TONE_CHUNK, sc.THEME_CHUNK, sc.DONE_CHUNK, sc.ART_CHUNK):
                self.assertNotIn(chunk, im.info)

    def test_art_stays_inside_the_window(self):
        for p in ("ps5", "switch"):
            with self.subTest(platform=p):
                out = self.build(p)
                x0, y0, x1, y1 = sc.platform_window(p)
                with sc.Image.open(out) as im:
                    im = im.convert("RGBA")
                    green = lambda px: px[1] > 150 and px[0] < 90 and px[2] < 90
                    self.assertTrue(green(im.getpixel((x0 + 30, y1 - 30))))                  # (not near the top-left: the Switch's tab is there)
                    self.assertTrue(green(im.getpixel((x1 - 30, y1 - 30))))
                    self.assertTrue(green(im.getpixel((x1 - 30, y0 + 30))))
                    self.assertFalse(green(im.getpixel((x0 - 8, y0 + 100))))           # the case's border, outside the window

    def test_platform_with_a_theme_is_refused(self):
        with self.assertRaises(ValueError):
            self.build("ps5", theme="christmas")

    def test_platform_with_a_gold_treatment_is_refused(self):
        for t in ("gold-case", "gold-border", "gold-case-rosette", "gold-border-rosette"):
            with self.subTest(treatment=t), self.assertRaises(ValueError):
                self.build("ps5", treatment=t)

    def test_unknown_platform_is_refused_when_building(self):
        with self.assertRaises(ValueError):
            sc.build_cover(self.portrait(), os.path.join(self.tmp, "x.png"), sc.load_frame(), platform="ps9")

    def test_marks_are_allowed_and_noted(self):
        for t in ("ribbon", "rosette"):
            with self.subTest(treatment=t):
                out = self.build("xboxone", treatment=t)
                self.assertEqual((sc.cover_platform(out), sc.cover_treatment(out)), ("xboxone", t))

    def test_cover_platform_reads_only_notes_we_write(self):
        def png(name, note=None):
            path = os.path.join(self.tmp, name)
            info = sc.PngInfo()
            if note is not None:
                info.add_text(sc.PLATFORM_CHUNK, note)
            sc.Image.new("RGBA", sc.SIZE).save(path, format="PNG", pnginfo=info)
            return path
        self.assertEqual(sc.cover_platform(png("a.png", "ps4")), "ps4")
        self.assertIsNone(sc.cover_platform(png("b.png")))
        self.assertIs(sc.cover_platform(png("c.png", "ps9")), False)
        self.assertIs(sc.cover_platform(png("d.png", "PS4")), False)
        junk = os.path.join(self.tmp, "e.png")
        sc.Image.new("RGB", (10, 10)).save(junk, format="JPEG")
        self.assertIs(sc.cover_platform(junk), False)
        self.assertIs(sc.cover_platform(os.path.join(self.tmp, "missing.png")), False)

    def test_preview_in_a_console_case(self):
        for p in sc.PLATFORMS:
            with self.subTest(platform=p):
                self.assertEqual(sc.preview_cover(platform=p).size, sc.SIZE)
        self.assertNotEqual(sc.preview_cover(platform="ps5").tobytes(), sc.preview_cover().tobytes())
        self.assertNotEqual(sc.preview_cover(platform="ps5", family=True).tobytes(), sc.preview_cover(platform="ps5").tobytes())
        with self.assertRaises(ValueError):
            sc.preview_cover(platform="ps5", theme="christmas")
        with self.assertRaises(ValueError):
            sc.preview_cover(platform="ps5", treatment="gold-case")

    # ---- recognising a console cover (Reset, Restore) ----
    def noise(self, seed=1):
        import random
        rnd = random.Random(seed)
        path = os.path.join(self.tmp, "noise%d.png" % seed)
        im = sc.Image.new("RGB", (120, 180))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(120 * 180)])
        im.save(path, format="PNG")
        return path

    def console_cover(self, platform, name, family=False, treatment=None, seed=1):
        out = os.path.join(self.tmp, name)
        sc.build_cover(self.noise(seed), out, sc.load_platform_frame(platform, family), platform=platform, treatment=treatment)
        return out

    def test_each_console_cover_is_recognised(self):
        for p in sc.PLATFORMS:
            for family in (False, True):
                for treatment in (None, "ribbon", "rosette"):
                    with self.subTest(platform=p, family=family, treatment=treatment):
                        self.assertTrue(sc.is_steamcase_cover(self.console_cover(p, "c.png", family, treatment)))

    def test_forged_note_with_other_pixels_is_not_ours(self):
        fake = os.path.join(self.tmp, "fake.png")
        info = sc.PngInfo()
        info.add_text(sc.PLATFORM_CHUNK, "ps5")
        sc.Image.effect_noise(sc.SIZE, 80).convert("RGBA").save(fake, format="PNG", pnginfo=info)
        self.assertFalse(sc.is_steamcase_cover(fake))

    def test_wrong_or_garbled_platform_note_is_not_ours(self):
        ps5 = self.console_cover("ps5", "ps5.png")
        for note in ("ps4", "ps9", "PS5", "", "ps5 "):
            with self.subTest(note=note):
                self.assertFalse(sc.is_steamcase_cover(self.resave(ps5, **{sc.PLATFORM_CHUNK: note})))

    def test_console_cover_with_colour_or_theme_notes_is_not_ours(self):
        ps5 = self.console_cover("ps5", "ps5.png")
        for notes in ({sc.HUE_CHUNK: "0"}, {sc.TONE_CHUNK: "100 100"}, {sc.THEME_CHUNK: "christmas"}, {sc.DONE_CHUNK: "gold-case"}):
            with self.subTest(notes=notes):
                self.assertFalse(sc.is_steamcase_cover(self.resave(ps5, **notes)))

    def test_a_console_cover_is_not_recognised_as_another_case(self):
        ps5 = self.console_cover("ps5", "ps5.png")
        self.assertFalse(sc.is_steamcase_cover(self.resave(ps5, **{sc.PLATFORM_CHUNK: "xbox360"})))

    def test_steam_covers_are_still_recognised(self):
        out = os.path.join(self.tmp, "steam.png")
        sc.build_cover(self.noise(), out, sc.load_frame(), 0)
        self.assertTrue(sc.is_steamcase_cover(out))
        self.assertFalse(sc.is_steamcase_cover(self.resave(out, **{sc.PLATFORM_CHUNK: "ps5"})))        # a Steam cover with a console note is not either

    def test_reset_finds_console_covers(self):
        for appid, p in ((1, "ps5"), (2, "switch")):
            os.replace(self.console_cover(p, "tmp%d.png" % appid), os.path.join(self.grid, "%dp.png" % appid))
        sc.build_cover(self.noise(), os.path.join(self.grid, "3p.png"), sc.load_frame(), 0)
        with open(os.path.join(self.grid, "4p.png"), "wb") as f:
            f.write(b"not ours")
        self.assertEqual(sc.find_our_covers(self.steam), ["1p.png", "2p.png", "3p.png"])

    # ---- folder checks: console covers are neither another colour nor another theme ----
    def folder(self, **covers):
        """Fill self.covers: name -> ("steam", hue, sat, val, theme) or ("ps5", treatment); the file is Name_<n>.png."""
        for n, (name, spec) in enumerate(covers.items(), 1):
            out = os.path.join(self.covers, "%s_%d.png" % (name, n))
            if spec[0] == "steam":
                _, hue, sat, val, theme = spec
                sc.build_cover(self.noise(n), out, sc.load_frame(hue, sat=sat, val=val), hue, sat=sat, val=val, theme=theme)
            else:
                sc.build_cover(self.noise(n), out, sc.load_platform_frame(spec[0]), platform=spec[0], treatment=spec[1])

    def test_mixed_colours_and_themes_ignore_console_covers(self):
        self.folder(A=("steam", 0, 0, 30, "christmas"), B=("ps5", None))
        self.assertFalse(sc.mixed_cover_colours(self.covers))
        self.assertFalse(sc.mixed_cover_themes(self.covers))
        self.folder(C=("steam", 0, 100, 100, "christmas"))
        self.assertTrue(sc.mixed_cover_colours(self.covers))                     # two Steam covers in two colours still count

    def test_mixed_themes_still_see_two_steam_themes(self):
        self.folder(A=("steam", 0, 100, 100, "christmas"), B=("ps5", None), C=("steam", 0, 100, 100, None))
        self.assertTrue(sc.mixed_cover_themes(self.covers))

    def test_existing_colour_skips_console_covers(self):
        self.folder(A=("ps5", None))
        self.assertIsNone(sc.existing_cover_colour(self.covers))
        self.folder(B=("steam", 42, 100, 100, None))
        self.assertEqual(sc.existing_cover_colour(self.covers), (42, 100, 100))

    def test_other_look_and_theme_ignore_console_covers(self):
        self.folder(A=("ps5", "ribbon"))
        self.assertFalse(sc.covers_in_other_look(self.covers, 134, 50, 50))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, completed=set(), treatment=None, theme="christmas"))
        self.assertFalse(sc.covers_in_other_theme(self.covers, "christmas"))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 134, 50, 50))
        self.folder(B=("steam", 0, 100, 100, None))
        self.assertTrue(sc.covers_in_other_colour(self.covers, 134, 50, 50))     # a Steam cover still counts

    def test_full_marks_and_art_checks_ignore_console_covers(self):
        self.folder(A=("ps5", "ribbon"))
        self.assertFalse(sc.covers_with_marks(self.covers, "full"))
        self.assertFalse(sc.covers_with_other_art(self.covers, {1: self.noise()}))
        self.assertEqual(sc.covers_with_art(self.covers), set())

    def test_apply_command_accepts_a_folder_with_console_covers(self):
        import contextlib, io
        self.folder(A=("steam", 0, 0, 30, "christmas"), B=("ps5", None))
        args = sc.argparse.Namespace(covers=self.covers, steam_dir=self.steam, user=None, yes=True, close_steam=False)
        with mock.patch.object(sc, "steam_running", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            sc.cmd_apply(args)
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png", "2p.png"])


class ConsoleMake(StoreMocks):
    """make_covers(platforms=...): the manual flow puts chosen games in console cases; the natural flow leaves those covers alone."""

    def cv(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def test_a_dict_makes_only_the_listed_games_in_their_cases(self):
        res = sc.make_covers({1: None, 2: None, 3: None}, self.covers, platforms={1: "ps5", 2: "xbox360"})
        self.assertEqual((sc.cover_platform(self.cv(1)), sc.cover_platform(self.cv(2))), ("ps5", "xbox360"))
        self.assertFalse(os.path.exists(self.cv(3)))
        self.assertEqual((res["ok"], res["platforms"], sorted(res["files"])), (2, 2, sorted([self.cv(1), self.cv(2)])))

    def test_only_narrows_the_dict_further(self):
        sc.make_covers({1: None, 2: None}, self.covers, platforms={1: "ps5", 2: "ps4"}, only=[2])
        self.assertEqual(os.listdir(self.covers), ["Game_2_2.png"])

    def test_the_steam_case_choice_rebuilds_a_console_cover(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        res = sc.make_covers({1: None}, self.covers, platforms={1: None})
        self.assertIsNone(sc.cover_platform(self.cv(1)))
        self.assertEqual(sc.cover_colour(self.cv(1)), (0, 100, 100))
        self.assertEqual((res["ok"], res["platforms"]), (1, 0))

    def test_a_console_choice_rebuilds_a_steam_cover(self):
        sc.make_covers({1: None}, self.covers)
        sc.make_covers({1: None}, self.covers, platforms={1: "ps4"})
        self.assertEqual(sc.cover_platform(self.cv(1)), "ps4")

    def test_another_console_rebuilds_and_the_same_one_is_kept(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        before = os.stat(self.cv(1)).st_mtime_ns
        seen = []
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"}, progress=lambda d, t, a, n, st: seen.append(st))
        self.assertEqual((seen, os.stat(self.cv(1)).st_mtime_ns), (["exists"], before))
        sc.make_covers({1: None}, self.covers, platforms={1: "switch"})
        self.assertEqual(sc.cover_platform(self.cv(1)), "switch")

    def test_the_natural_run_keeps_console_covers_even_with_force(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        before = self.read(self.cv(1))
        for force in (False, True):
            with self.subTest(force=force):
                res = sc.make_covers({1: None, 2: None}, self.covers, hue=134, force=force)
                self.assertEqual(self.read(self.cv(1)), before)
                self.assertEqual((res["ok"], res["platforms"]), (2, 1))
                self.assertIn(self.cv(1), res["files"])
        self.assertEqual(sc.cover_colour(self.cv(2)), (134, 100, 100))

    def test_the_natural_run_does_not_want_to_replace_them(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        sc.make_covers({1: None}, self.covers, hue=134)
        self.assertFalse(sc.covers_in_other_look(self.covers, 134))

    def test_a_garbled_platform_note_is_rebuilt_by_the_natural_run(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        os.replace(self.resave(self.cv(1), **{sc.PLATFORM_CHUNK: "ps9"}), self.cv(1))
        sc.make_covers({1: None}, self.covers)
        self.assertIsNone(sc.cover_platform(self.cv(1)))

    def test_unknown_platform_is_refused_before_any_lookup(self):
        with mock.patch.object(sc, "store_items", side_effect=AssertionError("looked up")), self.assertRaises(ValueError):
            sc.make_covers({1: None}, self.covers, platforms={1: "ps9"})

    def test_gold_and_themes_are_refused_with_a_console_case(self):
        for kw in ({"treatment": "gold-case"}, {"treatment": "gold-border-rosette"}, {"theme": "christmas"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                sc.make_covers({1: None}, self.covers, platforms={1: "ps5"}, **kw)
        sc.make_covers({1: None}, self.covers, platforms={1: None}, theme="christmas", treatment="rosette", completed={1})     # Steam case only: allowed
        self.assertEqual(sc.cover_theme(self.cv(1)), "christmas")

    def test_marks_go_on_the_completed_games_only(self):
        sc.make_covers({1: None, 2: None}, self.covers, platforms={1: "ps5", 2: "ps5"}, completed={2}, treatment="ribbon")
        self.assertEqual((sc.cover_treatment(self.cv(1)), sc.cover_treatment(self.cv(2))), (None, "ribbon"))

    def test_the_family_corner_goes_on_family_games_only(self):
        sc.make_covers({1: None, 2: None}, self.covers, platforms={1: "ps5", 2: "ps5"}, family={2})
        def green(path):
            with sc.Image.open(path) as im:
                return sum(1 for px in im.convert("RGB").crop((sc.SIZE[0] - 207, 0, sc.SIZE[0], 207)).getdata() if all(abs(a - b) <= 8 for a, b in zip(px, sc.FAMILY_COLOR)))
        self.assertEqual(green(self.cv(1)), 0)
        self.assertGreater(green(self.cv(2)), 1000)

    def test_covers_in_other_case_counts_what_a_run_would_rebuild(self):
        sc.make_covers({1: None, 2: None, 3: None}, self.covers, platforms={1: "ps5", 2: None, 3: "ps4"})
        count = lambda platforms, **kw: sc.covers_in_other_case(self.covers, platforms, **kw)
        self.assertEqual(count({1: "ps5", 2: None, 3: "ps4"}), 0)
        self.assertEqual(count({1: "ps4", 2: None, 3: "ps4"}), 1)                 # another console
        self.assertEqual(count({2: "xbox360"}), 1)                               # a Steam cover goes into a console case
        self.assertEqual(count({1: None}), 1)                                    # and the other way
        self.assertEqual(count({9: "ps5"}), 0)                                   # no cover yet for that game
        self.assertEqual(count({2: None}, tone=(134, 100, 100)), 1)              # the Steam case in another colour
        self.assertEqual(count({1: "ps5"}, tone=(134, 100, 100)), 0)             # a console case has no colour

    def test_covers_in_other_case_sees_other_art(self):
        mine = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), (10, 160, 30)).save(mine, format="JPEG")
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"}, custom_art={1: mine})
        count = lambda **kw: sc.covers_in_other_case(self.covers, {1: "ps5"}, **kw)
        self.assertEqual((count(), count(custom_art={1: mine})), (0, 0))              # art not asked about is not compared
        self.assertEqual(count(custom_art={}), 1)                                     # the option turned off
        sc.make_covers({1: None}, self.covers, force=True, platforms={1: "ps5"})
        self.assertEqual(count(custom_art={1: mine}), 1)                              # the option turned on

    def test_covers_in_other_case_sees_other_marks(self):
        sc.make_covers({1: None, 2: None}, self.covers, platforms={1: "ps5", 2: "ps5"}, completed={1}, treatment="ribbon")
        count = lambda **kw: sc.covers_in_other_case(self.covers, {1: "ps5", 2: "ps5"}, **kw)
        self.assertEqual(count(completed={1}, treatment="ribbon"), 0)
        self.assertEqual(count(completed={1}, treatment="rosette"), 1)           # the ribbon goes
        self.assertEqual(count(completed=set(), treatment=None), 1)              # "no highlight": game 1 loses its marks
        self.assertEqual(count(completed={1, 2}, treatment="ribbon"), 1)         # game 2 gains them
        self.assertEqual(count(completed=None), 0)                               # no games page: covers keep their marks

    def test_a_garbled_note_counts_as_another_case(self):
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        os.replace(self.resave(self.cv(1), **{sc.PLATFORM_CHUNK: "ps9"}), self.cv(1))
        self.assertEqual(sc.covers_in_other_case(self.covers, {1: "ps5"}), 1)

    def test_a_gold_or_full_marks_cover_goes_into_a_console_case_keeping_its_marks(self):
        """Review finding 1: an old gold-case look made the console build fail (a console case has no gold)."""
        for old, want in (("gold-case", "ribbon"), ("gold-border", "ribbon"), ("gold-border-rosette", "rosette"), ("ribbon", "ribbon"), ("rosette", "rosette")):
            with self.subTest(old=old):
                shutil.rmtree(self.covers)
                sc.make_covers({1: None}, self.covers, completed={1}, treatment=old)
                self.assertEqual(sc.covers_in_other_case(self.covers, {1: "ps5"}), 1)
                res = sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
                self.assertEqual((res["ok"], res["failed"]), (1, []))
                self.assertEqual((sc.cover_platform(self.cv(1)), sc.cover_treatment(self.cv(1))), ("ps5", want))
                self.assertEqual(sc.covers_in_other_case(self.covers, {1: "ps5"}), 0)       # and a second run keeps it

    def test_existing_theme_skips_console_covers(self):
        """Review finding 2."""
        sc.make_covers({10: None}, self.covers, platforms={10: "ps5"})
        sc.make_covers({11: None}, self.covers, theme="christmas")
        self.assertEqual(sc.existing_cover_theme(self.covers), "christmas")

    def test_a_steam_case_choice_replaces_a_cover_made_from_own_art(self):
        """Review finding 5: Make passes no own art when the option is off, so such a cover is rebuilt and the user must be asked."""
        art = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), (10, 160, 30)).save(art, format="JPEG")
        sc.make_covers({1: None}, self.covers, custom_art={1: art})
        self.assertEqual(sc.covers_in_other_case(self.covers, {1: None}, custom_art={}), 1)
        sc.make_covers({1: None}, self.covers, platforms={1: None})
        self.assertEqual(sc.covers_in_other_case(self.covers, {1: None}, custom_art={}), 0)

    def test_a_cover_with_a_garbled_console_note_is_a_reason_to_ask_before_the_natural_run_rebuilds_it(self):
        """Review finding 6: the natural run rebuilds it, so covers_in_other_look must say so (it skipped it silently)."""
        sc.make_covers({1: None}, self.covers)
        self.assertFalse(sc.covers_in_other_look(self.covers, 0))
        os.replace(self.resave(self.cv(1), **{sc.PLATFORM_CHUNK: "ps9"}), self.cv(1))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0))
        sc.make_covers({1: None}, self.covers)
        self.assertFalse(sc.covers_in_other_look(self.covers, 0))

    def test_every_console_mask_covers_a_good_part_of_the_cover(self):
        """Review finding 9: the recognition threshold is a floor, not the real size: say what the real ones are."""
        for p in sc.PLATFORMS:
            for treatment in (None, "ribbon", "rosette"):
                for family in (False, True):
                    with self.subTest(platform=p, treatment=treatment, family=family):
                        mask = sc._platform_reference((p, treatment), family)[1]
                        self.assertGreaterEqual(mask.histogram()[255] / (sc.SIZE[0] * sc.SIZE[1]), 0.06)

    def test_a_listed_game_missing_from_the_library_is_ignored(self):
        res = sc.make_covers({1: None}, self.covers, platforms={1: "ps5", 99: "ps4"})
        self.assertEqual((res["ok"], os.listdir(self.covers)), (1, ["Game_1_1.png"]))


class SteamMarksMoved(Base):
    """The Steam case too: the family corner is at the top right and the rosette at the left under the banner (covers made before keep being recognised)."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")

    @staticmethod
    def changed(a, b):
        return sc.ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).convert("RGB").convert("L").point(lambda v: 255 if v else 0)

    def test_the_family_corner_is_top_right(self):
        box = self.changed(sc.load_frame(0), sc.load_frame(0, True)).getbbox()
        self.assertTrue(box[0] >= sc.SIZE[0] - 207 and box[2] <= sc.SIZE[0] and box[3] <= 207, box)

    def test_the_old_corner_is_still_known_at_the_top_left(self):
        box = self.changed(sc.load_frame(0), sc.load_frame(0, True, legacy_corner=True)).getbbox()
        self.assertTrue(box[0] >= 0 and box[2] <= 207 and box[3] <= 207, box)

    def test_the_rosette_is_left_below_the_banner(self):
        box = self.changed(sc.preview_cover(), sc.preview_cover(treatment="rosette")).crop((0, 0, sc.SIZE[0], 450)).getbbox()
        self.assertAlmostEqual(box[0], sc.WINDOW[0] + sc.MARKS_GAP, delta=1)
        self.assertAlmostEqual(box[1], sc.WINDOW[1] + sc.MARKS_GAP, delta=1)

    def test_the_ribbon_has_the_width_of_the_console_cases(self):
        box = self.changed(sc.preview_cover(), sc.preview_cover(treatment="ribbon")).crop((0, 450, sc.SIZE[0], sc.SIZE[1])).getbbox()
        self.assertAlmostEqual(box[2] - box[0], sc.RIBBON_WIDTH, delta=2)
        self.assertAlmostEqual((box[0] + box[2]) / 2, (sc.WINDOW[0] + sc.WINDOW[2]) / 2, delta=2)
        self.assertAlmostEqual(box[3] + 450, sc.WINDOW[3] - sc.RIBBON_GAP, delta=2)

    def legacy(self, drop=(), **kw):
        """A cover as the version before this one made it: the corner on the left, the rosette at the top right. Its notes are those of a cover made now."""
        now = os.path.join(self.tmp, "now.png")
        hue, sat, val = kw.get("colour", (0, 100, 100))
        sc.build_cover(sc.DEFAULT_ART, now, sc.load_frame(hue, kw.get("family", False), sat=sat, val=val), hue, sat=sat, val=val, treatment=kw.get("treatment"))
        with sc.Image.open(now) as im:
            info = dict(im.info)
        old = sc.finish_treatment(sc._compose(sc.Image.open(sc.DEFAULT_ART).convert("RGBA"), sc.load_frame(hue, kw.get("family", False), sat=sat, val=val, legacy_corner=True)),
                                  kw.get("treatment"))
        out = os.path.join(self.tmp, "old.png")
        from PIL.PngImagePlugin import PngInfo
        meta = PngInfo()
        for k, v in info.items():
            if isinstance(v, str) and k not in drop:
                meta.add_text(k, v)
        old.save(out, pnginfo=meta)
        return out

    def test_covers_made_before_are_still_ours(self):
        for kw in ({}, {"family": True}, {"treatment": "ribbon"}, {"treatment": "rosette", "family": True}, {"treatment": "gold-border"},
                   {"colour": (134, 60, 80), "family": True}, {"colour": (134, 60, 80), "treatment": "gold-border-rosette"}):
            with self.subTest(**kw):
                self.assertTrue(sc.is_steamcase_cover(self.legacy(**kw)))

    def test_an_old_cover_without_its_treatment_note_is_not_ours(self):
        """The old rosette reached into the banner, so the frame no longer matched (the rosette of today sits over the art, which no check can see)."""
        self.assertTrue(sc.is_steamcase_cover(self.legacy(treatment="ribbon")))
        self.assertFalse(sc.is_steamcase_cover(self.legacy(drop=(sc.DONE_CHUNK,), treatment="ribbon")))

    def test_covers_made_now_are_ours(self):
        for kw in ({}, {"family": True}, {"treatment": "ribbon"}, {"treatment": "rosette", "family": True}):
            with self.subTest(**kw):
                out = os.path.join(self.tmp, "now.png")
                sc.build_cover(sc.DEFAULT_ART, out, sc.load_frame(0, kw.get("family", False)), 0, treatment=kw.get("treatment"))
                self.assertTrue(sc.is_steamcase_cover(out))


class HandMadeCovers(Base):
    """A cover made by hand (a console case or a group's Steam case) carries a group note, and every check of the usual flow ignores it."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.art = os.path.join(self.tmp, "art.png")
        sc.Image.new("RGB", (60, 90), (30, 200, 30)).save(self.art)

    def make(self, name, hue=0, **kw):
        out = os.path.join(self.covers, name)
        platform = kw.get("platform")
        frame = sc.load_platform_frame(platform) if platform else sc.load_frame(hue)
        sc.build_cover(self.art, out, frame, hue, **kw)
        return out

    def with_note(self, src, key, value):
        """A copy of the cover with one PNG note set (value None: removed)."""
        from PIL.PngImagePlugin import PngInfo
        out = os.path.join(self.tmp, "n_%s.png" % key)
        meta = PngInfo()
        with sc.Image.open(src) as im:
            for k, v in im.info.items():
                if isinstance(v, str) and k != key:
                    meta.add_text(k, v)
            if value is not None:
                meta.add_text(key, value)
            im.save(out, pnginfo=meta)
        return out

    def test_a_group_note_is_written_and_read_back(self):
        path = self.make("a.png", group="g1")
        self.assertEqual(sc.cover_group(path), "g1")
        self.assertIsNone(sc.cover_group(self.make("b.png")))

    def test_a_damaged_group_note_reads_as_false(self):
        path = self.make("a.png", group="g1")
        for bad in ("", "G1", "g 1", "g1;", "x" * 13, "é"):
            with self.subTest(bad=bad):
                self.assertIs(sc.cover_group(self.with_note(path, sc.GROUP_CHUNK, bad)), False)
        self.assertIs(sc.cover_group(os.path.join(self.tmp, "missing.png")), False)

    def test_a_bad_group_id_is_refused_before_anything_is_written(self):
        for bad in ("", "G1", "g 1", "x" * 13, 5, "a/b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.make("a.png", group=bad)
        self.assertFalse(os.path.exists(os.path.join(self.covers, "a.png")))

    def test_by_hand_means_a_console_case_or_a_group_note(self):
        self.assertIsNone(sc.cover_by_hand(self.make("plain.png")))
        self.assertIs(sc.cover_by_hand(self.make("group.png", group="g1")), True)
        self.assertIs(sc.cover_by_hand(self.make("console.png", platform="ps5")), True)
        self.assertIs(sc.cover_by_hand(self.make("both.png", platform="ps5", group="g1")), True)
        self.assertIs(sc.cover_by_hand(self.with_note(self.make("g2.png", group="g1"), sc.GROUP_CHUNK, "BAD")), False)       # a damaged note: the cover is rebuilt
        self.assertIs(sc.cover_by_hand(os.path.join(self.tmp, "missing.png")), False)

    def test_covers_by_hand_are_ours(self):
        for kw in ({"group": "g1"}, {"group": "g1", "hue": 134}, {"group": "g1", "treatment": "ribbon"}, {"group": "g1", "treatment": "rosette", "hue": 134},
                   {"group": "g1", "platform": "ps5"}, {"group": "g1", "platform": "switch", "treatment": "ribbon"}):
            with self.subTest(**kw):
                self.assertTrue(sc.is_steamcase_cover(self.make("c.png", **kw)))

    def test_a_group_note_never_goes_with_a_theme_or_a_damaged_note(self):
        themed = self.make("t.png", theme="christmas")
        self.assertFalse(sc.is_steamcase_cover(self.with_note(themed, sc.GROUP_CHUNK, "g1")))
        grouped = self.make("g.png", group="g1")
        self.assertFalse(sc.is_steamcase_cover(self.with_note(grouped, sc.GROUP_CHUNK, "NOPE")))
        console = self.make("c.png", platform="ps5", group="g1")
        self.assertFalse(sc.is_steamcase_cover(self.with_note(console, sc.GROUP_CHUNK, "NOPE")))
        self.assertFalse(sc.is_steamcase_cover(self.with_note(grouped, sc.THEME_CHUNK, "christmas")))

    def folder(self):
        """A usual library (two blue christmas covers) and, sorting before them, covers by hand: a red one with full marks and art of the user's, and a console one."""
        self.make("Plain_1_1.png", theme="christmas")
        self.make("Plain_2_2.png", theme="christmas")
        self.make("A_3_3.png", hue=134, treatment="ribbon", group="g1", from_art="custom fedcba9876543210")
        self.make("A_4_4.png", platform="ps5", group="g1")

    def test_the_checks_of_the_usual_flow_ignore_covers_by_hand(self):
        self.folder()
        self.assertEqual(sc.existing_cover_colour(self.covers), (0, 100, 100))                       # not that of the first cover by name, which is red
        self.assertFalse(sc.mixed_cover_colours(self.covers))
        self.assertFalse(sc.mixed_cover_themes(self.covers))
        self.assertEqual(sc.existing_cover_theme(self.covers), "christmas")
        self.assertFalse(sc.covers_in_other_theme(self.covers, "christmas"))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 0))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0))
        self.assertFalse(sc.covers_with_marks(self.covers, "full"))
        self.assertFalse(sc.covers_with_other_art(self.covers, {}))                                   # the art of a cover by hand is not in question
        self.assertEqual(sc.covers_with_art(self.covers), set())

    def test_forgetting_a_group_takes_the_note_off_and_keeps_the_picture(self):
        steam = self.make("Steam_1_1.png", hue=134, treatment="ribbon", group="g1")
        console = self.make("Console_2_2.png", platform="ps5", group="g1")
        other = self.make("Other_3_3.png", hue=134, group="g2")
        plain = self.make("Plain_4_4.png")
        before = {p: sc.Image.open(p).convert("RGBA").tobytes() for p in (steam, console, other, plain)}
        self.assertEqual(sc.forget_group(self.covers, {1, 2, 4, 99}), 2)                  # only covers with a note; the plain one and the missing game are not counted
        self.assertEqual([sc.cover_group(p) for p in (steam, console, other, plain)], [None, None, "g2", None])
        self.assertEqual({p: sc.Image.open(p).convert("RGBA").tobytes() for p in before}, before)       # the pictures are the same
        self.assertEqual((sc.cover_colour(steam), sc.cover_treatment(steam), sc.cover_platform(console)), ((134, 100, 100), "ribbon", "ps5"))
        self.assertTrue(sc.is_steamcase_cover(steam) and sc.is_steamcase_cover(console))
        self.assertIsNone(sc.cover_by_hand(steam))                                        # a Steam cover is a usual cover again
        self.assertTrue(sc.cover_by_hand(console))                                        # a console cover still is by hand: its case is its note
        self.assertEqual(os.listdir(self.covers).count("Steam_1_1.png"), 1)
        self.assertEqual([n for n in os.listdir(self.covers) if n.startswith(".")], [])    # no temporary file is left

    def test_forgetting_leaves_damaged_and_linked_files_alone(self):
        good = self.make("Good_1_1.png", group="g1")
        bad = os.path.join(self.covers, "Bad_2_2.png")
        with open(bad, "wb") as f:
            f.write(b"not a png")
        link = os.path.join(self.covers, "Link_3_3.png")
        os.symlink(good, link)
        self.assertEqual(sc.forget_group(self.covers, {1, 2, 3}), 1)
        self.assertEqual(open(bad, "rb").read(), b"not a png")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(sc.forget_group(os.path.join(self.tmp, "no folder"), {1}), 0)

    def test_a_damaged_group_note_makes_the_usual_flow_ask(self):
        self.folder()
        self.with_note(os.path.join(self.covers, "A_3_3.png"), sc.GROUP_CHUNK, "BAD")
        shutil.copy(os.path.join(self.tmp, "n_%s.png" % sc.GROUP_CHUNK), os.path.join(self.covers, "A_3_3.png"))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0))                                     # as for a damaged console note: the cover is rebuilt


class GroupMake(StoreMocks):
    """make_covers(tones=, groups=, repaint=): games of a group get their own colour, and the usual flow leaves them alone unless asked."""
    RED, GREEN = (134, 100, 100), (84, 100, 100)

    def cv(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def make(self, games, platforms, tones=None, groups=None, **kw):
        return sc.make_covers({i: None for i in games}, self.covers, platforms=platforms, tones=tones, groups=groups, **kw)

    def test_a_steam_case_game_gets_its_own_colour_and_group_note(self):
        res = self.make([1, 2, 3], {1: None, 2: None, 3: "ps5"}, tones={1: self.RED, 2: self.GREEN}, groups={1: "red", 2: "green", 3: "ps"})
        self.assertEqual((sc.cover_colour(self.cv(1)), sc.cover_colour(self.cv(2))), (self.RED, self.GREEN))
        self.assertEqual([sc.cover_group(self.cv(i)) for i in (1, 2, 3)], ["red", "green", "ps"])
        self.assertEqual((res["ok"], res["platforms"]), (3, 1))
        for i in (1, 2, 3):
            self.assertTrue(sc.is_steamcase_cover(self.cv(i)), i)

    def test_a_game_without_a_tone_gets_the_colour_of_the_run(self):
        self.make([1], {1: None}, tones={}, groups={1: "g"}, hue=84)
        self.assertEqual(sc.cover_colour(self.cv(1)), (84, 100, 100))

    def test_a_gold_group_is_a_gold_case_without_marks_and_marks_only_where_completed(self):
        gold = (sc.GOLD_HUE, 100, 100)
        self.make([1, 2], {1: None, 2: None}, tones={1: gold, 2: gold}, groups={1: "gold", 2: "gold"}, completed={2}, treatment="ribbon")
        self.assertEqual(sc.cover_colour(self.cv(1)), gold)
        self.assertIsNone(sc.cover_treatment(self.cv(1)))                        # not at 100%: no marks, whatever the group
        self.assertEqual(sc.cover_treatment(self.cv(2)), "ribbon")
        self.assertEqual(sc.cover_colour(self.cv(2)), gold)

    def test_without_a_games_page_no_game_of_a_group_gets_marks(self):
        self.make([1], {1: None}, tones={1: self.RED}, groups={1: "r"}, completed=None, treatment="ribbon")
        self.assertIsNone(sc.cover_treatment(self.cv(1)))

    def test_a_same_cover_is_kept_and_another_colour_or_group_rebuilds(self):
        self.make([1], {1: None}, tones={1: self.RED}, groups={1: "r"})
        before = os.stat(self.cv(1)).st_mtime_ns
        seen = []
        self.make([1], {1: None}, tones={1: self.RED}, groups={1: "r"}, progress=lambda d, t, a, n, st: seen.append(st))
        self.assertEqual((seen, os.stat(self.cv(1)).st_mtime_ns), (["exists"], before))
        self.make([1], {1: None}, tones={1: self.GREEN}, groups={1: "r"})
        self.assertEqual(sc.cover_colour(self.cv(1)), self.GREEN)
        self.make([1], {1: None}, tones={1: self.GREEN}, groups={1: "other"})
        self.assertEqual(sc.cover_group(self.cv(1)), "other")
        self.make([1], {1: None}, tones={1: self.GREEN})                          # no group any more: the note goes
        self.assertIsNone(sc.cover_group(self.cv(1)))

    def test_the_usual_flow_leaves_covers_by_hand_alone_even_with_force(self):
        self.make([1, 2], {1: None, 2: "ps5"}, tones={1: self.RED}, groups={1: "r", 2: "p"})
        before = {i: open(self.cv(i), "rb").read() for i in (1, 2)}
        res = sc.make_covers({1: None, 2: None, 3: None}, self.covers, force=True, hue=84)
        self.assertEqual({i: open(self.cv(i), "rb").read() for i in (1, 2)}, before)
        self.assertEqual((res["ok"], res["platforms"]), (3, 2))
        self.assertEqual(sc.cover_colour(self.cv(3)), (84, 100, 100))

    def test_repaint_hands_the_covers_back_to_the_usual_flow(self):
        self.make([1, 2, 3], {1: None, 2: "ps5", 3: None}, tones={1: self.RED, 3: self.RED}, groups={1: "r", 2: "p", 3: "r"})
        res = sc.make_covers({1: None, 2: None, 3: None}, self.covers, hue=84, repaint={1, 2})
        self.assertEqual([sc.cover_group(self.cv(i)) for i in (1, 2, 3)], [None, None, "r"])
        self.assertEqual((sc.cover_platform(self.cv(2)), sc.cover_colour(self.cv(1)), sc.cover_colour(self.cv(3))), (None, (84, 100, 100), self.RED))
        self.assertEqual(res["platforms"], 1)                                      # the one left alone

    def test_a_damaged_note_is_rebuilt_by_the_usual_flow(self):
        self.make([1], {1: None}, tones={1: self.RED}, groups={1: "r"})
        from PIL.PngImagePlugin import PngInfo
        meta = PngInfo()
        with sc.Image.open(self.cv(1)) as im:
            for k, v in im.info.items():
                if isinstance(v, str) and k != sc.GROUP_CHUNK:
                    meta.add_text(k, v)
            meta.add_text(sc.GROUP_CHUNK, "BAD NOTE")
            im.save(self.cv(1), pnginfo=meta)
        sc.make_covers({1: None}, self.covers, hue=84)
        self.assertEqual((sc.cover_group(self.cv(1)), sc.cover_colour(self.cv(1))), (None, (84, 100, 100)))

    def test_bad_input_is_refused_before_any_lookup(self):
        with mock.patch.object(sc, "store_items", side_effect=AssertionError("looked up")):
            for kw in ({"tones": {1: (360, 100, 100)}}, {"tones": {1: (0, 101, 100)}}, {"tones": {1: (0, 100)}}, {"tones": {1: "red"}}, {"tones": {"a": (0, 1, 1)}},
                       {"groups": {1: "BAD"}}, {"groups": {1: 5}}, {"groups": {"x": "a"}}, {"groups": {1: "g"}, "theme": "christmas", "treatment": "rosette"},
                       {"groups": {1: "g"}, "treatment": "gold-case"}, {"tones": {1: (0, 100, 100)}, "treatment": "gold-border"}, {"repaint": 5}):
                with self.subTest(**kw), self.assertRaises(ValueError):
                    sc.make_covers({1: None}, self.covers, platforms={1: None}, **kw)

    def test_the_reason_counts_a_game_with_another_colour_or_group(self):
        self.make([1, 2], {1: None, 2: None}, tones={1: self.RED, 2: self.RED}, groups={1: "r", 2: "r"})
        count = lambda tones, groups, **kw: sc.covers_in_other_case(self.covers, {1: None, 2: None}, tones=tones, groups=groups, **kw)
        self.assertEqual(count({1: self.RED, 2: self.RED}, {1: "r", 2: "r"}), 0)
        self.assertEqual(count({1: self.GREEN, 2: self.RED}, {1: "r", 2: "r"}), 1)
        self.assertEqual(count({1: self.RED, 2: self.RED}, {1: "r", 2: "other"}), 1)
        self.assertEqual(count({1: self.RED, 2: self.RED}, None), 2)                # no group wanted: both are rebuilt

    def test_a_group_of_the_usual_flow_reason_lists_the_names(self):
        from qtui import reasons
        self.assertIsNone(reasons.group_repaint_reason([]))
        title, text = reasons.group_repaint_reason([{"name": "Red Steam Cases", "games": [1, 2, 3]}, {"name": "PS5", "games": [4]}])
        self.assertIn("Red Steam Cases", text)
        self.assertIn("3 games", text)
        self.assertIn("PS5", text)
        self.assertIn("1 game", text)
        self.assertIn("deleted", text)


def use_cases_dir(test, mutate=None):
    """Point the engine at a copy of assets/cases (changed by `mutate(data)` on the parsed cases.json), with every cache that depends on it cleared before and after."""
    d = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, d, True)
    shutil.copytree(sc.CASES_DIR, d, dirs_exist_ok=True)
    if mutate:
        path = os.path.join(d, "cases.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mutate(data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    clear = lambda: (sc._case_windows.cache_clear(), sc._platform_reference.cache_clear())
    patcher = mock.patch.object(sc, "CASES_DIR", d)
    patcher.start()
    test.addCleanup(patcher.stop)
    clear()
    test.addCleanup(clear)
    return d


class CasesJsonIsChecked(Base):
    """A hand-made cases.json that is a little off is refused with one clear sentence, not a raw error from deep inside."""
    BAD = {
        "no window": lambda d: d["ps5"].pop("window"),
        "a window that is not four numbers": lambda d: d["ps5"].update(window=[0, 0, 600]),
        "a window with text in it": lambda d: d["ps5"].update(window=[0, "a", 600, 900]),
        "a window outside the picture": lambda d: d["ps5"].update(window=[0, 100, 700, 900]),
        "a window that is upside down": lambda d: d["ps5"].update(window=[100, 100, 50, 900]),
        "a window that is too small": lambda d: d["ps5"].update(window=[0, 0, 300, 300]),
        "an overlay that is not four numbers": lambda d: d["switch"].update(overlay=[0, 0, 100]),
        "an overlay outside the picture": lambda d: d["switch"].update(overlay=[0, 0, 700, 100]),
        "a missing platform": lambda d: d.pop("xbox360"),
    }

    def test_every_malformed_file_is_refused_in_words(self):
        for what, mutate in self.BAD.items():
            with self.subTest(what):
                use_cases_dir(self, mutate)
                for call in (lambda: sc.platform_window("ps5"), lambda: sc.load_platform_frame("ps5", True), lambda: sc.platform_marks_dy("ps5")):
                    with self.assertRaises(sc.SteamcaseError) as caught:
                        call()
                    self.assertIn("cases.json", str(caught.exception))

    def test_the_shipped_file_and_one_with_optional_parts_left_out_are_accepted(self):
        use_cases_dir(self)
        self.assertEqual(sc.platform_window("ps5")[0] >= 0, True)
        use_cases_dir(self, lambda d: d["switch"].pop("overlay"))
        self.assertIsNone(sc.platform_overlay("switch"))

    def test_the_self_test_reports_a_bad_file_instead_of_raising(self):
        from qtui import selfcheck
        use_cases_dir(self, lambda d: d["ps5"].update(overlay=[0, 0, 700, 100]))
        problems = selfcheck.engine_problems()
        self.assertTrue(any("cases.json" in p for p in problems), problems)

    def test_the_self_test_builds_every_case_with_options_on(self):
        from qtui import selfcheck
        calls = []
        real = sc.build_cover
        with mock.patch.object(sc, "build_cover", lambda *a, **kw: calls.append(kw.get("platform")) or real(*a, **kw)):
            self.assertEqual(selfcheck.engine_problems(), [])
        self.assertEqual(sorted({p for p in calls if p}), sorted(sc.PLATFORMS + (sc.CUSTOM,)))      # every case at least once, and the user's own (the group check builds one more)


class SelfCheckConsoleCases(Base):
    """The packaged app's self-test also builds and recognises a console cover."""

    def test_a_missing_case_is_reported(self):
        from qtui import selfcheck
        sc._case_windows.cache_clear()
        self.addCleanup(sc._case_windows.cache_clear)
        with mock.patch.object(sc, "CASES_DIR", os.path.join(self.tmp, "no-cases")):
            problems = selfcheck.engine_problems()
        self.assertTrue(any("console case" in p for p in problems), problems)

    def test_a_good_bundle_has_no_problems(self):
        from qtui import selfcheck
        self.assertEqual(selfcheck.engine_problems(), [])


class SelfCheckGroups(Base):
    """The packaged app's self-test also builds a cover made by hand (in a group, in a colour) and recognises it, and refuses a damaged note."""

    def test_a_good_bundle_builds_and_recognises_a_group_cover(self):
        from qtui import selfcheck
        seen = []
        real = sc.build_cover
        with mock.patch.object(sc, "build_cover", lambda *a, **kw: seen.append(kw.get("group")) or real(*a, **kw)):
            self.assertEqual(selfcheck.engine_problems(), [])
        self.assertIn("selfcheck", [g for g in seen if g])

    def test_a_group_cover_that_is_not_recognised_is_reported(self):
        from qtui import selfcheck
        real = sc.is_steamcase_cover
        with mock.patch.object(sc, "is_steamcase_cover", lambda path: False if sc.cover_group(path) else real(path)):
            problems = selfcheck.engine_problems()
        self.assertTrue(any("group" in p for p in problems), problems)


class ConsoleCaseCredits(unittest.TestCase):
    """The marks on the console cases belong to their owners, and the frames are the project's own artwork: docs/THIRD_PARTY.md says both."""

    def text(self):
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            return f.read()

    def test_it_names_the_marks_their_owners_and_that_there_is_no_affiliation(self):
        text = self.text()
        for needle in ("PlayStation", "Sony Interactive Entertainment", "Xbox", "Microsoft", "Nintendo", "assets/cases"):
            self.assertIn(needle, text)
        self.assertRegex(text, r"(?i)not affiliated with[^.]*Sony[^.]*Nintendo|not affiliated with[^.]*Nintendo[^.]*Sony")

    def test_it_says_where_the_frames_come_from(self):
        """The frames are the project's own artwork; no credit to a logo file that is no longer in the repository."""
        text = self.text()
        self.assertIn("own artwork", text)
        self.assertNotIn("build_cases", text)
        self.assertNotIn("not the official wordmark", text)

    def test_it_says_the_logos_are_not_ours_and_came_from_an_icon_website(self):
        text = self.text()
        self.assertRegex(text, r"(?i)logos[^.]*downloaded from a (public )?website of icons")
        self.assertRegex(text, r"(?i)not (the )?(intellectual )?property of this project|not our intellectual property")

    def test_the_drawing_tool_and_its_logo_files_are_gone(self):
        self.assertFalse(os.path.exists(os.path.join(sc.HERE, "tools", "build_cases.py")))
        self.assertFalse(os.path.exists(os.path.join(sc.HERE, "tools", "src", "cases")))


class ListGames(Base):
    """list_games tells the caller when the store could not be asked, so a window can say "offline" instead of showing a short list."""

    def test_errors_of_the_store_lookup_are_handed_back(self):
        errs = []
        with mock.patch.object(sc, "http_get", side_effect=OSError("offline")):
            rows = sc.list_games({1: "Installed", 2: None}, errors=errs)
        self.assertEqual(rows, [(1, "Installed")])                       # the unnamed game cannot be listed without the store
        self.assertEqual([str(e) for e in errs], ["offline"])

    def test_no_errors_when_the_store_answers(self):
        errs = []
        body = json.dumps({"response": {"store_items": [{"type": 0, "name": "Two"}]}}).encode()
        with mock.patch.object(sc, "http_get", return_value=body):
            rows = sc.list_games({2: None}, errors=errs)
        self.assertEqual((rows, errs), ([(2, "Two")], []))

    def test_errors_are_optional(self):
        with mock.patch.object(sc, "http_get", side_effect=OSError("offline")):
            self.assertEqual(sc.list_games({1: "Installed"}), [(1, "Installed")])


if __name__ == "__main__":
    unittest.main()


class CustomCase(Base):
    """The user's own case: one 600 x 900 PNG with a see-through art window, checked, kept in the covers folder and measured like a console case."""

    def setUp(self):
        super().setUp()
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.addCleanup(sc.use_custom_case, None)

    def case_file(self, name="mine.png", size=sc.SIZE, window=(20, 100, 580, 880), tab=None, colour=(30, 60, 200, 255)):
        im = sc.Image.new("RGBA", size, colour)
        if window:
            im.paste((0, 0, 0, 0), window)
        if tab:
            im.paste((255, 0, 0, 255), tab)
        path = os.path.join(self.tmp, name)
        im.save(path, format="PNG")
        return path

    def test_a_good_file_gives_its_window_and_tab(self):
        info = sc.check_case_file(self.case_file(tab=(30, 110, 70, 150)))
        self.assertEqual(info, {"window": [20, 100, 580, 880], "overlay": [30, 110, 70, 150]})
        self.assertEqual(sc.check_case_file(self.case_file("b.png")), {"window": [20, 100, 580, 880]})

    def test_a_frosted_glass_frame_that_is_never_fully_opaque_is_a_case(self):
        info = sc.check_case_file(self.case_file(colour=(240, 240, 240, 200)))
        self.assertEqual(info, {"window": [20, 100, 580, 880]})

    def test_a_soft_glow_at_the_edge_of_the_window_is_part_of_the_window(self):
        im = sc.Image.new("RGBA", sc.SIZE, (30, 60, 200, 255))
        im.paste((255, 255, 255, 100), (20, 100, 580, 880))
        im.paste((0, 0, 0, 0), (80, 160, 520, 820))
        path = os.path.join(self.tmp, "glow.png")
        im.save(path)
        self.assertEqual(sc.check_case_file(path), {"window": [20, 100, 580, 880]})

    def test_the_window_runs_up_to_the_sharp_edge_under_a_glass_glow(self):
        im = sc.Image.new("RGBA", sc.SIZE, (240, 240, 240, 60))       # a glass case: a rim of faint frame, then a pocket whose frame fades out towards the art
        draw = sc.ImageDraw.Draw(im)
        for d in range(40):
            draw.rectangle((20 + d, 100 + d, 579 - d, 879 - d), fill=(240, 240, 240, 220 - d * 3), outline=None)
        path = os.path.join(self.tmp, "glass.png")
        im.save(path)
        self.assertEqual(sc.check_case_file(path), {"window": [20, 100, 580, 880]})

    def test_a_frame_of_faint_shadow_is_still_not_a_case(self):
        with self.assertRaises(sc.SteamcaseError):
            sc.check_case_file(self.case_file(colour=(0, 0, 0, 40)))

    def test_transparent_corners_and_margins_outside_the_case_are_not_the_window(self):
        im = sc.Image.new("RGBA", sc.SIZE, (30, 60, 200, 255))
        im.paste((0, 0, 0, 0), (40, 120, 560, 860))
        for box in ((0, 0, 30, 30), (570, 0, 600, 30), (0, 870, 30, 900), (570, 870, 600, 900), (0, 300, 8, 600)):     # rounded outer corners and a see-through margin
            im.paste((0, 0, 0, 0), box)
        path = os.path.join(self.tmp, "round.png")
        im.save(path)
        self.assertEqual(sc.check_case_file(path), {"window": [40, 120, 560, 860]})

    def test_a_rounded_window_has_no_tab(self):
        im = sc.Image.new("RGBA", sc.SIZE, (30, 60, 200, 255))
        sc.ImageDraw.Draw(im).rounded_rectangle((20, 100, 579, 879), radius=120, fill=(0, 0, 0, 0))
        path = os.path.join(self.tmp, "roundwin.png")
        im.save(path)
        info = sc.check_case_file(path)
        self.assertEqual(info["window"], [20, 100, 580, 880])
        self.assertNotIn("overlay", info)

    def test_a_shadow_inside_the_window_is_not_a_tab(self):
        path = self.case_file(tab=None)
        im = sc.Image.open(path).convert("RGBA")
        im.paste((0, 0, 0, 40), (20, 100, 580, 108))                         # a faint strip along the top edge
        im.paste((0, 0, 0, 40), (20, 100, 28, 880))                          # and along the left edge: an L, mostly empty
        im.save(path)
        self.assertNotIn("overlay", sc.check_case_file(path))

    def test_the_measure_agrees_with_every_console_case(self):
        for p in sc.PLATFORMS:
            with self.subTest(platform=p):
                self.assertEqual(sc.check_case_file(os.path.join(sc.CASES_DIR, p + ".png")), sc._case_windows()[p])

    def test_a_case_with_no_frame_is_refused(self):
        for name, window in (("all.png", (0, 0, 600, 900)), ("thin.png", (3, 3, 597, 897))):
            with self.subTest(name):
                with self.assertRaises(sc.SteamcaseError) as ctx:
                    sc.check_case_file(self.case_file(name, window=window))
                self.assertIn("frame", str(ctx.exception))

    def test_a_picture_without_transparency_is_refused_in_one_sentence(self):
        path = os.path.join(self.tmp, "grey.png")
        sc.Image.new("I;16", sc.SIZE, 3000).save(path)
        with self.assertRaises(sc.SteamcaseError) as ctx:
            sc.check_case_file(path)
        self.assertIn("window", str(ctx.exception))

    def test_a_folder_that_cannot_be_written_is_one_sentence_and_keeps_the_slot(self):
        first = sc.save_custom_case(self.case_file(), self.covers)
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w") as f:
            f.write("a file where a folder should be")
        with self.assertRaises(sc.SteamcaseError):
            sc.save_custom_case(self.case_file("other.png", colour=(200, 30, 30, 255)), os.path.join(blocker, "covers"))
        with mock.patch.object(sc, "_replace", side_effect=PermissionError("busy")), self.assertRaises(sc.SteamcaseError):
            sc.save_custom_case(self.case_file("other.png", colour=(200, 30, 30, 255)), self.covers)
        self.assertEqual(sc.custom_case_digest(), first)                        # the slot only changes once the copy is on disk
        with open(os.path.join(self.covers, sc.CUSTOM_FILE), "rb") as f:
            self.assertEqual(sc.hashlib.sha256(f.read()).hexdigest()[:16], first)
        self.assertEqual([n for n in os.listdir(self.covers) if n != sc.CUSTOM_FILE], [])       # no temp file left behind

    def test_refused_files(self):
        big = os.path.join(self.tmp, "big.png")
        with open(big, "wb") as f:
            f.write(b"\0" * (sc.caseframe.MAX_FILE + 1))
        text = os.path.join(self.tmp, "text.png")
        with open(text, "w") as f:
            f.write("not a picture")
        good = self.case_file("good.png")
        with open(good, "rb") as f:
            cut = os.path.join(self.tmp, "cut.png")
            with open(cut, "wb") as g:
                g.write(f.read()[:200])
        link = os.path.join(self.tmp, "link.png")
        os.symlink(good, link)
        for name, path, word in (("no window", self.case_file("a.png", window=None), "window"),
                                 ("wrong size", self.case_file("b.png", size=(601, 900)), "600 x 900"),
                                 ("double size", self.case_file("c.png", size=(1200, 1800)), "600 x 900"),
                                 ("small window", self.case_file("d.png", window=(20, 100, 320, 880)), "400"),
                                 ("a link", link, "link"), ("too big", big, "big"), ("text", text, "PNG"), ("cut short", cut, "PNG"),
                                 ("missing", os.path.join(self.tmp, "none.png"), "PNG")):
            with self.subTest(name):
                with self.assertRaises(sc.SteamcaseError) as ctx:
                    sc.check_case_file(path)
                self.assertIn(word, str(ctx.exception))

    def test_save_keeps_a_copy_and_replacing_changes_the_digest(self):
        first = sc.save_custom_case(self.case_file(), self.covers)
        self.assertRegex(first, r"[0-9a-f]{16}")
        self.assertEqual(sc.custom_case_digest(), first)
        self.assertTrue(os.path.isfile(os.path.join(self.covers, sc.CUSTOM_FILE)))
        second = sc.save_custom_case(self.case_file("other.png", colour=(200, 30, 30, 255)), self.covers)
        self.assertNotEqual(first, second)
        self.assertEqual(sc.custom_case_digest(), second)

    def test_a_refused_pick_keeps_the_old_slot(self):
        first = sc.save_custom_case(self.case_file(), self.covers)
        with self.assertRaises(sc.SteamcaseError):
            sc.save_custom_case(self.case_file("bad.png", window=None), self.covers)
        self.assertEqual(sc.custom_case_digest(), first)
        sc.use_custom_case(None)
        self.assertEqual(sc.use_custom_case(self.covers), first)                       # the kept copy is the old, good one

    def test_use_custom_case_without_a_copy_is_none_and_a_broken_copy_is_a_sentence(self):
        self.assertIsNone(sc.use_custom_case(self.covers))
        with open(os.path.join(self.covers, sc.CUSTOM_FILE), "w") as f:
            f.write("junk")
        with self.assertRaises(sc.SteamcaseError):
            sc.use_custom_case(self.covers)
        self.assertIsNone(sc.custom_case_digest())

    def test_platform_functions_accept_custom_only_when_active(self):
        for call in (sc.platform_window, sc.platform_overlay, sc.load_platform_frame):
            with self.subTest(call=call.__name__), self.assertRaises(ValueError):
                call(sc.CUSTOM)
        sc.save_custom_case(self.case_file(tab=(30, 110, 70, 150)), self.covers)
        self.assertEqual(sc.platform_window(sc.CUSTOM), (20, 100, 580, 880))
        self.assertEqual(sc.platform_overlay(sc.CUSTOM), (30, 110, 70, 150))
        self.assertEqual(sc.load_platform_frame(sc.CUSTOM).size, sc.SIZE)
        self.assertEqual(sc.load_platform_frame(sc.CUSTOM, True).size, sc.SIZE)
        self.assertEqual(len(sc.platform_ribbon(sc.CUSTOM)), 3)
        self.assertIsInstance(sc.platform_marks_dy(sc.CUSTOM), int)
        self.assertNotIn(sc.CUSTOM, sc.PLATFORMS)


class CustomCaseCovers(StoreMocks):
    """make_covers(platforms={appid: CUSTOM}): covers in the user's own case carry its digest, and a new file rebuilds them."""

    def setUp(self):
        super().setUp()
        self.addCleanup(sc.use_custom_case, None)

    def case_file(self, name="mine.png", colour=(30, 60, 200, 255)):
        im = sc.Image.new("RGBA", sc.SIZE, colour)
        im.paste((0, 0, 0, 0), (20, 100, 580, 880))
        path = os.path.join(self.tmp, name)
        im.save(path, format="PNG")
        return path

    def cv(self, appid):
        return os.path.join(self.covers, "Game_%d_%d.png" % (appid, appid))

    def test_a_custom_cover_has_both_notes(self):
        digest = sc.save_custom_case(self.case_file(), self.covers)
        sc.make_covers({1: None}, self.covers, platforms={1: sc.CUSTOM})
        notes = sc.read_notes(self.cv(1))
        self.assertEqual((notes.platform, notes.case, notes.theme, notes.art), (sc.CUSTOM, digest, None, None))
        with sc.Image.open(self.cv(1)) as im:
            self.assertNotIn(sc.HUE_CHUNK, im.info)
        self.assertEqual(sc.cover_platform(self.cv(1)), sc.CUSTOM)

    def test_a_cover_in_the_users_own_case_can_hold_custom_art(self):
        digest = sc.save_custom_case(self.case_file(), self.covers)
        mine = os.path.join(self.tmp, "mine.jpg")
        sc.Image.new("RGB", (100, 150), (10, 160, 30)).save(mine, format="JPEG")
        sc.make_covers({1: None}, self.covers, platforms={1: sc.CUSTOM}, custom_art={1: mine})
        notes = sc.read_notes(self.cv(1))
        self.assertEqual((notes.platform, notes.case, notes.art), (sc.CUSTOM, digest, sc.art_note(mine)))

    def test_a_cover_in_a_console_case_has_no_case_note(self):
        sc.save_custom_case(self.case_file(), self.covers)
        sc.make_covers({1: None}, self.covers, platforms={1: "ps5"})
        self.assertIsNone(sc.read_notes(self.cv(1)).case)

    def test_same_file_keeps_covers_and_a_new_file_rebuilds_only_those(self):
        sc.save_custom_case(self.case_file(), self.covers)
        plan = {1: sc.CUSTOM, 2: "ps5"}
        sc.make_covers({1: None, 2: None}, self.covers, platforms=plan)
        self.assertEqual(sc.covers_in_other_case(self.covers, plan), 0)
        sc.save_custom_case(self.case_file("other.png", colour=(200, 30, 30, 255)), self.covers)
        self.assertEqual(sc.covers_in_other_case(self.covers, plan), 1)
        seen = {}
        sc.make_covers({1: None, 2: None}, self.covers, platforms=plan, progress=lambda d, t, a, n, st: seen.update({a: st}))
        self.assertEqual(seen[2], "exists")
        self.assertNotEqual(seen[1], "exists")
        self.assertEqual(sc.read_notes(self.cv(1)).case, sc.custom_case_digest())

    def test_covers_in_own_case_are_those_made_for_all_games_not_in_a_group(self):
        sc.save_custom_case(self.case_file(), self.covers)
        sc.make_covers({1: None, 2: None, 3: None}, self.covers, platforms={1: sc.CUSTOM, 2: sc.CUSTOM, 3: "ps5"}, groups={2: "gabc12345"})
        self.assertEqual(sc.covers_in_own_case(self.covers), {1})

    def test_make_without_a_case_says_so(self):
        with self.assertRaises(sc.SteamcaseError) as ctx:
            sc.make_covers({1: None}, self.covers, platforms={1: sc.CUSTOM})
        self.assertIn("case", str(ctx.exception))
        self.assertEqual(os.listdir(self.covers), [])

    def test_a_garbled_case_note_counts_as_damaged(self):
        sc.save_custom_case(self.case_file(), self.covers)
        sc.make_covers({1: None}, self.covers, platforms={1: sc.CUSTOM})
        bad = self.resave(self.cv(1), **{sc.CASE_CHUNK: "not-a-digest"})
        notes = sc.read_notes(bad)
        self.assertIs(notes.case, False)
        self.assertIs(sc.by_hand(notes), False)

    def test_is_steamcase_cover_keeps_knowing_covers_of_an_older_file(self):
        sc.save_custom_case(self.case_file(), self.covers)
        sc.make_covers({1: None}, self.covers, platforms={1: sc.CUSTOM})
        self.assertTrue(sc.is_steamcase_cover(self.cv(1)))
        self.assertFalse(sc.is_steamcase_cover(self.resave(self.cv(1), **{sc.PLATFORM_CHUNK: "ps5"})))              # a console note on a custom picture
        sc.save_custom_case(self.case_file("other.png", colour=(200, 30, 30, 255)), self.covers)
        self.assertTrue(sc.is_steamcase_cover(self.cv(1)))                           # made with the old file: Reset must still find it
        sc.use_custom_case(None)
        self.assertTrue(sc.is_steamcase_cover(self.cv(1)))                           # and with no case loaded at all (the command line, a new process)
        self.assertFalse(sc.is_steamcase_cover(self.resave(self.cv(1), **{sc.CASE_CHUNK: None})))               # a custom note needs its digest
        self.assertFalse(sc.is_steamcase_cover(self.resave(self.cv(1), **{sc.CASE_CHUNK: "zz"})))

    def test_a_cover_with_the_active_digest_must_also_match_its_pixels(self):
        digest = sc.save_custom_case(self.case_file(), self.covers)
        portrait = os.path.join(self.tmp, "portrait.jpg")
        sc.Image.new("RGB", (300, 450), (30, 220, 30)).save(portrait, format="JPEG")
        out = os.path.join(self.tmp, "fake.png")
        sc.build_cover(portrait, out, sc.load_platform_frame("ps5"), platform="ps5")           # a PS5 picture ...
        self.assertFalse(sc.is_steamcase_cover(self.resave(out, **{sc.PLATFORM_CHUNK: sc.CUSTOM, sc.CASE_CHUNK: digest})))    # ... wearing our custom notes

    def test_the_case_changing_during_a_run_stops_it_and_never_mixes_two_files(self):
        first = sc.save_custom_case(self.case_file(), self.covers)
        other = self.case_file("other.png", colour=(200, 30, 30, 255))
        swapped = []

        def progress(done, total, appid, name, status):
            if not swapped:
                swapped.append(sc.save_custom_case(other, self.covers))

        with self.assertRaises(sc.SteamcaseError) as ctx:
            sc.make_covers({1: None, 2: None, 3: None}, self.covers, platforms={1: sc.CUSTOM, 2: sc.CUSTOM, 3: sc.CUSTOM}, progress=progress)
        self.assertIn("changed", str(ctx.exception))
        for appid in (1, 2, 3):
            if os.path.exists(self.cv(appid)):
                self.assertEqual(sc.read_notes(self.cv(appid)).case, first)             # whatever was finished was built with the file it says
        self.assertFalse(os.path.exists(self.cv(3)))
        self.assertEqual([f for f in os.listdir(self.covers) if f.startswith(".tmp_")], [])      # the download of the game that was stopped is not left behind

    def test_marks_and_family_corner_use_the_measured_window(self):
        sc.save_custom_case(self.case_file(), self.covers)
        fam = sc.build_cover
        plain = os.path.join(self.tmp, "p.png")
        marked = os.path.join(self.tmp, "m.png")
        portrait = os.path.join(self.tmp, "portrait.jpg")
        sc.Image.new("RGB", (300, 450), (30, 220, 30)).save(portrait, format="JPEG", quality=100)
        fam(portrait, plain, sc.load_platform_frame(sc.CUSTOM), platform=sc.CUSTOM)
        fam(portrait, marked, sc.load_platform_frame(sc.CUSTOM, True), platform=sc.CUSTOM, treatment="rosette")
        diff = sc.ImageChops.difference(sc.Image.open(plain).convert("RGB"), sc.Image.open(marked).convert("RGB")).convert("L").point(lambda v: 255 if v > 8 else 0)
        box = diff.getbbox()
        self.assertTrue(box[0] >= 20 and box[3] <= 880, box)                           # the rosette sits at the left of the window, below the banner, and the corner is top right


class CustomCaseCli(StoreMocks):
    """make --case-file FILE: every game of the run goes in the user's own case (the same as the window's "My own case" on the Look step)."""

    def setUp(self):
        super().setUp()
        self.addCleanup(sc.use_custom_case, None)
        self.lib = self.fake_library(False)
        self.out = os.path.join(self.tmp, "out")
        im = sc.Image.new("RGBA", sc.SIZE, (30, 60, 200, 255))
        im.paste((0, 0, 0, 0), (20, 100, 580, 880))
        self.file = os.path.join(self.tmp, "mine.png")
        im.save(self.file, format="PNG")

    def make(self, *extra):
        return self.run_cli("make", "--steam-dir", self.steam, "--library", self.lib, "--out", self.out, *extra)

    def test_make_with_a_case_file_puts_every_game_in_it(self):
        text = self.make("--case-file", self.file)
        cover = os.path.join(self.out, "Game_1_1.png")
        self.assertEqual((sc.cover_platform(cover), sc.read_notes(cover).case), (sc.CUSTOM, sc.custom_case_digest()))
        self.assertIn("in your own case", text)
        self.assertTrue(os.path.isfile(os.path.join(self.out, sc.CUSTOM_FILE)))

    def test_the_case_options_that_mean_nothing_with_it_are_refused(self):
        page = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "games_page.html")
        for extra in (["--hue", "10"], ["--saturation", "10"], ["--brightness", "10"], ["--theme", "christmas"],
                      ["--games-page", page, "--completed-style", "gold-case"], ["--games-page", page, "--completed-style", "gold-border"]):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as ctx:
                self.make("--case-file", self.file, *extra)
            self.assertIn("--case-file", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.out, "Game_1_1.png")))

    def test_the_marks_work_with_it(self):
        page = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "games_page.html")
        self.make("--case-file", self.file, "--games-page", page, "--completed-style", "ribbon")        # must not raise

    def test_a_bad_case_file_is_one_sentence_and_makes_nothing(self):
        bad = os.path.join(self.tmp, "bad.png")
        sc.Image.new("RGBA", sc.SIZE, (1, 2, 3, 255)).save(bad)
        with self.assertRaises(SystemExit) as ctx:
            self.make("--case-file", bad)
        self.assertIn("window", str(ctx.exception))
        self.assertFalse(os.path.exists(os.path.join(self.out, "Game_1_1.png")))

    def test_the_kept_case_file_is_not_a_cover(self):
        self.make("--case-file", self.file)
        self.assertEqual([os.path.basename(p) for _, p in sc.scan_covers(self.out)], ["Game_1_1.png"])
        args = sc.argparse.Namespace(covers=self.out, steam_dir=self.steam, user=None, yes=True, close_steam=False)
        import contextlib, io
        with mock.patch.object(sc, "steam_running", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            sc.cmd_apply(args)
        self.assertEqual(sorted(os.listdir(self.grid)), ["1p.png"])


class PlainGold(StoreMocks):
    """The gold case and the gold border with no marks: marks "none"."""

    def flat(self):
        return sc._compose(sc.Image.new("RGBA", sc.SIZE, (10, 10, 10, 255)), sc.load_frame(sc.GOLD_HUE))

    def test_compose_and_split_round_trip(self):
        for name in sc.TREATMENTS:
            with self.subTest(name):
                self.assertEqual(sc.compose_treatment(*sc.split_treatment(name)), name)
        self.assertEqual(sc.MARKS, ("full", "rosette", "none"))
        self.assertEqual((sc.compose_treatment("gold-case", "none"), sc.compose_treatment("gold-border", "none")), ("gold-case-plain", "gold-border-plain"))
        self.assertIsNone(sc.compose_treatment("ribbon", "none"))               # the normal case with no marks is "No special case"
        self.assertEqual(sc.split_treatment("gold-border-plain"), ("gold-border", "none"))

    def test_gold_case_plain_has_no_marks(self):
        cover = self.flat()
        self.assertEqual(sc.finish_treatment(cover, "gold-case-plain", *sc.steam_marks()).tobytes(), cover.tobytes())
        self.assertNotEqual(sc.finish_treatment(cover, "gold-case-rosette", *sc.steam_marks()).tobytes(), cover.tobytes())

    def test_gold_border_plain_has_the_border_and_no_marks(self):
        cover = self.flat()
        plate = sc._gold_border().copy()
        plate.alpha_composite(cover.resize((sc.SIZE[0] - 2 * sc.BORDER, sc.SIZE[1] - 2 * sc.BORDER), sc.Image.LANCZOS), (sc.BORDER, sc.BORDER))
        self.assertEqual(sc.finish_treatment(cover, "gold-border-plain", *sc.steam_marks()).tobytes(), plate.tobytes())

    def test_make_covers_writes_the_plain_note_in_gold(self):
        for name in ("gold-case-plain", "gold-border-plain"):
            with self.subTest(name):
                folder = os.path.join(self.tmp, name)
                sc.make_covers({1: None, 2: None}, folder, completed={1}, treatment=name)
                one, two = (os.path.join(folder, "Game_%d_%d.png" % (a, a)) for a in (1, 2))
                self.assertEqual((sc.cover_treatment(one), sc.cover_treatment(two)), (name, None))
                self.assertEqual(sc.cover_colour(one), (sc.GOLD_HUE, 100, 100) if name == "gold-case-plain" else (0, 100, 100))
                self.assertEqual(sc.cover_colour(two), (0, 100, 100))

    def test_plain_gold_covers_are_ours(self):
        for name in ("gold-case-plain", "gold-border-plain"):
            with self.subTest(name):
                folder = os.path.join(self.tmp, name)
                sc.make_covers({1: None}, folder, completed={1}, treatment=name)
                self.assertTrue(sc.is_steamcase_cover(os.path.join(folder, "Game_1_1.png")))

    def test_changing_the_marks_to_none_rebuilds_only_the_100_covers(self):
        sc.make_covers({1: None, 2: None}, self.covers, completed={1}, treatment="gold-case-rosette")
        seen = {}
        sc.make_covers({1: None, 2: None}, self.covers, completed={1}, treatment="gold-case-plain", progress=lambda d, t, a, n, st: seen.update({a: st}))
        self.assertEqual((seen[2], seen[1] != "exists"), ("exists", True))

    def test_a_theme_only_goes_with_the_rosette(self):
        with self.assertRaises(ValueError):
            sc.make_covers({1: None}, self.covers, completed={1}, treatment="gold-case-plain", theme="christmas")

    def test_console_and_own_case_covers_never_get_a_plain_gold_treatment(self):
        self.assertIsNone(sc._console_marks("gold-case-plain"))
        self.assertEqual(sc._console_marks("gold-case-rosette"), "rosette")

    def test_a_theme_turns_kept_plain_gold_into_the_rosette_twin(self):
        for name, twin in (("gold-case-plain", "gold-case-rosette"), ("gold-border-plain", "gold-border-rosette")):
            with self.subTest(name):
                folder = os.path.join(self.tmp, name)
                sc.make_covers({1: None}, folder, completed={1}, treatment=name)
                sc.make_covers({1: None}, folder, theme="christmas")                  # no page: the cover keeps its look, under the theme
                cover = os.path.join(folder, "Game_1_1.png")
                self.assertEqual((sc.cover_treatment(cover), sc.cover_theme(cover)), (twin, "christmas"))
                self.assertTrue(sc.is_steamcase_cover(cover))

    def test_covers_with_no_marks_are_counted(self):
        sc.make_covers({1: None, 2: None}, self.covers, completed={1}, treatment="gold-case-plain")
        self.assertTrue(sc.covers_with_marks(self.covers, "none"))
        self.assertFalse(sc.covers_with_marks(self.covers, "full"))
        folder = os.path.join(self.tmp, "other")
        sc.make_covers({1: None}, folder, completed={1}, treatment="gold-case")
        self.assertFalse(sc.covers_with_marks(folder, "none"))

    def test_no_marks_under_a_theme_says_so_and_not_the_ribbon(self):
        import contextlib, io
        args = sc.argparse.Namespace(games_page=None, completed_style="gold-case", completed_marks="none")
        with self.assertRaises(sc.SteamcaseError) as ctx:
            sc._completion_args(args, "christmas")
        self.assertIn("no marks", str(ctx.exception))
        self.assertNotIn("ribbon", str(ctx.exception))

