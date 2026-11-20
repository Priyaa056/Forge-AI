// What a refinement changed: the PM's plan, the agents involved, files and the regression check.
// The plan sections are shared with the plan preview (PlanReview).
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  FileMinus2,
  FilePen,
  FilePlus2,
  Loader2,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { AGENTS } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";
import type { ChangePlan, FileChanges, RunChanges } from "@/lib/api/types";
import { ACTION_LABEL, AREA_LABEL } from "@/lib/refine";
import { cn } from "@/lib/utils";
import { Alert } from "./ui";

export function ChangesPanel({
  projectId,
  runId,
  live,
}: {
  projectId: string;
  runId: string;
  live: boolean;
}) {
  const changes = useQuery({
    queryKey: ["changes", projectId, runId],
    queryFn: () => forgeApi.getRunChanges(projectId, runId),
    refetchInterval: live ? 1500 : false,
  });
  if (changes.isLoading) {
    return (
      <p className="text-sm text-muted-foreground">
        <Loader2 className="mr-2 inline size-4 animate-spin" />
        Loading the change plan…
      </p>
    );
  }
  if (changes.error || !changes.data) {
    return <Alert>{changes.error?.message ?? "No change information for this build."}</Alert>;
  }
  return <ChangesView data={changes.data} live={live} />;
}

const ACTION_STYLE: Record<string, string> = {
  added: "bg-success/12 text-success",
  removed: "bg-destructive/10 text-destructive",
  modified: "bg-warning/15 text-foreground",
  renamed: "bg-accent text-accent-foreground",
};

const AGENT_ACTION_STYLE: Record<string, string> = {
  update: "bg-primary/10 text-primary",
  "update (impact check)": "bg-warning/15 text-foreground",
  reused: "bg-muted text-muted-foreground",
  reuse: "bg-muted text-muted-foreground",
};

