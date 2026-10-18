import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  ArrowRightLeft,
  ChartNoAxesCombined,
  Check,
  Download,
  GitCompareArrows,
  LockKeyhole,
  Save,
  ShieldCheck,
  TriangleAlert,
  X,
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

type ScenarioDraft = {
  name: string;
  description: string;
  currency: string;
  revenueBasis: string;
  labourBasis: string;
  materialsBasis: string;
  equipmentBasis: string;
  contingencyBasis: string;
  scheduleBasis: string;
  dependencies: string;
  reviewNotes: string;
};

type AssumptionDefinition = {
  key: keyof ScenarioDraft;
  label: string;
  hint: string;
};

const initialScenario: ScenarioDraft = {
  name: '',
  description: '',
  currency: '',
  revenueBasis: '',
  labourBasis: '',
  materialsBasis: '',
  equipmentBasis: '',
  contingencyBasis: '',
  scheduleBasis: '',
  dependencies: '',
  reviewNotes: '',
};

const assumptionDefinitions: AssumptionDefinition[] = [
  { key: 'revenueBasis', label: 'Revenue / pricing basis', hint: 'Contract value, pricing basis, or source to review later.' },
  { key: 'labourBasis', label: 'Labour cost basis', hint: 'Crew, hours, rates, or workforce availability assumption.' },
  { key: 'materialsBasis', label: 'Materials cost basis', hint: 'Quote, allowance, supplier basis, or procurement assumption.' },
  { key: 'equipmentBasis', label: 'Equipment cost basis', hint: 'Owned, hired, shared, or otherwise assumed equipment basis.' },
  { key: 'contingencyBasis', label: 'Contingency basis', hint: 'Risk allowance or contingency rationale; no percentage is calculated here.' },
  { key: 'scheduleBasis', label: 'Schedule / timing basis', hint: 'Working duration, milestone, or timing constraint to validate.' },
  { key: 'dependencies', label: 'Key dependencies', hint: 'Inputs, approvals, suppliers, or resources that could affect the scenario.' },
  { key: 'reviewNotes', label: 'Review notes', hint: 'Questions or evidence still needed before a connected comparison.' },
];

const currencyOptions = [
  { value: '', label: 'Select currency' },
  { value: 'AUD', label: 'AUD — Australian dollar' },
  { value: 'CAD', label: 'CAD — Canadian dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — Pound sterling' },
  { value: 'NZD', label: 'NZD — New Zealand dollar' },
  { value: 'USD', label: 'USD — US dollar' },
  { value: 'other', label: 'Other / specify in notes' },
];

function displayValue(value: string): string {
  return value.trim() || '—';
}

function ScenarioFields({
  prefix,
  draft,
  onChange,
}: {
  prefix: 'baseline' | 'alternative';
  draft: ScenarioDraft;
  onChange: <K extends keyof ScenarioDraft>(key: K, value: ScenarioDraft[K]) => void;
}) {
  const handleInputChange = (key: keyof ScenarioDraft) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    onChange(key, event.target.value);
  };

  return (
    <div className="form-grid">
      <Field label="Scenario name" htmlFor={`${prefix}-scenario-name`} required hint="Use a clear working name; it is not saved until an API is connected.">
        <TextInput
          id={`${prefix}-scenario-name`}
          value={draft.name}
          onChange={handleInputChange('name')}
          placeholder={prefix === 'baseline' ? 'Baseline working case' : 'Alternative working case'}
        />
      </Field>
      <Field label="Currency" htmlFor={`${prefix}-scenario-currency`} hint="Currency is an entry for later validation, not a conversion or calculation.">
        <SelectInput id={`${prefix}-scenario-currency`} value={draft.currency} onChange={handleInputChange('currency')}>
          {currencyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </SelectInput>
      </Field>
      <Field className="field-full" label="Scenario description" htmlFor={`${prefix}-scenario-description`} hint="Describe what is different or what this scenario is intended to test.">
        <TextArea
          id={`${prefix}-scenario-description`}
          value={draft.description}
          onChange={handleInputChange('description')}
          placeholder="Describe the scenario boundary and intended use"
          rows={3}
        />
      </Field>
      {assumptionDefinitions.map((definition) => (
        <Field
          key={definition.key}
          className={definition.key === 'dependencies' || definition.key === 'reviewNotes' ? 'field-full' : ''}
          label={definition.label}
          htmlFor={`${prefix}-scenario-${definition.key}`}
          hint={definition.hint}
        >
          {definition.key === 'dependencies' || definition.key === 'reviewNotes' ? (
            <TextArea
              id={`${prefix}-scenario-${definition.key}`}
              value={draft[definition.key]}
              onChange={handleInputChange(definition.key)}
              placeholder="Enter a draft note"
              rows={2}
            />
          ) : (
            <TextInput
              id={`${prefix}-scenario-${definition.key}`}
              value={draft[definition.key]}
              onChange={handleInputChange(definition.key)}
              placeholder="Enter an assumption or source basis"
            />
          )}
        </Field>
      ))}
    </div>
  );
}

