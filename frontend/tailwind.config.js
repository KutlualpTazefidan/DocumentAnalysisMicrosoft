export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // BAM corporate face is Frutiger (licensed); Arial is its documented
        // fallback and what the reference screenshots actually render in.
        sans: ["Arial", '"Helvetica Neue"', "Helvetica", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // ── BAM brand — sampled pixel-exact from data/logo/BAM_Logo_RGB.png ──
        bam: {
          navy: "#002832", // ink, wordmark, dark login backdrop base
          cyan: "#00aff0", // primary actions, links, active, focus ring
          "cyan-600": "#0098d4", // hover
          "cyan-700": "#0082b8", // active / pressed
          red: "#d2001f", // danger base
          "red-700": "#a80019", // danger hover
        },
        // ── Light UI neutrals — sampled from the reference screenshots ──
        canvas: "#e7e7e7", // app background
        line: "#dbdbdb", // card / table borders, dividers
        line2: "#c7c7c7", // input borders
        rail: "#f4f4f4", // left icon-rail background
        backdrop: "#1f1f1f", // login page backdrop
        rowsel: "#e5f6ff", // selected / hover row tint (BAM cyan tint)
        ink: {
          DEFAULT: "#333333", // body text (not pure black)
          muted: "#6b6b6b", // secondary text / captions
        },
        // ── Semantic status (rows, badges, charts) ──
        ok: { DEFAULT: "#006d00", fill: "#ceeccc" },
        warn: { DEFAULT: "#8a6100", fill: "#ffcb46" },
        bad: { DEFAULT: "#a80019", fill: "#ffdad1" },
        // ── Brand action palette — repointed to BAM cyan (was #1E7EB2).
        // .btn-primary / links / focus ring read these; the hue swap
        // BAM-ifies every CTA without touching call sites. ──
        brand: {
          500: "#00aff0",
          600: "#0098d4",
          700: "#0082b8",
        },
        // ── Destructive palette — repointed to BAM red (was #AE1B25). ──
        danger: {
          500: "#d2001f",
          700: "#a80019",
        },
        // ── Legacy dark-chrome scales — retained for surfaces not yet
        // migrated to the BAM light theme (charts, extract/provenienz
        // reader panes). Removed once those waves land. ──
        navy: {
          200: "#cfe6f5",
          300: "#8fbfdb",
          500: "#5a9ec9",
          600: "#1E7EB2",
          700: "#0a2e47",
          800: "#031E31",
          900: "#021727",
        },
        chrome2: {
          DEFAULT: "#576977",
          500: "#6d7f8d",
          600: "#576977",
          700: "#455563",
          800: "#3a4753",
          900: "#2b3640",
        },
      },
    },
  },
  plugins: [],
};
