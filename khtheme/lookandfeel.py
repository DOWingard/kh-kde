"""Global Theme (look-and-feel) packages: one per variant.

A package ties the variant's colour scheme, Plasma Style, application style
(Kvantum), window decoration, icons, cursors and wallpaper together, and ships
the splash screen.

The splash is laid out like the games' title screens: a plain ground, the
emblem or logo, and the variant's sprite walking a line as startup progresses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import VERSION, kvantum, log, wallpapers
from .colorscheme import scheme_id
from .palette import LOGO_BLUE, Palette, mix
from .svg import fill_template, write_text

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SPLASH_FONTS = ("KHTitle.otf", "KHMenuBold.otf")

SPLASH_QML = """import QtQuick

// Startup splash. `stage` counts the session's startup steps (1 to 6); the
// sprite walks one sixth of the line for each.
Rectangle {
    id: root

    property int stage
    readonly property real unit: Math.min(width, height)

    gradient: Gradient {
        GradientStop { position: 0; color: "@@GROUND_TOP@@" }
        GradientStop { position: 1; color: "@@GROUND_BOT@@" }
    }

    onStageChanged: {
        if (stage == 1) {
            intro.running = true;
        }
    }

    FontLoader { id: titleFont; source: "fonts/KHTitle.otf" }
    FontLoader { id: menuFont; source: "fonts/KHMenuBold.otf" }

    Item {
        id: content
        anchors.fill: parent
        opacity: 0

        Column {
            id: mark
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(root.height * 0.42 - height / 2)
            spacing: Math.round(root.unit * 0.02)

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "images/mark.png"
                height: Math.round(root.unit * @@MARK_HEIGHT@@)
                width: Math.round(height * sourceSize.width / Math.max(1, sourceSize.height))
                smooth: true
                mipmap: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: @@WORDMARK@@
                text: "Kingdom Hearts"
                textFormat: Text.PlainText
                color: "@@TEXT@@"
                font.family: titleFont.name
                font.pixelSize: Math.round(root.unit * 0.075)
            }
        }

        Item {
            id: track
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(root.height * 0.76)
            width: Math.round(root.width * 0.3)
            height: 2

            Rectangle {
                anchors.fill: parent
                color: "@@LINE@@"
                opacity: 0.35
            }
            Rectangle {
                height: parent.height
                width: walker.x + walker.width / 2
                color: "@@ACCENT@@"
            }
            AnimatedImage {
                id: walker
                source: "images/loading.gif"
                height: Math.round(root.unit * 0.12)
                width: Math.round(height * 100 / 120)
                y: -height + Math.round(height * 0.06)
                x: Math.round((track.width - width) * Math.min(root.stage, 6) / 6)
                smooth: true
                Behavior on x {
                    NumberAnimation { duration: 650; easing.type: Easing.InOutQuad }
                }
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: track.bottom
            anchors.topMargin: Math.round(root.unit * 0.028)
            text: "@@WORLD@@"
            textFormat: Text.PlainText
            color: "@@TEXT_DIM@@"
            font.family: menuFont.name
            font.weight: Font.Bold
            font.pixelSize: Math.max(13, Math.round(root.unit * 0.017))
            font.letterSpacing: Math.round(font.pixelSize * 0.3)
            font.capitalization: Font.AllUppercase
        }
    }

    OpacityAnimator {
        id: intro
        running: false
        target: content
        from: 0
        to: 1
        duration: 500
        easing.type: Easing.InOutQuad
    }
}
"""


def splash_qml(pal: Palette) -> str:
    if pal.dark:
        ground = (pal.complementary_alt, pal.complementary)
    else:
        ground = ("#ffffff", mix("#ffffff", LOGO_BLUE, 0.1))
    return fill_template(
        SPLASH_QML,
        {
            "GROUND_TOP": ground[0],
            "GROUND_BOT": ground[1],
            # The first game's logo carries its own wordmark; the sigil does not.
            "MARK_HEIGHT": "0.2" if pal.dark else "0.3",
            "WORDMARK": "true" if pal.dark else "false",
            "TEXT": pal.text,
            "TEXT_DIM": pal.text_dim,
            "LINE": pal.text_dim,
            "ACCENT": pal.indicator,
            "WORLD": pal.world,
        },
    )


def splash_mark(pal: Palette) -> Path:
    """Art at the centre of the splash and login screens."""
    return ASSETS / "reference" / pal.launcher_art if pal.dark else ASSETS / "logos" / "kh1-logo.png"


def _defaults(pal: Palette) -> str:
    return f"""[kcminputrc][Mouse]
cursorTheme={pal.cursor_id}

[kdeglobals][General]
ColorScheme={scheme_id(pal)}

