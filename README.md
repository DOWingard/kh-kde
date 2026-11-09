# Kingdom Hearts for KDE Plasma

A complete theme for KDE Plasma 6 in two variants that share one palette
vocabulary, taken from the series' own art:

| Variant | Mode | Look |
| --- | --- | --- |
| **Organization XIII** (`OrgXIII`) | dark | Black with white accents, after the black command menu of the second game: clipped corners, white hairlines, white selection bars with black text. Kingdom Key D gold appears only on links and the pointer. |
| **Sora** (`Sora`) | light | The first game's colours: logo blue title bars and selection, crown gold rules and ornaments, navy text, frames shaped like that game's menu headings (one rounded corner, one square). |

Colours come from the reference art, not from taste: the logo's heart blue
`#0088ce` and crown gold `#efbb05`, the Kingdom Key D's gold `#ebc81a` and
silver `#c8cbcb`, and the five colours of the first game's command menu for
errors, warnings, success, links and information.

This is a fan project, not affiliated with or endorsed by Disney or Square
Enix. The artwork, logos, sprites and sounds under `assets/` are theirs (or
their fan authors'); see `ASSETS.md` for every source. Keep it to personal use.

## What you get

For each variant:

- **Global Theme** tying everything together, with a **splash screen** laid out
  like a title screen: the logo or sigil, and the variant's sprite walking a
  line as startup progresses
- **Window decoration**: the caption sits in a command-menu header plate, the
  buttons are round controller prompts (triangle to minimise, square to
  maximise, cross to close), the window-menu button is the emblem
- **Plasma Style**: panel, popups, notifications, tooltips, task buttons and
  list highlights in the same shapes as the windows
- **Colour scheme** for applications
- **Cursor theme**: the Kingdom Key (Sora) or Kingdom Key D (Organization XIII)
  as pointer, the menu glove on links, a walking Sora or Roxas while busy
- **Icon theme**: heart-and-crown or Nobody sigil as the application launcher,
  on top of Breeze
- **Wallpapers**: three or four pictures per variant
- **Konsole colour scheme**

Shared by both: a wallpaper package that swaps its picture with the colour
scheme, a **sound theme** built from menu sound effects, the menu and title
**fonts**, and an **SDDM login theme**.

## Requirements

- KDE Plasma 6 (KWin with the Aurorae decoration engine, Breeze application style)
- Python 3.10+
- Build tools: `rsvg-convert` (librsvg), `magick` (ImageMagick 7), `ffmpeg`
- PyQt6, only for `tools/preview.py`

## Quick start

```sh
./build.py                    # generate everything into dist/
./install.py install          # copy into ~/.local/share
./install.py apply OrgXIII    # or: ./install.py apply Sora
```

To go back to the desktop you had before:

```sh
./install.py revert
```

`apply` records your current look first (theme ids, accent colour, sound
theme, wallpaper plugin, lock-screen wallpaper, plus copies of the touched
config files) in `~/.local/state/kingdom-hearts-plasma/`, and `revert` restores
from that record. If you change the desktop by hand between two `apply` runs,
the record is refreshed, so `revert` returns to what you last had. A custom
accent colour is removed while a variant is active, because it would override
the variant's selection colours; `revert` puts it back.

Other commands:

```sh
./install.py status                 # what is installed and what is active (JSON)
./install.py apply Sora --konsole   # also recolour Konsole profiles
./install.py uninstall              # remove installed files (revert first)
```

### Light/dark switching

`apply` registers Sora as the light Global Theme and Organization XIII as the
dark one, so Plasma's own day/night switch (System Settings → Colors & Themes →
Global Theme) moves between the two. The wallpaper and lock screen follow.

### Wallpapers

All pictures appear in the wallpaper chooser as "Kingdom Hearts — …". The
package named plain "Kingdom Hearts" is the one `apply` sets: it shows
Destiny Islands in light mode and Roxas in the black coat in dark mode.

### Sounds

System Settings → Sounds shows the theme as "Kingdom Hearts". Which effect
plays for which event is the `EVENTS` table in `khtheme/sounds.py`; the mapping
follows what each effect means in the game (confirm, cancel, error, notice).

### Fonts

KHMenu, KHGummi and KHTitle are installed as user fonts. The decoration,
splash and login screen use their own copies; nothing changes your system
fonts. To use KHMenu elsewhere, pick it in System Settings → Fonts.

### Login screen

