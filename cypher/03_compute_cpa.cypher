// ── Compute CPA — longest path per frontier node ─────────────────
// Runs gds.dag.longestPath on the scoped, node-split projection.
// Post-processing: maps virtual IDs back to real nodes, filters to
// frontier sinks only, and reconstructs the critical path.

CALL gds.dag.longestPath.stream('cpa_graph', {
  relationshipWeightProperty: "duration"
})
YIELD sourceNode, targetNode, totalCost, nodeIds

// Map virtual IDs back to real nodes via uid property
MATCH (source:Task {uid: sourceNode / 2})
MATCH (frontier:Task {uid: targetNode / 2})
WITH
  targetNode,
  source, frontier, totalCost,
  [id IN nodeIds WHERE id % 2 = 0 |
    head(collect { MATCH (n:Task {uid: id / 2}) RETURN n.name })
  ] AS path

// dag.longestPath yields a row per reachable node, not just sinks.
// Each real node n has two virtual IDs: n_in (2k, even) and n_out (2k+1, odd).
// The path ending at n_in includes n's duration; the path ending at n_out does not.
// We keep only even targetNodes (n_in) to count the full duration of the frontier node.
FILTER targetNode % 2 = 0
AND source.name = "T_G"                                          // keep only paths from our scoping node
AND NOT EXISTS { (frontier)<-[:PRECEDES]-(upstream:!Done) }      // to frontier nodes only

RETURN
  source.name    AS scopingNode,
  frontier.name  AS criticalFrontier,
  totalCost      AS criticalPathDuration,
  path           AS criticalPath
ORDER BY totalCost DESC
