// Desenvolvimento sem backend real: sobe o backend mock e o `astro dev` apontando para ele.
//   npm run dev:mock        (mock em MOCK_PORT, padrão 8787; site em http://localhost:4321)
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { criarServidor } from '../mock-backend/server.mjs';

const porta = Number(process.env.MOCK_PORT ?? 8787);
const mock = criarServidor().listen(porta, '127.0.0.1', () => {
	console.log(`[mock-backend] http://127.0.0.1:${porta}`);
	const cli = fileURLToPath(new URL('../node_modules/astro/bin/astro.mjs', import.meta.url));
	const astro = spawn(process.execPath, [cli, 'dev', ...process.argv.slice(2)], {
		stdio: 'inherit',
		env: { ...process.env, API_INTERNAL_URL: `http://127.0.0.1:${porta}` },
	});
	astro.on('exit', (codigo) => {
		mock.close();
		process.exit(codigo ?? 0);
	});
});
