import { defineConfig, devices } from '@playwright/test';

// Smoke de ponta a ponta contra o build de produção (scripts/start.mjs) e o backend mock.
// O build é feito antes (npm run build); aqui só sobem os dois servidores.
const MOCK = 'http://127.0.0.1:8788';
const SITE = 'http://127.0.0.1:4329';

export default defineConfig({
	testDir: 'e2e',
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	reporter: process.env.CI ? 'github' : 'list',
	use: { baseURL: SITE, trace: 'retain-on-failure' },
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: [
		{
			command: 'node mock-backend/server.mjs',
			env: { MOCK_PORT: '8788' },
			url: `${MOCK}/health`,
			reuseExistingServer: !process.env.CI,
		},
		{
			command: 'node scripts/start.mjs',
			env: { API_INTERNAL_URL: MOCK, HOST: '127.0.0.1', PORT: '4329' },
			url: `${SITE}/healthz`,
			reuseExistingServer: !process.env.CI,
		},
	],
});
