# neo4j-gds-compute-process-cpa
critical path analysis of jobs with dependency leveraging Neo4j GDS LongestPath algorithm

## Neo4j Demo: Monitoring Job Dependencies in Risk Computation Processes

This repository contains a demo implementation using Neo4j to monitor jobs with dependencies in risk computation processes for a banking environment. The demo focuses on modeling data lineage and system dependencies using a graph database, enabling real-time monitoring, anomaly detection, and critical path analysis (CPA). 

## Data Model
The Neo4j data model is designed to represent jobs in risk computation processes as a Directed Acyclic Graph (DAG), where jobs have dependencies and durations. This enables efficient tracing of lineage and identification of bottlenecks.

### Initial Model (from Import)
- **Nodes**:
  - `:Job` with properties:
    - `job_id` (unique string identifier).
    - `start_date` (string timestamp, e.g., "HH:MM:SS").
    - `end_date` (string timestamp, e.g., "HH:MM:SS").
    - `duration` (integer seconds, computed post-import).
- **Relationships**:
  - `[:DEPENDS]` (directed from a job to its dependency, indicating the source job depends on the target job).

This model is imported from CSV files:
- `vertices.csv`: Columns `Vertex` (job_id), `Start` (start_date), `End` (end_date).
- `edges.csv`: Columns `To Vertex` (source job_id), `From Vertex` (target job_id).

See `cypher_import.cypher` for the import script, which creates uniqueness constraints and loads data in batches.

### Refactored Model for Critical Path Analysis (CPA)
To perform CPA using Neo4j's Graph Data Science (GDS) library (e.g., `gds.dag.longestPath`), the graph is refactored into an edge-weighted DAG:
- **Additional Nodes**:
  - `:Start` (per job, with `job_id`).
  - `:End` (per job, with `job_id`).
  - `:KickOff` (single node representing the start of the entire process).
- **Relationships**:
  - `[:STARTS]` (from `:Job` to `:Start`).
  - `[:ENDS]` (from `:Job` to `:End`).
  - `[:TIME]` (weighted edges with `duration` property in seconds):
    - From `:Start` to `:End` for each job (duration = job execution time).
    - From `:End` of a dependency job to `:Start` of the dependent job (duration = 3 seconds wait time).
    - From `:KickOff` to `:Start` of initial jobs (duration = time from midnight to job start).

