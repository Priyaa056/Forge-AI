// Signed-in app layout: sidebar navigation, a top bar with search (Ctrl/Cmd+K) and the account menu.
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { FolderGit2, LayoutDashboard, LogOut, Menu, Plus, Search, Sparkles } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Logo, ThemeToggle, btnPrimary } from "@/components/brand";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { forgeApi } from "@/lib/api/forge";
import type { ProjectListItem } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { iconGradient, initials, projectColor } from "@/lib/projects";
import { cn } from "@/lib/utils";
import { StatusDot } from "./ui";

const STATUS_TO_DOT = {
  COMPLETED: "COMPLETED",
  FAILED: "FAILED",
  RUNNING: "RUNNING",
  PENDING: "PENDING",
} as const;

export function AppShell({ children }: { children: ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen">
      <aside
        className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r bg-card/80 backdrop-blur lg:flex"
        aria-label="Main navigation"
      >
        <SidebarContent />
      </aside>
      <Sheet open={drawer} onOpenChange={setDrawer}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <div className="flex h-full flex-col">
            <SidebarContent />
          </div>
        </SheetContent>
      </Sheet>
      <div className="lg:pl-64">
        <TopBar onMenu={() => setDrawer(true)} onSearch={() => setPalette(true)} />
        {children}
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} />
    </div>
  );
}

function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: forgeApi.listProjects, staleTime: 5_000 });
}

function SidebarContent() {
  const projects = useProjects();
  const system = useQuery({ queryKey: ["system"], queryFn: forgeApi.system, staleTime: 60_000 });
  const recent = (projects.data ?? []).slice(0, 6);
  const navItem =
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground";
  const navActive = "bg-accent text-accent-foreground hover:bg-accent";

  return (
    <>
      <div className="flex h-16 shrink-0 items-center border-b px-5">
        <Logo />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto overflow-x-hidden px-3 py-5">
        <Link to="/app/new" className={cn(btnPrimary, "w-full px-4 py-2")}>
          <Plus className="size-4" /> New project
        </Link>
        <nav className="grid gap-1">
          <Link
            to="/app"
            activeOptions={{ exact: true }}
            className={navItem}
            activeProps={{ className: navActive }}
          >
            <LayoutDashboard className="size-4" /> Dashboard
          </Link>
          <Link to="/app/new" className={navItem} activeProps={{ className: navActive }}>
            <Sparkles className="size-4" /> Build an app
          </Link>
        </nav>
        <div className="min-w-0">
          <p className="flex items-center justify-between px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Recent projects</span>
            {projects.data && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] normal-case tracking-normal">
                {projects.data.length}
              </span>
            )}
          </p>
          <ul className="mt-2 grid min-w-0 gap-0.5">
            {recent.map((p) => (
              <li key={p.project_id} className="min-w-0">
                <Link
                  to="/app/projects/$projectId"
                  params={{ projectId: p.project_id }}
                  title={p.name}
                  className={cn(navItem, "min-w-0 py-1.5")}
                  activeProps={{ className: navActive }}
                >
                  <ProjectIcon project={p} size="sm" />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <StatusDot status={STATUS_TO_DOT[p.last_status ?? "PENDING"]} />
                </Link>
              </li>
            ))}
            {projects.data && recent.length === 0 && (
              <li className="px-3 py-2 text-xs text-muted-foreground">No projects yet.</li>
            )}
          </ul>
        </div>
      </div>
      <div className="shrink-0 border-t p-3">
        <div className="rounded-xl border bg-background/60 p-3 text-xs">
          <p className="flex items-center gap-2 font-semibold">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
            7 agents ready
          </p>
          <p className="mt-1 text-muted-foreground">
            {system.data
              ? system.data.llm.llm_enabled
                ? `LLM mode · ${system.data.llm.provider ?? "LLM"}`
                : "Rule-based mode"
              : "Connecting…"}
          </p>
        </div>
      </div>
    </>
  );
}

