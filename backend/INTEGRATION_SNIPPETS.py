"""
QUICK INTEGRATION CODE SNIPPETS
====================================================================
Copy-paste code for main.py integration (Phase 2 & 3)

Each section can be directly added to main.py
Follow the INTEGRATION_GUIDE.md for context on where to paste

THIS IS DOCUMENTATION ONLY - All code examples are for reference
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 1: Imports (Add after existing imports in main.py)
# ════════════════════════════════════════════════════════════════════

"""
from taint_tracker import TaintTracker, DataFlowNode, DataFlowEdge
from git_service import GitService, RiskScoreCalculator, analyze_and_update_git_churn
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 2: Update Neo4jService.__init__()
# ════════════════════════════════════════════════════════════════════

"""
class Neo4jService:
    def __init__(self):
        self.graph: Optional[Graph] = None
        self.taint_tracker = TaintTracker()
        self.git_service = None
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 3: Add to Neo4jService.ensure_indexes()
# ════════════════════════════════════════════════════════════════════

"""
    def ensure_indexes(self):
        # Create indexes for Neo4j
        try:
            # Existing indexes...
            
            # NEW: Indexes for taint analysis
            self.graph.run('''
            CREATE INDEX ON :Property(property_key) IF NOT EXISTS;
            CREATE INDEX ON :Column(column_key) IF NOT EXISTS;
            CREATE INDEX ON :DataFlow(flow_key) IF NOT EXISTS;
            ''')
            
            # NEW: Indexes for churn analysis
            self.graph.run('''
            CREATE INDEX ON :Entity(churn_rate) IF NOT EXISTS;
            CREATE INDEX ON :Entity(true_risk_score) IF NOT EXISTS;
            ''')
        except Exception as e:
            logger.warning("Could not create indexes: %s", e)
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 4: Update lifespan() for schema constraints
# ════════════════════════════════════════════════════════════════════

"""
@asynccontextmanager
async def lifespan(application):
    # Connect to Neo4j on startup (non-fatal if unavailable).
    try:
        neo4j_service.connect()
        neo4j_service.ensure_indexes()
        
        # NEW: Setup taint analysis schema
        neo4j_service.graph.run('''
        CREATE CONSTRAINT property_unique IF NOT EXISTS
        FOR (p:Property) REQUIRE p.property_key IS UNIQUE;
        ''')
        neo4j_service.graph.run('''
        CREATE CONSTRAINT column_unique IF NOT EXISTS
        FOR (c:Column) REQUIRE c.column_key IS UNIQUE;
        ''')
        
        logger.info("Neo4j schema initialized")
    except Exception as e:
        logger.warning("Neo4j not available at startup: %s. Start Neo4j and retry.", e)
    yield
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 5: Update parse_typescript() to extract taint data
# ════════════════════════════════════════════════════════════════════

"""
# Add this AFTER the existing parse_typescript logic for creating nodes:

def parse_typescript(content: str, path: str, project_name: str) -> dict:
    # ... existing implementation ...
    
    # NEW: Extract taint information
    if neo4j_service.taint_tracker:
        property_nodes = neo4j_service.taint_tracker.extract_taint_from_typescript(content)
        
        for prop in property_nodes:
            try:
                # Create PROPERTY nodes in Neo4j
                neo4j_service.graph.run('''
                MATCH (cls:Entity {namespace_key: $class_key})
                CREATE (cls)-[:HAS_PROPERTY]->(prop:Property {
                    property_key: $property_key,
                    name: $name,
                    type_hint: $type_hint,
                    source_class: cls.namespace_key,
                    sensitive: $sensitive,
                    created_at: datetime()
                })
                ''', 
                class_key=prop.get("parent_class"),
                property_key=f"{project_name}:{prop['parent_class']}/{prop['name']}",
                name=prop['name'],
                type_hint=prop.get('type_hint', 'unknown'),
                sensitive=prop.get('sensitive', False))
            except Exception as e:
                logger.warning(f"Could not create property node: {e}")
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 6: Update parse_java() similarly
# ════════════════════════════════════════════════════════════════════

