// Helpers for the "Push to GitHub" dialog.

export const REPO_NAME = /^[A-Za-z0-9._-]{1,100}$/;
export const FULL_NAME = /^[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9._-]{1,100}$/;
/** GitHub's "new classic token" page with the repo scope preselected. */
export const TOKEN_URL =
  "https://github.com/settings/tokens/new?scopes=repo&description=FORGE%20AI";

/** A valid GitHub repository name derived from the project name. */
export function repoSlug(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^[-.]+|[-.]+$/g, "")
      .slice(0, 100) || "forge-app"
  );
}
