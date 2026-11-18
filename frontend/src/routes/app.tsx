import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import robot from "@/assets/robot.png";
import { AppHeader } from "@/components/app/AppHeader";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/app")({
  // Signed-in area: the session lives in the browser, so these pages render on the client.
  ssr: false,
  head: () => ({ meta: [{ title: "Dashboard — FORGE AI" }] }),
  component: AppLayout,
});

function AppLayout() {
  const { status } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (status === "anonymous") void navigate({ to: "/login" });
  }, [status, navigate]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-screen place-items-center bg-grid">
        <div className="text-center">
          <img src={robot} alt="" width={816} height={816} className="animate-float mx-auto w-24" />
          <p className="mt-4 text-sm text-muted-foreground">
            {status === "loading" ? "Loading your workspace…" : "Redirecting to log in…"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <Outlet />
    </div>
  );
}
