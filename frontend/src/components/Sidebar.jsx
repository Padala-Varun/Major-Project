import React from 'react';
import { FolderGit2, Moon, Plus, RefreshCw, Settings, Sun } from 'lucide-react';
import { AGENTS, TEAM_ORDER } from '../agents';
import { BRAND } from '../brand';
import { AgentIcon, BrandMark, splitRepo } from './ui';

function formatCount(n) {
  if (n == null) return '—';
  return n >= 10000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString();
}

function RepoCard({ status, ingesting, onConnect }) {
  if (!status.ingested) {
    return (
      <div className="repo-card">
        <div className="repo-card-head">
          <div className="repo-card-icon"><FolderGit2 size={16} /></div>
          <div className="repo-name">{ingesting ? 'Connecting…' : 'No repository'}</div>
        </div>
        {!ingesting && (
          <>
            <p className="repo-card-empty">Connect a GitHub repository to brief the agent team.</p>
            <button className="btn btn-outline btn-sm btn-block" onClick={onConnect}>
              <Plus size={14} /> Connect repository
            </button>
          </>
        )}
      </div>
    );
  }

  const d = status.details || {};
  const { owner, name } = splitRepo(d.repo?.url, status.repo_name);
  const stats = [
    ['Files', d.repo?.file_count],
    ['Graph nodes', d.graph?.total_nodes],
    ['Edges', d.graph?.total_edges],
    ['Chunks', d.faiss?.total_vectors],
  ];

  return (
    <div className="repo-card">
      <div className="repo-card-head">
        <div className="repo-card-icon"><FolderGit2 size={16} /></div>
        <div style={{ minWidth: 0, flex: 1 }}>
          {owner && <div className="repo-owner">{owner}</div>}
          <div className="repo-name" title={name}>{name}</div>
        </div>
        <button className="icon-btn sm" onClick={onConnect} title="Switch repository">
          <RefreshCw size={13} />
        </button>
      </div>
      <div className="repo-stats">
        {stats.map(([label, value]) => (
          <div className="repo-stat" key={label}>
            <div className="repo-stat-value">{formatCount(value)}</div>
            <div className="repo-stat-label">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Sidebar({
  status, ingesting, workingAgent, open, theme,
  onConnect, onOpenSettings, onToggleTheme,
}) {
  const statusText = status.ingested
    ? 'Ready'
    : ingesting ? 'Indexing repository…' : 'Waiting for a repository';
  const dotClass = status.ingested ? 'ok' : ingesting ? 'busy' : '';

  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand">
        <BrandMark />
        <div>
          <div className="brand-name">{BRAND.name}</div>
          <div className="brand-tag">{BRAND.tagline}</div>
        </div>
      </div>

      <div className="side-scroll">
        <div className="side-label">Repository</div>
        <RepoCard status={status} ingesting={ingesting} onConnect={onConnect} />

        <div className="side-label">Agent team</div>
        {TEAM_ORDER.map((id) => {
          const meta = AGENTS[id];
          const active = workingAgent === id;
          return (
            <div
              key={id}
              className={`team-member ${active ? 'active' : ''}`}
              style={{ '--agent-color': meta.color }}
            >
              <AgentIcon agent={id} />
              <div style={{ minWidth: 0 }}>
                <div className="team-name">{meta.name}</div>
                <div className="team-role">{meta.role}</div>
              </div>
              {active && <span className="team-status">Working</span>}
            </div>
          );
        })}
      </div>

      <div className="side-footer">
        <div className="status-line">
          <span className={`dot ${dotClass}`} />
          <span>{statusText}</span>
        </div>
        <button className="icon-btn" onClick={onToggleTheme} title="Toggle theme">
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button className="icon-btn" onClick={onOpenSettings} title="Settings">
          <Settings size={16} />
        </button>
      </div>
    </aside>
  );
}
