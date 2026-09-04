import React from 'react';
import {
  FileText,
  Layout,
  Server,
  Database,
  Lock,
  TestTube,
  Rocket,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  RotateCcw,
  Eye,
} from 'lucide-react';
import { AgentSummaryEntry, StageName } from '../types';

interface AgentCardProps {
  stage: StageName;
  title: string;
  description: string;
  summary?: AgentSummaryEntry;
  onViewArtifact: (artifactId: string) => void;
  onOpenRollback: (stage: StageName) => void;
}

const STAGE_ICONS: Record<StageName, React.ReactNode> = {
  pm: <FileText className="w-5 h-5 text-blue-400" />,
  ui: <Layout className="w-5 h-5 text-indigo-400" />,
  backend: <Server className="w-5 h-5 text-purple-400" />,
  db: <Database className="w-5 h-5 text-amber-400" />,
  auth: <Lock className="w-5 h-5 text-emerald-400" />,
  qa: <TestTube className="w-5 h-5 text-pink-400" />,
  deploy: <Rocket className="w-5 h-5 text-sky-400" />,
};

export const AgentCard: React.FC<AgentCardProps> = ({
  stage,
  title,
  description,
  summary,
  onViewArtifact,
  onOpenRollback,
}) => {
  const status = summary?.status || 'PENDING';
  const duration = summary?.duration_ms;
  const artifactId = summary?.artifact_id;
  const error = summary?.error;

  const durationStr = duration != null ? (duration > 1000 ? `${(duration / 1000).toFixed(2)}s` : `${duration}ms`) : '--';

  const renderStatusBadge = () => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 border border-emerald-800/80 text-emerald-400">
            <CheckCircle2 className="w-3.5 h-3.5" />
            COMPLETED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-950/80 border border-rose-800/80 text-rose-400">
            <XCircle className="w-3.5 h-3.5" />
            FAILED
          </span>
        );
      case 'RUNNING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-950/80 border border-blue-800/80 text-blue-400 pulse-subtle">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            RUNNING
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-900 border border-slate-800 text-slate-500">
            <Clock className="w-3.5 h-3.5" />
            PENDING
          </span>
        );
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-5 border border-slate-800/80 hover:border-slate-700/80 transition-all flex flex-col justify-between shadow-lg group">
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
              {STAGE_ICONS[stage]}
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 group-hover:text-blue-400 transition-colors">
                {title}
              </h3>
              <p className="text-xs text-slate-400">{description}</p>
            </div>
          </div>
          {renderStatusBadge()}
        </div>

        {error && (
          <div className="my-3 p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-300 text-xs font-mono break-all">
            <p className="font-semibold mb-1">Execution Error:</p>
            <span>{error}</span>
          </div>
        )}
      </div>

      <div className="pt-4 border-t border-slate-800/60 mt-4 space-y-3">
        <div className="flex items-center justify-between text-xs font-mono text-slate-400">
          <span>Duration:</span>
          <span className="text-slate-200 font-semibold">{durationStr}</span>
        </div>

        <div className="flex items-center justify-between gap-2">
          {artifactId ? (
            <button
              onClick={() => onViewArtifact(artifactId)}
              className="flex-1 px-3 py-1.5 rounded-lg bg-blue-950/50 hover:bg-blue-900/60 border border-blue-800/60 text-blue-300 text-xs font-mono flex items-center justify-center gap-1.5 transition-colors truncate"
              title={`View Artifact: ${artifactId}`}
            >
              <Eye className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <span className="truncate">Artifact: {artifactId.slice(0, 8)}...</span>
            </button>
          ) : (
            <span className="text-xs text-slate-600 font-mono italic">No artifact yet</span>
          )}

          <button
            onClick={() => onOpenRollback(stage)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1 transition-colors shrink-0"
            title="Rollback Stage"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
            <span>Rollback</span>
          </button>
        </div>
      </div>
    </div>
  );
};
