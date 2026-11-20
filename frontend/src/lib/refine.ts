// Helpers for iterative refinement (example change requests, labels).
import type { StageName } from "./api/types";

/** Example change requests built from the app's own modules, so they apply as written. */
export function refineExamples(moduleLabels: string[]): string[] {
  const labels = moduleLabels.filter(Boolean);
  const first = labels[0]?.toLowerCase();
  const second = labels[1]?.toLowerCase();
  const last = labels[labels.length - 1];
  const examples: string[] = [];
  if (first) examples.push(`Add a notes field to ${first}`);
  if (first && second)
    examples.push(`Add a manager role who can manage ${first} but not ${second}`);
  if (last && labels.length > 1) examples.push(`Remove the ${last} module`);
  examples.push("Change the primary colour to green");
  return examples;
}

export const ACTION_LABEL: Record<string, string> = {
  plan: "Planned",
  update: "Updated",
  "update (impact check)": "Updated (impact check)",
  reuse: "Reused",
  reused: "Reused",
  validate: "Validated",
  package: "Packaged",
};

export const AREA_LABEL: Record<string, string> = {
  project: "App name",
  theme: "Theme",
  entity: "Records",
  field: "Field",
  module: "Module",
  role: "Role",
  permission: "Permissions",
  workflow: "Workflow",
  rule: "Rule",
  metric: "Dashboard",
  seed: "Data",
};

export const AGENT_SHORT: Record<StageName, string> = {
  pm: "PM",
  ui: "UI",
  backend: "Backend",
  db: "Database",
  auth: "Auth",
  qa: "QA",
  deploy: "Deploy",
};
