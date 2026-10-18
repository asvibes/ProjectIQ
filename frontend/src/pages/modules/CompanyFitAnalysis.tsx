import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Download,
  ExternalLink,
  FileCheck2,
  FileSearch,
  Filter,
  Info,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  DataTable,
  EmptyState,
  Field,
  FormActions,
  InlineNotice,
  MetricCard,
  Panel,
  PageHeader,
  SelectInput,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type FitStatus = 'unknown' | 'met' | 'partially-met' | 'not-met' | 'not-applicable';
type EvidenceStatus = 'unknown' | 'verified' | 'unverified' | 'missing' | 'conflicting';
type RequirementScope = 'all' | 'mandatory' | 'optional';

type EvidenceDraft = {
  requirementId: string;
  capability: string;
  fitStatus: FitStatus;
  evidenceStatus: EvidenceStatus;
  sourceReference: string;
  verificationNote: string;
};

const initialEvidenceDraft: EvidenceDraft = {
  requirementId: '',
  capability: '',
  fitStatus: 'unknown',
  evidenceStatus: 'unknown',
  sourceReference: '',
  verificationNote: '',
};

const fitOptions: Array<{ value: FitStatus; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'met', label: 'Met' },
  { value: 'partially-met', label: 'Partially met' },
  { value: 'not-met', label: 'Not met' },
  { value: 'not-applicable', label: 'Not applicable' },
];

const evidenceOptions: Array<{ value: EvidenceStatus; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'verified', label: 'Verified' },
  { value: 'unverified', label: 'Unverified' },
  { value: 'missing', label: 'Missing' },
  { value: 'conflicting', label: 'Conflicting' },
];

function StatusPill({ children, tone }: { children: string; tone: 'neutral' | 'green' | 'amber' | 'red' | 'violet' | 'blue' }) {
  return <span className={`status-pill status-${tone}`}><span className="status-pill-dot" aria-hidden="true" />{children}</span>;
}