[kdeglobals][Icons]
Theme={pal.theme_id}

[kdeglobals][KDE]
widgetStyle={kvantum.style_key(pal)}

[kwinrc][org.kde.kdecoration2]
library=org.kde.kwin.aurorae
theme={pal.decoration_id}

[plasmarc][Theme]
name={pal.theme_id}

[ksplashrc][KSplash]
Theme={pal.theme_id}

[Wallpaper]
Image={wallpapers.default_for(pal).package_id}
"""


def _metadata(pal: Palette) -> str:
    return json.dumps(
        {
            "KPackageStructure": "Plasma/LookAndFeel",
            "KPlugin": {
                "Authors": [{"Name": "Kingdom Hearts Plasma theme"}],
                "Category": "",
                "Description": f"{pal.title}: {'dark' if pal.dark else 'light'} Kingdom Hearts desktop",
                "Id": pal.theme_id,
                "License": "Fan project; artwork © Disney / Square Enix",
                "Name": pal.theme_name,
                "Version": VERSION,
            },
            "X-Plasma-APIVersion": "2",
        },
        indent=4,
        ensure_ascii=False,
    )


def _run(cmd: list[str], what: str) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    except FileNotFoundError as exc:
        log.error("lookandfeel", f"{what}: tool is not installed", error=exc, command=cmd[0])
        raise
    except subprocess.TimeoutExpired as exc:
        log.error("lookandfeel", f"{what} timed out", error=exc, command=cmd[0])
        raise
    except subprocess.CalledProcessError as exc:
        log.error("lookandfeel", f"{what} failed", error=exc, command=cmd[0], stderr=exc.stderr[-2000:])
        raise


def _copy(source: Path, target: Path) -> None:
    if not source.is_file():
        log.error("lookandfeel", "asset is missing", path=str(source))
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _previews(pal: Palette, wallpaper: Path, previews: Path) -> None:
    """Chooser thumbnails: the wallpaper with the emblem and name on a band in
    the variant's surface colour, set in the menu font."""
    previews.mkdir(parents=True, exist_ok=True)
    full = previews / "fullscreenpreview.jpg"
    band = pal.complementary if pal.dark else "#ffffff"
    _run(
        [
            "magick", str(wallpaper),
            "(", "-size", "1920x150", f"xc:{band}", "-alpha", "set", "-channel", "A", "-evaluate", "multiply", "0.86", "+channel", ")",
            "-gravity", "south", "-composite",
            "(", str(ASSETS / "reference" / pal.launcher_art), "-trim", "+repage", "-resize", "x104", ")",
            "-gravity", "southwest", "-geometry", "+70+23", "-composite",
            "-font", str(ASSETS / "fonts" / "KHMenuBold.otf"), "-pointsize", "54", "-fill", pal.text,
            "-gravity", "southwest", "-annotate", "+210+44", pal.title,
            "-quality", "90", str(full),
        ],
        "fullscreen preview",
    )
    _run(["magick", str(full), "-resize", "600x337!", str(previews / "preview.png")], "preview thumbnail")
    ground = pal.complementary if pal.dark else "#ffffff"
    _run(
        [
            "magick", "-size", "300x169", f"xc:{ground}",
            "(", str(splash_mark(pal)), "-trim", "+repage", "-resize", "180x96", ")",
            "-gravity", "center", "-composite", str(previews / "splash.png"),
        ],
        "splash thumbnail",
    )


def build(out: Path, pal: Palette) -> Path:
    root = out / "plasma" / "look-and-feel" / pal.theme_id
    with log.timed("lookandfeel", "build global theme", variant=pal.key, target=str(root)):
        wallpaper = wallpapers.default_image(out, pal)
        if root.exists():
            shutil.rmtree(root)

        write_text(root / "metadata.json", _metadata(pal) + "\n")
        write_text(root / "contents" / "defaults", _defaults(pal))

        splash = root / "contents" / "splash"
        write_text(splash / "Splash.qml", splash_qml(pal))
        _copy(ASSETS / "loading" / pal.loading_art, splash / "images" / "loading.gif")
        for font in SPLASH_FONTS:
            _copy(ASSETS / "fonts" / font, splash / "fonts" / font)
        mark = splash_mark(pal)
        if not mark.is_file():
            log.error("lookandfeel", "splash art is missing", path=str(mark))
            raise FileNotFoundError(mark)
        _run(
            ["magick", str(mark), "-trim", "+repage", "-resize", "1200x700>", f"PNG32:{splash / 'images' / 'mark.png'}"],
            "splash art",
        )
        _previews(pal, wallpaper, root / "contents" / "previews")
        log.info("lookandfeel", "global theme written", variant=pal.key, wallpaper=wallpaper.parent.parent.parent.name)
    return root
