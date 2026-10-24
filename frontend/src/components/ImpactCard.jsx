import React, { useState } from 'react';
import { ChevronDown, ChevronRight, CircleAlert, Network, ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react';

// Status colors always come with an icon and a label, never color alone
export const IMPACT_LEVELS = {
  low: { label: 'Low impact', icon: ShieldCheck, className: 'low' },
  medium: { label: 'Medium impact', icon: TriangleAlert, className: 'medium' },
  high: { label: 'High impact', icon: ShieldAlert, className: 'high' },
};

export function ImpactBadge({ level }) {
  const meta = IMPACT_LEVELS[level] || IMPACT_LEVELS.low;
  const Icon = meta.icon;
  return (
    <span className={`impact-badge ${meta.className}`}>
      <Icon size={12} strokeWidth={2.4} /> {meta.label}
    </span>
  );
}

export default function ImpactCard({ impact, onShowOnMap }) {
  const [open, setOpen] = useState(false);
  const direct = impact.affected.filter((a) => a.depth === 1);
  const more = impact.affected_count - direct.length;

  return (
    <div className="impact">
      <div className="impact-head">
        <span className="impact-title">Impact analysis</span>
        <ImpactBadge level={impact.level} />
        {onShowOnMap && impact.affected_count + impact.changed.length > 0 && (
          <button className="btn btn-ghost btn-sm impact-map-btn" onClick={onShowOnMap}>
            <Network size={14} /> Show on map
          </button>
        )}
      </div>
      <p className="impact-summary">{impact.summary}</p>

      <div className="impact-files">
        {impact.changed.map((c) => (
          <div key={c.path} className="impact-file">
            <span className={`impact-status ${c.status}`}>{c.status === 'new' ? 'New' : 'Modified'}</span>
            <span className="impact-path" title={c.path}>{c.path}</span>
            {c.status === 'modified' && <span className="impact-meta">risk {c.risk}</span>}
          </div>
        ))}
      </div>

      {(impact.reasons.length > 0 || direct.length > 0) && (
        <button className="run-step-toggle" onClick={() => setOpen(!open)}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {open ? 'Hide details' : `Why ${IMPACT_LEVELS[impact.level]?.label.toLowerCase() || 'this rating'}?`}
        </button>
      )}
      {open && (
        <div className="impact-details">
          <ul className="map-reasons">
            {impact.reasons.map((r) => (
              <li key={r}><CircleAlert size={13} />{r}</li>
            ))}
          </ul>
          {direct.length > 0 && (
            <>
              <div className="side-label">Directly affected</div>
              {direct.slice(0, 8).map((a) => (
                <div key={a.path} className="impact-file">
                  <span className="impact-path" title={a.path}>{a.path}</span>
                  {!a.tested && <span className="impact-meta warn">no tests</span>}
                </div>
              ))}
              {direct.length > 8 && <div className="impact-meta">+{direct.length - 8} more</div>}
              {more > 0 && <div className="impact-meta">+{more} indirectly through these</div>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
