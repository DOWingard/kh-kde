// Off-screen picture of the Keyblade Browser menu, for checking it without
// touching the desktop. The plugin is found and loaded the way the Plasma
// shell does it (by id, on the Qt plugin path), and its entries are put in a
// menu set up like the shell's desktop menu.
//
//   kh-keyblade-preview <out.png> [--hover <slug>]
//
// Prints a JSON summary of the menu (entries, buttons, tooltips, caption) on stdout.
#include "khlog.h"

#include <Plasma/ContainmentActions>
#include <Plasma/PluginLoader>

#include <QApplication>
#include <QCommandLineParser>
#include <QEnterEvent>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QMenu>
#include <QPainter>
#include <QStyle>
#include <QTimer>
#include <QToolButton>

#include <cstdio>

namespace
{
const QString kContext = QStringLiteral("keyblade-preview");
const QString kPluginId = QStringLiteral("kingdomhearts_keyblades");
}

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    QCommandLineParser parser;
    parser.addHelpOption();
    parser.addPositionalArgument(QStringLiteral("out"), QStringLiteral("PNG to write"));
    const QCommandLineOption hover(QStringLiteral("hover"), QStringLiteral("Keyblade to show under the mouse."), QStringLiteral("slug"),
                                   QStringLiteral("oathkeeper"));
    parser.addOption(hover);
    parser.process(app);
    if (parser.positionalArguments().size() != 1) {
        parser.showHelp(2);
    }
    const QString out = parser.positionalArguments().first();

    Plasma::ContainmentActions *plugin = Plasma::PluginLoader::self()->loadContainmentActions(nullptr, kPluginId);
    if (!plugin) {
        KhLog::error(kContext, QStringLiteral("mouse action plugin not found on the Qt plugin path"),
                     QJsonObject{{QStringLiteral("plugin"), kPluginId}, {QStringLiteral("library_paths"), QJsonArray::fromStringList(QCoreApplication::libraryPaths())}});
        return 1;
    }

    QMenu menu;
    menu.setAttribute(Qt::WA_TranslucentBackground);
    menu.addActions(plugin->contextualActions());
    menu.popup(QPoint(0, 0));

    int code = 1;
    QTimer::singleShot(800, &app, [&] {
        QJsonObject summary;
        summary[QStringLiteral("entries")] = int(menu.actions().size());
        QJsonArray buttons;
        QToolButton *hovered = nullptr;
        const auto children = menu.findChildren<QToolButton *>();
        for (QToolButton *button : children) {
            buttons.append(QJsonObject{{QStringLiteral("slug"), button->property("slug").toString()},
                                       {QStringLiteral("tooltip"), button->toolTip()},
                                       {QStringLiteral("checked"), button->isChecked()}});
            if (button->property("slug").toString() == parser.value(hover)) {
                hovered = button;
            }
        }
        summary[QStringLiteral("buttons")] = buttons;
        if (hovered) {
            hovered->setAttribute(Qt::WA_UnderMouse, true);
            const QPointF centre = QRectF(hovered->rect()).center();
            QEnterEvent enter(centre, hovered->mapTo(&menu, centre), hovered->mapToGlobal(centre));
            QCoreApplication::sendEvent(hovered, &enter);
            hovered->update();
        }
        QTimer::singleShot(300, &app, [&, summary]() mutable {
            const auto labels = menu.findChildren<QLabel *>();
            summary[QStringLiteral("caption")] = labels.isEmpty() ? QString() : labels.first()->text();
            const QImage shot = menu.grab().toImage();
            const int gap = 24;
            QImage canvas(shot.width() + 2 * gap, shot.height() + 2 * gap, QImage::Format_ARGB32);
            canvas.fill(menu.palette().color(QPalette::Window).darker(140));
            QPainter painter(&canvas);
            painter.drawImage(gap, gap, shot);
            painter.end();
            if (!canvas.save(out)) {
                KhLog::error(kContext, QStringLiteral("cannot save the picture"), QJsonObject{{QStringLiteral("target"), out}});
            } else {
                summary[QStringLiteral("target")] = out;
                summary[QStringLiteral("style")] = QApplication::style()->name();
                const QByteArray json = QJsonDocument(summary).toJson(QJsonDocument::Indented);
                std::fwrite(json.constData(), 1, size_t(json.size()), stdout);
                code = 0;
            }
            app.quit();
        });
    });
    app.exec();
    return code;
}
