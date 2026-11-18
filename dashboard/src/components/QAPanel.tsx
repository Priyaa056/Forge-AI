import React, { useEffect, useState } from 'react';
import { Bug, ListChecks, TestTube } from 'lucide-react';
import type { AgentStatus, QaReport } from '../types';
import { ApiError, api, errorMessage } from '../services/api';
import { agentBadgeClass } from '../lib/stages';
import { cn, formatDuration } from '../lib/utils';
import { EmptyState, ErrorNote, Panel, ResultBadge, Spinner } from './ui';

interface QAPanelProps {
  projectId: string;
  runId: string;
  qaStatus: AgentStatus;
  /** Changes whenever the report may have changed (e.g. QA agent status). */
  refreshKey: string;
}

const SEVERITY_CLS: Record<string, string> = {
  CRITICAL: 'bg-rose-950/80 border-rose-700 text-rose-300',
  HIGH: 'bg-orange-950/70 border-orange-800 text-orange-300',
  MEDIUM: 'bg-amber-950/60 border-amber-800 text-amber-300',
  LOW: 'bg-slate-900 border-slate-700 text-slate-300',
};

export const TableWrap: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="overflow-x-auto rounded-xl border border-slate-800">
    <table className="w-full text-xs">{children}</table>
  </div>
);

export const Th: React.FC<{ children?: React.ReactNode; className?: string }> = ({ children, className }) => (
  <th className={cn('text-left font-medium text-slate-400 px-3 py-2 bg-slate-900/80 whitespace-nowrap', className)}>{children}</th>
);

export const Td: React.FC<{ children?: React.ReactNode; className?: string }> = ({ children, className }) => (
  <td className={cn('px-3 py-2 border-t border-slate-800/80 align-top', className)}>{children}</td>
);

