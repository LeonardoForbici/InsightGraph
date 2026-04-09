import React, { useState, useEffect, useCallback } from 'react';

interface GitCommit {
  hash: string;
  author: string;
  date: string;
  message: string;
  filesModified: string[];
  stats: {
    additions: number;
    deletions: number;
  };
}

interface GraphSnapshot {
  commitHash: string;
  timestamp: string;
  nodes: any[];
  edges: any[];
  diff: {
    added: string[];
    modified: string[];
    removed: string[];
  };
}

interface Timeline4DProps {
  onCommitSelected: (commitHash: string, snapshot: GraphSnapshot) => void;
  onReturnToPresent: () => void;
  onClose: () => void;
  repoUrl?: string;
  repoPath?: string;
  repoToken?: string;
  useShallowClone?: boolean;
}

const Timeline4D: React.FC<Timeline4DProps> = ({ onCommitSelected, onReturnToPresent, onClose, repoUrl, repoPath = ".", repoToken, useShallowClone = true }) => {
  console.log('Timeline4D component mounted with props:', { 
    repoUrl, 
    repoPath, 
    repoToken: repoToken ? '***' : 'none', 
    useShallowClone 
  });
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [selectedCommit, setSelectedCommit] = useState<GitCommit | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Load commit history on mount
  useEffect(() => {
    console.log('Timeline4D: useEffect triggered with dependencies:', { 
      repoUrl, 
      repoPath, 
      repoToken: repoToken ? '***' : 'none', 
      useShallowClone 
    });
    loadCommitHistory();
  }, [repoUrl, repoPath, repoToken, useShallowClone]); // Reload when config changes

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (selectedIndex === -1) return;

      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        navigateToPreviousCommit();
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        navigateToNextCommit();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        handleReturnToPresent();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIndex, commits]);

  const loadCommitHistory = async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Normalize repo URL (remove trailing slash)
      const normalizedRepoUrl = repoUrl?.trim().replace(/\/$/, '');
      
      const params = new URLSearchParams({
        max_commits: '100',
        repo_path: repoPath,
        use_shallow_clone: 'false'  // Desabilitar shallow clone para pegar histórico completo
      });
      if (normalizedRepoUrl) {
        params.append('repo_url', normalizedRepoUrl);
      }
      if (repoToken) {
        params.append('repo_token', repoToken);
      }
      
      console.log('Loading commit history with params:', params.toString());
      const response = await fetch(`/api/git/commits?${params.toString()}`);
      console.log('Response status:', response.status);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch commit history' }));
        throw new Error(errorData.detail || 'Failed to fetch commit history');
      }

      const data = await response.json();
      console.log('Commits loaded:', data.commits?.length || 0, 'commits');
      
      if (!data.commits || data.commits.length === 0) {
        setError('No commits found. Make sure the repository URL is correct and accessible.');
      } else {
        setCommits(data.commits || []);
      }
    } catch (err) {
      console.error('Error loading commit history:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to load commit history';
      setError(`Error loading commits: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  };

  const loadGraphSnapshot = async (commit: GitCommit, index: number) => {
    console.log('=== loadGraphSnapshot START ===');
    console.log('Commit:', commit.hash);
    console.log('Index:', index);
    console.log('Current state:', { isLoading, selectedIndex, selectedCommit: selectedCommit?.hash });
    
    setIsLoading(true);
    setError(null);

    try {
      // Normalize repo URL (remove trailing slash)
      const normalizedRepoUrl = repoUrl?.trim().replace(/\/$/, '');
      
      const params = new URLSearchParams({
        repo_path: repoPath,
        use_shallow_clone: useShallowClone.toString()
      });
      if (normalizedRepoUrl) {
        params.append('repo_url', normalizedRepoUrl);
      }
      if (repoToken) {
        params.append('repo_token', repoToken);
      }
      
      const url = `/api/git/snapshot/${commit.hash}?${params.toString()}`;
      console.log('Fetching URL:', url);
      
      const response = await fetch(url);
      console.log('Response received:', {
        status: response.status,
        statusText: response.statusText,
        ok: response.ok
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Error response body:', errorText);
        throw new Error(`Failed to load graph snapshot: ${response.status} ${response.statusText}`);
      }

      const snapshot: GraphSnapshot = await response.json();
      console.log('Snapshot received:', {
        commitHash: snapshot.commitHash,
        nodesCount: snapshot.nodes?.length || 0,
        edgesCount: snapshot.edges?.length || 0,
        diff: snapshot.diff
      });

      console.log('Setting state...');
      setSelectedCommit(commit);
      setSelectedIndex(index);
      
      console.log('Calling onCommitSelected...');
      onCommitSelected(commit.hash, snapshot);
      
      console.log('=== loadGraphSnapshot SUCCESS ===');
    } catch (err) {
      console.error('=== loadGraphSnapshot ERROR ===');
      console.error('Error:', err);
      setError('Failed to load graph snapshot: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsLoading(false);
      console.log('=== loadGraphSnapshot END ===');
    }
  };

  const handleSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const index = parseInt(event.target.value, 10);
    console.log('Slider changed to index:', index, 'of', commits.length);
    if (index >= 0 && index < commits.length) {
      console.log('Loading commit at index:', index, commits[index]);
      loadGraphSnapshot(commits[index], index);
    }
  };

  const navigateToPreviousCommit = () => {
    if (selectedIndex > 0) {
      loadGraphSnapshot(commits[selectedIndex - 1], selectedIndex - 1);
    }
  };

  const navigateToNextCommit = () => {
    if (selectedIndex < commits.length - 1) {
      loadGraphSnapshot(commits[selectedIndex + 1], selectedIndex + 1);
    }
  };

  const handleReturnToPresent = () => {
    setSelectedCommit(null);
    setSelectedIndex(-1);
    onReturnToPresent();
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  console.log('Timeline4D render state:', { 
    isLoading, 
    error, 
    commitsCount: commits.length,
    hasSelectedCommit: !!selectedCommit,
    selectedIndex 
  });

  if (isLoading && commits.length === 0) {
    return (
      <div className="timeline-4d loading">
        <p>Loading commit history...</p>
      </div>
    );
  }

  if (error && commits.length === 0) {
    return (
      <div className="timeline-4d error">
        <p>{error}</p>
        <button onClick={loadCommitHistory}>Retry</button>
      </div>
    );
  }

  return (
    <div className="timeline-4d">
      <div className="timeline-header">
        <h3>⏱️ Timeline 4D</h3>
        <div className="timeline-header-actions">
          {selectedCommit && (
            <button onClick={handleReturnToPresent} className="return-button">
              ← Present
            </button>
          )}
          <button onClick={onClose} className="close-timeline-button">
            ✕ Close
          </button>
        </div>
      </div>

      {commits.length > 0 && !selectedCommit && (
        <div className="timeline-info">
          <p>
            📊 <strong>{commits.length} commits</strong> loaded from <strong>{repoUrl || 'local repository'}</strong>
          </p>
          <p className="timeline-hint">
            👇 Select a commit below to view its changes. Your main graph will remain visible.
          </p>
        </div>
      )}

      {commits.length > 0 && (
        <div className="timeline-slider-container">
          <input
            type="range"
            min="0"
            max={commits.length - 1}
            value={selectedIndex >= 0 ? selectedIndex : 0}
            onChange={handleSliderChange}
            className="timeline-slider"
            disabled={isLoading}
          />
          <div className="timeline-markers">
            {commits.map((commit, index) => (
              <div
                key={commit.hash}
                className={`timeline-marker ${index === selectedIndex ? 'selected' : ''}`}
                style={{ left: `${(index / (commits.length - 1)) * 100}%` }}
                title={`${commit.author}: ${commit.message}`}
                onClick={() => {
                  console.log('Marker clicked for index:', index);
                  loadGraphSnapshot(commit, index);
                }}
              />
            ))}
          </div>
        </div>
      )}

      {commits.length > 0 && !selectedCommit && (
        <div className="commits-list">
          <h5>📜 Recent Commits</h5>
          <div className="commits-scroll">
            {commits.slice(0, 10).map((commit, index) => (
              <div
                key={commit.hash}
                className="commit-item"
                onClick={() => loadGraphSnapshot(commit, index)}
              >
                <div className="commit-item-header">
                  <span className="commit-item-hash">{commit.hash.substring(0, 7)}</span>
                  <span className="commit-item-author">{commit.author}</span>
                </div>
                <div className="commit-item-message">{commit.message}</div>
                <div className="commit-item-stats">
                  <span className="additions">+{commit.stats?.additions || 0}</span>
                  <span className="deletions">-{commit.stats?.deletions || 0}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedCommit && (
        <div className="commit-details">
          <div className="commit-metadata">
            <h4>{selectedCommit.message}</h4>
            <p className="commit-author">
              <strong>Author:</strong> {selectedCommit.author}
            </p>
            <p className="commit-date">
              <strong>Date:</strong> {formatDate(selectedCommit.date)}
            </p>
            <p className="commit-hash">
              <strong>Commit:</strong> {selectedCommit.hash.substring(0, 8)}
            </p>
            <p className="commit-stats">
              <span className="additions">+{selectedCommit.stats?.additions || 0}</span>
              {' / '}
              <span className="deletions">-{selectedCommit.stats?.deletions || 0}</span>
            </p>
          </div>

          <div className="files-modified">
            <h5>Files Modified ({selectedCommit.filesModified?.length || 0})</h5>
            <ul>
              {(selectedCommit.filesModified || []).slice(0, 10).map((file, index) => (
                <li key={index}>{file}</li>
              ))}
              {(selectedCommit.filesModified?.length || 0) > 10 && (
                <li className="more">... and {(selectedCommit.filesModified?.length || 0) - 10} more</li>
              )}
            </ul>
          </div>
          
          <div className="snapshot-info">
            <h5>📊 Commit Snapshot</h5>
            <div className="snapshot-stats">
              <div className="stat-card stat-added">
                <div className="stat-value">{selectedCommit.stats?.additions || 0}</div>
                <div className="stat-label">Lines Added</div>
              </div>
              <div className="stat-card stat-deleted">
                <div className="stat-value">{selectedCommit.stats?.deletions || 0}</div>
                <div className="stat-label">Lines Deleted</div>
              </div>
              <div className="stat-card stat-files">
                <div className="stat-value">{selectedCommit.filesModified?.length || 0}</div>
                <div className="stat-label">Files Changed</div>
              </div>
            </div>
            <div className="snapshot-mode-info">
              <p className="snapshot-hint">
                ⚡ <strong>Fast Mode Active</strong>
              </p>
              <p className="snapshot-description">
                Your main graph remains visible and unchanged. File changes are shown above.
                Navigate through commits to see how the codebase evolved over time.
              </p>
              <div className="snapshot-actions">
                <button onClick={handleReturnToPresent} className="btn-primary">
                  ← Return to Present
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="timeline-loading-overlay">
          <div className="loading-spinner"></div>
          <p>Loading snapshot...</p>
        </div>
      )}

      {error && (
        <div className="timeline-error-banner">
          <p>❌ {error}</p>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="keyboard-hints">
        <p>
          <kbd>←</kbd> Previous commit | <kbd>→</kbd> Next commit | <kbd>Esc</kbd> Return to present
        </p>
      </div>
    </div>
  );
};

export default Timeline4D;
