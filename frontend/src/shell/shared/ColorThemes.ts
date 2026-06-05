// BAM light chrome. `chrome`/`chromeFg` are legacy fields (the header is now
// white via BamHeader); `accent` drives the RoleMenu pill — cyan for ADMIN.
export const ADMIN_THEME = {
  chrome: "#ffffff",
  chromeFg: "#002832",
  accent: "#00aff0",
  label: "ADMIN",
} as const;

// CURATOR shares the BAM light chrome; the role pill uses a distinct teal
// accent so admin (cyan) and curator (teal) read apart at a glance.
export const CURATOR_THEME = {
  chrome: "#ffffff",
  chromeFg: "#002832",
  accent: "#34a186",
  label: "CURATOR",
} as const;

export type RoleTheme = typeof ADMIN_THEME | typeof CURATOR_THEME;
