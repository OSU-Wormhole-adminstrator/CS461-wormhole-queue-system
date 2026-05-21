module.exports = {
  extends: "stylelint-config-standard",
  ignoreFiles: [
    "venv/**",
    ".venv/**",
    "node_modules/**",
    "htmlcov/**",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
    "tests/browser/test-results/**",
    "app/static/vendor/**",
    "app/static/dist/**",
    "app/static/**/*.min.css",
  ],
  rules: {
    "no-duplicate-selectors": true,
    "color-no-invalid-hex": true,
    "comment-empty-line-before": null,
    "at-rule-no-unknown": [
      true,
      {
        ignoreAtRules: [
          "tailwind",
          "apply",
          "layer",
          "screen",
          "config",
          "theme",
          "variants",
          "responsive",
          "view-transition",
        ],
      },
    ],
  },
};