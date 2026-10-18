import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, CloudOff, Info, LoaderCircle, type LucideIcon } from 'lucide-react';

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-header"><div className="page-heading-copy">{eyebrow ? <p className="eyebrow"><span className="eyebrow-mark" aria-hidden="true"/>{eyebrow}</p> : null}<h1>{title}</h1>{description ? <p className="page-description">{description}</p> : null}</div>{actions ? <div className="page-header-actions">{actions}</div> : null}</div>;
}

export function Panel({ eyebrow, title, description, action, className = '', children }: { eyebrow?: string; title?: string; description?: string; action?: ReactNode; className?: string; children: ReactNode }) {
  const hasHeader = eyebrow || title || description || action;
  return <section className={`panel ${className}`}>{hasHeader ? <div className="panel-header"><div>{eyebrow ? <p className="panel-eyebrow">{eyebrow}</p> : null}{title ? <h2>{title}</h2> : null}{description ? <p className="panel-description">{description}</p> : null}</div>{action ? <div className="panel-header-action">{action}</div> : null}</div> : null}{children}</section>;
}

export function ApiNotice({ compact = false }: { compact?: boolean }) {
  return <div className={`api-notice${compact ? ' api-notice-compact' : ''}`} role="status"><span className="api-notice-icon"><CloudOff size={16} aria-hidden="true"/></span><div><strong>Backend API not connected</strong><p>This is the frontend-only workspace. Live project data and server actions are unavailable; nothing will be sent or saved.</p></div></div>;
}

export function Button({ children, variant = 'secondary', icon: Icon, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; icon?: LucideIcon }) {
  return <button className={`button button-${variant}${className ? ` ${className}` : ''}`} {...props}>{Icon ? <Icon size={15} strokeWidth={1.9} aria-hidden="true"/> : null}{children}</button>;
}

export function EmptyState({ icon: Icon, title, description, action, className = '' }: { icon?: LucideIcon; title: string; description: string; action?: ReactNode; className?: string }) {
  return <div className={`empty-state${className ? ` ${className}` : ''}`}><span className="empty-state-icon">{Icon ? <Icon size={20} strokeWidth={1.7} aria-hidden="true"/> : <Info size={19} aria-hidden="true"/>}</span><div className="empty-state-copy"><h3>{title}</h3><p>{description}</p>{action ? <div className="empty-state-action">{action}</div> : null}</div></div>;
}

export function LoadingState({ label = 'Loading', description }: { label?: string; description?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle size={18} className="loading-spinner" aria-hidden="true"/><div><strong>{label}</strong>{description ? <p>{description}</p> : null}</div></div>;
}

export function ErrorState({ title = 'Unable to load this information', description, onRetry }: { title?: string; description: string; onRetry?: () => void }) {
  return <div className="inline-notice notice-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>{title}</strong><p>{description}</p>{onRetry ? <Button type="button" variant="secondary" onClick={onRetry}>Retry</Button> : null}</div></div>;
}

export function SuccessState({ title, description }: { title: string; description?: string }) {
  return <div className="inline-notice notice-success" role="status"><CheckCircle2 size={16} aria-hidden="true"/><div><strong>{title}</strong>{description ? <p>{description}</p> : null}</div></div>;
}

export function MetricCard({ label, icon: Icon, value = '—', note }: { label: string; icon: LucideIcon; value?: string; note: string }) {
  return <section className="metric-card"><div className="metric-card-top"><span>{label}</span><Icon size={17} strokeWidth={1.8} aria-hidden="true"/></div><strong className="metric-value">{value}</strong><span className="metric-note">{note}</span></section>;
}

export function Field({ label, htmlFor, hint, required = false, className = '', children }: { label: string; htmlFor: string; hint?: string; required?: boolean; className?: string; children: ReactNode }) {
  return <div className={`field${className ? ` ${className}` : ''}`}><label htmlFor={htmlFor}>{label}{required ? <span className="required-mark" aria-hidden="true"> *</span> : null}</label>{children}{hint ? <small className="field-hint">{hint}</small> : null}</div>;
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) { return <input className={`input${props.className ? ` ${props.className}` : ''}`} {...props}/>; }
export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className={`input textarea${props.className ? ` ${props.className}` : ''}`} {...props}/>; }
export function SelectInput(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select className={`input select-input${props.className ? ` ${props.className}` : ''}`} {...props}/>; }
export function FormActions({ children, className = '' }: { children: ReactNode; className?: string }) { return <div className={`form-actions${className ? ` ${className}` : ''}`}>{children}</div>; }

const noticeIcons = { info: Info, warning: AlertTriangle, success: CheckCircle2, error: AlertCircle } satisfies Record<string, LucideIcon>;
export function InlineNotice({ children, variant = 'info' }: { children: ReactNode; variant?: 'info' | 'warning' | 'success' | 'error' }) {
  const Icon = noticeIcons[variant];
  return <div className={`inline-notice notice-${variant}`} role={variant === 'error' ? 'alert' : 'status'}><Icon size={16} aria-hidden="true"/><div>{children}</div></div>;
}

export function StatusPill({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'green' | 'amber' | 'red' | 'violet' | 'blue' }) {
  return <span className={`status-pill status-${tone}`}><span className="status-pill-dot" aria-hidden="true"/>{children}</span>;
}

export function Tabs({ label, value, onChange, items }: { label: string; value: string; onChange: (value: string) => void; items: Array<{ id: string; label: string }> }) {
  return <div className="tabs" role="tablist" aria-label={label}>{items.map((item) => <button type="button" role="tab" className={`tab${value === item.id ? ' is-active' : ''}`} aria-selected={value === item.id} key={item.id} onClick={() => onChange(item.id)}>{item.label}</button>)}</div>;
}

export function DataTable({ headers, children, label = 'Data table', emptyTitle, emptyDescription }: { headers: string[]; children?: ReactNode; label?: string; emptyTitle?: string; emptyDescription?: string }) {
  const hasRows = Boolean(children);
  return <><div className="data-table-wrap"><table className="data-table"><caption className="sr-only">{label}</caption><thead><tr>{headers.map((header) => <th scope="col" key={header}>{header}</th>)}</tr></thead><tbody>{children}</tbody></table></div>{emptyTitle && emptyDescription && !hasRows ? <EmptyState title={emptyTitle} description={emptyDescription} className="table-empty-state"/> : null}</>;
}

export function SectionHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="section-heading"><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>{action}</div>;
}
