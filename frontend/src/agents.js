import { Workflow, Compass, PencilRuler, Braces, ShieldCheck, GitPullRequest } from 'lucide-react';

/** The agent team, keyed by backend agent id. */
export const AGENTS = {
  supervisor: { name: 'Supervisor', role: 'Coordinates the team', icon: Workflow, color: 'var(--agent-supervisor)' },
  qa: { name: 'Explorer', role: 'Investigates the codebase', icon: Compass, color: 'var(--agent-qa)' },
  lld: { name: 'Architect', role: 'Designs the change', icon: PencilRuler, color: 'var(--agent-lld)' },
  codegen: { name: 'Engineer', role: 'Writes the code', icon: Braces, color: 'var(--agent-codegen)' },
  critic: { name: 'Critic', role: 'Reviews every change', icon: ShieldCheck, color: 'var(--agent-critic)' },
  pr: { name: 'Reviewer', role: 'Analyzes pull requests', icon: GitPullRequest, color: 'var(--agent-pr)' },
};

export const TEAM_ORDER = ['supervisor', 'qa', 'lld', 'codegen', 'critic', 'pr'];

/** Composer modes. `agent: null` lets the supervisor assemble the team. */
export const MODES = [
  { id: 'auto', agent: null, label: 'Team', hint: 'Supervisor picks the agents' },
  { id: 'fix', agent: null, label: 'Fix issue', hint: 'The team fixes a GitHub issue end to end' },
  { id: 'qa', agent: 'qa', label: 'Ask', hint: 'Explorer only' },
  { id: 'lld', agent: 'lld', label: 'Plan', hint: 'Architect only' },
  { id: 'codegen', agent: 'codegen', label: 'Code', hint: 'Engineer + Critic' },
  { id: 'pr', agent: 'pr', label: 'Review PR', hint: 'Reviewer only' },
];
