// ── Create toy graph ──────────────────────────────────────────────
// Two chained diamonds, a sibling, a cousin branch, and an unrelated branch.
// Diamonds illustrate exponential fan-out (Trap 2).
// Sibling, cousin, and unrelated branch illustrate scoping (Trap 1).

CREATE
  // Main process chain
  (tA:Task:Done {uid: 1,  name: "T_A", duration: 2.0}),
  (tB:Task      {uid: 2,  name: "T_B", duration: 1.0}),
  (tC:Task      {uid: 3,  name: "T_C", duration: 3.0}),  // ← first bottleneck
  (tD:Task      {uid: 4,  name: "T_D", duration: 1.0}),
  (tE:Task      {uid: 5,  name: "T_E", duration: 0.5}),
  (tF:Task      {uid: 6,  name: "T_F", duration: 2.0}),  // ← second bottleneck
  (tG:Task      {uid: 7,  name: "T_G", duration: 0.5}),  // ← scoping node

  // Diamond 1: T_A fans out to T_B and T_C, converges on T_D
  (tA)-[:PRECEDES]->(tB),
  (tA)-[:PRECEDES]->(tC),
  (tB)-[:PRECEDES]->(tD),
  (tC)-[:PRECEDES]->(tD),

  // Diamond 2: T_D fans out to T_E and T_F, converges on T_G
  (tD)-[:PRECEDES]->(tE),
  (tD)-[:PRECEDES]->(tF),
  (tE)-[:PRECEDES]->(tG),
  (tF)-[:PRECEDES]->(tG),

  // Sibling: T_F also precedes T_H — same parent as T_G, not an ancestor of T_G
  (tH:Task {uid: 8,  name: "T_H", duration: 1.5}),
  (tF)-[:PRECEDES]->(tH),

  // Cousin branch: T_D also leads to T_I → T_J — ancestor in common, not ancestor of T_G
  (tI:Task {uid: 9,  name: "T_I", duration: 1.0}),
  (tJ:Task {uid: 10, name: "T_J", duration: 0.5}),
  (tD)-[:PRECEDES]->(tI),
  (tI)-[:PRECEDES]->(tJ),

  // Unrelated branch — separate WCC, no path to T_G whatsoever
  (tX:Task {uid: 11, name: "T_X", duration: 1.0}),
  (tY:Task {uid: 12, name: "T_Y", duration: 1.0}),
  (tX)-[:PRECEDES]->(tY)
