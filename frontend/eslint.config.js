// Flat config (ESLint v9). Replaces the legacy .eslintrc — TypeScript + React.
import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/**", "coverage/**", "tests/walkthrough/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser, ...globals.node, ...globals.es2022 },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react,
      "react-hooks": reactHooks,
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...js.configs.recommended.rules,
      // turn off core rules that TypeScript supersedes (no-undef, no-unused-vars, …)
      ...tsPlugin.configs["flat/eslint-recommended"].rules,
      ...tsPlugin.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...react.configs["jsx-runtime"].rules, // React 17+ automatic JSX runtime
      ...reactHooks.configs.recommended.rules,
      "react/prop-types": "off", // types come from TypeScript
      // Literal quotes in JSX text render fine; noisy with German „…" typography.
      "react/no-unescaped-entities": "off",
      // Honor the leading-underscore convention for intentionally-unused names.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
    },
  },
];
