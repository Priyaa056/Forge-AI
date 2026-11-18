import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Cpu, FolderGit2, Layers, Loader2, Plus, RefreshCw } from "lucide-react";
import robot from "@/assets/robot.png";
import { btnPrimary } from "@/components/brand";
import { Alert, Eyebrow, RunStatusPill, btnSmall } from "@/components/app/ui";
import { forgeApi } from "@/lib/api/forge";
import { formatWhen } from "@/lib/agents";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/app/")({
  head: () => ({ meta: [{ title: "Dashboard — FORGE AI" }] }),
  component: Dashboard,
});

function Dashboard() {
  const { user } = useAuth();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: forgeApi.listProjects,
    refetchInterval: (query) =>
      query.state.data?.some((p) => p.last_status === "RUNNING" || p.last_status === "PENDING")
        ? 2000
        : false,
  });
  const system = useQuery({ queryKey: ["system"], queryFn: forgeApi.system, staleTime: 60_000 });

  const list = projects.data ?? [];
  const stable = list.filter((p) => p.current_version).length;
  const builds = list.reduce((sum, p) => sum + p.run_count, 0);

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>Dashboard</Eyebrow>
          <h1 className="mt-2 text-3xl font-bold md:text-4xl">
            Welcome back{user?.full_name ? `, ${user.full_name}` : ""}.
          </h1>
          <p className="mt-2 text-muted-foreground">
            Your projects and every build the seven agents have run.
          </p>
        </div>
        <Link to="/app/new" className={btnPrimary}>
          <Plus className="size-4" /> New project
        </Link>
      </div>

      <div className="mt-10 grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-3">
        {[
          { i: FolderGit2, t: "Projects", v: projects.data ? String(list.length) : "—" },
          { i: Layers, t: "Builds run", v: projects.data ? String(builds) : "—" },
          { i: Cpu, t: "Live versions", v: projects.data ? String(stable) : "—" },
        ].map((s) => (
          <div key={s.t} className="bg-card p-6">
            <s.i className="size-5 text-primary" />
            <p className="mt-4 font-display text-3xl font-bold">{s.v}</p>
            <p className="mt-1 text-sm text-muted-foreground">{s.t}</p>
          </div>
        ))}
      </div>

      {system.data && !system.data.llm.llm_enabled && (
        <div className="mt-6">
          <Alert tone="info">
            Agents are running in rule-based mode (no LLM key configured on the server).
            Requirements are derived from your prompt by FORGE AI's analyzer; every build is still
            generated, tested and health-checked for real.
          </Alert>
        </div>
      )}

      <section className="mt-12">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">Project history</h2>
          <button
            type="button"
            className={btnSmall}
            onClick={() => void projects.refetch()}
            aria-label="Refresh projects"
          >
            <RefreshCw className={`size-3.5 ${projects.isFetching ? "animate-spin" : ""}`} />{" "}
            Refresh
          </button>
        </div>

        {projects.isLoading && (
          <p className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading projects…
          </p>
        )}
        {projects.error && (
          <div className="mt-6">
            <Alert>{projects.error.message}</Alert>
          </div>
        )}

        {projects.data && list.length === 0 && (
          <div className="mt-6 rounded-3xl border bg-card p-12 text-center shadow-soft">
            <img
              src={robot}
              alt=""
              width={816}
              height={816}
              className="animate-float mx-auto w-24"
            />
            <h3 className="mt-4 text-2xl font-bold">No projects yet</h3>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              Describe an app in plain language and the seven agents will plan, build, test and
              package it.
            </p>
            <Link to="/app/new" className={`${btnPrimary} mt-8`}>
              Start Building <ArrowRight className="size-4" />
            </Link>
          </div>
        )}

        {list.length > 0 && (
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {list.map((p) => (
              <Link
                key={p.project_id}
                to="/app/projects/$projectId"
                params={{ projectId: p.project_id }}
                className="group rounded-2xl border bg-card p-6 shadow-soft transition hover:-translate-y-1 hover:border-primary"
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="min-w-0 truncate text-lg font-semibold group-hover:text-primary">
                    {p.name}
                  </h3>
                  <RunStatusPill status={p.last_status} className="shrink-0" />
                </div>
                {p.initial_prompt && (
                  <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                    {p.initial_prompt}
                  </p>
                )}
                <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {p.current_version
                      ? `Live version v${p.current_version}`
                      : "No stable version yet"}
                  </span>
                  <span>
                    {p.run_count} build{p.run_count === 1 ? "" : "s"}
                  </span>
                  <span>Updated {formatWhen(p.updated_at)}</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
