import { useApiNotice } from '../hooks/useApiNotice';
import { ApiNotice, Button, Field, FormActions, InlineNotice, PageHeader, Panel, SelectInput, TextArea, TextInput } from '../components/common/ui';

function EvidenceControls({ sectionId, sectionLabel }: { sectionId: string; sectionLabel: string }) {
  return (
    <div className="profile-evidence-grid">
      <Field label={`${sectionLabel} source / evidence reference`} htmlFor={`${sectionId}-source`} hint="A source citation is a draft until company records are connected.">
        <TextInput id={`${sectionId}-source`} placeholder="Document, record, or source location" />
      </Field>
      <Field label="Verification status" htmlFor={`${sectionId}-verification`} hint="Only a connected review can save or verify this information.">
        <SelectInput id={`${sectionId}-verification`} defaultValue="">
          <option value="">Not set</option>
          <option value="needs-review">Needs review</option>
          <option value="verified-by-person">Verified by a person</option>
          <option value="conflicting">Conflicting sources</option>
        </SelectInput>
      </Field>
    </div>
  );
}

export default function CompanyProfile() {
  const { message, reportUnavailable } = useApiNotice();
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    reportUnavailable('company profile save');
  }

  return <>
    <PageHeader
      eyebrow="Workspace / Company profile"
      title="Company profile"
      description="Organize the organization, delivery capability, certifications, financial capacity, and source evidence your ProjectIQ workflows will use. Profile values remain unsaved until a company service is connected."
      actions={<Button type="button" variant="primary" onClick={() => reportUnavailable('company profile save')}>Save profile</Button>}
    />
    <ApiNotice compact />
    <form onSubmit={submit} className="stack">
      <Panel title="Organization" description="Identity and operating context. Values are entered locally and are not a saved company record.">
        <div className="panel-body stack">
          <div className="form-grid">
            <Field label="Registered company name" htmlFor="company-name"><TextInput id="company-name" placeholder="Enter the legal company name" /></Field>
            <Field label="Trading name" htmlFor="trading-name"><TextInput id="trading-name" placeholder="Optional" /></Field>
            <Field label="Registration number" htmlFor="company-registration"><TextInput id="company-registration" placeholder="Company identifier" /></Field>
            <Field label="Primary jurisdiction" htmlFor="company-jurisdiction"><TextInput id="company-jurisdiction" placeholder="Country or region" /></Field>
            <Field label="Primary sector" htmlFor="company-sector"><SelectInput id="company-sector" defaultValue=""><option value="">Select a sector</option><option>Construction & infrastructure</option><option>Manufacturing</option><option>Professional services</option><option>Technology</option><option>Other</option></SelectInput></Field>
            <Field label="Years operating" htmlFor="company-years"><TextInput id="company-years" type="number" min="0" placeholder="Enter years" /></Field>
          </div>
          <EvidenceControls sectionId="organization" sectionLabel="Organization" />
        </div>
      </Panel>

      <div className="two-column-grid">
        <Panel title="Certifications & accreditations" description="Record names, valid dates, and where supporting evidence can be reviewed.">
          <div className="panel-body stack">
            <Field label="Certifications" htmlFor="certifications" hint="Use one entry per line. No certificate has been verified in this frontend."><TextArea id="certifications" placeholder="No certifications entered" /></Field>
            <EvidenceControls sectionId="certifications" sectionLabel="Certification" />
          </div>
        </Panel>
        <Panel title="Capabilities & delivery" description="Describe services, delivery limits, skills, and verified capacity.">
          <div className="panel-body stack">
            <Field label="Capabilities and skills" htmlFor="capabilities"><TextArea id="capabilities" placeholder="No capabilities entered" /></Field>
            <Field label="Delivery constraints" htmlFor="constraints"><TextArea id="constraints" placeholder="No constraints entered" /></Field>
            <EvidenceControls sectionId="capabilities" sectionLabel="Capability" />
          </div>
        </Panel>
      </div>

      <Panel title="Financial capacity" description="Provide a source-led description of financial capacity; no financial assessment is calculated or inferred here.">
        <div className="panel-body stack">
          <div className="form-grid">
            <Field label="Reporting period" htmlFor="finance-period" hint="Specify the statement period or financial year."><TextInput id="finance-period" placeholder="Reporting period" /></Field>
            <Field label="Currency basis" htmlFor="finance-currency"><SelectInput id="finance-currency" defaultValue=""><option value="">Select currency</option><option value="AUD">AUD</option><option value="CAD">CAD</option><option value="EUR">EUR</option><option value="GBP">GBP</option><option value="NZD">NZD</option><option value="USD">USD</option><option value="other">Other</option></SelectInput></Field>
            <Field label="Revenue basis / source" htmlFor="finance-revenue"><TextInput id="finance-revenue" placeholder="Describe the source and reporting basis" /></Field>
            <Field label="Working capital / liquidity evidence" htmlFor="finance-liquidity"><TextInput id="finance-liquidity" placeholder="Describe the available evidence" /></Field>
            <Field className="field-full" label="Financing, bonding, or guarantee notes" htmlFor="finance-facilities"><TextArea id="finance-facilities" placeholder="Record the source and scope of any relevant facility or guarantee" /></Field>
          </div>
          <EvidenceControls sectionId="finance" sectionLabel="Financial capacity" />
          <InlineNotice variant="info">Financial records require appropriate access controls and qualified review. Nothing entered here is persisted or submitted.</InlineNotice>
        </div>
      </Panel>

      <div className="two-column-grid">
        <Panel title="Equipment & assets" description="Describe assets and capacity alongside a source reference and human verification state.">
          <div className="panel-body stack"><Field label="Equipment inventory notes" htmlFor="company-equipment"><TextArea id="company-equipment" placeholder="No equipment information entered" /></Field><EvidenceControls sectionId="equipment" sectionLabel="Equipment" /></div>
        </Panel>
        <Panel title="Past projects" description="Capture relevant experience and evidence locations without asserting suitability.">
          <div className="panel-body stack"><Field label="Relevant past projects" htmlFor="past-projects"><TextArea id="past-projects" placeholder="No past projects entered" /></Field><EvidenceControls sectionId="past-projects" sectionLabel="Past project" /></div>
        </Panel>
      </div>

      {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
      <FormActions><Button type="submit" variant="secondary">Save profile</Button></FormActions>
    </form>
  </>;
}
