import React, { useState } from 'react';
import { ExternalLink, GitPullRequest, LoaderCircle, TriangleAlert } from 'lucide-react';
import { createPullRequest } from '../services/api';
import { BRAND } from '../brand';
import { Modal } from './ui';

const EXTENSIONS = {
  python: 'py', py: 'py', javascript: 'js', js: 'js', jsx: 'jsx', typescript: 'ts', ts: 'ts',
  tsx: 'tsx', java: 'java', go: 'go', rust: 'rs', ruby: 'rb', php: 'php', csharp: 'cs',
  cpp: 'cpp', c: 'c', kotlin: 'kt', swift: 'swift', html: 'html', css: 'css', json: 'json',
  yaml: 'yml', yml: 'yml', bash: 'sh', sh: 'sh', sql: 'sql', markdown: 'md',
};

export default function CreatePRModal({ codeBlocks, repoUrl, githubToken, title, onClose }) {
  const [files, setFiles] = useState(() =>
    codeBlocks.map((b, i) => ({
      path: b.filename || `generated/file_${i + 1}.${EXTENSIONS[b.language] || 'txt'}`,
      content: b.code || '',
      language: b.language || 'text',
    })),
  );
  const [branch, setBranch] = useState('');
  const [prTitle, setPrTitle] = useState(title ? `${BRAND.name}: ${title}`.slice(0, 100) : `${BRAND.name}: generated changes`);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const submit = async () => {
    const valid = files.filter((f) => f.path.trim() && f.content.trim());
    if (!repoUrl) return setError('No repository connected.');
    if (!valid.length) return setError('Add at least one file path.');

    setLoading(true);
    setError(null);
    try {
      setResult(await createPullRequest({
        repoUrl,
        githubToken: githubToken || null,
        files: valid.map(({ path, content }) => ({ path: path.trim(), content })),
        branchName: branch.trim() || null,
        commitMessage: prTitle,
        prTitle,
      }));
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to create the pull request.');
    } finally {
      setLoading(false);
    }
  };

  const icon = <GitPullRequest size={18} className="muted" />;

  if (result) {
    return (
      <Modal title="Pull request opened" icon={icon} onClose={onClose}
        footer={<button className="btn btn-outline" onClick={onClose}>Done</button>}>
        <div className="pr-success">
          <div className="pr-success-icon"><GitPullRequest size={20} /></div>
          <h4>{result.message || 'Pull request created'}</h4>
          <p>{result.files_committed?.length || files.length} file(s) committed to <code>{result.branch}</code></p>
          {result.pr_url && (
            <a className="btn btn-primary" href={result.pr_url} target="_blank" rel="noopener noreferrer">
              View on GitHub <ExternalLink size={14} />
            </a>
          )}
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Open a pull request"
      subtitle="Commit the generated code to a new branch"
      icon={icon}
      onClose={onClose}
      footer={(
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={loading}>Cancel</button>
          <button className="btn btn-primary" onClick={submit} disabled={loading}>
            {loading ? <LoaderCircle size={14} className="spin" /> : <GitPullRequest size={14} />}
            {loading ? 'Opening…' : 'Open pull request'}
          </button>
        </>
      )}
    >
      <div className="field">
        <label>Files</label>
        {files.map((f, i) => (
          <div className="file-row" key={i}>
            <input
              className="input mono"
              value={f.path}
              onChange={(e) => setFiles((prev) => prev.map((x, j) => (j === i ? { ...x, path: e.target.value } : x)))}
              placeholder="path/in/repo.py"
            />
            <span className="lang">{f.language}</span>
          </div>
        ))}
        <span className="field-hint">Set the path where each block belongs in the repository.</span>
      </div>
      <div className="field">
        <label htmlFor="pr-title">Title</label>
        <input id="pr-title" className="input" value={prTitle} onChange={(e) => setPrTitle(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="pr-branch">Branch</label>
        <input id="pr-branch" className="input mono" value={branch} onChange={(e) => setBranch(e.target.value)}
          placeholder="Auto-generated if empty" />
      </div>
      {error && (
        <div className="callout danger" style={{ marginBottom: 14 }}>
          <TriangleAlert size={15} /><span>{error}</span>
        </div>
      )}
    </Modal>
  );
}
