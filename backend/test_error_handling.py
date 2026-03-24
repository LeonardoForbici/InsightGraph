"""
Test comprehensive error handling for CodeQL components.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from codeql_database_manager import DatabaseManager, DatabaseError
from codeql_analysis_engine import AnalysisEngine, AnalysisError
from codeql_bridge import CodeQLBridge


class TestDatabaseManagerErrorHandling:
    """Test error handling in DatabaseManager."""
    
    def test_path_validation_directory_traversal(self):
        """Test that directory traversal attempts are blocked."""
        manager = DatabaseManager()
        
        with pytest.raises(DatabaseError) as exc_info:
            manager._validate_path("../../../etc/passwd", "test")
        
        assert "directory traversal" in str(exc_info.value).lower()
        assert exc_info.value.category == "invalid_path"
    
    def test_database_error_to_dict(self):
        """Test DatabaseError serialization to dict."""
        error = DatabaseError(
            message="Test error",
            details="Additional details",
            stderr="Some stderr output",
            category="test_category"
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error"] == "Test error"
        assert error_dict["category"] == "test_category"
        assert error_dict["details"] == "Additional details"
        assert "stderr" in error_dict
    
    def test_stderr_sanitization(self):
        """Test that stderr is sanitized to remove sensitive info."""
        error = DatabaseError(
            message="Test",
            stderr="Error in C:\\Users\\john\\project\\file.py at line 10"
        )
        
        error_dict = error.to_dict()
        sanitized = error_dict["stderr"]
        
        # Should replace absolute paths
        assert "C:\\Users\\john" not in sanitized
        assert "[PATH]" in sanitized
    
    def test_codeql_not_found_error(self):
        """Test error when CodeQL CLI is not found."""
        manager = DatabaseManager(codeql_path="nonexistent_codeql")
        
        with pytest.raises(DatabaseError) as exc_info:
            manager.create_database(
                source_path=".",
                database_path="./test_db",
                language="python"
            )
        
        assert exc_info.value.category == "codeql_not_found"
        assert "CodeQL CLI not found" in exc_info.value.message
    
    def test_invalid_source_path_error(self):
        """Test error when source path doesn't exist."""
        manager = DatabaseManager()
        
        with pytest.raises(DatabaseError) as exc_info:
            manager.create_database(
                source_path="/nonexistent/path",
                database_path="./test_db",
                language="python"
            )
        
        assert exc_info.value.category == "invalid_path"
        assert "does not exist" in exc_info.value.message.lower()


