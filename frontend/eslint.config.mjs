import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// v0.8.130 — design-system guardrails (UI audit Phase 1, 4.4). The codemod moved
// every class string onto theme tokens; these keep it that way. They match string
// literals and template parts anywhere, because class strings also live in cn(),
// cva() and constants, not only in className="…". CSS files are checked by
// src/lib/design-guardrails.test.ts, which also proves each pattern here fires.
const RAW_PALETTE =
  "\\b(?:bg|text|border|ring|from|to|via|fill|stroke|outline|divide|decoration|shadow|placeholder|accent|caret)-(?:amber|emerald|green|red|rose|blue|sky|violet|purple|teal|cyan|indigo|yellow|orange|lime|pink|fuchsia|slate|gray|zinc|neutral|stone)-\\d{2,3}\\b";
const MICRO_TYPE = "text-\\[(?:(?:[0-9]|1[01])(?:\\.[0-9]+)?px|0\\.[0-9]+rem)\\]";
const TRANSITION_ALL = "\\btransition-all\\b";
const SCALE_ON_INTERACTION = "\\b(?:hover|active|group-hover|group-active|focus-visible):scale-";
const HEX = "#[0-9a-fA-F]{6}\\b";

const everywhere = (pattern, message) => [
  { selector: `Literal[value=/${pattern}/]`, message },
  { selector: `TemplateElement[value.raw=/${pattern}/]`, message },
];

const designRules = [
  ...everywhere(RAW_PALETTE, "Use a theme token (e.g. bg-warning-soft, text-success-ink, text-muted-foreground, bg-primary/10) instead of a raw Tailwind palette colour; tokens follow all 27 themes."),
  ...everywhere(MICRO_TYPE, "Text below 12px is not allowed; use text-xs."),
  ...everywhere(TRANSITION_ALL, "Name the transitioned properties (transition-colors, transition-opacity, …) instead of transition-all."),
  ...everywhere(SCALE_ON_INTERACTION, "Do not scale on hover or press; use the colour state layers."),
  { selector: `JSXAttribute[name.name='className'] Literal[value=/${HEX}/]`, message: "Use a theme token, not a hex colour, in className." },
  { selector: `JSXAttribute[name.name='className'] TemplateElement[value.raw=/${HEX}/]`, message: "Use a theme token, not a hex colour, in className." },
  { selector: `JSXAttribute[name.name='style'] Literal[value=/${HEX}/]`, message: "Use a CSS variable (var(--primary), …), not a hex colour, in style." },
];

const eslintConfig = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/use-memo": "off",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: [
      "src/**/*.test.{ts,tsx}",
      "src/**/__tests__/**",
      // Data, not UI chrome: the theme catalogue's preview swatches and the brand constants.
      "src/lib/themes/catalog.ts",
      "src/lib/brand.ts",
    ],
    rules: {
      "no-restricted-syntax": ["error", ...designRules],
    },
  },
];

export default eslintConfig;