export default function CompanyFitAnalysis() {
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<RequirementScope>('all');
  const [fitFilter, setFitFilter] = useState<FitStatus | 'all'>('all');
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceStatus | 'all'>('all');
  const [draft, setDraft] = useState<EvidenceDraft>(initialEvidenceDraft);
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const hasFilters = Boolean(search.trim()) || scope !== 'all' || fitFilter !== 'all' || evidenceFilter !== 'all';

  const updateDraft = <K extends keyof EvidenceDraft>(key: K, value: EvidenceDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const clearFilters = () => {
    setSearch('');
    setScope('all');
    setFitFilter('all');
    setEvidenceFilter('all');
    clearNotice();
  };

  const handleBackendAction = (action: string) => {
    reportUnavailable(action);
  };

  const handleDraftSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this company fit evidence review');
  };

  const handleFocusReview = () => {
    clearNotice();
    document.getElementById('company-fit-evidence-form')?.focus();
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Project setup & evidence"
        title="Company Fit Analysis"
        description="Compare project requirements with company capabilities only when live records and supporting evidence are available. Unknown remains separate from not met."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} onClick={() => handleBackendAction('generating a gap report')}>Generate gap report</Button>
            <Button type="button" variant="primary" icon={Plus} onClick={handleFocusReview}>Add evidence</Button>
          </>
        )}
      />

      <ApiNotice />

      <div className="metric-grid" aria-label="Company fit summary">
        <MetricCard label="Met" icon={CheckCircle2} note="Awaiting live fit records" />
        <MetricCard label="Partially met" icon={Target} note="Awaiting live fit records" />
        <MetricCard label="Not met" icon={AlertTriangle} note="Not inferred from missing data" />
        <MetricCard label="Unknown" icon={Info} note="No evidence loaded" />
      </div>

      <Panel
        eyebrow="Interpretation guardrail"
        title="No fit conclusion without evidence"
        description="A capability claim needs a connected requirement, a company record, and a source that can be reviewed. This screen does not infer fit from absent data."
      >
        <div className="panel-body">
          <div className="three-column-grid">
            <div className="status-prompt"><StatusPill tone="neutral">Unknown</StatusPill><p>There is not enough connected evidence to assess the requirement.</p></div>
            <div className="status-prompt"><StatusPill tone="amber">Requires review</StatusPill><p>Evidence may exist but has not been verified or has a limitation.</p></div>
            <div className="status-prompt"><StatusPill tone="green">Verified evidence</StatusPill><p>A connected source has been reviewed; fit still remains a separate assessment.</p></div>
          </div>
          <div className="dashboard-disclaimer">
            <ShieldCheck size={16} strokeWidth={1.8} aria-hidden="true" />
            <p><strong>Missing evidence is not proof of a capability gap.</strong> Use the review controls below to record what needs verification when the API is connected.</p>
          </div>
        </div>
      </Panel>

      <div className="content-section stack">
        <Panel
          eyebrow="Requirement-to-capability comparison"
          title="Fit register"
          description="Connected requirement rows will show the requirement, capability evidence, verification state, fit status, and next action."
          action={<span className="status-pill status-neutral"><span className="status-pill-dot" aria-hidden="true" />No live records</span>}
        >
          <div className="panel-toolbar">
            <label className="search-control">
              <Search size={15} strokeWidth={1.8} aria-hidden="true" />
              <span className="sr-only">Search fit register</span>
              <input
                type="search"
                value={search}
                onChange={(event: ChangeEvent<HTMLInputElement>) => { setSearch(event.target.value); clearNotice(); }}
                placeholder="Search requirement, capability, source"
              />
            </label>
            <div className="table-toolbar-right">
              <label className="sr-only" htmlFor="company-fit-status-filter">Filter by fit status</label>
              <SelectInput
                id="company-fit-status-filter"
                value={fitFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setFitFilter(event.target.value as FitStatus | 'all'); clearNotice(); }}
              >
                <option value="all">All fit states</option>
                {fitOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
              <label className="sr-only" htmlFor="company-fit-evidence-filter">Filter by evidence state</label>
              <SelectInput
                id="company-fit-evidence-filter"
                value={evidenceFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setEvidenceFilter(event.target.value as EvidenceStatus | 'all'); clearNotice(); }}
              >
                <option value="all">All evidence states</option>
                {evidenceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
            </div>
          </div>

          <div className="panel-body" style={{ paddingTop: 0, paddingBottom: 12 }}>
            <div className="table-toolbar">
              <div className="table-toolbar-left">
                <Filter size={15} strokeWidth={1.8} aria-hidden="true" />
                <span className="field-hint">Requirement scope</span>
                <div className="filter-row" role="group" aria-label="Filter by requirement scope">
                  {([
                    { value: 'all', label: 'All' },
                    { value: 'mandatory', label: 'Mandatory' },
                    { value: 'optional', label: 'Optional' },
                  ] as Array<{ value: RequirementScope; label: string }>).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`filter-chip ${scope === option.value ? 'is-active' : ''}`}
                      aria-pressed={scope === option.value}
                      onClick={() => { setScope(option.value); clearNotice(); }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              {hasFilters ? <Button type="button" variant="ghost" onClick={clearFilters}>Clear filters</Button> : null}
            </div>
          </div>

          <DataTable
            label="Company fit requirement-to-capability comparison"
            headers={['Requirement', 'Company capability', 'Evidence / verification', 'Fit', 'Source', 'Next action']}
          >
            <tr>
              <td colSpan={6}>
                <EmptyState
                  className="table-empty-state"
                  icon={FileSearch}
                  title={hasFilters ? 'No matching fit records' : 'No fit records loaded'}
                  description={hasFilters
                    ? 'The current filters are ready, but no connected requirement or capability records are available to match.'
                    : 'Requirement-to-capability comparisons, source references, verification states, and fit outcomes will appear here when live project and company data are connected.'}
                />
              </td>
            </tr>
          </DataTable>

          <div className="panel-body" style={{ paddingTop: 12 }}>
            <div className="dashboard-disclaimer">
              <ClipboardCheck size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Actions are prepared, not completed.</strong> View requirement, view source, request information, recheck fit, and export actions cannot run until a backend API supplies live records.</p>
            </div>
          </div>
        </Panel>

        <div className="split-grid">
          <Panel
            eyebrow="Evidence / verification"
            title="Prepare an evidence review"
            description="These entries stay in local form state. Saving or attaching evidence is unavailable in the frontend-only workspace."
          >
            <form id="company-fit-evidence-form" className="panel-body" onSubmit={handleDraftSubmit}>
              <div className="form-grid">
                <Field label="Requirement ID" htmlFor="company-fit-requirement-id" hint="Use the identifier from a connected requirement record.">
                  <TextInput
                    id="company-fit-requirement-id"
                    value={draft.requirementId}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('requirementId', event.target.value)}
                    placeholder="e.g. connected requirement ID"
                  />
                </Field>
                <Field label="Company capability" htmlFor="company-fit-capability" hint="Describe the capability only when supported by a company record.">
                  <TextInput
                    id="company-fit-capability"
                    value={draft.capability}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('capability', event.target.value)}
                    placeholder="Enter a capability to review"
                  />
                </Field>
                <Field label="Fit status" htmlFor="company-fit-fit-status" hint="Unknown is the safe state when evidence is incomplete.">
                  <SelectInput
                    id="company-fit-fit-status"
                    value={draft.fitStatus}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('fitStatus', event.target.value as FitStatus)}
                  >
                    {fitOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field label="Evidence verification" htmlFor="company-fit-evidence-status" hint="Verification must be supported by a connected source review.">
                  <SelectInput
                    id="company-fit-evidence-status"
                    value={draft.evidenceStatus}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('evidenceStatus', event.target.value as EvidenceStatus)}
                  >
                    {evidenceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field className="field-full" label="Source / page reference" htmlFor="company-fit-source-reference" hint="Enter a document name, page, sheet, or section when a source is available.">
                  <TextInput
                    id="company-fit-source-reference"
                    value={draft.sourceReference}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('sourceReference', event.target.value)}
                    placeholder="No source reference connected"
                  />
                </Field>
                <Field className="field-full" label="Verification note" htmlFor="company-fit-verification-note" hint="Record what should be checked; do not imply that the check has happened.">
                  <TextArea
                    id="company-fit-verification-note"
                    value={draft.verificationNote}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('verificationNote', event.target.value)}
                    placeholder="Enter a review note or information request"
                  />
                </Field>
              </div>
              <FormActions>
                <Button type="button" variant="secondary" icon={ExternalLink} onClick={() => handleBackendAction('opening the supporting source')}>View source</Button>
                <Button type="button" variant="ghost" onClick={() => handleBackendAction('requesting more information')}>Request information</Button>
                <Button type="submit" variant="primary" icon={FileCheck2}>Save evidence review</Button>
              </FormActions>
              {message ? <InlineNotice variant="info">{message}</InlineNotice> : null}
            </form>
          </Panel>

          <div className="stack">
            <Panel
              eyebrow="Verification queue"
              title="What still needs review"
              description="This summary is intentionally empty until live findings and supporting documents are available."
            >
              <div className="panel-body">
                <EmptyState
                  icon={ShieldCheck}
                  title="No verification findings loaded"
                  description="Missing documents, unverified claims, conflicting evidence, and actions to close gaps will be listed here from connected data."
                />
              </div>
            </Panel>

            <Panel
              eyebrow="Connected actions"
              title="Recheck when data is available"
              description="Rechecking fit requires a live project requirement set and company capability evidence."
            >
              <div className="panel-body">
                <div className="key-value-list">
                  <div className="key-value-row"><span>Requirement source</span><strong>Not connected</strong></div>
                  <div className="key-value-row"><span>Company source</span><strong>Not connected</strong></div>
                  <div className="key-value-row"><span>Last fit check</span><strong>Unknown</strong></div>
                </div>
                <div className="form-actions form-actions-left">
                  <Button type="button" variant="secondary" icon={RefreshCw} onClick={() => handleBackendAction('rechecking company fit')}>Recheck fit</Button>
                  <Button type="button" variant="ghost" icon={Building2} onClick={() => handleBackendAction('opening the company capability profile')}>View company profile</Button>
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </>
  );
}
