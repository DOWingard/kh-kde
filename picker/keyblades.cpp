#include "keyblades.h"
#include "khlog.h"

#include <KConfig>
#include <KConfigGroup>

#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QImage>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QProcess>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSet>
#include <QStandardPaths>
#include <QTimer>
#include <QtEndian>

#include <algorithm>
#include <optional>
#include <vector>

namespace
{
const QString kContext = QStringLiteral("keyblades");
const QString kConfigFile = QStringLiteral("kingdom-hearts-plasmarc");
const QString kThemePrefix = QStringLiteral("KingdomHearts-");
// Shown for a moment while the active theme is reloaded; ships with Plasma.
const QString kStandIn = QStringLiteral("breeze_cursors");
const int kSwitchPauseMs = 1000;
const int kManifestFormat = 1;
const quint32 kXcursorImage = 0xfffd0002;

QJsonObject fields(std::initializer_list<std::pair<QString, QJsonValue>> list)
{
    QJsonObject object;
    for (const auto &[key, value] : list) {
        object[key] = value;
    }
    return object;
}

QStringList searchDirs()
{
    const QByteArray override = qgetenv("KH_CURSOR_DIRS");
    if (!override.isEmpty()) {
        return QString::fromLocal8Bit(override).split(QLatin1Char(':'), Qt::SkipEmptyParts);
    }
    // The places this project installs cursor themes to; system folders are
    // left alone, they are not ours to rewrite.
    return {QDir::homePath() + QStringLiteral("/.icons"),
            QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + QStringLiteral("/icons")};
}

std::optional<QJsonObject> loadManifest(const QString &themePath, QString *error)
{
    const QString path = themePath + QStringLiteral("/keyblades/manifest.json");
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("cannot read %1: %2").arg(path, file.errorString());
        return std::nullopt;
    }
    QJsonParseError parse;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parse);
    if (parse.error != QJsonParseError::NoError || !doc.isObject()) {
        *error = QStringLiteral("%1 is not valid JSON: %2").arg(path, parse.errorString());
        return std::nullopt;
    }
    const QJsonObject manifest = doc.object();
    if (manifest.value(QStringLiteral("format")).toInt() != kManifestFormat) {
        *error = QStringLiteral("%1 has format %2, expected %3")
                     .arg(path)
                     .arg(manifest.value(QStringLiteral("format")).toInt())
                     .arg(kManifestFormat);
        return std::nullopt;
    }
    return manifest;
}

// A manifest path must stay inside the keyblades folder.
std::optional<QString> resolve(const QString &store, const QString &relative)
{
    const QString path = QDir::cleanPath(store + QLatin1Char('/') + relative);
    if (relative.isEmpty() || QDir::isAbsolutePath(relative) || !path.startsWith(store + QLatin1Char('/'))) {
        return std::nullopt;
    }
    return path;
}

struct CursorImage {
    quint32 nominal;
    quint32 xhot;
    quint32 yhot;
    quint32 delay;
    QImage pixels; // premultiplied ARGB
};

QByteArray xcursorBytes(const std::vector<CursorImage> &images)
{
    QByteArray out;
    qsizetype total = 16 + 12 * qsizetype(images.size());
    for (const CursorImage &image : images) {
        total += 36 + 4 * qsizetype(image.pixels.width()) * image.pixels.height();
    }
    out.reserve(total);
    const auto put = [&out](quint32 value) {
        const quint32 le = qToLittleEndian(value);
        out.append(reinterpret_cast<const char *>(&le), 4);
    };
    out.append("Xcur", 4);
    put(16);
    put(0x10000);
    put(quint32(images.size()));
    quint32 offset = 16 + 12 * quint32(images.size());
    for (const CursorImage &image : images) {
        put(kXcursorImage);
        put(image.nominal);
        put(offset);
        offset += 36 + 4 * quint32(image.pixels.width()) * quint32(image.pixels.height());
    }
    for (const CursorImage &image : images) {
        const int width = image.pixels.width();
        const int height = image.pixels.height();
        for (const quint32 value : {36u, kXcursorImage, image.nominal, 1u, quint32(width), quint32(height), image.xhot, image.yhot, image.delay}) {
            put(value);
        }
        for (int y = 0; y < height; ++y) {
            const auto *row = reinterpret_cast<const quint32 *>(image.pixels.constScanLine(y));
            for (int x = 0; x < width; ++x) {
                put(row[x]);
            }
        }
    }
    return out;
}