export function ProjectIcon({
  project,
  size = "md",
}: {
  project: Pick<ProjectListItem, "name" | "project_id" | "theme_color">;
  size?: "sm" | "md";
}) {
  const color = projectColor(project.theme_color, project.project_id);
  return (
    <span
      aria-hidden
      className={cn(
        "grid shrink-0 place-items-center font-display font-bold text-white shadow-sm",
        size === "sm" ? "size-6 rounded-md text-[10px]" : "size-11 rounded-xl text-sm",
      )}
      style={{ backgroundImage: iconGradient(color) }}
    >
      {initials(project.name)}
    </span>
  );
}

function TopBar({ onMenu, onSearch }: { onMenu: () => void; onSearch: () => void }) {
  return (
    <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        <button
          type="button"
          onClick={onMenu}
          className="grid size-9 place-items-center rounded-lg border bg-card text-muted-foreground transition hover:text-foreground lg:hidden"
          aria-label="Open navigation"
        >
          <Menu className="size-4" />
        </button>
        <div className="lg:hidden">
          <Logo />
        </div>
        <button
          type="button"
          onClick={onSearch}
          className="ml-auto flex h-9 min-w-0 items-center gap-2 rounded-lg border bg-card px-3 text-sm text-muted-foreground transition hover:border-primary hover:text-foreground sm:w-72 lg:ml-0 lg:w-96"
          aria-label="Search projects and actions"
        >
          <Search className="size-4 shrink-0" />
          <span className="hidden flex-1 truncate text-left sm:inline">Search projects…</span>
          <kbd className="hidden rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] sm:inline">
            Ctrl K
          </kbd>
        </button>
        <div className="flex items-center gap-2 lg:ml-auto">
          <ThemeToggle />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}

function AccountMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const name = user?.full_name || user?.email || "Account";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Account menu"
        className="grid size-9 place-items-center rounded-full font-display text-xs font-bold text-white ring-offset-background transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        style={{ backgroundImage: iconGradient("#7c3aed") }}
      >
        {initials(name)}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60 rounded-xl p-1.5">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-semibold">{user?.full_name || "Signed in"}</p>
          <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => void navigate({ to: "/app" })}
          className="gap-2 rounded-lg"
        >
          <LayoutDashboard className="size-4" /> Dashboard
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => void navigate({ to: "/app/new" })}
          className="gap-2 rounded-lg"
        >
          <Plus className="size-4" /> New project
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={async () => {
            // Leave the guarded /app area first so the guard does not redirect to /login.
            await navigate({ to: "/" });
            logout();
          }}
          className="gap-2 rounded-lg text-destructive focus:bg-destructive/10 focus:text-destructive"
        >
          <LogOut className="size-4" /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const projects = useProjects();
  const navigate = useNavigate();
  const go = (to: () => Promise<void>) => {
    onOpenChange(false);
    void to();
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100%-2rem)] overflow-hidden rounded-2xl p-0 sm:max-w-lg">
        <DialogTitle className="sr-only">Search projects and actions</DialogTitle>
        <Command className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:gap-2 [&_[cmdk-item]]:rounded-lg [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-2.5">
          <CommandInput placeholder="Search projects or actions…" />
          <CommandList>
            <CommandEmpty>No matching projects.</CommandEmpty>
            <CommandGroup heading="Actions">
              <CommandItem onSelect={() => go(() => navigate({ to: "/app/new" }))}>
                <Plus className="size-4" /> New project
              </CommandItem>
              <CommandItem onSelect={() => go(() => navigate({ to: "/app" }))}>
                <LayoutDashboard className="size-4" /> Dashboard
              </CommandItem>
            </CommandGroup>
            <CommandGroup heading="Projects">
              {(projects.data ?? []).map((p) => (
                <CommandItem
                  key={p.project_id}
                  value={`${p.name} ${p.project_id} ${(p.modules ?? []).join(" ")}`}
                  onSelect={() =>
                    go(() =>
                      navigate({
                        to: "/app/projects/$projectId",
                        params: { projectId: p.project_id },
                      }),
                    )
                  }
                >
                  <ProjectIcon project={p} size="sm" />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {p.current_version ? `v${p.current_version}` : "no live version"}
                  </span>
                </CommandItem>
              ))}
              {projects.data && projects.data.length === 0 && (
                <CommandItem disabled>
                  <FolderGit2 className="size-4" /> No projects yet
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