export function ChangesView({ data, live = false }: { data: RunChanges; live?: boolean }) {
  const plan = data.plan;
  const pmError = data.error_reports?.["pm"];
  const regression = data.regression;
  const promoted = data.promotion?.state === "promoted" ? data.promotion.version : null;

  return (
    <div className="grid gap-4">
      <section className="rounded-2xl border bg-card p-5">
        <p className="text-xs font-semibold text-muted-foreground">
          CHANGE REQUEST · REFINING v{data.base_version}
          {promoted ? ` → LIVE AS v${promoted}` : ""}
        </p>
        <p className="mt-2 whitespace-pre-line text-sm">{data.change_request}</p>
        {plan?.summary && <p className="mt-3 text-sm text-muted-foreground">{plan.summary}</p>}
        {!plan && live && !pmError && (
          <p className="mt-3 text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline size-4 animate-spin" />
            The PM agent is planning the change…
          </p>
        )}
        {pmError && (
          <div className="mt-3">
            <Alert>{pmError}</Alert>
          </div>
        )}
      </section>

      {plan && (
        <PlanSections
          plan={plan}
          baseVersion={data.base_version}
          actions={data.agent_actions}
          escalated={data.escalated}
        />
      )}

      {data.files && <FilesSection files={data.files} />}

      {regression && (
        <section className="rounded-2xl border bg-card p-5">
          <h3 className="flex items-center gap-2 font-semibold">
            {regression.failures.length ? (
              <TriangleAlert className="size-4 text-destructive" />
            ) : (
              <CheckCircle2 className="size-4 text-success" />
            )}
            Existing features verified
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {regression.requirements_still_met}/{regression.requirements_checked} requirements and{" "}
            {regression.tests_still_passing}/{regression.tests_checked} tests that passed in v
            {regression.base_version} still pass
            {regression.requirements_retired || regression.tests_retired
              ? ` (${regression.requirements_retired} requirements and ${regression.tests_retired} tests retired by the change)`
              : ""}
            .
          </p>
          {regression.failures.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm text-destructive">
              {regression.failures.slice(0, 10).map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {plan && <PlanNotes plan={plan} />}
    </div>
  );
}

/** "What changes" and "Agents" (with what is kept), for a plan that is previewed or was applied. */
export function PlanSections({
  plan,
  baseVersion,
  actions = {},
  escalated = [],
}: {
  plan: ChangePlan;
  baseVersion: number | null;
  actions?: Record<string, string>;
  escalated?: { agent: string; files: string[] }[];
}) {
  const merged: Record<string, string> = {
    ...Object.fromEntries(plan.agents.map((a) => [a.agent, a.action])),
    ...actions,
  };
  return (
    <>
      {plan.changes.length > 0 && (
        <section className="rounded-2xl border bg-card p-5">
          <h3 className="font-semibold">What changes ({plan.changes.length})</h3>
          <ul className="mt-3 grid gap-2">
            {plan.changes.map((c, i) => (
              <li
                key={`${c.area}-${c.target}-${i}`}
                className="flex flex-wrap items-start gap-2 text-sm"
              >
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-semibold",
                    ACTION_STYLE[c.action] ?? "bg-muted",
                  )}
                >
                  {c.action}
                </span>
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {AREA_LABEL[c.area] ?? c.area}
                </span>
                <span className="font-medium">{c.target}</span>
                {c.detail && <span className="text-muted-foreground">— {c.detail}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-2xl border bg-card p-5">
        <h3 className="font-semibold">Agents</h3>
        <ul className="mt-3 grid gap-2">
          {AGENTS.map((agent) => {
            const action = merged[agent.stage] ?? "";
            const impact = plan.agents.find((a) => a.agent === agent.stage);
            const raised = escalated.find((e) => e.agent === agent.stage);
            return (
              <li
                key={agent.stage}
                className="grid gap-1 rounded-lg border bg-background px-3 py-2 sm:grid-cols-[11rem_9rem_1fr] sm:items-start"
              >
                <span className="flex items-center gap-2 text-sm font-medium">
                  <agent.icon className="size-4 text-primary" /> {agent.name}
                </span>
                <span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-semibold",
                      AGENT_ACTION_STYLE[action] ?? "bg-success/12 text-success",
                    )}
                  >
                    {ACTION_LABEL[action] ?? action}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {raised
                    ? `The plan reused this agent, but a dry run showed its output would change (${raised.files.slice(0, 3).join(", ")}), so it ran.`
                    : (impact?.reasons ?? []).slice(0, 3).join(" · ")}
                </span>
              </li>
            );
          })}
        </ul>
        {Object.keys(plan.preserved).length > 0 && (
          <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5 text-success" /> Kept from v{baseVersion}:
            {Object.entries(plan.preserved)
              .filter(([, n]) => n > 0)
              .map(([k, n]) => (
                <span key={k} className="rounded-full bg-muted px-2 py-0.5">
                  {n} {k.replace("_", " ")}
                </span>
              ))}
          </p>
        )}
      </section>
    </>
  );
}

export function FilesSection({ files, title = "Files" }: { files: FileChanges; title?: string }) {
  return (
    <section className="rounded-2xl border bg-card p-5">
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {files.counts.added} added · {files.counts.modified} modified · {files.counts.removed}{" "}
        removed · {files.counts.unchanged} unchanged
      </p>
      <div className="mt-3 grid gap-2 text-sm">
        <FileList icon={FilePlus2} title="Added" files={files.added} tone="text-success" />
        <FileList icon={FilePen} title="Modified" files={files.modified} tone="text-foreground" />
        <FileList icon={FileMinus2} title="Removed" files={files.removed} tone="text-destructive" />
      </div>
    </section>
  );
}

export function PlanNotes({ plan }: { plan: ChangePlan }) {
  if (!plan.unresolved.length && !plan.notes.length) return null;
  return (
    <section className="rounded-2xl border bg-card p-5 text-sm">
      {plan.unresolved.length > 0 && (
        <>
          <h3 className="font-semibold">Not applied</h3>
          <ul className="mt-2 list-disc pl-5 text-muted-foreground">
            {plan.unresolved.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </>
      )}
      {plan.notes.length > 0 && (
        <ul
          className={cn(
            "list-disc pl-5 text-muted-foreground",
            plan.unresolved.length > 0 && "mt-3",
          )}
        >
          {plan.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FileList({
  icon: Icon,
  title,
  files,
  tone,
}: {
  icon: typeof FilePlus2;
  title: string;
  files: string[];
  tone: string;
}) {
  if (!files.length) return null;
  return (
    <details className="rounded-lg border bg-background px-3 py-2" open={files.length <= 6}>
      <summary className="flex cursor-pointer items-center gap-2 font-medium">
        <Icon className={cn("size-4", tone)} /> {title} ({files.length})
      </summary>
      <ul className="mt-2 grid gap-0.5 font-mono text-xs text-muted-foreground">
        {files.map((f) => (
          <li key={f} className="break-all">
            {f}
          </li>
        ))}
      </ul>
    </details>
  );
}
