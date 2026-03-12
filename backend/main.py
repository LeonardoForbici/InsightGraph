"""
InsightGraph - Software Intelligence Backend
FastAPI application with tree-sitter parsing, dual Ollama AI integration, and Neo4j persistence.

Models:
  - qwen3-coder-next:q4_K_M  → Code scanner / SQL parser (motor de código)
  - qwen3:8b                  → Semantic AI for Q&A (interface inteligente)
"""

import os
import sys
import json
import asyncio
import logging
import datetime
import argparse
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from py2neo import Graph, Node, Relationship

# ──────────────────────────────────────────────
# tree-sitter imports
# ──────────────────────────────────────────────
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Tier 1: Fast Scan (Ultra veloz, não trava o PC no scan)
OLLAMA_FAST_MODEL = os.getenv("OLLAMA_FAST_MODEL", "qwen2.5-coder:1.5b")
# Tier 2: Chat & Q&A (Conversa melhor e entende o negócio)
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen3.5:4b")
# Tier 3: Complex Analysis (Inteligência máxima, mas lento)
OLLAMA_COMPLEX_MODEL = os.getenv("OLLAMA_COMPLEX_MODEL", "qwen3-coder-next:q4_K_M")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insightgraph")

# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application):
    """Connect to Neo4j on startup (non-fatal if unavailable)."""
    try:
        neo4j_service.connect()
        neo4j_service.ensure_indexes()
    except Exception as e:
        logger.warning("Neo4j not available at startup: %s. Start Neo4j and retry.", e)
    yield

