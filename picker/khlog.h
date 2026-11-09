// Structured logging: one JSON object per line on stderr, with the same
// fields as the Python tools (timestamp, level, context, message, run_id, and
// error where something failed). KH_LOG_LEVEL sets the threshold.
#pragma once

#include <QJsonObject>
#include <QString>

namespace KhLog
{
enum class Level { Debug = 10, Info = 20, Warn = 30, Error = 40 };

void write(Level level, const QString &context, const QString &message, const QJsonObject &fields = {});

inline void debug(const QString &context, const QString &message, const QJsonObject &fields = {})
{
    write(Level::Debug, context, message, fields);
}
inline void info(const QString &context, const QString &message, const QJsonObject &fields = {})
{
    write(Level::Info, context, message, fields);
}
inline void warn(const QString &context, const QString &message, const QJsonObject &fields = {})
{
    write(Level::Warn, context, message, fields);
}
inline void error(const QString &context, const QString &message, const QJsonObject &fields = {})
{
    write(Level::Error, context, message, fields);
}
}
