import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  ClipboardCheck,
  Download,
  ExternalLink,
  FileSearch,
  Info,
  Pencil,
  Search,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  DataTable,
  EmptyState,
  Field,
  InlineNotice,
  Panel,
  PageHeader,
  SelectInput,
  StatusPill,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type RequirementScope = 'all' | 'mandatory' | 'optional';
type ComplianceStatus = 'unknown' | 'partially-met' | 'not-met' | 'conflicting' | 'verified';
type ReviewStatus = 'all' | 'unreviewed' | 'in-review' | 'reviewed';
type RequirementSort = 'id-asc' | 'id-desc' | 'mandatory-first' | 'review-status';

type ReviewDraft = {
  requirementId: string;
  description: string;
  requirementType: 'mandatory' | 'optional';
  complianceStatus: ComplianceStatus;
  evidenceSummary: string;
  sourceReference: string;
  assignee: string;
  reviewer: string;
  reviewStatus: Exclude<ReviewStatus, 'all'>;
};

const initialDraft: ReviewDraft = {
  requirementId: '',
  description: '',
  requirementType: 'mandatory',
  complianceStatus: 'unknown',
  evidenceSummary: '',
  sourceReference: '',
  assignee: '',
  reviewer: '',
  reviewStatus: 'unreviewed',
};

const complianceOptions: Array<{ value: ComplianceStatus; label: string }> = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'partially-met', label: 'Partially met' },
  { value: 'not-met', label: 'Not met' },
  { value: 'conflicting', label: 'Conflicting' },
  { value: 'verified', label: 'Verified' },
];

const reviewOptions: Array<{ value: ReviewStatus; label: string }> = [
  { value: 'all', label: 'All review states' },
  { value: 'unreviewed', label: 'Unreviewed' },
  { value: 'in-review', label: 'In review' },
  { value: 'reviewed', label: 'Reviewed' },
];

const sortOptions: Array<{ value: RequirementSort; label: string }> = [
  { value: 'id-asc', label: 'ID, A–Z' },
  { value: 'id-desc', label: 'ID, Z–A' },
  { value: 'mandatory-first', label: 'Mandatory first' },
  { value: 'review-status', label: 'Review status' },
];

function complianceTone(status: ComplianceStatus): 'neutral' | 'green' | 'amber' | 'red' | 'violet' {
  switch (status) {
    case 'verified':
      return 'green';
    case 'partially-met':
      return 'amber';
    case 'not-met':
      return 'red';
    case 'conflicting':
      return 'violet';
    case 'unknown':
    default:
      return 'neutral';
  }
}

function complianceLabel(status: ComplianceStatus): string {
  return complianceOptions.find((option) => option.value === status)?.label ?? 'Unknown';
}

function sortRequirements(records: ReviewDraft[], sortBy: RequirementSort): ReviewDraft[] {
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
  return [...records].sort((left, right) => {
    if (sortBy === 'mandatory-first') {
      return left.requirementType === right.requirementType ? collator.compare(left.requirementId, right.requirementId) : left.requirementType === 'mandatory' ? -1 : 1;
    }
    if (sortBy === 'review-status') {
      return collator.compare(left.reviewStatus, right.reviewStatus) || collator.compare(left.requirementId, right.requirementId);
    }
    const order = collator.compare(left.requirementId, right.requirementId);
    return sortBy === 'id-desc' ? -order : order;
  });
}

