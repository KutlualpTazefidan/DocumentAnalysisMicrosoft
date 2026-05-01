export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        navy: {
          // Derived from ADMIN_THEME.chrome (#1e3a8a). navy-800 is the primary
          // chrome colour; lighter shades are used for text/borders on that
          // dark backdrop; darker shades for hover/active states.
          200: "#bfdbfe", // near blue-200 — readable light text on dark bg
          500: "#3b82f6", // blue-500 equivalent
          600: "#2563eb", // blue-600 — active/hover accent
          700: "#1d4ed8", // blue-700 — border / subtle bg on chrome
          800: "#1e3a8a", // blue-900 — ADMIN_THEME.chrome
          900: "#172554", // deeper — darkest chrome variant
        },
      },
    },
  },
  plugins: [],
};
