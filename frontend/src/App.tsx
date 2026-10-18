import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/Dashboard';
import CompanyProfile from './pages/CompanyProfile';
import NewProjectWizard from './pages/NewProjectWizard';
import ProjectOverview from './pages/ProjectOverview';
import Bidding from './pages/Bidding';
import DecisionBriefing from './pages/DecisionBriefing';
import Settings from './pages/Settings';
import ProjectsDocuments from './pages/modules/ProjectsDocuments';
import RequirementAnalysis from './pages/modules/RequirementAnalysis';
import CompanyFitAnalysis from './pages/modules/CompanyFitAnalysis';
import GapContradiction from './pages/modules/GapContradiction';
import RiskAnalysis from './pages/modules/RiskAnalysis';
import ResourcesWorkforce from './pages/modules/ResourcesWorkforce';
import FinancialAnalysis from './pages/modules/FinancialAnalysis';
import ScenarioPlanning from './pages/modules/ScenarioPlanning';
import AIAssistant from './pages/modules/AIAssistant';
import ReportsBriefings from './pages/modules/ReportsBriefings';
import EquipmentAnalysis from './pages/modules/EquipmentAnalysis';

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="projects" element={<ProjectsDocuments />} />
          <Route path="projects/new" element={<NewProjectWizard />} />
          <Route path="project" element={<ProjectOverview />} />
          <Route path="project/:projectId" element={<ProjectOverview />} />
          <Route path="company" element={<CompanyProfile />} />
          <Route path="requirements" element={<RequirementAnalysis />} />
          <Route path="company-fit" element={<CompanyFitAnalysis />} />
          <Route path="gaps" element={<GapContradiction />} />
          <Route path="risks" element={<RiskAnalysis />} />
          <Route path="resources" element={<ResourcesWorkforce />} />
          <Route path="financials" element={<FinancialAnalysis />} />
          <Route path="scenarios" element={<ScenarioPlanning />} />
          <Route path="assistant" element={<AIAssistant />} />
          <Route path="reports" element={<ReportsBriefings />} />
          <Route path="equipment" element={<EquipmentAnalysis />} />
          <Route path="briefing" element={<DecisionBriefing />} />
          <Route path="bidding" element={<Bidding />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
