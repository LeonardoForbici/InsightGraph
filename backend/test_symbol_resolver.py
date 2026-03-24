"""
Tests for SymbolResolver.

Unit tests: single symbol resolution, PL/SQL procedure resolution.
PBT: homonymous symbols generate distinct namespace_keys.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from symbol_resolver import SymbolResolver, ResolvedSymbol, TypeContext

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_resolver(nodes: dict) -> SymbolResolver:
    return SymbolResolver(None, nodes, None)


# ──────────────────────────────────────────────
# 5.2.1 — Unit test: single symbol resolution returns correct namespace_key
# ──────────────────────────────────────────────

def test_resolve_single_symbol():
    """memory_nodes has one node with name='save'.
    resolve('save') returns [ResolvedSymbol] with correct namespace_key."""
    nodes = {
        "com.example.UserService.save": {
            "labels": ["JavaMethod"],
            "properties": {
                "name": "save",
                "module": "com.example",
                "return_type": "void",
                "param_types": ["User"],
            },
        }
    }
    resolver = _make_resolver(nodes)
    results = resolver.resolve("save")

    assert len(results) == 1
    assert results[0].namespace_key == "com.example.UserService.save"
    assert results[0].name == "save"
    assert isinstance(results[0].type_context, TypeContext)


# ──────────────────────────────────────────────
# 5.2.2 — Unit test: PL/SQL procedure resolution via schema+package+procedure
# ──────────────────────────────────────────────

def test_resolve_plsql_procedure():
    """memory_nodes has node with key 'HR.PKG_EMPLOYEE.GET_SALARY'.
    _resolve_plsql_procedure('HR', 'PKG_EMPLOYEE', 'GET_SALARY') returns it."""
    nodes = {
        "HR.PKG_EMPLOYEE.GET_SALARY": {
            "labels": ["Procedure"],
            "properties": {
                "name": "GET_SALARY",
                "module": "HR.PKG_EMPLOYEE",
                "return_type": "NUMBER",
                "param_types": ["NUMBER"],
            },
        }
    }
    resolver = _make_resolver(nodes)
    result = resolver._resolve_plsql_procedure("HR", "PKG_EMPLOYEE", "GET_SALARY")

    assert result is not None
    assert result.namespace_key == "HR.PKG_EMPLOYEE.GET_SALARY"
    assert result.name == "GET_SALARY"
    assert result.resolution_method == "qualified_name"


# ──────────────────────────────────────────────
# 5.2.3 — PBT: homonymous symbols generate distinct namespace_keys
# Feature: semantic-elite-analysis, Property 4: Símbolos homônimos geram entradas distintas
# ──────────────────────────────────────────────

_module_st = st.text(
    min_size=1, max_size=20,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)


@given(
    modules=st.lists(
        _module_st,
        min_size=2,
        max_size=5,
        unique=True,
    )
)
@settings(max_examples=100)
def test_homonymous_symbols_distinct_keys(modules):
    """Create methods with same name in distinct modules.
    detect_conflicts() returns entries with unique namespace_keys and semantic_conflicts populated.

    Validates: Requirements 2.2, 2.7
    """
    method_name = "process"
    nodes = {}
    for module in modules:
        key = f"{module}.SomeClass.{method_name}"
        nodes[key] = {
            "labels": ["JavaMethod"],
            "properties": {
                "name": method_name,
                "module": module,
                "return_type": "void",
                "param_types": [],
            },
        }

    resolver = _make_resolver(nodes)
    conflicts = resolver.detect_conflicts(method_name)

    # All returned symbols must have unique namespace_keys
    returned_keys = [sym.namespace_key for sym in conflicts]
    assert len(returned_keys) == len(set(returned_keys)), (
        "detect_conflicts() returned duplicate namespace_keys"
    )

    # Each symbol must have semantic_conflicts populated (pointing to the others)
    for sym in conflicts:
        assert len(sym.semantic_conflicts) > 0, (
            f"Symbol {sym.namespace_key!r} has empty semantic_conflicts"
        )
        # Its own key must not appear in its own conflicts list
        assert sym.namespace_key not in sym.semantic_conflicts
