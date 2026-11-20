import { useQuery } from "@tanstack/react-query";
import { FileCode2, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { AGENTS, agentByStage } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";
import { cn } from "@/lib/utils";
import { Alert, EmptyState } from "./ui";

/** Generated source files, grouped by the agent that wrote them, with a read-only viewer. */
export function FilesPanel({ projectId, runId }: { projectId: string; runId: string }) {
  const files = useQuery({
    queryKey: ["files", projectId, runId],
    queryFn: () => forgeApi.listFiles(projectId, runId),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const content = useQuery({
    queryKey: ["file", projectId, runId, selected],
    queryFn: () => forgeApi.readFile(projectId, runId, selected ?? ""),
    enabled: Boolean(selected),
  });

  const groups = useMemo(() => {
    const list = (files.data ?? []).filter((f) =>
      f.path.toLowerCase().includes(filter.toLowerCase()),
    );
    return [...AGENTS.map((a) => a.stage), null]
      .map((stage) => ({
        stage,
        files: list.filter((f) => f.agent === stage),
      }))
      .filter((g) => g.files.length > 0);
  }, [files.data, filter]);

  if (files.isLoading)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Loading files…
      </p>
    );
  if (files.error) return <Alert>{files.error.message}</Alert>;
  if (!files.data?.length)
    return <EmptyState title="No files yet">Files appear as the agents write them.</EmptyState>;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,18rem)_minmax(0,1fr)]">
      <div className="min-w-0">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={`Filter ${files.data.length} files…`}
          className="w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
        />
        <div className="mt-3 max-h-[30rem] space-y-4 overflow-y-auto pr-1">
          {groups.map((group) => (
            <div key={group.stage ?? "other"}>
              <p className="text-xs font-semibold uppercase tracking-widest text-primary">
                {group.stage ? agentByStage(group.stage)?.name : "Other"} · {group.files.length}
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {group.files.map((f) => (
                  <li key={f.path}>
                    <button
                      type="button"
                      onClick={() => setSelected(f.path)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left font-mono text-xs transition hover:bg-muted",
                        selected === f.path && "bg-accent text-accent-foreground",
                      )}
                      title={f.path}
                    >
                      <FileCode2 className="size-3.5 shrink-0" />
                      <span className="truncate">{f.path}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="min-w-0 rounded-xl border bg-background">
        {!selected && (
          <p className="p-6 text-sm text-muted-foreground">Select a file to view its source.</p>
        )}
        {selected && (
          <>
            <div className="border-b px-4 py-2 font-mono text-xs text-muted-foreground">
              {selected}
            </div>
            {content.isLoading && <p className="p-4 text-sm text-muted-foreground">Loading…</p>}
            {content.error && (
              <div className="p-4">
                <Alert>{content.error.message}</Alert>
              </div>
            )}
            {content.data && (
              <pre className="max-h-[30rem] overflow-auto p-4 font-mono text-xs leading-relaxed">
                <code>{content.data.content}</code>
              </pre>
            )}
          </>
        )}
      </div>
    </div>
  );
}
