from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from neo4j import GraphDatabase
import os
import time

app = FastAPI()

# Connection state — set via /api/connect
_state = {"driver": None, "uri": None, "user": None, "password": None}


def get_driver():
    if _state["driver"] is None:
        raise HTTPException(status_code=503, detail="Not connected to Neo4j")
    return _state["driver"]


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


class ConnectRequest(BaseModel):
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""


@app.post("/api/connect")
def connect(req: ConnectRequest):
    """Connect to a Neo4j instance. Loads 60-task dataset if DB is empty."""
    # Close previous connection if any
    if _state["driver"]:
        try:
            _state["driver"].close()
        except Exception:
            pass

    try:
        driver = GraphDatabase.driver(req.uri, auth=(req.user, req.password))
        # Verify connectivity
        with driver.session() as session:
            session.run("RETURN 1").consume()
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    _state["driver"] = driver
    _state["uri"] = req.uri
    _state["user"] = req.user
    _state["password"] = req.password

    # Auto-load 60-task dataset if DB is empty
    with driver.session() as session:
        result = session.run("MATCH (n:Task) RETURN count(n) AS c")
        if result.single()["c"] == 0:
            cypher_path = os.path.join(os.path.dirname(__file__), "generate_dataset.cypher")
            with open(cypher_path) as f:
                cypher = f.read()
            for statement in cypher.split(";"):
                statement = statement.strip()
                if statement:
                    session.run("CYPHER 25 " + statement)

    return {"status": "ok", "uri": req.uri, "user": req.user}


@app.get("/api/status")
def status():
    """Check if connected."""
    if _state["driver"]:
        return {"connected": True, "uri": _state["uri"], "user": _state["user"]}
    return {"connected": False}


@app.get("/api/tasks")
def get_tasks():
    """Lightweight: return just uid, name, done for search/index."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""CYPHER 25
            MATCH (n:Task)
            RETURN n.uid AS uid, n.name AS name, n:Done AS done
        """)
        return {"tasks": [{"uid": r["uid"], "name": r["name"], "done": r["done"]} for r in result]}


@app.get("/api/expand/{uid}")
def expand_node(uid: int, direction: str = "both"):
    """Return a node + its neighbors + edges between them. direction: upstream|downstream|both"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""CYPHER 25
            MATCH (center:Task {uid: $uid})
            OPTIONAL MATCH (center)<-[:PRECEDES]-(upstream:Task)
            OPTIONAL MATCH (center)-[:PRECEDES]->(downstream:Task)
            WITH center,
                 collect(DISTINCT upstream) AS ups,
                 collect(DISTINCT downstream) AS downs
            WITH center, ups, downs,
                 CASE $direction
                   WHEN 'upstream' THEN [center] + ups
                   WHEN 'downstream' THEN [center] + downs
                   ELSE [center] + ups + downs
                 END AS neighborhood
            UNWIND neighborhood AS n
            WITH DISTINCT n, collect(DISTINCT n.uid) AS allUids
            // Not usable directly — re-collect
            WITH collect(DISTINCT n) AS nodes
            WITH nodes, [n IN nodes | n.uid] AS allUids
            UNWIND nodes AS n
            OPTIONAL MATCH (n)-[:PRECEDES]->(m:Task)
            WHERE m.uid IN allUids
            RETURN DISTINCT
              n.uid AS uid, n.name AS name, n.duration AS duration, n:Done AS done,
              collect(DISTINCT m.uid) AS targets
        """, uid=uid, direction=direction)
        nodes = []
        edges = []
        for r in result:
            nodes.append({"uid": r["uid"], "name": r["name"], "duration": r["duration"], "done": r["done"]})
            for t in r["targets"]:
                if t is not None:
                    edges.append({"source": r["uid"], "target": t})
        return {"nodes": nodes, "edges": edges}


