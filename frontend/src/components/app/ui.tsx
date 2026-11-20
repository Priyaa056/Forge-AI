// Small building blocks for the signed-in screens, built from the Lovable landing/auth patterns.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { AgentStatus, RunStatus } from "@/lib/api/types";
import { STATUS_DOT } from "@/lib/agents";

/** Same input style as the original AuthForm. */
export const fieldClass =
  "w-full rounded-xl border bg-background px-4 py-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-ring/25";

/** Compact variant of the original primary/ghost buttons for toolbars. */
export const btnSmall =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border bg-card px-3 py-1.5 text-xs font-semibold transition hover:bg-muted disabled:opacity-60";
export const btnSmallPrimary =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-glow transition hover:bg-primary-hover disabled:opacity-60";

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-sm font-semibold uppercase tracking-widest text-primary">{children}</p>;
}

/** The browser-window frame from the landing hero ("forge.ai/workspace"). */
export function WindowFrame({
  label,
  actions,
  children,
  className,
}: {
  label: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-2xl border bg-card p-2 shadow-soft", className)}>
      <div className="flex flex-wrap items-center gap-1.5 border-b px-3 pb-2">
        <span className="size-2.5 rounded-full bg-muted-foreground/30" />
        <span className="size-2.5 rounded-full bg-muted-foreground/30" />
        <span className="size-2.5 rounded-full bg-muted-foreground/30" />
        <span className="ml-3 min-w-0 flex-1 truncate text-xs text-muted-foreground">{label}</span>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

export function StatusDot({ status, className }: { status: AgentStatus; className?: string }) {
  return (
    <span
      className={cn("inline-block size-2 shrink-0 rounded-full", STATUS_DOT[status], className)}
    />
  );
}

const RUN_STYLES: Record<RunStatus, { label: string; cls: string; dot: AgentStatus }> = {
  PENDING: { label: "Queued", cls: "bg-muted text-muted-foreground", dot: "PENDING" },
  RUNNING: { label: "Building", cls: "bg-accent text-accent-foreground", dot: "RUNNING" },
  COMPLETED: { label: "Completed", cls: "bg-success/12 text-success", dot: "COMPLETED" },
  FAILED: { label: "Failed", cls: "bg-destructive/10 text-destructive", dot: "FAILED" },
};

export function RunStatusPill({
  status,
  className,
}: {
  status: RunStatus | null | undefined;
  className?: string;
}) {
  const style = RUN_STYLES[status ?? "PENDING"];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        style.cls,
        className,
      )}
    >
      <StatusDot status={style.dot} />
      {style.label}
    </span>
  );
}

export function Alert({
  tone = "error",
  children,
}: {
  tone?: "error" | "info";
  children: ReactNode;
}) {
  return (
    <p
      role={tone === "error" ? "alert" : undefined}
      className={cn(
        "rounded-lg px-3 py-2 text-sm",
        tone === "error"
          ? "bg-destructive/10 text-destructive"
          : "bg-accent text-xs text-accent-foreground",
      )}
    >
      {children}
    </p>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed bg-background px-6 py-10 text-center">
      <h3 className="font-semibold">{title}</h3>
      {children && (
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{children}</p>
      )}
      {action && <div className="mt-5 flex justify-center">{action}</div>}
    </div>
  );
}
