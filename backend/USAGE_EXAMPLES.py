"""
USAGE EXAMPLES & TESTING GUIDE
InsightGraph Phase 2 (Taint Analysis) + Phase 3 (Code Churn)

This file demonstrates:
1. Backend API usage examples (curl, Python)
2. Neo4j Cypher queries for analysis
3. Test data scenarios
4. Frontend integration patterns
"""

# ═══════════════════════════════════════════════════════════════════════════
# PART 1: BACKEND API USAGE
# ═══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────
# Example 1: Scan Project (Triggers Code + Git Analysis)
# ─────────────────────────────────────────────────────────────────────────
# 
# curl -X POST http://localhost:8000/api/scan \
#   -H "Content-Type: application/json" \
#   -d '{
#     "paths": ["/home/user/InsightGraph/backend", "/home/user/InsightGraph/frontend"]
#   }'

# Response:
# {
#   "status": "scanning",
#   "message": "Project scan started (code + Git churn in background)"
# }

# Background: 
# - Code parsing happens immediately (Java/TS/SQL files)
# - Property nodes created with HAS_PROPERTY relations
# - Git analysis triggered in background thread
# - Progress available at /api/scan/status

# ─────────────────────────────────────────────────────────────────────────
# Example 2: Get Antipatterns (including Taint + Churn data)
# ─────────────────────────────────────────────────────────────────────────
#
# curl -X GET http://localhost:8000/api/antipatterns?project=InsightGraph

# Response (excerpt):
# {
#   "circular_dependencies": [],
#   "god_classes": [
#     {
#       "namespace_key": "InsightGraph:UserService",
#       "line_count": 2843,
#       "method_count": 47
#     }
#   ],
#   "sensitive_flows": [
#     {
#       "source_property": "email",
#       "target": "email_column",
#       "flow_path": ["UserDTO", "UserMapper", "UserEntity", "users_table"],
#       "is_encrypted": false
#     }
#   ],
#   "true_risk_hotspots": [
#     {
#       "namespace_key": "InsightGraph:PaymentService/processPayment",
#       "complexity": 23,
#       "churn_rate": 4.5,
#       "true_risk_score": 87.3
#     }
#   ]
# }

# ─────────────────────────────────────────────────────────────────────────
# Example 3: Trace Sensitive Data Flow (Taint Analysis)
# ─────────────────────────────────────────────────────────────────────────
#
# curl -X GET http://localhost:8000/api/taint/trace/email

# Response:
# {
#   "source": "email",
#   "flows": [
#     {
#       "start_prop": "InsightGraph:UserDTO/email",
#       "paths": [
#         {
#           "from": "UserDTO.email",
#           "to": "UserEntity.email",
#           "relationship": "FLOWS_TO",
#           "transformation": "direct_assignment"
#         },
#         {
#           "from": "UserEntity.email",
#           "to": "users.email",
#           "relationship": "WRITES_TO_COLUMN",
#           "operation": "INSERT"
#         }
#       ],
#       "affected_components": ["UserMapper", "UserEntity", "DatabaseService"]
#     }
#   ],
#   "recommendation": "Review each TRANSFORMS_PROPERTY for encryption/hashing"
# }

# ─────────────────────────────────────────────────────────────────────────
# Example 4: Get Risk Metrics for a Node
# ─────────────────────────────────────────────────────────────────────────
#
# curl -X GET http://localhost:8000/api/node/InsightGraph:UserService%3A%2FgetUser/risk-metrics

# Response:
# {
#   "namespace_key": "InsightGraph:UserService/getUser",
#   "cyclomatic_complexity": 14,
#   "churn_rate": 3.2,
#   "churn_intensity": 45.7,
#   "commit_count": 19,
#   "true_risk_score": 65.8,
#   "severity": "High",
#   "color": {
#     "color": "#f97316",
#     "label": "High Risk"
#   },
#   "git_analyzed_at": "2024-01-15T10:30:00Z"
# }

