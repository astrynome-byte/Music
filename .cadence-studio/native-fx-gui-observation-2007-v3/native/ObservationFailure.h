// SPDX-License-Identifier: GPL-3.0-only
// Metadata-only observer diagnostics. No window/control text is captured here.
#pragma once
#include <cstdint>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include "ObservationGraph.h"

namespace cadence_observation {
class FirstFailure {
public:
    bool record(const std::string& phase, const std::string& operation,
                std::int32_t hresult, const RuntimeId& ownedRuntimeId,
                const char* origin = "provider_hresult")
    {
        if (m_calls != std::numeric_limits<std::uint32_t>::max()) ++m_calls;
        if (m_present) return false;
        m_present = true;
        m_phase = phase.substr(0, 80);
        m_operation = operation.substr(0, 120);
        m_origin = std::string(origin).substr(0, 32);
        m_hresult = hresult;
        // The caller passes only a previously PID-verified identity. Unknown or
        // foreign elements use an empty identity; no provider property is read.
        if (ownedRuntimeId.size() <= Graph::maxIdParts) m_id = ownedRuntimeId;
        return true;
    }

    bool present() const { return m_present; }
    std::string json() const
    {
        if (!m_present) return "null";
        std::ostringstream hex;
        hex << "0x" << std::hex << std::setfill('0') << std::setw(8)
            << static_cast<std::uint32_t>(m_hresult);
        std::string out = "{\"phase\":" + quoted(m_phase)
            + ",\"operation\":" + quoted(m_operation)
            + ",\"hresult\":" + std::to_string(m_hresult)
            + ",\"hresult_hex\":" + quoted(hex.str())
            + ",\"hresult_origin\":" + quoted(m_origin)
            + ",\"runtime_id\":[";
        for (std::size_t i = 0; i < m_id.size(); ++i) {
            if (i) out += ',';
            out += std::to_string(m_id[i]);
        }
        return out + "],\"recorded_failure_calls\":" + std::to_string(m_calls) + '}';
    }

private:
    static std::string quoted(const std::string& value)
    {
        std::string out = "\"";
        for (unsigned char c : value) {
            if (c == '\\' || c == '"') { out += '\\'; out += static_cast<char>(c); }
            else if (c == '\n') out += "\\n";
            else if (c == '\r') out += "\\r";
            else if (c == '\t') out += "\\t";
            else if (c < 32) out += '?';
            else out += static_cast<char>(c);
        }
        return out + '"';
    }
    bool m_present = false;
    std::uint32_t m_calls = 0;
    std::int32_t m_hresult = 0;
    std::string m_phase, m_operation, m_origin;
    RuntimeId m_id;
};
}
