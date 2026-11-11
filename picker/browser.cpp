// "Keyblade Browser": a desktop mouse action for Plasma. Bound to a mouse
// button on the desktop, it opens a menu holding a grid of every keyblade the
// cursor themes offer; picking one makes it the mouse pointer.
#include "keyblades.h"
#include "khlog.h"

#include <KPluginFactory>
#include <Plasma/ContainmentActions>

#include <QAction>
#include <QApplication>
#include <QButtonGroup>
#include <QElapsedTimer>
#include <QEvent>
#include <QFontDatabase>
#include <QGridLayout>
#include <QIcon>
#include <QImage>
#include <QJsonObject>
#include <QKeyEvent>
#include <QLabel>
#include <QMenu>
#include <QPainter>
#include <QProcess>
#include <QThread>
#include <QToolButton>
#include <QVBoxLayout>
#include <QWidgetAction>

#include <functional>
#include <memory>

namespace
{
const QString kContext = QStringLiteral("keyblade-browser");
const int kColumns = 6;
const int kSpriteZoom = 3; // pixel art, so whole multiples only
const qreal kRimOpacity = 0.3;
// The menu font of the games, when the theme's fonts are installed.
const QString kMenuFont = QStringLiteral("KHMenu");

// Several keyblades are mostly black with black outlines, which vanish on a
// dark menu. Each sprite gets a faint outline, one sprite pixel wide, in the
// menu's text colour: light on dark menus, dark on light ones.
QPixmap spritePixmap(const QImage &sprite, const QColor &rim)
{
    const QImage big = sprite.scaled(sprite.size() * kSpriteZoom, Qt::IgnoreAspectRatio, Qt::FastTransformation)
                           .convertToFormat(QImage::Format_ARGB32_Premultiplied);
    QImage shape = big;
    {
        QPainter painter(&shape);
        painter.setCompositionMode(QPainter::CompositionMode_SourceIn);
        painter.fillRect(shape.rect(), QColor(rim.red(), rim.green(), rim.blue()));
    }
    const int pad = kSpriteZoom;
    QImage grown(big.width() + 2 * pad, big.height() + 2 * pad, QImage::Format_ARGB32_Premultiplied);
    grown.fill(Qt::transparent);
    {
        QPainter painter(&grown);
        for (int dy = -1; dy <= 1; ++dy) {
            for (int dx = -1; dx <= 1; ++dx) {
                painter.drawImage(pad + dx * pad, pad + dy * pad, shape);
            }
        }
    }
    QImage out(grown.size(), QImage::Format_ARGB32_Premultiplied);
    out.fill(Qt::transparent);
    QPainter painter(&out);
    painter.setOpacity(kRimOpacity);
    painter.drawImage(0, 0, grown);
    painter.setOpacity(1.0);
    painter.drawImage(pad, pad, big);
    painter.end();
    return QPixmap::fromImage(out);
}

class KeybladeGrid : public QWidget
{
    Q_OBJECT
public:
    KeybladeGrid(const QList<Keyblades::Keyblade> &keyblades, const QString &current, const QString &problem, QWidget *parent)
        : QWidget(parent)
    {
        auto *layout = new QVBoxLayout(this);
        m_caption = new QLabel(this);
        m_caption->setAlignment(Qt::AlignCenter);
        QFont font = m_caption->font();
        if (QFontDatabase::families().contains(kMenuFont)) {
            font.setFamily(kMenuFont);
        }
        font.setPointSizeF(font.pointSizeF() * 1.35);
        font.setBold(true);
        m_caption->setFont(font);
        layout->addWidget(m_caption);

        if (keyblades.isEmpty()) {
            m_resting = problem;
            m_caption->setText(problem);
            return;
        }

        auto *grid = new QGridLayout;
        grid->setSpacing(2);
        layout->addLayout(grid);
        auto *group = new QButtonGroup(this);
        group->setExclusive(true);
        for (const Keyblades::Keyblade &keyblade : keyblades) {
            auto *button = new QToolButton(this);
            const QImage sprite(keyblade.sprite);
            if (sprite.isNull()) {
                KhLog::warn(kContext, QStringLiteral("keyblade sprite is unreadable"),
                            QJsonObject{{QStringLiteral("keyblade"), keyblade.slug}, {QStringLiteral("path"), keyblade.sprite}});
            }
            const QPixmap pixmap = spritePixmap(sprite, palette().color(QPalette::WindowText));
            QIcon icon;
            // The same picture in every state: a style tinting the selected
            // one would recolour the keyblade.
            for (const QIcon::Mode mode : {QIcon::Normal, QIcon::Active, QIcon::Selected}) {
                icon.addPixmap(pixmap, mode);
            }
            button->setIcon(icon);
            button->setIconSize(pixmap.size());
            button->setAutoRaise(true);
            button->setCheckable(true);
            button->setChecked(keyblade.slug == current);
            button->setToolTip(keyblade.name);
            button->setAccessibleName(keyblade.name);
            button->setFocusPolicy(Qt::StrongFocus);
            button->setProperty("slug", keyblade.slug);
            button->setProperty("keyblade", keyblade.name);
            button->installEventFilter(this);
            group->addButton(button);
            const int index = int(m_buttons.size());
            grid->addWidget(button, index / kColumns, index % kColumns);
            m_buttons.append(button);
            if (keyblade.slug == current) {
                m_resting = keyblade.name;
                setFocusProxy(button);
            }
            connect(button, &QToolButton::clicked, this, [this, slug = keyblade.slug] {
                Q_EMIT chosen(slug);
            });
        }
        if (!focusProxy()) {
            setFocusProxy(m_buttons.first());
        }
        if (m_resting.isEmpty()) {
            m_resting = QStringLiteral("Keyblade");
        }
        m_caption->setText(m_resting);
    }

Q_SIGNALS:
    void chosen(const QString &slug);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override
    {
        auto *button = qobject_cast<QToolButton *>(watched);
        if (!button) {
            return QWidget::eventFilter(watched, event);
        }
        switch (event->type()) {
        case QEvent::Enter:
        case QEvent::FocusIn:
            m_caption->setText(button->property("keyblade").toString());
            break;
        case QEvent::Leave:
            m_caption->setText(m_resting);
            break;
        case QEvent::KeyPress: {
            // Arrow keys walk the grid; the menu would otherwise take them
            // to move between its own entries.
            const int index = int(m_buttons.indexOf(button));
            const int count = int(m_buttons.size());
            int next = -1;
            switch (static_cast<QKeyEvent *>(event)->key()) {
            case Qt::Key_Left:
                next = index - 1;
                break;
            case Qt::Key_Right:
                next = index + 1;
                break;
            case Qt::Key_Up:
                next = index - kColumns;
                break;
            case Qt::Key_Down:
                next = index + kColumns;
                break;
            case Qt::Key_Return:
            case Qt::Key_Enter:
                button->click();
                return true;
            default:
                return QWidget::eventFilter(watched, event);
            }
            if (next >= 0 && next < count) {
                m_buttons.at(next)->setFocus(Qt::TabFocusReason);
            }
            return true;
        }
        default:
            break;
        }
        return QWidget::eventFilter(watched, event);
    }

private:
    QLabel *m_caption = nullptr;
    QList<QToolButton *> m_buttons;
    QString m_resting;
};

class KeybladeGridAction : public QWidgetAction
{
    Q_OBJECT
public:
    explicit KeybladeGridAction(QObject *parent)
        : QWidgetAction(parent)
    {
        setText(QStringLiteral("Keyblades"));
    }

protected:
    // Called each time the menu is put together, so the grid always shows
    // what is installed and chosen now.
    QWidget *createWidget(QWidget *parent) override
    {
        QString problem;
        const QList<Keyblades::Keyblade> keyblades = Keyblades::catalogue(&problem);
        const QString current = Keyblades::chosen();
        KhLog::debug(kContext, QStringLiteral("menu opened"),
                     QJsonObject{{QStringLiteral("keyblades"), int(keyblades.size())}, {QStringLiteral("current"), current}});
        // With no choice recorded the pointer is the main keyblade, which the
        // themes list first.
        const QString shown = !current.isEmpty() || keyblades.isEmpty() ? current : keyblades.first().slug;
        auto *grid = new KeybladeGrid(keyblades, shown, problem, parent);
        connect(grid, &KeybladeGrid::chosen, this, [this, grid](const QString &slug) {
            // Close first: the menu would otherwise stay up while the cursors
            // are rewritten.
            for (QWidget *widget = grid; widget; widget = widget->parentWidget()) {
                if (auto *menu = qobject_cast<QMenu *>(widget)) {
                    menu->close();
                    break;
                }
            }
            equip(slug);
        });
        return grid;
    }

private:
    void equip(const QString &slug)
    {
        if (m_busy) {
            // Kept rather than dropped: the latest choice follows once the
            // current one is on screen.
            m_pending = slug;
            KhLog::info(kContext, QStringLiteral("a keyblade is still being equipped; this choice follows it"),
                        QJsonObject{{QStringLiteral("keyblade"), slug}, {QStringLiteral("equipping"), m_equipping}});
            return;
        }
        m_busy = true;
        m_equipping = slug;
        m_pending.clear();
        m_clock.start();
        KhLog::info(kContext, QStringLiteral("keyblade chosen"), QJsonObject{{QStringLiteral("keyblade"), slug}});
        // Rewriting cursors reads and writes many files; it runs off the
        // shell's thread so the desktop stays responsive. The theme on screen
        // is rewritten and reloaded first; the others are rewritten while it
        // reloads, so the pointer changes after half the work.
        auto stages = std::make_shared<QList<QStringList>>();
        auto first = std::make_shared<Keyblades::Outcome>();
        runOffThread([slug, stages, first] {
            *stages = Keyblades::equipStages();
            *first = Keyblades::equip(slug, stages->value(0));
        }, [this, slug, stages, first] {
            if (first->rewritten == 0) {
                KhLog::error(kContext, QStringLiteral("keyblade not equipped on the theme in use"),
                             QJsonObject{{QStringLiteral("keyblade"), slug}, {QStringLiteral("error"), first->failures.join(QStringLiteral("; "))}});
            } else {
                ++m_outstanding;
                auto *reload = new Keyblades::CursorReload(this);
                connect(reload, &Keyblades::CursorReload::finished, this, [this, reload, slug](bool ok) {
                    reload->deleteLater();
                    KhLog::info(kContext, QStringLiteral("keyblade on screen"),
                                QJsonObject{{QStringLiteral("keyblade"), slug}, {QStringLiteral("reloaded"), ok},
                                            {QStringLiteral("duration_ms"), qint64(m_clock.elapsed())}});
                    stepDone();
                });
                reload->start();
            }
            if (stages->size() > 1) {
                ++m_outstanding;
                const QStringList rest = stages->at(1);
                auto outcome = std::make_shared<Keyblades::Outcome>();
                runOffThread([slug, rest, outcome] {
                    *outcome = Keyblades::equip(slug, rest);
                }, [this, slug, outcome] {
                    if (outcome->rewritten == 0) {
                        KhLog::error(kContext, QStringLiteral("keyblade not equipped on the other themes"),
                                     QJsonObject{{QStringLiteral("keyblade"), slug}, {QStringLiteral("error"), outcome->failures.join(QStringLiteral("; "))}});
                    }
                    stepDone();
                });
            }
            ++m_outstanding;
            stepDone();
        });
    }

