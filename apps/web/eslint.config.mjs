import nextVitals from "eslint-config-next/core-web-vitals";
import unusedImports from "eslint-plugin-unused-imports";

const eslintConfig = [
  ...nextVitals,
  {
    plugins: {
      "unused-imports": unusedImports,
    },
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "unused-imports/no-unused-imports": "error",
      "unused-imports/no-unused-vars": [
        "warn",
        {
          "vars": "all",
          "varsIgnorePattern": "^_",
          "args": "after-used",
          "argsIgnorePattern": "^_"
        }
      ]
    }
  }
];

export default eslintConfig;
