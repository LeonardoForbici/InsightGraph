# InsightGraph — Cypher Queries

## Index Creation (Run Once)

Execute these in Neo4j Browser after starting the database:

```cypher
-- Core entity index
CREATE INDEX idx_namespace IF NOT EXISTS FOR (n:Entity) ON (n.namespace_key);
CREATE INDEX idx_project IF NOT EXISTS FOR (n:Entity) ON (n.project);
CREATE INDEX idx_layer IF NOT EXISTS FOR (n:Entity) ON (n.layer);

-- Type-specific indexes
CREATE INDEX idx_java_class IF NOT EXISTS FOR (n:Java_Class) ON (n.namespace_key);
CREATE INDEX idx_java_method IF NOT EXISTS FOR (n:Java_Method) ON (n.namespace_key);
CREATE INDEX idx_ts_component IF NOT EXISTS FOR (n:TS_Component) ON (n.namespace_key);
CREATE INDEX idx_ts_function IF NOT EXISTS FOR (n:TS_Function) ON (n.namespace_key);
CREATE INDEX idx_sql_table IF NOT EXISTS FOR (n:SQL_Table) ON (n.namespace_key);
CREATE INDEX idx_sql_procedure IF NOT EXISTS FOR (n:SQL_Procedure) ON (n.namespace_key);
CREATE INDEX idx_mobile_component IF NOT EXISTS FOR (n:Mobile_Component) ON (n.namespace_key);
```

> **Note:** The backend's `ensure_indexes()` function runs these automatically on startup.

---

## Data Exploration

### List all entities

```cypher
MATCH (n:Entity)
RETURN n.namespace_key, n.name, labels(n), n.project, n.layer
ORDER BY n.project, n.layer
LIMIT 100;
```

### Count entities per project

```cypher
MATCH (n:Entity)
RETURN n.project AS project, count(n) AS total
ORDER BY total DESC;
```

### Count entities per type

```cypher
MATCH (n:Entity)
UNWIND labels(n) AS label
WITH label WHERE label <> 'Entity'
RETURN label, count(*) AS total
ORDER BY total DESC;
```

### List all relationships

```cypher
MATCH (a:Entity)-[r]->(b:Entity)
RETURN a.name, type(r), b.name
LIMIT 100;
```

---

## Impact Analysis

### Upstream (who calls/depends on this?)

```cypher
MATCH (upstream:Entity)-[r]->(target:Entity {namespace_key: $key})
RETURN upstream.name, type(r), upstream.namespace_key
ORDER BY type(r);
```

### Downstream (what does this call/depend on?)

```cypher
MATCH (target:Entity {namespace_key: $key})-[r]->(downstream:Entity)
RETURN downstream.name, type(r), downstream.namespace_key
ORDER BY type(r);
```

### Full impact (2 levels deep)

```cypher
MATCH path = (n:Entity {namespace_key: $key})-[*1..2]-(connected:Entity)
RETURN path;
```

---

## Cross-Project Analysis

### Find cross-project dependencies

```cypher
MATCH (a:Entity)-[r]->(b:Entity)
WHERE a.project <> b.project
RETURN a.project, a.name, type(r), b.project, b.name;
```

### Find SQL tables used by Java services

```cypher
MATCH (java:Java_Class)-[:CALLS|DEPENDS_ON*1..3]->(proc:SQL_Procedure)-[:READS_FROM|WRITES_TO]->(table:SQL_Table)
RETURN java.name, proc.name, table.name;
```

---

## Maintenance

### Clear all data

```cypher
MATCH (n) DETACH DELETE n;
```

### Clear a specific project

```cypher
MATCH (n:Entity {project: 'ProjectName'})
DETACH DELETE n;
```
