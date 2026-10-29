# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Regression tests: normal use, plus the attacks the app must refuse. No network, no real Steam.
Run:  python -m unittest discover -s tests -v"""
import http.server, json, os, re, shutil, socketserver, struct, sys, tempfile, threading, time, unittest, zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import steamcase as sc
import completion as cp


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


def _luminance(rgb):
    c = [v / 255 for v in rgb[:3]]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class FamilyFrame(unittest.TestCase):
    """The frame for family games: the normal frame plus a green corner triangle with the family icon."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        self.plain = sc.Image.open(sc.FRAME).convert("RGBA")
        self.family = sc.load_frame(0, True)

    def test_family_frame_equals_the_plain_frame_outside_the_corner(self):
        self.assertEqual(self.family.size, sc.SIZE)
        for box in ((220, 0, 600, 900), (0, 220, 220, 900)):
            self.assertEqual(self.family.crop(box).tobytes(), self.plain.crop(box).tobytes())

    def test_the_corner_is_green_and_follows_the_case_shape(self):
        r, g, b, a = self.family.getpixel((8, 8))
        self.assertEqual(a, 255)
        self.assertTrue(all(abs(x - y) <= 8 for x, y in zip((r, g, b), sc.FAMILY_COLOR)), (r, g, b))
        self.assertEqual(self.family.getpixel((0, 0))[3], 0)                  # the case's rounded corner stays transparent
        self.assertEqual(self.family.getpixel((150, 150)), self.plain.getpixel((150, 150)))     # past the diagonal the art window is untouched (it keeps the faint gloss)

    def test_the_icon_is_white_and_readable_on_the_triangle(self):
        self.assertGreaterEqual(contrast((255, 255, 255), sc.FAMILY_COLOR), sc.FAMILY_ICON_CONTRAST)
        self.assertEqual(self.family.getpixel((40, 35))[:3], (255, 255, 255))   # centre of the left person's head


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
        return sc.Image.open(path).convert("RGBA").getpixel((8, 8))[:3]

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
            r, g, b, a = sc.load_frame(hue, True).getpixel((8, 8))
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
            r, g, b, _ = sc.load_frame(0, True, sat=sat, val=val).getpixel((8, 8))
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
        """The first pixel of the Halloween overlay inside `box` that is at least `alpha` opaque and whose whole neighbourhood (`reach` pixels each way)
        is too: a pixel of the decorations well inside them, which the game's art cannot reach (the check pulls its mask back from the art's edge)."""
        with sc.Image.open(sc.HALLOWEEN_OVERLAY) as im:
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
                    path = self.make("t.png", hue, family, sat, val, treatment=treatment, theme="halloween")
                    self.assertTrue(sc.is_steamcase_cover(path), (hue, sat, val, family, treatment))
                    self.assertEqual(sc.cover_theme(path), "halloween")

    def test_themed_look_alikes_are_refused(self):
        real = self.make("r.png", 134, treatment="rosette", theme="halloween")
        self.assertTrue(sc.is_steamcase_cover(real))
        for what, xy in (("the pumpkin", self.deep_pixel((440, 780, 590, 880))), ("the hanging spider", self.deep_pixel((280, 120, 320, 220), 255, 3)),
                         ("the thread on the banner", (299, 20)), ("the web on the lip", self.deep_pixel((2, 884, 190, 896), 1, 0))):
            img = sc.Image.open(real).convert("RGBA")
            img.putpixel(xy, (1, 2, 3, 255))
            self.assertFalse(sc.is_steamcase_cover(self.save_with_notes(img, real)), what)
        classic = self.make("c.png", 134, treatment="rosette")
        forged = self.renote(classic, **self.notes_of(classic, theme="halloween"))
        self.assertFalse(sc.is_steamcase_cover(forged))                                  # a theme note on a cover without the decorations
        bare = self.renote(real, **self.notes_of(real, theme=None))
        self.assertFalse(sc.is_steamcase_cover(bare))                                    # decorations without their note
        for bad in ("Halloween", "halloween2", "", "spooky"):
            garbled = self.renote(real, **self.notes_of(real, theme=bad))
            self.assertFalse(sc.is_steamcase_cover(garbled), bad)
            self.assertIs(sc.cover_theme(garbled), False if bad else False)

    def test_a_themed_plain_cover_keeps_enough_frame_to_be_told_apart(self):
        for treatment in (None, "rosette", "gold-border-rosette"):
            for tone in ((0, 100, 100), (0, 0, 14), (0, 0, 78)):
                mask = sc._treated_reference((sc.tone_key(*tone), treatment, "halloween"), False)[1]
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
        self.assertEqual(mask.getpixel((526, 66)), 255)
        _, mask = sc._treated_reference((sc.tone_key(0), "gold-border", None), False)
        self.assertEqual(mask.getpixel((5, 450)), 255)

    def test_covers_from_earlier_versions_are_unchanged(self):
        self.assertTrue(sc.is_steamcase_cover(self.make("blue.png")))
        self.assertTrue(sc.is_steamcase_cover(self.renote(self.make("h.png", 134), hue="134")))      # hue note only
        self.assertTrue(sc.is_steamcase_cover(self.make("t.png", 134, sat=60, val=30)))
        self.assertTrue(sc.is_steamcase_cover(self.make("f.png", 84, True)))
        gold = self.make("g.png", treatment="gold-case")
        self.assertFalse(sc.is_steamcase_cover(self.renote(gold, **self.notes_of(gold, done=None))))   # the rosette is not part of a frame

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


