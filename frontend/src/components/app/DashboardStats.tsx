// Dashboard analytics: metric tiles with 14-day sparklines, builds per day and time per agent.
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  FlaskConical,
  Rocket,
  Timer,
  type LucideIcon,
} from "lucide-react";
import { useId } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { AGENTS, formatDuration } from "@/lib/agents";
import { forgeApi } from "@/lib/api/forge";
import type { DashboardStats } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function StatsOverview() {
  const stats = useQuery({
    queryKey: ["stats"],
    queryFn: () => forgeApi.stats(14),
    refetchInterval: (query) => ((query.state.data?.running ?? 0) > 0 ? 3000 : false),
  });
  if (stats.isLoading || !stats.data) {
    return <StatsSkeleton failed={Boolean(stats.error)} />;
  }
  return <StatsView stats={stats.data} />;
}

export function StatsView({ stats }: { stats: DashboardStats }) {
  const daily = stats.daily;
  return (
    <div className="grid gap-4">
      {/* 5 tiles: one row on wide screens, 3 + 2 (full width) on laptops, 2 + 2 + 1 on tablets */}
      <div
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6 xl:grid-cols-5"
        aria-label="Key metrics"
      >
        <MetricTile
          className="lg:col-span-2 xl:col-span-1"
          icon={Activity}
          label="Builds"
          value={String(stats.builds)}
          delta={stats.builds_change_pct}
          deltaLabel="vs previous 7 days"
          series={daily.map((d) => d.builds)}
          hint={
            stats.running
              ? `${stats.running} running now`
              : `${stats.refinements} refinement${stats.refinements === 1 ? "" : "s"}`
          }
        />
        <MetricTile
          className="lg:col-span-2 xl:col-span-1"
          icon={CheckCircle2}
          label="Success rate"
          value={stats.success_rate === null ? "—" : `${Math.round(stats.success_rate)}%`}
          delta={stats.success_rate_change}
          deltaUnit="pts"
          deltaLabel="vs previous 7 days"
          series={daily.map((d) => d.success_rate)}
          hint={`${stats.succeeded} passed · ${stats.failed} failed`}
          tone="success"
        />
        <MetricTile
          className="lg:col-span-2 xl:col-span-1"
          icon={Timer}
          label="Avg build time"
          value={stats.avg_build_ms === null ? "—" : formatDuration(stats.avg_build_ms)}
          series={daily.map((d) => d.avg_build_ms)}
          hint="All seven agents, end to end"
        />
        <MetricTile
          className="lg:col-span-3 xl:col-span-1"
          icon={FlaskConical}
          label="Tests passed"
          value={stats.tests_passed.toLocaleString()}
          series={daily.map((d) => d.tests_passed)}
          hint={
            stats.tests_run
              ? `${Math.round((100 * stats.tests_passed) / stats.tests_run)}% of ${stats.tests_run.toLocaleString()} generated tests`
              : "Generated and executed by QA"
          }
        />
        <MetricTile
          className="sm:col-span-2 lg:col-span-3 xl:col-span-1"
          icon={Rocket}
          label="Live apps"
          value={String(stats.live_apps)}
          hint={`of ${stats.projects} project${stats.projects === 1 ? "" : "s"}`}
          progress={stats.projects ? stats.live_apps / stats.projects : 0}
          tone="success"
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <BuildsChart stats={stats} />
        <AgentTimes stats={stats} />
      </div>
    </div>
  );
}

