// @ts-check
import node from '@astrojs/node';
import { defineConfig, envField } from 'astro/config';

// SSR com o servidor Node standalone: o navegador só fala com este servidor, e a URL do
// backend é lida em runtime (astro:env, context server/secret), nunca embutida no bundle.
export default defineConfig({
	output: 'server',
	adapter: node({ mode: 'standalone' }),
	site: process.env.PUBLIC_SITE_URL,
	env: {
		schema: {
			API_INTERNAL_URL: envField.string({ context: 'server', access: 'secret', url: true }),
			BACKEND_TIMEOUT_MS: envField.number({ context: 'server', access: 'secret', default: 8000, int: true, gt: 0 }),
			PAGE_CACHE_SECONDS: envField.number({ context: 'server', access: 'secret', default: 300, int: true, gt: -1 }),
			PUBLIC_SITE_URL: envField.string({ context: 'client', access: 'public', url: true, optional: true }),
		},
		// segredos não são validados no build (a imagem não conhece o ambiente): scripts/start.mjs
		// confere API_INTERNAL_URL na subida, e o astro:env valida ao ler
	},
});