class HueMath(unittest.TestCase):
    """The arithmetic behind the colour slider (the widget itself needs a display; see gui.py --selftest and the fuzzer)."""

    def setUp(self):
        try:
            import widgets
        except ImportError:
            self.skipTest("tkinter missing")
        self.w = widgets

    def test_hue_from_x_maps_and_clamps(self):
        f = self.w.hue_from_x
        self.assertEqual(f(10, 410, 10), 0)
        self.assertEqual(f(400, 410, 10), 359)
        self.assertEqual(f(-50, 410, 10), 0)
        self.assertEqual(f(9999, 410, 10), 359)
        self.assertIn(f(205, 410, 10), (179, 180))                       # the middle of the track
        self.assertEqual(f(5, 0, 0), 0)                                   # a track with no width: no division by zero
        self.assertEqual(f(5, 20, 10), 0)                                 # margins eat the whole width

    def test_value_from_x_maps_and_clamps_to_a_range(self):
        f = self.w.value_from_x
        self.assertEqual(f(10, 410, 10, 100), 0)
        self.assertEqual(f(400, 410, 10, 100), 100)
        self.assertEqual(f(-50, 410, 10, 100), 0)
        self.assertEqual(f(9999, 410, 10, 100), 100)
        self.assertEqual(f(205, 410, 10, 100), 50)
        self.assertEqual(f(5, 0, 0, 100), 0)                              # a track with no width
        self.assertEqual(self.w.hue_from_x(400, 410, 10), 359)            # the hue slider keeps its numbers
        self.assertEqual(self.w.hue_from_x(10, 410, 10), 0)

    def test_step_value_stops_at_both_ends(self):
        f = self.w.step_value
        self.assertEqual(f(0, "Left", 100), 0)
        self.assertEqual(f(100, "Right", 100), 100)
        self.assertEqual(f(95, "Prior", 100), 100)
        self.assertEqual(f(5, "Next", 100), 0)
        self.assertEqual(f(40, "Home", 100), 0)
        self.assertEqual(f(40, "End", 100), 100)
        self.assertEqual(f(40, "Right", 100), 41)
        self.assertEqual(f(40, "x", 100), 40)
        self.assertEqual(f(0, "Left", 359, wrap=True), 359)
        self.assertEqual(f(359, "Right", 359, wrap=True), 0)

    def test_drag_mode_tells_a_slide_from_a_swipe(self):
        f = self.w.drag_mode
        self.assertIsNone(f(0, 0, 6))                      # a tap or a tiny wobble: undecided
        self.assertIsNone(f(5, -5, 6))
        self.assertEqual(f(20, 4, 6), "horizontal")        # sliding the thumb
        self.assertEqual(f(-20, -19, 6), "horizontal")     # a diagonal that is mostly sideways still slides
        self.assertEqual(f(3, 25, 6), "vertical")          # a swipe to scroll the page
        self.assertEqual(f(-7, -30, 6), "vertical")
        self.assertEqual(f(10, 10, 6), "horizontal")       # a perfect diagonal goes to the slider (a tie never scrolls by accident)

    def test_step_hue_keys(self):
        f = self.w.step_hue
        self.assertEqual(f(0, "Left"), 359)
        self.assertEqual(f(359, "Right"), 0)
        self.assertEqual(f(10, "Prior"), 40)
        self.assertEqual(f(10, "Next"), 340)
        self.assertEqual(f(200, "Home"), 0)
        self.assertEqual(f(10, "End"), 359)
        self.assertEqual(f(77, "x"), 77)

    def test_step_choice_moves_and_stops_at_the_ends(self):
        f = self.w.step_choice
        self.assertEqual(f(0, "Left", 4), 0)
        self.assertEqual(f(3, "Right", 4), 3)
        self.assertEqual(f(1, "Right", 4), 2)
        self.assertEqual(f(2, "Home", 4), 0)
        self.assertEqual(f(1, "End", 4), 3)
        self.assertEqual(f(1, "x", 4), 1)
        self.assertEqual(f(0, "Down", 4), 1)
        self.assertEqual(f(2, "Up", 4), 1)


