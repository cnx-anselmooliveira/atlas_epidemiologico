/// <reference types="vitest/config" />
import { getViteConfig } from 'astro/config';

// O astro:env lê e valida as variáveis de servidor ao carregar a config: os testes de página
// sobem o backend mock exatamente nesta URL (tests/paginas.test.ts).
process.env.API_INTERNAL_URL = 'http://127.0.0.1:8799';
process.env.BACKEND_TIMEOUT_MS = '2000';

// Config do Vite do próprio Astro: os testes da Container API renderizam componentes .astro
export default getViteConfig({
	test: {
		include: ['tests/**/*.test.ts', 'mock-backend/**/*.test.ts'],
		environment: 'node',
	},
});
