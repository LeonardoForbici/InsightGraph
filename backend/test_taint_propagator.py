"""
Tests for TaintPropagator.

Unit tests: propagation with minimal in-memory graph, unresolved links.
PBT: completeness, data_type presence, precision risk detection.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from taint_propagator import TaintPropagator, TaintPath, TaintPoint

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

HIGH_PRECISION_TYPES = ["DECIMAL", "BIGINT", "NUMERIC"]
LOW_PRECISION_TYPES = ["NUMBER", "FLOAT", "INT", "INTEGER"]

# Pairs that are explicitly listed as dangerous in _DANGEROUS_CONVERSIONS
_DANGEROUS_PAIRS = [
    ("DECIMAL", "NUMBER"),
    ("DECIMAL", "FLOAT"),
    ("BIGINT", "INT"),
    ("BIGINT", "INTEGER"),
    ("NUMBER", "FLOAT"),
    ("NUMERIC", "NUMBER"),
    ("NUMERIC", "FLOAT"),
]


def _make_propagator(nodes: dict, edges: list) -> TaintPropagator:
    return TaintPropagator(None, nodes, edges)


# ──────────────────────────────────────────────
# 5.1.1 — Unit test: minimal graph (3 nodes, 2 edges)
# ──────────────────────────────────────────────

def test_propagate_minimal_graph():
    """3 nodes: column → procedure → java_method; 2 edges: MAPS_TO_COLUMN, CALLS.
    Verify TaintPath has 3 points."""
    nodes = {
        "db.SALARY_COL": {
            "labels": ["Column"],
            "properties": {"name": "SALARY_COL", "data_type": "NUMBER"},
        },
        "HR.PKG.GET_SALARY": {
            "labels": ["Procedure"],
            "properties": {"name": "GET_SALARY", "data_type": "NUMBER"},
        },
        "com.example.EmployeeService.getSalary": {
            "labels": ["JavaMethod"],
            "properties": {"name": "getSalary", "data_type": "BigDecimal"},
        },
    }
    edges = [
        {"from": "db.SALARY_COL", "to": "HR.PKG.GET_SALARY", "type": "MAPS_TO_COLUMN"},
        {"from": "HR.PKG.GET_SALARY", "to": "com.example.EmployeeService.getSalary", "type": "CALLS"},
    ]
    propagator = _make_propagator(nodes, edges)
    path = propagator.propagate("db.SALARY_COL", "change_column_type", "NUMBER", "FLOAT")

    assert isinstance(path, TaintPath)
    assert len(path.points) == 3
    assert path.total_hops == 3
    assert path.points[0].node_key == "db.SALARY_COL"


# ──────────────────────────────────────────────
# 5.1.2 — Unit test: unresolved link does not interrupt
# ──────────────────────────────────────────────

def test_unresolved_link_does_not_interrupt():
    """Edge points to a node_key not in memory_nodes.
    Verify TaintPoint(resolved=False) is in the path and propagation continues."""
    nodes = {
        "db.SALARY_COL": {
            "labels": ["Column"],
            "properties": {"name": "SALARY_COL", "data_type": "NUMBER"},
        },
        "com.example.EmployeeService.getSalary": {
            "labels": ["JavaMethod"],
            "properties": {"name": "getSalary", "data_type": "BigDecimal"},
        },
    }
    edges = [
        # Points to a node NOT in memory_nodes
        {"from": "db.SALARY_COL", "to": "GHOST_NODE", "type": "MAPS_TO_COLUMN"},
        # GHOST_NODE also has an outgoing edge to a real node
        {"from": "GHOST_NODE", "to": "com.example.EmployeeService.getSalary", "type": "CALLS"},
    ]
    propagator = _make_propagator(nodes, edges)
    path = propagator.propagate("db.SALARY_COL", "change_column_type", "NUMBER", "FLOAT")

    node_keys = [p.node_key for p in path.points]
    assert "GHOST_NODE" in node_keys, "Unresolved node must appear in path"

    ghost_point = next(p for p in path.points if p.node_key == "GHOST_NODE")
    assert ghost_point.resolved is False

    # Propagation must continue: the java method should also be reachable
    assert "com.example.EmployeeService.getSalary" in node_keys


# ──────────────────────────────────────────────
# 5.1.3 — PBT: TaintPath is complete (no silent omissions)
# Feature: semantic-elite-analysis, Property 1: TaintPath é completo e contínuo
# ──────────────────────────────────────────────

# Strategy: build a small linear graph with 1–5 nodes
_node_key_st = st.text(
    min_size=3, max_size=20,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._"),
)

_rel_types = st.sampled_from([
    "MAPS_TO_COLUMN", "MAPPED_FROM", "SERIALIZED_BY",
    "DISPLAYED_BY", "HAS_PARAMETER", "HAS_FIELD", "CALLS", "CALLS_HTTP",
])


@st.composite
def linear_graph(draw):
    """Generate a linear chain of 2–5 unique node keys connected by tracked relationships."""
    n = draw(st.integers(min_value=2, max_value=5))
    keys = draw(st.lists(_node_key_st, min_size=n, max_size=n, unique=True))
    nodes = {
        k: {
            "labels": ["JavaMethod"],
            "properties": {"name": k, "data_type": "String"},
        }
        for k in keys
    }
    edges = []
    for i in range(len(keys) - 1):
        rel = draw(_rel_types)
        edges.append({"from": keys[i], "to": keys[i + 1], "type": rel})
    return keys, nodes, edges


@given(graph=linear_graph())
@settings(max_examples=100)
def test_taint_path_no_silent_omissions(graph):
    """All reachable nodes via tracked relationships appear in TaintPath (resolved or unresolved).

    Validates: Requirements 1.1, 1.7
    """
    keys, nodes, edges = graph
    propagator = _make_propagator(nodes, edges)
    path = propagator.propagate(keys[0], "change_column_type", "NUMBER", "FLOAT")

    path_keys = {p.node_key for p in path.points}
    for key in keys:
        assert key in path_keys, f"Node {key!r} was silently omitted from TaintPath"


# ──────────────────────────────────────────────
# 5.1.4 — PBT: each TaintPoint has non-empty data_type
# Feature: semantic-elite-analysis, Property 2: Tipos registrados em cada ponto
# ──────────────────────────────────────────────

@st.composite
def nodes_and_edges(draw):
    """Generate 1–4 nodes with explicit data_type and a chain of edges."""
    n = draw(st.integers(min_value=1, max_value=4))
    keys = draw(st.lists(_node_key_st, min_size=n, max_size=n, unique=True))
    data_types = draw(st.lists(
        st.text(min_size=1, max_size=10, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        min_size=n, max_size=n,
    ))
    nodes = {
        k: {
            "labels": ["JavaMethod"],
            "properties": {"name": k, "data_type": dt},
        }
        for k, dt in zip(keys, data_types)
    }
    edges = []
    for i in range(len(keys) - 1):
        rel = draw(_rel_types)
        edges.append({"from": keys[i], "to": keys[i + 1], "type": rel})
    return nodes, edges, keys


@given(graph=nodes_and_edges())
@settings(max_examples=100)
def test_taint_points_have_data_type(graph):
    """Each TaintPoint has non-empty data_type, and total_hops == len(points).

    Validates: Requirements 1.2, 1.8
    """
    nodes, edges, keys = graph
    propagator = _make_propagator(nodes, edges)
    path = propagator.propagate(keys[0], "change_column_type", "NUMBER", "FLOAT")

    assert path.total_hops == len(path.points)
    for point in path.points:
        if point.resolved:
            assert point.data_type != "", (
                f"Resolved TaintPoint {point.node_key!r} has empty data_type"
            )


# ──────────────────────────────────────────────
# 5.1.5 — PBT: precision risk detected for dangerous type pairs
# Feature: semantic-elite-analysis, Property 3: Precision risk em conversões perigosas
# ──────────────────────────────────────────────

@given(pair=st.sampled_from(_DANGEROUS_PAIRS))
@settings(max_examples=100)
def test_precision_risk_detected(pair):
    """precision_risk=True for all known dangerous type pairs.

    Validates: Requirement 1.3
    """
    from_type, to_type = pair
    propagator = _make_propagator({}, [])
    risk, description = propagator._detect_precision_risk(from_type, to_type)
    assert risk is True, (
        f"Expected precision_risk=True for {from_type!r} → {to_type!r}, got False"
    )
