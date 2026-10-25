import React, { useState } from 'react';
import {
  Check, ChevronDown, ChevronRight, CircleCheck, CircleX, ExternalLink, FileDiff, FlaskConical,
  GitPullRequest, Info, LoaderCircle, Minus, TriangleAlert, Wrench,
} from 'lucide-react';
import { prepareChanges, streamVerify } from '../services/api';

const STAGES = [
  ['sandbox', 'Start an isolated sandbox'],
  ['clone', 'Clone the repository'],
  ['install', 'Install dependencies'],
  ['baseline', 'Run tests on the current code'],
  ['apply', 'Apply the change'],
  ['tests', 'Run tests with the change'],
  ['preview', 'Start a live preview'],
];

export function DiffView({ diff }) {
  if (!diff) return <div className="empty-note">No changes.</div>;
  return (
    <pre className="diff">
      {diff.split('\n').map((line, i) => {
        const kind = line.startsWith('@@') ? 'hunk'
          : line.startsWith('+++') || line.startsWith('---') ? 'meta'
            : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : '';
        return <div key={i} className={`diff-line ${kind}`}>{line || ' '}</div>;
      })}
    </pre>
  );
}

function StageIcon({ status }) {
  if (status === 'running') return <LoaderCircle size={13} className="spin" />;
  if (status === 'done') return <Check size={12} strokeWidth={3} />;
  if (status === 'failed') return <CircleX size={13} />;
  if (status === 'warning') return <TriangleAlert size={12} />;
  if (status === 'skipped') return <Minus size={12} />;
  return null;
}

