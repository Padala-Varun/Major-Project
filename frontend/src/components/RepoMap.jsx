import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  ArrowLeft, CircleAlert, FlaskConical, LoaderCircle, Maximize, MessageSquare,
  PencilRuler, Search, ShieldCheck, TriangleAlert, X,
} from 'lucide-react';
import { getBrief, getGraph } from '../services/api';
import Markdown from './Markdown';
import { ImpactBadge } from './ImpactCard';

// Categorical slots in fixed order, validated (dataviz validate_palette.js) against
// this app's light and dark surfaces. Modules past the 7th fold into "Other".
const PALETTE = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9'],
};
const OTHER = { light: '#a3a6b4', dark: '#5d6170' };
// Risk is a magnitude: one hue, receding (neutral) at low risk to vivid red at high
const RISK_RAMP = { light: ['#c4c6d0', '#e34948'], dark: ['#4a4e5c', '#e66767'] };

function mix(a, b, t) {
  const pa = a.match(/\w\w/g).map((h) => parseInt(h, 16));
  const pb = b.match(/\w\w/g).map((h) => parseInt(h, 16));
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(',')})`;
}

function readColors() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    text: v('--text'),
    text2: v('--text-2'),
    border: v('--border-strong'),
    accent: v('--accent'),
    danger: v('--danger'),
    surface: v('--surface'),
    bg: v('--bg'),
  };
}

// Generic file names read better with their folder: "flask/__init__.py"
const GENERIC_NAMES = new Set([
  '__init__.py', '__main__.py', 'index.js', 'index.jsx', 'index.ts', 'index.tsx', 'mod.rs', 'main.go',
]);

function displayName(n, duplicated) {
  if (!GENERIC_NAMES.has(n.name) && !duplicated.has(n.name)) return n.name;
  const parts = n.path.replace(/\\/g, '/').split('/');
  return parts.length > 1 ? `${parts[parts.length - 2]}/${n.name}` : n.name;
}

const normPath = (p) => p.replace(/\\/g, '/').replace(/^\.\//, '');

function prepare(raw) {
  const seen = new Set();
  const duplicated = new Set();
  raw.nodes.forEach((n) => (seen.has(n.name) ? duplicated.add(n.name) : seen.add(n.name)));
  const nodes = raw.nodes.map((n) => ({
    ...n,
    name: displayName(n, duplicated),
    r: Math.min(16, 3.5 + Math.sqrt(n.fan_in) * 2.4),
    inIds: new Set(),
    outIds: new Set(),
  }));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  raw.links.forEach(({ source, target }) => {
    byId[source]?.outIds.add(target);
    byId[target]?.inIds.add(source);
  });
  const hubCut = [...nodes].sort((a, b) => b.fan_in - a.fan_in)[Math.min(5, nodes.length - 1)]?.fan_in ?? 0;
  nodes.forEach((n) => { n.hub = n.fan_in > 0 && n.fan_in >= hubCut; });
  return {
    graph: { nodes, links: raw.links.map((l) => ({ ...l })) },
    byId,
    idByPath: Object.fromEntries(nodes.map((n) => [normPath(n.path), n.id])),
    raw,
  };
}

/** Pulls files of the same module toward their module's center. */
function clusterForce(strength = 0.07) {
  let nodes = [];
  const force = (alpha) => {
    const centers = {};
    nodes.forEach((n) => {
      const c = (centers[n.module] ||= { x: 0, y: 0, k: 0 });
      c.x += n.x; c.y += n.y; c.k += 1;
    });
    nodes.forEach((n) => {
      const c = centers[n.module];
      n.vx += (c.x / c.k - n.x) * alpha * strength;
      n.vy += (c.y / c.k - n.y) * alpha * strength;
    });
  };
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

/** Pull toward the center so unconnected files don't drift off-screen. */
function gravityForce(strength = 0.04) {
  let nodes = [];
  const force = (alpha) => {
    nodes.forEach((n) => {
      // Files with no imports either way have no links holding them in
      const k = n.inIds.size + n.outIds.size ? strength : strength * 6;
      n.vx -= n.x * alpha * k;
      n.vy -= n.y * alpha * k;
    });
  };
  force.initialize = (ns) => { nodes = ns; };
  return force;
}

/** One-page onboarding brief, written by the team from the map and README (cached server-side). */
function BriefPanel({ repoId }) {
  const [brief, setBrief] = useState({ status: 'loading', markdown: '', error: null });

  const load = useCallback((refresh = false) => {
    setBrief({ status: 'loading', markdown: '', error: null });
    getBrief(repoId, refresh)
      .then((b) => setBrief({ status: 'ready', markdown: b.markdown, error: null }))
      .catch((err) => setBrief({ status: 'error', markdown: '', error: err.response?.data?.detail || err.message }));
  }, [repoId]);

  useEffect(() => { load(); }, [load]);

  if (brief.status === 'loading') {
    return (
      <div className="brief-loading">
        <LoaderCircle size={16} className="spin" />
        <div>
          <div className="shimmer">Writing the onboarding brief…</div>
          <div className="muted">The Explorer reads the map and README. This takes a few seconds the first time.</div>
        </div>
      </div>
    );
  }
  if (brief.status === 'error') {
    return (
      <>
        <div className="callout danger"><TriangleAlert size={15} /><span>{brief.error}</span></div>
        <button className="btn btn-outline btn-sm" style={{ marginTop: 10 }} onClick={() => load()}>Try again</button>
      </>
    );
  }
  return (
    <div className="brief">
      <Markdown>{brief.markdown}</Markdown>
      <button className="btn btn-ghost btn-sm" style={{ marginTop: 12 }} onClick={() => load(true)}>Regenerate</button>
    </div>
  );
}

function RiskBar({ value }) {
  return (
    <div className="risk-bar" title={`Risk ${value}/100`}>
      <span style={{ width: `${value}%` }} />
    </div>
  );
}

function FileLink({ node, color, onSelect, meta }) {
  return (
    <button className="map-file" onClick={() => onSelect(node.id)}>
      <span className="swatch" style={{ background: color }} />
      <span className="map-file-name" title={node.path}>{node.name}</span>
      {meta && <span className="map-file-meta">{meta}</span>}
    </button>
  );
}

export default function RepoMap({ repoId, theme, onAsk, impact, onClearImpact }) {
  const [state, setState] = useState({ loading: true, error: null, data: null });
  const [colorBy, setColorBy] = useState('module');
  const [selected, setSelected] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [isolated, setIsolated] = useState(null);
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('brief');
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [mouse, setMouse] = useState({ x: 0, y: 0 });
  const wrapRef = useRef(null);
  const fgRef = useRef(null);
  const fittedRef = useRef(false);

  useEffect(() => {
    setState({ loading: true, error: null, data: null });
    setSelected(null);
    fittedRef.current = false;
    getGraph(repoId)
      .then((raw) => setState({ loading: false, error: null, data: prepare(raw) }))
      .catch((err) => setState({
        loading: false,
        error: err.response?.data?.detail || err.message || 'Could not load the map.',
        data: null,
      }));
  }, [repoId]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [state.data]);

  // Re-fit when the canvas is resized (window, mobile rotation, panel changes)
  useEffect(() => {
    if (!fittedRef.current) return undefined;
    const t = setTimeout(() => fgRef.current?.zoomToFit(300, 40), 150);
    return () => clearTimeout(t);
  }, [size.width, size.height]);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg || !state.data) return;
    fg.d3Force('charge').strength(-90);
    fg.d3Force('link').distance(36);
    fg.d3Force('cluster', clusterForce());
    fg.d3Force('gravity', gravityForce());
  }, [state.data]);

  const data = state.data;
  const mode = theme === 'light' ? 'light' : 'dark';

  // Canvas can't use CSS variables, so read the theme's values once it has applied
  const [colors, setColors] = useState(readColors);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setColors(readColors()));
    return () => cancelAnimationFrame(raf);
  }, [theme]);

  const moduleColor = useMemo(() => {
    const map = {};
    (data?.raw.modules || []).forEach((m, i) => {
      map[m.name] = i < PALETTE[mode].length ? PALETTE[mode][i] : OTHER[mode];
    });
    return map;
  }, [data, mode]);

  const colorOf = useCallback((n) => (colorBy === 'risk'
    ? mix(RISK_RAMP[mode][0], RISK_RAMP[mode][1], n.risk / 100)
    : moduleColor[n.module] || OTHER[mode]), [colorBy, mode, moduleColor]);

  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q || !data) return null;
    return new Set(data.graph.nodes.filter((n) => n.path.toLowerCase().includes(q)).map((n) => n.id));
  }, [search, data]);

  // Impact mode: the files a change modifies and everything depending on them
  const impactSets = useMemo(() => {
    if (!impact || !data) return null;
    const idOf = (p) => data.idByPath[normPath(p)];
    return {
      changed: new Set(impact.impact.changed.filter((c) => c.status === 'modified').map((c) => idOf(c.path)).filter(Boolean)),
      affected: new Map(impact.impact.affected.map((a) => [idOf(a.path), a.depth]).filter(([id]) => id)),
    };
  }, [impact, data]);

  // Nodes in focus: a selection or hover shows the file and its direct dependencies
  const focus = useMemo(() => {
    const id = selected || hovered;
    if (id && data?.byId[id]) {
      const n = data.byId[id];
      return new Set([id, ...n.inIds, ...n.outIds]);
    }
    if (impactSets) return new Set([...impactSets.changed, ...impactSets.affected.keys()]);
    if (isolated && data) return new Set(data.graph.nodes.filter((n) => n.module === isolated).map((n) => n.id));
    return matches;
  }, [selected, hovered, isolated, matches, data, impactSets]);

  const anchor = selected || hovered;

  const drawNode = useCallback((node, ctx, scale) => {
    const dim = focus && !focus.has(node.id);
    const color = colorOf(node);
    const r = node.r;
    ctx.globalAlpha = dim ? 0.13 : 1;

    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    if (node.is_test) {
      ctx.fillStyle = colors.surface;
      ctx.fill();
      ctx.lineWidth = Math.max(1.6, r * 0.38);
      ctx.strokeStyle = color;
      ctx.stroke();
    } else {
      ctx.fillStyle = color;
      ctx.fill();
      ctx.lineWidth = 1.5 / scale;
      ctx.strokeStyle = colors.bg;  // surface ring keeps overlapping nodes distinct
      ctx.stroke();
    }

    if (impactSets?.changed.has(node.id) && !dim) {
      // Pulsing ring so the changed file stands out even in a crowded graph
      const pulse = (Math.sin(Date.now() / 260) + 1) / 2;
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + (3 + pulse * 5) / scale, 0, 2 * Math.PI);
      ctx.lineWidth = 3 / scale;
      ctx.strokeStyle = colors.danger;
      ctx.globalAlpha = 0.45 + 0.55 * (1 - pulse);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    if (node.id === selected) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 3.5 / scale + 1.5, 0, 2 * Math.PI);
      ctx.lineWidth = 2 / scale;
      ctx.strokeStyle = colors.accent;
      ctx.stroke();
    }

    // In impact mode only the change and its direct dependents are labeled, to keep it readable
    const impactLabel = impactSets && !anchor
      ? impactSets.changed.has(node.id) || impactSets.affected.get(node.id) === 1
      : null;
    const showLabel = !dim && (impactLabel ?? (node.id === anchor
      || (focus && focus.has(node.id) && focus.size <= 40) || node.hub || scale > 2.4));
    if (showLabel) {
      const fs = Math.max(10 / scale, 2.2);
      ctx.font = `${node.id === anchor ? 600 : 500} ${fs}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.lineWidth = 3 / scale;
      ctx.strokeStyle = colors.bg;
      ctx.strokeText(node.name, node.x, node.y + r + 2.5 / scale);
      ctx.fillStyle = node.id === anchor ? colors.text : colors.text2;
      ctx.fillText(node.name, node.x, node.y + r + 2.5 / scale);
    }
    ctx.globalAlpha = 1;
  }, [focus, colorOf, colors, selected, anchor, impactSets]);

  const paintHitArea = useCallback((node, color, ctx) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.r + 4, 0, 2 * Math.PI);
    ctx.fill();
  }, []);

  const linkTouchesAnchor = useCallback((l) => (anchor
    ? l.source.id === anchor || l.target.id === anchor
    : Boolean(impactSets && (impactSets.changed.has(l.target.id) || impactSets.affected.has(l.target.id))
      && impactSets.affected.has(l.source.id))), [anchor, impactSets]);

  const select = useCallback((id, zoom = true) => {
    setSelected(id);
    setTab('overview');
    const n = data?.byId[id];
    if (zoom && n && fgRef.current && n.x != null) {
      fgRef.current.centerAt(n.x, n.y, 600);
      fgRef.current.zoom(Math.max(fgRef.current.zoom(), 2.6), 600);
    }
  }, [data]);

  const fit = () => fgRef.current?.zoomToFit(500, 50, impactSets ? (n) => focus?.has(n.id) : undefined);

  // Frame the impact area when impact mode starts (after the layout has settled)
  useEffect(() => {
    if (!impactSets || !fittedRef.current) return undefined;
    const t = setTimeout(() => fgRef.current?.zoomToFit(600, 60, (n) => focus?.has(n.id)), 100);
    return () => clearTimeout(t);
  }, [impactSets]);

  if (state.loading) {
    return <div className="map-state"><LoaderCircle size={20} className="spin" /> Mapping the architecture…</div>;
  }
  if (state.error) {
    return <div className="map-state"><div className="callout danger"><TriangleAlert size={15} /><span>{String(state.error)}</span></div></div>;
  }

  const { raw, byId } = data;
  const sel = selected && byId[selected];
  const hov = hovered && byId[hovered];
  const stats = raw.stats;
  const sortedFiles = [...data.graph.nodes].sort((a, b) => b.risk - a.risk || b.fan_in - a.fan_in);

  return (
    <div className="map">
      <div
        className="map-canvas"
        ref={wrapRef}
        onMouseMove={(e) => {
          const box = wrapRef.current.getBoundingClientRect();
          setMouse({ x: e.clientX - box.left, y: e.clientY - box.top });
        }}
      >
        {size.width > 0 && (
          <ForceGraph2D
            ref={fgRef}
            width={size.width}
            height={size.height}
            graphData={data.graph}
            nodeId="id"
            nodeLabel={() => ''}
            nodeCanvasObject={drawNode}
            nodePointerAreaPaint={paintHitArea}
            linkColor={(l) => (linkTouchesAnchor(l) ? colors.accent : colors.border)}
            linkWidth={(l) => (linkTouchesAnchor(l) ? 1.6 : 0.6)}
            linkVisibility={(l) => !focus || (focus.has(l.source.id) && focus.has(l.target.id))}
            linkDirectionalArrowLength={3}
            linkDirectionalArrowRelPos={1}
            linkDirectionalParticles={(l) => (linkTouchesAnchor(l) ? 2 : 0)}
            linkDirectionalParticleWidth={2.2}
            linkDirectionalParticleColor={() => colors.accent}
            autoPauseRedraw={false}
            cooldownTicks={160}
            onEngineStop={() => {
              if (!fittedRef.current) { fittedRef.current = true; fit(); }
            }}
            onNodeHover={(n) => setHovered(n ? n.id : null)}
            onNodeClick={(n) => select(n.id, false)}
            onBackgroundClick={() => { setSelected(null); setIsolated(null); }}
          />
        )}

        <div className="map-toolbar">
          <label className="map-search">
            <Search size={14} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && matches?.size) select([...matches][0]);
                if (e.key === 'Escape') setSearch('');
              }}
              placeholder="Find a file…"
              aria-label="Find a file"
            />
            {matches && <span className="muted">{matches.size}</span>}
          </label>
          <div className="segmented" role="tablist" aria-label="Color by">
            {[['module', 'Modules'], ['risk', 'Risk']].map(([id, label]) => (
              <button key={id} className={colorBy === id ? 'active' : ''} onClick={() => setColorBy(id)}>{label}</button>
            ))}
          </div>
          <button className="icon-btn map-fit" onClick={fit} title="Fit to screen"><Maximize size={15} /></button>
        </div>

        <div className="map-legend">
          {colorBy === 'risk' ? (
            <div className="legend-ramp">
              <span>Low risk</span>
              <span className="ramp" style={{ background: `linear-gradient(90deg, ${RISK_RAMP[mode][0]}, ${RISK_RAMP[mode][1]})` }} />
              <span>High</span>
            </div>
          ) : null}
          <div className="legend-notes">
            <span><span className="legend-dot big" /> Size: files importing it</span>
            <span><span className="legend-dot hollow" /> Test file</span>
          </div>
        </div>

        {impact && (
          <div className="map-impact-banner">
            <ImpactBadge level={impact.impact.level} />
            <div className="map-impact-text">
              <strong title={impact.label}>{impact.label || 'Proposed change'}</strong>
              <span>{impact.impact.summary} Red rings mark changed files.</span>
            </div>
            <button className="icon-btn sm" onClick={onClearImpact} aria-label="Exit impact view"><X size={14} /></button>
          </div>
        )}

        {hov && hov.id !== selected && (
          <div className="map-tip" style={{ left: mouse.x + 14, top: mouse.y + 14 }}>
            <div className="map-tip-name">{hov.name}</div>
            <div className="map-tip-path">{hov.path}</div>
            <div className="map-tip-row">
              {hov.is_test ? 'Test file' : `Risk ${hov.risk}`} · imported by {hov.fan_in} · imports {hov.fan_out}
            </div>
          </div>
        )}
      </div>

      <aside className="map-panel">
        {sel ? (
          <div className="panel-body">
            <button className="btn btn-ghost btn-sm map-back" onClick={() => setSelected(null)}>
              <ArrowLeft size={14} /> Overview
            </button>
            <h3 className="map-title">{sel.name}</h3>
            <div className="map-path">{sel.path}</div>
            <div className="map-chips">
              <span className="chip"><span className="swatch" style={{ background: moduleColor[sel.module] || OTHER[mode] }} />{sel.module}</span>
              <span className="chip">{sel.language}</span>
              {sel.is_test && <span className="chip"><FlaskConical size={12} /> Test</span>}
            </div>

            {!sel.is_test && (
              <div className="map-risk">
                <div className="map-risk-top">
                  <span className="map-risk-score">{sel.risk}</span>
                  <span className="muted">/ 100 change risk</span>
                </div>
                <RiskBar value={sel.risk} />
                <ul className="map-reasons">
                  {sel.risk_reasons.map((r) => (
                    <li key={r}>
                      {r.startsWith('No tests') ? <CircleAlert size={13} /> : r.startsWith('Covered') ? <ShieldCheck size={13} /> : <span className="dot" />}
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="map-metrics">
              <div><strong>{sel.lines}</strong><span>Lines</span></div>
              <div><strong>{sel.fan_in}</strong><span>Imported by</span></div>
              <div><strong>{sel.fan_out}</strong><span>Imports</span></div>
            </div>

            <div className="map-actions">
              <button className="btn btn-primary btn-sm" onClick={() => onAsk(
                `Explain ${sel.path}: what it is responsible for, its key classes and functions, and how the rest of the codebase depends on it.`,
              )}>
                <MessageSquare size={14} /> Ask the team
              </button>
              <button className="btn btn-outline btn-sm" onClick={() => onAsk(
                `Plan a safe change to ${sel.path}. It is imported by ${sel.fan_in} file(s); identify what could break and how to change it without regressions.`,
              )}>
                <PencilRuler size={14} /> Plan a change
              </button>
            </div>

            {[['Imported by', [...sel.inIds]], ['Imports', [...sel.outIds]]].map(([label, ids]) => ids.length > 0 && (
              <div key={label} className="map-section">
                <div className="side-label">{label} <span className="muted">{ids.length}</span></div>
                {ids.map((id) => byId[id]).sort((a, b) => b.fan_in - a.fan_in).map((n) => (
                  <FileLink key={n.id} node={n} color={colorOf(n)} onSelect={select} />
                ))}
              </div>
            ))}

            {[['Classes', sel.classes], ['Functions', sel.functions]].map(([label, names]) => names.length > 0 && (
              <div key={label} className="map-section">
                <div className="side-label">{label} <span className="muted">{names.length}</span></div>
                <div className="node-list">{names.map((nm) => <span key={nm} className="node-chip"><span>{nm}</span></span>)}</div>
              </div>
            ))}
          </div>
        ) : (
          <>
            <div className="tabs">
              {[['brief', 'Brief'], ['overview', 'Overview'], ['files', 'Files']].map(([id, label]) => (
                <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>
                  {label}{id === 'files' && <span className="count">{stats.files}</span>}
                </button>
              ))}
            </div>
            {tab === 'brief' ? (
              <div className="panel-body">
                <BriefPanel repoId={repoId} />
              </div>
            ) : tab === 'overview' ? (
              <div className="panel-body">
                <div className="map-stats">
                  {[['Files', stats.files], ['Dependencies', stats.dependencies], ['Classes', stats.classes], ['Functions', stats.functions]].map(([l, v]) => (
                    <div key={l}><strong>{v}</strong><span>{l}</span></div>
                  ))}
                </div>
                <p className="map-note">
                  {stats.test_files} test file{stats.test_files === 1 ? '' : 's'} · {stats.untested_files} source file{stats.untested_files === 1 ? '' : 's'} without tests
                  {stats.truncated && ' · showing the 600 most connected files'}
                </p>

                <div className="map-section">
                  <div className="side-label">Modules</div>
                  {raw.modules.map((m) => (
                    <button
                      key={m.name}
                      className={`map-file ${isolated === m.name ? 'active' : ''}`}
                      onClick={() => setIsolated(isolated === m.name ? null : m.name)}
                      title="Highlight this module"
                    >
                      <span className="swatch" style={{ background: moduleColor[m.name] }} />
                      <span className="map-file-name">{m.name}</span>
                      <span className="map-file-meta">{m.files}</span>
                    </button>
                  ))}
                </div>

                {raw.entry_points.length > 0 && (
                  <div className="map-section">
                    <div className="side-label">Entry points</div>
                    {raw.entry_points.map((id) => (
                      <FileLink key={id} node={byId[id]} color={colorOf(byId[id])} onSelect={select}
                        meta={`imports ${byId[id].fan_out}`} />
                    ))}
                  </div>
                )}

                <div className="map-section">
                  <div className="side-label">Risk hotspots</div>
                  {raw.hotspots.map((id) => {
                    const n = byId[id];
                    return (
                      <button key={id} className="hotspot" onClick={() => select(id)}>
                        <div className="hotspot-top">
                          <span className="map-file-name" title={n.path}>{n.name}</span>
                          <span className="hotspot-score">{n.risk}</span>
                        </div>
                        <RiskBar value={n.risk} />
                        <div className="hotspot-why">{n.risk_reasons.join(' · ')}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="panel-body">
                <table className="map-table">
                  <thead>
                    <tr><th>File</th><th>Risk</th><th>In</th></tr>
                  </thead>
                  <tbody>
                    {sortedFiles.map((n) => (
                      <tr key={n.id} onClick={() => select(n.id)}>
                        <td>
                          <span className="swatch" style={{ background: moduleColor[n.module] || OTHER[mode] }} />
                          <span title={n.path}>{n.name}</span>
                        </td>
                        <td>{n.is_test ? '—' : n.risk}</td>
                        <td>{n.fan_in}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
