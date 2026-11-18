import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Download, FileCode, FolderTree, Search } from 'lucide-react';
import type { GeneratedFile } from '../types';
import { STAGE_ORDER } from '../types';
import { ApiError, api, errorMessage } from '../services/api';
import { STAGE_META, agentBadgeClass, isStageName } from '../lib/stages';
import { cn, formatBytes } from '../lib/utils';
import { CopyButton, EmptyState, ErrorNote, Panel, Spinner } from './ui';

interface FilesPanelProps {
  projectId: string;
  runId: string;
  hasCurrentVersion: boolean;
  currentVersion: number | null;
  refreshKey: string;
}

type Source = 'run' | 'current';

export const FilesPanel: React.FC<FilesPanelProps> = ({ projectId, runId, hasCurrentVersion, currentVersion, refreshKey }) => {
  const [source, setSource] = useState<Source>('run');
  const [files, setFiles] = useState<GeneratedFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  const rid = source === 'current' ? 'current' : runId;

  useEffect(() => {
    setSelected(null);
    setContent(null);
  }, [rid]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listFiles(projectId, rid)
      .then((f) => !cancelled && setFiles(f))
      .catch((err) => {
        if (cancelled) return;
        setFiles([]);
        if (!(err instanceof ApiError && err.status === 404)) setError(errorMessage(err, 'Failed to list files'));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId, rid, refreshKey]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setContentLoading(true);
    setContentError(null);
    setContent(null);
    api
      .getFileContent(projectId, rid, selected)
      .then((r) => !cancelled && setContent(r.content))
      .catch((err) => {
        if (cancelled) return;
        setContentError(
          err instanceof ApiError && err.status === 413 ? 'File too large to display (over 500 KB).' : errorMessage(err, 'Failed to load file'),
        );
      })
      .finally(() => !cancelled && setContentLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId, rid, selected]);

  const groups = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const map = new Map<string, GeneratedFile[]>();
    files
      .filter((f) => !q || f.path.toLowerCase().includes(q))
      .forEach((f) => {
        const key = f.agent && isStageName(f.agent) ? f.agent : f.agent || 'other';
        map.set(key, [...(map.get(key) ?? []), f]);
      });
    const order = (k: string) => {
      const i = (STAGE_ORDER as string[]).indexOf(k);
      return i === -1 ? 99 : i;
    };
    return Array.from(map.entries())
      .sort((a, b) => order(a[0]) - order(b[0]) || a[0].localeCompare(b[0]))
      .map(([agent, list]) => ({ agent, files: list.sort((a, b) => a.path.localeCompare(b.path)) }));
  }, [files, filter]);

  const totalBytes = files.reduce((n, f) => n + (f.bytes ?? 0), 0);
  const lines = content?.split('\n') ?? [];

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Generated files
          <span className="text-[11px] font-mono text-slate-500 font-normal">
            {files.length} files · {formatBytes(totalBytes)}
          </span>
        </span>
      }
      icon={<FolderTree className="w-4 h-4 text-blue-400" />}
      actions={
        <>
          <div className="inline-flex rounded-lg border border-slate-700 overflow-hidden text-[11px]">
            <button
              onClick={() => setSource('run')}
              className={cn('px-2.5 py-1', source === 'run' ? 'bg-blue-600/40 text-white' : 'bg-slate-900 text-slate-400 hover:text-slate-200')}
            >
              This run
            </button>
            <button
              onClick={() => setSource('current')}
              disabled={!hasCurrentVersion}
              title={hasCurrentVersion ? undefined : 'No stable version yet'}
              className={cn(
                'px-2.5 py-1 border-l border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed',
                source === 'current' ? 'bg-blue-600/40 text-white' : 'bg-slate-900 text-slate-400 hover:text-slate-200',
              )}
            >
              Active version{currentVersion ? ` (v${currentVersion})` : ''}
            </button>
          </div>
          {files.length > 0 && (
            <a
              href={api.downloadUrl(projectId, rid)}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-[11px] text-slate-200"
              download
            >
              <Download className="w-3.5 h-3.5" /> .zip
            </a>
          )}
        </>
      }
      bodyClassName="p-0"
    >
      {error && <ErrorNote className="m-4" message={error} />}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] min-h-[420px]">
        <div className="border-b lg:border-b-0 lg:border-r border-slate-800 flex flex-col min-w-0">
          <div className="p-2.5 border-b border-slate-800/80">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter by path..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
          <div className="overflow-y-auto max-h-[300px] lg:max-h-[560px] p-1.5">
            {loading && files.length === 0 ? (
              <div className="p-4">
                <Spinner label="Loading files..." />
              </div>
            ) : groups.length === 0 ? (
              <EmptyState
                className="m-2"
                icon={<FileCode className="w-6 h-6" />}
                title={files.length === 0 ? 'No files generated yet.' : 'No files match the filter.'}
              />
            ) : (
              groups.map(({ agent, files: list }) => {
                const isCollapsed = collapsed[agent];
                return (
                  <div key={agent} className="mb-1">
                    <button
                      onClick={() => setCollapsed((c) => ({ ...c, [agent]: !c[agent] }))}
                      className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-slate-900 text-xs"
                    >
                      {isCollapsed ? <ChevronRight className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
                      <span className={cn('px-1.5 py-0.5 rounded border font-mono text-[10px]', agentBadgeClass(agent))}>{agent}</span>
                      <span className="text-slate-400 truncate">{isStageName(agent) ? STAGE_META[agent].title : 'Unattributed files'}</span>
                      <span className="ml-auto font-mono text-[10px] text-slate-500">{list.length}</span>
                    </button>
                    {!isCollapsed && (
                      <ul className="ml-3 border-l border-slate-800 pl-1.5">
                        {list.map((f) => (
                          <li key={f.path}>
                            <button
                              onClick={() => setSelected(f.path)}
                              className={cn(
                                'w-full text-left flex items-center gap-2 px-2 py-1 rounded-md font-mono text-[11px] transition-colors',
                                selected === f.path ? 'bg-blue-600/25 text-white' : 'text-slate-300 hover:bg-slate-900',
                              )}
                              title={f.path}
                            >
                              <span className="truncate flex-1 min-w-0">{f.path}</span>
                              <span className="text-[10px] text-slate-500 shrink-0">{formatBytes(f.bytes)}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="flex flex-col min-w-0">
          {selected ? (
            <>
              <div className="px-3 py-2 border-b border-slate-800/80 flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-slate-300 break-all">{selected}</span>
                {content != null && <CopyButton text={content} label="file" />}
              </div>
              <div className="overflow-auto max-h-[560px] bg-slate-950/90 flex-1">
                {contentLoading && (
                  <div className="p-4">
                    <Spinner label="Loading file..." />
                  </div>
                )}
                {contentError && <ErrorNote className="m-3" message={contentError} />}
                {content != null && !contentLoading && (
                  <pre className="text-[11px] leading-5 font-mono text-slate-200 py-2 min-w-max">
                    {lines.map((line, i) => (
                      <div key={i} className="flex">
                        <span className="select-none text-right text-slate-600 w-10 pr-3 shrink-0 tabular-nums">{i + 1}</span>
                        <span className="whitespace-pre pr-4">{line || ' '}</span>
                      </div>
                    ))}
                  </pre>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center p-6">
              <p className="text-xs text-slate-500">Select a file to view its contents.</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
};
