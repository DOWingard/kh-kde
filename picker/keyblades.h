// Choosing the keyblade the Kingdom Hearts cursor themes point with.
//
// Each installed cursor theme of the project carries, under keyblades/, every
// keyblade drawn at every cursor size, the art drawn over it on each cursor
// that shows it, and a manifest tying them together. Equipping a keyblade
// rewrites those cursors in every installed theme (light and dark) and records
// the choice, so a reinstall can put it back.
#pragma once

#include <QList>
#include <QObject>
#include <QString>
#include <QStringList>

#include <functional>

namespace Keyblades
{
struct Keyblade {
    QString slug;
    QString name;
    QString sprite; // absolute path of the unscaled sprite
};

struct Theme {
    QString id; // directory name, as cursor settings know it
    QString path; // the copy the cursor loaders use: the first folder holding it
    QString systemPath; // a package's read-only copy, when one is installed
};

struct Outcome {
    int rewritten = 0; // themes now pointing with the keyblade
    QStringList failures; // one line per theme that could not be rewritten
};

// Cursor themes of this project that can switch keyblades: those in the
// user's icon folders, then those a package installed system-wide. Equipping
// rewrites a user copy, made from the system-wide one when needed.
// KH_CURSOR_DIRS (colon-separated) replaces the folders searched, and every
// folder in it is treated as the user's.
QList<Theme> installedThemes();

// The keyblades on offer, in menu order; empty with `error` set when no
// theme is installed or its manifest cannot be read.
QList<Keyblade> catalogue(QString *error);

// The recorded choice, or an empty string when none was made.
QString chosen();

// Rewrite the keyed cursors of every installed theme with `slug` and record it.
Outcome equip(const QString &slug);

// The cursor theme the desktop uses now.
QString activeCursorTheme();

// Make the window manager drop the cursor images it holds by switching to a
// stand-in theme and back; does nothing when the active theme is not one of
// ours. Emits finished once, from the event loop.
class CursorReload : public QObject
{
    Q_OBJECT
public:
    explicit CursorReload(QObject *parent = nullptr);
    void start();

Q_SIGNALS:
    void finished(bool ok);

private:
    void apply(const QString &theme, std::function<void(bool)> then);
    QString m_theme;
};
}
