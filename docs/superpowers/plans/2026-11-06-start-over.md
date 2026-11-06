# Start over: plan

Tests first (tests/test_qtui.py, class StartOver and one HomeScreen test), then code.

1. `settings.forget_library(path)`: removes `library.txt` only.
2. `reset()` on Library, Picker, Look, Hundred, Make and Apply: each puts its own state back to what its constructor makes.
   Cases already has `reset()`.
3. `Shell.startOver()`: refuses while `canSwitch` is false; resets the five switches, the facts, the way and the step, calls the resets above, forgets the library note, emits `startedOver` and the toast.
4. `create_engine` connects `shell.startedOver` to `PreviewProvider.clear`.
5. `HomeScreen.qml`: the "Start over" section, its `ConfirmDialog`, disabled while `!shell.canSwitch`.
6. Portuguese strings in `qtui/i18n_pt_br.py`; changelog `[Unreleased]`; `CONTEXT.md`, `FEATURES.md`.
7. Full test run, the user's real-window look, `/thermo-nuclear-code-quality-review`.
