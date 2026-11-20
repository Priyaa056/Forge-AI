import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { btnPrimary, btnGhost } from "@/components/brand";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { forgeApi } from "@/lib/api/forge";
import type { ProjectDetail, RunListItem } from "@/lib/api/types";
import { formatDuration, formatWhen } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { Alert, RunStatusPill, btnSmall, fieldClass } from "./ui";

/** Stable versions, build history and rollback to an earlier stable version. */
export function VersionsPanel({
  project,
  onSelectRun,
}: {
  project: ProjectDetail;
  onSelectRun: (runId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<RunListItem | null>(null);
  const [reason, setReason] = useState("");
  const events = useQuery({
    queryKey: ["project-events", project.project_id],
    queryFn: () => forgeApi.getProjectEvents(project.project_id),
  });

  const rollback = useMutation({
    mutationFn: (runId: string) =>
      forgeApi.rollback(project.project_id, runId, reason.trim() || undefined),
    onSuccess: async (result) => {
      toast.success(
        `Version v${result.new_version} is live (restored from v${result.restored_from_version})`,
      );
      setTarget(null);
      setReason("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["preview", project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["files", project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["project-events", project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["projects"] }),
      ]);
    },
  });

  const versionOf = (runId: string) =>
    project.versions
      .filter((v) => v.run_id === runId && v.source === "run")
      .map((v) => v.version)[0];
  const rollbacks = (events.data ?? []).filter(
    (e) => e.event_type.startsWith("ROLLBACK") || e.event_type === "VERSION_PROMOTED",
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="rounded-2xl border bg-card p-5">
        <h3 className="font-semibold">Versions</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          A build becomes a version only when all seven agents succeed. Rollback restores the files
          and every agent artifact, verified by checksum.
        </p>
        {project.versions.length === 0 && (
          <p className="mt-4 text-sm text-muted-foreground">No stable version yet.</p>
        )}
        <ul className="mt-4 space-y-2">
          {[...project.versions].reverse().map((v) => (
            <li
              key={v.version}
              className={cn(
                "rounded-lg border bg-background px-3 py-2 text-sm",
                v.version === project.current_version && "border-primary",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold">v{v.version}</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {v.source === "rollback" && (
                    <span className="rounded-md bg-accent px-1.5 py-0.5 text-accent-foreground">
                      rollback of v{v.restored_from_version}
                    </span>
                  )}
                  {v.version === project.current_version && (
                    <span className="rounded-md bg-primary px-1.5 py-0.5 font-semibold text-primary-foreground">
                      Live
                    </span>
                  )}
                  {formatWhen(v.promoted_at)}
                </span>
              </div>
              {v.reason && <p className="mt-1 text-xs text-muted-foreground">Reason: {v.reason}</p>}
            </li>
          ))}
        </ul>
        {rollbacks.length > 0 && (
          <>
            <p className="mt-6 text-xs font-semibold uppercase tracking-widest text-primary">
              Version events
            </p>
            <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs text-muted-foreground">
              {[...rollbacks].reverse().map((e) => (
                <li key={e.event_id}>
                  {new Date(e.timestamp).toLocaleString()} — {e.error_message ?? e.message}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="rounded-2xl border bg-card p-5">
        <h3 className="flex items-center gap-2 font-semibold">
          <History className="size-4 text-primary" /> Build history
        </h3>
        <ul className="mt-4 space-y-2">
          {[...project.runs].reverse().map((run, i) => {
            const version = versionOf(run.run_id);
            const live = run.run_id === project.current_run_id;
            return (
              <li key={run.run_id} className="rounded-lg border bg-background p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => onSelectRun(run.run_id)}
                    className="font-semibold hover:text-primary"
                  >
                    Build {project.runs.length - i}
                    {version ? ` → v${version}` : ""}
                  </button>
                  <RunStatusPill status={run.execution_status} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{run.user_prompt}</p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                  <span>
                    {formatWhen(run.created_at)} · {formatDuration(run.total_duration_ms)}
                    {run.simulated_failure ? ` · test mode (${run.simulated_failure} fails)` : ""}
                  </span>
                  {run.stable && !live && (
                    <button type="button" className={btnSmall} onClick={() => setTarget(run)}>
                      <RotateCcw className="size-3.5" /> Restore this version
                    </button>
                  )}
                  {live && project.current_version && (
                    <span className="font-semibold text-primary">
                      Live version v{project.current_version}
                    </span>
                  )}
                  {!run.stable && run.execution_status === "FAILED" && (
                    <span>Not restorable — build failed</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <Dialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) setTarget(null);
        }}
      >
        <DialogContent className="rounded-2xl">
          <DialogHeader>
            <DialogTitle>Restore v{target ? versionOf(target.run_id) : ""}?</DialogTitle>
            <DialogDescription>
              The files and all seven agent artifacts from that build become the live version (as a
              new version number). Nothing is deleted. A running preview restarts on the restored
              version.
            </DialogDescription>
          </DialogHeader>
          <label className="block text-sm font-medium">
            Reason <span className="font-normal text-muted-foreground">(optional)</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={300}
              className={`${fieldClass} mt-1.5`}
              placeholder="e.g. The latest build changed the data model"
            />
          </label>
          {rollback.error && <Alert>{rollback.error.message}</Alert>}
          <DialogFooter className="gap-2">
            <button type="button" className={btnGhost} onClick={() => setTarget(null)}>
              Cancel
            </button>
            <button
              type="button"
              className={btnPrimary}
              disabled={rollback.isPending}
              onClick={() => target && rollback.mutate(target.run_id)}
            >
              {rollback.isPending && <Loader2 className="size-4 animate-spin" />} Restore version
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