class ReplaceReason(StoreMocks):
    """The sentence of the Replace prompt (gui.App._replace_reason) for every kind of change, over covers made by the app's own functions."""

    def setUp(self):
        super().setUp()
        try:
            import types, gui
        except ImportError:
            self.skipTest("tkinter missing")
        self.gui = gui
        self.fake = types.SimpleNamespace(covers_dir=self.covers)
        self.games = {1: None, 2: None}

    def made(self, hue=0, completed=None, treatment=None, theme=None):
        sc.make_covers(self.games, self.covers, hue=hue, completed=completed, treatment=treatment, theme=theme)

    def reason(self, tone, completed, treatment, theme=None):
        got = self.gui.App._replace_reason(self.fake, tone, completed, treatment, theme)
        self.assertIsNotNone(got)
        title, sentence = got
        self.assertTrue(title.strip() and sentence.strip() and "%" not in title.replace("100%", "") and "%" not in sentence.replace("100%", ""), got)
        return got

    def test_nothing_to_rebuild_gives_no_prompt(self):
        self.made(completed={1}, treatment="ribbon")
        self.assertIsNone(self.gui.App._replace_reason(self.fake, (0, 100, 100), {1}, "ribbon"))

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
        title, text = self.reason((0, 100, 100), None, None, "halloween")
        self.assertIn("theme", title.lower())
        self.assertIn("new ones in the Halloween theme", text)
        self.made(theme="halloween")
        self.assertIn("new ones in the Classic case", self.reason((0, 100, 100), None, None, None)[1])

    def test_a_theme_without_a_page_says_the_100_covers_lose_their_ribbon(self):
        self.made(completed={1}, treatment="ribbon")
        text = self.reason((0, 100, 100), None, None, "halloween")[1]
        self.assertIn("lose their ribbon", text)
        self.assertIn("Rosette and ribbon", text)                                  # and how to get it back
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made(completed={1}, treatment="rosette")
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "halloween")[1])        # nothing to lose
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made()
        self.assertNotIn("ribbon", self.reason((0, 100, 100), None, None, "halloween")[1])

    def test_covers_with_full_marks_are_found(self):
        self.assertFalse(sc.covers_with_full_marks(os.path.join(self.tmp, "nowhere")))
        self.made()
        self.assertFalse(sc.covers_with_full_marks(self.covers))
        self.made(completed={1}, treatment="gold-border-rosette")
        self.assertFalse(sc.covers_with_full_marks(self.covers))
        self.made(completed={1}, treatment="gold-border")
        self.assertTrue(sc.covers_with_full_marks(self.covers))

    def test_a_theme_with_a_colour_or_a_look_change_stays_readable(self):
        self.made()
        text = self.reason((134, 100, 100), None, None, "halloween")[1]
        self.assertIn("another colour or theme", text)
        self.assertNotIn(", and with", text)
        shutil.rmtree(self.covers, ignore_errors=True)
        self.made(completed={1}, treatment="ribbon")
        text = self.reason((0, 100, 100), {1}, "rosette", "halloween")[1]
        self.assertIn("100%", text)
        self.assertIn("All your covers are also made in the Halloween theme", text)

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

    def theme(self, out, appid):
        return sc.cover_theme(os.path.join(out, "Game_%d_%d.png" % (appid, appid)))

    def test_theme_makes_halloween_covers_and_keeps_the_colour_options(self):
        out = os.path.join(self.tmp, "out")
        text = self.make(out, "--theme", "halloween", "--hue", "134")
        self.assertEqual(self.theme(out, 1), "halloween")
        self.assertEqual(sc.cover_hue(os.path.join(out, "Game_1_1.png")), 134)
        self.assertIn("Halloween theme", text)

    def test_the_theme_of_the_covers_already_there_is_kept_unless_asked_otherwise(self):
        out = os.path.join(self.tmp, "out")
        self.make(out, "--theme", "halloween")
        path = os.path.join(out, "Game_1_1.png")
        before = self.read(path)
        text = self.make(out)                                                           # no --theme: Halloween covers stay Halloween
        self.assertEqual(self.read(path), before)
        self.assertIn("Halloween theme", text)
        self.make(out, "--theme", "classic")
        self.assertIsNone(self.theme(out, 1))
        self.assertNotIn("Halloween theme", self.make(out, "--theme", "classic"))

    def test_a_theme_gives_100_percent_games_the_rosette_only(self):
        page = self.page({1: (10, 10), 2: (1, 9)})
        out = os.path.join(self.tmp, "out")
        self.make(out, "--theme", "halloween", "--games-page", page)
        self.assertEqual(self.treatment(out, 1), "rosette")
        self.assertIsNone(self.treatment(out, 2))
        out2 = os.path.join(self.tmp, "out2")
        self.make(out2, "--theme", "halloween", "--games-page", page, "--completed-style", "gold-border", "--completed-marks", "rosette")
        self.assertEqual(self.treatment(out2, 1), "gold-border-rosette")
        self.make(out2, "--games-page", page)                                           # the folder is themed already: the default marks are rosette
        self.assertEqual(self.treatment(out2, 1), "rosette")

    def test_a_theme_and_full_marks_are_refused(self):
        page = self.page({1: (10, 10)})
        out = os.path.join(self.tmp, "out")
        with self.assertRaises(SystemExit) as caught:
            self.make(out, "--theme", "halloween", "--games-page", page, "--completed-marks", "full")
        self.assertIn("Halloween", str(caught.exception))
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
            sc.cmd_make(sc.argparse.Namespace(games_page=os.path.join(self.tmp, "missing.html"), completed_style=None, completed_marks=None, theme="classic"))
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
        """A cancelled theme change leaves classic and Halloween covers side by side; apply must not copy that mix into Steam."""
        lib = self.fake_library(False)
        out = os.path.join(self.tmp, "out")
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out)
        self.assertFalse(sc.mixed_cover_themes(out))
        sc.make_covers({2: None}, out, theme="halloween")                           # a cover from the interrupted run, in the other theme
        self.assertTrue(sc.mixed_cover_themes(out))
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("apply", "--steam-dir", self.steam, "--covers", out, "--yes")
        self.assertIn("more than one theme", str(caught.exception))
        self.assertEqual(os.listdir(self.grid), [])                                  # nothing was copied
        self.run_cli("make", "--steam-dir", self.steam, "--library", lib, "--out", out, "--theme", "halloween")
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
        self.assertEqual(done.getpixel((300, 400)), plain.getpixel((300, 400)))
        self.assertNotEqual(done.getpixel((526, 66)), plain.getpixel((526, 66)))
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
        self.assertTrue(any(near(p[:3], self.DISC) for p in pixels(im.crop((480, 30, 560, 100)))))
        box = im.crop((460, 20, 580, 140))                                                     # the whole disc, to find its centre
        disc = [(i % 120 + 460, i // 120 + 20) for i, p in enumerate(pixels(box)) if near(p[:3], self.DISC)]
        cx, cy = sum(x for x, _ in disc) / len(disc), sum(y for _, y in disc) / len(disc)
        want = (BORDER_AT(526, 0), BORDER_AT(66, 1))                                           # the disc shrank with the case: its centre moved
        self.assertTrue(abs(cx - want[0]) <= 2 and abs(cy - want[1]) <= 2, ((cx, cy), want))
        self.assertGreater(abs(cx - 526) + abs(cy - 66), 10)
        strip = pixels(im.crop((0, 0, 14, 900)))
        self.assertFalse(any(p[3] and near(p[:3], self.BAND) for p in strip))

    def test_family_corner_and_the_rosette_do_not_overlap(self):
        im = sc.preview_cover(0, True, treatment="ribbon")
        self.assertTrue(near(im.getpixel((8, 8))[:3], sc.FAMILY_COLOR, 8), im.getpixel((8, 8)))
        self.assertTrue(near(im.getpixel((526, 66))[:3], self.DISC), im.getpixel((526, 66)))

    def test_treatment_colour(self):
        self.assertEqual(sc.treatment_colour("gold-case", (20, 40, 50)), (176, 100, 100))
        self.assertEqual(sc.treatment_colour("ribbon", (20, 40, 50)), (20, 40, 50))
        c = (20, 40, 50)
        self.assertEqual(sc.treatment_colour(None, c), c)


    def test_compose_and_split_round_trip(self):
        for style in sc.CASES:
            for marks in sc.MARKS:
                self.assertEqual(sc.split_treatment(sc.compose_treatment(style, marks)), (style, marks))
        self.assertEqual(sc.compose_treatment("ribbon", "full"), "ribbon")
        self.assertEqual(sc.compose_treatment("ribbon", "rosette"), "rosette")
        self.assertEqual(sc.compose_treatment("gold-case", "rosette"), "gold-case-rosette")
        self.assertEqual(sc.compose_treatment("gold-border", "full"), "gold-border")
        self.assertEqual(len(sc.TREATMENTS), 6)
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
        self.assertNotEqual(list(pixels(only.crop((400, 0, 600, 120)))), list(pixels(plain.crop((400, 0, 600, 120)))))
        self.assertEqual(list(pixels(only.crop((400, 0, 600, 120)))), list(pixels(full.crop((400, 0, 600, 120)))))     # the same rosette
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
        sc.make_covers(self.games, self.covers, theme="halloween", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "ok"), statuses)
        self.assertEqual(sc.cover_theme(self.cover(1)), "halloween")
        statuses = []
        sc.make_covers(self.games, self.covers, theme="halloween", progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "exists"), statuses)
        sc.make_covers(self.games, self.covers, theme="halloween", force=True, progress=lambda *a: statuses.append((a[2], a[4])))
        self.assertIn((1, "ok"), statuses[2:])
        sc.make_covers(self.games, self.covers)                                           # no theme: back to classic
        self.assertIsNone(sc.cover_theme(self.cover(1)))
        self.assertNotIn(sc.THEME_CHUNK, sc.Image.open(self.cover(1)).info)

    def test_the_rebuild_checks_see_the_theme_and_keep_ignores_it(self):
        sc.make_covers(self.games, self.covers, theme="halloween")
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme=sc.KEEP))
        self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="halloween"))
        self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, theme=None))
        self.assertFalse(sc.covers_in_other_colour(self.covers, 0, 100, 100))              # a themed folder in its own colour is not "another colour"
        self.assertTrue(sc.covers_in_other_theme(self.covers, None))
        self.assertFalse(sc.covers_in_other_theme(self.covers, "halloween"))

    def test_a_theme_and_full_marks_are_refused_before_anything_is_made(self):
        for bad in ("ribbon", "gold-case", "gold-border"):
            with self.assertRaises(ValueError):
                sc.make_covers(self.games, self.covers, completed={1}, treatment=bad, theme="halloween")
        with self.assertRaises(ValueError):
            sc.make_covers(self.games, self.covers, theme="spooky")
        self.assertEqual(os.listdir(self.covers), [])
        for fine in (None, "rosette", "gold-border-rosette"):
            sc.make_covers(self.games, self.covers, completed={1}, treatment=fine, theme="halloween")
            self.assertEqual(sc.cover_theme(self.cover(1)), "halloween")

    def test_a_theme_over_existing_full_marks_covers_turns_them_into_rosette_only(self):
        for old, want in (("ribbon", "rosette"), ("gold-case", "gold-case-rosette"), ("gold-border", "gold-border-rosette")):
            shutil.rmtree(self.covers, ignore_errors=True)
            sc.make_covers(self.games, self.covers, completed={1}, treatment=old)
            self.assertTrue(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="halloween"))
            sc.make_covers(self.games, self.covers, theme="halloween")                    # no page: each cover keeps its look, with the marks the theme allows
            self.assertEqual(sc.cover_treatment(self.cover(1)), want)
            self.assertEqual(sc.cover_theme(self.cover(1)), "halloween")
            self.assertIsNone(sc.cover_treatment(self.cover(2)))
            self.assertFalse(sc.covers_in_other_look(self.covers, 0, 100, 100, theme="halloween"))

    def test_a_missing_halloween_overlay_fails_before_any_cover_is_made(self):
        with mock.patch.object(sc, "HALLOWEEN_OVERLAY", os.path.join(self.tmp, "no-overlay.png")):
            sc._halloween_overlay.cache_clear()
            self.addCleanup(sc._halloween_overlay.cache_clear)
            with self.assertRaises(OSError):
                sc.make_covers(self.games, self.covers, theme="halloween")
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
        box = sc.Image.open(self.cover(1)).convert("RGBA").crop((14, 14, 60, 60))
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



