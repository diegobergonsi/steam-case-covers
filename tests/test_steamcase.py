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
        try:
            with self.assertRaises(sc.SteamcaseError):
                sc.http_get("http://127.0.0.1:%d/x" % srv.server_address[1], tries=1)
        finally:
            srv.shutdown()
            srv.server_close()

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


if __name__ == "__main__":
    unittest.main()
