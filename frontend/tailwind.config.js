export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        // Chrome scale — derived from ADMIN_THEME.chrome (#031E31).
        // navy-800 is the primary chrome bg; lighter shades = text/borders
        // on that dark backdrop; darker = deeper chrome variant.
        navy: {
          200: "#cfe6f5", // light text on dark chrome (was blue-200)
          300: "#8fbfdb", // dimmed-but-readable text (replaces opacity-fix
                          // for disabled DocStepTabs which read text-navy-500/opacity-50
                          // — see audit; navy-500 alone is too dim on the new chrome)
          500: "#5a9ec9", // mid — active hint text
          600: "#1E7EB2", // brand blue — accent / active state on chrome
          700: "#0a2e47", // subtle border / hover-darker than chrome bg
          800: "#031E31", // ADMIN_THEME.chrome — primary chrome bg
          900: "#021727", // deepest chrome variant
        },
        // Brand action palette — the single blue for primary CTAs, links,
        // and the focus ring. Use these (not raw `blue-*`) when the surface
        // is white/light; navy-600 for the same hue on the chrome.
        brand: {
          500: "#1E7EB2",
          600: "#196590", // ~8% darker — hover
          700: "#154f72", // ~16% darker — active / pressed
        },
        // Destructive palette — base + permanent destructive variant.
        // Use `.btn-danger` for buttons; raw `danger-700` for delete-row
        // text / persistent destructive states (Deaktivieren).
        danger: {
          500: "#AE1B25", // base
          700: "#881A17", // hover / permanent destructive
        },
      },
    },
  },
  plugins: [],
};
