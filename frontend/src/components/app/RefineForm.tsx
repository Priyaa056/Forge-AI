// "Refine app": describe a change to the live version; the agents update only what it affects.
import { Loader2, Wand2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { btnPrimary } from "@/components/brand";
import { refineExamples } from "@/lib/refine";
import { cn } from "@/lib/utils";
import { Alert, fieldClass } from "./ui";

export function RefineForm({
  liveVersion,
  moduleLabels = [],
  onSubmit,
  compact = false,
  disabled = false,
  initialText = "",
  submitLabel = "Refine app",
  busyLabel = "Starting…",
  hint,
}: {
  liveVersion: number | null;
  moduleLabels?: string[];
  onSubmit: (changeRequest: string) => Promise<void>;
  compact?: boolean;
  disabled?: boolean;
  initialText?: string;
  submitLabel?: string;
  busyLabel?: string;
  hint?: string;
}) {
  const [text, setText] = useState(initialText);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const examples = refineExamples(moduleLabels);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const value = text.trim();
    if (value.split(/\s+/).length < 2 || value.length < 8) {
      setError("Describe the change, e.g. “Add a phone number field to members”.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit(value);
      setText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the refinement.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="grid gap-3">
      <label htmlFor={compact ? "refine-inline" : "refine-dialog"} className="text-sm font-medium">
        What should change?
      </label>
      <textarea
        id={compact ? "refine-inline" : "refine-dialog"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={compact ? 2 : 4}
        maxLength={5000}
        placeholder="e.g. Add a membership type (student, staff, public) to members. Remove the fines module."
        className={cn(fieldClass, "resize-y")}
        disabled={busy || disabled}
      />
      <div className="flex flex-wrap gap-1.5" aria-label="Example changes">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => setText((t) => (t.trim() ? `${t.trim()}. ${example}` : example))}
            className="rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground transition hover:border-primary hover:text-foreground"
            disabled={busy || disabled}
          >
            {example}
          </button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-md text-xs text-muted-foreground">
          {liveVersion
            ? (hint ??
              `v${liveVersion} stays live until the refined version passes QA. Only the agents your change affects update their files.`)
            : "Refinement needs a live version."}
        </p>
        <button
          type="submit"
          className={btnPrimary}
          disabled={busy || disabled || !liveVersion || !text.trim()}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Wand2 className="size-4" />}
          {busy ? busyLabel : submitLabel}
        </button>
      </div>
    </form>
  );
}
