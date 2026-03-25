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
import re
import asyncio
import logging
import datetime
import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from collections import defaultdict

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
# tkinter imports for folder picker
# ──────────────────────────────────────────────
import tkinter as tk
from tkinter import filedialog

# ──────────────────────────────────────────────
# CodeQL imports
# ──────────────────────────────────────────────
from codeql_orchestrator import CodeQLOrchestrator
from bidirectional_analyzer import BidirectionalAnalyzer
from contract_break_detector import ContractBreakDetector
from data_flow_tracker import DataFlowTracker
from deep_parser import DeepParser
from fragility_calculator import FragilityCalculator
from impact_engine import ChangeDescriptor, ImpactEngine
from semantic_analyzer import SemanticAnalyzer
from side_effect_detector import SideEffectDetector
from symbol_resolver import SymbolResolver
from taint_propagator import TaintPropagator

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
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
RAG_INDEX_FILE = Path(os.getenv("RAG_INDEX_FILE", "rag_index.json"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insightgraph")

# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(application):
    """Connect to Neo4j on startup (non-fatal if unavailable)."""
    try:
        if neo4j_service.connect():
            neo4j_service.ensure_indexes()
            logger.info("Neo4j connection established successfully")
        else:
            logger.warning("Neo4j not available at startup. Continuing with memory fallback.")
    except Exception as e:
        logger.warning("Neo4j error at startup: %s. Continuing with memory fallback.", e)

    try:
        _ensure_memory_graph_loaded()
        loaded = _load_rag_index()
        logger.info("RAG index startup load: %d entries from %s", loaded, RAG_INDEX_FILE)
    except Exception as e:
        logger.warning("RAG startup load failed: %s", e)
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
    ollama_embed: str = "unknown"
    scanner_model: str = OLLAMA_FAST_MODEL
    chat_model: str = OLLAMA_CHAT_MODEL
    complex_model: str = OLLAMA_COMPLEX_MODEL
    embed_model: str = OLLAMA_EMBED_MODEL
    rag_index_nodes: int = 0

class SimulationReviewRequest(BaseModel):
    risk_score: int = 0
    impact_insights: list[str] = []

class FileContentResponse(BaseModel):
    content: str
    file_path: str

# Global state
scan_state = ScanStatus(status="idle")
ai_busy = False  # True while Qwen Q&A is processing
scanned_projects: dict[str, str] = {}  # Maps project_name -> absolute_project_path

# In-memory graph storage (works even without Neo4j)
memory_nodes: list[dict] = []
memory_edges: list[dict] = []
rag_index: list[dict] = []
rag_index_metadata: dict = {}

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
        if not self.is_connected:
            return
        
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

# Initialize CodeQL components
def _discover_codeql_path() -> str:
    """Auto-discover CodeQL CLI executable.
    
    Priority:
    1. CODEQL_PATH environment variable
    2. 'codeql' in system PATH
    3. Common installation directories on Windows
    """
    import shutil
    
    # 1. Explicit env var
    env_path = os.getenv("CODEQL_PATH")
    if env_path:
        if os.path.isfile(env_path):
            logger.info("CodeQL CLI found via CODEQL_PATH: %s", env_path)
            return env_path
        logger.warning("CODEQL_PATH set to '%s' but file not found, continuing search...", env_path)
    
    # 2. Already in PATH
    found = shutil.which("codeql")
    if found:
        logger.info("CodeQL CLI found in PATH: %s", found)
        return found
    
    # 3. Probe common Windows locations
    common_locations = [
        r"C:\codeql\codeql\codeql.exe",
        r"C:\codeql\codeql.exe",
        os.path.expanduser(r"~\codeql\codeql.exe"),
        os.path.expanduser(r"~\codeql\codeql\codeql.exe"),
        r"C:\Program Files\codeql\codeql.exe",
        r"C:\Program Files (x86)\codeql\codeql.exe",
    ]
    for loc in common_locations:
        if os.path.isfile(loc):
            logger.info("CodeQL CLI discovered at: %s", loc)
            return loc
    
    # Fallback — return bare name and let subprocess raise a clear error later
    logger.warning("CodeQL CLI not found in PATH or common locations. "
                   "Set CODEQL_PATH env var or install from "
                   "https://github.com/github/codeql-cli-binaries")
    return "codeql"


def initialize_codeql():
    """Initialize CodeQL orchestrator and all its dependencies."""
    from codeql_database_manager import DatabaseManager
    from codeql_analysis_engine import AnalysisEngine
    from codeql_bridge import CodeQLBridge
    from codeql_models import ProjectRegistry, AnalysisHistory
    from sarif_manager import SARIFManager
    import os

    # Aggressive defaults for maximum throughput on a single analysis job.
    # Keep env override support for fine tuning in production.
    os.environ.setdefault("CODEQL_DB_THREADS", "0")
    os.environ.setdefault("CODEQL_DB_RAM", "0")
    os.environ.setdefault("CODEQL_ANALYZE_THREADS", "0")
    os.environ.setdefault("CODEQL_ANALYZE_RAM", "0")
    
    # Auto-discover CodeQL CLI
    codeql_path = _discover_codeql_path()
    codeql_db_dir = os.getenv("CODEQL_DB_DIR", "./codeql_databases")
    codeql_results_dir = os.getenv("CODEQL_RESULTS_DIR", "./codeql-results")
    codeql_timeout = int(os.getenv("CODEQL_TIMEOUT", "600"))
    codeql_db_timeout = int(os.getenv("CODEQL_DB_TIMEOUT", str(codeql_timeout)))
    codeql_analyze_timeout = int(os.getenv("CODEQL_ANALYZE_TIMEOUT", "5400"))
    codeql_max_concurrent = int(os.getenv("CODEQL_MAX_CONCURRENT", "1"))
    
    # Initialize components
    database_manager = DatabaseManager(codeql_path=codeql_path, timeout=codeql_db_timeout)
    analysis_engine = AnalysisEngine(codeql_path=codeql_path, timeout=codeql_analyze_timeout)
    sarif_manager = SARIFManager(output_dir=codeql_results_dir)
    sarif_ingestor = CodeQLBridge(neo4j_service=neo4j_service)
    project_registry = ProjectRegistry()
    analysis_history = AnalysisHistory()
    
    # Initialize orchestrator
    orchestrator = CodeQLOrchestrator(
        database_manager=database_manager,
        analysis_engine=analysis_engine,
        sarif_ingestor=sarif_ingestor,
        project_registry=project_registry,
        analysis_history=analysis_history,
        max_concurrent=codeql_max_concurrent,
        sarif_manager=sarif_manager,
    )
    
    logger.info(
        "CodeQL orchestrator initialized successfully (db_timeout=%ss, analyze_timeout=%ss, db_threads=%s, db_ram=%s, analyze_threads=%s, analyze_ram=%s, max_concurrent=%d)",
        codeql_db_timeout,
        codeql_analyze_timeout,
        os.getenv("CODEQL_DB_THREADS"),
        os.getenv("CODEQL_DB_RAM"),
        os.getenv("CODEQL_ANALYZE_THREADS"),
        os.getenv("CODEQL_ANALYZE_RAM"),
        codeql_max_concurrent,
    )
    return orchestrator

codeql_orchestrator = initialize_codeql()

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


def _get_git_owner(file_path: str) -> str:
    """Get the last commit author for a file using git log. Returns 'Desconhecido' if not in git or error."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%an", "--", file_path],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(file_path) or "."
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "Desconhecido"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        return "Desconhecido"


# Compliance helpers
SENSITIVE_TERMS = {"cpf", "cnpj", "senha", "password", "biometria", "token", "nsr", "pis", "rg", "email", "telefone", "phone"}
LOGGING_METHODS = {"console.log", "console.error", "console.warn", "logger.info", "logger.debug", "logger.warn", "logger.error", "log.info", "log.debug", "log.warn", "log.error", "print"}


def _is_sensitive_term(term: str) -> bool:
    """Check if a term contains sensitive data keywords."""
    term_lower = term.lower()
    return any(sensitive in term_lower for sensitive in SENSITIVE_TERMS)


def _check_compliance_violation(node, content: str) -> tuple[bool, list[str]]:
    """Check if a node contains compliance violations (logging sensitive data)."""
    violations = []
    # Simple heuristic: look for logging calls with sensitive terms in arguments
    content_lower = content.lower()
    for method in LOGGING_METHODS:
        if method in content_lower:
            # Check if sensitive terms appear near logging calls
            for term in SENSITIVE_TERMS:
                if term in content_lower:
                    # More precise check: look for term in the node's content
                    node_text = node.text.decode("utf-8").lower()
                    if term in node_text and method in node_text:
                        violations.append(term)
    return len(violations) > 0, violations


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


# ──────────────────────────────────────────────
# Software Intelligence Detection Functions
# ──────────────────────────────────────────────

def _detect_cloud_blocker(content: str, imports: list[str]) -> bool:
    """Detect cloud blockers (local disk I/O operations)."""
    # Java disk I/O
    java_blockers = ["java.io.File", "java.io.FileInputStream", "java.io.FileOutputStream", 
                     "java.nio.file.Files", "new File(", "FileReader", "FileWriter"]
    # TypeScript/Node disk I/O
    ts_blockers = ["fs.readFile", "fs.writeFile", "fs.readFileSync", "fs.writeFileSync",
                   "require('fs')", 'require("fs")', "from 'fs'", 'from "fs"']
    
    content_lower = content.lower()
    for blocker in java_blockers + ts_blockers:
        if blocker.lower() in content_lower:
            return True
    
    # Check imports explicitly
    for imp in imports:
        if "java.io" in imp or "java.nio.file" in imp or imp.strip() == "fs":
            return True
    
    return False


def _is_sensitive_data_name(name: str) -> bool:
    """Check if a variable/column name indicates sensitive data (GDPR/LGPD)."""
    sensitive_keywords = ["cpf", "password", "senha", "email", "credit_card", 
                         "ssn", "token", "apikey", "api_key", "secret", 
                         "private_key", "card_number", "cvv", "birthdate", "date_of_birth"]
    name_lower = name.lower()
    for keyword in sensitive_keywords:
        if keyword in name_lower:
            return True
    return False


def _detect_hardcoded_secret(node_name: str, content: str) -> bool:
    """
    Detect if a variable with a secret-like name is assigned a hardcoded string literal.
    E.g., const PASSWORD = "myPassword123"
    """
    if not _is_sensitive_data_name(node_name):
        return False
    
    # Look for patterns like: name = "..." or name = '...'
    import re
    patterns = [
        rf'{node_name}\s*=\s*["\']',  # const NAME = "..."
        rf'{node_name}\s*:\s*String\s*=\s*["\']',  # NAME: String = "..."
    ]
    
    for pattern in patterns:
        if re.search(pattern, content):
            return True
    
    return False


def _detect_empty_catch(node, content: str) -> bool:
    """Detect empty or comment-only catch blocks within a node."""
    def _is_empty_block(block_node):
        # Ignore braces and whitespace; consider only named children (statements) and exclude comments.
        for child in block_node.named_children:
            if child.type in ("line_comment", "block_comment", "comment"):
                continue
            # Found a real statement inside catch
            return False
        return True

    def _find_catch_clauses(n):
        if n.type == "catch_clause":
            yield n
        for c in n.children:
            yield from _find_catch_clauses(c)

    for catch in _find_catch_clauses(node):
        # In Java and TS, catch_clause usually has a block child
        block = next((c for c in catch.children if c.type == "block"), None)
        if block and _is_empty_block(block):
            return True
    return False


def _extract_spring_route(decorators: list[str]) -> str | None:
    """Try to extract a route path from a Spring mapping decorator."""
    import re
    pattern_simple = re.compile(r"@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*['\"]([^'\"]+)['\"]")
    pattern_named = re.compile(r"@(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping).*?(?:path|value)\s*=\s*['\"]([^'\"]+)['\"]")

    for deco in decorators:
        m = pattern_simple.search(deco)
        if m:
            return m.group(2).strip()
        m = pattern_named.search(deco)
        if m:
            return m.group(2).strip()
    return None


def parse_java(file_path: str, content: str, project_path: str) -> dict:
    """Parse Java file using tree-sitter and extract classes, methods, decorators."""
    tree = java_parser.parse(content.encode("utf-8"))
    root = tree.root_node
    project_name = _get_project_name(file_path, project_path)
    rel_path = os.path.relpath(file_path, project_path).replace("\\", "/")
    layer = _determine_java_layer(file_path, content)

    entities = {"nodes": [], "relationships": []}

    # Collect imports for cloud blocker detection + owner/type hints
    imports = []
    imported_simple_names: dict[str, str] = {}
    for child in root.children:
        if child.type == "import_declaration":
            import_text = child.text.decode("utf-8").replace("import ", "").replace(";", "").strip()
            imports.append(import_text)
            simple = import_text.split(".")[-1].strip()
            if simple and simple != "*":
                imported_simple_names[simple] = simple

    # Detect cloud blockers and hardcoded secrets at file level
    cloud_blocker = _detect_cloud_blocker(content, imports)

    def _simple_java_type(t: str | None) -> str | None:
        if not t:
            return None
        cleaned = t.strip()
        if not cleaned:
            return None
        cleaned = re.sub(r"<[^>]*>", "", cleaned)  # generics
        cleaned = cleaned.replace("[]", "").strip()
        cleaned = cleaned.split("|", 1)[0].strip()
        cleaned = cleaned.split(".", 1)[-1].strip() if "." in cleaned else cleaned
        if not cleaned:
            return None
        return imported_simple_names.get(cleaned, cleaned)

    def _infer_java_field_hints(class_body_node) -> dict[str, str]:
        txt = class_body_node.text.decode("utf-8")
        hints: dict[str, str] = {}
        # Examples:
        # private UserService userService;
        # @Autowired private UserService userService;
        # private final com.foo.UserService userService;
        for m in re.finditer(
            r"(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?([A-Za-z_][\w\.$<>\[\]]*)\s+([A-Za-z_][\w]*)\s*(?:=|;)",
            txt,
        ):
            typ = _simple_java_type(m.group(1))
            var_name = m.group(2)
            if typ and var_name:
                hints[var_name] = typ
        return hints

    def _extract_java_field_names(class_body_node) -> set[str]:
        txt = class_body_node.text.decode("utf-8")
        names: set[str] = set()
        for m in re.finditer(
            r"(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?[A-Za-z_][\w\.$<>\[\]]*\s+([A-Za-z_][\w]*)\s*(?:=|;)",
            txt,
        ):
            names.add(m.group(1))
        return names

    def _extract_method_field_refs(method_node, class_fields: set[str]) -> list[str]:
        if not class_fields:
            return []
        txt = method_node.text.decode("utf-8")
        refs: set[str] = set()
        for field_name in class_fields:
            if re.search(rf"\bthis\.{re.escape(field_name)}\b", txt):
                refs.add(field_name)
                continue
            if re.search(rf"\b{re.escape(field_name)}\b", txt):
                refs.add(field_name)
        return sorted(list(refs))

    def _infer_java_local_hints(method_node, base_hints: dict[str, str]) -> dict[str, str]:
        txt = method_node.text.decode("utf-8")
        hints = dict(base_hints)

        # Parameters in method signature: save(UserRequest request, String tenantId)
        signature = txt.split("{", 1)[0]
        for m in re.finditer(r"([A-Za-z_][\w\.$<>\[\]]*)\s+([A-Za-z_][\w]*)", signature):
            typ = _simple_java_type(m.group(1))
            var_name = m.group(2)
            if typ and var_name and var_name not in hints:
                hints[var_name] = typ

        # Local variables:
        # UserService svc = ...
        # var svc = new UserService(...)
        for m in re.finditer(
            r"([A-Za-z_][\w\.$<>\[\]]*)\s+([A-Za-z_][\w]*)\s*=\s*new\s+([A-Za-z_][\w\.$]*)",
            txt,
        ):
            declared = _simple_java_type(m.group(1))
            var_name = m.group(2)
            ctor = _simple_java_type(m.group(3))
            hints[var_name] = ctor or declared or m.group(3)

        for m in re.finditer(
            r"([A-Za-z_][\w\.$<>\[\]]*)\s+([A-Za-z_][\w]*)\s*=",
            txt,
        ):
            typ = _simple_java_type(m.group(1))
            var_name = m.group(2)
            if typ and var_name and var_name not in hints:
                hints[var_name] = typ

        return hints

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
                class_text = node.text.decode("utf-8")
                implements_interfaces: list[str] = []
                extends_class: str | None = None
                impl_match = re.search(r"\bimplements\s+([^{]+)\{", class_text)
                if impl_match:
                    raw_impls = impl_match.group(1)
                    for part in raw_impls.split(","):
                        iface = _simple_java_type(part.strip())
                        if iface:
                            implements_interfaces.append(iface)
                ext_match = re.search(r"\bextends\s+([A-Za-z_][\w\.$<>\[\]]*)", class_text)
                if ext_match:
                    extends_class = _simple_java_type(ext_match.group(1))
                
                # Build node with intelligence properties
                node_data = {
                    "label": "Java_Class",
                    "namespace_key": ns_key,
                    "name": class_name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    "decorators": ", ".join(decorators),
                    **metrics,
                }
                if implements_interfaces:
                    node_data["implements_interfaces"] = implements_interfaces
                if extends_class:
                    node_data["extends_class"] = extends_class
                
                # Add cloud blocker flag
                if cloud_blocker:
                    node_data["cloud_blocker"] = True
                
                # Add sensitive data flag
                if _is_sensitive_data_name(class_name):
                    node_data["labels"] = ["Sensitive_Data"]
                
                entities["nodes"].append(node_data)

                # Find methods within this class
                for child in node.children:
                    if child.type == "class_body":
                        class_field_hints = _infer_java_field_hints(child)
                        class_field_names = _extract_java_field_names(child)
                        if class_field_names:
                            node_data["class_fields"] = sorted(list(class_field_names))
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

                                    method_label = "Java_Method"
                                    route_path = _extract_spring_route(m_decorators)
                                    if route_path:
                                        method_label = "API_Endpoint"

                                    method_data = {
                                        "label": method_label,
                                        "namespace_key": method_ns_key,
                                        "name": method_name,
                                        "file": rel_path,
                                        "project": project_name,
                                        "layer": layer,
                                        "decorators": ", ".join(m_decorators),
                                        "parent_class": class_name,
                                        "called_routes": [],
                                        **m_metrics,
                                    }
                                    refs = _extract_method_field_refs(body_child, class_field_names)
                                    if refs:
                                        method_data["field_refs"] = refs

                                    if route_path:
                                        method_data["route_path"] = route_path

                                    # Add cloud blocker flag
                                    if cloud_blocker:
                                        method_data["cloud_blocker"] = True

                                    # Add sensitive data flag
                                    if _is_sensitive_data_name(method_name):
                                        method_data["labels"] = ["Sensitive_Data"]

                                    # Detect hardcoded secrets
                                    if _detect_hardcoded_secret(method_name, content):
                                        method_data["hardcoded_secret"] = True

                                    # Detect swallowed exceptions
                                    if _detect_empty_catch(body_child, content):
                                        method_data["swallowed_exception"] = True

                                    # Performance / Security scans
                                    n_plus_one_risk = False
                                    sql_injection_risk = False
                                    local_type_hints = _infer_java_local_hints(body_child, class_field_hints)

                                    def _collect_method_calls(n, called_routes: list[str], in_loop=False):
                                        nonlocal n_plus_one_risk, sql_injection_risk

                                        # Mark loops (for/while/do) as potential N+1 contexts
                                        if n.type in ("for_statement", "enhanced_for_statement", "while_statement", "do_statement"):
                                            in_loop = True

                                        if n.type == "method_invocation":
                                            called = None
                                            owner_hint = None
                                            name_node = n.child_by_field_name("name") or n.child_by_field_name("identifier")
                                            if name_node:
                                                called = name_node.text.decode("utf-8")
                                            else:
                                                m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", n.text.decode("utf-8"))
                                                if m:
                                                    called = m.group(1)

                                            invoke_text = n.text.decode("utf-8")
                                            # owner.method(...)
                                            om = re.search(r"(?:(?:this|super)\.)?([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", invoke_text)
                                            if om:
                                                owner_var = om.group(1)
                                                owner_hint = _simple_java_type(local_type_hints.get(owner_var) or owner_var)
                                            else:
                                                # Static call ClassName.method(...)
                                                sm = re.search(r"\b([A-Z][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", invoke_text)
                                                if sm:
                                                    owner_hint = _simple_java_type(sm.group(1))

                                            if called:
                                                lower_called = called.lower()
                                                # N+1 query heuristic (DB-like methods inside loops)
                                                if in_loop and any(k in lower_called for k in ("find", "get", "query", "select", "save")):
                                                    n_plus_one_risk = True

                                                # SQL Injection heuristic (query execution with string concatenation)
                                                if any(k in lower_called for k in ("executequery", "query")):
                                                    args_node = n.child_by_field_name("arguments") or n.child_by_field_name("argument_list")
                                                    if args_node and "+" in args_node.text.decode("utf-8"):
                                                        sql_injection_risk = True

                                                # HTTP call route extraction (Android/Java clients)
                                                try:
                                                    m = re.search(r"['\"](/[^'\"]+)['\"]", invoke_text)
                                                    if m:
                                                        called_routes.append(m.group(1))
                                                except Exception:
                                                    pass

                                                is_probably_self_call = (
                                                    called == method_name and
                                                    (owner_hint is None or owner_hint == class_name)
                                                )
                                                if not is_probably_self_call:
                                                    called_ns = (
                                                        f"{project_name}:{rel_path}:{owner_hint}.{called}"
                                                        if owner_hint else
                                                        f"{project_name}:{rel_path}:{called}"
                                                    )
                                                    rel_data = {
                                                        "from": method_ns_key,
                                                        "to": called_ns,
                                                        "type": "CALLS",
                                                        "target_method_hint": called,
                                                    }
                                                    if owner_hint:
                                                        rel_data["target_owner_hint"] = owner_hint
                                                    entities["relationships"].append(rel_data)

                                        for c in n.children:
                                            _collect_method_calls(c, called_routes, in_loop)

                                    _collect_method_calls(body_child, method_data["called_routes"])

                                    if n_plus_one_risk:
                                        method_data["n_plus_one_risk"] = True
                                    if sql_injection_risk:
                                        method_data["sql_injection_risk"] = True

                                    # Check for compliance violations (logging sensitive data)
                                    violation, leaked = _check_compliance_violation(body_child, content)
                                    if violation:
                                        method_data["compliance_violation"] = True
                                        method_data["leaked_data"] = leaked

                                    entities["nodes"].append(method_data)
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


def _extract_nest_route(decorators: list[str]) -> str | None:
    """Extract the route path from NestJS decorators like @Get('/x') or @Post('y')."""
    import re
    pattern = re.compile(r"@(Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]+)['\"]")
    for deco in decorators:
        m = pattern.search(deco)
        if m:
            return m.group(2).strip()
    return None


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

    # Collect imports for cloud blocker detection + symbol alias resolution
    imports = []
    import_alias_map: dict[str, str] = {}
    for child in root.children:
        if child.type == "import_statement":
            stmt_text = child.text.decode("utf-8")
            source_node = child.child_by_field_name("source")
            if source_node:
                import_path = source_node.text.decode("utf-8").strip("'\"")
                imports.append(import_path)
            # Default import: import Foo from '...'
            m_default = re.search(r"import\s+([A-Za-z_$][\w$]*)\s*(?:,|\s+from)", stmt_text)
            if m_default:
                alias = m_default.group(1).strip()
                if alias:
                    import_alias_map[alias] = alias
            # Namespace import: import * as NS from '...'
            m_ns = re.search(r"import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from", stmt_text)
            if m_ns:
                alias = m_ns.group(1).strip()
                if alias:
                    import_alias_map[alias] = alias
            # Named imports: import { A, B as C } from '...'
            m_named = re.search(r"\{([^}]*)\}", stmt_text)
            if m_named:
                body = m_named.group(1)
                for raw_part in body.split(","):
                    part = raw_part.strip().replace("type ", "")
                    if not part:
                        continue
                    if " as " in part:
                        original, alias = [p.strip() for p in part.split(" as ", 1)]
                        if alias:
                            import_alias_map[alias] = original or alias
                    else:
                        import_alias_map[part] = part

    # Detect cloud blockers and hardcoded secrets at file level
    cloud_blocker = _detect_cloud_blocker(content, imports)

    def _get_decorators(n):
        return [c.text.decode("utf-8") for c in n.children if c.type == "decorator"]

    def _normalize_symbol(sym: str | None) -> str | None:
        if not sym:
            return None
        cleaned = sym.strip()
        if not cleaned:
            return None
        cleaned = cleaned.split("<", 1)[0].split("|", 1)[0].split("[", 1)[0].strip()
        if not cleaned:
            return None
        return import_alias_map.get(cleaned, cleaned)

    def _infer_local_type_hints(scope_node) -> dict[str, str]:
        txt = scope_node.text.decode("utf-8")
        hints: dict[str, str] = {}

        # const x = new Foo(...)
        for m in re.finditer(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::\s*([A-Za-z_$][\w$<>\[\]\|]*))?\s*=\s*new\s+([A-Za-z_$][\w$]*)",
            txt,
        ):
            var_name = m.group(1)
            declared_type = _normalize_symbol(m.group(2))
            ctor_type = _normalize_symbol(m.group(3))
            hints[var_name] = ctor_type or declared_type or m.group(3)

        # Typed declarations: const svc: UserService = ...
        for m in re.finditer(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$<>\[\]\|]*)",
            txt,
        ):
            var_name = m.group(1)
            typ = _normalize_symbol(m.group(2))
            if var_name and typ and var_name not in hints:
                hints[var_name] = typ

        # Parameter hints from signature only (avoid object-literal noise in body)
        signature = txt.split("{", 1)[0]
        for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*([A-Za-z_$][\w$<>\[\]\|]*)", signature):
            var_name = m.group(1)
            typ = _normalize_symbol(m.group(2))
            if var_name and typ and var_name not in hints:
                hints[var_name] = typ

        return hints

    def _extract_ts_class_field_names(class_node) -> set[str]:
        txt = class_node.text.decode("utf-8")
        names: set[str] = set()
        # Examples:
        # private userService: UserService;
        # readonly repo = new Repo();
        for m in re.finditer(
            r"(?:private|protected|public|readonly|static|\s)+\s*([A-Za-z_$][\w$]*)\s*(?::|=|;)",
            txt,
        ):
            n = m.group(1).strip()
            if n and n not in {"constructor"}:
                names.add(n)
        return names

    def _extract_ts_method_field_refs(method_node, class_fields: set[str]) -> list[str]:
        if not class_fields:
            return []
        txt = method_node.text.decode("utf-8")
        refs: set[str] = set()
        for field_name in class_fields:
            if re.search(rf"\bthis\.{re.escape(field_name)}\b", txt):
                refs.add(field_name)
                continue
            if re.search(rf"\b{re.escape(field_name)}\b", txt):
                refs.add(field_name)
        return sorted(list(refs))

    def _collect_call_relationships(
        owner_ns: str,
        n,
        called_routes: list[str],
        in_loop: bool = False,
        local_type_hints: dict[str, str] | None = None,
        current_owner: str | None = None,
    ):
        """Traverse the AST subtree and record CALLS edges for call expressions.

        Returns:
            (n_plus_one_risk: bool, sql_injection_risk: bool)
        """
        n_plus_one_risk = False
        sql_injection_risk = False

        # Mark loop contexts
        if n.type in ("for_statement", "while_statement", "for_of_statement", "for_in_statement", "do_statement"):
            in_loop = True

        if n.type == "call_expression":
            # Try to find the called identifier (could be a plain function or a member access)
            func_node = n.child_by_field_name("function") or n.child_by_field_name("callee") or (n.children[0] if n.children else None)
            called_name = None
            func_text = ""
            owner_hint = None
            if func_node:
                func_text = func_node.text.decode("utf-8")
                if func_node.type in ("identifier", "property_identifier"):
                    called_name = func_text
                else:
                    # For member expressions, take the last identifier (e.g., obj.method)
                    for c in reversed(func_node.children):
                        if c.type in ("identifier", "property_identifier"):
                            called_name = c.text.decode("utf-8")
                            break
                # Infer owner hint from member expression roots like svc.findById(...)
                root_expr = func_text.replace("?.", ".")
                parts = [p.strip() for p in root_expr.split(".") if p.strip()]
                root = None
                if len(parts) >= 2:
                    if parts[0] == "this" and len(parts) >= 3:
                        root = parts[1]
                    elif parts[0] != "this":
                        root = parts[0]
                if root:
                    local_hints = local_type_hints or {}
                    if root in local_hints:
                        owner_hint = _normalize_symbol(local_hints.get(root))
                    else:
                        owner_hint = _normalize_symbol(import_alias_map.get(root) or (root if root[:1].isupper() else None))
                elif root_expr.startswith("this.") and current_owner:
                    owner_hint = _normalize_symbol(current_owner)

            if called_name:
                lower = called_name.lower()

                # N+1 query heuristic (calls involving DB-like methods inside loops)
                if in_loop and any(k in lower for k in ("find", "get", "query", "select", "save")):
                    n_plus_one_risk = True

                # SQL injection heuristic (string concatenation or template string feeding query)
                if any(k in lower for k in ("executequery", "query", "$query")):
                    args = [c for c in n.children if c.type in ("arguments", "argument_list")]
                    for arg in args:
                        text = arg.text.decode("utf-8")
                        if "+" in text or "`" in text:
                            sql_injection_risk = True

                # HTTP route extraction (frontend/mobile call sites)
                func_lower = func_text.lower()
                if any(kw in func_lower for kw in ("fetch(", "axios.", "api.", "http.", "axios(", "http.get", "http.post", "api.get", "api.post")):
                    import re
                    m = re.search(r"['\"](/[^'\"]+)['\"]", n.text.decode("utf-8"))
                    if m:
                        called_routes.append(m.group(1))

                called_ns = (
                    f"{project_name}:{rel_path}:{owner_hint}.{called_name}"
                    if owner_hint else
                    f"{project_name}:{rel_path}:{called_name}"
                )
                rel_data = {
                    "from": owner_ns,
                    "to": called_ns,
                    "type": "CALLS",
                    "target_method_hint": called_name,
                }
                if owner_hint:
                    rel_data["target_owner_hint"] = owner_hint
                entities["relationships"].append(rel_data)

        for c in n.children:
            child_n_plus_one, child_sql_injection = _collect_call_relationships(
                owner_ns,
                c,
                called_routes,
                in_loop,
                local_type_hints=local_type_hints,
                current_owner=current_owner,
            )
            n_plus_one_risk = n_plus_one_risk or child_n_plus_one
            sql_injection_risk = sql_injection_risk or child_sql_injection

        return n_plus_one_risk, sql_injection_risk

    def find_entities(node):
        # Class declarations
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                ns_key = f"{project_name}:{rel_path}:{name}"
                class_field_names = _extract_ts_class_field_names(node)
                
                node_data = {
                    "label": "TS_Component",
                    "namespace_key": ns_key,
                    "name": name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    **calculate_metrics(node)
                }
                if class_field_names:
                    node_data["class_fields"] = sorted(list(class_field_names))
                
                # Add intelligence properties
                if cloud_blocker:
                    node_data["cloud_blocker"] = True
                if _is_sensitive_data_name(name):
                    node_data["labels"] = ["Sensitive_Data"]
                
                entities["nodes"].append(node_data)

                # Detect NestJS controller methods (e.g., @Get(), @Post()) and create API_Endpoint nodes
                for class_child in node.children:
                    if class_child.type != "class_body":
                        continue
                    for method in class_child.children:
                        if method.type != "method_definition":
                            continue
                        decorators = _get_decorators(method)
                        route_path = _extract_nest_route(decorators)
                        if not route_path:
                            continue

                        name_node = method.child_by_field_name("name")
                        if not name_node:
                            continue

                        method_name = name_node.text.decode("utf-8")
                        method_ns = f"{project_name}:{rel_path}:{name}.{method_name}"

                        method_data = {
                            "label": "API_Endpoint",
                            "namespace_key": method_ns,
                            "name": method_name,
                            "file": rel_path,
                            "project": project_name,
                            "layer": layer,
                            "parent_class": name,
                            "route_path": route_path,
                            "called_routes": [],
                            **calculate_metrics(method),
                        }
                        m_refs = _extract_ts_method_field_refs(method, class_field_names)
                        if m_refs:
                            method_data["field_refs"] = m_refs

                        if cloud_blocker:
                            method_data["cloud_blocker"] = True
                        if _detect_empty_catch(method, content):
                            method_data["swallowed_exception"] = True

                        entities["nodes"].append(method_data)
                        entities["relationships"].append({
                            "from": ns_key,
                            "to": method_ns,
                            "type": "HAS_METHOD",
                        })

                        # Track method calls inside this class method to create CALLS relationships
                        n_plus_one, sql_injection = _collect_call_relationships(
                            method_ns,
                            method,
                            method_data["called_routes"],
                            local_type_hints=_infer_local_type_hints(method),
                            current_owner=name,
                        )
                        if n_plus_one:
                            method_data["n_plus_one_risk"] = True
                        if sql_injection:
                            method_data["sql_injection_risk"] = True

                        # Check for compliance violations
                        violation, leaked = _check_compliance_violation(method, content)
                        if violation:
                            method_data["compliance_violation"] = True
                            method_data["leaked_data"] = leaked

        # Function declarations (including exported)
        if node.type in ("function_declaration", "arrow_function"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = name_node.text.decode("utf-8")
                ns_key = f"{project_name}:{rel_path}:{name}"

                decorators = _get_decorators(node)
                route_path = _extract_nest_route(decorators)
                label = "API_Endpoint" if route_path else "TS_Function"

                node_data = {
                    "label": label,
                    "namespace_key": ns_key,
                    "name": name,
                    "file": rel_path,
                    "project": project_name,
                    "layer": layer,
                    "called_routes": [],
                    **calculate_metrics(node)
                }

                if route_path:
                    node_data["route_path"] = route_path

                # Add intelligence properties
                if cloud_blocker:
                    node_data["cloud_blocker"] = True
                if _is_sensitive_data_name(name):
                    node_data["labels"] = ["Sensitive_Data"]
                if _detect_hardcoded_secret(name, content):
                    node_data["hardcoded_secret"] = True
                if _detect_empty_catch(node, content):
                    node_data["swallowed_exception"] = True

                entities["nodes"].append(node_data)
                n_plus_one, sql_injection = _collect_call_relationships(
                    ns_key,
                    node,
                    node_data["called_routes"],
                    local_type_hints=_infer_local_type_hints(node),
                )
                if n_plus_one:
                    node_data["n_plus_one_risk"] = True
                if sql_injection:
                    node_data["sql_injection_risk"] = True

                # Check for compliance violations
                violation, leaked = _check_compliance_violation(node, content)
                if violation:
                    node_data["compliance_violation"] = True
                    node_data["leaked_data"] = leaked

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
                        
                        node_data = {
                            "label": label,
                            "namespace_key": ns_key,
                            "name": name,
                            "file": rel_path,
                            "project": project_name,
                            "layer": layer,
                            "called_routes": [],
                            **calculate_metrics(value_node)
                        }
                        
                        # Add intelligence properties
                        if cloud_blocker:
                            node_data["cloud_blocker"] = True
                        if _is_sensitive_data_name(name):
                            node_data["labels"] = ["Sensitive_Data"]
                        if _detect_hardcoded_secret(name, content):
                            node_data["hardcoded_secret"] = True
                        
                        entities["nodes"].append(node_data)
                        n_plus_one, sql_injection = _collect_call_relationships(
                            ns_key,
                            value_node,
                            node_data["called_routes"],
                            local_type_hints=_infer_local_type_hints(value_node),
                        )
                        if n_plus_one:
                            node_data["n_plus_one_risk"] = True
                        if sql_injection:
                            node_data["sql_injection_risk"] = True

                        # Check for compliance violations
                        violation, leaked = _check_compliance_violation(value_node, content)
                        if violation:
                            node_data["compliance_violation"] = True
                            node_data["leaked_data"] = leaked

        # Export default function
        if node.type == "export_statement":
            for child in node.children:
                if child.type == "function_declaration":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = name_node.text.decode("utf-8")
                        ns_key = f"{project_name}:{rel_path}:{name}"

                        decorators = _get_decorators(child)
                        route_path = _extract_nest_route(decorators)
                        label = "API_Endpoint" if route_path else ("TS_Component" if is_tsx else "TS_Function")

                        node_data = {
                            "label": label,
                            "namespace_key": ns_key,
                            "name": name,
                            "file": rel_path,
                            "project": project_name,
                            "layer": layer,
                            "called_routes": [],
                            **calculate_metrics(child)
                        }

                        if route_path:
                            node_data["route_path"] = route_path

                        # Add intelligence properties
                        if cloud_blocker:
                            node_data["cloud_blocker"] = True
                        if _is_sensitive_data_name(name):
                            node_data["labels"] = ["Sensitive_Data"]
                        if _detect_hardcoded_secret(name, content):
                            node_data["hardcoded_secret"] = True
                        if _detect_empty_catch(child, content):
                            node_data["swallowed_exception"] = True

                        entities["nodes"].append(node_data)
                        n_plus_one, sql_injection = _collect_call_relationships(
                            ns_key,
                            child,
                            node_data["called_routes"],
                            local_type_hints=_infer_local_type_hints(child),
                        )
                        if n_plus_one:
                            node_data["n_plus_one_risk"] = True
                        if sql_injection:
                            node_data["sql_injection_risk"] = True

                        # Check for compliance violations
                        violation, leaked = _check_compliance_violation(child, content)
                        if violation:
                            node_data["compliance_violation"] = True
                            node_data["leaked_data"] = leaked

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

    # Detect Express-like / Router endpoints (app.get, router.post, etc.)
    import re
    endpoint_pattern = re.compile(r"\b(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]")
    seen = set(n["namespace_key"] for n in entities["nodes"])
    for m in endpoint_pattern.finditer(content):
        method = m.group(1).upper()
        route_path = m.group(2)
        ns_key = f"{project_name}:{rel_path}:endpoint:{method}:{route_path}"
        if ns_key in seen:
            continue
        seen.add(ns_key)

        entities["nodes"].append({
            "label": "API_Endpoint",
            "namespace_key": ns_key,
            "name": f"{method} {route_path}",
            "file": rel_path,
            "project": project_name,
            "layer": layer,
            "route_path": route_path,
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

    prompt = f"""Analyze this SQL/PLSQL code and return ONLY a valid JSON (no markdown, no explanation) with this exact structure:
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

The code may include PL/SQL constructs such as:
- CREATE PROCEDURE
- CREATE PACKAGE
- CREATE TRIGGER
- PRAGMA, CURSOR, EXCEPTION blocks

IMPORTANT: For each procedure/function/package/trigger in the file, extract any call to other procedures/functions/packages/triggers and list their names in the "calls" array. This includes invocations like:
- MY_PROC(...)
- schema.OTHER_PROC(...)
- package_name.fn(...)
- SOME_TRIGGER(...) (when invoked)

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
DIRETRIZES DE RESPOSTA (OBRIGATÓRIO):
- Estruture TODAS as respostas em 3 blocos bem definidos (na ordem abaixo), usando cabeçalhos claros.

1) 📊 Visão Executiva (Simples):
   - Explicação voltada para diretores e stakeholders não-técnicos.
   - Use analogias do mundo real (ex: "apagar este componente é como tirar o motor do carro").

2) ⚙️ Visão Técnica (Avançada):
   - Impacto profundo em código, métodos, tabelas e injeções de dependência.

