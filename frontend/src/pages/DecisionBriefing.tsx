import { useState } from 'react';
import { FileCheck2, FileQuestion, ShieldAlert } from 'lucide-react';
import { useApiNotice } from '../hooks/useApiNotice';
import { ApiNotice, Button, EmptyState, InlineNotice, PageHeader, Panel, Tabs } from '../components/common/ui';

export default function DecisionBriefing() {
  const [audience, setAudience] = useState('executive');
  const { message, reportUnavailable } = useApiNotice();
  return <>
    <PageHeader eyebrow="Decision support / Briefing" title="Decision briefing" description="A concise, evidence-backed view of what is known, what remains uncertain, and what needs human review." actions={<Button variant="primary" onClick={() => reportUnavailable('briefing generation')}>Prepare briefing</Button>} />
    <ApiNotice />
    <Panel title="Briefing view" description="Choose the level of detail for the intended readers." action={<Tabs label="Briefing audience" value={audience} onChange={setAudience} items={[{ id: 'executive', label: 'Executive' }, { id: 'analyst', label: 'Analyst' }]} />}>
      <div className="panel-body">
        <div className="briefing-outline"><section><p className="panel-eyebrow">01 · Opportunity at a glance</p><EmptyState icon={FileQuestion} title="No project context loaded" description="Project scope, deadline, client, and tender context are waiting for the Projects API." /></section><section><p className="panel-eyebrow">02 · {audience === 'executive' ? 'Decision considerations' : 'Requirement and evidence detail'}</p><EmptyState icon={FileCheck2} title="No verified findings" description="No recommendation, compliance result, source citation, or financial conclusion is invented in this frontend." /></section><section><p className="panel-eyebrow">03 · Risks, assumptions & open questions</p><EmptyState icon={ShieldAlert} title="No review records loaded" description="These sections will draw from connected, traceable project data." /></section></div>
        {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
        <div className="briefing-footnote">A briefing is decision support only. People remain responsible for the final decision and specialist verification.</div>
      </div>
    </Panel>
  </>;
}
