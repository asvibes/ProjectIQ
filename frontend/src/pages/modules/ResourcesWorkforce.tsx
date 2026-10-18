import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  CalendarDays,
  ClipboardList,
  FileSearch,
  HardHat,
  Link2,
  Plus,
  RefreshCw,
  Save,
  UsersRound,
  Wrench,
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
  Tabs,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type ActiveTab = 'workforce' | 'resources';
type WorkforceAvailability = 'unknown' | 'recorded' | 'requires-review';
type ResourceOption = 'existing' | 'repair-upgrade' | 'purchase' | 'rental' | 'leasing' | 'outsourcing';

type PlanningDraft = {
  periodStart: string;
  periodEnd: string;
  planningNote: string;
};

type WorkforceDraft = {
  role: string;
  skills: string;
  requiredHeadcount: string;
  requiredCapacity: string;
  availableHeadcount: string;
  availableCapacity: string;
  knownCommitments: string;
  availability: WorkforceAvailability;
  reviewNote: string;
};

type ResourceDraft = {
  resourceName: string;
  equipmentLink: string;
  option: ResourceOption;
  capacity: string;
  availability: string;
  costOrAssumption: string;
  reviewNote: string;
};

const initialPlanningDraft: PlanningDraft = {
  periodStart: '',
  periodEnd: '',
  planningNote: '',
};

const initialWorkforceDraft: WorkforceDraft = {
  role: '',
  skills: '',
  requiredHeadcount: '',
  requiredCapacity: '',
  availableHeadcount: '',
  availableCapacity: '',
  knownCommitments: '',
  availability: 'unknown',
  reviewNote: '',
};

const initialResourceDraft: ResourceDraft = {
  resourceName: '',
  equipmentLink: '',
  option: 'existing',
  capacity: '',
  availability: '',
  costOrAssumption: '',
  reviewNote: '',
};

const resourceOptionLabels: Record<ResourceOption, string> = {
  existing: 'Existing equipment',
  'repair-upgrade': 'Repair or upgrade',
  purchase: 'Purchase',
  rental: 'Rental',
  leasing: 'Leasing',
  outsourcing: 'Outsourcing',
};

const workforceAvailabilityLabels: Record<WorkforceAvailability, string> = {
  unknown: 'Unknown',
  recorded: 'Recorded availability',
  'requires-review': 'Requires review',
};