3) ✅ Recomendação de Ação:
   - Plano de mitigação seguro e próximos passos práticos.

SEMPRE que possível, identifique 'namespace_keys' relevantes no contexto.

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
            chat_payload = {
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
            }
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=chat_payload)

            # Older Ollama builds may not expose /api/chat; fallback to /api/generate.
            if resp.status_code == 404:
                logger.warning("Ollama /api/chat not found. Falling back to /api/generate.")
                generate_payload = {
                    "model": model_name,
                    "prompt": f"{system_prompt}\n\n{prompt}",
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 400,
                        "top_k": 20,
                        "top_p": 0.9
                    },
                    "keep_alive": "5m"
                }
                resp = await client.post(f"{OLLAMA_URL}/api/generate", json=generate_payload)
                resp.raise_for_status()
                result = resp.json()
                return result.get("response", "{}")

            resp.raise_for_status()
            result = resp.json()
            return result.get("message", {}).get("content", "{}")

    try:
        try:
            # Try primary chat model first
            logger.info("Attempting AI response with primary model: %s (10s timeout)", OLLAMA_CHAT_MODEL)
            content = await _call_ollama(OLLAMA_CHAT_MODEL, 10.0)
            return {"raw_text": content, "model": OLLAMA_CHAT_MODEL}
        except (httpx.ReadTimeout, httpx.ConnectError, httpx.HTTPStatusError, ValueError) as e:
            logger.warning("Primary model %s failed (%s). Retrying with %s...", OLLAMA_CHAT_MODEL, e, OLLAMA_FAST_MODEL)
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
    """Send a complex request to the high-end architectural model with robust fallbacks."""
    global ai_busy
    ai_busy = True

    async def _call_ollama_generate(model: str, timeout: float) -> str:
        # Usamos /api/generate pois é mais universal e ignora a ausência de chat_templates
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt_text,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 1024
                    },
                    "keep_alive": "5m"
                },
            )
            resp.raise_for_status()
            result = resp.json()
            content = result.get("response", "").strip()
            
            if not content:
                raise ValueError(f"O modelo {model} retornou um texto vazio.")
                
            return content

    try:
        logger.info("Deep architectural review requested via %s", OLLAMA_COMPLEX_MODEL)
        try:
            return await _call_ollama_generate(OLLAMA_COMPLEX_MODEL, 180.0)
        except Exception as e:
            logger.warning("Complex model failed (%s); falling back to chat model", e)
            try:
                return await _call_ollama_generate(OLLAMA_CHAT_MODEL, 90.0)
            except Exception as e2:
                logger.warning("Chat model fallback failed (%s); trying fast model", e2)
                try:
                    return await _call_ollama_generate(OLLAMA_FAST_MODEL, 60.0)
                except Exception as e3:
                    logger.error("All fallback models failed: %s", e3)
                    return "⚠️ Todos os modelos de IA falharam em gerar o relatório. Verifique se os modelos estão instalados no Ollama (`ollama list`) e se o computador tem memória RAM/VRAM disponível."
    finally:
        ai_busy = False


