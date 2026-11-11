# Asset sources

Everything under `assets/` is third-party material. Kingdom Hearts artwork,
logos, sprites and audio are © Disney / Square Enix; fan-made pieces belong to
their authors. They are here for a personal desktop theme. Do not redistribute
this directory or the built `dist/` as if it were freely licensed.

Files were resized, cropped or re-encoded as noted; none was redrawn.

## `assets/reference/` — launcher emblems and colour references

Supplied by the theme's owner as the art to build on.

| File | What it is | Origin |
| --- | --- | --- |
| `kingdom-key.png` | Kingdom Key render (colour reference) | kh13.com gallery upload |
| `kingdom-key-d.png` | Kingdom Key D sprite (colour reference: the gold, silver and bronze tokens) | kh13.com gallery upload |
| `kh-heart-crown.png` | Series heart-and-crown emblem (light launcher) | pngegg.com |
| `nobody-sigil.png` | Nobody sigil (dark launcher) | pngaaa.com |
| `picker.png` | Screenshot of this project's keyblade browser, shown in the README | the theme's owner |

## `assets/keyblades/` — pointer keyblades

Item sprites from *Kingdom Hearts: Chain of Memories* (Game Boy Advance),
supplied by the theme's owner as two sheets downloaded from The Spriters
Resource ("Kingdom Hearts: Chain of Memories → Miscellaneous → Keyblades", per
the downloaded file names). Stored unmodified; the build cuts each sprite out
and enlarges it by whole multiples.

| File | What it is |
| --- | --- |
| `kingdom-key.png` | The Kingdom Key on its own: the main pointer |
| `sheet.png` | Every keyblade of the game in two columns |

The sheet's own Kingdom Key is pixel-identical to `kingdom-key.png` and is not
used. Where each sprite sits on the sheet, and its name, is the `KEYBLADES`
table in `khtheme/keyblades.py`; the names were matched by eye against the
first game's renders on the Kingdom Hearts Wiki (<https://www.khwiki.com>).
Soul Eater is Riku's sword rather than a keyblade, but it is on the sheet and
offered like the others.

## `assets/loading/` — busy-cursor and splash sprites

Animated sprites from *Kingdom Hearts Melody of Memory*, from the album
<https://www.kh13.com/gallery/album/3244-kingdom-hearts-melody-of-memory-gifs/>.

| File | Direct URL |
| --- | --- |
| `sora.gif` | <https://www.kh13.com/uploads/monthly_2020_08/large_sora.gif.d0f3f6207de7a3619d1829e078dc558c.gif> |
| `roxas.gif` | <https://www.kh13.com/uploads/monthly_2020_09/large.roxas.gif.6b6c0012191dccdd206a4da531f4bcd0.gif> |
| `axel.gif` | <https://www.kh13.com/uploads/monthly_2020_09/large_axel.gif.75f558c24d4eeff1b77a60d09d4f9cd8.gif> |
| `xion.gif` | <https://www.kh13.com/uploads/monthly_2020_09/large_xion.gif.3226f8d4a3bc9918cf38036e5acaf453.gif> |

`axel.gif` and `xion.gif` are alternates: set `loading_art` in
`khtheme/palette.py` to use one.

## `assets/cursor/`, `assets/fonts/`, `assets/sounds/` — Kingdom Hearts Re:Collection by Televo

<https://github.com/Televo/kingdom-hearts-recollection> — "a free archive of art
assets and custom fonts"; credit is appreciated but not required. These are
faithful fan recreations, not game rips. The repository has no licence file;
that README statement is the only grant. The files are unmodified copies taken
from its `main` branch on 2026-11-08 (no release or commit is pinned).

| File | From the archive |
| --- | --- |
| `cursor/menu-glove.png` | `Detailed/Config/Menu Glove.png` |
| `fonts/KHMenu.otf`, `KHMenuBold.otf`, `KHMenuItalic.otf`, `KHMenuBoldItalic.otf` | `Fonts/` — the menu text face |
| `fonts/KHGummi.otf` | `Fonts/` — the slanted capitals of menu headers |
| `fonts/KHTitle.otf` | `Fonts/` — the logo lettering |

## `assets/logos/`

| File | What it is | Source |
| --- | --- | --- |
| `kh1-logo.png` | Logo of the first game, scaled to 1400 px wide from the 3037×1947 original | <https://www.khwiki.com/File:Kingdom_Hearts_Logo_KH.png> (file: <https://kh.wiki.gallery/images/2/2e/Kingdom_Hearts_Logo_KH.png>) |

The wiki's licence note for this file was not checked; the logo is a Disney /
Square Enix trademark whoever hosts it.

## `assets/sounds/`

Sound effects from the same Televo archive (`Sound Effects/<category>/<name>.wav`),
stored unmodified; the build trims and levels them. Each file is named for what
it accompanies in the main games, and the event table in `khtheme/sounds.py`
relies on those names:

| Category in the archive | Files used |
| --- | --- |
| `User Interface` | `Information`, `Menu Move`, `Menu Select`, `Menu Close`, `Menu Open`, `Menu Denied`, `Menu Next`, `Save Game`, `Computer Off`, `Title Screen Start KH3`, `Match Count End`, `Match Win`, `Match Lose` |
| `Rewards` | `Popup`, `Reward`, `Photo` |
| `Combat` | `Lock On`, `Lock Off`, `Critical Health`, `Drive Max`, `MP Bubble`, `Enemy Despawn KH2` |

These are game audio, © Disney / Square Enix, whatever the archive's own terms.
The names were cross-checked against the menu effects of *Kingdom Hearts Melody
of Memory*, whose file names say what each is for in that game: `Information`,
`Popup`, `Lock On` and `Lock Off` are sample-identical to `SE_MENU_NOTICE_001`,
`NOTICE_004`, `COMM_CHECK_ON` and `COMM_CHECK_OFF`, and `Menu Move`, `Menu
Select`, `Menu Close`, `Menu Open`, `Menu Denied`, `Menu Next` and `Save Game`
match `COMM_SELECT`, `COMM_ENTER`, `COMM_CANCEL`, `COMM_MENU`, `COMM_NG`,
`COMM_PAGESLIDE` and `COMM_SAVEEND` with a waveform correlation of 0.998 or
more. The two labellings agree on every one.

Two effects have no counterpart in the archive and come from the game's own
files: `SE_MENU_NET_ERROR.wav` and `SE_MENU_NOTICE_003.wav`, from the
archive.org item `kingdom-hearts-melody-of-memory-sound-effects-and-voices`
(`Sound Effects.zip`, a rip of the Switch release).

## `assets/title/` — login screens

Both were supplied by the theme's owner and are stored exactly as received.
They are official wallpapers with the game's logo printed on them.

| File | What it shows | Kind | Source |
| --- | --- | --- | --- |
| `days.jpg` | *358/2 Days* logo; Roxas, Axel, Xion, Riku and King Mickey before the clock tower (Organization XIII login screen) | official wallpaper, 1280×1024 | supplied by the owner as `large.gallery_28068_20_97394.jpg.dd488b4acbae9c6b2cb162317ec35285.jpg` |
| `kh2.jpg` | *Kingdom Hearts II* logo; Sora and Roxas with sea-salt ice cream (Sora login screen) | official wallpaper, 1024×768 | supplied by the owner as `kh-2-final-mix-hd.jpg` |

## `assets/wallpapers/`

Each file is the source cropped to 16:9, scaled to at most 3840×2160 and saved
as JPEG. The two default pictures are the exception: they were supplied by the
theme's owner and are stored exactly as received.

| File | What it shows | Kind | Source |
| --- | --- | --- | --- |
| `dive-to-the-heart.jpg` | Sora falling across a stained-glass Station of Awakening, star field (dark default) | fan wallpaper, artist not identified (signed bottom right) | supplied by the owner as `wp2734365-kh-wallpaper.jpg`, wallpapercave.com id `wp2734365` |
| `final-mix-trio.jpg` | Sora, Donald and Goofy over the crown-and-emblem pattern (light default) | official character art in a wallpaper layout | supplied by the owner as `861243-3840x2160-desktop-4k-kingdom-hearts-final-mix-wallpaper-photo.jpg` |
| `roxas-black-coat.jpg` | Roxas in the black coat (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_11_KHIII.png> |
| `roxas-rain.jpg` | Roxas dual-wielding in the rain (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_23_KHIII.png> |
| `heart-moon.jpg` | The heart-shaped moon, Master Xehanort before it | KH3 in-game capture | <https://wall.alphacoders.com/big.php?i=1188048> |
| `black-coat.jpg` | Black-coated figure on a cliff at dawn (χ Back Cover) | official store screenshot | <https://www.microsoft.com/store/productId/9NB80T1XC43B> |
| `menu-pattern.jpg` | KH3 menu symbol pattern | fan layout of the official pattern | <https://catwithmonocle.com/news/2019/01/20/kingdom-hearts-iii-wallpaper-pattern-2/> |
| `destiny-islands.jpg` | Destiny Islands concept art (first game) | official artwork | <https://www.khwiki.com/File:Destiny_Islands_(Art).png> |
| `sora-islands.jpg` | Sora in his first outfit on Destiny Islands (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_05_KHIII.png> |
| `final-world.jpg` | Sora in the Final World | fan art by 星宮あき | <https://wall.alphacoders.com/big.php?i=1033224> |

`dive-to-the-heart.jpg` is 1440×900, smaller than a 1920×1080 screen, so the
build enlarges it by a third and trims 45 source rows from the top and the
bottom to reach 16:9; that trim removes the artist's signature and the last
caption line. A search for a larger copy of the same picture found none.