"""
# Add to parse_java() after node creation:

def parse_java(content: str, path: str, project_name: str) -> dict:
    # ... existing implementation ...
    
    # NEW: Extract taint information
    if neo4j_service.taint_tracker:
        property_nodes = neo4j_service.taint_tracker.extract_taint_from_java(content)
        
        for prop in property_nodes:
            try:
                neo4j_service.graph.run('''
                MATCH (cls:Entity {namespace_key: $class_key})
                CREATE (cls)-[:HAS_PROPERTY]->(prop:Property {
                    property_key: $property_key,
                    name: $name,
                    type_hint: $type_hint,
                    source_class: cls.namespace_key,
                    sensitive: $sensitive,
                    created_at: datetime()
                })
                ''', 
                class_key=prop.get("parent_class"),
                property_key=f"{project_name}:{prop['parent_class']}/{prop['name']}",
                name=prop['name'],
                type_hint=prop.get('type_hint', 'unknown'),
                sensitive=prop.get('sensitive', False))
            except Exception as e:
                logger.warning(f"Could not create property node: {e}")
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 7: Add taint trace endpoint
# ════════════════════════════════════════════════════════════════════

"""
@app.get("/api/taint/trace/{source_property}")
async def trace_taint(source_property: str):
    # Trace where a sensitive property flows through the codebase.
    try:
        result = neo4j_service.graph.run('''
        MATCH (prop:Property {name: $prop_name, sensitive: true})
        MATCH path = (prop)-[r:FLOWS_TO|TRANSFORMS_PROPERTY|WRITES_TO_COLUMN*1..10]->(target)
        RETURN {
            start_prop: prop.property_key,
            paths: collect(path),
            affected_components: collect(DISTINCT target.namespace_key)
        }
        ''', prop_name=source_property).to_dicts()
        
        return {
            "source": source_property,
            "flows": result,
            "recommendation": "Review each TRANSFORMS_PROPERTY for encryption/hashing"
        }
    except Exception as e:
        logger.error(f"Taint trace error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 8: Add risk metrics endpoint
# ════════════════════════════════════════════════════════════════════

"""
@app.get("/api/node/{node_key}/risk-metrics")
async def get_node_risk_metrics(node_key: str):
    # Get comprehensive risk metrics for a node.
    try:
        result = neo4j_service.graph.run('''
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
        ''', key=node_key).to_dict()
        
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
        logger.error(f"Risk metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 9: Update scan endpoint to trigger Git analysis
# ════════════════════════════════════════════════════════════════════

"""
@app.post("/api/scan")
async def scan_project(request: ScanRequest, background_tasks: BackgroundTasks):
    #
    # Scan project files and store in Neo4j.
    # Now triggers Git churn analysis as background task.
    #
    global scan_state
    
    scan_state = ScanStatus(status="scanning")
    
    async def do_scan():
        # ... existing scan logic (all the file parsing, node creation, etc.) ...
        
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
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 10: Update AntipatternData Pydantic model
# ════════════════════════════════════════════════════════════════════

"""
class AntipatternData(BaseModel):
    # ... existing fields ...
    circular_dependencies: list[dict] = []
    god_classes: list[dict] = []
    dead_code: list[dict] = []
    cloud_blockers: list[dict] = []
    hardcoded_secrets: list[dict] = []
    fat_controllers: list[dict] = []
    top_external_deps: list[dict] = []
    
    # NEW: Phase 2 Taint Analysis
    taint_sources: list[dict] = []
    sensitive_flows: list[dict] = []
    
    # NEW: Phase 3 Churn Metrics
    high_churn_methods: list[dict] = []
    true_risk_hotspots: list[dict] = []
    git_last_analyzed: Optional[str] = None
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 11: Update /api/antipatterns endpoint
# ════════════════════════════════════════════════════════════════════

"""
@app.get("/api/antipatterns")
async def get_antipatterns(project: Optional[str] = None):
    # Get comprehensive antipatterns analysis.
    try:
        # ... existing antipattern queries ...
        
        # NEW: Get sensitive data flows
        taint_flows = neo4j_service.graph.run('''
        MATCH (prop:Property {sensitive: true})
        MATCH path = (prop)-[r:FLOWS_TO|TRANSFORMS_PROPERTY*1..5]->(target)
        RETURN {
            source_property: prop.name,
            target: target.name,
            flow_path: [node in nodes(path) | node.name],
            is_encrypted: any(rel in relationships(path) WHERE rel.transformation_type = 'encryption')
        }
        ''').to_dicts()
        
        # NEW: Get high-risk components
        high_risk = neo4j_service.graph.run('''
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
        ''').to_dicts()
        
        return AntipatternData(
            # ...existing fields populated...
            sensitive_flows=taint_flows,
            true_risk_hotspots=high_risk,
            git_last_analyzed=datetime.datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error in antipatterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""

# ════════════════════════════════════════════════════════════════════
# SNIPPET 12: Dependencies (requirements.txt addition)
# ════════════════════════════════════════════════════════════════════

"""
ADD THIS LINE TO requirements.txt:
PyDriller==2.5  # For Git analysis
"""

# ════════════════════════════════════════════════════════════════════
# FRONTEND SNIPPETS - See GraphCanvas.integration.tsx
# ════════════════════════════════════════════════════════════════════

"""
SNIPPET 13: Update src/api.ts with new interfaces & functions

export interface RiskMetrics {
  namespace_key: string;
  cyclomatic_complexity: number;
  churn_rate: number;
  churn_intensity: number;
  commit_count: number;
  true_risk_score: number;
  severity: 'Low' | 'Medium' | 'High' | 'Critical';
  color: {
    color: '#22c55e' | '#eab308' | '#f97316' | '#ef4444';
    label: string;
  };
}

export async function getNodeRiskMetrics(nodeKey: string): Promise<RiskMetrics> {
  const response = await fetch(`/api/node/${nodeKey}/risk-metrics`);
  if (!response.ok) throw new Error('Failed to fetch risk metrics');
  return response.json();
}

export interface TaintTraceResult {
  source: string;
  flows: Array<{
    start_prop: string;
    paths: any[];
    affected_components: string[];
  }>;
  recommendation: string;
}

export async function traceTaintFlow(propertyName: string): Promise<TaintTraceResult> {
  const response = await fetch(`/api/taint/trace/${propertyName}`);
  if (!response.ok) throw new Error('Taint trace failed');
  return response.json();
}
"""

# ════════════════════════════════════════════════════════════════════
# INTEGRATION GUIDE - QUICK START
# ════════════════════════════════════════════════════════════════════

"""
STEP-BY-STEP INTEGRATION:

1. Add Imports (Snippet 1)
   - Location: main.py, after existing imports
   - What: Import new services (TaintTracker, GitService, RiskScoreCalculator)

2. Update Neo4jService.__init__ (Snippet 2)
   - Location: Neo4jService class
   - What: Add taint_tracker and graph type hints

3. Add Indexes (Snippet 3)
   - Location: Neo4jService.ensure_indexes() method
   - What: Create Neo4j indexes for taint analysis and churn data

4. Update Lifespan (Snippet 4)
   - Location: lifespan() context manager
   - What: Add schema constraints for Property and Column nodes

5. Parse TypeScript (Snippet 5)
   - Location: parse_typescript() function
   - What: Extract property/field taint data into Neo4j nodes

6. Parse Java (Snippet 6)
   - Location: parse_java() function
   - What: Extract property/field taint data from Java classes

7. Taint Trace Endpoint (Snippet 7)
   - Location: Add new endpoint in FastAPI app
   - What: REST endpoint to trace sensitive data flows

8. Risk Metrics Endpoint (Snippet 8)
   - Location: Add new endpoint in FastAPI app (near other /api endpoints)
   - What: Calculate and return node risk scores combining complexity + churn

9. Update Scan Endpoint (Snippet 9)
   - Location: scan_project() endpoint in main.py
   - What: Trigger Git churn analysis as background task after code scan

10. Update Pydantic Models (Snippet 10)
    - Location: AntipatternData class
    - What: Add new fields for taint analysis and churn metrics

11. Update Antipatterns Endpoint (Snippet 11)
    - Location: get_antipatterns() function
    - What: Query and return taint flows + high-risk components

12. Update requirements.txt (Snippet 12)
    - Location: requirements.txt
    - What: Add PyDriller dependency for Git analysis

13. Update Frontend API (Snippet 13)
    - Location: src/api.ts in frontend project
    - What: Add TypeScript interfaces and async functions for risk metrics + taint tracing
    - See: GraphCanvas.integration.tsx for React component updates
"""
