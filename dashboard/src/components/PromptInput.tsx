import React, { useState } from 'react';
import { FlaskConical, Loader2, Play, Sparkles } from 'lucide-react';
import type { StageName } from '../types';
import { STAGE_ORDER } from '../types';
import { STAGE_META } from '../lib/stages';
import { ErrorNote } from './ui';

export interface PromptSubmission {
  prompt: string;
  projectName?: string;
  simulateFailure?: StageName;
}

interface PromptInputProps {
  mode: 'project' | 'iteration';
  faultInjectionEnabled: boolean;
  onSubmit: (submission: PromptSubmission) => Promise<void>;
  /** Called when the user cancels (iteration modal only). */
  onCancel?: () => void;
}

const PRESETS = [
  {
    label: 'Task manager',
    prompt:
      'Build a task management app where users can register, create tasks with priority and due date, organise them into categories and filter by status.',
  },
  {
    label: 'Developer blog',
    prompt:
      'Build a developer blog platform with articles, tags and comments. Authors can write and edit their own posts; readers can comment after logging in.',
  },
  {
    label: 'Inventory tracker',
    prompt:
      'Build an inventory tracker for a small shop with products, suppliers and stock movements, low-stock alerts and an admin role that manages suppliers.',
  },
];

const ITERATION_EXAMPLES = [
  'Build a task manager with tasks, categories, due dates, priorities, comments and an admin dashboard.',
];

export const PromptInput: React.FC<PromptInputProps> = ({ mode, faultInjectionEnabled, onSubmit, onCancel }) => {
  const [prompt, setPrompt] = useState('');
  const [projectName, setProjectName] = useState('');
  const [simulate, setSimulate] = useState<StageName | ''>('');
  const [testMode, setTestMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isProject = mode === 'project';

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (submitting) return;
    if (!prompt.trim()) {
      setError(isProject ? 'Describe the application you want FORGE AI to build.' : 'Describe the updated application.');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({
        prompt: prompt.trim(),
        projectName: isProject && projectName.trim() ? projectName.trim() : undefined,
        simulateFailure: faultInjectionEnabled && testMode && simulate ? simulate : undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor={`prompt-${mode}`} className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-400" />
          {isProject ? 'Describe your app idea' : 'Describe the updated application (the app is regenerated from this prompt)'}
        </label>
        <span className="text-[11px] font-mono text-slate-500">{prompt.length} chars</span>
      </div>

      <textarea
        id={`prompt-${mode}`}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void handleSubmit(e);
        }}
        rows={isProject ? 5 : 4}
        placeholder={
          isProject
            ? 'e.g. Build a recipe sharing app where users can post recipes with ingredients and steps, rate recipes and save favourites.'
            : 'e.g. ' + ITERATION_EXAMPLES[0]
        }
        className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl p-3.5 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm resize-y transition-all"
      />

      {isProject && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400 mr-1">Examples:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => setPrompt(preset.prompt)}
              className="text-xs font-medium px-2.5 py-1 rounded-lg bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700/50 transition-colors"
            >
              {preset.label}
            </button>
          ))}
        </div>
      )}

      {isProject && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <label htmlFor="project-name" className="text-xs font-mono text-slate-400 shrink-0">
            Project name (optional)
          </label>
          <input
            id="project-name"
            type="text"
            maxLength={80}
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="Defaults to the start of your prompt"
            className="w-full sm:max-w-sm bg-slate-950 border border-slate-700/60 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>
      )}

      {faultInjectionEnabled && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 p-2.5 rounded-xl bg-slate-900/50 border border-slate-800">
          <label className="inline-flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={testMode}
              onChange={(e) => setTestMode(e.target.checked)}
              className="w-3.5 h-3.5 rounded bg-slate-900 border-slate-700 accent-amber-500"
            />
            <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
            Test mode: simulate failure in agent
          </label>
          <select
            value={simulate}
            disabled={!testMode}
            onChange={(e) => setSimulate(e.target.value as StageName | '')}
            className="bg-slate-950 border border-slate-700/70 rounded-lg px-2 py-1 text-xs text-slate-200 disabled:opacity-40 focus:outline-none focus:ring-1 focus:ring-amber-500"
            aria-label="Agent to fail"
          >
            <option value="">Select agent...</option>
            {STAGE_ORDER.map((s) => (
              <option key={s} value={s}>
                {STAGE_META[s].index}. {STAGE_META[s].title}
              </option>
            ))}
          </select>
          {testMode && simulate && (
            <span className="text-amber-300/80">
              The {STAGE_META[simulate].title} will fail on purpose; the previous stable version stays active.
            </span>
          )}
        </div>
      )}

      {error && <ErrorNote message={error} title={isProject ? 'Could not start generation' : 'Could not start iteration'} />}

      <div className="flex flex-wrap items-center justify-end gap-3">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-sm shadow-lg shadow-blue-600/25 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
          <span>{submitting ? 'Starting...' : isProject ? 'Generate' : 'Start iteration'}</span>
        </button>
      </div>
    </form>
  );
};