class DiscordButton(unittest.TestCase):
    """The Discord icon in the window's header: one link, one bundled image, credited."""
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

    def test_the_mark_is_readable_on_the_header_background(self):
        def lum(rgb):
            c = [x / 255 for x in rgb]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        try:
            import widgets
        except ImportError:
            self.skipTest("tkinter missing")
        bg, mark = tuple(int(widgets.BG[i:i + 2], 16) for i in (1, 3, 5)), (0x58, 0x65, 0xF2)    # the header background, the blurple
        self.assertGreaterEqual((lum(mark) + .05) / (lum(bg) + .05), 3.0)                  # WCAG for graphics

    def test_the_packaged_app_bundles_the_image_and_credits_the_source(self):
        with open(os.path.join(sc.HERE, "steamcase.spec"), encoding="utf-8") as f:
            self.assertIn("assets/discord.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read()
        for must in ("Simple Icons", "CC0", "Discord", "trademark"):
            self.assertIn(must, text)


class HalloweenOverlay(unittest.TestCase):
    """The artwork of the Halloween case theme: a transparent overlay with a web and a spider, a pumpkin and a hanging spider."""

    def setUp(self):
        if sc.Image is None:
            self.skipTest("Pillow missing")
        with sc.Image.open(sc.HALLOWEEN_OVERLAY) as im:
            self.mode, self.ov = im.mode, im.convert("RGBA")

    def ink(self, box):
        """How many pixels of the overlay in `box` are not fully transparent."""
        return sum(1 for p in pixels(self.ov.crop(box)) if p[3] > 0)

    def test_it_is_a_full_size_rgba_png(self):
        self.assertEqual((self.mode, self.ov.size), ("RGBA", (600, 900)))

    def test_the_three_decorations_are_where_they_should_be(self):
        self.assertGreaterEqual(self.ink((0, 700, 200, 900)), 400)                    # the web and the spider on it, bottom-left
        self.assertGreaterEqual(self.ink((440, 760, 600, 900)), 400)                  # the pumpkin, bottom-right
        self.assertGreaterEqual(self.ink((280, 0, 320, 220)), 400)                    # the thread and the spider hanging from the top centre

    def test_the_rest_of_the_cover_stays_clear(self):
        self.assertEqual(self.ink((140, 300, 460, 760)), 0)                           # the middle of the art
        self.assertEqual(self.ink((14, 96, 60, 140)), 0)                              # under the family corner
        self.assertEqual(self.ink((440, 20, 586, 80)), 0)                             # the platform badges, where the rosette goes

    def test_the_decorations_that_matter_are_opaque(self):
        solid = sum(1 for p in pixels(self.ov.crop((440, 760, 600, 900))) if p[3] == 255)
        self.assertGreater(solid, 3000)                                               # a pumpkin, not a faint sketch

    def test_the_packaged_app_bundles_it_and_the_licence_file_credits_it(self):
        with open(os.path.join(sc.HERE, "steamcase.spec"), encoding="utf-8") as f:
            self.assertIn("assets/halloween_overlay.png", f.read())
        with open(os.path.join(sc.HERE, "docs", "THIRD_PARTY.md"), encoding="utf-8") as f:
            text = f.read().lower()
        for must in ("halloween", "original artwork"):
            self.assertIn(must, text)


class ThemeCovers(unittest.TestCase):
    """The Halloween theme on a cover: the decorations, the note that records it, and reading it back."""

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
        themed, plain = sc.preview_cover(134, theme="halloween"), sc.preview_cover(134)
        self.assertNotEqual(themed.getpixel((520, 842)), plain.getpixel((520, 842)))             # the pumpkin
        self.assertEqual(themed.getpixel((300, 400)), plain.getpixel((300, 400)))                # the art
        self.assertEqual(themed.getpixel((7, 450)), plain.getpixel((7, 450)))                    # the case keeps its colour
        self.assertEqual(themed.getpixel((0, 0))[3], 0)                                          # nothing reaches past the rounded case

    def test_the_theme_is_noted_and_read_back(self):
        themed, plain = self.built("t.png", "halloween"), self.built("p.png")
        self.assertEqual(sc.cover_theme(themed), "halloween")
        self.assertIsNone(sc.cover_theme(plain))
        self.assertNotIn(sc.THEME_CHUNK, sc.Image.open(plain).info)                              # classic covers carry no note, as before themes existed
        from PIL.PngImagePlugin import PngInfo
        for bad in ("Halloween", "halloween2", ""):
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
        self.assertFalse(sc.covers_in_other_theme(d, "halloween"))
        sc.build_cover(self.src, os.path.join(d, "A_1_1.png"), sc.load_frame(0), 0)
        sc.build_cover(self.src, os.path.join(d, "B_2_2.png"), sc.load_frame(0), 0, theme="halloween")
        self.assertIsNone(sc.existing_cover_theme(d))                                           # the first by name decides
        self.assertTrue(sc.covers_in_other_theme(d, "halloween"))
        self.assertTrue(sc.covers_in_other_theme(d, None))
        os.remove(os.path.join(d, "A_1_1.png"))
        self.assertEqual(sc.existing_cover_theme(d), "halloween")
        self.assertFalse(sc.covers_in_other_theme(d, "halloween"))

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
        self.assertEqual(payload["allowed_mentions"], {"parse": []})                  # words in the changelog can never ping anyone

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
        for text in (release, announce):
            self.assertIn("DISCORD_WEBHOOK_URL", text)
            self.assertIn("continue-on-error: true", text)                            # a Discord problem never marks the release as failed
            for line in text.splitlines():
                self.assertFalse("curl" in line and "secrets." in line, line)           # the secret goes through the environment, never into the command line text


if __name__ == "__main__":
    unittest.main()
