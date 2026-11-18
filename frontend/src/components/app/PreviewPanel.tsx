import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  Play,
  RotateCw,
  Square,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { forgeApi } from "@/lib/api/forge";
import { Alert, EmptyState, WindowFrame, btnSmall, btnSmallPrimary } from "./ui";

/** Live preview of the generated app, styled like the landing page's "Generated preview" frame. */
export function PreviewPanel({
  projectId,
  slug,
  currentVersion,
}: {
  projectId: string;
  slug: string;
  currentVersion: number | null;
}) {
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const status = useQuery({
    queryKey: ["preview", projectId],
    queryFn: () => forgeApi.previewStatus(projectId),
  });
  const refresh = (data: Awaited<ReturnType<typeof forgeApi.previewStatus>>) =>
    queryClient.setQueryData(["preview", projectId], data);
  const start = useMutation({
    mutationFn: () => forgeApi.startPreview(projectId),
    onSuccess: refresh,
  });
  const stop = useMutation({
    mutationFn: () => forgeApi.stopPreview(projectId),
    onSuccess: refresh,
  });
  const download = useMutation({ mutationFn: () => forgeApi.downloadZip(projectId, "current") });

  if (!currentVersion) {
    return (
      <EmptyState title="No live version yet">
        A preview becomes available after a build passes QA and the deploy health check.
      </EmptyState>
    );
  }

  const preview = status.data;
  const running = Boolean(preview?.running && preview.url);
  const busy = start.isPending || stop.isPending;
  const copy = (value: string, label: string) => {
    void navigator.clipboard.writeText(value).then(() => toast.success(`${label} copied`));
  };

  return (
    <div className="space-y-4">
      <WindowFrame
        label={`Preview · ${slug} · v${preview?.version ?? currentVersion}`}
        actions={
          <>
            {running && preview?.url ? (
              <a href={preview.url} target="_blank" rel="noreferrer" className={btnSmall}>
                <ExternalLink className="size-3.5" /> Open
              </a>
            ) : (
              <button
                type="button"
                className={btnSmallPrimary}
                disabled={busy}
                onClick={() => start.mutate()}
              >
                {start.isPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Play className="size-3.5" />
                )}{" "}
                Start preview
              </button>
            )}
            {running && (
              <>
                <button
                  type="button"
                  className={btnSmall}
                  disabled={busy}
                  onClick={() => start.mutate()}
                >
                  <RotateCw className={`size-3.5 ${start.isPending ? "animate-spin" : ""}`} />{" "}
                  Restart
                </button>
                <button
                  type="button"
                  className={btnSmall}
                  disabled={busy}
                  onClick={() => stop.mutate()}
                >
                  <Square className="size-3.5" /> Stop
                </button>
              </>
            )}
            <button
              type="button"
              className={btnSmall}
              disabled={download.isPending}
              onClick={() => download.mutate()}
            >
              {download.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Download className="size-3.5" />
              )}{" "}
              Download ZIP
            </button>
          </>
        }
      >
        {running && preview?.url ? (
          <iframe
            title="Generated application preview"
            src={preview.url}
            className="h-[38rem] w-full rounded-b-xl bg-background"
          />
        ) : (
          <div className="grid place-items-center px-6 py-16 text-center">
            <div>
              <p className="font-semibold">
                {start.isPending ? "Starting the generated app…" : "Preview is stopped"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Starts the active version (its own API and React frontend) on a local port.
              </p>
            </div>
          </div>
        )}
      </WindowFrame>

      {(start.error || stop.error || download.error || status.error) && (
        <Alert>{(start.error ?? stop.error ?? download.error ?? status.error)?.message}</Alert>
      )}
      {preview?.stale && (
        <Alert tone="info">
          The preview is running an older version — restart it to load v{currentVersion}.
        </Alert>
      )}
      {preview?.message && <Alert tone="info">{preview.message}</Alert>}

      {preview && (
        <div className="rounded-2xl border bg-card p-5">
          <h3 className="font-semibold">Sign in to the generated app</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Local-only administrator account seeded into this preview. It is not your FORGE AI
            login.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="flex items-center justify-between gap-2 rounded-lg border bg-background px-3 py-2 text-sm">
              <span className="truncate font-mono">{preview.admin_email}</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => copy(preview.admin_email, "Email")}
                aria-label="Copy email"
              >
                <Copy className="size-4" />
              </button>
            </div>
            <div className="flex items-center justify-between gap-2 rounded-lg border bg-background px-3 py-2 text-sm">
              <span className="truncate font-mono">
                {showPassword ? preview.admin_password : "••••••••••••"}
              </span>
              <span className="flex gap-2">
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() => copy(preview.admin_password, "Password")}
                  aria-label="Copy password"
                >
                  <Copy className="size-4" />
                </button>
              </span>
            </div>
          </div>
          {preview.log_tail && (
            <details className="mt-4 text-xs">
              <summary className="cursor-pointer text-muted-foreground">Preview server log</summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded-lg border bg-background p-3 font-mono">
                {preview.log_tail}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
