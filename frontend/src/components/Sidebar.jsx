import React, { useState } from 'react';
import { ingestRepository } from '../services/api';

export default function Sidebar({ status, onIngested, onRepoUrlChange, onGithubTokenChange }) {
  const [repoUrl, setRepoUrl] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleIngest = async () => {
    if (!repoUrl.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await ingestRepository(repoUrl.trim(), githubToken.trim() || null);
      setResult(data);
      onIngested(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Ingestion failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-header">
        <div className="header-logo">
          <div className="header-logo-icon">⚡</div>
          <div>
            <h1>DevCopilot</h1>
            <span>AI Codebase Assistant</span>
          </div>
        </div>
      </div>

      {/* Repository Input */}
      <div className="sidebar-section">
        <h3>Repository</h3>

        <div className="input-group">
          <label htmlFor="repo-url">GitHub Repository URL</label>
          <input
            id="repo-url"
            type="text"
            className="input-field"
            placeholder="https://github.com/user/repo"
            value={repoUrl}
            onChange={(e) => {
              setRepoUrl(e.target.value);
              onRepoUrlChange?.(e.target.value);
            }}
            disabled={loading}
          />
        </div>

        <div className="input-group">
          <label htmlFor="github-token">GitHub Token (optional)</label>
          <input
            id="github-token"
            type="password"
            className="input-field"
            placeholder="ghp_xxxxxxxxxxxx"
            value={githubToken}
            onChange={(e) => {
              setGithubToken(e.target.value);
              onGithubTokenChange?.(e.target.value);
            }}
            disabled={loading}
          />
        </div>

        <button
          className="btn btn-primary btn-full"
          onClick={handleIngest}
          disabled={loading || !repoUrl.trim()}
          id="ingest-btn"
        >
          {loading ? (
            <>
              <div className="loading-spinner" />
              Ingesting...
            </>
          ) : (
            <>🔍 Ingest Repository</>
          )}
        </button>

        {/* Loading Progress */}
        {loading && (
          <div className="ingest-progress">
            <div className="progress-bar-bg">
              <div className="progress-bar-fill" style={{ width: '60%' }} />
            </div>
            <p className="progress-text">Cloning, parsing, building graph & indexing vectors...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="error-banner">
            ❌ {error}
          </div>
        )}

        {/* Success */}
        {result && (
          <div className="success-banner">
            ✅ {result.message}
          </div>
        )}

        {/* Stats */}
        {(result || status?.details) && (
          <>
            <h3 style={{ marginTop: 20 }}>Repository Stats</h3>
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-value">
                  {result?.file_count || status?.details?.repo?.file_count || 0}
                </div>
                <div className="stat-label">Files</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">
                  {result?.graph_nodes || status?.details?.graph?.total_nodes || 0}
                </div>
                <div className="stat-label">Graph Nodes</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">
                  {result?.graph_edges || status?.details?.graph?.total_edges || 0}
                </div>
                <div className="stat-label">Edges</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">
                  {result?.chunks_indexed || status?.details?.faiss?.total_vectors || 0}
                </div>
                <div className="stat-label">Chunks</div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* System Status */}
      <div className="sidebar-section" style={{ borderTop: '1px solid var(--border-subtle)', flex: 'none' }}>
        <h3>System Status</h3>
        <div className="header-status">
          <div className={`status-dot ${status?.ingested ? 'active' : loading ? 'loading' : ''}`} />
          <span>
            {status?.ingested
              ? `Ready — ${status.repo_name}`
              : loading
                ? 'Processing...'
                : 'No repository loaded'}
          </span>
        </div>
      </div>
    </aside>
  );
}