    void runOffThread(std::function<void()> work, std::function<void()> then)
    {
        QThread *worker = QThread::create(std::move(work));
        connect(worker, &QThread::finished, this, [worker, then = std::move(then)] {
            worker->deleteLater();
            then();
        });
        worker->start();
    }

    // One part of an equip (the reload, the other themes, the first stage
    // itself) is over; when none is left the next choice may start.
    void stepDone()
    {
        if (--m_outstanding > 0) {
            return;
        }
        KhLog::info(kContext, QStringLiteral("keyblade equipped everywhere"),
                    QJsonObject{{QStringLiteral("keyblade"), m_equipping}, {QStringLiteral("duration_ms"), qint64(m_clock.elapsed())}});
        m_busy = false;
        const QString next = m_pending;
        m_pending.clear();
        if (!next.isEmpty() && next != m_equipping) {
            equip(next);
        }
    }

    bool m_busy = false;
    int m_outstanding = 0;
    QString m_equipping;
    QString m_pending;
    QElapsedTimer m_clock;
};
}

class KeybladeBrowser : public Plasma::ContainmentActions
{
    Q_OBJECT
public:
    KeybladeBrowser(QObject *parent, const QVariantList &args)
        : Plasma::ContainmentActions(parent, args)
        , m_grid(new KeybladeGridAction(this))
        , m_separator(new QAction(this))
        , m_settings(new QAction(QIcon::fromTheme(QStringLiteral("preferences-desktop-cursors")), QStringLiteral("Cursor Settings…"), this))
    {
        m_separator->setSeparator(true);
        connect(m_settings, &QAction::triggered, this, [] {
            const QString program = QStringLiteral("kcmshell6");
            if (!QProcess::startDetached(program, {QStringLiteral("kcm_cursortheme")})) {
                KhLog::error(kContext, QStringLiteral("cannot open cursor settings"), QJsonObject{{QStringLiteral("tool"), program}});
            }
        });
        KhLog::debug(kContext, QStringLiteral("mouse action loaded"));
    }

    QList<QAction *> contextualActions() override
    {
        return {m_grid, m_separator, m_settings};
    }

private:
    KeybladeGridAction *m_grid;
    QAction *m_separator;
    QAction *m_settings;
};

K_PLUGIN_CLASS_WITH_JSON(KeybladeBrowser, "metadata.json")

#include "browser.moc"
