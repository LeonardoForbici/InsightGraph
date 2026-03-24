# CodeQL Integration Guide

## Overview

O `codeql_bridge.py` integra análise CodeQL de nível industrial ao InsightGraph, permitindo:

- **Taint Tracking**: Rastreamento de fluxo de dados desde SQL procedures até componentes React
- **Vulnerability Detection**: Detecção automática de vulnerabilidades de segurança
- **Path Marking**: Marcação de caminhos contaminados no grafo Neo4j com `is_tainted: true`

## Prerequisites

1. **Install CodeQL CLI**:
   ```bash
   # Download from https://github.com/github/codeql-cli-binaries/releases
   # Extract and add to PATH
   codeql --version
   ```

2. **Create CodeQL Database**:
   ```bash
   # For Java projects
   codeql database create codeql-db --language=java --source-root=./meuponto-api

   # For JavaScript/TypeScript
   codeql database create codeql-db --language=javascript --source-root=./frontend
   ```

## Usage

### Option 1: Python API

```python
from codeql_bridge import CodeQLBridge

# Initialize bridge
bridge = CodeQLBridge(neo4j_service, project_root="/path/to/project")

# Run analysis
success = bridge.run_analysis(
    database_path="./codeql-db",
    output_path="results.sarif",
    suite="security-extended"  # or "security-and-quality"
)

# Ingest results into Neo4j
if success:
    summary = bridge.ingest_sarif("results.sarif")
    print(f"Ingested {summary['ingested']} issues")
    print(f"Marked {summary['tainted_paths']} tainted paths")
```

### Option 2: FastAPI Endpoint

Add to `main.py`:

```python
from codeql_bridge import run_codeql_analysis

@app.post("/api/codeql/analyze")
async def codeql_analyze(
    database_path: str,
    output_path: str = "codeql-results.sarif"
):
    """Run CodeQL analysis and ingest results."""
    summary = run_codeql_analysis(
        neo4j_service,
        project_root=".",
        database_path=database_path,
        output_path=output_path
    )
    return summary
```

### Option 3: CLI Script

```python
# scripts/run_codeql.py
import sys
from backend.codeql_bridge import run_codeql_analysis
from backend.main import neo4j_service

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "./codeql-db"
    summary = run_codeql_analysis(neo4j_service, ".", db_path)
    print(f"Analysis complete: {summary}")
```

## What Gets Created in Neo4j

### 1. SecurityIssue Nodes

```cypher
(:SecurityIssue {
  namespace_key: "security:java/sql-injection:path/to/File.java:42",
  rule_id: "java/sql-injection",
  severity: "error",
  message: "Query built from user-controlled sources",
  file: "src/main/java/...",
  start_line: 42,
  end_line: 45,
  has_taint_flow: true
})
```

### 2. HAS_VULNERABILITY Relationships

```cypher
(:Java_Method)-[:HAS_VULNERABILITY]->(:SecurityIssue)
```

### 3. Tainted Path Marking

```cypher
// Before CodeQL
(:Procedure)-[:CALLS]->(:Java_Method)-[:CALLS_HTTP]->(:API_Endpoint)

// After CodeQL (if taint detected)
(:Procedure)-[:CALLS {is_tainted: true, taint_message: "..."}]->(:Java_Method)
(:Java_Method)-[:CALLS_HTTP {is_tainted: true}]->(:API_Endpoint)
```

## Query Examples

### Find All Vulnerabilities

```cypher
MATCH (e:Entity)-[:HAS_VULNERABILITY]->(s:SecurityIssue)
RETURN e.name, s.rule_id, s.severity, s.message
ORDER BY s.severity DESC
```

### Find Tainted Paths from Database to Frontend

```cypher
MATCH path = (db:Procedure)-[*..10 {is_tainted: true}]->(fe:Angular_Component)
RETURN path
```

### Security Hotspots (Most Vulnerable Entities)

```cypher
MATCH (e:Entity)-[:HAS_VULNERABILITY]->(s:SecurityIssue)
WITH e, count(s) AS vuln_count
WHERE vuln_count > 3
RETURN e.name, e.file, vuln_count
ORDER BY vuln_count DESC
LIMIT 20
```

### Critical Tainted Flows

```cypher
MATCH (source)-[r {is_tainted: true}]->(target)
WHERE source.layer = 'database' AND target.layer IN ['API', 'Frontend']
RETURN source.name, type(r), target.name, r.taint_message
```

## Integration with Existing Features

### 1. Impact Analysis Panel

Add a new tab "🔒 Security" that shows:
- Vulnerabilities affecting the selected node
- Tainted paths passing through it
- Security risk score

### 2. Graph Visualization

- Color tainted edges in red
- Add vulnerability badges to nodes
- Show security alerts on hover

### 3. Fragility Calculator

Incorporate security metrics:
```python
# In fragility_calculator.py
vuln_count = self._count_vulnerabilities(node_key)
fragility_score += vuln_count * 10  # Each vulnerability adds 10 points
```

## Advanced: Custom CodeQL Queries

Create custom queries for domain-specific analysis:

```ql
// queries/custom/taint-to-frontend.ql
/**
 * @name Taint flow from database to frontend
 * @kind path-problem
 */

import java
import semmle.code.java.dataflow.TaintTracking

class DatabaseToFrontendConfig extends TaintTracking::Configuration {
  DatabaseToFrontendConfig() { this = "DatabaseToFrontendConfig" }

  override predicate isSource(DataFlow::Node source) {
    exists(MethodAccess ma |
      ma.getMethod().getName().matches("execute%") and
      source.asExpr() = ma
    )
  }

  override predicate isSink(DataFlow::Node sink) {
    exists(MethodAccess ma |
      ma.getMethod().getName() = "sendResponse" and
      sink.asExpr() = ma.getAnArgument()
    )
  }
}

from DatabaseToFrontendConfig config, DataFlow::PathNode source, DataFlow::PathNode sink
where config.hasFlowPath(source, sink)
select sink.getNode(), source, sink, "Tainted data from $@ reaches frontend", source.getNode(), "database query"
```

Run with:
```bash
codeql database analyze codeql-db queries/custom/taint-to-frontend.ql --format=sarif-latest --output=custom-results.sarif
```

## Performance Considerations

- **Database Creation**: Can take 5-30 minutes for large projects
- **Analysis**: 1-10 minutes depending on query suite
- **Ingestion**: ~100 issues/second into Neo4j

## Troubleshooting

### "codeql: command not found"
- Ensure CodeQL CLI is in PATH
- Download from https://github.com/github/codeql-cli-binaries

### "No entities found for location"
- Run InsightGraph scan first to populate Neo4j
- Check that file paths match between CodeQL and InsightGraph

### "Analysis timeout"
- Increase timeout parameter: `run_analysis(..., timeout=1200)`
- Use smaller query suites: `suite="security-critical"`

## Next Steps

1. **Automate**: Add CodeQL analysis to CI/CD pipeline
2. **Dashboard**: Create security dashboard showing trends
3. **Alerts**: Set up notifications for critical vulnerabilities
4. **Remediation**: Link to fix suggestions and patches
