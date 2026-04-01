// ── Scope: collect ancestors of the scoping node ─────────────────
// Uses apoc.path.subgraphNodes with NODE_GLOBAL uniqueness.
// This avoids exponential path enumeration on diamond DAGs.
//
// This is a standalone illustration — in practice, scoping is folded
// directly into the projection query (02_project_subgraph.cypher).

MATCH (scopingNode:Task {name: "T_G"})
CALL apoc.path.subgraphNodes(scopingNode, {
  relationshipFilter: "<PRECEDES",
  minLevel: 0
})
YIELD node AS n
RETURN n.name AS ancestor
