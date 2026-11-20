import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { forgeApi } from "@/lib/api/forge";
import { ApiError } from "@/lib/api/client";
import { formatDuration } from "@/lib/agents";
import { cn } from "@/lib/utils";
import { Alert, EmptyState } from "./ui";

function Result({ status }: { status: string }) {
  const ok = status === "passed" || status === "healthy" || status === "success";
  const skipped = status === "skipped";
  const Icon = ok ? CheckCircle2 : skipped ? CircleDashed : XCircle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-semibold",
        ok ? "text-success" : skipped ? "text-muted-foreground" : "text-destructive",
      )}
    >
      <Icon className="size-3.5" /> {status}
    </span>
  );
}

const notProduced = (error: unknown) => error instanceof ApiError && error.status === 404;

/** QA report (executed checks and generated tests) and Deploy readiness for one build. */
export function QualityPanel({
  projectId,
  runId,
  finished,
}: {
  projectId: string;
  runId: string;
  finished: boolean;
}) {
  const qa = useQuery({
    queryKey: ["qa", projectId, runId],
    queryFn: () => forgeApi.getQAReport(projectId, runId),
    enabled: finished,
    retry: false,
  });
  const deploy = useQuery({
    queryKey: ["deploy", projectId, runId],
    queryFn: () => forgeApi.getDeployReport(projectId, runId),
    enabled: finished,
    retry: false,
  });

  if (!finished)
    return (
      <EmptyState title="Build in progress">
        Test and deployment reports appear when the QA and Deploy agents finish.
      </EmptyState>
    );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border bg-card p-5">
        <h3 className="font-semibold">QA Agent report</h3>
        {qa.isLoading && (
          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </p>
        )}
        {qa.error &&
          (notProduced(qa.error) ? (
            <p className="mt-3 text-sm text-muted-foreground">
              The QA agent did not run in this build.
            </p>
          ) : (
            <div className="mt-3">
              <Alert>{qa.error.message}</Alert>
            </div>
          ))}
        {qa.data && (
          <>
            <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-xl border bg-border text-center">
              {[
                { t: "Tests passed", v: `${qa.data.tests_passed}/${qa.data.tests_run}` },
                { t: "Score", v: `${Math.round(qa.data.score)}%` },
                { t: "Frontend build", v: qa.data.frontend_build },
              ].map((s) => (
                <div key={s.t} className="bg-background px-2 py-3">
                  <p className="font-display text-lg font-bold">{s.v}</p>
                  <p className="text-xs text-muted-foreground">{s.t}</p>
                </div>
              ))}
            </div>
            {qa.data.summary && (
              <p className="mt-3 text-sm text-muted-foreground">{qa.data.summary}</p>
            )}
            <ul className="mt-4 divide-y rounded-xl border bg-background">
              {qa.data.checks.map((c) => (
                <li
                  key={c.name}
                  className="flex items-start justify-between gap-3 px-3 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="block">{c.name}</span>
                    {c.details && c.status !== "passed" && (
                      <span className="block break-words text-xs text-muted-foreground">
                        {c.details.slice(0, 300)}
                      </span>
                    )}
                  </span>
                  <span className="flex shrink-0 flex-col items-end">
                    <Result status={c.status} />
                    <span className="text-xs text-muted-foreground">
                      {formatDuration(c.duration_ms)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {qa.data.test_suites.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2">
                {qa.data.test_suites.map((s) => (
                  <span
                    key={s.name}
                    className={cn(
                      "rounded-lg border px-2 py-1 font-mono text-xs",
                      s.failed_count
                        ? "border-destructive/50 text-destructive"
                        : "text-muted-foreground",
                    )}
                  >
                    {s.name} {s.passed_count}/{s.tests_count}
                  </span>
                ))}
              </div>
            )}
            {qa.data.errors.length > 0 && (
              <div className="mt-4 space-y-2">
                <p className="text-sm font-semibold">Problems found</p>
                {qa.data.errors.slice(0, 8).map((e) => (
                  <div
                    key={e.id}
                    className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive"
                  >
                    <span className="font-semibold">
                      {e.type} · {e.agent}
                    </span>
                    <span className="mt-1 block break-words font-mono">
                      {e.message.slice(0, 400)}
                    </span>
                  </div>
                ))}
                {qa.data.repair_recommendation && (
                  <Alert tone="info">{qa.data.repair_recommendation}</Alert>
                )}
              </div>
            )}
          </>
        )}
      </section>

      <section className="rounded-2xl border bg-card p-5">
        <h3 className="font-semibold">Deploy Agent report</h3>
        {deploy.isLoading && (
          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </p>
        )}
        {deploy.error &&
          (notProduced(deploy.error) ? (
            <p className="mt-3 text-sm text-muted-foreground">
              The Deploy agent did not run in this build (it only runs after QA passes).
            </p>
          ) : (
            <div className="mt-3">
              <Alert>{deploy.error.message}</Alert>
            </div>
          ))}
        {deploy.data && (
          <>
            <p className="mt-2 text-sm text-muted-foreground">{deploy.data.summary}</p>
            {!deploy.data.container_build_verified && (
              <div className="mt-3">
                <Alert tone="info">
                  Docker configuration was generated and validated, but container images were not
                  built on this server
                  {deploy.data.docker_available ? "" : " (Docker is not installed)"}. The app was
                  health-checked as a local process.
                </Alert>
              </div>
            )}
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-primary">
              Live health checks
            </p>
            <ul className="mt-2 divide-y rounded-xl border bg-background">
              {deploy.data.health_checks.map((h) => (
                <li
                  key={h.endpoint}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 truncate font-mono text-xs">{h.endpoint}</span>
                  <span className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                    {h.status_code} · {Math.round(h.response_time_ms)} ms{" "}
                    <Result status={h.status} />
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-primary">
              Readiness
            </p>
            <ul className="mt-2 divide-y rounded-xl border bg-background">
              {deploy.data.readiness_checks.map((c) => (
                <li
                  key={c.name}
                  className="flex items-start justify-between gap-3 px-3 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="block">{c.name}</span>
                    <span className="block break-words text-xs text-muted-foreground">
                      {c.details.slice(0, 200)}
                    </span>
                  </span>
                  <Result status={c.status} />
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-primary">
              Run it yourself
            </p>
            <ul className="mt-2 space-y-1">
              {deploy.data.instructions.map((line) => (
                <li
                  key={line}
                  className="rounded-lg border bg-background px-3 py-1.5 font-mono text-xs"
                >
                  {line}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
