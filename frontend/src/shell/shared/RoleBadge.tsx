import type { RoleTheme } from "./ColorThemes";

export function RoleBadge({ theme, name }: { theme: RoleTheme; name: string }) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide"
      style={{ background: theme.accent, color: "#1f2937" }}
      data-role={theme.label.toLowerCase()}
    >
      <span>{theme.label}</span>
      <span aria-hidden>·</span>
      <span>{name}</span>
    </div>
  );
}
