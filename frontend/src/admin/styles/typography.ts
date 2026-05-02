// frontend/src/admin/styles/typography.ts
//
// Single source of truth for font sizes used across the admin UI.
// Every element that wants a size class imports from here — never use
// raw `text-xs`/`text-sm`/`text-[Npx]` outside this file.
//
// Tier 1 — used everywhere as the default UI text:
//   T.body  (12px — buttons, labels, inputs, sidebar default)
//
// Tier 2 — supporting sizes:
//   T.tiny  (11px — legend swatches, inline secondary metadata)
//   T.heading (13px semibold — section headings like "Properties")
//   T.mono  (12px monospace — bbox values, conf numbers)
//
// Tier 3 — page-level (used in empty-state cards / route headers):
//   T.cardTitle (16px semibold)
//   T.cardSubtle (12px slate-500 — descriptive line under a card title)

export const T = {
  body: "text-[12px]",
  bodyMuted: "text-[12px] text-slate-500",
  bodyMedium: "text-[12px] font-medium",
  tiny: "text-[11px]",
  tinyMuted: "text-[11px] text-slate-500",
  tinyBold: "text-[11px] font-semibold uppercase tracking-wide text-slate-500",
  heading: "text-[13px] font-semibold",
  mono: "text-[12px] font-mono",
  cardTitle: "text-[16px] font-semibold",
  cardSubtle: "text-[12px] text-slate-500",
} as const;