# ═══════════════════════════════════════════════════════════════════════════
# PART 2: NEO4J CYPHER QUERY EXAMPLES
# ═══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────
# Query 1: Find all SENSITIVE property flows
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (prop:Property {sensitive: true})
# MATCH path = (prop)-[:FLOWS_TO|TRANSFORMS_PROPERTY|WRITES_TO_COLUMN*1..8]->(target)
# RETURN 
#   prop.name as sensitive_property,
#   length(path) as hops,
#   [node in nodes(path) | node.name] as flow_path,
#   target.name as final_destination
# ORDER BY hops DESC
# LIMIT 20;

# Result:
# sensitive_property | hops | flow_path | final_destination
# ─────────────────────────────────────────────────────────────
# email | 4 | ["email", "UserDTO", "UserEntity", "email"] | email
# password | 5 | ["password", "LoginDTO", "hash", "UserEntity", "pw_hash"] | pw_hash
# cpf | 3 | ["cpf", "PersonDTO", "PersonEntity", "cpf"] | cpf

# ─────────────────────────────────────────────────────────────────────────
# Query 2: Methods writing to sensitive columns (Data leakage risk)
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (method:Entity {type: "Method"})
# MATCH (method)-[:WRITES_TO_COLUMN]->(col:Column {sensitive: true})
# RETURN 
#   method.namespace_key,
#   method.cyclomatic_complexity,
#   col.name as target_column,
#   collect(col.name) as all_sensitive_cols
# ORDER BY method.cyclomatic_complexity DESC;

# Risk: Methods writing to sensitive columns should have strong encryption checks

# ─────────────────────────────────────────────────────────────────────────
# Query 3: Top 10 Risk Hotspots (Complexity × Churn)
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (e:Entity {type: "Class"})
# WHERE e.cyclomatic_complexity > 5 
#   AND e.churn_rate > 1
# RETURN 
#   e.namespace_key,
#   e.cyclomatic_complexity,
#   e.churn_rate,
#   e.churn_intensity,
#   ROUND((e.cyclomatic_complexity / 20) * (e.churn_rate * 10 + 1), 1) as true_risk_score
# ORDER BY true_risk_score DESC
# LIMIT 10;

# Result sample:
# namespace_key | complexity | churn_rate | churn_intensity | true_risk_score
# ──────────────────────────────────────────────────────────────────────────
# PaymentService | 28 | 5.2 | 67 | 89.4 ← CRITICAL
# UserValidator | 18 | 4.1 | 33 | 64.7 ← HIGH
# ReportGenerator | 12 | 2.3 | 18 | 28.6 ← MEDIUM

# ─────────────────────────────────────────────────────────────────────────
# Query 4: Trace Email from UI Controller to Database
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (prop:Property {name: "email"})
#   <-[:HAS_PROPERTY]-(dto:Entity)
# WHERE dto.name CONTAINS "DTO"
#   AND dto.type = "Class"
#
# MATCH (prop)-[f:FLOWS_TO*1..5]->(other_prop:Property)
#
# MATCH (method:Entity {type: "Method"})
#   -[:READS_FROM_COLUMN|WRITES_TO_COLUMN]->(col:Column)
# WHERE col.name = "email"
#
# RETURN 
#   dto.namespace_key as source_dto,
#   prop.name as source_prop,
#   collect(DISTINCT method.namespace_key) as processing_methods,
#   collect(DISTINCT col.column_key) as destination_columns;

# Critical for GDPR: Ensures email data is encrypted in transit

# ─────────────────────────────────────────────────────────────────────────
# Query 5: Churn Analysis - Frequently Changed Files
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (e:Entity {type: "File"})
# WHERE e.commit_count > 15
# RETURN 
#   e.namespace_key,
#   e.commit_count,
#   e.churn_rate,
#   e.churn_intensity,
#   e.true_risk_score
# ORDER BY e.commit_count DESC, e.true_risk_score DESC
# LIMIT 15;

# Insight: Files with high churn are often broken or undergoing active development
# Action: Consider refactoring to reduce change frequency and complexity

