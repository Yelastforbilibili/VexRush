# VexRush

**Dual-channel autoclicker for Windows** ｜ [简体中文](README.md)

Two click channels in one small program — left and right button each get their own, so you
never need to run two clickers side by side. Clicks are delivered as window messages, which
means the cursor is never moved and the target does not have to be in the foreground: you can
keep using the mouse while it clicks.

![Main window](docs/screenshot-main.png)

---

## Quick start

1. Run `VexRush.exe` (portable, single file, no installer).
2. The **Target app** box auto-selects a foreground `java.exe` / `javaw.exe` (i.e. Minecraft).
   For anything else, pick it from the list or just type the process name (e.g. `msedge.exe`).
3. Choose an interval, flip the channel switch on, then **hold** the trigger (mouse left /
   right by default). Release to stop.

Everything — including window position and both switches — is saved automatically and restored
next time.

---

## The window

Two cards, **Click 1** and **Click 2**, fully independent:

| Control | What it does |
| --- | --- |
| switch (top right) | Master switch for that channel (also toggled by its hotkey) |
| Interval | 1–2000 ms between clicks. 15 ms ≈ 66 clicks/s, 10 ms ≈ 100 clicks/s |
| Trigger | Mouse left / right / middle, or any keyboard key (`Custom key`, then press it) |
| Advanced (collapsible) | **Name** (renaming also updates the HUD), simulated button, on/off hotkey |
| Rate (collapsible) | Live rate curve, total clicks, current clicks per second |

The top bar also holds **Click HUD** (toggle) and **Settings**.

---

## Settings

| Section | Contents |
| --- | --- |
| Appearance | 4 themes (Light / Dark / Warm sand / Ink blue), 6 accent colours plus a custom picker, 4 UI font sizes, UI font, UI language |
| Target app | Auto-detect (prefers a foreground java/javaw), PostMessage or SendMessage delivery |
| Exclusive mode | **Only one channel**: turning one on turns the other off, so the two never spam together. **Restore previous**: turning the current channel off re-opens the one it replaced (only the most recent one is remembered, so repeated swaps never restore the wrong channel) |
| IME | **Unavailable for now** (greyed out, "coming soon"): telling a text box / IME composition apart is too unreliable across programs, so the option stays off and locked |
| HUD | Opens the HUD settings window |
| Config file | Shows the real path, opens the data folder, import / export / reset |

