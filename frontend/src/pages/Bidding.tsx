import { useState, type FormEvent } from 'react';
import { BadgeCheck, ClipboardList, FileSearch, ShieldCheck } from 'lucide-react';
import { useApiNotice } from '../hooks/useApiNotice';
import { ApiNotice, Button, EmptyState, Field, FormActions, InlineNotice, PageHeader, Panel, SelectInput, StatusPill, TextArea, TextInput } from '../components/common/ui';

type ReviewStatus = 'unreviewed' | 'follow-up' | 'in-review' | 'reviewed';
type FactorReview = { status: ReviewStatus; owner: string; source: string; notes: string };

const statusOptions: Array<{ value: ReviewStatus; label: string }> = [
  { value: 'unreviewed', label: 'Not reviewed' },
  { value: 'follow-up', label: 'Needs follow-up' },
  { value: 'in-review', label: 'Under review' },
  { value: 'reviewed', label: 'Reviewed by team' },
];

const factors = [
  { id: 'eligibility', label: 'Eligibility criteria', detail: 'Record the source for participation criteria and exclusions.' },
  { id: 'documents', label: 'Mandatory tender documents', detail: 'Track required submission items and their evidence references.' },
  { id: 'capability', label: 'Capability evidence', detail: 'Review the capability evidence the team would rely on.' },
  { id: 'delivery', label: 'Workforce and equipment', detail: 'Capture availability, capacity, and delivery dependencies.' },
  { id: 'financial', label: 'Financial feasibility', detail: 'Record the assumptions and qualified financial review needed.' },
  { id: 'risk', label: 'Risk and mitigation', detail: 'Document material exposures, proposed mitigations, and owners.' },
  { id: 'deadline', label: 'Submission deadline', detail: 'Check the source deadline and the time needed for approvals.' },
] as const;

type FactorId = typeof factors[number]['id'];
const initialFactorReview: FactorReview = { status: 'unreviewed', owner: '', source: '', notes: '' };
function createFactorDrafts(): Record<FactorId, FactorReview> {
  return Object.fromEntries(factors.map(({ id }) => [id, { ...initialFactorReview }])) as Record<FactorId, FactorReview>;
}

export default function Bidding() {
  const [decision, setDecision] = useState('');
  const [factorDrafts, setFactorDrafts] = useState<Record<FactorId, FactorReview>>(createFactorDrafts);
  const { message, reportUnavailable } = useApiNotice();

  function updateFactor(id: FactorId, field: keyof FactorReview, value: string) {
    setFactorDrafts((current) => ({ ...current, [id]: { ...current[id], [field]: value } }));
  }
  function saveFactor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    reportUnavailable('saving a bid-readiness factor review');
  }

  return <>
    <PageHeader eyebrow="Opportunity / Bidding" title="Bid preparation" description="Bring eligibility, mandatory documents, capability, delivery, financial, and deadline considerations into a human-led decision." />
    <ApiNotice />
    <div className="two-column-grid">
      <Panel title="Bid readiness review" description="Review each factor with its evidence, owner, and current team review state. Status labels describe the draft review—not eligibility or bid readiness.">
        <div className="panel-body">
          <InlineNotice variant="info"><strong>No assessment is inferred.</strong> Each factor remains unreviewed until the team enters source-backed information and connects a review service.</InlineNotice>
        </div>
        <div className="factor-review-list">
          {factors.map((factor) => {
            const draft = factorDrafts[factor.id];
            const statusLabel = statusOptions.find((option) => option.value === draft.status)?.label ?? 'Not reviewed';
            return (
              <details className="factor-review" key={factor.id}>
                <summary className="factor-review-summary">
                  <span className="factor-review-copy"><strong>{factor.label}</strong><small>{factor.detail}</small></span>
                  <StatusPill tone={draft.status === 'reviewed' ? 'blue' : draft.status === 'follow-up' ? 'amber' : 'neutral'}>{statusLabel}</StatusPill>
                </summary>
                <form className="factor-review-body" onSubmit={saveFactor}>
                  <div className="form-grid">
                    <Field label="Review status" htmlFor={`bid-${factor.id}-status`}>
                      <SelectInput id={`bid-${factor.id}-status`} value={draft.status} onChange={(event) => updateFactor(factor.id, 'status', event.target.value)}>
                        {statusOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                      </SelectInput>
                    </Field>
                    <Field label="Review owner" htmlFor={`bid-${factor.id}-owner`}><TextInput id={`bid-${factor.id}-owner`} value={draft.owner} onChange={(event) => updateFactor(factor.id, 'owner', event.target.value)} placeholder="Person responsible" /></Field>
                    <Field className="field-full" label="Source / evidence reference" htmlFor={`bid-${factor.id}-source`}><TextInput id={`bid-${factor.id}-source`} value={draft.source} onChange={(event) => updateFactor(factor.id, 'source', event.target.value)} placeholder="Document, page, record, or date" /></Field>
                    <Field className="field-full" label="Review notes and open questions" htmlFor={`bid-${factor.id}-notes`}><TextArea id={`bid-${factor.id}-notes`} value={draft.notes} onChange={(event) => updateFactor(factor.id, 'notes', event.target.value)} placeholder="Enter source-led notes; no conclusion is calculated" /></Field>
                  </div>
                  <FormActions><Button type="submit" variant="secondary" icon={FileSearch}>Save review note</Button></FormActions>
                </form>
              </details>
            );
          })}
        </div>
      </Panel>
      <Panel title="Decision factors" description="Record the team's reasoning; ProjectIQ does not submit bids or make the decision.">
        <form className="panel-body stack" onSubmit={(event) => { event.preventDefault(); reportUnavailable('bid-readiness assessment'); }}>
          <Field label="Decision status" htmlFor="bid-decision"><SelectInput id="bid-decision" value={decision} onChange={(event) => setDecision(event.target.value)}><option value="">Select after review</option><option value="pursue">Pursue</option><option value="investigate">Investigate</option><option value="decline">Decline</option></SelectInput></Field>
          <Field label="Rationale and open questions" htmlFor="bid-rationale"><TextArea id="bid-rationale" placeholder="Record evidence-backed considerations for the team" /></Field>
          {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
          <FormActions><Button type="submit" variant="primary" icon={ShieldCheck}>Save decision notes</Button></FormActions>
        </form>
      </Panel>
    </div>
    <div className="dashboard-panels-lower">
      <Panel title="Mandatory documents"><EmptyState icon={ClipboardList} title="No tender documents loaded" description="Document requirements and submission status appear after the document API is connected." /></Panel>
      <Panel title="Submission preparation"><EmptyState icon={BadgeCheck} title="No submission checklist loaded" description="Bid submission remains a human action; this screen will not submit a tender." /></Panel>
    </div>
  </>;
}