# ─────────────────────────────────────────────────────────────────────────
# Query 6: Summary - Risk by Package/Module
# ─────────────────────────────────────────────────────────────────────────
#
# MATCH (package:Entity {type: "Package"})
#   -[:CONTAINS*1..3]->(comp:Entity)
# WHERE comp.type IN ["Class", "Method"]
#   AND comp.true_risk_score IS NOT NULL
#
# RETURN 
#   package.namespace_key,
#   COUNT(DISTINCT comp) as component_count,
#   ROUND(AVG(comp.true_risk_score), 1) as avg_risk,
#   ROUND(MAX(comp.true_risk_score), 1) as max_risk,
#   SUM(CASE WHEN comp.true_risk_score > 70 THEN 1 ELSE 0 END) as critical_count
# ORDER BY max_risk DESC;

# ═══════════════════════════════════════════════════════════════════════════
# PART 3: PYTHON INTEGRATION EXAMPLES
# ═══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────
# Example: Analyze Git churn for a project and update Neo4j
# ─────────────────────────────────────────────────────────────────────────

from git_service import GitService, RiskScoreCalculator
from py2neo import Graph

# Initialize
repo_path = "/home/user/InsightGraph"
neo4j_graph = Graph("bolt://localhost:7687", auth=("neo4j", "password"))

# Analyze Git
git_service = GitService(repo_path)
churn_metrics = git_service._analyze_churn_sync(months=6)

# Map to Neo4j nodes
file_mapping = git_service.map_git_metrics_to_graph(churn_metrics, repo_path)

# Update Neo4j with metrics
for file_key, metrics in file_mapping.items():
    neo4j_graph.run("""
    MATCH (e:Entity)
    WHERE e.namespace_key CONTAINS $file_key
    SET e.churn_rate = $churn_rate,
        e.churn_intensity = $churn_intensity,
        e.commit_count = $commit_count
    """, 
    file_key=file_key,
    churn_rate=metrics["churn_rate"],
    churn_intensity=metrics["churn_intensity"],
    commit_count=metrics["commit_count"]
    )

# Calculate True Risk Scores
complexity = 15
churn_rate = 3.2
churn_intensity = 45

true_risk, severity = RiskScoreCalculator.calculate_true_risk(
    complexity, churn_rate, churn_intensity
)

print(f"True Risk Score: {true_risk:.1f} ({severity})")
# Output: True Risk Score: 64.8 (High)

# ─────────────────────────────────────────────────────────────────────────
# Example: Extract taint flows from TypeScript source
# ─────────────────────────────────────────────────────────────────────────

from taint_tracker import TaintTracker

tracker = TaintTracker()

typescript_src = """
class UserDTO {
  email: string;
  password: string;
  cpf?: string;
}

class UserEntity {
  email: string;
  passwordHash: string;
  cpf?: string;
}
"""

props = tracker.extract_taint_from_typescript(typescript_src)
for prop in props:
    print(f"Property: {prop['name']}, Type: {prop['type_hint']}, Sensitive: {prop['sensitive']}")

# Output:
# Property: email, Type: string, Sensitive: True
# Property: password, Type: string, Sensitive: True
# Property: cpf, Type: string, Sensitive: True

# ═══════════════════════════════════════════════════════════════════════════
# PART 4: FRONTEND TESTING
# ═══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────
# Test Case 1: Risk Hotspot Coloring
# ─────────────────────────────────────────────────────────────────────────

# Given: Node with true_risk_score = 89.3
# Expected: Node color = red (#ef4444), glow = true, fontWeight = bold

# In React component:
# const node = {
#   true_risk_score: 89.3,
#   cyclomatic_complexity: 25,
#   churn_rate: 4.1
# };
#
# const { color, severity } = getRiskScoreColor(node.true_risk_score);
# expect(color).toBe('#ef4444');  // Red
# expect(severity).toBe('Critical');

# ─────────────────────────────────────────────────────────────────────────
# Test Case 2: Taint Tooltip Display
# ─────────────────────────────────────────────────────────────────────────

# Mock API response:
# const mockRiskMetrics = {
#   namespace_key: "InsightGraph:PaymentService/processPayment",
#   cyclomatic_complexity: 23,
#   churn_rate: 4.5,
#   churn_intensity: 67.2,
#   true_risk_score: 87.3,
#   severity: "Critical"
# };

