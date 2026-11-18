import { FlaskConical, Loader2, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { btnPrimary } from "@/components/brand";
import { AGENTS } from "@/lib/agents";
import type { StageName } from "@/lib/api/types";
import { Alert, fieldClass } from "./ui";

export type PromptSubmission = {
  prompt: string;
  projectName?: string;
  simulateFailure?: StageName;
};

/** Prompt card modelled on the landing hero's PROMPT panel. Used for new projects and iterations. */
export function PromptForm({
  mode,
  faultInjection,
  onSubmit,
  initialPrompt = "",
}: {
  mode: "project" | "iteration";
  faultInjection: boolean;
  onSubmit: (submission: PromptSubmission) => Promise<void>;
  initialPrompt?: string;
}) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [projectName, setProjectName] = useState("");
  const [testMode, setTestMode] = useState(false);
  const [failStage, setFailStage] = useState<StageName>("qa");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (prompt.trim().length < 15) {
      setError(
        "Describe the application in a sentence or two — who uses it and what it should do.",
      );
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        prompt: prompt.trim(),
        ...(mode === "project" && projectName.trim() ? { projectName: projectName.trim() } : {}),
        ...(testMode ? { simulateFailure: failStage } : {}),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the build.");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="rounded-xl border bg-background p-4">
      <label htmlFor="forge-prompt" className="text-xs font-semibold text-muted-foreground">
        {mode === "project" ? "PROMPT" : "UPDATED PROMPT"}
      </label>
      <textarea
        id="forge-prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={mode === "project" ? 5 : 4}
        maxLength={4000}
        placeholder="Build a booking app for my yoga studio with class schedules, member logins and an admin dashboard."
        className={`${fieldClass} mt-2 resize-y`}
      />
      {mode === "iteration" && (
        <p className="mt-2 text-xs text-muted-foreground">
          The agents regenerate the whole application from this prompt. The current version stays
          active until the new build passes QA.
        </p>
      )}
      {mode === "project" && (
        <label className="mt-4 block text-sm font-medium">
          Project name <span className="font-normal text-muted-foreground">(optional)</span>
          <input
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            maxLength={80}
            placeholder="Defaults to the start of your prompt"
            className={`${fieldClass} mt-1.5`}
          />
        </label>
      )}
      {faultInjection && (
        <div className="mt-4 rounded-lg border border-dashed px-3 py-2.5 text-sm">
          <label className="flex items-center gap-2 font-medium">
            <input
              type="checkbox"
              checked={testMode}
              onChange={(e) => setTestMode(e.target.checked)}
              className="size-4 accent-[var(--primary)]"
            />
            <FlaskConical className="size-4 text-primary" /> Test mode: simulate an agent failure
          </label>
          {testMode && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              Fail the
              <select
                value={failStage}
                onChange={(e) => setFailStage(e.target.value as StageName)}
                className="rounded-lg border bg-background px-2 py-1 text-xs text-foreground"
              >
                {AGENTS.map((a) => (
                  <option key={a.stage} value={a.stage}>
                    {a.name}
                  </option>
                ))}
              </select>
              to see retries, skipped agents and recovery. The run is labelled as a test.
            </div>
          )}
        </div>
      )}
      {error && (
        <div className="mt-4">
          <Alert>{error}</Alert>
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <button type="submit" disabled={busy} className={btnPrimary}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {mode === "project" ? "Generate" : "Start iteration"}
        </button>
      </div>
    </form>
  );
}
