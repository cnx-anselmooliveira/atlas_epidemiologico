// @ts-check
import eslintPluginAstro from 'eslint-plugin-astro';
import tseslint from 'typescript-eslint';

// Código de src/lib/server/ só roda no servidor (fala com o backend pela URL interna).
// Scripts que vão para o navegador não podem importá-lo.
const somenteServidor = {
	patterns: [
		{
			group: ['**/lib/server', '**/lib/server/*', 'astro:env/server'],
			message: 'Código de servidor não pode ir para o navegador (URL interna do backend).',
		},
	],
};

export default [
	{ ignores: ['dist/', '.astro/', 'node_modules/', 'design-system/', 'playwright-report/', 'test-results/'] },
	...tseslint.configs.recommended,
	...eslintPluginAstro.configs.recommended,
	{ rules: { '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }] } },
	{
		// <script> dos componentes .astro (arquivos virtuais) e módulos de cliente
		files: ['**/*.astro/*.js', '**/*.astro/*.ts', 'src/scripts/**/*.{js,ts}'],
		rules: { 'no-restricted-imports': ['error', somenteServidor] },
	},
];
