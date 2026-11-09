#!/usr/bin/env python3
"""Render a window of common widgets in one colour scheme, off screen.

    widgetgallery.py <scheme.colors> <out.png>
    widgetgallery.py <scheme.colors> <out.png> --kvantum dist/Kvantum/KingdomHearts --style kvantum-dark

The scheme (and, with --kvantum, the Kvantum theme folder) is read at start-up,
so this runs as its own process with a throw-away configuration directory
holding only those. A menu with a highlighted row is drawn beside the window.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log  # noqa: E402

KEYS = ["Kingdom Key", "Oathkeeper", "Oblivion", "Bond of Flame", "Two Become One", "Ultima Weapon",
        "Star Seeker", "Hidden Dragon", "Hero's Crest", "Monochrome", "Follow the Wind", "Circle of Life",
        "Photon Debugger", "Gull Wing", "Rumbling Rose", "Guardian Soul", "Wishing Lamp", "Decisive Pumpkin"]


def build_gallery(widgets):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction
    W = widgets

    window = W.QWidget()
    window.resize(900, 520)
    outer = W.QVBoxLayout(window)

    bar = W.QToolBar()
    bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    for n, label in enumerate(["Items", "Abilities", "Party"]):
        action = QAction(label, bar)
        action.setCheckable(True)
        action.setChecked(n == 1)
        bar.addAction(action)
    bar.addSeparator()
    menu_button = W.QToolButton()
    menu_button.setText("Journal")
    menu_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
    menu_button.setMenu(W.QMenu(menu_button))
    bar.addWidget(menu_button)
    outer.addWidget(bar)

    tabs = W.QTabWidget()
    page = W.QWidget()
    tabs.addTab(page, "Abilities")
    tabs.addTab(W.QWidget(), "Items")
    tabs.addTab(W.QWidget(), "Config")
    row = W.QHBoxLayout(page)

    left = W.QVBoxLayout()
    keys = W.QListWidget()
    keys.addItems(KEYS)
    keys.setCurrentRow(1)
    keys.setAlternatingRowColors(True)
    left.addWidget(keys, 3)
    table = W.QTreeWidget()
    table.setHeaderLabels(["Ability", "AP", "World"])
    for name, ap, world in (("Scan", "1", "Traverse Town"), ("Guard", "2", "Hollow Bastion"),
                            ("Dodge Roll", "3", "Destiny Islands"), ("Aerial Recovery", "2", "Agrabah")):
        item = W.QTreeWidgetItem([name, ap, world])
        item.setCheckState(0, Qt.CheckState.Checked if ap != "3" else Qt.CheckState.Unchecked)
        table.addTopLevelItem(item)
    table.setCurrentItem(table.topLevelItem(1))
    left.addWidget(table, 2)
    row.addLayout(left, 1)

    side = W.QVBoxLayout()
    group = W.QGroupBox("Equip")
    form = W.QVBoxLayout(group)
    form.addWidget(W.QLineEdit("Roxas"))
    edit = W.QComboBox()
    edit.setEditable(True)
    edit.addItems(["Twilight Town", "The World That Never Was"])
    form.addWidget(edit)
    combo = W.QComboBox()
    combo.addItems(["Valor", "Wisdom", "Master", "Final"])
    form.addWidget(combo)
    checks = W.QHBoxLayout()
    auto = W.QCheckBox("Auto Limit")
    auto.setChecked(True)
    checks.addWidget(auto)
    checks.addWidget(W.QCheckBox("Scan"))
    tri = W.QCheckBox("Partial")
    tri.setTristate(True)
    tri.setCheckState(Qt.CheckState.PartiallyChecked)
    checks.addWidget(tri)
    off = W.QCheckBox("Locked")
    off.setChecked(True)
    off.setEnabled(False)
    checks.addWidget(off)
    form.addLayout(checks)
    radios = W.QHBoxLayout()
    standard = W.QRadioButton("Standard")
    standard.setChecked(True)
    radios.addWidget(standard)
    radios.addWidget(W.QRadioButton("Proud"))
    critical = W.QRadioButton("Critical")
    critical.setEnabled(False)
    radios.addWidget(critical)
    form.addLayout(radios)
    slider = W.QSlider(Qt.Orientation.Horizontal)
    slider.setValue(60)
    form.addWidget(slider)
    progress = W.QProgressBar()
    progress.setValue(72)
    form.addWidget(progress)
    spins = W.QHBoxLayout()
    spin = W.QSpinBox()
    spin.setValue(13)
    spins.addWidget(spin)
    spins.addWidget(W.QLabel('<a href="#">A link</a>'))
    form.addLayout(spins)
    side.addWidget(group)

    buttons = W.QHBoxLayout()
    disabled = W.QPushButton("Disabled")
    disabled.setEnabled(False)
    held = W.QPushButton("Held")
    held.setDown(True)
    confirm = W.QPushButton("Confirm")
    confirm.setDefault(True)
    buttons.addWidget(disabled)
    buttons.addWidget(held)
    buttons.addStretch()
    buttons.addWidget(W.QPushButton("Cancel"))
    buttons.addWidget(confirm)
    side.addLayout(buttons)
    row.addLayout(side, 1)
    outer.addWidget(tabs)

    menu = W.QMenu()
    menu.addAction("Attack")
    magic = menu.addMenu("Magic")
    magic.addAction("Fire")
    highlighted = menu.addAction("Items")
    menu.addSeparator()
    summon = menu.addAction("Summon")
    summon.setCheckable(True)
    summon.setChecked(True)
    menu.addAction("Drive").setEnabled(False)
    menu.setActiveAction(highlighted)

    keys.setFocus()
    return window, menu, (keys, table)


def styled_environment(config: Path, scheme: Path, style: str, kvantum_theme: Path | None) -> dict[str, str]:
    """Fill `config` as a configuration folder holding only the colour scheme,
    the widget style and (optionally) a Kvantum theme, and return the
    environment that makes a Qt program draw off screen with them."""
    (config / "kdeglobals").write_text(
        scheme.read_text(encoding="utf-8") + f"\n[KDE]\nwidgetStyle={style}\n", encoding="utf-8"
    )
    if kvantum_theme:
        shutil.copytree(kvantum_theme, config / "Kvantum" / kvantum_theme.name)
        (config / "Kvantum" / "kvantum.kvconfig").write_text(f"[General]\ntheme={kvantum_theme.name}\n", encoding="utf-8")
    return {
        "XDG_CONFIG_HOME": str(config),
        "QT_QPA_PLATFORM": "offscreen",
        # The offscreen platform loads no desktop integration by itself; without
        # Plasma's platform theme Qt falls back to Fusion and ignores the scheme.
        "QT_QPA_PLATFORMTHEME": "kde",
        "QT_STYLE_OVERRIDE": style,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scheme", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--kvantum", type=Path, help="Kvantum theme folder to load")
    parser.add_argument("--style", default="Breeze", help="Qt style key, e.g. kvantum or kvantum-dark")
    args = parser.parse_args()
    if not args.scheme.is_file():
        log.error("widgetgallery", "colour scheme not found", path=str(args.scheme))
        return 2
    if args.kvantum and not args.kvantum.is_dir():
        log.error("widgetgallery", "kvantum theme folder not found", path=str(args.kvantum))
        return 2

    with tempfile.TemporaryDirectory(prefix="khgallery-") as config:
        os.environ.update(styled_environment(Path(config), args.scheme, args.style, args.kvantum))
        try:
            from PyQt6 import QtWidgets
            from PyQt6.QtCore import QPoint, QTimer
            from PyQt6.QtGui import QColor, QImage, QPainter
        except ImportError as exc:
            log.error("widgetgallery", "PyQt6 is required", error=exc)
            return 2

        app = QtWidgets.QApplication(sys.argv[:1])
        window, menu, views = build_gallery(QtWidgets)
        window.show()
        # The first list has keyboard focus, so it shows the full selection and
        # the others the muted one of a selection outside the focused view.
        window.activateWindow()
        views[0].setFocus()
        # Opened once the window is active; a popup shown first would take the activation.
        QTimer.singleShot(200, lambda: menu.popup(QPoint(0, 0)))
        result = {"ok": False}

        def shoot() -> None:
            shot = window.grab().toImage()
            popup = menu.grab().toImage()
            gap = 24
            canvas = QImage(shot.width() + gap + popup.width() + gap, max(shot.height(), popup.height() + gap),
                            QImage.Format.Format_ARGB32)
            canvas.fill(QColor(window.palette().color(window.backgroundRole())).darker(115))
            painter = QPainter(canvas)
            painter.drawImage(0, 0, shot)
            painter.drawImage(shot.width() + gap, gap, popup)
            painter.end()
            args.target.parent.mkdir(parents=True, exist_ok=True)
            result["ok"] = canvas.save(str(args.target))
            result["style"] = app.style().objectName()
            app.quit()

        QTimer.singleShot(1200, shoot)
        app.exec()

    if not result["ok"]:
        log.error("widgetgallery", "could not save the render", target=str(args.target))
        return 1
    wanted = args.style.lower()
    if result.get("style", "").lower() != wanted:
        log.warn("widgetgallery", "the requested style was not used; the render is not representative",
                 wanted=args.style, used=result.get("style"))
        return 1
    log.info("widgetgallery", "rendered", target=str(args.target), style=result.get("style"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
