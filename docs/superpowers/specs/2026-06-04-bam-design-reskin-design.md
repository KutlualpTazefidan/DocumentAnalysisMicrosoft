# BAM Design Re-skin — Design Spec

> **Status:** Approved direction (2026-06-04). Fidelity = pixel-match to the BAM reference screenshots.
> **Goal:** Re-skin the goldens frontend so it visually belongs to the BAM internal tool family — the same look as the reference app *DIGITALE PRÜFMUSTERBEGLEITKARTE* — while keeping goldens' own information architecture and features unchanged.

## 1. Goal & Non-Goals

**Goal.** Make every goldens surface (login, landing, both shells, the six doc-step pages, the admin/management tables, settings, the curator surfaces, and the placeholders) read as the same product family as the BAM reference: light chrome, BAM brand palette, BAM logo + `GOLDENS` lockup, left icon rail, BAM-style data grids, and a logo'd login.

**Non-goals.** No behavioural / data-model / routing changes. No new features. No backend changes. This is purely a visual + layout-chrome re-skin. Functional logic (auth, queries, mutations, streaming, page-locking, voting, etc.) is preserved exactly.

## 2. Fidelity Decision

Of the three options weighed (brand-reskin-keep-dark / look-alike-light / pixel-match), the user chose **pixel-match (closest to the screenshots)**. Consequences:
- The current **dark** chrome (admin navy `#031E31`, curator emerald `#065f46`) **flips to BAM's light chrome** (white header, light-gray canvas, white cards). Dark backdrop survives **only** on the login screen.
- The current **top-link navigation** is replaced by a **left icon rail** (the reference's primary nav pattern).
- The dark **Recharts navy theme flips to a light** BAM-palette theme.

## 3. Design Tokens (sampled from source images)

Brand colors were sampled pixel-exact from `data/logo/BAM_Logo_RGB.png`; UI neutrals/semantics from the reference screenshots in `data/reference-design/`.

### 3.1 Brand
| Token | Hex | Use |
|---|---|---|
| `bam-navy` | `#002832` | ink, header wordmark, dark login backdrop base |
| `bam-cyan` | `#00aff0` | primary actions, links, active state, focus ring |
| `bam-cyan-hover` | `#0098d4` | primary hover (cyan −12% L) |
| `bam-cyan-active` | `#0082b8` | primary pressed |
| `bam-red` | `#d2001f` | danger / destructive / brand accent |
| `bam-red-hover` | `#a80019` | danger hover |

### 3.2 Neutrals
| Token | Hex | Use |
|---|---|---|
| `canvas` | `#e7e7e7` | app background |
| `surface` | `#ffffff` | cards, header, table base |
| `border` | `#dbdbdb` | card/table borders, dividers |
| `border-strong` | `#c7c7c7` | input borders |
| `ink` | `#333333` | body text |
| `ink-muted` | `#6b6b6b` | secondary text, captions |
| `rail` | `#f4f4f4` | left icon-rail background |
| `backdrop` | `#1f1f1f` | login page backdrop |

### 3.3 Semantic (status rows, badges, charts)
| Token | Hex (fg / fill) | Use |
|---|---|---|
| `success` | `#006d00` / `#ceeccc` | done / ok |
| `warning` | `#8a6100` / `#ffcb46` | in-progress / attention |
| `danger-status` | `#a80019` / `#ffdad1` | error / blocked / inactive |
| `info` / row-selected | `#0072a3` / `#e5f6ff` | selected & hover row tint (BAM cyan tint) |
| `neutral` | `#333333` / `#ededed` | raw / archived |

Chart categorical palette (pies/bars), sampled from the reference dashboard: `#00aff0`, `#006d00`, `#ffcb46`, `#d2001f`, `#8a589f`, `#34a186`, `#002832`, `#9aa7ad`.

## 4. Typography

Switch the base font stack from `system-ui` to **`Arial, "Helvetica Neue", Helvetica, sans-serif`** — the exact font the BAM reference renders in (Arial is BAM's documented fallback for the licensed Frutiger). No web-font download. The existing `T` type scale in `frontend/src/admin/styles/typography.ts` keeps its sizes; only the family changes (set globally in `globals.css` / Tailwind `fontFamily.sans`). Section titles adopt the reference's **small-caps gray** treatment (`uppercase tracking-wide text-ink-muted text-[11px] font-semibold`) — the existing `T.tinyBold` already matches; reuse it for card titles.

## 5. Component Anatomy

### 5.1 Chrome — `BamHeader` (new shared primitive)
White bar, 48px, 1px bottom border `#dbdbdb` plus a 2px `bam-cyan` hairline accent. Left: BAM mark (zigzag SVG/PNG) + `GOLDENS` uppercase `#002832` (+ small role label). Center: global controls that live in the header today (vLLM control). Right: tenant badge, notification icon, settings icon, and the role pill (Radix `RoleMenu` trigger). Replaces the inline dark headers in `AdminShell`/`CuratorShell`.

### 5.2 Navigation — `IconRail` (new shared primitive)
48px light vertical rail (`#f4f4f4`), right border `#dbdbdb`. Monochrome icons (`#6b6b6b`), active item = `bam-cyan` icon + 2px left cyan indicator + white pill. Carries the section nav currently in the admin header (Dokumente / Kuratoren / Fachbereiche / Pipelines / Übersicht) and the curator nav (Meine Dokumente). Tooltips on hover for labels.

### 5.3 Surfaces
Canvas `#e7e7e7`. Cards = `bg-white border border-[#dbdbdb] rounded` with a small-caps gray title row. The dark `bg-navy-800` chart/metric cards become white cards. Provenienz ReactFlow canvas and the extract/synthesise reader panes go to light surfaces.

### 5.4 Data grids — `DataTable` (new shared primitive)
Dense rows; header row `#f4f4f4` with `ink-muted` small-caps labels; **zebra** body (`#ffffff` / `#e5f6ff`); hover/selected = `#e5f6ff` with a left cyan bar; optional **semantic row tint** by status (success/warning/danger fills above). Compact icon action column. Wraps the inbox, curators, tenants, doc-curators tables and any future grids.

### 5.5 Forms
Inputs: `bg-white border border-[#c7c7c7] rounded`, optional left icon slot (person/lock), `focus:ring-2 focus:ring-bam-cyan`. Buttons via `globals.css`: `.btn-primary` = `bg-bam-cyan text-white hover:bg-bam-cyan-hover`; `.btn-danger` = `bg-bam-red`; `.btn-secondary` = white + `#c7c7c7` border.

### 5.6 Login (`LoginForm` + `/login` + landing modal)
Centered white card (`max-w-sm`, `rounded`, soft shadow) on a `#1f1f1f` backdrop. BAM logo on top, `GOLDENS` uppercase title, icon-prefixed username/password fields, eye toggle, full-width cyan button, and an amber dev-environment warning banner (`bg-[#fff8e1] border-l-4 border-[#ffcb46]`). Credentials/legacy-token tabs preserved.

### 5.7 Charts (`RechartsNavyTheme` → `RechartsBamTheme`)
Light card bg `#ffffff`, text `#333333`, grid `#dbdbdb`, accent `bam-cyan`, success/warn/danger as above, categorical palette from §3.3. Same context-provider API so chart components need no structural change.

### 5.8 Badges (`StatusBadge`)
Re-map the 7 tones to the BAM semantic fills (§3.3) — same component, new color map.

## 6. Component Architecture & Blast Radius

~80% of the visual change lands in **6 existing token surfaces**:
1. `frontend/tailwind.config.js` — replace `navy`/`brand`/`danger`/`chrome2` with the BAM token scales (§3).
2. `frontend/src/shell/shared/ColorThemes.ts` — `ADMIN_THEME`/`CURATOR_THEME` become light + role-accent only.
3. `frontend/src/admin/components/charts/RechartsNavyTheme.tsx` → BAM light palette.
4. `frontend/src/styles/globals.css` — `.btn-*`/`.input` recolor + Arial family + small-caps title util.
5. `frontend/src/admin/styles/typography.ts` — family note (sizes unchanged).
6. `frontend/src/admin/components/StatusBadge.tsx` — tone→BAM color map.

Plus **3 new shared primitives**: `BamHeader`, `IconRail`, `DataTable` (under `frontend/src/shell/` and `frontend/src/shared/components/`), then **per-surface application** to wire shells to header+rail and tables to `DataTable`.

## 7. Role Differentiation

Today admin vs curator is signalled by whole-chrome recolor (navy vs emerald). In the single-identity BAM look that's gone. Replace with: identical white header for both; role shown via (a) the **role pill color** — `ADMIN` = `bam-cyan`, `CURATOR` = `bam-navy` — and (b) **which icons appear in the rail**. The `ColorThemes.ts` `accent` field is retasked from chrome bg to pill accent.

## 8. Per-Surface Application Plan (all 19 surfaces)

**Chrome (3):** `AdminShell`, `CuratorShell` → `BamHeader` + `IconRail`; landing `Landing.tsx` → BAM hero on light + logo'd login modal.

**Auth (1):** `LoginForm` + `/login` route → §5.6 login.

**Doc-step pages (6):** `inbox` (→ `DataTable`), `extract` (light reader/editor panes + light box overlay chrome), `Synthesise` (light preview + question cards), `Comparison` (light panes, chunk cards, score bars), `Provenienz` (light ReactFlow canvas + node tiles), `Statistics` (→ light `RechartsBamTheme` cards). `DocStepTabs` → light tab bar, active = cyan underline.

**Management tables (4):** `Curators`, `TenantsAdmin`, `DocCurators`, → `DataTable`; create/edit modals → BAM modal style.

**Misc (5):** `Settings` (light account card), curator `Docs` (light list), curator `DocPage` (light reader + form), placeholders `Dashboard`/`Pipelines`/`CuratorActivity` (light empty-state cards).

Shared components touched in passing: `RoleMenu`, `Pagination`, `Toaster`, `Spinner`, `StageIndicator`, `LlmTopBarControl`, `QuestionList`, modals — recolor to BAM tokens.

## 9. Verification

- `frontend` `tsc --noEmit`, `eslint`, and the vitest suite stay green (re-skin must not break tests; update only snapshot/color assertions that legitimately change).
- Run the dev app and **screenshot each surface**, comparing side-by-side to the reference screenshots — the acceptance bar is "reads as the same family."
- No backend or API changes, so backend smoke is unaffected.

## 10. Out of Scope

- Pixel-identical replication of the reference's *content* (its tables/forms are a different domain). We match the **design language**, not the data.
- Dark-mode toggle. Single light theme only (login backdrop aside).
- The BAM licensed font (Frutiger). Arial fallback is used deliberately.
- Acting on the `feat/ui-walkthrough` audit salvage items — tracked separately.

## 11. Decision Log

- **DR-1** Fidelity = pixel-match (user, 2026-06-04). → light flip, left rail, light charts.
- **DR-2** Lockup = BAM mark + `GOLDENS` uppercase, single title slot (closest to reference's single uppercase app-title).
- **DR-3** Font = Arial/Helvetica system stack (matches screenshots, no web-font).
- **DR-4** Role differentiation via role-pill color + rail icons, not chrome color.
- **DR-5** Tokens sampled pixel-exact from the logo + screenshots, not eyeballed.
