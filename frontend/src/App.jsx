import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { ArrowLeft, FolderGit2, LoaderCircle, Menu, MessageSquare, Network, SquarePen } from 'lucide-react';
import Sidebar from './components/Sidebar';
import Chat from './components/Chat';
import ConnectRepo from './components/ConnectRepo';
import SettingsModal from './components/SettingsModal';
import { splitRepo } from './components/ui';
import { getStatus } from './services/api';
import { MODES } from './agents';

// The map pulls in the graph renderer; load it only when needed
const RepoMap = lazy(() => import('./components/RepoMap'));

function stored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch { /* storage unavailable */ }
}

const VIEWS = [
  { id: 'map', label: 'Map', icon: Network },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
];

export default function App() {
  const [status, setStatus] = useState({ ingested: false, status: 'idle' });
  const [loaded, setLoaded] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [showConnect, setShowConnect] = useState(false);
  const [theme, setTheme] = useState(() => stored('theme', 'dark'));
  const [view, setView] = useState('map');
  const [modeId, setModeId] = useState('auto');
  const [githubToken, setGithubToken] = useState('');
  const [workingAgent, setWorkingAgent] = useState(null);
  const [chatKey, setChatKey] = useState(0);
  const [pendingPrompt, setPendingPrompt] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Each viewer reopens the repo *they* connected, never someone else's
  useEffect(() => {
    const repo = stored('repo', null);
    if (!repo) {
      setLoaded(true);
      return;
    }
    getStatus(repo)
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    store('theme', theme);
  }, [theme]);

  const handleReady = useCallback((data) => {
    setStatus(data);
    if (data.repo_id) store('repo', data.repo_id);
    setShowConnect(false);
    setChatKey((k) => k + 1);
    setView('map');
  }, []);

  const openConnect = () => {
    setShowConnect(true);
    setSidebarOpen(false);
  };

  const askTeam = (text) => {
    setModeId('auto');
    setView('chat');
    setPendingPrompt({ text, id: Date.now() });
  };

  const mode = MODES.find((m) => m.id === modeId);
  const repoId = status.repo_id;
  const repoUrl = status.details?.repo?.url || '';
  const { owner, name } = splitRepo(repoUrl, status.repo_name);
  const workspaceVisible = loaded && status.ingested && !showConnect;
  const resumeRepo = status.status === 'processing' ? status.repo_id : null;

  return (
    <div className="app">
      <Sidebar
        status={status}
        ingesting={ingesting}
        workingAgent={workingAgent}
        open={sidebarOpen}
        theme={theme}
        onConnect={openConnect}
        onOpenSettings={() => setSettingsOpen(true)}
        onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      />
      {sidebarOpen && <div className="backdrop" style={{ zIndex: 44 }} onClick={() => setSidebarOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <div className="crumbs">
            <FolderGit2 size={15} className="muted" />
            {status.ingested ? (
              <>
                {owner && <span className="muted">{owner} /</span>}
                <strong>{name}</strong>
              </>
            ) : (
              <span className="muted">No repository connected</span>
            )}
          </div>

          {workspaceVisible && (
            <>
              {view === 'chat' && (
                <div className="segmented" role="tablist" aria-label="Mode">
                  {MODES.map((m) => (
                    <button
                      key={m.id}
                      role="tab"
                      aria-selected={m.id === modeId}
                      className={m.id === modeId ? 'active' : ''}
                      onClick={() => setModeId(m.id)}
                      title={m.hint}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
              <div className="segmented view-tabs" role="tablist" aria-label="View">
                {VIEWS.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={view === id}
                    className={view === id ? 'active' : ''}
                    onClick={() => setView(id)}
                  >
                    <Icon size={13} /> {label}
                  </button>
                ))}
              </div>
              {view === 'chat' && (
                <button className="icon-btn" onClick={() => setChatKey((k) => k + 1)} title="New conversation">
                  <SquarePen size={16} />
                </button>
              )}
            </>
          )}
          {showConnect && status.ingested && !ingesting && (
            <button className="btn btn-ghost btn-sm" onClick={() => setShowConnect(false)}>
              <ArrowLeft size={14} /> Back to {name}
            </button>
          )}
        </header>

        {loaded && (workspaceVisible ? (
          <>
            <div className={`map-view ${view === 'map' ? '' : 'hidden'}`}>
              <Suspense fallback={<div className="map-state"><LoaderCircle size={20} className="spin" /></div>}>
                <RepoMap repoId={repoId} theme={theme} onAsk={askTeam} />
              </Suspense>
            </div>
            <Chat
              key={chatKey}
              hidden={view !== 'chat'}
              mode={mode}
              repo={repoId}
              repoUrl={repoUrl}
              githubToken={githubToken}
              onWorkingChange={setWorkingAgent}
              pendingPrompt={pendingPrompt}
            />
          </>
        ) : (
          <div className="chat-scroll">
            <ConnectRepo
              resumeRepo={resumeRepo}
              githubToken={githubToken}
              onGithubTokenChange={setGithubToken}
              onIngestingChange={setIngesting}
              onReady={handleReady}
            />
          </div>
        ))}
      </main>

      {settingsOpen && (
        <SettingsModal
          githubToken={githubToken}
          onSave={setGithubToken}
          onClose={() => setSettingsOpen(false)}
        />
      )}
    </div>
  );
}
