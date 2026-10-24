import React, { useState } from 'react';
import { Settings } from 'lucide-react';
import { Modal } from './ui';

export default function SettingsModal({ githubToken, onSave, onClose }) {
  const [token, setToken] = useState(githubToken);

  return (
    <Modal
      title="Settings"
      subtitle="Session preferences"
      icon={<Settings size={18} className="muted" />}
      onClose={onClose}
      footer={(
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => { onSave(token.trim()); onClose(); }}>Save</button>
        </>
      )}
    >
      <div className="field">
        <label htmlFor="settings-token">GitHub token</label>
        <input
          id="settings-token"
          className="input mono"
          type="password"
          placeholder="github_pat_…"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoFocus
        />
        <span className="field-hint">
          Overrides the backend's GITHUB_TOKEN for private repositories and pull requests.
          Kept in memory only and cleared when you close the tab.
        </span>
      </div>
    </Modal>
  );
}
