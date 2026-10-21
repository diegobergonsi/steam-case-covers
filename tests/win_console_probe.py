# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""Windows only: does the app ever make a console window appear?

A windowed app has no console, so a console program it starts (tasklist) opens a black window that flashes and takes the focus.
This script starts the app without a console (pythonw), then looks at every visible window on the desktop for a few seconds.

    python tests/win_console_probe.py            the app must never show a console window (exit 1 if it does)
    python tests/win_console_probe.py --control  starts tasklist the careless way; the watcher MUST see it (exit 1 if it is blind)

The control proves that the watcher can see such a window on this machine, so a clean run of the real check means something."""
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONSOLE_EXES = {"tasklist.exe", "conhost.exe", "cmd.exe"}
WATCH_SECONDS = 12            # the app asks "is Steam running?" at once and then every 3 seconds


def visible_windows():
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    def exe_of(pid):
        h = kernel32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf, size = ctypes.create_unicode_buffer(520), wintypes.DWORD(520)
            return os.path.basename(buf.value) if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
        finally:
            kernel32.CloseHandle(h)

    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            found.append((cls.value, exe_of(pid.value).lower()))
        return True

    user32.EnumWindows(proc(each), 0)
    return found


def is_console(window):
    cls, exe = window
    return cls == "ConsoleWindowClass" or exe in CONSOLE_EXES


def main():
    if not sys.platform.startswith("win"):
        print("skipped: this check is for Windows")
        return 0
    control = "--control" in sys.argv
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")      # no console, like the packaged app
    if control:
        code = "import subprocess, time\nfor _ in range(8):\n    subprocess.run(['tasklist'], capture_output=True)\n    time.sleep(1)"
        cmd = [pythonw, "-c", code]
    else:
        cmd = [pythonw, os.path.join(ROOT, "gui.py")]
    child = subprocess.Popen(cmd, cwd=ROOT)
    seen = set()
    try:
        end = time.time() + WATCH_SECONDS
        while time.time() < end:
            seen.update(w for w in visible_windows() if is_console(w))
            time.sleep(0.01)
    finally:
        child.kill()
    print("console windows seen: %s" % (sorted(seen) or "none"))
    if control:
        if not seen:
            print("FAILED: the watcher did not see the console window that tasklist opens, so this check cannot be trusted")
            return 1
        print("ok: the watcher can see console windows")
        return 0
    if seen:
        print("FAILED: the app made a console window appear")
        return 1
    print("ok: no console window appeared in %d seconds" % WATCH_SECONDS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
