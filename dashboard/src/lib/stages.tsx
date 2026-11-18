import React from 'react';
import { Database, FileText, Layout, Lock, Rocket, Server, TestTube } from 'lucide-react';
import type { StageName } from '../types';

export interface StageMeta {
  stage: StageName;
  index: number;
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Tailwind text color for the stage icon / accents. */
  accent: string;
  /** Tailwind classes for the small agent badge (files, feed). */
  badge: string;
}

export const STAGE_META: Record<StageName, StageMeta> = {
  pm: {
    stage: 'pm',
    index: 1,
    title: 'PM Agent',
    description: 'Requirements, entities & features',
    icon: FileText,
    accent: 'text-blue-400',
    badge: 'bg-blue-950/70 text-blue-300 border-blue-800/70',
  },
  ui: {
    stage: 'ui',
    index: 2,
    title: 'UI Agent',
    description: 'React pages, components & design',
    icon: Layout,
    accent: 'text-indigo-400',
    badge: 'bg-indigo-950/70 text-indigo-300 border-indigo-800/70',
  },
  backend: {
    stage: 'backend',
    index: 3,
    title: 'Backend Agent',
    description: 'REST API routes & services',
    icon: Server,
    accent: 'text-purple-400',
    badge: 'bg-purple-950/70 text-purple-300 border-purple-800/70',
  },
  db: {
    stage: 'db',
    index: 4,
    title: 'DB Agent',
    description: 'Data models & persistence',
    icon: Database,
    accent: 'text-amber-400',
    badge: 'bg-amber-950/70 text-amber-300 border-amber-800/70',
  },
  auth: {
    stage: 'auth',
    index: 5,
    title: 'Auth Agent',
    description: 'Login, JWT & role-based access',
    icon: Lock,
    accent: 'text-emerald-400',
    badge: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/70',
  },
  qa: {
    stage: 'qa',
    index: 6,
    title: 'QA Agent',
    description: 'Executes tests & checks the app',
    icon: TestTube,
    accent: 'text-pink-400',
    badge: 'bg-pink-950/70 text-pink-300 border-pink-800/70',
  },
  deploy: {
    stage: 'deploy',
    index: 7,
    title: 'Deploy Agent',
    description: 'Readiness, health checks & Docker',
    icon: Rocket,
    accent: 'text-sky-400',
    badge: 'bg-sky-950/70 text-sky-300 border-sky-800/70',
  },
};

/** Map agent identifiers such as "backend", "BackendAgent" or "database" to a stage name. */
export function toStage(agent: string | null | undefined): StageName | null {
  if (!agent) return null;
  const key = agent.toLowerCase().replace(/[_\s-]*agent$/, '');
  if (key in STAGE_META) return key as StageName;
  if (key === 'database') return 'db';
  if (key === 'frontend') return 'ui';
  if (key === 'deployment') return 'deploy';
  return null;
}

export function agentBadgeClass(agent: string | null | undefined): string {
  const stage = toStage(agent);
  if (stage) return STAGE_META[stage].badge;
  return 'bg-slate-800/80 text-slate-300 border-slate-700/80';
}

export function isStageName(value: string | null | undefined): value is StageName {
  return !!value && value in STAGE_META;
}