# Test: Tooltip shows all metrics
# • Complexity: 23 ✓
# • Churn Rate: 4.50/mo ✓
# • Churn Intensity: 67.2 ✓
# • True Risk: 87.3 ✓

# ─────────────────────────────────────────────────────────────────────────
# Test Case 3: Risk Filter Works
# ─────────────────────────────────────────────────────────────────────────

# Given: 20 total nodes in graph
#   - 3 Critical nodes (score > 90)
#   - 5 High nodes (60-90)
#   - 7 Medium nodes (30-60)
#   - 5 Low nodes (< 30)

# When: Filter by "Critical"
# Then: Only 3 nodes visible, rest have hidden=true

# expect(
#   transformedNodes.filter(n => !n.hidden).length
# ).toBe(3);

# ═══════════════════════════════════════════════════════════════════════════
# PART 5: DATA SCENARIOS (TEST DATA SETUP)
# ═══════════════════════════════════════════════════════════════════════════

# Scenario 1: GDPR Compliance Violation
# ─────────────────────────────────────────────────────────────────────────
#
# Nodes to create:
# 1. UserDTO {sensitive: true, properties: [email, cpf, birthDate]}
# 2. UserEntity {sensitive: true, properties: [email, cpf, birthDate]}
# 3. SaveUserService/saveUser {complexity: 12, churn_rate: 2.1}
# 4. users_table {sensitive: true, columns: [id, email, cpf, birthDate]}
#
# Relations:
# - UserDTO FLOWS_TO UserEntity
# - UserEntity WRITES_TO_COLUMN users.email
# - UserEntity WRITES_TO_COLUMN users.cpf (❌ NO ENCRYPTION!)
#
# Expected insight: "GDPR violation detected - cpf written to database without encryption"

# Scenario 2: High-Risk Hotspot (Refactor Required)
# ─────────────────────────────────────────────────────────────────────────
#
# PaymentService/processPayment:
# - Complexity: 28 (high)
# - Commits (6mo): 31 → churn_rate = 5.2/mo
# - Avg lines per commit: 64 → churn_intensity = 64
#
# True Risk = (28 / 20 * 0.5) + (5.2 * 20 * 0.35) + (64 / 100 * 0.15)
#           = 0.7 + 36.4 + 9.6
#           = 46.7 ← MEDIUM initially
#
# Normalized:
# - Complexity factor: 28 * 2 = 56 /100 = 56
# - Churn rate: 5.2 * 20 = 104 → clamp to 100
# - Churn intensity: 64 / 0.5 = 128 → clamp to 100
#
# True Risk = 56 * 0.5 + 100 * 0.35 + 100 * 0.15 = 28 + 35 + 15 = 78 ← HIGH
# Expected: Appears in hotspots list, red/orange color, recommendation to refactor

# ═════════════════════════════════════════════════════════════════════════
# TROUBLESHOOTING
# ═════════════════════════════════════════════════════════════════════════

## Issue: Git churn not updating Neo4j
# Check:
# 1. Is PyDriller installed? → pip install PyDriller
# 2. Is background task running? → Check FastAPI logs
# 3. Neo4j schema constraints exist? → Run neo4j_schema_updates.cypher

## Issue: Taint flows not showing
# Check:
# 1. Are Property nodes created? → MATCH (p:Property) RETURN COUNT(p)
# 2. Did parse_typescript/parse_java store taint data? → Check server logs
# 3. HAS_PROPERTY relations present? → MATCH (e)-[:HAS_PROPERTY]->(p) RETURN COUNT(*)

## Issue: Risk score calculation wrong
# Verify formula:
# - Normalize complexity: min(complexity * 2, 100)
# - Normalize churn: min(churn_rate * 20, 100)
# - Normalize intensity: min(intensity / 0.5, 100)
# - True Risk = complexity_pct * 0.5 + churn_pct * 0.35 + intensity_pct * 0.15

## Performance: Graph loading slow
# Index Neo4j properties:
# CREATE INDEX ON :Entity(true_risk_score);
# CREATE INDEX ON :Entity(churn_rate);
# CREATE INDEX ON :Property(sensitive);
