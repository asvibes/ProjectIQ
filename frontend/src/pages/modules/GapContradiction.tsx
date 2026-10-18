import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  AlertTriangle,
  Check,
  CircleHelp,
  FileText,
  GitCompareArrows,
  Link2,
  ListFilter,
  RotateCcw,
  Search,
  ShieldAlert,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  DataTable,
  EmptyState,
  Field,
  FormActions,
  InlineNotice,
  PageHeader,
  Panel,
  SelectInput,
  StatusPill,
  Tabs,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type FindingTab = 'gaps' | 'contradictions';
type Severity = 'low' | 'medium' | 'high' | 'critical';
type ReviewStatus = 'unreviewed' | 'in-review' | 'reviewed' | 'resolved';
type FilterValue<T extends string> = 'all' | T;

type FindingDraft = {
  title: string;
  affectedRequirement: string;
  requirementSource: string;
  comparisonSource: string;
  evidenceSummary: string;
  severity: Severity;
  status: ReviewStatus;
  reviewNote: string;
};

const initialDraft: FindingDraft = {
  title: '',
  affectedRequirement: '',
  requirementSource: '',
  comparisonSource: '',
  evidenceSummary: '',
  severity: 'medium',
  status: 'unreviewed',
  reviewNote: '',
};

const severityOptions: Array<{ value: Severity; label: string }> = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

const statusOptions: Array<{ value: ReviewStatus; label: string }> = [
  { value: 'unreviewed', label: 'Unreviewed' },
  { value: 'in-review', label: 'In review' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'resolved', label: 'Resolved' },
];

const severityTone: Record<Severity, 'neutral' | 'amber' | 'red' | 'violet'> = {
  low: 'neutral',
  medium: 'amber',
  high: 'red',
  critical: 'violet',
};

const statusTone: Record<ReviewStatus, 'neutral' | 'blue' | 'green' | 'violet'> = {
  unreviewed: 'neutral',
  'in-review': 'blue',
  reviewed: 'violet',
  resolved: 'green',
};

function getLabel<T extends string>(options: Array<{ value: T; label: string }>, value: T): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

