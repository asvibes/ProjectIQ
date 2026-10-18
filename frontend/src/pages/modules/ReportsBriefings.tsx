import { useState, type ChangeEvent, type FormEvent } from 'react';
import {
  Download,
  FileCheck2,
  FileOutput,
  FileText,
  History,
  LayoutList,
  Presentation,
  Send,
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
  TextInput,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type OutputTab = 'reports' | 'briefings';
type Audience = 'executive' | 'analyst';

type OutputDraft = {
  projectId: string;
  reportType: string;
  title: string;
};

const reportTypes = [
  { value: 'decision-report', label: 'Project decision report' },
  { value: 'requirements-report', label: 'Requirements and evidence report' },
  { value: 'risk-report', label: 'Risk and review report' },
];

const initialDraft: OutputDraft = {
  projectId: '',
  reportType: 'decision-report',
  title: '',
};

export default function ReportsBriefings() {
  const [activeTab, setActiveTab] = useState<OutputTab>('reports');
  const [audience, setAudience] = useState<Audience>('executive');
  const [draft, setDraft] = useState<OutputDraft>(initialDraft);
  const { message, clearMessage, reportUnavailable } = useApiNotice();

  const updateDraft = <K extends keyof OutputDraft>(key: K, value: OutputDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    clearMessage();
  };

  const handleTabChange = (value: string) => {
    setActiveTab(value as OutputTab);
    clearMessage();
  };

  const handleAudienceChange = (value: string) => {
    setAudience(value as Audience);
    clearMessage();
  };

  const handleGenerate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable(activeTab === 'reports' ? 'report generation' : 'briefing preparation');
  };

  const handleUnavailableAction = (action: string) => {
    reportUnavailable(action);
  };

  const outputLabel = activeTab === 'reports' ? 'report' : 'briefing';
  const previewDescription = audience === 'executive'
    ? 'The executive view will prioritise decision context, material risks, assumptions, and open questions once project evidence is connected.'
    : 'The analyst view will provide a more detailed evidence and review structure once project records are connected.';

  return (
    <>
      <PageHeader
        eyebrow="Intelligence & outputs / Decision support"
        title="Reports & Briefings"
        description="Prepare an evidence-led project output without implying that a report has been generated or that any project data is available."
        actions={(
          <>
            <Button
              type="button"
              variant="secondary"
              icon={Download}
              onClick={() => handleUnavailableAction(`downloading the ${outputLabel}`)}
            >
              Download
            </Button>
            <Button
              type="button"
              variant="primary"
              icon={FileOutput}
              onClick={() => handleUnavailableAction(`exporting the ${outputLabel}`)}
            >
              Export
            </Button>
          </>
        )}
      />

      <div className="content-section stack">
        <ApiNotice />
        {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}

        <Panel
          eyebrow="Output workspace"
          title="Choose an output to prepare"
          description="These controls are local drafts only. No project list, report content, or generated file is loaded in this frontend-only workspace."
          action={(
            <Tabs
              label="Output type"
              value={activeTab}
              onChange={handleTabChange}
              items={[{ id: 'reports', label: 'Reports' }, { id: 'briefings', label: 'Briefings' }]}
            />
          )}
        >
          <form className="panel-body" onSubmit={handleGenerate}>
            <div className="form-grid">
              <Field
                label="Project"
                htmlFor="reports-briefings-project"
                required
                hint="A connected project will appear here when the Projects API is available."
              >
                <SelectInput
                  id="reports-briefings-project"
                  value={draft.projectId}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('projectId', event.target.value)}
                  required
                >
                  <option value="">No project data available</option>
                </SelectInput>
              </Field>

              <Field
                label={activeTab === 'reports' ? 'Report type' : 'Briefing type'}
                htmlFor="reports-briefings-type"
                required
                hint="Type selection is a local preparation setting; it does not start generation."
              >
                <SelectInput
                  id="reports-briefings-type"
                  value={draft.reportType}
                  onChange={(event: ChangeEvent<HTMLSelectElement>) => updateDraft('reportType', event.target.value)}
                  required
                >
                  {reportTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                </SelectInput>
              </Field>

              <Field
                className="field-full"
                label="Working title"
                htmlFor="reports-briefings-title"
                hint="Optional local text. It remains on screen if the action cannot be sent."
              >
                <TextInput
                  id="reports-briefings-title"
                  value={draft.title}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => updateDraft('title', event.target.value)}
                  placeholder={activeTab === 'reports' ? 'Add a working report title' : 'Add a working briefing title'}
                  maxLength={160}
                />
              </Field>
            </div>

            <div className="dashboard-disclaimer">
              <FileCheck2 size={16} strokeWidth={1.8} aria-hidden="true" />
              <p><strong>Evidence boundary:</strong> no project, requirement, risk, financial, or source records are connected. Empty sections below are intentional and do not represent findings.</p>
            </div>

            <FormActions className="form-actions-left">
              <Button type="submit" variant="primary" icon={Send}>
                {activeTab === 'reports' ? 'Generate report' : 'Prepare briefing'}
              </Button>
              <span className="field-hint">No request will be made while the backend API is disconnected.</span>
            </FormActions>
          </form>
        </Panel>

        <div className="split-grid">
          <Panel
            eyebrow="Output preview"
            title={`${activeTab === 'reports' ? 'Report' : 'Briefing'} preview`}
            description="Preview content will appear only after a connected service returns a traceable output."
            action={(
              <Tabs
                label="Preview audience"
                value={audience}
                onChange={handleAudienceChange}
                items={[{ id: 'executive', label: 'Executive' }, { id: 'analyst', label: 'Analyst' }]}
              />
            )}
          >
            <div className="panel-body">
              <div className="key-value-list" aria-label="Preview settings">
                <div className="key-value-row">
                  <span>Selected output</span>
                  <strong>{activeTab === 'reports' ? 'Report' : 'Briefing'}</strong>
                </div>
                <div className="key-value-row">
                  <span>View</span>
                  <strong>{audience === 'executive' ? 'Executive' : 'Analyst'}</strong>
                </div>
                <div className="key-value-row">
                  <span>Project context</span>
                  <strong>Not loaded</strong>
                </div>
              </div>
              <EmptyState
                icon={activeTab === 'reports' ? FileText : Presentation}
                title={`No ${outputLabel} preview available`}
                description={previewDescription}
              />
              <div className="form-actions form-actions-left">
                <Button
                  type="button"
                  variant="secondary"
                  icon={Download}
                  onClick={() => handleUnavailableAction(`downloading the ${outputLabel} preview`)}
                >
                  Download preview
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  icon={FileOutput}
                  onClick={() => handleUnavailableAction(`exporting the ${outputLabel} preview`)}
                >
                  Export preview
                </Button>
              </div>
            </div>
          </Panel>

          <Panel
            eyebrow="Traceability"
            title="Version history"
            description="Saved versions and their source details will be listed here when the reports service is connected."
            action={<StatusPill tone="neutral">No saved versions</StatusPill>}
          >
            <div className="panel-body">
              <DataTable
                label="Report and briefing version history"
                headers={['Version', 'Output', 'Updated', 'Status']}
                emptyTitle="No version history"
                emptyDescription="Nothing has been generated or saved. This empty table is not a record of a previous output."
              />
              <div className="dashboard-disclaimer">
                <History size={16} strokeWidth={1.8} aria-hidden="true" />
                <p><strong>Traceability stays explicit:</strong> a future version must identify its source project, output type, creator, and connected evidence before it can be shown here.</p>
              </div>
            </div>
          </Panel>
        </div>

        <Panel
          eyebrow="Output actions"
          title="What is available in this workspace"
          description="Buttons are present for interaction review, but they do not create, save, or download files without a connected API."
        >
          <div className="panel-body">
            <div className="filter-row" aria-label="Available output actions">
              <Button type="button" variant="secondary" icon={LayoutList} onClick={() => handleUnavailableAction('loading report sections')}>View sections</Button>
              <Button type="button" variant="secondary" icon={Download} onClick={() => handleUnavailableAction(`downloading the ${outputLabel}`)}>Download</Button>
              <Button type="button" variant="secondary" icon={FileOutput} onClick={() => handleUnavailableAction(`exporting the ${outputLabel}`)}>Export</Button>
            </div>
            <p className="field-hint">No file was generated, and no content was sent or saved.</p>
          </div>
        </Panel>
      </div>
    </>
  );
}
