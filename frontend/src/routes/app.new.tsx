import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import robot from "@/assets/robot.png";
import { PromptForm } from "@/components/app/PromptForm";
import { Eyebrow, StatusDot, WindowFrame } from "@/components/app/ui";
import { AGENTS } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";

export const Route = createFileRoute("/app/new")({
  head: () => ({ meta: [{ title: "New project — FORGE AI" }] }),
  component: NewProject,
});

function NewProject() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const system = useQuery({ queryKey: ["system"], queryFn: forgeApi.system, staleTime: 60_000 });

  return (
    <main className="overflow-x-hidden bg-grid">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <Eyebrow>New project</Eyebrow>
        <h1 className="mt-2 max-w-2xl text-3xl font-bold md:text-4xl">
          Describe your idea. The agents take it from there.
        </h1>

        <div className="relative mt-10">
          <img
            src={robot}
            alt="FORGE AI robot mascot"
            width={816}
            height={816}
            className="animate-float absolute -right-4 -top-20 z-10 hidden w-28 md:block lg:-right-10 lg:w-36"
          />
          <WindowFrame label="forge.ai/workspace/new">
            <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-[1.3fr_1fr]">
              <PromptForm
                mode="project"
                faultInjection={Boolean(system.data?.fault_injection_enabled)}
                onSubmit={async ({ prompt, projectName, simulateFailure }) => {
                  const { project_id, run_id } = await forgeApi.createProject(
                    prompt,
                    projectName,
                    simulateFailure,
                  );
                  await queryClient.invalidateQueries({ queryKey: ["projects"] });
                  await navigate({
                    to: "/app/projects/$projectId",
                    params: { projectId: project_id },
                    search: { run: run_id },
                  });
                }}
              />
              <div className="space-y-2">
                <p className="text-xs font-semibold text-muted-foreground">WHAT HAPPENS NEXT</p>
                {AGENTS.map((a) => (
                  <div
                    key={a.stage}
                    className="flex items-center gap-3 rounded-lg border bg-background px-3 py-2 text-sm"
                  >
                    <a.icon className="size-4 text-primary" />
                    <span className="flex-1">
                      {a.name}
                      <span className="block text-xs text-muted-foreground">{a.does}</span>
                    </span>
                    <StatusDot status="PENDING" />
                  </div>
                ))}
              </div>
            </div>
          </WindowFrame>
        </div>
      </div>
    </main>
  );
}
