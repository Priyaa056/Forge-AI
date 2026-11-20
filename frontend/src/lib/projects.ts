// Presentation helpers for projects (initials, app colours) and people (avatar initials).

const FALLBACK_COLORS = [
  "#7c3aed",
  "#2563eb",
  "#0d9488",
  "#db2777",
  "#ea580c",
  "#4f46e5",
  "#16a34a",
  "#0891b2",
];

/** Up to two initials of a project or person name ("Library Management System" -> "LM"). */
export function initials(name: string | null | undefined): string {
  const words = (name ?? "")
    .replace(/[^\p{L}\p{N}\s@._-]/gu, " ")
    .split(/[\s@._-]+/)
    .filter(Boolean);
  if (!words.length) return "?";
  const first = words[0] ?? "";
  const second = words[1] ?? "";
  return (first[0] + (second[0] ?? first[1] ?? "")).toUpperCase();
}

/** The generated app's own colour, or a stable colour derived from the project id. */
export function projectColor(themeColor: string | null | undefined, seed: string): string {
  if (themeColor && /^#[0-9a-fA-F]{6}$/.test(themeColor)) return themeColor;
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return FALLBACK_COLORS[hash % FALLBACK_COLORS.length] ?? "#7c3aed";
}

/** A soft gradient for app icons and avatars. */
export function iconGradient(color: string): string {
  return `linear-gradient(135deg, ${color} 0%, color-mix(in oklab, ${color} 65%, black) 100%)`;
}