function VerifyResult({ result, onFix }) {
  const [showLog, setShowLog] = useState(false);
  const [frameLoaded, setFrameLoaded] = useState(false);
  const tone = { pass: 'success', fail: 'danger', error: 'danger', no_tests: '' }[result.verdict];
  const Icon = { pass: CircleCheck, fail: CircleX, error: TriangleAlert, no_tests: Info }[result.verdict] || Info;
  const title = {
    pass: 'Verified', fail: 'Tests failed', error: "Couldn't verify", no_tests: 'No tests to run',
  }[result.verdict];

  return (
    <>
      <div className={`callout ${tone}`} style={{ marginTop: 10 }}>
        <Icon size={15} />
        <span><strong>{title}.</strong> {result.summary}</span>
      </div>
      {result.preview_url && (
        <div className="preview">
          <div className="preview-head">
            <span><strong>Live preview</strong> · available for about {result.preview_minutes} minutes</span>
            <a className="btn btn-outline btn-sm" href={result.preview_url} target="_blank" rel="noopener noreferrer">
              Open <ExternalLink size={13} />
            </a>
          </div>
          <div className="preview-body">
            {!frameLoaded && (
              <div className="preview-loading"><LoaderCircle size={16} className="spin" /> Loading preview…</div>
            )}
            <iframe
              className="preview-frame"
              src={result.preview_url}
              title="Live preview of the change"
              onLoad={() => setFrameLoaded(true)}
            />
          </div>
        </div>
      )}
      <div className="msg-actions">
        {result.verdict === 'fail' && onFix && (
          <button className="btn btn-primary btn-sm" onClick={onFix}>
            <Wrench size={14} /> Ask the Engineer to fix
          </button>
        )}
        {result.output && (
          <button className="btn btn-ghost btn-sm" onClick={() => setShowLog(!showLog)}>
            {showLog ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Test output
          </button>
        )}
      </div>
      {showLog && <pre className="diff log">{result.output}</pre>}
    </>
  );
}

/**
 * Ship a generated change: review the exact diff, verify it in a sandbox, open a PR.
 * `onPrepared` hands the prepared files (and verification) to the PR dialog.
 */
export default function ChangeReview({ codeBlocks, task, repo, githubToken, baseFiles, onOpenPR, onAsk }) {
  const [prepared, setPrepared] = useState({ status: 'idle', files: [], error: null });
  const [openDiff, setOpenDiff] = useState(null);
  const [preview, setPreview] = useState(false);
  const [verify, setVerify] = useState({ status: 'idle', stages: {}, result: null });

  const ensurePrepared = async () => {
    if (prepared.status === 'ready') return prepared.files;
    setPrepared({ status: 'loading', files: [], error: null });
    try {
      // A follow-up fix builds on the previous round's files instead of the repository's
      const { files } = await prepareChanges(repo, codeBlocks, task, githubToken || null, baseFiles);
      setPrepared({ status: 'ready', files, error: null });
      return files;
    } catch (err) {
      setPrepared({ status: 'error', files: [], error: err.response?.data?.detail || err.message });
      return null;
    }
  };

  const runVerify = async () => {
    const files = await ensurePrepared();
    if (!files?.length) return;
    setVerify({ status: 'running', stages: {}, result: null });
    try {
      await streamVerify({ repo, files, preview, githubToken }, (ev) => {
        if (ev.type === 'stage') {
          setVerify((v) => ({ ...v, stages: { ...v.stages, [ev.stage]: ev } }));
        } else if (ev.type === 'done') {
          setVerify((v) => ({ ...v, status: 'done', result: ev }));
        }
      });
    } catch (err) {
      setVerify((v) => ({ ...v, status: 'done', result: { verdict: 'error', summary: err.message } }));
    }
  };

  const openPR = async () => {
    const files = await ensurePrepared();
    if (files?.length) onOpenPR(files, verify.result);
  };

  const fixFailures = () => {
    const output = verify.result.output || '';
    const diffs = files.map((f) => f.diff).join('\n\n');
    const failing = output.split('\n').filter((l) => /^(FAILED|ERROR) /.test(l)).slice(0, 15);
    onAsk(
      `The sandbox test run failed for your change: ${verify.result.summary}\n\n`
      + (failing.length ? `Failing tests:\n${failing.join('\n')}\n\n` : '')
      + `Fix it so every test passes. If a failing test is one you added and its expectation is wrong, `
      + `correct that test; don't change the repository's existing tests to make them pass. `
      + `Return complete files with their paths for every file you change; files you don't return stay as they are.\n\n`
      + `Test output:\n${output.slice(-3000)}\n\n`
      + `Your current change (diff against the repository):\n${diffs.slice(0, 6000)}`,
      { baseFiles: files },
    );
  };

  const busy = prepared.status === 'loading' || verify.status === 'running';
  const files = prepared.files;

  return (
    <div className="changes">
      <div className="impact-head">
        <FileDiff size={15} className="muted" />
        <span className="impact-title">Ship this change</span>
        {prepared.status === 'ready' && (
          <span className="impact-meta">{files.length} file{files.length === 1 ? '' : 's'}</span>
        )}
      </div>

      {prepared.status === 'idle' && (
        <p className="impact-summary">
          Review the exact diff, run the repository's tests on it in a sandbox, then open a pull request.
        </p>
      )}
      {prepared.status === 'loading' && (
        <p className="impact-summary"><LoaderCircle size={13} className="spin" /> Preparing complete files and diffs…</p>
      )}
      {prepared.status === 'error' && (
        <div className="callout danger" style={{ margin: '8px 0' }}><TriangleAlert size={15} /><span>{prepared.error}</span></div>
      )}
      {prepared.status === 'ready' && files.length === 0 && (
        <p className="impact-summary">None of the code blocks name a file in the repository, so there's nothing to apply.</p>
      )}

      {files.map((f) => (
        <div key={f.path}>
          <button className="impact-file change-file" onClick={() => setOpenDiff(openDiff === f.path ? null : f.path)}>
            {openDiff === f.path ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <span className={`impact-status ${f.status}`}>
              {f.status === 'new' ? 'New' : f.merged ? 'Merged' : f.status === 'fragment' ? 'Partial' : 'Modified'}
            </span>
            <span className="impact-path" title={f.path}>{f.path}</span>
            <span className="impact-meta"><span className="add">+{f.additions}</span> <span className="del">−{f.deletions}</span></span>
          </button>
          {openDiff === f.path && (
            <>
              {f.note && <div className="change-note">{f.note}</div>}
              <DiffView diff={f.diff} />
            </>
          )}
        </div>
      ))}

      {verify.status !== 'idle' && (
        <ol className="stages verify-stages">
          {STAGES.filter(([id]) => id !== 'preview' || preview).map(([id, label]) => {
            const s = verify.stages[id];
            return (
              <li key={id} className={`stage ${s?.status === 'done' ? 'done' : s?.status === 'running' ? 'active' : ''} ${s?.status || ''}`}>
                <span className="stage-icon"><StageIcon status={s?.status} /></span>
                {label}
                {s?.detail && <span className="stage-detail" title={s.detail}>{s.detail}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {verify.result && <VerifyResult result={verify.result} onFix={onAsk ? fixFailures : null} />}

      <div className="msg-actions">
        {prepared.status === 'idle' && (
          <button className="btn btn-ghost btn-sm" onClick={ensurePrepared} disabled={busy}>
            <FileDiff size={14} /> Review diff
          </button>
        )}
        <button className="btn btn-outline btn-sm" onClick={runVerify} disabled={busy || files.length === 0 && prepared.status === 'ready'}>
          {verify.status === 'running' ? <LoaderCircle size={14} className="spin" /> : <FlaskConical size={14} />}
          {verify.status === 'running' ? 'Verifying…' : verify.result ? 'Verify again' : 'Verify in sandbox'}
        </button>
        <button className="btn btn-primary btn-sm" onClick={openPR} disabled={busy || files.length === 0 && prepared.status === 'ready'}>
          <GitPullRequest size={14} /> Open pull request
        </button>
        <label className="preview-toggle">
          <input type="checkbox" className="file-check" checked={preview} onChange={(e) => setPreview(e.target.checked)} disabled={busy} />
          Live preview (web apps)
        </label>
      </div>
    </div>
  );
}
