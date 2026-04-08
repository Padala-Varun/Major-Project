import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { sendQuery, createPullRequest } from '../services/api';
import ExplainabilityLog from './ExplainabilityLog';

const AGENT_LABELS = {
  qa: { label: 'Q&A Agent', emoji: '💬' },
  codegen: { label: 'Code Gen Agent', emoji: '⚙️' },
  lld: { label: 'LLD Planning Agent', emoji: '📐' },
  pr: { label: 'PR Analysis Agent', emoji: '🔀' },
};

export default function ChatInterface({ isReady, selectedAgent, prInfo, repoUrl, githubToken }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const query = input.trim();
    if (!query || loading) return;

    const userMsg = { role: 'user', content: query, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const result = await sendQuery(
        query,
        selectedAgent || null,
        prInfo?.repoUrl || null,
        prInfo?.prNumber || null,
      );

      const aiMsg = {
        role: 'ai',
        content: result.response || 'No response generated.',
        agentType: result.agent_type,
        codeBlocks: result.code_blocks || [],
        plan: result.plan || null,
        explanationLog: result.explanation_log || {},
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      const errMsg = {
        role: 'ai',
        content: `**Error:** ${err.response?.data?.detail || err.message || 'Something went wrong.'}`,
        agentType: 'error',
        explanationLog: {},
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isReady) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🚀</div>
        <h3>Welcome to DevCopilot</h3>
        <p>
          Ingest a GitHub repository using the sidebar to get started.
          Once loaded, you can ask questions, generate code, create design plans,
          and analyze pull requests.
        </p>
      </div>
    );
  }

  return (
    <div className="chat-container">
      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">💬</div>
            <h3>Start a conversation</h3>
            <p>
              Ask about the codebase architecture, request code generation,
              create design plans, or analyze pull requests.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            <div className={`chat-avatar ${msg.role}`}>
              {msg.role === 'ai' ? '⚡' : '👤'}
            </div>
            <div>
              {/* Agent Badge */}
              {msg.role === 'ai' && msg.agentType && AGENT_LABELS[msg.agentType] && (
                <div className={`agent-badge ${msg.agentType}`}>
                  {AGENT_LABELS[msg.agentType].emoji} {AGENT_LABELS[msg.agentType].label}
                </div>
              )}

              {/* Message Content */}
              <div className="chat-bubble">
                <ReactMarkdown
                  components={{
                    code({ node, inline, className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '');
                      return !inline && match ? (
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          customStyle={{
                            borderRadius: '8px',
                            margin: '8px 0',
                            fontSize: '0.82rem',
                          }}
                          {...props}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      ) : (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      );
                    },
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              </div>

              {/* Create PR Button — shown for codegen responses with code blocks */}
              {msg.role === 'ai' && msg.agentType === 'codegen' && msg.codeBlocks?.length > 0 && (
                <CreatePRButton
                  codeBlocks={msg.codeBlocks}
                  repoUrl={repoUrl}
                  githubToken={githubToken}
                />
              )}

              {/* Explainability Log */}
              {msg.role === 'ai' && msg.explanationLog && (
                <ExplainabilityLog log={msg.explanationLog} />
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="chat-message ai">
            <div className="chat-avatar ai">⚡</div>
            <div className="chat-bubble">
              <div className="loading-dots">
                <span /><span /><span />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder={
              selectedAgent
                ? `Ask the ${AGENT_LABELS[selectedAgent]?.label || 'agent'}...`
                : 'Ask about the codebase...'
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={1}
            id="chat-input"
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            id="send-btn"
          >
            ▶
          </button>
        </div>
      </div>
    </div>
  );
}


/* ── Create PR Button Component ────────────────────────── */

function CreatePRButton({ codeBlocks, repoUrl, githubToken }) {
  const [showForm, setShowForm] = useState(false);
  const [prLoading, setPrLoading] = useState(false);
  const [prResult, setPrResult] = useState(null);
  const [prError, setPrError] = useState(null);

  const [files, setFiles] = useState(() =>
    codeBlocks.map((block, i) => ({
      path: block.filename || `generated_file_${i + 1}.${block.language || 'txt'}`,
      content: block.code || '',
    }))
  );
  const [branchName, setBranchName] = useState('');
  const [commitMsg, setCommitMsg] = useState('Add code generated by DevCopilot');
  const [prTitle, setPrTitle] = useState('DevCopilot: Generated Code');

  const handleSubmit = async () => {
    if (!repoUrl) {
      setPrError('No repository URL available. Please ingest a repository first.');
      return;
    }

    const validFiles = files.filter((f) => f.path.trim() && f.content.trim());
    if (validFiles.length === 0) {
      setPrError('Please provide at least one file with a path and content.');
      return;
    }

    setPrLoading(true);
    setPrError(null);

    try {
      const result = await createPullRequest({
        repoUrl,
        githubToken,
        files: validFiles,
        branchName: branchName.trim() || null,
        commitMessage: commitMsg,
        prTitle,
      });
      setPrResult(result);
    } catch (err) {
      setPrError(err.response?.data?.detail || err.message || 'Failed to create PR');
    } finally {
      setPrLoading(false);
    }
  };

  const updateFilePath = (index, newPath) => {
    setFiles((prev) => prev.map((f, i) => (i === index ? { ...f, path: newPath } : f)));
  };

  // Success state
  if (prResult) {
    return (
      <div className="pr-result-banner">
        <div className="pr-result-icon">🎉</div>
        <div>
          <strong>{prResult.message}</strong>
          {prResult.pr_url && (
            <div style={{ marginTop: 6 }}>
              <a
                href={prResult.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="pr-link"
              >
                🔗 View Pull Request →
              </a>
            </div>
          )}
          {prResult.files_committed && (
            <div className="pr-files-list">
              {prResult.files_committed.map((f, i) => (
                <span key={i} className="pr-file-chip">{f}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 12 }}>
      {!showForm ? (
        <button className="btn btn-create-pr" onClick={() => setShowForm(true)}>
          🚀 Create Pull Request
        </button>
      ) : (
        <div className="pr-form">
          <h4>📤 Create Pull Request</h4>

          {/* File paths */}
          <div className="pr-form-section">
            <label>Files to commit:</label>
            {files.map((file, i) => (
              <div key={i} className="pr-file-row">
                <input
                  className="input-field"
                  placeholder="e.g., src/auth/login.py"
                  value={file.path}
                  onChange={(e) => updateFilePath(i, e.target.value)}
                />
                <span className="pr-file-lang">{codeBlocks[i]?.language || 'txt'}</span>
              </div>
            ))}
          </div>

          {/* Branch Name */}
          <div className="input-group">
            <label>Branch Name (optional)</label>
            <input
              className="input-field"
              placeholder="devcopilot/feature-name (auto-generated if empty)"
              value={branchName}
              onChange={(e) => setBranchName(e.target.value)}
            />
          </div>

          {/* Commit Message */}
          <div className="input-group">
            <label>Commit Message</label>
            <input
              className="input-field"
              value={commitMsg}
              onChange={(e) => setCommitMsg(e.target.value)}
            />
          </div>

          {/* PR Title */}
          <div className="input-group">
            <label>PR Title</label>
            <input
              className="input-field"
              value={prTitle}
              onChange={(e) => setPrTitle(e.target.value)}
            />
          </div>

          {prError && <div className="error-banner">❌ {prError}</div>}

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={prLoading}
            >
              {prLoading ? (
                <>
                  <div className="loading-spinner" /> Creating PR...
                </>
              ) : (
                '🚀 Send Pull Request'
              )}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => setShowForm(false)}
              disabled={prLoading}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
