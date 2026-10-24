import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, CircleCheck, CircleX } from 'lucide-react';
import { AGENTS } from '../agents';
import Markdown from './Markdown';
import { AgentIcon } from './ui';

function useElapsed(startedAt, running) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}

export function Verdict({ approved, score }) {
  if (approved == null) return null;
  const Icon = approved ? CircleCheck : CircleX;
  return (
    <span className={`verdict ${approved ? 'pass' : 'fail'}`}>
      <Icon size={11} strokeWidth={2.5} />
      {approved ? 'Approved' : 'Changes requested'}
      {score != null && ` · ${score}/10`}
    </span>
  );
}

function Step({ step }) {
  const [open, setOpen] = useState(false);
  const meta = AGENTS[step.agent];
  return (
    <li className="run-step">
      <AgentIcon agent={step.agent} />
      <div style={{ minWidth: 0 }}>
        <div className="run-step-top">
          <span className="run-step-name">{meta?.name || step.agent}</span>
          {step.error
            ? <span className="verdict fail"><CircleX size={11} strokeWidth={2.5} />Failed</span>
            : <Verdict approved={step.approved} score={step.score} />}
          <span className="run-step-time">{step.duration_seconds?.toFixed(1)}s</span>
        </div>
        <div className="run-step-reason">{step.reason}</div>
        <button className="run-step-toggle" onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {open ? 'Hide output' : 'Show output'}
        </button>
        {open && (
          <div className="run-step-output">
            <Markdown>{step.response}</Markdown>
          </div>
        )}
      </div>
    </li>
  );
}

export default function AgentRun({ steps, working, running, startedAt, totalSeconds }) {
  const [open, setOpen] = useState(true);
  const elapsed = useElapsed(startedAt, running);

  // Collapse once the run finishes; the answer below is what matters then
  useEffect(() => {
    if (!running) setOpen(false);
  }, [running]);

  const agents = [...new Set(steps.map((s) => s.agent))];
  const seconds = running ? elapsed : Math.round(totalSeconds || 0);
  const workingMeta = AGENTS[working];

  return (
    <div className="run">
      <button className="run-head" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <span className={`run-title ${running ? 'shimmer' : ''}`}>
          {running ? 'Agent team working' : 'Agent team run'}
        </span>
        <span className="run-meta">
          {steps.length} step{steps.length === 1 ? '' : 's'} · {seconds}s
        </span>
        <span className="run-avatars">
          {agents.map((a) => <AgentIcon key={a} agent={a} size="sm" />)}
        </span>
      </button>

      {open && (
        <ol className="run-steps">
          {steps.map((s, i) => <Step key={i} step={s} />)}
          {running && workingMeta && (
            <li className="run-step working">
              <AgentIcon agent={working} />
              <div>
                <div className="run-step-top">
                  <span className="run-step-name shimmer">{workingMeta.name} is working…</span>
                </div>
                <div className="run-step-reason">{workingMeta.role}</div>
              </div>
            </li>
          )}
          {running && !workingMeta && (
            <li className="run-step working">
              <AgentIcon agent="supervisor" />
              <div className="run-step-top">
                <span className="run-step-name shimmer">
                  {steps.length ? 'Supervisor is deciding the next step…' : 'Retrieving context from the knowledge graph…'}
                </span>
              </div>
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
