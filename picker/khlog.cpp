#include "khlog.h"

#include <QByteArray>
#include <QDateTime>
#include <QJsonDocument>
#include <QUuid>

#include <cstdio>
#include <mutex>

namespace
{
const QString &runId()
{
    static const QString id = QUuid::createUuid().toString(QUuid::Id128).left(12);
    return id;
}

const char *levelName(KhLog::Level level)
{
    switch (level) {
    case KhLog::Level::Debug:
        return "debug";
    case KhLog::Level::Info:
        return "info";
    case KhLog::Level::Warn:
        return "warn";
    case KhLog::Level::Error:
        return "error";
    }
    return "info";
}

void emitLine(const QJsonObject &record)
{
    static std::mutex lock;
    const QByteArray line = QJsonDocument(record).toJson(QJsonDocument::Compact) + '\n';
    const std::lock_guard<std::mutex> guard(lock);
    std::fwrite(line.constData(), 1, size_t(line.size()), stderr);
    std::fflush(stderr);
}

QJsonObject base(const char *level, const QString &context, const QString &message)
{
    QJsonObject record;
    record[QStringLiteral("timestamp")] = QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs);
    record[QStringLiteral("level")] = QString::fromLatin1(level);
    record[QStringLiteral("context")] = context;
    record[QStringLiteral("message")] = message;
    record[QStringLiteral("run_id")] = runId();
    return record;
}

int threshold()
{
    static const int value = [] {
        const QByteArray raw = qgetenv("KH_LOG_LEVEL").toLower();
        if (raw.isEmpty() || raw == "info") {
            return 20;
        }
        if (raw == "debug") {
            return 10;
        }
        if (raw == "warn") {
            return 30;
        }
        if (raw == "error") {
            return 40;
        }
        QJsonObject record = base("warn", QStringLiteral("log"), QStringLiteral("invalid KH_LOG_LEVEL, falling back to info"));
        record[QStringLiteral("value")] = QString::fromLocal8Bit(raw);
        emitLine(record);
        return 20;
    }();
    return value;
}
}

void KhLog::write(Level level, const QString &context, const QString &message, const QJsonObject &fields)
{
    if (int(level) < threshold()) {
        return;
    }
    QJsonObject record = base(levelName(level), context, message);
    for (auto it = fields.begin(); it != fields.end(); ++it) {
        record[it.key()] = it.value();
    }
    emitLine(record);
}
