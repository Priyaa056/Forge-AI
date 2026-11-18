import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Ban,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  HelpCircle,
  Loader2,
  RefreshCw,
  X,
  XCircle,
} from 'lucide-react';
import { cn, copyToClipboard } from '../lib/utils';

// ------------------------------------------------------------------ status badges
const STATUS_STYLES: Record<string, { cls: string; icon: React.ComponentType<{ className?: string }>; spin?: boolean }> = {
  PENDING: { cls: 'bg-slate-900 border-slate-700/80 text-slate-400', icon: Clock },
  RUNNING: { cls: 'bg-blue-950/80 border-blue-700/80 text-blue-300 pulse-subtle', icon: Loader2, spin: true },
  RETRYING: { cls: 'bg-amber-950/80 border-amber-700/80 text-amber-300', icon: RefreshCw, spin: true },
  COMPLETED: { cls: 'bg-emerald-950/80 border-emerald-800/80 text-emerald-400', icon: CheckCircle2 },
  FAILED: { cls: 'bg-rose-950/80 border-rose-800/80 text-rose-400', icon: XCircle },
  SKIPPED: { cls: 'bg-slate-900/60 border-slate-800 text-slate-600', icon: Ban },
  UNKNOWN: { cls: 'bg-slate-900 border-slate-800 text-slate-500', icon: HelpCircle },
};

export function statusTone(status: string | null | undefined): string {
  return (STATUS_STYLES[status ?? 'UNKNOWN'] ?? STATUS_STYLES.UNKNOWN).cls;
}

export const StatusBadge: React.FC<{ status: string | null | undefined; size?: 'xs' | 'sm'; className?: string }> = ({
  status,
  size = 'sm',
  className,
}) => {
  const key = status && STATUS_STYLES[status] ? status : 'UNKNOWN';
  const style = STATUS_STYLES[key];
  const Icon = style.icon;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border font-semibold whitespace-nowrap',
        size === 'xs' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        style.cls,
        className,
      )}
    >
      <Icon className={cn(size === 'xs' ? 'w-3 h-3' : 'w-3.5 h-3.5', style.spin && 'animate-spin')} />
      {status ?? 'UNKNOWN'}
    </span>
  );
};

/** Badge for lower-case result strings used in QA / deploy reports (passed, failed, healthy, success...). */
export const ResultBadge: React.FC<{ value: string | null | undefined; className?: string }> = ({ value, className }) => {
  const v = (value ?? 'unknown').toLowerCase();
  const good = ['passed', 'pass', 'success', 'healthy', 'ok', 'completed', 'ready'].includes(v);
  const bad = ['failed', 'fail', 'error', 'unhealthy', 'critical'].includes(v);
  const warn = ['skipped', 'warning', 'partial'].includes(v);
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-md border text-[11px] font-semibold font-mono whitespace-nowrap',
        good && 'bg-emerald-950/70 border-emerald-800/70 text-emerald-400',
        bad && 'bg-rose-950/70 border-rose-800/70 text-rose-400',
        warn && 'bg-slate-900 border-slate-700 text-slate-400',
        !good && !bad && !warn && 'bg-slate-900 border-slate-700 text-slate-300',
        className,
      )}
    >
      {value ?? 'unknown'}
    </span>
  );
};

// ------------------------------------------------------------------ layout primitives
export const Panel: React.FC<{
  title?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}> = ({ title, icon, actions, className, bodyClassName, children }) => (
  <section className={cn('glass-panel rounded-2xl border border-slate-800 shadow-lg min-w-0', className)}>
    {(title || actions) && (
      <div className="px-4 sm:px-5 py-3.5 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2 min-w-0">
          {icon}
          <span className="truncate">{title}</span>
        </h2>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    )}
    <div className={cn('p-4 sm:p-5', bodyClassName)}>{children}</div>
  </section>
);

export const Spinner: React.FC<{ className?: string; label?: string }> = ({ className, label }) => (
  <span className={cn('inline-flex items-center gap-2 text-xs text-slate-400', className)}>
    <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
    {label}
  </span>
);

export const EmptyState: React.FC<{ icon?: React.ReactNode; title: string; hint?: React.ReactNode; className?: string }> = ({
  icon,
  title,
  hint,
  className,
}) => (
  <div className={cn('p-6 sm:p-8 text-center border border-dashed border-slate-800 rounded-xl', className)}>
    {icon && <div className="flex justify-center mb-2 text-slate-600">{icon}</div>}
    <p className="text-sm text-slate-400">{title}</p>
    {hint && <div className="text-xs text-slate-500 mt-1">{hint}</div>}
  </div>
);