app = FastAPI(
    title="InsightGraph API",
    description="Software architecture analysis, impact visualization, and AI-powered Q&A",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────
class ScanRequest(BaseModel):
    paths: list[str]

class ScanStatus(BaseModel):
    status: str
    scanned_files: int = 0
    total_files: int = 0
    total_nodes: int = 0
    total_relationships: int = 0
    progress_percent: float = 0.0
    current_file: str = ""
    errors: list[str] = []

class AskRequest(BaseModel):
    question: str
    context_node: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    relevant_nodes: list[str] = []
    model: str
    context_used: int = 0

class SimulateRequest(BaseModel):
    deleted_nodes: list[str] = []
    added_edges: list[dict] = []  # [{"source": "A", "target": "B", "type": "CALLS"}]

class GraphStats(BaseModel):
    total_nodes: int = 0
    total_edges: int = 0
    nodes_by_type: dict[str, int] = {}
    edges_by_type: dict[str, int] = {}
    layers: dict[str, int] = {}
    projects: list[str] = []

class HealthStatus(BaseModel):
    neo4j: str = "disconnected"
    ollama_scanner: str = "unknown"
    ollama_chat: str = "unknown"
    scanner_model: str = OLLAMA_FAST_MODEL
    chat_model: str = OLLAMA_CHAT_MODEL
    complex_model: str = OLLAMA_COMPLEX_MODEL

# Global state
scan_state = ScanStatus(status="idle")
ai_busy = False  # True while Qwen Q&A is processing

# In-memory graph storage (works even without Neo4j)
memory_nodes: list[dict] = []
memory_edges: list[dict] = []

# ──────────────────────────────────────────────
# Neo4j Service
# ──────────────────────────────────────────────
class Neo4jService:
    def __init__(self):
        self.graph: Optional[Graph] = None

    def connect(self):
        try:
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            logger.info("Connected to Neo4j at %s", NEO4J_URI)
            return True
        except Exception as e:
            logger.warning("Failed to connect to Neo4j: %s", e)
            self.graph = None
            return False

    @property
    def is_connected(self) -> bool:
        return self.graph is not None

    def ensure_indexes(self):
        """Create indexes and constraints for performance."""
        queries = [
            "CREATE INDEX idx_namespace IF NOT EXISTS FOR (n:Entity) ON (n.namespace_key)",
            "CREATE INDEX idx_project IF NOT EXISTS FOR (n:Entity) ON (n.project)",
            "CREATE INDEX idx_layer IF NOT EXISTS FOR (n:Entity) ON (n.layer)",
            "CREATE INDEX idx_java_class IF NOT EXISTS FOR (n:Java_Class) ON (n.namespace_key)",
            "CREATE INDEX idx_java_method IF NOT EXISTS FOR (n:Java_Method) ON (n.namespace_key)",
            "CREATE INDEX idx_ts_component IF NOT EXISTS FOR (n:TS_Component) ON (n.namespace_key)",
            "CREATE INDEX idx_ts_function IF NOT EXISTS FOR (n:TS_Function) ON (n.namespace_key)",
            "CREATE INDEX idx_sql_table IF NOT EXISTS FOR (n:SQL_Table) ON (n.namespace_key)",
            "CREATE INDEX idx_sql_procedure IF NOT EXISTS FOR (n:SQL_Procedure) ON (n.namespace_key)",
            "CREATE INDEX idx_mobile_component IF NOT EXISTS FOR (n:Mobile_Component) ON (n.namespace_key)",
        ]
        for q in queries:
            try:
                self.graph.run(q)
            except Exception as e:
                logger.warning("Index query warning: %s", e)
        logger.info("Neo4j indexes ensured")

    def merge_node(self, label: str, namespace_key: str, properties: dict) -> None:
        """MERGE a node by namespace_key to avoid duplicates."""
        props = {**properties, "namespace_key": namespace_key}
        prop_str = ", ".join(f"n.{k} = ${k}" for k in props if k != "namespace_key")
        query = f"""
        MERGE (n:{label}:Entity {{namespace_key: $namespace_key}})
        ON CREATE SET {prop_str}
        ON MATCH SET {prop_str}
        """
        self.graph.run(query, **props)

    def merge_relationship(self, from_key: str, to_key: str, rel_type: str, props: dict = None) -> None:
        """MERGE a relationship between two nodes by namespace_key."""
        prop_clause = ""
        params = {"from_key": from_key, "to_key": to_key}
        if props:
            prop_clause = " SET " + ", ".join(f"r.{k} = ${k}" for k in props)
            params.update(props)
        query = f"""
        MATCH (a:Entity {{namespace_key: $from_key}})
        MATCH (b:Entity {{namespace_key: $to_key}})
        MERGE (a)-[r:{rel_type}]->(b)
        {prop_clause}
        """
        self.graph.run(query, **params)

    def get_full_graph(self, project: str = None, layer: str = None) -> dict:
        """Return all nodes and edges, optionally filtered."""
        where_clauses = []
        params = {}
        if project:
            where_clauses.append("n.project = $project")
            params["project"] = project
        if layer:
            where_clauses.append("n.layer = $layer")
            params["layer"] = layer

        where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        node_query = f"MATCH (n:Entity) {where} RETURN n LIMIT 2000"
        nodes_result = self.graph.run(node_query, **params).data()

        rel_query = f"""
        MATCH (a:Entity)-[r]->(b:Entity)
        {where.replace('n.', 'a.')}
        RETURN a.namespace_key AS source, b.namespace_key AS target, type(r) AS rel_type
        LIMIT 5000
        """
        rels_result = self.graph.run(rel_query, **params).data()

        nodes = []
        for record in nodes_result:
            node = record["n"]
            node_data = dict(node)
            node_data["labels"] = list(node.labels)
            nodes.append(node_data)

        edges = [
            {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
            for r in rels_result
        ]

        return {"nodes": nodes, "edges": edges}

    def get_impact(self, node_key: str) -> dict:
        """Return upstream and downstream neighbors of a node."""
        upstream_query = """
        MATCH (upstream:Entity)-[r]->(target:Entity {namespace_key: $key})
        RETURN upstream.namespace_key AS key, upstream.name AS name, 
               labels(upstream) AS labels, type(r) AS rel_type
        LIMIT 100
        """
        downstream_query = """
        MATCH (target:Entity {namespace_key: $key})-[r]->(downstream:Entity)
        RETURN downstream.namespace_key AS key, downstream.name AS name,
               labels(downstream) AS labels, type(r) AS rel_type
        LIMIT 100
        """
        upstream = self.graph.run(upstream_query, key=node_key).data()
        downstream = self.graph.run(downstream_query, key=node_key).data()

        return {"upstream": upstream, "downstream": downstream}

    def get_projects(self) -> list[str]:
        """List all distinct project names."""
        result = self.graph.run("MATCH (n:Entity) RETURN DISTINCT n.project AS project").data()
        return [r["project"] for r in result if r["project"]]

    def get_stats(self) -> dict:
        """Return comprehensive graph statistics."""
        stats = {
            "total_nodes": 0,
            "total_edges": 0,
            "nodes_by_type": {},
            "edges_by_type": {},
            "layers": {},
            "projects": [],
        }

        try:
            # Total nodes
            result = self.graph.run("MATCH (n:Entity) RETURN count(n) AS cnt").data()
            stats["total_nodes"] = result[0]["cnt"] if result else 0

            # Total edges
            result = self.graph.run("MATCH ()-[r]->() RETURN count(r) AS cnt").data()
            stats["total_edges"] = result[0]["cnt"] if result else 0

            # Nodes by type (excluding the 'Entity' label)
            result = self.graph.run("""
                MATCH (n:Entity)
                WITH [l IN labels(n) WHERE l <> 'Entity'][0] AS lbl
                RETURN lbl, count(*) AS cnt
                ORDER BY cnt DESC
            """).data()
            stats["nodes_by_type"] = {r["lbl"]: r["cnt"] for r in result if r["lbl"]}

            # Edges by type
            result = self.graph.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS rel_type, count(*) AS cnt
                ORDER BY cnt DESC
            """).data()
            stats["edges_by_type"] = {r["rel_type"]: r["cnt"] for r in result}

            # Layers
            result = self.graph.run("""
                MATCH (n:Entity)
                WHERE n.layer IS NOT NULL
                RETURN n.layer AS layer, count(*) AS cnt
                ORDER BY cnt DESC
            """).data()
            stats["layers"] = {r["layer"]: r["cnt"] for r in result}

            # Projects
            result = self.graph.run("MATCH (n:Entity) RETURN DISTINCT n.project AS project").data()
            stats["projects"] = [r["project"] for r in result if r["project"]]

        except Exception as e:
            logger.error("Error fetching stats: %s", e)

        return stats

    def get_graph_context(self, node_key: str = None, limit: int = 50) -> str:
        """Build a text summary of the graph for AI context."""
        try:
            if node_key:
                # Get context around a specific node
                query = """
                MATCH (center:Entity {namespace_key: $key})
                OPTIONAL MATCH (upstream:Entity)-[r1]->(center)
                OPTIONAL MATCH (center)-[r2]->(downstream:Entity)
                WITH center, 
                     collect(DISTINCT {name: upstream.name, type: type(r1), labels: labels(upstream)}) AS ups,
                     collect(DISTINCT {name: downstream.name, type: type(r2), labels: labels(downstream)}) AS downs
                RETURN center.name AS name, center.layer AS layer, labels(center) AS labels,
                       coalesce(center.complexity, 1) AS complexity, coalesce(center.loc, 0) AS loc,
                       ups, downs
                """
                result = self.graph.run(query, key=node_key).data()
                if not result:
                    return "Nó não encontrado no grafo."

                r = result[0]
                lines = [f"Nó: {r['name']} (Layer: {r['layer']}, Labels: {r['labels']}, Complexidade: {r['complexity']}, Linhas: {r['loc']})"]
                for u in r["ups"]:
                    if u["name"]:
                        lines.append(f"  ← {u['name']} [{u['type']}]")
                for d in r["downs"]:
                    if d["name"]:
                        lines.append(f"  → {d['name']} [{d['type']}]")
                return "\n".join(lines)
            else:
                # Get a general summary of the graph
                nodes_query = """
                MATCH (n:Entity)
                WITH [l IN labels(n) WHERE l <> 'Entity'][0] AS type, n.name AS name, 
                     n.layer AS layer, n.project AS project
                RETURN type, name, layer, project
                ORDER BY type, name
                LIMIT $limit
                """
                result = self.graph.run(nodes_query, limit=limit).data()

                rels_query = """
                MATCH (a:Entity)-[r]->(b:Entity)
                RETURN a.name AS source, type(r) AS rel, b.name AS target
                LIMIT $limit
                """
                rels = self.graph.run(rels_query, limit=limit).data()

                lines = ["=== Nós do Sistema ==="]
                for r in result:
                    lines.append(f"  [{r['type']}] {r['name']} (Layer: {r['layer']}, Project: {r['project']})")

                lines.append("\n=== Relacionamentos ===")
                for r in rels:
                    lines.append(f"  {r['source']} --[{r['rel']}]--> {r['target']}")

                return "\n".join(lines)

        except Exception as e:
            logger.error("Error building graph context: %s", e)
            return "Erro ao buscar contexto do grafo."


neo4j_service = Neo4jService()

def get_memory_graph_context(node_key: str = None, limit: int = 50) -> str:
    """Build a text summary of the graph from memory for AI context."""
    global memory_nodes, memory_edges
    try:
        if node_key:
            # Get context around a specific node
            node = next((n for n in memory_nodes if n["namespace_key"] == node_key), None)
            if not node:
                return "Nó não encontrado no grafo em memória."

            lines = [f"Nó: {node.get('name')} (Layer: {node.get('layer')}, Labels: {node.get('labels')}, Complexidade: {node.get('complexity', 1)}, Linhas: {node.get('loc', 0)})"]
            
            for edge in memory_edges:
                if edge["target"] == node_key:
                    src_node = next((n for n in memory_nodes if n["namespace_key"] == edge["source"]), None)
                    if src_node:
                        lines.append(f"  ← {src_node.get('name')} [{edge['type']}]")
                if edge["source"] == node_key:
                    tgt_node = next((n for n in memory_nodes if n["namespace_key"] == edge["target"]), None)
                    if tgt_node:
                        lines.append(f"  → {tgt_node.get('name')} [{edge['type']}]")
            return "\n".join(lines)
        else:
            # Get a general summary of the graph
            lines = ["=== Nós do Sistema (Memória) ==="]
            for n in memory_nodes[:limit]:
                type_lbl = [l for l in n.get("labels", []) if l != "Entity"]
                type_name = type_lbl[0] if type_lbl else "Desconhecido"
                lines.append(f"  [{type_name}] {n.get('name')} (Layer: {n.get('layer')}, Project: {n.get('project')})")

            lines.append("\n=== Relacionamentos ===")
            for e in memory_edges[:limit]:
                src_name = next((n.get("name") for n in memory_nodes if n["namespace_key"] == e["source"]), e["source"])
                tgt_name = next((n.get("name") for n in memory_nodes if n["namespace_key"] == e["target"]), e["target"])
                lines.append(f"  {src_name} --[{e['type']}]--> {tgt_name}")

            return "\n".join(lines)
    except Exception as e:
        logger.error("Error building memory graph context: %s", e)
        return "Erro ao buscar contexto do grafo em memória."
# Tree-Sitter Parsers
# ──────────────────────────────────────────────
JAVA_LANGUAGE = Language(tsjava.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())
TSX_LANGUAGE = Language(tstypescript.language_tsx())

java_parser = Parser(JAVA_LANGUAGE)
ts_parser = Parser(TS_LANGUAGE)
tsx_parser = Parser(TSX_LANGUAGE)


def _determine_java_layer(file_path: str, content: str) -> str:
    """Heuristic to determine the layer of a Java file."""
    fp = file_path.lower()
    c = content.lower()
    if "@restcontroller" in c or "@controller" in c or "controller" in fp:
        return "API"
    if "@service" in c or "service" in fp:
        return "Service"
    if "@repository" in c or "repository" in fp or "@entity" in c:
        return "Database"
    return "Service"

def _get_project_name(file_path: str, project_path: str) -> str:
    """Infer the specific project name. If the directory has sub-projects, return the sub-project name."""
    try:
        rel = os.path.relpath(file_path, project_path)
        parts = Path(rel).parts
        if len(parts) > 1:
            return parts[0]
        return Path(project_path).name
    except Exception:
        return Path(project_path).name


def _determine_ts_layer(file_path: str, content: str) -> str:
    """Heuristic to determine the layer of a TS/TSX file."""
    fp = file_path.lower()
    if ".tsx" in fp or "component" in fp or "page" in fp or "view" in fp:
        return "Frontend"
    if "service" in fp or "api" in fp:
        return "API"
    return "Frontend"


def calculate_metrics(node) -> dict:
    """Calculate basic code metrics from a tree-sitter node."""
    if not node:
        return {"loc": 0, "complexity": 1}
        
    loc = node.end_point[0] - node.start_point[0] + 1
    
    complexity_nodes = {
        "if_statement", "for_statement", "while_statement", "do_statement",
        "catch_clause", "switch_block", "switch_case", "switch_default",
        "ternary_expression", "conditional_expression"
    }
    
    complexity = 1
    def traverse(n):
        nonlocal complexity
        if n.type in complexity_nodes:
            complexity += 1
        
        # Check anonymous nodes for operators
        for child in n.children:
            if child.type in ("&&", "||", "?"):
                complexity += 1
            traverse(child)
            
    traverse(node)
    return {"loc": loc, "complexity": complexity}


def parse_java(file_path: str, content: str, project_path: str) -> dict:
    """Parse Java file using tree-sitter and extract classes, methods, decorators."""
    tree = java_parser.parse(content.encode("utf-8"))
    root = tree.root_node
    project_name = _get_project_name(file_path, project_path)
    rel_path = os.path.relpath(file_path, project_path).replace("\\", "/")
    layer = _determine_java_layer(file_path, content)

    entities = {"nodes": [], "relationships": []}

    # Find class declarations
    def find_classes(node):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = name_node.text.decode("utf-8")
                ns_key = f"{project_name}:{rel_path}:{class_name}"

                # Check for Spring annotations
                decorators = []
                if node.prev_sibling and node.prev_sibling.type == "modifiers":
                    for child in node.prev_sibling.children:
                        if child.type == "marker_annotation" or child.type == "annotation":
                            decorators.append(child.text.decode("utf-8"))

                metrics = calculate_metrics(node)
                entities["nodes"].append({
                    "label": "Java_Class",
                    "namespace_key": ns_key,
                    "name": class_name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    "decorators": ", ".join(decorators),
                    **metrics,
                })

                # Find methods within this class
                for child in node.children:
                    if child.type == "class_body":
                        for body_child in child.children:
                            if body_child.type == "method_declaration":
                                method_name_node = body_child.child_by_field_name("name")
                                if method_name_node:
                                    method_name = method_name_node.text.decode("utf-8")
                                    method_ns_key = f"{project_name}:{rel_path}:{class_name}.{method_name}"

                                    m_decorators = []
                                    if body_child.prev_sibling and body_child.prev_sibling.type == "modifiers":
                                        for mc in body_child.prev_sibling.children:
                                            if mc.type in ("marker_annotation", "annotation"):
                                                m_decorators.append(mc.text.decode("utf-8"))

                                    m_metrics = calculate_metrics(body_child)
                                    entities["nodes"].append({
                                        "label": "Java_Method",
                                        "namespace_key": method_ns_key,
                                        "name": method_name,
                                        "file": rel_path,
                                        "project": project_name,
                                        "layer": layer,
                                        "decorators": ", ".join(m_decorators),
                                        "parent_class": class_name,
                                        **m_metrics,
                                    })
                                    entities["relationships"].append({
                                        "from": ns_key,
                                        "to": method_ns_key,
                                        "type": "HAS_METHOD",
                                    })

        for child in node.children:
            find_classes(child)

    find_classes(root)

    # Find import statements for DEPENDS_ON relationships
    for child in root.children:
        if child.type == "import_declaration":
            import_text = child.text.decode("utf-8").replace("import ", "").replace(";", "").strip()
            if entities["nodes"]:
                entities["relationships"].append({
                    "from": entities["nodes"][0]["namespace_key"],
                    "to_import": import_text,
                    "type": "IMPORTS",
                })

    return entities


def parse_typescript(file_path: str, content: str, project_path: str) -> dict:
    """Parse TypeScript/TSX file using tree-sitter."""
    is_tsx = file_path.endswith(".tsx")
    parser = tsx_parser if is_tsx else ts_parser
    tree = parser.parse(content.encode("utf-8"))
    root = tree.root_node
    project_name = _get_project_name(file_path, project_path)
    rel_path = os.path.relpath(file_path, project_path).replace("\\", "/")
    layer = _determine_ts_layer(file_path, content)

    entities = {"nodes": [], "relationships": []}

    def find_entities(node):
        # Class declarations
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                ns_key = f"{project_name}:{rel_path}:{name}"
                entities["nodes"].append({
                    "label": "TS_Component",
                    "namespace_key": ns_key,
                    "name": name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    **calculate_metrics(node)
                })

        # Function declarations (including exported)
        if node.type in ("function_declaration", "arrow_function"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                ns_key = f"{project_name}:{rel_path}:{name}"
                entities["nodes"].append({
                    "label": "TS_Function",
                    "namespace_key": ns_key,
                    "name": name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    **calculate_metrics(node)
                })

        # Variable declarations with arrow functions (e.g., const MyComponent = () => {})
        if node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if name_node and value_node and value_node.type == "arrow_function":
                        name = name_node.text.decode("utf-8")
                        ns_key = f"{project_name}:{rel_path}:{name}"
                        label = "TS_Component" if is_tsx else "TS_Function"
                        entities["nodes"].append({
                            "label": label,
                            "namespace_key": ns_key,
                            "name": name,
                            "file": rel_path,
                            "project": project_name,
                            "layer": layer,
                            **calculate_metrics(value_node)
                        })

        # Export default function
        if node.type == "export_statement":
            for child in node.children:
                if child.type == "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = name_node.text.decode("utf-8")
                        ns_key = f"{project_name}:{rel_path}:{name}"
                        label = "TS_Component" if is_tsx else "TS_Function"
                        entities["nodes"].append({
                            "label": label,
                            "namespace_key": ns_key,
                            "name": name,
                            "file": rel_path,
                            "project": project_name,
                            "layer": layer,
                            **calculate_metrics(child)
                        })

        for child in node.children:
            find_entities(child)

    find_entities(root)

    # Find import statements
    for child in root.children:
        if child.type == "import_statement":
            source_node = child.child_by_field_name("source")
            if source_node and entities["nodes"]:
                import_path = source_node.text.decode("utf-8").strip("'\"")
                entities["relationships"].append({
                    "from": entities["nodes"][0]["namespace_key"],
                    "to_import": import_path,
                    "type": "IMPORTS",
                })

    return entities


# ──────────────────────────────────────────────
# Ollama SQL Parser (Motor: Coder-Next)
# ──────────────────────────────────────────────
async def parse_sql_with_ollama(file_path: str, content: str, project_path: str) -> dict:
    """Send SQL content to Ollama Coder-Next for analysis.
    Waits if Qwen Q&A is currently processing to avoid loading both models."""
    global ai_busy
    for _ in range(60):  # max 60s wait
        if not ai_busy:
            break
        await asyncio.sleep(1)
        logger.info("Waiting for Qwen Q&A to finish before calling Coder-Next...")
    project_name = _get_project_name(file_path, project_path)
    rel_path = os.path.relpath(file_path, project_path).replace("\\", "/")

    prompt = f"""Analyze this SQL code and return ONLY a valid JSON (no markdown, no explanation) with this exact structure:
{{
  "procedures": [
    {{
      "procedure_name": "string",
      "tables_read": ["table1", "table2"],
      "tables_written": ["table3"],
      "calls": ["other_procedure"]
    }}
  ],
  "tables": ["table1", "table2", "table3"]
}}

SQL Code:
```sql
{content[:4000]}
```"""

    entities = {"nodes": [], "relationships": []}

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_FAST_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 2000},
                },
            )
            response.raise_for_status()
            result = response.json()
            raw_text = result.get("response", "")

            # Try to extract JSON from the response
            json_start = raw_text.find("{")
            json_end = raw_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json.loads(raw_text[json_start:json_end])
            else:
                logger.warning("No JSON found in Ollama response for %s", file_path)
                return entities

            # Create table nodes
            tables = parsed.get("tables", [])
            for table_name in tables:
                ns_key = f"{project_name}:{rel_path}:{table_name}"
                entities["nodes"].append({
                    "label": "SQL_Table",
                    "namespace_key": ns_key,
                    "name": table_name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": "Database",
                })

            # Create procedure nodes and relationships
            procedures = parsed.get("procedures", [])
            for proc in procedures:
                proc_name = proc.get("procedure_name", "unknown")
                proc_ns_key = f"{project_name}:{rel_path}:{proc_name}"
                entities["nodes"].append({
                    "label": "SQL_Procedure",
                    "namespace_key": proc_ns_key,
                    "name": proc_name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": "Database",
                })
                for table in proc.get("tables_read", []):
                    table_ns = f"{project_name}:{rel_path}:{table}"
                    entities["relationships"].append({
                        "from": proc_ns_key,
                        "to": table_ns,
                        "type": "READS_FROM",
                    })

                for table in proc.get("tables_written", []):
                    table_ns = f"{project_name}:{rel_path}:{table}"
                    entities["relationships"].append({
                        "from": proc_ns_key,
                        "to": table_ns,
                        "type": "WRITES_TO",
                    })

                for called_proc in proc.get("calls", []):
                    called_ns = f"{project_name}:{rel_path}:{called_proc}"
                    entities["relationships"].append({
                        "from": proc_ns_key,
                        "to": called_ns,
                        "type": "CALLS",
                    })

    except httpx.ConnectError:
        logger.error("Cannot connect to Ollama at %s. Is it running?", OLLAMA_URL)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Ollama JSON response for %s: %s", file_path, e)
    except Exception as e:
        logger.error("Ollama SQL parsing error for %s: %s", file_path, e)

    return entities


# ──────────────────────────────────────────────
# Ollama Q&A (Interface Inteligente: Qwen)
# ──────────────────────────────────────────────
async def ask_ai(question: str, context: str) -> dict:
    """Send a question with graph context to Qwen for intelligent answers.
    Sets ai_busy flag to prevent Coder-Next from running simultaneously.
    If the primary model times out, retries with the fast model."""
    global ai_busy
    ai_busy = True
    
    system_prompt = """Você é o InsightGraph AI, um Arquiteto de Software Sênior e assistente prestativo.
DIRETRIZES DE RESPOSTA:
1. Se o usuário apenas cumprimentar, responda de forma amigável.
2. Se o usuário fizer uma pergunta técnica, forneça uma análise detalhada em Markdown.
3. SEMPRE que possível, identifique 'namespace_keys' relevantes no contexto.

RESPONDA SEMPRE NO FORMATO JSON:
{
  "resposta_texto": "Sua resposta aqui...",
  "nos_relevantes": ["chave1", "chave2"]
}"""

    prompt = f"""Contexto do grafo de dependências:
{context}

Pergunta do usuário:
{question}"""

    async def _call_ollama(model_name: str, timeout: float) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 400,
                        "top_k": 20,
                        "top_p": 0.9
                    },
                    "keep_alive": "5m"
                },
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("message", {}).get("content", "{}")

    try:
        try:
            # Try primary chat model first
            logger.info("Attempting AI response with primary model: %s (10s timeout)", OLLAMA_CHAT_MODEL)
            content = await _call_ollama(OLLAMA_CHAT_MODEL, 10.0)
            return {"raw_text": content, "model": OLLAMA_CHAT_MODEL}
        except (httpx.ReadTimeout, httpx.ConnectError) as e:
            logger.warning("Primary model %s failed or timed out. Retrying with %s...", OLLAMA_CHAT_MODEL, OLLAMA_FAST_MODEL)
            # Try fast model as fallback
            content = await _call_ollama(OLLAMA_FAST_MODEL, 60.0)
            return {"raw_text": content, "model": f"{OLLAMA_FAST_MODEL} (fallback)"}

    except Exception as e:
        logger.error("All AI models failed: %s", e)
        import json
        return {
            "raw_text": json.dumps({
                "resposta_texto": f"Erro ao consultar a IA: {str(e)}. Tente novamente mais tarde.", 
                "nos_relevantes": []
            }), 
            "model": "error"
        }
    finally:
        ai_busy = False


async def ask_complex_ai(prompt_text: str) -> str:
    """Send a complex request to the high-end architectural model."""
    global ai_busy
    ai_busy = True
    try:
        logger.info("Deep architectural review requested via %s", OLLAMA_COMPLEX_MODEL)
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_COMPLEX_MODEL,
                    "prompt": prompt_text,
                    "stream": False,
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 1024,
                    },
                    "keep_alive": "10m"
                },
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("response", "Erro ao gerar relatório profundo.")
    except Exception as e:
        logger.error("Complex AI failed: %s", e)
        return f"Desculpe, não conseguimos realizar a análise profunda agora: {str(e)}"
    finally:
        ai_busy = False


# ──────────────────────────────────────────────
# Project Scanner
# ──────────────────────────────────────────────
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".gradle", "build", "dist",
    ".idea", ".vscode", "target", "bin", ".next", "venv", "env",
}

SUPPORTED_EXTENSIONS = {".java", ".ts", ".tsx", ".sql"}


def _count_files(project_path: str) -> int:
    """Count all supported files in a project for progress tracking."""
    count = 0
    for root_dir, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file_name in files:
            ext = os.path.splitext(file_name)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                count += 1
    return count


async def scan_project(project_path: str) -> dict:
    """Walk a project directory and parse all supported files."""
    global scan_state
    project_path = os.path.normpath(project_path)
    all_entities = {"nodes": [], "relationships": []}

    if not os.path.isdir(project_path):
        scan_state.errors.append(f"Directory not found: {project_path}")
        return all_entities

    for root_dir, dirs, files in os.walk(project_path):
        # Skip irrelevant directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file_name in files:
            file_path = os.path.join(root_dir, file_name)
            ext = os.path.splitext(file_name)[1].lower()

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                scan_state.current_file = os.path.relpath(file_path, project_path).replace("\\", "/")

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                if not content.strip():
                    continue

                if ext == ".java":
                    result = parse_java(file_path, content, project_path)
                elif ext in (".ts", ".tsx"):
                    result = parse_typescript(file_path, content, project_path)
                elif ext == ".sql":
                    result = await parse_sql_with_ollama(file_path, content, project_path)
                else:
                    continue

                all_entities["nodes"].extend(result.get("nodes", []))
                all_entities["relationships"].extend(result.get("relationships", []))
                scan_state.scanned_files += 1

                # Update progress
                if scan_state.total_files > 0:
                    scan_state.progress_percent = round(
                        (scan_state.scanned_files / scan_state.total_files) * 100, 1
                    )

            except Exception as e:
                error_msg = f"Error parsing {file_path}: {e}"
                logger.error(error_msg)
                scan_state.errors.append(error_msg)

    return all_entities


async def ingest_to_neo4j(entities: dict) -> None:
    """Persist parsed entities into Neo4j (if connected) and always into memory."""
    global scan_state, memory_nodes, memory_edges

    for node in entities["nodes"]:
        label = node.pop("label")
        ns_key = node["namespace_key"]

        # Always store in memory
        memory_nodes.append({**node, "labels": [label, "Entity"]})

        # Try Neo4j if connected
        if neo4j_service.is_connected:
            try:
                neo4j_service.merge_node(label, ns_key, node)
            except Exception as e:
                logger.error("Failed to merge node %s: %s", ns_key, e)
        scan_state.total_nodes += 1

    for rel in entities["relationships"]:
        if "to_import" in rel:
            continue

        # Always store in memory
        memory_edges.append({"source": rel["from"], "target": rel["to"], "type": rel["type"]})

        # Try Neo4j if connected
        if neo4j_service.is_connected:
            try:
                neo4j_service.merge_relationship(rel["from"], rel["to"], rel["type"])
            except Exception as e:
                logger.error("Failed to merge relationship: %s", e)
        scan_state.total_relationships += 1


async def run_scan(paths: list[str]):
    """Background task to scan all projects."""
    global scan_state, memory_nodes, memory_edges
    scan_state = ScanStatus(status="scanning")
    memory_nodes = []
    memory_edges = []

    try:
        # Count total files first for progress tracking
        total = 0
        for project_path in paths:
            total += _count_files(project_path)
        scan_state.total_files = total

        for project_path in paths:
            logger.info("Scanning project: %s", project_path)
            entities = await scan_project(project_path)
            await ingest_to_neo4j(entities)

        scan_state.status = "completed"
        scan_state.progress_percent = 100.0
        scan_state.current_file = ""
        logger.info(
            "Scan complete: %d files, %d nodes, %d relationships",
            scan_state.scanned_files,
            scan_state.total_nodes,
            scan_state.total_relationships,
        )

        try:
            anti = await get_antipatterns()
            snapshot = {
                "timestamp": datetime.datetime.now().isoformat(),
                "total_nodes": scan_state.total_nodes,
                "total_edges": scan_state.total_relationships,
                "god_classes": len(anti.get("god_classes", [])),
                "circular_deps": len(anti.get("circular_dependencies", [])),
                "dead_code": len(anti.get("dead_code", []))
            }
            history_file = Path("history.json")
            history = []
            if history_file.exists():
                with open(history_file, "r") as f:
                    history = json.load(f)
            history.append(snapshot)
            with open(history_file, "w") as f:
                json.dump(history, f, indent=2)
            logger.info("Saved architecture snapshot to history.json")
        except Exception as he:
            logger.warning("Failed to save history snapshot: %s", he)

    except Exception as e:
        scan_state.status = "error"
        scan_state.errors.append(str(e))
        logger.error("Scan failed: %s", e)


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────


@app.post("/api/scan", response_model=ScanStatus)
async def trigger_scan(request: ScanRequest, background_tasks: BackgroundTasks):
    """Start scanning the provided project paths."""
    global scan_state
    if scan_state.status == "scanning":
        raise HTTPException(status_code=409, detail="A scan is already in progress")

    background_tasks.add_task(run_scan, request.paths)
    scan_state = ScanStatus(status="scanning")
    return scan_state


@app.get("/api/scan/status", response_model=ScanStatus)
async def get_scan_status():
    """Get the current scan status with progress."""
    return scan_state


@app.get("/api/graph")
async def get_graph(project: str = None, layer: str = None):
    """Return the full graph. Uses Neo4j if connected, otherwise in-memory data."""
    global memory_nodes, memory_edges
    if neo4j_service.is_connected:
        try:
            data = neo4j_service.get_full_graph(project=project, layer=layer)
            # Sync to memory if we're getting the full graph (no filters)
            if not project and not layer:
                memory_nodes = [dict(n) for n in data["nodes"]]
                memory_edges = [dict(e) for e in data["edges"]]
            return data
        except Exception as e:
            logger.warning("Neo4j query failed, falling back to memory: %s", e)

    # Fallback: return in-memory data
    nodes = memory_nodes
    edges = memory_edges
    if project:
        nodes = [n for n in nodes if n.get("project") == project]
    if layer:
        nodes = [n for n in nodes if n.get("layer") == layer]
    node_keys = {n["namespace_key"] for n in nodes}
    filtered_edges = [e for e in edges if e["source"] in node_keys and e["target"] in node_keys]
    return {"nodes": nodes, "edges": filtered_edges}


@app.get("/api/impact/{node_key:path}")
async def get_impact(node_key: str):
    """Return upstream and downstream neighbors of a node."""
    if neo4j_service.is_connected:
        try:
            return neo4j_service.get_impact(node_key)
        except Exception as e:
            logger.warning("Neo4j impact query failed, falling back to memory: %s", e)

    # Fallback: compute from in-memory data
    upstream = []
    downstream = []
    node_map = {n["namespace_key"]: n for n in memory_nodes}
    for edge in memory_edges:
        if edge["target"] == node_key and edge["source"] in node_map:
            n = node_map[edge["source"]]
            upstream.append({"key": n["namespace_key"], "name": n["name"], "labels": n.get("labels", []), "rel_type": edge["type"]})
        if edge["source"] == node_key and edge["target"] in node_map:
            n = node_map[edge["target"]]
            downstream.append({"key": n["namespace_key"], "name": n["name"], "labels": n.get("labels", []), "rel_type": edge["type"]})
    return {"upstream": upstream[:100], "downstream": downstream[:100]}


@app.get("/api/projects")
async def get_projects():
    """List all scanned projects."""
    if neo4j_service.is_connected:
        try:
            return {"projects": neo4j_service.get_projects()}
        except Exception:
            pass
    # Fallback
    projects = list({n.get("project") for n in memory_nodes if n.get("project")})
    return {"projects": projects}


@app.get("/api/impact/blast-radius/{node_key:path}")
async def get_blast_radius(node_key: str):
    """Calculate blast radius (multihop impact) and risk score for a node."""
    if neo4j_service.is_connected:
        try:
            # Multi-hop impact (things that depend on this node recursively up to 3 levels)
            query = """
            MATCH p=(upstream:Entity)-[*1..3]->(target:Entity {namespace_key: $key})
            UNWIND nodes(p) AS n
            UNWIND relationships(p) AS r
            RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT r) AS rels
            """
            result = neo4j_service.graph.run(query, key=node_key).data()
            if not result or not result[0]["nodes"]:
                return {"nodes": [], "edges": [], "risk_score": 0}
            
            nodes = []
            for n in result[0]["nodes"]:
                node_data = dict(n)
                node_data["labels"] = list(n.labels)
                nodes.append(node_data)
                
            edges = []
            for r in result[0]["rels"]:
                edges.append({
                    "source": r.nodes[0]["namespace_key"],
                    "target": r.nodes[1]["namespace_key"],
                    "type": type(r).__name__
                })
                
            # Heuristic Risk Score out of 100
            risk_score = min(100, len(nodes) * 4 + len(edges) * 2) 
            return {"nodes": nodes, "edges": edges, "risk_score": risk_score}
        except Exception as e:
            logger.warning("Neo4j blast radius query failed: %s", e)
    return {"nodes": [], "edges": [], "risk_score": 0}


@app.get("/api/antipatterns")
async def get_antipatterns():
    """Detect architectural antipatterns like circular dependencies and god classes."""
    antipatterns = {"circular_dependencies": [], "god_classes": [], "dead_code": []}
    if not neo4j_service.is_connected:
        return antipatterns
        
    try:
        # 1. Circular Dependencies (A -> B -> A)
        circ_query = """
        MATCH p=(n:Entity)-[*2..4]->(n)
        WHERE length(p) > 1
        RETURN [x IN nodes(p) | x.name] AS path, length(p) AS len
        LIMIT 50
        """
        circ_res = neo4j_service.graph.run(circ_query).data()
        seen_paths = set()
        for r in circ_res:
            path_tuple = tuple(sorted(r["path"]))
            if path_tuple not in seen_paths:
                seen_paths.add(path_tuple)
                antipatterns["circular_dependencies"].append({
                    "path": r["path"], "length": r["len"]
                })

        # 2. God Classes (High coupling or complexity)
        god_query = """
        MATCH (n:Entity)
        OPTIONAL MATCH (n)-[r_out]->()
        OPTIONAL MATCH ()-[r_in]->(n)
        WITH n, count(DISTINCT r_out) AS out_degree, count(DISTINCT r_in) AS in_degree
        WHERE (out_degree + in_degree) > 15 OR coalesce(n.complexity, 0) > 20
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, 
               out_degree, in_degree, coalesce(n.complexity, 0) AS complexity
        ORDER BY (out_degree + in_degree + coalesce(n.complexity, 0)) DESC
        LIMIT 50
        """
        god_res = neo4j_service.graph.run(god_query).data()
        antipatterns["god_classes"] = god_res

        # 3. Dead Code (No incoming relationships, not an API/Controller, not Frontend entry)
        dead_query = """
        MATCH (n:Entity)
        WHERE NOT ()-->(n) 
          AND NOT n.layer IN ['API', 'Frontend']
          AND coalesce(n.name, '') <> 'main' 
          AND coalesce(n.name, '') <> 'App'
          AND coalesce(n.name, '') <> 'index'
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 100
        """
        dead_res = neo4j_service.graph.run(dead_query).data()
        antipatterns["dead_code"] = dead_res

    except Exception as e:
        logger.error("Antipatterns query failed: %s", e)
        
    return antipatterns


@app.get("/api/graph/stats", response_model=GraphStats)
async def get_graph_stats():
    """Return comprehensive graph statistics."""
    if neo4j_service.is_connected:
        try:
            return neo4j_service.get_stats()
        except Exception:
            pass
    # Fallback: compute from memory
    from collections import Counter
    nodes_by_type = Counter()
    layers = Counter()
    edges_by_type = Counter()
    projects_set = set()
    for n in memory_nodes:
        labels = [l for l in n.get("labels", []) if l != "Entity"]
        if labels:
            nodes_by_type[labels[0]] += 1
        if n.get("layer"):
            layers[n["layer"]] += 1
        if n.get("project"):
            projects_set.add(n["project"])
    for e in memory_edges:
        edges_by_type[e["type"]] += 1
    return GraphStats(
        total_nodes=len(memory_nodes),
        total_edges=len(memory_edges),
        nodes_by_type=dict(nodes_by_type),
        edges_by_type=dict(edges_by_type),
        layers=dict(layers),
        projects=list(projects_set),
    )


@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """Ask an AI-powered question about the architecture.
    Blocked during scanning to prevent both models from loading simultaneously."""
    if scan_state.status == "scanning":
        raise HTTPException(
            status_code=409,
            detail="Um scan está em andamento. Aguarde o scan terminar antes de fazer perguntas à IA. "
                   "Isso evita que dois modelos de IA rodem ao mesmo tempo e sobrecarreguem o PC."
        )
    # Detect simple greetings to bypass heavy context fetching and AI generation
    input_clean = request.question.lower().strip()
    greetings = {
        "oi": "Olá! Sou o InsightGraph AI. Como posso ajudar você a analisar a arquitetura do seu projeto hoje?",
        "ola": "Olá! Estou pronto para ajudar com seus diagramas e análise de impacto. O que deseja saber?",
        "olá": "Olá! Estou pronto para ajudar com seus diagramas e análise de impacto. O que deseja saber?",
        "bom dia": "Bom dia! Como posso ajudar na sua análise técnica hoje?",
        "boa tarde": "Boa tarde! Alguma dúvida específica sobre os componentes do sistema?",
        "boa noite": "Boa noite! Em que posso ajudar na exploração do código agora?",
        "hey": "Olá! Como vai o desenvolvimento? Precisa de uma análise de impacto ou entender algum fluxo?",
        "hello": "Hello! I am InsightGraph AI. How can I help you explore your project architecture?"
    }
    
    if input_clean in greetings:
        logger.info("Fast-path greeting triggered.")
        return AskResponse(
            answer=greetings[input_clean],
            relevant_nodes=[],
            model="fast-path",
            context_used=0,
        )

    try:
        logger.info("Fetching graph context for question...")
        if neo4j_service.is_connected:
            context = neo4j_service.get_graph_context(
                node_key=request.context_node,
                limit=15, 
            )
        else:
            logger.info("Neo4j offline, using in-memory context fallback.")
            context = get_memory_graph_context(
                node_key=request.context_node,
                limit=15,
            )
        context_lines = len(context.split("\n"))
            
        ai_res = await ask_ai(request.question, context)
        answer_raw = ai_res["raw_text"]
        actual_model = ai_res["model"]
        
        logger.info("Raw AI response from %s: %s", actual_model, answer_raw[:200] + "...")
        
        # Try to extract JSON from the response
        json_start = answer_raw.find("{")
        json_end = answer_raw.rfind("}") + 1
        
        answer_text = ""
        relevant_nodes = []
        
        if json_start >= 0 and json_end > json_start:
            try:
                content = answer_raw[json_start:json_end]
                parsed_ans = json.loads(content)
                answer_text = parsed_ans.get("resposta_texto", "")
                relevant_nodes = parsed_ans.get("nos_relevantes", [])
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from AI response")
                
        # If extraction failed or yielded empty result, use raw text but clean it
        if not answer_text.strip():
            # Remove any JSON-like artifacts if we are using it as raw text
            answer_text = answer_raw.replace("{", "").replace("}", "").replace("\"resposta_texto\":", "").strip()
            if not answer_text:
                answer_text = "A IA não retornou nenhuma resposta. Tente fazer a pergunta de outra forma ou verifique se o modelo está carregado."

        return AskResponse(
            answer=answer_text,
            relevant_nodes=relevant_nodes,
            model=actual_model,
            context_used=context_lines,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate")
async def simulate_changes(req: SimulateRequest):
    """
    Perform a 'What-If' simulation using the in-memory graph.
    Returns the new graph topology and a risk score.
    """
    global memory_nodes, memory_edges
    
    logger.info("Starting simulation. Current memory nodes count: %d", len(memory_nodes))
    
    # Lazy load from Neo4j if memory is empty
    if not memory_nodes and neo4j_service.is_connected:
        try:
            logger.info("Simulation memory empty, lazily loading from Neo4j...")
            data = neo4j_service.get_full_graph()
            memory_nodes = data["nodes"]
            memory_edges = data["edges"]
            logger.info("Lazy load complete. Fetched %d nodes, %d edges", len(memory_nodes), len(memory_edges))
        except Exception as e:
            logger.error("Failed to lazily load graph for simulation: %s", e)

    nodes = {n["namespace_key"]: dict(n) for n in memory_nodes}
    edges = [dict(e) for e in memory_edges]
    logger.info("Nodes dictionary size: %d", len(nodes))

    deleted_set = set(req.deleted_nodes)
    
    # Tag deleted nodes
    for dk in deleted_set:
        if dk in nodes:
            nodes[dk]["status"] = "deleted"
            
    # Find impacted nodes recursively (Bi-directional BFS)
    # The user wants "everything" impacted if a root node is deleted.
    # We follow all edges in both directions to show system-wide reachability impact.
    impacted_set = set()
    queue = list(deleted_set)
    visited = set(deleted_set)
    
    while queue:
        current_id = queue.pop(0)
        
        for edge in edges:
            src = edge["source"]
            tgt = edge["target"]

            # Bi-directional propagation
            neighbor = None
            if src == current_id:
                neighbor = tgt
            elif tgt == current_id:
                neighbor = src
            
            if neighbor and neighbor not in visited:
                if neighbor in nodes:
                    impacted_set.add(neighbor)
                    visited.add(neighbor)
                    queue.append(neighbor)
            
    for ik in impacted_set:
        if ik in nodes:
            nodes[ik]["status"] = "impacted"

    # Tag edges
    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        if src in deleted_set or tgt in deleted_set:
            edge["status"] = "deleted"
        elif src in impacted_set or tgt in impacted_set:
            edge["status"] = "impacted"

    for edge in req.added_edges:
        if edge["source"] in nodes and edge["target"] in nodes:
            edges.append({
                "source": edge["source"],
                "target": edge["target"],
                "type": edge.get("type", "DEPENDS_ON"),
                "status": "added"
            })

    # Determine structural impact
    impact_insights = []
    
    # 1. Critical Failure Detection
    critical_keywords = ["main", "app", "application", "index", "server", "start"]
    found_critical = []
    for dk in deleted_set:
        node_name = nodes[dk].get("name", "").lower()
        if any(kw in node_name for kw in critical_keywords):
            found_critical.append(nodes[dk].get("name"))
    
    if found_critical:
        impact_insights.append(f"🔴 FALHA CRÍTICA: O ponto de entrada do sistema ({', '.join(found_critical)}) foi removido. O ambiente deixará de funcionar.")

    # 2. Layer-wise Impact Analysis
    layer_impacts = {}
    for ik in impacted_set:
        l = nodes[ik].get("layer", "Unknown")
        layer_impacts[l] = layer_impacts.get(l, 0) + 1
    
    # Sort layers for consistent reporting
    for layer, count in sorted(layer_impacts.items()):
        impact_insights.append(f"⚠️ Camada '{layer}': {count} componentes impactados.")

    # 3. Connection Loss
    deleted_edges_count = sum(1 for e in edges if e.get("status") == "deleted")
    if deleted_edges_count > 0:
        impact_insights.append(f"🔗 Quebra de Fluxo: {deleted_edges_count} conexões foram rompidas.")

    # 4. Resilience Note
    if not found_critical and len(impacted_set) < 5:
        impact_insights.append("✅ Baixo Impacto: A alteração parece ser isolada e não compromete o núcleo do sistema.")
    elif len(impacted_set) > 20:
        impact_insights.append(f"💣 Alto Risco: Esta mudança afeta um grande volume de dependências ({len(impacted_set)} nós).")

    affected_nodes_cnt = len(deleted_set) + len(impacted_set)
    affected_edges_cnt = deleted_edges_count + len(req.added_edges)
    risk_score = min(100, len(deleted_set) * 15 + len(impacted_set) * 5 + affected_edges_cnt * 2)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "risk_score": risk_score,
        "affected_count": affected_nodes_cnt + affected_edges_cnt,
        "impact_insights": impact_insights
    }


@app.post("/api/simulate/review")
async def review_simulation(sim_report: dict):
    """Generate a deep architectural review of a simulation scenario."""
    if scan_state.status == "scanning" or ai_busy:
         raise HTTPException(
            status_code=409,
            detail="A IA está ocupada ou o sistema está escaneando. Tente novamente em instantes."
        )

    risk = sim_report.get("risk_score", 0)
    insights = "\n".join([f"- {i}" for i in sim_report.get("impact_insights", [])])
    
    prompt = f"""Você é um Arquiteto de Software Sênior (Principal Architect).
Analise o seguinte cenário de simulação de mudanças no sistema:

SCORE DE RISCO CALCULADO: {risk}/100
INSIGHTS AUTOMÁTICOS:
{insights}

TAREFA:
Forneça uma consultoria arquitetural profunda sobre esta mudança. 
Seu relatório deve estar em Markdown e conter:
1. ANÁLISE DE IMPACTO ESTRUTURAL: Explique as consequências técnicas.
2. DÉBITO TÉCNICO E MANUTENIBILIDADE: Como isso afeta o futuro do código.
3. RECOMENDAÇÃO: Se a mudança é segura, perigosa ou se existe uma abordagem melhor.

SEJA PROFISSIONAL, OBJETIVO E TÉCNICO. RESPONDA EM PORTUGUÊS.
"""
    report = await ask_complex_ai(prompt)
    return {"report": report}


@app.get("/api/history")
async def get_history():
    """Returns the historical architectural snapshots."""
    history_file = Path("history.json")
    if history_file.exists():
        with open(history_file, "r") as f:
            return json.load(f)
    return []


@app.get("/api/health", response_model=HealthStatus)
async def get_health():
    """Check the health of all connected services."""
    status = HealthStatus()

    # Check Neo4j
    if neo4j_service.is_connected:
        try:
            neo4j_service.graph.run("RETURN 1")
            status.neo4j = "connected"
        except Exception:
            status.neo4j = "error"
    else:
        status.neo4j = "disconnected"

    # Check Ollama scanner model
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                status.ollama_scanner = "available" if OLLAMA_FAST_MODEL in models else "model_not_found"
                status.ollama_chat = "available" if OLLAMA_CHAT_MODEL in models else "model_not_found"
                # Check complex model if explicitly listed in tags
                if OLLAMA_COMPLEX_MODEL in models:
                    status.complex_model = "available"
                else:
                    # Don't fail health if complex model is missing, just report
                    status.complex_model = "not_found"
            else:
                status.ollama_scanner = "error"
                status.ollama_chat = "error"
    except httpx.ConnectError:
        status.ollama_scanner = "offline"
        status.ollama_chat = "offline"
    except Exception:
        status.ollama_scanner = "error"
        status.ollama_chat = "error"

    return status


# ──────────────────────────────────────────────
# Entry point & CI/CD CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightGraph Backend & CI/CD CLI")
    parser.add_argument("mode", nargs="?", default="serve", choices=["serve", "scan"], help="Mode to run: serve (API) or scan (CLI CI/CD)")
    parser.add_argument("--path", type=str, help="Path to project to scan (required for scan mode)")
    parser.add_argument("--fail-on-risk", type=int, default=0, help="Risk threshold (1-100) to fail the CI/CD pipeline")
    args = parser.parse_args()

    if args.mode == "scan":
        if not args.path:
            print("[InsightGraph] ERROR: --path is required for scan mode.")
            sys.exit(1)
            
        async def run_cli():
            print(f"[InsightGraph] Starting CI/CD scan for path: {args.path}")
            entities = await scan_project(args.path)
            await ingest_to_neo4j(entities)
            anti = await get_antipatterns()
            
            god_classes = len(anti.get("god_classes", []))
            circular_deps = len(anti.get("circular_dependencies", []))
            dead_code = len(anti.get("dead_code", []))
            
            # Simple heuristic matching the Simulation Risk Score
            risk_score = min(100, god_classes * 5 + circular_deps * 10 + min(dead_code, 20))
            
            print(f"[InsightGraph] Scan completed.")
            print(f" - God Classes: {god_classes}")
            print(f" - Circular Dependencies: {circular_deps}")
            print(f" - Dead Code: {dead_code}")
            print(f" - Total Calculated Risk Score: {risk_score}/100")
            
            if args.fail_on_risk > 0 and risk_score >= args.fail_on_risk:
                print(f"[InsightGraph] ❌ FAILED: Risk score {risk_score} is >= threshold {args.fail_on_risk}.")
                sys.exit(1)
            else:
                print("[InsightGraph] ✅ PASSED: Architecture adheres to risk limits.")
                sys.exit(0)
                
        asyncio.run(run_cli())
    else:
        import uvicorn
        # Fallback for standard hot-reloading
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
