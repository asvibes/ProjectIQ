import { useRef, useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, FilePlus2, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ApiNotice, Button, EmptyState, Field, FormActions, InlineNotice, PageHeader, Panel, SelectInput, TextArea, TextInput } from '../components/common/ui';
import { useApiNotice } from '../hooks/useApiNotice';

const steps = ['Opportunity', 'Project details', 'Documents', 'Review'];

type ProjectDraft = { title: string; client: string; tenderRef: string; procurementType: string; region: string; deadline: string; summary: string };
const blankDraft: ProjectDraft = { title: '', client: '', tenderRef: '', procurementType: '', region: '', deadline: '', summary: '' };

export default function NewProjectWizard() {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<ProjectDraft>(blankDraft);
  const [files, setFiles] = useState<File[]>([]);
  const { message, reportUnavailable } = useApiNotice();
  const formRef = useRef<HTMLFormElement>(null);
  const update = (key: keyof ProjectDraft, value: string) => setDraft((current) => ({ ...current, [key]: value }));

  function advance() {
    if (step < 2 && !formRef.current?.reportValidity()) return;
    setStep((current) => Math.min(current + 1, steps.length - 1));
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    reportUnavailable(step === 3 ? 'project creation' : 'draft save');
  }

  return (
    <>
      <PageHeader eyebrow="Projects / New project" title="Set up an opportunity" description="Capture the tender context before connecting your project and document services." actions={<Link className="button button-secondary" to="/projects"><ArrowLeft size={16}/><span>Back to projects</span></Link>} />
      <ApiNotice compact />
      <Panel className="wizard-card">
        <div className="panel-body">
          <ol className="wizard-steps" aria-label="Project setup progress">{steps.map((name, index) => <li className={`wizard-step${step === index ? ' is-active' : ''}${step > index ? ' is-complete' : ''}`} key={name}><span className="wizard-step-index">{index + 1}</span><span className="wizard-step-copy">{name}</span></li>)}</ol>
          <form ref={formRef} onSubmit={submit}>
            {step === 0 ? <div className="stack"><div><h2 className="form-section-title">Opportunity details</h2><p className="form-section-copy">Add the core information used to identify the tender.</p></div><div className="form-grid"><Field label="Project or opportunity name" htmlFor="project-title" required><TextInput id="project-title" required value={draft.title} onChange={(event) => update('title', event.target.value)} placeholder="e.g. Regional facilities framework" /></Field><Field label="Client / contracting authority" htmlFor="project-client" required><TextInput id="project-client" required value={draft.client} onChange={(event) => update('client', event.target.value)} placeholder="Organization name" /></Field><Field label="Tender reference" htmlFor="tender-ref"><TextInput id="tender-ref" value={draft.tenderRef} onChange={(event) => update('tenderRef', event.target.value)} placeholder="Reference as published" /></Field><Field label="Procurement type" htmlFor="procurement-type"><SelectInput id="procurement-type" value={draft.procurementType} onChange={(event) => update('procurementType', event.target.value)}><option value="">Select a type</option><option>Open procedure</option><option>Framework agreement</option><option>Restricted procedure</option><option>Other</option></SelectInput></Field></div></div> : null}
            {step === 1 ? <div className="stack"><div><h2 className="form-section-title">Project context</h2><p className="form-section-copy">These entries remain only in this browser screen until a project API is connected.</p></div><div className="form-grid"><Field label="Delivery region" htmlFor="region"><TextInput id="region" value={draft.region} onChange={(event) => update('region', event.target.value)} placeholder="Region or jurisdiction" /></Field><Field label="Submission deadline" htmlFor="deadline"><TextInput id="deadline" type="date" value={draft.deadline} onChange={(event) => update('deadline', event.target.value)} /></Field><Field label="Opportunity summary" htmlFor="project-summary" className="field-full"><TextArea id="project-summary" value={draft.summary} onChange={(event) => update('summary', event.target.value)} placeholder="Scope, delivery model, or context to review" /></Field></div></div> : null}
            {step === 2 ? <div className="stack"><div><h2 className="form-section-title">Tender documents</h2><p className="form-section-copy">Choose files to review the upload interface. They are not transferred or processed.</p></div><label className="file-dropzone"><input type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt" onChange={(event) => setFiles((current) => [...current, ...Array.from(event.target.files ?? [])])} /><span><FilePlus2 size={23}/><strong>Select tender or company files</strong><small>PDF, DOCX, XLSX, CSV or TXT · local selection only</small></span></label>{files.length ? <div className="file-list">{files.map((file, index) => <div className="file-list-item" key={`${file.name}-${index}`}><FilePlus2 size={16}/><strong>{file.name}</strong><span>Selected · not uploaded</span><button className="file-remove" type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}><X size={15}/></button></div>)}</div> : <EmptyState title="No files selected" description="Selected file names appear here. Nothing leaves your device in this frontend-only build." />}</div> : null}
            {step === 3 ? <div className="stack"><div><h2 className="form-section-title">Review project setup</h2><p className="form-section-copy">This is a review of your current unsaved entries, not a saved project.</p></div><div className="review-summary"><div><span>Opportunity</span><strong>{draft.title || 'Not entered'}</strong></div><div><span>Client</span><strong>{draft.client || 'Not entered'}</strong></div><div><span>Tender reference</span><strong>{draft.tenderRef || 'Not entered'}</strong></div><div><span>Deadline</span><strong>{draft.deadline || 'Not entered'}</strong></div><div><span>Files selected</span><strong>{files.length}</strong></div></div><InlineNotice variant="warning">Creating this project requires a backend connection. No project, file, or analysis job will be submitted.</InlineNotice></div> : null}
            {message ? <InlineNotice variant="warning">{message}</InlineNotice> : null}
            <FormActions>
              <Link className="button button-ghost" to="/dashboard">Cancel</Link>
              <Button type="button" variant="secondary" onClick={() => reportUnavailable('draft save')}>Save draft</Button>
              {step > 0 ? <Button type="button" variant="secondary" onClick={() => setStep((current) => Math.max(0, current - 1))}><ArrowLeft size={15}/>Back</Button> : null}
              {step < steps.length - 1 ? <Button type="button" variant="primary" onClick={advance}>Continue<ArrowRight size={15}/></Button> : <Button type="submit" variant="primary">Create project</Button>}
              {step === steps.length - 1 ? <Button type="button" variant="secondary" onClick={() => reportUnavailable('starting project analysis')}>Start analysis<ArrowRight size={15}/></Button> : null}
            </FormActions>
          </form>
        </div>
      </Panel>
    </>
  );
}
