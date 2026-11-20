// Refine with a plan preview: describe the change -> review the PM agent's plan -> Apply or Cancel.
// Nothing changes until "Apply changes"; the build then applies exactly the plan that was shown.
import { Database, Loader2, Pencil, Rocket, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { btnGhost, btnPrimary } from "@/components/brand";
import { forgeApi } from "@/lib/api/forge";
import type { RefinePreview } from "@/lib/api/types";
import { FilesSection, PlanNotes, PlanSections } from "./ChangesPanel";
import { RefineForm } from "./RefineForm";
import { Alert } from "./ui";

export function RefineFlow({
  projectId,
  liveVersion,
  moduleLabels = [],
  compact = false,
  disabled = false,
  onApplied,
  onCancel,
}: {
  projectId: string;
  liveVersion: number | null;
  moduleLabels?: string[];
  compact?: boolean;
  disabled?: boolean;
  onApplied: (runId: string) => void | Promise<void>;
  onCancel?: () => void;
}) {
  const [preview, setPreview] = useState<RefinePreview | null>(null);
  const [draftText, setDraftText] = useState("");

  if (preview) {
    return (
      <PlanReview
        projectId={projectId}
        preview={preview}
        onApplied={onApplied}
        onEdit={() => {
          setDraftText(preview.change_request);
          setPreview(null);
        }}
        onCancel={() => {
          setPreview(null);
          setDraftText("");
          onCancel?.();
        }}
      />
    );
  }
  return (
    <RefineForm
      key={draftText}
      compact={compact}
      disabled={disabled}
      liveVersion={liveVersion}
      moduleLabels={moduleLabels}
      initialText={draftText}
      submitLabel="Preview changes"
      busyLabel="Planning…"
      hint="Nothing changes until you review the plan and apply it."
      onSubmit={async (text) => {
        setPreview(await forgeApi.previewRefinement(projectId, text));
      }}
    />
  );
}

export function PlanReview({
  projectId,
  preview,
  onApplied,
  onEdit,
  onCancel,
}: {
  projectId: string;
  preview: RefinePreview;
  onApplied: (runId: string) => void | Promise<void>;
  onEdit: () => void;
  onCancel: () => void;
}) {
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const plan = preview.plan;
  const destructive = preview.warnings.length > 0;

  const apply = async () => {
    if (!preview.draft_id) return;
    setBusy(true);
    setError(null);
    try {
      const started = await forgeApi.applyRefinementPlan(projectId, preview.draft_id);
      await onApplied(started.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply the plan.");
      setBusy(false);
    }
  };

  return (
    <div className="grid min-w-0 gap-4 [&>*]:min-w-0" aria-label="Change plan preview">
      <section className="rounded-2xl border bg-card p-5">
        <p className="text-xs font-semibold text-muted-foreground">
          PLAN PREVIEW · v{preview.base_version} → v{preview.base_version + 1} · NOTHING CHANGED YET
        </p>
        <p className="mt-2 whitespace-pre-line text-sm">{preview.change_request}</p>
        {plan?.summary && <p className="mt-3 text-sm text-muted-foreground">{plan.summary}</p>}
        {!preview.applicable && preview.message && (
          <div className="mt-3">
            <Alert>{preview.message}</Alert>
          </div>
        )}
      </section>

      {destructive && (
        <section
          className="rounded-2xl border border-destructive/40 bg-destructive/5 p-5"
          aria-label="Data warnings"
        >
          <h3 className="flex items-center gap-2 font-semibold text-destructive">
            <TriangleAlert className="size-4" /> This change deletes data
          </h3>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {preview.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <label className="mt-3 flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="size-4 accent-[var(--destructive)]"
            />
            I understand this data will be deleted
          </label>
        </section>
      )}

      {plan && <PlanSections plan={plan} baseVersion={preview.base_version} />}
      {preview.files && <FilesSection files={preview.files} title="Code changes" />}

      {preview.migration && (
        <section className="rounded-2xl border bg-card p-5">
          <h3 className="flex items-center gap-2 font-semibold">
            <Database className="size-4 text-primary" /> Database migration
          </h3>
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer break-all font-mono text-xs">
              {preview.migration.file}
            </summary>
            <pre className="mt-2 max-h-72 max-w-full overflow-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed">
              {preview.migration.sql}
            </pre>
          </details>
        </section>
      )}

      {plan && <PlanNotes plan={{ ...plan, notes: [...plan.notes, ...preview.notes] }} />}
      {error && <Alert>{error}</Alert>}

      <div className="flex flex-wrap items-center gap-2">
        {preview.applicable && (
          <button
            type="button"
            className={btnPrimary}
            onClick={apply}
            disabled={busy || (destructive && !accepted)}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
            {busy ? "Applying…" : "Apply changes"}
          </button>
        )}
        <button type="button" className={btnGhost} onClick={onEdit} disabled={busy}>
          <Pencil className="size-4" /> Edit request
        </button>
        <button
          type="button"
          className="px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
