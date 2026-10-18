import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  AlertTriangle,
  BookOpenCheck,
  Download,
  FileSearch,
  Filter,
  Plus,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  Target,
  UserRound,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  DataTable,
  EmptyState,
  Field,
  FormActions,
  InlineNotice,
  Panel,
  PageHeader,
  SelectInput,
  StatusPill,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type RiskCategory = 'missing-information' | 'potential-issue' | 'contradiction' | 'unverified-assumption' | 'external-verification';
type RiskLikelihood = 'unknown' | 'rare' | 'unlikely' | 'possible' | 'likely' | 'almost-certain';
type RiskImpact = 'unknown' | 'minor' | 'moderate' | 'major' | 'severe';
type RiskSeverity = 'unknown' | 'low' | 'medium' | 'high' | 'critical';
type RiskStatus = 'open' | 'accepted' | 'mitigation-planned' | 'resolved';
type RiskStatusFilter = 'all' | RiskStatus;

type RiskDraft = {
  riskId: string;
  category: RiskCategory;
  description: string;
  evidence: string;
  source: string;
  consequence: string;
  likelihood: RiskLikelihood;
  impact: RiskImpact;
  severity: RiskSeverity;
  mitigation: string;
  owner: string;
  status: RiskStatus;
};

const initialDraft: RiskDraft = {
  riskId: '',
  category: 'missing-information',
  description: '',
  evidence: '',
  source: '',
  consequence: '',
  likelihood: 'unknown',
  impact: 'unknown',
  severity: 'unknown',
  mitigation: '',
  owner: '',
  status: 'open',
};

const categoryOptions: Array<{ value: RiskCategory; label: string }> = [
  { value: 'missing-information', label: 'Missing information' },
  { value: 'potential-issue', label: 'Potential issue' },
  { value: 'contradiction', label: 'Contradiction' },
  { value: 'unverified-assumption', label: 'Unverified assumption' },
  { value: 'external-verification', label: 'External verification' },
];

const statusOptions: Array<{ value: RiskStatus; label: string }> = [
  { value: 'open', label: 'Open' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'mitigation-planned', label: 'Mitigation planned' },
  { value: 'resolved', label: 'Resolved' },
];

const likelihoodOptions: Array<{ value: RiskLikelihood; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'rare', label: 'Rare' },
  { value: 'unlikely', label: 'Unlikely' },
  { value: 'possible', label: 'Possible' },
  { value: 'likely', label: 'Likely' },
  { value: 'almost-certain', label: 'Almost certain' },
];

const impactOptions: Array<{ value: RiskImpact; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'minor', label: 'Minor' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'major', label: 'Major' },
  { value: 'severe', label: 'Severe' },
];

