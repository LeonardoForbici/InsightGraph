// ═════════════════════════════════════════════════════════════
// NEO4J SCHEMA UPDATES - Fase 2 (Taint Analysis) & Fase 3 (Churn)
// ═════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────
// FASE 2: TAINT ANALYSIS - Node Types & Relations
// ─────────────────────────────────────────────────────────────

// Criar constraints para unicidade
CREATE CONSTRAINT property_unique IF NOT EXISTS
  FOR (p:Property) REQUIRE p.property_key IS UNIQUE;

CREATE CONSTRAINT column_unique IF NOT EXISTS
  FOR (c:Column) REQUIRE c.column_key IS UNIQUE;

CREATE CONSTRAINT dataflow_unique IF NOT EXISTS
  FOR (d:DataFlow) REQUIRE d.flow_key IS UNIQUE;

// ─────────────────────────────────────────────────────────────
// CREATE Property Nodes (DTO/Entity properties)
// Property nodes representam atributos de classes/DTOs
// property_key = "project:TypeName/propertyName"
// ─────────────────────────────────────────────────────────────

// MATCH (cls:Entity {name: "UserDTO"})
// WHERE cls.type = "Class"
// CREATE (cls)-[:HAS_PROPERTY]->(prop:Property {
//   property_key: cls.namespace_key + "/" + $propertyName,
//   name: $propertyName,
//   type_hint: $type,
//   source_class: cls.namespace_key,
//   sensitive: $isSensitive,
//   created_at: datetime()
// })

// ─────────────────────────────────────────────────────────────
// CREATE Column Nodes (Database columns)
// Column nodes representam colunas em tabelas SQL
// column_key = "db:schema/table/columnName"
// ─────────────────────────────────────────────────────────────

// MATCH (table:Entity {type: "Table"})
// WHERE table.name = $tableName
// CREATE (table)-[:HAS_COLUMN]->(col:Column {
//   column_key: table.namespace_key + "/" + $columnName,
//   name: $columnName,
//   type_hint: $sqlType,
//   source_table: table.namespace_key,
//   sensitive: $isSensitive,
//   created_at: datetime()
// })

// ─────────────────────────────────────────────────────────────
// FLOWS_TO Relations (Property-to-Property data flow)
// Indica que uma propriedade flui para outra
// Exemplo: UserDTO.email -> ResponseDTO.email
// ─────────────────────────────────────────────────────────────

MATCH (prop_from:Property), (prop_to:Property)
WHERE prop_from.property_key = "MyApp:UserDTO/email"
  AND prop_to.property_key = "MyApp:ResponseDTO/email"
CREATE (prop_from)-[:FLOWS_TO {
  flow_type: "dto_mapping",
  transformation: "direct_assignment",
  discovered_at: datetime()
}]->(prop_to);

// ─────────────────────────────────────────────────────────────
// READS_FROM_COLUMN Relations (SQL SELECT operations)
// Indicates method reads column from DB
// Exemplo: UserService.getUser() -> reads User.id, User.email
// ─────────────────────────────────────────────────────────────

MATCH (method:Entity {type: "Method"}), (col:Column)
WHERE method.namespace_key = "MyApp:UserService/getUser"
  AND col.column_key = "db:public/users/email"
CREATE (method)-[:READS_FROM_COLUMN {
  operation: "SELECT",
  context: "WHERE clause",
  discovered_at: datetime()
}]->(col);

// ─────────────────────────────────────────────────────────────
// WRITES_TO_COLUMN Relations (SQL INSERT/UPDATE operations)
// Indicates method writes to column
// Exemplo: UserService.saveUser() -> writes User.email, User.password
// ─────────────────────────────────────────────────────────────

MATCH (method:Entity {type: "Method"}), (col:Column)
WHERE method.namespace_key = "MyApp:UserService/saveUser"
  AND col.column_key = "db:public/users/password"
CREATE (method)-[:WRITES_TO_COLUMN {
  operation: "UPDATE",
  context: "SET clause",
  discovered_at: datetime()
}]->(col);

// ─────────────────────────────────────────────────────────────
// TRANSFORMS_PROPERTY Relation (Data transformation)
// Indicates property is transformed before flowing
// Exemplo: email -> hash(email), password -> encrypt(password)
// ─────────────────────────────────────────────────────────────

MATCH (prop_from:Property), (prop_to:Property)
WHERE prop_from.property_key = "MyApp:UserDTO/password"
  AND prop_to.property_key = "MyApp:User/passwordHash"
CREATE (prop_from)-[:TRANSFORMS_PROPERTY {
  transformation_type: "encryption",
  function: "bcrypt.hash",
  sensitive_preserved: true,
  discovered_at: datetime()
}]->(prop_to);

// ─────────────────────────────────────────────────────────────
// FASE 3: CHURN ANALYSIS - Node Updates
// ─────────────────────────────────────────────────────────────