# ──────────────────────────────────────────────
# Project Scanner
# ──────────────────────────────────────────────
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".gradle", "build", "dist",
    ".idea", ".vscode", "target", "bin", ".next", "venv", "env",
}

SUPPORTED_EXTENSIONS = {".java", ".ts", ".tsx", ".sql", ".prc", ".fnc", ".pkg"}


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


def _normalize_route(route: str) -> str:
    """Normalize a HTTP route for matching.

    - Trims whitespace and quotes
    - Removes query strings
    - Strips protocol/host
    - Ensures leading '/'
    - Converts to lowercase (for case-insensitive matching)
    """
    if not route or not isinstance(route, str):
        return ""
    r = route.strip().strip("\"'")
    # Remove query string
    if "?" in r:
        r = r.split("?", 1)[0]
    # Strip protocol/host if present
    if "://" in r:
        try:
            r = r.split("://", 1)[1]
            # keep only the path
            if "/" in r:
                r = r[r.index("/"):]
        except Exception:
            pass
    r = r.strip()
    if not r.startswith("/"):
        r = "/" + r
    # Remove trailing slash (but keep root)
    if len(r) > 1 and r.endswith("/"):
        r = r[:-1]
    return r.lower()


def _route_matches(pattern: str, candidate: str) -> bool:
    """Check if candidate path matches a pattern with optional {param} segments."""
    if not pattern or not candidate:
        return False

    p = pattern.strip("/")
    c = candidate.strip("/")
    p_segs = p.split("/") if p else []
    c_segs = c.split("/") if c else []

    if len(p_segs) != len(c_segs):
        return False

    for ps, cs in zip(p_segs, c_segs):
        if ps.startswith("{") and ps.endswith("}"):
            continue
        if ps != cs:
            return False
    return True


def _link_cross_project_apis(entities: dict) -> None:
    """Link frontend/mobile HTTP call sites to backend API endpoints.

    - Builds an index of API_Endpoint nodes by normalized route.
    - Scans nodes with `called_routes` and matches them to endpoints.
    - Adds CONSUMES_API relationships when a match is found.
    """
    nodes = entities.get("nodes", [])
    rels = entities.get("relationships", [])

    # Build endpoint index: normalized route -> list of endpoint namespace_keys
    endpoint_index: dict[str, list[str]] = {}
    for node in nodes:
        label = node.get("label") or ""
        labels = node.get("labels") or []
        if label == "API_Endpoint" or "API_Endpoint" in labels:
            route = node.get("route_path")
            if not route:
                continue
            norm = _normalize_route(route)
            if not norm:
                continue
            endpoint_index.setdefault(norm, []).append(node.get("namespace_key"))

    if not endpoint_index:
        return

    existing = set(
        (r.get("from"), r.get("to"), r.get("type"))
        for r in rels
        if r.get("from") and r.get("to") and r.get("type")
    )

    for node in nodes:
        called_routes = node.get("called_routes") or []
        if not isinstance(called_routes, list) or not called_routes:
            continue

        src = node.get("namespace_key")
        if not src:
            continue

        for raw in called_routes:
            cand = _normalize_route(raw)
            if not cand:
                continue

            # Exact match first
            matched = set(endpoint_index.get(cand, []))

            # Partial/parametric match for patterns like /users/{id}
            if not matched:
                for ep, ns_keys in endpoint_index.items():
                    if _route_matches(ep, cand) or _route_matches(cand, ep):
                        matched.update(ns_keys)

            for dst in matched:
                key = (src, dst, "CONSUMES_API")
                if key in existing:
                    continue
                rels.append({"from": src, "to": dst, "type": "CONSUMES_API"})
                existing.add(key)


def _extract_class_key_from_method(node: dict) -> str | None:
    """Infer parent class namespace key from a method node."""
    ns_key = node.get("namespace_key", "")
    parent_class = node.get("parent_class")
    if not ns_key:
        return None

    if parent_class:
        parts = ns_key.split(":")
        if len(parts) >= 3:
            return f"{parts[0]}:{parts[1]}:{parent_class}"

    if "." in ns_key.split(":")[-1]:
        prefix, tail = ns_key.rsplit(":", 1)
        cls = tail.split(".", 1)[0]
        return f"{prefix}:{cls}"
    return None


def _extract_owner_name_from_callable(node: dict) -> str | None:
    """Return owning class/component name for method-like call targets when available."""
    parent_class = node.get("parent_class")
    if isinstance(parent_class, str) and parent_class.strip():
        return parent_class.strip()
    ns_key = str(node.get("namespace_key", ""))
    tail = ns_key.split(":")[-1] if ns_key else ""
    if "." in tail:
        return tail.split(".", 1)[0].strip() or None
    return None


def _class_declares_interface(node_by_key: dict[str, dict], candidate: dict, owner_hint: str) -> bool:
    """Check if candidate's owning class declares implements owner_hint."""
    cls_key = _extract_class_key_from_method(candidate)
    if not cls_key:
        return False
    cls_node = node_by_key.get(cls_key) or {}
    impls = cls_node.get("implements_interfaces") or []
    if isinstance(impls, str):
        impls = [impls]
    owner_norm = owner_hint.strip().lower()
    for iface in impls:
        if str(iface).strip().lower() == owner_norm:
            return True
    return False


def _build_class_name_index(nodes: list[dict]) -> dict[tuple[str, str], dict]:
    """Index class nodes by (project, class_name_lower)."""
    index: dict[tuple[str, str], dict] = {}
    for n in nodes:
        if n.get("label") != "Java_Class":
            continue
        project = str(n.get("project") or "")
        name = str(n.get("name") or "").strip().lower()
        if not project or not name:
            continue
        index[(project, name)] = n
    return index


