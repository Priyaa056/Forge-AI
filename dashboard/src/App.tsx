import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, WifiOff } from 'lucide-react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { PromptInput, type PromptSubmission } from './components/PromptInput';
import { ProjectView } from './components/ProjectView';
import { ErrorNote } from './components/ui';
import { api, errorMessage, isNetworkError } from './services/api';
import type { ProjectListItem, SystemInfo } from './types';
import { STAGE_ORDER } from './types';
import { STAGE_META } from './lib/stages';

// ------------------------------------------------------------------ hash routing
type Route = { view: 'new' } | { view: 'project'; projectId: string; runId: string | null };

function parseHash(hash: string): Route {
  const parts = hash
    .replace(/^#\/?/, '')
    .split('/')
    .filter(Boolean)
    .map((p) => {
      try {
        return decodeURIComponent(p);
      } catch {
        return p;
      }
    });
  if (parts[0] === 'project' && parts[1]) {
    return { view: 'project', projectId: parts[1], runId: parts[2] === 'run' && parts[3] ? parts[3] : null };
  }
  return { view: 'new' };
}

function routeToHash(route: Route): string {
  if (route.view === 'new') return '#/new';
  const base = `#/project/${encodeURIComponent(route.projectId)}`;
  return route.runId ? `${base}/run/${encodeURIComponent(route.runId)}` : base;
}

const HEARTBEAT_MS = 5000;

// ------------------------------------------------------------------ new project view
const NewProjectView: React.FC<{
  system: SystemInfo | null;
  onCreate: (sub: PromptSubmission) => Promise<void>;
}> = ({ system, onCreate }) => (
  <div className="max-w-3xl mx-auto space-y-5">
    <div>
      <h2 className="text-xl sm:text-2xl font-bold text-white">Generate a new application</h2>
      <p className="text-sm text-slate-400 mt-1">
        Describe your app idea. Seven FORGE AI agents run in order and generate a real full-stack application (REST API,
        database, auth and React frontend) which is tested, checked for deployment readiness and versioned.
      </p>
    </div>

    <section className="glass-panel rounded-2xl p-4 sm:p-6 border border-slate-800 shadow-xl">
      <PromptInput mode="project" faultInjectionEnabled={!!system?.fault_injection_enabled} onSubmit={onCreate} />
    </section>

    <section className="glass-card rounded-2xl p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Agent pipeline</h3>
      <ol className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {STAGE_ORDER.map((s) => {
          const meta = STAGE_META[s];
          const Icon = meta.icon;
          return (
            <li key={s} className="flex items-center gap-2.5 text-xs">
              <span className="p-1.5 rounded-lg bg-slate-900 border border-slate-800">
                <Icon className={`w-4 h-4 ${meta.accent}`} />
              </span>
              <span className="text-slate-200 font-medium">
                {meta.index}. {meta.title}
              </span>
              <span className="text-slate-500 truncate">{meta.description}</span>
            </li>
          );
        })}
      </ol>
      <p className="text-[11px] text-slate-500 mt-3 flex items-center gap-1.5">
        <ArrowRight className="w-3 h-3" />
        A run that completes all seven agents becomes a stable version you can preview, download or roll back to.
      </p>
    </section>
  </div>
);

// ------------------------------------------------------------------ app
export default function App() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const systemRef = useRef<SystemInfo | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const navigate = useCallback((next: Route, replace = false) => {
    const hash = routeToHash(next);
    if (replace) window.history.replaceState(null, '', hash);
    else if (window.location.hash !== hash) window.location.hash = hash;
    setRoute(next);
    setSidebarOpen(false);
  }, []);

  const loadSystem = useCallback(async () => {
    try {
      const s = await api.getSystem();
      systemRef.current = s;
      setSystem(s);
    } catch {
      // reported through the heartbeat
    }
  }, []);

  const refreshProjects = useCallback(async (showSpinner = false) => {
    if (showSpinner) setProjectsLoading(true);
    try {
      const list = await api.listProjects();
      setProjects(list);
      setApiOnline(true);
      setApiError(null);
      if (!systemRef.current) void loadSystem();
    } catch (err) {
      if (isNetworkError(err)) {
        setApiOnline(false);
        setApiError(null);
      } else {
        setApiOnline(true);
        setApiError(errorMessage(err, 'Failed to load projects'));
      }
    } finally {
      setProjectsLoading(false);
    }
  }, [loadSystem]);

  // Heartbeat: keeps the project list fresh and detects when the platform API goes away / comes back.
  useEffect(() => {
    void loadSystem();
    void refreshProjects(true);
    const t = setInterval(() => void refreshProjects(), HEARTBEAT_MS);
    return () => clearInterval(t);
  }, [loadSystem, refreshProjects]);

  const createProject = async (sub: PromptSubmission) => {
    const res = await api.createProject({
      user_prompt: sub.prompt,
      project_name: sub.projectName,
      simulate_failure: sub.simulateFailure,
    });
    navigate({ view: 'project', projectId: res.project_id, runId: res.run_id });
    void refreshProjects();
  };

  const activeProjectId = route.view === 'project' ? route.projectId : null;

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-slate-100 selection:bg-blue-600 selection:text-white overflow-hidden">
      <Navbar system={system} apiOnline={apiOnline} onToggleSidebar={() => setSidebarOpen((o) => !o)} />

      <div className="flex-1 min-h-0 flex">
        <Sidebar
          projects={projects}
          loading={projectsLoading}
          activeProjectId={activeProjectId}
          isNewView={route.view === 'new'}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewProject={() => navigate({ view: 'new' })}
          onSelectProject={(pid) => navigate({ view: 'project', projectId: pid, runId: null })}
          onRefresh={() => void refreshProjects(true)}
        />

        <main className="flex-1 min-w-0 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5 pb-16 space-y-4">
            {apiOnline === false && (
              <div
                role="alert"
                className="p-3.5 rounded-2xl bg-rose-950/70 border border-rose-800 text-rose-100 text-sm flex flex-wrap items-start gap-3"
              >
                <WifiOff className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-[12rem]">
                  <p className="font-semibold">Cannot reach the FORGE AI platform API.</p>
                  <p className="text-xs text-rose-200/80 mt-0.5">
                    Expected at http://127.0.0.1:8000 (proxied via /api). Start it from the repository root with{' '}
                    <code className="px-1 py-0.5 rounded bg-rose-900/60">uvicorn backend.main:app --port 8000</code>.
                    Retrying every {HEARTBEAT_MS / 1000} s.
                  </p>
                </div>
                <button
                  onClick={() => void refreshProjects(true)}
                  className="px-3 py-1.5 rounded-lg bg-rose-900/70 hover:bg-rose-800 border border-rose-700 text-xs font-medium"
                >
                  Retry now
                </button>
              </div>
            )}
            {apiError && <ErrorNote title="Platform API error" message={apiError} onDismiss={() => setApiError(null)} />}

            {route.view === 'new' ? (
              <NewProjectView system={system} onCreate={createProject} />
            ) : (
              <ProjectView
                key={route.projectId}
                projectId={route.projectId}
                runId={route.runId}
                system={system}
                onSelectRun={(rid, replace) => navigate({ view: 'project', projectId: route.projectId, runId: rid }, replace)}
                onProjectsChanged={() => void refreshProjects()}
                onNewProject={() => navigate({ view: 'new' })}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
