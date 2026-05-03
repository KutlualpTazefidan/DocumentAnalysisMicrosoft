export const ADMIN_THEME = {
  chrome: "#1e3a8a",
  chromeFg: "#ffffff",
  accent: "#fbbf24",
  label: "ADMIN",
} as const;

export const CURATOR_THEME = {
  chrome: "#065f46",
  chromeFg: "#ffffff",
  accent: "#6ee7b7",
  label: "CURATOR",
} as const;

export type RoleTheme = typeof ADMIN_THEME | typeof CURATOR_THEME;
