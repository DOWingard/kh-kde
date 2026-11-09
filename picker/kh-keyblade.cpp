// Command-line side of the keyblade choice, for scripts and for putting the
// choice back after the cursor themes were reinstalled.
//
//   kh-keyblade list               the keyblades on offer, as JSON
//   kh-keyblade current            the recorded choice
//   kh-keyblade equip <slug>       point with that keyblade
//   kh-keyblade restore            equip the recorded choice again, if any
//
// equip and restore reload the active cursor theme unless --no-reload is given.
#include "keyblades.h"
#include "khlog.h"

#include <QCommandLineParser>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <cstdio>

namespace
{
const QString kContext = QStringLiteral("kh-keyblade");

void print(const QJsonDocument &doc)
{
    const QByteArray out = doc.toJson(QJsonDocument::Indented);
    std::fwrite(out.constData(), 1, size_t(out.size()), stdout);
}

int reload(QGuiApplication &app)
{
    Keyblades::CursorReload reload;
    int code = 0;
    QObject::connect(&reload, &Keyblades::CursorReload::finished, &app, [&app, &code](bool ok) {
        code = ok ? 0 : 1;
        app.quit();
    });
    reload.start();
    app.exec();
    return code;
}

int equip(QGuiApplication &app, const QString &slug, bool reloadAfter)
{
    QString problem;
    const QList<Keyblades::Keyblade> keyblades = Keyblades::catalogue(&problem);
    const bool known = std::any_of(keyblades.begin(), keyblades.end(), [&slug](const Keyblades::Keyblade &k) {
        return k.slug == slug;
    });
    if (!known) {
        KhLog::error(kContext, QStringLiteral("unknown keyblade"), QJsonObject{{QStringLiteral("keyblade"), slug}, {QStringLiteral("error"), problem}});
        return 2;
    }
    const Keyblades::Outcome outcome = Keyblades::equip(slug);
    if (outcome.rewritten == 0) {
        return 1;
    }
    const int reloaded = reloadAfter ? reload(app) : 0;
    return outcome.failures.isEmpty() ? reloaded : 1;
}
}

int main(int argc, char **argv)
{
    // QImage and QPainter need the GUI module, not a display.
    if (qEnvironmentVariableIsEmpty("QT_QPA_PLATFORM")) {
        qputenv("QT_QPA_PLATFORM", "offscreen");
    }
    QGuiApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("kh-keyblade"));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Choose the keyblade the Kingdom Hearts cursor themes point with."));
    parser.addHelpOption();
    parser.addPositionalArgument(QStringLiteral("command"), QStringLiteral("list | current | equip <slug> | restore"));
    const QCommandLineOption noReload(QStringLiteral("no-reload"), QStringLiteral("Do not make the desktop reload the active cursor theme."));
    parser.addOption(noReload);
    parser.process(app);
    const QStringList args = parser.positionalArguments();
    const QString command = args.value(0);
    KhLog::debug(kContext, QStringLiteral("command started"), QJsonObject{{QStringLiteral("command"), command}});

    if (command == QLatin1String("list")) {
        QString problem;
        QJsonArray list;
        const QList<Keyblades::Keyblade> keyblades = Keyblades::catalogue(&problem);
        for (const Keyblades::Keyblade &keyblade : keyblades) {
            list.append(QJsonObject{{QStringLiteral("slug"), keyblade.slug}, {QStringLiteral("name"), keyblade.name}});
        }
        print(QJsonDocument(list));
        return keyblades.isEmpty() ? 1 : 0;
    }
    if (command == QLatin1String("current")) {
        const QString current = Keyblades::chosen();
        std::printf("%s\n", qPrintable(current));
        return current.isEmpty() ? 1 : 0;
    }
    if (command == QLatin1String("equip") && args.size() == 2) {
        return equip(app, args.at(1), !parser.isSet(noReload));
    }
    if (command == QLatin1String("restore")) {
        const QString current = Keyblades::chosen();
        if (current.isEmpty()) {
            KhLog::info(kContext, QStringLiteral("no keyblade was chosen; the main one stays"));
            return 0;
        }
        return equip(app, current, !parser.isSet(noReload));
    }
    KhLog::error(kContext, QStringLiteral("unknown command"), QJsonObject{{QStringLiteral("arguments"), QJsonArray::fromStringList(args)}});
    parser.showHelp(2);
}