export default function GapContradiction() {
  const [activeTab, setActiveTab] = useState<FindingTab>('gaps');
  const [search, setSearch] = useState('');
  const [severityFilter, setSeverityFilter] = useState<FilterValue<Severity>>('all');
  const [statusFilter, setStatusFilter] = useState<FilterValue<ReviewStatus>>('all');
  const [draft, setDraft] = useState<FindingDraft>(initialDraft);
  const { message, reportUnavailable, clearMessage } = useApiNotice();

  const hasFilters = search.trim().length > 0 || severityFilter !== 'all' || statusFilter !== 'all';
  const tabLabel = activeTab === 'gaps' ? 'gaps' : 'contradictions';

  function updateDraft<K extends keyof FindingDraft>(key: K, value: FindingDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function handleDraftChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value } = event.target;
    if (name === 'severity') updateDraft('severity', value as Severity);
    if (name === 'status') updateDraft('status', value as ReviewStatus);
    if (name === 'title') updateDraft('title', value);
    if (name === 'affectedRequirement') updateDraft('affectedRequirement', value);
    if (name === 'requirementSource') updateDraft('requirementSource', value);
    if (name === 'comparisonSource') updateDraft('comparisonSource', value);
    if (name === 'evidenceSummary') updateDraft('evidenceSummary', value);
    if (name === 'reviewNote') updateDraft('reviewNote', value);
  }

  function handleRequestReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    reportUnavailable(`${activeTab === 'gaps' ? 'Gap' : 'Contradiction'} review request`);
  }

  function handleReviewAction(action: 'Review finding' | 'Resolve finding') {
    reportUnavailable(action);
  }

  function clearFilters() {
    setSearch('');
    setSeverityFilter('all');
    setStatusFilter('all');
    clearMessage();
  }

  return (
    <>
      <PageHeader
        eyebrow="Project evidence"
        title="Gap & Contradiction Detection"
        description="Compare requirement evidence across sources, then review missing information and conflicting details without treating unknown evidence as a failed requirement."
        actions={
          <Button type="button" variant="secondary" icon={RotateCcw} onClick={clearFilters} disabled={!hasFilters}>
            Reset filters
          </Button>
        }
      />

      <ApiNotice />

      <div className="content-section">
        <Panel
          eyebrow="Review queue"
          title="Findings"
          description="Connected finding records will appear here. No gaps, contradictions, source excerpts, or statuses are prefilled."
          action={<Tabs label="Finding type" value={activeTab} onChange={(value: string) => setActiveTab(value as FindingTab)} items={[{ id: 'gaps', label: 'Gaps' }, { id: 'contradictions', label: 'Contradictions' }]} />}
        >
          <div className="panel-toolbar">
            <div className="table-toolbar-left">
              <label className="search-control" htmlFor="finding-search">
                <Search size={15} aria-hidden="true" />
                <span className="sr-only">Search {tabLabel}</span>
                <input id="finding-search" value={search} onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)} placeholder={`Search ${tabLabel}`} />
              </label>
              <span className="status-prompt"><ListFilter size={14} aria-hidden="true" /> Filters apply to connected records only.</span>
            </div>
            <div className="table-toolbar-right">
              <Field label="Severity" htmlFor="severity-filter">
                <SelectInput id="severity-filter" value={severityFilter} onChange={(event: ChangeEvent<HTMLSelectElement>) => setSeverityFilter(event.target.value as FilterValue<Severity>)}>
                  <option value="all">All severities</option>
                  {severityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </Field>
              <Field label="Status" htmlFor="status-filter">
                <SelectInput id="status-filter" value={statusFilter} onChange={(event: ChangeEvent<HTMLSelectElement>) => setStatusFilter(event.target.value as FilterValue<ReviewStatus>)}>
                  <option value="all">All statuses</option>
                  {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </Field>
            </div>
          </div>

          <DataTable
            label={`${tabLabel} review queue`}
            headers={['Finding', 'Severity', 'Affected requirement', 'Sources', 'Status', 'Actions']}
            emptyTitle={hasFilters ? `No matching ${tabLabel}` : `No ${tabLabel} loaded`}
            emptyDescription={hasFilters
              ? `No connected ${tabLabel} match the current filters. Nothing is hidden or simulated.`
              : `Connected ${tabLabel}, affected requirements, source comparisons, and review controls will appear here when the API is connected.`}
          />
        </Panel>
      </div>

      <div className="content-section split-grid">
        <Panel
          eyebrow="Source comparison"
          title={`Prepare a ${activeTab === 'gaps' ? 'gap' : 'contradiction'} review`}
          description="Capture the references and evidence you want reviewed. These fields remain local to this screen until a connected service can receive them."
        >
          <form className="panel-body" onSubmit={handleRequestReview}>
            <div className="form-grid">
              <Field className="field-full" label="Finding title" htmlFor="finding-title" required hint="Use a concise description supported by the entered evidence.">
                <TextInput id="finding-title" name="title" value={draft.title} onChange={handleDraftChange} placeholder={`Describe the ${activeTab === 'gaps' ? 'missing information' : 'conflicting detail'}`} required />
              </Field>
              <Field className="field-full" label="Affected requirement" htmlFor="affected-requirement" required hint="Enter the requirement identifier or wording from a connected record.">
                <TextArea id="affected-requirement" name="affectedRequirement" value={draft.affectedRequirement} onChange={handleDraftChange} placeholder="Requirement ID or requirement text" required />
              </Field>
              <Field label="Requirement source" htmlFor="requirement-source" required hint="Source name or reference supplied by the user.">
                <TextInput id="requirement-source" name="requirementSource" value={draft.requirementSource} onChange={handleDraftChange} placeholder="Document or source reference" required />
              </Field>
              <Field label="Comparison source" htmlFor="comparison-source" required hint="The second source used for comparison, when applicable.">
                <TextInput id="comparison-source" name="comparisonSource" value={draft.comparisonSource} onChange={handleDraftChange} placeholder="Document or source reference" required />
              </Field>
              <Field className="field-full" label="Evidence summary" htmlFor="evidence-summary" hint="Record only what the sources say. Do not add an unverified conclusion.">
                <TextArea id="evidence-summary" name="evidenceSummary" value={draft.evidenceSummary} onChange={handleDraftChange} placeholder="Enter the relevant comparison context or evidence summary" />
              </Field>
              <Field label="Severity" htmlFor="finding-severity">
                <SelectInput id="finding-severity" name="severity" value={draft.severity} onChange={handleDraftChange}>
                  {severityOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </Field>
              <Field label="Review status" htmlFor="finding-status" hint="Status is a local draft value until saved by a connected service.">
                <SelectInput id="finding-status" name="status" value={draft.status} onChange={handleDraftChange}>
                  {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </Field>
            </div>
            <FormActions>
              <Button type="submit" variant="primary" icon={GitCompareArrows}>Request review</Button>
            </FormActions>
            {message ? <InlineNotice>{message}</InlineNotice> : null}
          </form>
        </Panel>

        <Panel
          eyebrow="Review / resolve"
          title="Decision controls"
          description="Review and resolution actions stop at the API boundary. Entered values remain on screen after each attempt."
        >
          <div className="panel-body stack">
            <div className="two-column-grid" aria-label="Source comparison summary">
              <div className="status-prompt stack stack-sm">
                <div className="panel-eyebrow"><FileText size={15} aria-hidden="true" /> Requirement evidence</div>
                <p>{draft.requirementSource || 'No requirement source entered'}</p>
                <small>{draft.affectedRequirement || 'Affected requirement will appear here'}</small>
              </div>
              <div className="status-prompt stack stack-sm">
                <div className="panel-eyebrow"><Link2 size={15} aria-hidden="true" /> Comparison evidence</div>
                <p>{draft.comparisonSource || 'No comparison source entered'}</p>
                <small>{draft.evidenceSummary || 'Evidence summary will appear here'}</small>
              </div>
            </div>

            <div className="filter-row" aria-label="Draft finding status">
              <StatusPill tone={severityTone[draft.severity]}>{getLabel(severityOptions, draft.severity)} severity</StatusPill>
              <StatusPill tone={statusTone[draft.status]}>{getLabel(statusOptions, draft.status)}</StatusPill>
            </div>

            <Field label="Review note" htmlFor="review-note" hint="Keep reviewer context with the local draft; it is not persisted.">
              <TextArea id="review-note" name="reviewNote" value={draft.reviewNote} onChange={handleDraftChange} placeholder="Add a note for the review or resolution decision" />
            </Field>

            <div className="form-actions form-actions-left">
              <Button type="button" variant="secondary" icon={Check} onClick={() => handleReviewAction('Review finding')}>Mark reviewed</Button>
              <Button type="button" variant="danger" icon={ShieldAlert} onClick={() => handleReviewAction('Resolve finding')}>Resolve finding</Button>
            </div>
            <EmptyState
              icon={CircleHelp}
              title="No connected finding selected"
              description="These controls are ready for a selected API finding. Nothing is marked reviewed or resolved in this frontend-only workspace."
            />
            <div className="dashboard-disclaimer">
              <AlertTriangle size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Evidence stays explicit.</strong> Missing evidence is not treated as proof of a gap, and an unresolved difference is not treated as a confirmed contradiction.</p>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
