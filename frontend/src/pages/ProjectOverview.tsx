import { useParams, Link } from 'react-router-dom';
import { Activity, AlertTriangle, CalendarDays, CircleDollarSign, CircleHelp, FileText, FolderKanban, ListChecks } from 'lucide-react';
import { ApiNotice, Button, EmptyState, PageHeader, Panel } from '../components/common/ui';
import ProjectTabs from '../components/layout/ProjectTabs';

const actions = [
  { label: 'Documents', path: '/projects', icon: FileText },
  { label: 'Requirements', path: '/requirements', icon: ListChecks },
  { label: 'Risk analysis', path: '/risks', icon: AlertTriangle },
];

export default function ProjectOverview() {
  const { projectId } = useParams();
  return <>
    <div className="breadcrumb-line"><Link to="/projects">Projects</Link><span aria-hidden="true">/</span><span>Project overview</span></div>
    <PageHeader eyebrow="Projects / Overview" title="Project overview" description="Project dates, evidence, requirements, financial context, risks, and next actions in one reviewable workspace." actions={<Button variant="secondary" disabled title="A project cannot be selected until project records are connected.">Project actions</Button>} />
    <ApiNotice />
    <ProjectTabs />
    <div className="dashboard-columns">
      <Panel eyebrow="Selected project" title="Project details" description={projectId ? `Project reference: ${projectId}. This record has not been loaded.` : 'No project is selected. Connect the Projects API to load a real project record.'}>
        <EmptyState icon={FolderKanban} title="Project data unavailable" description="Connect the Projects API and open a real project to load its dates, client, stage, requirements, and evidence. No example project has been substituted." action={<Link className="button button-primary" to="/projects">Open Projects & Documents</Link>} />
      </Panel>
      <div className="dashboard-side-stack">
        <Panel title="Key dates"><EmptyState icon={CalendarDays} title="No project dates" description="Deadline and milestone dates appear when project data is available." /></Panel>
        <Panel title="Open questions"><EmptyState icon={CircleHelp} title="No review records" description="No missing-information or risk conclusions are assumed without source data." /></Panel>
      </div>
    </div>
    <div className="dashboard-panels-lower">
      <Panel eyebrow="Financial snapshot" title="Financial highlights" description="Validated cost, revenue, margin, and cash-flow information belongs to the connected finance service.">
        <EmptyState icon={CircleDollarSign} title="No financial summary loaded" description="Financial highlights will appear only when a real project record and validated calculation response are connected." />
      </Panel>
      <Panel eyebrow="Requirements" title="Requirement progress" description="Progress depends on the connected requirement register and its review states.">
        <EmptyState icon={ListChecks} title="No requirement progress loaded" description="No completion percentage or compliance conclusion is inferred while requirement records are unavailable." />
      </Panel>
    </div>
    <div className="dashboard-panels-lower">
      <Panel title="Next actions"><EmptyState icon={ListChecks} title="No actions loaded" description="Action lists will appear with the connected project workflow." /></Panel>
      <Panel title="Recent project activity"><EmptyState icon={Activity} title="No activity loaded" description="Project activity is not stored in this frontend-only build." /></Panel>
    </div>
    <div className="quick-link-row">{actions.map(({ label, path, icon: Icon }) => <Link to={path} className="quick-link-card" key={path}><Icon size={18}/><span>{label}</span><span aria-hidden="true">→</span></Link>)}</div>
  </>;
}
