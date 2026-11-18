import React, { useEffect, useState } from 'react';
import { Container, HeartPulse, Rocket, ShieldCheck, Terminal } from 'lucide-react';
import type { AgentStatus, DeployReport } from '../types';
import { ApiError, api, errorMessage } from '../services/api';
import { cn, formatDuration } from '../lib/utils';
import { EmptyState, ErrorNote, Panel, ResultBadge, Spinner } from './ui';
import { TableWrap, Td, Th } from './QAPanel';

interface DeployPanelProps {
  projectId: string;
  runId: string;
  deployStatus: AgentStatus;
  refreshKey: string;
}

export const DeployPanel: React.FC<DeployPanelProps> = ({ projectId, runId, deployStatus, refreshKey }) => {
  const [report, setReport] = useState<DeployReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMissing(false);
    api
      .getDeployReport(projectId, runId)
      .then((r) => !cancelled && setReport(r))
      .catch((err) => {
        if (cancelled) return;
        setReport(null);
        if (err instanceof ApiError && err.status === 404) setMissing(true);
        else setError(errorMessage(err, 'Failed to load deployment report'));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [projectId, runId, refreshKey]);

  const body = () => {
    if (loading && !report) return <Spinner label="Loading deployment report..." />;
    if (error) return <ErrorNote message={error} />;
    if (missing || !report) {
      const waiting = deployStatus === 'PENDING' || deployStatus === 'RUNNING' || deployStatus === 'RETRYING';
      return (
        <EmptyState
          icon={<Rocket className="w-7 h-7" />}
          title={waiting ? 'The Deploy agent has not finished yet.' : 'No deployment report was produced in this run.'}
          hint={waiting ? undefined : 'The Deploy agent was skipped or failed before writing its report.'}
        />
      );
    }

    const health = report.health_checks ?? [];
    const readiness = report.readiness_checks ?? [];
    const instructions = report.instructions ?? [];
    const envVars = report.required_env_vars ?? [];

    return (
      <div className="space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800">
            <p className="text-[11px] text-slate-500">Status</p>
            <div className="mt-1 flex items-center gap-2">
              <ResultBadge value={report.status} />
              {report.environment && <span className="text-[11px] font-mono text-slate-500">{report.environment}</span>}
            </div>
          </div>
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800">
            <p className="text-[11px] text-slate-500">Deployment ready</p>
            <p className={cn('mt-1 text-sm font-semibold', report.deployment_ready ? 'text-emerald-400' : 'text-rose-400')}>
              {report.deployment_ready ? 'Yes' : 'No'}
            </p>
          </div>
          <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800">
            <p className="text-[11px] text-slate-500 flex items-center gap-1">
              <Container className="w-3 h-3" /> Docker
            </p>
            <p className={cn('mt-1 text-xs font-semibold', report.docker_available ? 'text-emerald-400' : 'text-slate-400')}>
              {report.docker_available ? 'Docker CLI available' : 'Docker CLI not found'}
            </p>
          </div>
        </div>

        {report.summary && <p className="text-xs text-slate-300 leading-relaxed break-words">{report.summary}</p>}

        {!report.container_build_verified ? (
          <div className="p-3 rounded-xl bg-slate-900/70 border border-amber-800/50 text-xs text-amber-200 flex items-start gap-2">
            <Container className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <span>
              <strong>Docker images not built on this machine.</strong> The Dockerfiles and compose file were generated and
              validated, but no container image was built or run here
              {report.docker_available ? '' : ' (Docker is not installed)'}. Health checks below ran against the app
              started as a local process.
            </span>
          </div>
        ) : (
          <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-800/50 text-xs text-emerald-200">
            Container images were built and verified on this machine.
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-blue-400" /> Readiness checks ({readiness.length})
          </h3>
          {readiness.length === 0 ? (
            <p className="text-xs text-slate-500">No readiness checks recorded.</p>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>Check</Th>
                  <Th>Status</Th>
                  <Th>Details</Th>
                </tr>
              </thead>
              <tbody>
                {readiness.map((c, i) => (
                  <tr key={`${c.name}-${i}`}>
                    <Td className="text-slate-200 min-w-[10rem]">{c.name}</Td>
                    <Td>
                      <ResultBadge value={c.status} />
                    </Td>
                    <Td className="text-slate-400 min-w-[14rem] break-words">{c.details || '--'}</Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
            <HeartPulse className="w-3.5 h-3.5 text-rose-400" /> Health checks ({health.length})
          </h3>
          {health.length === 0 ? (
            <p className="text-xs text-slate-500">No live health checks were run.</p>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>Endpoint</Th>
                  <Th>HTTP</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Response time</Th>
                </tr>
              </thead>
              <tbody>
                {health.map((h, i) => (
                  <tr key={`${h.endpoint}-${i}`}>
                    <Td className="font-mono text-slate-200 break-all">
                      {h.endpoint}
                      {h.message && <p className="text-[11px] text-slate-500 font-sans mt-0.5">{h.message}</p>}
                    </Td>
                    <Td className="font-mono text-slate-300">{h.status_code}</Td>
                    <Td>
                      <ResultBadge value={h.status} />
                    </Td>
                    <Td className="font-mono text-slate-400 text-right whitespace-nowrap">{formatDuration(h.response_time_ms)}</Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </div>

        {envVars.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-300 mb-2">Required environment variables</h3>
            <div className="flex flex-wrap gap-1.5">
              {envVars.map((v) => (
                <span key={v} className="px-2 py-0.5 rounded-md bg-slate-900 border border-slate-700 font-mono text-[11px] text-slate-300">
                  {v}
                </span>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3 className="text-xs font-semibold text-slate-300 mb-2 flex items-center gap-1.5">
            <Terminal className="w-3.5 h-3.5 text-slate-400" /> Instructions
          </h3>
          {instructions.length === 0 ? (
            <p className="text-xs text-slate-500">No instructions provided.</p>
          ) : (
            <ol className="space-y-1.5 list-decimal pl-5 text-xs text-slate-300 marker:text-slate-500">
              {instructions.map((line, i) => (
                <li key={i} className="font-mono break-words whitespace-pre-wrap">
                  {line}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    );
  };

  return (
    <Panel title="Deployment report" icon={<Rocket className="w-4 h-4 text-sky-400" />} actions={loading && report ? <Spinner /> : undefined}>
      {body()}
    </Panel>
  );
};
