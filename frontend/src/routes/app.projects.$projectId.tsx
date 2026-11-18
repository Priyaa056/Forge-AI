import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronLeft, Download, FlaskConical, Loader2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { btnGhost } from "@/components/brand";
import { ActivityFeed } from "@/components/app/ActivityFeed";
import { AgentPipeline } from "@/components/app/AgentPipeline";
import { ArtifactDialog } from "@/components/app/ArtifactDialog";
import { FilesPanel } from "@/components/app/FilesPanel";
import { PreviewPanel } from "@/components/app/PreviewPanel";
import { PromptForm } from "@/components/app/PromptForm";
import { QualityPanel } from "@/components/app/QualityPanel";
import { VersionsPanel } from "@/components/app/VersionsPanel";
import { Alert, RunStatusPill, WindowFrame } from "@/components/app/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { agentByStage, formatDuration, formatWhen } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";
import type { RunSummary, StageName } from "@/lib/api/types";

type WorkspaceSearch = { run?: string };

export const Route = createFileRoute("/app/projects/$projectId")({
  validateSearch: (search: Record<string, unknown>): WorkspaceSearch =>
    typeof search["run"] === "string" ? { run: search["run"] } : {},
  head: () => ({ meta: [{ title: "Workspace — FORGE AI" }] }),
  component: Workspace,
});

const isActive = (summary: RunSummary | undefined) =>
  !summary ||
  summary.execution_status === "PENDING" ||
  summary.execution_status === "RUNNING" ||
  summary.promotion?.state === "pending";

function slugify(name: string) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40) || "app"
  );
}

