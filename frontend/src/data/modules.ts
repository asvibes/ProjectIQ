import type { LucideIcon } from 'lucide-react';
import {
  AlertTriangle,
  Bot,
  Building2,
  Calculator,
  ClipboardCheck,
  FileSearch,
  FileText,
  FolderOpen,
  GitCompareArrows,
  PackageSearch,
  UsersRound,
} from 'lucide-react';

export type ModuleLink = {
  id: string;
  label: string;
  description: string;
  path: string;
  icon: LucideIcon;
};

export type ModuleGroup = {
  id: string;
  label: string;
  description: string;
  modules: ModuleLink[];
};

export const moduleGroups: ModuleGroup[] = [
  {
    id: 'project-evidence',
    label: 'Project setup & evidence',
    description: 'Bring the opportunity, requirements, and company evidence together.',
    modules: [
      { id: 'projects-documents', label: 'Projects & Documents', description: 'Manage projects and tender or company files.', path: '/projects', icon: FolderOpen },
      { id: 'requirements', label: 'Requirement Analysis', description: 'Extract and review tender requirements.', path: '/requirements', icon: ClipboardCheck },
      { id: 'company-fit', label: 'Company Fit Analysis', description: 'Compare requirements with capabilities and evidence.', path: '/company-fit', icon: Building2 },
      { id: 'gaps', label: 'Gap & Contradiction Detection', description: 'Review missing information and conflicting details.', path: '/gaps', icon: GitCompareArrows },
    ],
  },
  {
    id: 'delivery-capacity',
    label: 'Delivery & capacity',
    description: 'Understand project exposure and delivery resources.',
    modules: [
      { id: 'risks', label: 'Risk Analysis', description: 'Review severity, evidence, ownership, and mitigation.', path: '/risks', icon: AlertTriangle },
      { id: 'resources', label: 'Resource & Workforce Planning', description: 'Identify workforce and capacity gaps.', path: '/resources', icon: UsersRound },
      { id: 'equipment', label: 'Equipment Analysis', description: 'Review equipment needs and available options.', path: '/equipment', icon: PackageSearch },
    ],
  },
  {
    id: 'commercial-planning',
    label: 'Commercial planning',
    description: 'Organize assumptions before connecting deterministic calculations.',
    modules: [
      { id: 'financials', label: 'Financial Analysis', description: 'Set up cost, pricing, break-even, and cash-flow inputs.', path: '/financials', icon: Calculator },
      { id: 'scenarios', label: 'Scenario Planning', description: 'Prepare alternatives for later comparison.', path: '/scenarios', icon: GitCompareArrows },
    ],
  },
  {
    id: 'intelligence-output',
    label: 'Intelligence & outputs',
    description: 'Prepare evidence-led questions, briefings, and reports.',
    modules: [
      { id: 'assistant', label: 'AI Assistant', description: 'Ask document-grounded questions when a model is connected.', path: '/assistant', icon: Bot },
      { id: 'reports', label: 'Reports & Briefings', description: 'Prepare project summaries and decision outputs.', path: '/reports', icon: FileText },
    ],
  },
];

export const allModules = moduleGroups.flatMap((group) => group.modules);

export const workspaceLinks: ModuleLink[] = [
  { id: 'dashboard', label: 'Dashboard', description: 'Workspace overview', path: '/dashboard', icon: FileSearch },
  { id: 'company', label: 'Company Profile', description: 'Organization details and capabilities', path: '/company', icon: Building2 },
];
