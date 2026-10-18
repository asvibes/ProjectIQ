import { NavLink } from 'react-router-dom';

const tabs = [
  ['Overview', '/project'],
  ['Documents', '/projects'],
  ['Requirements', '/requirements'],
  ['Company fit', '/company-fit'],
  ['Gaps', '/gaps'],
  ['Risks', '/risks'],
  ['Resources', '/resources'],
  ['Equipment', '/equipment'],
  ['Financials', '/financials'],
  ['Scenarios', '/scenarios'],
  ['Briefing', '/briefing'],
  ['Reports', '/reports'],
  ['Bidding', '/bidding'],
] as const;

export default function ProjectTabs() {
  return (
    <nav className="project-tabs" aria-label="Project sections">
      {tabs.map(([label, path]) => <NavLink key={path} to={path} className={({ isActive }) => `project-tab${isActive ? ' is-active' : ''}`}>{label}</NavLink>)}
    </nav>
  );
}