export default function ResourcesWorkforce() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('workforce');
  const [planning, setPlanning] = useState<PlanningDraft>(initialPlanningDraft);
  const [workforce, setWorkforce] = useState<WorkforceDraft>(initialWorkforceDraft);
  const [resource, setResource] = useState<ResourceDraft>(initialResourceDraft);
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const updatePlanning = <K extends keyof PlanningDraft>(key: K, value: PlanningDraft[K]) => {
    setPlanning((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const updateWorkforce = <K extends keyof WorkforceDraft>(key: K, value: WorkforceDraft[K]) => {
    setWorkforce((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const updateResource = <K extends keyof ResourceDraft>(key: K, value: ResourceDraft[K]) => {
    setResource((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const handleBackendAction = (action: string) => {
    reportUnavailable(action);
  };

  const handlePlanningSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this planning period');
  };

  const handleWorkforceSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this workforce role');
  };

  const handleResourceSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this resource option');
  };

  const focusForm = (id: string) => {
    clearNotice();
    document.getElementById(id)?.focus();
  };

  const handleTabChange = (value: string) => {
    setActiveTab(value as ActiveTab);
    clearNotice();
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Delivery & capacity"
        title="Resource & Workforce Planning"
        description="Prepare workforce and equipment inputs for a connected planning review. Headcount, capacity, availability, and gaps stay separate until supported by project data."
        actions={(
          <>
            <Button
              type="button"
              variant="secondary"
              icon={RefreshCw}
              onClick={() => handleBackendAction('recalculating resource and workforce capacity')}
            >
              Recalculate
            </Button>
            <Button
              type="button"
              variant="primary"
              icon={Plus}
              onClick={() => focusForm(activeTab === 'workforce' ? 'workforce-role' : 'resource-name')}
            >
              {activeTab === 'workforce' ? 'Add role' : 'Add resource option'}
            </Button>
          </>
        )}
      />

      <ApiNotice />
      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

      <Panel
        eyebrow="Planning context"
        title="Set the period before reviewing capacity"
        description="These values are held only in this screen. No project dates, commitments, equipment records, or availability are loaded without an API connection."
      >
        <form className="panel-body" onSubmit={handlePlanningSubmit}>
          <div className="form-grid">
            <Field
              label="Period start"
              htmlFor="resources-period-start"
              hint="Use the start of the planning window you want to review."
            >
              <TextInput
                id="resources-period-start"
                type="date"
                value={planning.periodStart}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updatePlanning('periodStart', event.target.value)}
              />
            </Field>
            <Field
              label="Period end"
              htmlFor="resources-period-end"
              hint="A connected service can validate the period against project dates later."
            >
              <TextInput
                id="resources-period-end"
                type="date"
                value={planning.periodEnd}
                onChange={(event: ChangeEvent<HTMLInputElement>) => updatePlanning('periodEnd', event.target.value)}
              />
            </Field>
            <Field
              className="field-full"
              label="Planning note"
              htmlFor="resources-planning-note"
              hint="Record a scope or timing assumption without turning it into a calculated result."
            >
              <TextArea
                id="resources-planning-note"
                value={planning.planningNote}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updatePlanning('planningNote', event.target.value)}
                placeholder="Optional note about this planning period"
              />
            </Field>
          </div>
          <FormActions className="form-actions-left">
            <Button type="submit" variant="secondary" icon={Save}>Save planning context</Button>
          </FormActions>
        </form>
      </Panel>

      <div className="content-section stack">
        <Panel
          eyebrow="Capacity workspace"
          title="Workforce and resources"
          description="Switch between role capacity records and equipment options. Unknown values remain visible rather than being treated as unavailable."
          action={(
            <Tabs
              label="Resource planning view"
              value={activeTab}
              onChange={handleTabChange}
              items={[
                { id: 'workforce', label: 'Workforce' },
                { id: 'resources', label: 'Resources' },
              ]}
            />
          )}
        >
          {activeTab === 'workforce' ? (
            <WorkforceView
              draft={workforce}
              onUpdate={updateWorkforce}
              onSubmit={handleWorkforceSubmit}
              onAction={handleBackendAction}
            />
          ) : (
            <ResourcesView
              draft={resource}
              onUpdate={updateResource}
              onSubmit={handleResourceSubmit}
              onAction={handleBackendAction}
            />
          )}
        </Panel>
      </div>
    </>
  );
}

type WorkforceViewProps = {
  draft: WorkforceDraft;
  onUpdate: <K extends keyof WorkforceDraft>(key: K, value: WorkforceDraft[K]) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onAction: (action: string) => void;
};

function WorkforceView({ draft, onUpdate, onSubmit, onAction }: WorkforceViewProps) {
  return (
    <div className="stack">
      <div className="panel-body">
        <div className="dashboard-disclaimer">
          <UsersRound size={16} strokeWidth={1.8} aria-hidden="true" />
          <p>
            <strong>Headcount is not available capacity.</strong> Record both separately, along with known commitments and the basis for availability. No gap or staffing recommendation is calculated in this frontend-only view.
          </p>
        </div>
      </div>

      <div className="panel-body">
        <div className="three-column-grid">
          <div className="status-prompt">
            <StatusPill tone="neutral">Unknown</StatusPill>
            <p>No connected workforce records are available for this planning period.</p>
          </div>
          <div className="status-prompt">
            <StatusPill tone="blue">Capacity separate</StatusPill>
            <p>Required and available capacity need their own evidence or user-entered basis.</p>
          </div>
          <div className="status-prompt">
            <StatusPill tone="neutral">Not calculated</StatusPill>
            <p>A capacity gap will not be inferred from missing values or headcount.</p>
          </div>
        </div>
      </div>

      <div className="panel-body">
        <div className="section-heading">
          <div>
            <h2>Workforce comparison</h2>
            <p>Connected rows will compare role, skills, required inputs, availability evidence, and known commitments.</p>
          </div>
          <StatusPill tone="neutral">No live records</StatusPill>
        </div>
        <DataTable
          label="Workforce comparison"
          headers={[
            'Role / skills',
            'Required headcount',
            'Required capacity',
            'Available headcount',
            'Available capacity',
            'Known commitments',
            'Gap / status',
          ]}
        >
          <tr>
            <td colSpan={7}>
              <EmptyState
                className="table-empty-state"
                icon={FileSearch}
                title="No workforce records loaded"
                description="Role, skills, headcount, capacity, availability evidence, commitments, and gap status will appear here when connected records are available. Missing values remain unknown, not not-met."
              />
            </td>
          </tr>
        </DataTable>
      </div>

      <div className="split-grid">
        <Panel
          eyebrow="Role and capacity inputs"
          title="Prepare a workforce role"
          description="Draft entries remain on screen while the backend is unavailable. Saving does not send or persist them."
        >
          <form className="panel-body" onSubmit={onSubmit}>
            <div className="form-grid">
              <Field label="Role" htmlFor="workforce-role" hint="Enter the role to review for this planning period.">
                <TextInput
                  id="workforce-role"
                  value={draft.role}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('role', event.target.value)}
                  placeholder="e.g. Site supervisor"
                />
              </Field>
              <Field label="Skills / discipline" htmlFor="workforce-skills" hint="List the skills that should be supported by evidence.">
                <TextInput
                  id="workforce-skills"
                  value={draft.skills}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('skills', event.target.value)}
                  placeholder="e.g. Site coordination, safety"
                />
              </Field>
              <Field label="Required headcount" htmlFor="workforce-required-headcount" hint="A count of people needed; it is not a capacity value.">
                <TextInput
                  id="workforce-required-headcount"
                  type="number"
                  min="0"
                  inputMode="numeric"
                  value={draft.requiredHeadcount}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('requiredHeadcount', event.target.value)}
                  placeholder="Unknown"
                />
              </Field>
              <Field label="Required capacity" htmlFor="workforce-required-capacity" hint="Enter the unit and basis in the review note.">
                <TextInput
                  id="workforce-required-capacity"
                  value={draft.requiredCapacity}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('requiredCapacity', event.target.value)}
                  placeholder="e.g. 120 hours / period"
                />
              </Field>
              <Field label="Available headcount" htmlFor="workforce-available-headcount" hint="Do not assume employed headcount is available for this work.">
                <TextInput
                  id="workforce-available-headcount"
                  type="number"
                  min="0"
                  inputMode="numeric"
                  value={draft.availableHeadcount}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('availableHeadcount', event.target.value)}
                  placeholder="Unknown"
                />
              </Field>
              <Field label="Available capacity" htmlFor="workforce-available-capacity" hint="Record the capacity basis separately from headcount.">
                <TextInput
                  id="workforce-available-capacity"
                  value={draft.availableCapacity}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('availableCapacity', event.target.value)}
                  placeholder="e.g. 80 hours / period"
                />
              </Field>
              <Field label="Known commitments" htmlFor="workforce-known-commitments" hint="Record confirmed commitments; do not infer them from headcount.">
                <TextInput
                  id="workforce-known-commitments"
                  value={draft.knownCommitments}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('knownCommitments', event.target.value)}
                  placeholder="Unknown or enter a recorded commitment"
                />
              </Field>
              <Field label="Availability evidence" htmlFor="workforce-availability" hint="The state describes the record, not a staffing conclusion.">
                <SelectInput
                  id="workforce-availability"
                  value={draft.availability}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => onUpdate('availability', event.target.value as WorkforceAvailability)}
                >
                  {Object.entries(workforceAvailabilityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </SelectInput>
              </Field>
              <Field className="field-full" label="Review note / capacity basis" htmlFor="workforce-review-note" hint="Explain the source, unit, or assumption without implying that it has been verified.">
                <TextArea
                  id="workforce-review-note"
                  value={draft.reviewNote}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onUpdate('reviewNote', event.target.value)}
                  placeholder="Enter a source reference, availability basis, or follow-up question"
                />
              </Field>
            </div>
            <FormActions>
              <Button type="button" variant="secondary" icon={ClipboardList} onClick={() => onAction('editing workforce availability')}>Edit availability</Button>
              <Button type="button" variant="ghost" onClick={() => onAction('comparing workforce capacity')}>Compare capacity</Button>
              <Button type="submit" variant="primary" icon={Save}>Save role draft</Button>
            </FormActions>
          </form>
        </Panel>

        <Panel
          eyebrow="Review boundary"
          title="Unknown is a valid state"
          description="Use the fields to record what is known and what still needs a connected source."
        >
          <div className="panel-body stack">
            <div className="connection-card">
              <div className="connection-card-icon"><CalendarDays size={16} aria-hidden="true" /></div>
              <div><strong>Planning period</strong><small>Dates are entered above; no project schedule is connected to validate them.</small></div>
            </div>
            <div className="connection-card">
              <div className="connection-card-icon"><UsersRound size={16} aria-hidden="true" /></div>
              <div><strong>Availability basis</strong><small>Availability needs a recorded source or user-entered note. It is not derived from headcount.</small></div>
            </div>
            <div className="connection-card">
              <div className="connection-card-icon"><ClipboardList size={16} aria-hidden="true" /></div>
              <div><strong>Gap status</strong><small>Gap, hiring, training, and contractor needs stay uncalculated until a connected comparison is available.</small></div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

type ResourcesViewProps = {
  draft: ResourceDraft;
  onUpdate: <K extends keyof ResourceDraft>(key: K, value: ResourceDraft[K]) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onAction: (action: string) => void;
};

function ResourcesView({ draft, onUpdate, onSubmit, onAction }: ResourcesViewProps) {
  return (
    <div className="stack">
      <div className="panel-body">
        <div className="dashboard-disclaimer">
          <Wrench size={16} strokeWidth={1.8} aria-hidden="true" />
          <p>
            <strong>Equipment options need a source and an assumption.</strong> This view records possible options and capacity inputs without claiming that equipment is available, affordable, or suitable.
          </p>
        </div>
      </div>

      <div className="panel-body">
        <div className="three-column-grid">
          <div className="status-prompt">
            <StatusPill tone="neutral">Unknown</StatusPill>
            <p>No connected equipment records or project requirements are available.</p>
          </div>
          <div className="status-prompt">
            <StatusPill tone="blue">Options separate</StatusPill>
            <p>Existing, repair, purchase, rental, leasing, and outsourcing remain distinct options.</p>
          </div>
          <div className="status-prompt">
            <StatusPill tone="neutral">Not calculated</StatusPill>
            <p>Capacity, cost, and suitability are not compared in the browser.</p>
          </div>
        </div>
      </div>

      <div className="panel-body">
        <div className="section-heading">
          <div>
            <h2>Equipment comparison</h2>
            <p>Connected rows will compare linked equipment, option type, capacity, availability, and assumptions.</p>
          </div>
          <StatusPill tone="neutral">No live records</StatusPill>
        </div>
        <DataTable
          label="Equipment comparison"
          headers={['Resource / equipment link', 'Option', 'Capacity', 'Availability', 'Cost / assumptions', 'Status']}
        >
          <tr>
            <td colSpan={6}>
              <EmptyState
                className="table-empty-state"
                icon={FileSearch}
                title="No equipment options loaded"
                description="Equipment links, option types, capacity, availability, costs, and assumptions will appear here when connected records are available. No purchase, rental, or outsourcing recommendation is inferred."
              />
            </td>
          </tr>
        </DataTable>
      </div>

      <div className="split-grid">
        <Panel
          eyebrow="Equipment option inputs"
          title="Prepare an equipment option"
          description="Use this draft to record an option for later comparison. Saving remains unavailable until the backend is connected."
        >
          <form className="panel-body" onSubmit={onSubmit}>
            <div className="form-grid">
              <Field className="field-full" label="Resource or equipment name" htmlFor="resource-name" hint="Use a connected equipment record name when one is available.">
                <TextInput
                  id="resource-name"
                  value={draft.resourceName}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('resourceName', event.target.value)}
                  placeholder="e.g. Mobile crane"
                />
              </Field>
              <Field className="field-full" label="Equipment link / reference" htmlFor="resource-equipment-link" hint="Link or reference a requirement, asset, quote, or source without implying that it has been checked.">
                <TextInput
                  id="resource-equipment-link"
                  value={draft.equipmentLink}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('equipmentLink', event.target.value)}
                  placeholder="No connected equipment record"
                />
              </Field>
              <Field label="Option" htmlFor="resource-option" hint="Record the route being considered; no option is selected as best.">
                <SelectInput
                  id="resource-option"
                  value={draft.option}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => onUpdate('option', event.target.value as ResourceOption)}
                >
                  {Object.entries(resourceOptionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </SelectInput>
              </Field>
              <Field label="Capacity" htmlFor="resource-capacity" hint="Include the unit and basis in the review note.">
                <TextInput
                  id="resource-capacity"
                  value={draft.capacity}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('capacity', event.target.value)}
                  placeholder="Unknown"
                />
              </Field>
              <Field label="Availability" htmlFor="resource-availability" hint="Record a date, window, or unknown state; do not infer availability.">
                <TextInput
                  id="resource-availability"
                  value={draft.availability}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('availability', event.target.value)}
                  placeholder="Unknown"
                />
              </Field>
              <Field label="Cost / assumption" htmlFor="resource-cost-assumption" hint="Keep quotes, estimates, and assumptions clearly distinguishable.">
                <TextInput
                  id="resource-cost-assumption"
                  value={draft.costOrAssumption}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onUpdate('costOrAssumption', event.target.value)}
                  placeholder="Unknown or enter a recorded assumption"
                />
              </Field>
              <Field className="field-full" label="Review note" htmlFor="resource-review-note" hint="Record source, condition, lead time, or follow-up questions.">
                <TextArea
                  id="resource-review-note"
                  value={draft.reviewNote}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onUpdate('reviewNote', event.target.value)}
                  placeholder="Enter a source reference, equipment condition, or review note"
                />
              </Field>
            </div>
            <FormActions>
              <Button type="button" variant="secondary" icon={Link2} onClick={() => onAction('opening the equipment link')}>Open equipment link</Button>
              <Button type="button" variant="ghost" onClick={() => onAction('comparing equipment options')}>Compare options</Button>
              <Button type="submit" variant="primary" icon={Save}>Save option draft</Button>
            </FormActions>
          </form>
        </Panel>

        <Panel
          eyebrow="Option review boundary"
          title="No invented equipment fit"
          description="A missing equipment record is not proof that an option is unavailable or unsuitable."
        >
          <div className="panel-body stack">
            <div className="connection-card">
              <div className="connection-card-icon"><Link2 size={16} aria-hidden="true" /></div>
              <div><strong>Equipment link</strong><small>Links stay as references until a connected equipment or requirement record can be opened.</small></div>
            </div>
            <div className="connection-card">
              <div className="connection-card-icon"><HardHat size={16} aria-hidden="true" /></div>
              <div><strong>Capacity and availability</strong><small>Both are recorded as separate inputs. Neither is filled from a default or inferred from the option type.</small></div>
            </div>
            <div className="connection-card">
              <div className="connection-card-icon"><Wrench size={16} aria-hidden="true" /></div>
              <div><strong>Cost and suitability</strong><small>Quotes, estimates, condition, and suitability remain unknown until supported by connected evidence.</small></div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
