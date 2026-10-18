import { ArrowLeft, BriefcaseBusiness, Building2, LayoutDashboard, Settings, X } from 'lucide-react';
import { Link, NavLink } from 'react-router-dom';
import { moduleGroups } from '../../data/modules';

export default function Sidebar({ onNavigate, onClose }: { onNavigate: () => void; onClose: () => void }) {
  const linkClass = ({ isActive }: { isActive: boolean }) => `nav-link${isActive ? ' is-active' : ''}`;
  return (
    <aside id="app-navigation" className="app-sidebar" aria-label="ProjectIQ application navigation">
      <div className="sidebar-brand-row">
        <Link className="app-brand" to="/dashboard" onClick={onNavigate} aria-label="ProjectIQ Dashboard">
          <span className="app-brand-mark" aria-hidden="true"><svg viewBox="0 0 36 36" fill="none"><path d="M8 24.8 18 8.5l10 16.3H8Z" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round"/><path d="m13.2 24.8 4.8-7.5 4.8 7.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="18" cy="8.5" r="2.2" fill="currentColor"/></svg></span>
          <span className="app-brand-word">project<span>iq</span></span>
        </Link>
        <button className="sidebar-close" type="button" onClick={onClose} aria-label="Close navigation"><X size={19} /></button>
      </div>
      <div className="sidebar-workspace"><span className="workspace-mark"><BriefcaseBusiness size={18} strokeWidth={1.8} aria-hidden="true" /></span><span className="workspace-copy"><strong>ProjectIQ workspace</strong><small>Frontend · API unconnected</small></span></div>
      <div className="sidebar-scroll">
        <nav aria-label="Workspace and module links">
          <div className="nav-group"><p className="nav-group-title">Workspace</p><div className="nav-list">
            <NavLink className={linkClass} to="/dashboard" onClick={onNavigate} end><LayoutDashboard size={17} strokeWidth={1.8} aria-hidden="true"/><span>Dashboard</span></NavLink>
            <NavLink className={linkClass} to="/projects" onClick={onNavigate}><BriefcaseBusiness size={17} strokeWidth={1.8} aria-hidden="true"/><span>Projects & Documents</span></NavLink>
            <NavLink className={linkClass} to="/project" onClick={onNavigate}><FileProjectIcon/><span>Project overview</span></NavLink>
            <NavLink className={linkClass} to="/company" onClick={onNavigate}><Building2 size={17} strokeWidth={1.8} aria-hidden="true"/><span>Company profile</span></NavLink>
          </div></div>
          {moduleGroups.map((group) => <div className="nav-group" key={group.id}><p className="nav-group-title">{group.label}</p><div className="nav-list">{group.modules.filter((module) => module.id !== 'projects-documents').map((module) => { const Icon = module.icon; return <NavLink className={linkClass} key={module.id} to={module.path} onClick={onNavigate}><Icon size={17} strokeWidth={1.8} aria-hidden="true"/><span>{module.label}</span></NavLink>; })}{group.id === 'intelligence-output' ? <NavLink className={linkClass} to="/briefing" onClick={onNavigate}><BriefcaseBusiness size={17} strokeWidth={1.8} aria-hidden="true"/><span>Decision Briefing</span></NavLink> : null}</div></div>)}
          <div className="nav-group"><p className="nav-group-title">Other</p><div className="nav-list"><NavLink className={linkClass} to="/bidding" onClick={onNavigate}><BriefcaseBusiness size={17} strokeWidth={1.8} aria-hidden="true"/><span>Bidding</span></NavLink></div></div>
        </nav>
      </div>
      <div className="sidebar-footer"><NavLink className={linkClass} to="/settings" onClick={onNavigate}><Settings size={17} strokeWidth={1.8} aria-hidden="true"/><span>Settings</span></NavLink><a className="sidebar-footer-link" href="/" onClick={onNavigate}><ArrowLeft size={15} strokeWidth={1.8} aria-hidden="true"/><span>Back to ProjectIQ site</span></a></div>
    </aside>
  );
}

function FileProjectIcon() {
  return <BriefcaseBusiness size={17} strokeWidth={1.8} aria-hidden="true" />;
}