SDDM themes live in system directories, so this step needs root. Print the
commands with:

```sh
./install.py sddm
```

The variant is chosen in `theme.conf` inside the installed theme
(`variant=OrgXIII` or `variant=Sora`).

### Terminal

The Konsole colour schemes are installed but not activated unless you pass
`--konsole` to `apply`. To pick one by hand: Konsole → Settings → Edit Current
Profile → Appearance.

## Customising

Every colour is a named token in `khtheme/palette.py`, one `Palette` per
variant, built from the reference colours at the top of that file. The same
file names the art each variant uses:

| Token | Meaning |
| --- | --- |
| `pointer_art` | keyblade image used as the mouse pointer (`assets/reference/`) |
| `launcher_art` | emblem for the launcher, window menu and login screen |
| `loading_art` | animated sprite for busy cursors and the splash (`assets/loading/`) |
| `corner` | frame shapes: `cut` (clipped) or `heading` (rounded on opposite corners) |

Wallpapers are listed in `khtheme/wallpapers.py`; add a 16:9 JPEG to
`assets/wallpapers/` and a line to `WALLPAPERS`.

After any change:

```sh
./build.py && ./install.py install && ./install.py apply OrgXIII
```

Useful build options:

```sh
./build.py --only plasmastyle decoration   # rebuild selected components
./build.py --variant Sora                  # one variant only
./build.py --clean                         # start from an empty dist/
```

## Looking before applying

```sh
./tools/preview.py                    # renders to CONTEXT/tmp/previews/
./tools/preview.py --only decoration  # plasmastyle | decoration | splash | sddm | cursors | widgets
```

Nothing here touches the running desktop:

- the Plasma Style is drawn through KSvg, the library the shell uses, so slice
  bounds and margins are checked for real;
- the window decoration, splash and login screen run as QML against stand-ins
  for the objects KWin and SDDM provide (`tools/preview/mock/`);
- the cursor sheet is read back from the packed cursor files, with hotspots
  marked, on both a light and a dark surface;
- the widget gallery is drawn by Breeze in each colour scheme.

The stand-ins cannot catch a mistake against KWin's real decoration API. For
that, run the decoration under a private, headless KWin:

```sh
./tools/nestedkwin.py                 # writes CONTEXT/tmp/previews/kwin-<variant>.png
```

It starts KWin on its own D-Bus session with a throw-away configuration, opens
two test windows and saves that virtual screen. It needs `kwin_wayland`,
`dbus-run-session` and `spectacle`.

## Layout

```
build.py              build entry point
install.py            install / apply / revert / uninstall / status / sddm
ASSETS.md             where every piece of third-party art comes from
assets/               reference art, sprites, fonts, logo, sounds, wallpapers
khtheme/
  palette.py          colour tokens and art choices for both variants
  svg.py              9-slice frame and shadow builders
  colorscheme.py      application colour scheme
  plasmastyle.py      Plasma Style
  decoration.py       QML window decoration and its art
  wallpapers.py       wallpaper packages
  icons.py            launcher emblem icon theme
  cursors.py          cursor composition and Xcursor writer
  sounds.py           sound theme
  fonts.py            font staging
  konsole.py          terminal colours
  lookandfeel.py      Global Theme packages and splash
  sddm.py             login theme
  log.py              structured logging
tools/
  preview.py          offscreen renders of the built theme
  cursorsheet.py      contact sheet of a built cursor theme
  widgetgallery.py    widgets in one colour scheme
  nestedkwin.py       the decoration under a private headless KWin
dist/                 build output (generated)
```

## Logging

The tools write one JSON object per line to stderr with `timestamp`, `level`,
`context`, `message`, a `run_id` shared by all records of one invocation, and
`error` / `stack` on failures. Set `KH_LOG_LEVEL=debug` for per-file detail.
`install.py status` prints its report to stdout.

## Notes

- Application widgets (buttons, tabs, scroll bars) are drawn by Breeze in this
  theme's colours. Giving them the command-menu shapes too needs a widget
  style engine such as Kvantum, which is not included.
- Text beam, resize arrows and grab hands have no counterpart in the games;
  they are drawn to match the menu glove (white with a dark outline). Cursor
  shapes not produced here fall back to Breeze's.
- The Kingdom Key D art is 94×100 px, so its pointer is sharpest at cursor
  sizes up to 48.
- The Plasma Style overrides only the surfaces that define the look; the rest
  falls back to Breeze's colour-scheme-driven graphics.
