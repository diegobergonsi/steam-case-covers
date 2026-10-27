# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Regression tests: normal use, plus the attacks the app must refuse. No network, no real Steam.
Run:  python -m unittest discover -s tests -v"""
import http.server, json, os, shutil, socketserver, struct, sys, tempfile, threading, time, unittest, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import steamcase as sc


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

    def make(self, name, hue=0, family=False, sat=100, val=100):
        out = os.path.join(self.tmp, name)
        sc.build_cover(self.src, out, sc.load_frame(hue, family, sat=sat, val=val), hue, sat=sat, val=val)
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

    def test_a_black_cover_survives_zero_brightness(self):
        cover = self.make("k.png", 0, False, 0, 0)
        self.assertTrue(sc.is_steamcase_cover(cover))
        top = (0, 0, sc.SIZE[0], sc.WINDOW[1])
        self.assertEqual(sc.load_frame(0, sat=0, val=0).getchannel("A").tobytes(), sc.load_frame(0).getchannel("A").tobytes())
        self.assertEqual(sc.Image.open(cover).convert("RGBA").crop(top).getchannel("A").tobytes(), sc.load_frame(0).crop(top).getchannel("A").tobytes())


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


class FamilyHelp(unittest.TestCase):
    """The hover text next to "Only my installed games": it must say what the switch leaves out and how to get those games."""

    def test_the_help_explains_family_games_and_the_game_list(self):
        text = sc.FAMILY_HELP.lower()
        for must in ("family", "game list", "installed", "green corner"):
            self.assertIn(must, text)
        self.assertLess(len(sc.FAMILY_HELP), 700)                                 # a tooltip, not a manual


if __name__ == "__main__":
    unittest.main()
