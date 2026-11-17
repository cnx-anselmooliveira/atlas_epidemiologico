/// <reference types="vitest/config" />
import { getViteConfig } from 'astro/config';

// Config do Vite do próprio Astro: os testes da Container API renderizam componentes .astro
export default getViteConfig({
	test: {
		include: ['tests/**/*.test.ts', 'mock-backend/**/*.test.ts'],
		environment: 'node',
	},
});