// Adicionar propriedades de churn aos nós Entity existentes
MATCH (e:Entity)
WHERE e.type IN ["Class", "Method", "File"]
SET e.churn_rate = 0.0,           // Commits por mês
    e.churn_intensity = 0.0,       // Linhas alteradas por commit
    e.commit_count = 0,            // Total de commits nos últimos 6 meses
    e.git_analyzed_at = null,      // Data da última análise
    e.true_risk_score = 0.0        // Calculated risk = complexity * churn
RETURN COUNT(e) as nodes_updated;

// ─────────────────────────────────────────────────────────────
// UTILITY QUERIES
// ─────────────────────────────────────────────────────────────

// Query 1: Find all sensitive data flow paths
// Trace onde dados sensíveis (e.g., email, password) fluem
MATCH path = (prop:Property {sensitive: true})-[r:FLOWS_TO|READS_FROM_COLUMN|WRITES_TO_COLUMN*1..10]->(target)
WHERE target:Property OR target:Column OR target:Entity
RETURN path, properties(r) as relationship_properties
LIMIT 50;

// Query 2: Find high-churn, high-complexity components
// Identifica hotspots críticos combining complexity + churn
MATCH (e:Entity {type: "Class"})
WHERE e.cyclomatic_complexity > 10
  AND e.churn_rate > 2
RETURN e.namespace_key, e.cyclomatic_complexity, e.churn_rate, 
       (e.cyclomatic_complexity * e.churn_rate * 2.5) as risk_score
ORDER BY risk_score DESC
LIMIT 20;

// Query 3: All properties flowing to a sensitive column
// Para uma coluna sensível (e.g., users.email), achar todas as propriedades que fluem para ela
MATCH (col:Column {sensitive: true})
MATCH path = (prop:Property)-[r:FLOWS_TO|TRANSFORMS_PROPERTY*1..8]->(col)
RETURN col.name as sensitive_column,
       collect({
         property: prop.name,
         path_length: length(path),
         transformations: [rel in relationships(path) | rel.transformation_type]
       }) as source_properties;

// Query 4: Update true_risk_score for all entities
// Calcula e armazena true_risk_score = complexity * churn_rate
MATCH (e:Entity)
WHERE e.cyclomatic_complexity IS NOT NULL 
  AND e.churn_rate IS NOT NULL
SET e.true_risk_score = (e.cyclomatic_complexity / 20) * (e.churn_rate * 10 + 1)
RETURN COUNT(e) as updated_nodes;

// Query 5: Get top risky components
// Components ordenadas por true_risk_score descendente
MATCH (e:Entity {type: "Class"})
WHERE e.true_risk_score IS NOT NULL
ORDER BY e.true_risk_score DESC
RETURN e.namespace_key, e.cyclomatic_complexity, e.churn_rate, e.true_risk_score
LIMIT 10;

// Query 6: Trace method calls involving sensitive properties
// Achar todas as chamadas de métodos que processam dados sensíveis
MATCH (prop:Property {sensitive: true})-[f:FLOWS_TO*1..5]->(other_prop:Property)
MATCH (method:Entity {type: "Method"})-[:CALLS]->(called:Entity) 
WHERE called.namespace_key CONTAINS other_prop.source_class
RETURN DISTINCT method.namespace_key, other_prop.name, f
LIMIT 20;

// Query 7: Data flow from API Controller to Database
// Trace completo de um given DTO através de Services até Columns
MATCH (prop:Property)<-[:HAS_PROPERTY]-(dto:Entity)
WHERE dto.namespace_key CONTAINS "DTO"
  AND prop.sensitive = true
MATCH (method:Entity)-[:READS_FROM_COLUMN|WRITES_TO_COLUMN]->(col:Column {sensitive: true})
RETURN dto.name, prop.name, method.namespace_key, col.column_key;

// Query 8: Churn hotspots - Files changed most frequently
// Ficheiros com mais commits = higher instability
MATCH (e:Entity)
WHERE e.commit_count > 10
ORDER BY e.commit_count DESC, e.true_risk_score DESC
RETURN e.namespace_key, e.commit_count, e.churn_rate, e.churn_intensity
LIMIT 15;

// Query 9: Add metadata to existing entities
// Adicionar propriedades extras para análise
MATCH (e:Entity)
WHERE e.type = "Method"
SET e.has_sensitive_flow = EXISTS((e)-[:FLOWS_TO|READS_FROM_COLUMN]-(:Property {sensitive: true}))
RETURN COUNT(e) as methods_updated;

// Query 10: Calculate aggregate risk for entire modules
// Suma de riscos num módulo/package
MATCH (module:Entity {type: "Package"})
  -[:CONTAINS*1..3]->(comp:Entity)
WHERE comp.true_risk_score IS NOT NULL
RETURN module.namespace_key,
       COUNT(comp) as component_count,
       AVG(comp.true_risk_score) as avg_risk,
       MAX(comp.true_risk_score) as max_risk,
       SUM(comp.commit_count) as total_commits
ORDER BY max_risk DESC;
