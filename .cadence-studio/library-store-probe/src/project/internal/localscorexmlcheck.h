// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026 Cadence Studio contributors
#pragma once

#include <QByteArray>
#include <QXmlStreamReader>

namespace mu::project {
// A cheap structural gate before catalogue metadata extraction. This is not a
// musical validator or a replacement for MuseScore's native score reader.
inline bool isNativeScoreXml(const QByteArray& xml)
{
    if (xml.trimmed().isEmpty()) {
        return false;
    }
    QXmlStreamReader reader(xml);
    bool rootSeen = false;
    bool scoreSeen = false;
    bool legacyVersion = false;
    int depth = 0;
    while (!reader.atEnd()) {
        const auto token = reader.readNext();
        if (token == QXmlStreamReader::DTD) {
            return false;
        }
        if (token == QXmlStreamReader::StartElement) {
            if (!rootSeen) {
                if (reader.name() != QStringLiteral("museScore")) {
                    return false;
                }
                const QString version = reader.attributes().value(QStringLiteral("version")).toString().trimmed();
                if (version.isEmpty()) {
                    return false;
                }
                rootSeen = true;
                bool numeric = false;
                legacyVersion = version.section(QLatin1Char('.'), 0, 0).toInt(&numeric) == 1 && numeric;
            } else if (depth == 1) {
                const QString expected = legacyVersion ? QStringLiteral("Staff") : QStringLiteral("Score");
                if (reader.name() == expected) {
                    scoreSeen = true;
                }
            }
            ++depth;
        } else if (token == QXmlStreamReader::EndElement) {
            --depth;
        }
    }
    return rootSeen && scoreSeen && depth == 0 && !reader.hasError();
}
}
