"""
Tests for BidirectionalAnalyzer.

Unit tests: BOTTOM_UP and TOP_DOWN chain ordering with minimal graphs.
PBT: isolated artifacts return explicit result (isolated=True, chain=[]).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from taint_propagator import TaintPropagator
from fragility_calculator import FragilityCalculator
from side_effect_detector import SideEffectDetector
from bidirectional_analyzer import BidirectionalAnalyzer, BidirectionalResult

# ──────────────────────────────────────────────
# Stub dependencies
# ──────────────────────────────────────────────

class _StubSideEffectDetector:
    async def detect(self, change, affected_set):
        return []


class _StubImpactEngine:
    pass


def _make_analyzer(nodes: dict, edges: list) -> BidirectionalAnalyzer:
    """Build a BidirectionalAnalyzer backed entirely by in-memory data."""
    taint = TaintPropagator(None, nodes, edges)
    fragility = FragilityCalculator(None, nodes, edges, None)
    side_effects = _StubSideEffectDetector()
    impact = _StubImpactEngine()
    return BidirectionalAnalyzer(taint, None, side_effects, fragility, impact)


# ──────────────────────────────────────────────
# Minimal graph fixtures
# ──────────────────────────────────────────────

def _bottom_up_graph():
    """database → java → angular via CALLS, DISPLAYED_BY."""
    nodes = {
        "db.SALARY_COL": {
            "labels": ["Column"],
            "properties": {"name": "SALARY_COL", "data_type": "NUMBER"},
        },
        "com.example.EmployeeService.getSalary": {
            "labels": ["JavaMethod"],
            "properties": {"name": "getSalary", "data_type": "BigDecimal", "file": "EmployeeService.java"},
        },
        "salary.component": {
            "labels": ["AngularComponent"],
            "properties": {"name": "SalaryComponent", "data_type": "number", "file": "salary.component.ts"},
        },
    }
    edges = [
        {"from": "db.SALARY_COL", "to": "com.example.EmployeeService.getSalary", "type": "CALLS"},
        {"from": "com.example.EmployeeService.getSalary", "to": "salary.component", "type": "DISPLAYED_BY"},
    ]
    return nodes, edges


def _top_down_graph():
    """angular → java → database (reverse traversal via incoming edges)."""
    nodes, edges = _bottom_up_graph()
    return nodes, edges


# ──────────────────────────────────────────────
# 5.5.1 — Unit test: BOTTOM_UP chain in ascending layer order
# ──────────────────────────────────────────────

def test_bottom_up_chain_order():
    """BOTTOM_UP chain should be ordered: database, java, angular."""
    nodes, edges = _bottom_up_graph()
    analyzer = _make_analyzer(nodes, edges)

    result = asyncio.run(analyzer.analyze("db.SALARY_COL", "BOTTOM_UP"))

    assert isinstance(result, BidirectionalResult)
    assert result.direction == "BOTTOM_UP"
    assert len(result.chain) >= 2

    layers = [item.layer for item in result.chain]
    # database must come before java, java before angular
    layer_order = ["database", "procedure", "java", "typescript", "angular"]
    layer_indices = [layer_order.index(l) if l in layer_order else len(layer_order) for l in layers]
    assert layer_indices == sorted(layer_indices), (
        f"BOTTOM_UP chain not in ascending layer order: {layers}"
    )


# ──────────────────────────────────────────────
# 5.5.2 — Unit test: TOP_DOWN chain in descending layer order
# ──────────────────────────────────────────────

def test_top_down_chain_order():
    """TOP_DOWN chain should be ordered: angular, java, database."""
    nodes, edges = _top_down_graph()
    analyzer = _make_analyzer(nodes, edges)

    result = asyncio.run(analyzer.analyze("salary.component", "TOP_DOWN"))

    assert isinstance(result, BidirectionalResult)
    assert result.direction == "TOP_DOWN"
    assert len(result.chain) >= 2

    layers = [item.layer for item in result.chain]
    layer_order = ["angular", "typescript", "java", "procedure", "database"]
    layer_indices = [layer_order.index(l) if l in layer_order else len(layer_order) for l in layers]
    assert layer_indices == sorted(layer_indices), (
        f"TOP_DOWN chain not in descending layer order: {layers}"
    )


# ──────────────────────────────────────────────
# 5.5.3 — PBT: isolated artifact returns explicit result
# Feature: semantic-elite-analysis, Property 8: Artefatos isolados retornam resultado explícito
# ──────────────────────────────────────────────

_origin_st = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)


@given(origin=_origin_st)
@settings(max_examples=100)
def test_isolated_artifact_explicit_result(origin):
    """Empty graph → no path → isolated=True, chain=[].

    Validates: Requirement 5.8
    """
    # Empty graph: no nodes, no edges
    analyzer = _make_analyzer({}, [])
    result = asyncio.run(analyzer.analyze(origin, "BOTTOM_UP"))

    assert isinstance(result, BidirectionalResult)
    assert result.isolated is True, (
        f"Expected isolated=True for origin={origin!r} in empty graph, got isolated={result.isolated}"
    )
    assert result.chain == [], (
        f"Expected empty chain for isolated artifact, got {result.chain}"
    )