const severityOptions: Array<{ value: RiskSeverity; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const matrixLikelihoodLevels = ['Almost certain', 'Likely', 'Possible', 'Unlikely', 'Rare'] as const;
const matrixImpactLevels = ['Minor', 'Moderate', 'Major', 'Severe', 'Critical'] as const;

function statusTone(status: RiskStatus): 'neutral' | 'green' | 'amber' | 'red' | 'violet' | 'blue' {
  switch (status) {
    case 'resolved':
      return 'green';
    case 'mitigation-planned':
      return 'blue';
    case 'accepted':
      return 'violet';
    case 'open':
    default:
      return 'amber';
  }
}

function statusLabel(status: RiskStatus): string {
  return statusOptions.find((option) => option.value === status)?.label ?? 'Open';
}

function categoryLabel(category: RiskCategory): string {
  return categoryOptions.find((option) => option.value === category)?.label ?? 'Missing information';
}

export default function RiskAnalysis() {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<RiskCategory | 'all'>('all');
  const [statusFilter, setStatusFilter] = useState<RiskStatusFilter>('all');
  const [draft, setDraft] = useState<RiskDraft>(initialDraft);
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const hasFilters = Boolean(search.trim()) || categoryFilter !== 'all' || statusFilter !== 'all';

  const updateDraft = <K extends keyof RiskDraft>(key: K, value: RiskDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const clearFilters = () => {
    setSearch('');
    setCategoryFilter('all');
    setStatusFilter('all');
    clearNotice();
  };

  const focusRiskForm = () => {
    clearNotice();
    document.getElementById('risk-form-risk-id')?.focus();
  };

  const handleBackendAction = (action: string) => {
    reportUnavailable(action);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this risk draft');
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Delivery & capacity"
        title="Risk Analysis"
        description="Prepare an evidence-led risk register with likelihood, impact, ownership, and mitigation fields. Live risks are not loaded until an API is connected."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} onClick={() => handleBackendAction('exporting the risk register')}>Export register</Button>
            <Button type="button" variant="primary" icon={Plus} onClick={focusRiskForm}>Add risk</Button>
          </>
        )}
      />

      <ApiNotice />

      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

      <div className="metric-grid" aria-label="Risk register summary">
        <section className="metric-card">
          <div className="metric-card-top"><span>Risks loaded</span><ShieldAlert size={17} strokeWidth={1.8} aria-hidden="true" /></div>
          <strong className="metric-value">—</strong>
          <span className="metric-note">No risk data is loaded</span>
        </section>
        <section className="metric-card">
          <div className="metric-card-top"><span>High severity</span><AlertTriangle size={17} strokeWidth={1.8} aria-hidden="true" /></div>
          <strong className="metric-value">—</strong>
          <span className="metric-note">Not calculated without live risks</span>
        </section>
        <section className="metric-card">
          <div className="metric-card-top"><span>Unassigned</span><UserRound size={17} strokeWidth={1.8} aria-hidden="true" /></div>
          <strong className="metric-value">—</strong>
          <span className="metric-note">No owners available to review</span>
        </section>
        <section className="metric-card">
          <div className="metric-card-top"><span>Mitigation coverage</span><Target size={17} strokeWidth={1.8} aria-hidden="true" /></div>
          <strong className="metric-value">—</strong>
          <span className="metric-note">No live score or calculation</span>
        </section>
      </div>

      <Panel
        eyebrow="Severity vocabulary"
        title="Keep risk evidence and severity distinct"
        description="Severity is a recorded risk field, not a browser-calculated score. Unknown likelihood or impact stays unknown until supported by connected evidence."
      >
        <div className="panel-body">
          <div className="filter-row" aria-label="Risk severity vocabulary">
            {severityOptions.map((option) => (
              <StatusPill key={option.value} tone={option.value === 'critical' ? 'red' : option.value === 'high' ? 'amber' : option.value === 'medium' ? 'violet' : 'neutral'}>{option.label}</StatusPill>
            ))}
          </div>
          <div className="dashboard-disclaimer">
            <BookOpenCheck size={16} strokeWidth={1.8} aria-hidden="true" />
            <p><strong>No severity is inferred from missing evidence.</strong> Use the register to record a connected assessment when the backend supplies risk records and sources.</p>
          </div>
        </div>
      </Panel>

      <div className="content-section stack">
        <Panel
          eyebrow="Likelihood / impact matrix"
          title="Risk position overview"
          description="The matrix is ready for connected risk positions. It does not calculate, score, or place risks in the browser."
          action={<StatusPill tone="neutral">No live risks</StatusPill>}
        >
          <div className="panel-body">
            <div className="risk-matrix-shell" aria-label="Likelihood versus impact matrix">
              <div className="risk-matrix-y-label" aria-hidden="true">Likelihood</div>
              <div className="risk-matrix-content">
                <div className="risk-matrix-column-labels" aria-hidden="true">
                  <span />
                  {matrixImpactLevels.map((impact) => <span key={impact}>{impact}</span>)}
                </div>
                <div className="risk-matrix-grid">
                  {matrixLikelihoodLevels.map((likelihood) => (
                    <div className="risk-matrix-row" key={likelihood}>
                      <span className="risk-matrix-row-label">{likelihood}</span>
                      {matrixImpactLevels.map((impact) => (
                        <div className="risk-matrix-cell" key={`${likelihood}-${impact}`} aria-label={`${likelihood} likelihood and ${impact} impact: no risk data is loaded`}>
                          <span aria-hidden="true">—</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
                <p className="risk-matrix-x-label" aria-hidden="true">Impact</p>
              </div>
            </div>
            <EmptyState
              icon={ShieldAlert}
              title="No risk data is loaded"
              description="The likelihood/impact matrix will show connected risk positions when project risk records are available. No placeholder risks or live score are shown."
              className="matrix-empty-state"
            />
          </div>
        </Panel>

        <Panel
          eyebrow="Risk register"
          title="Search, filter, and review risks"
          description="Connected rows will show risk ID, category, description, evidence, source, consequence, likelihood, impact, severity, mitigation, owner, and status."
          action={<StatusPill tone="neutral">No live risks</StatusPill>}
        >
          <div className="panel-toolbar">
            <label className="search-control">
              <Search size={15} strokeWidth={1.8} aria-hidden="true" />
              <span className="sr-only">Search risk register</span>
              <input
                type="search"
                value={search}
                onChange={(event: ChangeEvent<HTMLInputElement>) => { setSearch(event.target.value); clearNotice(); }}
                placeholder="Search ID, description, evidence, owner"
              />
            </label>
            <div className="table-toolbar-right">
              <label className="sr-only" htmlFor="risk-category-filter">Filter by risk category</label>
              <SelectInput
                id="risk-category-filter"
                value={categoryFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setCategoryFilter(event.target.value as RiskCategory | 'all'); clearNotice(); }}
              >
                <option value="all">All categories</option>
                {categoryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
              <label className="sr-only" htmlFor="risk-status-filter">Filter by risk status</label>
              <SelectInput
                id="risk-status-filter"
                value={statusFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setStatusFilter(event.target.value as RiskStatusFilter); clearNotice(); }}
              >
                <option value="all">All statuses</option>
                {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
            </div>
          </div>

          <div className="panel-body" style={{ paddingTop: 0, paddingBottom: 12 }}>
            <div className="table-toolbar">
              <div className="table-toolbar-left">
                <Filter size={15} strokeWidth={1.8} aria-hidden="true" />
                <span className="field-hint">Status view</span>
                <div className="filter-row" role="group" aria-label="Filter by risk status">
                  {([{ value: 'all', label: 'All' }, ...statusOptions] as Array<{ value: RiskStatusFilter; label: string }>).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`filter-chip ${statusFilter === option.value ? 'is-active' : ''}`}
                      aria-pressed={statusFilter === option.value}
                      onClick={() => { setStatusFilter(option.value); clearNotice(); }}
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
            label="Risk register"
            headers={['Risk ID / description', 'Category', 'Evidence / source', 'Consequence', 'Likelihood / impact', 'Severity', 'Mitigation', 'Owner', 'Status']}
          >
            <tr>
              <td colSpan={9}>
                <EmptyState
                  className="table-empty-state"
                  icon={FileSearch}
                  title="No risk data is loaded"
                  description={hasFilters
                    ? 'The current filters are ready, but no connected risk records are available to match. Nothing is hidden or simulated.'
                    : 'Risk IDs, descriptions, categories, supporting evidence, source references, mitigation, owners, and statuses will appear here when the Risk API is connected.'}
                />
              </td>
            </tr>
          </DataTable>

          <div className="panel-body" style={{ paddingTop: 12 }}>
            <div className="dashboard-disclaimer">
              <SlidersHorizontal size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Register actions are prepared, not completed.</strong> Export, source viewing, assignment, acceptance, rejection, mitigation, and resolution actions cannot run until a backend API supplies live risks.</p>
            </div>
          </div>
        </Panel>

        <div className="split-grid">
          <Panel
            eyebrow="Add / edit risk"
            title="Prepare a risk record"
            description="These entries stay in local form state. Saving or editing a connected risk is unavailable in the frontend-only workspace."
          >
            <form id="risk-form" className="panel-body" onSubmit={handleSubmit}>
              <div className="form-grid">
                <Field label="Risk ID" htmlFor="risk-form-risk-id" hint="Use the identifier from a connected risk record when editing.">
                  <TextInput
                    id="risk-form-risk-id"
                    value={draft.riskId}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('riskId', event.target.value)}
                    placeholder="Enter a risk ID"
                  />
                </Field>
                <Field label="Category" htmlFor="risk-form-category" required>
                  <SelectInput
                    id="risk-form-category"
                    value={draft.category}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('category', event.target.value as RiskCategory)}
                  >
                    {categoryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field className="field-full" label="Risk description" htmlFor="risk-form-description" required hint="Describe the uncertainty or potential issue without presenting it as a confirmed outcome.">
                  <TextArea
                    id="risk-form-description"
                    value={draft.description}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('description', event.target.value)}
                    placeholder="Describe the risk to review"
                  />
                </Field>
                <Field className="field-full" label="Supporting evidence" htmlFor="risk-form-evidence" hint="Record what the evidence says; an empty field does not prove that a risk is absent.">
                  <TextArea
                    id="risk-form-evidence"
                    value={draft.evidence}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('evidence', event.target.value)}
                    placeholder="Enter evidence notes or leave blank when evidence is unavailable"
                  />
                </Field>
                <Field label="Source / page reference" htmlFor="risk-form-source" hint="Source references remain user-entered until documents are connected.">
                  <TextInput
                    id="risk-form-source"
                    value={draft.source}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('source', event.target.value)}
                    placeholder="Document, page, section, or URL"
                  />
                </Field>
                <Field label="Owner role" htmlFor="risk-form-owner">
                  <TextInput
                    id="risk-form-owner"
                    value={draft.owner}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('owner', event.target.value)}
                    placeholder="Role responsible for follow-up"
                  />
                </Field>
                <Field className="field-full" label="Potential consequence" htmlFor="risk-form-consequence" hint="Describe the consequence to consider; do not calculate a project outcome here.">
                  <TextArea
                    id="risk-form-consequence"
                    value={draft.consequence}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('consequence', event.target.value)}
                    placeholder="Describe the potential consequence"
                  />
                </Field>
                <Field label="Likelihood" htmlFor="risk-form-likelihood" hint="Unknown remains distinct from rare.">
                  <SelectInput
                    id="risk-form-likelihood"
                    value={draft.likelihood}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('likelihood', event.target.value as RiskLikelihood)}
                  >
                    {likelihoodOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field label="Impact" htmlFor="risk-form-impact" hint="Unknown remains distinct from minor.">
                  <SelectInput
                    id="risk-form-impact"
                    value={draft.impact}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('impact', event.target.value as RiskImpact)}
                  >
                    {impactOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field label="Severity" htmlFor="risk-form-severity" hint="Record a connected assessment; no score is calculated here.">
                  <SelectInput
                    id="risk-form-severity"
                    value={draft.severity}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('severity', event.target.value as RiskSeverity)}
                  >
                    {severityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field label="Status" htmlFor="risk-form-status">
                  <SelectInput
                    id="risk-form-status"
                    value={draft.status}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('status', event.target.value as RiskStatus)}
                  >
                    {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field className="field-full" label="Mitigation / response" htmlFor="risk-form-mitigation" hint="Describe the proposed response without implying it has been accepted or completed.">
                  <TextArea
                    id="risk-form-mitigation"
                    value={draft.mitigation}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('mitigation', event.target.value)}
                    placeholder="Enter a mitigation or verification action"
                  />
                </Field>
              </div>
              <FormActions>
                <Button type="button" variant="secondary" icon={FileSearch} onClick={() => handleBackendAction('opening the supporting risk source')}>View source</Button>
                <Button type="button" variant="ghost" onClick={() => handleBackendAction('assigning this risk owner')}>Assign owner</Button>
                <Button type="submit" variant="primary" icon={Plus}>Save risk</Button>
              </FormActions>
              {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
            </form>
          </Panel>

          <Panel
            eyebrow="Review guidance"
            title="Evidence before conclusion"
            description="Use these guardrails when a connected risk record is eventually available."
          >
            <div className="panel-body">
              <div className="status-prompt"><StatusPill tone="neutral">Unknown</StatusPill><p>Incomplete evidence keeps likelihood or impact unknown; it is not treated as zero.</p></div>
              <div className="status-prompt"><StatusPill tone="amber">Requires review</StatusPill><p>Contradictions, assumptions, and external verification needs remain visible for follow-up.</p></div>
              <div className="status-prompt"><StatusPill tone="green">Resolved</StatusPill><p>Use only when a connected workflow confirms the risk has been resolved; this screen does not mark it automatically.</p></div>
              <div className="dashboard-disclaimer">
                <AlertTriangle size={16} strokeWidth={1.8} aria-hidden="true" />
                <p><strong>No project decision is made here.</strong> Risk entries support review and accountability; they do not produce an autonomous bid/no-bid conclusion.</p>
              </div>
              <div className="form-section-copy"><strong>Current draft category:</strong> {categoryLabel(draft.category)}<br /><strong>Current draft status:</strong> <StatusPill tone={statusTone(draft.status)}>{statusLabel(draft.status)}</StatusPill><br /><strong>Current draft severity:</strong> {draft.severity === 'unknown' ? 'Unknown' : draft.severity}</div>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