export const ErrorNote: React.FC<{ message: string; onDismiss?: () => void; className?: string; title?: string }> = ({
  message,
  onDismiss,
  className,
  title,
}) => (
  <div
    role="alert"
    className={cn(
      'p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-200 text-xs flex items-start gap-2.5',
      className,
    )}
  >
    <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
    <div className="flex-1 min-w-0 break-words">
      {title && <p className="font-semibold mb-0.5">{title}</p>}
      <p className="whitespace-pre-wrap">{message}</p>
    </div>
    {onDismiss && (
      <button onClick={onDismiss} className="text-rose-400 hover:text-rose-200 shrink-0" aria-label="Dismiss">
        <X className="w-4 h-4" />
      </button>
    )}
  </div>
);

export const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'warning' | 'ghost'; size?: 'sm' | 'md' }
> = ({ variant = 'secondary', size = 'sm', className, children, ...rest }) => (
  <button
    {...rest}
    className={cn(
      'inline-flex items-center justify-center gap-1.5 rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap',
      size === 'sm' ? 'px-3 py-1.5 text-xs' : 'px-4 py-2 text-sm',
      variant === 'primary' &&
        'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-600/20',
      variant === 'secondary' && 'bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-200',
      variant === 'danger' && 'bg-rose-950/70 hover:bg-rose-900/70 border border-rose-800/70 text-rose-200',
      variant === 'warning' && 'bg-amber-600 hover:bg-amber-500 text-slate-950 font-semibold',
      variant === 'ghost' && 'text-slate-400 hover:text-white hover:bg-slate-800/80',
      className,
    )}
  >
    {children}
  </button>
);

export const CopyButton: React.FC<{ text: string; label?: string; className?: string }> = ({ text, label, className }) => {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => {
    if (state === 'idle') return;
    const t = setTimeout(() => setState('idle'), 1800);
    return () => clearTimeout(t);
  }, [state]);
  return (
    <button
      type="button"
      onClick={async () => setState((await copyToClipboard(text)) ? 'copied' : 'failed')}
      className={cn(
        'inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-[11px] font-medium transition-colors shrink-0',
        className,
      )}
      title={label ? `Copy ${label}` : 'Copy'}
    >
      {state === 'copied' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
      <span>{state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : 'Copy'}</span>
    </button>
  );
};

// ------------------------------------------------------------------ modal shell
export const Modal: React.FC<{
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  icon?: React.ReactNode;
  headerActions?: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}> = ({ open, onClose, title, subtitle, icon, headerActions, footer, size = 'lg', children }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/80 backdrop-blur-md"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={cn(
          'glass-panel rounded-2xl border border-slate-700/80 w-full max-h-[92vh] flex flex-col shadow-2xl overflow-hidden',
          size === 'md' && 'max-w-lg',
          size === 'lg' && 'max-w-3xl',
          size === 'xl' && 'max-w-5xl',
        )}
      >
        <div className="px-4 sm:px-6 py-4 border-b border-slate-800 flex items-start justify-between gap-3 bg-slate-900/60">
          <div className="flex items-start gap-3 min-w-0">
            {icon}
            <div className="min-w-0">
              <h3 className="text-base font-bold text-white break-words">{title}</h3>
              {subtitle && <div className="text-xs text-slate-400 font-mono mt-0.5 break-all">{subtitle}</div>}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {headerActions}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
        <div className="overflow-y-auto flex-1 min-h-0">{children}</div>
        {footer && (
          <div className="px-4 sm:px-6 py-3 border-t border-slate-800 bg-slate-900/60 flex flex-wrap justify-end items-center gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export const Tooltip: React.FC<{ text: string; children: React.ReactNode; className?: string }> = ({
  text,
  children,
  className,
}) => (
  <span className={cn('relative group inline-flex', className)} aria-label={text} tabIndex={0}>
    {children}
    <span
      role="tooltip"
      className="pointer-events-none absolute right-0 top-full mt-2 z-50 w-72 max-w-[80vw] rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-[11px] leading-relaxed text-slate-200 shadow-xl opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity font-sans"
    >
      {text}
    </span>
  </span>
);
