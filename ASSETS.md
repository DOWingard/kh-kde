# Asset sources

Everything under `assets/` is third-party material. Kingdom Hearts artwork,
logos, sprites and audio are © Disney / Square Enix; fan-made pieces belong to
their authors. They are here for a personal desktop theme. Do not redistribute
this directory or the built `dist/` as if it were freely licensed.

Files were resized, cropped or re-encoded as noted; none was redrawn.

## `assets/reference/` — pointer and launcher emblems

Supplied by the theme's owner as the art to build on.

| File | What it is | Origin |
| --- | --- | --- |
| `kingdom-key.png` | Kingdom Key render (light pointer) | kh13.com gallery upload |
| `kingdom-key-d.png` | Kingdom Key D sprite (dark pointer) | kh13.com gallery upload |
| `kh-heart-crown.png` | Series heart-and-crown emblem (light launcher) | pngegg.com |
| `nobody-sigil.png` | Nobody sigil (dark launcher) | pngaaa.com |

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

## `assets/cursor/`, `assets/fonts/` — Kingdom Hearts Re:Collection by Televo

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

Menu sound effects of *Kingdom Hearts Melody of Memory* (`SE_MENU_*`), from the
archive.org item `kingdom-hearts-melody-of-memory-sound-effects-and-voices`
(`Sound Effects.zip`, a rip of the Switch release). Stored unmodified; the
build trims and levels them. The event mapping is in `khtheme/sounds.py`.

## `assets/wallpapers/`

Each file is the source cropped to 16:9, scaled to at most 3840×2160 and saved
as JPEG.

| File | What it shows | Kind | Source |
| --- | --- | --- | --- |
| `roxas-black-coat.jpg` | Roxas in the black coat (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_11_KHIII.png> |
| `roxas-rain.jpg` | Roxas dual-wielding in the rain (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_23_KHIII.png> |
| `heart-moon.jpg` | The heart-shaped moon, Master Xehanort before it | KH3 in-game capture | <https://wall.alphacoders.com/big.php?i=1188048> |
| `black-coat.jpg` | Black-coated figure on a cliff at dawn (χ Back Cover) | official store screenshot | <https://www.microsoft.com/store/productId/9NB80T1XC43B> |
| `menu-pattern.jpg` | KH3 menu symbol pattern | fan layout of the official pattern | <https://catwithmonocle.com/news/2019/01/20/kingdom-hearts-iii-wallpaper-pattern-2/> |
| `destiny-islands.jpg` | Destiny Islands concept art (first game) | official artwork | <https://www.khwiki.com/File:Destiny_Islands_(Art).png> |
| `sora-islands.jpg` | Sora in his first outfit on Destiny Islands (KH3 opening) | official CG | <https://www.khwiki.com/File:Opening_05_KHIII.png> |
| `final-world.jpg` | Sora in the Final World | fan art by 星宮あき | <https://wall.alphacoders.com/big.php?i=1033224> |