class TestAnalysisEngineErrorHandling:
    """Test error handling in AnalysisEngine."""
    
    def test_path_validation_directory_traversal(self):
        """Test that directory traversal attempts are blocked."""
        engine = AnalysisEngine()
        
        with pytest.raises(AnalysisError) as exc_info:
            engine._validate_path("../../../etc/passwd", "test")
        
        assert "directory traversal" in str(exc_info.value).lower()
        assert exc_info.value.category == "invalid_path"
    
    def test_analysis_error_to_dict(self):
        """Test AnalysisError serialization to dict."""
        error = AnalysisError(
            message="Analysis failed",
            details="Query timeout",
            stderr="Error output",
            category="analysis_failed"
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error"] == "Analysis failed"
        assert error_dict["category"] == "analysis_failed"
        assert error_dict["details"] == "Query timeout"
        assert "stderr" in error_dict
    
    def test_invalid_suite_error(self):
        """Test error when invalid query suite is provided."""
        engine = AnalysisEngine()
        
        with pytest.raises(AnalysisError) as exc_info:
            engine.execute_analysis(
                database_path="./test_db",
                suite="invalid-suite"
            )
        
        assert exc_info.value.category == "invalid_suite"
        assert "Invalid query suite" in exc_info.value.message
    
    def test_invalid_database_error(self):
        """Test error when database doesn't exist."""
        engine = AnalysisEngine()
        
        with pytest.raises(AnalysisError) as exc_info:
            engine.execute_analysis(
                database_path="/nonexistent/database",
                suite="security-extended"
            )
        
        assert exc_info.value.category == "invalid_database"
        assert "does not exist" in exc_info.value.message.lower()


class TestCodeQLBridgeErrorHandling:
    """Test error handling in CodeQLBridge."""
    
    def test_path_validation_directory_traversal(self):
        """Test that directory traversal attempts are blocked in bridge."""
        mock_neo4j = Mock()
        
        with pytest.raises(ValueError) as exc_info:
            CodeQLBridge(mock_neo4j, "../../../etc")
        
        assert "directory traversal" in str(exc_info.value).lower()
    
    def test_run_analysis_invalid_database(self):
        """Test run_analysis with invalid database path."""
        mock_neo4j = Mock()
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        result = bridge.run_analysis(
            database_path="/nonexistent/database",
            output_path="./output.sarif"
        )
        
        assert result["success"] is False
        assert result["category"] == "invalid_database"
        assert result["stage"] == "analysis"
        assert "error" in result
    
    def test_ingest_sarif_file_not_found(self):
        """Test ingest_sarif with non-existent SARIF file."""
        mock_neo4j = Mock()
        mock_neo4j.is_connected = True
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        result = bridge.ingest_sarif("/nonexistent/file.sarif")
        
        assert "error" in result
        assert result["category"] == "invalid_path"
        assert result["stage"] == "ingestion"
        assert result["total_issues"] == 0
    
    def test_ingest_sarif_neo4j_disconnected(self):
        """Test ingest_sarif when Neo4j is disconnected."""
        mock_neo4j = Mock()
        mock_neo4j.is_connected = False
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        # Create a temporary SARIF file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sarif', delete=False) as f:
            json.dump({"runs": []}, f)
            sarif_path = f.name
        
        try:
            result = bridge.ingest_sarif(sarif_path)
            
            assert "error" in result
            assert result["error"] == "Neo4j disconnected"
            assert result["category"] == "neo4j_error"
            assert result["stage"] == "ingestion"
        finally:
            Path(sarif_path).unlink()
    
    def test_ingest_sarif_invalid_json(self):
        """Test ingest_sarif with invalid JSON."""
        mock_neo4j = Mock()
        mock_neo4j.is_connected = True
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        # Create a temporary file with invalid JSON
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sarif', delete=False) as f:
            f.write("{ invalid json }")
            sarif_path = f.name
        
        try:
            result = bridge.ingest_sarif(sarif_path)
            
            assert "error" in result
            assert result["category"] == "invalid_sarif"
            assert result["stage"] == "ingestion"
            assert "JSON parsing error" in result["details"]
        finally:
            Path(sarif_path).unlink()
    
    def test_sanitize_stderr(self):
        """Test stderr sanitization in CodeQLBridge."""
        stderr = "Error in C:\\Users\\john\\project\\file.py at line 10"
        sanitized = CodeQLBridge._sanitize_stderr(stderr)
        
        # Should replace absolute paths
        assert "C:\\Users\\john" not in sanitized
        assert "[PATH]" in sanitized


class TestErrorResponseFormat:
    """Test that error responses follow the required format."""
    
    def test_database_error_response_format(self):
        """Test DatabaseError response includes all required fields."""
        error = DatabaseError(
            message="Database creation failed",
            details="Insufficient permissions",
            stderr="Permission denied",
            category="database_creation_failed"
        )
        
        response = error.to_dict()
        
        # Requirements: 8.1, 8.2, 8.4, 8.5
        assert "error" in response
        assert "category" in response
        assert "details" in response
        assert "stderr" in response
    
    def test_analysis_error_response_format(self):
        """Test AnalysisError response includes all required fields."""
        error = AnalysisError(
            message="Analysis timeout",
            details="Exceeded 600 seconds",
            category="timeout"
        )
        
        response = error.to_dict()
        
        # Requirements: 8.1, 8.2, 8.4
        assert "error" in response
        assert "category" in response
        assert "details" in response
    
    def test_bridge_error_response_format(self):
        """Test CodeQLBridge error responses include required fields."""
        mock_neo4j = Mock()
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        result = bridge.run_analysis(
            database_path="/nonexistent/database",
            output_path="./output.sarif"
        )
        
        # Requirements: 8.1, 8.2, 8.4, 8.5
        assert "error" in result
        assert "category" in result
        assert "details" in result
        assert "stage" in result


class TestErrorLogging:
    """Test that errors are logged at ERROR level."""
    
    @patch('codeql_database_manager.logger')
    def test_database_error_logging(self, mock_logger):
        """Test that database errors are logged at ERROR level."""
        manager = DatabaseManager()
        
        try:
            manager.create_database(
                source_path="/nonexistent/path",
                database_path="./test_db",
                language="python"
            )
        except DatabaseError:
            pass
        
        # Verify ERROR level logging was called
        assert mock_logger.error.called
    
    @patch('codeql_analysis_engine.logger')
    def test_analysis_error_logging(self, mock_logger):
        """Test that analysis errors are logged at ERROR level."""
        engine = AnalysisEngine()
        
        try:
            engine.execute_analysis(
                database_path="/nonexistent/database",
                suite="security-extended"
            )
        except AnalysisError:
            pass
        
        # Verify ERROR level logging was called
        assert mock_logger.error.called
    
    @patch('codeql_bridge.logger')
    def test_bridge_error_logging(self, mock_logger):
        """Test that bridge errors are logged at ERROR level."""
        mock_neo4j = Mock()
        bridge = CodeQLBridge(mock_neo4j, ".")
        
        bridge.run_analysis(
            database_path="/nonexistent/database",
            output_path="./output.sarif"
        )
        
        # Verify ERROR level logging was called
        assert mock_logger.error.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
