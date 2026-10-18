import { useMemo, useState } from 'react';
import { Activity, CalendarDays, CheckCheck, CircleHelp, FileClock, FolderKanban, Plus, Search, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import ModuleHub from '../components/ModuleHub';
import { ApiNotice, EmptyState, MetricCard, Panel, PageHeader } from '../components/common/ui';

const attentionFilters = ['All', 'Missing', 'Unknown', 'Conflicting'] as const;

export default function Dashboard() {
  const [projectSearch, setProjectSearch] = useState('');
  const [attentionFilter, setAttentionFilter] = useState<(typeof attentionFilters)[number]>('All');
  const projectEmptyCopy = useMemo(() => projectSearch.trim()
    ? `No connected project records are available to search for “${projectSearch.trim()}”.`
    : 'Project records will appear here when you connect the Projects API.', [projectSearch]);

  return (
    <>
      <PageHeader
        eyebrow="Workspace / Overview"
        title="Your project workspace"
        description="A clear command center for opportunity review, evidence, feasibility, and delivery decisions."
        actions={<Link className="button button-primary" to="/projects/new"><Plus size={16} aria-hidden="true"/><span>New project</span></Link>}
      />
      <ApiNotice />
      <div className="metric-grid" aria-label="Project overview metrics">
        <MetricCard label="Active projects" icon={FolderKanban} note="Connect the Projects API to load" />
        <MetricCard label="Items for review" icon={ShieldAlert} note="No review records are loaded" />
        <MetricCard label="Next deadline" icon={CalendarDays} note="No project dates are loaded" />
      </div>

      <ModuleHub />

      <div className="dashboard-columns">
        <Panel className="dashboard-project-panel" eyebrow="Portfolio" title="Projects overview" description="Search and review project records when your backend is connected." action={<Link className="text-link" to="/projects">Open projects <span aria-hidden="true">→</span></Link>}>
          <div className="panel-toolbar">
            <label className="search-control"><Search size={15} aria-hidden="true"/><span className="sr-only">Search projects</span><input value={projectSearch} onChange={(event) => setProjectSearch(event.target.value)} placeholder="Search projects or clients" /></label>
            <span className="status-pill status-neutral">No live records</span>
          </div>
          <EmptyState icon={FolderKanban} title={projectSearch ? 'No matching projects' : 'No projects loaded'} description={projectEmptyCopy} action={<Link className="text-link" to="/projects/new">Create a project <span aria-hidden="true">→</span></Link>} />
        </Panel>
        <Panel eyebrow="Human review" title="Needs your attention" description="Evidence questions stay with the people responsible for the decision." action={<span className="status-pill status-neutral">No live items</span>}>
          <div className="panel-body">
            <div className="filter-row" role="group" aria-label="Filter attention items">
              {attentionFilters.map((filter) => <button className={`filter-chip${attentionFilter === filter ? ' is-active' : ''}`} type="button" key={filter} aria-pressed={attentionFilter === filter} onClick={() => setAttentionFilter(filter)}>{filter}</button>)}
            </div>
            <EmptyState icon={CheckCheck} title="Review queue is empty" description={`${attentionFilter === 'All' ? 'No review data is connected yet.' : `No ${attentionFilter.toLowerCase()} items are loaded because the API is not connected.`} This does not indicate that any requirement has been verified or resolved.`} className="dashboard-small-empty" />
          </div>
        </Panel>
      </div>

      <div className="dashboard-panels-lower">
        <Panel eyebrow="Project dates" title="Upcoming deadlines" description="Dates become visible when project data is connected.">
          <EmptyState icon={FileClock} title="No deadlines loaded" description="Connect the Projects API to display due dates and deadline context." className="dashboard-small-empty" />
        </Panel>
        <Panel eyebrow="Recent changes" title="Workspace activity" description="A traceable record of changes across projects and reviews.">
          <EmptyState icon={Activity} title="No activity loaded" description="Recent activity will appear here when an activity endpoint is connected." className="dashboard-small-empty" />
        </Panel>
      </div>

      <div className="dashboard-disclaimer"><CircleHelp size={16} aria-hidden="true"/><p><strong>No project data is being simulated.</strong> This frontend does not connect to a backend, store submissions, upload files, run analysis, calculate financial results, generate reports, or call an AI model.</p></div>
      <div className="dashboard-quick-actions"><span>Need to configure the workspace?</span><Link className="text-link" to="/company">Company profile <span aria-hidden="true">→</span></Link><Link className="text-link" to="/settings">Connection settings <span aria-hidden="true">→</span></Link></div>
    </>
  );
}
