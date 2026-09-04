import React, { useState } from 'react';
import { Play, Sparkles, FolderGit2, Loader2 } from 'lucide-react';

interface PromptInputProps {
  onStartPipeline: (prompt: string, projectId?: string) => Promise<void>;
  isLoading: boolean;
}

const PRESETS = [
  {
    label: 'Task Management App',
    prompt: 'Build a TaskFlow management app with user registration, task CRUD, priority tags, and category filtering.',
  },
  {
    label: 'Developer Blog',
    prompt: 'Build a DevBlog publishing platform with articles, comments, markdown tags, and author profiles.',
  },
  {
    label: 'E-commerce Platform',
    prompt: 'Build a StoreFront online e-commerce platform with product catalog, shopping cart, orders, and user auth.',
  },
];

export const PromptInput: React.FC<PromptInputProps> = ({ onStartPipeline, isLoading }) => {
  const [prompt, setPrompt] = useState(PRESETS[0].prompt);
  const [projectId, setProjectId] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isLoading) return;
    onStartPipeline(prompt.trim(), projectId.trim() || undefined);
  };

  return (
    <div className="glass-panel rounded-2xl p-6 mb-8 border border-slate-800 shadow-xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-blue-400" />
            Application Prompt Specification
          </label>
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-slate-400 hover:text-slate-200 transition-colors flex items-center gap-1 font-mono"
          >
            <FolderGit2 className="w-3.5 h-3.5" />
            {showAdvanced ? 'Hide Options' : 'Custom Project ID'}
          </button>
        </div>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder="Describe your application idea..."
          className="w-full bg-slate-900/90 border border-slate-700/80 rounded-xl p-4 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm resize-none transition-all"
        />

        {showAdvanced && (
          <div className="p-3 bg-slate-900/60 rounded-xl border border-slate-800 flex items-center gap-3">
            <label className="text-xs font-mono text-slate-400 shrink-0">Project ID:</label>
            <input
              type="text"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="e.g. proj_taskflow_01"
              className="w-full bg-slate-950 border border-slate-700/60 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 mr-1">Presets:</span>
            {PRESETS.map((preset, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setPrompt(preset.prompt)}
                className="text-xs font-medium px-2.5 py-1 rounded-lg bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700/50 transition-colors"
              >
                {preset.label}
              </button>
            ))}
          </div>

          <button
            type="submit"
            disabled={isLoading || !prompt.trim()}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium text-sm shadow-lg shadow-blue-600/25 flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Running Pipeline...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Start Pipeline Execution</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
