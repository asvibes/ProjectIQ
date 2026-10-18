import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  BadgeDollarSign,
  Calculator,
  CircleDollarSign,
  ClipboardList,
  Coins,
  Download,
  FileText,
  Landmark,
  LineChart,
  Percent,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Truck,
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
  MetricCard,
  Panel,
  PageHeader,
  SelectInput,
  StatusPill,
  TextArea,
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type InputStatus = 'verified' | 'estimate' | 'assumption' | 'missing';
type CostBasis = 'fixed' | 'unit-rate' | 'percentage' | 'monthly' | 'unknown';

type FinancialDraft = {
  revenue: string;
  revenueBasis: string;
  currency: string;
  conversionNote: string;
  taxTreatment: string;
  paymentTerms: string;
  labourRole: string;
  labourHours: string;
  labourRate: string;
  labourStatus: InputStatus;
  labourNote: string;
  materialsDescription: string;
  materialsQuantity: string;
  materialsUnitCost: string;
  materialsStatus: InputStatus;
  materialsNote: string;
  equipmentDescription: string;
  equipmentBasis: CostBasis;
  equipmentDuration: string;
  equipmentAmount: string;
  equipmentStatus: InputStatus;
  contractorsScope: string;
  contractorsAmount: string;
  contractorsStatus: InputStatus;
  contractorsNote: string;
  logisticsDescription: string;
  logisticsBasis: CostBasis;
  logisticsAmount: string;
  logisticsStatus: InputStatus;
  insuranceDescription: string;
  insuranceAmount: string;
  insuranceStatus: InputStatus;
  insuranceNote: string;
  overheadDescription: string;
  overheadBasis: CostBasis;
  overheadAmount: string;
  overheadStatus: InputStatus;
  contingencyPercent: string;
  contingencyBasis: string;
  contingencyStatus: InputStatus;
  financingDescription: string;
  financingAmount: string;
  financingRate: string;
  financingStatus: InputStatus;
  marginPercent: string;
  marginBasis: string;
  marginStatus: InputStatus;
  reviewNote: string;
};

const initialDraft: FinancialDraft = {
  revenue: '',
  revenueBasis: '',
  currency: '',
  conversionNote: '',
  taxTreatment: '',
  paymentTerms: '',
  labourRole: '',
  labourHours: '',
  labourRate: '',
  labourStatus: 'missing',
  labourNote: '',
  materialsDescription: '',
  materialsQuantity: '',
  materialsUnitCost: '',
  materialsStatus: 'missing',
  materialsNote: '',
  equipmentDescription: '',
  equipmentBasis: 'unknown',
  equipmentDuration: '',
  equipmentAmount: '',
  equipmentStatus: 'missing',
  contractorsScope: '',
  contractorsAmount: '',
  contractorsStatus: 'missing',
  contractorsNote: '',
  logisticsDescription: '',
  logisticsBasis: 'unknown',
  logisticsAmount: '',
  logisticsStatus: 'missing',
  insuranceDescription: '',
  insuranceAmount: '',
  insuranceStatus: 'missing',
  insuranceNote: '',
  overheadDescription: '',
  overheadBasis: 'unknown',
  overheadAmount: '',
  overheadStatus: 'missing',
  contingencyPercent: '',
  contingencyBasis: '',
  contingencyStatus: 'missing',
  financingDescription: '',
  financingAmount: '',
  financingRate: '',
  financingStatus: 'missing',
  marginPercent: '',
  marginBasis: '',
  marginStatus: 'missing',
  reviewNote: '',
};

const statusOptions: Array<{ value: InputStatus; label: string }> = [
  { value: 'verified', label: 'Verified quotation / source' },
  { value: 'estimate', label: 'Estimate' },
  { value: 'assumption', label: 'Assumption' },
  { value: 'missing', label: 'Missing input' },
];

