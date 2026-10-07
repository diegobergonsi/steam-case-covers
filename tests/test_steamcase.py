"""Regression tests: normal use, plus the attacks the app must refuse. No network, no real Steam.
Run:  python -m unittest discover -s tests -v"""
import http.server, json, os, shutil, socketserver, struct, sys, tempfile, threading, unittest, zlib

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

    def test_two_applies_in_the_same_second(self):
        for data in (b"A", b"B", b"C"):
            sc.apply_covers(self.steam, self.covers, files=[self.cover(1, data)])
        self.assertEqual(len(sc.list_backups(self.steam)), 3)


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

    def test_file_names_are_safe(self):
        self.assertEqual(sc.slug("../../etc/passwd"), "etc_passwd")
        self.assertLessEqual(len(sc.slug("X" * 500).encode()), 60)
        self.assertIsNone(sc.appid_of("Game_99999999999.png"))
        self.assertIsNone(sc.appid_of("Game_0.png"))


if __name__ == "__main__":
    unittest.main()
