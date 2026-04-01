from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from neo4j import GraphDatabase
import os

app = FastAPI()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pierre!!!")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/api/graph")
def get_graph():
    """Return all Task nodes and PRECEDES relationships."""
    with driver.session() as session:
        result = session.run("""
            MATCH (n:Task)
            OPTIONAL MATCH (n)-[r:PRECEDES]->(m:Task)
            RETURN n.uid AS uid, n.name AS name, n.duration AS duration,
                   n:Done AS done, m.uid AS target_uid
        """)
        nodes = {}
        edges = []
        for record in result:
            uid = record["uid"]
            if uid not in nodes:
                nodes[uid] = {
                    "uid": uid,
                    "name": record["name"],
                    "duration": record["duration"],
                    "done": record["done"],
                }
            if record["target_uid"] is not None:
                edges.append({"source": uid, "target": record["target_uid"]})
        return {"nodes": list(nodes.values()), "edges": edges}


@app.post("/api/complete/{uid}")
def complete_task(uid: int):
    """Mark a task and all its ancestors (upstream) as Done."""
    with driver.session() as session:
        result = session.run("""
            MATCH (target:Task {uid: $uid})
            CALL apoc.path.subgraphNodes(target, {
                relationshipFilter: "<PRECEDES",
                minLevel: 0
            })
            YIELD node AS n
            WHERE NOT n:Done
            SET n:Done
            RETURN count(n) AS completed
        """, uid=uid)
        record = result.single()
        return {"completed": record["completed"]}


@app.post("/api/uncomplete/{uid}")
def uncomplete_task(uid: int):
    """Remove Done label from a task and all its descendants (downstream)."""
    with driver.session() as session:
        result = session.run("""
            MATCH (target:Task {uid: $uid})
            CALL apoc.path.subgraphNodes(target, {
                relationshipFilter: "PRECEDES>",
                minLevel: 0
            })
            YIELD node AS n
            WHERE n:Done
            REMOVE n:Done
            RETURN count(n) AS uncompleted
        """, uid=uid)
        record = result.single()
        return {"uncompleted": record["uncompleted"]}


@app.get("/api/cpa/{uid}")
def compute_cpa(uid: int):
    """Compute CPA for a given scoping node. Returns longest paths to frontier nodes."""
    graph_name = f"cpa_{uid}"
    with driver.session() as session:
        # Drop existing projection if any
        try:
            session.run("CALL gds.graph.drop($name, false)", name=graph_name)
        except Exception:
            pass

        # Project scoped subgraph with virtual node splitting
        proj = session.run("""
            MATCH (scopingNode:Task {uid: $uid})
            CALL apoc.path.subgraphNodes(scopingNode, {
                relationshipFilter: "<PRECEDES",
                minLevel: 0
            })
            YIELD node AS n
            FILTER NOT n:Done
            OPTIONAL MATCH (n)<-[:PRECEDES]-(upstream:!Done)
            WITH
                n, upstream,
                2 * n.uid AS n_in,
                2 * n.uid + 1 AS n_out,
                2 * upstream.uid + 1 AS upstream_out,
                n.duration AS weight
            CALL (*) {
                RETURN n_in AS source, n_out AS target, weight AS w
                UNION
                WITH upstream_out WHERE upstream_out IS NOT NULL
                RETURN upstream_out AS source, n_in AS target, 0.0 AS w
            }
            WITH DISTINCT source, target, w
            WITH gds.graph.project(
                $graph_name,
                target,
                source,
                { relationshipProperties: { duration: w } }
            ) AS g
            RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
        """, uid=uid, graph_name=graph_name)
        proj_record = proj.single()
        if proj_record is None:
            raise HTTPException(status_code=400, detail="Node is Done or not found")

        # Run longestPath
        result = session.run("""
            CALL gds.dag.longestPath.stream($graph_name, {
                relationshipWeightProperty: "duration"
            })
            YIELD sourceNode, targetNode, totalCost, nodeIds
            MATCH (source:Task {uid: sourceNode / 2})
            MATCH (frontier:Task {uid: targetNode / 2})
            WITH
                targetNode,
                source, frontier, totalCost,
                [id IN nodeIds WHERE id % 2 = 0 |
                    head(collect { MATCH (n:Task {uid: id / 2}) RETURN n.uid })
                ] AS pathUids,
                [id IN nodeIds WHERE id % 2 = 0 |
                    head(collect { MATCH (n:Task {uid: id / 2}) RETURN n.name })
                ] AS pathNames
            FILTER targetNode % 2 = 0
            AND source.uid = $uid
            AND NOT EXISTS { (frontier)<-[:PRECEDES]-(upstream:!Done) }
            RETURN
                source.name AS scopingNode,
                frontier.name AS criticalFrontier,
                frontier.uid AS frontierUid,
                totalCost AS criticalPathDuration,
                pathUids AS pathUids,
                pathNames AS pathNames
            ORDER BY totalCost DESC
        """, graph_name=graph_name, uid=uid)

        paths = []
        for record in result:
            paths.append({
                "scopingNode": record["scopingNode"],
                "criticalFrontier": record["criticalFrontier"],
                "frontierUid": record["frontierUid"],
                "criticalPathDuration": record["criticalPathDuration"],
                "pathUids": record["pathUids"],
                "pathNames": record["pathNames"],
            })

        # Cleanup
        session.run("CALL gds.graph.drop($name, false)", name=graph_name)

        return {"paths": paths}


@app.post("/api/reset")
def reset_dataset():
    """Reload the dataset from the Cypher file."""
    cypher_path = os.path.join(os.path.dirname(__file__), "generate_dataset.cypher")
    with open(cypher_path) as f:
        cypher = f.read()
    with driver.session() as session:
        for statement in cypher.split(";"):
            statement = statement.strip()
            if statement:
                session.run(statement)
    return {"status": "ok"}


@app.post("/api/reset-large")
def reset_large_dataset(layers: int = 20, width: int = 25, seed: int = 42,
                        done: float = 0.3, density: float = 0.5):
    """Generate and load a large procedural dataset."""
    from generate_large_dataset import generate, load_to_neo4j
    nodes, edges, done_uids = generate(
        num_layers=layers, base_width=width, seed=seed,
        done_fraction=done, density=density,
    )
    n, e, d = load_to_neo4j(
        nodes, edges, done_uids, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    )
    return {"nodes": n, "edges": e, "done": d}


@app.on_event("shutdown")
def shutdown():
    driver.close()
