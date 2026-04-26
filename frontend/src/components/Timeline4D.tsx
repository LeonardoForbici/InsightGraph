import React, { useState, useEffect, useRef } from 'react';
import { fetchCicdStatus, fetchGraphActivityHeatmap } from '../api';

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
  const [cicdStatus, setCicdStatus] = useState<any | null>(null);
  const [replaySpeed, setReplaySpeed] = useState<number>(1);
  const [isReplaying, setIsReplaying] = useState(false);
  const [compareIndex, setCompareIndex] = useState<number | null>(null);
  const [heatmapAuthor, setHeatmapAuthor] = useState('');
  const [heatmapType, setHeatmapType] = useState('');
  const [heatmapArea, setHeatmapArea] = useState('');
  const [activityHotspots, setActivityHotspots] = useState<any[]>([]);
  const axisRef = useRef<HTMLCanvasElement | null>(null);

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

  useEffect(() => {
    if (!isReplaying || commits.length === 0) return;
    const current = selectedIndex >= 0 ? selectedIndex : 0;
    const timeoutMs = Math.max(80, Math.round(900 / Math.max(1, replaySpeed)));
    const timer = window.setTimeout(() => {
      if (current >= commits.length - 1) {
        setIsReplaying(false);
        return;
      }
      loadGraphSnapshot(commits[current + 1], current + 1);
    }, timeoutMs);
    return () => window.clearTimeout(timer);
  }, [isReplaying, selectedIndex, commits, replaySpeed]);

  useEffect(() => {
    const canvas = axisRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(20, h / 2);
    ctx.lineTo(w - 20, h / 2);
    ctx.stroke();
    commits.forEach((_, idx) => {
      const x = 20 + ((w - 40) * idx) / Math.max(1, commits.length - 1);
      const selected = idx === selectedIndex;
      ctx.fillStyle = selected ? '#60a5fa' : '#64748b';
      ctx.beginPath();
      ctx.arc(x, h / 2, selected ? 5 : 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }, [commits, selectedIndex]);

  useEffect(() => {
    fetchGraphActivityHeatmap({
      author: heatmapAuthor || undefined,
      type: heatmapType || undefined,
      area: heatmapArea || undefined,
    })
      .then((res) => setActivityHotspots((res.items || []).slice(0, 8)))
      .catch(() => setActivityHotspots([]));
  }, [heatmapAuthor, heatmapType, heatmapArea]);

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
        const ordered = [...(data.commits || [])].sort(
          (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
        );
        setCommits(ordered);
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
      try {
        const cicd = await fetchCicdStatus(commit.hash);
        setCicdStatus(cicd);
      } catch {
        setCicdStatus(null);
      }
      
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
    setCicdStatus(null);
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

      <div className="timeline-controls" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <div className="panel">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <strong>Replay</strong>
            <button className="btn btn-secondary" onClick={() => setIsReplaying((prev) => !prev)} disabled={commits.length === 0}>
              {isReplaying ? 'Pausar' : 'Reproduzir'}
            </button>
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              Velocidade {replaySpeed}x
              <input
                type="range"
                min={1}
                max={100}
                value={replaySpeed}
                onChange={(e) => setReplaySpeed(Number(e.target.value))}
              />
            </label>
          </div>
          <canvas ref={axisRef} width={520} height={72} style={{ width: '100%', marginTop: 8, borderRadius: 8 }} />
        </div>
        <div className="panel">
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <strong>Heatmap temporal</strong>
            <input className="input" placeholder="autor" value={heatmapAuthor} onChange={(e) => setHeatmapAuthor(e.target.value)} />
            <input className="input" placeholder="tipo" value={heatmapType} onChange={(e) => setHeatmapType(e.target.value)} />
            <input className="input" placeholder="área" value={heatmapArea} onChange={(e) => setHeatmapArea(e.target.value)} />
          </div>
          <div style={{ marginTop: 8, maxHeight: 72, overflowY: 'auto' }}>
            {activityHotspots.map((item) => (
              <div key={item.node_key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span>{item.node_key}</span>
                <span>{item.change_frequency}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

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
          <div className="snapshot-mode-info" style={{ marginTop: '12px' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <strong>Comparação side-by-side</strong>
              <select
                className="input"
                value={compareIndex ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setCompareIndex(v === '' ? null : Number(v));
                }}
              >
                <option value="">sem comparação</option>
                {commits.map((c, idx) => (
                  <option value={idx} key={c.hash}>
                    {c.hash.slice(0, 7)} - {c.author}
                  </option>
                ))}
              </select>
            </div>
            {compareIndex !== null && commits[compareIndex] && (
              <p className="snapshot-description" style={{ marginTop: 6 }}>
                Atual: <strong>{selectedCommit.hash.slice(0, 8)}</strong> vs
                comparação: <strong> {commits[compareIndex].hash.slice(0, 8)}</strong>
              </p>
            )}
          </div>
          {cicdStatus?.latest && (
            <div className="snapshot-mode-info" style={{ marginTop: '12px' }}>
              <p className="snapshot-hint">
                CI/CD: <strong>{String(cicdStatus.latest.status || 'unknown').toUpperCase()}</strong>
              </p>
              <p className="snapshot-description">
                Provider: {cicdStatus.latest.provider} | Commit: {String(cicdStatus.latest.commit_hash || '').slice(0, 8)}
              </p>
              {cicdStatus.latest.coverage !== undefined && cicdStatus.latest.coverage !== null && (
                <p className="snapshot-description">Coverage: {Number(cicdStatus.latest.coverage).toFixed(1)}%</p>
              )}
              {cicdStatus.latest.stack_trace && (
                <pre className="snapshot-description" style={{ whiteSpace: 'pre-wrap', maxHeight: '120px', overflowY: 'auto' }}>
                  {String(cicdStatus.latest.stack_trace).slice(0, 1200)}
                </pre>
              )}
            </div>
          )}
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