function MetricTile({
  icon: Icon,
  label,
  value,
  hint,
  series,
  delta,
  deltaUnit = "%",
  deltaLabel,
  progress,
  tone = "primary",
  className,
}: {
  className?: string;
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  series?: (number | null)[];
  delta?: number | null;
  deltaUnit?: "%" | "pts";
  deltaLabel?: string;
  progress?: number;
  tone?: "primary" | "success";
}) {
  const color = tone === "success" ? "var(--success)" : "var(--primary)";
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-2xl border bg-card p-5 shadow-soft transition hover:-translate-y-0.5 hover:border-primary/50",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <span
          className={cn(
            "grid size-8 place-items-center rounded-lg",
            tone === "success" ? "bg-success/12 text-success" : "bg-primary/10 text-primary",
          )}
        >
          <Icon className="size-4" />
        </span>
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-display text-3xl font-bold tracking-tight">{value}</span>
        {delta !== undefined && delta !== null && (
          <span
            title={deltaLabel}
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold",
              delta >= 0 ? "bg-success/12 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {delta >= 0 ? (
              <ArrowUpRight className="size-3" />
            ) : (
              <ArrowDownRight className="size-3" />
            )}
            {Math.abs(delta)}
            {deltaUnit === "%" ? "%" : " pts"}
          </span>
        )}
      </div>
      {hint && <p className="mt-1 truncate text-xs text-muted-foreground">{hint}</p>}
      {series && <Sparkline values={series} color={color} className="mt-3 h-10 w-full" />}
      {progress !== undefined && (
        <div className="mt-5 h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
          <div
            className="h-full rounded-full bg-success transition-all"
            style={{ width: `${Math.round(progress * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

/** A tiny trend line (no axes). Missing days are drawn as gaps. */
export function Sparkline({
  values,
  color,
  className,
}: {
  values: (number | null)[];
  color: string;
  className?: string;
}) {
  const gradientId = useId().replace(/:/g, "");
  const known = values.filter((v): v is number => v !== null);
  if (values.length < 2 || known.length === 0) {
    return <div className={cn("rounded bg-muted/50", className)} aria-hidden />;
  }
  const max = Math.max(...known, 1);
  const min = Math.min(...known, 0);
  const span = max - min || 1;
  const step = 100 / (values.length - 1);
  const points = values.map((v, i) =>
    v === null ? null : ([i * step, 30 - ((v - min) / span) * 26 - 2] as const),
  );
  const segments: string[] = [];
  let current = "";
  points.forEach((p) => {
    if (!p) {
      if (current) segments.push(current);
      current = "";
      return;
    }
    current += `${current ? "L" : "M"}${p[0].toFixed(2)},${p[1].toFixed(2)} `;
  });
  if (current) segments.push(current);
  const firstKnown = points.find((p) => p);
  const lastKnown = [...points].reverse().find((p) => p);
  const line = segments.join(" ");
  const single = known.length === 1 && lastKnown ? lastKnown : null;
  const area =
    !single && firstKnown && lastKnown && segments.length === 1
      ? `${line} L${lastKnown[0].toFixed(2)},30 L${firstKnown[0].toFixed(2)},30 Z`
      : "";
  return (
    <svg
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      overflow="visible"
      className={className}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {single && (
        // One day of data: a faint baseline and a dot (a zero-length round-capped stroke stays round
        // although the SVG is stretched with preserveAspectRatio="none").
        <>
          <path
            d="M0,28 L100,28"
            stroke={color}
            strokeOpacity="0.25"
            strokeWidth="1"
            strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke"
            data-testid="sparkline-baseline"
          />
          <path
            d={`M${single[0].toFixed(2)},${single[1].toFixed(2)} L${single[0].toFixed(2)},${single[1].toFixed(2)}`}
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            data-testid="sparkline-dot"
          />
        </>
      )}
      {area && <path d={area} fill={`url(#${gradientId})`} />}
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

const chartConfig = {
  succeeded: { label: "Succeeded", color: "var(--success)" },
  failed: { label: "Failed", color: "var(--destructive)" },
} satisfies ChartConfig;

function BuildsChart({ stats }: { stats: DashboardStats }) {
  const data = stats.daily.map((d) => ({
    ...d,
    day: new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
    }),
  }));
  const total = stats.daily.reduce((n, d) => n + d.builds, 0);
  return (
    <section
      className="rounded-2xl border bg-card p-5 shadow-soft lg:col-span-2"
      aria-label="Builds per day"
    >
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="font-semibold">Builds per day</h3>
          <p className="text-xs text-muted-foreground">
            Last {stats.days} days · {total} builds
          </p>
        </div>
      </div>
      <ChartContainer config={chartConfig} className="mt-4 aspect-auto h-56 w-full">
        <BarChart data={data} margin={{ left: -20, right: 4, top: 4 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis
            dataKey="day"
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            minTickGap={16}
          />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={40} />
          <ChartTooltip cursor={{ fillOpacity: 0.4 }} content={<ChartTooltipContent />} />
          <ChartLegend content={<ChartLegendContent />} />
          <Bar
            dataKey="succeeded"
            stackId="builds"
            fill="var(--color-succeeded)"
            radius={[0, 0, 4, 4]}
          />
          <Bar dataKey="failed" stackId="builds" fill="var(--color-failed)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartContainer>
    </section>
  );
}

function AgentTimes({ stats }: { stats: DashboardStats }) {
  const rows = AGENTS.map((a) => ({ agent: a, ms: stats.agent_avg_ms[a.stage] ?? null }));
  const max = Math.max(...rows.map((r) => r.ms ?? 0), 1);
  return (
    <section
      className="rounded-2xl border bg-card p-5 shadow-soft"
      aria-label="Average time per agent"
    >
      <h3 className="font-semibold">Time per agent</h3>
      <p className="text-xs text-muted-foreground">Average over successful builds</p>
      <ul className="mt-4 grid gap-3">
        {rows.map(({ agent, ms }) => (
          <li
            key={agent.stage}
            className="grid grid-cols-[7.5rem_1fr_3.5rem] items-center gap-2 text-xs"
          >
            <span className="flex items-center gap-1.5 truncate font-medium">
              <agent.icon className="size-3.5 shrink-0 text-primary" />
              {agent.name.replace(" Agent", "")}
            </span>
            <span className="h-2 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-primary/80"
                style={{ width: ms ? `${Math.max(3, (100 * ms) / max)}%` : "0%" }}
              />
            </span>
            <span className="text-right tabular-nums text-muted-foreground">
              {ms === null ? "—" : formatDuration(ms)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function StatsSkeleton({ failed }: { failed: boolean }) {
  return (
    <div className="grid gap-4" aria-busy={!failed}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-2xl border bg-card" />
        ))}
      </div>
      {failed && (
        <p className="text-xs text-muted-foreground">Analytics are unavailable right now.</p>
      )}
    </div>
  );
}
