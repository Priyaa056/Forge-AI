import React from 'react';
import { FolderGit2, Plus, RefreshCw, X } from 'lucide-react';
import type { ProjectListItem } from '../types';
import { cn, formatRelative } from '../lib/utils';
import { StatusBadge } from './ui';

interface SidebarProps {
  projects: ProjectListItem[];
  loading: boolean;
  activeProjectId: string | null;
  isNewView: boolean;
  open: boolean;
  onClose: () => void;
  onNewProject: () => void;
  onSelectProject: (projectId: string) => void;
  onRefresh: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  projects,
  loading,
  activeProjectId,
  isNewView,
  open,
  onClose,
  onNewProject,
  onSelectProject,
  onRefresh,
}) => {
  return (
    <>
      {/* Mobile backdrop */}
      <div
        className={cn('fixed inset-0 z-30 bg-slate-950/70 backdrop-blur-sm lg:hidden', open ? 'block' : 'hidden')}
        onClick={onClose}
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-72 max-w-[85vw] shrink-0 lg:static lg:z-auto lg:max-w-none',
          'bg-slate-950 lg:bg-slate-950/60 border-r border-slate-800 flex flex-col transition-transform duration-200',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
        aria-label="Project history"
      >
        <div className="px-4 py-4 border-b border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <FolderGit2 className="w-4 h-4 text-blue-400" />
              Projects
              <span className="font-mono text-slate-500 normal-case">({projects.length})</span>
            </h2>
            <div className="flex items-center gap-1">
              <button
                onClick={onRefresh}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                title="Refresh project list"
                aria-label="Refresh project list"
              >
                <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
              </button>
              <button
                onClick={onClose}
                className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
                aria-label="Close project list"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
          <button
            onClick={onNewProject}
            className={cn(
              'w-full px-3 py-2 rounded-xl text-sm font-medium flex items-center justify-center gap-2 transition-all',
              isNewView
                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-600/20'
                : 'bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200',
            )}
          >
            <Plus className="w-4 h-4" />
            New project
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {projects.length === 0 && !loading && (
            <p className="text-xs text-slate-500 px-3 py-6 text-center">
              No projects yet. Describe an app idea to generate your first one.
            </p>
          )}
          {projects.map((p) => {
            const active = p.project_id === activeProjectId;
            return (
              <button
                key={p.project_id}
                onClick={() => onSelectProject(p.project_id)}
                className={cn(
                  'w-full text-left px-3 py-2.5 rounded-xl border transition-colors group',
                  active
                    ? 'bg-blue-950/40 border-blue-800/70'
                    : 'border-transparent hover:bg-slate-900/80 hover:border-slate-800',
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <span
                    className={cn(
                      'text-sm font-medium line-clamp-2 break-words',
                      active ? 'text-white' : 'text-slate-200 group-hover:text-white',
                    )}
                  >
                    {p.name}
                  </span>
                  {p.last_status && <StatusBadge status={p.last_status} size="xs" className="shrink-0 mt-0.5" />}
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-[11px] font-mono text-slate-500">
                  <span
                    className={cn(
                      'px-1.5 py-0.5 rounded border',
                      p.current_version
                        ? 'bg-emerald-950/40 border-emerald-900/70 text-emerald-400'
                        : 'bg-slate-900 border-slate-800 text-slate-500',
                    )}
                  >
                    {p.current_version ? `v${p.current_version}` : 'no stable version'}
                  </span>
                  <span>
                    {p.run_count} run{p.run_count === 1 ? '' : 's'}
                  </span>
                  <span className="ml-auto truncate">{formatRelative(p.updated_at)}</span>
                </div>
              </button>
            );
          })}
        </nav>
      </aside>
    </>
  );
};
