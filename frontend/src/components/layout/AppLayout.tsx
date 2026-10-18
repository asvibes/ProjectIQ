import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className={`app-shell${menuOpen ? ' sidebar-open' : ''}`}>
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>Skip to page content</a>
      <Sidebar onNavigate={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)} />
      <button className="sidebar-scrim" type="button" aria-label="Close navigation" tabIndex={menuOpen ? 0 : -1} onClick={() => setMenuOpen(false)} />
      <div className="app-main">
        <TopBar menuOpen={menuOpen} onOpenMenu={() => setMenuOpen(true)} />
        <main className="app-content" id="main-content" tabIndex={-1}><Outlet /></main>
        <footer className="app-footer"><span>ProjectIQ · Frontend implementation</span><span>Decision support only; qualified professionals verify specialist matters.</span><a href="/">Return to the landing page ↗</a></footer>
      </div>
    </div>
  );
}
