import React from 'react';
import { ArrowRight } from 'lucide-react';
import { AgentCard } from './AgentCard';
import type { AgentStatus, RunSummary, StageName } from '../types';
import { STAGE_ORDER } from '../types';

interface AgentGridProps {
  summary: RunSummary | null;
  onOpenArtifact: (artifactId: string) => void;
  onOpenVersions: (stage: StageName) => void;
}

export const AgentGrid: React.FC<AgentGridProps> = ({ summary, onOpenArtifact, onOpenVersions }) => {
  return (
    <section className="min-w-0">
      <h2 className="text-sm font-semibold text-white mb-3 flex flex-wrap items-center gap-2">
        <span>Agent pipeline</span>
        <span className="text-[11px] text-slate-500 font-mono font-normal flex items-center gap-1 flex-wrap">
          {STAGE_ORDER.map((s, i) => (
            <React.Fragment key={s}>
              {i > 0 && <ArrowRight className="w-3 h-3" />}
              {s}
            </React.Fragment>
          ))}
        </span>
        <span className="text-[11px] text-slate-500 font-normal">· click a card to open its artifact</span>
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {STAGE_ORDER.map((stage) => {
          const entry = summary?.agents?.[stage];
          const status: AgentStatus = entry?.status ?? summary?.agent_statuses?.[stage] ?? 'PENDING';
          const artifactId = entry?.artifact_id ?? summary?.artifact_ids?.[stage] ?? null;
          return (
            <AgentCard
              key={stage}
              stage={stage}
              entry={entry}
              status={status}
              artifactId={artifactId}
              simulated={summary?.simulated_failure === stage}
              onOpenArtifact={onOpenArtifact}
              onOpenVersions={onOpenVersions}
            />
          );
        })}
      </div>
    </section>
  );
};
