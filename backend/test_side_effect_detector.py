"""
Tests for SideEffectDetector.

Unit tests: extraction of // BUSINESS RULE: and --RULE: comments.
PBT: inferred side effects have confidence_score < 70.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from side_effect_detector import SideEffectDetector, SideEffect, BusinessRuleNode

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_detector() -> SideEffectDetector:
    return SideEffectDetector(None, {}, [], None)


# ──────────────────────────────────────────────
# 5.4.1 — Unit test: extraction of // BUSINESS RULE:
# ──────────────────────────────────────────────

def test_extract_java_business_rule():
    """// BUSINESS RULE: comment must be extracted as an explicit rule with confidence=100."""
    source = "// BUSINESS RULE: Only active employees can request overtime"
    detector = _make_detector()
    rules = detector.extract_business_rules(source, "com.example.EmployeeService")

    assert len(rules) == 1
    assert "Only active employees" in rules[0].rule_text
    assert rules[0].inferred is False
    assert rules[0].confidence_score == 100


# ──────────────────────────────────────────────
# 5.4.2 — Unit test: extraction of --RULE: (PL/SQL)
# ──────────────────────────────────────────────

def test_extract_plsql_rule():
    """--RULE: comment must be extracted as an explicit rule."""
    source = "--RULE: Retroactive entries not allowed after fiscal closing"
    detector = _make_detector()
    rules = detector.extract_business_rules(source, "HR.PKG_PAYROLL.PROCESS")

    assert len(rules) == 1
    assert "Retroactive" in rules[0].rule_text
    assert rules[0].inferred is False
    assert rules[0].confidence_score == 100


# ──────────────────────────────────────────────
# 5.4.3 — PBT: inferred side effects have confidence_score < 70
# Feature: semantic-elite-analysis, Property 9: Side effects inferidos têm confidence < 70
# ──────────────────────────────────────────────

@given(confidence=st.integers(min_value=0, max_value=69))
@settings(max_examples=100)
def test_inferred_side_effects_low_confidence(confidence):
    """SideEffect with inferred=True must have confidence_score < 70.

    Validates: Requirement 3.7
    """
    effect = SideEffect(
        artifact_key="test",
        artifact_name="test",
        effect_type="SILENT_LOGIC_FAILURE",
        rule_violated="test rule",
        side_effect_risk=True,
        inferred=True,
        confidence_score=confidence,
    )
    assert effect.inferred is True
    assert effect.confidence_score < 70, (
        f"Inferred SideEffect has confidence_score={effect.confidence_score}, expected < 70"
    )
