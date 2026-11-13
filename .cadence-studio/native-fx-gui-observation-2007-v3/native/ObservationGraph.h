// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstddef>
#include <utility>
#include <set>
#include <string>
#include <vector>

namespace cadence_observation {
using RuntimeId = std::vector<int>;
struct Edge {
    RuntimeId from, to;
    std::string relation;
    bool cycle = false, duplicate = false;
};
enum class Visit { first, duplicate, cycle, invalid, limit };
// RuntimeIds are per-snapshot opaque UIA identities. Unknown/empty identities
// cannot participate in deduplication and must block the observation.
class Graph {
public:
    static constexpr std::size_t maxNodes = 1200, maxEdges = 3600, maxIdParts = 64;
    Visit enter(const RuntimeId& id, const RuntimeId& parent, const std::string& relation) {
        if (id.empty() || id.size() > maxIdParts) return Visit::invalid;
        if (edges.size() >= maxEdges) return Visit::limit;
        const bool inPath = active.count(id) != 0;
        const bool seen = visited.count(id) != 0;
        edges.push_back({parent, id, relation, inPath, seen});
        if (inPath) { ++cycleEdges; return Visit::cycle; }
        if (seen) { ++duplicateEdges; return Visit::duplicate; }
        if (visited.size() >= maxNodes) return Visit::limit;
        visited.insert(id); active.insert(id); return Visit::first;
    }
    void leave(const RuntimeId& id) { active.erase(id); }
    bool siblingRepeat(const RuntimeId& parent, const RuntimeId& id) {
        if (id.empty() || id.size() > maxIdParts || edges.size() >= maxEdges) return false;
        edges.push_back({parent,id,"repeated_sibling",true,true}); ++cycleEdges; return true;
    }
    std::size_t uniqueNodes() const { return visited.size(); }
    std::vector<Edge> edges;
    std::size_t cycleEdges = 0, duplicateEdges = 0;
private:
    std::set<RuntimeId> visited, active;
};
class ActiveScope {
public:
    ActiveScope(Graph& graph, RuntimeId id): m_graph(graph), m_id(std::move(id)) {}
    ~ActiveScope() { m_graph.leave(m_id); }
private:
    Graph& m_graph;
    RuntimeId m_id;
};
}
