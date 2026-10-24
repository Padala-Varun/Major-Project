import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight, Check, ChevronRight, Clock, FolderGit2, Github, KeyRound, LoaderCircle,
  Network, ShieldCheck, Sparkles, TriangleAlert, Workflow,
} from 'lucide-react';
import { getRepos, getStatus, ingestRepository } from '../services/api';
import { repoIdFromUrl, splitRepo } from './ui';

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_MS = 10 * 60 * 1000;

const STAGES = [
  { id: 'clone', label: 'Cloning repository' },
  { id: 'parse', label: 'Parsing source files' },
  { id: 'graph', label: 'Building knowledge graph' },
  { id: 'embed', label: 'Embedding code chunks' },
  { id: 'index', label: 'Indexing for retrieval' },
];

const EXAMPLES = ['psf/requests', 'pallets/flask', 'expressjs/express'];

const FEATURES = [
  { icon: Network, title: 'Understands structure', text: 'Maps every file, class and import into a knowledge graph.' },
  { icon: Workflow, title: 'Works as a team', text: 'A supervisor coordinates specialist agents per request.' },
  { icon: ShieldCheck, title: 'Checks its own work', text: 'A critic reviews generated code before you see it.' },
];

function timeAgo(epochSeconds) {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function describeError(err) {
  if (!err.response) return 'Cannot reach the backend. Start it with: cd backend && python main.py';
  const detail = err.response.data?.detail;
  if (detail?.message) return detail.message;
  if (typeof detail === 'string') {
    return detail === 'Not Found'
      ? 'API endpoint not found. Check that VITE_API_BASE ends with /api.'
      : detail;
  }
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join(', ');
  return err.message || 'Ingestion failed';
}

export default function ConnectRepo({ resumeRepo, githubToken, onGithubTokenChange, onIngestingChange, onReady }) {
  const [url, setUrl] = useState('');
  const [recent, setRecent] = useState([]);
  const [showToken, setShowToken] = useState(false);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(null);
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const pollRef = useRef(null);
  const startedRef = useRef(null);

  const stop = useCallback(() => {
    clearInterval(pollRef.current);
    pollRef.current = null;
    setRunning(false);
    onIngestingChange(false);
  }, [onIngestingChange]);

  const poll = useCallback((repoId) => {
    clearInterval(pollRef.current);
    startedRef.current = Date.now();
    setRunning(true);
    onIngestingChange(true);

    const tick = async () => {
      setElapsed(Math.floor((Date.now() - startedRef.current) / 1000));
      if (Date.now() - startedRef.current > MAX_POLL_MS) {
        stop();
        setError('Ingestion timed out. Check the backend logs and try again.');
        return;
      }
      try {
        const data = await getStatus(repoId);
        if (data.ingested || data.status === 'done') {
          stop();
          onReady(data);
        } else if (data.status === 'error') {
          stop();
          setError(data.error || 'Ingestion failed on the server.');
        } else if (data.stage) {
          setStage(data.stage);
        }
      } catch {
        // Transient network error: keep polling
      }
    };

    tick();
    pollRef.current = setInterval(tick, POLL_INTERVAL_MS);
  }, [onIngestingChange, onReady, stop]);

  useEffect(() => {
    if (resumeRepo) poll(resumeRepo);
    return () => clearInterval(pollRef.current);
  }, [resumeRepo, poll]);

  useEffect(() => {
    getRepos().then((d) => setRecent(d.repos || [])).catch(() => {});
  }, []);

  const start = async (repoUrl = url) => {
    const target = repoUrl.trim();
    if (!target || running) return;
    setUrl(target);
    setError(null);
    setStage('clone');
    try {
      const res = await ingestRepository(target, githubToken.trim() || null);
      if (res.status === 'done') {
        onReady(await getStatus(res.repo_id));  // indexed before: opens instantly
      } else {
        poll(res.repo_id);
      }
    } catch (err) {
      const busyWith = err.response?.status === 409 && err.response.data?.detail?.repo_id;
      if (busyWith && busyWith === repoIdFromUrl(target)) poll(busyWith);  // already running: follow it
      else setError(describeError(err));
    }
  };

  const activeIndex = Math.max(0, STAGES.findIndex((s) => s.id === stage));
  const { owner, name } = splitRepo(url, 'repository');

  return (
    <div className="connect">
      <div className="connect-inner">
        {running ? (
          <div className="ingest">
            <div className="ingest-head">
              <div className="repo-card-icon"><Github size={16} /></div>
              <div style={{ minWidth: 0 }}>
                {owner && <div className="repo-owner">{owner}</div>}
                <div className="repo-name">{url ? name : 'Repository'}</div>
              </div>
              <span className="ingest-time">
                {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}
              </span>
            </div>
            <ol className="stages">
              {STAGES.map((s, i) => {
                const state = i < activeIndex ? 'done' : i === activeIndex ? 'active' : '';
                return (
                  <li key={s.id} className={`stage ${state}`}>
                    <span className="stage-icon">
                      {state === 'done' && <Check size={12} strokeWidth={3} />}
                      {state === 'active' && <LoaderCircle size={13} className="spin" />}
                    </span>
                    {s.label}
                    {state === 'active' && <span className="stage-detail">In progress</span>}
                  </li>
                );
              })}
            </ol>
          </div>
        ) : (
          <>
            <div className="eyebrow"><Sparkles size={13} /> Multi-agent codebase engineering</div>
            <h1>Take over <em>any codebase</em><br />in minutes.</h1>
            <p className="connect-sub">
              Connect a GitHub repository. The agent team maps its structure, then explores,
              plans, writes and reviews code with you.
            </p>

            <form
              className="repo-input"
              onSubmit={(e) => { e.preventDefault(); start(); }}
            >
              <Github size={18} />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                spellCheck={false}
                autoFocus
                aria-label="GitHub repository URL"
              />
              <button className="btn btn-primary" type="submit" disabled={!url.trim()}>
                Connect <ArrowRight size={15} />
              </button>
            </form>

            <div className="examples">
              Try
              {EXAMPLES.map((ex) => (
                <button key={ex} className="example" onClick={() => start(`https://github.com/${ex}`)}>
                  {ex}
                </button>
              ))}
            </div>

            {showToken ? (
              <div className="token-row field">
                <label htmlFor="connect-token">GitHub token</label>
                <input
                  id="connect-token"
                  className="input mono"
                  type="password"
                  placeholder="github_pat_…"
                  value={githubToken}
                  onChange={(e) => onGithubTokenChange(e.target.value)}
                />
                <span className="field-hint">Only needed for private repositories. Kept in memory for this session.</span>
              </div>
            ) : (
              <button className="token-toggle" onClick={() => setShowToken(true)}>
                <KeyRound size={13} /> Private repository? Add a token
              </button>
            )}

            {recent.length > 0 && (
              <div className="recent">
                <div className="side-label"><Clock size={11} /> Recently analyzed</div>
                {recent.slice(0, 4).map((r) => {
                  const { owner, name: repoName } = splitRepo(r.repo_url, r.repo_name);
                  return (
                    <button key={r.id} className="recent-item" onClick={() => start(r.repo_url)}>
                      <span className="repo-card-icon"><FolderGit2 size={15} /></span>
                      <span className="recent-name">
                        {owner && <span className="muted">{owner} / </span>}{repoName}
                      </span>
                      <span className="recent-meta">{r.file_count} files · {timeAgo(r.ingested_at)}</span>
                      <ChevronRight size={15} className="muted" />
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}

        {error && (
          <div className="callout danger" style={{ marginTop: 16 }}>
            <TriangleAlert size={15} />
            <span>{error}</span>
          </div>
        )}

        {!running && (
          <div className="features">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <div className="feature" key={title}>
                <Icon size={18} />
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
