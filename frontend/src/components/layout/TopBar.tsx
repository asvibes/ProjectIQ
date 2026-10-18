import { useEffect } from 'react';
import { CloudOff, Menu, Settings } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const routeLabels: Array<[string, string]> = [
  ['/dashboard', 'Dashboard'], ['/projects/new', 'New project'], ['/projects', 'Projects & Documents'],
  ['/company', 'Company profile'], ['/company-fit', 'Company fit'], ['/requirements', 'Requirement analysis'],
  ['/gaps', 'Gaps & contradictions'], ['/risks', 'Risk analysis'], ['/resources', 'Resources & workforce'],
  ['/equipment', 'Equipment analysis'], ['/financials', 'Financial analysis'], ['/scenarios', 'Scenario planning'],
  ['/assistant', 'AI assistant'], ['/reports', 'Reports & briefings'], ['/briefing', 'Decision briefing'],
  ['/bidding', 'Bidding'], ['/settings', 'Settings'], ['/project', 'Project overview'], ['/project/', 'Project overview'],
];

export function getRouteLabel(pathname: string) {
  const match = routeLabels.find(([prefix]) => prefix === pathname || (prefix.endsWith('/') && pathname.startsWith(prefix)));
  return match?.[1] ?? 'ProjectIQ workspace';
}

export default function TopBar({ onOpenMenu, menuOpen }: { onOpenMenu: () => void; menuOpen: boolean }) {
  const location = useLocation();
  const title = getRouteLabel(location.pathname);

  useEffect(() => {
    document.title = `${title} | ProjectIQ`;
  }, [title]);

  return (
    <header className="app-topbar">
      <div className="topbar-left">
        <button className="mobile-menu-button" type="button" onClick={onOpenMenu} aria-label="Open navigation" aria-expanded={menuOpen} aria-controls="app-navigation"><Menu size={19} strokeWidth={1.9} /></button>
        <div className="topbar-crumbs"><span>Workspace</span><span className="crumb-divider" aria-hidden="true">/</span><strong>{title}</strong></div>
      </div>
      <div className="topbar-right">
        <span className="api-status-pill"><CloudOff size={15} strokeWidth={1.8} aria-hidden="true"/><span>API not connected</span></span>
        <Link className="topbar-settings" to="/settings" aria-label="Open settings"><Settings size={17} strokeWidth={1.8} /></Link>
      </div>
    </header>
  );
}
