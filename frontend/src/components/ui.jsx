import React, { useEffect, useId, useState } from 'react';
import { Check, Copy, X } from 'lucide-react';
import { AGENTS } from '../agents';

export function BrandMark({ className = 'brand-mark' }) {
  const id = useId();
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#8b7cf8" />
          <stop offset="1" stopColor="#4f9cf7" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${id})`} />
      <path d="M10 21 16 11 22 21Z" fill="none" stroke="#fff" strokeOpacity=".55"
        strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="16" cy="11" r="3" fill="#fff" />
      <circle cx="10" cy="21" r="3" fill="#fff" />
      <circle cx="22" cy="21" r="3" fill="#fff" fillOpacity=".85" />
    </svg>
  );
}

export function AgentIcon({ agent, size = 'md' }) {
  const meta = AGENTS[agent];
  if (!meta) return null;
  const Icon = meta.icon;
  return (
    <span
      className={`agent-icon ${size === 'sm' ? 'sm' : ''}`}
      style={{ '--agent-color': meta.color }}
      title={meta.name}
    >
      <Icon size={size === 'sm' ? 12 : 14} strokeWidth={2.2} />
    </span>
  );
}

export function CopyButton({ text, label, className = 'btn btn-ghost btn-sm' }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  };

  const Icon = copied ? Check : Copy;
  return (
    <button className={label ? className : 'icon-btn sm'} onClick={copy} title="Copy">
      <Icon size={14} />
      {label && (copied ? 'Copied' : label)}
    </button>
  );
}

export function useEscape(onEscape) {
  useEffect(() => {
    const handler = (e) => e.key === 'Escape' && onEscape();
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onEscape]);
}

export function Modal({ title, subtitle, icon, onClose, children, footer }) {
  useEscape(onClose);
  return (
    <div className="modal-wrap" role="dialog" aria-modal="true" aria-label={title}>
      <div className="backdrop" onClick={onClose} />
      <div className="modal">
        <div className="panel-head">
          {icon}
          <div>
            <h3>{title}</h3>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

/** Same id the backend derives (workspace.repo_id_from_url): "owner__name". */
export function repoIdFromUrl(url) {
  const m = /github\.com[/:]([^/\s]+)\/([^/\s]+?)(?:\.git)?\/?$/.exec((url || '').trim());
  const raw = m ? `${m[1]}__${m[2]}` : (url || '').trim().replace(/\/+$/, '').split('/').pop() || 'repo';
  return raw.toLowerCase().replace(/[^a-z0-9_.-]/g, '-');
}

/** "owner/repo" from a GitHub URL, falling back to the repo name. */
export function splitRepo(url, fallbackName) {
  const m = /github\.com[/:]([^/]+)\/([^/.]+)/.exec(url || '');
  return m ? { owner: m[1], name: m[2] } : { owner: null, name: fallbackName || 'repository' };
}
