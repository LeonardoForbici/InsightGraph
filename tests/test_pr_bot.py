"""
Property-based tests for PR Bot.

Tests Properties 1 and 2 from the InsightGraph SaaS Roadmap design document.
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, strategies as st, settings
from pr_bot import PRBot, AffectedSet


# ──────────────────────────────────────────────
# Hypothesis strategies
# ──────────────────────────────────────────────

@st.composite
def affected_set_strategy(draw):
    """
    Generate random AffectedSet instances.
    
    Strategy:
    - affected_count: 0 to 500 items
    - max_depth: 0 to 50 (via call_chain length)
    - Each item has a call_chain list
    """
    num_items = draw(st.integers(min_value=0, max_value=500))
    items = []
    
    for _ in range(num_items):
        # Generate call chain with depth 0 to 50
        chain_length = draw(st.integers(min_value=0, max_value=51))
        call_chain = [f"node_{i}" for i in range(chain_length)]
        
        item = {
            "name": draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))),
            "namespace_key": draw(st.text(min_size=1, max_size=100)),
            "category": draw(st.sampled_from(["service", "module", "class", "function"])),
            "confidence_score": draw(st.integers(min_value=0, max_value=100)),
            "call_chain": call_chain,
        }
        items.append(item)
    
    metadata = {
        "elapsed_seconds": draw(st.floats(min_value=0.0, max_value=120.0)),
    }
    
    return AffectedSet(items=items, analysis_metadata=metadata)


@st.composite
def antipatterns_strategy(draw):
    """
    Generate random antipatterns dict.
    
    Strategy:
    - 0 to 100 antipatterns across various categories
    - Categories: circular_dependencies, god_classes, hardcoded_secrets, etc.
    """
    categories = [
        "circular_dependencies",
        "god_classes",
        "hardcoded_secrets",
        "sql_injection_risk",
        "cloud_blockers",
        "architecture_violations",
        "dead_code",
    ]
    
    antipatterns = {}
    
    for category in categories:
        # Each category has 0 to 20 items
        num_items = draw(st.integers(min_value=0, max_value=20))
        items = []
        
        for _ in range(num_items):
            item = {
                "key": draw(st.text(min_size=1, max_size=100)),
                "namespace_key": draw(st.text(min_size=1, max_size=100)),
                "name": draw(st.text(min_size=1, max_size=50)),
            }
            items.append(item)
        
        antipatterns[category] = items
    
    return antipatterns


# ──────────────────────────────────────────────
# Property 1: Impact score sempre dentro do intervalo válido [0, 100]
# ──────────────────────────────────────────────

# Feature: insightgraph-saas-roadmap, Property 1: Impact score sempre dentro do intervalo válido [0, 100]
# **Validates: Requirements 1.4**

@settings(max_examples=100)
@given(
    affected_set=affected_set_strategy(),
    antipatterns=antipatterns_strategy(),
)
@pytest.mark.asyncio
async def test_property_1_impact_score_always_in_valid_range(affected_set, antipatterns):
    """
    Property 1: Impact score sempre dentro do intervalo válido [0, 100]
    
    For any valid AffectedSet (with any number of items, depth, and antipattern count),
    compute_impact_score must return an integer in the range [0, 100].
    
    **Validates: Requirements 1.4**
    """
    # Arrange
    bot = PRBot(
        api_url="http://localhost:8000",
        github_token="fake_token",
        repo="owner/repo"
    )
    
    # Act
    score = await bot.compute_impact_score(affected_set, antipatterns)
    
    # Assert
    assert isinstance(score, int), f"Score must be an integer, got {type(score)}"
    assert 0 <= score <= 100, f"Score must be in [0, 100], got {score}"


# ──────────────────────────────────────────────
# Property 2: Comentário do PR contém todos os campos obrigatórios
# ──────────────────────────────────────────────

# Feature: insightgraph-saas-roadmap, Property 2: Comentário do PR contém todos os campos obrigatórios
# **Validates: Requirements 1.5, 1.6, 1.10**

@settings(max_examples=100)
@given(
    affected_set=affected_set_strategy(),
    antipatterns=antipatterns_strategy(),
)
@pytest.mark.asyncio
async def test_property_2_comment_contains_all_required_fields(affected_set, antipatterns):
    """
    Property 2: Comentário do PR contém todos os campos obrigatórios
    
    For any valid analysis result (with score, affected nodes, and antipatterns),
    the generated PR comment must contain:
    - Impact score
    - List of affected services/modules
    - Risk alerts
    
    This property validates that the comment structure is complete regardless of
    whether antipatterns are empty or embeddings are available.
    
    **Validates: Requirements 1.5, 1.6, 1.10**
    """
    # Arrange
    bot = PRBot(
        api_url="http://localhost:8000",
        github_token="fake_token",
        repo="owner/repo"
    )
    
    # Act
    score = await bot.compute_impact_score(affected_set, antipatterns)
    comment_body = bot._build_comment_body(score, affected_set, antipatterns)
    
    # Assert - Check that all required sections are present
    assert "## 🔍 InsightGraph — Impact Analysis" in comment_body, \
        "Comment must contain the main header"
    
    assert "**Impact Score:**" in comment_body, \
        "Comment must contain the impact score section"
    
    assert str(score) in comment_body, \
        f"Comment must contain the actual score value {score}"
    
    assert "### 📦 Affected Services & Modules" in comment_body, \
        "Comment must contain the affected services section"
    
    assert "### ⚠️ Risk Alerts" in comment_body, \
        "Comment must contain the risk alerts section"
    
    assert "### 🐛 Antipatterns Detected" in comment_body, \
        "Comment must contain the antipatterns section"
    
    # Verify that the comment handles empty cases gracefully
    if affected_set.affected_count == 0:
        assert "_No affected nodes detected._" in comment_body, \
            "Comment must indicate when no affected nodes are present"
    
    # Count antipatterns
    antipattern_count = sum(
        len(items) for items in antipatterns.values() if isinstance(items, list)
    )
    
    if antipattern_count == 0:
        assert "_No antipatterns detected._" in comment_body or "_No risk alerts detected._" in comment_body, \
            "Comment must indicate when no antipatterns are present"