bool rewriteTheme(const Keyblades::Theme &theme, const QString &slug, QString *error)
{
    const std::optional<QJsonObject> manifest = loadManifest(theme.path, error);
    if (!manifest) {
        return false;
    }
    const QString store = QDir::cleanPath(theme.path + QStringLiteral("/keyblades"));

    QJsonObject keys;
    const QJsonArray list = manifest->value(QStringLiteral("keyblades")).toArray();
    for (const QJsonValue &entry : list) {
        if (entry.toObject().value(QStringLiteral("slug")).toString() == slug) {
            keys = entry.toObject().value(QStringLiteral("keys")).toObject();
            break;
        }
    }
    if (keys.isEmpty()) {
        *error = QStringLiteral("%1 is not in this theme's manifest").arg(slug);
        return false;
    }

    QHash<QString, QImage> loaded;
    const auto image = [&](const QString &relative) -> QImage {
        if (auto it = loaded.constFind(relative); it != loaded.constEnd()) {
            return *it;
        }
        const std::optional<QString> path = resolve(store, relative);
        QImage result;
        if (path) {
            result = QImage(*path).convertToFormat(QImage::Format_ARGB32_Premultiplied);
        }
        loaded.insert(relative, result);
        return result;
    };

    static const QRegularExpression cursorName(QStringLiteral("^[a-z][a-z-]*$"));
    const QJsonObject cursors = manifest->value(QStringLiteral("cursors")).toObject();
    if (cursors.isEmpty()) {
        *error = QStringLiteral("the manifest lists no cursors");
        return false;
    }
    for (auto cursor = cursors.begin(); cursor != cursors.end(); ++cursor) {
        const QString name = cursor.key();
        if (!cursorName.match(name).hasMatch()) {
            *error = QStringLiteral("the manifest names a cursor %1, which is not a plain file name").arg(name);
            return false;
        }
        const QJsonObject bySize = cursor.value().toObject();
        QList<int> sizes;
        for (const QString &size : bySize.keys()) {
            sizes.append(size.toInt());
        }
        std::sort(sizes.begin(), sizes.end());

        std::vector<CursorImage> images;
        for (const int size : sizes) {
            const QString sizeKey = QString::number(size);
            const QJsonObject spec = bySize.value(sizeKey).toObject();
            const QJsonObject keyInfo = keys.value(sizeKey).toObject();
            const QString keyPath = keyInfo.value(QStringLiteral("image")).toString();
            const QImage key = image(keyPath);
            const QJsonArray hotspot = keyInfo.value(QStringLiteral("hotspot")).toArray();
            const int width = spec.value(QStringLiteral("width")).toInt();
            const int height = spec.value(QStringLiteral("height")).toInt();
            if (key.isNull() || hotspot.size() != 2 || width <= 0 || height <= 0 || key.width() > width || key.height() > height) {
                *error = QStringLiteral("%1 at size %2: the key image %3 is missing or does not fit the %4x%5 canvas")
                             .arg(name, sizeKey, keyPath)
                             .arg(width)
                             .arg(height);
                return false;
            }
            const int xhot = std::clamp(hotspot.at(0).toInt(), 0, width - 1);
            const int yhot = std::clamp(hotspot.at(1).toInt(), 0, height - 1);
            const QJsonArray frames = spec.value(QStringLiteral("frames")).toArray();
            if (frames.isEmpty()) {
                *error = QStringLiteral("%1 at size %2 has no frames").arg(name, sizeKey);
                return false;
            }
            for (const QJsonValue &frameValue : frames) {
                const QJsonObject frame = frameValue.toObject();
                QImage canvas(width, height, QImage::Format_ARGB32_Premultiplied);
                canvas.fill(Qt::transparent);
                QPainter painter(&canvas);
                painter.drawImage(0, 0, key);
                const QJsonValue overlayPath = frame.value(QStringLiteral("overlay"));
                if (overlayPath.isString()) {
                    const QImage overlay = image(overlayPath.toString());
                    if (overlay.isNull()) {
                        painter.end();
                        *error = QStringLiteral("%1 at size %2: overlay %3 is missing").arg(name, sizeKey, overlayPath.toString());
                        return false;
                    }
                    painter.drawImage(0, 0, overlay);
                }
                painter.end();
                images.push_back({quint32(size), quint32(xhot), quint32(yhot), quint32(frame.value(QStringLiteral("delay")).toInt()), canvas});
            }
        }

        // Written aside and renamed into place, so a running window manager
        // never reads a half-written cursor.
        QSaveFile file(theme.path + QStringLiteral("/cursors/") + name);
        if (!file.open(QIODevice::WriteOnly)) {
            *error = QStringLiteral("cannot write cursor %1: %2").arg(name, file.errorString());
            return false;
        }
        file.write(xcursorBytes(images));
        if (!file.commit()) {
            *error = QStringLiteral("cannot write cursor %1: %2").arg(name, file.errorString());
            return false;
        }
        KhLog::debug(kContext, QStringLiteral("cursor rewritten"),
                     fields({{QStringLiteral("theme"), theme.id}, {QStringLiteral("cursor"), name}, {QStringLiteral("images"), int(images.size())}}));
    }
    return true;
}
}

