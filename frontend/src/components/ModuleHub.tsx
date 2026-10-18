import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { moduleGroups } from '../data/modules';

export default function ModuleHub() {
  return (
    <section className="module-hub" aria-labelledby="module-hub-heading">
      <div className="module-hub-header">
        <div>
          <p className="panel-eyebrow">PROJECTIQ WORKSPACE</p>
          <h2 id="module-hub-heading">All modules</h2>
          <p>Choose the part of the opportunity you want to work on.</p>
        </div>
        <span className="module-hub-count">{moduleGroups.reduce((total, group) => total + group.modules.length, 0)} application modules</span>
      </div>
      <div className="module-hub-grid">
        {moduleGroups.map((group) => (
          <section className="module-category" key={group.id} aria-labelledby={`module-group-${group.id}`}>
            <div className="module-category-header">
              <div><h3 id={`module-group-${group.id}`}>{group.label}</h3><p>{group.description}</p></div>
              <span>{group.modules.length.toString().padStart(2, '0')}</span>
            </div>
            <div className="module-category-list">
              {group.modules.map((module) => {
                const Icon = module.icon;
                return (
                  <Link className="module-row" key={module.id} to={module.path}>
                    <span className="module-icon"><Icon size={17} strokeWidth={1.8} aria-hidden="true" /></span>
                    <span className="module-row-copy"><strong>{module.label}</strong><small>{module.description}</small></span>
                    <span className="module-row-arrow"><ArrowUpRight size={16} strokeWidth={1.8} aria-hidden="true" /></span>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
