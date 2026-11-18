import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MODE_LABEL, agentByStage } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";
import { Alert } from "./ui";

/** Shows the versioned artifact an agent produced: its JSON contract, metadata, files and lineage. */
export function ArtifactDialog({
  artifactId,
  onClose,
}: {
  artifactId: string | null;
  onClose: () => void;
}) {
  const artifact = useQuery({
    queryKey: ["artifact", artifactId],
    queryFn: () => forgeApi.getArtifact(artifactId ?? ""),
    enabled: Boolean(artifactId),
  });
  const data = artifact.data;
  const agent = data ? agentByStage(data.agent_name) : undefined;

  return (
    <Dialog
      open={artifactId !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-x-hidden overflow-y-auto rounded-2xl">
        <DialogHeader>
          <DialogTitle>{agent ? `${agent.name} artifact` : "Artifact"}</DialogTitle>
          <DialogDescription>
            {data
              ? `${data.artifact_type} · version ${data.version} · ${data.status.toLowerCase()} · ${new Date(data.created_at).toLocaleString()}`
              : "Loading…"}
          </DialogDescription>
        </DialogHeader>
        {artifact.isLoading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading artifact…
          </p>
        )}
        {artifact.error && <Alert>{artifact.error.message}</Alert>}
        {data && (
          <div className="min-w-0 space-y-4 text-sm">
            <div className="flex flex-wrap gap-2 text-xs">
              {data.metadata.generation_mode && (
                <span className="rounded-md bg-accent px-2 py-0.5 text-accent-foreground">
                  {MODE_LABEL[data.metadata.generation_mode] ?? data.metadata.generation_mode}
                </span>
              )}
              {data.metadata.spec_file && (
                <span className="rounded-md border px-2 py-0.5 font-mono">
                  {data.metadata.spec_file}
                </span>
              )}
              {(data.metadata.attempts ?? 1) > 1 && (
                <span className="rounded-md border px-2 py-0.5">
                  {data.metadata.attempts} attempts
                </span>
              )}
              {data.metadata.is_rollback && (
                <span className="rounded-md border px-2 py-0.5">restored by rollback</span>
              )}
            </div>
            {data.metadata.error && <Alert>{data.metadata.error}</Alert>}
            {data.input_artifacts.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Built from:{" "}
                <span className="font-mono">
                  {data.input_artifacts.map((id) => id.slice(0, 8)).join(", ")}
                </span>
              </p>
            )}
            {(data.metadata.generated_files?.length ?? 0) > 0 && (
              <details>
                <summary className="cursor-pointer font-semibold">
                  Files written ({data.metadata.generated_files?.length})
                </summary>
                <ul className="mt-2 grid gap-0.5 font-mono text-xs text-muted-foreground sm:grid-cols-2">
                  {data.metadata.generated_files?.map((f) => (
                    <li key={f} className="truncate">
                      {f}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <pre className="max-h-[50vh] overflow-auto rounded-xl border bg-background p-4 font-mono text-xs leading-relaxed">
              {JSON.stringify(data.content, null, 2)}
            </pre>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