QList<Keyblades::Theme> Keyblades::installedThemes()
{
    QList<Theme> themes;
    QSet<QString> seen;
    const QStringList dirs = searchDirs();
    for (const QString &dir : dirs) {
        const QDir base(dir);
        const QStringList entries = base.entryList({kThemePrefix + QLatin1Char('*')}, QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
        for (const QString &entry : entries) {
            const QString path = base.filePath(entry);
            // The first folder holding a theme wins, as it does for the cursor loaders.
            if (seen.contains(entry) || !QFileInfo::exists(path + QStringLiteral("/keyblades/manifest.json"))) {
                continue;
            }
            seen.insert(entry);
            themes.append({entry, path});
        }
    }
    KhLog::debug(kContext, QStringLiteral("cursor themes with keyblades found"),
                 fields({{QStringLiteral("count"), int(themes.size())}, {QStringLiteral("searched"), QJsonArray::fromStringList(dirs)}}));
    return themes;
}

QList<Keyblades::Keyblade> Keyblades::catalogue(QString *error)
{
    const QList<Theme> themes = installedThemes();
    if (themes.isEmpty()) {
        *error = QStringLiteral("No Kingdom Hearts cursor theme is installed.");
        KhLog::warn(kContext, QStringLiteral("no cursor theme with keyblades is installed"),
                    fields({{QStringLiteral("searched"), QJsonArray::fromStringList(searchDirs())}}));
        return {};
    }
    // Every theme offers the same keyblades; the first one's list is used.
    const Theme &theme = themes.first();
    QString why;
    const std::optional<QJsonObject> manifest = loadManifest(theme.path, &why);
    if (!manifest) {
        *error = QStringLiteral("The cursor theme %1 is damaged; reinstall it.").arg(theme.id);
        KhLog::error(kContext, QStringLiteral("cannot read the keyblade manifest"),
                     fields({{QStringLiteral("theme"), theme.id}, {QStringLiteral("error"), why}}));
        return {};
    }
    const QString store = QDir::cleanPath(theme.path + QStringLiteral("/keyblades"));
    QList<Keyblade> keyblades;
    const QJsonArray list = manifest->value(QStringLiteral("keyblades")).toArray();
    for (const QJsonValue &value : list) {
        const QJsonObject entry = value.toObject();
        const QString slug = entry.value(QStringLiteral("slug")).toString();
        const std::optional<QString> sprite = resolve(store, entry.value(QStringLiteral("sprite")).toString());
        if (slug.isEmpty() || !sprite) {
            KhLog::warn(kContext, QStringLiteral("manifest entry skipped"), fields({{QStringLiteral("theme"), theme.id}, {QStringLiteral("entry"), entry}}));
            continue;
        }
        keyblades.append({slug, entry.value(QStringLiteral("name")).toString(slug), *sprite});
    }
    KhLog::debug(kContext, QStringLiteral("catalogue read"), fields({{QStringLiteral("theme"), theme.id}, {QStringLiteral("keyblades"), int(keyblades.size())}}));
    return keyblades;
}

QString Keyblades::chosen()
{
    return KConfig(kConfigFile).group(QStringLiteral("Keyblade")).readEntry("Current", QString());
}

QString Keyblades::activeCursorTheme()
{
    return KConfig(QStringLiteral("kcminputrc")).group(QStringLiteral("Mouse")).readEntry("cursorTheme", kStandIn);
}

Keyblades::Outcome Keyblades::equip(const QString &slug)
{
    QElapsedTimer timer;
    timer.start();
    Outcome outcome;
    const QList<Theme> themes = installedThemes();
    if (themes.isEmpty()) {
        outcome.failures.append(QStringLiteral("no Kingdom Hearts cursor theme is installed"));
        KhLog::error(kContext, QStringLiteral("cannot equip: no cursor theme with keyblades is installed"),
                     fields({{QStringLiteral("keyblade"), slug}, {QStringLiteral("searched"), QJsonArray::fromStringList(searchDirs())}}));
        return outcome;
    }
    for (const Theme &theme : themes) {
        QString error;
        if (rewriteTheme(theme, slug, &error)) {
            ++outcome.rewritten;
        } else {
            outcome.failures.append(theme.id + QStringLiteral(": ") + error);
            KhLog::error(kContext, QStringLiteral("cursor theme not rewritten"),
                         fields({{QStringLiteral("theme"), theme.id}, {QStringLiteral("path"), theme.path},
                                 {QStringLiteral("keyblade"), slug}, {QStringLiteral("error"), error}}));
        }
    }
    if (outcome.rewritten > 0) {
        KConfig config(kConfigFile);
        config.group(QStringLiteral("Keyblade")).writeEntry("Current", slug);
        if (!config.sync()) {
            outcome.failures.append(QStringLiteral("the choice could not be saved"));
            KhLog::warn(kContext, QStringLiteral("choice not saved; a reinstall will bring back the main keyblade"),
                        fields({{QStringLiteral("keyblade"), slug}, {QStringLiteral("config"), kConfigFile}}));
        }
    }
    KhLog::info(kContext, QStringLiteral("keyblade equipped"),
                fields({{QStringLiteral("keyblade"), slug}, {QStringLiteral("themes"), outcome.rewritten},
                        {QStringLiteral("failed"), int(outcome.failures.size())}, {QStringLiteral("duration_ms"), qint64(timer.elapsed())}}));
    return outcome;
}

Keyblades::CursorReload::CursorReload(QObject *parent)
    : QObject(parent)
{
}

void Keyblades::CursorReload::start()
{
    m_theme = activeCursorTheme();
    const QList<Theme> themes = installedThemes();
    const bool ours = std::any_of(themes.begin(), themes.end(), [this](const Theme &theme) {
        return theme.id == m_theme;
    });
    if (!ours) {
        KhLog::info(kContext, QStringLiteral("active cursor theme has no keyblades; nothing to reload"), fields({{QStringLiteral("active"), m_theme}}));
        QTimer::singleShot(0, this, [this] {
            Q_EMIT finished(true);
        });
        return;
    }
    // The window manager only reloads a theme it switches to, so it is shown
    // a stand-in for a moment and then the theme again.
    apply(kStandIn, [this](bool) {
        QTimer::singleShot(kSwitchPauseMs, this, [this] {
            apply(m_theme, [this](bool ok) {
                if (ok) {
                    KhLog::info(kContext, QStringLiteral("cursor theme reloaded"), fields({{QStringLiteral("theme"), m_theme}}));
                }
                Q_EMIT finished(ok);
            });
        });
    });
}

void Keyblades::CursorReload::apply(const QString &theme, std::function<void(bool)> then)
{
    auto *process = new QProcess(this);
    const QString program = QStringLiteral("plasma-apply-cursortheme");
    connect(process, &QProcess::finished, this, [process, theme, then](int code, QProcess::ExitStatus status) {
        const bool ok = status == QProcess::NormalExit && code == 0;
        if (!ok) {
            KhLog::warn(kContext, QStringLiteral("switching cursor theme failed"),
                        fields({{QStringLiteral("theme"), theme}, {QStringLiteral("exit_code"), code},
                                {QStringLiteral("stderr"), QString::fromLocal8Bit(process->readAllStandardError()).right(800)}}));
        }
        process->deleteLater();
        then(ok);
    });
    connect(process, &QProcess::errorOccurred, this, [process, program, theme, then](QProcess::ProcessError error) {
        // A process that never started reports no finished signal.
        if (error == QProcess::FailedToStart) {
            KhLog::error(kContext, QStringLiteral("cannot run the cursor theme tool"),
                         fields({{QStringLiteral("tool"), program}, {QStringLiteral("theme"), theme}, {QStringLiteral("error"), process->errorString()}}));
            process->deleteLater();
            then(false);
        }
    });
    KhLog::debug(kContext, QStringLiteral("switching cursor theme"), fields({{QStringLiteral("theme"), theme}}));
    process->start(program, {theme});
}