def _class_extends_hint(
    node_by_key: dict[str, dict],
    class_index: dict[tuple[str, str], dict],
    candidate: dict,
    owner_hint: str,
    max_depth: int = 8,
) -> bool:
    """Check whether candidate's owning class extends owner_hint (directly or transitively)."""
    cls_key = _extract_class_key_from_method(candidate)
    if not cls_key:
        return False
    cls_node = node_by_key.get(cls_key) or {}
    project = str(cls_node.get("project") or "")
    target = owner_hint.strip().lower()
    if not project or not target:
        return False

    current = cls_node
    visited: set[str] = set()
    depth = 0
    while current and depth < max_depth:
        current_name = str(current.get("name") or "").strip().lower()
        if current_name and current_name == target:
            return True
        parent_name = str(current.get("extends_class") or "").strip().lower()
        if not parent_name or parent_name in visited:
            return False
        if parent_name == target:
            return True
        visited.add(parent_name)
        current = class_index.get((project, parent_name))
        depth += 1
    return False


def _resolve_internal_calls(entities: dict, max_hops: int = 4) -> None:
    """Resolve CALLS edges to concrete method/function nodes and derive transitive calls."""
    nodes = entities.get("nodes", [])
    rels = entities.get("relationships", [])
    node_by_key = {n.get("namespace_key"): n for n in nodes if n.get("namespace_key")}
    method_like_labels = {"Java_Method", "TS_Function", "API_Endpoint"}

    method_nodes = [
        n for n in nodes
        if (n.get("label") in method_like_labels) and n.get("namespace_key")
    ]
    class_index = _build_class_name_index(nodes)
    by_method_name: dict[str, list[dict]] = defaultdict(list)
    for n in method_nodes:
        by_method_name[str(n.get("name", "")).strip()].append(n)

    existing = {
        (r.get("from"), r.get("to"), r.get("type"))
        for r in rels
        if r.get("from") and r.get("to") and r.get("type")
    }

    direct_adjacency: dict[str, set[str]] = defaultdict(set)

    for rel in list(rels):
        if rel.get("type") != "CALLS":
            continue
        src = rel.get("from")
        raw_to = rel.get("to", "")
        if not src or not raw_to:
            continue
        src_node = node_by_key.get(src)
        if not src_node:
            continue

        called_name = rel.get("target_method_hint") or raw_to.split(":")[-1].split(".")[-1]
        owner_hint = str(rel.get("target_owner_hint") or "").strip() or None
        candidates = by_method_name.get(called_name, [])
        if not candidates:
            continue

        src_project = src_node.get("project")
        src_file = src_node.get("file")
        src_class_key = _extract_class_key_from_method(src_node)
        if owner_hint:
            hinted_candidates = [
                cand for cand in candidates
                if (_extract_owner_name_from_callable(cand) or "").lower() == owner_hint.lower()
            ]
            impl_candidates = [
                cand for cand in candidates
                if _class_declares_interface(node_by_key, cand, owner_hint)
            ]
            extends_candidates = [
                cand for cand in candidates
                if _class_extends_hint(node_by_key, class_index, cand, owner_hint)
            ]
            if hinted_candidates:
                candidates = hinted_candidates
            elif impl_candidates:
                candidates = impl_candidates
            elif extends_candidates:
                candidates = extends_candidates

        def _score(candidate: dict) -> tuple[int, int]:
            score = 0
            if candidate.get("project") == src_project:
                score += 40
            if candidate.get("file") == src_file:
                score += 30
            cand_class_key = _extract_class_key_from_method(candidate)
            if src_class_key and cand_class_key and src_class_key == cand_class_key:
                score += 30
            cand_owner = _extract_owner_name_from_callable(candidate)
            if owner_hint and cand_owner and cand_owner.lower() == owner_hint.lower():
                score += 50
            if owner_hint and _class_declares_interface(node_by_key, candidate, owner_hint):
                score += 35
            if owner_hint and _class_extends_hint(node_by_key, class_index, candidate, owner_hint):
                score += 30
            if owner_hint and cand_owner and (
                cand_owner.lower() == f"{owner_hint.lower()}impl" or
                cand_owner.lower().endswith(owner_hint.lower())
            ):
                score += 15
            return score, -len(candidate.get("namespace_key", ""))

        ranked = sorted(candidates, key=_score, reverse=True)
        best = ranked[0]
        dst = best.get("namespace_key")
        if not dst or src == dst:
            continue

        confidence = min(100, _score(best)[0])
        method = "exact_key" if confidence >= 90 else ("qualified_name" if confidence >= 70 else "heuristic")

        key = (src, dst, "CALLS_RESOLVED")
        if key not in existing:
            rels.append({
                "from": src,
                "to": dst,
                "type": "CALLS_RESOLVED",
                "confidence_score": confidence,
                "resolution_method": method,
            })
            existing.add(key)
        direct_adjacency[src].add(dst)

    # N-hop derived edges for impact propagation
    for origin in list(direct_adjacency.keys()):
        visited = {origin}
        frontier = [(origin, 0)]
        while frontier:
            current, depth = frontier.pop(0)
            if depth >= max_hops:
                continue
            for nxt in direct_adjacency.get(current, set()):
                if nxt in visited:
                    continue
                visited.add(nxt)
                frontier.append((nxt, depth + 1))
                if depth + 1 >= 2:
                    key = (origin, nxt, "CALLS_NHOP")
                    if key not in existing:
                        rels.append({
                            "from": origin,
                            "to": nxt,
                            "type": "CALLS_NHOP",
                            "hop_distance": depth + 1,
                        })
                        existing.add(key)


def _apply_ck_metrics(entities: dict) -> None:
    """Compute CK-style class metrics (WMC, CBO, RFC, LCOM proxy)."""
    nodes = entities.get("nodes", [])
    rels = entities.get("relationships", [])
    node_by_key = {n.get("namespace_key"): n for n in nodes if n.get("namespace_key")}
    class_nodes = [n for n in nodes if n.get("label") in ("Java_Class", "TS_Component")]
    has_method = [r for r in rels if r.get("type") == "HAS_METHOD" and r.get("to") in node_by_key]
    calls = [r for r in rels if r.get("type") in ("CALLS_RESOLVED", "CALLS")]

    methods_by_class: dict[str, list[dict]] = defaultdict(list)
    for rel in has_method:
        cls_key = rel.get("from")
        method = node_by_key.get(rel.get("to"))
        if cls_key and method:
            methods_by_class[cls_key].append(method)

    call_targets_by_method: dict[str, set[str]] = defaultdict(set)
    for rel in calls:
        src = rel.get("from")
        dst = rel.get("to")
        if src and dst:
            call_targets_by_method[src].add(dst)

    outgoing_by_class: dict[str, set[str]] = defaultdict(set)
    for rel in rels:
        if rel.get("type") in ("IMPORTS", "DEPENDS_ON") and rel.get("from"):
            outgoing_by_class[rel["from"]].add(rel.get("to") or rel.get("to_import"))

    for cls in class_nodes:
        cls_key = cls.get("namespace_key")
        if not cls_key:
            continue
        methods = methods_by_class.get(cls_key, [])
        if not methods:
            cls["wmc"] = 0
            cls["cbo"] = 0
            cls["rfc"] = 0
            cls["lcom"] = 0.0
            continue

        method_keys = {m.get("namespace_key") for m in methods if m.get("namespace_key")}
        # WMC: sum of method complexities
        wmc = sum(int(m.get("complexity", 1) or 1) for m in methods)

        # CBO: unique external class dependencies via calls/imports
        dep_classes = set(outgoing_by_class.get(cls_key, set()))
        external_called_classes = set()
        for m in methods:
            mkey = m.get("namespace_key")
            if not mkey:
                continue
            for dst in call_targets_by_method.get(mkey, set()):
                dst_node = node_by_key.get(dst)
                if not dst_node:
                    continue
                dst_class = _extract_class_key_from_method(dst_node) or dst
                if dst_class != cls_key:
                    external_called_classes.add(dst_class)
        cbo = len({d for d in dep_classes if d}) + len(external_called_classes)

        # RFC: own methods + distinct callable methods reached directly
        callable_set = set()
        for m in methods:
            mkey = m.get("namespace_key")
            if not mkey:
                continue
            callable_set.update(call_targets_by_method.get(mkey, set()))
        rfc = len(methods) + len(callable_set)

        # LCOM (field-sharing based): percentage of method pairs that do not share any class field
        method_field_refs: dict[str, set[str]] = {}
        for m in methods:
            mkey = m.get("namespace_key")
            refs = m.get("field_refs") or []
            if mkey and isinstance(refs, list):
                method_field_refs[mkey] = {str(r) for r in refs if str(r).strip()}

        total_pairs = 0
        non_cohesive_pairs = 0
        cohesive_pairs = 0
        method_key_list = [mk for mk in method_keys if mk]
        for i in range(len(method_key_list)):
            for j in range(i + 1, len(method_key_list)):
                total_pairs += 1
                a = method_key_list[i]
                b = method_key_list[j]
                shared = method_field_refs.get(a, set()) & method_field_refs.get(b, set())
                if shared:
                    cohesive_pairs += 1
                else:
                    non_cohesive_pairs += 1

        if total_pairs > 0:
            # LCOM normalized between 0..1
            lcom = max(0.0, float(non_cohesive_pairs - cohesive_pairs) / float(total_pairs))
        else:
            lcom = 0.0

        cls["wmc"] = int(wmc)
        cls["cbo"] = int(cbo)
        cls["rfc"] = int(rfc)
        cls["lcom"] = round(float(lcom), 4)