The data directory is fixed at **`%APPDATA%\VexRush`** (`config.json` and `lang\` live there).
A leftover `config.json` next to the exe is migrated once on first start.

---

## Click HUD

A small always-on-top panel for recording or streaming: frameless, optionally click-through,
showing state, rate, count and interval per channel.

![HUD settings](docs/screenshot-hud-settings.png)

- **Layout**: vertical / horizontal; the **title text** can be turned off and reworded.
- **Content**: state / rate / clicks / interval, each individually switchable.
- **Enter / exit animations**: fade, scale, slide, spring, blur, none — driven at the monitor
  refresh rate (120 Hz here → 8 ms per frame, capped at 144 Hz).
- **Dragging**: follows only while held, with eased interpolation (can be disabled or tuned).
  On release it first **snaps to the pointer**, and only a genuine flick glides on — at most
  **16 px**, and it can never leave the screen.
- **Appearance**: font size, background opacity (backdrop only), overall opacity (dims the text
  too), idle dimming, corner radius, padding, row gap, background and text colours, accent
  source (follow theme / per channel / custom), rainbow flow and its speed.
- The right-click menu lets you lock the position, toggle click-through, toggle each field,
  replay the animation, open the settings, or hide the HUD.
- **Replay animation** plays the enter animation again so you can judge it without toggling.

---

## Language packs

The UI language is data, not code — drop a JSON file into `%APPDATA%\VexRush\lang\`:

```json
{
  "_name": "Deutsch",
  "interval": "Intervall",
  "click": "Klick %d"
}
```

- Keys are stable semantic ids — copy `example.json`, keep the keys, translate the values.
- `_name` is what the language list shows.
- Keep `%d` / `%s` / `%0.1f` placeholders; `%%` is a literal percent sign.
- Missing keys fall back to the built-in Simplified Chinese text, then to the key itself.
- Your own packs are marked *unofficial* in the list; the two shipped packs are not.

---

## When nothing happens

1. **Right target?** The hint on the right of the target bar shows `process · window title`.
2. **Elevation**: if the target runs elevated, VexRush must run elevated too, otherwise UIPI
   blocks the messages.
3. **Some programs never accept window messages**: games and tools reading input through
   DirectInput / Raw Input ignore them by design. `SendMessage` occasionally helps, usually not.
4. **Hotkey dead?** Defaults are `x` and `r`. Hotkeys are registered twice (low-level hook plus
   `RegisterHotKey`), so they usually work while another window has focus — a fullscreen game
   that grabs the keyboard exclusively may still swallow them.
5. **It refuses to click while VexRush is focused** — that is deliberate, so pressing a UI
   button can never leak clicks into the game.

---

## Known limitations

- Window-message clicking is not compatible with every program (see DirectInput above).
- An elevated target requires an elevated VexRush.
- The "ignore while typing" guard is temporarily unavailable (see above).
- Windows 10 / 11 (x64) only.

---

# Developer notes

## Working on the source

```bat
pip install PyQt5 pywin32 pynput psutil pyinstaller
python main.py                 :: run from source
python main.py --multi         :: ignore the single-instance lock (testing)
```

High DPI uses `AA_EnableHighDpiScaling` + `AA_UseHighDpiPixmaps` with the `PassThrough`
rounding policy; verified at 175 %.

## Building

```bat
python -m PyInstaller --noconfirm --clean dual_clicker.spec
:: -> dist\VexRush.exe  (onefile, console-less, icon + version info, embeds assets\fonts and assets\lang)
```

Close any leftover `dist\VexRush.exe` first, otherwise the build fails with
`PermissionError: [WinError 5]`.

## Tests

All three suites run real windows and real input on Windows, and point `APPDATA` at a throwaway
folder so they never touch your settings:

```bat
python tests\selftest.py     :: config / theme / i18n / HUD geometry and dragging / message posting
python tests\e2e_test.py     :: holds F19 against a throwaway target, letter hotkey, real mouse, foreground guard
python tests\exe_check.py    :: packaged exe: high DPI, config round-trip, restart restore (takes an exe path)
```

Notes:

- Drag / animation tests need a **clean temporary APPDATA**, otherwise a stale window geometry
  makes them fail for the wrong reason.
- `e2e_test` must run with `cfg.exclusive = False` — it verifies that both channels are
  independent; exclusive mode has its own test in `selftest`.
- `exe_check` also deletes `dist\config.json`: a leftover portable config is migrated into the
  data directory at startup and drags the old window size along.

## Layout

```
main.py                  entry point: high DPI, single instance, QApplication, fonts + language
app/
  config.py              dataclass config, atomic save, v1→v2 migration, data/lang dirs
  engine.py              pynput input hub, target registry, click worker, channels
  winapi.py              screen / refresh-rate / IME queries, window-message clicking, hotkeys
  theme.py               design tokens, QSS + palette generation, custom accents
  widgets.py             custom controls (switch, number field, segmented, sparkline …)
  mainwindow.py          main window: target bar, cards, footer, wiring
  channel_card.py        one click channel card (interval / trigger / advanced / rate)
  window_drag.py         Win32 side: caption drag takeover, hotkey registration, auto sizing
  switcher.py            blurred full-screen curtain that hides the theme rebuild cost
  overlay.py             the Click HUD: painting, layout, drag, position
  overlay_anim.py        HUD enter / exit animations and easing curves
  overlay_menu.py        HUD right-click menu (custom rounded dark menu)
  overlay_settings.py    HUD settings window
  settings.py            application settings window
  dialogbase.py          shared dialog scaffolding (header / scroll area / footer, grid rows)
  fonts.py               bundled font loading + system font list
  i18n.py                JSON language packs: built-in assets/lang + user lang\
  icon.py                generated application icon
  screen.py              monitor geometry helpers (clamp a point / widget on-screen)
  textfmt.py             small number / text formatters shared by UI modules
  debug.py               opt-in file logging (`VEXRUSH_DEBUG`)
assets/fonts/            ChillRoundM.otf + its OFL licence text
assets/lang/             zh_cn.json, en_us.json, example.json
tests/, tools/           test suites and developer tools (preview.py, make_icon.py)
docs/                    screenshots used by the READMEs
```

## Traps worth knowing

1. **Schedule with `time.perf_counter()`, never `time.monotonic()`.** The latter is
   `GetTickCount64` on Windows with 15.6 ms granularity, which collapses every interval at or
   below 15 ms to ~16 ms — 10 ms gave only 65 clicks/s.
2. **The `WM_MOVING` / `WM_SIZING` lParam RECT is in physical pixels** while Qt geometry is in
   logical pixels; mixing them at 175 % scaling makes the window jitter. Dragging no longer
   uses the system modal loop at all: the app calls `SetCapture` and eases with `SetWindowPos`
   every frame.
3. **PyQt5 aborts the process when a slot raises an uncaught exception.** Wrap timer and input
   callbacks in a thin `try/except` shell, otherwise one `NameError` becomes "freezes and dies".
4. **`QFontDatabase` / `QFontMetrics` must be used after `QApplication` exists**, or the frozen
   build dies at startup with an access violation (0xC0000005) and no stderr. Use a
   `faulthandler.enable(file=...)` probe entry point to find it.
5. **Splitting modules drops module-level constants** (the `NameError` only fires on that code
   path). An AST sweep for "used but never defined" names is a cheap pre-commit check.
6. **Keep test windows inside the virtual screen** (the offscreen platform is 768×576);
   otherwise `clamp_point` drags them back to the edge and the measured movement is a lie.
7. The global git config rewrites `github.com` through `gh-proxy.com` here — remove that
   section (or use a reachable URL) before pushing.

## Commit and release convention

- First line: version + one sentence. Body: **Fix / Add / Remove** sections.
- Before releasing: three suites green → bump `APP_VERSION` and all four version fields in
  `version_info.txt` (both the tuples and the strings) → rebuild → `exe_check`.
- Artifacts stay in `dist\`; never commit them.

## Licence

The application source is MIT — see `LICENSE`.

The bundled font **ChillRoundM** comes from [Warren2060/ChillRound](https://github.com/Warren2060/ChillRound)
and is licensed under the SIL Open Font License 1.1; the licence text ships next to the font at
`assets/fonts/LICENSE-ChillRound.txt`. Its reserved font names (`ChillRoundF`, `ChillRoundM`)
are kept unchanged as the OFL requires, and the font is **not** covered by the MIT licence above.
