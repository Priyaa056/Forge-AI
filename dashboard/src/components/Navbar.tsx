import React from 'react';
import { Box, Brain, Container, Cpu, Info, Menu, Wrench } from 'lucide-react';
import type { SystemInfo } from '../types';
import { cn } from '../lib/utils';
import { Tooltip } from './ui';

interface NavbarProps {
  system: SystemInfo | null;
  apiOnline: boolean | null;
  onToggleSidebar: () => void;
}

const Chip: React.FC<{ ok: boolean | null; icon: React.ReactNode; label: string; title?: string }> = ({
  ok,
  icon,
  label,
  title,
}) => (
  <span
    title={title}
    className={cn(
      'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-mono whitespace-nowrap',
      ok === null && 'bg-slate-900 border-slate-800 text-slate-500',
      ok === true && 'bg-emerald-950/50 border-emerald-800/60 text-emerald-300',
      ok === false && 'bg-slate-900 border-slate-700/80 text-slate-400',
    )}
  >
    {icon}
    {label}
  </span>
);

export const Navbar: React.FC<NavbarProps> = ({ system, apiOnline, onToggleSidebar }) => {
  const llm = system?.llm;
  return (
    <header className="glass-panel relative shrink-0 z-20 border-b border-slate-800 px-3 sm:px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onToggleSidebar}
            className="lg:hidden p-2 rounded-lg text-slate-300 hover:bg-slate-800 border border-slate-800"
            aria-label="Toggle project list"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="p-2 bg-blue-600/20 border border-blue-500/30 rounded-xl text-blue-400 shrink-0">
            <Cpu className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-base sm:text-lg font-bold tracking-tight text-white flex items-center gap-2">
              FORGE AI
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-900/60 border border-blue-700/60 text-blue-300 uppercase tracking-wide">
                Platform dashboard
              </span>
            </h1>
            <p className="text-[11px] text-slate-400 truncate hidden sm:block">
              Seven agents build your app here; the generated app opens separately via Preview.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          <Chip
            ok={apiOnline}
            icon={
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  apiOnline === null ? 'bg-slate-500' : apiOnline ? 'bg-emerald-400 pulse-subtle' : 'bg-rose-500',
                )}
              />
            }
            label={apiOnline === null ? 'API: connecting' : apiOnline ? 'API online' : 'API offline'}
            title="FORGE AI platform API (http://127.0.0.1:8000)"
          />

          {llm &&
            (llm.mode === 'llm' ? (
              <Chip
                ok={true}
                icon={<Brain className="w-3.5 h-3.5" />}
                label={`LLM mode${llm.provider ? ` · ${llm.provider}` : ''}`}
                title={llm.detail}
              />
            ) : (
              <Tooltip text={llm.detail}>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-mono whitespace-nowrap bg-amber-950/50 border-amber-800/60 text-amber-300 cursor-help">
                  <Brain className="w-3.5 h-3.5" />
                  Rule-based mode
                  <Info className="w-3 h-3 opacity-70" />
                </span>
              </Tooltip>
            ))}

          {system && (
            <>
              <Chip
                ok={system.frontend_toolchain_ready}
                icon={<Wrench className="w-3.5 h-3.5" />}
                label={system.frontend_toolchain_ready ? 'Frontend toolchain ready' : 'Frontend toolchain not ready'}
                title={
                  system.frontend_toolchain_ready
                    ? 'Node toolchain is installed; generated React frontends can be built.'
                    : system.node_available
                      ? 'Node is available but the frontend toolchain is not installed yet (installed on first build).'
                      : 'Node.js was not found; generated frontends cannot be built on this machine.'
                }
              />
              <Chip
                ok={system.node_available}
                icon={<Box className="w-3.5 h-3.5" />}
                label={system.node_available ? 'Node' : 'No Node'}
                title={system.node_available ? 'Node.js found' : 'Node.js not found on PATH'}
              />
              <Chip
                ok={system.docker_available}
                icon={<Container className="w-3.5 h-3.5" />}
                label={system.docker_available ? 'Docker' : 'No Docker'}
                title={system.docker_available ? 'Docker CLI found' : 'Docker CLI not found; images are not built on this machine'}
              />
            </>
          )}
        </div>
      </div>
    </header>
  );
};
