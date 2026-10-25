/**
 * ShipSafe API Service
 * Handles all communication with the FastAPI backend.
 */

import axios from 'axios';

const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');

const api = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 min default timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Ingest a GitHub repository.
 * @param {string} repoUrl - GitHub repository URL
 * @param {string} [githubToken] - Optional GitHub access token
 * @param {boolean} [refresh] - Re-index even if the repo was ingested before
 * @returns {Promise<Object>} { status: "processing" | "done", repo_id }
 */
export async function ingestRepository(repoUrl, githubToken = null, refresh = false) {
  const payload = { repo_url: repoUrl, refresh };
  if (githubToken) {
    payload.github_token = githubToken;
  }
  const response = await api.post('/ingest', payload, { timeout: 30000 }); // Backend returns immediately
  return response.data;
}

/**
 * Send a query to the multi-agent system.
 * @param {string} query - User's question or request
 * @param {string} [agentType] - Force specific agent (qa, codegen, lld, pr)
 * @param {string} [repoUrl] - Repo URL for PR analysis
 * @param {number} [prNumber] - PR number for analysis
 * @returns {Promise<Object>} Agent response with explanation log
 */
export async function sendQuery(query, agentType = null, repoUrl = null, prNumber = null, repo = null) {
  const payload = { query };
  if (repo) payload.repo = repo;
  if (agentType) payload.agent_type = agentType;
  if (repoUrl) payload.repo_url = repoUrl;
  if (prNumber) payload.pr_number = prNumber;

  const response = await api.post('/query', payload, { timeout: 300000 });
  return response.data;
}

/**
 * Send a query and receive agent progress as it happens.
 * Falls back to the blocking /query endpoint on backends without streaming.
 * @param {Object} params - { query, repo, agentType, repoUrl, prNumber }
 * @param {(event: Object) => void} onEvent - called per event; the last has type "final"
 */
export async function streamQuery({ query, history, repo, agentType, repoUrl, prNumber, requireCode }, onEvent) {
  const payload = { query };
  if (requireCode) payload.require_code = true;
  if (history?.length) payload.history = history;
  if (repo) payload.repo = repo;
  if (agentType) payload.agent_type = agentType;
  if (repoUrl) payload.repo_url = repoUrl;
  if (prNumber) payload.pr_number = prNumber;

  const res = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (res.status === 404 || res.status === 405) {
    const result = await sendQuery(query, agentType, repoUrl, prNumber, repo);
    onEvent({ type: 'final', ...result });
    return;
  }
  await readEvents(res, onEvent);
}

/** Read a Server-Sent Events response, calling onEvent for each JSON event. */
async function readEvents(res, onEvent) {
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop();
    for (const frame of frames) {
      const data = frame.split('\n').find((l) => l.startsWith('data: '));
      if (data) onEvent(JSON.parse(data.slice(6)));
    }
  }
}

/**
 * Fetch a GitHub issue (URL or "#42") with the task the agent team should work from.
 * @returns {Promise<Object>} { number, title, body, labels, url, comments, task }
 */
export async function getIssue(repo, ref, githubToken = null) {
  const params = { repo, ref };
  if (githubToken) params.github_token = githubToken;
  const response = await api.get('/issue', { params });
  return response.data;
}

/**
 * Turn generated code blocks into complete files with diffs (fragments are merged
 * into the existing files on GitHub).
 * @returns {Promise<Object>} { files: [{ path, status, content, diff, additions, deletions, merged, note }] }
 */
export async function prepareChanges(repo, codeBlocks, task, githubToken = null, baseFiles = null) {
  const payload = { repo, task, code_blocks: codeBlocks.map(({ code, language, filename }) => ({ code, language, filename })) };
  if (baseFiles?.length) payload.base_files = baseFiles;
  if (githubToken) payload.github_token = githubToken;
  const response = await api.post('/changes/prepare', payload, { timeout: 300000 });
  return response.data;
}

/**
 * Run the repo's tests on the change in a sandbox, streaming progress.
 * @param {Object} params - { repo, files: [{path, content}], preview, githubToken }
 * @param {(event: Object) => void} onEvent - stage events, then a final "done" event
 */
export async function streamVerify({ repo, files, preview, githubToken }, onEvent) {
  const payload = { repo, files: files.map(({ path, content }) => ({ path, content })), preview: Boolean(preview) };
  if (githubToken) payload.github_token = githubToken;
  const res = await fetch(`${API_BASE}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await readEvents(res, onEvent);
}

/**
 * One-page onboarding brief for the repository (generated once, then cached).
 * @returns {Promise<Object>} { markdown, generated_at }
 */
export async function getBrief(repo, refresh = false) {
  const response = await api.get('/brief', { params: { repo, refresh }, timeout: 180000 });
  return response.data;
}

/**
 * Get ingestion status and stats for a repository.
 * @param {string} [repo] - Repo id (defaults to the server's last ingested repo)
 * @returns {Promise<Object>} Status with ingestion state and stats
 */
export async function getStatus(repo = null) {
  const response = await api.get('/status', { params: repo ? { repo } : {} });
  return response.data;
}

/**
 * Repositories saved on the server, most recent first.
 * @returns {Promise<Object>} { repos: [...], processing: repoId | null }
 */
export async function getRepos() {
  const response = await api.get('/repos');
  return response.data;
}

/**
 * Architecture map: file dependency graph with modules, entry points and risk.
 * @param {string} repo - Repo id
 * @returns {Promise<Object>} { nodes, links, modules, hotspots, entry_points, stats }
 */
export async function getGraph(repo) {
  const response = await api.get('/graph', { params: { repo } });
  return response.data;
}

/**
 * Get knowledge graph statistics.
 * @returns {Promise<Object>} Graph stats with sample nodes
 */
export async function getGraphStats() {
  const response = await api.get('/graph-stats');
  return response.data;
}

/**
 * Create a GitHub Pull Request with generated code.
 * @param {Object} params - PR creation parameters
 * @returns {Promise<Object>} PR result with pr_url, pr_number
 */
export async function createPullRequest({ repoUrl, githubToken, files, branchName, commitMessage, prTitle, prBody }) {
  const payload = {
    repo_url: repoUrl,
    files,
    commit_message: commitMessage || 'Add code generated by ShipSafe',
    pr_title: prTitle || 'ShipSafe: Generated Code',
  };
  if (githubToken) payload.github_token = githubToken;
  if (branchName) payload.branch_name = branchName;
  if (prBody) payload.pr_body = prBody;

  const response = await api.post('/create-pr', payload, { timeout: 60000 });
  return response.data;
}

export default api;