export default function ScenarioPlanning() {
  const [baseline, setBaseline] = useState<ScenarioDraft>(initialScenario);
  const [alternative, setAlternative] = useState<ScenarioDraft>(initialScenario);
  const [showPromotionConfirmation, setShowPromotionConfirmation] = useState(false);
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const updateScenario = <K extends keyof ScenarioDraft>(
    scenario: 'baseline' | 'alternative',
    key: K,
    value: ScenarioDraft[K],
  ) => {
    if (scenario === 'baseline') {
      setBaseline((current) => ({ ...current, [key]: value }));
    } else {
      setAlternative((current) => ({ ...current, [key]: value }));
    }
    clearNotice();
  };

  const handleSave = (scenario: 'baseline' | 'alternative') => (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable(`saving the ${scenario} scenario`);
  };

  const changedAssumptions = assumptionDefinitions.filter(({ key }) => baseline[key].trim() !== alternative[key].trim());

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Commercial planning"
        title="Scenario Planning"
        description="Set up a baseline and an alternative using explicit, editable assumptions. Comparison and promotion stay unavailable until a connected backend can validate and persist the scenario set."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} onClick={() => reportUnavailable('exporting the scenario comparison')}>
              Export scenarios
            </Button>
            <Button type="button" variant="secondary" icon={GitCompareArrows} onClick={() => reportUnavailable('comparing these scenarios')}>
              Compare scenarios
            </Button>
            <Button type="button" variant="primary" icon={ArrowRightLeft} onClick={() => setShowPromotionConfirmation(true)}>
              Promote alternative
            </Button>
          </>
        )}
      />

      <ApiNotice />
      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

      <Panel
        eyebrow="Comparison guardrail"
        title="Draft assumptions only"
        description="This screen holds entries in local React state for review. It does not calculate financial impact, produce projections, send requests, or change a baseline."
      >
        <div className="panel-body">
          <div className="three-column-grid">
            <div className="status-prompt">
              <StatusPill tone="violet">Baseline</StatusPill>
              <p>The reference case you choose to keep visible for comparison. It is not persisted here.</p>
            </div>
            <div className="status-prompt">
              <StatusPill tone="blue">Alternative</StatusPill>
              <p>A separate draft for a different set of assumptions. It cannot replace the baseline in this workspace.</p>
            </div>
            <div className="status-prompt">
              <StatusPill tone="neutral">No projections</StatusPill>
              <p>Impact, margin, cash flow, and other calculated outputs remain empty until a connected service validates inputs.</p>
            </div>
          </div>
          <div className="dashboard-disclaimer">
            <LockKeyhole size={16} strokeWidth={1.8} aria-hidden="true" />
            <p><strong>Nothing is sent or saved.</strong> Form entries remain on screen when an unavailable action is attempted.</p>
          </div>
        </div>
      </Panel>

      <div className="content-section split-grid">
        <Panel
          eyebrow="Reference case"
          title="Baseline scenario"
          description="Capture the assumptions currently used as the reference. Keep values explicit and reviewable."
          action={<StatusPill tone="violet">Draft baseline</StatusPill>}
        >
          <form className="panel-body" onSubmit={handleSave('baseline')}>
            <ScenarioFields
              prefix="baseline"
              draft={baseline}
              onChange={(key, value) => updateScenario('baseline', key, value)}
            />
            <FormActions>
              <Button type="submit" variant="secondary" icon={Save}>Save baseline</Button>
            </FormActions>
          </form>
        </Panel>

        <Panel
          eyebrow="What-if case"
          title="Alternative scenario"
          description="Capture a distinct set of assumptions to review beside the baseline. Editing does not imply a projection."
          action={<StatusPill tone="blue">Draft alternative</StatusPill>}
        >
          <form className="panel-body" onSubmit={handleSave('alternative')}>
            <ScenarioFields
              prefix="alternative"
              draft={alternative}
              onChange={(key, value) => updateScenario('alternative', key, value)}
            />
            <FormActions>
              <Button type="submit" variant="secondary" icon={Save}>Save alternative</Button>
            </FormActions>
          </form>
        </Panel>
      </div>

      <Panel
        eyebrow="Scenario comparison"
        title="Compare entered assumptions"
        description="The table below is a side-by-side view of the values currently entered in this browser view. It contains no calculated variance or simulated projection."
        action={<StatusPill tone="neutral">No live comparison</StatusPill>}
      >
        <DataTable
          label="Baseline and alternative scenario assumptions"
          headers={['Assumption', 'Baseline entry', 'Alternative entry', 'Local draft state']}
        >
          {assumptionDefinitions.map(({ key, label }) => {
            const changed = baseline[key].trim() !== alternative[key].trim();
            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>{displayValue(baseline[key])}</td>
                <td>{displayValue(alternative[key])}</td>
                <td>
                  <StatusPill tone={changed ? 'amber' : 'neutral'}>
                    {changed ? 'Changed entry' : 'Same or blank'}
                  </StatusPill>
                </td>
              </tr>
            );
          })}
        </DataTable>
        <div className="panel-body">
          <div className="form-actions form-actions-left">
            <Button type="button" variant="primary" icon={GitCompareArrows} onClick={() => reportUnavailable('comparing these scenarios')}>
              Run connected comparison
            </Button>
            <Button type="button" variant="ghost" icon={ChartNoAxesCombined} onClick={() => reportUnavailable('loading scenario projections')}>
              Load projections
            </Button>
          </div>
        </div>
      </Panel>

      <div className="content-section split-grid">
        <Panel
          eyebrow="Review slot"
          title="Changed-assumption summary"
          description="This local summary only identifies different entered text. A connected comparison service is required to assess impact or materiality."
        >
          <div className="panel-body">
            {changedAssumptions.length === 0 ? (
              <EmptyState
                icon={GitCompareArrows}
                title="No changed assumptions yet"
                description="Enter a value in one scenario or use different values in both scenarios to populate this review slot."
              />
            ) : (
              <div className="key-value-list">
                {changedAssumptions.map(({ key, label }) => (
                  <div className="key-value-row" key={key}>
                    <span>{label}</span>
                    <strong>Baseline: {displayValue(baseline[key])} · Alternative: {displayValue(alternative[key])}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel
          eyebrow="Future output"
          title="Projection area"
          description="Reserved for deterministic results returned by a connected backend. Nothing is inferred from the draft entries in this screen."
        >
          <div className="panel-body">
            <EmptyState
              icon={ChartNoAxesCombined}
              title="No projections available"
              description="Revenue impact, cost movement, cash flow, margin, and schedule outcomes will remain empty until a connected service returns validated results."
            />
          </div>
        </Panel>
      </div>

      <Panel
        eyebrow="Baseline change control"
        title="Promote alternative to baseline"
        description="Promotion is a consequential action. It requires a backend confirmation and will never be performed by this frontend-only screen."
      >
        <div className="panel-body">
          {showPromotionConfirmation ? (
            <div className="inline-notice notice-warning" role="alert">
              <TriangleAlert size={16} aria-hidden="true" />
              <div>
                <strong>Confirm promotion request</strong>
                <p>This would replace the connected baseline only after the backend validates and saves it. The API is unavailable here, so confirming will not change the baseline or send any entries.</p>
                <div className="form-actions form-actions-left">
                  <Button type="button" variant="ghost" icon={X} onClick={() => setShowPromotionConfirmation(false)}>Cancel</Button>
                  <Button
                    type="button"
                    variant="primary"
                    icon={Check}
                    onClick={() => {
                      reportUnavailable('promoting the alternative scenario to baseline');
                      setShowPromotionConfirmation(false);
                    }}
                  >
                    Confirm promotion request
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="dashboard-disclaimer">
              <ShieldCheck size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Baseline is unchanged.</strong> Review the alternative entries first, then open the explicit confirmation step if you want to request promotion when an API is connected.</p>
              <Button type="button" variant="secondary" icon={ArrowRightLeft} onClick={() => setShowPromotionConfirmation(true)}>Review promotion</Button>
            </div>
          )}
        </div>
      </Panel>
    </>
  );
}
