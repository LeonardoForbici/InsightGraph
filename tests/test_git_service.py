"""
Test for GitService checkout_commit functionality (Task 4.2)

This test verifies that:
1. checkout_commit() validates commit hash
2. checkout_commit() saves original branch
3. checkout_commit() creates temporary directory
4. checkout_commit() clones and checks out commit
5. Error handling and cleanup work correctly

Requirements: 15.3, 15.6
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess


class TestGitServiceCheckout:
    """Test GitService checkout_commit functionality."""
    
    def test_checkout_commit_validates_hash(self):
        """Test that checkout_commit validates commit hash before proceeding."""
        from backend.git_service import GitService
        
        # Create a mock GitService with a valid repo
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            # Mock _is_valid_commit to return False
            with patch.object(git_service, '_is_valid_commit', return_value=False):
                with pytest.raises(ValueError, match="Invalid commit hash"):
                    git_service.checkout_commit("invalid_hash")
    
    def test_checkout_commit_saves_original_branch(self):
        """Test that checkout_commit saves the original branch."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            # Mock the helper methods
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/test_dir'), \
                 patch('subprocess.run') as mock_run:
                
                # Mock successful git operations
                mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
                
                try:
                    git_service.checkout_commit("abc123")
                    
                    # Verify original branch was saved
                    assert git_service._original_branch == 'main'
                finally:
                    # Cleanup
                    git_service._temp_dir = None
    
    def test_checkout_commit_creates_temp_directory(self):
        """Test that checkout_commit creates a temporary directory."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/insightgraph_test') as mock_mkdtemp, \
                 patch('subprocess.run') as mock_run:
                
                mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
                
                try:
                    result = git_service.checkout_commit("abc123")
                    
                    # Verify temp directory was created with correct prefix
                    mock_mkdtemp.assert_called_once()
                    assert mock_mkdtemp.call_args[1]['prefix'] == 'insightgraph_'
                    
                    # Verify result is the temp directory path
                    assert result == Path('/tmp/insightgraph_test')
                finally:
                    git_service._temp_dir = None
    
    def test_checkout_commit_clones_and_checks_out(self):
        """Test that checkout_commit performs git clone and checkout."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            git_service.repo_path = Path("/test/repo")
            
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/insightgraph_test'), \
                 patch('subprocess.run') as mock_run:
                
                mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
                
                try:
                    git_service.checkout_commit("abc123")
                    
                    # Verify git clone was called
                    clone_call = mock_run.call_args_list[0]
                    assert clone_call[0][0] == ['git', 'clone', '/test/repo', '/tmp/insightgraph_test']
                    assert clone_call[1]['timeout'] == 300
                    
                    # Verify git checkout was called
                    checkout_call = mock_run.call_args_list[1]
                    assert checkout_call[0][0] == ['git', '-C', '/tmp/insightgraph_test', 'checkout', 'abc123']
                    assert checkout_call[1]['timeout'] == 60
                finally:
                    git_service._temp_dir = None
    
    def test_checkout_commit_cleanup_on_clone_failure(self):
        """Test that checkout_commit cleans up temp directory on clone failure."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/insightgraph_test'), \
                 patch('subprocess.run') as mock_run, \
                 patch.object(git_service, '_cleanup_temp_dir') as mock_cleanup:
                
                # Simulate clone failure
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, 'git clone', stderr='Clone failed'
                )
                
                with pytest.raises(RuntimeError, match="Git command failed"):
                    git_service.checkout_commit("abc123")
                
                # Verify cleanup was called
                mock_cleanup.assert_called_once()
    
    def test_checkout_commit_cleanup_on_checkout_failure(self):
        """Test that checkout_commit cleans up temp directory on checkout failure."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/insightgraph_test'), \
                 patch('subprocess.run') as mock_run, \
                 patch.object(git_service, '_cleanup_temp_dir') as mock_cleanup:
                
                # First call (clone) succeeds, second call (checkout) fails
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout='', stderr=''),  # clone success
                    subprocess.CalledProcessError(1, 'git checkout', stderr='Checkout failed')  # checkout fail
                ]
                
                with pytest.raises(RuntimeError, match="Git command failed"):
                    git_service.checkout_commit("abc123")
                
                # Verify cleanup was called
                mock_cleanup.assert_called_once()
    
    def test_checkout_commit_timeout_handling(self):
        """Test that checkout_commit handles timeout errors."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch.object(git_service, '_is_valid_commit', return_value=True), \
                 patch.object(git_service, '_get_current_branch', return_value='main'), \
                 patch('tempfile.mkdtemp', return_value='/tmp/insightgraph_test'), \
                 patch('subprocess.run') as mock_run, \
                 patch.object(git_service, '_cleanup_temp_dir') as mock_cleanup:
                
                # Simulate timeout
                mock_run.side_effect = subprocess.TimeoutExpired('git clone', 300)
                
                with pytest.raises(RuntimeError, match="Git operation timed out"):
                    git_service.checkout_commit("abc123")
                
                # Verify cleanup was called
                mock_cleanup.assert_called_once()
    
    def test_cleanup_temp_dir_removes_directory(self):
        """Test that _cleanup_temp_dir removes the temporary directory."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            # Create a real temporary directory for this test
            temp_dir = Path(tempfile.mkdtemp(prefix="test_cleanup_"))
            git_service._temp_dir = temp_dir
            
            try:
                # Verify directory exists
                assert temp_dir.exists()
                
                # Call cleanup
                git_service._cleanup_temp_dir()
                
                # Verify directory was removed
                assert not temp_dir.exists()
                assert git_service._temp_dir is None
            finally:
                # Ensure cleanup even if test fails
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
    
    def test_get_current_branch_success(self):
        """Test that _get_current_branch returns the current branch name."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='main\n',
                    stderr=''
                )
                
                branch = git_service._get_current_branch()
                
                assert branch == 'main'
                mock_run.assert_called_once()
                assert mock_run.call_args[0][0] == ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
    
    def test_get_current_branch_failure(self):
        """Test that _get_current_branch raises error on failure."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, 'git rev-parse', stderr='Not a git repository'
                )
                
                with pytest.raises(RuntimeError, match="Failed to get current branch"):
                    git_service._get_current_branch()
    
    def test_is_valid_commit_returns_true_for_valid_hash(self):
        """Test that _is_valid_commit returns True for valid commit hash."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                
                result = git_service._is_valid_commit("abc123")
                
                assert result is True
                mock_run.assert_called_once()
    
    def test_is_valid_commit_returns_false_for_invalid_hash(self):
        """Test that _is_valid_commit returns False for invalid commit hash."""
        from backend.git_service import GitService
        
        with patch.object(GitService, '_validate_git_repo'):
            git_service = GitService("/test/repo")
            
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, 'git cat-file', stderr='Not a valid object'
                )
                
                result = git_service._is_valid_commit("invalid")
                
                assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