const basisOptions: Array<{ value: CostBasis; label: string }> = [
  { value: 'unknown', label: 'Select basis' },
  { value: 'fixed', label: 'Fixed amount' },
  { value: 'unit-rate', label: 'Unit rate' },
  { value: 'percentage', label: 'Percentage' },
  { value: 'monthly', label: 'Monthly' },
];

function StatusSelect({ id, value, onChange }: { id: string; value: InputStatus; onChange: (value: InputStatus) => void }) {
  return (
    <SelectInput id={id} value={value} onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value as InputStatus)}>
      {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </SelectInput>
  );
}

function BasisSelect({ id, value, onChange }: { id: string; value: CostBasis; onChange: (value: CostBasis) => void }) {
  return (
    <SelectInput id={id} value={value} onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value as CostBasis)}>
      {basisOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </SelectInput>
  );
}

export default function FinancialAnalysis() {
  const [draft, setDraft] = useState<FinancialDraft>(initialDraft);
  const { message, clearNotice, reportUnavailable } = useApiNotice();

  const updateDraft = <K extends keyof FinancialDraft>(key: K, value: FinancialDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearNotice();
  };

  const handleUnavailableAction = (action: string) => {
    reportUnavailable(action);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this financial input set');
  };

  const focusInput = (id: string) => {
    clearNotice();
    document.getElementById(id)?.focus();
  };

  return (
    <>
      <PageHeader
        eyebrow="Project workspace / Commercial planning"
        title="Financial Analysis"
        description="Capture revenue, cost, financing, and margin assumptions for a future deterministic financial review. Results stay empty until a connected calculation service validates these inputs."
        actions={(
          <>
            <Button type="button" variant="secondary" icon={Download} onClick={() => handleUnavailableAction('exporting financial inputs')}>Export inputs</Button>
            <Button type="button" variant="primary" icon={RefreshCw} onClick={() => handleUnavailableAction('recalculating financial results')}>Recalculate</Button>
          </>
        )}
      />
      <ApiNotice />
      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

      <div className="metric-grid" aria-label="Financial analysis summary">
        <MetricCard label="Total cost" icon={Calculator} note="Awaiting backend calculation" />
        <MetricCard label="Suggested bid" icon={BadgeDollarSign} note="Not available without validated inputs" />
        <MetricCard label="Break-even" icon={LineChart} note="Requires dated cost and revenue records" />
        <MetricCard label="Cash flow" icon={Coins} note="No periods loaded from the API" />
      </div>

      <Panel
        eyebrow="Revenue & currency"
        title="Set the commercial frame"
        description="Keep revenue, currency, tax treatment, and payment assumptions explicit. Values are held in this browser view only."
      >
        <form className="panel-body" onSubmit={handleSubmit}>
          <div className="form-grid">
            <Field label="Expected revenue" htmlFor="financial-revenue" hint="Enter the project revenue in the selected currency; no total is calculated here.">
              <TextInput id="financial-revenue" type="number" min="0" step="any" inputMode="decimal" value={draft.revenue} onChange={(event) => updateDraft('revenue', event.target.value)} placeholder="Amount" />
            </Field>
            <Field label="Revenue basis" htmlFor="financial-revenue-basis" hint="For example: contract value, milestone value, or internal estimate.">
              <TextInput id="financial-revenue-basis" value={draft.revenueBasis} onChange={(event) => updateDraft('revenueBasis', event.target.value)} placeholder="Basis or source" />
            </Field>
            <Field label="Currency" htmlFor="financial-currency" required hint="Do not mix currencies without an explicit conversion source.">
              <SelectInput id="financial-currency" required value={draft.currency} onChange={(event) => updateDraft('currency', event.target.value)}>
                <option value="">Select currency</option>
                <option value="AUD">AUD — Australian dollar</option>
                <option value="CAD">CAD — Canadian dollar</option>
                <option value="EUR">EUR — Euro</option>
                <option value="GBP">GBP — Pound sterling</option>
                <option value="NZD">NZD — New Zealand dollar</option>
                <option value="USD">USD — US dollar</option>
                <option value="other">Other / specify in note</option>
              </SelectInput>
            </Field>
            <Field label="Tax treatment" htmlFor="financial-tax-treatment" hint="Record whether revenue and costs are tax-inclusive or tax-exclusive.">
              <SelectInput id="financial-tax-treatment" value={draft.taxTreatment} onChange={(event) => updateDraft('taxTreatment', event.target.value)}>
                <option value="">Select treatment</option>
                <option value="inclusive">Tax inclusive</option>
                <option value="exclusive">Tax exclusive</option>
                <option value="unknown">Unknown / needs review</option>
              </SelectInput>
            </Field>
            <Field label="Payment terms" htmlFor="financial-payment-terms" hint="Optional timing assumption for a future cash-flow schedule.">
              <TextInput id="financial-payment-terms" value={draft.paymentTerms} onChange={(event) => updateDraft('paymentTerms', event.target.value)} placeholder="e.g. milestone or net days" />
            </Field>
            <Field label="Conversion / currency note" htmlFor="financial-conversion-note" hint="Name the source and date if conversion is required.">
              <TextInput id="financial-conversion-note" value={draft.conversionNote} onChange={(event) => updateDraft('conversionNote', event.target.value)} placeholder="Source, date, or conversion constraint" />
            </Field>
          </div>
          <FormActions className="form-actions-left">
            <Button type="submit" variant="secondary" icon={Save}>Save commercial inputs</Button>
          </FormActions>
        </form>
      </Panel>

      <Panel
        eyebrow="Cost model inputs"
        title="Organise the cost assumptions"
        description="Use one section for each cost category. Status labels describe provenance, not calculation certainty."
        action={<Button type="button" variant="ghost" icon={Plus} onClick={() => focusInput('financial-labour-role')}>Start a cost line</Button>}
      >
        <form className="panel-body" onSubmit={handleSubmit}>
          <div className="form-grid">
            <fieldset className="financial-fieldset field-full">
              <legend><UsersRound size={16} aria-hidden="true" /> Labour</legend>
              <p className="field-hint">Record role-level hours and rates without treating headcount as capacity.</p>
              <div className="form-grid">
                <Field label="Role or work package" htmlFor="financial-labour-role"><TextInput id="financial-labour-role" value={draft.labourRole} onChange={(event) => updateDraft('labourRole', event.target.value)} placeholder="Role, crew, or work package" /></Field>
                <Field label="Hours / quantity" htmlFor="financial-labour-hours"><TextInput id="financial-labour-hours" type="number" min="0" step="any" value={draft.labourHours} onChange={(event) => updateDraft('labourHours', event.target.value)} placeholder="Hours" /></Field>
                <Field label="Rate" htmlFor="financial-labour-rate"><TextInput id="financial-labour-rate" type="number" min="0" step="any" value={draft.labourRate} onChange={(event) => updateDraft('labourRate', event.target.value)} placeholder="Rate in selected currency" /></Field>
                <Field label="Input provenance" htmlFor="financial-labour-status"><StatusSelect id="financial-labour-status" value={draft.labourStatus} onChange={(value) => updateDraft('labourStatus', value)} /></Field>
                <Field label="Labour note" htmlFor="financial-labour-note" className="field-full"><TextInput id="financial-labour-note" value={draft.labourNote} onChange={(event) => updateDraft('labourNote', event.target.value)} placeholder="Source, roster assumption, or review note" /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset field-full">
              <legend><ClipboardList size={16} aria-hidden="true" /> Materials</legend>
              <p className="field-hint">Capture quantities, unit costs, and whether a quote or estimate supports the entry.</p>
              <div className="form-grid">
                <Field label="Material or item" htmlFor="financial-materials-description"><TextInput id="financial-materials-description" value={draft.materialsDescription} onChange={(event) => updateDraft('materialsDescription', event.target.value)} placeholder="Material, component, or consumable" /></Field>
                <Field label="Quantity" htmlFor="financial-materials-quantity"><TextInput id="financial-materials-quantity" type="number" min="0" step="any" value={draft.materialsQuantity} onChange={(event) => updateDraft('materialsQuantity', event.target.value)} placeholder="Quantity" /></Field>
                <Field label="Unit cost" htmlFor="financial-materials-unit-cost"><TextInput id="financial-materials-unit-cost" type="number" min="0" step="any" value={draft.materialsUnitCost} onChange={(event) => updateDraft('materialsUnitCost', event.target.value)} placeholder="Unit cost" /></Field>
                <Field label="Input provenance" htmlFor="financial-materials-status"><StatusSelect id="financial-materials-status" value={draft.materialsStatus} onChange={(value) => updateDraft('materialsStatus', value)} /></Field>
                <Field label="Materials note" htmlFor="financial-materials-note" className="field-full"><TextInput id="financial-materials-note" value={draft.materialsNote} onChange={(event) => updateDraft('materialsNote', event.target.value)} placeholder="Supplier, quote reference, or escalation note" /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><Wrench size={16} aria-hidden="true" /> Equipment</legend>
              <div className="form-grid">
                <Field label="Equipment or asset" htmlFor="financial-equipment-description" className="field-full"><TextInput id="financial-equipment-description" value={draft.equipmentDescription} onChange={(event) => updateDraft('equipmentDescription', event.target.value)} placeholder="Asset or equipment option" /></Field>
                <Field label="Cost basis" htmlFor="financial-equipment-basis"><BasisSelect id="financial-equipment-basis" value={draft.equipmentBasis} onChange={(value) => updateDraft('equipmentBasis', value)} /></Field>
                <Field label="Duration / quantity" htmlFor="financial-equipment-duration"><TextInput id="financial-equipment-duration" value={draft.equipmentDuration} onChange={(event) => updateDraft('equipmentDuration', event.target.value)} placeholder="Days, months, or units" /></Field>
                <Field label="Amount" htmlFor="financial-equipment-amount"><TextInput id="financial-equipment-amount" type="number" min="0" step="any" value={draft.equipmentAmount} onChange={(event) => updateDraft('equipmentAmount', event.target.value)} placeholder="Amount" /></Field>
                <Field label="Input provenance" htmlFor="financial-equipment-status" className="field-full"><StatusSelect id="financial-equipment-status" value={draft.equipmentStatus} onChange={(value) => updateDraft('equipmentStatus', value)} /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><UsersRound size={16} aria-hidden="true" /> Contractors</legend>
              <div className="form-grid">
                <Field label="Scope or contractor" htmlFor="financial-contractors-scope" className="field-full"><TextInput id="financial-contractors-scope" value={draft.contractorsScope} onChange={(event) => updateDraft('contractorsScope', event.target.value)} placeholder="External scope or supplier" /></Field>
                <Field label="Amount" htmlFor="financial-contractors-amount"><TextInput id="financial-contractors-amount" type="number" min="0" step="any" value={draft.contractorsAmount} onChange={(event) => updateDraft('contractorsAmount', event.target.value)} placeholder="Amount" /></Field>
                <Field label="Input provenance" htmlFor="financial-contractors-status"><StatusSelect id="financial-contractors-status" value={draft.contractorsStatus} onChange={(value) => updateDraft('contractorsStatus', value)} /></Field>
                <Field label="Contractor note" htmlFor="financial-contractors-note" className="field-full"><TextInput id="financial-contractors-note" value={draft.contractorsNote} onChange={(event) => updateDraft('contractorsNote', event.target.value)} placeholder="Scope boundary, quote, or dependency" /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><Truck size={16} aria-hidden="true" /> Logistics</legend>
              <div className="form-grid">
                <Field label="Logistics item" htmlFor="financial-logistics-description" className="field-full"><TextInput id="financial-logistics-description" value={draft.logisticsDescription} onChange={(event) => updateDraft('logisticsDescription', event.target.value)} placeholder="Freight, travel, storage, or handling" /></Field>
                <Field label="Cost basis" htmlFor="financial-logistics-basis"><BasisSelect id="financial-logistics-basis" value={draft.logisticsBasis} onChange={(value) => updateDraft('logisticsBasis', value)} /></Field>
                <Field label="Amount" htmlFor="financial-logistics-amount"><TextInput id="financial-logistics-amount" type="number" min="0" step="any" value={draft.logisticsAmount} onChange={(event) => updateDraft('logisticsAmount', event.target.value)} placeholder="Amount" /></Field>
                <Field label="Input provenance" htmlFor="financial-logistics-status" className="field-full"><StatusSelect id="financial-logistics-status" value={draft.logisticsStatus} onChange={(value) => updateDraft('logisticsStatus', value)} /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><ShieldCheck size={16} aria-hidden="true" /> Insurance &amp; compliance</legend>
              <div className="form-grid">
                <Field label="Policy, permit, or compliance item" htmlFor="financial-insurance-description" className="field-full"><TextInput id="financial-insurance-description" value={draft.insuranceDescription} onChange={(event) => updateDraft('insuranceDescription', event.target.value)} placeholder="Insurance, certification, permit, or audit" /></Field>
                <Field label="Amount" htmlFor="financial-insurance-amount"><TextInput id="financial-insurance-amount" type="number" min="0" step="any" value={draft.insuranceAmount} onChange={(event) => updateDraft('insuranceAmount', event.target.value)} placeholder="Amount" /></Field>
                <Field label="Input provenance" htmlFor="financial-insurance-status"><StatusSelect id="financial-insurance-status" value={draft.insuranceStatus} onChange={(value) => updateDraft('insuranceStatus', value)} /></Field>
                <Field label="Coverage or requirement note" htmlFor="financial-insurance-note" className="field-full"><TextInput id="financial-insurance-note" value={draft.insuranceNote} onChange={(event) => updateDraft('insuranceNote', event.target.value)} placeholder="Coverage period or compliance requirement" /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><Landmark size={16} aria-hidden="true" /> Overhead</legend>
              <div className="form-grid">
                <Field label="Overhead category" htmlFor="financial-overhead-description" className="field-full"><TextInput id="financial-overhead-description" value={draft.overheadDescription} onChange={(event) => updateDraft('overheadDescription', event.target.value)} placeholder="Project management, office, or administration" /></Field>
                <Field label="Cost basis" htmlFor="financial-overhead-basis"><BasisSelect id="financial-overhead-basis" value={draft.overheadBasis} onChange={(value) => updateDraft('overheadBasis', value)} /></Field>
                <Field label="Amount / rate" htmlFor="financial-overhead-amount"><TextInput id="financial-overhead-amount" type="number" min="0" step="any" value={draft.overheadAmount} onChange={(event) => updateDraft('overheadAmount', event.target.value)} placeholder="Amount or rate" /></Field>
                <Field label="Input provenance" htmlFor="financial-overhead-status" className="field-full"><StatusSelect id="financial-overhead-status" value={draft.overheadStatus} onChange={(value) => updateDraft('overheadStatus', value)} /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><Percent size={16} aria-hidden="true" /> Contingency</legend>
              <div className="form-grid">
                <Field label="Contingency rate" htmlFor="financial-contingency-percent"><TextInput id="financial-contingency-percent" type="number" min="0" step="any" value={draft.contingencyPercent} onChange={(event) => updateDraft('contingencyPercent', event.target.value)} placeholder="Percentage" /></Field>
                <Field label="Applied to" htmlFor="financial-contingency-basis"><TextInput id="financial-contingency-basis" value={draft.contingencyBasis} onChange={(event) => updateDraft('contingencyBasis', event.target.value)} placeholder="Scope or cost base" /></Field>
                <Field label="Input provenance" htmlFor="financial-contingency-status" className="field-full"><StatusSelect id="financial-contingency-status" value={draft.contingencyStatus} onChange={(value) => updateDraft('contingencyStatus', value)} /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><CircleDollarSign size={16} aria-hidden="true" /> Financing</legend>
              <div className="form-grid">
                <Field label="Facility or financing cost" htmlFor="financial-financing-description" className="field-full"><TextInput id="financial-financing-description" value={draft.financingDescription} onChange={(event) => updateDraft('financingDescription', event.target.value)} placeholder="Loan, facility, fee, or funding assumption" /></Field>
                <Field label="Amount / fee" htmlFor="financial-financing-amount"><TextInput id="financial-financing-amount" type="number" min="0" step="any" value={draft.financingAmount} onChange={(event) => updateDraft('financingAmount', event.target.value)} placeholder="Amount" /></Field>
                <Field label="Rate" htmlFor="financial-financing-rate"><TextInput id="financial-financing-rate" type="number" min="0" step="any" value={draft.financingRate} onChange={(event) => updateDraft('financingRate', event.target.value)} placeholder="Rate, if applicable" /></Field>
                <Field label="Input provenance" htmlFor="financial-financing-status" className="field-full"><StatusSelect id="financial-financing-status" value={draft.financingStatus} onChange={(value) => updateDraft('financingStatus', value)} /></Field>
              </div>
            </fieldset>

            <fieldset className="financial-fieldset">
              <legend><Percent size={16} aria-hidden="true" /> Desired margin</legend>
              <div className="form-grid">
                <Field label="Target margin" htmlFor="financial-margin-percent"><TextInput id="financial-margin-percent" type="number" min="0" step="any" value={draft.marginPercent} onChange={(event) => updateDraft('marginPercent', event.target.value)} placeholder="Percentage" /></Field>
                <Field label="Margin basis" htmlFor="financial-margin-basis"><TextInput id="financial-margin-basis" value={draft.marginBasis} onChange={(event) => updateDraft('marginBasis', event.target.value)} placeholder="Commercial policy or basis" /></Field>
                <Field label="Input provenance" htmlFor="financial-margin-status" className="field-full"><StatusSelect id="financial-margin-status" value={draft.marginStatus} onChange={(value) => updateDraft('marginStatus', value)} /></Field>
              </div>
            </fieldset>
          </div>
          <Field label="Review note" htmlFor="financial-review-note" hint="Capture unresolved assumptions for the connected calculation review.">
            <TextArea id="financial-review-note" value={draft.reviewNote} onChange={(event) => updateDraft('reviewNote', event.target.value)} placeholder="What should be verified before relying on a financial result?" />
          </Field>
          <FormActions className="form-actions-left">
            <Button type="submit" variant="secondary" icon={Save}>Save cost inputs</Button>
            <Button type="button" variant="ghost" icon={FileText} onClick={() => handleUnavailableAction('saving a financial baseline')}>Save baseline</Button>
            <Button type="button" variant="ghost" icon={Plus} onClick={() => handleUnavailableAction('creating a financial scenario')}>Create scenario</Button>
          </FormActions>
        </form>
      </Panel>

      <div className="content-section stack">
        <Panel
          eyebrow="Results workspace"
          title="Backend-calculated results"
          description="The frontend deliberately does not calculate totals, prices, break-even, profitability, ROI, payback, or cash flow. A connected deterministic service must validate provenance, currency, dates, and missing inputs first."
        >
          <div className="panel-body">
            <EmptyState
              icon={Calculator}
              title="No financial results are available"
              description="Connect the backend calculation engine to load validated totals and profitability metrics. Your current form entries remain on screen and have not been sent or saved."
            />
            <div className="formula-grid" aria-label="Financial formula and provenance explanation">
              <section className="explanation-card">
                <div className="explanation-card-heading"><Calculator size={17} aria-hidden="true" /><h3>Calculation contract</h3></div>
                <ul className="plain-list">
                  <li><strong>Revenue:</strong> the entered revenue value, currency, tax treatment, and timing are inputs only.</li>
                  <li><strong>Cost model:</strong> the connected service determines which categories and provenance statuses are eligible for a result.</li>
                  <li><strong>Margin and price:</strong> the backend applies its documented formula after validating the cost basis; this screen performs no arithmetic.</li>
                  <li><strong>Break-even and cash flow:</strong> require backend-validated timing, payment, financing, and cost records.</li>
                </ul>
              </section>
              <section className="explanation-card">
                <div className="explanation-card-heading"><FileText size={17} aria-hidden="true" /><h3>Provenance to review</h3></div>
                <p className="panel-description">Every value should remain traceable before it contributes to a result.</p>
                <div className="status-list">
                  <StatusPill tone="green">Verified quotation / source</StatusPill>
                  <StatusPill tone="amber">Estimate</StatusPill>
                  <StatusPill tone="violet">Assumption</StatusPill>
                  <StatusPill tone="neutral">Missing input</StatusPill>
                </div>
                <p className="field-hint">Unknown or missing information must not be interpreted as zero, not met, or a completed calculation.</p>
              </section>
            </div>
          </div>
        </Panel>

        <div className="two-column-grid">
          <Panel eyebrow="Cost breakdown" title="Category results" description="The result table and visualization are populated by the calculation service; no seeded rows are shown.">
            <div className="chart-empty" role="status" aria-label="Cost breakdown chart has no data">
              <div className="chart-empty-guides" aria-hidden="true"><span /><span /><span /><span /></div>
              <div className="chart-empty-message"><Calculator size={18} aria-hidden="true" /><strong>No cost inputs to chart</strong><span>Connect validated category results to render a cost breakdown.</span></div>
            </div>
            <DataTable
              headers={['Category', 'Validated basis', 'Result']}
              label="Financial cost breakdown"
              emptyTitle="No category results yet"
              emptyDescription="Submit the inputs to a connected deterministic calculation service before reviewing category totals."
            />
          </Panel>
          <Panel eyebrow="Cash-flow schedule" title="Periods and movements" description="Cash-flow periods, inflows, outflows, balances, and the chart require dated backend records.">
            <div className="chart-empty" role="status" aria-label="Cash-flow chart has no data">
              <div className="chart-empty-guides" aria-hidden="true"><span /><span /><span /><span /></div>
              <div className="chart-empty-message"><LineChart size={18} aria-hidden="true" /><strong>No dated cash-flow inputs</strong><span>A connected service must validate timing before any flow is drawn.</span></div>
            </div>
            <DataTable
              headers={['Period', 'Inflow', 'Outflow', 'Balance']}
              label="Financial cash-flow schedule"
              emptyTitle="No cash-flow periods yet"
              emptyDescription="Payment terms and dated cost records are not connected, so no cash flow is displayed."
            />
          </Panel>
        </div>
      </div>

      <Panel eyebrow="Review handoff" title="Keep the next decision accountable" description="Use the API notice and provenance labels as the handoff boundary. No action below claims to have changed a project record.">
        <div className="panel-body">
          <div className="inline-notice notice-info" role="note">
            <Landmark size={16} aria-hidden="true" />
            <div><strong>Frontend-only draft</strong><p>Values can be edited for review, but saving, exporting, scenario creation, and recalculation remain unavailable until the API is connected.</p></div>
          </div>
          <FormActions className="form-actions-left">
            <Button type="button" variant="secondary" icon={Download} onClick={() => handleUnavailableAction('exporting the financial review')}>Export review</Button>
            <Button type="button" variant="ghost" icon={RefreshCw} onClick={() => handleUnavailableAction('requesting a backend review')}>Request backend review</Button>
          </FormActions>
        </div>
      </Panel>
    </>
  );
}