export default function RequirementAnalysis() {
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<RequirementScope>('all');
  const [complianceFilter, setComplianceFilter] = useState<ComplianceStatus | 'all'>('all');
  const [reviewFilter, setReviewFilter] = useState<ReviewStatus>('all');
  const [sortBy, setSortBy] = useState<RequirementSort>('id-asc');
  const [draft, setDraft] = useState<ReviewDraft>(initialDraft);
  const { message, clearMessage, reportUnavailable } = useApiNotice();

  const hasFilters = Boolean(search.trim()) || scope !== 'all' || complianceFilter !== 'all' || reviewFilter !== 'all';
  // Deliberately empty until the Requirements API is connected; never seed example rows.
  const connectedRecords: ReviewDraft[] = [];
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleRequirements = sortRequirements(connectedRecords.filter((record) => {
    const matchesSearch = !normalizedSearch || [record.requirementId, record.description, record.sourceReference].some((value) => value.toLocaleLowerCase().includes(normalizedSearch));
    return matchesSearch
      && (scope === 'all' || record.requirementType === scope)
      && (complianceFilter === 'all' || record.complianceStatus === complianceFilter)
      && (reviewFilter === 'all' || record.reviewStatus === reviewFilter);
  }), sortBy);

  const updateDraft = <K extends keyof ReviewDraft>(key: K, value: ReviewDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearMessage();
  };

  const handleExport = () => {
    reportUnavailable('exporting the requirement checklist as CSV');
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this requirement review');
  };

  const handleClearFilters = () => {
    setSearch('');
    setScope('all');
    setComplianceFilter('all');
    setReviewFilter('all');
    setSortBy('id-asc');
    clearMessage();
  };

  const loadRequirementForReview = (record: ReviewDraft) => {
    setDraft(record);
    clearMessage();
    document.getElementById('requirement-review-form')?.focus();
  };

  const handleSourceAction = () => {
    reportUnavailable('opening this requirement source');
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Project setup & evidence"
        title="Requirement Analysis"
        description="Review tender requirements against their source evidence without turning missing information into a compliance conclusion. Live requirements are not loaded until an API is connected."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} onClick={handleExport}>Export CSV</Button>
            <Button type="button" variant="primary" icon={Pencil} onClick={() => { clearMessage(); document.getElementById('requirement-review-form')?.focus(); }}>Review requirement</Button>
          </>
        )}
      />

      <ApiNotice />

      <Panel
        eyebrow="Review vocabulary"
        title="Keep evidence states distinct"
        description="These labels describe the available review vocabulary; no requirement status is inferred while connected records are unavailable."
      >
        <div className="panel-body">
          <div className="filter-row" aria-label="Requirement compliance status vocabulary">
            {complianceOptions.map((option) => (
              <StatusPill key={option.value} tone={complianceTone(option.value)}>{option.label}</StatusPill>
            ))}
          </div>
          <div className="dashboard-disclaimer">
            <Info size={16} strokeWidth={1.8} aria-hidden="true" />
            <p><strong>Unknown is not Not met.</strong> Missing, incomplete, or conflicting evidence stays visible for review instead of being converted into a conclusion.</p>
          </div>
        </div>
      </Panel>

      <div className="content-section stack">
        <Panel
          eyebrow="Requirement register"
          title="Search and review requirements"
          description="The register is prepared for connected requirement records. Nothing is fabricated or pre-classified in this frontend."
          action={<StatusPill tone="neutral">No live requirements</StatusPill>}
        >
          <div className="panel-toolbar">
            <label className="search-control">
              <Search size={15} strokeWidth={1.8} aria-hidden="true" />
              <span className="sr-only">Search requirements</span>
              <input
                type="search"
                value={search}
                onChange={(event) => { setSearch(event.target.value); clearMessage(); }}
                placeholder="Search ID, description, source"
              />
            </label>
            <div className="table-toolbar-right">
              <label className="sr-only" htmlFor="requirement-compliance-filter">Filter by compliance status</label>
              <SelectInput
                id="requirement-compliance-filter"
                value={complianceFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setComplianceFilter(event.target.value as ComplianceStatus | 'all'); clearMessage(); }}
              >
                <option value="all">All compliance states</option>
                {complianceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
              <label className="sr-only" htmlFor="requirement-review-filter">Filter by review status</label>
              <SelectInput
                id="requirement-review-filter"
                value={reviewFilter}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setReviewFilter(event.target.value as ReviewStatus); clearMessage(); }}
              >
                {reviewOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
              <label className="sr-only" htmlFor="requirement-sort-order">Sort requirements</label>
              <SelectInput
                id="requirement-sort-order"
                value={sortBy}
                onChange={(event: ChangeEvent<HTMLSelectElement>) => { setSortBy(event.target.value as RequirementSort); clearMessage(); }}
              >
                {sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </SelectInput>
            </div>
          </div>

          <div className="panel-body" style={{ paddingTop: 0, paddingBottom: 12 }}>
            <div className="table-toolbar">
              <div className="table-toolbar-left">
                <span className="field-hint">Requirement type</span>
                <div className="filter-row" role="group" aria-label="Filter by requirement type">
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
                      onClick={() => { setScope(option.value); clearMessage(); }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              {hasFilters ? <Button type="button" variant="ghost" onClick={handleClearFilters}>Clear filters</Button> : null}
            </div>
          </div>

          <DataTable
            label="Requirement register"
            headers={['Requirement', 'Mandatory / optional', 'Compliance', 'Evidence / source', 'Assignee / reviewer', 'Review status', 'Actions']}
            emptyTitle={hasFilters ? 'No matching requirements' : 'No requirements loaded'}
            emptyDescription={hasFilters
              ? 'No connected requirement records match the current search and filters. Nothing is hidden or simulated.'
              : 'Requirement records, evidence summaries, source references, assignments, and review statuses will appear here when the Requirements API is connected.'}
          >
            {visibleRequirements.length ? visibleRequirements.map((record) => (
              <tr key={record.requirementId}>
                <td><strong>{record.requirementId}</strong><span className="table-cell-secondary">{record.description}</span></td>
                <td>{record.requirementType === 'mandatory' ? 'Mandatory' : 'Optional'}</td>
                <td><StatusPill tone={complianceTone(record.complianceStatus)}>{complianceLabel(record.complianceStatus)}</StatusPill></td>
                <td><span>{record.sourceReference || 'Not referenced'}</span><span className="table-cell-secondary">{record.evidenceSummary || 'No evidence note'}</span></td>
                <td>{record.assignee || 'Unassigned'}<span className="table-cell-secondary">{record.reviewer || 'No reviewer'}</span></td>
                <td><StatusPill tone="neutral">{record.reviewStatus}</StatusPill></td>
                <td><Button type="button" variant="ghost" onClick={() => loadRequirementForReview(record)}>Review</Button></td>
              </tr>
            )) : undefined}
          </DataTable>

          <div className="panel-body" style={{ paddingTop: 12 }}>
            <div className="dashboard-disclaimer">
              <ClipboardCheck size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Review and edit affordances are ready.</strong> Enter a connected requirement below to prepare a review draft. Saving, source viewing, and CSV export remain unavailable until the API is connected.</p>
            </div>
          </div>
        </Panel>

        <div className="split-grid">
          <Panel
            eyebrow="Review / edit"
            title="Prepare a requirement review"
            description="These fields remain local to this screen until a connected service can save them."
          >
            <form className="panel-body" onSubmit={handleSubmit}>
              <div className="form-grid">
                <Field label="Requirement ID" htmlFor="requirement-review-form" hint="Use the identifier from the source record.">
                  <TextInput
                    id="requirement-review-form"
                    value={draft.requirementId}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('requirementId', event.target.value)}
                    placeholder="e.g. from connected record"
                  />
                </Field>
                <Field label="Requirement type" htmlFor="requirement-type">
                  <SelectInput
                    id="requirement-type"
                    value={draft.requirementType}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('requirementType', event.target.value as ReviewDraft['requirementType'])}
                  >
                    <option value="mandatory">Mandatory</option>
                    <option value="optional">Optional</option>
                  </SelectInput>
                </Field>
                <Field className="field-full" label="Requirement description" htmlFor="requirement-description" hint="Describe the requirement exactly as supported by the source record.">
                  <TextArea
                    id="requirement-description"
                    value={draft.description}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('description', event.target.value)}
                    placeholder="Enter a requirement description"
                  />
                </Field>
                <Field label="Compliance status" htmlFor="requirement-compliance-status" hint="Keep Unknown separate from Not met when evidence is incomplete.">
                  <SelectInput
                    id="requirement-compliance-status"
                    value={draft.complianceStatus}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('complianceStatus', event.target.value as ComplianceStatus)}
                  >
                    {complianceOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </SelectInput>
                </Field>
                <Field label="Review status" htmlFor="requirement-review-status">
                  <SelectInput
                    id="requirement-review-status"
                    value={draft.reviewStatus}
                    onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('reviewStatus', event.target.value as ReviewDraft['reviewStatus'])}
                  >
                    <option value="unreviewed">Unreviewed</option>
                    <option value="in-review">In review</option>
                    <option value="reviewed">Reviewed</option>
                  </SelectInput>
                </Field>
                <Field className="field-full" label="Evidence summary" htmlFor="requirement-evidence" hint="Record what the evidence says; do not treat an empty field as proof of non-compliance.">
                  <TextArea
                    id="requirement-evidence"
                    value={draft.evidenceSummary}
                    onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('evidenceSummary', event.target.value)}
                    placeholder="Enter evidence notes or leave blank when evidence is not available"
                  />
                </Field>
                <Field label="Source / page reference" htmlFor="requirement-source" hint="A source reference is user-entered until document data is connected.">
                  <TextInput
                    id="requirement-source"
                    value={draft.sourceReference}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('sourceReference', event.target.value)}
                    placeholder="Document name, page, or section"
                  />
                </Field>
                <Field label="Assignee" htmlFor="requirement-assignee">
                  <TextInput
                    id="requirement-assignee"
                    value={draft.assignee}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('assignee', event.target.value)}
                    placeholder="Person responsible for follow-up"
                  />
                </Field>
                <Field label="Reviewer" htmlFor="requirement-reviewer">
                  <TextInput
                    id="requirement-reviewer"
                    value={draft.reviewer}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('reviewer', event.target.value)}
                    placeholder="Person responsible for review"
                  />
                </Field>
              </div>
              <div className="form-actions form-actions-left">
                <Button type="submit" variant="primary" icon={ShieldCheck}>Save review</Button>
                <Button type="button" variant="ghost" onClick={() => { setDraft(initialDraft); clearMessage(); }}>Clear draft</Button>
              </div>
              {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
            </form>
          </Panel>

          <Panel
            eyebrow="Source / evidence"
            title="Evidence context"
            description="Sources and evidence should remain inspectable and attributable when connected records are available."
          >
            <div className="panel-body">
              <div className="key-value-list">
                <div className="key-value-row"><span>Source reference</span><strong>{draft.sourceReference.trim() || 'Not entered'}</strong></div>
                <div className="key-value-row"><span>Evidence summary</span><strong>{draft.evidenceSummary.trim() ? 'Draft entered' : 'Not entered'}</strong></div>
                <div className="key-value-row"><span>Assignee</span><strong>{draft.assignee.trim() || 'Not assigned'}</strong></div>
                <div className="key-value-row"><span>Reviewer</span><strong>{draft.reviewer.trim() || 'Not assigned'}</strong></div>
                <div className="key-value-row"><span>Current draft status</span><strong>{complianceLabel(draft.complianceStatus)}</strong></div>
              </div>
              <div className="form-actions form-actions-left">
                <Button type="button" variant="secondary" icon={ExternalLink} disabled={!draft.sourceReference.trim()} onClick={handleSourceAction}>View source</Button>
              </div>
              {!draft.sourceReference.trim() ? (
                <EmptyState
                  icon={FileSearch}
                  title="No source selected"
                  description="Enter a document, page, or section reference in the review draft. Opening it will remain unavailable until the source service is connected."
                />
              ) : (
                <InlineNotice variant="info">
                  <strong>{draft.sourceReference}</strong><br />This source reference is a local draft only; no document was opened or sent.
                </InlineNotice>
              )}
              <div className="dashboard-disclaimer">
                <UserRound size={16} strokeWidth={1.8} aria-hidden="true" />
                <p><strong>Accountability stays explicit.</strong> Assignee and reviewer values are shown as entered and are not saved or notified from this screen.</p>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