function Workspace() {
  const { projectId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [iterating, setIterating] = useState(false);
  const [tab, setTab] = useState("activity");

  const system = useQuery({ queryKey: ["system"], queryFn: forgeApi.system, staleTime: 60_000 });
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => forgeApi.getProject(projectId),
  });
  const runs = project.data?.runs ?? [];
  const runId = search.run ?? runs[runs.length - 1]?.run_id;

  const summary = useQuery({
    queryKey: ["run", projectId, runId],
    queryFn: () => forgeApi.getRun(projectId, runId ?? ""),
    enabled: Boolean(runId),
    refetchInterval: (query) => (isActive(query.state.data) ? 1000 : false),
  });
  const active = isActive(summary.data);
  const events = useQuery({
    queryKey: ["events", projectId, runId],
    queryFn: () => forgeApi.getRunEvents(projectId, runId ?? ""),
    enabled: Boolean(runId),
    refetchInterval: active ? 1000 : false,
  });

  // When a build finishes, refresh everything that depends on it (versions, files, preview, history).
  const wasActive = useRef(active);
  useEffect(() => {
    if (wasActive.current && !active && summary.data) {
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["files", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["preview", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["events", projectId, runId] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    }
    wasActive.current = active;
  }, [active, summary.data, projectId, runId, queryClient]);

  const download = useMutation({ mutationFn: () => forgeApi.downloadZip(projectId, "current") });

  const selectRun = (id: string) =>
    void navigate({ to: "/app/projects/$projectId", params: { projectId }, search: { run: id } });

  if (project.isLoading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-16 text-sm text-muted-foreground">
        <Loader2 className="mr-2 inline size-4 animate-spin" />
        Loading project…
      </main>
    );
  }
  if (project.error || !project.data) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-16">
        <Alert>{project.error?.message ?? "Project not found."}</Alert>
        <Link to="/app" className={`${btnGhost} mt-6`}>
          Back to dashboard
        </Link>
      </main>
    );
  }

  const p = project.data;
  const name = p.project_name || p.name;
  const run = summary.data;
  const runIndex = runs.findIndex((r) => r.run_id === runId);
  const failedAgent = run
    ? (Object.entries(run.agents).find(([, a]) => a.status === "FAILED")?.[0] as
        StageName | undefined)
    : undefined;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <Link
        to="/app"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="size-4" /> Dashboard
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold md:text-4xl">{name}</h1>
            {p.current_version ? (
              <span className="rounded-full bg-success/12 px-2.5 py-0.5 text-xs font-semibold text-success">
                Live v{p.current_version}
              </span>
            ) : (
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                No live version yet
              </span>
            )}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Created {formatWhen(p.created_at)} · {runs.length} build{runs.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={btnGhost}
            onClick={() => setIterating(true)}
            disabled={active}
          >
            <Sparkles className="size-4" /> New iteration
          </button>
          <button
            type="button"
            className={btnGhost}
            disabled={!p.current_version || download.isPending}
            onClick={() => download.mutate()}
          >
            {download.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}{" "}
            Download ZIP
          </button>
        </div>
      </div>
      {download.error && (
        <div className="mt-4">
          <Alert>{download.error.message}</Alert>
        </div>
      )}

      {runs.length > 1 && (
        <div className="mt-6 flex flex-wrap gap-2">
          {runs.map((r, i) => (
            <button
              key={r.run_id}
              type="button"
              onClick={() => selectRun(r.run_id)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${r.run_id === runId ? "border-primary bg-accent text-accent-foreground" : "bg-card hover:bg-muted"}`}
            >
              Build {i + 1}
              {r.run_id === p.current_run_id
                ? " · live"
                : r.execution_status === "FAILED"
                  ? " · failed"
                  : ""}
            </button>
          ))}
        </div>
      )}

      <WindowFrame
        className="mt-6"
        label={`forge.ai/workspace/${slugify(name)}${runIndex >= 0 ? ` · build ${runIndex + 1}` : ""}`}
        actions={<RunStatusPill status={run?.execution_status} />}
      >
        <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-[1fr_1.25fr]">
          <div className="space-y-4">
            <div className="rounded-xl border bg-background p-4">
              <p className="text-xs font-semibold text-muted-foreground">PROMPT</p>
              <p className="mt-2 text-sm">
                {run?.user_prompt ?? runs[runIndex]?.user_prompt ?? p.initial_prompt}
              </p>
            </div>
            <div className="rounded-xl border bg-background p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                <span>PROGRESS</span>
                <span>{run?.progress_percent ?? 0}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full transition-all ${run?.execution_status === "FAILED" ? "bg-destructive" : "bg-primary"}`}
                  style={{ width: `${run?.progress_percent ?? 0}%` }}
                />
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                {active && run?.current_agent
                  ? `${agentByStage(run.current_agent)?.name ?? run.current_agent} is working…`
                  : run?.promotion?.state === "pending"
                    ? "Promoting the build to the live version…"
                    : run?.execution_status === "COMPLETED"
                      ? `All seven agents finished${run.promotion?.state === "promoted" ? ` — live as v${run.promotion.version}` : ""}.`
                      : run?.execution_status === "FAILED"
                        ? `${failedAgent ? agentByStage(failedAgent)?.name : "An agent"} failed; later agents were skipped${p.current_version ? ` and v${p.current_version} stays live` : ""}.`
                        : "Waiting to start…"}
              </p>
              <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-lg border bg-border text-center">
                {[
                  { t: "Duration", v: formatDuration(run?.total_duration_ms) },
                  { t: "Agents done", v: run ? `${run.successful_agent_count}/7` : "—" },
                  {
                    t: "QA",
                    v: run?.qa_summary?.tests_run
                      ? `${run.qa_summary.tests_passed}/${run.qa_summary.tests_run}`
                      : "—",
                  },
                ].map((s) => (
                  <div key={s.t} className="bg-card px-2 py-2">
                    <p className="font-display text-base font-bold">{s.v}</p>
                    <p className="text-[11px] text-muted-foreground">{s.t}</p>
                  </div>
                ))}
              </div>
            </div>
            {run?.simulated_failure && (
              <p className="flex gap-2 rounded-lg bg-accent px-3 py-2 text-xs text-accent-foreground">
                <FlaskConical className="mt-0.5 size-3.5 shrink-0" /> Test mode: a failure was
                injected into the {agentByStage(run.simulated_failure)?.name}.
              </p>
            )}
            {failedAgent && run?.agents[failedAgent].error && (
              <Alert>{run.agents[failedAgent].error}</Alert>
            )}
            {summary.error && <Alert>{summary.error.message}</Alert>}
          </div>
          <AgentPipeline
            summary={run}
            onSelect={(stage) => {
              const id = run?.agents[stage].artifact_id;
              if (id) setArtifactId(id);
            }}
          />
        </div>
      </WindowFrame>

      <Tabs value={tab} onValueChange={setTab} className="mt-10">
        <TabsList className="flex h-auto flex-wrap justify-start gap-1 rounded-xl bg-muted p-1">
          <TabsTrigger value="activity" className="rounded-lg">
            Activity
          </TabsTrigger>
          <TabsTrigger value="files" className="rounded-lg">
            Files
          </TabsTrigger>
          <TabsTrigger value="preview" className="rounded-lg">
            Preview
          </TabsTrigger>
          <TabsTrigger value="quality" className="rounded-lg">
            Tests & deploy
          </TabsTrigger>
          <TabsTrigger value="versions" className="rounded-lg">
            Versions
          </TabsTrigger>
        </TabsList>
        <TabsContent value="activity" className="mt-6">
          <ActivityFeed events={events.data ?? []} live={active} />
        </TabsContent>
        <TabsContent value="files" className="mt-6">
          {runId && <FilesPanel projectId={projectId} runId={runId} />}
        </TabsContent>
        <TabsContent value="preview" className="mt-6">
          <PreviewPanel
            projectId={projectId}
            slug={slugify(name)}
            currentVersion={p.current_version}
          />
        </TabsContent>
        <TabsContent value="quality" className="mt-6">
          {runId && <QualityPanel projectId={projectId} runId={runId} finished={!active} />}
        </TabsContent>
        <TabsContent value="versions" className="mt-6">
          <VersionsPanel project={p} onSelectRun={selectRun} />
        </TabsContent>
      </Tabs>

      <ArtifactDialog artifactId={artifactId} onClose={() => setArtifactId(null)} />

      <Dialog open={iterating} onOpenChange={setIterating}>
        <DialogContent className="max-w-xl rounded-2xl">
          <DialogHeader>
            <DialogTitle>New iteration</DialogTitle>
            <DialogDescription>
              Run the seven agents again on this project with an updated description.
            </DialogDescription>
          </DialogHeader>
          <PromptForm
            mode="iteration"
            initialPrompt={runs[runs.length - 1]?.user_prompt ?? p.initial_prompt}
            faultInjection={Boolean(system.data?.fault_injection_enabled)}
            onSubmit={async ({ prompt, simulateFailure }) => {
              const created = await forgeApi.createRun(projectId, prompt, simulateFailure);
              await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
              setIterating(false);
              setTab("activity");
              selectRun(created.run_id);
            }}
          />
        </DialogContent>
      </Dialog>
    </main>
  );
}
