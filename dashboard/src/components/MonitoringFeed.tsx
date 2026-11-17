import React from 'react';
import { Activity, RefreshCw, AlertTriangle, CheckCircle2, Info, Layers } from 'lucide-react';
import { ExecutionEventModel } from '../types';

interface MonitoringFeedProps {
  events: ExecutionEventModel[];
  onRefresh: () => void;
  isLoading: boolean;
}

export const MonitoringFeed: React.FC<MonitoringFeedProps> = ({ events, onRefresh, isLoading }) => {
  const getEventBadge = (type: string) => {
    if (type.includes('COMPLETED')) {
      return 'bg-emerald-950/80 text-emerald-400 border-emerald-800';
    }
    if (type.includes('FAILED')) {
      return 'bg-rose-950/80 text-rose-400 border-rose-800';
    }
    if (type.includes('STARTED')) {
      return 'bg-blue-950/80 text-blue-400 border-blue-800';
    }
    if (type.includes('ROLLBACK')) {
      return 'bg-amber-950/80 text-amber-400 border-amber-800';
    }
    return 'bg-slate-900 text-slate-400 border-slate-800';
  };

  const getEventIcon = (type: string) => {
    if (type.includes('COMPLETED')) return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
    if (type.includes('FAILED')) return <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />;
    if (type.includes('ARTIFACT')) return <Layers className="w-3.5 h-3.5 text-indigo-400 shrink-0" />;
    return <Info className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
  };

  return (
    <div className="glass-panel rounded-2xl p-6 border border-slate-800">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Monitoring Execution Feed</h2>
          <span className="text-xs font-mono text-slate-400 font-normal">({events.length} events recorded)</span>
        </div>

        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh Feed</span>
        </button>
      </div>

      {events.length === 0 ? (
        <div className="p-8 text-center border border-dashed border-slate-800 rounded-xl">
          <Activity className="w-8 h-8 text-slate-600 mx-auto mb-2" />
          <p className="text-sm text-slate-400">No monitoring execution events recorded yet.</p>
          <p className="text-xs text-slate-600 mt-1">Start a pipeline run to observe events.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {events.map((evt) => (
            <div
              key={evt.event_id}
              className="p-3 rounded-xl bg-slate-900/70 border border-slate-800/80 hover:border-slate-700/80 transition-colors flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs font-mono"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                {getEventIcon(evt.event_type)}
                <span className={`px-2 py-0.5 rounded-md font-semibold border text-[11px] ${getEventBadge(evt.event_type)}`}>
                  {evt.event_type}
                </span>
                {evt.agent_name && (
                  <span className="text-slate-300 font-semibold bg-slate-800 px-2 py-0.5 rounded">
                    [{evt.agent_name}]
                  </span>
                )}
                <span className="text-slate-300 truncate">{evt.message || evt.error_message}</span>
              </div>

              <div className="flex items-center gap-3 text-slate-500 text-[11px] shrink-0 self-end sm:self-auto">
                {evt.duration_ms != null && (
                  <span className="text-slate-400">{evt.duration_ms}ms</span>
                )}
                <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
