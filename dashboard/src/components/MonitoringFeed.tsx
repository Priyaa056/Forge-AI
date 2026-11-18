import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, AlertTriangle, ArrowDownToLine, CheckCircle2, Info, Layers, RotateCcw, Terminal } from 'lucide-react';
import type { ExecutionEvent } from '../types';
import { STAGE_ORDER } from '../types';
import { agentBadgeClass } from '../lib/stages';
import { cn, formatDuration, formatTime } from '../lib/utils';
import { EmptyState, Panel, Spinner } from './ui';

interface MonitoringFeedProps {
  events: ExecutionEvent[];
  live: boolean;
  loading: boolean;
}

type LevelFilter = 'all' | 'issues';
type KindFilter = 'all' | 'logs' | 'lifecycle';

function eventTone(evt: ExecutionEvent): string {
  const t = evt.event_type;
  if (evt.level === 'error' || t.endsWith('FAILED')) return 'text-rose-300';
  if (evt.level === 'warning' || t === 'AGENT_RETRYING') return 'text-amber-300';
  if (t.endsWith('COMPLETED') || t === 'VERSION_PROMOTED') return 'text-emerald-300';
  if (t === 'AGENT_SKIPPED') return 'text-slate-500';
  if (t.endsWith('STARTED')) return 'text-blue-300';
  return 'text-slate-300';
}

function eventIcon(evt: ExecutionEvent) {
  const t = evt.event_type;
  if (t === 'AGENT_LOG') return <Terminal className="w-3.5 h-3.5 text-slate-500 shrink-0" />;
  if (t.endsWith('FAILED')) return <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />;
  if (t.startsWith('ROLLBACK')) return <RotateCcw className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
  if (t.endsWith('COMPLETED') || t === 'VERSION_PROMOTED') return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
  if (t.startsWith('ARTIFACT')) return <Layers className="w-3.5 h-3.5 text-indigo-400 shrink-0" />;
  return <Info className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
}

function isIssue(evt: ExecutionEvent): boolean {
  return (
    evt.level === 'warning' ||
    evt.level === 'error' ||
    evt.event_type.endsWith('FAILED') ||
    evt.event_type === 'AGENT_RETRYING'
  );
}

export const EventLine: React.FC<{ evt: ExecutionEvent; showRun?: boolean }> = ({ evt, showRun }) => {
  const isLog = evt.event_type === 'AGENT_LOG';
  const text = [evt.message, evt.error_message && evt.error_message !== evt.message ? evt.error_message : null]
    .filter(Boolean)
    .join(' — ');
  return (
    <div
      className={cn(
        'px-2.5 py-1.5 rounded-lg flex items-start gap-2 text-[11px] sm:text-xs font-mono leading-relaxed',
        isLog ? 'hover:bg-slate-900/60' : 'bg-slate-900/70 border border-slate-800/80',
        evt.level === 'error' && isLog && 'bg-rose-950/30',
        evt.level === 'warning' && isLog && 'bg-amber-950/20',
      )}
    >
      <span className="text-slate-500 shrink-0 tabular-nums">{formatTime(evt.timestamp)}</span>
      <span className="mt-0.5">{eventIcon(evt)}</span>
      <div className="min-w-0 flex-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        {evt.agent_name && (
          <span className={cn('px-1.5 rounded border text-[10px] font-semibold shrink-0', agentBadgeClass(evt.agent_name))}>
            {evt.agent_name}
          </span>
        )}
        {!isLog && <span className={cn('font-semibold text-[10px] shrink-0', eventTone(evt))}>{evt.event_type}</span>}
        {showRun && evt.run_id && <span className="text-[10px] text-slate-500 shrink-0">{evt.run_id}</span>}
        <span className={cn('break-words min-w-0', isLog ? eventTone(evt) : 'text-slate-300')}>
          {text || (isLog ? '' : evt.status ?? '')}
        </span>
        {evt.duration_ms != null && !isLog && (
          <span className="text-slate-500 text-[10px] shrink-0">{formatDuration(evt.duration_ms)}</span>
        )}
      </div>
    </div>
  );
};

