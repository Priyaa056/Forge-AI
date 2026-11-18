import { Link, useNavigate } from "@tanstack/react-router";
import { LogOut, Plus } from "lucide-react";
import { Logo, ThemeToggle, btnPrimary } from "@/components/brand";
import { useAuth } from "@/lib/auth";
import { btnSmall } from "./ui";

/** Signed-in header: same sticky, blurred bar as the landing page. */
export function AppHeader() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-6">
        <div className="flex min-w-0 items-center gap-8">
          <div className="shrink-0">
            <Logo />
          </div>
          <nav className="hidden gap-6 text-sm text-muted-foreground md:flex">
            <Link
              to="/app"
              activeOptions={{ exact: true }}
              className="hover:text-foreground"
              activeProps={{ className: "font-semibold text-foreground" }}
            >
              Dashboard
            </Link>
            <Link
              to="/app/new"
              className="hover:text-foreground"
              activeProps={{ className: "font-semibold text-foreground" }}
            >
              New project
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden sm:block">
            <Link to="/app/new" className={`${btnPrimary} px-4 py-2`}>
              <Plus className="size-4" /> New project
            </Link>
          </span>
          <Link to="/app/new" className={`${btnSmall} sm:hidden`} aria-label="New project">
            <Plus className="size-3.5" />
          </Link>
          <ThemeToggle />
          <span
            className="hidden max-w-[12rem] truncate text-sm text-muted-foreground lg:block"
            title={user?.email}
          >
            {user?.email}
          </span>
          <button
            type="button"
            onClick={async () => {
              // Leave the guarded /app area first so the guard does not redirect to /login.
              await navigate({ to: "/" });
              logout();
            }}
            className={btnSmall}
            aria-label="Log out"
          >
            <LogOut className="size-3.5" /> <span className="hidden sm:inline">Log out</span>
          </button>
        </div>
      </div>
    </header>
  );
}
