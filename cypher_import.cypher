:param {
  // Define the file path root and the individual file names required for loading.
  // https://neo4j.com/docs/operations-manual/current/configuration/file-locations/
  file_path_root: 'file:///', // Change this to the folder your script can access the files at.
  file_0: 'vertices.csv',
  file_1: 'edges.csv'
};

// CONSTRAINT creation
// -------------------
//
// Create node uniqueness constraints, ensuring no duplicates for the given node label and ID property exist in the database. This also ensures no duplicates are introduced in future.
//
// NOTE: The following constraint creation syntax is generated based on the current connected database version 5.27.0.
CREATE CONSTRAINT `job_id_Job_uniq` IF NOT EXISTS
FOR (n: `Job`)
REQUIRE (n.`job_id`) IS UNIQUE;

:param {
  idsToSkip: []
};

// NODE load
// ---------
//
// Load nodes in batches, one node label at a time. Nodes will be created using a MERGE statement to ensure a node with the same label and ID property remains unique. Pre-existing nodes found by a MERGE statement will have their other properties set to the latest values encountered in a load file.
//
// NOTE: Any nodes with IDs in the 'idsToSkip' list parameter will not be loaded.
LOAD CSV WITH HEADERS FROM ($file_path_root + $file_0) AS row
WITH row
WHERE NOT row.`Vertex` IN $idsToSkip AND NOT row.`Vertex` IS NULL
CALL (row) {
  MERGE (n: `Job` { `job_id`: row.`Vertex` })
  SET n.`job_id` = row.`Vertex`
  SET n.`start_date` = row.`Start`
  SET n.`end_date` = row.`End`
} IN TRANSACTIONS OF 10000 ROWS;


// RELATIONSHIP load
// -----------------
//
// Load relationships in batches, one relationship type at a time. Relationships are created using a MERGE statement, meaning only one relationship of a given type will ever be created between a pair of nodes.
LOAD CSV WITH HEADERS FROM ($file_path_root + $file_1) AS row
WITH row 
CALL (row) {
  MATCH (source: `Job` { `job_id`: row.`To Vertex` })
  MATCH (target: `Job` { `job_id`: row.`From Vertex` })
  MERGE (source)-[r: `DEPENDS`]->(target)
} IN TRANSACTIONS OF 10000 ROWS;
