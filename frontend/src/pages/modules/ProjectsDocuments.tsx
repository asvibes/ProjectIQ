import { useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react';
import {
  ArrowRight,
  Building2,
  FileSearch,
  FileText,
  FolderOpen,
  FolderPlus,
  Search,
  UploadCloud,
  X,
} from 'lucide-react';
import { Link } from 'react-router-dom';
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
  Tabs,
} from '../../components/common/ui';
import { useApiNotice } from '../../hooks/useApiNotice';

type WorkspaceTab = 'projects' | 'documents';
type ProjectFilter = 'all' | 'active' | 'review' | 'archived';
type DocumentFilter = 'all' | 'tender' | 'company' | 'other';

const projectTabs = [
  { id: 'projects', label: 'Projects' },
  { id: 'documents', label: 'Documents' },
];

const projectFilterOptions: Array<{ value: ProjectFilter; label: string }> = [
  { value: 'all', label: 'All project status' },
  { value: 'active', label: 'Active' },
  { value: 'review', label: 'Needs review' },
  { value: 'archived', label: 'Archived' },
];

const documentFilterOptions: Array<{ value: DocumentFilter; label: string }> = [
  { value: 'all', label: 'All document types' },
  { value: 'tender', label: 'Tender documents' },
  { value: 'company', label: 'Company documents' },
  { value: 'other', label: 'Other files' },
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProjectsDocuments() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('projects');
  const [projectSearch, setProjectSearch] = useState('');
  const [projectFilter, setProjectFilter] = useState<ProjectFilter>('all');
  const [documentSearch, setDocumentSearch] = useState('');
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>('all');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const { message, clearMessage, reportUnavailable } = useApiNotice();

  const handleTabChange = (tab: string) => {
    if (tab === 'projects' || tab === 'documents') {
      setActiveTab(tab);
      clearMessage();
    }
  };

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    setSelectedFile(file);
    clearMessage();
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    handleFile(event.dataTransfer.files[0]);
  };

  const handleSaveDocument = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    reportUnavailable('saving this document');
  };

  const projectEmptyTitle = projectSearch.trim() || projectFilter !== 'all'
    ? 'No matching projects'
    : 'No projects loaded';
  const projectEmptyDescription = projectSearch.trim() || projectFilter !== 'all'
    ? 'No connected project records match the current search and filter. Nothing is hidden or simulated.'
    : 'Project records will appear here when the Projects API is connected. Create a project to begin once the API is available.';
  const documentEmptyTitle = documentSearch.trim() || documentFilter !== 'all'
    ? 'No matching documents'
    : 'No documents loaded';
  const documentEmptyDescription = documentSearch.trim() || documentFilter !== 'all'
    ? 'No connected document records match the current search and filter. Nothing is hidden or simulated.'
    : 'Tender and company documents will appear here when the Documents API is connected. A file selected below remains only on this screen.';

  return (
    <>
      <PageHeader
        eyebrow="Workspace / Project setup & evidence"
        title="Projects & Documents"
        description="Organise project records and the tender or company files that support careful review. Live records are not loaded until an API is connected."
        actions={(
          <Link className="button button-primary" to="/projects/new">
            <FolderPlus size={16} strokeWidth={1.8} aria-hidden="true" />
            <span>New project</span>
          </Link>
        )}
      />

      <ApiNotice />

      <section className="panel" aria-labelledby="workspace-tabs-title">
        <div className="panel-header">
          <div>
            <p className="panel-eyebrow">Workspace records</p>
            <h2 id="workspace-tabs-title">Projects and supporting documents</h2>
            <p className="panel-description">Search, filter, and prepare local entries without implying that anything has been sent or saved.</p>
          </div>
          <span className="status-pill status-neutral">No live records</span>
        </div>
        <div className="panel-body">
          <Tabs items={projectTabs} value={activeTab} onChange={handleTabChange} label="Projects and documents view" />
        </div>
      </section>

      {activeTab === 'projects' ? (
        <div className="content-section stack">
          <Panel
            eyebrow="Project register"
            title="Projects"
            description="The table is ready for connected project records; no projects are fabricated in this frontend."
            action={<Link className="text-link" to="/projects/new">Open new project flow <ArrowRight size={14} aria-hidden="true" /></Link>}
          >
            <div className="panel-toolbar">
              <label className="search-control">
                <Search size={15} strokeWidth={1.8} aria-hidden="true" />
                <span className="sr-only">Search projects or clients</span>
                <input
                  value={projectSearch}
                  onChange={(event) => setProjectSearch(event.target.value)}
                  placeholder="Search projects or clients"
                  type="search"
                />
              </label>
              <div className="table-toolbar-right">
                <label className="sr-only" htmlFor="project-status-filter">Filter projects by status</label>
                <SelectInput id="project-status-filter" value={projectFilter} onChange={(event: ChangeEvent<HTMLSelectElement>) => setProjectFilter(event.target.value as ProjectFilter)}>
                  {projectFilterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </div>
            </div>
            <DataTable
              headers={['Project', 'Client', 'Deadline', 'Status', 'Open']}
              emptyTitle={projectEmptyTitle}
              emptyDescription={projectEmptyDescription}
            />
          </Panel>

          <Panel eyebrow="Getting started" title="Start with a project record" description="Use the New Project flow when your connected service is ready to receive a project draft.">
            <div className="panel-body">
              <EmptyState
                icon={FolderOpen}
                title="No project selected"
                description="There is no current project context to show. Starting a project keeps its details and documents together for later review."
                action={<Link className="text-link" to="/projects/new">Go to New Project <ArrowRight size={14} aria-hidden="true" /></Link>}
              />
            </div>
          </Panel>
        </div>
      ) : (
        <div className="content-section stack">
          <Panel
            eyebrow="Document register"
            title="Documents"
            description="Review tender and company files after they are returned by the connected Documents API."
            action={<span className="status-pill status-neutral">No live files</span>}
          >
            <div className="panel-toolbar">
              <label className="search-control">
                <Search size={15} strokeWidth={1.8} aria-hidden="true" />
                <span className="sr-only">Search documents</span>
                <input
                  value={documentSearch}
                  onChange={(event) => setDocumentSearch(event.target.value)}
                  placeholder="Search filenames or document types"
                  type="search"
                />
              </label>
              <div className="table-toolbar-right">
                <label className="sr-only" htmlFor="document-type-filter">Filter documents by type</label>
                <SelectInput id="document-type-filter" value={documentFilter} onChange={(event: ChangeEvent<HTMLSelectElement>) => setDocumentFilter(event.target.value as DocumentFilter)}>
                  {documentFilterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </SelectInput>
              </div>
            </div>
            <DataTable
              headers={['Filename', 'Type', 'Added', 'Version', 'Processing status']}
              emptyTitle={documentEmptyTitle}
              emptyDescription={documentEmptyDescription}
            />
          </Panel>

          <div className="split-grid">
            <Panel title="Select a document" eyebrow="Local file selection" description="Choose a file to review the interaction locally. This control does not upload or process it.">
              <form className="panel-body" onSubmit={handleSaveDocument}>
                <Field label="Tender or company file" htmlFor="document-file" hint="Supported file types can be connected later; this screen only reads the browser-selected file name and size.">
                  <label
                    className="file-dropzone"
                    htmlFor="document-file"
                    onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    style={isDragging ? { borderColor: 'var(--violet)', background: 'var(--violet-pale)' } : undefined}
                  >
                    <UploadCloud size={22} strokeWidth={1.7} aria-hidden="true" />
                    <span><strong>{isDragging ? 'Release to select this file' : 'Drop a file here or choose one'}</strong><br /><small>Selected locally only</small></span>
                    <input id="document-file" type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" onChange={(event) => handleFile(event.target.files?.[0])} />
                  </label>
                </Field>

                {selectedFile ? (
                  <div className="file-list" aria-live="polite">
                    <div className="file-list-item">
                      <FileText size={17} strokeWidth={1.7} aria-hidden="true" />
                      <strong title={selectedFile.name}>{selectedFile.name}</strong>
                      <span>{formatFileSize(selectedFile.size)} · local only</span>
                      <Button type="button" variant="ghost" aria-label={`Remove ${selectedFile.name}`} onClick={() => { setSelectedFile(null); clearMessage(); }} icon={X} />
                    </div>
                  </div>
                ) : (
                  <InlineNotice variant="info">No file is selected. Choosing a file does not upload, process, or save it.</InlineNotice>
                )}

                <div className="form-actions form-actions-left">
                  <Button type="submit" variant="secondary" disabled={!selectedFile} icon={FileSearch}>Save to project</Button>
                </div>
                {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
              </form>
            </Panel>

            <Panel title="Document sources" eyebrow="Evidence handling" description="Keep the origin and review state of each file explicit when records become available.">
              <div className="panel-body">
                <div className="key-value-list">
                  <div className="key-value-row"><span>Tender files</span><strong>Not connected</strong></div>
                  <div className="key-value-row"><span>Company files</span><strong>Not connected</strong></div>
                  <div className="key-value-row"><span>Processing</span><strong>Not available</strong></div>
                  <div className="key-value-row"><span>Source review</span><strong>Awaiting records</strong></div>
                </div>
                <div className="dashboard-disclaimer"><Building2 size={16} strokeWidth={1.8} aria-hidden="true" /><p><strong>Evidence stays unverified.</strong> A missing or unconnected file is not evidence that a capability or requirement is absent.</p></div>
              </div>
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
