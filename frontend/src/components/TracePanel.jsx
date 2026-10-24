import React, { useState } from 'react';
import { ScrollText, X } from 'lucide-react';
import { AGENTS } from '../agents';
import { AgentIcon, useEscape } from './ui';
import { Verdict } from './AgentRun';

function humanize(step) {
  return step.replace(/_/g, ' ');
}

function formatDetails(details) {
  if (details == null) return null;
  if (typeof details === 'string') return details;
  return Object.entries(details)
    .map(([k, v]) => `${humanize(k)}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
    .join(' · ');
}

/** "[qa] faiss_retrieval" → { agent: "qa", label: "faiss retrieval" } */
function parseStep(step) {
  const tagged = /^\[(\w+)\] (.*)$/.exec(step);
  if (tagged) return { agent: tagged[1], label: humanize(tagged[2]) };
  const routed = /^supervisor → (\w+)$/.exec(step);
  if (routed) {
    const next = routed[1];
    return { agent: 'supervisor', label: next === 'finish' ? 'finished the run' : `assigned ${AGENTS[next]?.name || next}` };
  }
  return { agent: null, label: humanize(step) };
}

function Timeline({ log }) {
  const steps = log.reasoning_steps || [];
  if (!steps.length) return <div className="empty-note">No reasoning steps recorded.</div>;
  return steps.map((s, i) => {
    const { agent, label } = parseStep(s.step);
    const detail = formatDetails(s.details);
    return (
      <div className="trace-event" key={i}>
        <span className="trace-time">+{(s.timestamp || 0).toFixed(2)}s</span>
        <div style={{ minWidth: 0 }}>
          <div className="agent-chip">
            {agent && <AgentIcon agent={agent} size="sm" />}
            <span className="trace-step">{AGENTS[agent]?.name || ''} {label}</span>
          </div>
          {detail && (
            <div className={`trace-detail ${typeof s.details === 'object' ? 'mono' : ''}`}>{detail}</div>
          )}
        </div>
      </div>
    );
  });
}

function Agents({ log }) {
  const timeline = log.agent_timeline || [];
  if (!timeline.length) return <div className="empty-note">No agent activity recorded.</div>;
  return timeline.map((t, i) => (
    <div className="trace-event" key={i}>
      <span className="trace-time">{t.duration_seconds}s</span>
      <div>
        <div className="agent-chip">
          <AgentIcon agent={t.agent} size="sm" />
          <span className="trace-step">{AGENTS[t.agent]?.name || t.agent}</span>
          <Verdict approved={t.approved} score={t.score} />
        </div>
        <div className="trace-detail">{t.reason}</div>
      </div>
    </div>
  ));
}

function Sources({ log }) {
  const chunks = log.faiss_chunks_retrieved || [];
  if (!chunks.length) return <div className="empty-note">No code chunks were retrieved.</div>;
  return [...chunks].sort((a, b) => (b.score || 0) - (a.score || 0)).map((c, i) => (
    <div className="source" key={i}>
      <div className="source-top">
        <span className="source-path" title={c.file_path}>{c.file_path}</span>
        {c.start_line != null && <span className="source-lines">L{c.start_line}–{c.end_line}</span>}
        <span className="source-score">{(c.score || 0).toFixed(3)}</span>
      </div>
      <div className="score-bar">
        <span style={{ width: `${Math.min(100, Math.max(0, (c.score || 0) * 100))}%` }} />
      </div>
      {c.entities?.length > 0 && <div className="source-entities">{c.entities.join(', ')}</div>}
    </div>
  ));
}

function GraphNodes({ log }) {
  const nodes = log.graph_nodes_visited || [];
  if (!nodes.length) return <div className="empty-note">No graph nodes were visited.</div>;
  return (
    <div className="node-list">
      {nodes.map((id) => {
        const [kind, ...rest] = id.split(':');
        return (
          <span className="node-chip" key={id} title={id}>
            <span className="node-kind">{kind}</span>
            <span>{rest.join(':') || id}</span>
          </span>
        );
      })}
    </div>
  );
}

const TABS = [
  { id: 'agents', label: 'Agents', count: (l) => l.agent_timeline?.length, Body: Agents },
  { id: 'timeline', label: 'Timeline', count: (l) => l.reasoning_steps?.length, Body: Timeline },
  { id: 'sources', label: 'Sources', count: (l) => l.faiss_chunks_count, Body: Sources },
  { id: 'graph', label: 'Graph', count: (l) => l.graph_nodes_count, Body: GraphNodes },
];

export default function TracePanel({ log, onClose }) {
  const [tab, setTab] = useState('agents');
  useEscape(onClose);
  const { Body } = TABS.find((t) => t.id === tab);

  const stats = [
    [`${log.total_time_seconds ?? 0}s`, 'Total time'],
    [log.agent_timeline?.length ?? 0, 'Agent runs'],
    [log.graph_nodes_count ?? 0, 'Graph nodes'],
    [log.faiss_chunks_count ?? 0, 'Code chunks'],
  ];

  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Reasoning trace">
        <div className="panel-head">
          <ScrollText size={18} className="muted" />
          <div>
            <h3>Reasoning trace</h3>
            <p>How the team reached this answer</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="trace-stats">
          {stats.map(([value, label]) => (
            <div className="trace-stat" key={label}>
              <div className="trace-stat-value">{value}</div>
              <div className="trace-stat-label">{label}</div>
            </div>
          ))}
        </div>
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              <span className="count">{t.count(log) ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="panel-body">
          <Body log={log} />
        </div>
      </aside>
    </>
  );
}