export const MonitoringFeed: React.FC<MonitoringFeedProps> = ({ events, live, loading }) => {
  const [agent, setAgent] = useState<string>('all');
  const [level, setLevel] = useState<LevelFilter>('all');
  const [kind, setKind] = useState<KindFilter>('all');
  const [follow, setFollow] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const agents = useMemo(() => {
    const extra = new Set<string>();
    events.forEach((e) => {
      if (e.agent_name && !(STAGE_ORDER as string[]).includes(e.agent_name)) extra.add(e.agent_name);
    });
    return [...STAGE_ORDER, ...Array.from(extra).sort()];
  }, [events]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    events.forEach((e) => {
      if (e.agent_name) c[e.agent_name] = (c[e.agent_name] ?? 0) + 1;
    });
    return c;
  }, [events]);

  const filtered = useMemo(
    () =>
      events.filter(
        (e) =>
          (agent === 'all' || e.agent_name === agent) &&
          (level === 'all' || isIssue(e)) &&
          (kind === 'all' || (kind === 'logs' ? e.event_type === 'AGENT_LOG' : e.event_type !== 'AGENT_LOG')),
      ),
    [events, agent, level, kind],
  );

  useEffect(() => {
    if (follow && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filtered.length, follow]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom !== follow) setFollow(atBottom);
  };

  const selectCls =
    'bg-slate-950 border border-slate-700/70 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500';

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          Live monitoring feed
          <span className="text-[11px] font-mono text-slate-500 font-normal">
            {filtered.length}/{events.length} events
          </span>
        </span>
      }
      icon={<Activity className="w-4 h-4 text-blue-400" />}
      actions={
        <>
          {live ? (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-emerald-300">
              <span className="w-2 h-2 rounded-full bg-emerald-400 pulse-subtle" />
              live · polling every 1 s
            </span>
          ) : (
            <span className="text-[11px] font-mono text-slate-500">run finished · polling stopped</span>
          )}
        </>
      }
      bodyClassName="p-0"
    >
      <div className="px-4 sm:px-5 py-2.5 border-b border-slate-800/80 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1">
          {['all', ...agents].map((a) => (
            <button
              key={a}
              onClick={() => setAgent(a)}
              className={cn(
                'px-2 py-0.5 rounded-md border text-[11px] font-mono transition-colors',
                agent === a
                  ? a === 'all'
                    ? 'bg-blue-600/30 border-blue-500/60 text-blue-200'
                    : cn(agentBadgeClass(a), 'ring-1 ring-white/30')
                  : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200',
              )}
            >
              {a}
              {a !== 'all' && counts[a] ? <span className="ml-1 opacity-60">{counts[a]}</span> : null}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <select value={kind} onChange={(e) => setKind(e.target.value as KindFilter)} className={selectCls} aria-label="Event kind">
            <option value="all">Logs + lifecycle</option>
            <option value="logs">Agent logs only</option>
            <option value="lifecycle">Lifecycle only</option>
          </select>
          <select value={level} onChange={(e) => setLevel(e.target.value as LevelFilter)} className={selectCls} aria-label="Level">
            <option value="all">All levels</option>
            <option value="issues">Warnings & errors</option>
          </select>
        </div>
      </div>

      <div className="relative">
        <div ref={scrollRef} onScroll={onScroll} className="h-[420px] overflow-y-auto px-2 sm:px-3 py-2 space-y-1">
          {loading && events.length === 0 ? (
            <div className="p-6 flex justify-center">
              <Spinner label="Loading events..." />
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              className="m-2"
              icon={<Activity className="w-7 h-7" />}
              title={events.length === 0 ? 'No events recorded for this run yet.' : 'No events match the current filters.'}
            />
          ) : (
            filtered.map((evt) => <EventLine key={evt.event_id} evt={evt} />)
          )}
        </div>
        {!follow && filtered.length > 0 && (
          <button
            onClick={() => setFollow(true)}
            className="absolute bottom-3 right-4 px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-medium shadow-lg flex items-center gap-1"
          >
            <ArrowDownToLine className="w-3.5 h-3.5" />
            Follow latest
          </button>
        )}
      </div>
    </Panel>
  );
};
