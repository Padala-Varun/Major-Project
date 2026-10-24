import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowUp, Braces, CircleCheck, Compass, GitPullRequest, Network, PencilRuler,
  ScrollText, TriangleAlert,
} from 'lucide-react';
import { streamQuery } from '../services/api';
import { AGENTS } from '../agents';
import { BRAND } from '../brand';
import AgentRun from './AgentRun';
import Markdown from './Markdown';
import TracePanel from './TracePanel';
import CreatePRModal from './CreatePRModal';
import ImpactCard from './ImpactCard';
import { AgentIcon, BrandMark, CopyButton } from './ui';

const SUGGESTIONS = [
  { icon: Compass, title: 'Explain the architecture', text: 'Give me a high-level tour of this codebase: its main modules and how they fit together.' },
  { icon: Network, title: 'Trace a flow', text: 'Walk me through what happens end to end when the main entry point runs.' },
  { icon: PencilRuler, title: 'Plan a change', text: 'Design how we could add structured logging across this project.' },
  { icon: Braces, title: 'Ship an improvement', text: 'Find a function that lacks error handling and implement a robust fix.' },
];

function CriticSummary({ critic, revisions }) {
  if (!critic) return null;
  const rounds = revisions ? ` after ${revisions} revision${revisions > 1 ? 's' : ''}` : '';
  return critic.approved ? (
    <div className="callout success" style={{ marginTop: 14 }}>
      <CircleCheck size={15} />
      <span>
        <strong>Approved by the Critic</strong>
        {critic.score != null && ` · ${critic.score}/10`}{rounds}
      </span>
    </div>
  ) : (
    <div className="callout danger" style={{ marginTop: 14 }}>
      <TriangleAlert size={15} />
      <span>
        <strong>The Critic still has concerns</strong>{rounds}. Review its notes in the agent run before using this code.
      </span>
    </div>
  );
}

/** The answer a finished message shows: the last non-critic agent's output. */
function answerOf(msg) {
  const workers = msg.steps.filter((s) => s.agent !== 'critic');
  return workers.length ? workers[workers.length - 1].response : msg.result?.response;
}

const HISTORY_TURNS = 6;

