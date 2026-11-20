// Delete action for a project card: a ⋮ menu with "Delete Project" and a confirmation dialog.
import { Loader2, MoreVertical, Trash2 } from "lucide-react";
import { btnGhost } from "@/components/brand";
import { Alert } from "@/components/app/ui";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/** The ⋮ button in a card's top-right corner. Rendered beside the card link, never inside it. */
export function ProjectActionsMenu({
  projectName,
  onDelete,
  className,
}: {
  projectName: string;
  onDelete: () => void;
  className?: string;
}) {
  return (
    // Non-modal so the confirmation dialog can take focus as soon as the menu closes.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger
        aria-label={`Project actions for ${projectName}`}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 data-[state=open]:bg-muted data-[state=open]:text-foreground",
          className,
        )}
      >
        <MoreVertical className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[11rem] rounded-xl p-1.5">
        <DropdownMenuItem
          onSelect={onDelete}
          className="cursor-pointer gap-2 rounded-lg px-2.5 py-2 font-medium text-destructive focus:bg-destructive/10 focus:text-destructive"
        >
          <Trash2 className="size-4" /> Delete Project
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** "Are you sure?" dialog. Stays open (showing the error) if the deletion fails. */
export function DeleteProjectDialog({
  projectName,
  open,
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  projectName: string | null;
  open: boolean;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !pending) onCancel();
      }}
    >
      <AlertDialogContent className="rounded-2xl">
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{projectName}”?</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete this project? This action cannot be undone.
          </AlertDialogDescription>
          <p className="text-sm text-muted-foreground">
            Every build, version, generated file and preview of{" "}
            <span className="font-semibold text-foreground">{projectName}</span> is permanently
            removed. Your other projects are not affected.
          </p>
        </AlertDialogHeader>
        {error && <Alert>{error}</Alert>}
        <AlertDialogFooter className="gap-2">
          <AlertDialogCancel className={cn(btnGhost, "mt-0 h-auto")} disabled={pending}>
            Cancel
          </AlertDialogCancel>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-destructive px-5 py-2.5 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90 disabled:opacity-60"
          >
            {pending ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            {pending ? "Deleting…" : "Delete"}
          </button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
