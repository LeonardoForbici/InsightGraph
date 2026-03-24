"""
INTEGRATION GUIDE - main.py updates for Phase 2 & Phase 3

This file documents where and how to integrate:
1. taint_tracker.py (Phase 2 - Taint Analysis)
2. git_service.py (Phase 3 - Churn Analysis)
3. Neo4j schema updates

STEP 1: Add imports at top of main.py (after line 50)
────────────────────────────────────────────────────────────
from taint_tracker import TaintTracker, DataFlowNode, DataFlowEdge
from git_service import GitService, RiskScoreCalculator, analyze_and_update_git_churn

STEP 2: Initialize services in Neo4jService class (after __init__)
────────────────────────────────────────────────────────────
class Neo4jService:
    def __init__(self):
        self.graph: Optional[Graph] = None
        self.taint_tracker = TaintTracker()  # NEW
        self.git_service = None  # Will be initialized per project  # NEW

    def ensure_indexes(self):
        """Create indexes for Neo4j"""
        try:
            # Existing indexes...
            
            # NEW: Indexes for taint analysis
            self.graph.run("""
            CREATE INDEX ON :Property(property_key) IF NOT EXISTS;
            CREATE INDEX ON :Column(column_key) IF NOT EXISTS;
            CREATE INDEX ON :DataFlow(flow_key) IF NOT EXISTS;
            """)
            
            # NEW: Indexes for churn analysis
            self.graph.run("""
            CREATE INDEX ON :Entity(churn_rate) IF NOT EXISTS;
            CREATE INDEX ON :Entity(true_risk_score) IF NOT EXISTS;
            """)
        except Exception as e:
            logger.warning("Could not create indexes: %s", e)

STEP 3: Modify parse_typescript() to extract taint information (Find existing function)
────────────────────────────────────────────────────────────
def parse_typescript(content: str, path: str, project_name: str) -> dict:
    # ... existing implementation ...
    
    # AFTER extracting nodes and properties, ADD:
    # ─────────────────────────────────────────
    if neo4j_service.taint_tracker:
        # Extract properties from class declarations
        property_nodes = neo4j_service.taint_tracker.extract_taint_from_typescript(content)
        
        for prop in property_nodes:
            # Create PROPERTY nodes in Neo4j
            result = neo4j_service.graph.run("""
            MATCH (cls:Entity {namespace_key: $class_key})
            CREATE (cls)-[:HAS_PROPERTY]->(prop:Property {
                property_key: $property_key,
                name: $name,
                type_hint: $type_hint,
                source_class: cls.namespace_key,
                sensitive: $sensitive,
                created_at: datetime()
            })
            RETURN prop.property_key
            """, class_key=prop.get("parent_class"),
                property_key=f"{project_name}:{prop['parent_class']}/{prop['name']}",
                name=prop['name'],
                type_hint=prop.get('type_hint', 'unknown'),
                sensitive=prop.get('sensitive', False))

STEP 4: Modify parse_java() similarly
────────────────────────────────────────────────────────────
def parse_java(content: str, path: str, project_name: str) -> dict:
    # ... existing implementation ...
    
    if neo4j_service.taint_tracker:
        # Extract properties from Java classes
        property_nodes = neo4j_service.taint_tracker.extract_taint_from_java(content)
        
        # Same property node creation as above
        for prop in property_nodes:
            neo4j_service.graph.run("""
            MATCH (cls:Entity {namespace_key: $class_key})
            CREATE (cls)-[:HAS_PROPERTY]->(prop:Property {
                property_key: $property_key,
                name: $name,
                type_hint: $type_hint,
                source_class: cls.namespace_key,
                sensitive: $sensitive,
                created_at: datetime()
            })
            """, class_key=prop.get("parent_class"),
                property_key=f"{project_name}:{prop['parent_class']}/{prop['name']}",
                name=prop['name'],
                type_hint=prop.get('type_hint', 'unknown'),
                sensitive=prop.get('sensitive', False))

STEP 5: Modify parse_sql_with_ollama() to extract column information
────────────────────────────────────────────────────────────
def parse_sql_with_ollama(content: str, path: str, project_name: str) -> dict:
    # ... existing SQL parsing ...
    
    # AFTER parsing tables, ADD:
    # ─────────────────────────────────────────
    # Extract column operations (SELECT, UPDATE, INSERT)
    flow_edges = neo4j_service.taint_tracker.track_column_access(content)
    
    for edge in flow_edges:
        operation_type = edge.flow_type  # "reads", "writes"
        relation_type = "READS_FROM_COLUMN" if operation_type == "reads" else "WRITES_TO_COLUMN"
        
        neo4j_service.graph.run(f"""
        MATCH (method:Entity {{namespace_key: $method_key}})
        MATCH (col:Column {{column_key: $column_key}})
        CREATE (method)-[:{relation_type} {{
            operation: $operation,
            context: $context,
            discovered_at: datetime()
        }}]->(col)
        """, method_key=edge.from_key, column_key=edge.to_key,
            operation=edge.context.upper().split()[0],
            context=edge.context)

STEP 6: Add new endpoint for taint analysis API
────────────────────────────────────────────────────────────
@app.post("/api/taint/trace/{source_property}")
async def trace_taint(source_property: str):
    """
    Trace where a sensitive property flows through the codebase.
    Example: GET /api/taint/trace/email
    Returns: List of nodes and edges showing data flow
    """
    try:
        # Query taint flows from source property
        result = neo4j_service.graph.run("""
        MATCH (prop:Property {name: $prop_name, sensitive: true})
        MATCH path = (prop)-[r:FLOWS_TO|TRANSFORMS_PROPERTY|WRITES_TO_COLUMN*1..10]->(target)
        RETURN {
            start_prop: prop.property_key,
            paths: collect(path),
            affected_components: collect(DISTINCT target.namespace_key)
        }
        """, prop_name=source_property).to_dicts()
        
        return {
            "source": source_property,
            "flows": result,
            "recommendation": "Review each TRANSFORMS_PROPERTY for encryption/hashing"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

STEP 7: Add endpoint for risk metrics
────────────────────────────────────────────────────────────
@app.get("/api/node/{node_key}/risk-metrics")
async def get_node_risk_metrics(node_key: str):
    """
    Get comprehensive risk metrics for a node.
    Returns: complexity, churn_rate, churn_intensity, true_risk_score, severity
    """
    try:
        result = neo4j_service.graph.run("""
        MATCH (n:Entity {namespace_key: $key})
        RETURN {
            namespace_key: n.namespace_key,
            cyclomatic_complexity: n.cyclomatic_complexity,
            churn_rate: coalesce(n.churn_rate, 0),
            churn_intensity: coalesce(n.churn_intensity, 0),
            commit_count: coalesce(n.commit_count, 0),
            true_risk_score: coalesce(n.true_risk_score, 0),
            git_analyzed_at: n.git_analyzed_at
        }
        """, key=node_key).to_dict()
        
        if result:
            complexity = result.get("cyclomatic_complexity", 0)
            churn_rate = result.get("churn_rate", 0)
            churn_intensity = result.get("churn_intensity", 0)
            
            true_risk, severity = RiskScoreCalculator.calculate_true_risk(
                complexity, churn_rate, churn_intensity
            )
            
            return {
                **result,
                "true_risk_score": true_risk,
                "severity": severity,
                "color": RiskScoreCalculator.get_hotspot_color(true_risk)
            }
        else:
            raise HTTPException(status_code=404, detail="Node not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

STEP 8: Modify scan endpoint to trigger Git analysis
────────────────────────────────────────────────────────────
@app.post("/api/scan")
async def scan_project(request: ScanRequest, background_tasks: BackgroundTasks):
    """
    Scan project files and store in Neo4j.
    MODIFICATION: Add Git churn analysis as background task
    """
    global scan_state
    
    scan_state = ScanStatus(status="scanning")
    
    async def do_scan():
        # ... existing scan logic ...
        
        # AFTER completing code scan, ADD background task for Git analysis:
        for project_path in request.paths:
            logger.info(f"Queuing Git churn analysis for {project_path}")
            background_tasks.add_task(
                analyze_and_update_git_churn,
                project_path,
                neo4j_service
            )
    
    asyncio.create_task(do_scan())
    return {"status": "scanning", "message": "Project scan started (code + Git churn in background)"}

STEP 9: Run Neo4j schema setup
────────────────────────────────────────────────────────────
# Execute neo4j_schema_updates.cypher in Neo4j Browser or run:
# MATCH (n) DETACH DELETE n;  # Clean start (OPTIONAL)
# Then execute each CREATE CONSTRAINT and query from neo4j_schema_updates.cypher

ALTERNATIVE: Add schema setup to lifespan:
────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application):
    try:
        neo4j_service.connect()
        neo4j_service.ensure_indexes()
        
        # NEW: Setup taint analysis schema
        neo4j_service.graph.run("""
        CREATE CONSTRAINT property_unique IF NOT EXISTS
        FOR (p:Property) REQUIRE p.property_key IS UNIQUE;
        """)
        neo4j_service.graph.run("""
        CREATE CONSTRAINT column_unique IF NOT EXISTS
        FOR (c:Column) REQUIRE c.column_key IS UNIQUE;
        """)
        
        logger.info("Neo4j schema initialized")
    except Exception as e:
        logger.warning("Neo4j setup error: %s", e)
    
    yield

STEP 10: Update AntipatternData model to include risk metrics
────────────────────────────────────────────────────────────
# In Pydantic models section, extend AntipatternData:

class AntipatternData(BaseModel):
    # ... existing fields ...
    
    # Phase 2: Taint Analysis
    taint_sources: list[dict] = []  # Properties/columns with sensitive data flows
    sensitive_flows: list[dict] = []  # Trace of sensitive data movement
    
    # Phase 3: Churn Metrics
    high_churn_methods: list[dict] = []  # Methods changed frequently
    true_risk_hotspots: list[dict] = []  # Complexity × Churn risk areas
    git_last_analyzed: Optional[str] = None

STEP 11: Update /api/antipatterns endpoint
────────────────────────────────────────────────────────────
@app.get("/api/antipatterns")
async def get_antipatterns(project: Optional[str] = None):
    """
    Get comprehensive antipatterns analysis.
    MODIFICATION: Include taint analysis and risk metrics
    """
    try:
        # ... existing antipattern queries ...
        
        # NEW: Get sensitive data flows
        taint_flows = neo4j_service.graph.run("""
        MATCH (prop:Property {sensitive: true})
        MATCH path = (prop)-[r:FLOWS_TO|TRANSFORMS_PROPERTY*1..5]->(target)
        RETURN {
            source_property: prop.name,
            target: target.name,
            flow_path: [node in nodes(path) | node.name],
            is_encrypted: any(rel in relationships(path) WHERE rel.transformation_type = 'encryption')
        }
        """).to_dicts()
        
        # NEW: Get high-risk components
        high_risk = neo4j_service.graph.run("""
        MATCH (e:Entity)
        WHERE e.cyclomatic_complexity > 10 AND e.churn_rate > 2
        RETURN {
            namespace_key: e.namespace_key,
            complexity: e.cyclomatic_complexity,
            churn_rate: e.churn_rate,
            true_risk_score: (e.cyclomatic_complexity * 0.5) + (e.churn_rate * 3.5)
        }
        ORDER BY true_risk_score DESC
        LIMIT 10
        """).to_dicts()
        
        return AntipatternData(
            # ...existing fields...
            sensitive_flows=taint_flows,
            true_risk_hotspots=high_risk,
            git_last_analyzed=datetime.datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error in antipatterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))

═════════════════════════════════════════════════════════════════════
TESTING CHECKLIST
═════════════════════════════════════════════════════════════════════

Phase 2 (Taint Analysis) Tests:
✓ Parse TypeScript file with UserDTO → ResponseDTO
✓ Verify Property nodes created with sensitive=true
✓ Query FLOWS_TO relationships
✓ GET /api/taint/trace/email returns flow path
✓ Verify TRANSFORMS_PROPERTY shown when encryption applied

Phase 3 (Churn Analysis) Tests:
✓ POST /api/scan triggers Git analysis in background
✓ Verify ChurnMetrics calculated for scanned files
✓ GET /api/node/UserService/getUser/risk-metrics shows churn_rate
✓ True Risk Score > 50 for high-complexity + high-churn components
✓ GraphCanvas displays nodes with color intensity based on true_risk_score

Integration Tests:
✓ Full data flow from DTO property → method call → column write
✓ Sensitive data tracking through transformations
✓ Risk hotspots correctly identified and scored

═════════════════════════════════════════════════════════════════════
DEPENDENCIES TO INSTALL
═════════════════════════════════════════════════════════════════════

pip install PyDriller  # For Git churn analysis
# Already have: py2neo, tree-sitter, httpx, fastapi

═════════════════════════════════════════════════════════════════════
"""
