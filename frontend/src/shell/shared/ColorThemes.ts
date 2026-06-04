// BAM light chrome. `chrome`/`chromeFg` are legacy fields (the header is now
// white via BamHeader); `accent` drives the RoleMenu pill — cyan for ADMIN.
export const ADMIN_THEME = {
  chrome: "#ffffff",
  chromeFg: "#002832",
  accent: "#00aff0",
  label: "ADMIN",
} as const;

export const CURATOR_THEME = {
  chrome: "#065f46",
  chromeFg: "#ffffff",
  accent: "#6ee7b7",
  label: "CURATOR",
} as const;

export type RoleTheme = typeof ADMIN_THEME | typeof CURATOR_THEME;
