// ── Project filtered ancestor subgraph into GDS ──────────────────
// Combines: ancestor scoping (APOC), completion filtering,
// virtual node splitting, and GDS projection — all in one pass.
//
// The graph is projected in REVERSE so that the scoping node becomes
// the source for gds.dag.longestPath, making results filterable.

MATCH (scopingNode:Task {name: "T_G"})

// 1. Collect ancestor nodes
CALL apoc.path.subgraphNodes(scopingNode, {
  relationshipFilter: "<PRECEDES",
  minLevel: 0
})
YIELD node AS n

// 2. Filter out completed tasks
FILTER NOT n:Done

// 3. Find edges — OPTIONAL MATCH ensures frontier nodes still appear
//    even when all their upstreams are Done (no connectivity edge needed)
OPTIONAL MATCH (n)<-[:PRECEDES]-(upstream:!Done)

// 4. Node splitting — using n.uid (integer) as GDS projection requires NODE | INTEGER
//    n_in  = 2 * uid     (entry point)
//    n_out = 2 * uid + 1 (exit point)
WITH
  n, upstream,
  2 * n.uid              AS n_in,
  2 * n.uid + 1          AS n_out,
  2 * upstream.uid + 1   AS upstream_out,
  n.duration             AS weight

// 5. Emit both virtual edge types
// Duration edge always emitted; connectivity edge only when upstream exists
CALL (*) {
  RETURN n_in  AS source, n_out AS target, weight AS w          // duration edge — always
  UNION
  WITH upstream_out WHERE upstream_out IS NOT NULL
  RETURN upstream_out AS source, n_in AS target, 0.0 AS w       // connectivity edge — frontier nodes excluded
}
WITH DISTINCT source, target, w

// 6. Project into GDS (reversed: scoping node becomes source for longestPath)
WITH gds.graph.project(
  'cpa_graph',
  target,
  source,
  { relationshipProperties: { duration: w } }
) AS g
RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
