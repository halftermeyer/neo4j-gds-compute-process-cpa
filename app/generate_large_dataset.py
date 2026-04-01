"""
Generate a large realistic DAG dataset for CPA testing.

Usage:
    python generate_large_dataset.py [--layers 20] [--width 30] [--seed 42]

Default: ~500 nodes, ~3000 edges across 20 layers of 25 tasks each.
"""

import argparse
import random
from neo4j import GraphDatabase
import os

# Phase names by layer range — gives realistic task names
PHASE_PREFIXES = [
    (0, 2, "Extract"),
    (2, 5, "Clean"),
    (5, 8, "Validate"),
    (8, 11, "Enrich"),
    (11, 14, "Compute"),
    (14, 17, "Aggregate"),
    (17, 19, "Report"),
    (19, 100, "Finalize"),
]

DOMAIN_SUFFIXES = [
    "MarketData", "Positions", "Trades", "Counterparties", "RiskFactors",
    "Collateral", "Limits", "PnL", "Cashflows", "Settlements",
    "Derivatives", "Equities", "FixedIncome", "FX", "Commodities",
    "CreditRisk", "MarketRisk", "OpRisk", "LiquidityRisk", "CounterpartyRisk",
    "VaR", "CVA", "DVA", "FVA", "PFE",
    "StressTest", "Greeks", "Margin", "Capital", "Exposure",
    "Regulatory", "Internal", "Dashboard", "Alert", "Signoff",
]


def get_task_name(layer, index, num_layers):
    prefix = "Task"
    for lo, hi, p in PHASE_PREFIXES:
        frac_lo = lo / 20
        frac_hi = hi / 20
        layer_frac = layer / num_layers
        if frac_lo <= layer_frac < frac_hi:
            prefix = p
            break
    suffix = DOMAIN_SUFFIXES[index % len(DOMAIN_SUFFIXES)]
    return f"{prefix}_{suffix}_{layer}_{index}"


def generate(num_layers=20, base_width=25, seed=42, done_fraction=0.3,
             intra_connect_prob=0.15, cross_layer_prob=0.03):
    rng = random.Random(seed)

    nodes = []  # list of (uid, name, duration, layer)
    edges = []  # list of (source_uid, target_uid)
    uid_counter = 1

    layer_nodes = {}  # layer -> list of uids

    for layer in range(num_layers):
        # Vary width per layer: wider in the middle, narrower at edges
        progress = layer / (num_layers - 1)
        width_factor = 1.0 + 1.2 * (1.0 - abs(2 * progress - 1))  # peaks at middle
        width = max(3, int(base_width * width_factor * rng.uniform(0.8, 1.2)))

        layer_uids = []
        for i in range(width):
            uid = uid_counter
            uid_counter += 1
            name = get_task_name(layer, i, num_layers)
            # Duration: later layers tend to have longer tasks
            base_dur = 1.0 + progress * 10.0
            duration = round(rng.uniform(base_dur * 0.3, base_dur * 2.0), 1)
            nodes.append((uid, name, duration, layer))
            layer_uids.append(uid)

        layer_nodes[layer] = layer_uids

        # Create edges from previous layer
        if layer > 0:
            prev_uids = layer_nodes[layer - 1]
            for uid in layer_uids:
                # Each node connects to 1-4 nodes in the previous layer
                num_parents = rng.randint(1, min(4, len(prev_uids)))
                parents = rng.sample(prev_uids, num_parents)
                for parent_uid in parents:
                    edges.append((parent_uid, uid))

            # Extra intra-layer connections from the same previous layer
            # (creates diamonds)
            for uid in layer_uids:
                for prev_uid in prev_uids:
                    if (prev_uid, uid) not in set(edges[-len(layer_uids) * 4:]):
                        if rng.random() < intra_connect_prob:
                            edges.append((prev_uid, uid))

        # Cross-layer connections (skip connections, 2+ layers back)
        if layer > 1:
            for uid in layer_uids:
                for prev_layer in range(max(0, layer - 3), layer - 1):
                    for prev_uid in layer_nodes[prev_layer]:
                        if rng.random() < cross_layer_prob:
                            edges.append((prev_uid, uid))

    # Deduplicate edges
    edges = list(set(edges))

    # Mark early nodes as Done
    done_uids = set()
    for uid, name, dur, layer in nodes:
        layer_frac = layer / (num_layers - 1)
        # High chance of done for early layers, tapering off
        if rng.random() < done_fraction * (1.0 - layer_frac) * 2:
            done_uids.add(uid)

    # Ensure consistency: if a node is Done, all its ancestors should be Done too
    # Build adjacency for ancestor lookup
    children_of = {}
    parents_of = {}
    for src, tgt in edges:
        children_of.setdefault(src, []).append(tgt)
        parents_of.setdefault(tgt, []).append(src)

    # If a node is Done, mark all ancestors as Done
    def mark_ancestors_done(uid):
        stack = [uid]
        while stack:
            n = stack.pop()
            for p in parents_of.get(n, []):
                if p not in done_uids:
                    done_uids.add(p)
                    stack.append(p)

    for uid in list(done_uids):
        mark_ancestors_done(uid)

    return nodes, edges, done_uids


def load_to_neo4j(nodes, edges, done_uids, uri, user, password):
    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        # Clean
        session.run("MATCH (n) DETACH DELETE n")

        # Create index for fast lookups
        session.run("CREATE INDEX task_uid IF NOT EXISTS FOR (n:Task) ON (n.uid)")

        # Batch create nodes
        batch_size = 500
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            params = [{
                "uid": uid, "name": name, "duration": dur,
                "done": uid in done_uids
            } for uid, name, dur, layer in batch]
            session.run("""
                UNWIND $batch AS p
                CALL (p) {
                    CREATE (n:Task {uid: p.uid, name: p.name, duration: p.duration})
                    WITH n, p
                    WHERE p.done
                    SET n:Done
                }
            """, batch=params)

        # Batch create edges
        for i in range(0, len(edges), batch_size):
            batch = edges[i:i + batch_size]
            params = [{"src": s, "tgt": t} for s, t in batch]
            session.run("""
                UNWIND $batch AS e
                MATCH (a:Task {uid: e.src})
                MATCH (b:Task {uid: e.tgt})
                CREATE (a)-[:PRECEDES]->(b)
            """, batch=params)

    driver.close()
    return len(nodes), len(edges), len(done_uids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate large CPA dataset")
    parser.add_argument("--layers", type=int, default=20, help="Number of layers (default: 20)")
    parser.add_argument("--width", type=int, default=25, help="Base width per layer (default: 25)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--done", type=float, default=0.3, help="Fraction of done tasks (default: 0.3)")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD", "pierre!!!"))
    args = parser.parse_args()

    print(f"Generating dataset: {args.layers} layers, ~{args.width} width, seed={args.seed}")
    nodes, edges, done_uids = generate(
        num_layers=args.layers, base_width=args.width,
        seed=args.seed, done_fraction=args.done,
    )
    print(f"Generated: {len(nodes)} nodes, {len(edges)} edges, {len(done_uids)} done")

    print(f"Loading into Neo4j at {args.uri}...")
    n, e, d = load_to_neo4j(nodes, edges, done_uids, args.uri, args.user, args.password)
    print(f"Loaded: {n} nodes, {e} edges, {d} done")