def _compute_git_churn(project_path: str, days: int | None = None) -> dict[str, int]:
    """Compute per-file churn from git log --name-only."""
    try:
        cmd = ["git", "-C", project_path, "log", "--name-only", "--pretty=format:"]
        if days is not None and days > 0:
            cmd = ["git", "-C", project_path, "log", f"--since={days}.days", "--name-only", "--pretty=format:"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
        if proc.returncode != 0:
            return {}
        churn: dict[str, int] = defaultdict(int)
        for line in proc.stdout.splitlines():
            rel = line.strip().replace("\\", "/")
            if not rel:
                continue
            churn[rel] += 1
        return dict(churn)
    except Exception:
        return {}


def _compute_git_cochange_pairs(project_path: str, days: int = 90, top_n: int = 30) -> list[dict]:
    """Compute top co-change file pairs from git history."""
    try:
        cmd = [
            "git",
            "-C",
            project_path,
            "log",
            f"--since={max(1, days)}.days",
            "--name-only",
            "--pretty=format:__COMMIT__",
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="ignore",
        )
        if proc.returncode != 0:
            return []

        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        current_files: set[str] = set()

        def flush_commit():
            files = sorted(list(current_files))
            if len(files) < 2:
                return
            for i in range(len(files)):
                for j in range(i + 1, len(files)):
                    pair_count[(files[i], files[j])] += 1

        for line in proc.stdout.splitlines():
            text = line.strip().replace("\\", "/")
            if not text:
                continue
            if text == "__COMMIT__":
                flush_commit()
                current_files = set()
                continue
            current_files.add(text)
        flush_commit()

        ranked = sorted(pair_count.items(), key=lambda x: x[1], reverse=True)
        return [
            {"file_a": a, "file_b": b, "cochange_count": cnt}
            for (a, b), cnt in ranked[: max(1, min(top_n, 200))]
        ]
    except Exception:
        return []


def _apply_git_hotspots(entities: dict, project_path: str) -> None:
    """Apply Adam Tornhill-style hotspot proxy = complexity * churn."""
    churn_by_file = _compute_git_churn(project_path)
    if not churn_by_file:
        return

    for node in entities.get("nodes", []):
        rel_file = str(node.get("file", "")).replace("\\", "/")
        churn = int(churn_by_file.get(rel_file, 0))
        complexity = int(node.get("complexity", 1) or 1)
        hotspot_score = min(100.0, float(complexity * max(1, churn)))
        node["git_churn"] = churn
        node["hotspot_score"] = round(hotspot_score, 2)


async def scan_project(project_path: str) -> dict:
    """Walk a project directory and parse all supported files."""
    global scan_state, scanned_projects
    project_path = os.path.normpath(project_path)
    all_entities = {"nodes": [], "relationships": []}

    # Collect test file names for Test Gap Analysis
    # We treat any file containing 'test' or 'spec' in the filename as a test file.
    test_files: set[str] = set()

    # Register this project for later file access
    project_name = Path(project_path).name
    scanned_projects[project_name] = project_path
    logger.info(f"Registered project: {project_name} -> {project_path}")

    if not os.path.isdir(project_path):
        scan_state.errors.append(f"Directory not found: {project_path}")
        return all_entities

    for root_dir, dirs, files in os.walk(project_path):
        # Skip irrelevant directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file_name in files:
            file_path = os.path.join(root_dir, file_name)
            ext = os.path.splitext(file_name)[1].lower()

            # Gather test file basenames for Test Gap Analysis
            fname_lower = file_name.lower()
            if "test" in fname_lower or "spec" in fname_lower:
                base = os.path.splitext(file_name)[0]
                test_files.add(base.lower())

            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                scan_state.current_file = os.path.relpath(file_path, project_path).replace("\\", "/")

                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                owner = _get_git_owner(file_path)

                if not content.strip():
                    continue

                if ext == ".java":
                    result = parse_java(file_path, content, project_path)
                elif ext in (".ts", ".tsx"):
                    result = parse_typescript(file_path, content, project_path)
                elif ext in (".sql", ".prc", ".fnc", ".pkg"):
                    result = await parse_sql_with_ollama(file_path, content, project_path)
                else:
                    continue

                # Add owner to all nodes from this file
                for node in result.get("nodes", []):
                    node["owner"] = owner

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

    # Test Gap Analysis: flag classes/components without an associated test file
    for node in all_entities.get("nodes", []):
        if node.get("label") not in ("Java_Class", "TS_Component"):
            continue

        class_name = str(node.get("name", ""))
        if not class_name:
            continue

        class_lower = class_name.lower()
        # A corresponding test file is any filename that includes the class name
        has_test = any(class_lower in tf for tf in test_files)
        if not has_test:
            node["missing_tests"] = True

    # Cross-project API linking (frontend/mobile -> backend endpoints)
    _link_cross_project_apis(all_entities)
    # Resolve method/function calls to concrete targets and derive N-hop links
    _resolve_internal_calls(all_entities, max_hops=4)
    # Compute CK-style class metrics
    _apply_ck_metrics(all_entities)
    # Apply Git churn + hotspot score
    _apply_git_hotspots(all_entities, project_path)

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
        # Handle IMPORTS separately - create external dependency node
        if "to_import" in rel:
            if neo4j_service.is_connected:
                try:
                    # Create external dependency node
                    dep_import = rel["to_import"]
                    if dep_import and not dep_import.startswith("."):
                        dep_ns_key = f"external:{dep_import}"
                        neo4j_service.merge_node("External_Dependency", dep_ns_key, {
                            "namespace_key": dep_ns_key,
                            "name": dep_import,
                            "type": "external"
                        })
                        # Create IMPORTS relationship
                        neo4j_service.merge_relationship(rel["from"], dep_ns_key, "IMPORTS")
                        scan_state.total_relationships += 1
                except Exception as e:
                    logger.error("Failed to process import relationship: %s", e)
            continue

        rel_props = {
            k: v
            for k, v in rel.items()
            if k not in ("from", "to", "type", "to_import")
        }

        # Always store in memory
        memory_edges.append({
            "source": rel["from"],
            "target": rel["to"],
            "type": rel["type"],
            **rel_props,
        })

        # Try Neo4j if connected
        if neo4j_service.is_connected:
            try:
                neo4j_service.merge_relationship(rel["from"], rel["to"], rel["type"], rel_props or None)
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
        try:
            _rebuild_rag_index(include_embeddings=False, persist=True)
        except Exception as reidx_err:
            logger.warning("Post-scan RAG index refresh failed: %s", reidx_err)
        logger.info(
            "Scan complete: %d files, %d nodes, %d relationships",
            scan_state.scanned_files,
            scan_state.total_nodes,
            scan_state.total_relationships,
        )

        try:
            anti = await get_antipatterns()
            call_res = _compute_call_resolution_summary(top_n=10)
            snapshot = {
                "timestamp": datetime.datetime.now().isoformat(),
                "total_nodes": scan_state.total_nodes,
                "total_edges": scan_state.total_relationships,
                "god_classes": len(anti.get("god_classes", [])),
                "circular_deps": len(anti.get("circular_dependencies", [])),
                "dead_code": len(anti.get("dead_code", [])),
                "call_resolution_rate": float(call_res.get("resolution_rate", 0.0) or 0.0),
                "call_total": int(call_res.get("total_calls", 0) or 0),
                "call_resolved": int(call_res.get("resolved_calls", 0) or 0),
                "call_unresolved": int(call_res.get("unresolved_calls", 0) or 0),
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


def _ensure_memory_graph_loaded() -> None:
    """Populate in-memory graph from Neo4j when empty."""
    global memory_nodes, memory_edges
    if memory_nodes:
        return
    if not neo4j_service.is_connected:
        return
    try:
        data = neo4j_service.get_full_graph()
        memory_nodes = [dict(n) for n in data.get("nodes", [])]
        memory_edges = [dict(e) for e in data.get("edges", [])]
    except Exception as e:
        logger.warning("Failed to lazy-load memory graph: %s", e)


def _memory_nodes_index() -> dict[str, dict]:
    """Build a dict-shaped memory index expected by semantic analyzers."""
    _ensure_memory_graph_loaded()
    index: dict[str, dict] = {}
    for node in memory_nodes:
        key = node.get("namespace_key")
        if not key:
            continue
        index[key] = {
            "labels": list(node.get("labels", [])),
            "properties": dict(node),
        }
    return index


def _normalized_memory_edges() -> list[dict]:
    """Normalize edge keys so analyzers can consume both source/target and from/to."""
    _ensure_memory_graph_loaded()
    normalized: list[dict] = []
    for edge in memory_edges:
        src = edge.get("source") or edge.get("from")
        tgt = edge.get("target") or edge.get("to")
        if not src or not tgt:
            continue
        normalized.append({
            "source": src,
            "target": tgt,
            "from": src,
            "to": tgt,
            "type": edge.get("type", ""),
        })
    return normalized


def _build_analysis_runtime() -> dict[str, object]:
    """Create analyzer instances wired with current graph state."""
    memory_index = _memory_nodes_index()
    normalized_edges = _normalized_memory_edges()
    deep_parser = DeepParser()
    semantic_analyzer = SemanticAnalyzer(ollama_url=OLLAMA_URL, model=OLLAMA_COMPLEX_MODEL)
    impact_engine = ImpactEngine(neo4j_service, memory_nodes, normalized_edges)
    taint_propagator = TaintPropagator(neo4j_service, memory_index, normalized_edges)
    symbol_resolver = SymbolResolver(neo4j_service, memory_index, deep_parser)
    side_effect_detector = SideEffectDetector(
        neo4j_service,
        memory_index,
        normalized_edges,
        semantic_analyzer,
    )
    fragility_calculator = FragilityCalculator(
        neo4j_service,
        memory_index,
        normalized_edges,
        semantic_analyzer,
    )
    bidirectional_analyzer = BidirectionalAnalyzer(
        taint_propagator,
        symbol_resolver,
        side_effect_detector,
        fragility_calculator,
        impact_engine,
    )
    contract_break_detector = ContractBreakDetector(neo4j_service, memory_nodes)
    data_flow_tracker = DataFlowTracker(neo4j_service, memory_nodes, normalized_edges)

    return {
        "memory_index": memory_index,
        "semantic_analyzer": semantic_analyzer,
        "impact_engine": impact_engine,
        "taint_propagator": taint_propagator,
        "symbol_resolver": symbol_resolver,
        "side_effect_detector": side_effect_detector,
        "fragility_calculator": fragility_calculator,
        "bidirectional_analyzer": bidirectional_analyzer,
        "contract_break_detector": contract_break_detector,
        "data_flow_tracker": data_flow_tracker,
    }


def _compute_call_resolution_summary(project: str | None = None, top_n: int = 20) -> dict:
    """Compute CALLS resolution quality summary for current in-memory graph."""
    _ensure_memory_graph_loaded()
    node_by_key = {n.get("namespace_key"): n for n in memory_nodes if n.get("namespace_key")}

    def _method_hint_from_call(edge: dict) -> str:
        hint = str(edge.get("target_method_hint") or "").strip()
        if hint:
            return hint
        raw = str(edge.get("target") or edge.get("to") or "")
        tail = raw.split(":")[-1] if raw else ""
        return (tail.split(".")[-1] if tail else "").strip()

    calls = [e for e in memory_edges if e.get("type") == "CALLS"]
    resolved = [e for e in memory_edges if e.get("type") == "CALLS_RESOLVED"]

    if project:
        calls = [
            e for e in calls
            if (node_by_key.get(e.get("source"), {}) or {}).get("project") == project
        ]
        resolved = [
            e for e in resolved
            if (node_by_key.get(e.get("source"), {}) or {}).get("project") == project
        ]

    resolved_hints_by_src: dict[str, set[str]] = defaultdict(set)
    for e in resolved:
        src = e.get("source") or e.get("from")
        dst = e.get("target") or e.get("to")
        if not src or not dst:
            continue
        dst_node = node_by_key.get(dst) or {}
        name = str(dst_node.get("name") or "").strip()
        if name:
            resolved_hints_by_src[src].add(name)

    unresolved_items: list[dict] = []
    unresolved_groups: dict[tuple[str, str], dict] = {}
    by_project: dict[str, dict] = {}

    resolved_count = 0
    for call in calls:
        src = call.get("source") or call.get("from")
        if not src:
            continue
        src_node = node_by_key.get(src) or {}
        src_project = str(src_node.get("project") or "unknown")
        method_hint = _method_hint_from_call(call)
        owner_hint = str(call.get("target_owner_hint") or "").strip()

        proj = by_project.setdefault(src_project, {"total_calls": 0, "resolved_calls": 0})
        proj["total_calls"] += 1

        is_resolved = bool(method_hint and method_hint in resolved_hints_by_src.get(src, set()))
        if is_resolved:
            resolved_count += 1
            proj["resolved_calls"] += 1
            continue

        unresolved_items.append(call)
        key = (owner_hint or "-", method_hint or "<unknown>")
        bucket = unresolved_groups.setdefault(
            key,
            {"owner_hint": owner_hint or None, "method_hint": method_hint or "<unknown>", "count": 0, "examples": []},
        )
        bucket["count"] += 1
        if len(bucket["examples"]) < 5:
            bucket["examples"].append({
                "source": src,
                "source_name": src_node.get("name"),
                "source_file": src_node.get("file"),
                "source_project": src_project,
            })

    total_calls = len(calls)
    unresolved_count = total_calls - resolved_count
    rate = (resolved_count / total_calls * 100.0) if total_calls else 0.0

    by_project_rows = []
    for project_name, vals in by_project.items():
        p_total = int(vals.get("total_calls", 0))
        p_res = int(vals.get("resolved_calls", 0))
        p_unres = max(0, p_total - p_res)
        p_rate = (p_res / p_total * 100.0) if p_total else 0.0
        by_project_rows.append({
            "project": project_name,
            "total_calls": p_total,
            "resolved_calls": p_res,
            "unresolved_calls": p_unres,
            "resolution_rate": round(p_rate, 2),
        })
    by_project_rows.sort(key=lambda x: x["resolution_rate"])

    top_unresolved = sorted(unresolved_groups.values(), key=lambda x: x["count"], reverse=True)[: max(1, min(top_n, 100))]

    return {
        "total_calls": total_calls,
        "resolved_calls": resolved_count,
        "unresolved_calls": unresolved_count,
        "resolution_rate": round(rate, 2),
        "by_project": by_project_rows,
        "top_unresolved": top_unresolved,
    }


def _source_snippets_for_keys(keys: list[str], memory_index: dict[str, dict]) -> dict[str, str]:
    """Collect source snippets by node key for semantic impact analysis."""
    snippets: dict[str, str] = {}
    for key in keys:
        node = memory_index.get(key, {})
        props = node.get("properties", {})
        source = props.get("source_code") or props.get("source") or ""
        if source:
            snippets[key] = source
    return snippets


def _node_text_blob(node: dict) -> str:
    parts = [
        str(node.get("namespace_key", "")),
        str(node.get("name", "")),
        " ".join(node.get("labels", []) if isinstance(node.get("labels"), list) else []),
        str(node.get("layer", "")),
        str(node.get("file", "")),
        str(node.get("decorators", "")),
        str(node.get("route_path", "")),
    ]
    return " ".join(parts).lower()


def _save_rag_index() -> None:
    """Persist current in-memory RAG index to disk."""
    global rag_index_metadata
    try:
        payload = {
            "model": OLLAMA_EMBED_MODEL,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "entries": rag_index,
            "node_count": len(memory_nodes),
            "edge_count": len(memory_edges),
        }
        RAG_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RAG_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        rag_index_metadata = {
            "loaded": True,
            "model": OLLAMA_EMBED_MODEL,
            "generated_at": payload["generated_at"],
            "entries": len(rag_index),
            "path": str(RAG_INDEX_FILE),
        }
    except Exception as e:
        logger.warning("Failed to persist RAG index: %s", e)


def _load_rag_index() -> int:
    """Load RAG index from disk if available."""
    global rag_index, rag_index_metadata
    if not RAG_INDEX_FILE.exists():
        rag_index_metadata = {"loaded": False, "reason": "not_found", "path": str(RAG_INDEX_FILE)}
        return 0
    try:
        with open(RAG_INDEX_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        entries = payload.get("entries") if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            rag_index = []
            rag_index_metadata = {"loaded": False, "reason": "invalid_format", "path": str(RAG_INDEX_FILE)}
            return 0
        rag_index = [e for e in entries if isinstance(e, dict) and e.get("key") and e.get("blob") is not None]
        rag_index_metadata = {
            "loaded": True,
            "path": str(RAG_INDEX_FILE),
            "model": payload.get("model") if isinstance(payload, dict) else None,
            "generated_at": payload.get("generated_at") if isinstance(payload, dict) else None,
            "entries": len(rag_index),
        }
        return len(rag_index)
    except Exception as e:
        rag_index = []
        rag_index_metadata = {"loaded": False, "reason": str(e), "path": str(RAG_INDEX_FILE)}
        logger.warning("Failed to load RAG index: %s", e)
        return 0


def _is_rag_index_stale() -> bool:
    """Detect if RAG index likely mismatches current in-memory graph."""
    if not rag_index:
        return True
    node_keys = {n.get("namespace_key") for n in memory_nodes if n.get("namespace_key")}
    index_keys = {e.get("key") for e in rag_index if e.get("key")}
    if not node_keys:
        return False
    if not index_keys:
        return True
    missing_ratio = len(node_keys - index_keys) / max(1, len(node_keys))
    return missing_ratio > 0.15


def _vector_dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _vector_norm(a: list[float]) -> float:
    return (_vector_dot(a, a) ** 0.5) or 1.0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return _vector_dot(a, b) / (_vector_norm(a) * _vector_norm(b))


def _embed_text(text: str) -> Optional[list[float]]:
    """Get embedding from Ollama local API; returns None on any failure."""
    if not text.strip():
        return None
    try:
        payload = {"model": OLLAMA_EMBED_MODEL, "prompt": text}
        with httpx.Client(timeout=8.0) as client:
            res = client.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
            if res.status_code != 200:
                return None
            data = res.json()
            emb = data.get("embedding")
            if isinstance(emb, list) and emb:
                return [float(x) for x in emb]
    except Exception:
        return None
    return None


def _rag_search_nodes(
    question: str,
    node_key: str | None = None,
    limit: int = 20,
    use_semantic: bool = True,
) -> list[dict]:
    """Hybrid RAG retrieval (lexical + optional embedding similarity)."""
    _ensure_memory_graph_loaded()
    q_tokens = [t for t in question.lower().split() if len(t) >= 3]
    if not q_tokens and not question.strip():
        return []

    neighborhood = set()
    if node_key:
        neighborhood.add(node_key)
        for e in memory_edges:
            if e.get("source") == node_key:
                neighborhood.add(e.get("target"))
            if e.get("target") == node_key:
                neighborhood.add(e.get("source"))

    if not rag_index:
        _load_rag_index()
    if not rag_index or _is_rag_index_stale():
        _rebuild_rag_index(include_embeddings=False, persist=True)
    blob_by_key = {entry["key"]: entry["blob"] for entry in rag_index}
    entry_by_key = {entry["key"]: entry for entry in rag_index}

    q_emb = _embed_text(question) if use_semantic else None
    scored: list[tuple[float, dict]] = []
    for node in memory_nodes:
        key = node.get("namespace_key")
        if not key:
            continue
        index_entry = entry_by_key.get(key)
        blob = blob_by_key.get(key, "")
        if not blob:
            continue
        lexical_score = 0.0
        for tok in q_tokens:
            if tok in blob:
                lexical_score += 1.0
        semantic_score = 0.0
        if q_emb and index_entry and isinstance(index_entry.get("embedding"), list):
            semantic_score = max(0.0, _cosine_similarity(q_emb, index_entry["embedding"]))

        score = lexical_score + (semantic_score * 3.0)
        if score <= 0:
            continue
        if node_key and node.get("namespace_key") in neighborhood:
            score += 1.5
        if node.get("hotspot_score"):
            score += min(2.0, float(node.get("hotspot_score", 0.0)) / 50.0)
        scored.append((score, node))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(n) for _, n in scored[:limit]]


def _format_rag_context(nodes: list[dict]) -> str:
    lines = []
    for n in nodes:
        lines.append(
            f"[{n.get('label', '')}] {n.get('name', '')} | key={n.get('namespace_key', '')} | "
            f"layer={n.get('layer', '')} | file={n.get('file', '')} | "
            f"complexity={n.get('complexity', 0)} | hotspot={n.get('hotspot_score', 0)}"
        )
    return "\n".join(lines)


def _rebuild_rag_index(include_embeddings: bool = False, persist: bool = True) -> int:
    """Rebuild in-memory RAG index with optional embeddings."""
    global rag_index
    _ensure_memory_graph_loaded()
    rag_index = []
    for n in memory_nodes:
        key = n.get("namespace_key")
        if not key:
            continue
        blob = _node_text_blob(n)
        rag_index.append({
            "key": key,
            "blob": blob,
            "embedding": _embed_text(blob) if include_embeddings else None,
        })
    if persist:
        _save_rag_index()
    return len(rag_index)


def _ck_risk_score(node: dict) -> float:
    """Compute a normalized CK risk score from stored CK metrics."""
    wmc = float(node.get("wmc", 0) or 0)
    cbo = float(node.get("cbo", 0) or 0)
    rfc = float(node.get("rfc", 0) or 0)
    lcom = float(node.get("lcom", 0.0) or 0.0)
    raw = (wmc * 1.6) + (cbo * 2.2) + (rfc * 0.5) + (lcom * 20.0)
    return round(min(100.0, max(0.0, raw / 3.0)), 2)


@app.post("/api/impact/analyze")
async def analyze_impact(request: dict):
    """Run structured impact analysis and optional semantic summary."""
    runtime = _build_analysis_runtime()
    impact_engine = runtime["impact_engine"]
    semantic_analyzer = runtime["semantic_analyzer"]
    memory_index = runtime["memory_index"]

    try:
        change = ChangeDescriptor(
            change_type=request.get("change_type", ""),
            target_key=request.get("target_key", ""),
            parameter_name=request.get("parameter_name"),
            old_type=request.get("old_type"),
            new_type=request.get("new_type"),
            max_depth=int(request.get("max_depth", 5) or 5),
        )
        if not change.target_key:
            raise HTTPException(status_code=400, detail="target_key is required")

        affected_set = impact_engine.analyze(change)
        snippets = _source_snippets_for_keys(
            [item.namespace_key for item in affected_set.items[:50]],
            memory_index,
        )
        semantic = await semantic_analyzer.analyze_impact(change, affected_set, snippets)

        payload = asdict(affected_set)
        payload["semantic_analysis"] = asdict(semantic) if semantic else None
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Impact analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dataflow/{node_key:path}")
async def get_data_flow(node_key: str):
    """Trace field/column propagation toward frontend layers."""
    runtime = _build_analysis_runtime()
    tracker = runtime["data_flow_tracker"]
    try:
        return asdict(tracker.trace_column_to_frontend(node_key))
    except Exception as e:
        logger.error("DataFlow tracking failed for %s: %s", node_key, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contracts/broken")
async def get_contract_breaks():
    """Return all contract breaks detected by signature hash changes."""
    runtime = _build_analysis_runtime()
    detector = runtime["contract_break_detector"]
    try:
        return {"broken_contracts": detector.get_all_broken()}
    except Exception as e:
        logger.error("Contract break listing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/method/{node_key:path}/usages")
async def get_method_usages(node_key: str):
    """Return callers/callees and nearby chain details for a method/function node."""
    _ensure_memory_graph_loaded()
    node_map = {n.get("namespace_key"): n for n in memory_nodes if n.get("namespace_key")}
    callers = []
    callees = []
    rel_types = {"CALLS_RESOLVED", "CALLS", "CALLS_NHOP"}
    for e in memory_edges:
        if e.get("type") not in rel_types:
            continue
        src = e.get("source")
        tgt = e.get("target")
        if tgt == node_key and src in node_map:
            src_node = node_map[src]
            callers.append({
                "key": src,
                "name": src_node.get("name"),
                "file": src_node.get("file"),
                "layer": src_node.get("layer"),
                "type": e.get("type"),
                "confidence_score": e.get("confidence_score"),
                "hop_distance": e.get("hop_distance"),
            })
        if src == node_key and tgt in node_map:
            tgt_node = node_map[tgt]
            callees.append({
                "key": tgt,
                "name": tgt_node.get("name"),
                "file": tgt_node.get("file"),
                "layer": tgt_node.get("layer"),
                "type": e.get("type"),
                "confidence_score": e.get("confidence_score"),
                "hop_distance": e.get("hop_distance"),
            })
    return {
        "node_key": node_key,
        "callers": callers[:500],
        "callees": callees[:500],
        "total_callers": len(callers),
        "total_callees": len(callees),
    }


@app.get("/api/hotspots")
async def get_hotspots(top_n: int = 50, days: int | None = None):
    """Return nodes ranked by hotspot score (complexity * churn)."""
    _ensure_memory_graph_loaded()
    # Fast path: use stored score from latest scan
    if not days or days <= 0:
        scored = [
            n for n in memory_nodes
            if (n.get("hotspot_score") is not None) and float(n.get("hotspot_score", 0)) > 0
        ]
        scored.sort(key=lambda n: float(n.get("hotspot_score", 0)), reverse=True)
        return {"hotspots": scored[: max(1, min(top_n, 500))], "window_days": None}

    # Temporal window: recompute churn from git history by project
    churn_cache: dict[str, dict[str, int]] = {}
    hotspots = []
    for node in memory_nodes:
        project = str(node.get("project", "") or "")
        rel_file = str(node.get("file", "") or "").replace("\\", "/")
        if not project or not rel_file:
            continue
        if project not in churn_cache:
            project_path = scanned_projects.get(project, "")
            churn_cache[project] = _compute_git_churn(project_path, days=days) if project_path else {}
        churn = int(churn_cache[project].get(rel_file, 0))
        complexity = int(node.get("complexity", 1) or 1)
        hotspot_score = min(100.0, float(complexity * max(1, churn)))
        category = "critical" if hotspot_score >= 80 else ("danger" if hotspot_score >= 50 else ("watch" if hotspot_score >= 25 else "low"))
        hotspots.append({
            **node,
            "git_churn": churn,
            "hotspot_score": round(hotspot_score, 2),
            "category": category,
        })

    hotspots.sort(key=lambda n: float(n.get("hotspot_score", 0) or 0), reverse=True)
    return {"hotspots": hotspots[: max(1, min(top_n, 500))], "window_days": days}


@app.get("/api/hotspots/cochange")
async def get_hotspots_cochange(days: int = 90, top_n: int = 30):
    """Return most frequent co-change file pairs per scanned project."""
    result = {}
    for project, path in scanned_projects.items():
        if not path:
            continue
        result[project] = _compute_git_cochange_pairs(path, days=days, top_n=top_n)
    return {"projects": result, "window_days": days}


@app.get("/api/calls/resolution")
async def get_call_resolution(project: str | None = None, top_n: int = 20):
    """Return diagnostics for CALLS -> CALLS_RESOLVED quality."""
    try:
        return _compute_call_resolution_summary(project=project, top_n=top_n)
    except Exception as e:
        logger.error("Call resolution summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/metrics/ck")
async def get_ck_metrics(project: str | None = None, min_risk: float = 0.0):
    """Return CK metrics for class-like nodes with optional filters."""
    _ensure_memory_graph_loaded()
    class_nodes = [
        dict(n) for n in memory_nodes
        if n.get("label") in ("Java_Class", "TS_Component")
    ]
    if project:
        class_nodes = [n for n in class_nodes if n.get("project") == project]

    results = []
    for n in class_nodes:
        risk = _ck_risk_score(n)
        if risk < float(min_risk):
            continue
        results.append({
            "namespace_key": n.get("namespace_key"),
            "class_name": n.get("name"),
            "project": n.get("project"),
            "file": n.get("file"),
            "layer": n.get("layer"),
            "wmc": int(n.get("wmc", 0) or 0),
            "cbo": int(n.get("cbo", 0) or 0),
            "rfc": int(n.get("rfc", 0) or 0),
            "lcom": float(n.get("lcom", 0.0) or 0.0),
            "risk_score": risk,
            "is_god_class": bool((n.get("wmc", 0) or 0) > 20 and (n.get("cbo", 0) or 0) > 10),
            "hotspot_score": float(n.get("hotspot_score", 0) or 0),
        })

    results.sort(key=lambda r: r["risk_score"], reverse=True)
    return {"metrics": results, "total": len(results)}


@app.get("/api/rag/search")
async def rag_search(q: str, node_key: str | None = None, limit: int = 20, semantic: bool = True):
    """Search relevant graph nodes for a free-text query (hybrid lexical/semantic)."""
    return {
        "nodes": _rag_search_nodes(
            q,
            node_key=node_key,
            limit=max(1, min(limit, 100)),
            use_semantic=semantic,
        )
    }


@app.post("/api/rag/index")
async def rag_reindex(request: dict | None = None):
    """Force rebuild of in-memory RAG index with optional embeddings."""
    request = request or {}
    include_embeddings = bool(request.get("include_embeddings", False))
    count = _rebuild_rag_index(include_embeddings=include_embeddings)
    return {
        "indexed_nodes": count,
        "status": "ok",
        "include_embeddings": include_embeddings,
        "embedding_model": OLLAMA_EMBED_MODEL if include_embeddings else None,
    }


@app.get("/api/rag/status")
async def rag_status():
    """Return runtime and persisted status for local RAG index."""
    _ensure_memory_graph_loaded()
    if not rag_index:
        _load_rag_index()
    has_embeddings = sum(1 for e in rag_index if isinstance(e.get("embedding"), list) and e.get("embedding"))
    return {
        "entries": len(rag_index),
        "with_embeddings": has_embeddings,
        "embedding_coverage": round((has_embeddings / max(1, len(rag_index))) * 100.0, 2),
        "stale": _is_rag_index_stale(),
        "embed_model": OLLAMA_EMBED_MODEL,
        "index_file": str(RAG_INDEX_FILE),
        "metadata": rag_index_metadata,
    }


@app.get("/api/graph/search")
async def semantic_graph_search(
    q: str,
    top_k: int = 20,
    node_key: str | None = None,
    semantic: bool = True,
):
    """Semantic graph search endpoint compatible with roadmap naming."""
    nodes = _rag_search_nodes(
        q,
        node_key=node_key,
        limit=max(1, min(top_k, 100)),
        use_semantic=semantic,
    )
    results = []
    for n in nodes:
        results.append({
            "key": n.get("namespace_key"),
            "name": n.get("name"),
            "layer": n.get("layer"),
            "project": n.get("project"),
            "file": n.get("file"),
            "labels": n.get("labels", []),
            "hotspot_score": n.get("hotspot_score", 0),
        })
    return {"results": results, "query": q}


@app.get("/api/fields/{node_key:path}")
async def get_field_nodes(node_key: str):
    """Return HAS_FIELD/HAS_PARAMETER children for a node."""
    if neo4j_service.is_connected:
        try:
            query = """
            MATCH (p:Entity {namespace_key: $key})-[r:HAS_FIELD|HAS_PARAMETER]->(f:Entity)
            RETURN f, type(r) AS rel_type
            LIMIT 500
            """
            rows = neo4j_service.graph.run(query, key=node_key).data()
            field_nodes = []
            for row in rows:
                node = dict(row["f"])
                node["labels"] = list(row["f"].labels)
                node["relationship_type"] = row["rel_type"]
                field_nodes.append(node)
            return {"field_nodes": field_nodes}
        except Exception as e:
            logger.warning("Neo4j field node query failed, using memory: %s", e)

    _ensure_memory_graph_loaded()
    node_map = {n.get("namespace_key"): n for n in memory_nodes if n.get("namespace_key")}
    field_nodes = []
    for edge in _normalized_memory_edges():
        if edge["source"] != node_key:
            continue
        if edge["type"] not in {"HAS_FIELD", "HAS_PARAMETER"}:
            continue
        target = node_map.get(edge["target"])
        if target:
            node = dict(target)
            node["relationship_type"] = edge["type"]
            field_nodes.append(node)
    return {"field_nodes": field_nodes}


@app.get("/api/fragility/{node_key:path}")
async def get_fragility(node_key: str):
    """Calculate and return fragility detail for a node."""
    runtime = _build_analysis_runtime()
    calculator = runtime["fragility_calculator"]
    try:
        detail = await calculator.calculate(node_key)
        return asdict(detail)
    except Exception as e:
        logger.error("Fragility calculation failed for %s: %s", node_key, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fragility/ranking")
async def get_fragility_ranking(top_n: int = 20):
    """Return top-N fragility ranking."""
    runtime = _build_analysis_runtime()
    calculator = runtime["fragility_calculator"]
    try:
        ranking = calculator.get_ranking(top_n=top_n)
        if not ranking:
            await calculator.calculate_all()
            ranking = calculator.get_ranking(top_n=top_n)
        return [asdict(item) for item in ranking]
    except Exception as e:
        logger.error("Fragility ranking failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/taint/propagate")
async def propagate_taint(request: dict):
    """Run taint propagation from an origin key."""
    runtime = _build_analysis_runtime()
    propagator = runtime["taint_propagator"]
    try:
        origin_key = request.get("origin_key", "")
        if not origin_key:
            raise HTTPException(status_code=400, detail="origin_key is required")
        taint_path = propagator.propagate(
            origin_key=origin_key,
            change_type=request.get("change_type", ""),
            old_type=request.get("old_type", "") or "",
            new_type=request.get("new_type", "") or "",
        )
        return asdict(taint_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Taint propagation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/symbol/resolve")
async def resolve_symbol(name: str, context_key: str = ""):
    """Resolve symbols by name with optional context key prioritization."""
    runtime = _build_analysis_runtime()
    resolver = runtime["symbol_resolver"]
    try:
        return [asdict(item) for item in resolver.resolve(name=name, context_key=context_key)]
    except Exception as e:
        logger.error("Symbol resolution failed for %s: %s", name, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/side-effects/detect")
async def detect_side_effects(request: dict):
    """Detect side effects for a change over an affected set."""
    runtime = _build_analysis_runtime()
    detector = runtime["side_effect_detector"]
    impact_engine = runtime["impact_engine"]
    try:
        change = dict(request.get("change") or request)
        target_key = change.get("target_key") or change.get("artifact_key")
        if target_key and not change.get("artifact_key"):
            change["artifact_key"] = target_key

        affected_set = list(request.get("affected_set") or [])
        if not affected_set and target_key:
            descriptor = ChangeDescriptor(
                change_type=change.get("change_type", "change_method_signature"),
                target_key=target_key,
                parameter_name=change.get("parameter_name"),
                old_type=change.get("old_type"),
                new_type=change.get("new_type"),
                max_depth=int(change.get("max_depth", 5) or 5),
            )
            impact = impact_engine.analyze(descriptor)
            affected_set = [item.namespace_key for item in impact.items]

        results = await detector.detect(change=change, affected_set=affected_set)
        return [asdict(item) for item in results]
    except Exception as e:
        logger.error("Side effect detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bidirectional/analyze")
async def analyze_bidirectional(request: dict):
    """Run bidirectional propagation analysis."""
    runtime = _build_analysis_runtime()
    analyzer = runtime["bidirectional_analyzer"]
    try:
        origin_key = request.get("origin_key", "")
        if not origin_key:
            raise HTTPException(status_code=400, detail="origin_key is required")
        direction = str(request.get("direction", "BOTTOM_UP")).upper()
        if direction not in {"BOTTOM_UP", "TOP_DOWN"}:
            raise HTTPException(status_code=400, detail="direction must be BOTTOM_UP or TOP_DOWN")
        result = await analyzer.analyze(
            origin_key=origin_key,
            direction=direction,
            change=request.get("change"),
        )
        return asdict(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bidirectional analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/security/node/{node_key:path}/vulnerabilities")
async def get_node_vulnerabilities(node_key: str):
    """Return CodeQL vulnerabilities linked to a node."""
    if neo4j_service.is_connected:
        try:
            direct_query = """
            MATCH (e:Entity {namespace_key: $key})-[:HAS_VULNERABILITY]->(s:SecurityIssue)
            RETURN
              s.rule_id AS rule_id,
              coalesce(s.severity, 'note') AS severity,
              coalesce(s.message, '') AS message,
              coalesce(s.file, '') AS file_path,
              coalesce(s.start_line, 0) AS start_line,
              coalesce(s.end_line, 0) AS end_line
            LIMIT 200
            """
            rows = neo4j_service.graph.run(direct_query, key=node_key).data()
            if rows:
                return [{**row, "entity_key": node_key} for row in rows]

            fallback_query = """
            MATCH (e:Entity {namespace_key: $key})
            WHERE e.file IS NOT NULL
            MATCH (s:SecurityIssue)
            WHERE s.file = e.file
            RETURN
              s.rule_id AS rule_id,
              coalesce(s.severity, 'note') AS severity,
              coalesce(s.message, '') AS message,
              coalesce(s.file, '') AS file_path,
              coalesce(s.start_line, 0) AS start_line,
              coalesce(s.end_line, 0) AS end_line
            LIMIT 200
            """
            rows = neo4j_service.graph.run(fallback_query, key=node_key).data()
            return [{**row, "entity_key": node_key} for row in rows]
        except Exception as e:
            logger.warning("Security vulnerability query failed: %s", e)

    # Memory fallback (best effort from heuristic flags)
    _ensure_memory_graph_loaded()
    node = next((n for n in memory_nodes if n.get("namespace_key") == node_key), None)
    if not node:
        return []

    issues = []
    if node.get("hardcoded_secret"):
        issues.append({
            "rule_id": "hardcoded-secret",
            "severity": "error",
            "message": "Potential hardcoded secret detected.",
            "file_path": node.get("file", ""),
            "start_line": int(node.get("start_line", 0) or 0),
            "end_line": int(node.get("end_line", 0) or 0),
            "entity_key": node_key,
        })
    if node.get("sql_injection_risk"):
        issues.append({
            "rule_id": "sql-injection-risk",
            "severity": "warning",
            "message": "Potential SQL injection risk inferred.",
            "file_path": node.get("file", ""),
            "start_line": int(node.get("start_line", 0) or 0),
            "end_line": int(node.get("end_line", 0) or 0),
            "entity_key": node_key,
        })
    return issues


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


@app.delete("/api/projects/{project_name}")
async def delete_project(project_name: str):
    """Delete a project's nodes from Neo4j (if connected) and clean in-memory graph."""
    global memory_nodes, memory_edges

    # Delete from Neo4j if available
    if neo4j_service.is_connected:
        try:
            neo4j_service.graph.run(
                "MATCH (n:Entity {project: $project_name}) DETACH DELETE n",
                project_name=project_name,
            )
        except Exception as e:
            logger.error("Failed to delete project nodes from Neo4j: %s", e)

    # Clean in-memory graph
    before_nodes = len(memory_nodes)
    memory_nodes = [n for n in memory_nodes if n.get("project") != project_name]
    removed_keys = {n["namespace_key"] for n in memory_nodes}
    before_edges = len(memory_edges)
    memory_edges = [e for e in memory_edges if e["source"] in removed_keys and e["target"] in removed_keys]

    return {
        "project": project_name,
        "nodes_removed": before_nodes - len(memory_nodes),
        "edges_removed": before_edges - len(memory_edges),
    }


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
    antipatterns = {
        "circular_dependencies": [],
        "god_classes": [],
        "dead_code": [],
        "cloud_blockers": [],
        "hardcoded_secrets": [],
        "swallowed_exceptions": [],
        "fat_controllers": [],
        "top_external_deps": [],
        "untested_critical_code": [],
        "architecture_violations": [],
        "n_plus_one_risk": [],
        "sql_injection_risk": [],
        "compliance_violations": []
    }

    if not neo4j_service.is_connected:
        # Fallback: compute antipatterns from in-memory graph
        nodes_by_key = {n["namespace_key"]: n for n in memory_nodes}
        out_degree: dict[str, int] = {}
        in_degree: dict[str, int] = {}

        for e in memory_edges:
            src = e.get("source")
            tgt = e.get("target")
            if src:
                out_degree[src] = out_degree.get(src, 0) + 1
            if tgt:
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        # 1. God Classes: high degree OR complex
        god_classes = []
        for n in memory_nodes:
            key = n.get("namespace_key")
            if not key:
                continue
            complexity = n.get("complexity") or 0
            deg = (out_degree.get(key, 0) + in_degree.get(key, 0))
            if deg > 15 or complexity > 20:
                god_classes.append({
                    "key": key,
                    "name": n.get("name"),
                    "layer": n.get("layer"),
                    "out_degree": out_degree.get(key, 0),
                    "in_degree": in_degree.get(key, 0),
                    "complexity": complexity,
                })
        antipatterns["god_classes"] = god_classes

        # 2. Dead Code: no incoming edges, ignore Frontend/API
        excluded_names = {"main", "App", "index"}
        dead_code = []
        for n in memory_nodes:
            key = n.get("namespace_key")
            if not key:
                continue
            layer = n.get("layer")
            name = (n.get("name") or "")
            if in_degree.get(key, 0) == 0 and layer not in ("API", "Frontend") and name not in excluded_names:
                dead_code.append({
                    "key": key,
                    "name": name,
                    "layer": layer,
                    "file": n.get("file"),
                })
        antipatterns["dead_code"] = dead_code

        # 3. Cloud Blockers
        antipatterns["cloud_blockers"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
            }
            for n in memory_nodes
            if n.get("cloud_blocker")
        ]

        # 4. Hardcoded Secrets
        antipatterns["hardcoded_secrets"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
            }
            for n in memory_nodes
            if n.get("hardcoded_secret")
        ]

        # 5. Fat Controllers (API layer high complexity)
        fat_controllers = []
        for n in memory_nodes:
            if n.get("layer") == "API" and (n.get("complexity") or 0) > 10:
                key = n.get("namespace_key")
                fat_controllers.append({
                    "key": key,
                    "name": n.get("name"),
                    "layer": n.get("layer"),
                    "complexity": n.get("complexity"),
                    "out_degree": out_degree.get(key, 0),
                    "in_degree": in_degree.get(key, 0),
                })
        antipatterns["fat_controllers"] = fat_controllers

        # Preserve existing fallbacks for other categories
        antipatterns["untested_critical_code"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "complexity": n.get("complexity"),
            }
            for n in memory_nodes
            if n.get("missing_tests") and (n.get("complexity") or 0) > 5
        ]
        antipatterns["swallowed_exceptions"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
            }
            for n in memory_nodes
            if n.get("swallowed_exception")
        ]

        # Architecture violations (Frontend -> Database/Service, API -> Database)
        violations = []
        for e in memory_edges:
            src = nodes_by_key.get(e.get("source"))
            tgt = nodes_by_key.get(e.get("target"))
            if not src or not tgt:
                continue
            if e.get("type") not in ("CALLS", "IMPORTS"):
                continue
            src_layer = src.get("layer")
            tgt_layer = tgt.get("layer")
            if src_layer == "Frontend" and tgt_layer in ("Database", "Service"):
                violations.append({
                    "source": src.get("namespace_key"),
                    "source_name": src.get("name"),
                    "source_layer": src_layer,
                    "target": tgt.get("namespace_key"),
                    "target_name": tgt.get("name"),
                    "target_layer": tgt_layer,
                    "relation": e.get("type"),
                })
            if src_layer == "API" and tgt_layer == "Database":
                violations.append({
                    "source": src.get("namespace_key"),
                    "source_name": src.get("name"),
                    "source_layer": src_layer,
                    "target": tgt.get("namespace_key"),
                    "target_name": tgt.get("name"),
                    "target_layer": tgt_layer,
                    "relation": e.get("type"),
                })
        antipatterns["architecture_violations"] = violations

        antipatterns["n_plus_one_risk"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
            }
            for n in memory_nodes
            if n.get("n_plus_one_risk")
        ]

        antipatterns["sql_injection_risk"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
            }
            for n in memory_nodes
            if n.get("sql_injection_risk")
        ]

        antipatterns["compliance_violations"] = [
            {
                "key": n["namespace_key"],
                "name": n.get("name"),
                "layer": n.get("layer"),
                "file": n.get("file"),
                "leaked_data": n.get("leaked_data", [])
            }
            for n in memory_nodes
            if n.get("compliance_violation")
        ]

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

        # 4. Cloud Blockers (Disk I/O detected)
        cloud_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.cloud_blocker, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 100
        """
        cloud_res = neo4j_service.graph.run(cloud_query).data()
        antipatterns["cloud_blockers"] = cloud_res

        # 5. Hardcoded Secrets (Sensitive variables with literal assignments)
        secrets_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.hardcoded_secret, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 100
        """
        secrets_res = neo4j_service.graph.run(secrets_query).data()
        antipatterns["hardcoded_secrets"] = secrets_res

        # 6. Untested Critical Code (missing tests with high complexity)
        untested_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.missing_tests, false) = true AND coalesce(n.complexity, 0) > 5
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.complexity, 0) AS complexity, coalesce(n.file, '') AS file
        LIMIT 100
        """
        untested_res = neo4j_service.graph.run(untested_query).data()
        antipatterns["untested_critical_code"] = untested_res

        # 7. Swallowed Exceptions (empty catch blocks)
        swallowed_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.swallowed_exception, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 100
        """
        swallowed_res = neo4j_service.graph.run(swallowed_query).data()
        antipatterns["swallowed_exceptions"] = swallowed_res

        # 8. Fat Controllers (API layer with high complexity)
        fat_query = """
        MATCH (n:Entity)
        WHERE n.layer = 'API' AND coalesce(n.complexity, 0) > 10
        OPTIONAL MATCH (n)-[r_out]->()
        OPTIONAL MATCH ()-[r_in]->(n)
        WITH n, count(DISTINCT r_out) AS out_degree, count(DISTINCT r_in) AS in_degree
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, 
               coalesce(n.complexity, 0) AS complexity, out_degree, in_degree
        ORDER BY coalesce(n.complexity, 0) DESC
        LIMIT 50
        """
        fat_res = neo4j_service.graph.run(fat_query).data()
        antipatterns["fat_controllers"] = fat_res

        # 7. Top 5 External Dependencies (Most imported packages)
        deps_query = """
        MATCH ()-[r:IMPORTS]->(dep:External_Dependency)
        RETURN dep.name AS package_name, count(*) AS usage_count
        ORDER BY usage_count DESC
        LIMIT 5
        """
        deps_res = neo4j_service.graph.run(deps_query).data()
        antipatterns["top_external_deps"] = deps_res

        # 8. Architecture violations (Frontend -> Database/Service, API -> Database)
        arch_query = """
        MATCH (a:Entity)-[r]->(b:Entity)
        WHERE type(r) IN ['CALLS', 'IMPORTS']
          AND (
              (a.layer = 'Frontend' AND b.layer IN ['Database', 'Service'])
              OR (a.layer = 'API' AND b.layer = 'Database')
          )
        RETURN a.namespace_key AS source, a.name AS source_name, a.layer AS source_layer,
               b.namespace_key AS target, b.name AS target_name, b.layer AS target_layer,
               type(r) AS relation
        LIMIT 200
        """
        arch_res = neo4j_service.graph.run(arch_query).data()
        antipatterns["architecture_violations"] = arch_res

        # 9. N+1 Query Risks
        nplus_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.n_plus_one_risk, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 200
        """
        nplus_res = neo4j_service.graph.run(nplus_query).data()
        antipatterns["n_plus_one_risk"] = nplus_res

        # 10. SQL Injection Risks
        sql_inj_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.sql_injection_risk, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file
        LIMIT 200
        """
        sql_inj_res = neo4j_service.graph.run(sql_inj_query).data()
        antipatterns["sql_injection_risk"] = sql_inj_res

        # 11. Compliance Violations
        compliance_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.compliance_violation, false) = true
        RETURN n.namespace_key AS key, n.name AS name, n.layer AS layer, coalesce(n.file, '') AS file, coalesce(n.leaked_data, []) AS leaked_data
        LIMIT 200
        """
        compliance_res = neo4j_service.graph.run(compliance_query).data()
        antipatterns["compliance_violations"] = compliance_res

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
        logger.info("Fetching graph context for question with RAG retrieval...")
        if neo4j_service.is_connected:
            base_context = neo4j_service.get_graph_context(
                node_key=request.context_node,
                limit=15,
            )
        else:
            logger.info("Neo4j offline, using in-memory context fallback.")
            base_context = get_memory_graph_context(
                node_key=request.context_node,
                limit=15,
            )

        rag_nodes = _rag_search_nodes(
            request.question,
            node_key=request.context_node,
            limit=20,
        )
        rag_context = _format_rag_context(rag_nodes)
        context = base_context
        if rag_context.strip():
            context = f"{base_context}\n\n=== RAG Context (Top Relevant Nodes) ===\n{rag_context}"
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
            nodes[dk]["impact_distance"] = 0
            
    # Find impacted nodes recursively (Bi-directional BFS) and record impact distance
    # The user wants "everything" impacted if a root node is deleted.
    # We follow all edges in both directions to show system-wide reachability impact.
    adj: dict[str, set[str]] = {}
    for edge in edges:
        adj.setdefault(edge["source"], set()).add(edge["target"])
        adj.setdefault(edge["target"], set()).add(edge["source"])

    distances: dict[str, int] = {}
    visited = set(deleted_set)
    queue: list[tuple[str, int]] = []

    # Seed first-level impact (distance = 1)
    for d in deleted_set:
        for neigh in adj.get(d, []):
            if neigh not in visited:
                distances[neigh] = 1
                visited.add(neigh)
                queue.append((neigh, 1))

    # BFS to propagate impact distances
    while queue:
        current_id, dist = queue.pop(0)
        for neigh in adj.get(current_id, []):
            if neigh not in visited:
                distances[neigh] = dist + 1
                visited.add(neigh)
                queue.append((neigh, dist + 1))

    impacted_set = set(distances.keys())
    for ik, dist in distances.items():
        if ik in nodes:
            nodes[ik]["status"] = "impacted"
            nodes[ik]["impact_distance"] = dist

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
        if dk in nodes:  # safety: ignore ghost nodes not loaded into memory
            node_name = nodes[dk].get("name", "").lower()
            if any(kw in node_name for kw in critical_keywords):
                found_critical.append(nodes[dk].get("name"))
    
    if found_critical:
        impact_insights.append(f"🔴 FALHA CRÍTICA: O ponto de entrada do sistema ({', '.join(found_critical)}) foi removido. O ambiente deixará de funcionar.")

    # 2. Layer-wise Impact Analysis
    layer_impacts = {}
    for ik in impacted_set:
        if ik in nodes:  # safety: ignore ghost nodes not loaded into memory
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

    # 5. Contract Break Insights (CALLS dependencies)
    for dk in deleted_set:
        node = nodes.get(dk)
        if not node:
            continue
        if node.get("label") not in ("Java_Method", "TS_Function", "SQL_Procedure"):
            continue

        broken_count = 0
        for edge in edges:
            if edge.get("type") != "CALLS":
                continue
            if edge.get("source") != dk:
                continue
            tgt = edge.get("target")
            if tgt in impacted_set and tgt in nodes:
                tgt_label = nodes[tgt].get("label")
                if tgt_label in ("Java_Method", "TS_Function", "SQL_Procedure"):
                    broken_count += 1

        if broken_count > 0:
            label = node.get("label")
            if label == "SQL_Procedure":
                template = "⚠️ Quebra de Contrato: A remoção da procedure/função {name} quebrou diretamente {count} outras funções/procedures que dependiam dela."
            else:
                template = "⚠️ Quebra de Contrato: A remoção do método {name} quebrou diretamente {count} outras funções que dependiam dele."

            impact_insights.append(
                template.format(name=node.get('name', dk), count=broken_count)
            )

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
async def review_simulation(sim_report: SimulationReviewRequest):
    """Generate a deep architectural review of a simulation scenario."""
    if scan_state.status == "scanning" or ai_busy:
         raise HTTPException(
            status_code=409,
            detail="A IA está ocupada ou o sistema está escaneando. Tente novamente em instantes."
        )

    risk = sim_report.risk_score
    insights = "\n".join([f"- {i}" for i in sim_report.impact_insights])
    
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


@app.get("/api/system/browse-folder")
def browse_folder():
    """Open native system folder picker dialog and return selected path."""
    try:
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        root.attributes("-topmost", True)  # Force window to stay on top
        selected_path = filedialog.askdirectory(title="Select Project Folder")
        root.destroy()
        if selected_path:
            return {"path": selected_path}
        else:
            return {"path": None}
    except Exception as e:
        logger.error("Folder picker failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to open folder picker")


@app.get("/api/workspaces")
async def get_workspaces():
    """Return list of analyzed project names from Neo4j or memory fallback."""
    projects = set()
    
    # Try Neo4j first
    if neo4j_service.is_connected:
        try:
            query = "MATCH (n) RETURN DISTINCT n.project as project"
            result = neo4j_service.graph.run(query)
            for record in result:
                if record["project"]:
                    projects.add(record["project"])
        except Exception as e:
            logger.warning("Neo4j query failed for projects: %s", e)
    
    # Fallback to memory_nodes
    if not projects:
        for node in memory_nodes:
            if "project" in node and node["project"]:
                projects.add(node["project"])
    
    return {"projects": list(projects)}


@app.delete("/api/workspaces/{project_name}")
async def delete_workspace(project_name: str):
    """Delete all nodes and relationships for a specific project."""
    global memory_nodes, memory_edges
    
    if neo4j_service.is_connected:
        try:
            query = "MATCH (n {project: $project_name}) DETACH DELETE n"
            neo4j_service.graph.run(query, project_name=project_name)
            logger.info(f"Deleted project {project_name} from Neo4j")
        except Exception as e:
            logger.error(f"Failed to delete project {project_name} from Neo4j: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete project from database: {str(e)}")
    else:
        # Fallback: filter memory_nodes and memory_edges
        original_count = len(memory_nodes)
        memory_nodes = [n for n in memory_nodes if n.get("project") != project_name]
        deleted_nodes = original_count - len(memory_nodes)
        
        # Get set of remaining namespace_keys
        remaining_keys = {n["namespace_key"] for n in memory_nodes}
        
        # Filter edges to only keep those with both source and target in remaining_keys
        original_edges = len(memory_edges)
        memory_edges = [
            e for e in memory_edges 
            if e["source"] in remaining_keys and e["target"] in remaining_keys
        ]
        deleted_edges = original_edges - len(memory_edges)
        
        logger.info(f"Deleted project {project_name} from memory: {deleted_nodes} nodes, {deleted_edges} edges")
    
    return {"message": f"Projeto {project_name} deletado com sucesso"}


@app.get("/api/history")
async def get_history():
    """Returns the historical architectural snapshots."""
    history_file = Path("history.json")
    if history_file.exists():
        with open(history_file, "r") as f:
            return json.load(f)
    return []


@app.get("/api/evolution/summary")
async def get_evolution_summary(window: int = 20):
    """Return aggregated evolution trends and current hotspot concentration."""
    history_file = Path("history.json")
    history: list[dict] = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    history = raw[-max(2, min(window, 200)):]
        except Exception as e:
            logger.warning("Failed to read history.json for evolution summary: %s", e)

    risk_series = []
    for item in history:
        god = int(item.get("god_classes", 0) or 0)
        circ = int(item.get("circular_deps", 0) or 0)
        dead = int(item.get("dead_code", 0) or 0)
        risk = min(100, god * 5 + circ * 10 + dead)
        risk_series.append({
            "timestamp": item.get("timestamp"),
            "risk_score": risk,
            "total_nodes": int(item.get("total_nodes", 0) or 0),
            "total_edges": int(item.get("total_edges", 0) or 0),
            "god_classes": god,
            "circular_deps": circ,
            "dead_code": dead,
            "call_resolution_rate": float(item.get("call_resolution_rate", 0.0) or 0.0),
        })

    def _trend(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        return round(values[-1] - values[0], 2)

    risk_values = [float(x["risk_score"]) for x in risk_series]
    node_values = [float(x["total_nodes"]) for x in risk_series]
    edge_values = [float(x["total_edges"]) for x in risk_series]
    call_res_values = [float(x.get("call_resolution_rate", 0.0) or 0.0) for x in risk_series]

    _ensure_memory_graph_loaded()
    project_hotspots: dict[str, list[dict]] = defaultdict(list)
    for node in memory_nodes:
        hs = float(node.get("hotspot_score", 0) or 0)
        if hs <= 0:
            continue
        project = str(node.get("project", "unknown") or "unknown")
        project_hotspots[project].append(node)

    top_hotspots_by_project = {}
    for project, arr in project_hotspots.items():
        arr_sorted = sorted(arr, key=lambda n: float(n.get("hotspot_score", 0) or 0), reverse=True)
        top_hotspots_by_project[project] = [
            {
                "namespace_key": n.get("namespace_key"),
                "name": n.get("name"),
                "file": n.get("file"),
                "complexity": int(n.get("complexity", 0) or 0),
                "git_churn": int(n.get("git_churn", 0) or 0),
                "hotspot_score": float(n.get("hotspot_score", 0) or 0),
            }
            for n in arr_sorted[:10]
        ]

    return {
        "series": risk_series,
        "trend": {
            "risk_delta": _trend(risk_values),
            "nodes_delta": _trend(node_values),
            "edges_delta": _trend(edge_values),
            "call_resolution_delta": _trend(call_res_values),
        },
        "top_hotspots_by_project": top_hotspots_by_project,
        "window_size": len(risk_series),
    }


@app.get("/api/file/content", response_model=FileContentResponse)
async def get_file_content(file_path: str, project: str = None):
    """
    Fetch the raw content of a file used in the graph analysis.
    Validates that the path is safe and readable.
    
    Args:
        file_path: Relative path to file (as stored in graph nodes)
        project: Project name (optional, used to locate the file)
    """
    global scanned_projects
    try:
        import re
        from urllib.parse import unquote

        # Normalize incoming path from different producers (graph/SARIF/UI).
        normalized_input = (file_path or "").strip().strip('"').strip("'")
        normalized_input = unquote(normalized_input)
        if normalized_input.startswith("file://"):
            normalized_input = normalized_input[7:]
        normalized_input = normalized_input.replace("\\", "/")
        # Strip line/column suffix, e.g. "src/Foo.java:123:9" -> "src/Foo.java"
        match = re.match(r"^(.*\.[A-Za-z0-9_]+):\d+(?::\d+)?$", normalized_input)
        if match:
            normalized_input = match.group(1)

        # Try to locate the file in this order:
        # 1. Within the registered project directory
        # 2. Relative to current working directory
        # 3. As-is (absolute path)
        
        possible_paths = []
        
        # First priority: use registered project path from runtime scans
        if project and project in scanned_projects:
            project_base = Path(scanned_projects[project])
            possible_paths.append(project_base / normalized_input)
            logger.info(f"Checking registered project path: {project_base / normalized_input}")

        # Also try CodeQL project registry source_path when project name matches.
        if project:
            try:
                for p in codeql_orchestrator.project_registry.list_projects():
                    if p.name == project:
                        codeql_base = Path(p.source_path)
                        normalized_file = normalized_input

                        # Standard candidate: source_path + file_path
                        possible_paths.append(codeql_base / normalized_file)

                        # If source_path already points to "src" and file_path starts with "src/",
                        # avoid duplicating segment (".../src/src/...").
                        if codeql_base.name.lower() == "src" and normalized_file.startswith("src/"):
                            possible_paths.append(codeql_base.parent / normalized_file)

                        # If file_path is relative from inside src (for example "main/java/..."),
                        # try anchoring under src explicitly.
                        possible_paths.append(codeql_base / "src" / normalized_file)

                        logger.info(
                            "Checking CodeQL project path candidates for %s using base %s",
                            project,
                            codeql_base,
                        )
                        break
            except Exception as e:
                logger.warning("Failed to resolve CodeQL project path for %s: %s", project, e)
        
        # Second priority: relative to cwd
        cwd_path = Path.cwd() / normalized_input
        possible_paths.append(cwd_path)
        logger.info(f"Checking cwd path: {cwd_path}")
        
        # Third priority: absolute path as-is
        abs_path = Path(normalized_input).resolve()
        possible_paths.append(abs_path)
        logger.info(f"Checking absolute path: {abs_path}")

        # Additional fallback: search in all known project roots when project name does not match.
        known_roots = []
        for root in scanned_projects.values():
            try:
                known_roots.append(Path(root).resolve())
            except Exception:
                pass
        try:
            for p in codeql_orchestrator.project_registry.list_projects():
                try:
                    known_roots.append(Path(p.source_path).resolve())
                except Exception:
                    continue
        except Exception:
            pass
        # Deduplicate roots
        unique_roots = []
        seen_roots = set()
        for root in known_roots:
            key = str(root).lower()
            if key not in seen_roots:
                seen_roots.add(key)
                unique_roots.append(root)

        for root in unique_roots:
            variants = [normalized_input]
            parts = [p for p in normalized_input.split("/") if p]
            if parts and parts[0].lower() == root.name.lower():
                variants.append("/".join(parts[1:]))

            src_idx = normalized_input.lower().find("/src/")
            if src_idx > 0:
                variants.append(normalized_input[src_idx + 1:])  # keep from "src/..."

            # Deduplicate variants
            unique_variants = []
            seen_variants = set()
            for v in variants:
                key = v.lower()
                if v and key not in seen_variants:
                    seen_variants.add(key)
                    unique_variants.append(v)

            for variant in unique_variants:
                possible_paths.append(root / variant)
                possible_paths.append(root / "src" / variant)
        
        # Find the first existing file
        found_path = None
        for candidate in possible_paths:
            try:
                resolved = candidate.resolve()
                if resolved.exists() and resolved.is_file():
                    found_path = resolved
                    logger.info(f"Found file at: {found_path}")
                    break
            except Exception as e:
                logger.debug(f"Checking {candidate} failed: {e}")
                continue
        
        if not found_path:
            logger.warning(
                f"File not found: {file_path} (normalized={normalized_input}, project={project}, checked paths={possible_paths})"
            )
            raise HTTPException(status_code=404, detail=f"File not found: {normalized_input}")
        
        # Security: prevent access outside known project roots when project is specified.
        if project:
            allowed_roots = []
            if project in scanned_projects:
                allowed_roots.append(Path(scanned_projects[project]).resolve())
            try:
                for p in codeql_orchestrator.project_registry.list_projects():
                    if p.name == project:
                        allowed_roots.append(Path(p.source_path).resolve())
                        break
            except Exception:
                pass

            if allowed_roots:
                inside_allowed_root = False
                for root in allowed_roots:
                    try:
                        found_path.relative_to(root)
                        inside_allowed_root = True
                        break
                    except ValueError:
                        continue

                if not inside_allowed_root:
                    logger.warning(f"Security violation: file outside project roots: {found_path}")
                    raise HTTPException(status_code=403, detail="Access denied: file outside project directory")
        
        # Read file content asynchronously
        try:
            content = await asyncio.to_thread(lambda: found_path.read_text(encoding='utf-8'))
        except UnicodeDecodeError:
            logger.warning(f"Could not decode file as UTF-8: {found_path}, trying with latin-1")
            # Fallback to latin-1 which can read most files
            content = await asyncio.to_thread(lambda: found_path.read_text(encoding='latin-1'))
        
        logger.info(f"Successfully read file: {found_path} ({len(content)} bytes)")
        return FileContentResponse(content=content, file_path=str(found_path.relative_to(found_path.cwd()) if found_path.cwd() in found_path.parents else found_path))
    
    except HTTPException:
        raise
    except PermissionError as e:
        logger.error(f"Permission denied reading file {file_path}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied reading file")
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


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
                status.ollama_embed = "available" if OLLAMA_EMBED_MODEL in models else "model_not_found"
                # Check complex model if explicitly listed in tags
                if OLLAMA_COMPLEX_MODEL in models:
                    status.complex_model = "available"
                else:
                    # Don't fail health if complex model is missing, just report
                    status.complex_model = "not_found"
            else:
                status.ollama_scanner = "error"
                status.ollama_chat = "error"
                status.ollama_embed = "error"
    except httpx.ConnectError:
        status.ollama_scanner = "offline"
        status.ollama_chat = "offline"
        status.ollama_embed = "offline"
    except Exception:
        status.ollama_scanner = "error"
        status.ollama_chat = "error"
        status.ollama_embed = "error"

    if not rag_index:
        _load_rag_index()
    status.rag_index_nodes = len(rag_index)

    return status


@app.get("/api/system/diagnostics")
async def system_diagnostics():
    """Consolidated runtime diagnostics for local CAST operation."""
    health = await get_health()
    _ensure_memory_graph_loaded()
    call_resolution = _compute_call_resolution_summary(top_n=10)
    rag = await rag_status()
    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "health": health.model_dump() if hasattr(health, "model_dump") else dict(health),
        "graph": {
            "nodes": len(memory_nodes),
            "edges": len(memory_edges),
            "projects": sorted({str(n.get("project")) for n in memory_nodes if n.get("project")}),
        },
        "call_resolution": call_resolution,
        "rag": rag,
    }


@app.post("/api/system/regression")
async def run_regression():
    """Run core regression suite for CAST-local behavior."""
    try:
        from regression_suite import run_regression_suite
        result = run_regression_suite(verbosity=1)
        return result
    except Exception as e:
        logger.error("Regression suite execution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# Entry point & CI/CD CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightGraph Backend & CI/CD CLI")
    parser.add_argument("mode", nargs="?", default="serve", choices=["serve", "scan", "regression"], help="Mode to run: serve (API), scan (CLI CI/CD), or regression (core test suite)")
    parser.add_argument("--path", type=str, help="Path to project to scan (required for scan mode)")
    parser.add_argument("--fail-on-risk", type=int, default=0, help="Risk threshold (1-100) to fail the CI/CD pipeline")
    args = parser.parse_args()

    if args.mode == "regression":
        from regression_suite import run_regression_suite
        print("[InsightGraph] Running regression suite...")
        outcome = run_regression_suite(verbosity=2)
        print(f"[InsightGraph] Regression result: ran={outcome['ran']} failures={outcome['failures']} errors={outcome['errors']}")
        if not outcome["successful"]:
            sys.exit(1)
        print("[InsightGraph] Regression suite passed.")
    elif args.mode == "scan":
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


# ──────────────────────────────────────────────
# CodeQL API Endpoints
# ──────────────────────────────────────────────
from dataclasses import asdict as _asdict

@app.get("/api/codeql/projects")
async def get_codeql_projects():
    """Get all CodeQL projects."""
    try:
        projects = codeql_orchestrator.project_registry.list_projects()
        return [_asdict(p) for p in projects]
    except Exception as e:
        logger.error(f"Error listing CodeQL projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/codeql/projects")
async def create_codeql_project(request: dict):
    """Create a new CodeQL project."""
    try:
        from codeql_models import CodeQLProject
        project = CodeQLProject.create(
            name=request["name"],
            source_path=request["source_path"],
            language=request.get("language", "java"),
            database_path=request.get("database_path", ""),
        )
        codeql_orchestrator.project_registry.add_project(project)
        return _asdict(project)
    except Exception as e:
        logger.error(f"Error creating CodeQL project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/codeql/projects/{project_id}")
async def update_codeql_project(project_id: str, request: dict):
    """Update a CodeQL project."""
    try:
        project = codeql_orchestrator.project_registry.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if "source_path" in request:
            project.source_path = request["source_path"]
        if "database_path" in request:
            project.database_path = request["database_path"]
        if "name" in request:
            project.name = request["name"]

        codeql_orchestrator.project_registry.add_project(project)
        return _asdict(project)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating CodeQL project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/codeql/projects/{project_id}")
async def delete_codeql_project(project_id: str):
    """Delete a CodeQL project."""
    try:
        removed = codeql_orchestrator.project_registry.remove_project(project_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"message": "Project deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting CodeQL project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/codeql/projects/{project_id}/database")
async def delete_codeql_database(project_id: str):
    """Delete a CodeQL project's database."""
    try:
        import shutil
        project = codeql_orchestrator.project_registry.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        db_path = Path(project.database_path)
        if db_path.exists():
            shutil.rmtree(db_path)

        return {"message": "Database deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting CodeQL database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/codeql/analyze")
