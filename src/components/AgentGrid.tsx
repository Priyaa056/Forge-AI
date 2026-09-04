import React from 'react';
import { AgentCard } from './AgentCard';
import { PipelineStatusSummary, StageName } from '../types';

interface AgentGridProps {
  summary: PipelineStatusSummary | null;
  onViewArtifact: (artifactId: string) => void;
  onOpenRollback: (stage: StageName) => void;
}

const STAGES: { stage: StageName; title: string; description: string }[] = [
  {
    stage: 'pm',
    title: '1. PM Agent',
    description: 'Requirements, features & Tech Stack',
  },
  {
    stage: 'ui',
    title: '2. UI Agent',
    description: 'Component specs, pages & design system',
  },
  {
    stage: 'backend',
    title: '3. Backend Agent',
    description: 'REST endpoints & service Layer specs',
  },
  {
    stage: 'db',
    title: '4. DB Agent',
    description: 'SQLAlchemy models & Alembic metadata',
  },
  {
    stage: 'auth',
    title: '5. Auth Agent',
    description: 'JWT strategy, RBAC roles & hashing specs',
  },
  {
    stage: 'qa',
    title: '6. QA Agent',
    description: 'Integration test suites & security scan',
  },
  {
    stage: 'deploy',
    title: '7. Deploy Agent',
    description: 'Docker containerization & health checks',
  },
];

export const AgentGrid: React.FC<AgentGridProps> = ({
  summary,
  onViewArtifact,
  onOpenRollback,
}) => {
  return (
    <div className="mb-10">
      <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span>7-Agent Pipeline Stages</span>
        <span className="text-xs text-slate-400 font-mono font-normal">
          (Sequential execution chain)
        </span>
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
        {STAGES.map((s) => (
          <AgentCard
            key={s.stage}
            stage={s.stage}
            title={s.title}
            description={s.description}
            summary={summary?.agents?.[s.stage]}
            onViewArtifact={onViewArtifact}
            onOpenRollback={onOpenRollback}
          />
        ))}
      </div>
    </div>
  );
};