function AssistantMessage({ msg, query, onTrace, onCreatePR, onShowImpact }) {
  const running = msg.status === 'running';
  const steps = msg.steps;
  const critic = [...steps].reverse().find((s) => s.agent === 'critic');
  const answer = answerOf(msg);
  const impact = msg.result?.impact;
  const showRun = running || steps.length > 1;
  const log = msg.result?.explanation_log;
  const codeBlocks = msg.result?.code_blocks || [];
  const singleAgent = !showRun && steps.length === 1 ? steps[0].agent : null;

  return (
    <div className="msg msg-ai">
      <BrandMark />
      <div className="msg-body">
        <div className="msg-head">
          {BRAND.name}
          {singleAgent && (
            <span className="agent-chip">
              <AgentIcon agent={singleAgent} size="sm" />
              {AGENTS[singleAgent]?.name}
            </span>
          )}
        </div>

        {showRun && (
          <AgentRun
            steps={steps}
            working={msg.working}
            running={running}
            startedAt={msg.startedAt}
            totalSeconds={log?.total_time_seconds}
          />
        )}

        {msg.status === 'error' && (
          <div className="callout danger">
            <TriangleAlert size={15} />
            <span>{msg.error || 'Something went wrong.'}</span>
          </div>
        )}

        {msg.status === 'done' && (
          <>
            <Markdown>{answer || 'No response was generated.'}</Markdown>
            <CriticSummary critic={critic} revisions={log?.revision_count} />
            {impact && <ImpactCard impact={impact} onShowOnMap={() => onShowImpact(impact, query)} />}
            <div className="msg-actions">
              <CopyButton text={answer || ''} label="Copy" />
              {log && Object.keys(log).length > 0 && (
                <button className="btn btn-ghost btn-sm" onClick={() => onTrace(log)}>
                  <ScrollText size={14} /> Reasoning trace
                </button>
              )}
              {codeBlocks.length > 0 && (
                <button className="btn btn-outline btn-sm" onClick={() => onCreatePR({ codeBlocks, title: query, impact, critic })}>
                  <GitPullRequest size={14} /> Open pull request
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function Chat({
  mode, repo, repoUrl, githubToken, onWorkingChange, onShowImpact, hidden, pendingPrompt,
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [prNumber, setPrNumber] = useState('');
  const [busy, setBusy] = useState(false);
  const [trace, setTrace] = useState(null);
  const [prDraft, setPrDraft] = useState(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);

  const send = async (text) => {
    const query = (text ?? input).trim();
    if (!query || busy) return;

    // Earlier turns so follow-ups ("now add tests for that") have context
    const history = messages.flatMap((m) => {
      if (m.role === 'user') return [{ role: 'user', content: m.content }];
      return m.status === 'done' ? [{ role: 'assistant', content: answerOf(m) || '' }] : [];
    }).slice(-HISTORY_TURNS);

    const id = Date.now();
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: query, mode: mode.id === 'auto' ? null : mode.label },
      { id, role: 'ai', status: 'running', steps: [], working: null, result: null, startedAt: Date.now() },
    ]);
    setInput('');
    setBusy(true);

    const update = (fn) => setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));

    try {
      await streamQuery(
        {
          query,
          history,
          repo,
          agentType: mode.agent,
          repoUrl,
          prNumber: mode.id === 'pr' ? Number(prNumber) || null : null,
        },
        (ev) => {
          if (ev.type === 'working') {
            onWorkingChange(ev.agent);
            update((m) => ({ ...m, working: ev.agent }));
          } else if (ev.type === 'step') {
            update((m) => ({ ...m, steps: [...m.steps, ev], working: null }));
          } else if (ev.type === 'final') {
            update((m) => ({
              ...m,
              status: ev.status === 'error' ? 'error' : 'done',
              error: ev.status === 'error' ? ev.response : null,
              result: ev,
              steps: ev.steps?.length ? ev.steps : m.steps,
              working: null,
            }));
          }
        },
      );
    } catch (err) {
      update((m) => ({ ...m, status: 'error', error: err.message || 'Request failed.' }));
    } finally {
      update((m) => (m.status === 'running'
        ? { ...m, status: 'error', error: 'The connection closed before the team finished.' }
        : m));
      setBusy(false);
      onWorkingChange(null);
      inputRef.current?.focus();
    }
  };

  // Prompts sent from the architecture map ("Ask the team", "Plan a change")
  const lastPromptRef = useRef(null);
  useEffect(() => {
    if (pendingPrompt && pendingPrompt.id !== lastPromptRef.current) {
      lastPromptRef.current = pendingPrompt.id;
      send(pendingPrompt.text);
    }
  }, [pendingPrompt]);

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className={`chat ${hidden ? 'hidden' : ''}`}>
      <div className="chat-scroll">
        <div className="chat-column">
          {messages.length === 0 ? (
            <div className="welcome">
              <h2>What should the team work on?</h2>
              <p>Ask a question, request a design, or have the agents write and review code.</p>
              <div className="suggestions">
                {SUGGESTIONS.map(({ icon: Icon, title, text }) => (
                  <button key={title} className="suggestion" onClick={() => send(text)}>
                    <Icon size={17} className="muted" style={{ marginTop: 1, flexShrink: 0 }} />
                    <div>
                      <div className="suggestion-title">{title}</div>
                      <div className="suggestion-text">{text}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (msg.role === 'user' ? (
              <div className="msg" key={i}>
                <div className="msg-user"><div className="bubble">{msg.content}</div></div>
                {msg.mode && <div className="msg-user msg-meta">{msg.mode} mode</div>}
              </div>
            ) : (
              <AssistantMessage
                key={msg.id}
                msg={msg}
                query={messages[i - 1]?.content}
                onTrace={setTrace}
                onCreatePR={setPrDraft}
                onShowImpact={onShowImpact}
              />
            )))
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="composer">
        <div className="composer-box">
          <textarea
            ref={inputRef}
            className="composer-input"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={mode.id === 'pr' ? 'What should the Reviewer look for?' : 'Ask the team anything about this codebase…'}
            aria-label="Message"
          />
          <div className="composer-foot">
            <span className="composer-mode"><strong>{mode.label}</strong> · {mode.hint}</span>
            {mode.id === 'pr' && (
              <label className="pr-input">
                PR #
                <input
                  inputMode="numeric"
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value.replace(/\D/g, ''))}
                  placeholder="all"
                />
              </label>
            )}
            <button className="send-btn" onClick={() => send()} disabled={busy || !input.trim()} aria-label="Send">
              <ArrowUp size={16} strokeWidth={2.5} />
            </button>
          </div>
        </div>
        <div className="composer-hint">
          <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
        </div>
      </div>

      {trace && <TracePanel log={trace} onClose={() => setTrace(null)} />}
      {prDraft && (
        <CreatePRModal
          codeBlocks={prDraft.codeBlocks}
          title={prDraft.title}
          impact={prDraft.impact}
          critic={prDraft.critic}
          repoUrl={repoUrl}
          githubToken={githubToken}
          onClose={() => setPrDraft(null)}
        />
      )}
    </div>
  );
}
