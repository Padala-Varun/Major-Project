import React, { useState } from 'react';

export default function ExplainabilityLog({ log }) {
  const [expanded, setExpanded] = useState(false);

  if (!log || Object.keys(log).length === 0) return null;

  return (
    <div>
      <button className="explain-toggle" onClick={() => setExpanded(!expanded)}>
        {expanded ? '▾' : '▸'} Explainability Log
        <span style={{ opacity: 0.6 }}> — {log.total_time_seconds || 0}s</span>
      </button>

      {expanded && (
        <div className="explain-panel">
          {/* Stats summary */}
          <div style={{ marginBottom: 12 }}>
            <span className="explain-stat">
              🔗 Graph Nodes: <span className="num">{log.graph_nodes_count || 0}</span>
            </span>
            <span className="explain-stat">
              📄 FAISS Chunks: <span className="num">{log.faiss_chunks_count || 0}</span>
            </span>
            <span className="explain-stat">
              ⏱️ Time: <span className="num">{log.total_time_seconds || 0}s</span>
            </span>
            <span className="explain-stat">
              🤖 Agent: <span className="num">{log.agent_type || 'unknown'}</span>
            </span>
          </div>

          {/* Reasoning Steps */}
          {log.reasoning_steps?.length > 0 && (
            <>
              <h4>🧠 Reasoning Steps</h4>
              {log.reasoning_steps.map((step, i) => (
                <div key={i} className="explain-item">
                  <strong>{step.step}</strong>
                  <span style={{ float: 'right', opacity: 0.5 }}>
                    +{step.timestamp?.toFixed(2)}s
                  </span>
                  {step.details && typeof step.details === 'string' && (
                    <div style={{ marginTop: 4, opacity: 0.7 }}>{step.details}</div>
                  )}
                  {step.details && typeof step.details === 'object' && (
                    <div style={{ marginTop: 4, opacity: 0.7, fontSize: '0.7rem' }}>
                      {JSON.stringify(step.details, null, 0).substring(0, 200)}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}

          {/* Graph Nodes Visited */}
          {log.graph_nodes_visited?.length > 0 && (
            <>
              <h4>🔗 Graph Nodes Visited</h4>
              {log.graph_nodes_visited.slice(0, 15).map((node, i) => (
                <div key={i} className="explain-item">{node}</div>
              ))}
              {log.graph_nodes_visited.length > 15 && (
                <div className="explain-item" style={{ opacity: 0.5 }}>
                  ...and {log.graph_nodes_visited.length - 15} more
                </div>
              )}
            </>
          )}

          {/* FAISS Chunks */}
          {log.faiss_chunks_retrieved?.length > 0 && (
            <>
              <h4>📄 Retrieved Code Chunks</h4>
              {log.faiss_chunks_retrieved.slice(0, 8).map((chunk, i) => (
                <div key={i} className="explain-item">
                  <strong>{chunk.file_path}</strong>
                  <span style={{ float: 'right' }}>Score: {chunk.score}</span>
                  {chunk.entities?.length > 0 && (
                    <div style={{ marginTop: 4, opacity: 0.6 }}>
                      {chunk.entities.join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}

          {/* Intermediate Conclusions */}
          {log.intermediate_conclusions?.length > 0 && (
            <>
              <h4>💡 Intermediate Conclusions</h4>
              {log.intermediate_conclusions.map((conclusion, i) => (
                <div key={i} className="explain-item">{conclusion}</div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
