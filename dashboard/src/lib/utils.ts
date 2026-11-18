import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { ExecutionStatus, Promotion, RunSummary } from '../types';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return '--';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s - m * 60);
  return `${m}m ${rest.toString().padStart(2, '0')}s`;
}

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatTime(value: string | null | undefined): string {
  const d = toDate(value);
  if (!d) return '--';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

export function formatDateTime(value: string | null | undefined): string {
  const d = toDate(value);
  if (!d) return '--';
  return d.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function formatRelative(value: string | null | undefined): string {
  const d = toDate(value);
  if (!d) return '--';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 45) return 'just now';
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.round(diff / 86400)} d ago`;
  return d.toLocaleDateString();
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '--';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function isRunActive(status: ExecutionStatus | string | null | undefined): boolean {
  return status === 'PENDING' || status === 'RUNNING';
}

/** True while the dashboard should keep polling a run (still executing or waiting for promotion). */
export function needsPolling(summary: Pick<RunSummary, 'execution_status' | 'promotion'> | null): boolean {
  if (!summary) return true;
  return isRunActive(summary.execution_status) || summary.promotion?.state === 'pending';
}

export function promotionLabel(p: Promotion | null | undefined): string {
  switch (p?.state) {
    case 'pending':
      return 'Promotion pending';
    case 'promoted':
      return p.version != null ? `Promoted to v${p.version}` : 'Promoted';
    case 'failed':
      return 'Promotion failed';
    default:
      return 'Not promoted';
  }
}

export function shortId(id: string | null | undefined, len = 8): string {
  if (!id) return '--';
  return id.length > len + 4 ? `${id.slice(0, len)}...` : id;
}

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the legacy path
  }
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.setAttribute('readonly', '');
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}
