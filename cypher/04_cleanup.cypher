// ── Clean up — drop in-memory projection ─────────────────────────
// MUST be called after each CPA computation.
// The graph is dynamic; the next query needs a fresh projection.
// In production, wrap steps 02–04 in an APOC procedure so the drop
// is guaranteed even on failure.

CALL gds.graph.drop('cpa_graph')
