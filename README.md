# VexRush

A tiny Windows autoclicker with **two independent click channels**, a configurable
on-screen HUD, themes, and a Chinese / English UI.

VexRush posts real window messages (`WM_LBUTTONDOWN` / `WM_LBUTTONUP` …) to a target
window instead of moving the cursor, so the window under the mouse is never stolen and the
target does not have to be in the foreground.

## Features

- **Two channels** (`连点1`, `连点2` — both renameable), each with its own interval, trigger
  and simulated button: click the left and right mouse button at the same time without
  starting two programs.
- **Intervals from 1 ms to 2000 ms.** Scheduling uses `time.perf_counter()` (QPC), so 10 ms
  really means ~100 clicks/s. Measured: 1 / 2 / 5 / 10 / 15 / 16 / 20 / 33 / 50 / 100 ms all
  reach 100 % of the requested rate.
- **Any trigger**: mouse left/right/middle, or any keyboard key, plus a global on/off
  hotkey per channel.
- **Foreground guard**: while the VexRush window itself is focused it never clicks
  outwards, so pressing a button in the UI cannot fire into the game.
- **Typing / IME guard** (optional): while the foreground window shows a visible caret or
  the IME is composing text, neither the hotkeys nor the mouse triggers react.
- **Exclusive mode** (防卡手): turning one channel on turns the other off, and turning it
  back off restores only the channel it replaced — one slot only, so repeated swaps never
  resurrect the wrong channel.
- **Click HUD**: frameless always-on-top panel showing state, rate, count and interval per
  channel. Smooth drag interpolation with optional inertia, enter/exit animations
  (fade / scale / slide / spring / blur / none) driven at the monitor refresh rate
  (capped at 144 Hz), rainbow accent, click-through mode, and adjustable opacity, radius,
  padding, gap, colours and accent source.
- **4 themes × 6 accent colours × custom accent × 4 font sizes**, with a dark title bar
  that follows the theme.
- **Built-in rounded CJK font** (ChillRoundM, OFL 1.1) or any installed system font.
- **Portable config**: `config.json` next to the exe (fallback `%APPDATA%\VexRush`), saved
  automatically with a visible “saved at hh:mm:ss”, plus import / export / reset and a
  button that opens the data folder.
- **Single instance**, high-DPI aware (verified at 175 %), no console window.

## Usage

1. Start `VexRush.exe`.
2. Pick the target in **目标程序 / Target app** — it auto-selects a foreground `java.exe` /
   `javaw.exe` (i.e. Minecraft) when one is running.
3. Set the interval and trigger, then flip the channel switch on.
4. Hold the trigger — the target window receives clicks; release to stop.

Everything is saved automatically, including the window position.

### Known limitations

- Window-message clicking is not compatible with every program: games and tools that read
  input through DirectInput / Raw Input ignore these messages by design.
- If the target runs elevated, VexRush must run elevated too, otherwise UIPI blocks the
  messages.
- Chromium-based apps sometimes paint their own text caret, so the typing guard may not
  detect them.

## Build

```bat
pip install PyQt5 pywin32 pynput psutil pyinstaller
python -m PyInstaller --noconfirm --clean dual_clicker.spec
:: -> dist\VexRush.exe
```

Tests (Windows only — they create real windows and send real input):

```bat
python tests\selftest.py     :: config, theme, i18n, HUD geometry, IME gate, message posting
python tests\e2e_test.py     :: end-to-end against a throwaway target window
python tests\exe_check.py    :: packaged exe: high DPI, config round-trip, restore
```

Developer helpers: `tools\preview.py` renders any screen offscreen (`--theme`, `--accent`,
`--lang`, `--settings`, `--overlay-settings`, `--demo` …) and `tools\make_icon.py`
regenerates `icon.ico`.

## Layout

```
main.py                  entry point (high DPI, single instance, QApplication)
app/
  config.py              dataclass config, atomic save, v1 → v2 migration
  engine.py              pynput input hub, target registry, click worker, channels
  winapi.py              screen / refresh-rate / IME queries, window-message clicking
  theme.py               design tokens, QSS + palette generation
  widgets.py             custom controls (switch, number field, segmented, sparkline …)
  overlay.py             the Click HUD: painting, animations, drag, context menu
  overlay_settings.py    HUD settings window
  settings.py            application settings window
  dialogbase.py          shared dialog scaffolding (header / scroll area / footer, grid rows)
  fonts.py               bundled font loading + system font list
  i18n.py, i18n_en.py    translation lookup (source strings are Chinese, table is English)
  icon.py                generated application icon
assets/fonts/            ChillRoundM.otf + its OFL licence text
tests/, tools/           test suites and developer tools
```

## Licence

VexRush source is released under the MIT licence — see `LICENSE`.

The bundled font **ChillRoundM** (寒蝉半圆体) is taken from
[Warren2060/ChillRound](https://github.com/Warren2060/ChillRound) and is licensed under the
SIL Open Font License 1.1; the original licence text ships next to the font at
`assets/fonts/LICENSE-ChillRound.txt`. Its reserved font names (`ChillRoundF`,
`ChillRoundM`) are kept unchanged as the OFL requires, and the font is **not** covered by
the MIT licence above.
