import React from 'react';
import { X, Copy, Check, FileCode, GitFork, Calendar } from 'lucide-react';
import { ArtifactModel } from '../types';

interface ArtifactModalProps {
  artifact: ArtifactModel | null;
  onClose: () => void;
}

export const ArtifactModal: React.FC<ArtifactModalProps> = ({ artifact, onClose }) => {
  const [copied, setCopied] = React.useState(false);

  if (!artifact) return null;

  const jsonString = JSON.stringify(artifact.content, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="glass-panel rounded-2xl border border-slate-700/80 w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <FileCode className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-white">
                  Artifact: {artifact.artifact_type}
                </h3>
                <span className="text-xs font-mono px-2 py-0.5 rounded-md bg-blue-950 text-blue-400 border border-blue-800">
                  v{artifact.version}
                </span>
                <span className="text-xs font-mono px-2 py-0.5 rounded-md bg-slate-800 text-slate-300">
                  Agent: {artifact.agent_name}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">ID: {artifact.artifact_id}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors border border-slate-700"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 text-slate-400" />}
              <span>{copied ? 'Copied!' : 'Copy Payload'}</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Subheader info */}
        <div className="px-6 py-3 bg-slate-950/60 border-b border-slate-800/80 flex flex-wrap items-center justify-between text-xs font-mono text-slate-400 gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-3.5 h-3.5 text-slate-500" />
            <span>Created: {artifact.created_at}</span>
          </div>

          <div className="flex items-center gap-2">
            <GitFork className="w-3.5 h-3.5 text-indigo-400" />
            <span>Lineage Inputs: {artifact.input_artifacts.length > 0 ? artifact.input_artifacts.join(', ') : 'None (Root Artifact)'}</span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 bg-slate-950/90 font-mono text-xs text-emerald-400">
          <pre className="whitespace-pre-wrap leading-relaxed">{jsonString}</pre>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-900/60 flex justify-between items-center text-xs text-slate-400">
          <span>Project ID: {artifact.project_id}</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
