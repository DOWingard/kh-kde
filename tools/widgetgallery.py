#!/usr/bin/env python3
"""Render a window of common widgets in one colour scheme, off screen.

    widgetgallery.py <scheme.colors> <out.png>

The scheme is read by the Breeze style at start-up, so this runs as its own
process with a throw-away configuration directory holding only that scheme.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from khtheme import log  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        log.error("widgetgallery", "usage: widgetgallery.py <scheme.colors> <out.png>")
        return 2
    scheme, target = Path(sys.argv[1]), Path(sys.argv[2])
    if not scheme.is_file():
        log.error("widgetgallery", "colour scheme not found", path=str(scheme))
        return 2
    with tempfile.TemporaryDirectory(prefix="khgallery-") as config:
        Path(config, "kdeglobals").write_text(
            scheme.read_text(encoding="utf-8") + "\n[KDE]\nwidgetStyle=Breeze\n", encoding="utf-8"
        )
        os.environ["XDG_CONFIG_HOME"] = config
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        # The offscreen platform loads no desktop integration by itself; without
        # Plasma's platform theme Qt falls back to Fusion and ignores the scheme.
        os.environ["QT_QPA_PLATFORMTHEME"] = "kde"
        os.environ.pop("QT_STYLE_OVERRIDE", None)
        try:
            from PyQt6.QtCore import Qt, QTimer
            from PyQt6.QtWidgets import (
                QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                QProgressBar, QPushButton, QRadioButton, QSlider, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
            )
        except ImportError as exc:
            log.error("widgetgallery", "PyQt6 is required", error=exc)
            return 2

        app = QApplication(sys.argv[:1])
        window = QWidget()
        window.resize(760, 440)
        outer = QVBoxLayout(window)
        tabs = QTabWidget()
        page = QWidget()
        tabs.addTab(page, "Abilities")
        tabs.addTab(QWidget(), "Items")
        tabs.addTab(QWidget(), "Config")
        row = QHBoxLayout(page)

        keys = QListWidget()
        keys.addItems(["Kingdom Key", "Oathkeeper", "Oblivion", "Bond of Flame", "Two Become One", "Ultima Weapon"])
        keys.setCurrentRow(1)
        keys.setAlternatingRowColors(True)
        row.addWidget(keys, 1)

        side = QVBoxLayout()
        group = QGroupBox("Equip")
        form = QVBoxLayout(group)
        form.addWidget(QLineEdit("Roxas"))
        combo = QComboBox()
        combo.addItems(["Valor", "Wisdom", "Master", "Final"])
        form.addWidget(combo)
        auto = QCheckBox("Auto Limit")
        auto.setChecked(True)
        form.addWidget(auto)
        form.addWidget(QCheckBox("Scan"))
        standard = QRadioButton("Standard")
        standard.setChecked(True)
        form.addWidget(standard)
        form.addWidget(QRadioButton("Proud"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setValue(60)
        form.addWidget(slider)
        progress = QProgressBar()
        progress.setValue(72)
        form.addWidget(progress)
        spin = QSpinBox()
        spin.setValue(13)
        form.addWidget(spin)
        form.addWidget(QLabel('<a href="#">A link</a> &nbsp; <a href="#v">plain text</a>'))
        side.addWidget(group)
        buttons = QHBoxLayout()
        disabled = QPushButton("Disabled")
        disabled.setEnabled(False)
        confirm = QPushButton("Confirm")
        confirm.setDefault(True)
        buttons.addWidget(disabled)
        buttons.addStretch()
        buttons.addWidget(QPushButton("Cancel"))
        buttons.addWidget(confirm)
        side.addLayout(buttons)
        row.addLayout(side, 1)
        outer.addWidget(tabs)

        window.show()
        keys.setFocus()
        result = {"ok": False}

        def shoot() -> None:
            image = window.grab()
            target.parent.mkdir(parents=True, exist_ok=True)
            result["ok"] = image.save(str(target))
            result["style"] = app.style().objectName()
            app.quit()

        QTimer.singleShot(900, shoot)
        app.exec()
    if not result["ok"]:
        log.error("widgetgallery", "could not save the render", target=str(target))
        return 1
    if result.get("style", "").lower() != "breeze":
        log.warn("widgetgallery", "Breeze style was not used; colours may not be representative", style=result.get("style"))
    log.info("widgetgallery", "rendered", target=str(target), style=result.get("style"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
