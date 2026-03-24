"""
Test for /api/graph/stats endpoint with vulnerability counts.

Requirements: 10.4
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from main import app, neo4j_service


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_neo4j_stats():
    """Mock Neo4j stats response with vulnerability data."""
    return {
        "total_nodes": 100,
        "total_edges": 150,
        "nodes_by_type": {
            "Java_Class": 50,
            "Java_Method": 30,
            "TS_Component": 20
        },
        "edges_by_type": {
            "CALLS": 80,
            "DEPENDS_ON": 70
        },
        "layers": {
            "API": 30,
            "Service": 40,
            "Database": 30
        },
        "projects": ["project1", "project2"],
        "vulnerabilities_by_severity": {
            "error": 5,
            "warning": 10,
            "note": 3
        },
        "total_vulnerabilities": 18
    }


def test_stats_endpoint_includes_vulnerabilities(client, mock_neo4j_stats):
    """Test that /api/graph/stats includes vulnerability counts."""
    # Mock Neo4j connection and stats by mocking the graph attribute
    with patch.object(neo4j_service, 'graph', Mock()):
        with patch.object(neo4j_service, 'get_stats', return_value=mock_neo4j_stats):
            response = client.get("/api/graph/stats")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify basic stats
            assert data["total_nodes"] == 100
            assert data["total_edges"] == 150
            
            # Verify vulnerability counts (Requirements: 10.4)
            assert "vulnerabilities_by_severity" in data
            assert "total_vulnerabilities" in data
            assert data["total_vulnerabilities"] == 18
            assert data["vulnerabilities_by_severity"]["error"] == 5
            assert data["vulnerabilities_by_severity"]["warning"] == 10
            assert data["vulnerabilities_by_severity"]["note"] == 3


def test_stats_endpoint_no_vulnerabilities(client):
    """Test stats endpoint when no vulnerabilities exist."""
    mock_stats = {
        "total_nodes": 50,
        "total_edges": 75,
        "nodes_by_type": {"Java_Class": 50},
        "edges_by_type": {"CALLS": 75},
        "layers": {"API": 50},
        "projects": ["project1"],
        "vulnerabilities_by_severity": {},
        "total_vulnerabilities": 0
    }
    
    with patch.object(neo4j_service, 'graph', Mock()):
        with patch.object(neo4j_service, 'get_stats', return_value=mock_stats):
            response = client.get("/api/graph/stats")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["total_vulnerabilities"] == 0
            assert data["vulnerabilities_by_severity"] == {}


def test_stats_endpoint_memory_fallback(client):
    """Test stats endpoint falls back to memory when Neo4j is disconnected."""
    with patch.object(neo4j_service, 'graph', None):
        response = client.get("/api/graph/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        # Memory fallback should include vulnerability fields (empty)
        assert "vulnerabilities_by_severity" in data
        assert "total_vulnerabilities" in data
        assert data["total_vulnerabilities"] == 0
        assert data["vulnerabilities_by_severity"] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
