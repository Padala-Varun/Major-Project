import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { getStatus } from './services/api';

const AGENTS = [
  { id: null, label: 'Auto-Route', emoji: '🤖' },
  { id: 'qa', label: 'Q&A', emoji: '💬' },
  { id: 'codegen', label: 'Code Gen', emoji: '⚙️' },
  { id: 'lld', label: 'LLD Plan', emoji: '📐' },
  { id: 'pr', label: 'PR Analysis', emoji: '🔀' },
];

export default function App() {
  const [status, setStatus] = useState({ ingested: false, status: 'idle' });
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [prInfo, setPrInfo] = useState({ repoUrl: '', prNumber: '' });
  const [repoUrl, setRepoUrl] = useState('');
  const [githubToken, setGithubToken] = useState('');

  // Check status on mount
  useEffect(() => {
    getStatus()
      .then(setStatus)
      .catch(() => {});
  }, []);

  const handleIngested = (data) => {
    // Accept both old IngestResponse shape and new status poll shape
    if (data.details) {
      // Coming from status poll — already in the right format
      setStatus(data);
    } else {
      setStatus({
        ingested: true,
        repo_name: data.repo_name,
        status: 'done',
        details: {
          repo: { file_count: data.file_count },
          graph: { total_nodes: data.graph_nodes, total_edges: data.graph_edges },
          faiss: { total_vectors: data.chunks_indexed },
        },
      });
    }
  };

  return (
    <div className="app-container">
      <Sidebar
        status={status}
        onIngested={handleIngested}
        onRepoUrlChange={setRepoUrl}
        onGithubTokenChange={setGithubToken}
      />

      <div className="main-content">
        {/* Header with tabs */}
        <div className="content-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
            <div className="header-status">
              <div className={`status-dot ${status.ingested ? 'active' : ''}`} />
              <span style={{ fontWeight: 500 }}>
                {status.ingested ? status.repo_name : 'No Repository'}
              </span>
            </div>

            {/* Agent Selector */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {AGENTS.map((agent) => (
                <button
                  key={agent.id || 'auto'}
                  className={`agent-selector-btn ${selectedAgent === agent.id ? 'selected' : ''}`}
                  onClick={() => setSelectedAgent(agent.id)}
                  id={`agent-${agent.id || 'auto'}`}
                >
                  {agent.emoji} {agent.label}
                </button>
              ))}
            </div>
          </div>

          {/* PR Info (shown when PR agent selected) */}
          {selectedAgent === 'pr' && (
            <div style={{
              display: 'flex', gap: 12, marginTop: 12,
              paddingTop: 12, borderTop: '1px solid var(--border-subtle)',
            }}>
              <div className="input-group" style={{ flex: 1, marginBottom: 0 }}>
                <label>PR Repository URL</label>
                <input
                  className="input-field"
                  placeholder="https://github.com/user/repo"
                  value={prInfo.repoUrl}
                  onChange={(e) => setPrInfo((p) => ({ ...p, repoUrl: e.target.value }))}
                />
              </div>
              <div className="input-group" style={{ width: 120, marginBottom: 0 }}>
                <label>PR Number</label>
                <input
                  className="input-field"
                  placeholder="#123"
                  type="number"
                  value={prInfo.prNumber}
                  onChange={(e) => setPrInfo((p) => ({ ...p, prNumber: parseInt(e.target.value) || '' }))}
                />
              </div>
            </div>
          )}
        </div>

        {/* Chat Interface */}
        <ChatInterface
          isReady={status.ingested}
          selectedAgent={selectedAgent}
          prInfo={prInfo}
          repoUrl={repoUrl}
          githubToken={githubToken}
        />
      </div>
    </div>
  );
}