async def start_codeql_analysis(request: dict, background_tasks: BackgroundTasks):
    """Start CodeQL analysis for a project."""
    try:
        job_id = await codeql_orchestrator.start_analysis(
            project_id=request["project_id"],
            suite=request.get("suite", "security-and-quality"),
            force_recreate=request.get("force_recreate", False),
        )
        return {"job_id": job_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting CodeQL analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/codeql/jobs/{job_id}")
async def get_codeql_job_status(job_id: str):
    """Get CodeQL job status."""
    try:
        job = codeql_orchestrator.get_status(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        payload = _asdict(job)
        payload["active_jobs"] = len(codeql_orchestrator.active_jobs)
        payload["queue_size"] = len(codeql_orchestrator.job_queue)
        payload["server_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if job.status == "queued" and job_id in codeql_orchestrator.job_queue:
            payload["queue_position"] = list(codeql_orchestrator.job_queue).index(job_id) + 1
        else:
            payload["queue_position"] = None

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting CodeQL job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/codeql/history")
async def get_codeql_history(
    project_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: Optional[int] = None,
):
    """Get CodeQL analysis history with optional filters."""
    try:
        entries = codeql_orchestrator.analysis_history.list_entries(
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return [_asdict(e) for e in entries]
    except Exception as e:
        logger.error(f"Error getting CodeQL history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/codeql/results/{project_id}")
async def get_codeql_results(project_id: str):
    """Get CodeQL analysis results for a project."""
    try:
        entries = codeql_orchestrator.analysis_history.list_entries(project_id=project_id, limit=1)
        if not entries:
            return {
                "vulnerabilities_count": 0,
                "ingested_count": 0,
                "skipped_count": 0,
                "tainted_paths_count": 0,
            }

        latest = entries[0]
        summary = latest.results_summary or {}
        return {
            "vulnerabilities_count": summary.get("total_issues", 0),
            "ingested_count": summary.get("ingested", 0),
            "skipped_count": summary.get("skipped", 0),
            "tainted_paths_count": summary.get("tainted_paths", 0),
        }
    except Exception as e:
        logger.error(f"Error getting CodeQL results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