This refactoring treats time as relationships, allowing GDS to compute longest paths (critical paths) based on cumulative durations. It draws from the approach in the Neo4j blog post ["Unlocking DAGs in Neo4j: From Basics to Critical Path Analysis"](https://neo4j.com/blog/developer/dags-neo4j-critical-path-analysis/), enabling scalable analysis of delays and dependencies in risk computations.

## Setup Instructions
1. Start a Neo4j instance with GDS plugin installed.
2. Run `cypher_import.cypher` to import data (update file paths as needed).
3. Execute the queries in sequence as described below.

## Modeling Queries
These queries build and refactor the data model for dependency mapping and real-time monitoring.

### Clean
**Description**: Resets the graph by deleting temporary nodes (`:KickOff`, `:Start`, `:End`) and dropping the in-memory graph projection.

**Query**:
```cypher
MATCH (ko:KickOff)
OPTIONAL CALL (ko) { 
WITH ko LIMIT 1
DETACH DELETE ko
};
MATCH (x:End|Start)
CALL (x) { DETACH DELETE x} IN TRANSACTIONS OF 1000 ROWS;
CALL gds.graph.drop('g');
```

### Compute Job Durations
**Description**: Calculates the duration (in seconds) between `start_date` and `end_date` for each `:Job` node and sets it as a property.

**Query**:
```cypher
MATCH (j:Job)
CALL (j) {
  WITH j.job_id AS job_id, duration.between(time(j.start_date), time(j.end_date)) AS duration
  WITH job_id, duration, duration.seconds AS sec
  SET j.duration = sec
  } IN CONCURRENT TRANSACTIONS OF 1000 ROWS
```

### Create Index for Merge
**Description**: Creates indexes on `job_id` for `:Start` and `:End` nodes to optimize merge operations.

**Query**:
```cypher
CREATE INDEX start_job_id IF NOT EXISTS FOR (s:Start) ON (s.job_id);
CREATE INDEX end_job_id IF NOT EXISTS FOR (e:End) ON (e.job_id);
```

### Time as Rels
**Description**: Creates `:Start` and `:End` nodes for each job, links them to the job, and adds a `:TIME` relationship representing the job's duration.

**Query**:
```cypher
MATCH (j:Job)
CALL (j) {
  MERGE (s:Start {job_id: j.job_id})
  MERGE (e:End {job_id: j.job_id})
  MERGE (j)-[:STARTS]->(s)
  MERGE (j)-[:ENDS]->(e)
  MERGE (s)-[:TIME {duration: j.duration}]->(e)
} IN CONCURRENT TRANSACTIONS OF 1000 ROWS
```

### Dependency 3sec Wait Time
**Description**: Adds `:TIME` relationships with a 3-second duration between the end of a dependency job and the start of the dependent job.

**Query**:
```cypher
MATCH (j1)-[:DEPENDS]->(j0)
CALL (j0, j1) {
  MERGE (s:Start {job_id: j1.job_id})
  MERGE (e:End {job_id: j0.job_id})
  MERGE (e)-[:TIME {duration: 3}]->(s)
} IN CONCURRENT TRANSACTIONS OF 1000 ROWS
```

### Kickoff Node
**Description**: Creates a single `:KickOff` node to represent the process start.

**Query**:
```cypher
MERGE (:KickOff)
```

### KickOff to Initial Jobs
**Description**: Connects the `:KickOff` node to the `:Start` nodes of jobs with no incoming dependencies, using the time from midnight as duration.

**Query**:
```cypher
MATCH (j:Job)
WITH duration.between (time("00:00:00"), time(j.start_date)).seconds AS duration
ORDER BY duration ASC LIMIT 1
MATCH (ko:KickOff)
WITH ko, duration
MATCH (j:Job)-[:STARTS]->(s)
WHERE NOT EXISTS {(j)-[:DEPENDS]->()}
CALL (ko, s, duration) {
  MERGE (ko)-[:TIME {duration: duration}]->(s)
} IN TRANSACTIONS OF 1000 ROWS
```

## Critical Path Analysis (CPA) Queries
These queries project the refactored graph and compute critical paths to identify potential delays and bottlenecks, addressing anomaly detection and proactive risk management.

### Project In-Memory Graph
**Description**: Projects the refactored graph into memory for GDS analysis, including `:TIME` relationships and their durations.

**Query**:
```cypher
MATCH (source:Start|KickOff|End)
OPTIONAL MATCH (source)-[r:TIME]->(target)
RETURN gds.graph.project("g", source, target, {relationshipProperties: r {.duration}})
```

### Stream Critical Paths
**Description**: Streams the longest paths (critical paths) using GDS, yielding the target node, total cost (duration), path, and costs for analysis of delays.

**Query**:
```cypher
CALL gds.dag.longestPath.stream("g", {relationshipWeightProperty: "duration"})
YIELD targetNode as target, totalCost, path, costs
WITH target AS last_activity, totalCost, path, costs
ORDER BY totalCost DESC
WITH last_activity, collect ({totalCost:totalCost, path:path, costs:costs})[0] AS longest
RETURN last_activity, longest.totalCost AS critical_time, longest.path AS path, longest.costs AS costs
```

### Stream Critical Times
**Description**: Streams critical times for specific last activities (e.g., filtered job_ids), ordering by activity length for targeted delay analysis.

**Query**:
```cypher
CALL gds.dag.longestPath.stream("g", {relationshipWeightProperty: "duration"})
YIELD targetNode as target, totalCost, path, costs
WITH gds.util.asNode(target).job_id AS last_activity, totalCost, path, costs
ORDER BY totalCost DESC
WITH last_activity, collect ({totalCost:totalCost, path:path, costs:costs})[0] AS longest
WHERE last_activity IN $job_id_list
WITH last_activity, longest.totalCost AS critical_time, longest.path AS path, longest.costs AS costs
ORDER BY size(last_activity)
RETURN last_activity, critical_time
```

This CPA approach scales to large graphs (e.g., thousands of jobs), identifying the longest sequence of dependent tasks to prevent service disruptions and ensure SLA adherence. It unlocks faster incident resolution and reduced analyst effort (estimated >30% reduction).
