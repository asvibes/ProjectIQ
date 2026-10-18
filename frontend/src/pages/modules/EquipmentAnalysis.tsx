import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  ArrowRightLeft,
  ClipboardCheck,
  Filter,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import {
  ApiNotice,
  Button,
  DataTable,
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

type EquipmentOptionType =
  | 'existing'
  | 'repair-upgrade'
  | 'purchase'
  | 'rental'
  | 'leasing'
  | 'outsourcing';

type EquipmentOptionDraft = {
  requirement: string;
  equipment: string;
  category: string;
  optionType: EquipmentOptionType;
  capacity: string;
  cost: string;
  availability: string;
  source: string;
  notes: string;
};

const emptyOption: EquipmentOptionDraft = {
  requirement: '',
  equipment: '',
  category: '',
  optionType: 'existing',
  capacity: '',
  cost: '',
  availability: '',
  source: '',
  notes: '',
};

const optionTypeLabels: Record<EquipmentOptionType, string> = {
  existing: 'Existing equipment',
  'repair-upgrade': 'Repair or upgrade',
  purchase: 'Purchase',
  rental: 'Rental',
  leasing: 'Leasing',
  outsourcing: 'Outsourcing',
};

const optionTypeValues = Object.entries(optionTypeLabels) as Array<[
  EquipmentOptionType,
  string,
]>;

export default function EquipmentAnalysis() {
  const [draft, setDraft] = useState<EquipmentOptionDraft>(emptyOption);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [optionTypeFilter, setOptionTypeFilter] = useState<'all' | EquipmentOptionType>('all');
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const updateDraft = <K extends keyof EquipmentOptionDraft>(
    key: K,
    value: EquipmentOptionDraft[K],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this equipment option');
  };

  const handleControlChange = (setter: (value: string) => void, value: string) => {
    setter(value);
    clearNotice();
  };

  const focusOptionForm = () => {
    clearNotice();
    document.getElementById('equipment-option-requirement')?.focus();
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Delivery & capacity"
        title="Equipment Analysis"
        description="Map project requirements to equipment options without assuming fleet ownership, availability, pricing, or capacity until evidence is connected."
        actions={(
          <>
            <Button
              type="button"
              variant="secondary"
              icon={ArrowRightLeft}
              onClick={() => reportUnavailable('comparing equipment options')}
            >
              Compare options
            </Button>
            <Button type="button" variant="primary" icon={Plus} onClick={focusOptionForm}>
              Add option
            </Button>
          </>
        )}
      />

      <ApiNotice />
      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

      <div className="content-section stack">
        <Panel
          eyebrow="Equipment requirements"
          title="Requirements and options"
          description="Search and filter the connected equipment register when available. This table intentionally starts without seeded rows or comparison results."
          action={<StatusPill tone="neutral">No live records</StatusPill>}
        >
          <div className="panel-body stack">
            <div className="dashboard-disclaimer">
              <ClipboardCheck size={16} strokeWidth={1.8} aria-hidden="true" />
              <p>
                <strong>Evidence stays separate from decisions.</strong> Requirement values, capacity, cost, availability, and source references are shown only when provided by a connected service or entered by you. Empty values are not interpreted as unavailable or unaffordable.
              </p>
            </div>

            <div className="filter-bar" aria-label="Equipment table filters">
              <div className="filter-search">
                <Search size={16} aria-hidden="true" />
                <label className="sr-only" htmlFor="equipment-search">Search equipment requirements</label>
                <TextInput
                  id="equipment-search"
                  type="search"
                  value={searchTerm}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => handleControlChange(setSearchTerm, event.target.value)}
                  placeholder="Search requirement or equipment"
                />
              </div>
              <div className="filter-control">
                <Filter size={15} aria-hidden="true" />
                <label className="sr-only" htmlFor="equipment-category-filter">Filter by category</label>
                <SelectInput
                  id="equipment-category-filter"
                  value={categoryFilter}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => handleControlChange(setCategoryFilter, event.target.value)}
                >
                  <option value="all">All categories</option>
                  <option value="lifting">Lifting</option>
                  <option value="earthworks">Earthworks</option>
                  <option value="transport">Transport</option>
                  <option value="specialist">Specialist</option>
                </SelectInput>
              </div>
              <div className="filter-control">
                <SlidersHorizontal size={15} aria-hidden="true" />
                <label className="sr-only" htmlFor="equipment-option-filter">Filter by option type</label>
                <SelectInput
                  id="equipment-option-filter"
                  value={optionTypeFilter}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                    setOptionTypeFilter(event.target.value as 'all' | EquipmentOptionType);
                    clearNotice();
                  }}
                >
                  <option value="all">All option types</option>
                  {optionTypeValues.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </SelectInput>
              </div>
              <span className="filter-note">{searchTerm || categoryFilter !== 'all' || optionTypeFilter !== 'all' ? 'Filters ready for connected records' : 'No filters applied'}</span>
            </div>

            <DataTable
              label="Equipment requirements and options"
              headers={[
                'Requirement',
                'Equipment',
                'Category',
                'Option',
                'Capacity',
                'Cost / assumption',
                'Availability',
                'Source',
                'Actions',
              ]}
              emptyTitle="No equipment records to review"
              emptyDescription="Connect the project data source or add an option below. No fleet, availability, prices, capacity, or comparison outcomes have been assumed."
            >
              {undefined}
            </DataTable>
          </div>
        </Panel>

        <Panel
          eyebrow="Option workspace"
          title="Add or edit an equipment option"
          description="Keep the user's draft visible while a connected service is unavailable. Source and assumption notes make the basis for each value explicit."
          action={<StatusPill tone="blue">Draft only</StatusPill>}
        >
          <form className="panel-body" onSubmit={handleSubmit}>
            <div className="form-grid">
              <Field
                label="Requirement"
                htmlFor="equipment-option-requirement"
                required
                hint="Use the requirement wording or a concise reference from the project documents."
              >
                <TextInput
                  id="equipment-option-requirement"
                  value={draft.requirement}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('requirement', event.target.value)}
                  placeholder="e.g. Lift materials to specified height"
                  required
                />
              </Field>
              <Field
                label="Equipment"
                htmlFor="equipment-option-equipment"
                required
                hint="Name the machine, asset, provider, or outsourced service."
              >
                <TextInput
                  id="equipment-option-equipment"
                  value={draft.equipment}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('equipment', event.target.value)}
                  placeholder="Equipment or service name"
                  required
                />
              </Field>
              <Field label="Category" htmlFor="equipment-option-category" required>
                <TextInput
                  id="equipment-option-category"
                  value={draft.category}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('category', event.target.value)}
                  placeholder="e.g. Lifting"
                  required
                />
              </Field>
              <Field
                label="Option type"
                htmlFor="equipment-option-type"
                hint="Record the route being considered; do not treat it as a recommendation."
              >
                <SelectInput
                  id="equipment-option-type"
                  value={draft.optionType}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('optionType', event.target.value as EquipmentOptionType)}
                >
                  {optionTypeValues.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </SelectInput>
              </Field>
              <Field
                label="Capacity"
                htmlFor="equipment-option-capacity"
                hint="Include the unit and basis if known; leave blank when not evidenced."
              >
                <TextInput
                  id="equipment-option-capacity"
                  value={draft.capacity}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('capacity', event.target.value)}
                  placeholder="e.g. 10 t / 20 m"
                />
              </Field>
              <Field
                label="Cost / assumption"
                htmlFor="equipment-option-cost"
                hint="Enter a source-backed amount or label the value as an assumption. No total is calculated here."
              >
                <TextInput
                  id="equipment-option-cost"
                  value={draft.cost}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('cost', event.target.value)}
                  placeholder="Amount, rate, or assumption"
                />
              </Field>
              <Field
                label="Availability"
                htmlFor="equipment-option-availability"
                hint="Describe the known window or state; blank does not mean unavailable."
              >
                <TextInput
                  id="equipment-option-availability"
                  value={draft.availability}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('availability', event.target.value)}
                  placeholder="Window, status, or unknown"
                />
              </Field>
              <Field
                label="Source"
                htmlFor="equipment-option-source"
                hint="Reference the document, record, quotation, or person that supports these values."
              >
                <TextInput
                  id="equipment-option-source"
                  value={draft.source}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('source', event.target.value)}
                  placeholder="Document or evidence reference"
                />
              </Field>
              <Field
                className="field-full"
                label="Notes and assumptions"
                htmlFor="equipment-option-notes"
                hint="Capture constraints, lead time, inspection needs, or what still needs review."
              >
                <TextArea
                  id="equipment-option-notes"
                  value={draft.notes}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) => updateDraft('notes', event.target.value)}
                  placeholder="Optional context for this option"
                  rows={4}
                />
              </Field>
            </div>
            <FormActions className="form-actions-left">
              <Button type="submit" variant="primary" icon={Pencil}>Save option</Button>
              <Button
                type="button"
                variant="secondary"
                icon={ArrowRightLeft}
                onClick={() => reportUnavailable('comparing this equipment option')}
              >
                Compare this option
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setDraft(emptyOption);
                  clearNotice();
                }}
              >
                Clear draft
              </Button>
            </FormActions>
          </form>
        </Panel>

        <Panel
          eyebrow="Review guidance"
          title="What is still unknown"
          description="Use the connected data source to replace these neutral placeholders with evidence, not assumptions."
        >
          <div className="panel-body">
            <div className="three-column-grid">
              <div className="status-prompt">
                <StatusPill tone="neutral">Capacity unknown</StatusPill>
                <p>No capacity is inferred from equipment names or categories.</p>
              </div>
              <div className="status-prompt">
                <StatusPill tone="neutral">Availability unknown</StatusPill>
                <p>Ownership or employment does not establish availability for this project.</p>
              </div>
              <div className="status-prompt">
                <StatusPill tone="neutral">Cost not calculated</StatusPill>
                <p>No prices, totals, rankings, or best-option comparison are produced in this screen.</p>
              </div>
            </div>
            <div className="dashboard-disclaimer" style={{ marginTop: '16px' }}>
              <Sparkles size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Connect evidence before deciding.</strong> The frontend preserves structured inputs for a future service; it does not claim that an equipment choice is feasible or preferred.</p>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