@app.get("/api/expand-deep/{uid}")
def expand_deep(uid: int, direction: str = "upstream"):
    """Return all transitive upstream or downstream nodes + edges. direction: upstream|downstream"""
    driver = get_driver()
    rel_filter = "<PRECEDES" if direction == "upstream" else "PRECEDES>"
    with driver.session() as session:
        result = session.run("""CYPHER 25
            MATCH (center:Task {uid: $uid})
            CALL apoc.path.subgraphNodes(center, {
                relationshipFilter: $relFilter,
                minLevel: 0
            })
            YIELD node AS n
            WITH collect(n) AS nodes, [n IN collect(n) | n.uid] AS allUids
            UNWIND nodes AS n
            OPTIONAL MATCH (n)-[:PRECEDES]->(m:Task)
            WHERE m.uid IN allUids
            RETURN DISTINCT
              n.uid AS uid, n.name AS name, n.duration AS duration, n:Done AS done,
              collect(DISTINCT m.uid) AS targets
        """, uid=uid, relFilter=rel_filter)
        nodes = []
        edges = []
        for r in result:
            nodes.append({"uid": r["uid"], "name": r["name"], "duration": r["duration"], "done": r["done"]})
            for t in r["targets"]:
                if t is not None:
                    edges.append({"source": r["uid"], "target": t})
        return {"nodes": nodes, "edges": edges}


@app.get("/api/graph")
def get_graph():
    """Return all Task nodes and PRECEDES relationships (use for Show All on small graphs)."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""CYPHER 25
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
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""CYPHER 25
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
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""CYPHER 25
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
    driver = get_driver()
    graph_name = f"cpa_{uid}"
    t0 = time.perf_counter()
    with driver.session() as session:
        # Drop existing projection if any
        try:
            session.run("CALL gds.graph.drop($name, false)", name=graph_name)
        except Exception:
            pass

        # Project scoped subgraph with virtual node splitting
        proj = session.run("""CYPHER 25
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
        result = session.run("""CYPHER 25
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

        # Collect full ancestor subgraph (non-Done) for highlighting
        ancestor_result = session.run("""CYPHER 25
            MATCH (scopingNode:Task {uid: $uid})
            CALL apoc.path.subgraphNodes(scopingNode, {
                relationshipFilter: "<PRECEDES",
                minLevel: 0
            })
            YIELD node AS n
            WHERE NOT n:Done
            WITH collect(n.uid) AS ancestorUids
            UNWIND ancestorUids AS aUid
            MATCH (a:Task {uid: aUid})
            OPTIONAL MATCH (a)<-[:PRECEDES]-(b:Task&!Done)
            WHERE b.uid IN ancestorUids
            RETURN ancestorUids,
                   collect(DISTINCT [b.uid, a.uid]) AS ancestorEdges
        """, uid=uid)
        anc = ancestor_result.single()
        ancestor_uids = anc["ancestorUids"] if anc else []
        ancestor_edges = [[e[0], e[1]] for e in (anc["ancestorEdges"] if anc else []) if e[0] is not None]

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {"paths": paths, "ancestorUids": ancestor_uids, "ancestorEdges": ancestor_edges, "elapsed_ms": elapsed_ms}


@app.post("/api/reset")
def reset_dataset():
    """Reload the dataset from the Cypher file."""
    driver = get_driver()
    cypher_path = os.path.join(os.path.dirname(__file__), "generate_dataset.cypher")
    with open(cypher_path) as f:
        cypher = f.read()
    with driver.session() as session:
        for statement in cypher.split(";"):
            statement = statement.strip()
            if statement:
                session.run("CYPHER 25 " + statement)
    return {"status": "ok"}


@app.post("/api/reset-large")
def reset_large_dataset(layers: int = 20, width: int = 25, seed: int = 42,
                        done: float = 0.3, density: float = 0.5):
    """Generate and load a large procedural dataset."""
    driver = get_driver()
    from generate_large_dataset import generate, load_to_neo4j
    nodes, edges, done_uids = generate(
        num_layers=layers, base_width=width, seed=seed,
        done_fraction=done, density=density,
    )
    n, e, d = load_to_neo4j(
        nodes, edges, done_uids,
        _state["uri"], _state["user"], _state["password"],
    )
    return {"nodes": n, "edges": e, "done": d}


@app.on_event("shutdown")
def shutdown():
    if _state["driver"]:
        _state["driver"].close()
