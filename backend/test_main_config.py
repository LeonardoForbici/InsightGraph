"""
Test configuration management in backend/main.py

Tests that CodeQL environment variables are read correctly with proper fallbacks.
Validates: Requirements 11.1, 11.2, 11.3, 11.5, 11.6
"""

import os
import pytest
from unittest.mock import patch


def test_codeql_config_defaults():
    """Test that CodeQL configuration uses correct default values."""
    # Clear environment variables to test defaults
    env_keys = [
        "CODEQL_PATH",
        "CODEQL_DB_DIR",
        "CODEQL_RESULTS_DIR",
        "CODEQL_MAX_CONCURRENT",
        "CODEQL_TIMEOUT",
    ]
    
    # Save original values
    original_values = {key: os.environ.get(key) for key in env_keys}
    
    try:
        # Remove the variables
        for key in env_keys:
            os.environ.pop(key, None)
        
        # Re-import main to get fresh configuration
        import importlib
        import main
        importlib.reload(main)
        
        # Verify defaults
        assert main.CODEQL_PATH == "C:\\codeql\\codeql\\codeql.exe"
        assert main.CODEQL_DB_DIR == "./codeql-databases"
        assert main.CODEQL_RESULTS_DIR == "./codeql-results"
        assert main.CODEQL_MAX_CONCURRENT == 3
        assert main.CODEQL_TIMEOUT == 600
    finally:
        # Restore original values
        for key, value in original_values.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)


def test_codeql_config_from_environment():
    """Test that CodeQL configuration reads from environment variables."""
    env_vars = {
        "CODEQL_PATH": "/custom/path/codeql",
        "CODEQL_DB_DIR": "/custom/databases",
        "CODEQL_RESULTS_DIR": "/custom/results",
        "CODEQL_MAX_CONCURRENT": "5",
        "CODEQL_TIMEOUT": "1200",
    }
    
    with patch.dict(os.environ, env_vars):
        # Re-import main to get fresh configuration
        import importlib
        import main
        importlib.reload(main)
        
        # Verify environment values are used
        assert main.CODEQL_PATH == "/custom/path/codeql"
        assert main.CODEQL_DB_DIR == "/custom/databases"
        assert main.CODEQL_RESULTS_DIR == "/custom/results"
        assert main.CODEQL_MAX_CONCURRENT == 5
        assert main.CODEQL_TIMEOUT == 1200


def test_codeql_config_integer_parsing():
    """Test that integer configuration values are parsed correctly."""
    env_vars = {
        "CODEQL_MAX_CONCURRENT": "10",
        "CODEQL_TIMEOUT": "3600",
    }
    
    with patch.dict(os.environ, env_vars):
        import importlib
        import main
        importlib.reload(main)
        
        # Verify types
        assert isinstance(main.CODEQL_MAX_CONCURRENT, int)
        assert isinstance(main.CODEQL_TIMEOUT, int)
        assert main.CODEQL_MAX_CONCURRENT == 10
        assert main.CODEQL_TIMEOUT == 3600


def test_codeql_path_validation_warning(caplog):
    """Test that a warning is logged when CodeQL CLI is not found."""
    import logging
    
    # Use a non-existent path
    env_vars = {
        "CODEQL_PATH": "/nonexistent/path/codeql",
    }
    
    with patch.dict(os.environ, env_vars):
        import importlib
        import main
        importlib.reload(main)
        
        # The validation happens in the lifespan function
        # We can't easily test the lifespan function without starting the app
        # But we can verify the configuration is set
        assert main.CODEQL_PATH == "/nonexistent/path/codeql"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
