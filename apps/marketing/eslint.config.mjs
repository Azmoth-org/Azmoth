import { createRequire } from 'module';
import nextPlugin from '@next/eslint-plugin-next';
import i18next from 'eslint-plugin-i18next';

const require = createRequire(import.meta.url);

// Load dependencies
const tsEslint = require('typescript-eslint');
const reactHooks = require('eslint-plugin-react-hooks');
const globals = require('globals');

// NOTE: eslint-plugin-react, eslint-plugin-jsx-a11y, and eslint-plugin-import
// are intentionally omitted — their latest versions only support ESLint ^9,
// while Next.js 16 ships ESLint 10 (context.getFilename/context.getScope removed).
// Upstream issue tracking: eslint-plugin-react#3895, jsx-a11y#1020.

const eslintConfig = [
  // Base — browser/node globals + files to check
  {
    name: 'silkdev/base',
    files: ['**/*.{js,jsx,mjs,ts,tsx,mts,cts}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.es2025 },
    },
    linterOptions: {
      reportUnusedDisableDirectives: true,
    },
  },

  // Next.js core web vitals rules
  nextPlugin.configs['core-web-vitals'],

  // TypeScript recommended rules
  ...tsEslint.configs.recommended,

  // React hooks plugin (compatible with ESLint 10)
  {
    name: 'silkdev/react-hooks',
    plugins: {
      'react-hooks': reactHooks,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },

  // i18n — flag untranslated literal strings
  i18next.configs['flat/recommended'],
  {
    name: 'silkdev/i18n',
    rules: {
      'i18next/no-literal-string': ['error', {
        attribute: { 'aria-label': true },
      }],
    },
  },

  // Custom rules
  {
    name: 'silkdev/custom',
    rules: {
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },

  // Global ignores — component library / generated files are not i18n-audited
  {
    name: 'silkdev/ignores',
    ignores: [
      '.next/**',
      'out/**',
      'build/**',
      'node_modules/**',
      'next-env.d.ts',
      'src/components/ui/**',
      'src/components/assistant-ui/**',
      'src/lib/utils.ts',
    ],
  },
];

export default eslintConfig;
