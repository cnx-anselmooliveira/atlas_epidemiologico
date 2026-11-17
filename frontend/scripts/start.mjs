// Inicia o servidor de produção (dist/server/entry.mjs) só se a configuração de runtime
// estiver válida. O astro:env valida as variáveis de servidor quando uma página as lê pela
// primeira vez; aqui a falha acontece na subida, antes de receber tráfego.
//   node scripts/start.mjs

function falhar(mensagem) {
	console.error(`[atlas] configuração inválida: ${mensagem}`);
	process.exit(1);
}

const url = process.env.API_INTERNAL_URL;
if (!url) falhar('API_INTERNAL_URL não definida (URL interna do backend, ex.: http://backend:8000)');
try {
	new URL(url);
} catch {
	falhar(`API_INTERNAL_URL não é uma URL: ${url}`);
}
for (const nome of ['BACKEND_TIMEOUT_MS', 'PAGE_CACHE_SECONDS']) {
	const valor = process.env[nome];
	if (valor !== undefined && !/^\d+$/.test(valor)) falhar(`${nome} deve ser um inteiro: ${valor}`);
}

await import('../dist/server/entry.mjs');
