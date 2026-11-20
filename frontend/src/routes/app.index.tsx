import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Loader2, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import robot from "@/assets/robot.png";
import { btnPrimary } from "@/components/brand";
import { StatsOverview } from "@/components/app/DashboardStats";
import { DeleteProjectDialog } from "@/components/app/DeleteProject";
import { ProjectCard } from "@/components/app/ProjectCard";
import { Alert, Eyebrow, btnSmall } from "@/components/app/ui";
import { forgeApi } from "@/lib/api/forge";
import type { ProjectListItem } from "@/lib/api/types";
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
  const queryClient = useQueryClient();
  const [toDelete, setToDelete] = useState<ProjectListItem | null>(null);
  const removal = useMutation({
    mutationFn: (project: ProjectListItem) => forgeApi.deleteProject(project.project_id),
    onSuccess: (_result, project) => {
      // Remove the card at once, drop everything cached for that project, then re-sync with the server.
      queryClient.setQueryData<ProjectListItem[]>(["projects"], (old) =>
        old?.filter((p) => p.project_id !== project.project_id),
      );
      queryClient.removeQueries({
        predicate: (q) => q.queryKey[0] !== "projects" && q.queryKey.includes(project.project_id),
      });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      setToDelete(null);
      toast.success("Project deleted successfully.");
    },
    onError: (error) => {
      toast.error(`Could not delete the project: ${error.message}`);
    },
  });

  const list = projects.data ?? [];

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:py-10">
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

      {system.data && !system.data.llm.llm_enabled && (
        <div className="mt-6">
          <Alert tone="info">
            Agents are running in rule-based mode (no LLM key configured on the server).
            Requirements are derived from your prompt by FORGE AI's analyzer; every build is still
            generated, tested and health-checked for real.
          </Alert>
        </div>
      )}

      <div className="mt-8">
        <StatsOverview />
      </div>

      <section className="mt-12">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-xl font-bold">
            Project history
            {projects.data && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                {list.length}
              </span>
            )}
          </h2>
          <button
            type="button"
            className={btnSmall}
            onClick={() => {
              void projects.refetch();
              void queryClient.invalidateQueries({ queryKey: ["stats"] });
            }}
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
          <div className="mt-6 grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            {list.map((p) => (
              <ProjectCard
                key={p.project_id}
                project={p}
                onDelete={() => {
                  removal.reset();
                  setToDelete(p);
                }}
              />
            ))}
          </div>
        )}
      </section>

      <DeleteProjectDialog
        open={toDelete !== null}
        projectName={toDelete?.name ?? null}
        pending={removal.isPending}
        error={removal.error ? removal.error.message : null}
        onCancel={() => {
          setToDelete(null);
          removal.reset();
        }}
        onConfirm={() => toDelete && removal.mutate(toDelete)}
      />
    </main>
  );
}