export const QAPanel: React.FC<QAPanelProps> = ({ projectId, runId, qaStatus, refreshKey }) => {
  const [report, setReport] = useState<QaReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMissing(false);
    api
      .getQaReport(projectId, runId)
      .then((r) => !cancelled && setReport(r))
      .catch((err) => {
        if (cancelled) return;
        setReport(null);
        if (err instanceof ApiError && err.status === 404) setMissing(true);
        else setError(errorMessage(err, 'Failed to load QA report'));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId, runId, refreshKey]);

  const body = () => {
    if (loading && !report) return <Spinner label="Loading QA report..." />;
    if (error) return <ErrorNote message={error} />;
    if (missing || !report) {
      const waiting = qaStatus === 'PENDING' || qaStatus === 'RUNNING' || qaStatus === 'RETRYING';
      return (
        <EmptyState
          icon={<TestTube className="w-7 h-7" />}
          title={waiting ? 'The QA agent has not finished yet.' : 'No QA report was produced in this run.'}
          hint={
            waiting
              ? 'The report appears here when the QA agent completes.'
              : 'The QA agent was skipped or failed before writing its report.'
          }
        />
      );
    }

    const checks = report.checks ?? [];
    const suites = report.test_suites ?? [];
    const failing = (report.test_results ?? []).filter((t) => t.status !== 'passed' && t.status !== 'skipped');
    const errors = report.errors ?? [];

    return (
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3">
          <ResultBadge value={report.status} className="text-xs px-2.5 py-1" />
          <span className="text-sm font-mono text-white">
            Score <span className="font-bold">{Math.round(report.score ?? 0)}%</span>
          </span>
          <span className="text-xs font-mono text-slate-400">
            {report.tests_passed}/{report.tests_run} tests passed · {report.tests_failed} failed
          </span>
          {report.frontend_build && (
            <span className="text-xs font-mono text-slate-400 flex items-center gap-1">
              frontend build <ResultBadge value={report.frontend_build} />
            </span>
          )}
        </div>
        {report.summary && <p className="text-xs text-slate-300 leading-relaxed">{report.summary}</p>}
        {report.repair_recommendation && (
          <div
            className={
              report.status === 'passed'
                ? 'p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/50 text-xs text-emerald-200'
                : 'p-3 rounded-xl bg-amber-950/30 border border-amber-800/50 text-xs text-amber-200'
            }
          >
            <span className="font-semibold">{report.status === 'passed' ? 'Next step: ' : 'Repair recommendation: '}</span>
            {report.repair_recommendation}
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
            <ListChecks className="w-3.5 h-3.5 text-blue-400" /> Checks ({checks.length})
          </h3>
          {checks.length === 0 ? (
            <p className="text-xs text-slate-500">No checks recorded.</p>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>Check</Th>
                  <Th>Category</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Duration</Th>
                  <Th>Details</Th>
                </tr>
              </thead>
              <tbody>
                {checks.map((c, i) => (
                  <tr key={`${c.name}-${i}`} className={c.status === 'failed' ? 'bg-rose-950/20' : undefined}>
                    <Td className="text-slate-200 font-medium min-w-[10rem]">{c.name}</Td>
                    <Td className="font-mono text-slate-400">{c.category}</Td>
                    <Td>
                      <ResultBadge value={c.status} />
                    </Td>
                    <Td className="font-mono text-slate-400 text-right whitespace-nowrap">{formatDuration(c.duration_ms)}</Td>
                    <Td className="text-slate-400 min-w-[14rem] break-words whitespace-pre-wrap">{c.details || '--'}</Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2">Test suites ({suites.length})</h3>
          {suites.length === 0 ? (
            <p className="text-xs text-slate-500">No test suites were executed.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {suites.map((s) => {
                const pct = s.tests_count ? (100 * s.passed_count) / s.tests_count : 0;
                return (
                  <div key={s.name} className="p-3 rounded-xl bg-slate-900/70 border border-slate-800">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-mono text-slate-200 truncate" title={s.name}>
                        {s.name}
                      </span>
                      <span className="font-mono shrink-0">
                        <span className="text-emerald-400">{s.passed_count} passed</span>
                        {s.failed_count > 0 && <span className="text-rose-400"> · {s.failed_count} failed</span>}
                        <span className="text-slate-500"> / {s.tests_count}</span>
                      </span>
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-rose-900/60 overflow-hidden">
                      <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2">Failing tests ({failing.length})</h3>
          {failing.length === 0 ? (
            <p className="text-xs text-emerald-400/80">No failing tests.</p>
          ) : (
            <ul className="space-y-1.5">
              {failing.map((t, i) => (
                <li key={`${t.suite}-${t.name}-${i}`} className="p-3 rounded-xl bg-rose-950/20 border border-rose-900/60 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <ResultBadge value={t.status} />
                    <span className="font-mono text-slate-200 break-all">{t.name}</span>
                    <span className="font-mono text-slate-500 break-all">{t.suite}</span>
                  </div>
                  {t.message && (
                    <pre className="mt-2 font-mono text-[11px] text-rose-200/90 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                      {t.message}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
            <Bug className="w-3.5 h-3.5 text-rose-400" /> Errors ({errors.length})
          </h3>
          {errors.length === 0 ? (
            <p className="text-xs text-emerald-400/80">No errors reported.</p>
          ) : (
            <ul className="space-y-2">
              {errors.map((e) => (
                <li key={e.id} className="p-3 rounded-xl bg-slate-900/70 border border-slate-800 text-xs space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-slate-500">{e.id}</span>
                    <span className={cn('px-1.5 py-0.5 rounded border text-[10px] font-semibold', SEVERITY_CLS[e.severity] ?? SEVERITY_CLS.LOW)}>
                      {e.severity}
                    </span>
                    <span className="font-mono text-slate-300">{e.type}</span>
                    <span className="text-slate-500">in {e.component}</span>
                    <span className="ml-auto inline-flex items-center gap-1 text-slate-400">
                      responsible agent
                      <span className={cn('px-1.5 py-0.5 rounded border font-mono text-[10px]', agentBadgeClass(e.agent))}>{e.agent}</span>
                    </span>
                  </div>
                  <p className="text-slate-200 break-words">{e.message}</p>
                  {e.suggestion && <p className="text-slate-400 break-words">Suggestion: {e.suggestion}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  };

  return (
    <Panel title="QA report" icon={<TestTube className="w-4 h-4 text-pink-400" />} actions={loading && report ? <Spinner /> : undefined}>
      {body()}
    </Panel>
  );
};
