import { useEffect, useState } from 'react';
import { Bot, CloudOff, Database, SlidersHorizontal } from 'lucide-react';
import { useApiNotice } from '../hooks/useApiNotice';
import { ApiNotice, Button, Field, FormActions, InlineNotice, PageHeader, Panel, SelectInput } from '../components/common/ui';

export default function Settings() {
  const [currency, setCurrency] = useState('USD');
  const [units, setUnits] = useState('Metric');
  const [theme, setTheme] = useState('Light');
  const { message, reportUnavailable } = useApiNotice();

  useEffect(() => {
    const root = document.documentElement;
    if (theme !== 'System') {
      if (theme === 'Dark') root.dataset.theme = 'dark';
      else delete root.dataset.theme;
      return;
    }
    const preference = window.matchMedia('(prefers-color-scheme: dark)');
    const applySystemTheme = () => { if (preference.matches) root.dataset.theme = 'dark'; else delete root.dataset.theme; };
    applySystemTheme();
    preference.addEventListener('change', applySystemTheme);
    return () => preference.removeEventListener('change', applySystemTheme);
  }, [theme]);

  return <>
    <PageHeader eyebrow="Workspace / Settings" title="Settings" description="Review connection state, workspace display preferences, and data-management boundaries." />
    <ApiNotice />
    <div className="two-column-grid">
      <Panel title="Application connection" description="The frontend is ready for your future API integration.">
        <div className="panel-body stack"><div className="connection-card"><span className="connection-card-icon"><CloudOff size={19}/></span><div><strong>Backend API not configured</strong><small>No requests are being made from this application.</small></div></div><div className="connection-card"><span className="connection-card-icon"><Bot size={19}/></span><div><strong>AI model not connected</strong><small>Ask AI will not send prompts or return generated answers.</small></div></div><div className="status-prompt">Connection fields and tokens are intentionally not requested or stored in this frontend build. Wire your API client into <code>frontend/src/api/connection.ts</code> when ready.</div></div>
      </Panel>
      <Panel title="Display preferences" description="Currency, units, and theme selections apply in this browser session only; they are not persisted.">
        <form className="panel-body" onSubmit={(event) => { event.preventDefault(); reportUnavailable('preference save'); }}><div className="form-grid"><Field label="Currency" htmlFor="pref-currency"><SelectInput id="pref-currency" value={currency} onChange={(event) => setCurrency(event.target.value)}><option>USD</option><option>GBP</option><option>EUR</option><option>AUD</option><option>CAD</option></SelectInput></Field><Field label="Units" htmlFor="pref-units"><SelectInput id="pref-units" value={units} onChange={(event) => setUnits(event.target.value)}><option>Metric</option><option>Imperial</option></SelectInput></Field><Field label="Theme" htmlFor="pref-theme"><SelectInput id="pref-theme" value={theme} onChange={(event) => setTheme(event.target.value)}><option>Light</option><option>Dark</option><option>System</option></SelectInput></Field></div>{message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}<FormActions><Button type="submit" variant="primary" icon={SlidersHorizontal}>Save preferences</Button></FormActions></form>
      </Panel>
    </div>
    <div className="dashboard-panels-lower"><Panel title="Data management" description="No data is stored by this frontend."><div className="panel-body"><div className="connection-card"><span className="connection-card-icon"><Database size={19}/></span><div><strong>No workspace records are stored here</strong><small>Export, deletion, retention, and recovery controls require your connected backend.</small></div></div></div></Panel><Panel title="Analysis behavior" description="Keep ProjectIQ decision support transparent."><div className="panel-body"><div className="key-value-list"><div className="key-value-row"><span>Automatic bid decisions</span><strong>Not performed</strong></div><div className="key-value-row"><span>Financial calculations</span><strong>Backend integration required</strong></div><div className="key-value-row"><span>Evidence citations</span><strong>Not available without source data</strong></div></div></div></Panel></div>
  </>;
}
